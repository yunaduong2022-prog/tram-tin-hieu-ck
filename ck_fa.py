"""FA chứng khoán: 40 mã, 100 điểm, BCTC Q3/2026; đọc EOD, không ghi giá/API."""
from pathlib import Path
from functools import lru_cache
import csv, math, json
import pandas as pd
ROOT=Path(__file__).resolve().parent
PATH=ROOT/'data/ck_fa_inputs.csv'
EOD=ROOT/'data/eod_prices.csv'
META=ROOT/'data/eod_meta.json'
SYMBOLS=frozenset('VPX BSI HCM SSI TCX FTS VND MBS VDS ABW VCK VCI AGR BVS VFS DSE CTS PSI VIX DSC SBS SHS ORS BMS VUA PHS EVS IVS TVS TCI TVB APS UPS AAS HAC VIG APG CSI LPS WSS'.split())
WEIGHTS={'ROE':20,'ROA':5,'Tăng trưởng DT':5,'Tăng trưởng LNST':10,'Biên LNR':10,'VCSH/TTS':15,'Nợ vay/VCSH':10,'Margin/VCSH':10,'P/B lịch sử':5,'P/B ngành':5,'P/E':5}
MIN_PEERS=24
FIELDS={'ROE':'ROE TTM (%)','ROA':'ROA TTM (%)','Tăng trưởng DT':'Tăng trưởng doanh thu TTM (%)','Biên LNR':'Biên LNR TTM (%)','VCSH/TTS':'VCSH/TTS (%)','Nợ vay/VCSH':'Nợ vay/VCSH (lần)','Margin/VCSH':'Margin/VCSH (%)','P/B TB':'P/B tham chiếu lịch sử dùng FA','LNST':'LNST CĐ công ty mẹ TTM (tỷ)','LNST trước':'LNST CĐ công ty mẹ TTM trước (tỷ)'}
def num(r,k):
    try:
        v=float(r.get(k,'')); return v if math.isfinite(v) else None
    except (ValueError,TypeError):return None

def fmt(v,d=2):return '—' if v is None else f'{v:,.{d}f}'.replace(',','@').replace('.',',').replace('@','.')

def tier(v,limits,points,reverse=False):
    if v is None:return None
    return next((p for t,p in zip(limits,points) if (v<=t if reverse else v>=t)),0)

def pb_factor(v,ref):
    if v is None or ref is None or v<=0 or ref<=0:return None
    d=v/ref-1
    for t,p in [(-.30,1),(-.15,.8),(.15,.6),(.30,.3)]:
        if d<=t+1e-12:return p
    return .1

def margin_factor(v):
    if v is None or v<0:return None
    return .6 if v<30 else .8 if v<60 else 1 if v<=120 else .8 if v<=150 else .4 if v<=180 else .2 if v<=200 else 0

def growth(now,prior):
    if now is None or prior is None:return None,None,'Thiếu dữ liệu'
    if now<=0:return 0,None,'Thua lỗ/hòa vốn'
    if prior<=0:return .6,None,'Phục hồi từ lỗ/hòa vốn'
    g=(now/prior-1)*100
    return tier(g,(30,15,5,0),(1,.8,.6,.3)),g,''

def grade(s):return 'Chưa đủ dữ liệu' if s is None else 'A – Tốt' if s>=75 else 'B – Khá' if s>=60 else 'C – Trung bình' if s>=40 else 'D – Yếu'

def evaluate(r,pb,pe,industry):
    v={k:num(r,c) for k,c in FIELDS.items()};v.update({'P/B':pb,'P/E':pe})
    n=int(num(r,'Số quý tham chiếu FA') or 0)
    g,v['Tăng trưởng LNST'],gs=growth(v['LNST'],v['LNST trước'])
    eq=num(r,'VCSH (tỷ)');positive=eq is not None and eq>0
    def standard(k,limits):return tier(v[k],limits,(1,.8,.6,.3))
    def lev(k,limits):
        return (0 if eq<=0 else tier(v[k],limits,(1,.8,.6,.4,.2),True) if v[k] is not None and v[k]>=0 else None) if eq is not None else None
    hist=pb_factor(pb,v['P/B TB']) if n>=2 else (.6 if r['Mã']=='LPS' and n==1 and pb is not None and pb>0 else None)
    p={'ROE':standard('ROE',(18,14,10,5)) if positive else (0 if eq is not None else None),'ROA':standard('ROA',(8,6,4,2)),'Tăng trưởng DT':standard('Tăng trưởng DT',(30,15,5,0)),'Tăng trưởng LNST':g,'Biên LNR':standard('Biên LNR',(40,30,20,10)), 'VCSH/TTS':tier(v['VCSH/TTS'],(50,40,30,20,10),(1,.8,.6,.4,.2)), 'Nợ vay/VCSH':lev('Nợ vay/VCSH',(.5,1,1.5,2,3)), 'Margin/VCSH':margin_factor(v['Margin/VCSH']) if positive else (0 if eq is not None else None), 'P/B lịch sử':hist if positive else (0 if eq is not None else None), 'P/B ngành':pb_factor(pb,industry) if positive else (0 if eq is not None else None), 'P/E':0 if v['LNST'] is not None and v['LNST']<=0 else (tier(pe,(8,12,18,25),(1,.8,.6,.3),True) if pe is not None and pe>0 else None)}
    if pe is not None and pe>25 and v['LNST'] is not None and v['LNST']>0:p['P/E']=.1
    points={k:None if p[k] is None else round(p[k]*w,6) for k,w in WEIGHTS.items()}
    coverage=sum(w for k,w in WEIGHTS.items() if points[k] is not None)
    score=round(sum(points.values()),2) if coverage==100 else None
    warn=[]
    if v['Margin/VCSH'] is not None and v['Margin/VCSH']>200:warn.append('Margin/VCSH trên 200% theo BCTC; cần đối chiếu cơ sở pháp lý')
    elif v['Margin/VCSH'] is not None and v['Margin/VCSH']>150:warn.append('Dư địa margin hạn chế')
    if v['Nợ vay/VCSH'] is not None and v['Nợ vay/VCSH']>2:warn.append('Nợ vay cao')
    if eq is not None and eq<=0:warn.append('VCSH không dương')
    if v['LNST'] is not None and v['LNST']<=0:warn.append('LNST TTM không dương')
    diff=num(r,'Chênh lệch CP (%)')
    if diff is not None and abs(diff)>1:warn.append('CP tham chiếu lệch vốn góp Q3')
    return {'code':r['Mã'],'raw':r,'v':v,'p':p,'points':points,'coverage':coverage,'score':score,'grade':grade(score),'industry':industry,'history_n':n,'growth_state':gs,'warnings':warn,'ranks':{},'rank':None}

METRICS=('ROE','ROA','Tăng trưởng DT','Tăng trưởng LNST','Biên LNR','VCSH/TTS','Nợ vay/VCSH','P/B','P/E')
def rank(rows):
    for k in METRICS:
        eligible={s:e['v'][k] for s,e in rows.items() if e['v'][k] is not None and (k not in ('P/B','P/E') or e['v'][k]>0) and (k not in ('ROE','Nợ vay/VCSH','P/B') or (num(e['raw'],'VCSH (tỷ)') or 0)>0) and (k!='P/E' or (e['v']['LNST'] or 0)>0)}
        low=k in ('Nợ vay/VCSH','P/B','P/E')
        for s,v in eligible.items():rows[s]['ranks'][k]=1+sum((x<v if low else x>v) for x in eligible.values())
    for e in rows.values():
        if e['score'] is not None:e['rank']=1+sum(x['score'] is not None and x['score']>e['score'] for x in rows.values())
    return rows

def read_rows(path):
    with open(path,encoding='utf-8-sig',newline='') as f: rows=list(csv.DictReader(f))
    if len(rows)!=40 or {r['Mã'] for r in rows}!=SYMBOLS:raise ValueError('CK_FA_INVALID_UNIVERSE')
    return {r['Mã']:r for r in rows}

def snapshot(rows):
    pbs=[num(r,'P/B Q3 nguồn') for r in rows.values() if (num(r,'VCSH (tỷ)') or 0)>0];pbs=[x for x in pbs if x is not None and x>0]
    industry=sum(pbs)/len(pbs) if pbs else None
    return rank({s:evaluate(r,num(r,'P/B Q3 nguồn'),num(r,'P/E Q3 nguồn'),industry) for s,r in rows.items()})

def latest_prices(eod,meta):
    day=pd.Timestamp(json.loads(Path(meta).read_text(encoding='utf-8-sig'))['latest_date']).normalize()
    if pd.isna(day):raise ValueError('INVALID_EOD_DATE')
    df=pd.read_csv(eod,usecols=['Mã','Ngày','Giá đóng cửa'],dtype={'Mã':str},encoding='utf-8-sig')
    raw=df['Ngày'].astype(str).str.strip();iso=raw.str.match(r'^\d{4}-\d{2}-\d{2}')
    parsed=pd.to_datetime(raw.where(~iso),format='mixed',dayfirst=True,errors='coerce');parsed.loc[iso]=pd.to_datetime(raw.loc[iso].str[:10],format='%Y-%m-%d',errors='coerce')
    df['Ngày']=parsed.dt.normalize()
    if df['Ngày'].max()!=day:raise ValueError('EOD_META_MISMATCH')
    prices={}
    for s,g in df.loc[df['Ngày'].eq(day)&df['Mã'].isin(SYMBOLS)].groupby('Mã'):
        if len(g)!=1:continue
        px=num(g.iloc[0],'Giá đóng cửa')
        if px is not None and px>0:prices[s]=px*1000
    return day.date().isoformat(),prices

def build(rows,day,prices):
    valuations={}
    for s,r in rows.items():
        px=prices.get(s);bv=num(r,'BVPS tham chiếu (đ)');eps=num(r,'EPS TTM tham chiếu (đ)')
        if px is None or not math.isfinite(px) or px<=0 or bv is None or bv<=0 or eps is None or not r.get('Ngày công bố nguồn') or r['Ngày công bố nguồn'][:10]>day:continue
        valuations[s]=(px/bv,px/eps if eps!=0 else None,px)
    n=len(valuations)
    if n<MIN_PEERS:return {'day':day,'results':{},'prices':valuations,'peers':n,'reason':'Chưa đủ 24 mã cùng phiên'}
    industry=sum(x[0] for x in valuations.values())/n
    return {'day':day,'results':rank({s:evaluate(rows[s],x[0],x[1],industry) for s,x in valuations.items()}),'prices':valuations,'peers':n,'reason':''}

def stamp(path):
    p=Path(path);s=p.stat();return str(p),s.st_mtime_ns,s.st_size
@lru_cache(maxsize=3)
def cached_snapshot(i):return snapshot(read_rows(i[0]))
@lru_cache(maxsize=3)
def cached(i,e,m):
    rows=read_rows(i[0]);day,prices=latest_prices(e[0],m[0]);return build(rows,day,prices)

def load(input_path=PATH,eod=EOD,meta=META):
    try:return cached(stamp(input_path),stamp(eod),stamp(meta))
    except (OSError,ValueError,KeyError,TypeError,OverflowError):return {'day':None,'results':{},'prices':{},'peers':0,'reason':'EOD chưa hợp lệ'}

def notes(e,state=None):
    v=e['v'];p=e['p'];out=[]
    def top(k):return f' | TOP {e["ranks"][k]} Ngành Chứng khoán' if state and e['ranks'].get(k,99)<=5 else ''
    def label(f):return {1:'Rất tốt',.8:'Tốt',.6:'Trung bình',.3:'Yếu',0:'Rất yếu'}.get(f,'Thiếu dữ liệu')
    for k,n in [('ROE','ROE'),('ROA','ROA'),('Biên LNR','Biên lợi nhuận ròng TTM'),('Tăng trưởng DT','Tăng trưởng doanh thu TTM'),('Tăng trưởng LNST','Tăng trưởng LNST TTM')]:
        out.append(n+' – '+e['growth_state'] if k=='Tăng trưởng LNST' and e['growth_state'] else f'{n} {fmt(v[k])}% – {label(p[k])}'+top(k))
    out.append(f'VCSH/Tổng tài sản {fmt(v["VCSH/TTS"])}% – '+{1:'Rất tốt',.8:'Tốt',.6:'Khá',.4:'Trung bình',.2:'Yếu',0:'Rủi ro cao'}.get(p['VCSH/TTS'],'Thiếu dữ liệu')+f' | {fmt(e["points"]["VCSH/TTS"],0)}/15 điểm'+top('VCSH/TTS'))
    out.append(f'Nợ vay/VCSH {fmt(v["Nợ vay/VCSH"])} lần – '+{1:'Rất an toàn',.8:'An toàn',.6:'Trung bình',.4:'Khá cao',.2:'Cao',0:'Rủi ro cao'}.get(p['Nợ vay/VCSH'],'Thiếu dữ liệu')+top('Nợ vay/VCSH'))
    m=v['Margin/VCSH'];ml='Thiếu dữ liệu' if m is None else 'Khai thác thấp' if m<30 else 'Còn dư địa' if m<60 else 'Cân bằng' if m<=120 else 'Khai thác cao' if m<=150 else 'Dư địa hạn chế' if m<=180 else 'Gần giới hạn' if m<=200 else 'Cần đối chiếu'
    out.append(f'Margin/VCSH {fmt(m)}% – {ml} | {fmt(e["points"]["Margin/VCSH"],0)}/10 điểm')
    def cmp(ref):
        if ref is None or ref<=0 or v['P/B'] is None:return '—'
        d=(v['P/B']/ref-1)*100;return ('Thấp hơn ' if d<0 else 'Cao hơn ' if d>0 else 'Bằng ') +fmt(abs(d))+'%'
    hist=f'TB 3 năm (12 quý): {fmt(v["P/B TB"])} ({cmp(v["P/B TB"])})' if e['history_n']==12 else f'TB {e["history_n"]} quý: {fmt(v["P/B TB"])} ({cmp(v["P/B TB"])})' if e['history_n']>=2 else 'Lịch sử 1 quý – trung tính 3/5 điểm'
    peers=f' ({state["peers"]}/40 mã)' if state else ' (tham chiếu Q3)'
    out.append(f'P/B {fmt(v["P/B"])} lần'+top('P/B')+f' | {hist} | TB ngành{peers}: {fmt(e["industry"])} ({cmp(e["industry"])})')
    out.append(f'P/E {fmt(v["P/E"])} lần – '+('LNST không dương' if (v['LNST'] or 0)<=0 else {1:'Định giá thấp',.8:'Hấp dẫn',.6:'Hợp lý',.3:'Khá cao',.1:'Cao'}.get(p['P/E'],'Thiếu dữ liệu'))+top('P/E'))
    if state:
        count=sum(x['score'] is not None for x in state['results'].values());last=f'Hạng {e["rank"]}/{count} Ngành Chứng khoán | BCTC Q3/2026 | Định giá EOD {state["day"]} (ước tính)'
    else:last='FA tham chiếu Q3/2026 – thiếu định giá EOD đủ điều kiện; không xếp hạng EOD'
    if e['warnings']:last='Cảnh báo: '+'; '.join(e['warnings'])+' | '+last
    out.append(last)
    return out

def for_symbol(symbol):
    s=str(symbol).strip().upper();state=load();e=state['results'].get(s)
    if e and e['score'] is not None:return e['score'],notes(e,state)
    try:e=cached_snapshot(stamp(PATH)).get(s)
    except (OSError,ValueError,KeyError,TypeError):return None,[]
    return (e['score'],notes(e)) if e else (None,[])

def detail(symbol):
    s=str(symbol).upper().strip();state=load();e=state['results'].get(s)
    if not e or e['score'] is None:return 'FA tham chiếu Q3/2026; '+(state['reason'] or 'Mã thiếu EOD cùng phiên')+'. Không xếp hạng chung với EOD.'
    r=e['raw'];return f'Giá EOD {state["day"]}: {fmt(state["prices"][s][2],0)} đ; EPS TTM tham chiếu {fmt(num(r,"EPS TTM tham chiếu (đ)"),0)} đ; BVPS {fmt(num(r,"BVPS tham chiếu (đ)"),0)} đ. P/B và P/E = giá/BVPS hoặc EPS. EPS dùng LNST công ty mẹ/CP tham chiếu, không phải EPS bình quân gia quyền. P/B lịch sử theo ZIP; LPS 1 quý áp dụng trung tính. Chưa điều chỉnh biến động vốn sau kỳ. Không chấm vốn khả dụng. Margin/VCSH tính từ BCTC, không phải kết luận tuân thủ. Nguồn: '+r['Nguồn']
