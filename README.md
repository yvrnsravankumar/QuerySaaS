# QuerySaaS

QuerySaaS is a Python library for querying and synchronizing enterprise SaaS applications. The Oracle Fusion provider supports BI Publisher SQL execution, Oracle-aware SQL planning, DuckDB synchronization, local delimited-file extraction, FBDI import and purge workflows, ESS job submission and monitoring, BI Publisher catalog lifecycle operations, and a provider-neutral AI assistant foundation.

**Current version: 0.3.5**

Repository: <https://github.com/yvrnsravankumar/QuerySaaS>

## Highlights

- Provider-neutral `connect()` API with Oracle Fusion support.
- Backward-compatible `executequery()` returning pandas DataFrames.
- Comment-aware Oracle SQL planning, counting, limiting, and deterministic paging.
- Sequential and parallel Fusion-to-DuckDB synchronization.
- Atomic sequential and parallel delimited-file extraction.
- Live and packaged FBDI job registry support.
- FBDI ZIP upload, CSV packaging, DuckDB export, import, and purge.
- Generic ESS job submission and monitoring.
- BI Publisher catalog browsing, download, upload, extraction, XML inspection, protected copy, replacement, verification, deletion, and scheduling.
- AI profiles with configurable Base URLs, local Ollama, Gemini, OpenAI-compatible APIs, and enterprise adapters.
- AI-generated Oracle SQL extraction, classification, read-only enforcement, schema allowlists, explanation, and repair.
- Retry policy, cancellation, SSE parsing, and usage telemetry.
- Generated or repaired SQL is never executed automatically.

## Installation

```powershell
pip install querysaas
```

For local development from the repository root:

```powershell
python -m pip install -e .
```

## Quick start

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
    print(frame)
```

## Documentation

- [Complete public API](docs/PUBLIC_API.md)
- [AI Assistant](docs/AI_ASSISTANT.md)
- [BI Publisher](docs/BI_PUBLISHER.md)
- [FBDI and ESS](docs/FBDI_ESS.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Security](docs/SECURITY.md)
- [Version history](docs/VERSION_HISTORY.md)
- [Manual GitHub upload](docs/GITHUB_MANUAL_UPLOAD.md)

## Core examples

### Execute Oracle Fusion SQL

```python
frame = connection.executequery(
    """
    SELECT
        PROJECT_ID,
        SEGMENT1,
        NAME
    FROM PJF_PROJECTS_ALL_VL
    WHERE ROWNUM <= 100
    """,
    all_varchar=True,
)
```

### Count a query

```python
result = connection.countquery(
    "SELECT * FROM PJF_PROJECTS_ALL_VL"
)
print(result.row_count)
print(result.generated_sql)
```

### Copy to a local CSV atomically

```python
result = connection.copy2file_parallel(
    query="SELECT * FROM PJF_PROJECTS_ALL_VL",
    filename=r"C:\QuerySaaS\exports\projects.csv",
    order_by="PROJECT_ID",
    chunk_size=5000,
    max_workers=4,
)
print(result.rows)
print(result.filename)
```

### Generate safe Oracle SQL with local Ollama

```python
from querysaas import (
    AiProviderProfile,
    OracleSchemaContext,
    generate_oracle_sql,
)

profile = AiProviderProfile(
    provider="ollama",
    model="qwen3:8b",
    base_url="http://127.0.0.1:11434/v1",
)

context = OracleSchemaContext(
    tables={
        "PJF_PROJECTS_ALL_B": [
            "PROJECT_ID",
            "SEGMENT1",
            "STATUS_CODE",
        ]
    }
)

result = generate_oracle_sql(
    profile,
    "List active projects and project numbers.",
    schema_context=context.to_prompt_text(),
)
print(result.sql)
print(result.classification.to_dict())
```

### Repair an Oracle query without executing it

```python
from querysaas import repair_oracle_sql

repair = repair_oracle_sql(
    profile,
    original_sql="SELECT BAD_COLUMN FROM PJF_PROJECTS_ALL_B",
    oracle_error="ORA-00904: BAD_COLUMN: invalid identifier",
    schema_context=context,
)
print(repair.repaired_sql)
print(repair.unified_diff)
```

## Development verification

```powershell
python -m compileall .\src\querysaas .\tests
python -m pytest -q
python -m build
python -m twine check .\dist\*
```

## Security summary

- Keep Oracle Fusion and AI credentials separate.
- Use environment credential references instead of storing resolved secrets in profile JSON.
- Keep SSL verification enabled.
- Review AI request previews before external transmission.
- Use schema allowlists and sensitive-column exclusions.
- Review generated or repaired SQL before execution.
- Never commit `.env`, credentials, Authorization headers, cookies, query results, customer data, BI Publisher object Base64, or generated FBDI archives.

## License

MIT License. See [LICENSE](LICENSE).

## BI Publisher 0.3.2 migration

```python
result = source.copy_bip_object(
    destination_connection=target,
    source_report_absolute_path=source_path,
    destination_absolute_path=target_path,
    overwrite=True,
    verify=True,
    dry_run=False,
)
```


## BI Publisher 0.3.2 correction

The 0.3.2 source uses canonical metadata-aware exceptions, readable verification, eventual-consistency polling for CREATE and REPLACE, verified rollback, and opt-in ScheduleReportWSSService notifications.


## QuerySaaS 0.3.3

Version 0.3.3 republishes the corrected BI Publisher consolidation after the original 0.3.2 release. It provides canonical metadata-aware BI Publisher exceptions, safe `to_dict()` serialization, CREATE eventual-consistency polling, readable committed-write preservation, verified restoration, readable-only verification, and opt-in scheduling notifications.


## Local Data Library
Query CSV, TSV, and Parquet files by filename without extensions. Exact names with spaces use double quotes, for example `SELECT * FROM "Sales Data"`; normalized aliases such as `sales_data` are also available. See [Local Data Library](docs/LOCAL_DATA_LIBRARY.md).


## Network retry standard

QuerySaaS 0.3.5 exposes a consistent retry contract on network-bound query, extraction, BI Publisher read, FBDI registry read, and ESS monitoring operations:

```python
result = fusion.executequery(
    sql,
    max_retries=3,
    retry_base_seconds=1.0,
    retry_max_seconds=30.0,
)
```

`max_retries=3` means one initial request plus at most three retries. QuerySaaS retries recognized transient connection failures and HTTP 408, 429, 500, 502, 503, and 504 responses. Authentication, authorization, validation, protected-operation, schema, and cancellation failures are not retried. Local Data Library methods remain local-only and do not expose network retry parameters.
