"""Folder-based CSV, TSV, and Parquet SQL library powered by DuckDB."""
from __future__ import annotations
import re, time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
import duckdb
import pandas as pd
from .exceptions import (LocalDataError, LocalDataFileError, LocalDataFolderError,
    LocalDataReadOnlyError, LocalDataSqlError, LocalDataTableNameError)

_SUPPORTED={".csv":"csv",".tsv":"tsv",".parquet":"parquet"}
_RESERVED={"all","alter","and","as","by","case","create","delete","describe","drop","from","group","having","insert","into","join","limit","merge","not","null","on","or","order","select","set","show","table","update","where","with"}
_DML={"INSERT","UPDATE","DELETE","MERGE","ALTER","DROP","TRUNCATE"}
_BLOCKED={"INSTALL","LOAD","ATTACH","DETACH","IMPORT","EXPORT","PRAGMA"}

def _quote(value): return '"'+str(value).replace('"','""')+'"'
def _literal(value): return "'"+str(value).replace("'","''")+"'"
def _safe_name(value):
    name=re.sub(r"[^0-9A-Za-z_]+","_",str(value)).strip("_").lower()
    name=re.sub(r"_+","_",name) or "file"
    if name[0].isdigit(): name="t_"+name
    if name in _RESERVED: name="file_"+name
    return name

def _first_keyword(sql):
    text=re.sub(r"(?s)/\*.*?\*/|--[^\r\n]*"," ",str(sql)).strip()
    m=re.match(r"([A-Za-z]+)",text)
    return m.group(1).upper() if m else ""

def _dml_targets(sql):
    """Return DML target identifiers, preserving spaces in quoted names."""
    text=re.sub(r"(?s)/\*.*?\*/|--[^\r\n]*"," ",str(sql)).strip()
    patterns=(
        r'(?is)^\s*UPDATE\s+(?P<name>"(?:""|[^"])+"|[^\s;(]+)',
        r'(?is)^\s*INSERT\s+INTO\s+(?P<name>"(?:""|[^"])+"|[^\s;(]+)',
        r'(?is)^\s*DELETE\s+FROM\s+(?P<name>"(?:""|[^"])+"|[^\s;(]+)',
        r'(?is)^\s*MERGE\s+INTO\s+(?P<name>"(?:""|[^"])+"|[^\s;(]+)',
        r'(?is)^\s*(?:ALTER|DROP|TRUNCATE)\s+TABLE\s+(?:IF\s+EXISTS\s+)?(?P<name>"(?:""|[^"])+"|[^\s;(]+)',
    )
    targets=[]
    for pattern in patterns:
        match=re.match(pattern,text)
        if not match:
            continue
        name=match.group("name")
        if name.startswith('"') and name.endswith('"'):
            name=name[1:-1].replace('""','"')
        targets.append(name)
        break
    return targets

@dataclass(frozen=True)
class LocalDataFile:
    table_name:str; exact_name:str; relative_path:str; absolute_path:str
    file_type:str; size_bytes:int; readable:bool; error:str|None=None
    def to_dict(self): return self.__dict__.copy()

@dataclass(frozen=True)
class LocalSqlResult:
    statement_type:str; dataframe:Any=None; rows_affected:int|None=None
    duration_ms:float=0.0; transaction_committed:bool=False
    def to_dict(self):
        return {"statement_type":self.statement_type,"rows_affected":self.rows_affected,
                "duration_ms":self.duration_ms,"transaction_committed":self.transaction_committed}

class LocalDataLibrary:
    """Register local data files as DuckDB views using filename aliases."""
    def __init__(self, folder, database=None, *, recursive=True, read_only=False):
        self.folder=Path(folder).expanduser().resolve()
        if not self.folder.is_dir(): raise LocalDataFolderError(f"Local data folder does not exist: {self.folder}")
        self.recursive=bool(recursive); self.read_only=bool(read_only)
        if database is None: database=self.folder/"querysaas.duckdb"
        self.database=Path(database).expanduser().resolve() if str(database) != ":memory:" else Path(":memory:")
        self.connection=duckdb.connect(str(database), read_only=self.read_only)
        self._files=[]; self._file_backed=set(); self.refresh()
    def __enter__(self): return self
    def __exit__(self,*args): self.close()
    def close(self):
        if self.connection is not None: self.connection.close(); self.connection=None
    def _discover(self):
        iterator=self.folder.rglob("*") if self.recursive else self.folder.glob("*")
        db=self.database.resolve() if str(self.database) != ":memory:" else None
        return [p for p in iterator if p.is_file() and p.suffix.lower() in _SUPPORTED and (db is None or p.resolve()!=db)]
    def refresh(self):
        files=sorted(self._discover(),key=lambda p:str(p.relative_to(self.folder)).casefold())
        stems={}
        for p in files: stems.setdefault(p.stem.casefold(),[]).append(p)
        used=set(); records=[]; self._file_backed=set()
        for p in files:
            rel=p.relative_to(self.folder).as_posix(); exact=p.stem
            exact_alias=exact if len(stems[p.stem.casefold()])==1 else str(Path(rel).with_suffix("")).replace("\\","/")
            safe=_safe_name(exact if len(stems[p.stem.casefold()])==1 else Path(rel).with_suffix("").as_posix())
            base=safe; n=2
            while safe.casefold() in used: safe=f"{base}_{n}"; n+=1
            used.add(safe.casefold())
            reader=(f"read_parquet({_literal(str(p))})" if p.suffix.lower()==".parquet" else
                    f"read_csv_auto({_literal(str(p))}, header=true" + (", delim='\\t'" if p.suffix.lower()==".tsv" else "") + ")")
            try:
                self.connection.execute(f"CREATE OR REPLACE VIEW {_quote(safe)} AS SELECT * FROM {reader}")
                if exact_alias.casefold()!=safe.casefold():
                    self.connection.execute(f"CREATE OR REPLACE VIEW {_quote(exact_alias)} AS SELECT * FROM {_quote(safe)}")
                records.append(LocalDataFile(safe,exact_alias,rel,str(p),_SUPPORTED[p.suffix.lower()],p.stat().st_size,True,None))
                self._file_backed.update({safe.casefold(),exact_alias.casefold()})
            except Exception as exc:
                records.append(LocalDataFile(safe,exact_alias,rel,str(p),_SUPPORTED[p.suffix.lower()],p.stat().st_size,False,str(exc)))
        self._files=records
        self.connection.execute("CREATE OR REPLACE TEMP TABLE querysaas_files(table_name VARCHAR, exact_name VARCHAR, relative_path VARCHAR, absolute_path VARCHAR, file_type VARCHAR, size_bytes BIGINT, readable BOOLEAN, error VARCHAR)")
        if records:
            self.connection.executemany("INSERT INTO querysaas_files VALUES (?,?,?,?,?,?,?,?)",[(r.table_name,r.exact_name,r.relative_path,r.absolute_path,r.file_type,r.size_bytes,r.readable,r.error) for r in records])
        return self.list_files()
    def list_files(self): return pd.DataFrame([x.to_dict() for x in self._files])
    files=list_files
    def list_tables(self): return self.connection.execute("SHOW TABLES").fetchdf()
    tables=list_tables
    def describe_table(self,name): return self.connection.execute(f"DESCRIBE {_quote(name)}").fetchdf()
    def preview(self,name,limit=100):
        if not isinstance(limit,int) or limit<1: raise ValueError("limit must be a positive integer")
        return self.connection.execute(f"SELECT * FROM {_quote(name)} LIMIT ?",[limit]).fetchdf()
    def count(self,name): return int(self.connection.execute(f"SELECT COUNT(*) FROM {_quote(name)}").fetchone()[0])
    def query(self,sql,parameters=None):
        keyword=_first_keyword(sql)
        if keyword not in {"SELECT","WITH","SHOW","DESCRIBE","EXPLAIN","SUMMARIZE"}: raise LocalDataSqlError("query() accepts read-only SQL; use execute() for managed-table DDL or DML.")
        try: return self.connection.execute(sql,parameters or []).fetchdf()
        except Exception as exc: raise LocalDataSqlError(str(exc)) from exc
    def _guard(self,sql):
        keyword=_first_keyword(sql)
        if keyword in _BLOCKED: raise LocalDataSqlError(f"Administrative statement is disabled: {keyword}")
        if self.read_only and keyword not in {"SELECT","WITH","SHOW","DESCRIBE","EXPLAIN","SUMMARIZE"}: raise LocalDataReadOnlyError("The local data library is open in read-only mode.")
        if keyword in _DML:
            for target in _dml_targets(sql):
                if target.casefold() in self._file_backed:
                    raise LocalDataReadOnlyError(
                        f"'{target}' is file-backed. Materialize it before DML."
                    )
        return keyword
    def execute(self,sql,parameters=None):
        keyword=self._guard(sql); started=time.perf_counter()
        try:
            self.connection.execute("BEGIN")
            cursor=self.connection.execute(sql,parameters or [])
            frame=cursor.fetchdf() if cursor.description else None
            self.connection.execute("COMMIT")
            return LocalSqlResult(keyword,frame,None,(time.perf_counter()-started)*1000,True)
        except Exception as exc:
            try:self.connection.execute("ROLLBACK")
            except Exception:pass
            if isinstance(exc,LocalDataError): raise
            raise LocalDataSqlError(str(exc)) from exc
    def materialize(self,source,as_table=None,*,replace=False):
        target=as_table or f"managed_{_safe_name(source)}"
        if target.casefold() in self._file_backed: raise LocalDataTableNameError("Managed table name conflicts with a file-backed alias.")
        clause="CREATE OR REPLACE TABLE" if replace else "CREATE TABLE"
        self.connection.execute(f"{clause} {_quote(target)} AS SELECT * FROM {_quote(source)}")
        return target
    def export(self,source,output_file,*,format=None,compression="zstd"):
        target=Path(output_file).expanduser().resolve(); target.parent.mkdir(parents=True,exist_ok=True)
        fmt=(format or target.suffix.lstrip(".")).lower()
        if fmt not in {"csv","tsv","parquet"}: raise LocalDataFileError("Export format must be csv, tsv, or parquet.")
        source_sql=source if re.match(r"(?is)^\s*(SELECT|WITH)\b",str(source)) else f"SELECT * FROM {_quote(source)}"
        if fmt=="parquet": options=f"FORMAT PARQUET, COMPRESSION {_quote(compression)}"
        elif fmt=="tsv": options="FORMAT CSV, HEADER, DELIMITER '\\t'"
        else: options="FORMAT CSV, HEADER"
        self.connection.execute(f"COPY ({source_sql}) TO {_literal(str(target))} ({options})")
        return str(target)
    def export_csv(self,source,output_file): return self.export(source,output_file,format="csv")
    def export_tsv(self,source,output_file): return self.export(source,output_file,format="tsv")
    def export_parquet(self,source,output_file,compression="zstd"): return self.export(source,output_file,format="parquet",compression=compression)

def open_data_library(folder,database=None,*,recursive=True,read_only=False):
    return LocalDataLibrary(folder,database,recursive=recursive,read_only=read_only)
