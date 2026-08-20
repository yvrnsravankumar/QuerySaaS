import inspect
import pytest
import querysaas
from querysaas import FusionConnection
from querysaas.fusion_api import LEGACY_METHOD_MAP, _select_mode


class CountResult:
    def __init__(self, row_count):
        self.row_count = row_count


class FakeConnection:
    _validate_identifier = staticmethod(lambda value, label="identifier": str(value))
    def __init__(self, rows):
        self.rows = rows
        self.calls = []
    def countquery(self, query):
        return CountResult(self.rows)
    def copy2file(self, *args, **kwargs):
        self.calls.append(("copy2file", args, kwargs)); return "sequential-file"
    def copy2file_parallel(self, *args, **kwargs):
        self.calls.append(("copy2file_parallel", args, kwargs)); return "parallel-file"
    def syncquery2dd(self, **kwargs):
        self.calls.append(("syncquery2dd", (), kwargs)); return "sequential-sync"
    def syncquery2dd_parallel(self, **kwargs):
        self.calls.append(("syncquery2dd_parallel", (), kwargs)); return "parallel-sync"
    def copy2dd(self, **kwargs):
        self.calls.append(("copy2dd", (), kwargs)); return "sequential-table"
    def copy2dd_parallel(self, **kwargs):
        self.calls.append(("copy2dd_parallel", (), kwargs)); return "parallel-table"


def test_version_and_methods():
    assert querysaas.__version__ == "0.3.8"
    for name in ["execute_fusion_query", "count_fusion_query", "copy_fusion_query_to_file", "copy_fusion_table_to_duckdb", "sync_fusion_query_to_duckdb"]:
        assert callable(getattr(FusionConnection, name))
    for name in LEGACY_METHOD_MAP:
        assert callable(getattr(FusionConnection, name))


def test_auto_threshold_boundary():
    assert _select_mode(FakeConnection(5000), "SELECT 1 FROM DUAL").selected_mode == "sequential"
    assert _select_mode(FakeConnection(5001), "SELECT 1 FROM DUAL").selected_mode == "parallel"


def test_query_file_routes_without_rowid():
    from querysaas.fusion_api import copy_fusion_query_to_file
    small = FakeConnection(10)
    assert copy_fusion_query_to_file(small, "SELECT ID FROM T", "x.csv") == "sequential-file"
    large = FakeConnection(6000)
    assert copy_fusion_query_to_file(large, "SELECT ID FROM T", "x.csv", order_by="ID") == "parallel-file"
    assert "ROWID" not in large.calls[0][1][0].upper()


def test_large_query_requires_order_by():
    from querysaas.fusion_api import copy_fusion_query_to_file
    with pytest.raises(ValueError, match="order_by"):
        copy_fusion_query_to_file(FakeConnection(6000), "SELECT ID FROM T", "x.csv")


def test_query_sync_never_injects_rowid():
    from querysaas.fusion_api import sync_fusion_query_to_duckdb
    connection = FakeConnection(6000)
    result = sync_fusion_query_to_duckdb(connection, "SELECT ID FROM T", "t", primary_key="ID", order_by="ID")
    assert result == "parallel-sync"
    assert "ROWID" not in connection.calls[0][2]["query"].upper()


def test_table_only_rowid_fallback():
    from querysaas.fusion_api import copy_fusion_table_to_duckdb
    connection = FakeConnection(6000)
    result = copy_fusion_table_to_duckdb(connection, "GL_CODE_COMBINATIONS")
    assert result == "parallel-sync"
    call = connection.calls[0][2]
    assert "ROWIDTOCHAR(querysaas_source.ROWID)" in call["query"]
    assert call["primary_key"] == "SOURCE_ROWID"
    assert call["order_by"] == "SOURCE_ROWID"


def test_signatures_keep_safe_defaults():
    signature = inspect.signature(FusionConnection.copy_fusion_query_to_file)
    assert signature.parameters["mode"].default == "auto"
    assert signature.parameters["parallel_threshold"].default == 5000
    assert signature.parameters["max_retries"].default == 3


