# QuerySaaS Architecture

## Package layout

```text
src/querysaas/
  __init__.py          Public imports and version
  registry.py          Provider-neutral connect entry point
  oracle_fusion.py     Fusion connection, BI Publisher execution, DuckDB sync
  sql.py               Oracle SQL planner
  pipeline.py          Local file pipelines
  fbdi.py              FBDI registry, imports, ESS, purge
  bip.py               BI Publisher catalog and object lifecycle
  ai.py                Provider profiles and text generation
  ai_sql.py            SQL extraction, classification, and safety
  ai_context.py        Named profiles, credentials, schema context, previews
  ai_repair.py         SQL explanation and repair
  ai_enterprise.py     Enterprise provider adapters
  ai_runtime.py        Retry, cancellation, streaming, and telemetry
  exceptions.py        Core structured exceptions
  xdrz_payload.py      Embedded BI Publisher provisioning payload
  data/fbdi_jobs.csv   Packaged FBDI registry fallback
```

## Dependency direction

```text
registry -> oracle_fusion
oracle_fusion -> sql, exceptions, xdrz_payload
pipeline -> sql, exceptions
fbdi -> oracle_fusion connection services
bip -> FusionConnection method installer
ai_context -> ai, ai_sql
ai_repair -> ai, ai_sql, ai_context
ai_enterprise -> ai transport primitives
ai_runtime -> ai generation APIs
```

## Method installation

Pipeline, FBDI, and BI Publisher modules install methods on `FusionConnection` during package import. This preserves the established connection object while keeping implementation modules separated by domain.

## Data safety boundaries

```text
Oracle credentials -> FusionConnection only
AI credentials -> AiProviderProfile only
Profile JSON -> credential references only
Schema context -> explicit allowlisted metadata
AI output -> extraction and validation, never auto-execution
BI Publisher archives -> explicit in-memory or file operations
```

## Reliability design

- Atomic local-file replacement.
- Deterministic parallel pagination.
- Serialized DuckDB merge operations.
- FBDI live registry with packaged fallback.
- BI Publisher replacement with backup restoration attempt.
- AI retries with cancellation checks.
- Patch scripts with timestamped backups and automatic rollback.
