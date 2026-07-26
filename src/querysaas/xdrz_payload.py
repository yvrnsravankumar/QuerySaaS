"""Embedded BI Publisher XDRZ payload used by the Oracle Fusion connector.

Replace the placeholder below with the complete Base64 XDRZ archive before
building or publishing QuerySaaS. The payload is intentionally normalized at
import time so it may be split over multiple lines for readability.
"""

BIP_XDRZ_BASE64 = """
PASTE_YOUR_EXISTING_COMPLETE_XDRZ_BASE64_HERE
"""

BIP_XDRZ_BASE64 = "".join(BIP_XDRZ_BASE64.split())

if not BIP_XDRZ_BASE64 or BIP_XDRZ_BASE64 == "PASTE_YOUR_EXISTING_COMPLETE_XDRZ_BASE64_HERE":
    raise RuntimeError(
        "QuerySaaS has no embedded BIP XDRZ payload. Replace the placeholder "
        "in querysaas/xdrz_payload.py before using the Oracle Fusion connector."
    )
