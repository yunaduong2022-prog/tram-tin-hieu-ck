"""Windows-only, per-ticker foreign buy/sell historical flow collector (VNStock VCI).

Uses validated atomic history primitives already deployed for proprietary_flow.
No vendor calls are made by the Cloud web app. No credential logging or Git writes.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import pandas as pd

import proprietary_flow_collector as core

ROOT=Path(__file__).resolve().parent
CSV=ROOT/'data'/'foreign_stock_flow.csv'
STATE=ROOT/'data'/'.foreign_stock_state'/'roundrobin.json'
SOURCE='VNSTOCK5_VCI_FOREIGN'
PRIORITIES=('VPB','FPT','VIX','HPG','MBB','TCB','SSI','VRE')


def normalized(raw,code,**kwargs):
    """Validate the dated gross/net contract; never invent buy/sell columns."""
    df=core.normalized(raw,code,**kwargs)
    df['data_source']=df['data_source'].str.replace('VNSTOCK5_VCI_PROPRIETARY',SOURCE,regex=False)
    return core.validate(df)


def worker(code,limit,out):
    from vnstock import Market  # imported only inside local Windows child process
    raw=Market().equity(code).foreign_flow(limit=limit,source='vci')
    result=normalized(raw,code)
    Path(out).write_text(result.to_json(orient='records',date_format='iso'),encoding='utf-8')


def collect(*,symbols=None,max_symbols=18,limit=65,timeout=28,budget_seconds=540,root=ROOT,worker_script=None):
    root=Path(root)
    codes=(core.active_codes(root) if not symbols else [c.strip().upper() for c in symbols.split(',') if c.strip()])
    codes=sorted(set(c for c in codes if re.fullmatch(r'[A-Z][A-Z0-9]{1,5}',c)))
    if not codes:
        print('FOREIGN_STOCK_RESULT: NO_CODES | NO_GIT_PUSH',flush=True)
        return False
    state=root/'data'/'.foreign_stock_state'/'roundrobin.json'
    chosen,new_cursor=core.select_codes(codes,state,min(max_symbols,len(codes)),PRIORITIES)
    worker_script=Path(worker_script or __file__)
    successful=[];failures=[];start=time.monotonic()
    for code in chosen:
        if time.monotonic()-start+timeout+2>budget_seconds:break
        try:
            with tempfile.TemporaryDirectory(prefix='min_foreign_equity_worker_') as temp:
                output=Path(temp)/'result.json'
                ret=subprocess.run([sys.executable,'-B','-u',str(worker_script),'--worker',code,
                                    '--limit',str(limit),'--out',str(output)],
                                   cwd=str(root),capture_output=True,text=True,encoding='utf-8',
                                   errors='replace',timeout=timeout)
                if ret.returncode or not output.is_file():raise core.InvalidSource('No provider data')
                data=pd.read_json(output,orient='records',convert_dates=False,dtype={'trading_date':str,'symbol':str})
                validated=core.validate(data)
                if not validated.symbol.eq(code).all() or not validated.data_source.str.startswith(SOURCE).all():
                    raise core.InvalidSource('Foreign source mismatch')
                successful.append(validated)
                print('FOREIGN_STOCK_OK:',code,'rows:',len(validated),flush=True)
        except (core.InvalidSource,OSError,ValueError,subprocess.TimeoutExpired) as exc:
            failures.append(code)
            print('FOREIGN_STOCK_SKIP:',code,type(exc).__name__,flush=True)
    result='NO_NEW_DATA';rows=0
    if successful:
        result,rows=core.save(pd.concat(successful,ignore_index=True),root/'data'/'foreign_stock_flow.csv')
    # rotation advances only for actual attempted non-pinned symbols
    priority=[c for c in PRIORITIES if c in codes][:min(6,max_symbols)]
    nonpriority=[c for c in codes if c not in priority]
    pinned=len(priority);rotated_scheduled=max(0,len(chosen)-pinned)
    rotated_attempted=max(0,len(successful)+len(failures)-pinned)
    prev=(new_cursor-rotated_scheduled)%len(nonpriority) if nonpriority else 0
    core._write_state(state,(prev+rotated_attempted)%len(nonpriority) if nonpriority else 0)
    print('FOREIGN_STOCK_RESULT:',result,'| success:',len(successful),'| failures:',len(failures),
          '| attempted:',len(successful)+len(failures),'| total_history_rows:',rows,
          '| source:VCI | NO_GIT_PUSH',flush=True)
    return bool(successful)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--collect',action='store_true')
    parser.add_argument('--worker')
    parser.add_argument('--out')
    parser.add_argument('--symbols')
    parser.add_argument('--limit',type=int,default=65)
    parser.add_argument('--max-symbols',type=int,default=18)
    parser.add_argument('--timeout',type=int,default=28)
    parser.add_argument('--budget-seconds',type=int,default=540)
    args=parser.parse_args()
    try:
        if args.worker:
            if not args.out or not re.fullmatch(r'[A-Z][A-Z0-9]{1,5}',args.worker):return 2
            worker(args.worker,max(3,min(args.limit,250)),args.out)
            return 0
        if not args.collect:return 2
        ok=collect(symbols=args.symbols,max_symbols=max(1,min(args.max_symbols,80)),
                   limit=max(3,min(args.limit,250)),timeout=max(5,min(args.timeout,75)),
                   budget_seconds=max(35,min(args.budget_seconds,1500)))
        return 0 if ok else 1
    except Exception as exc:
        print('FOREIGN_STOCK_BLOCK:',type(exc).__name__,'| previous data preserved',flush=True)
        return 2

if __name__=='__main__':sys.exit(main())
