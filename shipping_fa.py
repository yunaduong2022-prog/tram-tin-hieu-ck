"""Vận tải biển: research FA only, Q3/2026 TTM, separate from port FA.
Quarterly/annual user-provided exports; no write to EOD or trading data.
"""
import math
from functools import lru_cache
from pathlib import Path
import port_fa as base

ROOT=Path(__file__).resolve().parent
PATH=ROOT/'data/shipping_fa_inputs.csv'
ASOF='2026-11-26'
TANKER=frozenset('PVT PVP VTO VIP GSP PDV'.split())
CARGO=frozenset('HAH VOS VNA VST'.split())
SYMBOLS=TANKER|CARGO
WEIGHTS={'roe':10,'roa':5,'margin':10,'rev_growth':5,'profit_growth':10,'cfo_ratio':10,'netdebt_ebitda':10,'interest_cover':10,'equity_ratio':5,'current_ratio':5,'ev_ebitda':10,'pe':5,'pb_hist':3,'pb_industry':2}
BANDS={'roe':(20,15,10),'roa':(10,7,4),'margin':(30,22,15),'rev_growth':(20,10,5),'profit_growth':(25,15,5),'cfo_ratio':(1.2,1,.75),'netdebt_ebitda':(1,2,3),'interest_cover':(8,5,3),'equity_ratio':(60,50,40),'current_ratio':(2,1.5,1),'ev_ebitda':(5,7,9),'pe':(7,10,14)}
LOW={'netdebt_ebitda','ev_ebitda','pe','pb'}
LABELS={**base.LABELS,'profit_growth':'Tăng LNST báo cáo TTM','cfo_ratio':'CFO/LNST hợp nhất','current_ratio':'Thanh toán hiện hành'}
FLAGS={'OTHER':'Thu nhập khác đáng kể, LNST chưa chuẩn hóa','CAP':'Số cổ phiếu hoặc vốn chưa khớp','NEG_EQUITY':'Vốn chủ sở hữu âm','NEG_CFO':'Dòng tiền kinh doanh âm','NEG_EBITDA':'EBITDA âm','FY_DIFF':'Số năm 2025 và tổng quý có chênh lệch; dùng chuỗi quý nhất quán'}

def group(s):return 'Vận tải dầu khí' if s in TANKER else 'Vận tải container & hàng rời'

def read_rows(path=PATH):
    import csv
    with open(path,encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
    if len(rows)!=len(SYMBOLS) or {r['code'] for r in rows}!=SYMBOLS:raise ValueError('SHIPPING_INVALID_UNIVERSE')
    return {r['code']:r for r in rows}

def tier(k,v):
    if v is None:return None
    if k in ('pe','ev_ebitda') and v<=0:return None
    for lim,fac in zip(BANDS[k],(1,.8,.6)):
        if (v<=lim if k in LOW else v>=lim):return fac
    if k in LOW:return .3 if v<= {'netdebt_ebitda':5,'ev_ebitda':14,'pe':22}[k] else 0
    return .3 if v>0 else 0

def valuation(r,price,shares):
    n=lambda k:base.num(r,k)
    if price is None or price<9000 or not shares or shares<=0 or not n('parent_equity') or n('parent_equity')<=0:return None
    if not n('ebitda') or n('ebitda')<=0:return None
    if any(n(k) is None for k in ('debt','cash','nci')):return None
    cap=price*shares/1e9
    return dict(pe=base.ratio(cap,n('profit')),pb=base.ratio(cap,n('parent_equity')),ev_ebitda=base.ratio(cap+n('debt')-n('cash')+n('nci'),n('ebitda')))

def evaluate(r,vals,industry,day,mode):
    n=lambda k:base.num(r,k)
    v={k:n(k) for k in BANDS};v.update(vals,pb_hist=n('pb_hist'),pb_industry=industry)
    f={k:tier(k,v[k]) for k in BANDS}
    if n('profit') is not None and n('profit')<=0:f.update(profit_growth=0,pe=0)
    elif n('profit') is not None and n('prior_profit') is not None and n('prior_profit')<=0:f['profit_growth']=.6
    f.update(pb_hist=base.pb_factor(v['pb'],v['pb_hist']),pb_industry=base.pb_factor(v['pb'],industry))
    pts={k:None if f[k] is None else round(f[k]*w,5) for k,w in WEIGHTS.items()}
    coverage=sum(w for k,w in WEIGHTS.items() if pts[k] is not None)
    return dict(code=r['code'],v=v,factors=f,points=pts,coverage=coverage,score=round(sum(pts.values()),2) if coverage==100 else None,raw=r,day=day,mode=mode,group=group(r['code']),rank=None,count=0,ranks={})

def rank(results):
    for g in (group('PVT'),group('HAH')):
        peers=[e for e in results.values() if e['group']==g and e['score'] is not None]
        if len(peers)<3:continue
        for e in peers:
            e['rank']=1+sum(x['score']>e['score'] for x in peers);e['count']=len(peers)
            for k in (*BANDS,'pb'):
                v=e['v'][k]; a=[x['v'][k] for x in peers if x['v'][k] is not None]
                if v is not None and len(a)>=3:e['ranks'][k]=1+sum(n<v if k in LOW else n>v for n in a)
    return results

def results(rows,prices=None,shares=None,day=None):
    live=prices is not None; vals={}
    if live and (day is None or not ASOF<=day<='2027-03-29'):return {}
    for s,r in rows.items():
        n=lambda k:base.num(r,k)
        a,b=n('shares'),n('source_shares')
        if not a or not b or abs(a/b-1)>.01 or 'CAP' in r['flags'].split('+'):continue
        if live:
            sh=shares.get(s)
            if not sh or abs(sh/a-1)>.01 or not r['pub'] or r['pub']>day:continue
            price=prices.get(s)
        else:sh=b;price=n('price_proxy')
        v=valuation(r,price,sh)
        if v is not None:vals[s]=v
    if len(vals)<3:return {}
    industry=sum(v['pb'] for v in vals.values())/len(vals)
    return rank({s:evaluate(rows[s],v,industry,day,'eod' if live else 'snapshot') for s,v in vals.items()})

@lru_cache(maxsize=3)
def cached_rows(i):return read_rows(i[0])
@lru_cache(maxsize=3)
def cached_snapshot(i):return results(cached_rows(i))

def latest_prices(eod,meta):
    # Same guards as port, but do not alter its universe or global state.
    import json,pandas as pd
    m=json.loads(Path(meta).read_text(encoding='utf-8-sig'));d=pd.Timestamp(m['latest_date']).normalize()
    if pd.isna(d) or d.date().isoformat()<ASOF:raise ValueError('SHIPPING_BAD_DATE')
    df=pd.read_csv(eod,usecols=['Mã','Ngày','Giá đóng cửa'],dtype={'Mã':str},encoding='utf-8-sig')
    raw=df['Ngày'].astype(str).str.strip();iso=raw.str.match(r'^\d{4}-\d{2}-\d{2}')
    dates=pd.to_datetime(raw.where(~iso),format='mixed',dayfirst=True,errors='coerce');dates.loc[iso]=pd.to_datetime(raw.loc[iso].str[:10],format='%Y-%m-%d',errors='coerce')
    df['Ngày']=dates.dt.normalize()
    if df['Ngày'].max()!=d:raise ValueError('SHIPPING_META_MISMATCH')
    failed={str(x).split(':',1)[0].strip() for x in m.get('failed',[])};p={}
    for s,g in df.loc[df['Ngày'].eq(d)&df['Mã'].isin(SYMBOLS)].groupby('Mã'):
        if len(g)!=1 or s in failed:continue
        v=base.num(g.iloc[0],'Giá đóng cửa')
        if v is not None and v>0:p[s]=v*1000
    return d.date().isoformat(),p

@lru_cache(maxsize=3)
def cached_eod(i,e,m,sh):
    day,prices=latest_prices(e[0],m[0]);return prices,results(cached_rows(i),prices,base.read_shares(sh[0]),day)

def state():
    try:i=base.stamp(PATH);rows=cached_rows(i);snap=cached_snapshot(i)
    except (OSError,ValueError,KeyError,TypeError):return {},{},{},{}
    try:prices,live=cached_eod(i,base.stamp(base.EOD),base.stamp(base.META),base.stamp(base.SHARES))
    except (OSError,ValueError,KeyError,TypeError,OverflowError):prices,live={},{}
    return rows,snap,prices,live

def notes(e):
    v=e['v'];r=e['raw'];out=['FA tham khảo | Vận tải biển | Q3/2026 TTM | '+('EOD ước tính '+e['day'] if e['mode']=='eod' else 'Định giá ZIP không có ngày phiên xác nhận')]
    flags=[FLAGS[k] for k in r['flags'].split('+') if k in FLAGS]
    if flags:out.append('Cảnh báo: '+'; '.join(flags))
    def top(k):return f' | TOP {e["ranks"][k]} Nhóm {e["group"]}' if e['ranks'].get(k,99)<=5 else ''
    for k in BANDS:
        val='Không phát sinh lãi vay' if k=='interest_cover' and v[k]>=1000 else base.fmt(v[k])+('%' if k in base.PCT else ' lần')
        out.append(f'{LABELS[k]} {val} – {base.grade(e["factors"][k])}'+top(k))
    def cmp(x):return base.fmt((v['pb']/x-1)*100)+'%' if x and x>0 else '—'
    out.append(f'P/B {base.fmt(v["pb"])} lần'+top('pb')+f' | TB 3 năm (quý): {base.fmt(v["pb_hist"])} ({cmp(v["pb_hist"])}) | TB ngành {base.fmt(v["pb_industry"])} ({cmp(v["pb_industry"])})')
    if e['rank'] is not None:out.append(f'Hạng tham khảo {e["rank"]}/{e["count"]} Nhóm {e["group"]}')
    return out

def lookup(symbol):
    s=str(symbol).strip().upper();rows,snap,prices,live=state();r=rows.get(s)
    if not r:return None,['Chưa có dữ liệu Vận tải biển.']
    if s in prices and prices[s]<9000:return None,['Vận tải biển: giá EOD dưới 9.000đ, không xếp hạng.']
    if 'NEG_EQUITY' in r['flags']:return None,['Vận tải biển: vốn chủ sở hữu âm, không chấm FA.']
    if 'CAP' in r['flags']:return None,['Vận tải biển: cơ sở vốn chưa khớp, chưa chấm FA.']
    e=live.get(s) or snap.get(s)
    if not e or e['score'] is None:return None,['Vận tải biển: chưa đủ dữ liệu hoặc không đạt điều kiện giá.']
    return e,notes(e)

def for_symbol(symbol):
    e,t=lookup(symbol);return (e['score'] if e else None),t

def detail(symbol):
    e,t=lookup(symbol)
    return ('SHIPPING FA V1 | Chỉ tham khảo, không xếp hạng VIP chính thức. Nguồn: hai ZIP tài chính năm/quý do người dùng cung cấp. EBITDA = EBIT hoạt động + khấu hao; CFO/LNST hợp nhất. P/B lịch sử là trung bình quan sát theo quý, không phải trung bình giá từng phiên. EV gồm NCI; chưa chuẩn hóa khoản bất thường. ' if e else '')+'; '.join(t)
