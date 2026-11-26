"""PORT FA V1: Q3/2026 TTM; all scores are research estimates, never trade signals.
Source: uploaded Vietcap/SSI financial ZIP and user valuation screenshots 26/11/2026.
EOD is read-only; no price write or silent backfill. Missing data never becomes zero.
"""
import csv
import json
import math
from datetime import date
from functools import lru_cache
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parent
PATH=ROOT/'data/port_fa_inputs.csv'
EOD=ROOT/'data/eod_prices.csv'
META=ROOT/'data/eod_meta.json'
SHARES=ROOT/'data/shares_outstanding.csv'
ASOF='2026-11-26'
PORT=frozenset('CCP DVP CQN SGP CCT CDN PDN VGR CCR GMD PHP CAG CMP DXP NAP CLL QNP VSC'.split())
LOGISTICS=frozenset('ILB IST TMS GIC TCL TCW STG'.split())
SPECIAL=frozenset('CPI PAP VMS VIN DS3 PSN PQN VGP'.split())
SYMBOLS=PORT|LOGISTICS|SPECIAL
WEIGHTS={'roe':10,'roa':5,'margin':10,'rev_growth':10,'profit_growth':10,'cfo_ratio':10,'netdebt_ebitda':10,'interest_cover':5,'equity_ratio':5,'ev_ebitda':10,'pe':5,'pb_hist':5,'pb_industry':5}
LABELS={'roe':'ROE','roa':'ROA','margin':'Biên EBITDA hoạt động','rev_growth':'Tăng doanh thu TTM','profit_growth':'Tăng LNST báo cáo TTM','cfo_ratio':'CFO/LNST','netdebt_ebitda':'Nợ ròng/EBITDA','interest_cover':'EBIT/Lãi vay','equity_ratio':'VCSH/Tổng tài sản','ev_ebitda':'EV/EBITDA','pe':'P/E','pb_hist':'P/B lịch sử','pb_industry':'P/B ngành'}
BANDS={'roe':(20,15,10),'roa':(10,7,4),'margin':(40,30,20),'rev_growth':(20,10,5),'profit_growth':(25,15,5),'cfo_ratio':(1.2,1,.75),'netdebt_ebitda':(1,2,3),'interest_cover':(8,5,3),'equity_ratio':(60,50,40),'ev_ebitda':(6,8,10),'pe':(8,12,16)}
LOW={'netdebt_ebitda','ev_ebitda','pe','pb'}
PCT={'roe','roa','margin','rev_growth','profit_growth','equity_ratio'}
FLAG_NAMES={'OTHER':'Thu nhập khác đáng kể','FIN':'Tài chính ròng đáng kể','CAP':'Cơ sở vốn Q3 chưa khớp','SHARES':'Số CP thay đổi','REVIEW':'Cần rà soát lợi nhuận/cơ sở định giá','SPECIAL':'Mô hình đặc thù'}

def num(r,k):
    try:
        v=float(r.get(k,''));return v if math.isfinite(v) else None
    except (TypeError,ValueError):return None

def ratio(a,b):return a/b if a is not None and b is not None and b>0 else None

def tier(v,k):
    if v is None:return None
    if k in ('pe','ev_ebitda') and v<=0:return None
    for limit,factor in zip(BANDS[k],(1,.8,.6)):
        if (v<=limit if k in LOW else v>=limit):return factor
    # Weak band is not a reward for a loss, negative cash flow, or extremely high leverage.
    if k in LOW:return .3 if v<=({'netdebt_ebitda':5,'ev_ebitda':15,'pe':25}[k]) else 0
    return .3 if v>0 else 0

def pb_factor(pb,ref):
    if pb is None or ref is None or min(pb,ref)<=0:return None
    d=pb/ref-1
    for t,f in ((-.30,1),(-.15,.8),(.15,.6),(.30,.3)):
        if d<=t+1e-10:return f
    return .1

def group(s):return 'Cảng khai thác' if s in PORT else 'ICD - Kho bãi - Logistics' if s in LOGISTICS else 'Đặc thù'

def read_rows(path):
    with open(path,encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
    if len(rows)!=len(SYMBOLS) or {r['code'] for r in rows}!=SYMBOLS:raise ValueError('PORT_INVALID_UNIVERSE')
    return {r['code']:r for r in rows}

def evaluate(r,pe,pb,ev,industry,day,mode):
    v={k:num(r,k) for k in BANDS};v.update(pe=pe,pb=pb,ev_ebitda=ev,pb_hist=num(r,'pb_hist'),pb_industry=industry)
    points={k:tier(v[k],k) for k in BANDS}
    p,prior=num(r,'profit'),num(r,'prior_profit')
    if p is not None and p<=0:points['profit_growth']=0;points['pe']=0
    elif p is not None and prior is not None and prior<=0:points['profit_growth']=.6
    if v['interest_cover'] is not None and v['interest_cover']>=1000:pass
    points.update(pb_hist=pb_factor(pb,v['pb_hist']),pb_industry=pb_factor(pb,industry))
    if num(r,'parent_equity') is not None and num(r,'parent_equity')<=0:points['pb_hist']=points['pb_industry']=0
    pts={k:None if points[k] is None else round(points[k]*w,4) for k,w in WEIGHTS.items()}
    coverage=sum(w for k,w in WEIGHTS.items() if pts[k] is not None)
    score=round(sum(pts.values()),2) if coverage==100 else None
    return dict(code=r['code'],v=v,points=pts,factors=points,coverage=coverage,score=score,ranks={},rank=None,count=0,day=day,mode=mode,raw=r,group=group(r['code']))

def rank(results):
    for g in ('Cảng khai thác','ICD - Kho bãi - Logistics'):
        peers=[e for e in results.values() if e['group']==g and e['score'] is not None]
        if len(peers)<3:continue
        for e in peers:
            e['rank']=1+sum(x['score']>e['score'] for x in peers);e['count']=len(peers)
            for k in (*BANDS,'pb'):
                v=e['v'].get(k)
                if v is None or (k in ('pb','pe','ev_ebitda') and v<=0):continue
                a=[x['v'].get(k) for x in peers];a=[n for n in a if n is not None and (k not in ('pb','pe','ev_ebitda') or n>0)]
                if len(a)>=3:e['ranks'][k]=1+sum(n<v if k in LOW else n>v for n in a)
    return results

def snapshot(rows):
    # Screenshot market cap / source CP is a screening proxy, not actual close.
    return rank({s:evaluate(r,num(r,'pe'),num(r,'pb'),num(r,'ev_ebitda'),1.97,ASOF,'snapshot') for s,r in rows.items() if s not in SPECIAL and (num(r,'price_proxy') or 0)>=9000 and (num(r,'volume') or 0)>0})

def stamp(p):
    p=Path(p);st=p.stat();return str(p),st.st_mtime_ns,st.st_size

@lru_cache(maxsize=3)
def cached_rows(i):return read_rows(i[0])

@lru_cache(maxsize=3)
def cached_snapshot(i):return snapshot(cached_rows(i))

def latest_prices(eod,meta):
    meta=json.loads(Path(meta).read_text(encoding='utf-8-sig'));day=pd.Timestamp(meta['latest_date']).normalize()
    if pd.isna(day):raise ValueError('PORT_INVALID_EOD_DATE')
    if day.date().isoformat()<ASOF:raise ValueError('PORT_EOD_BEFORE_SNAPSHOT')
    df=pd.read_csv(eod,usecols=['Mã','Ngày','Giá đóng cửa'],dtype={'Mã':str},encoding='utf-8-sig')
    raw=df['Ngày'].astype(str).str.strip();iso=raw.str.match(r'^\d{4}-\d{2}-\d{2}')
    parsed=pd.to_datetime(raw.where(~iso),format='mixed',dayfirst=True,errors='coerce');parsed.loc[iso]=pd.to_datetime(raw.loc[iso].str[:10],format='%Y-%m-%d',errors='coerce')
    df['Ngày']=parsed.dt.normalize()
    if df['Ngày'].max()!=day:raise ValueError('PORT_META_MISMATCH')
    failed={str(x).split(':',1)[0].strip() for x in meta.get('failed',[])}
    prices={}
    for s,g in df.loc[df['Ngày'].eq(day)&df['Mã'].isin(SYMBOLS)].groupby('Mã'):
        if len(g)!=1 or s in failed:continue
        p=num(g.iloc[0],'Giá đóng cửa')
        if p is not None and p>0:prices[s]=p*1000
    return day.date().isoformat(),prices

def read_shares(path):
    with open(path,encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
    out={};duplicates=set()
    for r in rows:
        s=r['Mã'].strip().upper()
        if s in out:duplicates.add(s)
        out[s]=num(r,'Số CP lưu hành')
    return {s:n for s,n in out.items() if s not in duplicates}

def dynamic(rows,day,prices,shares):
    valuations={}
    if not ASOF<=day<='2027-03-29':return {}
    for s,r in rows.items():
        p=prices.get(s);sh=shares.get(s);ref=num(r,'shares');cur=num(r,'current_shares')
        if s in SPECIAL or p is None or p<9000 or not sh or not ref or not cur or min(sh,ref,cur)<=0:continue
        if {'CAP','SHARES'}&set(r.get('flags','').split('+')) or abs(sh/ref-1)>.01 or abs(sh/cur-1)>.01:continue
        if not r.get('pub') or r['pub']>day:continue
        eq,profit,eb,db,cash,nci=(num(r,k) for k in ('parent_equity','profit','ebitda','debt','cash','nci'))
        cap=p*sh/1e9;pb=ratio(cap,eq)
        if pb is None:continue
        pe=ratio(cap,profit);ev=ratio(cap+db-cash+nci,eb) if all(x is not None for x in (db,cash,nci)) else None
        valuations[s]=(pe,pb,ev)
    if len(valuations)<12:return {}
    industry=sum(x[1] for x in valuations.values())/len(valuations)
    return rank({s:evaluate(rows[s],pe,pb,ev,industry,day,'eod') for s,(pe,pb,ev) in valuations.items()})

@lru_cache(maxsize=3)
def cached_eod(i,e,m,sh):
    day,prices=latest_prices(e[0],m[0]);return day,prices,dynamic(cached_rows(i),day,prices,read_shares(sh[0]))

def state(input_path=PATH,eod=EOD,meta=META,shares=SHARES):
    try:i=stamp(input_path);ref=cached_snapshot(i)
    except (OSError,ValueError,KeyError,TypeError):return {},None,{},{}
    try:day,prices,live=cached_eod(i,stamp(eod),stamp(meta),stamp(shares))
    except (OSError,ValueError,KeyError,TypeError,OverflowError):day,prices,live=None,{},{}
    return ref,day,prices,live

def fmt(v):return '—' if v is None else f'{v:,.2f}'.replace(',','@').replace('.',',').replace('@','.')

def grade(f):return {1:'Rất tốt',.8:'Tốt',.6:'Trung bình',.3:'Yếu',.1:'Cao',0:'Rất yếu'}.get(f,'Thiếu dữ liệu')

def notes(e):
    v=e['v'];r=e['raw'];rank=e['ranks'];group_name=e['group'];out=[]
    # Lead with reference provenance in all three screens, even if only first tags visible.
    out.append('FA tham khảo | BCTC Q3/2026 | '+('EOD ước tính '+e['day'] if e['mode']=='eod' else 'Ảnh định giá 26/11/2026; không phải giá EOD'))
    def top(k):return f' | TOP {rank[k]} {group_name}' if rank.get(k,99)<=5 else ''
    for k in BANDS:
        x=v[k];val='Không phát sinh lãi vay' if k=='interest_cover' and x is not None and x>=1000 else fmt(x)+('%' if k in PCT else ' lần')
        out.append(f'{LABELS[k]} {val} – {grade(e["factors"][k])}'+top(k))
    def cmp(x):return fmt((v['pb']/x-1)*100)+'%' if v['pb'] is not None and x is not None and x>0 else '—'
    out.append(f'P/B {fmt(v["pb"])} lần'+top('pb')+f' | TB 3N (ảnh): {fmt(v["pb_hist"])} ({cmp(v["pb_hist"])}) | TB ngành {fmt(v["pb_industry"])} ({cmp(v["pb_industry"])})')
    if e['rank'] is not None:out.append(f'Hạng tham khảo {e["rank"]}/{e["count"]} {group_name}')
    flags=[FLAG_NAMES[x] for x in r.get('flags','').split('+') if x in FLAG_NAMES]
    if flags:out.insert(1,'Cảnh báo: '+'; '.join(flags))
    return out

def lookup(symbol):
    s=str(symbol).strip().upper();ref,day,prices,live=state()
    if s in SPECIAL:return None,['PORT FA: nhóm đặc thù, không xếp chung.']
    if s in prices and prices[s]<9000:return None,['PORT FA: giá EOD dưới 9.000đ, không xếp hạng.']
    # Never mix current and snapshot ranks; require complete indicators.
    e=live.get(s) if s in live and live[s]['score'] is not None else ref.get(s)
    if not e or e['score'] is None:return None,['PORT FA: chưa đủ dữ liệu hoặc không đạt điều kiện giá/thanh khoản.']
    return e,notes(e)

def for_symbol(symbol):
    e,tags=lookup(symbol);return (e['score'] if e else None),tags

def detail(symbol):
    e,tags=lookup(symbol)
    if not e:return '; '.join(tags)
    return ('PORT FA V1 - chỉ tham khảo, không xếp hạng VIP chính thức. LNST là số báo cáo, chưa chuẩn hóa khoản bất thường. '
            'P/B TB 3N lấy từ ảnh ngày 26/11/2026; cách tính của nguồn ảnh chưa xác minh. '
            'EOD ước tính theo vốn Q3 và CP đối chiếu (chưa xác nhận toàn bộ biến động vốn sau kỳ); EV gồm NCI. '
            'Xếp hạng theo nhóm hoạt động, chỉ mã đủ điểm cùng nguồn định giá; thiếu chỉ tiêu không quy 0. '
            'Nguồn: ZIP BCTC Q3/2026 người dùng cung cấp và ảnh định giá 26/11/2026. '+ '; '.join(tags))

def score_grade(value):
    try:v=float(value)
    except (ValueError,TypeError):return None
    if not math.isfinite(v) or not 0<=v<=100:return None
    return 'A' if v>=75 else 'B' if v>=60 else 'C' if v>=40 else 'D'
