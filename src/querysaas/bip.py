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
from .exceptions import BIPublisherError

SOAP_NS="http://www.w3.org/2003/05/soap-envelope"
PUB_NS="http://xmlns.oracle.com/oxp/service/PublicReportService"
SERVICE_PATH="/xmlpserver/services/ExternalReportWSSService"
TYPES={"xdoz","xdmz","xssz"}
TYPE_MAP={".xdo":"xdoz",".xdm":"xdmz",".xss":"xssz"}
XML_EXTENSIONS={".xdo",".xdm",".xpt",".xss",".cfg",".meta",".sec",".xml"}
ET.register_namespace("soap",SOAP_NS); ET.register_namespace("pub",PUB_NS)

class BIPAuthenticationError(BIPublisherError): pass
class BIPAuthorizationError(BIPublisherError): pass
class BIPConnectionError(BIPublisherError): pass
class BIPTimeoutError(BIPublisherError): pass
class BIPHTTPError(BIPublisherError): pass
class BIPSOAPFaultError(BIPublisherError): pass
class BIPInvalidResponseError(BIPublisherError): pass
class BIPCatalogError(BIPublisherError): pass
class BIPObjectNotFoundError(BIPublisherError): pass
class BIPInvalidBase64Error(BIPublisherError): pass
class BIPUnsupportedObjectTypeError(BIPublisherError): pass
class BIPUploadError(BIPublisherError): pass
class BIPReportExecutionError(BIPublisherError): pass

def _local(tag): return tag.rsplit("}",1)[-1]
def _path(value, *, allow_empty=False, trailing=False):
    if value is None: value=""
    value=str(value).strip()
    if not value and allow_empty: return ""
    if not value: raise ValueError("BI Publisher catalog path cannot be empty.")
    if not value.startswith("/"): value="/"+value
    if not trailing and value!="/": value=value.rstrip("/")
    return value

def _object_type(value):
    value=str(value or "").strip().lower().lstrip(".")
    if value not in TYPES:
        raise BIPUnsupportedObjectTypeError("Unsupported BI Publisher object type. Supported values: xdoz, xdmz, xssz.")
    return value

def _archive_type(report_path): return TYPE_MAP.get(Path(report_path).suffix.lower(),"unknown")
def _envelope(operation, values):
    env=ET.Element(f"{{{SOAP_NS}}}Envelope"); ET.SubElement(env,f"{{{SOAP_NS}}}Header"); body=ET.SubElement(env,f"{{{SOAP_NS}}}Body")
    op=ET.SubElement(body,f"{{{PUB_NS}}}{operation}")
    for name,value in values:
        element=ET.SubElement(op,f"{{{PUB_NS}}}{name}"); element.text=str(value)
    return ET.tostring(env,encoding="utf-8",xml_declaration=True)
def _preview(text, limit=800):
    text=re.sub(r"(?is)(<[^>]*(?:objectZippedData|downloadReportObjectReturn|reportBytes)[^>]*>).*?(</[^>]+>)",r"\1[REDACTED]\2",text or "")
    return text[:limit]
def _fault(root):
    for e in root.iter():
        if _local(e.tag)=="Fault":
            code=reason=None
            for item in e.iter():
                if _local(item.tag) in {"Value","faultcode"} and code is None: code=(item.text or "").strip()
                if _local(item.tag) in {"Text","faultstring"} and reason is None: reason=(item.text or "").strip()
            ora=re.search(r"(ORA-\d{5}):\s*([^\r\n<]+)",reason or "")
            err=BIPSOAPFaultError(f"BI Publisher SOAP fault: {reason or 'Unknown fault'}")
            err.soap_fault_code=code; err.soap_fault_reason=reason; err.oracle_error_code=ora.group(1) if ora else None; err.oracle_message=ora.group(2).strip() if ora else None
            raise err

def _transport(self, operation, values):
    url=self.url.rstrip("/")+SERVICE_PATH; payload=_envelope(operation,values)
    headers={"Authorization":self.auth_header,"Content-Type":"application/soap+xml; charset=UTF-8","Accept":"application/soap+xml, text/xml"}
    sender=getattr(getattr(self,"session",None),"post",None) or getattr(getattr(self,"_session",None),"post",None) or requests.post
    try: response=sender(url,headers=headers,data=payload,timeout=self.timeout,verify=self.verify_ssl)
    except requests.Timeout as exc: raise BIPTimeoutError(f"BI Publisher {operation} timed out after {self.timeout} seconds.") from exc
    except requests.ConnectionError as exc: raise BIPConnectionError(f"BI Publisher {operation} connection failed.") from exc
    if response.status_code==401: raise BIPAuthenticationError(f"BI Publisher {operation} authentication failed (HTTP 401).")
    if response.status_code==403: raise BIPAuthorizationError(f"BI Publisher {operation} authorization failed (HTTP 403).")
    if not response.ok: raise BIPHTTPError(f"BI Publisher {operation} failed (HTTP {response.status_code}): {_preview(response.text)}")
    try: root=SafeET.fromstring(response.content)
    except Exception as exc: raise BIPInvalidResponseError(f"BI Publisher {operation} returned invalid XML: {_preview(response.text)}") from exc
    _fault(root); return root

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
    path=_path(report_absolute_path); root=_transport(self,"downloadReportObject",[("reportAbsolutePath",path)])
    element=_find(root,["downloadReportObjectReturn","objectZippedData","reportObjectData","reportObject"])
    if element is None or not "".join(element.itertext()).strip(): raise BIPObjectNotFoundError(f"BI Publisher returned no object payload for {path}.")
    normalized="".join("".join(element.itertext()).split())
    data=_decode(normalized); kind=_archive_type(path); saved=None
    if output_file is not None:
        target=Path(output_file).expanduser()
        if not target.suffix and kind!="unknown": target=target.with_suffix("."+kind)
        target=target.resolve(); target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists() and not overwrite: raise FileExistsError(f"Destination already exists: {target}")
        target.write_bytes(data); saved=str(target)
    return {"success":True,"operation":"downloadReportObject","report_absolute_path":path,"object_type":kind,"object_size_bytes":len(data),"object_zipped_data":normalized,"output_file":saved}

def upload_bip_object(self, report_object_absolute_path_url, object_type, object_zipped_data):
    destination=_path(report_object_absolute_path_url); kind=_object_type(object_type)
    data=_decode(object_zipped_data); encoded=base64.b64encode(data).decode("ascii")
    root=_transport(self,"uploadReportObject",[("reportObjectAbsolutePathURL",destination),("objectType",kind),("objectZippedData",encoded)])
    element=_find(root,["uploadReportObjectReturn","uploadReportObjectResult","return"])
    raw=(element.text or "").strip() if element is not None else None
    success=True if raw is None else raw.casefold() in {"true","success","successful","1"}
    return {"success":success,"operation":"uploadReportObject","report_object_absolute_path_url":destination,"object_type":kind,"object_size_bytes":len(data),"oracle_result":raw}

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

def copy_bip_object(self, destination_connection, source_report_absolute_path, destination_absolute_path, object_type=None):
    if destination_connection is None or not callable(getattr(destination_connection,"upload_bip_object",None)): raise TypeError("destination_connection must be an open QuerySaaS Fusion connection.")
    downloaded=self.download_bip_object(source_report_absolute_path)
    kind=_object_type(object_type) if object_type is not None else downloaded["object_type"]
    if kind=="unknown": raise BIPUnsupportedObjectTypeError("Unable to infer archive type; supply object_type as xdoz, xdmz, or xssz.")
    uploaded=destination_connection.upload_bip_object(destination_absolute_path,kind,downloaded["object_zipped_data"])
    safe_download={k:v for k,v in downloaded.items() if k!="object_zipped_data"}
    return {"success":bool(uploaded["success"]),"operation":"copy_bip_object","source_report_absolute_path":downloaded["report_absolute_path"],"destination_absolute_path":_path(destination_absolute_path),"object_type":kind,"object_size_bytes":downloaded["object_size_bytes"],"download":safe_download,"upload":uploaded}

def install_bip_methods(cls):
    cls.get_folder_contents=get_folder_contents; cls.download_bip_object=download_bip_object; cls.upload_bip_object=upload_bip_object
    cls.extract_bip_object=extract_bip_object; cls.get_bip_object_xml=get_bip_object_xml; cls.copy_bip_object=copy_bip_object
