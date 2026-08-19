import json
import pandas as pd
from querysaas.parallel_parts import plan_parallel_execution, copy_fusion_query_to_parts
class Count:
    def __init__(self,n): self.row_count=n
class Fake:
    def __init__(self,n): self.n=n
    def countquery(self,q): return Count(self.n)
    def executequery(self,sql,all_varchar=True,**kwargs):
        off=int(sql.split('OFFSET ')[1].split()[0]); lim=int(sql.split('FETCH NEXT ')[1].split()[0])
        return pd.DataFrame({'ID':list(range(off,min(off+lim,self.n)))})
def test_auto_plan():
    p=plan_parallel_execution(Fake(600000),'SELECT ID FROM T')
    assert p.chunk_size==10000 and p.total_chunks==60 and p.max_workers==16 and p.max_pending_pages==32
def test_max_rows_and_small_plan():
    p=plan_parallel_execution(Fake(1000000),'SELECT ID FROM T',max_rows=10000)
    assert p.planned_rows==10000 and p.chunk_size==10000 and p.total_chunks==1 and p.max_workers==1
def test_csv_parts_manifest(tmp_path):
    out=tmp_path/'parts'
    r=copy_fusion_query_to_parts(Fake(9),'SELECT ID FROM T',out,'ID',mode='parallel',chunk_size=2,max_workers=2,max_pending_pages=4,output_format='csv',progress='none')
    assert r.rows==9 and r.part_count==5
    data=json.loads((out/'manifest.json').read_text())
    assert data['written_rows']==9 and len(data['files'])==5
    assert all((out/x['name']).exists() and x['sha256'] for x in data['files'])
def test_parquet_parts(tmp_path):
    out=tmp_path/'pq'
    r=copy_fusion_query_to_parts(Fake(5),'SELECT ID FROM T',out,'ID',mode='parallel',chunk_size=2,max_workers=2,output_format='parquet',progress='none')
    assert r.part_count==3 and len(list(out.glob('*.parquet')))==3
