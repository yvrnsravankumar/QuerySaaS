# Version History

## 0.3.2

BI Publisher Phase 1 consolidated into the source package.


## 0.3.3

Corrected BI Publisher exception identity and metadata, CREATE eventual-consistency behavior, readable committed-write handling, scheduling notification defaults, and verification-mode documentation. Built as a new release because published package files are immutable.


## 0.3.4
Added the DuckDB-backed Local Data Library with filename-as-table aliases, managed-table DML, and CSV, TSV, and Parquet export.


## 0.3.5

Standardized retries across approved network-bound query, file extraction, DuckDB synchronization, BI Publisher read, FBDI registry read, and ESS monitoring methods. The default is three retries with capped exponential backoff and jitter. Non-idempotent submissions remain excluded from blind automatic retries.
