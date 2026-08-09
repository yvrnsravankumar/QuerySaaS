import base64, io, zipfile
import pytest
from querysaas import bip

def archive_b64(name="dataModel.xdm", content=b"x"):
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,"w") as z: z.writestr(name,content)
    return base64.b64encode(stream.getvalue()).decode()

class Fake:
    pass

def test_delete_polls_and_uses_delete_report(monkeypatch):
    c=Fake(); states=iter([True,True,False]); c.bip_object_exists=lambda p: next(states)
    captured={}
    def transport(instance,op,values):
        captured.update(op=op,values=values)
        return bip.SafeET.fromstring("<r><deleteReportReturn>true</deleteReportReturn></r>")
    monkeypatch.setattr(bip,"_transport",transport); monkeypatch.setattr(bip.time,"sleep",lambda n:None)
    result=bip.delete_bip_object(c,"/Custom/Test/X.xdm",verify=True,timeout=1,poll_interval=.1)
    assert captured=={"op":"deleteReport","values":[("reportAbsolutePath","/Custom/Test/X.xdm")]}
    assert result["verified"] is True and result["soap_operation"]=="deleteReport"

@pytest.mark.parametrize("path",["/","/Custom","/Shared Folders","/~user"])
def test_delete_protected_roots(path):
    with pytest.raises(bip.BIPDeleteError): bip.delete_bip_object(Fake(),path)

def test_delete_raises_when_target_remains(monkeypatch):
    c=Fake(); c.bip_object_exists=lambda p:True
    monkeypatch.setattr(bip,"_transport",lambda *a,**k:bip.SafeET.fromstring("<r><return>true</return></r>"))
    monkeypatch.setattr(bip.time,"sleep",lambda n:None); ticks=iter([0,2])
    monkeypatch.setattr(bip.time,"monotonic",lambda:next(ticks))
    with pytest.raises(bip.BIPDeleteError): bip.delete_bip_object(c,"/Custom/Test/X.xdm",timeout=1,poll_interval=.1)

def test_plan_performs_no_download_or_write():
    source=Fake(); target=Fake(); calls=[]
    source.bip_object_exists=lambda p:True; target.bip_object_exists=lambda p:False
    source.download_bip_object=lambda p: calls.append("download")
    target.upload_bip_object=lambda *a: calls.append("upload")
    plan=bip.plan_bip_object_copy(source,target,"/Custom/S.xdm","/Custom/T.xdm",overwrite=True)
    assert plan["action"]=="CREATE" and calls==[]

def test_create_ambiguous_response_but_readable_target_succeeds():
    source=Fake(); target=Fake(); data=archive_b64()
    source.bip_object_exists=lambda p:True; target.bip_object_exists=lambda p:False
    source.download_bip_object=lambda p:{"success":True,"report_absolute_path":p,"object_type":"xdmz","object_size_bytes":10,"object_zipped_data":data}
    target.upload_bip_object=lambda *a:{"success":False,"ambiguous":True}
    target.verify_bip_object=lambda *a:{"success":True,"object_type":"xdmz"}
    result=bip.copy_bip_object(source,target,"/Custom/S.xdm","/Custom/T.xdm",overwrite=True)
    assert result["success"] is True and result["action"]=="CREATE"
    assert result["result"]["upload_warning"]["type"]=="AmbiguousUploadResult"
    assert "object_zipped_data" not in str(result)

def test_replace_upload_exception_readable_target_does_not_restore(monkeypatch):
    c=Fake(); data=archive_b64(); exists=iter([True,True])
    c.bip_object_exists=lambda p:next(exists)
    c.download_bip_object=lambda p:{"object_type":"xdmz","object_size_bytes":5,"object_zipped_data":data}
    c.delete_bip_object=lambda *a,**k:{"success":True}
    c.upload_bip_object=lambda *a:(_ for _ in ()).throw(bip.BIPUploadError("ambiguous"))
    c.verify_bip_object=lambda *a:{"success":True,"object_type":"xdmz"}
    result=bip.replace_bip_object(c,"/Custom/T.xdm","xdmz",data,timeout=1,poll_interval=.1)
    assert result["success"] is True and result["restored"] is False
    assert result["upload_warning"]["type"]=="BIPUploadError"

def test_restored_true_only_after_verification(monkeypatch):
    # State sequence: original exists; replacement appears after polling; partial target exists; restored backup appears.
    c=Fake(); data=archive_b64(); states=iter([True,False,False,True,True,True])
    c.bip_object_exists=lambda p:next(states)
    c.download_bip_object=lambda p:{"object_type":"xdmz","object_size_bytes":5,"object_zipped_data":data}
    c.delete_bip_object=lambda *a,**k:{"success":True}
    uploads=[]
    def upload(*a):
        uploads.append(1)
        if len(uploads)==1: raise bip.BIPUploadError("failed")
        return {"success":True}
    c.upload_bip_object=upload
    checks=iter([bip.BIPVerificationError("bad"),{"success":True,"object_type":"xdmz"}])
    def verify(*a):
        value=next(checks)
        if isinstance(value,Exception): raise value
        return value
    c.verify_bip_object=verify
    with pytest.raises(bip.BIPReplaceError) as info:
        bip.replace_bip_object(c,"/Custom/T.xdm","xdmz",data,timeout=1,poll_interval=.1)
    assert info.value.restore_attempted is True
    assert info.value.restored is True
    assert info.value.restoration_verification["success"] is True

def test_no_temporary_alias_or_marker():
    source=open(bip.__file__,encoding="utf-8").read()
    assert "copy_bip_object_v020" not in source
    assert "QUERYSAAS-BIP-0.2" not in source