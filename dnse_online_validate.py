"""Private DNSE G1 display only. Never used by TA scoring."""
import json, re
from pathlib import Path
from decimal import Decimal, InvalidOperation
from foreign_session_card import _dates

REPORT = 'hose_resume_20261127_214718_794657.json'
SOURCE = 'DNSE_OPENAPI_VOLUME_PROFILE_G1_X10'

def number(x):
    if isinstance(x, bool) or x is None: raise ValueError('number')
    try: d = Decimal(str(x))
    except (InvalidOperation, ValueError): raise ValueError('number') from None
    if not d.is_finite() or d < 0: raise ValueError('number')
    return d

def qty(x):
    d=number(x)
    if d!=d.to_integral_value(): raise ValueError('qty')
    return int(d)

def validate(row, code, day, e):
    lo,hi,cl,v=e
    if (row['symbol'],row['date'],row['board'],row['source'])!=(code,day,'G1',SOURCE): raise ValueError('identity')
    if not 0<lo<=cl<=hi or v<=0 or number(row['close_vnd'])!=cl or qty(row['eod_volume'])!=v: raise ValueError('eod')
    vols=tuple(qty(row[k+'_vol']) for k in ('buy','sell','unknown'))
    vals=tuple(number(row[k+'_val']) for k in ('buy','sell','unknown'))
    if sum(vols)!=v or sum(vals)!=number(row['total_val']) or any(not lo*q<=a<=hi*q for q,a in zip(vols,vals)): raise ValueError('sum')
    return vols, vals

def windows(rows,dates):
    if dates!=sorted(set(dates)) or len(rows)!=len(dates): raise ValueError('calendar')
    out={}
    for n in (1,5,10,20):
        w=rows[-n:]; count=sum(r is not None for r in w)
        complete=len(w)==count==n
        vs=tuple(sum(r[0][i] for r in w) for i in range(3)) if complete else None
        ts=tuple(sum((r[1][i] for r in w),Decimal(0)) for i in range(3)) if complete else None
        out[n]=dict(total=vs[:2] if vs else None,est=ts[:2] if ts else None,unknown=vs[2] if vs else None,unknown_val=ts[2] if ts else None,count=count,floor=False,floor_offer=None)
    return out
