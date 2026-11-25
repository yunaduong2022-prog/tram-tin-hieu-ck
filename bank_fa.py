"""Bank FA v1: only approved, dated, same-period inputs; no imputation."""
import csv
import math
from datetime import date
from pathlib import Path
from functools import lru_cache
BANKS = frozenset('VCB BID CTG TCB MBB VPB ACB HDB STB SHB TPB VIB LPB MSB OCB SSB EIB KLB NAB VAB NVB ABB BVB BAB VBB SGB PGB PCB'.split())
NON_BANK = frozenset(('EVF','TIN'))
WEIGHTS = {'ROE':20,'NIM':15,'CASA':10,'NPL':20,'LLR':20,'PB_REL':15}
FIELDS = ['symbol','period_end','published_date','source','reviewed','ROE','NIM','CASA','NPL','LLR','PB','PB_AVG5']
BANDS = {'ROE':[(25,20),(18,17),(15,14),(12,10),(8,5)],'NIM':[(4.5,15),(3.5,12),(2.5,9),(2,5)],'CASA':[(35,10),(25,8),(20,6),(15,4),(10,2)],'LLR':[(200,20),(150,17),(100,14),(70,8),(50,4)],'NPL':[(1,20),(1.5,17),(2,14),(3,8),(5,3)],'PB_REL':[(.7,15),(.85,12),(1,9),(1.2,5),(1.5,2)]}
LIMITS={'ROE':(-100,100),'NIM':(-10,20),'CASA':(0,100),'NPL':(0,100),'LLR':(0,10000),'PB':(.000001,200),'PB_AVG5':(.000001,200)}
PATH=Path(__file__).resolve().parent/'data'/'bank_fa_inputs.csv'
def num(row,k):
    try:
        v=float(row.get(k,'')); lo,hi=LIMITS[k]
        return v if math.isfinite(v) and lo<=v<=hi else None
    except (ValueError,TypeError): return None

def evaluate(row, today=None):
    today=today or date.today(); row=row or {}; vals={k:num(row,k) for k in LIMITS}
    vals['PB_REL']=vals['PB']/vals['PB_AVG5'] if vals['PB'] is not None and vals['PB_AVG5'] is not None else None
    pts={}
    for k in WEIGHTS:
        v=vals[k]
        if v is not None: pts[k]=next((p for t,p in BANDS[k] if (v<=t if k in ('NPL','PB_REL') else v>=t)),0)
    coverage=sum(WEIGHTS[k] for k in pts); missing=[k for k in WEIGHTS if k not in pts]; tags=[]
    valid=False
    try:
        period=date.fromisoformat(row.get('period_end','')); pub=date.fromisoformat(row.get('published_date',''))
        valid=period<=pub<=today and (today-period).days<=180 and period.month in (3,6,9,12) and (period.day==31 if period.month in (3,12) else period.day==30) and row.get('reviewed','').strip().lower()=='yes' and bool(row.get('source','').strip())
    except (ValueError,TypeError): pass
    risk=(vals['NPL'] is not None and vals['NPL']>3) or (vals['LLR'] is not None and vals['LLR']<50) or (vals['ROE'] is not None and vals['ROE']<8)
    if risk: tags.append('Cảnh báo rủi ro tài chính')
    if not valid: tags.append('Chưa xác minh kỳ/nguồn hoặc dữ liệu quá hạn')
    if missing: tags.append('Thiếu: '+', '.join(missing))
    # Require all six for official score; partial is a lower-bound, not normalized.
    official=valid and coverage==100
    score=sum(pts.values()) if official else None
    status='Chính thức' if official else ('Tạm tính' if valid and coverage>=60 else 'Chưa đủ dữ liệu')
    grade=('Rất tốt' if score>=85 else 'Tốt' if score>=70 else 'Khá' if score>=55 else 'Trung bình' if score>=40 else 'Yếu') if score is not None else status
    return dict(score=score,coverage=coverage,partial=sum(pts.values()) if valid and coverage>=60 else None,status=status,grade=grade,points=pts,values=vals,risk=risk,tags=tags,period=row.get('period_end',''),source=row.get('source',''))
@lru_cache(maxsize=8)
def _read(path,mtime):
    with open(path,encoding='utf-8-sig',newline='') as f:
        rows=list(csv.DictReader(f))
    out={}; dup=set()
    for r in rows:
        s=r.get('symbol','').strip().upper()
        if s not in BANKS: continue
        if s in out: dup.add(s)
        out[s]=r
    return {s:r for s,r in out.items() if s not in dup}
def load():
    try: return _read(str(PATH),PATH.stat().st_mtime_ns)
    except (OSError,ValueError,csv.Error): return {}
def for_symbol(symbol): return evaluate(load().get(symbol))
def render():
    import streamlit as st
    import pandas as pd
    st.subheader('Xếp hạng cơ bản ngân hàng | BANK FA V1')
    st.caption('Chỉ chấm chính thức khi đủ 6 chỉ tiêu đã xác minh cùng kỳ. Điểm tạm tính không quy đổi lên 100 và không dùng trong VIP.')
    rows=[]
    for s in sorted(BANKS):
        e=for_symbol(s); v=e['values']; p=e['points']
        rows.append({'Mã':s,'FA':e['score'],'Điểm tạm':e['partial'],'Độ phủ (%)':e['coverage'],'Xếp loại':e['grade'],**{k:v[k] for k in ('ROE','NIM','CASA','NPL','LLR','PB_REL')},'Kỳ':e['period'],'Nguồn':e['source'],'Cảnh báo':'; '.join(e['tags']),**{k+' điểm':p.get(k) for k in WEIGHTS}})
    df=pd.DataFrame(rows).sort_values(['FA','Độ phủ (%)','Mã'],ascending=[False,False,True],na_position='last')
    st.dataframe(df,hide_index=True,use_container_width=True)
    s=st.selectbox('Chi tiết điểm ngân hàng',sorted(BANKS),key='bank_fa_detail_v1'); e=for_symbol(s)
    st.write(f"{s} · {e['grade']} · Độ phủ {e['coverage']}%")
    st.dataframe(pd.DataFrame([{'Chỉ tiêu':k,'Giá trị':e['values'][k],'Điểm':e['points'].get(k),'Tối đa':w} for k,w in WEIGHTS.items()]),hide_index=True,use_container_width=True)
