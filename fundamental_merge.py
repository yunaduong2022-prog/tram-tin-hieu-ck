"""Merge dated fundamental snapshots conservatively; no per-field period mixing."""
import pandas as pd
from fund_guard import sanitize, METRICS

KEY='Mã'; DATE='Cập nhật'; NAME='Tên công ty'
def read(path):
    d=pd.read_csv(path,encoding='utf-8-sig',dtype=str,keep_default_na=False)
    if not {KEY,DATE,NAME,*METRICS}.issubset(d): raise ValueError('FUND_SCHEMA_INVALID')
    d[KEY]=d[KEY].str.strip().str.upper()
    if d[KEY].eq('').any() or d[KEY].duplicated().any(): raise ValueError('FUND_KEYS_INVALID')
    d,w=sanitize(d)
    for x in w: print('FUND_GUARD:',x)
    return d.set_index(KEY)

def merge(local, remote):
    a,b=read(local),read(remote)
    if set(a.columns)!=set(b.columns): raise ValueError('FUND_SCHEMA_MISMATCH')
    def stamp(r):
        d=pd.to_datetime(r[DATE],format='%d/%m/%Y',errors='coerce')
        if pd.notna(d) and d>pd.Timestamp.now(tz='Asia/Ho_Chi_Minh').tz_localize(None).normalize():
            raise ValueError('FUND_FUTURE_DATE')
        return d
    def available(r): return {m for m in METRICS if pd.notna(r[m])}
    out=[]
    for k in sorted(set(a.index)|set(b.index)):
        if k not in a.index: r=b.loc[k].copy(); stamp(r)
        elif k not in b.index: r=a.loc[k].copy(); stamp(r)
        else:
            x,y=a.loc[k],b.loc[k]; dx,dy=stamp(x),stamp(y); ax,ay=available(x),available(y)
            # Retain remote valid fields; prefer newer local rows only when they
            # cover existing metrics. An empty remote snapshot can be repaired
            # from a dated local row. Never blend metrics across reporting dates.
            if not ay and ax and pd.notna(dx): r=x.copy()
            elif not ax and ay: r=y.copy()
            elif pd.notna(dx) and (pd.isna(dy) or dx>dy):
                if ax.issuperset(ay): r=x.copy()
                else:
                    print('FUND_NEWER_PARTIAL_REVIEW:',k); r=y.copy()
            elif pd.notna(dy) and (pd.isna(dx) or dy>dx): r=y.copy()
            else:
                conflicts=[m for m in ax&ay if abs(float(x[m])-float(y[m]))>1e-9]
                if conflicts:
                    print('FUND_EQUAL_OR_UNKNOWN_DATE_CONFLICT:',k,','.join(sorted(conflicts))); r=y.copy()
                elif ax>ay and pd.notna(dx): r=x.copy()
                else: r=y.copy()
            if not str(r[NAME]).strip(): r[NAME]=x[NAME] or y[NAME]
        r[KEY]=k;out.append(r)
    result=pd.DataFrame(out).set_index(KEY).reset_index()
    result,_=sanitize(result)
    return result[[KEY,*a.columns]]
