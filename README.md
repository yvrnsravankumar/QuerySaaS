# QuerySaaS

**Query, explore, and synchronize enterprise SaaS applications.**

QuerySaaS 0.1.0 includes the Oracle Fusion BI Publisher connector and DuckDB synchronization engine. The provider-neutral `connect()` API is designed for future Salesforce and other ERP/CRM/HCM connectors.

## Important: embed the BIP report payload

Open:

```text
src/querysaas/xdrz_payload.py
```

Replace:

```text
PASTE_YOUR_EXISTING_COMPLETE_XDRZ_BASE64_HERE
```

with the complete XDRZ Base64 archive. The payload is stored inside the installed Python package and is not accepted as a runtime argument or environment variable.

> Embedding the payload makes it available to anyone who can read the wheel or source distribution. Do not embed Fusion usernames, passwords, session tokens, or API keys.

## Install for development

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
```

Windows:

```powershell
.venv\Scriptsctivate
pip install -e ".[dev]"
```

## Provider-neutral API

```python
from querysaas import connect

con = connect(
    "oracle_fusion",
    url=FUSION_URL,
    username=FUSION_USERNAME,
    password=FUSION_PASSWORD,
)

df = con.executequery("SELECT * FROM dual", all_varchar=True)
```

## Parallel Fusion-to-DuckDB synchronization

```python
result = con.copy2dd_parallel(
    table_name="hz_geographies",
    primary_key="GEOGRAPHY_ID",
    count=5000,
    max_workers=4,
    duckdb_path="querysaas.duckdb",
    all_varchar=True,
)
```

## Build and publish

```bash
python -m build
python -m twine check dist/*
python -m twine upload --repository testpypi dist/*
```

After validation:

```bash
python -m twine upload dist/*
```
### Parallel Fusion-to-local delimited file pipeline

The complete destination path and file name are supplied through one
`filename` parameter. The delimiter defaults to comma. Query pages execute in
parallel with Oracle `ORDER BY ... OFFSET ... FETCH NEXT ...` pagination, then
write to one local file in offset order.

```python
result = con.copy2file_parallel(
    query="SELECT * FROM HZ_CUST_ACCOUNTS",
    filename=r"C:\QuerySaaS\exports\hz_cust_accounts.csv",
    order_by="CUST_ACCOUNT_ID",
    chunk_size=5000,
    max_workers=4,
)

print(result.filename)
print(result.rows, result.chunks)
```

Pipe-delimited output:

```python
result = con.copy2file_parallel(
    query="SELECT * FROM HZ_CUST_ACCOUNTS",
    filename=r"C:\QuerySaaS\exports\hz_cust_accounts.txt",
    order_by="CUST_ACCOUNT_ID",
    delimiter="|",
    chunk_size=5000,
    max_workers=4,
)
```

`order_by` must uniquely and deterministically order the rows. Use a primary
key, or a stable composite expression such as `LAST_UPDATE_DATE, RECORD_ID`.



<!-- QUERYSAAS-03-BEGIN -->
## QuerySaaS 0.1.3
Adds comment-aware Oracle SQL planning, countquery(), structured exceptions, atomic parallel file output, schema validation, and FBDI CSV/DuckDB/import/purge proof-of-concept methods. The full filename remains one parameter, delimiter defaults to comma, and parallel order_by must be deterministic and preferably unique. See examples/hz_cust_accounts_functional_test.py.
<!-- QUERYSAAS-03-END -->

<!-- QUERYSAAS-BIP-BEGIN -->
## Oracle BI Publisher Catalog and Object Management
QuerySaaS reuses the authenticated Fusion connection and SOAP 1.2 ExternalReportWSSService for get_folder_contents(), download_bip_object(), upload_bip_object(), extract_bip_object(), get_bip_object_xml(), and cross-connection copy_bip_object(). The data-pipeline client also exposes submit_ess_job(), and purge_fbdi() reuses it. SSL verification remains enabled by default. Credentials, Authorization, cookies, report output, and object Base64 must never be logged. Object archive mappings are .xdo to xdoz, .xdm to xdmz, and .xss to xssz. copy_bip_object() is invoked on the source connection and requires destination_connection.
<!-- QUERYSAAS-BIP-END -->
