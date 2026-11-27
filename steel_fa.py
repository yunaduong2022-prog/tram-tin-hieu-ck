"""Steel FA V1: report-based reference score, no EOD writes or VIP ranking."""
import csv, math, json
from functools import lru_cache
from pathlib import Path
ROOT=Path(__file__).resolve().parent
PATH=ROOT/'data/steel_fa_inputs.csv'
EOD=ROOT/'data/eod_prices.csv'; META=ROOT/'data/eod_meta.json'; SHARES=ROOT/'data/shares_outstanding.csv'
SYMBOLS=frozenset('HPG TVN TIS POM VGS HSG NKG GDA DTL SMC TLH HMC'.split())
GROUPS={'production':(20,15,10,5),'coating':(15,12,8,5),'trade':(8,6,4,2)}
WEIGHTS={'roe':10,'roa':5,'margin':10,'rev_growth':5,'profit_growth':10,'debt_eq':10,'netdebt_ebitda':10,'interest_cover':5,'cfo_ratio':10,'dio':10,'pb_hist':5,'pb_industry':5,'pe_hist':2.5,'pe_industry':2.5}
LABELS={'roe':'ROE','roa':'ROA','margin':'Biên lợi nhuận gộp','rev_growth':'Tăng trưởng doanh thu TTM','profit_growth':'Tăng trưởng LNST TTM','debt_eq':'Nợ vay/VCSH','netdebt_ebitda':'Nợ vay ròng/EBITDA','interest_cover':'Khả năng trả lãi vay','cfo_ratio':'CFO/LNST','dio':'Số ngày tồn kho'}
PERCENT={'roe','roa','margin','rev_growth','profit_growth','cfo_ratio'}
LOW={'debt_eq','netdebt_ebitda','dio','pb','pe'}
MIN_PEERS=5

def num(r,k):
    try:
        x=float(r.get(k,'')); return x if math.isfinite(x) else None
    except (ValueError,TypeError,OverflowError):return None

def ratio(a,b):return a/b if a is not None and b is not None and b>0 else None

def tier(v,limits,points,reverse=False,default=0):
    if v is None:return None
    return next((p for t,p in zip(limits,points) if (v<=t+1e-10 if reverse else v>=t-1e-10)),default)

def valpoint(v,ref,w):
    if v is None:return None
    if v<=0:return 0
    r=ratio(v,ref)
    f=tier(r,(.7,.9,1.1,1.3,1.5),(1,.8,.6,.4,.2),True)
    return None if f is None else round(f*w,4)

def evaluate(r,pe,pb,sector_pe,sector_pb,mode='snapshot',day=None):
    v={k:num(r,k) for k in ('roe','roa','margin','rev_growth','profit','profit_prev','equity','debt_eq','ebitda','netdebt_ebitda','ebit','interest','cfo','dio','dio_hist','other_pct','da','parent_equity','parent_profit','pb_hist','pe_hist')}
    v.update(pe=pe,pb=pb,sector_pe=sector_pe,sector_pb=sector_pb)
    profit,prior,eq=v['profit'],v['profit_prev'],v['equity']; cfo=v['cfo']; eb=v['ebitda']; it=v['interest']; ebit=v['ebit']
    v['profit_growth']=None if prior is None or prior<=0 or profit is None else (profit/prior-1)*100
    pg=None if profit is None or prior is None else 0 if profit<=0 else 6 if prior<=0 else tier(v['profit_growth'],(30,20,10,0,-10),(10,8,6,4,2))
    v['interest_cover']=ratio(ebit,it)
    v['cfo_ratio']=ratio(cfo,profit)
    p={'roe':0 if eq is not None and eq<=0 else tier(v['roe'],(20,15,10,5,1e-9),(10,8,6,3,1)),
       'roa':tier(v['roa'],(10,7,5,3,1e-9),(5,4,3,2,1)),
       'margin':tier(v['margin'],(*GROUPS[r['group']],1e-9),(10,8,6,4,2)),
       'rev_growth':tier(v['rev_growth'],(30,20,10,0,-10),(5,4,3,2,1)), 'profit_growth':pg,
       'debt_eq':0 if eq is not None and eq<=0 else tier(v['debt_eq'],(.3,.6,1,1.5,2),(10,8,6,3,1),True),
       'netdebt_ebitda':0 if eb is not None and eb<=0 else tier(v['netdebt_ebitda'],(1,2,3,4,5),(10,8,6,3,1),True),
       'interest_cover':None if it is None or ebit is None or it<0 else (5 if ebit>0 else 0) if it==0 else tier(v['interest_cover'],(8,5,3,1.5,1),(5,4,3,2,1)),
       'cfo_ratio':None if cfo is None or profit is None else (4 if cfo>0 else 0) if profit<=0 else tier(v['cfo_ratio'],(1,.8,.5,.2,0),(10,8,6,4,2)),
       'dio':tier(ratio(v['dio'],v['dio_hist']),(.8,1,1.2,1.4,1.6),(10,8,6,4,2),True),
       'pb_hist':valpoint(pb,v['pb_hist'],5), 'pb_industry':valpoint(pb,sector_pb,5),
       'pe_hist':valpoint(pe,v['pe_hist'],2.5), 'pe_industry':valpoint(pe,sector_pe,2.5)}
    if v['parent_equity'] is not None and v['parent_equity']<=0:p.update(pb_hist=0,pb_industry=0)
    if v['parent_profit'] is not None and v['parent_profit']<=0:p.update(pe_hist=0,pe_industry=0)
    warnings=[]
    if eq is not None and eq<=0:warnings.append('Vốn chủ sở hữu không dương')
    if profit is not None and profit<=0:warnings.append('LNST TTM không dương')
    if cfo is not None and cfo<0:warnings.append('CFO TTM âm')
    if v['netdebt_ebitda'] is not None and v['netdebt_ebitda']>5:warnings.append('Nợ ròng/EBITDA trên 5 lần')
    if eb is not None and eb<=0:warnings.append('EBITDA không dương')
    if v['other_pct'] is not None and v['other_pct']>=30:warnings.append('Thu nhập khác từ 30% LNST; chưa chuẩn hóa lợi nhuận')
    if v['da'] is not None and v['da']<0:warnings.append('Khấu hao âm; cần xác minh EBITDA')
    if pe is not None and pe>0 and (v['pe_hist'] is None or v['pe_hist']<=0):warnings.append('P/E TB 3 năm không hợp lệ')
    coverage=sum(w for k,w in WEIGHTS.items() if p[k] is not None)
    subtotal=round(sum(x for x in p.values() if x is not None),2)
    return dict(code=r['code'],raw=r,v=v,points=p,coverage=coverage,subtotal=subtotal,score=subtotal if coverage==100 else None,ranks={},warnings=warnings,mode=mode,day=day,rank_count=0)

def read_rows(path):
    with open(path,encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
    if len(rows)!=len(SYMBOLS) or {r['code'] for r in rows}!=SYMBOLS:raise ValueError('STEEL_INVALID_UNIVERSE')
    return {r['code']:r for r in rows}

def rank(results):
    eligible=[e for e in results.values() if e['score'] is not None and (e['v']['equity'] or 0)>0 and not (num(e['raw'],'other_pct') or 0)>=30]
    for e in eligible:
        e['rank_count']=len(eligible)
        for k in (*LABELS,'pb','pe'):
            # Margin and DIO are compared within the same business model only.
            peers=[x for x in eligible if k not in ('margin','dio') or x['raw']['group']==e['raw']['group']]
            peers=[x for x in peers if k not in ('roe','debt_eq') or (x['v']['equity'] or 0)>0]
            if k in ('roe','debt_eq') and (e['v']['equity'] or 0)<=0:continue
            a=[x['v'].get(k) for x in peers]; a=[x for x in a if x is not None and (k not in ('pb','pe') or x>0)]
            v=e['v'].get(k)
            if len(a)>=5 and v is not None and (k not in ('pe','pb') or v>0):e['ranks'][k]=1+sum(x<v if k in LOW else x>v for x in a)
    return results

def snapshot(rows):
    return rank({s:evaluate(r,num(r,'pe'),num(r,'pb'),6.45,1.03) for s,r in rows.items()})

def dynamic(rows,day,prices,shares):
    vals={}
    if not '2026-11-27'<=day<='2027-03-31':return {}
    for s,r in rows.items():
        px=prices.get(s);sh=shares.get(s);ref=num(r,'shares_m');eq=num(r,'parent_equity');p=num(r,'parent_profit')
        if px is None or px<=0 or sh is None or sh<=0 or not ref or abs(sh/(ref*1e6)-1)>.01 or not r.get('pub') or r['pub']>day:continue
        cap=px*sh/1e9
        vals[s]=(cap/p if p is not None and p!=0 else None,cap/eq if eq is not None and eq!=0 else None,cap,p,eq)
    pes=[x for x in vals.values() if x[0] is not None and x[0]>0];pbs=[x for x in vals.values() if x[1] is not None and x[1]>0]
    if min(len(pes),len(pbs))<MIN_PEERS:return {}
    # Market-cap aggregate over positive denominators, not arithmetic average of multiples.
    spe=sum(x[2] for x in pes)/sum(x[3] for x in pes);spb=sum(x[2] for x in pbs)/sum(x[4] for x in pbs)
    return rank({s:evaluate(rows[s],x[0],x[1],spe,spb,'eod',day) for s,x in vals.items()})

def stamp(p):
    p=Path(p);s=p.stat();return str(p),s.st_mtime_ns,s.st_size

@lru_cache(maxsize=3)
def ref_cached(i):return snapshot(read_rows(i[0]))

def latest_prices(eod,meta):
    import pandas as pd
    m=json.loads(Path(meta).read_text(encoding='utf-8-sig')); day=pd.Timestamp(m['latest_date']).normalize()
    if pd.isna(day):raise ValueError('STEEL_INVALID_EOD_DATE')
    from datetime import datetime, timezone, timedelta
    if day.date()>datetime.now(timezone(timedelta(hours=7))).date():raise ValueError('STEEL_FUTURE_EOD')
    df=pd.read_csv(eod,usecols=['Mã','Ngày','Giá đóng cửa'],dtype={'Mã':str},encoding='utf-8-sig')
    raw=df['Ngày'].astype(str).str.strip();iso=raw.str.match(r'^\d{4}-\d{2}-\d{2}')
    parsed=pd.to_datetime(raw.where(~iso),format='mixed',dayfirst=True,errors='coerce');parsed.loc[iso]=pd.to_datetime(raw.loc[iso].str[:10],format='%Y-%m-%d',errors='coerce')
    df['Ngày']=parsed.dt.normalize()
    if df['Ngày'].max()!=day:raise ValueError('STEEL_META_MISMATCH')
    failed={str(x).split(':',1)[0].strip() for x in m.get('failed',[])};prices={}
    for s,g in df.loc[df['Ngày'].eq(day)&df['Mã'].isin(SYMBOLS)].groupby('Mã'):
        if len(g)!=1 or s in failed:continue
        px=num(g.iloc[0],'Giá đóng cửa')
        if px is not None and px>0:prices[s]=px*1000
    return day.date().isoformat(),prices

@lru_cache(maxsize=3)
def eod_cached(i,e,m,sh):
    from port_fa import read_shares
    day,prices=latest_prices(e[0],m[0]);shares=read_shares(sh[0]);return day,prices,dynamic(read_rows(i[0]),day,prices,shares)

def lookup(symbol):
    s=str(symbol).strip().upper()
    if s not in SYMBOLS:return None,[]
    try:i=stamp(PATH);ref=ref_cached(i)
    except (OSError,ValueError,KeyError,TypeError):return None,['FA Thép: thiếu dữ liệu đầu vào']
    try:day,prices,live=eod_cached(i,stamp(EOD),stamp(META),stamp(SHARES))
    except (OSError,ValueError,KeyError,TypeError,OverflowError):day,prices,live=None,{},{}
    if s in prices and prices[s]<9000:return None,['FA Thép: giá EOD dưới 9.000đ; không xếp hạng theo dõi']
    e=live.get(s) or ref.get(s)
    return e,notes(e) if e else []

def fmt(v):return '—' if v is None else f'{v:,.2f}'.replace(',','@').replace('.',',').replace('@','.')
def cmp(v,ref):
    q=ratio(v,ref)
    if q is None or q<=0:return 'Không áp dụng'
    d=(q-1)*100;return ('Thấp hơn ' if d<0 else 'Cao hơn ' if d>0 else 'Bằng ')+fmt(abs(d))+'%'

def notes(e):
    v,p=e['v'],e['points'];out=['FA tham khảo | Thép | BCTC '+e['raw']['period']+' | '+('EOD ước tính '+e['day'] if e['mode']=='eod' else 'Nguồn định giá cập nhật 27/11/2026; chưa xác nhận phiên giá')]
    def top(k):return f' | TOP {e["ranks"][k]} Nhóm thép khảo sát' if e['ranks'].get(k,99)<=5 else ''
    def label(k):
        if p[k] is None:return 'Thiếu dữ liệu'
        f=p[k]/WEIGHTS[k];return 'Rất tốt' if f>=.9 else 'Tốt' if f>=.75 else 'Khá' if f>=.6 else 'Trung bình' if f>=.4 else 'Yếu' if f>0 else 'Rất yếu'
    for k,n in LABELS.items():
        x=v[k];val=fmt(x*100 if k=='cfo_ratio' and x is not None else x)+('%' if k in PERCENT else ' ngày' if k=='dio' else ' lần')
        if k=='profit_growth' and x is None and v['profit'] is not None and v['profit_prev'] is not None:val='Phục hồi từ lỗ' if v['profit']>0 else 'Thua lỗ/hòa vốn'
        if k=='cfo_ratio' and v['profit'] is not None and v['profit']<=0:val='CFO '+fmt(v['cfo'])+' tỷ; LNST không dương'
        if k=='interest_cover' and v['interest']==0:val='Không phát sinh lãi vay'
        if k=='dio':val+=' | TB 3 năm '+fmt(v['dio_hist'])+' ngày'
        out.append(f'{n} {val} – {label(k)} | {fmt(p[k])}/{WEIGHTS[k]}'+top(k))
    for k in ('pb','pe'):
        a,b=v[k+'_hist'],v['sector_'+k];x=v[k];n=k.upper()[0]+'/'+k.upper()[1]
        points=[p[k+'_hist'],p[k+'_industry']];score=sum(t for t in points if t is not None);maximum=WEIGHTS[k+'_hist']+WEIGHTS[k+'_industry'];sector='TB nhóm EOD' if e['mode']=='eod' else 'TB ngành (ảnh)'
        out.append(f'{n} {fmt(x)} lần | TB 3 năm: {fmt(a)} ({cmp(x,a)}) | {sector}: {fmt(b)} ({cmp(x,b)}) | {fmt(score)}/{maximum}'+(' (thiếu tham chiếu)' if None in points else '')+top(k))
    if e['score'] is None:out.insert(0,f'Chưa đủ dữ liệu FA: {fmt(e["subtotal"])}/{fmt(e["coverage"])} điểm khả dụng; không xếp loại')
    if e['warnings']:out.append('Rủi ro: '+'; '.join(e['warnings']))
    out.append('Định giá: '+('EOD ước tính '+e['day'] if e['mode']=='eod' else 'nguồn cập nhật 27/11/2026; chưa xác nhận phiên giá'))
    return out



def compact_notes(tags):
    # Keep complete notes for detail; shorten only the shared main cards.
    import re
    out=[]
    for raw in tags or []:
        t=str(raw)
        if t.startswith(('FA tham khảo | Thép |','Định giá:')):
            continue
        # Keep incomplete coverage and warnings, including their numeric data.
        if t.startswith(('Rủi ro:', 'Chưa đủ dữ liệu FA:', 'FA Thép:')):
            out.append(t);continue
        t=re.sub(r' \| (?:\d[\d.,]*|—)/\d+(?:\.\d+)?(?= \| TOP | \(thiếu tham chiếu\)|$)', '', t)
        t=t.replace(' Nhóm thép khảo sát',' nhóm khảo sát')
        t=t.replace('Tăng trưởng doanh thu TTM','Tăng trưởng DT').replace('Tăng trưởng LNST TTM','Tăng trưởng LNST')
        t=t.replace('Nợ vay ròng/EBITDA','Nợ ròng/EBITDA').replace('Số ngày tồn kho','Tồn kho')
        t=t.replace('TB ngành (ảnh):','TB ngành:')
        t=t.replace(' lần','x') if t.startswith(('P/B ','P/E ','Nợ vay/VCSH ','Nợ ròng/EBITDA ','Khả năng trả lãi vay ')) else t
        out.append(t)
    return out


def for_symbol(symbol):
    e,tags=lookup(symbol);return (e['score'] if e else None),tags

def detail(symbol):
    e,tags=lookup(symbol)
    return ('STEEL FA V2 – tham khảo, không xếp hạng VIP chính thức. 12 mã đã phân nhóm; không đại diện toàn bộ 32 mã trong ảnh. '
            'BCTC quý từ ZIP, TTM 4 quý; ROE/ROA dùng LNST hợp nhất và bình quân đầu/cuối kỳ; DIO TB 12 kỳ TTM; nợ ròng trừ tiền và tương đương tiền; EBIT = LNTT + lãi vay. '
            'P/E P/B lịch sử và mốc ngành 6,45/1,03 lấy từ ảnh nguồn cập nhật 27/11/2026; chưa xác nhận phiên giá/phương pháp. EOD dùng vốn và lợi nhuận công ty mẹ, số CP đối chiếu; trung bình nhóm EOD theo vốn hóa/tổng mẫu số dương (tối thiểu 5 mã mỗi tỷ số), không phải toàn ngành. '
            'Thiếu dữ liệu không quy 0; lợi nhuận chưa chuẩn hóa. '+ '; '.join(tags))
