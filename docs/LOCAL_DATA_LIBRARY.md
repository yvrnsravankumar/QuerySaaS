# Local Data Library

Query CSV, TSV, and Parquet files by filename without the extension.

```python
from querysaas import open_data_library
with open_data_library(r"C:\\Data") as db:
    print(db.query('SELECT * FROM "Sales Data"'))
    print(db.query("SELECT * FROM sales_data"))
```

Each file receives an exact quoted alias and a normalized alias. `Sales Data.csv` is available as `"Sales Data"` and `sales_data`. File-backed aliases are read-only. Use `materialize()` to create a managed DuckDB table before INSERT, UPDATE, DELETE, or MERGE. Exports support CSV, TSV, and Parquet.
