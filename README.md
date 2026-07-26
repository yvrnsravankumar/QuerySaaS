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
