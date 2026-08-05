"""Comment-aware Oracle SQL planning for QuerySaaS."""
from __future__ import annotations
from dataclasses import asdict, dataclass, field
from typing import Any
import re
from .exceptions import MultipleStatementsError, SqlValidationError, UnsupportedStatementError

@dataclass(frozen=True)
class SqlPlan:
    original_sql: str
    executable_sql: str
    operation: str
    transformed: bool
    strategy: str
    warnings: tuple[str,...]=()
    metadata: dict[str,Any]=field(default_factory=dict)
    def to_dict(self): return asdict(self)

@dataclass(frozen=True)
class _Scan:
    masked: str
    depth: tuple[int,...]

def _scan(sql: str) -> _Scan:
    out=list(sql); depths=[0]*len(sql); i=0; depth=0; block=0
    while i<len(sql):
        depths[i]=depth
        if block:
            if sql.startswith('/*',i): block+=1; out[i:i+2]=[' ',' ']; i+=2; continue
            if sql.startswith('*/',i): block-=1; out[i:i+2]=[' ',' ']; i+=2; continue
            if sql[i] not in '\r\n': out[i]=' '
            i+=1; continue
        if sql.startswith('--',i):
            out[i:i+2]=[' ',' ']; i+=2
            while i<len(sql) and sql[i] not in '\r\n': out[i]=' '; depths[i]=depth; i+=1
            continue
        if sql.startswith('/*',i): block=1; out[i:i+2]=[' ',' ']; i+=2; continue
        if sql[i] in 'qQ' and i+2<len(sql) and sql[i+1]=="'":
            opener=sql[i+2]; closer={'[':']','(':')','{':'}','<':'>'}.get(opener,opener); j=i+3
            while j+1<len(sql) and not (sql[j]==closer and sql[j+1]=="'"): j+=1
            end=min(len(sql),j+2)
            for k in range(i,end):
                depths[k]=depth
                if sql[k] not in '\r\n': out[k]=' '
            i=end; continue
        if sql[i]=="'":
            j=i+1
            while j<len(sql):
                if sql[j]=="'":
                    if j+1<len(sql) and sql[j+1]=="'": j+=2; continue
                    j+=1; break
                j+=1
            for k in range(i,j):
                depths[k]=depth
                if sql[k] not in '\r\n': out[k]=' '
            i=j; continue
        if sql[i]=='"':
            j=i+1
            while j<len(sql):
                if sql[j]=='"':
                    if j+1<len(sql) and sql[j+1]=='"': j+=2; continue
                    j+=1; break
                j+=1
            for k in range(i,j):
                depths[k]=depth
                if sql[k] not in '\r\n': out[k]=' '
            i=j; continue
        if sql[i]=='(': depth+=1
        elif sql[i]==')': depth=max(0,depth-1)
        depths[i]=depth; i+=1
    if block: raise SqlValidationError('Unterminated block comment.')
    return _Scan(''.join(out),tuple(depths))

def _trim_semicolon(sql):
    s=_scan(sql); indices=[i for i,c in enumerate(s.masked) if not c.isspace()]
    if not indices: raise SqlValidationError('SQL cannot be empty.')
    last=indices[-1]
    if s.masked[last]==';': return sql[:last]+sql[last+1:]
    return sql

def _top_tokens(sql):
    s=_scan(sql); return [(m.group(0).upper(),m.start(),m.end()) for m in re.finditer(r'[A-Za-z_][A-Za-z0-9_$#]*|;',s.masked) if s.depth[m.start()]==0]

def _outer_order_pos(sql):
    toks=_top_tokens(sql)
    for idx in range(len(toks)-2,-1,-1):
        if toks[idx][0]=='ORDER' and toks[idx+1][0]=='BY': return toks[idx][1]
    return None

def _outer_limited(sql):
    s=_scan(sql); top=''.join(c if s.depth[i]==0 else ' ' for i,c in enumerate(s.masked))
    return bool(re.search(r'\bROWNUM\s*(?:<=|<|=)\s*\d+',top,re.I) or re.search(r'\bFETCH\s+(?:FIRST|NEXT)\s+\d+\s+ROWS?\s+ONLY\b',top,re.I))

class OracleSqlPlanner:
    def validate_query(self, sql):
        if not isinstance(sql,str) or not sql.strip(): raise SqlValidationError('SQL cannot be empty.')
        cleaned=_trim_semicolon(sql); toks=_top_tokens(cleaned)
        semis=[t for t in toks if t[0]==';']
        if semis: raise MultipleStatementsError('Multiple executable SQL statements are not supported.')
        words=[t[0] for t in toks]
        if not words or words[0] not in {'SELECT','WITH'}: raise UnsupportedStatementError('Only SELECT and WITH statements are supported.')
        if words[-1] in {'WHERE','AND','OR','BY','FROM','JOIN','ON','GROUP','ORDER','HAVING','UNION','OFFSET','FETCH'}: raise SqlValidationError(f'Incomplete SQL clause ending in {words[-1]}.')
        return SqlPlan(sql,cleaned,'validate',cleaned!=sql,'unchanged',metadata={'statement':words[0]})
    def count_query(self, sql):
        valid=self.validate_query(sql); source=valid.executable_sql.rstrip(); pos=_outer_order_pos(source); warnings=()
        if pos is not None:
            source=source[:pos].rstrip(); warnings=('Removed outermost ORDER BY for count wrapper.',)
        executable='SELECT COUNT(*) AS ROW_COUNT\nFROM (\n'+source+'\n) querysaas_count_source'
        return SqlPlan(sql,executable,'count',True,'oracle_count_wrapper',warnings,{'removed_outer_order_by':pos is not None})
    def limit_query(self, sql, max_rows):
        if isinstance(max_rows,bool) or not isinstance(max_rows,int) or max_rows<=0: raise ValueError('max_rows must be a positive integer.')
        valid=self.validate_query(sql); source=valid.executable_sql.rstrip()
        if _outer_limited(source): return SqlPlan(sql,source,'limit',False,'already_limited',metadata={'max_rows':max_rows})
        simple=bool(re.fullmatch(r'\s*SELECT\s+\*\s+FROM\s+[A-Za-z_][A-Za-z0-9_.$#]*(?:\s+[A-Za-z_][A-Za-z0-9_$#]*)?\s*',_scan(source).masked,re.I))
        if simple: executable=source+'\nWHERE ROWNUM <= '+str(max_rows); strategy='oracle_simple_rownum'
        else: executable='SELECT *\nFROM (\n'+source+'\n) querysaas_limited\nWHERE ROWNUM <= '+str(max_rows); strategy='oracle_wrapper_rownum'
        return SqlPlan(sql,executable,'limit',True,strategy,metadata={'max_rows':max_rows})
    def page_query(self, sql, order_by, offset, limit):
        if isinstance(offset,bool) or not isinstance(offset,int) or offset<0: raise ValueError('offset must be an integer zero or greater.')
        if isinstance(limit,bool) or not isinstance(limit,int) or limit<=0: raise ValueError('limit must be a positive integer.')
        if not isinstance(order_by,str) or not order_by.strip(): raise ValueError('order_by is required for deterministic paging.')
        valid=self.validate_query(sql); source=valid.executable_sql.rstrip()
        executable='SELECT *\nFROM (\n'+source+'\n) querysaas_page\nORDER BY '+order_by.strip()+f'\nOFFSET {offset} ROWS\nFETCH NEXT {limit} ROWS ONLY'
        return SqlPlan(sql,executable,'page',True,'oracle_offset_fetch',metadata={'order_by':order_by.strip(),'offset':offset,'limit':limit})

_default=OracleSqlPlanner()
def validate_query(sql): return _default.validate_query(sql)
def count_query(sql): return _default.count_query(sql)
def limit_query(sql,max_rows): return _default.limit_query(sql,max_rows)
def page_query(sql,order_by,offset,limit): return _default.page_query(sql,order_by,offset,limit)
