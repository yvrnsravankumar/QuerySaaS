from types import SimpleNamespace
import pytest
import querysaas.fbdi as fbdi


def test_normalize_ess_parameters():
    assert fbdi._normalize_ess_parameters(None) == "#NULL"
    assert fbdi._normalize_ess_parameters([1, None, "N"]) == "1,#NULL,N"
    assert fbdi._normalize_ess_parameters("1,2") == "1,2"


def test_submit_ess_job(monkeypatch):
    connection = SimpleNamespace()
    monkeypatch.setattr(fbdi, "_post", lambda self, payload: {"ReqstId": "14557", **payload})
    result = fbdi.submit_ess_job(
        connection,
        "/oracle/apps/ess/test",
        "TestJob",
        [1, None, "N"],
    )
    assert result["request_id"] == "14557"
    assert result["ess_parameters"] == "1,#NULL,N"


def test_submit_ess_job_validation():
    with pytest.raises(ValueError):
        fbdi.submit_ess_job(SimpleNamespace(), "", "TestJob")
    with pytest.raises(ValueError):
        fbdi.submit_ess_job(SimpleNamespace(), "/test", "")


def test_purge_reuses_submit_ess_job(monkeypatch):
    captured = {}
    connection = SimpleNamespace()
    def submit(**kwargs):
        captured.update(kwargs)
        return {"status": "SUBMITTED", "request_id": "900", "ess_parameters": kwargs["parameters"], "response": {"ReqstId": "900"}}
    connection.submit_ess_job = submit
    monkeypatch.setattr(fbdi, "_resolve", lambda self, selectors: {"interface_options_id": "39", "business_object": "Project Budget"})
    result = fbdi.purge_fbdi(connection, load_request_id=100, standard_file_name="ProjectBudgets")
    assert result["purge_request_id"] == "900"
    assert captured["job_definition_name"] == "InterfaceLoaderPurge"
    assert captured["parameters"] == "39,100,#NULL,#NULL,#NULL,ORA_FBDI,USER,#NULL,#NULL"
