# QuerySaaS

**Query, explore, and synchronize enterprise SaaS applications.**

[![QuerySaaS CI](https://github.com/yvrnsravankumar/QuerySaaS/actions/workflows/ci.yml/badge.svg)](https://github.com/yvrnsravankumar/QuerySaaS/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue)
![Status](https://img.shields.io/badge/status-alpha-orange)
![License](https://img.shields.io/badge/license-MIT-green)

QuerySaaS is a Python library for querying and synchronizing data from enterprise SaaS applications. Version `0.1.0` provides an Oracle Fusion Cloud connector that executes SQL through BI Publisher and loads query or table results into DuckDB.

The connector architecture is designed to support additional providers such as Salesforce, Oracle ATP, Workday, NetSuite, and SAP in future releases.

> **Project status:** QuerySaaS is currently an alpha release. Test it in a non-production environment before using it with business-critical data.

---

## Features

### Oracle Fusion Cloud

- Execute SQL through Oracle Fusion BI Publisher
- Basic authentication and bearer-token support
- Automatic BI Publisher report provisioning
- Embedded BIP XDRZ report payload
- Empty-result-safe SOAP and XML processing
- pandas DataFrame results
- Configurable request timeout and SSL verification

### DuckDB synchronization

- Synchronize complete Oracle Fusion tables or views
- Synchronize arbitrary SQL query results
- Initial loads and incremental updates
- Single-column and composite merge keys
- `LAST_UPDATE_DATE` watermark filtering
- Optional additional source predicates
- All-column `VARCHAR` normalization
- Safe handling when a query returns no rows

### Parallel extraction

- Concurrent BI Publisher chunk requests
- Configurable worker count and chunk size
- Stable key-based ordering
- Serialized DuckDB merge operations
- Progress and row-count summaries
- Clear chunk and offset error reporting

---

## Supported and planned providers

### Available in `0.1.0`

- Oracle Fusion Cloud through BI Publisher
- DuckDB as a synchronization destination

### Planned

- Salesforce
- Oracle ATP through ORDS
- Workday
- NetSuite
- SAP
- CSV, DAT, XML, JSON, and Parquet destinations

---

## Project structure

```text
QuerySaaS/
├── pyproject.toml
├── README.md
├── LICENSE
├── MANIFEST.in
├── examples/
│   ├── quickstart.py
│   └── querysaas_quickstart.ipynb
├── src/
│   └── querysaas/
│       ├── __init__.py
│       ├── registry.py
│       ├── oracle_fusion.py
│       └── xdrz_payload.py
└── tests/
    └── test_packaging.py
```

---

## Installation

### Install from source

Clone the repository:

```bash
git clone https://github.com/yvrnsravankumar/QuerySaaS.git
cd QuerySaaS
```

Create and activate a virtual environment.

#### Windows PowerShell

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

#### Linux or macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install QuerySaaS:

```bash
python -m pip install --upgrade pip
python -m pip install -e .
```

Install the development dependencies:

```bash
python -m pip install -e ".[dev]"
```

### Install from PyPI

This command will be available after the first PyPI release:

```bash
pip install querysaas
```

---

## Embedded BI Publisher payload

The Oracle Fusion connector uses the packaged XDRZ payload in:

```text
src/querysaas/xdrz_payload.py
```

The payload is normalized when the module loads:

```python
BIP_XDRZ_BASE64 = "".join(BIP_XDRZ_BASE64.split())
```

### Security notice

The embedded XDRZ payload is part of the source distribution and generated wheel. Anyone with repository or package access can extract it.

Do not embed:

- Oracle Fusion passwords
- Bearer tokens
- Salesforce access tokens
- Session cookies
- API keys
- Environment-specific secrets

Use a private repository and private package index if the report definition is proprietary.

---

## Quick start

```python
from getpass import getpass
from querysaas import connect

fusion_url = "https://your-host.oraclecloud.com"
fusion_username = "your.username"
fusion_password = getpass("Oracle Fusion password: ")

with connect(
    "oracle_fusion",
    url=fusion_url,
    username=fusion_username,
    password=fusion_password,
) as con:
    dataframe = con.executequery(
        "SELECT * FROM dual",
        all_varchar=True,
    )

    print(dataframe)
```

---

## Query Oracle Fusion

```python
sql = """
SELECT
    GEOGRAPHY_ID,
    GEOGRAPHY_CODE,
    GEOGRAPHY_NAME,
    GEOGRAPHY_TYPE,
    LAST_UPDATE_DATE
FROM
    HZ_GEOGRAPHIES
WHERE
    GEOGRAPHY_TYPE = 'COUNTRY'
ORDER BY
    GEOGRAPHY_ID
"""

with connect(
    "oracle_fusion",
    url=fusion_url,
    username=fusion_username,
    password=fusion_password,
) as con:
    dataframe = con.executequery(
        sql,
        all_varchar=True,
    )
```

A valid query returning no records produces an empty DataFrame instead of raising a no-data exception.

---

## Synchronize a Fusion table to DuckDB

```python
result = con.copy2dd(
    table_name="hz_geographies",
    primary_key="GEOGRAPHY_ID",
    count=5000,
    duckdb_path="querysaas.duckdb",
    replace_target=False,
    last_update_date="2026-07-01 00:00:00",
    last_update_date_column="LAST_UPDATE_DATE",
    all_varchar=True,
)

print(result)
```

---

## Parallel table synchronization

```python
result = con.copy2dd_parallel(
    table_name="hz_geographies",
    primary_key="GEOGRAPHY_ID",
    count=5000,
    max_workers=4,
    duckdb_path="querysaas.duckdb",
    replace_target=False,
    last_update_date="2026-07-01 00:00:00",
    last_update_date_column="LAST_UPDATE_DATE",
    additional_where="GEOGRAPHY_TYPE = 'COUNTRY'",
    all_varchar=True,
)

print(result)
```

Start with three or four workers. Increasing worker count may cause BI Publisher throttling or timeouts.

---

## Synchronize an arbitrary query

```python
query = """
SELECT
    GEOGRAPHY_ID,
    GEOGRAPHY_CODE,
    GEOGRAPHY_NAME,
    GEOGRAPHY_TYPE,
    LAST_UPDATE_DATE
FROM
    HZ_GEOGRAPHIES
WHERE
    GEOGRAPHY_TYPE = 'COUNTRY'
"""

result = con.syncquery2dd_parallel(
    query=query,
    target_table="HZ_GEOGRAPHIES_COUNTRY",
    primary_key="GEOGRAPHY_ID",
    count=5000,
    max_workers=4,
    duckdb_path="querysaas.duckdb",
    replace_target=False,
    all_varchar=True,
)
```

The primary-key columns must be included in the query result and should provide stable deterministic ordering.

---

## Composite primary keys

```python
result = con.syncquery2dd_parallel(
    query="""
        SELECT
            JE_HEADER_ID,
            JE_LINE_NUM,
            LEDGER_ID,
            PERIOD_NAME,
            LAST_UPDATE_DATE
        FROM
            GL_JE_LINES
    """,
    target_table="GL_JE_LINES",
    primary_key=["JE_HEADER_ID", "JE_LINE_NUM"],
    count=5000,
    max_workers=4,
    all_varchar=True,
)
```

---

## Provider-neutral API

QuerySaaS exposes a common entry point:

```python
from querysaas import connect
```

Current provider:

```python
fusion = connect(
    "oracle_fusion",
    url=fusion_url,
    username=fusion_username,
    password=fusion_password,
)
```

Planned provider shape:

```python
salesforce = connect(
    "salesforce",
    instance_url=salesforce_url,
    access_token=access_token,
)
```

The Salesforce connector is planned and is not included in version `0.1.0`.

---

## Run tests

```bash
python -m pytest
```

The GitHub Actions workflow validates QuerySaaS using Python 3.10, 3.11, and 3.12.

---

## Build the package

```bash
python -m build
python -m twine check dist/*
```

Expected artifacts:

```text
dist/
├── querysaas-0.1.0-py3-none-any.whl
└── querysaas-0.1.0.tar.gz
```

---

## Release workflow

QuerySaaS uses the following release process:

```text
Push source to GitHub
→ Run CI on Python 3.10, 3.11, and 3.12
→ Create a version tag
→ Publish a GitHub Release
→ Build distributions
→ Publish through PyPI Trusted Publishing
```

For release `0.1.0`:

```bash
git tag -a v0.1.0 -m "QuerySaaS 0.1.0"
git push origin v0.1.0
```

The PyPI workflow is triggered when the GitHub Release is published.

---

## Versioning

QuerySaaS follows semantic versioning:

```text
0.1.1  Bug fixes
0.2.0  Backward-compatible features or new connectors
1.0.0  Stable public API
```

A version uploaded to PyPI cannot be replaced. Every release must use a new version number.

---

## Roadmap

- [x] Oracle Fusion BI Publisher queries
- [x] Empty-result-safe DataFrame processing
- [x] DuckDB table and query synchronization
- [x] Parallel BI Publisher extraction
- [x] Incremental loading and keyed merge
- [ ] Salesforce connector
- [ ] Oracle ATP/ORDS connector
- [ ] Workday connector
- [ ] NetSuite connector
- [ ] SAP connector
- [ ] Pluggable destination interface
- [ ] QuerySaaS CLI
- [ ] QuerySaaS Studio desktop/web interface

---

## Contributing

1. Fork the repository.
2. Create a feature branch.
3. Add or update tests.
4. Run `python -m pytest`.
5. Submit a pull request.

For connector contributions, keep provider-specific logic isolated from the provider-neutral registry and public API.

---

## License

QuerySaaS is licensed under the MIT License. See [LICENSE](LICENSE).

---

## Disclaimer

QuerySaaS is an independent open-source project. QuerySaaS is not affiliated with, endorsed by, or sponsored by Oracle, Salesforce, SAP, Workday, or NetSuite. Product names and trademarks belong to their respective owners.
