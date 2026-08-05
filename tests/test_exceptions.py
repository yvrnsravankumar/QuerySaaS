from querysaas.exceptions import PipelineSchemaError, OracleSqlError
def test_fields():
    e=PipelineSchemaError('x',expected_columns=['A'],actual_columns=['B'],offset=1,limit=2,filename='x.csv'); assert e.offset==1
def test_oracle(): assert 'ORA-00942' in str(OracleSqlError('x',oracle_code='ORA-00942',oracle_message='missing'))
