import pytest
from querysaas import bip

def test_preview_redacts_before_truncation():
    text="Authorization: Bearer topsecret " + "x"*1000
    value=bip._preview(text,40)
    assert "topsecret" not in value
    assert "[REDACTED]" in value

def test_safe_metadata_redacts_sensitive_keys():
    value=bip._safe_metadata({"object_zipped_data":"abc","P_B64_CONTENT":"def","nested":{"token":"ghi"},"path":"/Custom/X"})
    assert value["object_zipped_data"]=="[REDACTED]"
    assert value["P_B64_CONTENT"]=="[REDACTED]"
    assert value["nested"]["token"]=="[REDACTED]"
    assert value["path"]=="/Custom/X"

def test_missing_classifier_tokens():
    error=bip.BIPSOAPFaultError("Unable to download Report Due to unable to find ReportObject")
    assert bip._is_missing_bip_error(error) is True

def test_exists_only_hides_missing(monkeypatch):
    class C: pass
    c=C()
    def missing(path): raise bip.BIPHTTPError("report object not found")
    c.download_bip_object=missing
    assert bip.bip_object_exists(c,"/Custom/X.xdm") is False
    def unrelated(path): raise bip.BIPHTTPError("database unavailable")
    c.download_bip_object=unrelated
    with pytest.raises(bip.BIPHTTPError): bip.bip_object_exists(c,"/Custom/X.xdm")