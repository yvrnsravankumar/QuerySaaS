"""Additive unified Oracle Fusion API for QuerySaaS 0.3.6.

This module routes to the validated 0.3.5 implementations. It does not replace
or rewrite the existing extraction or DuckDB engines.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import contextlib
import io
import time

PARALLEL_THRESHOLD = 5000


@dataclass(frozen=True)
class FusionModeDecision:
    requested_mode: str
    selected_mode: str
    row_count: int | None
    parallel_threshold: int

    def to_dict(self):
        return asdict(self)


def _validate_mode(mode):
    value = str(mode or "auto").strip().casefold()
    if value not in {"auto", "sequential", "parallel"}:
        raise ValueError("mode must be 'auto', 'sequential', or 'parallel'.")
    return value


def _row_count(value):
    if hasattr(value, "row_count"):
        return int(value.row_count)
    if isinstance(value, dict):
        for key in ("row_count", "count", "COUNT"):
            if key in value:
                return int(value[key])
    try:
        return int(value)
    except (TypeError, ValueError) as error:
        raise TypeError("Unable to determine a numeric row count.") from error


def _select_mode(connection, query, mode="auto", parallel_threshold=PARALLEL_THRESHOLD):
    requested = _validate_mode(mode)
    if isinstance(parallel_threshold, bool) or not isinstance(parallel_threshold, int) or parallel_threshold < 1:
        raise ValueError("parallel_threshold must be a positive integer.")
    if requested != "auto":
        return FusionModeDecision(requested, requested, None, parallel_threshold)
    count_result = connection.countquery(query)
    count = _row_count(count_result)
    selected = "parallel" if count > parallel_threshold else "sequential"
    return FusionModeDecision(requested, selected, count, parallel_threshold)


def execute_fusion_query(self, sql, **kwargs):
    """Execute an Oracle Fusion query through the established executequery API."""
    return self.executequery(sql, **kwargs)


def count_fusion_query(self, sql):
    """Count an Oracle Fusion query through the established countquery API."""
    return self.countquery(sql)


def copy_fusion_query_to_file(
    self, query, filename, *, mode="auto", order_by=None,
    parallel_threshold=PARALLEL_THRESHOLD, delimiter=",", chunk_size="auto",
    max_workers="auto", worker_limit=8, max_pending_pages="auto",
    start_offset=0, max_rows=None, all_varchar=True, encoding="utf-8-sig",
    overwrite=True, include_header=True, quotechar='"', quoting=0,
    progress="summary", progress_interval_pages=10,
    output_mode="single_file", output_format="csv", max_file_rows=None,
    max_retries=3, retry_base_seconds=1.0, retry_max_seconds=30.0,
    resume=True, checkpoint_file=None, split_failed_pages=True, minimum_chunk_size=1000,
):
    """Copy a query to one file or an atomic directory of CSV/Parquet parts."""
    from .parallel_parts import copy_fusion_query_to_parts, plan_parallel_execution
    output_mode=str(output_mode).casefold()
    if output_mode not in {"single_file","part_files"}:
        raise ValueError("output_mode must be 'single_file' or 'part_files'.")
    if output_mode=="part_files":
        return copy_fusion_query_to_parts(
            self,query,filename,order_by,mode=mode,parallel_threshold=parallel_threshold,
            chunk_size=chunk_size,max_workers=max_workers,worker_limit=worker_limit,
            max_pending_pages=max_pending_pages,max_rows=max_rows,max_file_rows=max_file_rows,
            output_format=output_format,delimiter=delimiter,encoding=encoding,
            include_header=include_header,overwrite=overwrite,all_varchar=all_varchar,
            progress=progress,progress_interval_pages=progress_interval_pages,
            max_retries=max_retries,retry_base_seconds=retry_base_seconds,
            retry_max_seconds=retry_max_seconds,resume=resume,checkpoint_file=checkpoint_file,
            split_failed_pages=split_failed_pages,minimum_chunk_size=minimum_chunk_size,
        )
    plan=plan_parallel_execution(self,query,mode=mode,parallel_threshold=parallel_threshold,
        chunk_size=chunk_size,max_workers=max_workers,worker_limit=worker_limit,
        max_pending_pages=max_pending_pages,max_rows=max_rows,max_file_rows=None)
    if plan.selected_mode=="sequential":
        return self.copy2file(query,filename,delimiter=delimiter,max_rows=max_rows,
            all_varchar=all_varchar,encoding=encoding,overwrite=overwrite,
            include_header=include_header,quotechar=quotechar,quoting=quoting,
            max_retries=max_retries,retry_base_seconds=retry_base_seconds,
            retry_max_seconds=retry_max_seconds)
    if not isinstance(order_by,str) or not order_by.strip():
        raise ValueError("order_by is required when parallel mode is selected for an arbitrary query.")
    return self.copy2file_parallel(query,filename,order_by,delimiter=delimiter,
        chunk_size=plan.chunk_size,max_workers=plan.max_workers,
        max_pending_pages=plan.max_pending_pages,start_offset=start_offset,max_rows=max_rows,
        all_varchar=all_varchar,encoding=encoding,overwrite=overwrite,
        include_header=include_header,quotechar=quotechar,quoting=quoting,
        progress=progress,progress_interval_pages=progress_interval_pages,
        max_retries=max_retries,retry_base_seconds=retry_base_seconds,
        retry_max_seconds=retry_max_seconds)


def _timed_duckdb_result(result, started, *, operation, total_rows=None, quiet=True):
    elapsed=max(time.perf_counter()-started,0.001)
    if not isinstance(result,dict):
        if quiet:
            print(f"{operation} completed in {elapsed:.2f} seconds ({elapsed/60.0:.2f} minutes).")
        return result
    value=dict(result)
    rows=value.get("processed_rows",value.get("rows",value.get("source_rows",0))) or 0
    value.update({
        "operation":operation,
        "total_rows":total_rows if total_rows is not None else value.get("source_rows"),
        "actual_runtime_seconds":elapsed,
        "actual_runtime_minutes":elapsed/60.0,
        "rows_per_second":float(rows)/elapsed if rows else 0.0,
    })
    if quiet:
        print(f"{operation} completed: {int(rows):,} rows in {elapsed:.2f} seconds ({elapsed/60.0:.2f} minutes).")
    return value


def _run_quietly(function, quiet):
    if not quiet:
        return function()
    with contextlib.redirect_stdout(io.StringIO()):
        return function()


def sync_fusion_query_to_duckdb(
    self, query, target_table, *, mode="auto", primary_key=None, order_by=None,
    parallel_threshold=PARALLEL_THRESHOLD, count=5000,
    duckdb_path="fusion_data.duckdb", replace_target=False,
    all_varchar=True, max_workers=4, quiet=True,
    max_retries=3, retry_base_seconds=1.0, retry_max_seconds=30.0,
    resume=True, checkpoint_file=None, split_failed_pages=True, minimum_chunk_size=1000,
):
    """Synchronize a query to a named DuckDB table and return runtime metrics."""
    started=time.perf_counter()
    target=self._validate_identifier(target_table,"target table")
    if order_by is None and primary_key is not None:
        order_by=primary_key
    decision=_select_mode(self,query,mode,parallel_threshold)
    total_rows=decision.row_count
    if decision.selected_mode=="parallel" and primary_key is None:
        raise ValueError("primary_key is required for parallel arbitrary-query synchronization.")
    def operation():
        if decision.selected_mode=="sequential":
            return self.syncquery2dd(query=query,target_table=target,primary_key=primary_key,
                count=count,duckdb_path=duckdb_path,replace_target=replace_target,
                all_varchar=all_varchar,order_by=order_by,max_retries=max_retries,
                retry_base_seconds=retry_base_seconds,retry_max_seconds=retry_max_seconds)
        return self.syncquery2dd_parallel(query=query,target_table=target,
            primary_key=primary_key,count=count,duckdb_path=duckdb_path,
            replace_target=replace_target,all_varchar=all_varchar,order_by=order_by,
            max_workers=max_workers,max_retries=max_retries,
            retry_base_seconds=retry_base_seconds,retry_max_seconds=retry_max_seconds)
    result=_run_quietly(operation,quiet)
    return _timed_duckdb_result(result,started,operation="Fusion query to DuckDB",total_rows=total_rows,quiet=quiet)


def copy_fusion_table_to_duckdb(
    self, table_name, *, target_table=None, mode="auto", primary_key=None,
    rowid_column_name="SOURCE_ROWID", parallel_threshold=PARALLEL_THRESHOLD,
    count=5000, duckdb_path="fusion_data.duckdb", replace_target=True,
    last_update_date=None, last_update_date_column="LAST_UPDATE_DATE",
    additional_where=None, all_varchar=True, max_workers=4, quiet=True,
    max_retries=3, retry_base_seconds=1.0, retry_max_seconds=30.0,
    resume=True, checkpoint_file=None, split_failed_pages=True, minimum_chunk_size=1000,
):
    """Copy a Fusion table to an optional differently named DuckDB target."""
    table=self._validate_identifier(table_name,"table name")
    target=self._validate_identifier(target_table or table,"target table")
    filters=[]
    if last_update_date is not None:
        column=self._validate_identifier(last_update_date_column,"last-update-date column")
        safe_date=str(last_update_date).replace("'","''")
        filters.append(f"querysaas_source.{column} >= TIMESTAMP '{safe_date}'")
    if additional_where:
        filters.append(f"({additional_where})")
    where_clause=" WHERE "+" AND ".join(filters) if filters else ""
    if primary_key is None:
        key=self._validate_identifier(rowid_column_name,"ROWID fallback column")
        query=(f"SELECT ROWIDTOCHAR(querysaas_source.ROWID) AS {key}, "
               f"querysaas_source.* FROM {table} querysaas_source{where_clause}")
    else:
        key=primary_key
        query=f"SELECT querysaas_source.* FROM {table} querysaas_source{where_clause}"
    return sync_fusion_query_to_duckdb(self,query,target,mode=mode,
        primary_key=key,order_by=key,parallel_threshold=parallel_threshold,
        count=count,duckdb_path=duckdb_path,replace_target=replace_target,
        all_varchar=all_varchar,max_workers=max_workers,quiet=quiet,
        max_retries=max_retries,retry_base_seconds=retry_base_seconds,
        retry_max_seconds=retry_max_seconds)


def install_unified_fusion_methods(connection_class):
    connection_class.execute_fusion_query = execute_fusion_query
    connection_class.count_fusion_query = count_fusion_query
    connection_class.copy_fusion_query_to_file = copy_fusion_query_to_file
    connection_class.copy_fusion_table_to_duckdb = copy_fusion_table_to_duckdb
    connection_class.sync_fusion_query_to_duckdb = sync_fusion_query_to_duckdb


LEGACY_METHOD_MAP = {
    "executequery": "execute_fusion_query",
    "countquery": "count_fusion_query",
    "copy2file": "copy_fusion_query_to_file[mode=sequential]",
    "copy2file_parallel": "copy_fusion_query_to_file[mode=parallel]",
    "copy2dd": "copy_fusion_table_to_duckdb[mode=sequential]",
    "copy2dd_parallel": "copy_fusion_table_to_duckdb[mode=parallel]",
    "syncquery2dd": "sync_fusion_query_to_duckdb[mode=sequential]",
    "syncquery2dd_parallel": "sync_fusion_query_to_duckdb[mode=parallel]",
}



