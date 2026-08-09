import xml.etree.ElementTree as ET

import pytest

from querysaas import bip


class Fake:
    pass


def local(element):
    return element.tag.rsplit("}", 1)[-1]


def children(element, name):
    return [item for item in element.iter() if local(item) == name]


def response(value="2823", prefix="ns2"):
    return ET.fromstring(
        f"""
        <soap:Envelope xmlns:soap="{bip.SOAP_NS}"
          xmlns:{prefix}="{bip.SCHEDULE_REPORT_NS}">
          <soap:Body>
            <{prefix}:scheduleReport>{value}</{prefix}:scheduleReport>
          </soap:Body>
        </soap:Envelope>
        """
    )


def schedule(monkeypatch, **overrides):
    captured = {}

    def transport(instance, operation, values, **kwargs):
        captured.update(
            operation=operation,
            values=values,
            kwargs=kwargs,
        )
        return response()

    monkeypatch.setattr(bip, "_transport", transport)
    arguments = {
        "report_absolute_path": "/~user.name@example.com/DataViewerTool/v1/csv.xdo",
        "output_format": "csv",
        "parameters": {"P_LEDGER_ID": "300000001"},
        "notification_user_name": "user.name@example.com",
        "notification_to": "user.name@example.com",
        "notify_when_success": True,
        "notify_when_failed": True,
        "notify_when_skipped": True,
        "notify_when_warning": True,
        "save_data": True,
        "save_output": True,
        "schedule_public": True,
        "job_name": "PostmanTest",
        "user_job_desc": "Post Name",
    }
    arguments.update(overrides)
    result = bip.schedule_bip_report(Fake(), **arguments)
    return result, captured


def test_uses_schedule_service_namespace_and_soap12(monkeypatch):
    result, captured = schedule(monkeypatch)
    assert captured["operation"] == "scheduleReport"
    assert captured["values"] == []
    assert captured["kwargs"]["service_path"].endswith(
        "/ScheduleReportWSSService"
    )
    assert captured["kwargs"]["namespace"] == bip.SCHEDULE_REPORT_NS
    root = ET.fromstring(captured["kwargs"]["payload"])
    assert root.tag == f"{{{bip.SOAP_NS}}}Envelope"
    assert children(root, "scheduleRequest")
    assert children(root, "reportRequest")
    assert result["schedule_id"] == 2823


def test_nested_report_fields_and_options(monkeypatch):
    result, captured = schedule(
        monkeypatch,
        size_of_data_chunk_download=-1,
    )
    root = ET.fromstring(captured["kwargs"]["payload"])
    expected = {
        "attributeFormat": "csv",
        "reportAbsolutePath": "/~user.name@example.com/DataViewerTool/v1/csv.xdo",
        "sizeOfDataChunkDownload": "-1",
        "notificationUserName": "user.name@example.com",
        "notificationTo": "user.name@example.com",
        "notifyWhenSuccess": "true",
        "notifyWhenFailed": "true",
        "notifyWhenSkipped": "true",
        "notifyWhenWarning": "true",
        "saveDataOption": "true",
        "saveOutputOption": "true",
        "schedulePublicOption": "true",
        "userJobName": "PostmanTest",
        "userJobDesc": "Post Name",
    }
    for name, value in expected.items():
        matches = children(root, name)
        assert len(matches) == 1
        assert matches[0].text == value
    assert result["notification_recipient_masked"] == "u***@example.com"
    # The catalog path may legitimately contain a user email in a My Folders path.
    # Verify that no unmasked notification recipient field is returned instead.
    assert "notification_to" not in result
    assert "notification_user_name" not in result


def test_scalar_and_multiple_parameters(monkeypatch):
    result, captured = schedule(
        monkeypatch,
        parameters={
            "P_LEDGER_ID": ["300000001", "300000002"],
            "P_STATUS": "OPEN",
        },
    )
    root = ET.fromstring(captured["kwargs"]["payload"])
    parameter_container = children(root, "parameterNameValues")[0]
    parameter_items = [
        item
        for item in list(parameter_container)
        if local(item) == "item"
    ]
    assert len(parameter_items) == 2
    values = {}
    for item in parameter_items:
        name = children(item, "name")[0].text
        values[name] = [element.text for element in children(item, "values")[0]]
    assert values["P_LEDGER_ID"] == ["300000001", "300000002"]
    assert values["P_STATUS"] == ["OPEN"]
    assert result["parameter_names"] == ["P_LEDGER_ID", "P_STATUS"]
    assert "300000001" not in str(result)


def test_p_b64_content_passed_through_once_and_not_returned(monkeypatch):
    original = "H4sIA_NOT_REENCODED_VALUE"
    result, captured = schedule(
        monkeypatch,
        parameters={"P_B64_CONTENT": original},
    )
    root = ET.fromstring(captured["kwargs"]["payload"])
    parameter_container = children(root, "parameterNameValues")[0]
    item = [node for node in list(parameter_container) if local(node) == "item"][0]
    assert children(item, "name")[0].text == "P_B64_CONTENT"
    assert list(children(item, "values")[0])[0].text == original
    assert original not in str(result)
    assert result["parameter_names"] == ["P_B64_CONTENT"]


def test_namespace_prefix_independent_and_non_numeric_id(monkeypatch):
    monkeypatch.setattr(
        bip,
        "_transport",
        lambda *args, **kwargs: response("JOB-ABC", prefix="random"),
    )
    result = bip.schedule_bip_report(
        Fake(),
        "/Custom/Test/Report.xdo",
        notify_when_failed=False,
        notify_when_warning=False,
    )
    assert result["schedule_id"] == "JOB-ABC"


def test_missing_schedule_id(monkeypatch):
    monkeypatch.setattr(
        bip,
        "_transport",
        lambda *args, **kwargs: ET.fromstring("<root/>")
    )
    with pytest.raises(bip.BIPScheduleError):
        bip.schedule_bip_report(
            Fake(),
            "/Custom/Test/Report.xdo",
            notify_when_failed=False,
            notify_when_warning=False,
        )


@pytest.mark.parametrize(
    "field",
    [
        "notify_when_success",
        "notify_when_failed",
        "notify_when_skipped",
        "notify_when_warning",
        "save_data",
        "save_output",
        "schedule_public",
    ],
)
def test_boolean_validation(monkeypatch, field):
    arguments = {
        "notify_when_failed": False,
        "notify_when_warning": False,
        field: "true",
    }
    with pytest.raises(ValueError):
        bip.schedule_bip_report(
            Fake(),
            "/Custom/Test/Report.xdo",
            **arguments,
        )


def test_notification_recipient_required():
    with pytest.raises(ValueError, match="notification_to"):
        bip.schedule_bip_report(
            Fake(),
            "/Custom/Test/Report.xdo",
            notify_when_success=True,
            notification_to=None,
        )


def test_empty_recipients_rejected():
    with pytest.raises(ValueError):
        bip.schedule_bip_report(
            Fake(),
            "/Custom/Test/Report.xdo",
            notification_to="   ",
        )


def test_parameter_validation():
    with pytest.raises(TypeError):
        bip.schedule_bip_report(
            Fake(),
            "/Custom/Test/Report.xdo",
            parameters=[("P_ID", "1")],
            notify_when_failed=False,
            notify_when_warning=False,
        )
    with pytest.raises(ValueError):
        bip.schedule_bip_report(
            Fake(),
            "/Custom/Test/Report.xdo",
            parameters={"": "1"},
            notify_when_failed=False,
            notify_when_warning=False,
        )


def test_payload_and_recipient_redaction_helpers():
    text = (
        "notificationTo=user.name@example.com "
        "P_B64_CONTENT=SECRET_BASE64_VALUE "
        "Authorization: Bearer token-value"
    )
    safe = bip._preview(text)
    assert "token-value" not in safe
    assert bip._safe_metadata(
        {"P_B64_CONTENT": "SECRET_BASE64_VALUE"}
    )["P_B64_CONTENT"] == "[REDACTED]"


def test_public_signature_and_registration():
    import inspect
    from querysaas.oracle_fusion import FusionConnection

    signature = inspect.signature(FusionConnection.schedule_bip_report)
    required = {
        "output_format",
        "parameters",
        "size_of_data_chunk_download",
        "notification_user_name",
        "notification_to",
        "notify_when_success",
        "notify_when_failed",
        "notify_when_skipped",
        "notify_when_warning",
        "save_data",
        "save_output",
        "schedule_public",
        "job_name",
        "user_job_desc",
    }
    assert required.issubset(signature.parameters)