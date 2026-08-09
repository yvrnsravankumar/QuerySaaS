import base64, io, zipfile
from querysaas import bip

class Fake: pass

def zipped():
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,"w") as z:z.writestr("dataModel.xdm",b"x")
    return stream.getvalue()

def test_upload_encodes_bytes_exactly_once(monkeypatch):
    captured={}
    def transport(instance,op,values):
        captured.update(op=op,values=dict(values))
        return bip.SafeET.fromstring("<r><uploadReportObjectReturn>true</uploadReportObjectReturn></r>")
    monkeypatch.setattr(bip,"_transport",transport)
    result=bip.upload_bip_object(Fake(),"/Custom/X.xdm","xdmz",zipped())
    assert base64.b64decode(captured["values"]["objectZippedData"])==zipped()
    assert result["success"] is True and "object_zipped_data" not in result

def test_upload_missing_result_is_ambiguous(monkeypatch):
    monkeypatch.setattr(bip,"_transport",lambda *a,**k:bip.SafeET.fromstring("<r/>"))
    result=bip.upload_bip_object(Fake(),"/Custom/X.xdm","xdmz",zipped())
    assert result["success"] is False and result["ambiguous"] is True

def test_verification_readable_does_not_compare_raw_hash():
    c=Fake(); data=base64.b64encode(zipped()).decode()
    c.download_bip_object=lambda p:{"object_type":"xdmz","object_zipped_data":data}
    result=bip.verify_bip_object(c,"/Custom/X.xdm")
    assert result["verification_mode"]=="readable"
    assert result["member_count"]==1