"""Fertilizer FA V1. Reference score only; reads EOD, never writes market data."""
import csv, json, math, re
from pathlib import Path
from functools import lru_cache
from datetime import datetime, timezone, timedelta
from steel_fa import num, ratio, tier, fmt, cmp, stamp
ROOT=Path(__file__).resolve().parent
PATH=ROOT/'data/fertilizer_fa_inputs.csv';EOD=ROOT/'data/eod_prices.csv';META=ROOT/'data/eod_meta.json';SHARES=ROOT/'data/shares_outstanding.csv'
SCORED=frozenset('DCM DPM BFC DDV'.split())
EXCLUDED=frozenset('LAS SFG VAF'.split())
# Route excluded tickers explicitly, never fall through to generic FA.
SYMBOLS=SCORED|EXCLUDED
ASOF='2026-11-27'; EXPIRES='2027-03-31'
GROUPS={'ure':(30,25,20,15),'npk':(20,15,12,8),'dap':(25,20,15,10)}
BENCH=(6.14,1.21)
WEIGHTS=dict(roe=10,roa=5,margin=10,net_margin=5,rev_growth=5,profit_growth=10,netdebt_ebitda=10,interest_cover=5,current_ratio=5,cfo_ratio=10,wc=5,ev=5,pb_hist=5,pb_industry=2.5,pe_hist=5,pe_industry=2.5)
LABELS=dict(roe='ROE',roa='ROA',margin='Biên lợi nhuận gộp',net_margin='Biên lợi nhuận ròng',rev_growth='Tăng trưởng DT',profit_growth='Tăng trưởng LNST',netdebt_ebitda='Nợ ròng/EBITDA',interest_cover='Khả năng trả lãi vay',current_ratio='Thanh toán hiện hành',cfo_ratio='CFO/LNST',wc='Tồn kho',ev='EV/EBITDA')
LOW={'netdebt_ebitda','wc','ev','pb','pe'}
PERCENT={'roe','roa','margin','net_margin','rev_growth','profit_growth','cfo_ratio'}
SCOPE='TOP trong tối đa 4 mã Phân bón đủ dữ liệu, không phải toàn bộ ngành; biên gộp theo mô hình kinh doanh; xếp hạng định giá cùng chế độ giá.'
DRIVERS={'ure':'Giá Urê, chi phí khí, công suất và xuất khẩu.','npk':'Giá Urê, DAP, Kali đầu vào và mùa vụ.','dap':'Giá DAP, apatit, amoniac, lưu huỳnh và hàng tồn kho.'}
def read_rows(path=PATH):
    with open(path,encoding='utf-8-sig',newline='') as f: rows=list(csv.DictReader(f))
    if len(rows)!=len(SCORED) or {r['code'] for r in rows}!=SCORED:raise ValueError('FERT_INVALID_UNIVERSE')
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
    v={k:num(r,k) for k in ('roe','roa','margin','net_margin','inventory_growth','rev_growth','profit','profit_prev','equity','parent_equity','parent_profit','debt','cash','nci','ebitda','ebit','interest','cfo','current_ratio','wc','wc_hist','pe_hist','pb_hist','q_profit_growth','other_pct','da')}
    v.update(pe=pe,pb=pb,ev=ev_of(r,cap),sector_pe=spe,sector_pb=spb)
    profit,prior,eq,cfo,eb,ebit,it=[v[k] for k in ('profit','profit_prev','equity','cfo','ebitda','ebit','interest')]
    v['netdebt_ebitda']=ratio(v['debt']-v['cash'],eb) if v['debt'] is not None and v['cash'] is not None else None
    v['interest_cover']=ratio(ebit,it);v['cfo_ratio']=ratio(cfo,profit)
    v['profit_growth']=(profit/prior-1)*100 if prior is not None and prior>0 and profit is not None else None
    g=GROUPS.get(r['group']);pg=None if profit is None or prior is None else 0 if profit<=0 else 6 if prior<=0 else tier(v['profit_growth'],(30,20,10,0,-10),(10,8,6,4,2))
    p=dict(roe=0 if eq is not None and eq<=0 else tier(v['roe'],(20,15,10,5,1e-9),(10,8,6,3,1)),roa=tier(v['roa'],(10,7,5,3,1e-9),(5,4,3,2,1)),margin=tier(v['margin'],(*g,1e-9),(10,8,6,4,2)) if g else None,net_margin=tier(v['net_margin'],(15,10,7,3,1e-9),(5,4,3,2,1)),rev_growth=tier(v['rev_growth'],(30,20,10,0,-10),(5,4,3,2,1)),profit_growth=pg,netdebt_ebitda=0 if eb is not None and eb<=0 else tier(v['netdebt_ebitda'],(1,2,3,4,5),(10,8,6,3,1),True),interest_cover=None if it is None or ebit is None or it<0 else (5 if ebit>0 else 0) if it==0 else tier(v['interest_cover'],(8,5,3,1.5,1),(5,4,3,2,1)),current_ratio=tier(v['current_ratio'],(2,1.5,1.2,1,.8),(5,4,3,2,1)),cfo_ratio=None if cfo is None or profit is None else (4 if cfo>0 else 0) if profit<=0 else tier(v['cfo_ratio'],(1,.8,.5,.2,0),(10,8,6,4,2)),wc=tier(ratio(v['wc'],v['wc_hist']),(.8,1,1.2,1.4,1.6),(5,4,3,2,1),True) if g else None,ev=0 if eb is not None and eb<=0 else tier(v['ev'],(4,6,8,10,15),(5,4,3,2,1),True) if v['ev'] is not None and v['ev']>0 else None,pb_hist=vp(pb,v['pb_hist'],5),pb_industry=vp(pb,spb,2.5),pe_hist=vp(pe,v['pe_hist'],5),pe_industry=vp(pe,spe,2.5))
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
    if v['inventory_growth'] is not None and v['rev_growth'] is not None and v['inventory_growth']>v['rev_growth']+20:w.append('Tồn kho tăng nhanh hơn doanh thu TTM')
    if v['cfo_ratio'] is not None and v['cfo_ratio']<.5:w.append('CFO/LNST dưới 50%')
    if v['q_profit_growth'] is not None and v['q_profit_growth']<-50:w.append('Thận trọng với P/E thấp do chu kỳ lợi nhuận')
    if v['profit_growth'] is not None and v['profit_growth']<-10:w.append('LNST TTM giảm '+fmt(abs(v['profit_growth']))+'%')
    coverage=sum(WEIGHTS[k] for k,x in p.items() if x is not None);subtotal=round(sum(x for x in p.values() if x is not None),2)
    return dict(code=r['code'],raw=r,v=v,points=p,coverage=coverage,subtotal=subtotal,score=subtotal if coverage==100 and r['period']=='2026Q3' else None,ranks={},warnings=w,mode=mode,day=day)

def snapshot(rows):
    return {s:evaluate(r,num(r,'pe'),num(r,'pb'),num(r,'cap'),*BENCH,'snapshot',ASOF) for s,r in rows.items()}

def ranked(results):
    peers=[e for e in results.values() if e['score'] is not None and (e['v']['equity'] or 0)>0]
    for e in results.values():e['ranks']={}
    for e in peers:
        for k in (*LABELS,'pb','pe'):
            v=e['v'].get(k)
            if v is None or (k in ('pb','pe','ev') and v<=0):continue
            a=[x for x in peers if (k not in ('margin','net_margin','wc') or x['raw']['group']==e['raw']['group']) and (k not in ('pb','pe','ev') or x['mode']==e['mode'])]
            values=[x['v'][k] for x in a if x['v'].get(k) is not None and (k not in ('pb','pe','ev') or x['v'][k]>0)]
            if len(values)>=2:e['ranks'][k]=(1+sum(x<v if k in LOW else x>v for x in values),len(values))
    return results

def dynamic(rows,day,prices,shares):
    if not ASOF<=day<=EXPIRES:return {}
    vals={}
    for s,r in rows.items():
        px,sh=prices.get(s),shares.get(s);ref=num(r,'shares')
        if r['period']!='2026Q3' or not r['pub'] or r['pub']>day or not px or px<9000 or not sh or not ref or min(sh,ref)<=0 or abs(sh/ref-1)>.005:continue
        cap=px*sh/1e9;profit=num(r,'parent_profit');eq=num(r,'parent_equity')
        if profit is None or eq is None or min(profit,eq)<=0:continue
        vals[s]=(cap/profit,cap/eq,cap,profit,eq)
    # At least 3 comparable names; never silently call this the entire industry.
    if len(vals)<3:return {}
    spe=sum(x[2] for x in vals.values())/sum(x[3] for x in vals.values());spb=sum(x[2] for x in vals.values())/sum(x[4] for x in vals.values())
    result={s:evaluate(rows[s],pe,pb,cap,spe,spb,'eod',day) for s,(pe,pb,cap,*_) in vals.items()}
    for e in result.values():e['peer_count']=len(vals)
    return result

def latest_prices(eod,meta):
    import pandas as pd
    m=json.loads(Path(meta).read_text(encoding='utf-8-sig'));day=pd.Timestamp(m['latest_date']).normalize()
    if pd.isna(day) or day.date()>datetime.now(timezone(timedelta(hours=7))).date():raise ValueError('FERT_INVALID_EOD_DATE')
    df=pd.read_csv(eod,usecols=['Mã','Ngày','Giá đóng cửa'],dtype={'Mã':str},encoding='utf-8-sig');raw=df['Ngày'].astype(str).str.strip();iso=raw.str.match(r'^\d{4}-\d{2}-\d{2}')
    parsed=pd.to_datetime(raw.where(~iso),format='mixed',dayfirst=True,errors='coerce');parsed.loc[iso]=pd.to_datetime(raw.loc[iso].str[:10],format='%Y-%m-%d',errors='coerce');df['Ngày']=parsed.dt.normalize()
    if df['Ngày'].max()!=day:raise ValueError('FERT_META_MISMATCH')
    failed={str(x).split(':',1)[0].strip() for x in m.get('failed',[])};prices={}
    for s,g in df.loc[df['Ngày'].eq(day)&df['Mã'].isin(SYMBOLS)].groupby('Mã'):
        if len(g)!=1 or s in failed:continue
        px=num(g.iloc[0],'Giá đóng cửa')
        if px is not None and px>0:prices[s]=px*1000
    return day.date().isoformat(),prices

def resolve(rows,day,prices,shares):
    if not ASOF<=day<=EXPIRES:return {}
    live=dynamic(rows,day,prices,shares)
    if live:return ranked(live)
    # Snapshot used only for its dated session, with actual EOD price near implied snapshot price.
    # No stale snapshot carried to a new trading session.
    if day!=ASOF:return {}
    out={}
    for s,e in snapshot(rows).items():
        px=prices.get(s);r=rows[s];ref=num(r,'shares');cap=num(r,'cap')
        if px is None or px<9000 or not ref or not cap or abs(px/(cap*1e9/ref)-1)>.01:continue
        e['warnings'].append('Định giá ảnh SStock ngày 27/11/2026; chưa đủ điều kiện tính EOD')
        out[s]=e
    return ranked(out)

@lru_cache(maxsize=3)
def cached(i,e,m,sh):
    from port_fa import read_shares
    day,prices=latest_prices(e[0],m[0]);return day,prices,resolve(read_rows(i[0]),day,prices,read_shares(sh[0]))
def lookup(symbol):
    s=str(symbol).strip().upper()
    if s in EXCLUDED:return None,['FA tham khảo | Phân bón | Không chấm V1','FA Phân bón: loại khỏi V1 do dữ liệu chưa xác minh']
    if s not in SCORED:return None,[]
    try:day,prices,results=cached(stamp(PATH),stamp(EOD),stamp(META),stamp(SHARES))
    except (OSError,ValueError,KeyError,TypeError,OverflowError):return None,['FA Phân bón: chưa xác minh được dữ liệu EOD/đầu vào']
    if s not in prices:return None,['FA Phân bón: chưa có giá EOD hợp lệ cùng phiên']
    if prices[s]<9000:return None,['FA Phân bón: giá EOD dưới 9.000đ; không xếp hạng theo dõi']
    e=results.get(s);return (e,notes(e)) if e else (None,['FA Phân bón: thiếu dữ liệu định giá đồng phiên hoặc ngoài kỳ hiệu lực'])

def notes(e):
    r,v,p=e['raw'],e['v'],e['points'];mode='EOD ước tính '+e['day'] if e['mode']=='eod' else 'Ảnh SStock cập nhật 27/11/2026; chưa xác nhận phiên giá'
    out=['FA tham khảo | Phân bón | BCTC '+r['period']+' | '+mode+' | '+SCOPE]
    def top(k):
        a=e['ranks'].get(k)
        return f' | TOP {a[0]}/{a[1]} '+('cùng nhóm' if k in ('margin','net_margin','wc') else 'mã Phân bón') if a else ''
    def label(k):
        if p[k] is None:return 'Thiếu dữ liệu'
        f=p[k]/WEIGHTS[k];return 'Rất tốt' if f>=.9 else 'Tốt' if f>=.75 else 'Khá' if f>=.6 else 'Trung bình' if f>=.4 else 'Yếu' if f>0 else 'Rất yếu'
    for k,n in LABELS.items():
        x=v[k];val=fmt(x*100 if k=='cfo_ratio' and x is not None else x)+('%' if k in PERCENT else ' ngày' if k=='wc' else 'x')
        if k=='wc':n='Tồn kho';val+=' | TB 3 năm: '+fmt(v['wc_hist'])+' ngày'
        if k=='interest_cover' and v['interest']==0:val='Không phát sinh lãi vay'
        if k=='profit_growth' and x is None and v['profit'] is not None and v['profit_prev'] is not None:val='Phục hồi từ lỗ' if v['profit']>0 else 'Thua lỗ/hòa vốn'
        if k=='cfo_ratio' and v['profit'] is not None and v['profit']<=0:val='CFO '+fmt(v['cfo'])+' tỷ; LNST không dương'
        out.append(f'{n} {val} – {label(k)} | {fmt(p[k])}/{WEIGHTS[k]}'+top(k))
    for k in ('pb','pe'):
        x,a,b=v[k],v[k+'_hist'],v['sector_'+k];n='P/B' if k=='pb' else 'P/E';pts=[p[k+'_hist'],p[k+'_industry']];sector=f'TB {e.get("peer_count",4)} mã EOD' if e['mode']=='eod' else 'TB Phân bón & BVTV (ảnh 27/11)'
        out.append(f'{n} {fmt(x)}x | TB 3 năm: {fmt(a)} ({cmp(x,a)}) | {sector}: {fmt(b)} ({cmp(x,b)}) | {fmt(sum(t for t in pts if t is not None))}/{WEIGHTS[k+"_hist"]+WEIGHTS[k+"_industry"]}'+(' (thiếu tham chiếu)' if None in pts else '')+top(k))
    if e['score'] is None:out.insert(0,f'Chưa đủ dữ liệu FA: {fmt(e["subtotal"])}/{fmt(e["coverage"])} điểm khả dụng; không xếp loại')
    if e['warnings']:
        risks=[w for w in e['warnings'] if not w.startswith('Định giá ảnh')]
        tech=[w for w in e['warnings'] if w.startswith('Định giá ảnh')]
        if risks:out.append('Rủi ro: '+'; '.join(risks))
        if tech:out.append('Chi tiết: '+'; '.join(tech))
    out.append('Chi tiết: '+mode+'; nguồn BCTC Vietcap Q3/2026, định giá SStock 27/11/2026. EV = vốn hóa + nợ vay + lợi ích CĐ không kiểm soát - tiền và tương đương tiền (chưa trừ đầu tư ngắn hạn). EBITDA = LNTT + lãi vay + khấu hao. ROE/ROA bình quân đầu/cuối TTM; DIO bình quân tồn kho đầu/cuối TTM chia giá vốn TTM × 365; TB 12 kỳ TTM trước. TB 3–4 mã EOD = tổng vốn hóa/tổng LNST công ty mẹ hoặc vốn chủ công ty mẹ. TB ảnh Phân bón & BVTV gồm cả thuốc BVTV. Không phải toàn ngành.')
    out.append('Động lực: '+DRIVERS[r['group']])
    return out

def compact_notes(tags):
    out=[]
    for raw in tags or []:
        t=str(raw)
        if t.startswith(('FA tham khảo |','Chi tiết:','Động lực:','Nghiên cứu tham khảo:')):continue
        if t.startswith(('Rủi ro:','Chưa đủ dữ liệu FA:','FA Phân bón:')):out.append(t);continue
        t=re.sub(r' \| (?:\d[\d.,]*|—)/\d+(?:\.\d+)?(?= \| TOP | \(thiếu tham chiếu\)|$)','',t)
        out.append(t.replace('TB ngành (ảnh):','TB ngành:'))
    return out

def for_symbol(symbol):
    e,t=lookup(symbol);return (e['score'] if e else None),t

def detail(symbol):
    _,t=lookup(symbol);return 'FERTILIZER FA V1 – tham khảo, không xếp hạng VIP chính thức. '+ '; '.join(t)
