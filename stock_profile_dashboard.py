"""Read-only stock overview built from local EOD and optional metadata.

No VNStock requests, no writes, no customer/portfolio files, no secrets reads.
"""
from __future__ import annotations

from pathlib import Path
import math
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
import hourly_native_1h as NH

EOD_COLS = ('Ngày', 'Giá mở cửa', 'Giá cao nhất', 'Giá thấp nhất', 'Giá đóng cửa', 'Khối lượng khớp lệnh')
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


def make_candle(d):
    x = d['Ngày']
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                        vertical_spacing=.045, row_heights=[.76, .24])
    fig.add_trace(go.Candlestick(x=x, open=d['Giá mở cửa'], high=d['Giá cao nhất'],
        low=d['Giá thấp nhất'], close=d['Giá đóng cửa'], name='OHLC',
        increasing_line_color='#089981', decreasing_line_color='#F23645'), row=1, col=1)
    fig.add_trace(go.Bar(x=x, y=d['Khối lượng khớp lệnh'], name='Khối lượng',
                         marker_color='#b48329', opacity=.65), row=2, col=1)
    fig.update_layout(template='plotly_dark', height=340,
        margin=dict(l=8, r=8, t=10, b=15),
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
        showlegend=False, xaxis_rangeslider_visible=False)
    fig.update_xaxes(showgrid=False, rangeslider_visible=False)
    return fig


def quick_chart_period(d, period):
    """D/W/M candles aggregated from confirmed EOD prices only."""
    if d is None or d.empty:
        return pd.DataFrame()
    if period == '1D':
        return d.tail(120).copy()
    if period not in ('1W', '1M'):
        raise ValueError('Unsupported EOD chart period: ' + str(period))
    key = d['Ngày'].dt.to_period('W-FRI' if period == '1W' else 'M')
    return d.groupby(key, sort=True).agg({
        'Ngày': 'last', 'Giá mở cửa': 'first', 'Giá cao nhất': 'max',
        'Giá thấp nhất': 'min', 'Giá đóng cửa': 'last',
        'Khối lượng khớp lệnh': 'sum'}).reset_index(drop=True).tail(156 if period == '1W' else 120)


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
    foreign=foreign_for_code(code)
    name=text_value(fund.get('Tên công ty'))
    if name=='Chưa có dữ liệu':
        name=code
    sector=text_value(bctc.get('Ngành'))
    exchange=text_value(bctc.get('Sàn'))

    st.markdown(f'### {code} · {name}')
    st.caption(f'{exchange} · {sector} · Giá EOD đã xác nhận: {date} · Khung 1H / 1D / 1W / 1M')
    k1,k2,k3,k4=st.columns(4)
    k1.metric('Giá EOD (nghìn đồng)',display(eod_close),f'{change:+.2f}%' if change is not None else None)
    k2.metric('KL EOD (cp)',display(latest['Khối lượng khớp lệnh'],',.0f'))
    k3.metric('Vốn hóa (tỷ đồng)', display(fund.get('Vốn hóa TT'),',.0f'))
    _low = number(latest['Giá thấp nhất'])
    _high = number(latest['Giá cao nhất'])
    _range = (_high / _low - 1) * 100 if _low and _high else None
    k4.metric('Biên độ EOD (%)', display(_range, '.2f', '%'))
    st.caption(f"OHLC EOD ({date}): O {display(latest['Giá mở cửa'])} · H {display(latest['Giá cao nhất'])} · L {display(latest['Giá thấp nhất'])} · C {display(latest['Giá đóng cửa'])}")

    left,right=st.columns([1.35,1],gap='large')
    with left:
        st.markdown('**Biểu đồ nhanh**')
        choices = ['1H', '1D', '1W', '1M']
        period = st.selectbox('Khung biểu đồ', choices, index=0,
                              key=f'min_profile_eod_v1_{code}')
        if period == '1H':
            p_hour = NH.FILE
            try:
                selected = NH.read_symbol(p_hour, code)
            except (OSError, ValueError, KeyError):
                selected = pd.DataFrame()
            if selected.empty:
                st.info('Chưa có nến VCI 1H nguyên gốc cho mã này trên máy chủ.')
            else:
                st.caption(f"VCI nguyên gốc 1H · tới {selected['Ngày'].iloc[-1]:%H:%M %d/%m/%Y} giờ VN")
                st.plotly_chart(make_candle(selected), use_container_width=True)
        else:
            st.caption('Nến Ngày / Tuần / Tháng đều được gộp từ giá EOD đã xác nhận.')
            selected = quick_chart_period(d, period)
            if selected.empty:
                st.info('Chưa có nến EOD cho khung thời gian đã chọn.')
            else:
                st.plotly_chart(make_candle(selected), use_container_width=True)
        st.caption(f'Giá và chỉ báo dùng ngày dữ liệu thực có của {code}; không tạo phiên bị thiếu.')
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

    st.caption('Thông tin phục vụ nghiên cứu cá nhân. Nguồn EOD / BCTC có thời điểm cập nhật khác nhau.')
