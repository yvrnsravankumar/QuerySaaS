import time
import pandas as pd
from querysaas.pipeline import copy_fusion_to_local_parallel
class Fake:
    def executequery(self,sql,all_varchar=True):
        off=int(sql.split('OFFSET ')[1].split(' ')[0]); lim=int(sql.split('FETCH NEXT ')[1].split(' ')[0]); time.sleep(0.02 if off==0 else 0)
        vals=list(range(off,min(off+lim,5))); return pd.DataFrame({'ID':vals,'TEXT':['A|B' for _ in vals]})
def test_order_header_quote(tmp_path):
    p=tmp_path/'x.txt'; r=copy_fusion_to_local_parallel(Fake(),'SELECT * FROM t',p,'ID',delimiter='|',chunk_size=2,max_workers=3,max_rows=5)
    lines=p.read_text(encoding='utf-8-sig').splitlines(); assert lines[0]=='ID|TEXT' and sum(x=='ID|TEXT' for x in lines)==1 and '"A|B"' in lines[1]; assert r.rows==5
