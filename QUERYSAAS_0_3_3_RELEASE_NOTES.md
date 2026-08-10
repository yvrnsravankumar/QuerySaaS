# QuerySaaS 0.3.3 Release Notes

QuerySaaS 0.3.3 is the publishable correction release for the BI Publisher consolidation originally released as 0.3.2.

## Added

- Metadata-aware BI Publisher exceptions.
- Safe exception `to_dict()` serialization.
- CREATE eventual-consistency handling with `timeout` and `poll_interval`.
- Regression tests for ambiguous Oracle upload responses and delayed catalog visibility.

## Fixed

- HTTP 500 SOAP-fault classification remains ahead of generic HTTP handling.
- Duplicate BI Publisher exception identity.
- Replacement exception construction and cause preservation.
- CREATE propagation timing without duplicate uploads.
- Readable committed replacement preservation.
- Scheduling notification defaults and validation.
- Unsupported verification modes are rejected instead of silently ignored.

## Security

- Archive payload, authorization, token, cookie, password, `P_B64_CONTENT`, and recipient redaction.
- Notification recipients remain masked in public results.
- Scheduling parameter values are omitted from public results.

## Known limitations

- QuerySaaS 0.3.3 supports only `verification_mode="readable"`.
- Raw ZIP equality is not used because Oracle may repackage BI Publisher archives.
- Oracle Fusion integration testing is opt-in and requires explicit credentials.
- This preparation does not publish to PyPI and does not update QuerySaaS Studio.
