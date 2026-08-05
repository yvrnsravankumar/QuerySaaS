"""Unit tests for QuerySaaS live FBDI registry refresh and viewing APIs."""
from types import SimpleNamespace

import pandas as pd
import pytest

import querysaas.fbdi as fbdi


LIVE_ROWS = [
    {
        "ERP_FAMILY": "PRJ",
        "APPLICATION_ID": "10039",
        "BUSINESS_OBJECT": "Project Budget",
        "ERP_INTERFACE_OPTIONS_ID": "39",
        "UCM_ACCOUNT": "prj/projectControl/import",
        "DOCUMENT_ACCOUNT": "prj$/projectControl$/import$",
        "LOAD_JOB_NAME": "",
        "IMPORT_JOB_NAME": (
            "/oracle/apps/ess/projects/control/budgetsAndForecasts;"
            "ImportBudgetsInterfaceData"
        ),
        "CONTROL_FILE_NAME": "PjoPlanVersionsXface.ctl",
        "INTERFACE_TABLE_NAMES": "PJO_PLAN_VERSIONS_XFACE",
    },
    {
        "ERP_FAMILY": "FIN",
        "APPLICATION_ID": "200",
        "BUSINESS_OBJECT": "payableInvoiceBatch",
        "ERP_INTERFACE_OPTIONS_ID": "1",
        "UCM_ACCOUNT": "fin/payables/import",
        "DOCUMENT_ACCOUNT": "fin$/payables$/import$",
        "LOAD_JOB_NAME": "",
        "IMPORT_JOB_NAME": (
            "/oracle/apps/ess/financials/payables/invoices/transactions;"
            "APXIIMPT"
        ),
        "CONTROL_FILE_NAME": "ApInvoicesInterface.ctl",
        "INTERFACE_TABLE_NAMES": "AP_INVOICES_INTERFACE",
    },
]


def make_frame():
    return pd.DataFrame(LIVE_ROWS)


def make_connection(frame=None, error=None):
    calls = []

    def executequery(sql, all_varchar=True):
        calls.append({"sql": sql, "all_varchar": all_varchar})
        if error is not None:
            raise error
        return (frame if frame is not None else make_frame()).copy()

    connection = SimpleNamespace(executequery=executequery)
    connection.calls = calls
    return connection


def test_refresh_queries_oracle_and_caches_rows():
    connection = make_connection()

    result = fbdi.refresh_fbdi_jobs(connection, force=True)

    assert len(connection.calls) == 1
    assert "FROM fun_erp_interface_options opt" in connection.calls[0]["sql"]
    assert "LEFT JOIN fun_erp_interface_details det" in connection.calls[0]["sql"]
    assert connection.calls[0]["all_varchar"] is True
    assert result.attrs["source"] == "oracle_fusion"
    assert result.attrs["refreshed_at"]
    assert result.attrs["refresh_error"] is None
    assert len(result) == 2


def test_refresh_without_force_reuses_connection_cache():
    connection = make_connection()

    fbdi.refresh_fbdi_jobs(connection, force=True)
    second = fbdi.refresh_fbdi_jobs(connection, force=False)

    assert len(connection.calls) == 1
    assert second.attrs["source"] == "oracle_fusion"


def test_force_refresh_queries_oracle_again():
    connection = make_connection()

    fbdi.refresh_fbdi_jobs(connection, force=True)
    fbdi.refresh_fbdi_jobs(connection, force=True)

    assert len(connection.calls) == 2


def test_get_fbdi_jobs_auto_refreshes_on_first_use():
    connection = make_connection()

    result = fbdi.get_fbdi_jobs(connection)

    assert len(connection.calls) == 1
    assert result.attrs["source"] == "oracle_fusion"
    assert set(result["BUSINESS_OBJECT"]) == {
        "Project Budget",
        "payableInvoiceBatch",
    }


def test_get_fbdi_jobs_business_object_filter_is_case_insensitive():
    connection = make_connection()

    result = fbdi.get_fbdi_jobs(
        connection,
        business_object="project budget",
    )

    assert len(result) == 1
    assert result.iloc[0]["ERP_INTERFACE_OPTIONS_ID"] == "39"


def test_get_fbdi_jobs_interface_table_filter_handles_csv_lists():
    rows = make_frame()
    rows.loc[
        rows["ERP_INTERFACE_OPTIONS_ID"] == "1",
        "INTERFACE_TABLE_NAMES",
    ] = "AP_INVOICES_INTERFACE, AP_INVOICE_LINES_INTERFACE"
    connection = make_connection(rows)

    result = fbdi.get_fbdi_jobs(
        connection,
        interface_table="ap_invoice_lines_interface",
    )

    assert len(result) == 1
    assert result.iloc[0]["BUSINESS_OBJECT"] == "payableInvoiceBatch"


def test_get_fbdi_jobs_dictionary_result():
    connection = make_connection()

    result = fbdi.get_fbdi_jobs(
        connection,
        erp_family="PRJ",
        as_dataframe=False,
    )

    assert result["count"] == 1
    assert result["source"] == "oracle_fusion"
    assert result["rows"][0]["BUSINESS_OBJECT"] == "Project Budget"


def test_live_query_missing_required_columns_is_rejected(monkeypatch):
    incomplete = make_frame().drop(columns=["CONTROL_FILE_NAME"])
    connection = make_connection(incomplete)
    monkeypatch.setattr(fbdi, "_packaged_rows", lambda: [])

    with pytest.raises(RuntimeError, match="no packaged fallback"):
        fbdi.refresh_fbdi_jobs(connection, force=True)


def test_failed_live_refresh_uses_packaged_fallback(monkeypatch):
    connection = make_connection(error=RuntimeError("metadata access denied"))
    monkeypatch.setattr(fbdi, "_packaged_rows", lambda: list(LIVE_ROWS))

    result = fbdi.refresh_fbdi_jobs(connection, force=True)

    assert result.attrs["source"] == "packaged_fallback"
    assert "metadata access denied" in result.attrs["refresh_error"]
    assert len(result) == 2


def test_no_live_or_packaged_registry_raises(monkeypatch):
    connection = make_connection(error=RuntimeError("query failed"))
    monkeypatch.setattr(fbdi, "_packaged_rows", lambda: [])

    with pytest.raises(RuntimeError, match="no packaged fallback"):
        fbdi.refresh_fbdi_jobs(connection, force=True)


def test_force_must_be_boolean():
    connection = make_connection()

    with pytest.raises(ValueError, match="force"):
        fbdi.refresh_fbdi_jobs(connection, force="yes")


def test_installer_registers_public_methods():
    class FakeConnection:
        pass

    fbdi.install_fbdi_methods(FakeConnection)

    assert FakeConnection.refresh_fbdi_jobs is fbdi.refresh_fbdi_jobs
    assert FakeConnection.get_fbdi_jobs is fbdi.get_fbdi_jobs
