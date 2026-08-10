import inspect
import io
import zipfile
from types import SimpleNamespace
import pytest
import querysaas.bip as bip
from querysaas.exceptions import (
    BIPDeleteError, BIPHTTPError, BIPObjectAlreadyExistsError, BIPReplaceError,
    BIPSOAPFaultError, BIPScheduleError, BIPUploadError, BIPVerificationError,
)


def archive_bytes():
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as z:
        z.writestr("test.xdm", "<x/>")
    return stream.getvalue()


def test_exception_identity():
    assert bip.BIPObjectAlreadyExistsError is BIPObjectAlreadyExistsError
    assert bip.BIPVerificationError is BIPVerificationError
    assert bip.BIPDeleteError is BIPDeleteError
    assert bip.BIPReplaceError is BIPReplaceError
    assert bip.BIPScheduleError is BIPScheduleError


def test_metadata_exception_and_safe_dict():
    error = BIPHTTPError("test", operation="downloadReportObject", report_absolute_path="/Custom/Test.xdm", status_code=500, metadata={"attempt": 1, "token": "secret", "password": "secret", "object_zipped_data": "large-base64"})
    assert str(error) == "test"
    assert error.operation == "downloadReportObject"
    assert error.status_code == 500
    assert error.metadata["attempt"] == 1
    result = error.to_dict()
    assert result["type"] == "BIPHTTPError"
    assert result["metadata"]["attempt"] == 1
    assert "secret" not in repr(result)
    assert "large-base64" not in repr(result)


def test_soap_and_replace_metadata_and_cause():
    fault = BIPSOAPFaultError("SOAP fault", operation="downloadReportObject", status_code=500, soap_fault_code="env:Receiver", soap_fault_reason="Unable to find ReportObject")
    assert fault.soap_fault_code == "env:Receiver"
    root = BIPUploadError("upload failed", operation="uploadReportObject")
    replacement = BIPReplaceError("replacement failed", operation="replace_bip_object", report_absolute_path="/Custom/Test.xdm", object_type="xdmz", deleted=True, restore_attempted=True, restored=True, replacement_error=root, restoration_verification={"success": True, "object_type": "xdmz"})
    assert replacement.replacement_error is root
    assert replacement.to_dict()["restored"] is True
    try:
        raise replacement from root
    except BIPReplaceError as caught:
        assert caught.__cause__ is root


def test_only_readable_verification_mode(monkeypatch):
    connection = SimpleNamespace(download_bip_object=lambda path: {"object_type": "xdmz", "object_zipped_data": archive_bytes()})
    result = bip.verify_bip_object(connection, "/Custom/Test.xdm")
    assert result["verification_mode"] == "readable"
    with pytest.raises(ValueError, match="only verification_mode='readable'"):
        bip.verify_bip_object(connection, "/Custom/Test.xdm", verification_mode="raw_archive")


def source_connection():
    return SimpleNamespace(
        bip_object_exists=lambda path: True,
        download_bip_object=lambda path: {"object_type": "xdmz", "object_zipped_data": archive_bytes(), "object_size_bytes": len(archive_bytes()), "report_absolute_path": path},
    )


def test_create_false_existence_probe_but_readable_target_succeeds():
    destination = SimpleNamespace()
    destination.bip_object_exists = lambda path: False
    calls = []
    destination.upload_bip_object = lambda *args: calls.append(args) or {"success": False, "ambiguous": True}
    destination.verify_bip_object = lambda path, kind: {"success": True, "object_type": kind}
    result = bip.copy_bip_object(source_connection(), destination, "/Custom/S.xdm", "/Custom/T.xdm", timeout=1, poll_interval=.01)
    assert result["success"] is True
    assert len(calls) == 1
    assert result["result"]["upload_warning"]["type"] == "AmbiguousUploadResult"


def test_create_polls_once_upload_and_delayed_availability(monkeypatch):
    states = iter([False, False, True])
    destination = SimpleNamespace()
    destination.bip_object_exists = lambda path: next(states)
    calls = []
    destination.upload_bip_object = lambda *args: calls.append(args) or {"success": False, "ambiguous": True}
    destination.verify_bip_object = lambda path, kind: {"success": True}
    monkeypatch.setattr(bip.time, "sleep", lambda value: None)
    result = bip.copy_bip_object(source_connection(), destination, "/Custom/S.xdm", "/Custom/T.xdm", timeout=1, poll_interval=.01)
    assert result["success"] is True
    assert len(calls) == 1
    assert result["result"]["upload_warning"]["type"] == "AmbiguousUploadResult"


def test_create_upload_exception_readable_target(monkeypatch):
    state = {"checks": 0}
    destination = SimpleNamespace()
    def exists(path):
        state["checks"] += 1
        return state["checks"] != 1
    destination.bip_object_exists = exists
    upload_error = BIPUploadError("transport ended after commit")
    destination.upload_bip_object = lambda *args: (_ for _ in ()).throw(upload_error)
    destination.verify_bip_object = lambda path, kind: {"success": True}
    result = bip.copy_bip_object(source_connection(), destination, "/Custom/S.xdm", "/Custom/T.xdm", timeout=1, poll_interval=.01)
    assert result["success"] is True
    assert result["result"]["upload_warning"]["type"] == "BIPUploadError"


def test_create_missing_reraises_original(monkeypatch):
    destination = SimpleNamespace(bip_object_exists=lambda path: False)
    upload_error = BIPUploadError("upload failed")
    destination.upload_bip_object = lambda *args: (_ for _ in ()).throw(upload_error)
    monkeypatch.setattr(bip.time, "sleep", lambda value: None)
    monkeypatch.setattr(bip.time, "monotonic", iter([0, 2]).__next__)
    with pytest.raises(BIPUploadError) as caught:
        bip.copy_bip_object(source_connection(), destination, "/Custom/S.xdm", "/Custom/T.xdm", timeout=1, poll_interval=.01)
    assert caught.value is upload_error


def test_copy_signature_and_replace_polling_forwarded():
    signature = inspect.signature(bip.copy_bip_object)
    assert signature.parameters["timeout"].default == 10
    assert signature.parameters["poll_interval"].default == .5


def test_schedule_defaults_are_opt_in():
    sig = inspect.signature(bip.schedule_bip_report)
    assert sig.parameters["notify_when_success"].default is False
    assert sig.parameters["notify_when_failed"].default is False
    assert sig.parameters["notify_when_skipped"].default is False
    assert sig.parameters["notify_when_warning"].default is False


def test_notification_requires_recipient_and_username(monkeypatch):
    connection = SimpleNamespace()
    with pytest.raises(ValueError, match="notification_to"):
        bip.schedule_bip_report(connection, "/Custom/Test.xdo", notify_when_failed=True)
    with pytest.raises(ValueError, match="notification_user_name"):
        bip.schedule_bip_report(connection, "/Custom/Test.xdo", notify_when_failed=True, notification_to="a@example.com")
