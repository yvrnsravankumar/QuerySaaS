from querysaas.fusion_api import copy_fusion_table_to_duckdb, sync_fusion_query_to_duckdb
class Count:
    def __init__(self,n): self.row_count=n
class Fake:
    _validate_identifier=staticmethod(lambda value,label='identifier':str(value))
    def __init__(self,n=100): self.n=n; self.calls=[]
    def countquery(self,q): return Count(self.n)
    def syncquery2dd(self,**kwargs): self.calls.append(('sequential',kwargs)); return {'processed_rows':self.n,'source_rows':self.n}
    def syncquery2dd_parallel(self,**kwargs): self.calls.append(('parallel',kwargs)); return {'processed_rows':self.n,'source_rows':self.n}
def test_query_sync_defaults_order_to_primary_key():
    f=Fake(6000); r=sync_fusion_query_to_duckdb(f,'SELECT ID FROM T','local_t',primary_key='ID',quiet=True)
    assert f.calls[0][0]=='parallel' and f.calls[0][1]['order_by']=='ID'
    assert r['actual_runtime_seconds']>0 and r['rows_per_second']>0
def test_table_target_name_and_rowid_fallback():
    f=Fake(6000); r=copy_fusion_table_to_duckdb(f,'SOURCE_T',target_table='LOCAL_T',quiet=True)
    call=f.calls[0][1]
    assert call['target_table']=='LOCAL_T'
    assert call['primary_key']=='SOURCE_ROWID' and call['order_by']=='SOURCE_ROWID'
    assert 'ROWIDTOCHAR(querysaas_source.ROWID)' in call['query']
def test_table_target_defaults_to_source():
    f=Fake(10); copy_fusion_table_to_duckdb(f,'SOURCE_T',primary_key='ID',quiet=True)
    assert f.calls[0][1]['target_table']=='SOURCE_T'

class ScalarFake(Fake):
    def syncquery2dd_parallel(self,**kwargs):
        self.calls.append(("parallel",kwargs))
        return "parallel-sync"

def test_existing_scalar_return_contract_is_preserved():
    fake=ScalarFake(6000)
    result=sync_fusion_query_to_duckdb(fake,"SELECT ID FROM T","local_t",primary_key="ID",quiet=True)
    assert result=="parallel-sync"
