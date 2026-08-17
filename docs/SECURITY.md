# Security

Credentials, tokens, archive Base64, P_B64_CONTENT, and full recipients are excluded from public diagnostics. Destructive catalog operations use verified state transitions.


## Safe exception serialization

`BIPOperationError.to_dict()` redacts credentials, authorization values, tokens, passwords, cookies, archive payloads, `P_B64_CONTENT`, and notification recipients. Replacement exceptions retain real cause objects internally but serialize only safe text and verification metadata.
