# Security

Credentials, tokens, archive Base64, P_B64_CONTENT, and full recipients are excluded from public diagnostics. Destructive catalog operations use verified state transitions.


## Safe exception serialization

`BIPOperationError.to_dict()` redacts credentials, authorization values, tokens, passwords, cookies, archive payloads, `P_B64_CONTENT`, and notification recipients. Replacement exceptions retain real cause objects internally but serialize only safe text and verification metadata.


## Retry safety

QuerySaaS retries only the approved network-bound read, query, extraction, registry, and monitoring operations. HTTP 401, HTTP 403, invalid SQL, invalid parameters, protected catalog operations, schema mismatches, and explicit cancellation are never retried. Non-idempotent BI Publisher uploads, scheduling submissions, FBDI submissions, ESS submissions, and purge submissions are intentionally excluded from the automatic retry installer to prevent duplicate Oracle operations.
