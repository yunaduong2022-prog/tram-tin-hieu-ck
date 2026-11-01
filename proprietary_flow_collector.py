"""Windows-only, per-equity VNStock 5 proprietary (broker self-trading) flow.

No calls on Streamlit Cloud. Source timestamps are kept; no calendar-date guessing.
No Git, R2 or secrets access. Default request budget is intentionally bounded.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from zoneinfo import ZoneInfo

import pandas as pd

ROOT = Path(__file__).resolve().parent
CSV = ROOT / 'data' / 'proprietary_flow.csv'
STATE = ROOT / 'data' / '.proprietary_state'
COLUMNS = ['trading_date', 'symbol', 'buy_vol', 'buy_val', 'sell_vol', 'sell_val',
           'net_vol', 'net_val', 'data_source', 'collected_utc']
NUMERIC = ('buy_vol','buy_val','sell_vol','sell_val','net_vol','net_val')
PRIORITIES = ('VPB','FPT','VIX','HPG','MBB','TCB','SSI','VRE')
TZ = ZoneInfo('Asia/Ho_Chi_Minh')

class InvalidSource(Exception): pass

def _num(x):
    try:
        if x is None or (isinstance(x,str) and not x.strip()):return float('nan')
        value=float(x)
        return value if math.isfinite(value) else float('nan')
    except (TypeError,ValueError):return float('nan')

def _none(x):return pd.isna(x)

def normalized(raw, symbol, observed=None, *, today=None):
    """Verify source schema, timestamp, value sign and reconciliation.

    buy/sell are never synthesized from net. Net may be computed from both
    verified gross values, with that derivation labelled in data_source.
    """
    symbol=str(symbol).strip().upper()
    if not re.fullmatch(r'[A-Z][A-Z0-9]{1,5}',symbol):raise InvalidSource('Invalid symbol')
    if not isinstance(raw,pd.DataFrame) or raw.empty:raise InvalidSource('No source rows')
    d=raw.copy()
    d.columns=[str(c).strip().lower() for c in d.columns]
    if 'time' not in d:raise InvalidSource('Missing source time')
    if not ({'net_val','buy_val'} & set(d.columns)):
        raise InvalidSource('No net or buy/sell monetary fields')
    if 'net_val' not in d and not {'buy_val','sell_val'}.issubset(d.columns):
        raise InvalidSource('Cannot derive monetary net')
    observed=observed or datetime.now(ZoneInfo('UTC')).isoformat(timespec='seconds')
    today=today or datetime.now(TZ).date()
    rows=[]
    for rec in d.to_dict('records'):
        try:
            dt=pd.Timestamp(rec['time'])
            if pd.isna(dt):continue
            if dt.tzinfo is not None:dt=dt.tz_convert(TZ)
            day=dt.date()
            if day>today or day.year<2000:continue
        except (ValueError,TypeError,OverflowError):continue
        vals={c:_num(rec.get(c)) for c in NUMERIC}
        if all(_none(vals[c]) for c in ('net_val','buy_val','sell_val')):continue
        if any(vals[k]<0 for k in ('buy_vol','buy_val','sell_vol','sell_val') if not _none(vals[k])):continue
        source='VNSTOCK5_VCI_PROPRIETARY'
        if _none(vals['net_val']):
            if _none(vals['buy_val']) or _none(vals['sell_val']):continue
            vals['net_val']=vals['buy_val']-vals['sell_val']
            source+='_NET_FROM_GROSS'
        elif not _none(vals['buy_val']) and not _none(vals['sell_val']):
            err=abs(vals['buy_val']-vals['sell_val']-vals['net_val'])
            tol=max(1_000_000.0, .005*max(abs(vals['buy_val']),abs(vals['sell_val']),abs(vals['net_val'])))
            if err>tol:continue
        if _none(vals['net_vol']) and not _none(vals['buy_vol']) and not _none(vals['sell_vol']):
            vals['net_vol']=vals['buy_vol']-vals['sell_vol']
        if not _none(vals['net_vol']) and not _none(vals['buy_vol']) and not _none(vals['sell_vol']):
            if abs(vals['buy_vol']-vals['sell_vol']-vals['net_vol'])>max(1.0, .005*max(vals['buy_vol'],vals['sell_vol'])):continue
        if abs(vals['net_val'])>1e16 or any(abs(vals[k])>1e16 for k in ('buy_val','sell_val') if not _none(vals[k])):continue
        rows.append({'trading_date':day.isoformat(),'symbol':symbol,**vals,'data_source':source,'collected_utc':observed})
    result=pd.DataFrame(rows,columns=COLUMNS)
    if result.empty:raise InvalidSource('Source has no date-verified numeric rows')
    return result.drop_duplicates(['trading_date','symbol'],keep='last').sort_values('trading_date')

def validate(frame):
    if not isinstance(frame,pd.DataFrame) or frame.empty or not set(COLUMNS).issubset(frame):
        raise InvalidSource('Invalid stored proprietary table')
    d=frame[list(COLUMNS)].copy()
    d['trading_date']=d['trading_date'].astype(str)
    d['symbol']=d['symbol'].astype(str).str.upper().str.strip()
    parsed=pd.to_datetime(d['trading_date'],format='%Y-%m-%d',errors='coerce')
    if parsed.isna().any() or (parsed.dt.date>datetime.now(TZ).date()).any():raise InvalidSource('Invalid future or missing trading date')
    if not d.symbol.str.fullmatch(r'[A-Z][A-Z0-9]{1,5}').all():raise InvalidSource('Invalid ticker')
    if d.duplicated(['trading_date','symbol']).any():raise InvalidSource('Duplicated ticker/day')
    for name in NUMERIC:d[name]=pd.to_numeric(d[name],errors='coerce')
    if d['net_val'].isna().any() or d['net_val'].abs().gt(1e16).any():raise InvalidSource('Missing or absurd monetary net')
    if d[list(NUMERIC)].isin([float('inf'),float('-inf')]).any().any():raise InvalidSource('Infinite numeric data')
    for col in ('buy_vol','buy_val','sell_vol','sell_val'):
        if d[col].lt(0).any():raise InvalidSource('Negative gross field')
    if d['data_source'].astype(str).str.len().gt(90).any():raise InvalidSource('Invalid source label')
    return d

def merge(old, incoming):
    new=validate(incoming)
    if old is None or old.empty:return new.sort_values(['symbol','trading_date']).reset_index(drop=True)
    prev=validate(old)
    # More populated gross fields win for exact symbol/day; otherwise newest validated row.
    both=pd.concat([prev.assign(_new=0),new.assign(_new=1)],ignore_index=True)
    both['_complete']=both[['buy_vol','buy_val','sell_vol','sell_val']].notna().sum(axis=1)
    both=both.sort_values(['symbol','trading_date','_complete','_new']).drop_duplicates(['symbol','trading_date'],keep='last')
    return validate(both.drop(columns=['_complete','_new'])).sort_values(['symbol','trading_date']).reset_index(drop=True)

def save(data, destination=CSV):
    destination=Path(destination)
    destination.parent.mkdir(parents=True,exist_ok=True)
    old=pd.read_csv(destination,encoding='utf-8-sig',dtype={'symbol':str,'trading_date':str},low_memory=False) if destination.exists() else None
    combined=merge(old,data)
    # Avoid touching CSV or R2 if identical rows. collected_utc is audit metadata and
    # intentionally retained as before for existing rows to prevent needless updates.
    if old is not None:
        oldval=validate(old).sort_values(['symbol','trading_date']).reset_index(drop=True)
        if combined.equals(oldval):return 'NO_CHANGES',len(combined)
    with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8-sig',newline='',suffix='.csv',prefix='.prop_',dir=destination.parent,delete=False) as f:
        tmp=Path(f.name)
        combined.to_csv(f,index=False)
        f.flush();os.fsync(f.fileno())
    try:
        validate(pd.read_csv(tmp,encoding='utf-8-sig',dtype={'symbol':str,'trading_date':str}))
        if destination.exists():
            from shutil import copy2
            folder=destination.parent/'.proprietary_state'/'backups'; folder.mkdir(parents=True,exist_ok=True)
            copy2(destination,folder/('prop_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'.csv'))
        os.replace(tmp,destination)
    finally:tmp.unlink(missing_ok=True)
    return 'SAVED',len(combined)

def active_codes(root=ROOT):
    eod=Path(root)/'data'/'eod_prices.csv'
    if not eod.is_file():return list(PRIORITIES)
    df=pd.read_csv(eod,usecols=['Mã','Ngày'],encoding='utf-8-sig',low_memory=False)
    df['Ngày']=pd.to_datetime(df['Ngày'],errors='coerce',dayfirst=True,format='mixed')
    latest=df['Ngày'].max()
    df=df.loc[df['Ngày'].ge(latest-pd.Timedelta(days=14))]
    codes=df['Mã'].dropna().astype(str).str.strip().str.upper().unique().tolist()
    return sorted(c for c in codes if re.fullmatch(r'[A-Z][A-Z0-9]{1,5}',c) and c not in ('VNINDEX','VN30'))

def select_codes(codes,statefile,limit,preferred=PRIORITIES):
    codes=sorted(set(codes))
    priority=[c for c in preferred if c in codes]
    # Keep at most 6 often-inspected tickers fresh and rotate all other codes.
    pinned=priority[:min(6,limit)]
    rest=[c for c in codes if c not in pinned]
    statefile=Path(statefile)
    try:cursor=int(json.loads(statefile.read_text(encoding='utf-8')).get('cursor',0))
    except (OSError,ValueError,AttributeError):cursor=0
    rotated=[rest[(cursor+i)%len(rest)] for i in range(min(limit-len(pinned),len(rest)))] if rest else []
    next_cursor=(cursor+len(rotated))%len(rest) if rest else 0
    return pinned+rotated,next_cursor

def _write_state(path,cursor):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=path.parent,delete=False) as f:
        tmp=Path(f.name);json.dump({'cursor':cursor},f)
        f.flush();os.fsync(f.fileno())
    try:os.replace(tmp,path)
    finally:tmp.unlink(missing_ok=True)

def collect(*,symbols=None,max_symbols=18,length=65,timeout=28,budget_seconds=520,root=ROOT,worker=None):
    root=Path(root)
    if worker is None:worker=Path(__file__)
    choices=active_codes(root) if not symbols else [s.strip().upper() for s in symbols.split(',') if s.strip()]
    choices=[s for s in choices if re.fullmatch(r'[A-Z][A-Z0-9]{1,5}',s)]
    state=root/'data'/'.proprietary_state'/'roundrobin.json'
    chosen,next_cursor=select_codes(choices,state,max_symbols,preferred=PRIORITIES)
    start=time.monotonic(); successes=0; failures=[]; frames=[]
    for code in chosen:
        if time.monotonic()-start+timeout+3>budget_seconds:break
        with tempfile.TemporaryDirectory(prefix='min_prop_worker_') as folder:
            out=Path(folder)/'result.json'
            try:
                result=subprocess.run([sys.executable,'-B','-u',str(worker),'--worker',code,'--limit',str(length),'--out',str(out)],
                                      capture_output=True,text=True,encoding='utf-8',errors='replace',cwd=str(root),timeout=timeout)
                if result.returncode or not out.is_file():raise InvalidSource('Provider missing/timeout/error')
                raw=pd.read_json(out,orient='records',convert_dates=False,dtype={'trading_date':str,'symbol':str})
                parsed=validate(raw)
                if not parsed['symbol'].eq(code).all():raise InvalidSource('Unexpected symbol from worker')
                frames.append(parsed);successes+=1
                print('COLLECT_OK:',code,'rows:',len(parsed),flush=True)
            except (OSError,ValueError,InvalidSource,subprocess.TimeoutExpired,TypeError) as exc:
                failures.append(code+':'+type(exc).__name__)
                print('COLLECT_SKIP:',code,':',type(exc).__name__,flush=True)
    total=0; status='NO_NEW_DATA'
    if frames:
        status,total=save(pd.concat(frames,ignore_index=True),root/'data'/'proprietary_flow.csv')
    # Advance only by number actually visited (avoid skipping candidates after time budget).
    attempted=successes+len(failures)
    pinned=min(6,len(chosen)) if not symbols else min(6,len(chosen))
    rotated_attempts=max(0,attempted-pinned)
    rest_len=max(0,len(set(choices))-min(6,len([c for c in PRIORITIES if c in choices])))
    prev_cursor=(next_cursor-max(0,len(chosen)-pinned))%rest_len if rest_len else 0
    _write_state(state,(prev_cursor+rotated_attempts)%rest_len if rest_len else 0)
    print('PROPRIETARY_RESULT:',status,'| success:',successes,'| failures:',len(failures),
          '| attempted:',attempted,'| total_history_rows:',total,'| source:VCI | NO_GIT_PUSH',flush=True)
    return successes>0,failures

def worker(symbol,limit,destination):
    # Avoid importing VNStock on Streamlit Cloud or parent validation tests.
    from vnstock import Market
    raw=Market().equity(symbol).proprietary_flow(limit=limit,source='vci')
    # A local, private subprocess result. The parent verifies everything again.
    if not isinstance(raw,pd.DataFrame):raise InvalidSource('Provider returned unexpected type')
    checked=normalized(raw,symbol)
    Path(destination).write_text(checked.to_json(orient='records',date_format='iso'),encoding='utf-8')

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--collect',action='store_true')
    parser.add_argument('--worker')
    parser.add_argument('--out')
    parser.add_argument('--symbols')
    parser.add_argument('--limit',type=int,default=65)
    parser.add_argument('--max-symbols',type=int,default=18)
    parser.add_argument('--timeout',type=int,default=28)
    parser.add_argument('--budget-seconds',type=int,default=520)
    args=parser.parse_args()
    try:
        if args.worker:
            if not args.out or not re.fullmatch(r'[A-Z][A-Z0-9]{1,5}',args.worker):return 2
            worker(args.worker,max(3,min(args.limit,250)),args.out)
            return 0
        if not args.collect:return 2
        ok,errors=collect(symbols=args.symbols,max_symbols=max(1,min(args.max_symbols,80)),
                          length=max(3,min(args.limit,250)),timeout=max(5,min(args.timeout,75)),
                          budget_seconds=max(30,min(args.budget_seconds,1500)))
        return 0 if ok else 1
    except Exception as exc:
        print('PROPRIETARY_BLOCK:',type(exc).__name__, '| old data retained',flush=True)
        return 2

if __name__=='__main__':sys.exit(main())
