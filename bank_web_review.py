"""Bank research: fixed server configuration or session upload. No official inputs, global cache, writes or VIP side effects."""
import csv, io, math, hashlib
from datetime import date, datetime
from zoneinfo import ZoneInfo
import bank_fa as b

METRICS=('ROE','NIM','CASA','NPL','LLR')
COLUMNS=('symbol','period_end','published_date',*METRICS,'equity_parent_VND','shares_capital_q3','shares_history','treasury_book_value_VND')
STATE='bank_web_review_v1_rows'
HASH='bank_web_review_v1_hash'
EPOCH='bank_web_review_v1_epoch'

def parse(data, today=None):
    today=today or datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).date()
    if len(data)>128_000: raise ValueError('File quá lớn')
    reader=csv.DictReader(io.StringIO(data.decode('utf-8-sig')))
    if not reader.fieldnames or len(set(reader.fieldnames))!=len(reader.fieldnames) or not set(COLUMNS)<=set(reader.fieldnames):
        raise ValueError('Sai cấu trúc CSV BANK WEB REVIEW')
    rows={}
    for r in reader:
        s=r['symbol'].strip().upper()
        if s not in b.BANKS or s in rows: raise ValueError('Mã không hợp lệ hoặc trùng: '+s)
        p=date.fromisoformat(r['period_end']); pub=date.fromisoformat(r['published_date'])
        if (p.month,p.day) not in ((3,31),(6,30),(9,30),(12,31)) or not p<=pub<=today: raise ValueError('Kỳ/ngày công bố không hợp lệ: '+s)
        v={k:b.num(r,k) for k in METRICS}
        if any(x is None for x in v.values()): raise ValueError('Chỉ tiêu thiếu/sai miền: '+s)
        eq,cap,sh,tr=(float(r[k]) for k in COLUMNS[-4:])
        if not all(math.isfinite(x) for x in (eq,cap,sh,tr)) or cap<=0 or sh<=0: raise ValueError('Cơ sở vốn không hợp lệ: '+s)
        match=eq>0 and abs(sh/cap-1)<=.0001 and tr==0
        # Research estimate only: quarterly parent equity / latest candidate shares.
        # No assumption that a paid issuance has been added to quarterly equity.
        status=r.get('shares_review_status','')
        basis=r.get('basis_status','')
        note=('Cơ sở vốn Q3 khớp; chưa xác minh biến động vốn' if match else 'Ước tính: vốn chủ Q3 chưa điều chỉnh biến động vốn/cổ phiếu quỹ')
        if status=='CONFLICT_PENDING': note+=' · Xung đột nguồn số cổ phiếu'
        rows[s]=dict(symbol=s,period_end=str(p),published_date=str(pub),**v,
                     bvps=eq/sh if eq>0 else None,capital_check=note,
                     shares=sh,shares_source=r.get('shares_source','Nguồn CSV cũ; chưa rõ ngày hiệu lực'),
                     shares_asof=r.get('shares_retrieved_date',''),shares_review_status=status,basis_status=basis)
    if set(rows)!=set(b.BANKS): raise ValueError('File phải đủ 28 mã ngân hàng, không trùng')
    return rows

def points(k,v):
    return next((p for t,p in b.BANDS[k] if (v<=t if k in ('NPL','PB') else v>=t)),0)

def score(row, price=None, price_day=None, fresh=False, today=None):
    today=today or datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).date()
    p=date.fromisoformat(row['period_end']); pub=date.fromisoformat(row['published_date'])
    usable=p<=pub<=today
    old_period=(today-p).days>180
    v={k:row[k] for k in METRICS}
    pts={k:points(k,v[k]) for k in METRICS}
    quality=sum(pts.values()) if usable else None
    pb=None
    try:
        px=float(price); day=date.fromisoformat(str(price_day)[:10]); bvps=row['bvps']
        if usable and fresh and pub<=day<=today and bvps and math.isfinite(px) and px>0:
            ratio=px*1000/bvps
            if math.isfinite(ratio) and .000001<=ratio<=200: pb=ratio
    except (ValueError,TypeError,OverflowError): pass
    pp=points('PB',pb) if pb is not None else None
    risk=v['NPL']>3 or v['LLR']<50 or v['ROE']<8
    return {'Mã':row['symbol'],'FA tham khảo /100':quality+pp if quality is not None and pp is not None else None,
            'Tài chính /85':quality,'P/B ứng viên':pb,'Điểm P/B /15':pp,**v,
            'BVPS ứng viên (VND)':row['bvps'],'Giá EOD (nghìn VND)':price if fresh else None,
            'Phiên giá':str(price_day)[:10] if fresh else '', 'Kỳ':row['period_end'],'Công bố':row['published_date'],
            'Rủi ro':'Cảnh báo' if risk else 'Không vượt ngưỡng',
            'Trạng thái':(row['capital_check'] + (' · BCTC trên 180 ngày; cần cập nhật quý mới' if old_period else '')) if usable else 'Ngày công bố không hợp lệ',
            'CP lưu hành ứng viên':row.get('shares'),'Nguồn CP':row.get('shares_source',''),'Ngày tra cứu CP':row.get('shares_asof',''),
            **{k+' điểm':v if usable else None for k,v in pts.items()}}

def current_prices(frames_d,asof):
    import pandas as pd
    from market_eod_guard import stale
    out={}
    if not isinstance(frames_d,pd.DataFrame) or not {'Mã','Ngày','Giá đóng cửa'}<=set(frames_d.columns): return out
    try:
        expected=pd.Timestamp(asof)
        if pd.isna(expected) or stale(expected):return out
    except (TypeError,ValueError,OverflowError):return out
    view=frames_d.loc[frames_d['Mã'].isin(b.BANKS),['Mã','Ngày','Giá đóng cửa']].copy()
    view['Ngày']=pd.to_datetime(view['Ngày'],errors='coerce');view=view.dropna(subset=['Ngày'])
    for s,g in view.groupby('Mã'):
        g=g.sort_values('Ngày'); day=g['Ngày'].iat[-1]
        if day.date()!=expected.date() or stale(day):continue
        last=g[g['Ngày']==day]['Giá đóng cửa']; nums=pd.to_numeric(last,errors='coerce')
        if len(nums)!=1 or not math.isfinite(float(nums.iloc[0])) or nums.iloc[0]<=0:continue
        out[s]=(float(nums.iloc[0]),day.date(),True)
    return out

# BANK_FIXED_V2: configured dataset stays server-side; never cache private rows globally.
def fixed_rows(config, today=None):
    import base64
    # Owner/private_app are compatibility aliases for a PRIVATE Streamlit deployment.
    # Never expose this dataset on a public deployment without distribution permission.
    mode=config.get('mode','owner')
    if mode not in ('owner','private_app','public'):
        raise ValueError('Sai chế độ BANK FIXED')
    if mode=='public' and config.get('distribution_rights_confirmed') is not True:
        raise ValueError('Chưa xác nhận quyền công bố dữ liệu')
    encoded=config.get('csv_b64','')
    if not isinstance(encoded,str) or len(encoded)>172000:
        raise ValueError('Dữ liệu BANK FIXED không hợp lệ')
    return parse(base64.b64decode(encoded,validate=True),today=today)


def fixed_ui(st,key):
    # Authentication belongs to Streamlit private sharing, not the bank panel.
    try:
        config=st.secrets.get('bank_fixed_v2')
    except (FileNotFoundError, KeyError):
        return False,None
    if config is None:
        return False,None
    try:
        rows=fixed_rows(config)
    except (ValueError,TypeError,KeyError,UnicodeError,csv.Error):
        st.error('BANK FA: cấu hình hoặc dữ liệu quý không hợp lệ. Kiểm tra Secrets.')
        return True,None
    st.caption('Dữ liệu ngân hàng cố định theo quý · FA ước tính · Dùng cho phân tích cá nhân; không tự thay đổi khuyến nghị VIP.')
    return True,rows


def resolve_rows(st,key):
    st.markdown('**BANK FA · Dữ liệu quý (ước tính)**')
    configured, rows = fixed_ui(st,key)
    if configured and rows is None:
        return None
    if not configured:
        st.caption('Nạp CSV cá nhân vào phiên đang dùng. Không lưu vào GitHub/R2, dùng cho điểm tham khảo cá nhân, không tự thay đổi VIP. P/B ước tính theo vốn chủ Q3 và số cổ phiếu ứng viên; chưa xác minh biến động vốn.')
        epoch=st.session_state.get(EPOCH,0)
        with st.expander('Nạp / xóa dữ liệu ngân hàng',expanded=STATE not in st.session_state):
            uploaded=st.file_uploader('Chọn BANK_REVIEW_28.csv',type=['csv'],key=f'bank_review_upload_{key}_{epoch}')
            if uploaded is not None:
                raw=uploaded.getvalue(); sig=hashlib.sha256(raw).hexdigest()
                if st.session_state.get(HASH)!=sig:
                    try:
                        rows=parse(raw);st.session_state[STATE]=rows;st.session_state[HASH]=sig
                    except (ValueError,UnicodeError,TypeError,KeyError,csv.Error) as err:
                        st.error('Không nhập được: '+str(err));return None
            if STATE in st.session_state:
                if st.button('Xóa dữ liệu khỏi phiên',key=f'bank_review_clear_{key}_{epoch}'):
                    st.session_state.pop(STATE,None);st.session_state.pop(HASH,None);st.session_state[EPOCH]=epoch+1;st.rerun()
        rows=st.session_state.get(STATE)
    if not rows:
        st.info('Chưa có dữ liệu cố định. Thêm hoặc thay nhóm [bank_fixed_v2] trong Streamlit Secrets.');return None
    return rows

def chart_review(rows, symbol, frames_d, asof):
    if not rows or symbol not in rows:return None
    prices=current_prices(frames_d,asof)
    return score(rows[symbol],*prices.get(symbol,(None,None,False)))


def render(frames_d,asof,*,symbol=None,key='rank',resolved=False,rows=None):
    import streamlit as st
    import pandas as pd
    if not resolved: rows=resolve_rows(st,key)
    if not rows:return
    prices=current_prices(frames_d,asof)
    data=[score(r,*prices.get(s,(None,None,False))) for s,r in rows.items()]
    df=pd.DataFrame(data)
    c1,c2=st.columns(2);c1.metric('Có điểm tài chính',f"{df['Tài chính /85'].notna().sum()}/28");c2.metric('Có FA tham khảo',f"{df['FA tham khảo /100'].notna().sum()}/28")
    st.caption('P/B ước tính = giá EOD / (vốn chủ Q3 / số CP ứng viên). Chưa điều chỉnh tiền thu phát hành hoặc cổ tức sau kỳ. Mã có xung đột nguồn được ghi chú. Dùng cho FA và tổng điểm tham khảo; không tự thay đổi khuyến nghị VIP.')
    if symbol is not None:
        r=next((r for r in data if r['Mã']==symbol),None)
        if r is None:return
        a,c,d=st.columns(3)
        a.metric('FA tham khảo', '—' if r['FA tham khảo /100'] is None else f"{r['FA tham khảo /100']}/100")
        c.metric('Tài chính', '—' if r['Tài chính /85'] is None else f"{r['Tài chính /85']}/85")
        d.metric('P/B ứng viên','—' if r['P/B ứng viên'] is None else f"{r['P/B ứng viên']:.2f}x")
        if r['Rủi ro']=='Cảnh báo':st.warning('Vượt ít nhất một ngưỡng rủi ro BANK FA.')
        st.caption(r['Trạng thái']+' · Kỳ '+r['Kỳ']+' · Phiên giá '+(r['Phiên giá'] or 'Chưa đủ'))
        st.caption('CP ứng viên: '+format(r['CP lưu hành ứng viên'],',.0f')+' · '+r['Nguồn CP']+' · Ngày tra cứu: '+(r['Ngày tra cứu CP'] or 'Chưa rõ'))
        st.dataframe(pd.DataFrame([{'Chỉ tiêu':k,'Giá trị':r[k],'Điểm':r[k+' điểm'],'Tối đa':b.WEIGHTS[k]} for k in METRICS]+[{'Chỉ tiêu':'P/B','Giá trị':r['P/B ứng viên'],'Điểm':r['Điểm P/B /15'],'Tối đa':15}]),hide_index=True,use_container_width=True)
    else:
        df=df.sort_values(['FA tham khảo /100','Tài chính /85','Mã'],ascending=[False,False,True],na_position='last')
        st.dataframe(df,hide_index=True,use_container_width=True)
