import pytest
from querysaas import OracleSqlPlanner, SqlValidationError
p=OracleSqlPlanner()
@pytest.mark.parametrize('sql',['', '   '])
def test_empty(sql):
    with pytest.raises(SqlValidationError): p.validate_query(sql)
def test_comments_quotes_qquotes():
    p.validate_query("SELECT q'[; -- /* x */]' x FROM dual -- ;\n")
def test_multiple():
    with pytest.raises(SqlValidationError): p.validate_query('SELECT 1 FROM dual; SELECT 2 FROM dual')
def test_count_comment_newline():
    x=p.count_query("SELECT * FROM dual\n-- WHERE X=1")
    assert '\n) querysaas_count_source' in x.executable_sql
def test_limit_ignores_comment(): assert p.limit_query('SELECT * FROM dual -- ROWNUM <= 5',10).transformed
def test_limit_active(): assert p.limit_query('SELECT * FROM dual WHERE ROWNUM <= 5',10).strategy=='already_limited'
def test_page():
    x=p.page_query('SELECT * FROM dual','A, B',5,10); assert 'OFFSET 5 ROWS' in x.executable_sql and 'ORDER BY A, B' in x.executable_sql
