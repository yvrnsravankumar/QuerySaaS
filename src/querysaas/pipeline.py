"""Fusion-to-local file pipelines with bounded, ordered, atomic output."""
from __future__ import annotations
import csv, inspect, os, time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import asdict, dataclass
from pathlib import Path
from uuid import uuid4
import pandas as pd
from .exceptions import PipelinePageError, PipelineSchemaError
from .sql import OracleSqlPlanner

@dataclass(frozen=True)
class LocalFileCopyResult:
    filename:str; rows:int; columns:int; delimiter:str; encoding:str; chunks:int; chunk_size:int; max_workers:int; order_by:str
    elapsed_seconds:float=0.0; rows_per_second:float=0.0; pages_submitted:int=0; peak_pending:int=0; retry_scope:str='operation'
    @property
    def path(self): return self.filename
    def to_dict(self): return asdict(self)

def _validate_filename(filename):
    if filename is None or not str(filename).strip(): raise ValueError('filename cannot be empty')
    p=Path(filename).expanduser().resolve(); p.parent.mkdir(parents=True,exist_ok=True); return p

def _validate_delimiter(d):
    if not isinstance(d,str) or len(d)!=1 or d in {'\r','\n','\0'}: raise ValueError('delimiter must be one non-newline character')
    return d

def _fetch_page(connection, plan, offset, limit, all_varchar, filename, max_retries, retry_base_seconds, retry_max_seconds):
    try:
        executequery=connection.executequery
        parameters=inspect.signature(executequery).parameters
        accepts_keywords=any(parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in parameters.values())
        kwargs={'all_varchar':all_varchar}
        if accepts_keywords or 'max_retries' in parameters: kwargs['max_retries']=max_retries
        if accepts_keywords or 'retry_base_seconds' in parameters: kwargs['retry_base_seconds']=retry_base_seconds
        if accepts_keywords or 'retry_max_seconds' in parameters: kwargs['retry_max_seconds']=retry_max_seconds
        frame=executequery(plan.executable_sql,**kwargs)
        return offset, limit, frame if isinstance(frame,pd.DataFrame) else pd.DataFrame(frame)
    except Exception as exc:
        raise PipelinePageError('Fusion page request failed',offset=offset,limit=limit,generated_sql=plan.executable_sql,filename=str(filename),original_exception=exc) from exc

def copy_fusion_to_local_parallel(connection, query, filename, order_by, *, delimiter=',', chunk_size=5000, max_workers=4, max_pending_pages=None, start_offset=0, max_rows=None, all_varchar=True, encoding='utf-8-sig', overwrite=True, include_header=True, quotechar='"', quoting=csv.QUOTE_MINIMAL, progress='none', progress_interval_pages=10, max_retries=3, retry_base_seconds=1.0, retry_max_seconds=30.0):
    if connection is None or not callable(getattr(connection,'executequery',None)): raise TypeError('connection must expose executequery')
    if isinstance(chunk_size,bool) or not isinstance(chunk_size,int) or chunk_size<1: raise ValueError('chunk_size must be positive')
    if isinstance(max_workers,bool) or not isinstance(max_workers,int) or not 1<=max_workers<=32: raise ValueError('max_workers must be between 1 and 32')
    if max_pending_pages is None: max_pending_pages=max_workers*2
    if isinstance(max_pending_pages,bool) or not isinstance(max_pending_pages,int) or max_pending_pages<max_workers: raise ValueError('max_pending_pages must be at least max_workers')
    if isinstance(start_offset,bool) or not isinstance(start_offset,int) or start_offset<0: raise ValueError('start_offset must be zero or greater')
    if max_rows is not None and (isinstance(max_rows,bool) or not isinstance(max_rows,int) or max_rows<1): raise ValueError('max_rows must be positive or None')
    if not isinstance(quotechar,str) or len(quotechar)!=1: raise ValueError('quotechar must be exactly one character')
    if progress not in {'none','summary','pages'}: raise ValueError("progress must be 'none', 'summary', or 'pages'")
    if isinstance(progress_interval_pages,bool) or not isinstance(progress_interval_pages,int) or progress_interval_pages<1: raise ValueError('progress_interval_pages must be positive')
    planner=OracleSqlPlanner(); planner.validate_query(query); planner.page_query(query,order_by,start_offset,1)
    output=_validate_filename(filename); delimiter=_validate_delimiter(delimiter)
    if output.exists() and not overwrite: raise FileExistsError(f'Destination already exists: {output}')
    temporary=output.with_name(f'.{output.name}.{uuid4().hex}.tmp')
    total_rows=total_columns=chunks=0; next_offset=start_offset; expected=None; wrote_header=False
    submitted=peak_pending=0; next_write=start_offset; terminal_offset=None; pages={}; pending={}; started=time.perf_counter()
    def can_submit():
        if terminal_offset is not None: return False
        if max_rows is None: return True
        return next_offset-start_offset < max_rows
    def submit_one(executor):
        nonlocal next_offset,submitted,peak_pending
        if not can_submit(): return False
        remaining=None if max_rows is None else max_rows-(next_offset-start_offset)
        limit=chunk_size if remaining is None else min(chunk_size,remaining)
        offset=next_offset; plan=planner.page_query(query,order_by,offset,limit); next_offset+=limit
        future=executor.submit(_fetch_page,connection,plan,offset,limit,all_varchar,output,max_retries,retry_base_seconds,retry_max_seconds)
        pending[future]=(offset,limit); submitted+=1; peak_pending=max(peak_pending,len(pending)); return True
    try:
        with temporary.open('w',encoding=encoding,newline='') as stream, ThreadPoolExecutor(max_workers=max_workers) as executor:
            while len(pending)<max_pending_pages and submit_one(executor): pass
            while pending:
                done,_=wait(tuple(pending),return_when=FIRST_COMPLETED)
                for future in done:
                    off,lim=pending.pop(future)
                    try: pages[off]=future.result()
                    except Exception:
                        for queued in pending: queued.cancel()
                        raise
                while next_write in pages:
                    off,used,frame=pages.pop(next_write); rows=len(frame.index)
                    if rows:
                        actual=tuple(str(c) for c in frame.columns)
                        if expected is None: expected=actual; total_columns=len(actual)
                        elif actual!=expected: raise PipelineSchemaError('Fusion page schema changed',expected_columns=expected,actual_columns=actual,offset=off,limit=used,filename=str(output))
                        frame.to_csv(stream,sep=delimiter,index=False,header=include_header and not wrote_header,quotechar=quotechar,quoting=quoting,lineterminator='\n')
                        wrote_header=True; total_rows+=rows; chunks+=1
                        if progress=='pages' or (progress=='summary' and chunks%progress_interval_pages==0):
                            elapsed=max(time.perf_counter()-started,0.001); print(f'Parallel progress: {total_rows:,} rows, {chunks} pages, {total_rows/elapsed:,.0f} rows/second')
                    next_write+=used
                    if rows<used:
                        terminal_offset=off
                        for future,(queued_offset,_) in list(pending.items()):
                            if queued_offset>off: future.cancel(); pending.pop(future,None)
                        pages={key:value for key,value in pages.items() if key<=off}
                        break
                while terminal_offset is None and len(pending)<max_pending_pages and submit_one(executor): pass
        os.replace(temporary,output)
    except Exception:
        if temporary.exists(): temporary.unlink()
        raise
    finally:
        pages.clear()
        if temporary.exists(): temporary.unlink()
    elapsed=max(time.perf_counter()-started,0.001)
    return LocalFileCopyResult(str(output),total_rows,total_columns,delimiter,encoding,chunks,chunk_size,max_workers,order_by.strip(),elapsed,total_rows/elapsed,submitted,peak_pending,'page')

def copy_fusion_to_local(connection, query, filename, *, delimiter=',', max_rows=None, all_varchar=True, encoding='utf-8-sig', overwrite=True, include_header=True, quotechar='"', quoting=csv.QUOTE_MINIMAL):
    output=_validate_filename(filename)
    if output.exists() and not overwrite: raise FileExistsError(f'Destination already exists: {output}')
    plan=OracleSqlPlanner().limit_query(query,max_rows) if max_rows is not None else OracleSqlPlanner().validate_query(query)
    frame=connection.executequery(plan.executable_sql,all_varchar=all_varchar)
    if not isinstance(frame,pd.DataFrame): frame=pd.DataFrame(frame)
    temp=output.with_name(f'.{output.name}.{uuid4().hex}.tmp'); started=time.perf_counter()
    try:
        frame.to_csv(temp,sep=_validate_delimiter(delimiter),index=False,header=include_header,encoding=encoding,quotechar=quotechar,quoting=quoting,lineterminator='\n')
        os.replace(temp,output)
    finally:
        if temp.exists(): temp.unlink()
    elapsed=max(time.perf_counter()-started,0.001)
    return LocalFileCopyResult(str(output),len(frame),len(frame.columns),delimiter,encoding,1 if len(frame) else 0,max_rows or len(frame) or 1,1,'',elapsed,len(frame)/elapsed,1,1,'operation')

def _copy2file(self, query, filename, **kwargs): return copy_fusion_to_local(self,query,filename,**kwargs)
def _copy2file_parallel(self, query, filename, order_by, *, delimiter=',', chunk_size=5000, max_workers=4, max_pending_pages=None, start_offset=0, max_rows=None, all_varchar=True, encoding='utf-8-sig', overwrite=True, include_header=True, quotechar='"', quoting=csv.QUOTE_MINIMAL, progress='none', progress_interval_pages=10, max_retries=3, retry_base_seconds=1.0, retry_max_seconds=30.0):
    return copy_fusion_to_local_parallel(self,query,filename,order_by,delimiter=delimiter,chunk_size=chunk_size,max_workers=max_workers,max_pending_pages=max_pending_pages,start_offset=start_offset,max_rows=max_rows,all_varchar=all_varchar,encoding=encoding,overwrite=overwrite,include_header=include_header,quotechar=quotechar,quoting=quoting,progress=progress,progress_interval_pages=progress_interval_pages,max_retries=max_retries,retry_base_seconds=retry_base_seconds,retry_max_seconds=retry_max_seconds)

def install_pipeline_methods(connection_class):
    connection_class.copy2file=_copy2file; connection_class.copy2file_parallel=_copy2file_parallel
