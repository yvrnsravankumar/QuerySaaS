# Changelog
## 0.3.8 - 2026-08-20

### Added

- Automatic OpenAI-compatible model discovery using only an API URL and key.
- Model discovery through the OpenAI-compatible `/models` route.
- Automatic preferred-model selection and chat-completion verification.
- Support for API URLs supplied as either a gateway root or `/v1` API root.
- DuckDB AI SQL generation supporting DDL, DML, transactions, administration statements, and multi-statement scripts.
- Explicit Oracle Fusion and DuckDB AI SQL execution targets.
- Resumable CSV and Parquet part-file extraction.
- Checkpoint verification, manifests, SHA-256 hashes, and failed-page splitting.
- Expanded Local Data Library, FBDI, ESS, and BI Publisher capabilities.
- Comprehensive replacement README covering the complete QuerySaaS feature set.

### Changed

- Increased the canonical parallel worker limit to 32.
- Changed automatic parallel planning to use up to 32 workers.
- Changed automatic pending-page planning to use up to 64 pending pages.
- Preserved Oracle Fusion AI SQL as read-only.
- Allowed complete DuckDB SQL generation, including unrestricted valid DDL and DML.
- Preserved legacy Fusion methods while documenting canonical replacements.

### Performance

- Validated a 9,549,914-row GL_BALANCES extraction using 32 workers.
- Completed the QuerySaaS pipeline in approximately 56 minutes.
- Achieved approximately 2,843 rows per second.
- Completed with no failed requests or retries.
- Completed with no malformed rows, empty primary keys, ordering errors, or adjacent duplicate keys.

### Validation

- 206 tests passed.
- 1 test skipped.
- Automatic AI model-discovery tests passed.
- OpenAI-compatible transport tests passed.
- DuckDB AI SQL tests passed.
- Oracle Fusion SQL safety tests passed.
- Parallel extraction and planning tests passed.
## 0.3.7 - 2026-08-18
### Added
- Automatic row-count planning for chunk size, workers, pending pages, and total chunks.
- Atomic CSV and Parquet part-file datasets with manifest row counts and SHA-256 hashes.
- Canonical wrapper support for progress and all Phase 1 parallel options.
### Added
- Automatic row-count planning for chunk size, workers, pending pages, and total chunks.
- Atomic CSV and Parquet part-file datasets with manifest row counts and SHA-256 hashes.
- Canonical wrapper support for progress and all Phase 1 parallel options.
### Changed
- Parallel file extraction uses persistent bounded scheduling instead of repeated executor waves.
- Retry options are forwarded to each page and the complete operation is no longer blindly retried.
- Added page, pending, elapsed-time, and throughput metrics plus optional summary progress.
### Preserved
- Ordered output, schema checks, atomic replacement, legacy methods, unified 0.3.6 API, and QuerySaaS Studio compatibility.

## 0.3.6 - 2026-08-18
### Added
- Canonical Fusion method names with all legacy methods preserved.
- Automatic sequential routing for 5,000 rows or fewer and parallel routing above 5,000 rows.
- Table-only SOURCE_ROWID fallback through the existing validated table-copy behavior.
- Permanent pytest exclusions for backups, patches, reports, and generated folders.
### Preserved
- QuerySaaS 0.3.5 extraction, retry, DuckDB, BI Publisher, FBDI, ESS, AI, and Local Data Library engines.
- QuerySaaS Studio compatibility.

## 0.3.5 - 2026-08-17

### Added
- Consistent `max_retries=3`, `retry_base_seconds=1.0`, and `retry_max_seconds=30.0` parameters for approved network-bound methods.
- Shared capped exponential-backoff retry policy with jitter.
- Retry exhaustion metadata for structured operational exceptions when supported.
- Signature and behavior regression tests for query, extraction, BI Publisher read, FBDI registry read, and ESS monitoring methods.

### Changed
- Network query retry defaults are standardized to three retries, meaning four total attempts.
- Parallel file and DuckDB extraction operations inherit the same page-level retry contract.

### Security
- Authentication, authorization, invalid SQL, protected operations, schema mismatches, and cancellations are never retried automatically.
- Local Data Library methods remain outside the network retry layer.

## 0.3.4 - 2026-08-17
### Added
- DuckDB-backed Local Data Library for CSV, TSV, and Parquet folders.
- Exact quoted filename aliases and normalized SQL-safe aliases.
- Managed-table DML, transactional execution, discovery, preview, materialization, and export methods.
- CSV, TSV, and Parquet export support.
### Preserved
- All existing QuerySaaS public methods and behavior.
## 0.3.3 - 2026-08-09

### Added
- Metadata-aware BI Publisher exceptions with safe `to_dict()` serialization.
- CREATE destination-availability and readability handling with timeout controls.
- Regression coverage for ambiguous uploads, delayed visibility, and committed readable targets.

### Fixed
- Duplicate BI Publisher exception class identity in `bip.py`.
- Fully initialized replacement diagnostics and preserved exception cause chains.
- CREATE propagation timing without duplicate upload attempts.
- Replacement handling so readable committed targets are not rolled back.
- Scheduling notification defaults so notifications are opt-in.
- Verification-mode advertising so only `readable` is accepted.

### Security
- Redacted tokens, credentials, archive payloads, `P_B64_CONTENT`, and recipient metadata in serialized exceptions.
- Retained recipient masking and omission of scheduling parameter values from public results.

### Validation
- Oracle integration tests remain opt-in and were not run without credentials.
- No QuerySaaS Studio files or installed Studio packages were modified.


## 0.3.2 - 2026-08-09

### 0.3.2 BI Publisher correctness update

- Added metadata-aware, redacted BI Publisher exception serialization.
- Removed duplicate exception declarations from `bip.py`.
- Added CREATE visibility polling and timeout propagation.
- Preserved readable committed replacements after ambiguous uploads or upload exceptions.
- Made scheduling notifications opt-in and required explicit recipient and username when enabled.
- Restricted verification modes to the implemented `readable` contract.

- Consolidated BI Publisher transport, lifecycle, scheduling, exceptions, redaction, and tests.
- Added verified deletion and restoration, ambiguous-write verification, protected roots, read-only planning, and canonical copy.
- Added ScheduleReportWSSService scheduling with nested parameters and notification controls.

## 0.3.1 - 2026-08-08

### Fixed
- Use the Oracle Fusion BI Publisher `deleteReport` SOAP operation.
- Parse `deleteReportReturn` and `deleteReportResult` responses.
- Retain legacy delete response element names as parsing fallbacks.
- Keep SSO Bearer and Basic Authorization behavior unchanged.
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
