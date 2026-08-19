import inspect
import time
import pandas as pd
import pytest
from querysaas.pipeline import copy_fusion_to_local_parallel

class Fake:
    def __init__(self, fail_once=None):
        self.fail_once=fail_once; self.attempts={}; self.kwargs=[]
    def executequery(self,sql,all_varchar=True,**kwargs):
        off=int(sql.split('OFFSET ')[1].split(' ')[0]); lim=int(sql.split('FETCH NEXT ')[1].split(' ')[0])
        self.kwargs.append(kwargs); self.attempts[off]=self.attempts.get(off,0)+1
        if off==self.fail_once and self.attempts[off]==1: raise ConnectionError('temporary page failure')
        time.sleep(0.01 if off==0 else 0)
        values=list(range(off,min(off+lim,9)))
        return pd.DataFrame({'ID':values})

def test_bounded_ordered_page_engine(tmp_path):
    output=tmp_path/'bounded.csv'; connection=Fake()
    result=copy_fusion_to_local_parallel(connection,'SELECT ID FROM T',output,'ID',chunk_size=2,max_workers=2,max_pending_pages=4,max_rows=9)
    frame=pd.read_csv(output)
    assert frame.ID.tolist()==list(range(9))
    assert result.rows==9 and result.peak_pending<=4 and result.pages_submitted==5
    assert result.retry_scope=='page' and result.rows_per_second>0

def test_retry_parameters_are_forwarded_to_each_page(tmp_path):
    connection=Fake(); output=tmp_path/'retry.csv'
    copy_fusion_to_local_parallel(connection,'SELECT ID FROM T',output,'ID',chunk_size=3,max_workers=2,max_rows=6,max_retries=7,retry_base_seconds=2.0,retry_max_seconds=9.0)
    assert connection.kwargs
    assert all(item=={'max_retries':7,'retry_base_seconds':2.0,'retry_max_seconds':9.0} for item in connection.kwargs)

def test_existing_destination_is_preserved_on_page_failure(tmp_path):
    output=tmp_path/'existing.csv'; output.write_text('ORIGINAL',encoding='utf-8')
    with pytest.raises(Exception):
        copy_fusion_to_local_parallel(Fake(fail_once=2),'SELECT ID FROM T',output,'ID',chunk_size=2,max_workers=2,max_rows=8,max_retries=0)
    assert output.read_text(encoding='utf-8')=='ORIGINAL'

def test_signature_has_phase1_controls():
    signature=inspect.signature(copy_fusion_to_local_parallel)
    assert signature.parameters['max_pending_pages'].default is None
    assert signature.parameters['progress'].default=='none'
    assert signature.parameters['max_retries'].default==3


def test_connection_without_retry_keywords_remains_compatible(tmp_path):
    class LegacyFake:
        def executequery(self,sql,all_varchar=True):
            off=int(sql.split('OFFSET ')[1].split(' ')[0]); lim=int(sql.split('FETCH NEXT ')[1].split(' ')[0])
            return pd.DataFrame({'ID':list(range(off,min(off+lim,3)))})
    output=tmp_path/'legacy.csv'
    result=copy_fusion_to_local_parallel(LegacyFake(),'SELECT ID FROM T',output,'ID',chunk_size=2,max_workers=2,max_rows=3)
    assert result.rows==3
