"""Resumable exact-offset parallel part extraction for QuerySaaS 0.3.7."""
from __future__ import annotations
import hashlib, json, math, os, shutil, time
from collections import deque
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import asdict, dataclass
from pathlib import Path
import duckdb
from .exceptions import PipelineSchemaError
from .pipeline import _fetch_page
from .sql import OracleSqlPlanner

@dataclass(frozen=True)
class ParallelExecutionPlan:
    total_rows:int; planned_rows:int; selected_mode:str; chunk_size:int; total_chunks:int; max_workers:int; max_pending_pages:int; expected_output_files:int
    def to_dict(self): return asdict(self)

@dataclass(frozen=True)
class PartFileCopyResult:
    output_directory:str; manifest_file:str; rows:int; columns:int; part_count:int; output_format:str; elapsed_seconds:float; rows_per_second:float; execution_plan:ParallelExecutionPlan; checkpoint_file:str|None=None; resumed_parts:int=0; split_pages:int=0
    @property
    def filename(self): return self.output_directory
    @property
    def path(self): return self.output_directory
    def to_dict(self):
        value=asdict(self); value['execution_plan']=self.execution_plan.to_dict(); return value

def _count_rows(connection, query):
    value=connection.countquery(query)
    if hasattr(value,'row_count'): return int(value.row_count)
    if isinstance(value,dict):
        for key in ('row_count','count','COUNT'):
            if key in value: return int(value[key])
    return int(value)

def plan_parallel_execution(connection, query, *, mode='auto', parallel_threshold=5000, chunk_size=10000, max_workers=16, worker_limit=16, max_pending_pages=32, max_rows=None, max_file_rows=None):
    total=_count_rows(connection,query)
    planned=total if max_rows is None else min(total,int(max_rows))
    chunk=10000 if chunk_size=='auto' else int(chunk_size)
    if chunk<1: raise ValueError('chunk_size must be positive or auto')
    if max_file_rows is not None:
        if isinstance(max_file_rows,bool) or int(max_file_rows)<1: raise ValueError('max_file_rows must be positive or None')
        chunk=min(chunk,int(max_file_rows))
    chunks=math.ceil(planned/chunk) if planned else 0
    requested=str(mode or 'auto').casefold()
    if requested not in {'auto','sequential','parallel'}: raise ValueError("mode must be 'auto', 'sequential', or 'parallel'")
    selected=('parallel' if planned>parallel_threshold else 'sequential') if requested=='auto' else requested
    requested_workers = 32 if max_workers == "auto" else int(max_workers)
    workers=min(requested_workers,int(worker_limit),max(chunks,1))
    if workers<1 or workers>32: raise ValueError('max_workers must resolve between 1 and 32')
    if selected=='sequential': workers=1
    requested_pending=workers*2 if max_pending_pages in ('auto',None) else int(max_pending_pages)
    pending=min(max(chunks,1),requested_pending)
    if pending<workers: pending=workers
    return ParallelExecutionPlan(total,planned,selected,chunk,chunks,workers,pending,chunks)

def _sha256(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''): digest.update(block)
    return digest.hexdigest()

def _write_part(frame,path,output_format,delimiter,encoding,include_header):
    if output_format=='csv': frame.to_csv(path,index=False,header=include_header,sep=delimiter,encoding=encoding,lineterminator='\n')
    else:
        con=duckdb.connect(':memory:')
        try:
            con.register('_querysaas_part',frame); escaped=str(path).replace("'","''")
            con.execute(f"COPY _querysaas_part TO '{escaped}' (FORMAT PARQUET, COMPRESSION ZSTD)")
        finally: con.close()

def _payload_failure(error):
    current=error; parts=[]; seen=set()
    while current is not None and id(current) not in seen:
        seen.add(id(current)); parts.append(f'{type(current).__name__}: {current}')
        current=getattr(current,'original_exception',None) or getattr(current,'__cause__',None)
    text=' '.join(parts).casefold()
    return any(token in text for token in ('invalid soap xml','parseerror','no element found','truncated','unexpected end','reportbytes'))

def _query_hash(query,order_by,planned,fmt):
    value=json.dumps({'query':query.strip(),'order_by':order_by.strip(),'planned_rows':planned,'format':fmt},sort_keys=True)
    return hashlib.sha256(value.encode('utf-8')).hexdigest()

def _atomic_json(path,value):
    temporary=Path(str(path)+'.tmp'); temporary.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8'); os.replace(temporary,path)

def copy_fusion_query_to_parts(connection, query, output_directory, order_by, *, mode='auto', parallel_threshold=5000, chunk_size=10000, max_workers=16, worker_limit=16, max_pending_pages=32, max_rows=None, max_file_rows=None, output_format='parquet', delimiter=',', encoding='utf-8-sig', include_header=True, overwrite=True, all_varchar=True, progress='summary', progress_interval_pages=10, max_retries=3, retry_base_seconds=1.0, retry_max_seconds=30.0, resume=True, checkpoint_file=None, split_failed_pages=True, minimum_chunk_size=1000):
    if not isinstance(order_by,str) or not order_by.strip(): raise ValueError('order_by is required for part_files output')
    output_format=str(output_format).casefold()
    if output_format not in {'csv','parquet'}: raise ValueError("output_format must be 'csv' or 'parquet'")
    if progress not in {'none','summary','pages'}: raise ValueError("progress must be 'none', 'summary', or 'pages'")
    if isinstance(minimum_chunk_size,bool) or int(minimum_chunk_size)<1: raise ValueError('minimum_chunk_size must be positive')
    plan=plan_parallel_execution(connection,query,mode=mode,parallel_threshold=parallel_threshold,chunk_size=chunk_size,max_workers=max_workers,worker_limit=worker_limit,max_pending_pages=max_pending_pages,max_rows=max_rows,max_file_rows=max_file_rows)
    output=Path(output_directory).expanduser().resolve(); output.parent.mkdir(parents=True,exist_ok=True)
    if output.exists() and not overwrite: raise FileExistsError(f'Destination already exists: {output}')
    work=output.with_name(f'.{output.name}.querysaas-work'); parts_dir=work/'parts'; parts_dir.mkdir(parents=True,exist_ok=True)
    checkpoint=Path(checkpoint_file).expanduser().resolve() if checkpoint_file else work/'checkpoint.json'
    query_hash=_query_hash(query,order_by,plan.planned_rows,output_format)
    completed=[]; resumed_parts=0
    if resume and checkpoint.exists():
        state=json.loads(checkpoint.read_text(encoding='utf-8'))
        if state.get('query_hash')!=query_hash: raise ValueError('Existing checkpoint does not match the current query and extraction plan')
        for item in state.get('completed',[]):
            path=parts_dir/item['name']
            if path.exists() and _sha256(path)==item.get('sha256'):
                completed.append(item); resumed_parts+=1
    elif checkpoint.exists():
        shutil.rmtree(work); parts_dir.mkdir(parents=True,exist_ok=True)
    planner=OracleSqlPlanner(); planner.validate_query(query); planner.page_query(query,order_by,0,1)
    expected=None
    if completed: expected=tuple(completed[0].get('columns',()))
    def covered(off,limit):
        end=off+limit; spans=sorted((int(x['offset']),int(x['offset'])+int(x['limit'])) for x in completed if int(x['offset'])<end and int(x['offset'])+int(x['limit'])>off)
        cursor=off
        for low,high in spans:
            if low>cursor: return False
            cursor=max(cursor,high)
            if cursor>=end:return True
        return cursor>=end
    tasks=deque()
    for off in range(0,plan.planned_rows,plan.chunk_size):
        limit=min(plan.chunk_size,plan.planned_rows-off)
        if not covered(off,limit): tasks.append((off,limit,0))
    pending={}; started=time.perf_counter(); split_pages=0; completed_this_run=0
    def save_checkpoint(status='running'):
        _atomic_json(checkpoint,{'version':1,'status':status,'query_hash':query_hash,'planned_rows':plan.planned_rows,'chunk_size':plan.chunk_size,'order_by':order_by,'output_format':output_format,'completed':sorted(completed,key=lambda x:int(x['offset']))})
    def submit(executor,task):
        off,limit,depth=task; page=planner.page_query(query,order_by,off,limit)
        future=executor.submit(_fetch_page,connection,page,off,limit,all_varchar,output,max_retries,retry_base_seconds,retry_max_seconds); pending[future]=task
    save_checkpoint()
    try:
        with ThreadPoolExecutor(max_workers=plan.max_workers) as executor:
            while tasks or pending:
                while tasks and len(pending)<plan.max_pending_pages: submit(executor,tasks.popleft())
                done,_=wait(tuple(pending),return_when=FIRST_COMPLETED)
                for future in done:
                    off,limit,depth=pending.pop(future)
                    try: _,_,frame=future.result()
                    except Exception as error:
                        if split_failed_pages and _payload_failure(error) and limit>int(minimum_chunk_size):
                            left=max(int(minimum_chunk_size),limit//2); right=limit-left
                            if right<=0: raise
                            tasks.appendleft((off+left,right,depth+1)); tasks.appendleft((off,left,depth+1)); split_pages+=1; save_checkpoint(); continue
                        raise
                    rows=len(frame); actual=tuple(str(c) for c in frame.columns)
                    if expected is None: expected=actual
                    elif actual!=expected: raise PipelineSchemaError('Fusion page schema changed',expected_columns=expected,actual_columns=actual,offset=off,limit=limit,filename=str(output))
                    suffix='csv' if output_format=='csv' else 'parquet'; path=parts_dir/f'part-{off:012d}-{limit:08d}.{suffix}'
                    _write_part(frame,path,output_format,delimiter,encoding,include_header)
                    item={'name':path.name,'rows':rows,'offset':off,'limit':limit,'depth':depth,'columns':list(actual),'sha256':_sha256(path)}
                    completed=[x for x in completed if not (int(x['offset'])==off and int(x['limit'])==limit)]; completed.append(item); completed_this_run+=1; save_checkpoint()
                    written=sum(int(x['rows']) for x in completed)
                    if progress=='pages' or (progress=='summary' and completed_this_run%max(int(progress_interval_pages),1)==0):
                        elapsed=max(time.perf_counter()-started,.001); print(f'Parallel parts: {written:,}/{plan.planned_rows:,} rows, {len(completed)} files, {written/elapsed:,.0f} rows/second, {split_pages} splits')
        completed.sort(key=lambda item:int(item['offset'])); written=sum(int(x['rows']) for x in completed)
        if written!=plan.planned_rows: raise RuntimeError(f'Expected {plan.planned_rows:,} rows but completed parts contain {written:,} rows')
        manifest={'querysaas_version':'0.3.7','status':'complete','total_source_rows':plan.total_rows,'planned_rows':plan.planned_rows,'written_rows':written,'columns':list(expected or ()),'output_mode':'part_files','output_format':output_format,'order_by':order_by,'execution_plan':plan.to_dict(),'resumed_parts':resumed_parts,'split_pages':split_pages,'files':completed}
        manifest_path=work/'manifest.json'; manifest_path.write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8'); save_checkpoint('complete')
        publish=output.with_name(f'.{output.name}.publish')
        if publish.exists(): shutil.rmtree(publish)
        publish.mkdir(); shutil.copy2(manifest_path,publish/'manifest.json')
        for item in completed: shutil.copy2(parts_dir/item['name'],publish/item['name'])
        old=None
        if output.exists(): old=output.with_name(f'.{output.name}.old'); shutil.rmtree(old,ignore_errors=True); os.replace(output,old)
        os.replace(publish,output)
        if old is not None: shutil.rmtree(old)
        shutil.rmtree(work,ignore_errors=True)
    except Exception:
        save_checkpoint('failed')
        raise
    elapsed=max(time.perf_counter()-started,.001)
    return PartFileCopyResult(str(output),str(output/'manifest.json'),written,len(expected or ()),len(completed),output_format,elapsed,written/elapsed,plan,str(output/'manifest.json'),resumed_parts,split_pages)
