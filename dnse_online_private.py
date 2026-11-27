"""DNSE display for an already access-controlled private Streamlit app. No trading or TA changes."""
import hashlib, hmac, json, re
from datetime import date
from decimal import Decimal
from dnse_online_validate import validate, windows, number, qty
from dnse_online_card import card_html, price_warning, prior_volume_ma20
from foreign_session_card import _dates, calendar_sessions
MAX_BYTES=12_000_000

def valid_day(day):
    return isinstance(day,str) and bool(re.fullmatch(r'\d{4}-\d{2}-\d{2}',day)) and date.fromisoformat(day).isoformat()==day

def object_key(conf,day):
    if not valid_day(day): raise ValueError('date')
    return conf['prefix']+'/dnse-personal-v1/'+day+'.json'

def decode(blob,sha,day):
    if len(blob)>MAX_BYTES or not hmac.compare_digest(hashlib.sha256(blob).hexdigest(),str(sha)):raise ValueError('checksum')
    b=json.loads(blob)
    if b['version']!=1 or b['target']!=day or b['dates']!=sorted(set(b['dates'])) or len(b['dates'])!=20 or b['dates'][-1]!=day or not all(valid_day(d) for d in b['dates']):raise ValueError('calendar')
    if len(b['scope'])!=239 or b['scope']!=sorted(set(b['scope'])) or not all(re.fullmatch('[A-Z0-9]{3}',s) for s in b['scope']):raise ValueError('scope')
    if not isinstance(b['rows'],dict) or not isinstance(b['quotes'],dict) or len(b['rows'])>4780:raise ValueError('rows')
    return b

def models_for(b,code,dates,daily):
    if dates!=b['dates'] or code not in b['scope']:return None,None
    own=daily.loc[daily['Mã'].astype(str).str.strip().str.upper().eq(code)].copy()
    own['_day']=_dates(own['Ngày'].tolist()).dt.strftime('%Y-%m-%d').values
    rows=[]; last_e=None
    for d in dates:
        try:
            g=own.loc[own['_day'].eq(d)]
            if len(g)!=1:raise ValueError('eod row')
            x=g.iloc[0];e=tuple(number(x[k])*1000 for k in ('Giá thấp nhất','Giá cao nhất','Giá đóng cửa'))+(qty(x['Khối lượng khớp lệnh']),)
            r=b['rows'][code+'_'+d];rows.append(validate(r,code,d,e))
            if d==dates[-1]:last_e=e
        except (ValueError,KeyError,TypeError):rows.append(None)
    q=None
    if last_e:
        try:
            raw=b['quotes'][code]
            if number(raw['close'])!=last_e[2] or qty(raw['volume'])!=last_e[3]:raise ValueError('quote eod')
            floor,ceil=raw['floor'],raw['ceiling']
            if type(floor)!=bool or type(ceil)!=bool or (floor and ceil):raise ValueError('flags')
            q=dict(close=last_e[2],volume=last_e[3],floor=floor,ceiling=ceil,offer=qty(raw['offer']) if floor and raw['offer'] is not None else None,bid=qty(raw['bid']) if ceil and raw['bid'] is not None else None)
        except (ValueError,KeyError,TypeError):pass
    return windows(rows,dates),q

def enabled():
    import streamlit as st
    try:return st.secrets.get('dnse_personal',{}).get('enabled') is True
    except Exception:return False

def _download(day):
    import streamlit as st
    import r2_bridge as R
    conf=R.config_from_mapping(st.secrets)
    if not conf:raise ValueError('R2 config')
    response=R.client(conf).get_object(Bucket=conf['bucket'],Key=object_key(conf,day))
    try:blob=response['Body'].read(MAX_BYTES+1)
    finally:response['Body'].close()
    return decode(blob,response.get('Metadata',{}).get('sha256'),day)

def render(code,daily,asof,*,key,dark=True):
    import streamlit as st
    if not enabled():return
    with st.container(border=True):
        try:
            dates=[d.strftime('%Y-%m-%d') for d in calendar_sessions(daily,asof,period=20)]
            if len(dates)!=20:raise ValueError('calendar')
            code=str(code).strip().upper()
            b=st.cache_data(ttl=120,max_entries=4,show_spinner=False)(_download)(dates[-1])
            models,q=models_for(b,code,dates,daily)
            if models is None:st.caption('DNSE: mã hoặc lịch phiên chưa được xác minh.');return
            ma20=prior_volume_ma20(daily,code,dates) if q and (q['floor'] or q['ceiling']) else None
            st.markdown(card_html(models,dark=dark,price_warning=price_warning(daily,code,dates),quote=q,code=code,date=dates[-1],prior_ma20=ma20,source='DNSE'),unsafe_allow_html=True)
        except Exception:
            st.caption('DNSE: chưa có dữ liệu đã xác minh cho phiên đang xem hoặc R2 chưa sẵn sàng. Không dùng dữ liệu phiên cũ thay thế.')
