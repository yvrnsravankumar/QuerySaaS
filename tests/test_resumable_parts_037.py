import json
import pandas as pd
from querysaas.parallel_parts import copy_fusion_query_to_parts, plan_parallel_execution

class Count:
    def __init__(self,n): self.row_count=n
class Fake:
    def __init__(self,n,fail_once=False): self.n=n; self.fail_once=fail_once; self.failed=False
    def countquery(self,q): return Count(self.n)
    def executequery(self,sql,all_varchar=True,**kwargs):
        off=int(sql.split('OFFSET ')[1].split()[0]); lim=int(sql.split('FETCH NEXT ')[1].split()[0])
        if self.fail_once and not self.failed and lim>=8:
            self.failed=True; raise RuntimeError('Oracle Fusion returned invalid SOAP XML. ParseError: no element found')
        return pd.DataFrame({'ID':list(range(off,min(off+lim,self.n)))})

def test_default_plan_uses_benchmark_profile():
    plan=plan_parallel_execution(Fake(200000),'SELECT ID FROM T')
    assert plan.chunk_size==10000 and plan.max_workers==16 and plan.max_pending_pages==20

def test_failed_payload_page_is_split(tmp_path):
    out=tmp_path/'parts'
    result=copy_fusion_query_to_parts(Fake(20,True),'SELECT ID FROM T',out,'ID',mode='parallel',chunk_size=10,max_workers=2,max_pending_pages=4,minimum_chunk_size=2,progress='none')
    assert result.rows==20 and result.split_pages==1
    manifest=json.loads((out/'manifest.json').read_text())
    assert manifest['split_pages']==1 and sum(x['rows'] for x in manifest['files'])==20

def test_checkpoint_is_retained_after_failure(tmp_path):
    class AlwaysFails(Fake):
        def executequery(self,sql,all_varchar=True,**kwargs): raise RuntimeError('permanent failure')
    out=tmp_path/'failed'
    try: copy_fusion_query_to_parts(AlwaysFails(5),'SELECT ID FROM T',out,'ID',mode='parallel',chunk_size=5,max_workers=1,max_pending_pages=1,progress='none')
    except Exception: pass
    assert (tmp_path/'.failed.querysaas-work'/'checkpoint.json').exists()
