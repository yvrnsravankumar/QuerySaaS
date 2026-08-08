# Changelog

## 0.3.0 - 2026-08-08

- Consolidated stable AI assistant API.
- Added SQL explanation and repair.
- Added enterprise provider adapters.
- Added retry, cancellation, SSE parsing, and usage telemetry.
- Preserved read-only and schema-context safeguards.

## 0.2.4 - 2026-08-08

### Added
- Safe Oracle error-code and message parsing.
- Read-only SQL technical explanation through configured AI providers.
- Oracle SQL repair using sanitized errors and approved schema context.
- Structured before-and-after SQL comparison and unified diff.
- Repaired-query read-only, planner, and schema-context validation.
- Detection of unchanged repairs and unsafe provider output.

### Security
- Oracle errors are redacted before provider transmission.
- Repair output cannot use write SQL or tables outside approved context.
- Explanation and repair methods never execute SQL automatically.
## 0.2.3 - 2026-08-08

### Added
- Named AI profiles with deterministic JSON persistence.
- Environment-based credential references without serializing resolved secrets.
- Validated Oracle schema context with table, column, exclusion, and size policies.
- SQL referenced-table extraction and approved-context validation.
- Redacted AI SQL request previews before provider transmission.
- Atomic profile writes, duplicate protection, profile deletion, and case-insensitive lookup.

### Security
- Profile files contain credential reference names only, not API-key values.
- Request previews never include resolved credentials.
- Schema context can exclude sensitive columns before prompt construction.
## 0.2.2 - 2026-08-08

### Added
- Oracle SQL extraction from fenced and plain AI responses.
- Structured statement classification and risk reasons.
- Read-only SELECT/WITH enforcement.
- Multiple-statement, DML, DDL, PL/SQL, row-locking, network, file, scheduler, and dynamic-SQL blocking.
- Oracle-aware assistant prompt construction with schema context.
- Structured `AiSqlResult` and `AiSqlClassification` models.
- `generate_oracle_sql()` for generation, extraction, classification, and validation without automatic execution.
## 0.2.1 - 2026-08-08

### Added
- Provider-neutral AI profile and response models.
- Configurable and validated provider Base URLs.
- Local Ollama through its OpenAI-compatible chat endpoint.
- OpenAI and guarded OpenAI-compatible chat providers.
- Gemini REST text generation.
- Provider connection testing through model discovery.
- Recursive context credential redaction.
- Redirect, remote HTTP, metadata endpoint, and unsafe network protections.
## 0.2.0 - 2026-08-08

### Added
- BI Publisher object existence and archive verification.
- Guarded catalog-object deletion.
- Replacement with in-memory backup and best-effort restoration.
- Read-only copy planning and dry-run support.
- Protected cross-connection copy with overwrite and verification controls.
- BI Publisher report scheduling.
- Typed lifecycle, replacement, verification, and scheduling exceptions.

### Changed
- Package version synchronized across `pyproject.toml`, `querysaas.__version__`, README, tests, and release documentation.
All notable changes to QuerySaaS are documented in this file.

## 0.1.3 - 2026-08-05

GitHub release baseline for the existing `querysaas` package. This release is additive and keeps the package name, provider name, and established public APIs unchanged.

### Added

- Comment-aware `OracleSqlPlanner` with validation, count, row-limit, and OFFSET/FETCH page planning.
- Functional SQL-planner APIs: `validate_query()`, `count_query()`, `limit_query()`, and `page_query()`.
- Structured `SqlPlan` results.
- `FusionConnection.countquery()` and `CountQueryResult`.
- Structured QuerySaaS, SQL, Oracle Fusion, BI Publisher, and pipeline exceptions.
- Atomic parallel Fusion-to-local file output with schema consistency validation.
- FBDI registry-based ZIP import, CSV packaging, DuckDB export, and purge operations.
- Friendly FBDI selector matching across business objects, control files, and interface tables.
- Single-request and request-range interface purge support.
- Generic `submit_ess_job()` for Oracle Fusion ESS submissions.
- `monitor_ess_job(request_id, finder="ESSExecutionDetailsRF")` for normalized parent and child ESS execution details.
- ESS monitor result fields for finder name, full finder expression, parent status, child jobs, terminal state, and success state.
- BI Publisher SOAP 1.2 catalog and object-management support through `ExternalReportWSSService`.
- `get_folder_contents()` for catalog roots, Shared Folders, My Folders, and nested folders.
- Case-insensitive catalog item filtering and folder-first alphabetical sorting.
- `download_bip_object()` using `downloadReportObject` with namespace-prefix-independent parsing.
- Strict Base64 validation and decoded object-size reporting.
- Object archive inference: `.xdo` to `xdoz`, `.xdm` to `xdmz`, and `.xss` to `xssz`.
- Optional binary archive output for retrieved BI Publisher objects.
- `upload_bip_object()` using `uploadReportObject`, accepting validated Base64 text or archive bytes.
- `extract_bip_object()` with ZIP validation and path-traversal protection.
- `get_bip_object_xml()` for retrieving XML-compatible BI Publisher archive members.
- Cross-connection `copy_bip_object()` that downloads through the source connection and uploads through the destination connection.
- Mocked BI Publisher and ESS tests.

### Changed

- Reworked `README.md` as the GitHub landing page with repository installation, architecture, complete public API examples, security guidance, testing, packaging, and publication instructions.
- Consolidated release history in `CHANGELOG.md` for GitHub publication.
- Parallel local-file pagination delegates SQL generation to the shared Oracle SQL planner.
- Parallel pages are written in ascending offset order even when page requests finish out of order.
- The first non-empty page establishes the header and schema.
- Later non-empty pages must preserve column names, order, and count.
- Output remains temporary until all pages succeed, preserving an existing destination after failure.
- `purge_fbdi()` now reuses `submit_ess_job()` rather than duplicating ESS REST submission logic.
- ESS parameters can be supplied as `None`, a comma-delimited string, a list, or a tuple; Python `None` becomes Oracle `#NULL`.
- BI Publisher catalog/object operations reuse the existing Fusion credentials, timeout, and SSL-verification configuration.
- BI Publisher XML parsing is independent of response namespace prefixes.
- Package metadata uses current SPDX-style license metadata.
- Project URLs point to <https://github.com/yvrnsravankumar/QuerySaaS>.

### Security

- SSL verification remains enabled by default.
- Callers do not need to construct or store pre-encoded Basic Authorization values.
- Credentials, Authorization headers, cookies, session values, report output Base64, object Base64, and complete upload SOAP bodies are excluded from normal logs and summaries.
- BI Publisher object archives are written only when explicitly requested.
- Cross-connection object copy omits Base64 from the combined result.
- Invalid object Base64 and unsupported upload archive types are rejected before upload.
- BI Publisher ZIP extraction rejects absolute paths and parent-directory traversal.

### Diagnostics

- SOAP faults are detected before operation-specific response parsing.
- HTTP 401 and 403 are distinguished as authentication and authorization failures.
- BI Publisher timeout, connection, HTTP, malformed XML, missing payload, invalid Base64, unsupported type, upload, and report execution failures receive contextual errors.
- Oracle errors such as `ORA-01722` remain visible and are classified as BI Publisher Data Model SQL errors.
- ESS monitoring parses Oracle’s nested JSON `RequestStatus` payload and returns normalized parent and child job details.

### Preserved

- Existing `querysaas` package and distribution name.
- Provider-neutral `connect()` API and `oracle_fusion` provider name.
- Existing `executequery()` calling convention and DataFrame return behavior.
- Existing DuckDB methods: `copy2dd()`, `syncquery2dd()`, `copy2dd_parallel()`, and `syncquery2dd_parallel()`.
- Existing local-file methods: `copy2file()` and `copy2file_parallel()`.
- Full-path `filename` parameter.
- Default comma delimiter and `utf-8-sig` encoding.
- One-header output behavior.
- Existing FBDI import, CSV, DuckDB, ZIP, and purge APIs.
- Existing BI Publisher report execution behavior.

## 0.1.2 - 2026-08-04

### Added

- Parallel Fusion-to-local delimited-file pipeline.
- `copy_fusion_to_local_parallel()`.
- `FusionConnection.copy2file_parallel()`.
- `LocalFileCopyResult`.
- Oracle OFFSET/FETCH page extraction with deterministic `order_by`.
- Configurable chunk size, worker count, delimiter, encoding, quoting, and header behavior.

### Preserved

- Default comma delimiter.
- Full-path destination filename.
- Existing Oracle Fusion connector and DuckDB synchronization APIs.

## 0.1.0 - 2026-08-04

### Added

- Initial QuerySaaS Python library.
- Provider-neutral `connect()` entry point.
- Oracle Fusion `FusionConnection`.
- BI Publisher report provisioning and SQL execution.
- DuckDB copy and synchronization APIs.
- Authentication header construction and Oracle Fusion connection lifecycle.

<!-- QUERYSAAS-FBDI-REGISTRY-BEGIN -->
## 0.1.4 - 2026-08-05

### Added

- Added `refresh_fbdi_jobs()` to query live Oracle Fusion FBDI metadata.
- Added `get_fbdi_jobs()` with DataFrame or dictionary output and filters for ERP family, application ID, business object, interface option ID, control file, and interface table.
- Added automatic first-use refresh for FBDI import, CSV, DuckDB, and purge operations.
- Added connection-level caching, forced refresh, validated fallback, and registry unit/live tests.

### Fixed

- Included `data/*.csv` explicitly in wheel package data.
- Preserved the packaged FBDI registry as a fallback when live metadata access is unavailable.
<!-- QUERYSAAS-FBDI-REGISTRY-END -->

## Documentation completed for 0.3.0

- Added a comprehensive public API reference with executable examples.
- Added detailed AI Assistant, BI Publisher, FBDI/ESS, architecture, security, and version-history guides.
- Added a GitHub web-interface upload and release guide for environments without Git.
- Replaced the root README with a concise 0.3.0 landing page linked to detailed documentation.