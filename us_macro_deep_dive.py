"""Multi-session market context and dedicated drill-down for US macro quotes.

Uses historical, timestamped Yahoo closes already supplied by us_overnight_macro.
No external API calls, generated quote values, or trading recommendations.
"""
from __future__ import annotations

from datetime import date, datetime
from math import isfinite
from zoneinfo import ZoneInfo
from html import escape

import pandas as pd
import streamlit as st
import us_macro_impact as IMPACT

VN_ZONE = ZoneInfo('Asia/Ho_Chi_Minh')
WINDOWS = (5, 10, 20, 60, 120, 252)
# Cumulative thresholds are separate from a single-day noise threshold.
CUMULATIVE_THRESHOLD = {
    '^DJI': 1.5, '^GSPC': 1.5, '^IXIC': 2.0, 'DX-Y.NYB': 0.6,
    '^TNX': 8.0, '^VIX': 8.0, 'BZ=F': 3.0, 'CL=F': 3.0, 'GC=F': 2.0,
}

EXPLAIN = {
    '^DJI': (
        'Dow Jones theo dõi 30 doanh nghiệp lớn của Mỹ, nghiêng về nhóm doanh nghiệp trưởng thành và chu kỳ.',
        'Xu hướng nhiều phiên phản ánh tâm lý với chu kỳ kinh tế Mỹ. Ảnh hưởng tới VN-Index chủ yếu qua tâm lý quốc tế và dòng vốn, không phải quan hệ nhân quả trực tiếp.',
        'Độ rộng thị trường Mỹ, S&P 500, VIX, dòng vốn ngoại và thanh khoản VN.'),
    '^GSPC': (
        'S&P 500 là chỉ số rộng của cổ phiếu vốn hóa lớn Mỹ.',
        'Chuỗi tăng/giảm bền vững có thể tác động khẩu vị rủi ro. Cần phân biệt đà tăng tập trung vào vài cổ phiếu hay lan rộng toàn thị trường.',
        'VIX, DXY, lợi suất Mỹ, khối ngoại và độ rộng VN-Index.'),
    '^IXIC': (
        'Nasdaq Composite có trọng số đáng kể ở nhóm công nghệ và tăng trưởng.',
        'Đà giảm kéo dài, đặc biệt khi lợi suất tăng, có thể khiến các cổ phiếu định giá cao thận trọng hơn. Ảnh hưởng tới cổ phiếu công nghệ Việt Nam không cơ học.',
        'Lợi suất Mỹ, S&P 500 và diễn biến thực tế nhóm công nghệ tại Việt Nam.'),
    'DX-Y.NYB': (
        'DXY đo sức mạnh USD so với rổ sáu ngoại tệ chính, không phải tỷ giá USD/VND.',
        'DXY duy trì vùng cao hoặc tăng liên tục có thể gây sức ép tỷ giá và dòng vốn vào thị trường mới nổi, khiến việc nới lỏng lãi suất trong nước khó khăn hơn. Tuy nhiên tác động tùy cung cầu USD trong nước, điều hành tỷ giá và kỳ vọng lãi suất Mỹ.',
        'USD/VND liên ngân hàng và ngân hàng, tỷ giá trung tâm, lãi suất liên ngân hàng, khối ngoại mua/bán ròng, lợi suất TPCP Mỹ.'),
    '^TNX': (
        'Đây là lợi suất trái phiếu Kho bạc Mỹ 10 năm, không phải mức giá trái phiếu. 1 điểm phần trăm = 100 điểm cơ bản.',
        'Lợi suất cao kéo dài có thể nâng chi phí chiết khấu tài sản rủi ro và tạo sức ép dòng vốn. Lợi suất tăng do tăng trưởng mạnh khác với tăng do lo ngại lạm phát.',
        'Mức thay đổi tính bằng điểm cơ bản; DXY, tỷ giá USD/VND, Fed và lãi suất Việt Nam.'),
    '^VIX': (
        'VIX đo biến động kỳ vọng 30 ngày của S&P 500, không phải xác suất VN-Index giảm.',
        'Một phiên VIX giảm chưa đủ xóa trạng thái căng thẳng nếu chỉ số vẫn cao và đã tăng mạnh nhiều phiên. Xem đồng thời mức tuyệt đối, xu hướng tích lũy và S&P 500.',
        'Ngưỡng VIX tương đối trong 60/252 phiên, S&P 500, thanh khoản VN và dòng vốn ngoại.'),
    'BZ=F': (
        'Brent là giá hợp đồng tương lai dầu thô tham chiếu quốc tế, khác với giá xăng bán lẻ Việt Nam.',
        'Dầu cao kéo dài có thể hỗ trợ mảng khai thác và dịch vụ dầu khí nhưng gia tăng chi phí đầu vào ở các ngành vận tải/tiêu thụ nhiều nhiên liệu. Lợi nhuận lọc dầu phụ thuộc crack spread.',
        'WTI, chênh lệch giá sản phẩm–dầu thô, kỳ điều chỉnh xăng dầu trong nước và nguyên nhân dầu tăng.'),
    'CL=F': (
        'WTI là giá hợp đồng tương lai dầu tham chiếu Mỹ; cần theo dõi cùng Brent.',
        'WTI tăng nhiều phiên cùng Brent có thể xác nhận xu hướng dầu, nhưng giá bán nhiên liệu và biên lợi nhuận từng doanh nghiệp Việt Nam còn phụ thuộc yếu tố nội địa.',
        'Brent, chênh lệch Brent–WTI, biên lợi nhuận dầu khí và giá xăng dầu Việt Nam.'),
    'GC=F': (
        'GC=F là giá hợp đồng tương lai vàng, không phải giá vàng vật chất tại Việt Nam.',
        'Vàng cao có thể phản ánh nhu cầu phòng thủ, lạm phát hoặc kỳ vọng USD/lãi suất. Không có quy luật vàng tăng đồng nghĩa chứng khoán giảm. Doanh nghiệp trang sức chịu tác động của tồn kho, biên giá và sức mua.',
        'DXY, lợi suất thực Mỹ, VIX, chênh lệch vàng trong nước–thế giới và chính sách tồn kho.'),
}


def _fmt_pct(x: float | None) -> str:
    return '—' if x is None else f'{x:+.2f}%'.replace('.', ',')


def evaluate(item: dict, today: date | None = None) -> dict:
    """Compute returns at n sessions, local range position, and cumulative bias.

    Exactly n prior sessions are used: close[-1]/close[-n-1]-1.
    ^TNX cumulative deltas are basis points, not relative percentages.
    No conclusion if quote is stale, invalid or without enough history.
    """
    today = today or datetime.now(VN_ZONE).date()
    if not item.get('ok'):
        return {'valid': False, 'message': 'Nguồn chưa có báo giá đã xác minh.'}
    try:
        symbol = str(item['symbol'])
        latest_date = date.fromisoformat(item['session_date'])
        points = [float(x) for x in item['points']]
        days = list(item['days'])
        if len(points) != len(days) or len(points) < 3:
            raise ValueError('Length mismatch')
        if any(not isfinite(x) or x <= 0 for x in points):
            raise ValueError('Invalid price')
        if any(days[i] >= days[i+1] for i in range(len(days)-1)):
            raise ValueError('Dates not ascending')
        if date.fromisoformat(days[-1]) != latest_date:
            raise ValueError('Session date mismatch')
        if abs(points[-1] / float(item['price']) - 1) > 0.0000001:
            raise ValueError('Last price mismatch')
    except (KeyError, ValueError, TypeError, OverflowError, ZeroDivisionError):
        return {'valid': False, 'message': 'Lịch sử giá không hợp lệ để phân tích lũy kế.'}
    age = (today - latest_date).days
    if age < -1 or age > 5:
        return {'valid': False, 'message': 'Dữ liệu phiên đã cũ hoặc có ngày bất thường; không suy diễn trạng thái hiện tại.'}
    last = points[-1]
    is_yield = symbol == '^TNX'
    changes: dict[int, float | None] = {}
    for n in WINDOWS:
        if len(points) >= n + 1:
            changes[n] = (last - points[-n-1]) * 100.0 if is_yield else (last / points[-n-1] - 1) * 100.0
        else:
            changes[n] = None
    ma20 = sum(points[-20:]) / 20 if len(points) >= 20 else None
    ma60 = sum(points[-60:]) / 60 if len(points) >= 60 else None
    positions: dict[int, dict] = {}
    for n in (20, 60, 252):
        if len(points) >= n:
            section = points[-n:]
            low, high = min(section), max(section)
            pct = (last - low) / (high - low) * 100.0 if high > low else 50.0
            positions[n] = {'low': low, 'high': high, 'position': pct,
                            'near_high': last >= high * 0.98}
    # Combine 20 and 60-session regimes. A tiny one-day move cannot erase a
    # persistent uptrend. A clearly opposing 20-session move *can* invalidate it.
    threshold = CUMULATIVE_THRESHOLD.get(symbol, 1.5)
    trend, trend_n = 'insufficient', None
    for n in (20, 60, 120, 10, 5):
        value = changes.get(n)
        if value is None:
            continue
        limit = threshold * (2.0 if n == 120 else 1.0)
        recent20 = changes.get(20)
        if n >= 60 and recent20 is not None:
            # A substantial counter-move in the last month takes precedence.
            if value > 0 and recent20 <= -threshold * 0.5:
                continue
            if value < 0 and recent20 >= threshold * 0.5:
                continue
        if value >= limit:
            trend, trend_n = 'up', n
            break
        if value <= -limit:
            trend, trend_n = 'down', n
            break
    if trend_n is None:
        trend_n = next((n for n in (20, 60, 10, 5) if changes.get(n) is not None), None)
        trend = 'sideways' if trend_n is not None else 'insufficient'
    p60 = positions.get(60, {}).get('position')
    p252 = positions.get(252, {}).get('position')
    if p252 is not None and p252 >= 85:
        zone = 'Gần vùng cao 252 phiên'
    elif p60 is not None and p60 >= 80:
        zone = 'Vùng cao 60 phiên'
    elif p60 is not None and p60 <= 20:
        zone = 'Vùng thấp 60 phiên'
    elif p60 is not None:
        zone = 'Giữa biên độ 60 phiên'
    else:
        zone = 'Chưa đủ dữ liệu định vị vùng giá'
    if trend == 'up':
        bias = 'Xu hướng tích lũy tăng'
    elif trend == 'down':
        bias = 'Xu hướng tích lũy giảm'
    elif trend == 'sideways':
        bias = 'Tích lũy đi ngang/chưa đủ độ lớn'
    else:
        bias = 'Chưa đủ lịch sử'
    return {'valid': True, 'symbol': symbol, 'change': changes, 'last': last, 'age': age,
            'latest_date': latest_date, 'ma20': ma20, 'ma60': ma60, 'positions': positions,
            'trend': trend, 'trend_window': trend_n, 'bias': bias, 'zone': zone,
            'is_yield': is_yield, 'points': points, 'days': days,
            'daily_change': float(item['change_pct'])}


def short_html(item: dict) -> str:
    """Compact non-authoritative read: daily vs cumulative; detail is click-to-open."""
    result = evaluate(item)
    if not result['valid']:
        return '<div class="usn-impact usn-impact-stale"><div class="usn-impact-title">XU HƯỚNG LŨY KẾ</div><div class="usn-impact-note">' + escape(result['message']) + '</div></div>'
    n = result['trend_window']
    val = result['change'].get(n) if n else None
    unit = ' điểm cơ bản' if result['is_yield'] else '%'
    cum = (f'{val:+.1f}' if result['is_yield'] else f'{val:+.2f}') + unit if val is not None else '—'
    text = f'Phiên gần nhất {_fmt_pct(result["daily_change"])} · Lũy kế {n or "—"} phiên: {cum}'
    zone = f'{result["zone"]} · {result["bias"]}'
    return ('<div class="usn-impact"><div class="usn-impact-title">XU HƯỚNG NHIỀU PHIÊN</div>'
            f'<div class="usn-impact-note">{escape(text)}</div>'
            f'<div class="usn-impact-check">{escape(zone)}</div>'
            '<div class="usn-impact-check">Chọn <b>Phân tích chi tiết</b> để xem tác động đến chứng khoán VN.</div></div>')


def render_detail(item: dict, spec: tuple[str, str, str]) -> None:
    symbol, label, unit = spec
    st.title(f'Phân tích Vĩ mô · {label}')
    st.caption('Báo giá từ Yahoo Finance (không chính thức), đánh giá lịch sử nhiều phiên. Không phải tín hiệu giao dịch.')
    data = evaluate(item)
    if not data['valid']:
        st.warning(data['message'])
        return
    change = data['change']
    val = data['last']
    st.caption(f'Phiên dữ liệu: {data["latest_date"]:%d/%m/%Y} · Mức độ đánh giá chỉ so với chuỗi giá được cung cấp, không phải toàn bộ lịch sử.')
    a,b,c = st.columns(3)
    a.metric('Giá / mức hiện tại', f'{val:,.2f}'.replace(',', '~').replace('.', ',').replace('~', '.') + ('%' if unit == 'yield' else ''),
             _fmt_pct(data['daily_change']))
    v20 = change.get(20)
    v60 = change.get(60)
    unit_ = ' bp' if data['is_yield'] else '%'
    b.metric('Lũy kế 20 phiên', (f'{v20:+.1f}' if data['is_yield'] else f'{v20:+.2f}') + unit_ if v20 is not None else '—')
    c.metric('Lũy kế 60 phiên', (f'{v60:+.1f}' if data['is_yield'] else f'{v60:+.2f}') + unit_ if v60 is not None else '—')
    st.markdown(f'**Đánh giá:** {data["zone"]} · {data["bias"]}. Một phiên giảm/tăng nhẹ không đủ đảo chiều xu hướng tích lũy.')

    periods = [5, 10, 20, 60, 120, 252]
    table = []
    for n in periods:
        v = change[n]
        if v is not None:
            table.append({'Khoảng': f'{n} phiên', 'Biến động lũy kế':
                          (f'{v:+.1f} bp' if data['is_yield'] else f'{v:+.2f}%'),
                          'Diễn giải': 'Tăng' if v>0 else 'Giảm' if v<0 else 'Đi ngang'})
        else:
            table.append({'Khoảng': f'{n} phiên', 'Biến động lũy kế': '—', 'Diễn giải': 'Chưa đủ lịch sử'})
    st.subheader('1. Biến động tích lũy theo các khung')
    st.dataframe(pd.DataFrame(table), hide_index=True, use_container_width=True)

    win = st.selectbox('Khoảng thời gian trên biểu đồ', [60, 120, 252, 500],
                       format_func=lambda x: f'{x} phiên gần nhất', key=f'usn_period_{symbol}')
    subset = pd.DataFrame({'Ngày': pd.to_datetime(data['days'][-win:]), 'Giá': data['points'][-win:]})
    st.line_chart(subset.set_index('Ngày'), height=270)
    st.caption('Biểu đồ chỉ gồm các phiên đã có dữ liệu. Vùng cao 60/252 phiên là vị trí tương đối, không có nghĩa đang ở đỉnh lịch sử.')
    for n in (20, 60, 252):
        v = data['positions'].get(n)
        if v:
            st.caption(f'Vùng {n} phiên: thấp {v["low"]:,.2f} · cao {v["high"]:,.2f} · vị trí hiện tại {v["position"]:.0f}% biên độ.')
    st.caption('MA20: ' + (f'{data["ma20"]:.2f}' if data['ma20'] else '—') +
               ' · MA60: ' + (f'{data["ma60"]:.2f}' if data['ma60'] else '—'))

    what, channel, watch = EXPLAIN[symbol]
    st.subheader('2. Ý nghĩa và tác động có thể có đến Việt Nam')
    st.markdown(what)
    st.markdown(channel)
    st.markdown('**Đọc trong bối cảnh hiện tại:** ' + (
        'Đà tăng nhiều phiên đáng chú ý dù biến động ngày cuối có thể giảm.' if data['trend']=='up' else
        'Đà giảm nhiều phiên đáng chú ý dù phiên gần nhất có thể hồi.' if data['trend']=='down' else
        'Chưa có xung lực đủ rõ theo ngưỡng phân loại; cần đối chiếu thêm các yếu tố khác.'))
    rules = IMPACT.RULES.get(symbol, {})
    if rules:
        with st.expander('Nếu chỉ số DUY TRÌ TĂNG: nhóm hưởng lợi, nhóm chịu áp lực', expanded=(data['trend']=='up')):
            note, benefits, pressures, check = rules['up']
            st.write(note)
            st.markdown('**Có thể hưởng lợi:** ' + benefits)
            st.markdown('**Có thể chịu áp lực:** ' + pressures)
            st.markdown('**Cần xác nhận:** ' + check)
        with st.expander('Nếu chỉ số DUY TRÌ GIẢM: nhóm hưởng lợi, nhóm chịu áp lực', expanded=(data['trend']=='down')):
            note, benefits, pressures, check = rules['down']
            st.write(note)
            st.markdown('**Có thể hưởng lợi:** ' + benefits)
            st.markdown('**Có thể chịu áp lực:** ' + pressures)
            st.markdown('**Cần xác nhận:** ' + check)
    st.subheader('3. Điều kiện cần theo dõi')
    st.write(watch)
    st.caption('Đây là kịch bản định tính theo cơ chế kinh tế, không phải xác nhận rằng một nhóm ngành đã tăng/giảm trên thị trường Việt Nam. Cần đối chiếu dữ liệu giá, khối ngoại, tỷ giá và điều kiện riêng của doanh nghiệp.')
