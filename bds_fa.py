"""FA chung cho 33 mã BĐS, snapshot Q3/2026; không phụ thuộc nguồn giá/API."""
from pathlib import Path
from functools import lru_cache
import csv, math

PATH = Path(__file__).resolve().parent / 'data' / 'bds_fa_inputs.csv'
SYMBOLS = frozenset('VHM NVL KDH DXG DIG PDR NLG TCH AGG NTL HQC SGR HPX HDC LDG NBB SCR QCG VPI CEO KBC IDC SZC BCM IJC VGC VRE DXS CRE VIC HDG HTN HHS'.split())
WEIGHTS = {'ROE':10,'ROA':5,'Biên LNG':10,'Tăng trưởng LNST':10,'Nợ vay/VCSH':15,'CFO':15,'HTK':10,'MNTTT':10,'P/B lịch sử':5,'P/B ngành':5,'P/E':5}
FIELDS = {'ROE':'ROE TTM đã xác minh (%)','ROA':'ROA TTM đã xác minh (%)','Biên LNG':'Biên LNG TTM (%)','Nợ vay/VCSH':'Nợ vay/VCSH (lần)','P/B':'P/B dùng FA kỳ Q3 ZIP','P/B TB':'P/B TB 3N dùng FA ZIP','P/E':'P/E dùng FA kỳ Q3 ZIP','LNST':'LNST TTM (tỷ đồng)','LNST trước':'LNST TTM kỳ trước (tỷ đồng)','VCSH':'VCSH Q3 (tỷ)','CFO TTM':'CFO TTM'}

def number(row,key):
    try:
        n=float(row.get(key,'')); return n if math.isfinite(n) else None
    except (TypeError,ValueError): return None

def fmt(n,d=2):
    return '—' if n is None else f'{n:,.{d}f}'.replace(',','@').replace('.',',').replace('@','.')

def levels(v, thresholds, reverse=False):
    if v is None: return None
    for t,p in zip(thresholds,(1,.8,.6,.3)):
        if (v<=t if reverse else v>=t): return p
    return 0

def pb_level(v,b):
    if v is None or b is None or v<=0 or b<=0: return None
    d=v/b-1
    if d<=-.30+1e-12:return 1
    if d<=-.15+1e-12:return .8
    if d<=.15+1e-12:return .6
    if d<=.30+1e-12:return .3
    return .1

def growth(now,prev):
    if now is None or prev is None:return None,None,'Thiếu dữ liệu'
    if now<=0:return 0,None,'Thua lỗ/hòa vốn'
    if prev<=0:return .6,None,'Phục hồi từ lỗ/hòa vốn'
    v=(now/prev-1)*100
    return levels(v,(30,15,5,0)),v,None

def cfo_level(vals):
    if any(v is None for v in vals):return None
    n=sum(v>0 for v in vals); net=sum(vals)
    return {3:1,2:(.8 if net>0 else .4),1:(.6 if net>0 else .2),0:0}[n]

def grade(score):
    return 'Chưa đủ dữ liệu' if score is None else 'A – Tốt' if score>=75 else 'B – Khá' if score>=60 else 'C – Trung bình' if score>=40 else 'D – Yếu'

def label(p):
    return {1:'Rất tốt',.8:'Tốt',.6:'Trung bình',.3:'Yếu',.1:'Rất yếu',0:'Rất yếu'}.get(p,'Chưa đủ dữ liệu')

def val_label(p):
    return {1:'Định giá thấp',.8:'Hấp dẫn',.6:'Hợp lý',.3:'Khá cao',.1:'Cao',0:'Cao'}.get(p,'Chưa đủ dữ liệu')

def change_pct(now,old):
    return (now/old-1)*100 if now is not None and old is not None and old>0 else None


def project_metrics(row):
    inv,assets=number(row,'HTK ròng Q3 (tỷ)'),number(row,'Tổng tài sản Q3 (tỷ)')
    adv=number(row,'Người mua trả tiền trước NH Q3/2026 (tỷ)')
    prior=number(row,'Người mua trả tiền trước NH Q3/2025 (tỷ)')
    valid=assets is not None and assets>0 and inv is not None and inv>=0
    ir=inv/assets*100 if valid else None
    ar=adv/assets*100 if valid and adv is not None and adv>=0 else None
    cov=adv/inv*100 if ar is not None and inv>0 else None
    ag=change_pct(adv,prior) if adv is not None and adv>=0 else None
    neutral=ir is not None and ar is not None and ir<10 and ar<1
    ip=levels(ir,(20,40,60,75),True)
    ap=None; cp=None; gp=None
    if ar is not None and prior is not None and prior>=0:
        if neutral:ap=.6
        else:
            cp=levels(cov,(50,30,15,5)) if cov is not None else .6
            gp=levels(ag,(30,15,0,-20)) if ag is not None else (.6 if adv>0 else 0)
            ap=(cp+gp)/2
    return {'HTK/TTS':ir,'MNTTT/HTK':cov,'MNTTT YoY':ag,'HTK YoY':change_pct(inv,number(row,'HTK ròng Q3/2025 (tỷ)')),
            'HTK QoQ':change_pct(inv,number(row,'HTK ròng Q2/2026 (tỷ)')),'MNTTT QoQ':change_pct(adv,number(row,'Người mua trả tiền trước NH Q2/2026 (tỷ)')),
            'HTK tỷ':inv,'MNTTT tỷ':adv,'MNTTT/TTS':ar,'neutral':neutral,'inventory_factor':ip,'advance_factor':ap,'coverage_factor':cp,'growth_factor':gp}


def evaluate(row,industry):
    v={k:number(row,f) for k,f in FIELDS.items()}; cfo=[number(row,f'CFO {y}') for y in (2023,2024,2025)]
    g,gval,gstate=growth(v['LNST'],v['LNST trước']); v['Tăng trưởng LNST']=gval
    equity=v['VCSH']; valid_equity=equity is not None and equity>0
    debt=v['Nợ vay/VCSH']; pb=v['P/B']; pe=v['P/E']; pbh=v['P/B TB']
    p={'ROE':levels(v['ROE'],(18,12,8,5)) if valid_equity else (0 if equity is not None else None),'ROA':levels(v['ROA'],(8,5,3,1)),'Biên LNG':levels(v['Biên LNG'],(40,30,20,10)),'Tăng trưởng LNST':g,'Nợ vay/VCSH':levels(debt,(.3,.5,1,1.5),True) if valid_equity and debt is not None and debt>=0 else (0 if equity is not None and equity<=0 else None),'CFO':cfo_level(cfo),'P/B lịch sử':pb_level(pb,pbh) if valid_equity else (0 if equity is not None else None),'P/B ngành':pb_level(pb,industry) if valid_equity else (0 if equity is not None else None),'P/E':(0 if v['LNST'] is not None and v['LNST']<=0 else levels(pe,(8,12,18,25),True) if pe is not None and pe>0 else None)}
    project=project_metrics(row)
    p.update({'HTK':project['inventory_factor'],'MNTTT':project['advance_factor']})
    v.update({k:project[k] for k in ('HTK/TTS','MNTTT/HTK','MNTTT YoY')})
    points={k:(None if p[k] is None else round(p[k]*w,6)) for k,w in WEIGHTS.items()}
    coverage=sum(w for k,w in WEIGHTS.items() if points[k] is not None)
    # Snapshot đủ dữ liệu: không tái phân bổ, không biến thiếu thành 0.
    score=round(sum(x for x in points.values() if x is not None),2) if coverage==100 else None
    warnings=[]
    if equity is not None and equity<=0:warnings.append('Vốn chủ sở hữu không dương')
    if debt is not None and debt>1.5:warnings.append('Áp lực nợ vay cao')
    if all(x is not None and x<0 for x in cfo):warnings.append('CFO âm cả 3 năm')
    if v['CFO TTM'] is not None and v['CFO TTM']<0:warnings.append('CFO TTM âm')
    if v['LNST'] is not None and v['LNST']<=0:warnings.append('LNST TTM không dương')
    inv,assets=number(row,'HTK ròng Q3 (tỷ)'),number(row,'Tổng tài sản Q3 (tỷ)')
    cash,short=number(row,'Tiền và tương đương Q3 (tỷ)'),number(row,'Nợ vay NH Q3 (tỷ)')
    if inv is not None and assets is not None and assets>0 and inv/assets>.6:warnings.append('HTK/Tổng tài sản trên 60%')
    if cash is not None and short is not None and short>0 and cash/short<1:warnings.append('Tiền thấp hơn nợ vay ngắn hạn')
    return {'code':row['Mã'],'values':v,'cfo':cfo,'growth_state':gstate,'factors':p,'points':points,'coverage':coverage,'score':score,'grade':grade(score),'warnings':warnings,'industry_pb':industry,'period':row.get('Kỳ tham chiếu định giá FA','Q3/2026'),'ranks':{},'project':project}

def rank_values(results):
    metrics=('ROE','ROA','Biên LNG','Tăng trưởng LNST','Nợ vay/VCSH','P/B','P/E','HTK/TTS','MNTTT/HTK','MNTTT YoY')
    for k in metrics:
        eligible={s:e['values'][k] for s,e in results.items() if e['values'][k] is not None and (k not in ('P/B','P/E') or e['values'][k]>0) and (k not in ('ROE','Nợ vay/VCSH','P/B') or e['values']['VCSH'] is not None and e['values']['VCSH']>0) and (k!='P/E' or e['values']['LNST'] is not None and e['values']['LNST']>0)}
        if k in ('MNTTT/HTK','MNTTT YoY'):
            eligible={s:v for s,v in eligible.items() if not results[s]['project']['neutral']}
        reverse=k not in ('Nợ vay/VCSH','P/B','P/E','HTK/TTS')
        for s,v in eligible.items():
            rank=1+sum((a>v if reverse else a<v) for a in eligible.values());results[s]['ranks'][k]=rank
    for s,e in results.items():
        if e['score'] is not None:e['rank']=1+sum(r['score'] is not None and r['score']>e['score'] for r in results.values())
        else:e['rank']=None
    return results

@lru_cache(maxsize=4)
def _load(path,mtime):
    with open(path,encoding='utf-8-sig',newline='') as f: rows=list(csv.DictReader(f))
    if len(rows)!=len(SYMBOLS) or {r['Mã'] for r in rows}!=SYMBOLS:raise ValueError('BDS_FA_INVALID_UNIVERSE')
    pbs=[number(r,FIELDS['P/B']) for r in rows if (number(r,FIELDS['VCSH']) or 0)>0]; pbs=[n for n in pbs if n is not None and n>0]
    industry=sum(pbs)/len(pbs) if pbs else None
    return rank_values({r['Mã']:evaluate(r,industry) for r in rows})

def load(path=PATH):
    path=Path(path);return _load(str(path),path.stat().st_mtime_ns)

def notes(e):
    v=e['values'];p=e['factors'];r=e['ranks']; out=[]
    def top(k):return f' | TOP {r[k]} Ngành BĐS' if k in r and r[k]<=5 else ''
    for k,n in [('ROE','ROE'),('ROA','ROA'),('Biên LNG','Biên lợi nhuận gộp TTM')]:out.append(f'{n} {fmt(v[k])}% – {label(p[k])}'+top(k))
    k='Tăng trưởng LNST';out.append('Tăng trưởng LNST TTM – '+e['growth_state'] if e['growth_state'] else f'Tăng trưởng LNST TTM {fmt(v[k])}% – {label(p[k])}'+top(k))
    k='Nợ vay/VCSH';out.append(f'{k} {fmt(v[k])} lần – '+{1:'Rất an toàn',.8:'An toàn',.6:'Trung bình',.3:'Nợ vay cao',0:'Rủi ro cao'}.get(p[k],'Chưa đủ dữ liệu')+top(k))
    c=e['cfo'];out.append(f'CFO dương {sum(x is not None and x>0 for x in c)}/3 năm – {fmt(e["points"]["CFO"],0)}/15 điểm')
    q=e['project']; ip=p['HTK']; ap=p['MNTTT']
    concentration={1:'Tập trung thấp',.8:'Tập trung vừa',.6:'Trung bình',.3:'Tập trung cao',0:'Tập trung rất cao'}.get(ip,'Thiếu dữ liệu')
    out.append(f'HTK/Tổng tài sản {fmt(q["HTK/TTS"])}% – {concentration} | {fmt(e["points"]["HTK"],1)}/10 điểm'+top('HTK/TTS')+f' | HTK YoY {fmt(q["HTK YoY"])}%, QoQ {fmt(q["HTK QoQ"])}%')
    advance_text='Mức trung tính (HTK và MNTTT không trọng yếu)' if q['neutral'] else f'MNTTT/HTK {fmt(q["MNTTT/HTK"])}%'+top('MNTTT/HTK')+f' | YoY {fmt(q["MNTTT YoY"])}%'+top('MNTTT YoY')
    out.append(f'Người mua trả tiền trước NH {fmt(q["MNTTT tỷ"])} tỷ – {advance_text} | {fmt(e["points"]["MNTTT"],1)}/10 điểm'+f' | QoQ {fmt(q["MNTTT QoQ"])}%')
    def compare(b):return '—' if b is None or b<=0 or v['P/B'] is None else ('Thấp hơn ' if v['P/B']<b else 'Cao hơn ' if v['P/B']>b else 'Bằng ') + fmt(abs(v['P/B']/b-1)*100)+'%'
    out.append(f'P/B {fmt(v["P/B"])} lần'+top('P/B')+f' | TB 3 năm (12 quý): {fmt(v["P/B TB"])} ({compare(v["P/B TB"])}) | TB ngành: {fmt(e["industry_pb"])} ({compare(e["industry_pb"])})')
    out.append(f'P/E {fmt(v["P/E"])} lần – '+('Không có LNST dương' if v['LNST'] is not None and v['LNST']<=0 else val_label(p['P/E']))+top('P/E'))
    if e['warnings']:out.append('Cảnh báo: '+ '; '.join(e['warnings']))
    out.append(f'{e["grade"]} | Hạng {e["rank"]}/33 · FA Q3/2026 · ngày giá ZIP chưa xác định')
    return out

def for_symbol(symbol):
    e=load().get(str(symbol).upper().strip());return (e['score'],notes(e)) if e else (None,[])
