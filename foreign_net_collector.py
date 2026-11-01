"""VNStock 5 Insights foreign *net* flow collector (Windows only).

No credentials read or printed. Never runs on Streamlit Cloud. Day is sourced
from date-bearing VND rankings and verified before attaching to ASEAN snapshots.
"""
from __future__ import annotations

import argparse
from datetime import datetime, date
from pathlib import Path
import os
import re
import tempfile
import sys
from zoneinfo import ZoneInfo

import pandas as pd

ROOT = Path(__file__).resolve().parent
NET_CSV = ROOT/'data'/'foreign_net_flow.csv'
COLUMNS = ['trading_date','symbol','exchange','net_value_vnd','net_volume','net_10d_vnd',
           'source_scope','observed_at_utc']
VN_TZ = ZoneInfo('Asia/Ho_Chi_Minh')

class SourceUnavailable(Exception):
    pass


def latest_eod_date(path: Path) -> str:
    if not path.is_file():
        raise SourceUnavailable('EOD CSV not found')
    # Read only column names + date. The source may use dd/mm/YYYY.
    dates = pd.read_csv(path, usecols=['Ngày'])['Ngày']
    iso=dates.astype(str).str.match(r'^\d{4}-\d{2}-\d{2}')
    parsed=pd.Series(pd.NaT,index=dates.index,dtype='datetime64[ns]')
    parsed.loc[iso]=pd.to_datetime(dates.loc[iso],format='%Y-%m-%d',errors='coerce')
    parsed.loc[~iso]=pd.to_datetime(dates.loc[~iso],dayfirst=True,errors='coerce')
    if parsed.notna().sum() == 0:
        raise SourceUnavailable('Invalid EOD date column')
    latest = parsed.max().date()
    if latest > datetime.now(VN_TZ).date():
        raise SourceUnavailable('EOD date is in the future')
    return latest.isoformat()


def _safe_symbols(frame):
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame()
    d=frame.copy()
    d.columns=[str(c).strip().lower() for c in d.columns]
    if 'symbol' not in d:
        return pd.DataFrame()
    d['symbol']=d['symbol'].astype(str).str.strip().str.upper()
    return d[d['symbol'].str.fullmatch(r'[A-Z][A-Z0-9]{1,5}',na=False)]


def dated_ranks(ins, when):
    """Date-verified top-net data from VNStock ranking, values in VND."""
    entries=[]
    for method, sign in ((ins.ranking.foreign_buy,1),(ins.ranking.foreign_sell,-1)):
        try:
            data=_safe_symbols(method(date=when,limit=100))
        except Exception as exc:
            raise SourceUnavailable('VNStock ranking not available: '+type(exc).__name__) from None
        if data.empty:
            continue
        if not {'date','net_value'}.issubset(set(data.columns)):
            raise SourceUnavailable('VNStock ranking missing net_value/date')
        parsed=pd.to_datetime(data['date'],errors='coerce',utc=True).dt.tz_convert('Asia/Ho_Chi_Minh').dt.strftime('%Y-%m-%d')
        # Never append a snapshot for a different or undated trading day.
        if not parsed.eq(when).all():
            raise SourceUnavailable('Ranking date does not match EOD date')
        data['net_value']=pd.to_numeric(data['net_value'],errors='coerce')
        if not data['net_value'].dropna().empty:
            if sign>0: data=data[data['net_value']>0]
            else: data=data[data['net_value']<0]
        entries.extend(zip(data['symbol'],data['net_value']))
    if not entries:
        raise SourceUnavailable('No dated VNStock foreign ranking for '+when)
    ranks=pd.DataFrame(entries,columns=['symbol','net_value_vnd']).dropna()
    ranks=ranks.drop_duplicates('symbol',keep='first')
    if len(ranks)>1500 or ranks['net_value_vnd'].abs().gt(10**16).any():
        raise SourceUnavailable('Ranking values out of range')
    return ranks


def live_flow(ins):
    """Return latest source snapshots (not date-labelled) for all supported exchanges."""
    parts=[]
    errors=[]
    for exchange in ('HOSE','HNX','UPCOM'):
        try:
            data=_safe_symbols(ins.flow.foreign(exchange=exchange,group_by='stock'))
            if data.empty or not {'value_1d','symbol'}.issubset(data):
                errors.append(exchange+'_empty_or_schema')
                continue
            data=data.drop_duplicates('symbol',keep='first')
            for col in ('value_1d','volume_1d','value_10d'):
                if col not in data:
                    data[col]=float('nan')
                data[col]=pd.to_numeric(data[col],errors='coerce')
            data=data.dropna(subset=['value_1d'])
            data['exchange']=exchange
            parts.append(data[['symbol','exchange','value_1d','volume_1d','value_10d']])
        except Exception as exc:
            errors.append(exchange+'_'+type(exc).__name__)
    if not parts:
        return pd.DataFrame(),errors
    full=pd.concat(parts,ignore_index=True)
    full=full.drop_duplicates('symbol',keep='first')
    full=full[full['value_1d'].abs().le(10**16)]
    return full,errors


def build_snapshot(ranks, flows, when, observed):
    """Use full-market flow only if date-anchored ranked values agree.

    If the two providers disagree we display correctly dated ranking subset,
    never pretend it covers all listed stocks.
    """
    if not flows.empty:
        combined=ranks.merge(flows,on='symbol',how='inner')
        comparisons=combined[(combined['net_value_vnd'].abs()>1e8) & combined['value_1d'].notna()]
        comparisons=comparisons.assign(relative=(comparisons['value_1d']-comparisons['net_value_vnd']).abs() / comparisons['net_value_vnd'].abs().clip(lower=1e8))
        # At least three independently dated symbols and 75% agreement at 5% tolerance.
        agree=len(comparisons)>=3 and (comparisons['relative']<=.05).mean()>=.75
        if agree:
            result=flows.rename(columns={'value_1d':'net_value_vnd','volume_1d':'net_volume','value_10d':'net_10d_vnd'}).copy()
            result['source_scope']='FLOW_VERIFIED_FULL'
        else:
            result=ranks.copy()
            result['exchange']=''
            result['net_volume']=float('nan')
            result['net_10d_vnd']=float('nan')
            result['source_scope']='RANKING_TOP_ONLY'
    else:
        result=ranks.copy()
        result['exchange']=''
        result['net_volume']=float('nan')
        result['net_10d_vnd']=float('nan')
        result['source_scope']='RANKING_TOP_ONLY'
    result['trading_date']=when
    result['observed_at_utc']=observed
    result=result[COLUMNS].copy()
    result=result.drop_duplicates(['trading_date','symbol'])
    result=result[result['net_value_vnd'].notna()]
    if result.empty:
        raise SourceUnavailable('No validated foreign net rows')
    return result


def validate_table(frame):
    if frame.empty or not set(COLUMNS).issubset(frame.columns):
        raise ValueError('Invalid/empty net table')
    df=frame[COLUMNS].copy()
    df['net_value_vnd']=pd.to_numeric(df['net_value_vnd'],errors='coerce')
    if df['net_value_vnd'].isna().any() or df['net_value_vnd'].abs().gt(10**16).any():
        raise ValueError('Invalid VND values')
    if not df['symbol'].astype(str).str.fullmatch(r'[A-Z][A-Z0-9]{1,5}').all():
        raise ValueError('Invalid stock symbols')
    dates=pd.to_datetime(df['trading_date'],format='%Y-%m-%d',errors='coerce')
    if dates.isna().any():
        raise ValueError('Invalid trading dates')
    if df.duplicated(['trading_date','symbol']).any():
        raise ValueError('Duplicate per date and symbol')
    if not df['source_scope'].isin(['FLOW_VERIFIED_FULL','RANKING_TOP_ONLY']).all():
        raise ValueError('Unknown coverage')
    if df['observed_at_utc'].isna().any():
        raise ValueError('Missing observation timestamp')
    return df


def save_snapshot(new, path=NET_CSV):
    path=Path(path)
    incoming=validate_table(new)
    if path.exists():
        old=validate_table(pd.read_csv(path,dtype={'symbol':str,'trading_date':str},keep_default_na=False).replace({'':float('nan')}))
        date=incoming['trading_date'].iloc[0]
        previous=old[old['trading_date'].eq(date)]
        if not previous.empty:
            old_full=previous['source_scope'].eq('FLOW_VERIFIED_FULL').all()
            new_full=incoming['source_scope'].eq('FLOW_VERIFIED_FULL').all()
            if old_full and not new_full:
                return 'KEPT_BETTER_EXISTING',len(old)
            if old_full==new_full and len(previous)>len(incoming):
                return 'KEPT_LARGER_EXISTING',len(old)
        combined=pd.concat([old[old['trading_date'].ne(date)],incoming],ignore_index=True)
    else:
        combined=incoming
    combined=validate_table(combined).sort_values(['trading_date','symbol']).reset_index(drop=True)
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,temp=tempfile.mkstemp(dir=path.parent,prefix='.foreign_net_',suffix='.csv')
    try:
        with os.fdopen(fd,'w',encoding='utf-8-sig',newline='') as out:
            combined.to_csv(out,index=False)
            out.flush();os.fsync(out.fileno())
        if path.exists():
            from shutil import copy2
            folder=path.parent/'.foreign_backups';folder.mkdir(exist_ok=True)
            dst=folder/('foreign_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'.csv')
            copy2(path,dst)
        os.replace(temp,path)
    finally:
        if os.path.exists(temp): os.unlink(temp)
    return 'SAVED',len(combined)


def run_collector(ins, *, root=ROOT, now=None, save=True):
    now=now or datetime.now(VN_TZ)
    target=latest_eod_date(Path(root)/'data'/'eod_prices.csv')
    # At/after the market close, use the session date even if the full EOD
    # collector is still running; the ranking API itself verifies the date.
    local=now.astimezone(VN_TZ)
    if local.weekday()<5 and (local.hour,local.minute)>=(15,40):
        target=max(target,local.date().isoformat())
    ranks=dated_ranks(ins,target)
    flows,errors=live_flow(ins)
    snapshot=build_snapshot(ranks,flows,target,now.astimezone(ZoneInfo('UTC')).isoformat(timespec='seconds'))
    if save:
        status,total=save_snapshot(snapshot,Path(root)/'data'/'foreign_net_flow.csv')
    else:
        status,total='DRY_RUN',len(snapshot)
    return {'status':status,'date':target,'rows':len(snapshot),'total_rows':total,'coverage':snapshot['source_scope'].iloc[0],
            'exchange_errors':len(errors)}


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--collect',action='store_true')
    a=ap.parse_args()
    if not a.collect:
        print('COLLECT_BLOCK: Use --collect to access VNStock from this Windows machine',flush=True)
        return 2
    try:
        from vnstock import Insights
        out=run_collector(Insights())
        print('FOREIGN_RESULT: '+out['status']+' | date='+out['date']+' | coverage='+out['coverage']+
              ' | rows='+str(out['rows'])+' | exchange_errors='+str(out['exchange_errors'])+' | NO_GIT_PUSH',flush=True)
        return 0
    except Exception as exc:
        # No credentials/provider URLs in logs.
        print('FOREIGN_BLOCK: '+type(exc).__name__+' | current history retained | '+
              (str(exc)[:180] if isinstance(exc,SourceUnavailable) else 'Check VNStock access/schema'),flush=True)
        return 1

if __name__=='__main__':
    sys.exit(main())
