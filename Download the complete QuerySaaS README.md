# QuerySaaS

> A Python toolkit for Oracle Fusion Cloud data access, high-volume parallel extraction, DuckDB analytics, BI Publisher administration, FBDI packaging and submission, ESS monitoring, local data workflows, and provider-independent AI-assisted SQL.

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![PyPI](https://img.shields.io/pypi/v/querysaas?label=PyPI)](https://pypi.org/project/querysaas/)
[![License](https://img.shields.io/badge/License-See%20LICENSE-blue)](LICENSE)

QuerySaaS provides a consistent Python API for extracting and analyzing Oracle Fusion Cloud data without requiring application code to implement paging, parallel request scheduling, retries, file publication, DuckDB synchronization, BI Publisher SOAP operations, FBDI metadata resolution, ESS monitoring, AI provider transport, or SQL safety from scratch.

The package is designed for:

- Oracle Fusion technical teams
- Data engineering teams
- Integration developers
- BI Publisher administrators
- FBDI and ESS automation developers
- DuckDB and local analytics users
- QuerySaaS Studio
- Python applications and command-line workflows
- AI-assisted Oracle Fusion and DuckDB SQL workflows

---

## Table of contents

- [Why QuerySaaS](#why-querysaas)
- [Feature overview](#feature-overview)
- [Installation](#installation)
- [Quick start](#quick-start)
- [Connection configuration](#connection-configuration)
- [Canonical Oracle Fusion API](#canonical-oracle-fusion-api)
- [Legacy API compatibility](#legacy-api-compatibility)
- [Sequential and parallel extraction](#sequential-and-parallel-extraction)
- [Parallel execution planning](#parallel-execution-planning)
- [Single-file CSV exports](#single-file-csv-exports)
- [Resumable CSV and Parquet part datasets](#resumable-csv-and-parquet-part-datasets)
- [Retries, cancellation, and failure handling](#retries-cancellation-and-failure-handling)
- [DuckDB synchronization](#duckdb-synchronization)
- [Local Data Library](#local-data-library)
- [DuckDB exports and Parquet](#duckdb-exports-and-parquet)
- [FBDI registry and package generation](#fbdi-registry-and-package-generation)
- [FBDI upload, import, and purge](#fbdi-upload-import-and-purge)
- [ESS job submission and monitoring](#ess-job-submission-and-monitoring)
- [BI Publisher catalog operations](#bi-publisher-catalog-operations)
- [BI Publisher scheduling](#bi-publisher-scheduling)
- [AI provider support](#ai-provider-support)
- [Automatic AI model discovery](#automatic-ai-model-discovery)
- [AI SQL generation](#ai-sql-generation)
- [Oracle Fusion and DuckDB SQL policies](#oracle-fusion-and-duckdb-sql-policies)
- [AI schema context and data privacy](#ai-schema-context-and-data-privacy)
- [Security](#security)
- [Result contracts and metrics](#result-contracts-and-metrics)
- [Logging and diagnostics](#logging-and-diagnostics)
- [Testing](#testing)
- [Packaging and release validation](#packaging-and-release-validation)
- [Migration guide](#migration-guide)
- [Performance guidance](#performance-guidance)
- [Troubleshooting](#troubleshooting)
- [Project structure](#project-structure)
- [Documentation](#documentation)
- [Contributing](#contributing)
- [Versioning](#versioning)
- [License](#license)

---

## Why QuerySaaS

Oracle Fusion data workflows often require several technologies at once:

- BI Publisher or Fusion service calls for data retrieval
- Deterministic pagination for large extracts
- Retry and error handling for remote requests
- CSV or Parquet publication
- Local analytical storage
- DuckDB table synchronization
- FBDI metadata, ZIP packaging, document upload, and ESS jobs
- BI Publisher catalog operations
- Secure AI provider integration
- Read-only enforcement for generated Oracle Fusion SQL

QuerySaaS brings these capabilities into one package with shared conventions for configuration, structured results, retries, redaction, diagnostics, and compatibility.

### Design goals

1. **Canonical, descriptive APIs**
   
   New code uses names such as `execute_fusion_query()` and `copy_fusion_query_to_file()` instead of abbreviated method names.

2. **Backward compatibility**
   
   Established legacy methods remain available during migration.

3. **Deterministic data movement**
   
   Parallel extraction preserves output order and validates schema consistency.

4. **Bounded concurrency**
   
   Worker and pending-page limits prevent unbounded submission.

5. **Failure-safe publication**
   
   Outputs are written through temporary locations and promoted only after successful completion.

6. **Local-first analytics**
   
   DuckDB, CSV, TSV, and Parquet workflows remain available without a separate database server.

7. **Provider-independent AI**
   
   Applications provide an API URL and credential, while QuerySaaS owns model discovery, compatible request routes, response parsing, and safe metadata.

8. **Target-specific SQL policy**
   
   Oracle Fusion generation remains read-only. DuckDB generation supports its full SQL language, including DDL and DML.

---

## Feature overview

### Oracle Fusion data access

- Execute Fusion SQL queries
- Count query rows
- Sequential extraction
- Parallel extraction
- Automatic mode selection
- Deterministic ordering
- Configurable chunk sizes
- Bounded workers and pending pages
- Page-scoped retries
- CSV output
- CSV part datasets
- Parquet part datasets
- Checkpoints and resume
- SHA-256 manifests
- Failed-page splitting
- Runtime and throughput metrics

### DuckDB

- Copy Fusion tables to DuckDB
- Synchronize arbitrary Fusion queries to DuckDB
- Explicit target-table naming
- Primary-key-aware merge workflows
- Serialized local writes with parallel remote extraction
- Local SQL execution
- Managed local tables
- File-backed read-only aliases
- CSV, TSV, and Parquet export
- Parquet export for DuckDB query results
- AI generation of DuckDB SELECT, DML, DDL, transactions, and scripts

### Local Data Library

- Folder discovery
- CSV support
- TSV support
- Parquet support
- Filename-based aliases
- Safe normalized aliases
- Table listing
- File listing
- Table description
- Preview and count
- Materialization to managed DuckDB tables
- Local querying
- Export to CSV, TSV, or Parquet

### FBDI and ESS

- Packaged FBDI registry
- Live registry refresh with packaged fallback
- Registry search and filtering
- Business object metadata resolution
- CSV-to-FBDI ZIP generation
- DuckDB-to-FBDI ZIP generation
- Existing ZIP submission support
- Document upload
- Load Interface File job submission
- Import job submission
- ESS status polling
- Interface-table purge operations
- Structured request IDs and results

### BI Publisher

- Catalog folder listing
- Object existence checks
- Object download
- Object upload
- Object extraction
- Object validation
- Object replacement
- Object deletion with protected-path handling
- Copy planning and execution
- Polling for catalog consistency
- Report scheduling
- Notification options
- Redacted diagnostics

### AI

- OpenAI-compatible APIs
- Automatic model discovery from `/models`
- Chat verification through `/chat/completions`
- Gateway-root and `/v1` URL normalization
- Automatic model selection
- Anthropic-compatible architecture support
- Gemini, OpenAI, OpenAI-compatible, and Ollama foundations
- Oracle Fusion SQL generation
- Oracle SQL explanation
- Oracle SQL repair
- DuckDB SQL generation
- Bounded schema context
- Request previews
- Credential-safe result dictionaries
- Provider-independent results and errors

---

## Installation

### Install from PyPI

```bash
python -m pip install querysaas
```

### Install a specific version

```bash
python -m pip install querysaas==0.3.8
```

### Upgrade

```bash
python -m pip install --upgrade querysaas
```

### Install from a local wheel

```bash
python -m pip install dist/querysaas-0.3.8-py3-none-any.whl
```

### Development installation

```bash
python -m pip install -e .
```

### Verify installation

```bash
python -c "import querysaas; print(querysaas.__version__); print(querysaas.__file__)"
```

---

## Quick start

### Connect to Oracle Fusion

```python
import os
from querysaas import connect

fusion = connect(
    base_url=os.environ["FUSION_BASE_URL"],
    username=os.environ["FUSION_USERNAME"],
    password=os.environ["FUSION_PASSWORD"],
)
```

Use the connection as a context manager when supported by the application flow:

```python
import os
from querysaas import connect

with connect(
    base_url=os.environ["FUSION_BASE_URL"],
    username=os.environ["FUSION_USERNAME"],
    password=os.environ["FUSION_PASSWORD"],
) as fusion:
    result = fusion.execute_fusion_query(
        "SELECT LEDGER_ID, NAME FROM GL_LEDGERS"
    )
    print(result)
```

### Execute a query

```python
result = fusion.execute_fusion_query(
    "SELECT LEDGER_ID, NAME, CURRENCY_CODE FROM GL_LEDGERS"
)
```

### Count a query

```python
count = fusion.count_fusion_query(
    "SELECT LEDGER_ID FROM GL_LEDGERS"
)
```

### Export a query automatically

```python
result = fusion.copy_fusion_query_to_file(
    query="""
        SELECT
            ROWIDTOCHAR(gb.ROWID) AS GL_BALANCE_PK,
            gb.LEDGER_ID,
            gb.CODE_COMBINATION_ID,
            gb.PERIOD_NAME,
            gb.CURRENCY_CODE,
            gb.ACTUAL_FLAG,
            gb.PERIOD_NET_DR,
            gb.PERIOD_NET_CR
        FROM GL_BALANCES gb
        WHERE gb.LAST_UPDATE_DATE >= DATE '2026-01-01'
    """,
    filename="gl_balances.csv",
    mode="auto",
    order_by="GL_BALANCE_PK",
    overwrite=True,
)
```

### Open the Local Data Library

```python
from querysaas import open_data_library

with open_data_library("./data") as db:
    db.refresh()
    print(db.list_files())
    print(db.list_tables())
    result = db.query("SELECT COUNT(*) FROM sales_data")
    print(result)
```

---

## Connection configuration

QuerySaaS applications should obtain credentials from environment variables or approved secret stores.

Recommended environment variables:

```text
FUSION_BASE_URL
FUSION_USERNAME
FUSION_PASSWORD
```

Example PowerShell session setup:

```powershell
$env:FUSION_BASE_URL = "https://example.fa.us2.oraclecloud.com"
$env:FUSION_USERNAME = "integration.user"
$env:FUSION_PASSWORD = Read-Host "Fusion password" -AsSecureString
```

Applications may provide their own credential resolver. QuerySaaS does not require credentials to be embedded in source code.

### Connection responsibilities

The Fusion connection owns:

- Authentication configuration
- Fusion endpoint configuration
- Query transport
- Request retries
- Response normalization
- Installed canonical and legacy methods
- Connection close behavior

Always close long-lived connections when the workflow ends.

---

## Canonical Oracle Fusion API

The canonical API provides descriptive names for application code.

### `execute_fusion_query`

```python
result = fusion.execute_fusion_query(
    "SELECT LEDGER_ID, NAME FROM GL_LEDGERS"
)
```

Use for direct query execution when the expected result fits a normal in-memory response.

### `count_fusion_query`

```python
row_count = fusion.count_fusion_query(
    "SELECT CODE_COMBINATION_ID FROM GL_CODE_COMBINATIONS"
)
```

Use for planning, progress, threshold decisions, and reconciliation.

### `copy_fusion_query_to_file`

```python
result = fusion.copy_fusion_query_to_file(
    query="SELECT CODE_COMBINATION_ID, SEGMENT1 FROM GL_CODE_COMBINATIONS",
    filename="code_combinations.csv",
    order_by="CODE_COMBINATION_ID",
    mode="auto",
)
```

Supports:

- `mode="auto"`
- `mode="sequential"`
- `mode="parallel"`
- Single-file CSV
- CSV part datasets
- Parquet part datasets
- Retry controls
- Resume controls
- Progress controls
- Worker and pending-page controls

### `copy_fusion_table_to_duckdb`

```python
result = fusion.copy_fusion_table_to_duckdb(
    table_name="GL_CODE_COMBINATIONS",
    target_table="gl_code_combinations",
    primary_key="CODE_COMBINATION_ID",
    mode="parallel",
    duckdb_path="fusion.duckdb",
)
```

### `sync_fusion_query_to_duckdb`

```python
result = fusion.sync_fusion_query_to_duckdb(
    query="""
        SELECT
            CODE_COMBINATION_ID,
            SEGMENT1,
            SEGMENT2,
            ENABLED_FLAG,
            LAST_UPDATE_DATE
        FROM GL_CODE_COMBINATIONS
    """,
    target_table="gl_code_combinations",
    primary_key="CODE_COMBINATION_ID",
    order_by="CODE_COMBINATION_ID",
    mode="parallel",
    duckdb_path="fusion.duckdb",
)
```

---

## Legacy API compatibility

Existing applications can continue using the established abbreviated methods while migrating.

| Legacy method | Canonical replacement |
|---|---|
| `executequery` | `execute_fusion_query` |
| `countquery` | `count_fusion_query` |
| `copy2file` | `copy_fusion_query_to_file` with sequential mode |
| `copy2file_parallel` | `copy_fusion_query_to_file` with parallel mode |
| `copy2dd` | `copy_fusion_table_to_duckdb` with sequential mode |
| `copy2dd_parallel` | `copy_fusion_table_to_duckdb` with parallel mode |
| `syncquery2dd` | `sync_fusion_query_to_duckdb` with sequential mode |
| `syncquery2dd_parallel` | `sync_fusion_query_to_duckdb` with parallel mode |

### Migration example

Legacy:

```python
fusion.copy2file_parallel(
    sql,
    "output.csv",
    order_by="ID",
    chunk_size=5000,
    max_workers=8,
)
```

Canonical:

```python
fusion.copy_fusion_query_to_file(
    query=sql,
    filename="output.csv",
    mode="parallel",
    order_by="ID",
    chunk_size=5000,
    max_workers=32,
    max_pending_pages=64,
)
```

New examples and new source code should use canonical methods.

---

## Sequential and parallel extraction

### Sequential mode

Sequential mode requests pages one at a time and is useful for:

- Small result sets
- Simple troubleshooting
- Low-concurrency environments
- Workloads where deterministic ordering exists but parallelism is unnecessary

```python
result = fusion.copy_fusion_query_to_file(
    query=sql,
    filename="small_export.csv",
    mode="sequential",
)
```

### Parallel mode

Parallel mode requests multiple deterministic pages concurrently while writing results in logical page order.

```python
result = fusion.copy_fusion_query_to_file(
    query=sql,
    filename="large_export.csv",
    mode="parallel",
    order_by="UNIQUE_KEY",
    chunk_size=5000,
    max_workers=32,
    max_pending_pages=64,
)
```

### Automatic mode

```python
result = fusion.copy_fusion_query_to_file(
    query=sql,
    filename="automatic_export.csv",
    mode="auto",
    order_by="UNIQUE_KEY",
    parallel_threshold=5000,
)
```

Automatic mode uses row-count planning and selects sequential or parallel execution according to the configured threshold.

### Deterministic ordering requirement

Parallel query extraction requires a stable `order_by` expression.

Good choices:

```text
A unique primary key
A stable composite business key
A generated physical extraction key when explicitly appropriate
```

Avoid non-unique ordering such as:

```sql
ORDER BY LAST_UPDATE_DATE
```

Prefer:

```sql
ORDER BY LAST_UPDATE_DATE, PRIMARY_KEY
```

---

## Parallel execution planning

QuerySaaS plans:

- Total source rows
- Maximum rows to process
- Chunk size
- Total chunks
- Selected execution mode
- Effective worker count
- Maximum pending pages
- Expected output files

### Automatic maximum-performance profile

For sufficiently large extracts, the current automatic profile resolves to:

```text
Workers:       32
Pending pages: 64
```

The effective worker count is reduced when fewer pages are available.

For example:

```text
20 pages and max_workers=32 → 20 effective workers
1910 pages and max_workers=32 → 32 effective workers
```

### Plan inspection

```python
from querysaas import plan_parallel_execution

plan = plan_parallel_execution(
    fusion,
    "SELECT ID FROM LARGE_TABLE",
    mode="parallel",
    chunk_size=5000,
    max_workers="auto",
    worker_limit=32,
    max_pending_pages="auto",
)

print(plan.total_rows)
print(plan.total_chunks)
print(plan.max_workers)
print(plan.max_pending_pages)
```

### Explicit profile selection

```python
result = fusion.copy_fusion_query_to_file(
    query=sql,
    filename="output.csv",
    mode="parallel",
    order_by="ID",
    chunk_size=5000,
    max_workers=24,
    max_pending_pages=48,
)
```

Use explicit values when a Fusion environment requires a lower concurrency profile.

---

## Single-file CSV exports

```python
result = fusion.copy_fusion_query_to_file(
    query=sql,
    filename="output.csv",
    mode="parallel",
    order_by="PRIMARY_KEY",
    output_mode="single_file",
    output_format="csv",
    include_header=True,
    encoding="utf-8-sig",
    overwrite=True,
)
```

### Single-file guarantees

- One header row
- Logical page ordering
- Schema consistency checks
- Temporary output before publication
- Existing destination preservation on failure
- Structured row and page metrics

### CSV controls

Depending on the method version and execution path, controls include:

```text
delimiter
encoding
quotechar
quoting
include_header
all_varchar
overwrite
```

---

## Resumable CSV and Parquet part datasets

Part datasets are recommended for large or restartable operations.

```python
result = fusion.copy_fusion_query_to_file(
    query=sql,
    filename="exports/gl_balances_parts",
    mode="parallel",
    order_by="GL_BALANCE_PK",
    output_mode="part_files",
    output_format="parquet",
    chunk_size=5000,
    max_workers=32,
    max_pending_pages=64,
    resume=True,
)
```

### Dataset contents

```text
exports/gl_balances_parts/
  manifest.json
  part-000001.parquet
  part-000002.parquet
  part-000003.parquet
  ...
```

A failed working directory may include checkpoint state for resume.

### Manifest information

The manifest can include:

- Operation status
- Source query identity
- Planned rows
- Written rows
- Column information
- Output format
- Chunk details
- Worker details
- Part filenames
- Per-part row counts
- SHA-256 hashes
- Resume metrics
- Split-page metrics

### Resume

```python
result = fusion.copy_fusion_query_to_file(
    query=sql,
    filename="exports/gl_balances_parts",
    mode="parallel",
    order_by="GL_BALANCE_PK",
    output_mode="part_files",
    output_format="parquet",
    resume=True,
)
```

Resume validates completed parts before skipping them.

### Failed-page splitting

Large pages that repeatedly fail for payload-size reasons can be divided into smaller ranges:

```python
result = fusion.copy_fusion_query_to_file(
    query=sql,
    filename="exports/parts",
    mode="parallel",
    order_by="ID",
    output_mode="part_files",
    split_failed_pages=True,
    minimum_chunk_size=1000,
)
```

---

## Retries, cancellation, and failure handling

### Retry contract

Network-bound operations generally use:

```python
max_retries=3
retry_base_seconds=1.0
retry_max_seconds=30.0
```

A retry count of 3 means:

```text
1 initial attempt
up to 3 additional retry attempts
```

### Retryable conditions

Examples include:

- Temporary connection failures
- HTTP 429
- HTTP 502
- HTTP 503
- HTTP 504
- Temporary provider overload

### Non-retryable conditions

Examples include:

- Authentication failure
- Authorization failure
- Invalid SQL
- Schema mismatch
- Unsafe operation
- Unsupported protocol
- User cancellation

### Failure-safe output

If extraction fails before publication:

- Incomplete output is not promoted
- Existing valid output is preserved
- The operation returns a structured exception
- Resumable part workflows may retain checkpoint state

---

## DuckDB synchronization

QuerySaaS combines parallel Fusion extraction with controlled DuckDB writes.

### Copy a Fusion table

```python
result = fusion.copy_fusion_table_to_duckdb(
    table_name="GL_BALANCES",
    target_table="gl_balances",
    primary_key="GL_BALANCE_PK",
    order_by="GL_BALANCE_PK",
    mode="parallel",
    duckdb_path="fusion.duckdb",
)
```

### Synchronize a query

```python
result = fusion.sync_fusion_query_to_duckdb(
    query="""
        SELECT
            CODE_COMBINATION_ID,
            SEGMENT1,
            SEGMENT2,
            ENABLED_FLAG,
            LAST_UPDATE_DATE
        FROM GL_CODE_COMBINATIONS
    """,
    target_table="gl_code_combinations",
    primary_key="CODE_COMBINATION_ID",
    order_by="CODE_COMBINATION_ID",
    mode="parallel",
    duckdb_path="fusion.duckdb",
)
```

### Primary keys

Use a stable logical primary key whenever possible. Direct table-copy workflows may support a source ROWID fallback for extraction scenarios. Query-based synchronization does not inject ROWID into arbitrary SQL.

### Write model

Parallelism applies to remote extraction. DuckDB writes or merges remain controlled to avoid unsafe concurrent writes.

---

## Local Data Library

The Local Data Library provides a DuckDB-backed analytical layer over local folders.

```python
from querysaas import open_data_library

with open_data_library("./data") as db:
    db.refresh()
    print(db.list_files())
    print(db.list_tables())
```

### Supported local sources

```text
CSV
TSV
Parquet
Managed DuckDB tables
Managed DuckDB views
```

### List files

```python
files = db.list_files()
```

### List tables

```python
tables = db.list_tables()
```

### Describe a table

```python
columns = db.describe_table("sales_data")
```

### Preview a table

```python
preview = db.preview("sales_data")
```

### Count rows

```python
row_count = db.count("sales_data")
```

### Run local SQL

```python
result = db.query(
    """
    SELECT
        customer_id,
        SUM(amount) AS total_amount
    FROM sales_data
    GROUP BY customer_id
    ORDER BY total_amount DESC
    """
)
```

### Materialize a file-backed source

```python
result = db.materialize(
    "sales_data",
    as_table="sales_data_managed",
    replace=False,
)
```

File-backed aliases remain read-only. Managed DuckDB tables support local DML and DDL.

### Aliases

A file such as:

```text
Sales Data.csv
```

may be registered with:

```sql
SELECT * FROM "Sales Data";
```

and a normalized alias such as:

```sql
SELECT * FROM sales_data;
```

---

## DuckDB exports and Parquet

QuerySaaS supports local result export to:

```text
CSV
TSV
Parquet
```

Parquet is recommended for analytical workflows because it preserves types, supports compression, and enables column projection.

Conceptual workflow:

```python
result = db.query("SELECT * FROM managed_sales")
result.export("managed_sales.parquet", format="parquet")
```

Use the exact export method exposed by the installed result contract.

### Recommended output choice

| Use case | Recommended format |
|---|---|
| Interchange with legacy systems | CSV |
| Tab-delimited downstream process | TSV |
| DuckDB analytics | Parquet |
| Large resumable Fusion extraction | Parquet part dataset |

---

## FBDI registry and package generation

QuerySaaS includes a packaged FBDI registry at:

```text
src/querysaas/data/fbdi_jobs.csv
```

The registry supports metadata such as:

- Business object name
- Application ID
- Interface option ID
- Document account
- Load job
- Import job
- Control file
- Required CSV names
- Interface table names

### Registry workflow

```text
Use live registry when available
→ validate live response
→ fall back to packaged registry when needed
→ filter and resolve business object
```

### Search the registry

Use the registry APIs exposed by the installed QuerySaaS version to:

- List supported business objects
- Search by name
- Filter by application
- Resolve a package configuration
- Inspect required CSV files
- Inspect interface tables

### Create an FBDI ZIP from CSV files

```text
Input CSV files
→ validate expected Oracle filenames
→ validate duplicate names
→ include the control file
→ create ZIP package
→ return package metadata
```

### Create FBDI data from DuckDB

A local DuckDB query can supply one or more CSV payloads that are assembled into the required FBDI package.

Use this pattern when:

- Local transformations are performed in DuckDB
- Several source files must be mapped to Oracle FBDI filenames
- The package requires controlled formatting
- The output must be tested before upload

---

## FBDI upload, import, and purge

QuerySaaS supports the FBDI submission lifecycle:

```text
Prepare package
→ upload to the configured document account
→ submit Load Interface File job
→ monitor completion
→ submit Import job when required
→ monitor completion
→ return request IDs and status
```

### Existing ZIP submission

Applications can submit an existing valid FBDI ZIP package through the FBDI upload API.

### Multiple CSV mapping

Applications such as QuerySaaS Studio can map multiple local CSV files to the Oracle filenames expected by a selected FBDI business object.

### Interface-table visibility

The selected registry entry should expose interface-table names so the user understands which staging tables are involved.

### Purge operations

Interface-table purge is a separate operation from upload and import.

Recommended safeguards:

- Display business object
- Display environment
- Display interface-table names
- Require explicit user intent
- Return ESS request ID
- Monitor final status

---

## ESS job submission and monitoring

QuerySaaS supports Oracle Enterprise Scheduler Service workflows.

Typical operations include:

- Submit a job
- Submit Load Interface File
- Submit import processes
- Submit interface-table purge
- Retrieve request status
- Poll until completion
- Inspect parent and child requests
- Return terminal status

### Monitoring loop

```python
request_id = submit_result.request_id

while True:
    status = fusion.get_ess_request_status(request_id)
    if status.is_terminal:
        break
    time.sleep(5)
```

Use the exact ESS method names exposed by the installed version.

### Terminal states

Applications should distinguish:

```text
Succeeded
Warning
Error
Cancelled
Expired
Other terminal outcomes
```

---

## BI Publisher catalog operations

QuerySaaS supports BI Publisher catalog workflows through structured service operations.

### Folder listing

- List catalog folders
- List supported objects
- Resolve paths

### Download

- Download supported BI Publisher objects
- Decode archived content safely
- Preserve object metadata

### Upload

- Upload archived objects
- Encode bytes exactly once
- Verify upload results
- Poll for catalog consistency

### Extract and inspect

- Extract supported archive content
- Inspect safe metadata
- Avoid exposing binary payloads in logs

### Copy

Copy workflows may include:

```text
Plan source and destination
→ validate source
→ inspect destination
→ preserve destination when required
→ upload source content
→ poll for consistency
→ verify final object
→ restore destination if replacement fails
```

### Delete

Deletion should respect protected catalog paths and return structured outcomes.

### Replacement safety

Replacement workflows should verify both backup and final destination readability.

---

## BI Publisher scheduling

QuerySaaS supports report scheduling with options such as:

- Report path
- Output format
- Parameters
- Job name
- Job description
- Notification recipients
- Notification events

Conceptual example:

```python
result = fusion.schedule_bip_report(
    report_path="/Custom/Finance/Balance Report.xdo",
    output_format="csv",
    parameters={
        "P_LEDGER_ID": "300000001",
        "P_PERIOD_NAME": "Jan-26",
    },
)
```

Notification and recipient details should be masked in logs and diagnostics.

---

## AI provider support

QuerySaaS provides provider-independent AI foundations for SQL generation, explanation, repair, model discovery, retries, safe results, and schema context.

### Supported provider categories

Depending on the installed adapter modules:

```text
OpenAI
OpenAI-compatible services
Anthropic Claude
Google Gemini
Ollama
Enterprise gateways using a supported protocol
```

A vendor name is not a protocol. For example, an IBM gateway can expose OpenAI-compatible and Anthropic-compatible endpoints.

### IBM Consulting Advantage example

The following API root was validated with both OpenAI-compatible and Anthropic-compatible routes:

```text
https://api.nextgen-beta.ica.ibm.com/ica/v1
```

OpenAI-compatible routes:

```text
GET  /models
POST /chat/completions
Authorization: Bearer <credential>
```

Anthropic-compatible route:

```text
POST /messages
x-api-key: <credential>
anthropic-version: 2023-06-01
```

The recommended normal workflow uses OpenAI-compatible model discovery and chat generation.

---

## Automatic AI model discovery

The user needs only:

```text
API URL
API key
```

QuerySaaS can then:

```text
Normalize the URL
→ request /models
→ parse accessible model IDs
→ select a default
→ verify /chat/completions
→ return a safe setup result
```

### Configure a provider automatically

```python
import os
from querysaas import configure_openai_compatible_provider

setup = configure_openai_compatible_provider(
    base_url="https://api.nextgen-beta.ica.ibm.com/ica/v1",
    api_key=os.environ["QUERYSAAS_AI_API_KEY"],
)

print(setup.selected_model)

for model in setup.models:
    print(model.model_id, model.display_name)
```

### List models from a URL

```python
import os
from querysaas import list_ai_models_from_url

models = list_ai_models_from_url(
    "https://api.nextgen-beta.ica.ibm.com/ica/v1",
    os.environ["QUERYSAAS_AI_API_KEY"],
)
```

### URL normalization

```python
from querysaas import normalize_openai_compatible_api_root

assert normalize_openai_compatible_api_root(
    "https://api.nextgen-beta.ica.ibm.com/ica"
) == "https://api.nextgen-beta.ica.ibm.com/ica/v1"

assert normalize_openai_compatible_api_root(
    "https://api.nextgen-beta.ica.ibm.com/ica/v1"
) == "https://api.nextgen-beta.ica.ibm.com/ica/v1"
```

This prevents duplicate paths such as:

```text
/v1/v1/models
/v1/v1/chat/completions
```

### Default model selection

The selection order is:

1. Previously saved model if still available
2. Organization-preferred model if supplied and available
3. Verified preferred model
4. General-purpose fallback
5. First returned model

```python
from querysaas import select_default_ai_model

selected = select_default_ai_model(
    models,
    previous_model="gpt-4o",
    preferred_models=("claude-sonnet-4-5",),
)
```

### Credential handling

The API key is used to authenticate requests. Safe result dictionaries do not include the key.

QuerySaaS Studio should store only a credential reference and resolve the secret through an approved credential store.

---

## AI SQL generation

### Oracle Fusion SQL generation

```python
from querysaas import generate_oracle_sql

result = generate_oracle_sql(
    setup.profile,
    "Generate a query showing actual balances by ledger and period.",
    schema_context=schema_text,
)

print(result.sql)
```

### Explain Oracle SQL

```python
from querysaas import explain_oracle_sql

result = explain_oracle_sql(
    setup.profile,
    sql,
    schema_context=schema_text,
)
```

### Repair Oracle SQL

```python
from querysaas import repair_oracle_sql

result = repair_oracle_sql(
    setup.profile,
    sql,
    oracle_error="ORA-00904: invalid identifier",
    schema_context=schema_text,
)
```

### DuckDB SQL generation

DuckDB generation supports the complete DuckDB SQL language.

```python
from querysaas import generate_duckdb_sql

result = generate_duckdb_sql(
    setup.profile,
    "Create a schema named reporting and build a monthly balance summary table.",
    schema_context=duckdb_schema_text,
    allow_multiple_statements=True,
)

print(result["sql"])
print(result["classification"])
```

DuckDB generation can include:

```text
SELECT
INSERT
UPDATE
DELETE
MERGE
CREATE
CREATE OR REPLACE
ALTER
DROP
TRUNCATE
RENAME
COPY
ATTACH
DETACH
IMPORT
EXPORT
INSTALL
LOAD
BEGIN
COMMIT
ROLLBACK
PRAGMA
```

DuckDB classification is informational and does not reject valid DDL or DML.

---

## Oracle Fusion and DuckDB SQL policies

### Oracle Fusion

Oracle Fusion AI SQL is read-only.

Allowed:

```text
SELECT
Read-only WITH
```

Rejected:

```text
INSERT
UPDATE
DELETE
MERGE
DDL
PL/SQL
Transaction control
Multiple statements
FOR UPDATE
Unsafe network or scheduler package calls
```

Generated SQL is returned for review and is not executed automatically.

### DuckDB

DuckDB AI SQL generation supports:

- Read-only SQL
- DML
- DDL
- Transactions
- Multi-statement scripts
- DuckDB administration statements

Generated SQL is still returned for review and is not automatically executed by the AI generation API.

### Explicit execution target

```python
from querysaas import normalize_sql_execution_target

assert normalize_sql_execution_target("fusion") == "oracle_fusion"
assert normalize_sql_execution_target("duckdb") == "duckdb"
```

Never apply Oracle Fusion read-only validation to DuckDB SQL.

---

## AI schema context and data privacy

Models do not automatically access Fusion, DuckDB, local files, or credentials.

A model receives only the information QuerySaaS includes in the outbound request.

### Recommended schema-only context

```text
GL_BALANCES:
  LEDGER_ID
  CODE_COMBINATION_ID
  PERIOD_NAME
  CURRENCY_CODE
  ACTUAL_FLAG
  PERIOD_NET_DR
  PERIOD_NET_CR

GL_LEDGERS:
  LEDGER_ID
  NAME
  CURRENCY_CODE
```

### Do not send by default

```text
Query-result rows
Complete CSV files
Complete Parquet files
Complete DuckDB tables
Fusion credentials
AI API keys
Authentication headers
Tokens
Passwords
```

### Recommended context controls

```text
Schema metadata: Enabled with bounded selection
Active SQL: User-controlled
Sample rows: Disabled by default
Query results: Disabled by default
Complete files: Never automatic
```

### Schema context workflow

```text
Local schema catalog
→ rank tables and columns against the prompt
→ exclude sensitive columns
→ enforce table, column, and character limits
→ preview outbound context
→ send approved metadata
```

### DuckDB metadata for context

```python
with open_data_library("./data") as db:
    tables = db.list_tables()
    columns = db.describe_table("sales_data")
```

The same metadata can support editor autocomplete and AI context without sending actual rows.

---

## Security

### Never embed secrets

Do not place credentials in:

```text
Source files
README examples
Workspace JSON
Provider profile JSON
Logs
Reports
Diagnostics
Prompt previews
Telemetry
Generated artifacts
```

### Recommended secret sources

```text
Environment variables
Windows Credential Manager
OCI Vault
Approved enterprise secret managers
```

### Redaction

QuerySaaS should redact:

- Passwords
- API keys
- Authorization headers
- `x-api-key` values
- Cookies
- Tokens
- Signed URLs
- BI Publisher archive payloads
- FBDI package content
- Sensitive notification details

### AI privacy

The selected model can process only data sent in the request. QuerySaaS applications control schema, SQL, sample data, and result inclusion.

### File safety

For destructive application operations:

- Create a verified backup
- Validate backup readability
- Preserve existing valid destinations
- Stop when backup verification fails

---

## Result contracts and metrics

Parallel and synchronization results may expose:

```text
rows
total_rows
processed_rows
columns
pages_written
pages_submitted
peak_pending_pages
chunk_count
selected_mode
elapsed_seconds
rows_per_second
retry_scope
source
target
output_file
manifest_file
resumed_parts
split_pages
```

Inspect the installed result type rather than relying on tuple position.

### Performance metrics

Useful metrics include:

- QuerySaaS pipeline duration
- Measured end-to-end duration
- Parallel request window
- Post-last-page finalization
- Page average
- Page median
- Page P90 and P95
- Effective concurrency
- Rows per second
- Failed requests
- Retry attempts

---

## Logging and diagnostics

Applications should distinguish:

```text
User activity history
Operation logs
Developer diagnostics
Audit records
Generated data
```

Recommended safe fields:

- Timestamp with timezone
- Operation ID
- Operation type
- Phase
- Duration
- Row count
- Page count
- Retry count
- Safe endpoint
- Provider protocol
- Model identifier
- Normalized error category

Do not log credentials or complete sensitive payloads.

---

## Testing

Run the complete test suite:

```bash
python -m pytest -q
```

Compile source and tests:

```bash
python -m compileall -q src/querysaas tests
```

### Focused test areas

```text
Canonical public API
Legacy compatibility
Parallel planning
Bounded scheduling
Retry forwarding
Single-file publication
Part-file manifests
Checkpoint and resume
DuckDB synchronization
Local Data Library
FBDI registry and packaging
ESS requests
BI Publisher download and upload
AI provider transport
Automatic model discovery
Oracle SQL safety
DuckDB SQL generation
Packaging metadata
```

### Network tests

Normal unit and integration tests should mock external networks. Live Oracle Fusion and AI provider tests should be separate, explicitly invoked, and credential-safe.

---

## Packaging and release validation

### Build

```bash
python -m build
```

### Validate artifacts

```bash
python -m twine check dist/*
```

### Inspect artifacts

Expected files for version 0.3.8:

```text
dist/querysaas-0.3.8-py3-none-any.whl
dist/querysaas-0.3.8.tar.gz
```

### Clean-environment test

```bash
python -m venv .release-verify
.release-verify/Scripts/python.exe -m pip install dist/querysaas-0.3.8-py3-none-any.whl
.release-verify/Scripts/python.exe -c "import querysaas; print(querysaas.__version__)"
```

### Upload to TestPyPI

```bash
python -m twine upload --repository testpypi dist/*
```

### Upload to PyPI

Upload the same validated files after TestPyPI verification:

```bash
python -m twine upload dist/*
```

Do not rebuild between TestPyPI and production publication.

---

## Migration guide

### Migrate query execution

Before:

```python
result = fusion.executequery(sql)
```

After:

```python
result = fusion.execute_fusion_query(sql)
```

### Migrate row counting

Before:

```python
count = fusion.countquery(sql)
```

After:

```python
count = fusion.count_fusion_query(sql)
```

### Migrate file export

Before:

```python
result = fusion.copy2file_parallel(
    sql,
    "output.csv",
    order_by="ID",
)
```

After:

```python
result = fusion.copy_fusion_query_to_file(
    query=sql,
    filename="output.csv",
    mode="parallel",
    order_by="ID",
)
```

### Migrate DuckDB sync

Before:

```python
result = fusion.syncquery2dd_parallel(
    sql,
    "target_table",
    primary_key="ID",
)
```

After:

```python
result = fusion.sync_fusion_query_to_duckdb(
    query=sql,
    target_table="target_table",
    primary_key="ID",
    order_by="ID",
    mode="parallel",
)
```

### Migrate AI setup

Before:

```python
profile = AiProviderProfile(
    provider="openai_compatible",
    model="manually-entered-model",
    base_url=api_url,
    api_key=api_key,
)
```

After:

```python
setup = configure_openai_compatible_provider(
    base_url=api_url,
    api_key=api_key,
)

profile = setup.profile
models = setup.models
```

---

## Performance guidance

### Select required columns

Avoid selecting every source column when only a smaller analytical subset is needed.

Prefer:

```sql
SELECT LEDGER_ID, PERIOD_NAME, CURRENCY_CODE, PERIOD_NET_DR, PERIOD_NET_CR
FROM GL_BALANCES
```

instead of:

```sql
SELECT *
FROM GL_BALANCES
```

### Use deterministic ordering

Parallel pagination depends on stable ordering.

### Use 5,000-row chunks as a validated starting point

A 5,000-row chunk size has performed well in large Oracle Fusion extraction tests. Benchmark each Fusion environment independently.

### Use the 32-worker automatic profile when appropriate

A validated GL_BALANCES workload processed approximately 9.55 million rows with:

```text
Workers:               32
Pending pages:         64
Chunk size:            5,000
Pipeline duration:     approximately 56 minutes
Throughput:            approximately 2,843 rows/second
Failed requests:       0
Retries:               0
Validation errors:     0
```

Environment capacity, query shape, selected columns, time of day, and Fusion service load can change results.

### Prefer part datasets for restartability

For multi-hour or production-critical extracts, use resumable Parquet part datasets rather than one large CSV.

### Watch deep offset cost

Very large OFFSET/FETCH values can increase page latency. Partitioned or key-range extraction may be more efficient for some tables.

---

## Troubleshooting

### Parallel mode requires `order_by`

**Symptom**

```text
ValueError: order_by is required
```

**Resolution**

Provide a stable unique or composite ordering expression.

```python
order_by="LAST_UPDATE_DATE, PRIMARY_KEY"
```

### Fewer workers than requested

The effective worker count cannot exceed the number of pages.

```text
100,000 rows / 5,000 = 20 pages
```

A request for 32 workers therefore uses at most 20 workers.

### AI URL produces `/v1/v1/models`

Use the current URL normalization API:

```python
normalize_openai_compatible_api_root(api_url)
```

Both gateway-root and `/v1` URLs normalize correctly.

### AI models are not listed

Check:

- API key validity
- Bearer authentication support
- `/models` availability
- HTTPS connectivity
- Proxy or firewall restrictions
- Response compatibility with OpenAI `data[].id`

### AI chat fails after model discovery

Possible reasons:

- The first returned model is not chat-capable
- The model is visible but not authorized for generation
- The gateway requires a different route
- The provider is rate-limited

Use `configure_openai_compatible_provider()` so QuerySaaS selects and verifies a model.

### BI Publisher ZIP byte test is unstable

A test that calls a ZIP-producing helper twice may compare archives containing different timestamp metadata. Generate the archive once and reuse the same bytes in the input and assertion.

### Existing destination remains unchanged after failure

This behavior is intentional. QuerySaaS publishes final output only after successful completion and validation.

### DuckDB cannot update a CSV alias

File-backed aliases are read-only. Materialize the source to a managed table first.

```python
db.materialize("sales_data", as_table="sales_data_managed")
```

---

## Project structure

Representative package structure:

```text
querysaas/
  pyproject.toml
  README.md
  CHANGELOG.md
  LICENSE
  MANIFEST.in
  src/
    querysaas/
      __init__.py
      oracle_fusion.py
      fusion_api.py
      pipeline.py
      parallel_parts.py
      local_data.py
      bipublisher.py
      fbdi.py
      ai.py
      ai_context.py
      ai_sql.py
      ai_repair.py
      ai_runtime.py
      ai_enterprise.py
      data/
        fbdi_jobs.csv
  tests/
  docs/
  examples/
```

The exact source layout may evolve, but public APIs should remain stable through documented migration paths.

---

## Documentation

Recommended documentation topics:

```text
docs/ARCHITECTURE.md
docs/PUBLIC_API.md
docs/BI_PUBLISHER.md
docs/LOCAL_DATA_LIBRARY.md
docs/SECURITY.md
docs/VERSION_HISTORY.md
docs/GITHUB_MANUAL_UPLOAD.md
docs/QUERYSAAS_AI_PROVIDER_ARCHITECTURE_AND_IMPLEMENTATION_HANDOFF.md
docs/QUERYSAAS_0_3_7_GITHUB_PYPI_RELEASE_AND_METHOD_MIGRATION_GUIDE.md
```

Documentation should be updated after every feature addition, including:

- Architecture
- Public API
- Examples
- Security
- Theme and Studio integration notes when applicable
- Version history
- Migration notes
- Validation evidence
- Known limitations

---

## Contributing

Before submitting a change:

1. Preserve backward compatibility when practical.
2. Add or update tests.
3. Compile source and tests.
4. Run focused tests.
5. Run the complete test suite.
6. Update documentation.
7. Avoid credentials and customer data in fixtures.
8. Use mocked HTTP transport in normal tests.
9. Preserve deterministic ordering in parallel workflows.
10. Preserve output and backup safety.

### Validation checklist

```bash
python -m compileall -q src/querysaas tests
python -m pytest -q
python -m build
python -m twine check dist/*
```

---

## Versioning

QuerySaaS follows versioned package releases.

Published PyPI release files are immutable. Changes to code or package metadata require a new version.

Recommended version decisions:

```text
Patch release: backward-compatible fixes and enhancements
Minor release: substantial new compatible capabilities
Major release: incompatible public API changes
Post release: packaging or documentation-only correction when appropriate
```

Consult `CHANGELOG.md` and `docs/VERSION_HISTORY.md` for release-specific details.

---

## License

See [LICENSE](LICENSE) for the project license and usage terms.

---

## Final summary

QuerySaaS provides one Python package for:

- Oracle Fusion query execution
- Automatic, sequential, and parallel extraction
- 32-worker bounded planning
- Ordered and failure-safe CSV publication
- Resumable CSV and Parquet datasets
- DuckDB synchronization
- Local CSV, TSV, Parquet, and DuckDB analytics
- FBDI registry, package, upload, import, and purge workflows
- ESS submission and monitoring
- BI Publisher catalog and scheduling operations
- OpenAI-compatible automatic model discovery
- Provider-independent AI generation
- Read-only Oracle Fusion SQL safety
- Full DuckDB SQL generation
- Bounded schema context and credential-safe results

The package is intended to serve both direct Python users and the QuerySaaS Studio desktop application while preserving a stable, testable, secure, and extensible architecture.
