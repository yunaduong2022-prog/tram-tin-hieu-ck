"""Retail FA V1: dated reference-only score. No EOD or official VIP writes."""
import csv
import math
from pathlib import Path
from functools import lru_cache

SYMBOLS=frozenset('MWG FRT PNJ DGW PET MSN'.split())
PATH=Path(__file__).resolve().parent/'data'/'retail_fa_inputs.csv'
ASOF='2026-11-28'
WEIGHTS=dict(roe=10,roa=5,margin=5,net_margin=5,rev_growth=10,profit_growth=10,netdebt_ebitda=10,interest_cover=5,current_ratio=5,cfo_ratio=10,dio=5,pe_hist=7.5,pe_industry=7.5,pb_hist=2.5,pb_industry=2.5)
LABELS=dict(roe='ROE',roa='ROA',margin='Biên lợi nhuận gộp',net_margin='Biên lợi nhuận ròng',rev_growth='Tăng trưởng DT TTM',profit_growth='Tăng trưởng LNST mẹ TTM',netdebt_ebitda='Nợ ròng/EBITDA',interest_cover='Khả năng trả lãi vay',current_ratio='Thanh toán hiện hành',cfo_ratio='CFO/LNST',dio='Tồn kho')
# Thresholds are research policy, not industry standards. Distinct models for margin.
MARGINS={'retail':((20,15,10,5,0),(6,4,3,1,0)), 'jewelry':((20,16,12,8,0),(7,5,3,1,0)), 'distribution':((9,8,6,5,0),(4,3,2.5,1,0)), 'diversified':((30,25,20,10,0),(10,8,5,2,0))}
LOW={'netdebt_ebitda'}
PCT={'roe','roa','margin','net_margin','rev_growth','profit_growth','cfo_ratio'}
def num(r,k):
    try:
        v=float(r.get(k,''));return v if math.isfinite(v) else None
    except (TypeError,ValueError,OverflowError):return None

def band(v,thresholds,points,reverse=False):
    if v is None:return None
    return next((p for a,p in zip(thresholds,points) if (v<=a+1e-9 if reverse else v>=a-1e-9)),0)

def ratio(v,b):return v/b if v is not None and b is not None and b>0 else None

def valuation(v,b,w):
    if v is None:return None
    if v<=0:return 0
    q=ratio(v,b)
    p=band(q,(.7,.9,1.1,1.3,1.5),(1,.8,.6,.4,.2),True)
    return None if p is None else round(p*w,4)

def evaluate(r):
    if r['code'] not in SYMBOLS or r['period']!='2026-09-30' or not r['period']<=r['pub']<=ASOF:raise ValueError('INVALID_RETAIL_SOURCE')
    v={k:num(r,k) for k in (*LABELS,'dio_hist','pe','pe_hist','pb','pb_hist','sector_pe','sector_pb','positive_pe_hist','positive_pe_count','profit','consolidated_profit','cfo','other_pct')}
    ph=v['pe_hist']; substituted=False
    if ph is not None and ph<=0 and (v['positive_pe_count'] or 0)>=8 and (v['positive_pe_hist'] or 0)>0:
        ph=v['positive_pe_hist'];substituted=True
    g,n=MARGINS[r['group']]
    p=dict(roe=band(v['roe'],(25,20,15,10,1e-8),(10,8,6,4,2)),roa=band(v['roa'],(10,8,5,3,1e-8),(5,4,3,2,1)),margin=band(v['margin'],g,(5,4,3,2,0)),net_margin=band(v['net_margin'],n,(5,4,3,2,0)),rev_growth=band(v['rev_growth'],(25,15,10,0),(10,8,6,4)),profit_growth=band(v['profit_growth'],(30,20,10,0),(10,8,6,4)),netdebt_ebitda=band(v['netdebt_ebitda'],(1,2,3,4,5),(10,8,6,4,2),True),interest_cover=band(v['interest_cover'],(8,5,3,1.5,1),(5,4,3,2,1)),current_ratio=band(v['current_ratio'],(2,1.5,1.2,1,.8),(5,4,3,2,1)),cfo_ratio=band(v['cfo_ratio'],(100,80,60,30,1e-8),(10,8,6,4,2)),dio=band(ratio(v['dio'],v['dio_hist']),(.8,1,1.2,1.4,1.6),(5,4,3,2,1),True),pe_hist=valuation(v['pe'],ph,7.5),pe_industry=valuation(v['pe'],v['sector_pe'],7.5),pb_hist=valuation(v['pb'],v['pb_hist'],2.5),pb_industry=valuation(v['pb'],v['sector_pb'],2.5))
    coverage=sum(WEIGHTS[k] for k,x in p.items() if x is not None)
    subtotal=round(sum(x for x in p.values() if x is not None),2)
    return dict(raw=r,v=v,p=p,score=subtotal if coverage==100 else None,coverage=coverage,subtotal=subtotal,ph=ph,substituted=substituted)

@lru_cache(maxsize=3)
def _load(path,stamp):
    with open(path,encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
    if len(rows)!=len(SYMBOLS) or {r['code'] for r in rows}!=SYMBOLS:raise ValueError('INVALID_RETAIL_UNIVERSE')
    return {r['code']:evaluate(r) for r in rows}

def all_scores():return _load(str(PATH),PATH.stat().st_mtime_ns)

def fmt(v):return '—' if v is None else f'{v:,.2f}'.replace(',','@').replace('.',',').replace('@','.')
def compare(v,b):
    q=ratio(v,b)
    if q is None or q<=0:return 'Không áp dụng'
    d=(q-1)*100;return ('Thấp hơn ' if d<0 else 'Cao hơn ' if d>0 else 'Bằng ')+fmt(abs(d))+'%'

def rank(e,results,k):
    # Only compare shared financial indicators within the five retail/distribution names;
    # no ranking margins, DIO, or MSN against unlike models.
    if e['raw']['code']=='MSN' or k in ('margin','net_margin','dio'):return ''
    v=e['v'][k]; peers=[x['v'][k] for s,x in results.items() if s!='MSN' and x['score'] is not None and x['v'][k] is not None]
    if v is None or len(peers)<5:return ''
    n=1+sum(x<v-1e-8 if k in LOW else x>v+1e-8 for x in peers)
    return f' | TOP {n}/5 nhóm Bán lẻ theo dõi'

def notes(e,results):
    r,v,p=e['raw'],e['v'],e['p'];out=[f'FA tham khảo | Bán lẻ | BCTC Q3/2026 | Định giá SStock 28/11/2026 (snapshot)']
    if e['score'] is None:out.append(f'Chưa đủ dữ liệu FA: {fmt(e["subtotal"])}/{fmt(e["coverage"])} điểm khả dụng; không xếp loại')
    for k,n in LABELS.items():
        x=v[k]; f=None if p[k] is None else p[k]/WEIGHTS[k];label='Thiếu dữ liệu' if f is None else 'Rất tốt' if f>=.9 else 'Tốt' if f>=.75 else 'Khá' if f>=.6 else 'Trung bình' if f>=.4 else 'Yếu' if f>0 else 'Rất yếu'
        value=fmt(x)+('%' if k in PCT else ' ngày' if k=='dio' else 'x')
        if k=='dio':value+=' | TB 3 năm: '+fmt(v['dio_hist'])+' ngày'
        out.append(f'{n} {value} – {label}'+rank(e,results,k))
    sector='Đa ngành' if r['code']=='MSN' else 'Bán lẻ'
    for k in ('pe','pb'):
        x=v[k]; h=e['ph'] if k=='pe' else v['pb_hist']; b=v['sector_'+k];label='TB 8 quý P/E dương' if k=='pe' and e['substituted'] else 'TB 3 năm'
        out.append(f'{"P/E" if k=="pe" else "P/B"} {fmt(x)}x | {label}: {fmt(h)}x ({compare(x,h)}) | TB ngành {sector}: {fmt(b)}x ({compare(x,b)})')
    out.append('Định giá: snapshot SStock 28/11/2026, chưa cập nhật theo EOD')
    risk=[]
    if (v['cfo'] or 0)<0:risk.append('CFO TTM âm')
    if (v['netdebt_ebitda'] or 0)>4:risk.append('Nợ ròng/EBITDA trên 4x')
    if (v['current_ratio'] or 0)<1:risk.append('Thanh toán hiện hành dưới 1x')
    if (v['profit_growth'] or 0)<0:risk.append('LNST mẹ TTM giảm')
    if e['substituted']:risk.append('P/E TB 3 năm SStock âm; dùng 8 quý P/E dương, có thể thiên lệch')
    if risk:out.append('Rủi ro: '+'; '.join(risk))
    out.append('Chi tiết: Vietcap BCTC TTM Q4/2025–Q3/2026; ROE theo LNST/VCSH mẹ bình quân đầu cuối; ROA và CFO/LNST theo LNST hợp nhất; EBITDA = LNTT + lãi vay + khấu hao; nợ ròng chỉ trừ tiền và tương đương tiền; tồn kho bình quân đầu cuối TTM / giá vốn TTM × 365, TB 12 quý TTM trước. Điểm định giá cố định tại snapshot, chưa xác minh cơ sở cổ phiếu lưu hành. TOP chỉ trong 5 mã theo dõi, không đại diện toàn ngành. MSN dùng benchmark Đa ngành.')
    out.append('Chi tiết: điểm từng tiêu chí '+', '.join(f'{k}={fmt(x)}/{WEIGHTS[k]}' for k,x in p.items()))
    return out

def for_symbol(symbol):
    s=str(symbol).strip().upper()
    if s not in SYMBOLS:return None,[]
    try:
        results=all_scores();e=results[s];return e['score'],notes(e,results)
    except (OSError,ValueError,KeyError,TypeError,OverflowError):return None,['FA Bán lẻ: thiếu hoặc lỗi dữ liệu đầu vào']

def compact_notes(tags):return [str(t) for t in tags or [] if not str(t).startswith(('FA tham khảo |','Chi tiết:'))]
def detail(symbol):return 'RETAIL FA V1 – tham khảo, không xếp hạng VIP chính thức. '+'; '.join(for_symbol(symbol)[1])
