"""Oracle BI Publisher catalog and object-management operations."""
from __future__ import annotations
import base64, binascii, io, re, time, zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET
import requests
try:
    from defusedxml import ElementTree as SafeET
except ImportError:  # pragma: no cover
    SafeET = ET
from .exceptions import (
    BIPAuthenticationError,
    BIPAuthorizationError,
    BIPCatalogError,
    BIPConnectionError,
    BIPDeleteError,
    BIPHTTPError,
    BIPInvalidBase64Error,
    BIPInvalidResponseError,
    BIPObjectAlreadyExistsError,
    BIPObjectNotFoundError,
    BIPOperationError,
    BIPReplaceError,
    BIPReportExecutionError,
    BIPRestoreError,
    BIPSOAPFaultError,
    BIPScheduleError,
    BIPTimeoutError,
    BIPUnsupportedObjectTypeError,
    BIPUploadError,
    BIPVerificationError,
)

SOAP_NS = "http://www.w3.org/2003/05/soap-envelope"
PUBLIC_REPORT_NS = "http://xmlns.oracle.com/oxp/service/PublicReportService"
SCHEDULE_REPORT_NS = "http://xmlns.oracle.com/oxp/service/ScheduleReportService"
EXTERNAL_REPORT_SERVICE_PATH = "/xmlpserver/services/ExternalReportWSSService"
SCHEDULE_REPORT_SERVICE_PATH = "/xmlpserver/services/ScheduleReportWSSService"
PUB_NS = PUBLIC_REPORT_NS
SERVICE_PATH = EXTERNAL_REPORT_SERVICE_PATH
TYPES = {"xdoz", "xdmz", "xssz"}
TYPE_MAP = {".xdo": "xdoz", ".xdm": "xdmz", ".xss": "xssz"}
XML_EXTENSIONS = {".xdo", ".xdm", ".xpt", ".xss", ".cfg", ".meta", ".sec", ".xml"}
SENSITIVE_KEYS = (
    "token", "authorization", "password", "cookie", "base64", "payload",
    "zipped", "archive_data", "object_zipped_data", "p_b64_content",
)
MISSING_BIP_TOKENS = (
    "unable to find reportobject", "unable to find report object",
    "unable to download report", "reportobject not found",
    "report object not found", "does not exist", "cannot find", "not found",
    "returned no object payload",
)

ET.register_namespace("soap", SOAP_NS)
ET.register_namespace("pub", PUBLIC_REPORT_NS)
ET.register_namespace("sch", SCHEDULE_REPORT_NS)


def _local(tag):
    return tag.rsplit("}", 1)[-1]


def _path(value, *, allow_empty=False, trailing=False):
    if value is None:
        value = ""
    value = str(value).strip()
    if not value and allow_empty:
        return ""
    if not value:
        raise ValueError("BI Publisher catalog path cannot be empty.")
    if not value.startswith("/"):
        value = "/" + value
    if not trailing and value != "/":
        value = value.rstrip("/")
    return value


def _object_type(value):
    value = str(value or "").strip().lower().lstrip(".")
    if value not in TYPES:
        raise BIPUnsupportedObjectTypeError(
            "Unsupported BI Publisher object type. Supported values: xdoz, xdmz, xssz."
        )
    return value


def _archive_type(report_path):
    return TYPE_MAP.get(Path(report_path).suffix.lower(), "unknown")


def _redact_text(value):
    text = str(value or "")
    patterns = (
        r"(?is)(<[^>]*(?:objectZippedData|downloadReportObjectReturn|reportBytes|P_B64_CONTENT)[^>]*>).*?(</[^>]+>)",
        r"(?i)(Authorization\s*:\s*)(?:Bearer|Basic)\s+\S+",
        r"(?i)\b(password|token|secret|cookie|api[_-]?key)\b\s*[:=]\s*[^\s,;]+",
    )
    text = re.sub(patterns[0], r"\1[REDACTED]\2", text)
    text = re.sub(patterns[1], r"\1[REDACTED]", text)
    text = re.sub(patterns[2], r"\1=[REDACTED]", text)
    return text


def _preview(text, limit=800):
    return _redact_text(text)[:limit]


def _safe_metadata(value):
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            name = str(key)
            if any(secret in name.casefold() for secret in SENSITIVE_KEYS):
                result[name] = "[REDACTED]"
            else:
                result[name] = _safe_metadata(item)
        return result
    if isinstance(value, (list, tuple)):
        return [_safe_metadata(item) for item in value]
    if isinstance(value, BaseException):
        return _preview(str(value))
    if isinstance(value, (str, int, float, bool)) or value is None:
        return _redact_text(value) if isinstance(value, str) else value
    return _preview(repr(value))


def _envelope(operation, values, *, namespace=PUBLIC_REPORT_NS):
    env = ET.Element(f"{{{SOAP_NS}}}Envelope")
    ET.SubElement(env, f"{{{SOAP_NS}}}Header")
    body = ET.SubElement(env, f"{{{SOAP_NS}}}Body")
    op = ET.SubElement(body, f"{{{namespace}}}{operation}")
    for name, value in values:
        element = ET.SubElement(op, f"{{{namespace}}}{name}")
        element.text = str(value)
    return ET.tostring(env, encoding="utf-8", xml_declaration=True)


def _soap_fault(root, *, operation, status_code=None):
    for element in root.iter():
        if _local(element.tag) != "Fault":
            continue
        code = reason = detail = None
        for item in element.iter():
            local = _local(item.tag)
            text = (item.text or "").strip()
            if local in {"Value", "faultcode"} and not code:
                code = text
            elif local in {"Text", "faultstring"} and not reason:
                reason = text
            elif local in {"Detail", "detail"} and text:
                detail = text
        combined = " ".join(part for part in (reason, detail) if part)
        ora = re.search(r"(ORA-\d{5}):\s*([^\r\n<]+)", combined)
        error = BIPSOAPFaultError(
            f"BI Publisher {operation} SOAP fault: {_preview(reason or detail or 'Unknown fault')}",
            operation=operation,
            status_code=status_code,
            soap_fault_code=code,
            soap_fault_reason=_redact_text(reason),
            oracle_error_code=ora.group(1) if ora else None,
            oracle_message=_redact_text(ora.group(2).strip()) if ora else None,
        )
        raise error


def _sender(self):
    return (
        getattr(getattr(self, "session", None), "post", None)
        or getattr(getattr(self, "_session", None), "post", None)
        or requests.post
    )


def _transport(self, operation, values, *, service_path=EXTERNAL_REPORT_SERVICE_PATH,
               namespace=PUBLIC_REPORT_NS, payload=None):
    url = self.url.rstrip("/") + service_path
    request_body = payload if payload is not None else _envelope(operation, values, namespace=namespace)
    headers = {
        "Authorization": self.auth_header,
        "Content-Type": "application/soap+xml; charset=UTF-8",
        "Accept": "application/soap+xml, text/xml",
    }
    try:
        response = _sender(self)(
            url, headers=headers, data=request_body, timeout=self.timeout,
            verify=self.verify_ssl,
        )
    except requests.Timeout as exc:
        raise BIPTimeoutError(
            f"BI Publisher {operation} timed out after {self.timeout} seconds.",
            operation=operation,
        ) from exc
    except requests.ConnectionError as exc:
        raise BIPConnectionError(
            f"BI Publisher {operation} connection failed.", operation=operation
        ) from exc

    if response.status_code == 401:
        raise BIPAuthenticationError(
            f"BI Publisher {operation} authentication failed (HTTP 401).",
            operation=operation, status_code=401,
        )
    if response.status_code == 403:
        raise BIPAuthorizationError(
            f"BI Publisher {operation} authorization failed (HTTP 403).",
            operation=operation, status_code=403,
        )

    root = None
    if getattr(response, "content", b""):
        try:
            root = SafeET.fromstring(response.content)
        except Exception:
            root = None
    if root is not None:
        _soap_fault(root, operation=operation, status_code=response.status_code)
    if not response.ok:
        raise BIPHTTPError(
            f"BI Publisher {operation} failed (HTTP {response.status_code}): "
            f"{_preview(getattr(response, 'text', ''))}",
            operation=operation, status_code=response.status_code,
        )
    if root is None:
        raise BIPInvalidResponseError(
            f"BI Publisher {operation} returned invalid XML.",
            operation=operation, status_code=response.status_code,
        )
    return root


def _fault(root):
    """Backward-compatible internal fault parser."""
    return _soap_fault(root, operation="unknown")


def _is_missing_bip_error(error):
    text = " ".join(
        str(value or "")
        for value in (
            getattr(error, "soap_fault_reason", None),
            getattr(error, "oracle_message", None),
            str(error),
        )
    ).casefold()
    return any(token in text for token in MISSING_BIP_TOKENS)



def _validate_bool(name, value):
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be True or False.")


def _validate_polling(timeout, poll_interval):
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
        raise ValueError("timeout must be greater than zero.")
    if isinstance(poll_interval, bool) or not isinstance(poll_interval, (int, float)) or poll_interval <= 0:
        raise ValueError("poll_interval must be greater than zero.")
    if poll_interval > timeout:
        raise ValueError("poll_interval cannot exceed timeout.")


def _protected_catalog_path(path):
    normalized = path.rstrip("/") or "/"
    protected = {"/", "/custom", "/shared folders"}
    if normalized.casefold() in protected:
        return True
    parts = [part for part in normalized.split("/") if part]
    return len(parts) == 1 and parts[0].startswith("~")


def _wait_for_state(connection, path, *, exists, timeout, poll_interval):
    deadline = time.monotonic() + timeout
    last = None
    while True:
        last = bool(connection.bip_object_exists(path))
        if last is exists:
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(poll_interval)


def _public_download(downloaded):
    return {key: value for key, value in downloaded.items() if key != "object_zipped_data"}


def _warning(error):
    if error is None:
        return None
    return {
        "type": type(error).__name__,
        "message": _preview(str(error)),
        "operation": getattr(error, "operation", None),
        "status_code": getattr(error, "status_code", None),
        "soap_fault_code": getattr(error, "soap_fault_code", None),
        "soap_fault_reason": _redact_text(getattr(error, "soap_fault_reason", None)),
        "oracle_error_code": getattr(error, "oracle_error_code", None),
        "oracle_message": _redact_text(getattr(error, "oracle_message", None)),
    }

def _find(root,names):
    for preferred in names:
        for e in root.iter():
            if _local(e.tag)==preferred: return e
    return None

def _decode(value):
    if isinstance(value,dict): value=value.get("object_zipped_data")
    if isinstance(value,str):
        value="".join(value.split())
        if not value: raise BIPInvalidBase64Error("BI Publisher object Base64 cannot be empty.")
        try: data=base64.b64decode(value,validate=True)
        except (ValueError,binascii.Error) as exc: raise BIPInvalidBase64Error("BI Publisher object data is not valid Base64.") from exc
    elif isinstance(value,(bytes,bytearray)):
        data=bytes(value)
        if not data: raise BIPInvalidResponseError("BI Publisher archive bytes cannot be empty.")
    else: raise TypeError("Object data must be Base64 text, bytes, or a download result dictionary.")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            bad=z.testzip()
            if bad: raise BIPInvalidResponseError(f"BI Publisher archive contains a corrupt member: {bad}")
    except zipfile.BadZipFile as exc: raise BIPInvalidResponseError("BI Publisher object is not a valid ZIP archive.") from exc
    return data

def get_folder_contents(self, folder_absolute_path="", item_type=None):
    folder=_path(folder_absolute_path,allow_empty=True)
    root=_transport(self,"getFolderContents",[("folderAbsolutePath",folder)])
    fields={"absolutePath":"absolute_path","creationDate":"creation_date","displayName":"display_name","fileName":"file_name","lastModified":"last_modified","lastModifier":"last_modifier","owner":"owner","parentAbsolutePath":"parent_absolute_path","type":"type"}
    items=[]
    candidates=[e for e in root.iter() if _local(e.tag) in {"item","catalogItem","getFolderContentsReturn"}]
    for node in candidates:
        values={name:None for name in fields.values()}
        found=False
        for child in node.iter():
            local=_local(child.tag)
            if local in fields: values[fields[local]]=(child.text or "").strip() or None; found=True
        if found and values not in items: items.append(values)
    if item_type is not None: items=[x for x in items if (x.get("type") or "").casefold()==str(item_type).strip().casefold()]
    items.sort(key=lambda x:(0 if (x.get("type") or "").casefold()=="folder" else 1,(x.get("display_name") or x.get("file_name") or "").casefold()))
    return {"success":True,"folder_absolute_path":folder,"count":len(items),"items":items}


def download_bip_object(self, report_absolute_path, output_file=None, overwrite=False):
    """Download, decode once, and validate a BI Publisher object archive."""
    _validate_bool("overwrite", overwrite)
    report_path = _path(report_absolute_path)
    root = _transport(
        self,
        "downloadReportObject",
        [("reportAbsolutePath", report_path)],
    )
    element = _find(
        root,
        ["downloadReportObjectReturn", "objectZippedData", "reportObjectData", "reportObject"],
    )
    if element is None or not "".join(element.itertext()).strip():
        raise BIPObjectNotFoundError(
            f"BI Publisher returned no object payload for {report_path}.",
            operation="downloadReportObject",
            report_absolute_path=report_path,
        )
    normalized = "".join("".join(element.itertext()).split())
    archive = _decode(normalized)
    object_type = _archive_type(report_path)
    saved = None
    if output_file is not None:
        target = Path(output_file).expanduser()
        if not target.suffix and object_type != "unknown":
            target = target.with_suffix("." + object_type)
        target = target.resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and not overwrite:
            raise FileExistsError(f"Destination already exists: {target}")
        target.write_bytes(archive)
        saved = str(target)
    return {
        "success": True,
        "operation": "downloadReportObject",
        "report_absolute_path": report_path,
        "object_type": object_type,
        "object_size_bytes": len(archive),
        "object_zipped_data": normalized,
        "output_file": saved,
    }


def upload_bip_object(self, report_object_absolute_path_url, object_type, object_zipped_data):
    """Validate and upload one BI Publisher archive without exposing its payload."""
    destination = _path(report_object_absolute_path_url)
    kind = _object_type(object_type)
    archive = _decode(object_zipped_data)
    encoded = base64.b64encode(archive).decode("ascii")
    root = _transport(
        self,
        "uploadReportObject",
        [
            ("reportObjectAbsolutePathURL", destination),
            ("objectType", kind),
            ("objectZippedData", encoded),
        ],
    )
    element = _find(root, ["uploadReportObjectReturn", "uploadReportObjectResult", "return"])
    raw = (element.text or "").strip() if element is not None else None
    confirmed = raw is not None and raw.casefold() in {"true", "success", "successful", "1", "yes"}
    return {
        "success": confirmed,
        "confirmed": confirmed,
        "ambiguous": not confirmed,
        "operation": "uploadReportObject",
        "report_object_absolute_path_url": destination,
        "object_type": kind,
        "object_size_bytes": len(archive),
        "oracle_result": raw,
    }

def extract_bip_object(self, object_zipped_data, output_directory=None, overwrite=False):
    data=_decode(object_zipped_data); destination=Path(output_directory).expanduser().resolve() if output_directory is not None else None
    if destination: destination.mkdir(parents=True,exist_ok=True)
    members=[]
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for item in z.infolist():
            if item.is_dir(): continue
            member=Path(item.filename)
            if member.is_absolute() or ".." in member.parts: raise BIPInvalidResponseError(f"Unsafe BI Publisher archive member: {item.filename}")
            content=z.read(item); saved=None
            if destination:
                target=(destination/member).resolve()
                try: target.relative_to(destination)
                except ValueError as exc: raise BIPInvalidResponseError(f"Unsafe BI Publisher archive member: {item.filename}") from exc
                if target.exists() and not overwrite: raise FileExistsError(f"Destination already exists: {target}")
                target.parent.mkdir(parents=True,exist_ok=True); target.write_bytes(content); saved=str(target)
            members.append({"name":item.filename,"size_bytes":len(content),"is_xml":member.suffix.casefold() in XML_EXTENSIONS,"output_file":saved})
    return {"success":True,"operation":"extract_bip_object","object_size_bytes":len(data),"member_count":len(members),"members":members,"output_directory":str(destination) if destination else None}

def get_bip_object_xml(self, report_absolute_path, member_name=None, include_non_xml=False):
    downloaded=self.download_bip_object(report_absolute_path); data=_decode(downloaded)
    result={}
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names=[member_name] if member_name else [i.filename for i in z.infolist() if not i.is_dir()]
        for name in names:
            if name not in z.namelist(): raise BIPObjectNotFoundError(f"BI Publisher archive member not found: {name}")
            suffix=Path(name).suffix.casefold()
            if suffix not in XML_EXTENSIONS and not include_non_xml: continue
            content=z.read(name)
            try: text=content.decode("utf-8-sig")
            except UnicodeDecodeError:
                if include_non_xml: result[name]={"size_bytes":len(content),"content_type":"application/octet-stream","text":None}
                continue
            valid=None; error=None
            if suffix in XML_EXTENSIONS:
                try: SafeET.fromstring(content); valid=True
                except Exception as exc: valid=False; error=str(exc)
            result[name]={"size_bytes":len(content),"content_type":"application/xml" if suffix in XML_EXTENSIONS else "text/plain","xml_valid":valid,"xml_error":error,"text":text}
    base={"success":True,"operation":"get_bip_object_xml","report_absolute_path":downloaded["report_absolute_path"],"object_type":downloaded["object_type"],"object_size_bytes":downloaded["object_size_bytes"]}
    if member_name:
        if member_name not in result: raise BIPInvalidResponseError(f"Requested member could not be decoded: {member_name}")
        return {**base,"member_name":member_name,**result[member_name]}
    return {**base,"member_count":len(result),"members":result}

class BIPObjectAlreadyExistsError(BIPCatalogError):
    """Raised when an operation would overwrite an existing catalog object."""

class BIPVerificationError(BIPCatalogError):
    """Raised when a BI Publisher object cannot be verified."""

class BIPDeleteError(BIPCatalogError):
    """Raised when a BI Publisher object cannot be deleted safely."""

class BIPReplaceError(BIPCatalogError):
    """Raised when replacement or restoration fails."""

class BIPScheduleError(BIPReportExecutionError):
    """Raised when a BI Publisher schedule request fails."""


def _bool_result(root, names):
    element = _find(root, names)
    raw = (element.text or "").strip() if element is not None else None
    if raw is None:
        return True, None
    return raw.casefold() in {"true", "success", "successful", "1", "yes"}, raw


def bip_object_exists(self, report_absolute_path):
    """Return False only for recognized missing-object failures."""
    path = _path(report_absolute_path)
    try:
        result = self.download_bip_object(path)
    except BIPObjectNotFoundError:
        return False
    except (BIPSOAPFaultError, BIPHTTPError) as exc:
        if _is_missing_bip_error(exc):
            return False
        raise
    return bool(result.get("success"))



def verify_bip_object(self, report_absolute_path, object_type=None, verification_mode="readable"):
    """Verify readability and object-type compatibility; raw ZIP equality is optional."""
    path = _path(report_absolute_path)
    mode = str(verification_mode or "").strip().casefold()
    if mode not in {"readable", "primary_content", "nonvolatile_members", "raw_archive"}:
        raise ValueError("Unsupported verification_mode.")
    downloaded = self.download_bip_object(path)
    archive_data = _decode(downloaded)
    inferred = downloaded.get("object_type") or "unknown"
    expected = _object_type(object_type) if object_type is not None else inferred
    if expected != "unknown" and inferred != "unknown" and expected != inferred:
        raise BIPVerificationError(
            f"BI Publisher object type mismatch for {path}: expected {expected}, received {inferred}.",
            operation="verify_bip_object",
            report_absolute_path=path,
        )
    with zipfile.ZipFile(io.BytesIO(archive_data)) as archive:
        bad = archive.testzip()
        if bad:
            raise BIPVerificationError(
                f"BI Publisher archive contains a corrupt member: {bad}",
                operation="verify_bip_object",
                report_absolute_path=path,
            )
        members = [item.filename for item in archive.infolist() if not item.is_dir()]
    if not members:
        raise BIPVerificationError(
            f"BI Publisher object archive is empty: {path}",
            operation="verify_bip_object",
            report_absolute_path=path,
        )
    return {
        "success": True,
        "operation": "verify_bip_object",
        "report_absolute_path": path,
        "object_type": inferred,
        "object_size_bytes": len(archive_data),
        "member_count": len(members),
        "members": members,
        "verification_mode": mode,
    }


def delete_bip_object(
    self,
    report_absolute_path,
    *,
    missing_ok=False,
    verify=True,
    timeout=10,
    poll_interval=0.5,
):
    """Delete through deleteReport and optionally poll until absence is confirmed."""
    _validate_bool("missing_ok", missing_ok)
    _validate_bool("verify", verify)
    _validate_polling(timeout, poll_interval)
    path = _path(report_absolute_path)
    if _protected_catalog_path(path):
        raise BIPDeleteError(
            f"Refusing to delete protected BI Publisher catalog path: {path}",
            operation="delete_bip_object",
            report_absolute_path=path,
        )
    if not self.bip_object_exists(path):
        if missing_ok:
            return {
                "success": True,
                "operation": "delete_bip_object",
                "soap_operation": "deleteReport",
                "report_absolute_path": path,
                "deleted": False,
                "missing": True,
                "verified": True if verify else None,
                "oracle_result": None,
            }
        raise BIPObjectNotFoundError(
            f"BI Publisher object does not exist: {path}",
            operation="delete_bip_object",
            report_absolute_path=path,
        )
    root = _transport(self, "deleteReport", [("reportAbsolutePath", path)])
    success, raw = _bool_result(
        root,
        ["deleteReportReturn", "deleteReportResult", "deleteReportObjectReturn", "deleteReportObjectResult", "return"],
    )
    if not success:
        raise BIPDeleteError(
            f"BI Publisher did not confirm deletion of {path}: {raw}",
            operation="delete_bip_object",
            report_absolute_path=path,
        )
    verified = None
    if verify:
        verified = _wait_for_state(
            self, path, exists=False, timeout=timeout, poll_interval=poll_interval
        )
        if not verified:
            raise BIPDeleteError(
                f"BI Publisher object remained after deleteReport: {path}",
                operation="delete_bip_object",
                report_absolute_path=path,
                metadata={"timeout": timeout, "poll_interval": poll_interval},
            )
    return {
        "success": True,
        "operation": "delete_bip_object",
        "soap_operation": "deleteReport",
        "report_absolute_path": path,
        "deleted": True,
        "missing": False,
        "verified": verified,
        "oracle_result": raw,
    }


def plan_bip_object_copy(
    self,
    destination_connection,
    source_report_absolute_path,
    destination_absolute_path,
    object_type=None,
    overwrite=False,
):
    """Resolve SOURCE_MISSING, CREATE, REPLACE, or BLOCKED without writes."""
    if destination_connection is None or not callable(getattr(destination_connection, "bip_object_exists", None)):
        raise TypeError("destination_connection must be an open QuerySaaS Fusion connection.")
    _validate_bool("overwrite", overwrite)
    source = _path(source_report_absolute_path)
    destination = _path(destination_absolute_path)
    kind = _object_type(object_type) if object_type is not None else _archive_type(source)
    source_exists = self.bip_object_exists(source)
    destination_exists = destination_connection.bip_object_exists(destination)
    if not source_exists:
        action = "SOURCE_MISSING"
    elif destination_exists and not overwrite:
        action = "BLOCKED_DESTINATION_EXISTS"
    elif destination_exists:
        action = "REPLACE"
    else:
        action = "CREATE"
    return {
        "success": source_exists and action != "BLOCKED_DESTINATION_EXISTS",
        "operation": "plan_bip_object_copy",
        "source_report_absolute_path": source,
        "destination_absolute_path": destination,
        "object_type": kind,
        "source_exists": source_exists,
        "destination_exists": destination_exists,
        "overwrite": overwrite,
        "action": action,
    }


def replace_bip_object(
    self,
    report_object_absolute_path_url,
    object_type,
    object_zipped_data,
    *,
    verify=True,
    timeout=10,
    poll_interval=0.5,
):
    """Replace safely, preserving committed readable writes and verified restoration."""
    _validate_bool("verify", verify)
    _validate_polling(timeout, poll_interval)
    destination = _path(report_object_absolute_path_url)
    kind = _object_type(object_type)
    replacement = _decode(object_zipped_data)
    existed = self.bip_object_exists(destination)
    backup = self.download_bip_object(destination) if existed else None
    deleted = False
    upload = None
    upload_error = None
    verification = None
    if existed:
        self.delete_bip_object(
            destination, verify=True, timeout=timeout, poll_interval=poll_interval
        )
        deleted = True
    try:
        upload = self.upload_bip_object(destination, kind, replacement)
    except Exception as exc:
        upload_error = exc
    try:
        if verify or upload_error is not None or not (upload or {}).get("success"):
            if not _wait_for_state(self, destination, exists=True, timeout=timeout, poll_interval=poll_interval):
                raise BIPVerificationError(
                    f"Replacement object did not become available: {destination}",
                    operation="replace_bip_object",
                    report_absolute_path=destination,
                )
            verification = self.verify_bip_object(destination, kind)
        if verification and verification.get("success"):
            return {
                "success": True,
                "operation": "replace_bip_object",
                "report_absolute_path": destination,
                "object_type": kind,
                "replaced_existing": existed,
                "backup": (
                    {"object_type": backup.get("object_type"), "object_size_bytes": backup.get("object_size_bytes")}
                    if backup else None
                ),
                "upload": upload,
                "upload_warning": _warning(upload_error) if upload_error else (
                    None if (upload or {}).get("success") else {"type": "AmbiguousUploadResult", "message": "Oracle did not positively confirm the upload."}
                ),
                "verification": verification,
                "restored": False,
            }
        if not verify and upload_error is None and (upload or {}).get("success"):
            return {
                "success": True,
                "operation": "replace_bip_object",
                "report_absolute_path": destination,
                "object_type": kind,
                "replaced_existing": existed,
                "backup": ({"object_type": backup.get("object_type"), "object_size_bytes": backup.get("object_size_bytes")} if backup else None),
                "upload": upload,
                "upload_warning": None,
                "verification": None,
                "restored": False,
            }
        raise upload_error or BIPVerificationError(
            f"Replacement was not confirmed for {destination}",
            operation="replace_bip_object",
            report_absolute_path=destination,
        )
    except Exception as replacement_error:
        restore_attempted = backup is not None
        restored = False
        restoration_error = None
        restoration_verification = None
        if backup is not None:
            try:
                if self.bip_object_exists(destination):
                    self.delete_bip_object(
                        destination, missing_ok=True, verify=True,
                        timeout=timeout, poll_interval=poll_interval,
                    )
                self.upload_bip_object(
                    destination, backup["object_type"], backup["object_zipped_data"]
                )
                if not _wait_for_state(self, destination, exists=True, timeout=timeout, poll_interval=poll_interval):
                    raise BIPRestoreError(
                        f"Restored object did not become available: {destination}",
                        operation="replace_bip_object",
                        report_absolute_path=destination,
                    )
                restoration_verification = self.verify_bip_object(
                    destination, backup["object_type"]
                )
                restored = bool(restoration_verification.get("success"))
            except Exception as exc:
                restoration_error = exc
        error = BIPReplaceError(
            f"BI Publisher replacement failed for {destination}; restored={restored}.",
            operation="replace_bip_object",
            report_absolute_path=destination,
        )
        error.object_type = kind
        error.deleted = deleted
        error.restore_attempted = restore_attempted
        error.restored = restored
        error.replacement_error = replacement_error
        error.restoration_error = restoration_error
        error.restoration_verification = _safe_metadata(restoration_verification)
        raise error from replacement_error


def copy_bip_object(
    self,
    destination_connection,
    source_report_absolute_path,
    destination_absolute_path,
    object_type=None,
    *,
    overwrite=False,
    verify=True,
    dry_run=False,
):
    """Plan and execute CREATE or REPLACE without exposing archive payloads."""
    _validate_bool("overwrite", overwrite)
    _validate_bool("verify", verify)
    _validate_bool("dry_run", dry_run)
    plan = plan_bip_object_copy(
        self,
        destination_connection,
        source_report_absolute_path,
        destination_absolute_path,
        object_type=object_type,
        overwrite=overwrite,
    )
    if dry_run:
        return plan
    if plan["action"] == "SOURCE_MISSING":
        raise BIPObjectNotFoundError(
            f"BI Publisher source object does not exist: {plan['source_report_absolute_path']}",
            operation="copy_bip_object",
            report_absolute_path=plan["source_report_absolute_path"],
        )
    if plan["action"] == "BLOCKED_DESTINATION_EXISTS":
        raise BIPObjectAlreadyExistsError(
            f"BI Publisher destination already exists: {plan['destination_absolute_path']}",
            operation="copy_bip_object",
            report_absolute_path=plan["destination_absolute_path"],
        )
    downloaded = self.download_bip_object(plan["source_report_absolute_path"])
    kind = _object_type(object_type) if object_type is not None else downloaded["object_type"]
    if kind == "unknown":
        raise BIPUnsupportedObjectTypeError(
            "Unable to infer archive type; supply object_type as xdoz, xdmz, or xssz."
        )
    if plan["action"] == "REPLACE":
        result = destination_connection.replace_bip_object(
            plan["destination_absolute_path"],
            kind,
            downloaded["object_zipped_data"],
            verify=verify,
        )
    else:
        upload = None
        upload_error = None
        verification = None
        try:
            upload = destination_connection.upload_bip_object(
                plan["destination_absolute_path"], kind, downloaded["object_zipped_data"]
            )
        except Exception as exc:
            upload_error = exc
        if verify or upload_error is not None or not (upload or {}).get("success"):
            try:
                verification = destination_connection.verify_bip_object(
                    plan["destination_absolute_path"], kind
                )
            except Exception:
                if upload_error is not None:
                    raise upload_error
                raise
        if verification and verification.get("success"):
            result = {
                "success": True,
                "action": "CREATE",
                "upload": upload,
                "upload_warning": _warning(upload_error) if upload_error else (
                    None if (upload or {}).get("success") else {"type": "AmbiguousUploadResult", "message": "Oracle did not positively confirm the upload."}
                ),
                "verification": verification,
            }
        elif upload_error is not None:
            raise upload_error
        else:
            result = {
                "success": bool((upload or {}).get("success")),
                "action": "CREATE",
                "upload": upload,
                "upload_warning": None,
                "verification": verification,
            }
    return {
        "success": bool(result.get("success")),
        "operation": "copy_bip_object",
        "source_report_absolute_path": plan["source_report_absolute_path"],
        "destination_absolute_path": plan["destination_absolute_path"],
        "object_type": kind,
        "object_size_bytes": downloaded["object_size_bytes"],
        "action": plan["action"],
        "overwrite": overwrite,
        "verified": bool(result.get("verification")) if verify else False,
        "result": _safe_metadata(result),
    }



def _schedule_parameter_values(parameters):
    """Normalize report parameter values without encoding their contents."""
    if parameters is None:
        return []
    if not isinstance(parameters, dict):
        raise TypeError("parameters must be a dictionary of parameter names and values.")
    normalized = []
    for raw_name, raw_value in parameters.items():
        name = str(raw_name or "").strip()
        if not name:
            raise ValueError("BI Publisher parameter names cannot be empty.")
        values = raw_value if isinstance(raw_value, (list, tuple)) else [raw_value]
        if not values:
            values = [None]
        normalized.append(
            (
                name,
                ["" if value is None else str(value) for value in values],
            )
        )
    return normalized


def _schedule_envelope(
    report_absolute_path,
    *,
    output_format,
    parameters,
    size_of_data_chunk_download,
    notification_user_name,
    notification_to,
    notify_when_success,
    notify_when_failed,
    notify_when_skipped,
    notify_when_warning,
    save_data,
    save_output,
    schedule_public,
    job_name,
    user_job_desc,
):
    """Build the nested ScheduleReportService SOAP 1.2 request."""
    envelope = ET.Element(f"{{{SOAP_NS}}}Envelope")
    ET.SubElement(envelope, f"{{{SOAP_NS}}}Header")
    body = ET.SubElement(envelope, f"{{{SOAP_NS}}}Body")
    operation = ET.SubElement(body, f"{{{SCHEDULE_REPORT_NS}}}scheduleReport")
    schedule_request = ET.SubElement(
        operation,
        f"{{{SCHEDULE_REPORT_NS}}}scheduleRequest",
    )
    report_request = ET.SubElement(
        schedule_request,
        f"{{{SCHEDULE_REPORT_NS}}}reportRequest",
    )

    attribute_format = ET.SubElement(
        report_request,
        f"{{{SCHEDULE_REPORT_NS}}}attributeFormat",
    )
    attribute_format.text = output_format

    parameter_name_values = ET.SubElement(
        report_request,
        f"{{{SCHEDULE_REPORT_NS}}}parameterNameValues",
    )
    for name, values in parameters:
        parameter_item = ET.SubElement(
            parameter_name_values,
            f"{{{SCHEDULE_REPORT_NS}}}item",
        )
        name_element = ET.SubElement(
            parameter_item,
            f"{{{SCHEDULE_REPORT_NS}}}name",
        )
        name_element.text = name
        values_element = ET.SubElement(
            parameter_item,
            f"{{{SCHEDULE_REPORT_NS}}}values",
        )
        for value in values:
            value_element = ET.SubElement(
                values_element,
                f"{{{SCHEDULE_REPORT_NS}}}item",
            )
            value_element.text = value

    report_path = ET.SubElement(
        report_request,
        f"{{{SCHEDULE_REPORT_NS}}}reportAbsolutePath",
    )
    report_path.text = report_absolute_path

    chunk_size = ET.SubElement(
        report_request,
        f"{{{SCHEDULE_REPORT_NS}}}sizeOfDataChunkDownload",
    )
    chunk_size.text = str(size_of_data_chunk_download)

    optional_text = (
        ("notificationUserName", notification_user_name),
        ("notificationTo", notification_to),
    )
    for name, value in optional_text:
        if value is not None:
            element = ET.SubElement(
                schedule_request,
                f"{{{SCHEDULE_REPORT_NS}}}{name}",
            )
            element.text = value

    boolean_values = (
        ("notifyWhenSuccess", notify_when_success),
        ("notifyWhenFailed", notify_when_failed),
        ("notifyWhenSkipped", notify_when_skipped),
        ("notifyWhenWarning", notify_when_warning),
        ("saveDataOption", save_data),
        ("saveOutputOption", save_output),
        ("schedulePublicOption", schedule_public),
    )
    for name, value in boolean_values:
        element = ET.SubElement(
            schedule_request,
            f"{{{SCHEDULE_REPORT_NS}}}{name}",
        )
        element.text = str(value).lower()

    if user_job_desc is not None:
        description = ET.SubElement(
            schedule_request,
            f"{{{SCHEDULE_REPORT_NS}}}userJobDesc",
        )
        description.text = user_job_desc

    if job_name is not None:
        name_element = ET.SubElement(
            schedule_request,
            f"{{{SCHEDULE_REPORT_NS}}}userJobName",
        )
        name_element.text = job_name

    return ET.tostring(
        envelope,
        encoding="utf-8",
        xml_declaration=True,
    )


def _optional_schedule_text(name, value):
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string or None.")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{name} cannot be empty.")
    return normalized


def _mask_recipient(value):
    if not value:
        return None
    first = value.split(",", 1)[0].strip()
    if "@" not in first:
        return "[MASKED]"
    local, domain = first.split("@", 1)
    prefix = local[:1] if local else "*"
    return f"{prefix}***@{domain}"


def _schedule_id(root):
    preferred = (
        "scheduleReportReturn",
        "scheduleReportResult",
        "scheduleReport",
        "jobID",
        "jobId",
        "return",
    )
    for local_name in preferred:
        for element in root.iter():
            if _local(element.tag) != local_name:
                continue
            text = "".join(element.itertext()).strip()
            if text:
                return int(text) if text.isdigit() else text
    return None


def schedule_bip_report(
    self,
    report_absolute_path,
    *,
    output_format="csv",
    parameters=None,
    size_of_data_chunk_download=-1,
    notification_user_name=None,
    notification_to=None,
    notify_when_success=False,
    notify_when_failed=True,
    notify_when_skipped=False,
    notify_when_warning=True,
    save_data=True,
    save_output=True,
    schedule_public=True,
    job_name=None,
    user_job_desc=None,
):
    """Schedule a BI Publisher report through ScheduleReportWSSService."""
    path = _path(report_absolute_path)
    if not isinstance(output_format, str) or not output_format.strip():
        raise ValueError("output_format must be a non-empty string.")
    output_format = output_format.strip()

    if (
        isinstance(size_of_data_chunk_download, bool)
        or not isinstance(size_of_data_chunk_download, int)
    ):
        raise TypeError("size_of_data_chunk_download must be an integer.")

    flags = {
        "notify_when_success": notify_when_success,
        "notify_when_failed": notify_when_failed,
        "notify_when_skipped": notify_when_skipped,
        "notify_when_warning": notify_when_warning,
        "save_data": save_data,
        "save_output": save_output,
        "schedule_public": schedule_public,
    }
    for name, value in flags.items():
        _validate_bool(name, value)

    normalized_parameters = _schedule_parameter_values(parameters)
    notification_user_name = _optional_schedule_text(
        "notification_user_name",
        notification_user_name,
    )
    notification_to = _optional_schedule_text(
        "notification_to",
        notification_to,
    )
    job_name = _optional_schedule_text("job_name", job_name)
    user_job_desc = _optional_schedule_text("user_job_desc", user_job_desc)

    notification_events = {
        "success": notify_when_success,
        "failed": notify_when_failed,
        "skipped": notify_when_skipped,
        "warning": notify_when_warning,
    }
    notifications_enabled = any(notification_events.values())
    if notifications_enabled and notification_to is None:
        raise ValueError(
            "notification_to is required when any notification event is enabled."
        )

    payload = _schedule_envelope(
        path,
        output_format=output_format,
        parameters=normalized_parameters,
        size_of_data_chunk_download=size_of_data_chunk_download,
        notification_user_name=notification_user_name,
        notification_to=notification_to,
        notify_when_success=notify_when_success,
        notify_when_failed=notify_when_failed,
        notify_when_skipped=notify_when_skipped,
        notify_when_warning=notify_when_warning,
        save_data=save_data,
        save_output=save_output,
        schedule_public=schedule_public,
        job_name=job_name,
        user_job_desc=user_job_desc,
    )

    root = _transport(
        self,
        "scheduleReport",
        [],
        service_path=SCHEDULE_REPORT_SERVICE_PATH,
        namespace=SCHEDULE_REPORT_NS,
        payload=payload,
    )
    schedule_id = _schedule_id(root)
    if schedule_id is None:
        raise BIPScheduleError(
            f"BI Publisher did not return a schedule ID for {path}.",
            operation="schedule_bip_report",
            report_absolute_path=path,
        )

    return {
        "success": True,
        "operation": "schedule_bip_report",
        "soap_operation": "scheduleReport",
        "schedule_id": schedule_id,
        "report_absolute_path": path,
        "output_format": output_format,
        "parameter_names": [name for name, _ in normalized_parameters],
        "save_data": save_data,
        "save_output": save_output,
        "schedule_public": schedule_public,
        "notifications_enabled": notifications_enabled,
        "notification_events": notification_events,
        "notification_recipient_masked": _mask_recipient(notification_to),
        "job_name": job_name,
        "user_job_desc": user_job_desc,
    }

def install_bip_methods(cls):
    cls.get_folder_contents = get_folder_contents
    cls.download_bip_object = download_bip_object
    cls.upload_bip_object = upload_bip_object
    cls.extract_bip_object = extract_bip_object
    cls.get_bip_object_xml = get_bip_object_xml
    cls.bip_object_exists = bip_object_exists
    cls.verify_bip_object = verify_bip_object
    cls.delete_bip_object = delete_bip_object
    cls.replace_bip_object = replace_bip_object
    cls.plan_bip_object_copy = plan_bip_object_copy
    cls.copy_bip_object = copy_bip_object
    cls.schedule_bip_report = schedule_bip_report
