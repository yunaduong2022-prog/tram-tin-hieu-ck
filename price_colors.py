"""Display-only Vietnamese equity colors. Prices are in thousands of VND.
Daily official limits are date-keyed; no inference from a rounded return.
"""
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_FLOOR, ROUND_CEILING
from functools import lru_cache
from pathlib import Path
import csv
import math

COLORS = {'ceiling':'#D946EF','up':'#089981','flat':'#EAB308','down':'#F23645','floor':'#22D3EE','unknown':'#8B95A5'}
LABELS = {'ceiling':'Trần','up':'Tăng','flat':'Tham chiếu','down':'Giảm','floor':'Sàn','unknown':'Chưa đủ dữ liệu'}
PATH = Path(__file__).resolve().parent / 'data' / 'price_limits_daily.csv'
_CTX = ContextVar('price_color_session', default=('', {}))

def number(v):
    try:
        x=float(v)
        return x if math.isfinite(x) else None
    except (TypeError,ValueError,OverflowError): return None

def day_key(v):
    if isinstance(v,(datetime,date)): return v.isoformat()[:10]
    try: return date.fromisoformat(str(v)[:10]).isoformat()
    except (TypeError,ValueError):
        try: return datetime.strptime(str(v).strip()[:10], '%d/%m/%Y').date().isoformat()
        except (TypeError,ValueError): return ''

def exchange(v):
    x=str(v).upper().strip()
    return 'HOSE' if x in ('HOSE','HSX') else x if x in ('HNX','UPCOM') else ''

def _decimal(v):
    return Decimal(str(v))

def tick(v,ex):
    x=_decimal(v)
    if ex!='HOSE': return Decimal('.1')
    return Decimal('.01') if x<10 else Decimal('.05') if x<50 else Decimal('.1')

def ordinary_limits(reference,ex):
    """Normal-session calculation for diagnostics only. Do not use as verified limits."""
    ex=exchange(ex); ref=_decimal(reference)
    if not ex or not ref.is_finite() or ref<=0: raise ValueError('invalid reference')
    rate={'HOSE':Decimal('.07'),'HNX':Decimal('.1'),'UPCOM':Decimal('.15')}[ex]
    a,b=ref*(1+rate),ref*(1-rate)
    ta,tb=tick(a,ex),tick(b,ex)
    hi=(a/ta).to_integral_value(rounding=ROUND_FLOOR)*ta
    lo=(b/tb).to_integral_value(rounding=ROUND_CEILING)*tb
    if hi<=ref: hi=ref+tick(ref,ex)
    if lo>=ref: lo=max(tick(ref,ex),ref-tick(ref,ex))
    return float(hi),float(lo)

def valid_row(row):
    d=day_key(row.get('trading_date')); s=str(row.get('symbol','')).strip().upper(); ex=exchange(row.get('exchange'))
    ref,hi,lo=(number(row.get(k)) for k in ('reference_price','ceiling_price','floor_price'))
    if not d or len(s)!=3 or not s.isalnum() or not ex or any(x is None for x in (ref,hi,lo)): return None
    if not 0<lo<=ref<=hi or hi==lo or hi/ref>1.51 or lo/ref<.49: return None
    # Exact tick-grid validation. No rounding adjusted OHLC onto a tick.
    if any(abs(float(_decimal(x)/tick(x,ex))-round(float(_decimal(x)/tick(x,ex))))>1e-6 for x in (ref,hi,lo)): return None
    return d,s,ex,ref,hi,lo

@lru_cache(maxsize=4)
def _read(path,stamp):
    out={}; bad=set()
    try:
        with open(path,encoding='utf-8-sig',newline='') as f:
            for r in csv.DictReader(f):
                v=valid_row(r)
                if v is None: continue
                d,s,ex,ref,hi,lo=v; k=(d,s); value=(ex,ref,hi,lo)
                if k in out and out[k]!=value: bad.add(k)
                out[k]=value
    except (OSError,ValueError,TypeError,InvalidOperation): return {}
    return {k:v for k,v in out.items() if k not in bad}

def limits(path=PATH):
    try: return _read(str(path),Path(path).stat().st_mtime_ns)
    except OSError: return {}

def bind_daily(frame,asof):
    """Bind active EOD session per Streamlit execution context, no shared mutation."""
    day=day_key(asof); rows={}
    try:
        cols=['Mã','Ngày','Giá đóng cửa','Chg_%']
        x=frame.loc[frame['Ngày']==asof,cols]
        for s,d,p,c in x.itertuples(index=False,name=None):
            code=str(s).upper(); price=number(p)
            if price is not None and price>0: rows[code]=(price,number(c))
    except (KeyError,TypeError,AttributeError,ValueError): pass
    _CTX.set((day,rows))

@dataclass(frozen=True)
class Display:
    state:str
    delta:float|None
    pct:float|None
    verified:bool=False
    @property
    def color(self): return COLORS[self.state]
    @property
    def label(self): return LABELS[self.state]
    @property
    def arrow(self): return '▲' if self.state in ('ceiling','up') else '▼' if self.state in ('floor','down') else '■' if self.state=='flat' else ''
    @property
    def change_text(self):
        return f'{self.arrow} {self.delta:+.2f} ({self.pct:+.2f}%)' if self.delta is not None and self.pct is not None else ''
    @property
    def pct_text(self): return f'{self.pct:+.2f}%' if self.pct is not None else '—'

def _direction(delta):
    return 'unknown' if delta is None else 'flat' if abs(delta)<1e-8 else 'up' if delta>0 else 'down'

def display(code,price,chg=None,*,day=None,prev=None,session=True):
    """Official same-date limits take precedence; unknown falls back to direction.
    A non-daily period never inherits a daily ceiling/floor. Default date requires
    matching the active EOD price for this exact ticker, preventing stale reuse.
    """
    s=str(code).strip().upper(); p=number(price); c=number(chg); before=number(prev)
    active,rows=_CTX.get(); row=rows.get(s); d=day_key(day) if day is not None else ''
    if not d and day is None and row and p is not None and abs(row[0]-p)<1e-7:
        d=active
        if c is None and session: c=row[1]
    if p is None or p<=0: return Display('unknown',None,None)
    if session and d:
        q=limits().get((d,s))
        if q:
            ex,ref,hi,lo=q
            if lo-1e-7<=p<=hi+1e-7 and abs(float(_decimal(p)/tick(p,ex))-round(float(_decimal(p)/tick(p,ex))))<1e-6:
                state='ceiling' if abs(p-hi)<1e-7 else 'floor' if abs(p-lo)<1e-7 else _direction(p-ref)
                return Display(state,p-ref,(p/ref-1)*100,True)
    if before is not None and before>0:
        return Display(_direction(p-before),p-before,(p/before-1)*100)
    if c is not None and c>-100:
        return Display(_direction(c),p-p/(1+c/100),c)
    return Display('unknown',None,None)

def style_row(row,code='Mã',price='Giá',chg='Chg_%',columns=None):
    x=display(row.get(code),row.get(price),row.get(chg))
    targets=set(columns or (price,chg))
    return ['color:'+x.color+';font-weight:600' if k in targets and x.state!='unknown' else '' for k in row.index]

def display_frame(frame,code='Mã',price='Giá',chg='Chg_%'):
    """Copy only display data, preserve trading frame and multi-period metrics."""
    out=frame.copy()
    if all(k in out.columns for k in (code,price,chg)):
        for i in out.index:
            r=out.loc[i]
            if getattr(r,'ndim',0)!=1: continue
            v=display(r[code],r[price],r[chg])
            if v.verified: out.at[i,chg]=v.pct
    return out
