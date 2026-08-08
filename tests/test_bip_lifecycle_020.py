import io
import zipfile

from querysaas import FusionConnection
from querysaas import bip as bip


def archive_bytes():
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("_report.xdo", "<report/>")
    return stream.getvalue()


def test_installer_registers_020_methods():
    class FakeConnection:
        pass
    bip.install_bip_methods(FakeConnection)
    for name in (
        "bip_object_exists", "verify_bip_object", "delete_bip_object",
        "replace_bip_object", "plan_bip_object_copy", "copy_bip_object",
        "schedule_bip_report",
    ):
        assert callable(getattr(FakeConnection, name))


def test_plan_create_without_transfer():
    class Destination:
        def bip_object_exists(self, path):
            return False
    source = object.__new__(FusionConnection)
    source.bip_object_exists = lambda path: True
    plan = bip.plan_bip_object_copy(
        source, Destination(), "/Custom/A.xdo", "/Custom/B.xdo"
    )
    assert plan["action"] == "CREATE"
    assert plan["success"] is True


def test_verify_archive(monkeypatch):
    connection = object.__new__(FusionConnection)
    payload = archive_bytes()
    monkeypatch.setattr(
        connection,
        "download_bip_object",
        lambda path: {
            "success": True,
            "object_type": "xdoz",
            "object_size_bytes": len(payload),
            "object_zipped_data": payload,
        },
    )
    result = bip.verify_bip_object(connection, "/Custom/A.xdo", "xdoz")
    assert result["member_count"] == 1
    assert result["object_type"] == "xdoz"


def test_delete_missing_ok(monkeypatch):
    connection = object.__new__(FusionConnection)
    monkeypatch.setattr(connection, "bip_object_exists", lambda path: False)
    result = bip.delete_bip_object(connection, "/Custom/Missing.xdo", missing_ok=True)
    assert result["missing"] is True
    assert result["deleted"] is False