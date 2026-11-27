"""Oil FA V1. Reference score only; reads EOD, never writes market data."""
import csv, json, math, re
from pathlib import Path
from functools import lru_cache
from datetime import datetime, timezone, timedelta
from steel_fa import num, ratio, tier, fmt, cmp, stamp
ROOT=Path(__file__).resolve().parent
PATH=ROOT/'data/oil_fa_inputs.csv';EOD=ROOT/'data/eod_prices.csv';META=ROOT/'data/eod_meta.json';SHARES=ROOT/'data/shares_outstanding.csv'
SYMBOLS=frozenset('GAS PLX BSR PVD PVS PVC OIL PGD POS PPT PTV PVB PVM PXS PVE'.split())
ASOF='2026-11-27'; EXPIRES='2027-03-31'
GROUPS={'service':(25,20,15,10),'gas':(20,15,10,7),'refine':(15,10,7,4),'trade':(10,7,5,3)}
BENCH={'oil':(4.64,1.22),'distribution':(11.0,1.93)}
WEIGHTS=dict(roe=10,roa=5,margin=10,rev_growth=5,profit_growth=10,netdebt_ebitda=10,interest_cover=5,current_ratio=5,cfo_ratio=10,wc=10,ev=5,pb_hist=5,pb_industry=5,pe_hist=2.5,pe_industry=2.5)
LABELS=dict(roe='ROE',roa='ROA',margin='Biên lợi nhuận gộp',rev_growth='Tăng trưởng DT',profit_growth='Tăng trưởng LNST',netdebt_ebitda='Nợ ròng/EBITDA',interest_cover='Khả năng trả lãi vay',current_ratio='Thanh toán hiện hành',cfo_ratio='CFO/LNST',wc='Vốn lưu động',ev='EV/EBITDA')
LOW={'netdebt_ebitda','wc','ev','pb','pe'}
PERCENT={'roe','roa','margin','rev_growth','profit_growth','cfo_ratio'}
SCOPE='TOP chỉ trong các mã đủ điều kiện, không phải toàn bộ ngành; biên gộp/vốn lưu động theo nhóm kinh doanh, định giá theo nhóm và cùng chế độ giá.'
RESEARCH={'BSR':('Biên lọc dầu, sản lượng và bảo dưỡng nhà máy.','Lợi nhuận chu kỳ cao; TCBS dự báo giảm tốc năm 2027 (09/11/2026). Không coi dự phóng là số thực tế.','https://www.tcbs.com.vn/wp-content/uploads/2026/11/20261109_BSR_Bao_cao_cap_nhat_KQKD_Q3_2026-1.pdf'), 'PVB':('Tiến độ dự án Lô B – Ô Môn.','Theo KIS, LNST Q3 giảm YoY dù doanh thu tăng; theo dõi công nợ, CFO.','https://24hmoney.vn/bao-cao-phan-tich/pvb-bao-cao-cap-nhat-kqkd-q3-2026-rpid6229.html'), 'PVC':('Nhu cầu hóa chất và dịch vụ kỹ thuật dầu khí.','BCTC hợp nhất: theo dõi khoản phải thu, chi phí lãi vay và CFO.','https://pvchem.com.vn/bao-cao-tai-chinh/bao-cao-tai-chinh-quy-iii2026.html')}
DRIVERS={'service':'Hợp đồng, tiến độ dự án và hiệu suất sử dụng thiết bị.','gas':'Sản lượng, giá bán khí và chi phí đầu vào.','trade':'Sản lượng tiêu thụ, biên phân phối và vốn lưu động.','refine':'Crack spread, công suất, bảo dưỡng và tồn kho.'}
def read_rows(path=PATH):
    with open(path,encoding='utf-8-sig',newline='') as f: rows=list(csv.DictReader(f))
    if len(rows)!=len(SYMBOLS) or {r['code'] for r in rows}!=SYMBOLS:raise ValueError('OIL_INVALID_UNIVERSE')
    return {r['code']:r for r in rows}
def vp(v,ref,w):
    if v is None:return None
    if v<=0:return 0
    q=ratio(v,ref)
    f=tier(q,(.7,.9,1.1,1.3,1.5),(1,.8,.6,.4,.2),True)
    return None if f is None else round(f*w,4)
def ev_of(r,cap):
    db,cash,nci,eb=[num(r,k) for k in ('debt','cash','nci','ebitda')]
    if cap is None or cap<=0 or any(v is None for v in (db,cash,nci,eb)) or eb<=0:return None
    return (cap+db-cash+nci)/eb

def evaluate(r,pe,pb,cap,spe,spb,mode,day=None):
    v={k:num(r,k) for k in ('roe','roa','margin','rev_growth','profit','profit_prev','equity','parent_equity','parent_profit','debt','cash','nci','ebitda','ebit','interest','cfo','current_ratio','wc','wc_hist','pe_hist','pb_hist','q_profit_growth','other_pct','da')}
    v.update(pe=pe,pb=pb,ev=ev_of(r,cap),sector_pe=spe,sector_pb=spb)
    profit,prior,eq,cfo,eb,ebit,it=[v[k] for k in ('profit','profit_prev','equity','cfo','ebitda','ebit','interest')]
    v['netdebt_ebitda']=ratio(v['debt']-v['cash'],eb) if v['debt'] is not None and v['cash'] is not None else None
    v['interest_cover']=ratio(ebit,it);v['cfo_ratio']=ratio(cfo,profit)
    v['profit_growth']=(profit/prior-1)*100 if prior is not None and prior>0 and profit is not None else None
    g=GROUPS.get(r['group']);pg=None if profit is None or prior is None else 0 if profit<=0 else 6 if prior<=0 else tier(v['profit_growth'],(30,20,10,0,-10),(10,8,6,4,2))
    p=dict(roe=0 if eq is not None and eq<=0 else tier(v['roe'],(20,15,10,5,1e-9),(10,8,6,3,1)),roa=tier(v['roa'],(10,7,5,3,1e-9),(5,4,3,2,1)),margin=tier(v['margin'],(*g,1e-9),(10,8,6,4,2)) if g else None,rev_growth=tier(v['rev_growth'],(30,20,10,0,-10),(5,4,3,2,1)),profit_growth=pg,netdebt_ebitda=0 if eb is not None and eb<=0 else tier(v['netdebt_ebitda'],(1,2,3,4,5),(10,8,6,3,1),True),interest_cover=None if it is None or ebit is None or it<0 else (5 if ebit>0 else 0) if it==0 else tier(v['interest_cover'],(8,5,3,1.5,1),(5,4,3,2,1)),current_ratio=tier(v['current_ratio'],(2,1.5,1.2,1,.8),(5,4,3,2,1)),cfo_ratio=None if cfo is None or profit is None else (4 if cfo>0 else 0) if profit<=0 else tier(v['cfo_ratio'],(1,.8,.5,.2,0),(10,8,6,4,2)),wc=tier(ratio(v['wc'],v['wc_hist']),(.8,1,1.2,1.4,1.6),(10,8,6,4,2),True) if g else None,ev=0 if eb is not None and eb<=0 else tier(v['ev'],(4,6,8,10,15),(5,4,3,2,1),True) if v['ev'] is not None and v['ev']>0 else None,pb_hist=vp(pb,v['pb_hist'],5),pb_industry=vp(pb,spb,5),pe_hist=vp(pe,v['pe_hist'],2.5),pe_industry=vp(pe,spe,2.5))
    if v['parent_equity'] is not None and v['parent_equity']<=0:p.update(pb_hist=0,pb_industry=0)
    if v['parent_profit'] is not None and v['parent_profit']<=0:p.update(pe_hist=0,pe_industry=0)
    w=[]
    if r['period']!='2026Q3':w.append('Thiếu BCTC Q3/2026 đồng kỳ')
    if not g:w.append('Chưa xác minh nhóm kinh doanh để chấm biên gộp và vốn lưu động')
    if eq is not None and eq<=0:w.append('Vốn chủ sở hữu không dương')
    if profit is not None and profit<=0:w.append('LNST TTM không dương')
    if cfo is not None and cfo<0:w.append('CFO TTM âm'+(', LNST dương' if profit is not None and profit>0 else ''))
    if v['netdebt_ebitda'] is not None and v['netdebt_ebitda']>5:w.append('Nợ ròng/EBITDA trên 5x')
    if v['q_profit_growth'] is not None and v['q_profit_growth']<0:w.append('LNST quý gần nhất giảm YoY '+fmt(v['q_profit_growth'])+'%')
    if v['other_pct'] is not None and v['other_pct']>=30:w.append('Thu nhập khác từ 30% LNST; chưa chuẩn hóa')
    if eb is not None and eb<=0:w.append('EBITDA không dương')
    if v['da'] is not None and v['da']<0:w.append('Khấu hao âm; chưa xác minh EBITDA')
    if v['ev'] is not None and v['ev']<=0:w.append('EV không dương; không chấm là định giá rẻ')
    if r['pe_hist_source']!='SStock':w.append('P/E TB 3 năm SStock bất thường; '+('dùng TB quý P/E dương Vietcap' if v['pe_hist'] is not None else 'thiếu lịch sử thay thế hợp lệ'))
    coverage=sum(WEIGHTS[k] for k,x in p.items() if x is not None);subtotal=round(sum(x for x in p.values() if x is not None),2)
    return dict(code=r['code'],raw=r,v=v,points=p,coverage=coverage,subtotal=subtotal,score=subtotal if coverage==100 and r['period']=='2026Q3' else None,ranks={},warnings=w,mode=mode,day=day)

def snapshot(rows):
    return {s:evaluate(r,num(r,'pe'),num(r,'pb'),num(r,'cap'),*BENCH[r['sector']],'snapshot',ASOF) for s,r in rows.items()}
def ranked(results):
    peers=[e for e in results.values() if e['score'] is not None and (e['v']['equity'] or 0)>0]
    for e in results.values():e['ranks']={}
    for e in peers:
        for k in (*LABELS,'pb','pe'):
            v=e['v'].get(k)
            if v is None or (k in ('pb','pe','ev') and v<=0):continue
            # Do not award misleading cross-business ranks for margin/WC; keep valuation ranks within a benchmark and price mode.
            a=[x for x in peers if (k not in ('margin','wc') or x['raw']['group']==e['raw']['group']) and (k not in ('pb','pe','ev') or (x['raw']['sector']==e['raw']['sector'] and x['mode']==e['mode']))]
            values=[x['v'][k] for x in a if x['v'].get(k) is not None and (k not in ('pb','pe','ev') or x['v'][k]>0)]
            if len(values)>=5:e['ranks'][k]=1+sum(x<v if k in LOW else x>v for x in values)
    return results

def dynamic(rows,day,prices,shares):
    if not '2026-11-01'<=day<=EXPIRES:return {}
    vals={}
    for s,r in rows.items():
        px,sh=prices.get(s),shares.get(s);ref=num(r,'shares');z=num(r,'zip_shares')
        if r['period']!='2026Q3' or not r['pub'] or r['pub']>day or not px or px<=0 or not sh or not ref or not z or min(sh,ref,z)<=0 or max(abs(sh/ref-1),abs(sh/z-1))>.01:continue
        cap=px*sh/1e9;profit=num(r,'parent_profit');eq=num(r,'parent_equity')
        vals[s]=(cap/profit if profit is not None and profit!=0 else None,cap/eq if eq is not None and eq!=0 else None,cap,profit,eq)
    out={}
    for sector in BENCH:
        candidates={s:x for s,x in vals.items() if rows[s]['sector']==sector};pes=[x for x in candidates.values() if x[0] is not None and x[0]>0];pbs=[x for x in candidates.values() if x[1] is not None and x[1]>0]
        if min(len(pes),len(pbs))<(3 if sector=='distribution' else 5):continue
        spe=sum(x[2] for x in pes)/sum(x[3] for x in pes);spb=sum(x[2] for x in pbs)/sum(x[4] for x in pbs)
        for s,(pe,pb,cap,*_) in candidates.items():out[s]=evaluate(rows[s],pe,pb,cap,spe,spb,'eod',day)
    return out

def latest_prices(eod,meta):
    import pandas as pd
    m=json.loads(Path(meta).read_text(encoding='utf-8-sig'));day=pd.Timestamp(m['latest_date']).normalize()
    if pd.isna(day) or day.date()>datetime.now(timezone(timedelta(hours=7))).date():raise ValueError('OIL_INVALID_EOD_DATE')
    df=pd.read_csv(eod,usecols=['Mã','Ngày','Giá đóng cửa'],dtype={'Mã':str},encoding='utf-8-sig');raw=df['Ngày'].astype(str).str.strip();iso=raw.str.match(r'^\d{4}-\d{2}-\d{2}')
    parsed=pd.to_datetime(raw.where(~iso),format='mixed',dayfirst=True,errors='coerce');parsed.loc[iso]=pd.to_datetime(raw.loc[iso].str[:10],format='%Y-%m-%d',errors='coerce');df['Ngày']=parsed.dt.normalize()
    if df['Ngày'].max()!=day:raise ValueError('OIL_META_MISMATCH')
    failed={str(x).split(':',1)[0].strip() for x in m.get('failed',[])};prices={}
    for s,g in df.loc[df['Ngày'].eq(day)&df['Mã'].isin(SYMBOLS)].groupby('Mã'):
        if len(g)!=1 or s in failed:continue
        px=num(g.iloc[0],'Giá đóng cửa')
        if px is not None and px>0:prices[s]=px*1000
    return day.date().isoformat(),prices

def resolve(rows,day,prices,shares):
    if not '2026-11-01'<=day<=EXPIRES:return {}
    live=dynamic(rows,day,prices,shares);snap=snapshot(rows);out={}
    for s,r in rows.items():
        px=prices.get(s)
        if px is None or px<9000 or not r['pub'] or r['pub']>day:continue
        e=live.get(s)
        # Snapshot explicitly dated; do not silently treat it as EOD. Snapshot is not used for backdated EOD before the image date except the 26 Nov latest close.
        if e is None and '2026-11-26'<=day<='2026-12-04':
            e=snap[s];e['warnings'].append('Dùng ảnh cập nhật 27/11/2026; chưa đủ điều kiện tính định giá EOD')
            sh=shares.get(s);ref=num(r,'shares');z=num(r,'zip_shares')
            if not sh or not ref or not z or min(sh,ref,z)<=0 or max(abs(sh/ref-1),abs(sh/z-1))>.01:e['warnings'].append('Số CP chưa đối chiếu khớp; không tự tính lại định giá')
        if e is not None:out[s]=e
    return ranked(out)

@lru_cache(maxsize=3)
def cached(i,e,m,sh):
    from port_fa import read_shares
    day,prices=latest_prices(e[0],m[0]);return day,prices,resolve(read_rows(i[0]),day,prices,read_shares(sh[0]))
def lookup(symbol):
    s=str(symbol).strip().upper()
    if s not in SYMBOLS:return None,[]
    try:day,prices,results=cached(stamp(PATH),stamp(EOD),stamp(META),stamp(SHARES))
    except (OSError,ValueError,KeyError,TypeError,OverflowError):return None,['FA Dầu khí: chưa xác minh được dữ liệu EOD/đầu vào']
    if s not in prices:return None,['FA Dầu khí: chưa có giá EOD hợp lệ cùng phiên']
    if prices[s]<9000:return None,['FA Dầu khí: giá EOD dưới 9.000đ; không xếp hạng theo dõi']
    e=results.get(s);return (e,notes(e)) if e else (None,['FA Dầu khí: dữ liệu ngoài kỳ hiệu lực hoặc thiếu kỳ báo cáo'])

def notes(e):
    r,v,p=e['raw'],e['v'],e['points'];mode='EOD ước tính '+e['day'] if e['mode']=='eod' else 'Ảnh SStock cập nhật 27/11/2026; chưa xác nhận phiên giá'
    out=['FA tham khảo | Dầu khí | BCTC '+r['period']+' | '+mode+' | '+SCOPE]
    def top(k):return f' | TOP {e["ranks"][k]} Ngành Dầu khí' if e['ranks'].get(k,99)<=5 else ''
    def label(k):
        if p[k] is None:return 'Thiếu dữ liệu'
        f=p[k]/WEIGHTS[k];return 'Rất tốt' if f>=.9 else 'Tốt' if f>=.75 else 'Khá' if f>=.6 else 'Trung bình' if f>=.4 else 'Yếu' if f>0 else 'Rất yếu'
    for k,n in LABELS.items():
        x=v[k];val=fmt(x*100 if k=='cfo_ratio' and x is not None else x)+('%' if k in PERCENT else ' ngày' if k=='wc' else 'x')
        if k=='wc':n='Tồn kho' if r['group'] in ('trade','refine') else 'Số ngày phải thu';val+=' | TB 3 năm: '+fmt(v['wc_hist'])+' ngày'
        if k=='interest_cover' and v['interest']==0:val='Không phát sinh lãi vay'
        if k=='profit_growth' and x is None and v['profit'] is not None and v['profit_prev'] is not None:val='Phục hồi từ lỗ' if v['profit']>0 else 'Thua lỗ/hòa vốn'
        if k=='cfo_ratio' and v['profit'] is not None and v['profit']<=0:val='CFO '+fmt(v['cfo'])+' tỷ; LNST không dương'
        out.append(f'{n} {val} – {label(k)} | {fmt(p[k])}/{WEIGHTS[k]}'+top(k))
    for k in ('pb','pe'):
        x,a,b=v[k],v[k+'_hist'],v['sector_'+k];n='P/B' if k=='pb' else 'P/E';pts=[p[k+'_hist'],p[k+'_industry']];sector='TB nhóm EOD' if e['mode']=='eod' else 'TB ngành (ảnh)'
        out.append(f'{n} {fmt(x)}x | TB 3 năm: {fmt(a)} ({cmp(x,a)}) | {sector}: {fmt(b)} ({cmp(x,b)}) | {fmt(sum(t for t in pts if t is not None))}/{WEIGHTS[k+"_hist"]+WEIGHTS[k+"_industry"]}'+(' (thiếu tham chiếu)' if None in pts else '')+top(k))
    if e['score'] is None:out.insert(0,f'Chưa đủ dữ liệu FA: {fmt(e["subtotal"])}/{fmt(e["coverage"])} điểm khả dụng; không xếp loại')
    if e['warnings']:out.append('Rủi ro: '+'; '.join(e['warnings']))
    if r['pe_hist_source']!='SStock':out.append('Chi tiết: P/E TB SStock '+fmt(num(r,'pe_hist_raw'))+'; lịch sử Vietcap '+r['pe_hist_n']+'/12 quý dương trước Q3/2026 (tối thiểu 8).')
    out.append('Chi tiết: '+mode+'; EV = vốn hóa + nợ vay + lợi ích CĐ không kiểm soát - tiền và tương đương tiền; không trừ khoản đầu tư ngắn hạn chưa xác minh. EBITDA = LNTT + lãi vay + khấu hao. BCTC TTM đến Q3/2026; ROE/ROA bình quân đầu/cuối TTM; TB vốn lưu động 12 kỳ TTM. TB nhóm EOD = tổng vốn hóa/tổng mẫu số dương, tối thiểu 3 mã phân phối hoặc 5 mã dầu khí, không phải toàn ngành. Không chấm dự phóng.')
    d=RESEARCH.get(e['code']);out.append('Động lực: '+(d[0] if d else DRIVERS.get(r['group'],'Chưa xác minh')))
    if d:out.append('Nghiên cứu tham khảo: '+d[1]+' Nguồn: '+d[2])
    return out

def compact_notes(tags):
    out=[]
    for raw in tags or []:
        t=str(raw)
        if t.startswith(('FA tham khảo |','Chi tiết:','Động lực:','Nghiên cứu tham khảo:')):continue
        if t.startswith(('Rủi ro:','Chưa đủ dữ liệu FA:','FA Dầu khí:')):out.append(t);continue
        t=re.sub(r' \| (?:\d[\d.,]*|—)/\d+(?:\.\d+)?(?= \| TOP | \(thiếu tham chiếu\)|$)','',t)
        out.append(t.replace('TB ngành (ảnh):','TB ngành:'))
    return out

def for_symbol(symbol):
    e,t=lookup(symbol);return (e['score'] if e else None),t

def detail(symbol):
    _,t=lookup(symbol);return 'OIL FA V1 – tham khảo, không xếp hạng VIP chính thức. '+ '; '.join(t)
