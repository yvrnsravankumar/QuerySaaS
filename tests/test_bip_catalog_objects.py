import base64, io, zipfile
from pathlib import Path
from types import SimpleNamespace
import pytest
import querysaas.bip as bip
from querysaas.bip import *

def archive():
    b=io.BytesIO()
    with zipfile.ZipFile(b,"w") as z: z.writestr("_report.xdo","<report/>")
    return b.getvalue()
def response(xml,status=200): return SimpleNamespace(status_code=status,ok=status<400,content=xml.encode(),text=xml)
def client(monkeypatch,xml):
    c=SimpleNamespace(url="https://example.invalid",auth_header="Basic REDACTED",timeout=10,verify_ssl=True)
    c._session=SimpleNamespace(post=lambda *a,**k: response(xml))
    for name in ("get_folder_contents","download_bip_object","upload_bip_object","extract_bip_object","get_bip_object_xml","copy_bip_object"):
        setattr(c,name,getattr(__import__('querysaas.bip',fromlist=[name]),name).__get__(c))
    return c
def envelope(body): return f'<e:Envelope xmlns:e="{SOAP_NS}" xmlns:x="{PUB_NS}"><e:Body>{body}</e:Body></e:Envelope>'
def test_download_prefix_independent(tmp_path):
    data=archive(); b64=base64.b64encode(data).decode(); c=client(None,envelope(f'<x:downloadReportObjectResponse><x:downloadReportObjectReturn>{b64}</x:downloadReportObjectReturn></x:downloadReportObjectResponse>'))
    r=c.download_bip_object('/Custom/Test.XDO',tmp_path/'test'); assert r['object_type']=='xdoz' and Path(r['output_file']).read_bytes()==data
def test_upload_bytes():
    c=client(None,envelope('<x:uploadReportObjectResponse><x:uploadReportObjectReturn>true</x:uploadReportObjectReturn></x:uploadReportObjectResponse>'))
    assert c.upload_bip_object('/Custom/Target','.XDOZ',archive())['success']
def test_folder_sort_filter():
    xml=envelope('<x:getFolderContentsResponse><x:getFolderContentsReturn><x:absolutePath>/Custom/R</x:absolutePath><x:displayName>zReport</x:displayName><x:type>Report</x:type></x:getFolderContentsReturn><x:getFolderContentsReturn><x:absolutePath>/Custom/F</x:absolutePath><x:displayName>aFolder</x:displayName><x:type>Folder</x:type></x:getFolderContentsReturn></x:getFolderContentsResponse>')
    r=client(None,xml).get_folder_contents('/Custom/'); assert [x['type'] for x in r['items']]==['Folder','Report']
def test_invalid_type_before_http():
    with pytest.raises(BIPUnsupportedObjectTypeError): bip._object_type('xdo')
def test_extract_and_xml():
    c=client(None,envelope('')); r=c.extract_bip_object(archive()); assert r['member_count']==1
def test_copy_reuses_methods():
    data=base64.b64encode(archive()).decode(); source=SimpleNamespace(download_bip_object=lambda p:{'success':True,'operation':'downloadReportObject','report_absolute_path':p,'object_type':'xdoz','object_size_bytes':len(archive()),'object_zipped_data':data})
    target=SimpleNamespace(bip_object_exists=lambda p:False, upload_bip_object=lambda p,t,d:{'success':True,'operation':'uploadReportObject','object_type':t,'object_size_bytes':len(archive())}, verify_bip_object=lambda p,t:{'success':True,'object_type':t})
    source.bip_object_exists=lambda p:True; r=copy_bip_object(source,target,'/Custom/A.xdo','/Custom/B',verify=True); assert r['success'] and 'object_zipped_data' not in str(r)
