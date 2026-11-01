"""Read-only stock overview built from local EOD, 15m and optional metadata.

No VNStock requests, no writes, no customer/portfolio files, no secrets reads.
"""
from __future__ import annotations

from pathlib import Path
import math
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

EOD_COLS = ('Ngày', 'Giá mở cửa', 'Giá cao nhất', 'Giá thấp nhất', 'Giá đóng cửa', 'Khối lượng khớp lệnh')
INTRADAY = Path('data/intraday_15m.csv')
FOREIGN = Path('data/foreign_net_flow.csv')


def number(x):
    """Return finite float or None. Never synthesize missing fundamentals."""
    try:
        y = float(pd.to_numeric(x, errors='coerce'))
        return y if math.isfinite(y) else None
    except (ValueError, TypeError):
        return None


def display(x, style=',.2f', suffix=''):
    v = number(x)
    return '—' if v is None else f'{v:{style}}{suffix}'


def text_value(x):
    if x is None or pd.isna(x) or not str(x).strip():
        return 'Chưa có dữ liệu'
    return str(x).strip()


@st.cache_data(show_spinner=False, max_entries=6)
def read_table(path: str, mtime_ns: int):
    # mtime_ns participates in the cache key; no cached missing-file response.
    return pd.read_csv(path, encoding='utf-8-sig', low_memory=False)


def row_for_code(path: str, code: str):
    p = Path(path)
    if not p.is_file():
        return {}
    try:
        frame = read_table(str(p), p.stat().st_mtime_ns)
        if 'Mã' not in frame.columns:
            return {}
        matching = frame[frame['Mã'].astype(str).str.strip().str.upper().eq(code)]
        return matching.iloc[-1].to_dict() if not matching.empty else {}
    except (OSError, ValueError, KeyError, UnicodeDecodeError):
        return {}


def intraday_for_code(code):
    p = INTRADAY
    if not p.is_file():
        return pd.DataFrame()
    try:
        d = read_table(str(p), p.stat().st_mtime_ns)
        required = {'symbol', 'time', 'open', 'high', 'low', 'close', 'volume'}
        if not required.issubset(d.columns):
            return pd.DataFrame()
        d = d.loc[d['symbol'].astype(str).str.upper().eq(code), list(required)].copy()
        if d.empty:
            return d
        d['time'] = pd.to_datetime(d['time'], errors='coerce', utc=True).dt.tz_convert('Asia/Ho_Chi_Minh')
        for col in ['open', 'high', 'low', 'close', 'volume']:
            d[col] = pd.to_numeric(d[col], errors='coerce')
        d = d.dropna(subset=['time', 'open', 'high', 'low', 'close', 'volume'])
        d = d[(d[['open','high','low','close']].min(axis=1)>0) & (d['volume']>=0) &
              (d['high']>=d[['open','close','low']].max(axis=1)) &
              (d['low']<=d[['open','close','high']].min(axis=1))]
        d = d.drop_duplicates('time', keep='last').sort_values('time')
        # The source collector is responsible for finalized bars. Do not present
        # an unfinished bar as confirmed if one is unexpectedly present.
        now = pd.Timestamp.now(tz='Asia/Ho_Chi_Minh')
        d = d.loc[d['time'] + pd.Timedelta(minutes=15) <= now]
        return d.tail(400)
    except (OSError, ValueError, KeyError, UnicodeDecodeError, TypeError):
        return pd.DataFrame()


def foreign_for_code(code):
    """Only verified rank entries, no invented 20-day or full-market totals."""
    p = FOREIGN
    if not p.is_file():
        return pd.DataFrame()
    try:
        d = read_table(str(p), p.stat().st_mtime_ns)
        if not {'symbol','trading_date','net_value_vnd','source_scope'}.issubset(d.columns):
            return pd.DataFrame()
        d = d[d['symbol'].astype(str).str.upper().eq(code)].copy()
        d['date'] = pd.to_datetime(d['trading_date'], errors='coerce')
        d['net_ty'] = pd.to_numeric(d['net_value_vnd'], errors='coerce') / 1e9
        return d.dropna(subset=['date','net_ty']).drop_duplicates('date', keep='last').sort_values('date').tail(20)
    except (OSError, ValueError, KeyError, UnicodeDecodeError, TypeError):
        return pd.DataFrame()


def normalize_eod(g):
    if g is None or g.empty or not set(EOD_COLS).issubset(g.columns):
        return pd.DataFrame()
    d = g[list(EOD_COLS)].copy()
    d['Ngày'] = pd.to_datetime(d['Ngày'], errors='coerce', dayfirst=True, format='mixed')
    for col in EOD_COLS[1:]:
        d[col] = pd.to_numeric(d[col], errors='coerce')
    d = d.dropna(subset=EOD_COLS)
    d = d[(d['Giá đóng cửa']>0)&(d['Giá cao nhất']>=d['Giá thấp nhất'])]
    return d.sort_values('Ngày').drop_duplicates('Ngày', keep='last')


def make_candle(d, intraday=False):
    x = d['time'].dt.strftime('%d/%m %H:%M') if intraday else d['Ngày']
    o,h,l,c,v = ('open','high','low','close','volume') if intraday else EOD_COLS[1:]
    fig=make_subplots(rows=2,cols=1,shared_xaxes=True,vertical_spacing=.045,row_heights=[.76,.24])
    fig.add_trace(go.Candlestick(x=x,open=d[o],high=d[h],low=d[l],close=d[c],name='OHLC',
                                 increasing_line_color='#089981',decreasing_line_color='#F23645'),row=1,col=1)
    fig.add_trace(go.Bar(x=x,y=d[v],name='KL',marker_color='#b48329',opacity=.65),row=2,col=1)
    fig.update_layout(template='plotly_dark',height=340,margin=dict(l=8,r=8,t=10,b=15),
                      paper_bgcolor='rgba(0,0,0,0)',plot_bgcolor='rgba(0,0,0,0)',
                      showlegend=False,xaxis_rangeslider_visible=False)
    fig.update_xaxes(showgrid=False)
    if intraday:
        fig.update_xaxes(type='category', nticks=12)
    return fig




def quick_chart_period(d, intraday, period):
    """Show real candles at the selected interval from *stored* EOD or 15m data.

    MIN_HOURLY_CANDLE_STYLE_V1: 1H and VN-session 4H are OHLC aggregates of 15m,
    not four 15m candles disguised as a 1H chart. Missing bars are not fabricated.
    """
    if d is None or d.empty:
        return pd.DataFrame(), False, 'Chưa có dữ liệu giá EOD để tham chiếu.'
    latest_eod = pd.to_datetime(d.iloc[-1]['Ngày']).date()
    valid = pd.DataFrame()
    if intraday is not None and not intraday.empty and 'time' in intraday.columns:
        valid = intraday.dropna(subset=['time']).sort_values('time')
    has_current_15m = (not valid.empty and
                       valid.iloc[-1]['time'].date() >= latest_eod)
    if period == '15 phút':
        if valid.empty:
            return pd.DataFrame(), True, 'Chưa có nến 15 phút đã đóng của mã này.'
        return valid.tail(200), True, (
            f'15 phút: nến gần nhất {valid.iloc[-1]["time"]:%d/%m/%Y %H:%M}; không phải realtime.')
    if period in ('1 giờ', '4 giờ'):
        if valid.empty:
            return pd.DataFrame(), True, 'Chưa có dữ liệu 15 phút để tạo nến giờ OHLC.'
        src=valid.copy()
        # Floor by Vietnam exchange wall-clock hours; 4H = one Vietnam session.
        bucket=(src['time'].dt.floor('h') if period == '1 giờ'
                else src['time'].dt.normalize())
        src['_hour_bucket']=bucket
        candles=src.groupby('_hour_bucket',sort=True).agg({
            'time':'last','open':'first','high':'max','low':'min',
            'close':'last','volume':'sum'}).reset_index(drop=True)
        candles=candles.tail(140 if period == '1 giờ' else 65)
        stamp=candles.iloc[-1]['time']
        stale_note='' if has_current_15m else ' · Dữ liệu giờ chưa cập nhật tới phiên EOD mới nhất.'
        vn_note=' · 4H = một phiên khớp lệnh Việt Nam (không phải nến 4 giờ quốc tế).' if period=='4 giờ' else ''
        return candles, True, (
            f'{period}: {len(candles)} nến OHLC tổng hợp từ 15m đã lưu; '
            f'nến mới nhất đến {stamp:%d/%m/%Y %H:%M}.'+vn_note+stale_note+
            ' Nến giờ có thể thiếu dữ liệu khi thiếu nến 15m.')
    if period in ('1 ngày','1 tuần'):
        days = 1 if period == '1 ngày' else 5
        if has_current_15m:
            dates = sorted(valid['time'].dt.date.unique())[-days:]
            portion = valid.loc[valid['time'].dt.date.isin(set(dates))]
            if not portion.empty:
                return portion, True, (
                    f'{period}: {len(dates)}/{days} phiên có nến 15m đã đóng; '
                    f'mới nhất {portion.iloc[-1]["time"]:%d/%m/%Y %H:%M}.')
        return d.tail(days), False, (
            f'{period}: nến 15 phút chưa đủ mới; dùng {min(len(d),days)} nến EOD đã xác nhận.')
    size = {'1 tháng':21,'3 tháng':63,'6 tháng':126,'1 năm':252,'Tất cả':len(d)}.get(period)
    if size is None:
        raise ValueError('Unknown stock quick-chart range: '+str(period))
    return d.tail(size), False, ''


def render_profile(g, code, fund):
    """Stock profile UI, never writes back to EOD and never calls a vendor API."""
    code = str(code).upper().strip()
    d = normalize_eod(g)
    if d.empty:
        st.warning('Chưa đủ dữ liệu giá EOD hợp lệ để hiển thị thông tin chung.')
        return
    latest, previous = d.iloc[-1], d.iloc[-2] if len(d)>1 else None
    eod_close=number(latest['Giá đóng cửa'])
    change = (eod_close/number(previous['Giá đóng cửa'])-1)*100 if previous is not None and number(previous['Giá đóng cửa']) else None
    date=latest['Ngày'].strftime('%d/%m/%Y')

    general=row_for_code('data/thong_tin_chung.csv', code)
    bctc=row_for_code('data/bctc.csv', code)
    shares=row_for_code('data/shares_outstanding.csv',code)
    intraday=intraday_for_code(code)
    foreign=foreign_for_code(code)
    name=text_value(fund.get('Tên công ty'))
    if name=='Chưa có dữ liệu':
        name=code
    sector=text_value(bctc.get('Ngành'))
    exchange=text_value(bctc.get('Sàn'))

    st.markdown(f'### {code} · {name}')
    st.caption(f'{exchange} · {sector} · Giá EOD đã xác nhận: {date} · Theo dõi 15m từ nến đã đóng (nếu có)')
    k1,k2,k3,k4=st.columns(4)
    k1.metric('Giá EOD (nghìn đồng)',display(eod_close),f'{change:+.2f}%' if change is not None else None)
    k2.metric('KL EOD (cp)',display(latest['Khối lượng khớp lệnh'],',.0f'))
    k3.metric('Vốn hóa (tỷ đồng)', display(fund.get('Vốn hóa TT'),',.0f'))
    k4.metric('Giá 15m đã đóng (nghìn đồng)' if not intraday.empty else 'Biên độ EOD',
              display(intraday.iloc[-1]['close']) if not intraday.empty else display((number(latest['Giá cao nhất'])/number(latest['Giá thấp nhất'])-1)*100 if number(latest['Giá thấp nhất']) else None,'.2f','%'))
    st.caption(f"OHLC EOD ({date}): O {display(latest['Giá mở cửa'])} · H {display(latest['Giá cao nhất'])} · L {display(latest['Giá thấp nhất'])} · C {display(latest['Giá đóng cửa'])}" +
               (f" | 15m đã đóng: {intraday.iloc[-1]['time']:%d/%m %H:%M}" if not intraday.empty else ' | Chưa có nến 15m của mã'))

    left,right=st.columns([1.35,1],gap='large')
    with left:
        st.markdown('**Biểu đồ nhanh**')
        # QUICK_CHART_V3_1H_1D_1W: explicit choices; new widget key clears stale UI state.
        choices = ['15 phút','1 giờ','4 giờ','1 ngày','1 tuần','1 tháng','3 tháng','6 tháng','1 năm','Tất cả']
        default = '1 ngày' if not intraday.empty else '1 tháng'
        period = st.selectbox('Khoảng biểu đồ', choices, index=choices.index(default),
                              key=f'min_profile_quick_v4_{code}')
        st.caption('Xem nhanh · 1H và 4H tổng hợp nến OHLC từ 15m; 1 ngày / 1 tuần dùng nến 15m đã đóng khi có; kỳ dài dùng EOD.')
        selected, use_intra, period_note = quick_chart_period(d, intraday, period)
        if period_note:
            st.caption(period_note)
        if selected.empty:
            st.info('Chưa đủ dữ liệu nến đã đóng cho khoảng thời gian này. Chọn kỳ dài hơn hoặc kiểm tra lần cập nhật 15m.')
        else:
            st.plotly_chart(make_candle(selected,use_intra), use_container_width=True)
        st.caption('Biểu đồ nhanh từ dữ liệu đã lưu. Tab Biểu đồ chính giữ đầy đủ 6 khung và bộ chỉ báo.')
    with right:
        st.markdown('**Hồ sơ doanh nghiệp & định giá**')
        slcp = number(general.get('SLCP lưu hành (cp)')) or number(shares.get('Số CP lưu hành'))
        freefloat = number(general.get('%freefloat'))
        capital = number(general.get('Vốn điều lệ (tỷ)'))
        rows=[('Mã / Sàn',f'{code} / {exchange}'),('Ngành',sector),
              ('Vốn điều lệ (tỷ)',display(capital,',.0f')),
              ('SLCP lưu hành (cp)',display(slcp,',.0f')),
              ('Free float (%)',display(freefloat,'.2f')),
              ('P/E',display(fund.get('P/E'),'.2f')),
              ('P/B',display(fund.get('P/B'),'.2f')),
              ('ROE (%)',display(bctc.get('ROE TTM (%)') if number(bctc.get('ROE TTM (%)')) is not None else fund.get('ROE'),'.2f')),
              ('ROA TTM (%)',display(bctc.get('ROA TTM (%)'),'.2f')),
              ('Kỳ BCTC',text_value(bctc.get('Kỳ BCTC'))),
              ('Website',text_value(general.get('Website')))]
        st.dataframe(pd.DataFrame(rows,columns=['Chỉ tiêu','Giá trị']), hide_index=True,use_container_width=True,height=404)
        st.caption('Số liệu cơ bản lấy từ file đã được kiểm tra; trường thiếu hiển thị —, không tự điền số giả.')

    st.markdown('**Dòng tiền và thanh khoản**')
    a,b,c=st.columns(3)
    with a:
        with st.container(border=True):
            st.markdown('**Khối ngoại**')
            if foreign.empty:
                st.caption('Chưa có bản ghi xác minh cho mã này. Mã không thuộc Top không được mặc định bằng 0.')
            else:
                last=foreign.iloc[-1]
                st.metric('Mua/bán ròng (tỷ)',display(last['net_ty'],'+,.2f'))
                st.caption(f'{last["date"]:%d/%m/%Y} · {text_value(last["source_scope"])}; không đại diện toàn thị trường')
                if len(foreign)>1:
                    st.plotly_chart(go.Figure(go.Bar(x=foreign['date'],y=foreign['net_ty'],marker_color='#1eac85'))
                                    .update_layout(template='plotly_dark',height=165,margin=dict(l=5,r=5,t=0,b=0),
                                                   paper_bgcolor='rgba(0,0,0,0)',plot_bgcolor='rgba(0,0,0,0)'),use_container_width=True)
    with b:
        with st.container(border=True):
            st.markdown('**Tự doanh**')
            # MIN_PROP_STOCK_COMPACT_V1
            from proprietary_dashboard import render_compact
            render_compact(code)
    with c:
        with st.container(border=True):
            st.markdown('**Thanh khoản EOD**')
            vol=d['Khối lượng khớp lệnh']; avg20=vol.tail(20).mean() if len(vol)>=20 else None
            ratio=number(vol.iloc[-1])/avg20 if avg20 else None
            st.metric('KL so với TB20',display(ratio,'.2f','x'))
            st.caption('KL TB20: '+display(avg20,',.0f')+' cp · EOD '+date)

    # MIN_PROP_STOCK_DETAILS_V1
    with st.expander('📈 Tự doanh · Bảng giao dịch và biểu đồ 20 phiên', expanded=False):
        from proprietary_dashboard import render_detail
        render_detail(code, d)

    st.caption('Thông tin phục vụ nghiên cứu cá nhân. Nguồn EOD / Intraday / BCTC có thời điểm cập nhật khác nhau.')
