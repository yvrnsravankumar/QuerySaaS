import xml.etree.ElementTree as ET

import pytest

from querysaas import FusionConnection
from querysaas import bip


def connection():
    return object.__new__(FusionConnection)


def response(name="deleteReportReturn", value="true"):
    return ET.fromstring(
        f"""
        <soap:Envelope
          xmlns:soap="http://www.w3.org/2003/05/soap-envelope"
          xmlns:pub="http://xmlns.oracle.com/oxp/service/PublicReportService">
          <soap:Body>
            <pub:deleteReportResponse>
              <pub:{name}>{value}</pub:{name}>
            </pub:deleteReportResponse>
          </soap:Body>
        </soap:Envelope>
        """
    )


def test_delete_uses_delete_report(monkeypatch):
    item = connection()
    captured = {}
    monkeypatch.setattr(item, "bip_object_exists", lambda path: True)

    def transport(instance, operation, values):
        captured.update(operation=operation, values=values)
        return response()

    monkeypatch.setattr(bip, "_transport", transport)
    result = bip.delete_bip_object(item, "/Custom/Finance/Report.xdo")

    assert captured == {
        "operation": "deleteReport",
        "values": [("reportAbsolutePath", "/Custom/Finance/Report.xdo")],
    }
    assert result["operation"] == "deleteReport"
    assert result["oracle_result"] == "true"


def test_delete_false_is_rejected(monkeypatch):
    item = connection()
    monkeypatch.setattr(item, "bip_object_exists", lambda path: True)
    monkeypatch.setattr(
        bip,
        "_transport",
        lambda instance, operation, values: response("deleteReportReturn", "false"),
    )
    with pytest.raises(bip.BIPDeleteError):
        bip.delete_bip_object(item, "/Custom/Finance/Report.xdo")


def test_delete_legacy_response_is_accepted(monkeypatch):
    item = connection()
    monkeypatch.setattr(item, "bip_object_exists", lambda path: True)
    monkeypatch.setattr(
        bip,
        "_transport",
        lambda instance, operation, values: response(
            "deleteReportObjectReturn", "true"
        ),
    )
    assert bip.delete_bip_object(
        item, "/Custom/Finance/Report.xdo"
    )["deleted"] is True


def test_delete_missing_ok(monkeypatch):
    item = connection()
    monkeypatch.setattr(item, "bip_object_exists", lambda path: False)
    result = bip.delete_bip_object(
        item, "/Custom/Finance/Missing.xdo", missing_ok=True
    )
    assert result["operation"] == "deleteReport"
    assert result["deleted"] is False
    assert result["missing"] is True