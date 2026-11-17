"""US stock indices, rates and commodity dashboard for Trạm Tín Hiệu > Vĩ mô.

The data is obtained from Yahoo Finance's unofficial, rate-limited chart v8
endpoint. It is not an exchange-certified real-time feed. Quotes and their
sparklines derive from the same series; stale/failing symbols are not fabricated.
Only this Streamlit fragment reruns every 15 minutes while the page is open.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from html import escape
import json
import math
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

import streamlit as st
import us_macro_impact as IMPACT  # MIN_MACRO_SECTOR_IMPACT_V1
import us_macro_deep_dive as DEEP  # MIN_MACRO_MULTISESSION_V1

TZ_VN = ZoneInfo('Asia/Ho_Chi_Minh')
USER_AGENT = 'Mozilla/5.0 (compatible; TramTinHieuMacro/1.0)'
REFRESH_SECONDS = 900
CACHE_SECONDS = 600

# Symbol, Vietnamese label, units.  ^TNX is already quoted in percent by Yahoo.
INSTRUMENTS = (
    ('^DJI', 'DOW JONES', 'index'),
    ('^GSPC', 'S&P 500', 'index'),
    ('^IXIC', 'NASDAQ', 'index'),
    ('DX-Y.NYB', 'DXY (USD)', 'index'),
    ('^TNX', 'LỢI SUẤT TP MỸ 10 NĂM', 'yield'),
    ('^VIX', 'VIX (CHỈ SỐ SỢ HÃI)', 'index'),
    ('BZ=F', 'DẦU BRENT', 'oil'),
    ('CL=F', 'DẦU WTI', 'oil'),
    ('GC=F', 'VÀNG THẾ GIỚI', 'gold'),
)


def parse_chart(payload: dict, symbol: str) -> dict:
    """Parse verified daily closes and latest quote time from Yahoo's chart v8.

    Return only values observed in Yahoo response. No synthetic dates or prices.
    """
    chart = payload.get('chart') or {}
    if chart.get('error'):
        raise ValueError('Yahoo báo lỗi dữ liệu')
    results = chart.get('result') or []
    if not results or not isinstance(results[0], dict):
        raise ValueError('Không có kết quả từ nguồn')
    result = results[0]
    meta = result.get('meta') or {}
    series_list = (result.get('indicators') or {}).get('quote') or []
    stamps = result.get('timestamp') or []
    if not series_list or not stamps:
        raise ValueError('Không có chuỗi dữ liệu giá')
    closes = series_list[0].get('close') or []
    if not isinstance(closes, list) or len(closes) != len(stamps):
        raise ValueError('Chuỗi giá và thời gian không khớp')
    latest_by_date: dict[str, tuple[int, float]] = {}
    exchange_tz = meta.get('exchangeTimezoneName') or 'UTC'
    try:
        tz = ZoneInfo(exchange_tz)
    except (KeyError, ValueError):
        tz = timezone.utc
    for ts, raw_price in zip(stamps, closes):
        try:
            timestamp = int(ts)
            price = float(raw_price)
            if not math.isfinite(price) or price <= 0:
                continue
            day = datetime.fromtimestamp(timestamp, timezone.utc).astimezone(tz).strftime('%Y-%m-%d')
        except (TypeError, ValueError, OverflowError, OSError):
            continue
        latest_by_date[day] = (timestamp, price)
    values = sorted(latest_by_date.items())
    if len(values) < 3:
        raise ValueError('Không đủ dữ liệu phiên để so sánh')
    last = values[-1][1][1]
    previous = values[-2][1][1]
    change = (last / previous - 1) * 100
    if not math.isfinite(change):
        raise ValueError('Mức thay đổi không hợp lệ')
    quote_ts = meta.get('regularMarketTime')
    try:
        quote_ts = int(quote_ts)
        if quote_ts <= 0:
            quote_ts = None
    except (ValueError, TypeError):
        quote_ts = None
    return {
        'symbol': symbol,
        'price': last,
        'previous': previous,
        'change_pct': change,
        'days': [day for day, _ in values],
        'points': [v[1] for _, v in values],
        'session_date': values[-1][0],
        'market_time': quote_ts,
    }


def _fetch_one(symbol: str) -> dict:
    err = None
    for host in ('query1.finance.yahoo.com', 'query2.finance.yahoo.com'):
        url = ('https://' + host + '/v8/finance/chart/' + quote(symbol, safe='')
               + '?range=2y&interval=1d')
        request = Request(url, headers={'User-Agent': USER_AGENT, 'Accept': 'application/json'})
        try:
            with urlopen(request, timeout=8) as response:
                raw = response.read(1_500_000)
            result = parse_chart(json.loads(raw), symbol)
            return {'ok': True, **result}
        except (HTTPError, URLError, TimeoutError, OSError, ValueError, TypeError,
                KeyError, json.JSONDecodeError) as exc:
            err = type(exc).__name__
    return {'ok': False, 'symbol': symbol, 'reason': err or 'Nguồn không khả dụng'}


@st.cache_data(ttl=CACHE_SECONDS, show_spinner=False, max_entries=2)
def _fetch_all() -> tuple[list[dict], str]:
    """Fetch in parallel, but cache on Streamlit's main execution thread."""
    got = {}
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(_fetch_one, spec[0]): spec[0] for spec in INSTRUMENTS}
        for fut in as_completed(futures):
            symbol = futures[fut]
            try:
                got[symbol] = fut.result()
            except Exception:
                got[symbol] = {'ok': False, 'symbol': symbol, 'reason': 'Lỗi kết nối'}
    fetched = datetime.now(TZ_VN).strftime('%H:%M %d/%m/%Y')
    return [got[spec[0]] for spec in INSTRUMENTS], fetched


def _number(value: float, unit: str) -> str:
    if unit == 'index' and value >= 1000:
        text = f'{value:,.0f}'
    else:
        text = f'{value:,.2f}'
    # Vietnamese numeric convention: thousands dot, decimal comma.
    text = text.replace(',', '~').replace('.', ',').replace('~', '.')
    if unit == 'yield':
        text += '%'
    return text


def _spark_svg(points: list[float], idx: int, positive: bool) -> str:
    if len(points) < 3:
        return ''
    width, height = 300, 78
    low, high = min(points), max(points)
    span = high - low or max(abs(low) * .005, 1.0)
    coords = [(i * width / (len(points) - 1), 7 + (high - v) / span * 60)
              for i, v in enumerate(points)]
    line = ' '.join(f'{x:.1f},{y:.1f}' for x, y in coords)
    fill_path = ('M ' + ' L '.join(f'{x:.1f},{y:.1f}' for x, y in coords)
                 + f' L {width},75 L 0,75 Z')
    color = '#21c6a1' if positive else '#fc4e78'
    grad = f'usn-grad-{idx}'
    return (f'<svg viewBox="0 0 {width} {height}" role="img" '
            'aria-label="Biến động giá 3 tháng" preserveAspectRatio="none" '
            'style="width:100%;height:86px;display:block">'
            f'<defs><linearGradient id="{grad}" x1="0" y1="0" x2="0" y2="1">'
            f'<stop offset="0%" stop-color="{color}" stop-opacity="0.24"/>'
            f'<stop offset="100%" stop-color="{color}" stop-opacity="0.02"/>'
            '</linearGradient></defs>'
            f'<path d="{fill_path}" fill="url(#{grad})" />'
            f'<polyline points="{line}" fill="none" stroke="{color}" '
            'stroke-width="2.7" stroke-linejoin="round" stroke-linecap="round" />'
            f'<circle cx="{coords[-1][0]:.1f}" cy="{coords[-1][1]:.1f}" r="3.7" fill="{color}" />'
            '</svg>')


def _card(item: dict, spec: tuple[str, str, str], idx: int) -> str:
    symbol, label, unit = spec
    href = 'https://finance.yahoo.com/quote/' + quote(symbol, safe='') + '/'
    if not item.get('ok'):
        return (f'<article class="usn-card usn-unavailable">'
                f'<div class="usn-label">{escape(label)}</div>'
                '<div class="usn-head"><span class="usn-price">—</span>'
                '<span class="usn-change usn-neutral">Chưa có dữ liệu</span></div>'
                '<div class="usn-asof">Không nhận được giá từ nguồn</div>'
                '<div class="usn-blank">Đang chờ dữ liệu hợp lệ</div>'
                f'{DEEP.short_html(item)}'
                f'<a class="usn-link" href="{href}" target="_blank" '
                'rel="noopener noreferrer">Xem nguồn ↗</a></article>')
    positive = item['change_pct'] >= 0
    change = item['change_pct']
    change_text = f'{change:+.2f}%'.replace('.', ',')
    day = datetime.strptime(item['session_date'], '%Y-%m-%d').strftime('%d/%m/%Y')
    market_ts = item.get('market_time')
    market_label = ''
    if market_ts is not None:
        stamp = datetime.fromtimestamp(market_ts, timezone.utc).astimezone(TZ_VN)
        market_label = f' · báo giá {stamp:%H:%M %d/%m} VN'
    extra = {'gold': 'USD/oz · HĐTL', 'oil': 'USD/thùng · HĐTL',
             'yield': 'Lợi suất (%)', 'index': 'Điểm chỉ số'}[unit]
    return (
        '<article class="usn-card">'
        f'<div class="usn-label">{escape(label)}</div>'
        f'<div class="usn-head"><span class="usn-price">{_number(item["price"], unit)}</span>'
        f'<span class="usn-change {"usn-up" if positive else "usn-down"}">{change_text}</span></div>'
        f'<div class="usn-asof">Phiên {day}{market_label}</div>'
        f'<div class="usn-chart">{_spark_svg(item["points"][-64:], idx, positive)}</div>'
        f'<div class="usn-footer"><span>{extra}</span>'
        f'<a class="usn-link" href="{href}" target="_blank" '
        'rel="noopener noreferrer">Yahoo Finance ↗</a></div>'
        f'{DEEP.short_html(item)}'
        '</article>'
    )


CSS = """
<style>
.usn-shell{margin:16px 0 22px;max-width:1500px}
.usn-headline{text-align:center;margin:10px 0 26px}
.usn-kicker{font-size:12px;font-weight:800;letter-spacing:2px;color:#e1b557}
.usn-title{color:var(--txt2,#e8edfa);font-size:clamp(22px,3vw,33px);font-weight:800;
  line-height:1.35;margin:5px 0 3px;letter-spacing:.4px}
.usn-subtitle{font-size:13px;color:var(--muted,#9aabc2)}
.usn-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:15px 20px}
.usn-card{background:#111a2d;border:1px solid #24334e;border-radius:14px;padding:17px 18px 12px;
  min-width:0;box-shadow:0 2px 6px rgba(0,0,0,.12);color:#ecf2fa}
.usn-label{font-size:13px;font-weight:800;color:#8c9cba;letter-spacing:.45px;min-height:30px}
.usn-head{display:flex;align-items:baseline;justify-content:space-between;gap:10px;flex-wrap:wrap}
.usn-price{font-size:clamp(22px,2.45vw,31px);font-weight:750;font-variant-numeric:tabular-nums;white-space:nowrap}
.usn-change{font-size:clamp(14px,1.4vw,20px);font-weight:800;white-space:nowrap}
.usn-up{color:#26c8a3}.usn-down{color:#fa537a}.usn-neutral{color:#a9b5ca;font-size:13px}
.usn-asof{font-size:11px;color:#899bb7;min-height:24px;margin:5px 0}
.usn-chart{margin-top:3px}.usn-blank{height:86px;display:flex;align-items:center;justify-content:center;color:#7184a4;font-size:12px}
.usn-footer{display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap;
  font-size:10.5px;color:#899bb7;margin-top:4px}
.usn-link{color:#93b6e4!important;text-decoration:none!important}.usn-link:hover{text-decoration:underline!important}
.usn-impact{background:#0a1325;border:1px solid #293b56;border-radius:9px;
  margin-top:12px;padding:11px 12px;color:#dbe6f5;font-size:11.5px;line-height:1.48}
.usn-impact-title{color:#e9b85c;font-size:10.5px;font-weight:800;letter-spacing:.45px;margin-bottom:5px}
.usn-impact-move{font-size:11px;color:#b9cbea;margin-bottom:5px;font-weight:650}
.usn-impact-note{color:#d4deed;margin:5px 0 8px}
.usn-impact-line{padding:4px 0;border-top:1px solid #24354c;overflow-wrap:anywhere}
.usn-impact-line b{color:#f3f5ff}
.usn-impact-check{margin:6px 0 0;color:#a9bdcf;overflow-wrap:anywhere}
.usn-impact-check b{color:#e9b85c}
.usn-impact-neutral .usn-impact-note,.usn-impact-stale .usn-impact-note{color:#9bb0c9}
.usn-divider{border-top:1px solid #bb9250;margin:26px 0 14px}
.usn-footer-title{color:var(--txt2,#e8edfa);font-size:16px;font-weight:800;letter-spacing:.35px}
.usn-source-note{font-size:12px;color:var(--muted,#94a3b8);line-height:1.6;margin:9px 0 3px}
@media(max-width:900px){.usn-grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}}
@media(max-width:600px){.usn-grid{grid-template-columns:1fr}.usn-card{padding:14px 16px 10px}}
</style>
"""


@st.fragment(run_every='15min')
def _live_dashboard() -> None:
    with st.spinner('Đang kiểm tra dữ liệu thị trường quốc tế...'):
        quotes, fetched_at = _fetch_all()
    instruments = {spec[0]: spec for spec in INSTRUMENTS}
    by_symbol = {q['symbol']: q for q in quotes}
    count = sum(bool(q.get('ok')) for q in quotes)
    st.markdown(CSS, unsafe_allow_html=True)
    st.markdown(
        '<div class="usn-headline">'
        '<div class="usn-kicker">TRẠM TÍN HIỆU · MIN TRADING</div>'
        '<div class="usn-title">THỊ TRƯỜNG MỸ &amp; HÀNG HÓA ĐÊM QUA</div>'
        '<div class="usn-subtitle">Bấm Phân tích chi tiết tại từng chỉ số để xem lũy kế '
        '5/10/20/60/120/252 phiên, vị trí vùng giá và tác động tới chứng khoán Việt Nam.</div>'
        '</div>', unsafe_allow_html=True)
    selected = st.session_state.get('us_macro_selected_symbol')
    if selected in instruments:
        if st.button('← Quay lại bảng 9 chỉ số', key='usn_macro_back'):
            st.session_state['us_macro_selected_symbol'] = None
            st.rerun(scope='fragment')
        DEEP.render_detail(by_symbol.get(selected, {'ok': False}), instruments[selected])
        return
    # Native Streamlit buttons avoid injected JavaScript / untrusted external links.
    # One button per tile; selecting a tile shows ONLY its full analysis.
    for start in range(0, len(INSTRUMENTS), 3):
        cols = st.columns(3, gap='medium')
        for idx in range(start, min(start + 3, len(INSTRUMENTS))):
            spec = INSTRUMENTS[idx]
            symbol = spec[0]
            with cols[idx - start]:
                st.markdown(_card(by_symbol.get(symbol, {'ok': False, 'symbol': symbol}), spec, idx),
                            unsafe_allow_html=True)
                if st.button(f'Phân tích chi tiết · {spec[1]}',
                             key=f'usn_macro_open_{idx}', use_container_width=True):
                    st.session_state['us_macro_selected_symbol'] = symbol
                    st.rerun(scope='fragment')
    st.markdown(
        '<div class="usn-divider"></div><div class="usn-footer-title">TẬP TRUNG CỔ PHIẾU HƠN CHỈ SỐ</div>'
        '<div class="usn-source-note">'
        'Nguồn Yahoo Finance không chính thức: không phải báo giá trực tiếp. '
        'Biểu đồ nhỏ là khoảng 3 tháng gần nhất; tính xu hướng lũy kế bằng lịch sử 2 năm. '
        f'Truy vấn lúc {escape(fetched_at)} giờ VN · {count}/9 chỉ số có dữ liệu. '
        'Làm mới mỗi 15 phút khi trang được mở. '
        'Ảnh hưởng tới ngành Việt Nam là kịch bản định tính có điều kiện, '
        'không thay thế việc kiểm tra dữ liệu trong nước hay khuyến nghị mua/bán.'
        '</div>', unsafe_allow_html=True)
    if count == 0:
        st.warning('Nguồn chưa trả dữ liệu; không suy diễn từ giá giả hoặc dữ liệu cũ.')


def render() -> None:
    """Mount the dashboard only when the macro page is selected."""
    _live_dashboard()
