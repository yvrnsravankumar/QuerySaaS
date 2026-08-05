import pandas as pd
from querysaas.oracle_fusion import FusionConnection

def test_countquery(monkeypatch):
    c=object.__new__(FusionConnection); c.closed=False
    monkeypatch.setattr(c,'executequery',lambda sql,all_varchar=True: pd.DataFrame({'ROW_COUNT':['7']}))
    r=c.countquery('SELECT * FROM dual -- comment')
    assert r.row_count==7 and '\n) querysaas_count_source' in r.generated_sql
