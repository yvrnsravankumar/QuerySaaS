# QuerySaaS

QuerySaaS is a Python library for querying and synchronizing enterprise SaaS data. The current Oracle Fusion provider supports BI Publisher SQL execution, Oracle SQL planning, DuckDB synchronization, local delimited-file extraction, FBDI import and purge workflows, generic ESS job submission and monitoring, and BI Publisher catalog/object management.

Current version: **0.1.3**

Repository: <https://github.com/yvrnsravankumar/QuerySaaS>

## Installation

```powershell
pip install querysaas
```

## Connection

Use the provider-neutral `connect()` API. QuerySaaS creates the authorization header from the supplied credentials. Callers should not construct or pass a pre-encoded Basic Authorization value.

```python
from querysaas import connect

with connect(
    "oracle_fusion",
    url=FUSION_URL,
    username=FUSION_USERNAME,
    password=FUSION_PASSWORD,
    provision=False,
    verify_ssl=True,
) as connection:
    frame = connection.executequery(
        "SELECT * FROM dual",
        all_varchar=True,
    )
```

Configuration options include:

- `url`: Oracle Fusion base URL
- `username`: Oracle Fusion username
- `password`: password or configured credential
- `use_sso`: use bearer-token authentication when supported
- `provision`: provision the QuerySaaS BI Publisher object on connection
- `report_path`: BI Publisher execution report path
- `timeout`: HTTP timeout in seconds
- `verify_ssl`: SSL verification, enabled by default

## Repository layout

```text
QuerySaaS/
├── examples/
├── src/
│   └── querysaas/
│       ├── __init__.py
│       ├── bip.py
│       ├── exceptions.py
│       ├── fbdi.py
│       ├── oracle_fusion.py
│       ├── pipeline.py
│       ├── registry.py
│       ├── sql.py
│       ├── xdrz_payload.py
│       └── data/
│           └── fbdi_jobs.csv
├── tests/
├── CHANGELOG.md
├── LICENSE
├── MANIFEST.in
├── pyproject.toml
└── README.md
```

## Architecture

```text
QuerySaaS FusionConnection
├── BI Publisher report execution
│   └── ExternalReportWSSService
├── Oracle SQL planner
│   ├── validate
│   ├── count
│   ├── limit
│   └── page
├── Data pipelines
│   ├── Fusion to DuckDB
│   ├── Fusion to delimited files
│   └── FBDI CSV, DuckDB, ZIP, and purge
├── ERP Integrations REST API
│   ├── submit_ess_job
│   └── monitor_ess_job
└── BI Publisher catalog and objects
    ├── get_folder_contents
    ├── download_bip_object
    ├── upload_bip_object
    ├── extract_bip_object
    ├── get_bip_object_xml
    └── copy_bip_object
```

## BI Publisher SQL execution

```python
frame = connection.executequery(
    "SELECT * FROM HZ_CUST_ACCOUNTS",
    all_varchar=True,
)
```

`executequery()` remains backward compatible and returns a pandas DataFrame unless raw output is requested.

### Count query

```python
sql = """
SELECT *
FROM HZ_CUST_ACCOUNTS
-- WHERE STATUS = 'A'
"""

result = connection.countquery(sql)
print(result.row_count)
print(result.generated_sql)
```

The count wrapper places its closing parenthesis on a new line so a trailing line comment cannot hide the generated wrapper syntax.

## Oracle SQL planner

### Class API

```python
from querysaas import OracleSqlPlanner

planner = OracleSqlPlanner()

count_plan = planner.count_query(sql)
limit_plan = planner.limit_query(sql, max_rows=200)
page_plan = planner.page_query(
    sql,
    order_by="CUST_ACCOUNT_ID",
    offset=5000,
    limit=5000,
)
```

### Functional API

```python
from querysaas import (
    count_query,
    limit_query,
    page_query,
    validate_query,
)

validate_query(sql)
count_plan = count_query(sql)
limit_plan = limit_query(sql, max_rows=200)
page_plan = page_query(
    sql,
    order_by="LAST_UPDATE_DATE, CUST_ACCOUNT_ID",
    offset=0,
    limit=5000,
)
```

Planner operations return `SqlPlan` with:

- `original_sql`
- `executable_sql`
- `operation`
- `transformed`
- `strategy`
- `warnings`
- `metadata`
- `to_dict()`

The planner is comment-aware and understands line comments, nested block comments, quoted identifiers, single-quoted strings, escaped quotes, and Oracle q-quoted strings.

## Fusion to local files

The filename contains the complete destination directory and filename. The default delimiter is comma and the default encoding is `utf-8-sig`.

```python
result = connection.copy2file_parallel(
    query="""
        SELECT
            CUST_ACCOUNT_ID,
            ACCOUNT_NUMBER,
            STATUS,
            CREATION_DATE,
            LAST_UPDATE_DATE
        FROM HZ_CUST_ACCOUNTS
    """,
    filename=r"C:\QuerySaaS\exports\hz_cust_accounts.csv",
    order_by="CUST_ACCOUNT_ID",
    chunk_size=5000,
    max_workers=4,
)

print(result.filename)
print(result.rows)
print(result.columns)
print(result.chunks)
```

A deterministic and preferably unique `order_by` is required. A non-unique expression may create unstable page boundaries if source data changes during extraction.

Parallel pages may finish in any order. QuerySaaS writes them in ascending offset order, writes the header once from the first non-empty page, validates later page schemas, writes through a temporary file, and replaces the destination only after success.

### Pipe-delimited output

```python
result = connection.copy2file_parallel(
    query="SELECT * FROM HZ_CUST_ACCOUNTS",
    filename=r"C:\QuerySaaS\exports\hz_cust_accounts.txt",
    order_by="CUST_ACCOUNT_ID",
    delimiter="|",
    chunk_size=5000,
    max_workers=4,
)
```

CSV-standard quoting is applied to values containing the delimiter, quotes, or newlines.

## DuckDB synchronization

Existing APIs remain available:

```python
connection.copy2dd(...)
connection.syncquery2dd(...)
connection.copy2dd_parallel(...)
connection.syncquery2dd_parallel(...)
```

Parallel extraction uses deterministic Oracle pagination, while DuckDB merge operations are serialized. Primary or composite keys are recommended for stable extraction and safe merges.

## FBDI pipelines

```python
result = connection.import_fbdi(
    source=r"C:\FBDI\ProjectBudgets.zip",
    standard_file_name="ProjectBudgets",
)
```

```python
result = connection.csv2fbdi(
    source={
        r"C:\FBDI\project_budgets.csv": "ProjectBudgets",
    },
    zip_file=r"C:\FBDI\ProjectBudgets.zip",
)
```

```python
result = connection.duckdb2fbdi(
    duckdb_path=r"C:\FBDI\staging.duckdb",
    files={
        "ProjectBudgets": "SELECT * FROM PROJECT_BUDGET_STAGE",
    },
    zip_file=r"C:\FBDI\ProjectBudgets.zip",
)
```

### Purge a single load request

```python
result = connection.purge_fbdi(
    load_request_id=9820834,
    standard_file_name="ProjectBudgets",
)
```

### Purge a range

```python
result = connection.purge_fbdi(
    low_load_request_id=9820834,
    high_load_request_id=9820840,
    standard_file_name="ProjectBudgets",
)
```

Purge permanently removes matching interface records. Keep request ranges narrow and verify all identifiers before submission.

## ESS jobs

### Submit an ESS job

```python
submission = connection.submit_ess_job(
    job_package_name=(
        "/oracle/apps/ess/financials/commonModules/"
        "shared/common/interfaceLoader"
    ),
    job_definition_name="InterfaceLoaderController",
    parameters=[1, 10420, "N", "N"],
)

print(submission["request_id"])
```

`parameters` may be `None`, a comma-delimited string, a list, or a tuple. Python `None` values are serialized as Oracle `#NULL`.

### Monitor an ESS job

```python
status = connection.monitor_ess_job(
    request_id=submission["request_id"],
)

print(status["job_name"])
print(status["status"])
print(status["terminal"])
print(status["succeeded"])
```

The default finder is `ESSExecutionDetailsRF`:

```python
status = connection.monitor_ess_job(
    request_id=9820976,
    finder="ESSExecutionDetailsRF",
)
```

QuerySaaS sends:

```text
ESSExecutionDetailsRF;requestId=9820976
```

The caller supplies only the finder name. QuerySaaS appends `requestId` and returns normalized parent and child jobs, plus `finder` and `finder_expression`.

## BI Publisher catalog and object management

These operations use SOAP 1.2 against:

```text
/xmlpserver/services/ExternalReportWSSService
```

They reuse the QuerySaaS connection authentication, timeout, and SSL verification settings.

### Browse catalog contents

```python
result = connection.get_folder_contents(
    folder_absolute_path="/Custom",
    item_type="Folder",
)

for item in result["items"]:
    print(item["display_name"], item["type"])
```

Path behavior:

- `""` lists catalog roots
- `"/"` represents Shared Folders
- `"/~username"` represents that user’s My Folders location
- nested paths, spaces, case, and tilde syntax are preserved
- filtering by `item_type` is case-insensitive
- folders sort first, followed by other objects alphabetically

### Download a BI Publisher object

```python
result = connection.download_bip_object(
    report_absolute_path=(
        "/Custom/CMN_DataSync/"
        "CMN_DataSync_Report.xdo"
    ),
)

print(result["object_type"])
print(result["object_size_bytes"])
```

Optional binary file output:

```python
result = connection.download_bip_object(
    report_absolute_path="/Custom/Finance/Project Budget.xdo",
    output_file=r"C:\QuerySaaS\bip\ProjectBudget",
)
```

If the output filename has no extension and the source type is known, QuerySaaS adds the inferred archive extension.

### Archive type mapping

```text
.xdo -> xdoz
.xdm -> xdmz
.xss -> xssz
```

`object_type` always expects the zipped archive type. An unknown source extension can be downloaded, but copy requires an explicit supported type.

### Extract an object archive

```python
result = connection.extract_bip_object(
    object_zipped_data=download_result,
    output_directory=r"C:\QuerySaaS\bip\ProjectBudget",
    overwrite=False,
)
```

Extraction validates the ZIP archive and blocks absolute paths and parent-directory traversal.

### Read XML members

```python
result = connection.get_bip_object_xml(
    report_absolute_path="/Custom/Finance/Project Budget.xdo",
    member_name="_report.xdo",
)

print(result["xml_valid"])
print(result["text"])
```

Without `member_name`, QuerySaaS returns all XML-compatible members found in the object archive.

### Upload Base64

```python
result = connection.upload_bip_object(
    report_object_absolute_path_url=(
        "/~Integration.User/DataSyncTool"
    ),
    object_type="xdoz",
    object_zipped_data=download_result["object_zipped_data"],
)
```

### Upload bytes

```python
from pathlib import Path

archive_bytes = Path(
    r"C:\QuerySaaS\bip\ProjectBudget.xdoz"
).read_bytes()

result = connection.upload_bip_object(
    report_object_absolute_path_url=(
        "/~Integration.User/DataSyncTool"
    ),
    object_type="xdoz",
    object_zipped_data=archive_bytes,
)
```

Supported archive types are `xdoz`, `xdmz`, and `xssz`. Values such as `.XDOZ` are normalized to `xdoz`. Catalog, zip, xdo, xdm, xss, PDF, CSV, unknown, and empty values are rejected before Oracle is called.

### Copy between two Fusion connections

```python
from querysaas import connect

with connect(
    "oracle_fusion",
    url=SOURCE_FUSION_URL,
    username=SOURCE_USERNAME,
    password=SOURCE_PASSWORD,
    provision=False,
) as source_connection:
    with connect(
        "oracle_fusion",
        url=DESTINATION_FUSION_URL,
        username=DESTINATION_USERNAME,
        password=DESTINATION_PASSWORD,
        provision=False,
    ) as destination_connection:
        result = source_connection.copy_bip_object(
            destination_connection=destination_connection,
            source_report_absolute_path=(
                "/Custom/Finance/Project Budget.xdo"
            ),
            destination_absolute_path=(
                "/~Integration.User/DataSyncTool"
            ),
        )
```

The source connection performs retrieval and the destination connection performs upload. `copy_bip_object()` reuses `download_bip_object()` and `upload_bip_object()` and removes object Base64 from the combined result.

## Errors

QuerySaaS includes structured SQL and pipeline exceptions, plus BI Publisher-specific errors for authentication, authorization, transport, timeout, HTTP failures, SOAP faults, invalid XML, missing object payloads, invalid Base64, unsupported object types, uploads, and report execution.

An Oracle error such as:

```text
ORA-01722: invalid number
```

is a BI Publisher Data Model SQL problem, not a network, Base64, catalog, upload, or FBDI error.

## Security

- Use HTTPS Oracle Fusion base URLs.
- SSL verification is enabled by default.
- Do not hard-code passwords, tokens, Authorization headers, cookies, or session values.
- Basic Authorization is reversible and must be treated as a credential.
- Rotate credentials immediately if they are exposed.
- QuerySaaS does not log object archive Base64 or BI Publisher report-output Base64.
- Do not print `object_zipped_data` or include it in telemetry.
- Archive files are written only when explicitly requested.
- Clear notebook outputs before committing notebooks.

## Troubleshooting

### Empty catalog result

Verify the path, permissions, and whether the folder has immediate children. `get_folder_contents()` does not recurse by default.

### Permission denied

Confirm that the connected Fusion user can access the catalog path or ESS operation. HTTP 401 indicates authentication failure; HTTP 403 indicates authorization failure.

### Object not found

Verify the complete catalog path, case, spaces, and source extension.

### Invalid Base64 or ZIP

The object operation validates Oracle Base64 strictly and checks that decoded content is a readable ZIP archive.

### Unsupported upload type

Use only `xdoz`, `xdmz`, or `xssz`. Source extensions `.xdo`, `.xdm`, and `.xss` are catalog types, not upload archive types.

### Invalid XML

`get_bip_object_xml()` reports XML validity per member. A malformed optional member does not need to invalidate unrelated archive members.

### SOAP fault

Review the safe fault reason, HTTP status, operation, and catalog/report path. Credentials and object Base64 are excluded from error summaries.

### ESS request not found

`monitor_ess_job()` returns `found=False` when Oracle returns no items for the request ID.

## Development, testing, and release

Run the complete local verification from the repository root:

```powershell
python -m compileall .\src\querysaas .\tests
python -m pytest -v
python -m build
python -m twine check .\dist\*
```

Validate the wheel in a clean environment:

```powershell
$ReleaseTest = Join-Path $env:TEMP "querysaas-release-test"
Remove-Item $ReleaseTest -Recurse -Force -ErrorAction SilentlyContinue
python -m venv $ReleaseTest
$ReleasePython = Join-Path $ReleaseTest "Scripts\python.exe"
& $ReleasePython -m pip install .\dist\querysaas-0.1.3-py3-none-any.whl
& $ReleasePython -c @"
import querysaas
assert querysaas.__version__ == "0.1.3"
print("QuerySaaS clean installation passed.")
"@
Remove-Item $ReleaseTest -Recurse -Force
```

Before committing or uploading through the GitHub UI, exclude generated and sensitive content:

```text
.venv/
.release-test/
.manual_backups/
.pytest_cache/
__pycache__/
build/
dist/
*.egg-info/
.env
.env.*
*.duckdb
QUERYSAAS_LIBRARY_SOURCE_REPORT.txt
```

Never commit Fusion passwords, Authorization values, session cookies, customer data files, generated FBDI archives, or BI Publisher object Base64.

### GitHub publication

The repository root should contain `README.md`, `CHANGELOG.md`, `LICENSE`, `MANIFEST.in`, `pyproject.toml`, `src`, `tests`, and `examples`. Preserve the `src/querysaas` hierarchy when uploading files in the GitHub UI.

Recommended GitHub commit message for this release:

```text
Release QuerySaaS 0.1.3 with BI Publisher and ESS APIs
```

## Compatibility

Version 0.1.3 preserves:

- package name `querysaas`
- provider name `oracle_fusion`
- `connect()` calling convention
- `executequery()` behavior
- DuckDB synchronization method names
- local-file pipeline method names
- full-path `filename` parameter
- default comma delimiter
- one-header file behavior
- FBDI import, CSV, DuckDB, and purge APIs

The BI Publisher catalog/object APIs and generic ESS APIs are additive.
