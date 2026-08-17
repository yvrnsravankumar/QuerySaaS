from pathlib import Path
import pandas as pd
import pytest
from querysaas import open_data_library
from querysaas.exceptions import LocalDataReadOnlyError

def test_filename_aliases_query_dml_and_export(tmp_path):
    pd.DataFrame({"id":[1,2],"amount":[10,20]}).to_csv(tmp_path/"Sales Data.csv",index=False)
    pd.DataFrame({"id":[1,2],"name":["A","B"]}).to_csv(tmp_path/"Customers.tsv",sep="\t",index=False)
    pd.DataFrame({"id":[1,2],"status":["N","Y"]}).to_parquet(tmp_path/"Orders.parquet",index=False)
    with open_data_library(tmp_path,database=tmp_path/"library.duckdb") as db:
        assert len(db.query('SELECT * FROM "Sales Data"'))==2
        assert len(db.query('SELECT * FROM sales_data'))==2
        assert len(db.query('SELECT * FROM customers'))==2
        assert len(db.query('SELECT * FROM orders'))==2
        with pytest.raises(LocalDataReadOnlyError): db.execute('UPDATE "Sales Data" SET amount=0')
        with pytest.raises(LocalDataReadOnlyError): db.execute('DELETE FROM "Sales Data" WHERE id=1')
        with pytest.raises(LocalDataReadOnlyError): db.execute('INSERT INTO "Sales Data" SELECT * FROM sales_data')
        with pytest.raises(LocalDataReadOnlyError): db.execute('DROP TABLE "Sales Data"')
        assert db.materialize("Sales Data",as_table="managed_sales")=="managed_sales"
        result=db.execute("UPDATE managed_sales SET amount=amount+1 WHERE id=?",[1])
        assert result.transaction_committed is True
        assert db.query("SELECT amount FROM managed_sales WHERE id=1").iloc[0,0]==11
        out=db.export_parquet("managed_sales",tmp_path/"out.parquet")
        assert Path(out).exists()

def test_subfolder_duplicate_names(tmp_path):
    (tmp_path/"North").mkdir(); (tmp_path/"South").mkdir()
    pd.DataFrame({"x":[1]}).to_csv(tmp_path/"North"/"Sales Data.csv",index=False)
    pd.DataFrame({"x":[2]}).to_csv(tmp_path/"South"/"Sales Data.csv",index=False)
    with open_data_library(tmp_path,database=":memory:") as db:
        assert db.query('SELECT * FROM "North/Sales Data"').iloc[0,0]==1
        assert db.query("SELECT * FROM south_sales_data").iloc[0,0]==2
