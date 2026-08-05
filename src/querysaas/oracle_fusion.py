"""QuerySaaS Oracle Fusion connector and DuckDB synchronization engine."""


import base64
import getpass
import gzip
import html
import re
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import StringIO
from urllib.parse import urlparse
from xml.sax.saxutils import escape

import duckdb
import pandas as pd
import requests


REQUEST_TIMEOUT = 300
VERIFY_SSL = True

BIP_UPLOAD_PATH = "/~{{username}}/DataSyncTool"
BIP_EXECUTION_REPORT_PATH = "/~{{username}}/DataSyncTool/v1/csv.xdo"


from .xdrz_payload import BIP_XDRZ_BASE64

def normalize_report_url(url):
    if not isinstance(url, str) or not url.strip():
        raise ValueError("Oracle Fusion URL cannot be empty.")

    parsed = urlparse(html.unescape(url.strip()))

    if not parsed.scheme or not parsed.netloc:
        raise ValueError(
            "Use a complete Fusion URL such as "
            "https://example.fa.ocs.oraclecloud.com"
        )

    return (
        f"{parsed.scheme}://{parsed.netloc}"
        "/xmlpserver/services/ExternalReportWSSService"
    )


def replace_username(path, username):
    return re.sub(
        r"\{\{username\}\}",
        lambda _: username,
        path,
        flags=re.IGNORECASE,
    )


def build_auth_header(username, credential, use_sso=False):
    if not username or not username.strip():
        raise ValueError("Oracle Fusion username cannot be empty.")

    if not credential:
        raise ValueError("Password or bearer token cannot be empty.")

    if use_sso:
        return f"Bearer {credential}"

    raw_credentials = f"{username}:{credential}".encode("utf-8")
    encoded_credentials = base64.b64encode(raw_credentials).decode("ascii")
    return f"Basic {encoded_credentials}"


def gzip_base64(sql):
    if not isinstance(sql, str) or not sql.strip():
        raise ValueError("SQL query cannot be empty.")

    compressed = gzip.compress(
        sql.encode("utf-8"),
        compresslevel=9,
        mtime=0,
    )

    return base64.b64encode(compressed).decode("ascii")


def local_name(tag):
    return tag.split("}")[-1]


def extract_soap_fault(response_text):
    if not response_text:
        return None

    try:
        root = ET.fromstring(response_text)
    except ET.ParseError:
        return None

    for node in root.iter():
        if local_name(node.tag).lower() == "faultstring" and node.text:
            return html.unescape(node.text.strip())

    for node in root.iter():
        if local_name(node.tag).lower() != "fault":
            continue

        for child in node.iter():
            if local_name(child.tag).lower() == "text" and child.text:
                return html.unescape(child.text.strip())

    return None


def extract_report_bytes(response_text):
    """
    Extract reportBytes from the BI Publisher SOAP response.

    An existing but empty reportBytes element is treated as a valid
    no-data response and returns an empty string.
    """
    try:
        root = ET.fromstring(response_text)
    except ET.ParseError as error:
        raise RuntimeError(
            "Oracle Fusion returned invalid SOAP XML.\n"
            f"Response: {response_text[:1000]}"
        ) from error

    for node in root.iter():
        if local_name(node.tag).lower() != "reportbytes":
            continue

        if node.text is None or not node.text.strip():
            return ""

        report_base64 = "".join(node.text.split())

        try:
            base64.b64decode(report_base64, validate=True)
        except Exception as error:
            raise RuntimeError(
                "The reportBytes value is not valid Base64."
            ) from error

        return report_base64

    raise RuntimeError(
        "The Oracle Fusion SOAP response does not contain reportBytes."
    )

def validate_xdrz():
    if (
        not BIP_XDRZ_BASE64
        or "PASTE_YOUR_EXISTING" in BIP_XDRZ_BASE64
    ):
        raise ValueError(
            "Paste the complete Base64 XDRZ value into "
            "BIP_XDRZ_BASE64 before connecting."
        )

    try:
        archive = base64.b64decode(
            BIP_XDRZ_BASE64,
            validate=True,
        )
    except Exception as error:
        raise ValueError(
            "The embedded XDRZ value is not valid Base64."
        ) from error

    if not archive.startswith(b"PK"):
        raise ValueError(
            "The embedded content is not a ZIP-based XDRZ archive."
        )

    return len(archive)



def provision_bip_report(
        fusion_url,
        username,
        auth_header,
        timeout=REQUEST_TIMEOUT,
        verify_ssl=VERIFY_SSL,
    ):
        validate_xdrz()

        endpoint = normalize_report_url(fusion_url)
        upload_path = replace_username(BIP_UPLOAD_PATH, username)

        payload = f"""
    <soap:Envelope
        xmlns:soap="http://www.w3.org/2003/05/soap-envelope"
        xmlns:pub="http://xmlns.oracle.com/oxp/service/PublicReportService">
        <soap:Header/>
        <soap:Body>
            <pub:uploadReportObject>
                <pub:reportObjectAbsolutePathURL>{escape(upload_path)}</pub:reportObjectAbsolutePathURL>
                <pub:objectType>xdrz</pub:objectType>
                <pub:objectZippedData>{BIP_XDRZ_BASE64}</pub:objectZippedData>
            </pub:uploadReportObject>
        </soap:Body>
    </soap:Envelope>
    """.strip()

        try:
            response = requests.post(
                endpoint,
                headers={
                    "Content-Type": "application/soap+xml;charset=UTF-8",
                    "Authorization": auth_header,
                },
                data=payload.encode("utf-8"),
                timeout=timeout,
                verify=verify_ssl,
            )
        except requests.RequestException as error:
            raise RuntimeError(
                f"Oracle Fusion connection failed: {error}"
            ) from error

        response_text = response.text or ""
        fault_message = extract_soap_fault(response_text)
        combined_response = (
            response_text + " " + (fault_message or "")
        ).lower()

        if any(
            indicator in combined_response
            for indicator in (
                "alreadyexists",
                "already exists",
                "object already exists",
            )
        ):
            return "exists"

        if response.ok and not fault_message:
            return "created"

        error_message = (
            fault_message
            or f"HTTP {response.status_code} {response.reason}"
        )

        raise RuntimeError(
            "BIP provisioning failed: "
            f"{error_message}\n"
            f"Response: {response_text[:1000]}"
        )



def execute_query(
        fusion_url,
        username,
        auth_header,
        raw_sql,
        report_path=BIP_EXECUTION_REPORT_PATH,
        timeout=REQUEST_TIMEOUT,
        verify_ssl=VERIFY_SSL,
    ):
        endpoint = normalize_report_url(fusion_url)
        final_report_path = replace_username(report_path, username)
        encoded_sql = gzip_base64(raw_sql)

        envelope = f"""
    <soap:Envelope
        xmlns:soap="http://www.w3.org/2003/05/soap-envelope"
        xmlns:pub="http://xmlns.oracle.com/oxp/service/PublicReportService">
        <soap:Header/>
        <soap:Body>
            <pub:runReport>
                <pub:reportRequest>
                    <pub:parameterNameValues>
                        <pub:item>
                            <pub:name>P_B64_CONTENT</pub:name>
                            <pub:values>
                                <pub:item>{escape(encoded_sql)}</pub:item>
                            </pub:values>
                        </pub:item>
                    </pub:parameterNameValues>
                    <pub:reportAbsolutePath>{escape(final_report_path)}</pub:reportAbsolutePath>
                    <pub:attributeFormat>xml</pub:attributeFormat>
                    <pub:sizeOfDataChunkDownload>-1</pub:sizeOfDataChunkDownload>
                </pub:reportRequest>
            </pub:runReport>
        </soap:Body>
    </soap:Envelope>
    """.strip()

        try:
            response = requests.post(
                endpoint,
                headers={
                    "Content-Type": "application/soap+xml;charset=UTF-8",
                    "Authorization": auth_header,
                },
                data=envelope.encode("utf-8"),
                timeout=timeout,
                verify=verify_ssl,
            )
        except requests.RequestException as error:
            raise RuntimeError(
                f"Oracle Fusion query request failed: {error}"
            ) from error

        response_text = response.text or ""

        if not response.ok and response.status_code != 500:
            raise RuntimeError(
                f"Oracle Fusion returned HTTP {response.status_code}.\n"
                f"Response: {response_text[:1000]}"
            )

        fault_message = extract_soap_fault(response_text)

        if fault_message:
            raise RuntimeError(
                f"Oracle Fusion SOAP fault: {fault_message}"
            )

        if not response.ok:
            raise RuntimeError(
                f"Oracle Fusion returned HTTP {response.status_code}.\n"
                f"Response: {response_text[:1000]}"
            )

        return {
            "report_base64": extract_report_bytes(response_text),
            "soap_response": response_text,
            "http_status": response.status_code,
            "report_path": final_report_path,
            "sql": raw_sql,
        }



class FusionConnection:
    def __init__(
        self,
        url,
        username,
        password,
        use_sso=False,
        provision=True,
        report_path=BIP_EXECUTION_REPORT_PATH,
        timeout=REQUEST_TIMEOUT,
        verify_ssl=VERIFY_SSL,
    ):
        self.url = url
        self.username = username
        self.report_path = report_path
        self.timeout = timeout
        self.verify_ssl = verify_ssl
        self.closed = False

        self.auth_header = build_auth_header(
            username=username,
            credential=password,
            use_sso=use_sso,
        )

        self.provision_status = None

        if provision:
            self.provision_status = provision_bip_report(
                fusion_url=self.url,
                username=self.username,
                auth_header=self.auth_header,
                timeout=self.timeout,
                verify_ssl=self.verify_ssl,
            )

        print("Oracle Fusion connection established.")

        if self.provision_status:
            print("BIP provision status:", self.provision_status)

    def _assert_open(self):
        if self.closed:
            raise RuntimeError("The Oracle Fusion connection is closed.")

    @staticmethod
    def _validate_identifier(identifier, label="identifier"):
        if not isinstance(identifier, str) or not re.fullmatch(
            r"[A-Za-z_][A-Za-z0-9_$#]*",
            identifier.strip(),
        ):
            raise ValueError(
                f"Invalid {label}. Use letters, numbers, underscores, $, or #; "
                "the first character must be a letter or underscore."
            )
        return identifier.strip()

    @classmethod
    def _normalize_primary_keys(cls, primary_key):
        if primary_key is None:
            return []

        if isinstance(primary_key, str):
            primary_keys = [primary_key]
        else:
            primary_keys = list(primary_key)

        if not primary_keys:
            raise ValueError("primary_key cannot be an empty list.")

        return [
            cls._validate_identifier(column, "primary-key column")
            for column in primary_keys
        ]

    @staticmethod
    def _xml_to_dataframe(report_base64, all_varchar=False):
        """
        Convert Base64-encoded BI Publisher XML into a DataFrame.

        Empty reportBytes, empty decoded XML, and XML documents without
        row data return an empty DataFrame instead of raising an error.
        """
        if report_base64 is None or not str(report_base64).strip():
            return pd.DataFrame()

        try:
            xml_bytes = base64.b64decode(
                report_base64,
                validate=True,
            )
        except Exception as error:
            raise RuntimeError(
                "The Fusion report result is not valid Base64."
            ) from error

        if not xml_bytes or not xml_bytes.strip():
            return pd.DataFrame()

        try:
            xml_text = xml_bytes.decode("utf-8-sig")
        except UnicodeDecodeError as error:
            raise RuntimeError(
                "Unable to decode the Fusion report result as UTF-8 XML."
            ) from error

        if not xml_text.strip():
            return pd.DataFrame()

        try:
            xml_root = ET.fromstring(xml_text)
        except ET.ParseError as error:
            raise RuntimeError(
                "The decoded Fusion result is not valid XML.\n"
                f"XML preview: {xml_text[:1000]}"
            ) from error

        # Examples: <DATA_DS/> or <DATA_DS></DATA_DS>
        if len(xml_root) == 0:
            return pd.DataFrame()

        has_result_data = False

        for row_element in xml_root:
            if len(row_element) > 0:
                has_result_data = True
                break

            if row_element.text and row_element.text.strip():
                has_result_data = True
                break

        if not has_result_data:
            return pd.DataFrame()

        try:
            dataframe = pd.read_xml(
                StringIO(xml_text),
                parser="etree",
            )
        except ValueError as error:
            error_text = str(error).lower()
            empty_messages = (
                "xpath does not return any nodes",
                "no nodes",
                "no elements",
            )

            if any(message in error_text for message in empty_messages):
                return pd.DataFrame()

            raise RuntimeError(
                "Unable to convert the Fusion XML result into a DataFrame.\n"
                f"XML preview: {xml_text[:1000]}"
            ) from error
        except Exception as error:
            raise RuntimeError(
                "Unable to convert the Fusion XML result into a DataFrame.\n"
                f"XML preview: {xml_text[:1000]}"
            ) from error

        if dataframe is None:
            dataframe = pd.DataFrame()

        if all_varchar and not dataframe.empty:
            for column in dataframe.columns:
                dataframe[column] = dataframe[column].astype("string")

        return dataframe

    def executequery(self, sql, as_dataframe=True, all_varchar=False):
        """
        Execute SQL through Fusion BIP.

        A successful query with no rows returns an empty DataFrame.
        """
        self._assert_open()

        if not isinstance(sql, str) or not sql.strip():
            raise ValueError("SQL query cannot be empty.")

        result = execute_query(
            fusion_url=self.url,
            username=self.username,
            auth_header=self.auth_header,
            raw_sql=sql,
            report_path=self.report_path,
            timeout=self.timeout,
            verify_ssl=self.verify_ssl,
        )

        if not as_dataframe:
            return result

        dataframe = self._xml_to_dataframe(
            report_base64=result.get("report_base64"),
            all_varchar=all_varchar,
        )

        if dataframe.empty:
            print("Query completed successfully: no rows returned.")
            return dataframe

        print(
            f"Query completed: {len(dataframe):,} rows x "
            f"{len(dataframe.columns):,} columns."
        )

        return dataframe

    @staticmethod
    def _convert_all_columns_to_string(dataframe):
        """Convert all result columns to pandas string dtype."""
        if dataframe is None:
            return pd.DataFrame()

        dataframe = dataframe.copy()

        for column in dataframe.columns:
            dataframe[column] = dataframe[column].astype("string")

        return dataframe

    @classmethod
    def _build_copy_filter(
        cls,
        last_update_date=None,
        last_update_date_column="LAST_UPDATE_DATE",
        additional_where=None,
    ):
        """Build the trusted incremental and additional source predicate."""
        conditions = []

        if last_update_date is not None:
            last_update_date_column = cls._validate_identifier(
                last_update_date_column,
                "last-update-date column",
            )

            try:
                parsed_date = pd.to_datetime(
                    last_update_date,
                    errors="raise",
                    utc=True,
                )
            except Exception as error:
                raise ValueError(
                    "Invalid last_update_date. Use YYYY-MM-DD or "
                    "YYYY-MM-DD HH:MM:SS."
                ) from error

            normalized_date = parsed_date.strftime("%Y-%m-%d %H:%M:%S")

            conditions.append(
                f"{last_update_date_column} >= "
                f"TO_TIMESTAMP('{normalized_date}', "
                f"'YYYY-MM-DD HH24:MI:SS')"
            )

        if additional_where is not None:
            additional_where = str(additional_where).strip()

            if additional_where:
                if ";" in additional_where:
                    raise ValueError(
                        "additional_where must be a predicate only and cannot "
                        "contain a semicolon."
                    )

                conditions.append(f"({additional_where})")

        if not conditions:
            return ""

        return " WHERE " + " AND ".join(conditions)

    def _rowid_is_available(self, table_name):
        """Return True when Oracle ROWID can be selected from the source."""
        test_sql = f"""
            SELECT
                ROWIDTOCHAR(t.ROWID) AS SOURCE_ROWID
            FROM
                {table_name} t
            WHERE
                ROWNUM = 1
        """.strip()

        try:
            test_df = self.executequery(test_sql)
            return (
                test_df is not None
                and "SOURCE_ROWID" in test_df.columns
            )
        except Exception:
            return False

    @staticmethod
    def _merge_dataframe(
        duck_con,
        dataframe,
        table_name,
        primary_keys,
        temporary_view="_fusion_merge_chunk",
    ):
        """Create the DuckDB table or merge one DataFrame chunk into it."""
        if dataframe is None or dataframe.empty:
            return 0

        missing_keys = [
            key for key in primary_keys
            if key not in dataframe.columns
        ]

        if missing_keys:
            raise RuntimeError(
                "Merge-key columns are missing from the Fusion result: "
                + ", ".join(missing_keys)
            )

        try:
            duck_con.unregister(temporary_view)
        except Exception:
            pass

        duck_con.register(temporary_view, dataframe)

        try:
            table_exists = duck_con.execute(
                """
                SELECT COUNT(*)
                FROM information_schema.tables
                WHERE lower(table_name) = lower(?)
                """,
                [table_name],
            ).fetchone()[0] > 0

            if not table_exists:
                duck_con.execute(
                    f'CREATE TABLE "{table_name}" AS '
                    f'SELECT * FROM "{temporary_view}"'
                )
                return len(dataframe)

            target_columns = {
                row[1]
                for row in duck_con.execute(
                    f'PRAGMA table_info("{table_name}")'
                ).fetchall()
            }

            source_columns = list(dataframe.columns)

            if set(source_columns) != target_columns:
                missing_in_target = sorted(set(source_columns) - target_columns)
                missing_in_source = sorted(target_columns - set(source_columns))
                raise RuntimeError(
                    "Source and DuckDB schemas differ. "
                    f"Missing in target: {missing_in_target}; "
                    f"missing in source: {missing_in_source}."
                )

            merge_condition = " AND ".join(
                f'tgt."{column}" = src."{column}"'
                for column in primary_keys
            )

            non_key_columns = [
                column for column in source_columns
                if column not in primary_keys
            ]

            matched_clause = ""
            if non_key_columns:
                assignments = ", ".join(
                    f'"{column}" = src."{column}"'
                    for column in non_key_columns
                )
                matched_clause = (
                    "WHEN MATCHED THEN UPDATE SET " + assignments
                )

            insert_columns = ", ".join(
                f'"{column}"' for column in source_columns
            )
            insert_values = ", ".join(
                f'src."{column}"' for column in source_columns
            )

            merge_sql = f"""
                MERGE INTO "{table_name}" AS tgt
                USING "{temporary_view}" AS src
                ON {merge_condition}
                {matched_clause}
                WHEN NOT MATCHED THEN
                    INSERT ({insert_columns})
                    VALUES ({insert_values})
            """

            duck_con.execute(merge_sql)
            return len(dataframe)

        finally:
            try:
                duck_con.unregister(temporary_view)
            except Exception:
                pass

    def copy2dd(
        self,
        table_name,
        primary_key=None,
        use_rowid=True,
        count=5000,
        duckdb_path="fusion_data.duckdb",
        replace_target=False,
        last_update_date=None,
        last_update_date_column="LAST_UPDATE_DATE",
        additional_where=None,
        all_varchar=True,
    ):
        """
        Copy and merge filtered Oracle Fusion data into DuckDB in chunks.

        All source columns default to DuckDB VARCHAR to prevent type-inference
        differences between chunks. The supplied primary/composite key controls
        both deterministic extraction ordering and DuckDB MERGE matching.

        Parameters
        ----------
        table_name:
            Oracle Fusion table or view. DuckDB uses the same table name.
        primary_key:
            One key column or a list/tuple of composite-key columns.
        use_rowid:
            If no key is supplied, test and use Oracle ROWID as SOURCE_ROWID.
        count:
            Maximum rows requested from BIP per chunk.
        duckdb_path:
            Target DuckDB database file.
        replace_target:
            Drop the existing target before loading when True.
        last_update_date:
            Optional incremental lower bound, such as "2026-07-01 00:00:00".
        last_update_date_column:
            Source timestamp column, default LAST_UPDATE_DATE.
        additional_where:
            Optional trusted SQL predicate appended with AND.
        all_varchar:
            Convert every extracted column to string before DuckDB merge.
        """
        self._assert_open()
        table_name = self._validate_identifier(table_name, "table name")
        primary_keys = self._normalize_primary_keys(primary_key)

        if not isinstance(count, int) or count <= 0:
            raise ValueError("count must be a positive integer chunk size.")

        where_clause = self._build_copy_filter(
            last_update_date=last_update_date,
            last_update_date_column=last_update_date_column,
            additional_where=additional_where,
        )

        use_source_rowid = False

        if not primary_keys:
            if not use_rowid:
                raise ValueError("Provide primary_key or set use_rowid=True.")

            print(f"No primary key supplied; testing ROWID for {table_name}...")

            if not self._rowid_is_available(table_name):
                raise RuntimeError(
                    "ROWID is not available for this source. Provide a real "
                    "primary or composite key. Many Fusion views do not expose ROWID."
                )

            primary_keys = ["SOURCE_ROWID"]
            use_source_rowid = True
            print("Using SOURCE_ROWID as the extraction and merge key.")
        else:
            print("Using merge key:", ", ".join(primary_keys))

        count_sql = f"""
            SELECT COUNT(1) AS ROW_COUNT
            FROM {table_name}
            {where_clause}
        """.strip()

        print("Counting filtered source rows...")
        count_df = self.executequery(count_sql, all_varchar=True)

        if count_df.empty or "ROW_COUNT" not in count_df.columns:
            raise RuntimeError(
                "The count query did not return the expected ROW_COUNT column."
            )

        total_rows = int(count_df.iloc[0]["ROW_COUNT"])
        print(f"Source rows selected: {total_rows:,}")

        duck_con = duckdb.connect(duckdb_path)
        processed_rows = 0
        chunks_processed = 0

        try:
            if replace_target:
                duck_con.execute(f'DROP TABLE IF EXISTS "{table_name}"')
                print(f'Dropped existing DuckDB table "{table_name}".')

            if total_rows == 0:
                table_exists = duck_con.execute(
                    """
                    SELECT COUNT(*)
                    FROM information_schema.tables
                    WHERE lower(table_name) = lower(?)
                    """,
                    [table_name],
                ).fetchone()[0] > 0

                duckdb_rows = (
                    duck_con.execute(
                        f'SELECT COUNT(*) FROM "{table_name}"'
                    ).fetchone()[0]
                    if table_exists else 0
                )

                print("No source rows matched the supplied filter.")

                return {
                    "source_rows": 0,
                    "processed_rows": 0,
                    "duckdb_rows": duckdb_rows,
                    "chunks": 0,
                    "duckdb_path": duckdb_path,
                    "table_name": table_name,
                    "merge_key": primary_keys,
                    "used_rowid": use_source_rowid,
                    "last_update_date": last_update_date,
                    "additional_where": additional_where,
                }

            order_by = (
                "t.ROWID"
                if use_source_rowid
                else ", ".join(primary_keys)
            )

            for offset in range(0, total_rows, count):
                chunks_processed += 1

                if use_source_rowid:
                    chunk_sql = f"""
                        SELECT
                            ROWIDTOCHAR(t.ROWID) AS SOURCE_ROWID,
                            t.*
                        FROM {table_name} t
                        {where_clause}
                        ORDER BY {order_by}
                        OFFSET {offset} ROWS
                        FETCH NEXT {count} ROWS ONLY
                    """.strip()
                else:
                    chunk_sql = f"""
                        SELECT *
                        FROM {table_name}
                        {where_clause}
                        ORDER BY {order_by}
                        OFFSET {offset} ROWS
                        FETCH NEXT {count} ROWS ONLY
                    """.strip()

                print(
                    f"Fetching chunk {chunks_processed}: offset {offset:,}, "
                    f"maximum rows {count:,}..."
                )

                chunk_df = self.executequery(
                    chunk_sql,
                    all_varchar=all_varchar,
                )

                if chunk_df.empty:
                    print("No rows returned; stopping extraction.")
                    break

                if all_varchar:
                    chunk_df = self._convert_all_columns_to_string(chunk_df)

                self._merge_dataframe(
                    duck_con=duck_con,
                    dataframe=chunk_df,
                    table_name=table_name,
                    primary_keys=primary_keys,
                )

                processed_rows += len(chunk_df)
                print(
                    f"Merged chunk {chunks_processed}: {len(chunk_df):,} rows; "
                    f"processed {processed_rows:,}/{total_rows:,}."
                )

            table_exists = duck_con.execute(
                """
                SELECT COUNT(*)
                FROM information_schema.tables
                WHERE lower(table_name) = lower(?)
                """,
                [table_name],
            ).fetchone()[0] > 0

            duckdb_rows = (
                duck_con.execute(
                    f'SELECT COUNT(*) FROM "{table_name}"'
                ).fetchone()[0]
                if table_exists else 0
            )

            print(
                f"Copy completed: {processed_rows:,} filtered source rows "
                f"processed; {duckdb_rows:,} rows currently in DuckDB table "
                f'"{table_name}".'
            )

            return {
                "source_rows": total_rows,
                "processed_rows": processed_rows,
                "duckdb_rows": duckdb_rows,
                "chunks": chunks_processed,
                "duckdb_path": duckdb_path,
                "table_name": table_name,
                "merge_key": primary_keys,
                "used_rowid": use_source_rowid,
                "replace_target": replace_target,
                "all_varchar": all_varchar,
                "last_update_date": last_update_date,
                "last_update_date_column": last_update_date_column,
                "additional_where": additional_where,
            }

        finally:
            duck_con.close()

    def syncquery2dd(
        self,
        query,
        target_table,
        primary_key=None,
        count=5000,
        duckdb_path="fusion_data.duckdb",
        replace_target=False,
        all_varchar=True,
        order_by=None,
    ):
        """
        Execute an arbitrary Oracle Fusion SQL query in BIP-safe chunks and
        synchronize the result into a DuckDB table.

        Parameters
        ----------
        query:
            Source SELECT query. Do not include a trailing semicolon.
        target_table:
            DuckDB target table name.
        primary_key:
            One key column or a list/tuple of composite-key columns. When
            supplied, each chunk is merged into DuckDB. When omitted,
            replace_target must be True and chunks are appended after the
            first chunk creates the table.
        count:
            Maximum rows requested from BIP per chunk.
        duckdb_path:
            DuckDB database file.
        replace_target:
            Drop the existing target before synchronization.
        all_varchar:
            Convert all result columns to strings before DuckDB registration.
        order_by:
            Optional deterministic ordering columns. Defaults to primary_key.

        Returns
        -------
        dict
            Synchronization summary.
        """
        self._assert_open()

        if not isinstance(query, str) or not query.strip():
            raise ValueError("query must contain a SELECT statement.")

        source_query = query.strip().rstrip(";").strip()

        if not re.match(r"^SELECT\\b", source_query, flags=re.IGNORECASE):
            raise ValueError("syncquery2dd supports SELECT queries only.")

        target_table = self._validate_identifier(target_table, "target table")
        primary_keys = self._normalize_primary_keys(primary_key)

        if not isinstance(count, int) or count <= 0:
            raise ValueError("count must be a positive integer chunk size.")

        if order_by is None:
            order_columns = primary_keys
        elif isinstance(order_by, str):
            order_columns = [order_by]
        else:
            order_columns = list(order_by)

        order_columns = [
            self._validate_identifier(column, "order-by column")
            for column in order_columns
        ]

        if not order_columns:
            raise ValueError(
                "Provide primary_key or order_by so chunk extraction is deterministic."
            )

        if not primary_keys and not replace_target:
            raise ValueError(
                "primary_key is required for merge mode. Without a key, set "
                "replace_target=True for a full refresh."
            )

        order_expression = ", ".join(
            f'q."{column}"' for column in order_columns
        )

        count_sql = f"""
            SELECT COUNT(1) AS ROW_COUNT
            FROM (
                {source_query}
            ) q
        """.strip()

        print("Counting query result rows...")
        count_df = self.executequery(count_sql, all_varchar=True)

        if count_df.empty or "ROW_COUNT" not in count_df.columns:
            raise RuntimeError(
                "The query count did not return the expected ROW_COUNT column."
            )

        total_rows = int(count_df.iloc[0]["ROW_COUNT"])
        print(f"Query rows selected: {total_rows:,}")

        duck_con = duckdb.connect(duckdb_path)
        processed_rows = 0
        chunks_processed = 0
        temporary_view = "_fusion_query_sync_chunk"

        try:
            if replace_target:
                duck_con.execute(f'DROP TABLE IF EXISTS "{target_table}"')
                print(f'Dropped existing DuckDB table "{target_table}".')

            if total_rows == 0:
                table_exists = duck_con.execute(
                    """
                    SELECT COUNT(*)
                    FROM information_schema.tables
                    WHERE lower(table_name) = lower(?)
                    """,
                    [target_table],
                ).fetchone()[0] > 0

                duckdb_rows = (
                    duck_con.execute(
                        f'SELECT COUNT(*) FROM "{target_table}"'
                    ).fetchone()[0]
                    if table_exists else 0
                )

                print("Query completed successfully: no rows to synchronize.")
                return {
                    "query_rows": 0,
                    "processed_rows": 0,
                    "duckdb_rows": duckdb_rows,
                    "chunks": 0,
                    "target_table": target_table,
                    "duckdb_path": duckdb_path,
                    "primary_key": primary_keys,
                    "replace_target": replace_target,
                }

            for offset in range(0, total_rows, count):
                chunks_processed += 1

                chunk_sql = f"""
                    SELECT q.*
                    FROM (
                        {source_query}
                    ) q
                    ORDER BY {order_expression}
                    OFFSET {offset} ROWS
                    FETCH NEXT {count} ROWS ONLY
                """.strip()

                print(
                    f"Fetching query chunk {chunks_processed}: offset {offset:,}, "
                    f"maximum rows {count:,}..."
                )

                chunk_df = self.executequery(
                    chunk_sql,
                    all_varchar=all_varchar,
                )

                if chunk_df.empty:
                    print("No rows returned for this chunk; stopping synchronization.")
                    break

                if all_varchar:
                    chunk_df = self._convert_all_columns_to_string(chunk_df)

                if primary_keys:
                    self._merge_dataframe(
                        duck_con=duck_con,
                        dataframe=chunk_df,
                        table_name=target_table,
                        primary_keys=primary_keys,
                        temporary_view=temporary_view,
                    )
                else:
                    try:
                        duck_con.unregister(temporary_view)
                    except Exception:
                        pass

                    duck_con.register(temporary_view, chunk_df)

                    try:
                        table_exists = duck_con.execute(
                            """
                            SELECT COUNT(*)
                            FROM information_schema.tables
                            WHERE lower(table_name) = lower(?)
                            """,
                            [target_table],
                        ).fetchone()[0] > 0

                        if not table_exists:
                            duck_con.execute(
                                f'CREATE TABLE "{target_table}" AS '
                                f'SELECT * FROM "{temporary_view}"'
                            )
                        else:
                            duck_con.execute(
                                f'INSERT INTO "{target_table}" '
                                f'SELECT * FROM "{temporary_view}"'
                            )
                    finally:
                        try:
                            duck_con.unregister(temporary_view)
                        except Exception:
                            pass

                processed_rows += len(chunk_df)
                print(
                    f"Synchronized chunk {chunks_processed}: "
                    f"{len(chunk_df):,} rows; "
                    f"processed {processed_rows:,}/{total_rows:,}."
                )

            table_exists = duck_con.execute(
                """
                SELECT COUNT(*)
                FROM information_schema.tables
                WHERE lower(table_name) = lower(?)
                """,
                [target_table],
            ).fetchone()[0] > 0

            duckdb_rows = (
                duck_con.execute(
                    f'SELECT COUNT(*) FROM "{target_table}"'
                ).fetchone()[0]
                if table_exists else 0
            )

            print(
                f'Query synchronization completed: {processed_rows:,} rows '
                f'processed; {duckdb_rows:,} rows in "{target_table}".'
            )

            return {
                "query_rows": total_rows,
                "processed_rows": processed_rows,
                "duckdb_rows": duckdb_rows,
                "chunks": chunks_processed,
                "target_table": target_table,
                "duckdb_path": duckdb_path,
                "primary_key": primary_keys,
                "order_by": order_columns,
                "replace_target": replace_target,
                "all_varchar": all_varchar,
            }

        finally:
            try:
                duck_con.unregister(temporary_view)
            except Exception:
                pass
            duck_con.close()

    def close(self):
        self.auth_header = None
        self.closed = True
        print("Oracle Fusion connection closed.")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()


def fusionconnect(
    url,
    user,
    password,
    use_sso=False,
    provision=True,
    report_path=BIP_EXECUTION_REPORT_PATH,
    timeout=REQUEST_TIMEOUT,
    verify_ssl=VERIFY_SSL,
):
    return FusionConnection(
        url=url,
        username=user,
        password=password,
        use_sso=use_sso,
        provision=provision,
        report_path=report_path,
        timeout=timeout,
        verify_ssl=verify_ssl,
    )



def _syncquery2dd_parallel(
    self,
    query,
    target_table,
    primary_key,
    count=5000,
    duckdb_path="fusion_data.duckdb",
    replace_target=False,
    all_varchar=True,
    order_by=None,
    max_workers=4,
):
    """
    Synchronize an arbitrary Fusion SELECT query to DuckDB with parallel
    BIP chunk extraction and serialized DuckDB MERGE operations.
    """
    self._assert_open()

    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must contain a SELECT statement.")

    source_query = query.strip().rstrip(";").strip()

    if not re.match(r"^SELECT\b", source_query, flags=re.IGNORECASE):
        raise ValueError("Only SELECT queries are supported.")

    target_table = self._validate_identifier(target_table, "target table")
    primary_keys = self._normalize_primary_keys(primary_key)

    if not primary_keys:
        raise ValueError(
            "primary_key is required for safe parallel extraction and MERGE."
        )

    if not isinstance(count, int) or count <= 0:
        raise ValueError("count must be a positive integer chunk size.")

    if not isinstance(max_workers, int) or not 1 <= max_workers <= 8:
        raise ValueError("max_workers must be between 1 and 8.")

    if order_by is None:
        order_columns = primary_keys
    elif isinstance(order_by, str):
        order_columns = [order_by]
    else:
        order_columns = list(order_by)

    order_columns = [
        self._validate_identifier(column, "order-by column")
        for column in order_columns
    ]

    order_expression = ", ".join(
        f'q."{column}"' for column in order_columns
    )

    count_sql = f"""
        SELECT COUNT(1) AS ROW_COUNT
        FROM (
            {source_query}
        ) q
    """.strip()

    print("Counting query result rows...")
    count_df = self.executequery(count_sql, all_varchar=True)

    if count_df.empty or "ROW_COUNT" not in count_df.columns:
        raise RuntimeError(
            "The count query did not return the expected ROW_COUNT column."
        )

    total_rows = int(count_df.iloc[0]["ROW_COUNT"])
    total_chunks = (total_rows + count - 1) // count if total_rows else 0

    print(f"Query rows selected: {total_rows:,}")
    print(f"Parallel chunks: {total_chunks:,}; BIP workers: {max_workers}")

    duck_con = duckdb.connect(duckdb_path)
    processed_rows = 0
    completed_chunks = 0

    try:
        if replace_target:
            duck_con.execute(f'DROP TABLE IF EXISTS "{target_table}"')
            print(f'Dropped existing DuckDB table "{target_table}".')

        if total_rows == 0:
            table_exists = duck_con.execute(
                """
                SELECT COUNT(*)
                FROM information_schema.tables
                WHERE lower(table_name) = lower(?)
                """,
                [target_table],
            ).fetchone()[0] > 0

            duckdb_rows = (
                duck_con.execute(
                    f'SELECT COUNT(*) FROM "{target_table}"'
                ).fetchone()[0]
                if table_exists else 0
            )

            print("Query completed successfully: no rows to synchronize.")
            return {
                "query_rows": 0,
                "processed_rows": 0,
                "duckdb_rows": duckdb_rows,
                "chunks": 0,
                "max_workers": max_workers,
                "target_table": target_table,
                "duckdb_path": duckdb_path,
                "primary_key": primary_keys,
            }

        chunk_specs = [
            (chunk_number, offset)
            for chunk_number, offset in enumerate(
                range(0, total_rows, count),
                start=1,
            )
        ]

        def fetch_chunk(chunk_number, offset):
            chunk_sql = f"""
                SELECT q.*
                FROM (
                    {source_query}
                ) q
                ORDER BY {order_expression}
                OFFSET {offset} ROWS
                FETCH NEXT {count} ROWS ONLY
            """.strip()

            print(
                f"Starting BIP chunk {chunk_number}/{total_chunks}; "
                f"offset {offset:,}."
            )

            dataframe = self.executequery(
                chunk_sql,
                all_varchar=all_varchar,
            )

            return {
                "chunk_number": chunk_number,
                "offset": offset,
                "dataframe": dataframe,
            }

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {
                executor.submit(fetch_chunk, chunk_number, offset): (
                    chunk_number,
                    offset,
                )
                for chunk_number, offset in chunk_specs
            }

            for future in as_completed(future_map):
                chunk_number, offset = future_map[future]

                try:
                    chunk_result = future.result()
                except Exception as error:
                    for pending_future in future_map:
                        pending_future.cancel()

                    raise RuntimeError(
                        f"Parallel BIP chunk {chunk_number} failed at "
                        f"offset {offset:,}: {error}"
                    ) from error

                chunk_df = chunk_result["dataframe"]

                if chunk_df is None or chunk_df.empty:
                    print(f"Chunk {chunk_number} returned no rows; skipping.")
                    completed_chunks += 1
                    continue

                if all_varchar:
                    chunk_df = self._convert_all_columns_to_string(chunk_df)

                # DuckDB MERGE is intentionally performed in this main thread.
                self._merge_dataframe(
                    duck_con=duck_con,
                    dataframe=chunk_df,
                    table_name=target_table,
                    primary_keys=primary_keys,
                    temporary_view=f"_fusion_parallel_chunk_{chunk_number}",
                )

                processed_rows += len(chunk_df)
                completed_chunks += 1

                print(
                    f"Merged chunk {chunk_number}/{total_chunks}: "
                    f"{len(chunk_df):,} rows; cumulative "
                    f"{processed_rows:,}/{total_rows:,}."
                )

        table_exists = duck_con.execute(
            """
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE lower(table_name) = lower(?)
            """,
            [target_table],
        ).fetchone()[0] > 0

        duckdb_rows = (
            duck_con.execute(
                f'SELECT COUNT(*) FROM "{target_table}"'
            ).fetchone()[0]
            if table_exists else 0
        )

        if processed_rows != total_rows:
            print(
                "Warning: processed row count differs from the initial count. "
                "The Fusion source may have changed during extraction."
            )

        print(
            f'Parallel query synchronization completed: {processed_rows:,} '
            f'rows processed; {duckdb_rows:,} rows in "{target_table}".'
        )

        return {
            "query_rows": total_rows,
            "processed_rows": processed_rows,
            "duckdb_rows": duckdb_rows,
            "chunks": total_chunks,
            "completed_chunks": completed_chunks,
            "chunk_size": count,
            "max_workers": max_workers,
            "target_table": target_table,
            "duckdb_path": duckdb_path,
            "primary_key": primary_keys,
            "order_by": order_columns,
            "replace_target": replace_target,
            "all_varchar": all_varchar,
        }

    finally:
        duck_con.close()


def _copy2dd_parallel(
    self,
    table_name,
    primary_key,
    count=5000,
    duckdb_path="fusion_data.duckdb",
    replace_target=False,
    last_update_date=None,
    last_update_date_column="LAST_UPDATE_DATE",
    additional_where=None,
    all_varchar=True,
    max_workers=4,
):
    """
    Synchronize a Fusion table/view to DuckDB with parallel BIP extraction.

    The incremental and additional predicates are applied inside the source
    query before parallel pagination.
    """
    self._assert_open()
    table_name = self._validate_identifier(table_name, "table name")
    primary_keys = self._normalize_primary_keys(primary_key)

    if not primary_keys:
        raise ValueError(
            "primary_key is required for safe parallel table synchronization."
        )

    where_clause = self._build_copy_filter(
        last_update_date=last_update_date,
        last_update_date_column=last_update_date_column,
        additional_where=additional_where,
    )

    source_query = f"""
        SELECT *
        FROM {table_name}
        {where_clause}
    """.strip()

    result = self.syncquery2dd_parallel(
        query=source_query,
        target_table=table_name,
        primary_key=primary_keys,
        count=count,
        duckdb_path=duckdb_path,
        replace_target=replace_target,
        all_varchar=all_varchar,
        order_by=primary_keys,
        max_workers=max_workers,
    )

    result.update({
        "source_table": table_name,
        "last_update_date": last_update_date,
        "last_update_date_column": last_update_date_column,
        "additional_where": additional_where,
    })

    return result


# Add the parallel methods to the existing connection class.
FusionConnection.syncquery2dd_parallel = _syncquery2dd_parallel
FusionConnection.copy2dd_parallel = _copy2dd_parallel
# BEGIN QUERYSAAS COPY2FILE PIPELINE
from .pipeline import _copy2file, _copy2file_parallel

FusionConnection.copy2file = _copy2file
FusionConnection.copy2file_parallel = _copy2file_parallel
# END QUERYSAAS COPY2FILE PIPELINE
# QUERYSAAS-03-BEGIN
from dataclasses import dataclass
from time import perf_counter
from .sql import OracleSqlPlanner
from .exceptions import OracleSqlError
@dataclass(frozen=True)
class CountQueryResult:
    row_count: int
    duration_ms: int
    generated_sql: str
    strategy: str

def _countquery_013(self, sql):
    plan=OracleSqlPlanner().count_query(sql); started=perf_counter()
    frame=self.executequery(plan.executable_sql,all_varchar=True)
    if frame.empty or 'ROW_COUNT' not in frame.columns: raise RuntimeError('Count query did not return ROW_COUNT.')
    return CountQueryResult(int(frame.iloc[0]['ROW_COUNT']),int((perf_counter()-started)*1000),plan.executable_sql,plan.strategy)
FusionConnection.countquery=_countquery_013
# QUERYSAAS-03-END