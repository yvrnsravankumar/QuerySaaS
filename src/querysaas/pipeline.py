"""Fusion-to-local file pipelines with ordered, atomic output."""
from __future__ import annotations
import csv, os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4
import pandas as pd
from .exceptions import PipelinePageError, PipelineSchemaError
from .sql import OracleSqlPlanner

@dataclass(frozen=True)
class LocalFileCopyResult:
    filename:str; rows:int; columns:int; delimiter:str; encoding:str; chunks:int; chunk_size:int; max_workers:int; order_by:str
    @property
    def path(self): return self.filename
    def to_dict(self): return asdict(self)

def _validate_filename(filename):
    if filename is None or not str(filename).strip(): raise ValueError('filename cannot be empty')
    p=Path(filename).expanduser().resolve(); p.parent.mkdir(parents=True,exist_ok=True); return p

def _validate_delimiter(d):
    if not isinstance(d,str) or len(d)!=1 or d in {'\r','\n','\0'}: raise ValueError('delimiter must be one non-newline character')
    return d

def _fetch_page(connection, plan, offset, limit, all_varchar, filename):
    try:
        frame=connection.executequery(plan.executable_sql,all_varchar=all_varchar)
        return offset, limit, frame if isinstance(frame,pd.DataFrame) else pd.DataFrame(frame)
    except Exception as exc:
        raise PipelinePageError('Fusion page request failed',offset=offset,limit=limit,generated_sql=plan.executable_sql,filename=str(filename),original_exception=exc) from exc

def copy_fusion_to_local_parallel(connection, query, filename, order_by, *, delimiter=',', chunk_size=5000, max_workers=4, start_offset=0, max_rows=None, all_varchar=True, encoding='utf-8-sig', overwrite=True, include_header=True, quotechar='"', quoting=csv.QUOTE_MINIMAL):
    if connection is None or not callable(getattr(connection,'executequery',None)): raise TypeError('connection must expose executequery')
    if not isinstance(chunk_size,int) or chunk_size<1: raise ValueError('chunk_size must be positive')
    if not isinstance(max_workers,int) or max_workers<1: raise ValueError('max_workers must be positive')
    if not isinstance(start_offset,int) or start_offset<0: raise ValueError('start_offset must be zero or greater')
    if max_rows is not None and (not isinstance(max_rows,int) or max_rows<1): raise ValueError('max_rows must be positive or None')
    if not isinstance(quotechar,str) or len(quotechar)!=1: raise ValueError('quotechar must be exactly one character')
    planner=OracleSqlPlanner(); planner.validate_query(query); planner.page_query(query,order_by,start_offset,1)
    output=_validate_filename(filename); delimiter=_validate_delimiter(delimiter)
    if output.exists() and not overwrite: raise FileExistsError(f'Destination already exists: {output}')
    temporary=output.with_name(f'.{output.name}.{uuid4().hex}.tmp')
    total_rows=total_columns=chunks=0; next_offset=start_offset; finished=False; expected=None; wrote_header=False
    try:
        with temporary.open('w',encoding=encoding,newline='') as stream:
            while not finished:
                specs=[]
                for _ in range(max_workers):
                    remaining=None if max_rows is None else max_rows-(next_offset-start_offset)
                    if remaining is not None and remaining<=0: finished=True; break
                    lim=chunk_size if remaining is None else min(chunk_size,remaining)
                    specs.append((next_offset,lim,planner.page_query(query,order_by,next_offset,lim))); next_offset+=lim
                if not specs: break
                pages={}
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    futures={executor.submit(_fetch_page,connection,plan,off,lim,all_varchar,output):(off,lim) for off,lim,plan in specs}
                    try:
                        for future in as_completed(futures):
                            off,lim=futures[future]; pages[off]=future.result()
                    except Exception:
                        for pending in futures: pending.cancel()
                        raise
                for off,lim,_ in sorted(specs,key=lambda x:x[0]):
                    _,used,frame=pages[off]; rows=len(frame.index)
                    if rows:
                        actual=tuple(str(c) for c in frame.columns)
                        if expected is None: expected=actual; total_columns=len(actual)
                        elif actual!=expected: raise PipelineSchemaError('Fusion page schema changed',expected_columns=expected,actual_columns=actual,offset=off,limit=used,filename=str(output))
                        frame.to_csv(stream,sep=delimiter,index=False,header=include_header and not wrote_header,quotechar=quotechar,quoting=quoting,lineterminator='\n')
                        wrote_header=True; total_rows+=rows; chunks+=1
                    if rows<used: finished=True; break
        os.replace(temporary,output)
    except Exception:
        if temporary.exists(): temporary.unlink()
        raise
    finally:
        if temporary.exists(): temporary.unlink()
    return LocalFileCopyResult(str(output),total_rows,total_columns,delimiter,encoding,chunks,chunk_size,max_workers,order_by.strip())

def copy_fusion_to_local(connection, query, filename, *, delimiter=',', max_rows=None, all_varchar=True, encoding='utf-8-sig', overwrite=True, include_header=True, quotechar='"', quoting=csv.QUOTE_MINIMAL):
    output=_validate_filename(filename)
    if output.exists() and not overwrite: raise FileExistsError(f'Destination already exists: {output}')
    plan=OracleSqlPlanner().limit_query(query,max_rows) if max_rows is not None else OracleSqlPlanner().validate_query(query)
    frame=connection.executequery(plan.executable_sql,all_varchar=all_varchar)
    if not isinstance(frame,pd.DataFrame): frame=pd.DataFrame(frame)
    temp=output.with_name(f'.{output.name}.{uuid4().hex}.tmp')
    try:
        frame.to_csv(temp,sep=_validate_delimiter(delimiter),index=False,header=include_header,encoding=encoding,quotechar=quotechar,quoting=quoting,lineterminator='\n')
        os.replace(temp,output)
    finally:
        if temp.exists(): temp.unlink()
    return LocalFileCopyResult(str(output),len(frame),len(frame.columns),delimiter,encoding,1 if len(frame) else 0,max_rows or len(frame) or 1,1,'')

def _copy2file(self, query, filename, **kwargs): return copy_fusion_to_local(self,query,filename,**kwargs)
def _copy2file_parallel(self, query, filename, order_by, **kwargs): return copy_fusion_to_local_parallel(self,query,filename,order_by,**kwargs)

def install_pipeline_methods(connection_class):
    connection_class.copy2file=_copy2file; connection_class.copy2file_parallel=_copy2file_parallel
