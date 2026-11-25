"""Read-only BDS valuation from the canonical existing EOD store; never fetch prices."""
from pathlib import Path
from functools import lru_cache
import csv
import json
import math
import pandas as pd
import bds_fa as b

ROOT=Path(__file__).resolve().parent
BASIS=ROOT/'data'/'bds_fa_valuation_basis.csv'
EOD=ROOT/'data'/'eod_prices.csv'
META=ROOT/'data'/'eod_meta.json'
MIN_PEERS=20


def read_rows(path):
    with Path(path).open(encoding='utf-8-sig',newline='') as f:
        rows=list(csv.DictReader(f))
    if len(rows)!=33 or {r['Mã'] for r in rows}!=b.SYMBOLS:
        raise ValueError('BDS_FA_INVALID_UNIVERSE')
    return {r['Mã']:r for r in rows}


def latest_prices(eod,meta):
    """Only the explicitly published session; reject ambiguous duplicate bars."""
    day=pd.Timestamp(json.loads(Path(meta).read_text(encoding='utf-8-sig'))['latest_date']).normalize()
    if pd.isna(day):raise ValueError('INVALID_EOD_DATE')
    cols=['Mã','Ngày','Giá đóng cửa']
    df=pd.read_csv(eod,usecols=cols,dtype={'Mã':str},encoding='utf-8-sig')
    raw=df['Ngày'].astype(str).str.strip()
    iso=raw.str.match(r'^\d{4}-\d{2}-\d{2}')
    parsed=pd.to_datetime(raw.where(~iso),format='mixed',dayfirst=True,errors='coerce')
    parsed.loc[iso]=pd.to_datetime(raw.loc[iso].str[:10],format='%Y-%m-%d',errors='coerce')
    df['Ngày']=parsed.dt.normalize()
    if df['Ngày'].max()!=day:raise ValueError('EOD_META_MISMATCH')
    view=df.loc[df['Ngày'].eq(day)&df['Mã'].isin(b.SYMBOLS)]
    prices={}
    for s,g in view.groupby('Mã'):
        if len(g)!=1:continue
        x=b.number(g.iloc[0], 'Giá đóng cửa')
        if x is not None and x>0:prices[s]=x*1000 # EOD price in thousand VND
    return day.date().isoformat(),prices


def build(rows,basis,day,prices):
    """Recompute all peers with one date; never mix historical snapshot into daily mean."""
    prepared={}; valuations={}
    for s,raw in rows.items():
        q=basis.get(s,{})
        bv=b.number(q,'BVPS tham chiếu (VND)');eps=b.number(q,'EPS tham chiếu (VND)')
        px=prices.get(s)
        if not (px is not None and math.isfinite(px) and px>0 and bv is not None and bv>0 and eps is not None and q.get('Ngày công bố','9999')<=day):continue
        pb=px/bv;pe=px/eps if eps!=0 else None
        row=dict(raw);row[b.FIELDS['P/B']]=pb;row[b.FIELDS['P/E']]=pe
        row['Kỳ tham chiếu định giá FA']='EOD '+day
        prepared[s]=row;valuations[s]={'price':px,'pb':pb,'pe':pe,'bvps':bv,'eps':eps,'basis':q}
    if len(prepared)<MIN_PEERS:
        return {'day':day,'results':{},'valuations':valuations,'peers':len(prepared),'reason':'Chưa đủ 20 mã có giá cùng phiên'}
    industry=sum(v['pb'] for v in valuations.values())/len(valuations)
    results=b.rank_values({s:b.evaluate(row,industry) for s,row in prepared.items()})
    return {'day':day,'results':results,'valuations':valuations,'peers':len(prepared),'reason':''}


def stamp(path):
    s=Path(path).stat();return (str(path),s.st_mtime_ns,s.st_size)


@lru_cache(maxsize=3)
def _cached(input_stamp,basis_stamp,eod_stamp,meta_stamp):
    rows=read_rows(input_stamp[0]);basis=read_rows(basis_stamp[0]);day,prices=latest_prices(eod_stamp[0],meta_stamp[0])
    return build(rows,basis,day,prices)


def load(input_path=None,basis_path=None,eod_path=None,meta_path=None):
    try:
        return _cached(stamp(input_path or b.PATH),stamp(basis_path or BASIS),stamp(eod_path or EOD),stamp(meta_path or META))
    except (OSError,ValueError,KeyError,TypeError,OverflowError):
        return {'day':None,'results':{},'valuations':{},'peers':0,'reason':'Chưa có dữ liệu EOD hợp lệ hoặc dữ liệu định giá không đồng bộ'}


def display_notes(e,state,*,fallback=False):
    notes=list(b.notes(e))
    # Keep all metric notes within existing 12-line limit; the last line carries source/date status.
    last=notes.pop()
    warnings='Cảnh báo: '+'; '.join(e['warnings'])+' | ' if e['warnings'] else ''
    if fallback:
        notes.append(warnings+f'{e["grade"]} | FA tham chiếu Q3/2026 – chưa có định giá EOD đủ điều kiện')
        return notes
    day=pd.Timestamp(state['day']).strftime('%d/%m/%Y')
    n=sum(x['score'] is not None for x in state['results'].values())
    # Distinguish the peer count used for P/B from the number of scores actually ranked.
    for i,t in enumerate(notes):
        if t.startswith('P/B '):notes[i]=t.replace('TB ngành:',f'TB ngành ({state["peers"]}/33 mã):')
    q=state['valuations'][e['code']]['basis']
    diff=b.number(q,'Chênh lệch CP (%)')
    flag=' | CP tham chiếu lệch vốn góp Q3' if diff is not None and abs(diff)>1 else ''
    rank=f'Hạng {e["rank"]}/{n} Ngành BĐS' if e['rank'] is not None else 'Chưa đủ điểm xếp hạng'
    notes.append(warnings+f'{e["grade"]} | {rank} | BCTC Q3/2026 | Định giá EOD {day} (ước tính)'+flag)
    return notes


def for_symbol(symbol):
    s=str(symbol).strip().upper();state=load();e=state['results'].get(s)
    if e is not None and e['score'] is not None:return e['score'],display_notes(e,state)
    # Existing quarterly score is retained solely as an explicitly labelled reference;
    # it is never included in the daily sector mean or daily ranking.
    e=b.load().get(s)
    return (e['score'],display_notes(e,state,fallback=True)) if e else (None,[])


def detail(symbol):
    state=load();s=str(symbol).upper().strip();v=state['valuations'].get(s);e=state['results'].get(s)
    if not v or not e or e['score'] is None:
        return 'FA tham chiếu Q3/2026: '+(state['reason'] or 'Mã thiếu giá cùng phiên hoặc dữ liệu định giá hợp lệ')+'. Không xếp hạng chung với các mã EOD.'
    q=v['basis'];return (f"Giá đóng cửa EOD {state['day']}: {b.fmt(v['price'],0)} đồng. "
        f"BVPS tham chiếu {b.fmt(v['bvps'],0)} đồng; EPS TTM tham chiếu {b.fmt(v['eps'],0)} đồng. "
        f"Số CP tham chiếu {q['CP tham chiếu ZIP']}; chênh lệch với vốn góp Q3 {b.fmt(b.number(q,'Chênh lệch CP (%)'))}%. "
        f"P/B = giá/BVPS; P/E = giá/EPS. BVPS = VCSH công ty mẹ/CP; EPS = LNST công ty mẹ TTM/CP tham chiếu (không phải EPS bình quân gia quyền công bố). "
        f"P/B lịch sử giữ nguyên 12 quý; P/B ngành bình quân {state['peers']}/33 mã cùng phiên. "
        "Chưa điều chỉnh phát hành/cổ tức sau kỳ, giá EOD theo kho hiện tại. Nguồn: "+q['Nguồn'])
