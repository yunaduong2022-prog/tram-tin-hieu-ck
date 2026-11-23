"""Read-only price-pressure ↔ market-sector context for Vietnam macro.

CPI subgroup prices and market-sector OHLCV live on different observation dates.
This bridge NEVER infers causality, profitability, money inflows or buy/sell calls.
It reuses existing sector_dashboard.calculate_sector_metrics (no duplicated scores).
"""
from __future__ import annotations

from datetime import date, datetime
import math
from zoneinfo import ZoneInfo

PRICE_FACTORS = (
    ('food', 'Thực phẩm'),
    ('fuel', 'Xăng dầu'),
    ('power', 'Điện sinh hoạt'),
    ('housing', 'Nhà ở, điện nước & VLXD'),
    ('inputs', 'Nguyên vật liệu sản xuất'),
)
# Context hypotheses only, NOT conclusions about any company's costs or margins.
EXPOSURES = (
    ('food', 'Nông nghiệp & thực phẩm', 'Giá đầu vào và khả năng điều chỉnh giá bán', 'Kiểm tra nguyên liệu mua thực, biên gộp và cơ cấu doanh thu'),
    ('food', 'Thịt & chăn nuôi', 'Giá bán thực phẩm và chi phí thức ăn có thể tác động ngược chiều', 'Kiểm tra giá bán đầu ra, giá cám, sản lượng'),
    ('food', 'Bán lẻ', 'Giá giỏ hàng và sức mua; tác động có thể hai chiều', 'Kiểm tra doanh số, biên lợi nhuận gộp và sức mua'),
    ('fuel', 'Dầu khí', 'Giá bán và giá vốn phân hóa theo khâu thượng/hạ nguồn', 'Kiểm tra crack spread, giá nhập, tồn kho và hợp đồng'),
    ('fuel', 'Vận tải', 'Nhiên liệu có thể tăng chi phí khai thác', 'Kiểm tra cơ chế phụ thu nhiên liệu và hợp đồng vận tải'),
    ('fuel', 'Vận tải biển hàng hóa', 'Giá nhiên liệu, cước và hợp đồng ảnh hưởng biên lợi nhuận', 'Kiểm tra bunker fuel, giá cước và tỷ lệ chuyển giá'),
    ('power', 'Điện', 'CPI điện sinh hoạt KHÔNG đồng nhất biểu giá đầu vào/đầu ra doanh nghiệp điện', 'Kiểm tra cơ chế giá bán, PPA, chi phí nhiên liệu và thủy văn'),
    ('power', 'Hàng công nghiệp', 'Chi phí điện sản xuất phải dùng biểu giá thực áp dụng, không lấy CPI điện dân dụng thay thế', 'Kiểm tra tỷ trọng chi phí điện và biểu giá sản xuất'),
    ('housing', 'Xây dựng', 'Giá vật liệu và đơn giá hợp đồng có thể ảnh hưởng chi phí', 'Kiểm tra backlog, hợp đồng cố định giá, công nợ và nghiệm thu'),
    ('housing', 'Vật liệu xây dựng', 'Nhu cầu xây dựng, giá bán và giá vốn biến động khác nhau', 'Kiểm tra sản lượng, giá bán, chi phí năng lượng'),
    ('housing', 'Thép', 'Nhu cầu xây dựng không đồng nghĩa giá thép hoặc biên lợi nhuận cùng chiều', 'Kiểm tra HRC, quặng, than, tồn kho và đơn hàng'),
    ('housing', 'Bất động sản', 'Chi phí xây dựng có thể ảnh hưởng giá vốn dự án', 'Kiểm tra pháp lý, tiến độ bán hàng, chi phí vốn và dòng tiền'),
    ('inputs', 'Thép', 'Chỉ số đầu vào toàn nền kinh tế không phản ánh riêng giá nguyên liệu thép', 'Kiểm tra HRC/quặng/than, giá bán và tồn kho'),
    ('inputs', 'Phân bón', 'Giá đầu vào, chi phí khí/than và giá bán phân bón cần đối chiếu riêng', 'Kiểm tra giá khí, giá bán, tồn kho và sản lượng'),
    ('inputs', 'Hàng công nghiệp', 'Giá nguyên liệu sản xuất có thể làm thay đổi giá vốn', 'Kiểm tra tỷ trọng nguyên liệu, khả năng chuyển giá và đơn hàng'),
)
MAX_PRICE_AGE_DAYS = 45
MAX_MISSED_EXPECTED_SESSIONS = 2  # Conservative, transparent T2–T6 proxy; holidays need separate confirmation.
MIN_SECTOR_MEMBERS = 3
MIN_SESSIONS = 22  # >=21 phiên để quan sát lợi suất một tháng


def _number(value):
    """Return finite number only, not 0 for missing/NaN/strings."""
    if value is None or isinstance(value, bool):
        return None
    try:
        n = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return n if math.isfinite(n) else None


def _as_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def expected_market_sessions_since(last_date, asof, *, hour_vn=None):
    """Count expected weekday closings AFTER EOD, without inventing exchange sessions.

    Saturdays and Sundays are excluded. Public holidays and special exchange closures are not removed by the
    weekday proxy; this can overstate missed sessions, so the result is
    provisional and explicitly labelled as such in the UI.
    When hour_vn is supplied and it is before 16:00, do not count today.
    """
    from datetime import timedelta
    last_date = _as_date(last_date)
    asof = _as_date(asof)
    if not last_date or not asof or last_date > asof:
        return None
    end = asof
    if hour_vn is not None and int(hour_vn) < 16:
        end -= timedelta(days=1)
    if end <= last_date:
        return 0
    return sum((last_date + timedelta(days=i)).weekday() < 5
               for i in range(1, (end - last_date).days + 1))


def compact_rows(rows):
    """UI-only formatted table. Missing measurements are a dash, never zero."""
    out = []
    for row in rows:
        r = row or {}
        ret = _number(r.get('Hiệu suất 1 tháng (%)'))
        rs = _number(r.get('RS 1 tháng (điểm %)'))
        breadth = _number(r.get('Độ rộng tăng giá (%)'))
        turn = _number(r.get('GTGD/TB20 (lần)'))
        enough = str(r.get('Trạng thái bằng chứng', '')).startswith('Đủ đối chiếu')
        out.append({
            'Ngành': str(r.get('Ngành') or '—'),
            '1 tháng': f'{ret:+.2f}%' if ret is not None else '—',
            'RS (điểm %)': f'{rs:+.2f}' if rs is not None else '—',
            'Độ rộng': f'{breadth:.1f}%' if breadth is not None else '—',
            'GTGD/TB20': f'{turn:.2f}x' if turn is not None else '—',
            'Trạng thái': str(r.get('Quan sát sức mạnh giá') or 'Đủ dữ liệu') if enough else 'Thiếu dữ liệu',
        })
    return out


def sector_evidence_summary(rows, ctx):
    """Explain observed RS/breadth/trading; never claim CPI causality or flows."""
    valid = [r for r in rows if str(r.get('Trạng thái bằng chứng', '')).startswith('Đủ đối chiếu')]
    missing = len(rows) - len(valid)
    if not valid:
        return ('Chưa đủ dữ liệu xác minh đồng thời giá ngành, nguồn RS, độ rộng và GTGD '
                'để đánh giá sức mạnh tương đối. Không suy luận dòng tiền hoặc lợi nhuận từ CPI.')
    strong = sum(_number(r.get('RS 1 tháng (điểm %)')) > 0 for r in valid)
    weak = sum(_number(r.get('RS 1 tháng (điểm %)')) < 0 for r in valid)
    aligned_up = sum(_number(r.get('RS 1 tháng (điểm %)')) > 0 and
                     _number(r.get('Độ rộng tăng giá (%)')) >= 55 for r in valid)
    aligned_down = sum(_number(r.get('RS 1 tháng (điểm %)')) < 0 and
                       _number(r.get('Độ rộng tăng giá (%)')) < 45 for r in valid)
    intro = (f'Trong {len(valid)} ngành đủ dữ liệu: {strong} RS dương, {weak} RS âm; '
             f'{aligned_up} ngành mạnh tương đối kèm độ rộng từ 55%, '
             f'{aligned_down} ngành yếu tương đối kèm độ rộng dưới 45%.')
    samples = []
    for r in valid[:4]:
        rs = _number(r.get('RS 1 tháng (điểm %)'))
        width = _number(r.get('Độ rộng tăng giá (%)'))
        vol = _number(r.get('GTGD/TB20 (lần)'))
        samples.append(f"{r['Ngành']}: RS {rs:+.2f} điểm %, độ rộng {width:.1f}%, GTGD/TB20 {vol:.2f}x")
    lag = ctx.get('market_lag_sessions')
    trailing = f' {missing} ngành thiếu xác nhận nên không đưa vào kết luận.' if missing else ''
    if lag is not None and lag > 0:
        trailing += f' Giá EOD đã cách {lag} phiên dự kiến T2–T6; chưa xác minh lịch nghỉ lễ.'
    return (intro + ' ' + '; '.join(samples) + '.' + trailing +
            ' GTGD là mức giao dịch tương đối, KHÔNG phải dòng tiền mua ròng; '
            'chưa thể kết luận CPI gây ra biến động giá, doanh thu hoặc biên lợi nhuận.')


def latest_factor(prices, factor):
    """Select only numeric, correctly based (MoM / YTD YoY) national reports."""
    if factor not in dict(PRICE_FACTORS):
        raise ValueError('COST_UNKNOWN_FACTOR')
    expected = 'ytd_yoy' if factor == 'inputs' else 'mom'
    items = [p for p in prices if p.get('category') == factor and p.get('basis') == expected and
             p.get('rate') is not None and _as_date(p.get('date')) is not None]
    return max(items, key=lambda x: _as_date(x['date']), default=None)


def bridge_rows(prices, sector_metrics, info, factor, *, today, hour_vn=None):
    """Join at sector level with explicit mismatched dates, no inferred causality.

    sector_metrics uses existing sector_dashboard's exact field names. Each row
    retains a scenario and explicit real-world checks, not a recommendation.
    """
    observation = latest_factor(prices, factor)
    if not observation:
        return [], {'reason': 'Thiếu số liệu nhóm giá đã xác minh', 'price': None}
    price_date = _as_date(observation['date'])
    if price_date > today:
        return [], {'reason': 'Kỳ giá trong tương lai', 'price': None}
    market_date = _as_date(info.get('latest_date')) if isinstance(info, dict) else None
    lag_sessions = expected_market_sessions_since(market_date, today, hour_vn=hour_vn)
    market_ok = lag_sessions is not None and lag_sessions <= MAX_MISSED_EXPECTED_SESSIONS
    price_ok = 0 <= (today - price_date).days <= MAX_PRICE_AGE_DAYS
    sessions_ok = _number(info.get('sessions')) is not None and _number(info['sessions']) >= MIN_SESSIONS if isinstance(info, dict) else False
    # 'has_index' only means a VN-Index ticker was present somewhere in raw EOD.
    # The canonical 1-month benchmark may still have fallen back to a proxy.
    benchmark = info.get('benchmark', {}) if isinstance(info, dict) else {}
    bench_1m = benchmark.get('1 tháng') if isinstance(benchmark, dict) else None
    benchmark_source = (bench_1m[1] if isinstance(bench_1m, (tuple, list)) and
                        len(bench_1m) >= 2 else '')
    has_index = str(benchmark_source).startswith('VN-Index (')
    has_proxy = str(benchmark_source).startswith('trung vị rổ cổ phiếu')
    benchmark_verified = has_index or has_proxy
    records = sector_metrics.to_dict('records') if hasattr(sector_metrics, 'to_dict') else list(sector_metrics or [])
    index = {str(row.get('Nhóm ngành')): row for row in records if isinstance(row, dict)}
    output = []
    for _, sector, pathway, checks in [x for x in EXPOSURES if x[0] == factor]:
        row = index.get(sector, {})
        count = _number(row.get('Số mã có dữ liệu'))
        rs = _number(row.get('RS 1 tháng (điểm %) '))
        ret = _number(row.get('Hiệu suất 1 tháng (%)'))
        breadth = _number(row.get('Độ rộng tăng giá (%)'))
        turnover = _number(row.get('GTGD so TB20 (%)'))
        adequate = bool(market_ok and price_ok and sessions_ok and benchmark_verified
                        and count is not None and count >= MIN_SECTOR_MEMBERS
                        and rs is not None and ret is not None and breadth is not None and turnover is not None)
        if adequate:
            strength = ('Giá mạnh tương đối' if rs > 0 and breadth >= 55 else
                        'Giá yếu tương đối' if rs < 0 and breadth < 45 else 'Chưa đồng thuận')
            activity = ('GTGD cao hơn TB20' if turnover >= 120 else
                        'GTGD thấp hơn TB20' if turnover < 80 else 'GTGD gần TB20')
            status = 'Đủ đối chiếu thị trường · chưa chứng minh tác động'
        else:
            strength, activity = 'Chưa kết luận', 'Chưa kết luận'
            reasons = []
            if not price_ok: reasons.append('kỳ giá cũ')
            if not market_ok: reasons.append('giá cổ phiếu cũ/thiếu')
            if not sessions_ok: reasons.append('thiếu phiên')
            if not benchmark_verified: reasons.append('thiếu nguồn tham chiếu RS')
            if count is None or count < MIN_SECTOR_MEMBERS: reasons.append('ít mã ngành')
            if any(x is None for x in (rs, ret, breadth, turnover)): reasons.append('thiếu thước đo')
            status = 'Thiếu xác nhận: ' + ', '.join(reasons)
        output.append({
            'Ngành': sector, 'Kênh chi phí / doanh thu cần kiểm tra': pathway,
            'Hiệu suất 1 tháng (%)': round(ret, 2) if adequate else None,
            'RS 1 tháng (điểm %)': round(rs, 2) if adequate else None,
            'Độ rộng tăng giá (%)': round(breadth, 1) if adequate else None,
            'GTGD/TB20 (lần)': round(turnover / 100, 2) if adequate else None,
            'Quan sát sức mạnh giá': strength, 'Quan sát giao dịch': activity,
            'Trạng thái bằng chứng': status, 'Cần xác nhận tại doanh nghiệp': checks,
        })
    return output, {
        'price': observation, 'price_date': price_date, 'market_date': market_date,
        'price_ok': price_ok, 'market_ok': market_ok, 'has_index': has_index,
        'market_lag_sessions': lag_sessions,
        'market_calendar_note': 'Số phiên dự kiến T2–T6; chưa loại ngày nghỉ lễ/sự kiện đóng cửa đặc biệt',
        'rs_label': ('RS so VN-Index' if has_index else
                     'RS so proxy trung vị cổ phiếu' if has_proxy else
                     'RS chưa xác định nguồn tham chiếu'),
        'reason': None,
    }


def render_sector_cost_bridge(raw) -> None:
    """Streamlit UI; only compute expensive sector metrics on the chosen tab."""
    import streamlit as st
    import pandas as pd
    from macro_price_pressures import read_prices

    st.markdown('#### Chi phí đầu vào → sức mạnh giá & giao dịch ngành')
    st.caption('Liên hệ có điều kiện, KHÔNG phải ngành hưởng lợi/bị hại đã xác nhận. '
               'CPI đo giá hàng hóa; GTGD/TB20 là mức độ giao dịch, KHÔNG phải tiền mua ròng.')
    today = datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).date()
    factor = st.selectbox('Yếu tố giá muốn đối chiếu', [x[0] for x in PRICE_FACTORS],
                          format_func=lambda key: dict(PRICE_FACTORS)[key], key='mvn_cost_sector_factor_v1')
    try:
        prices = read_prices(today=today)
    except ValueError as exc:
        st.warning(f'Chưa có kho số liệu giá đã xác minh ({exc}). Không suy đoán tác động.')
        return
    observation = latest_factor(prices, factor)
    if observation is None:
        st.warning('Chưa có số liệu quốc gia đúng phương pháp đo cho yếu tố này.')
        return
    basis = 'bình quân lũy kế YoY' if factor == 'inputs' else 'so tháng trước (MoM)'
    st.caption(f"Nguồn áp lực giá: **{observation['period']} · {observation['rate']:+.2f}% {basis}** "
               f"(kỳ đến {observation['date']:%d/%m/%Y}). "
               f"[Báo cáo Cục Thống kê]({observation['source_url']})")
    if raw is None or getattr(raw, 'empty', True):
        st.info('Chưa có dữ liệu giá cổ phiếu nguồn đang chọn để đối chiếu RS/GTGD. '
                'Mở mục Ngành → Tổng quan ngành sau khi cập nhật EOD.')
        return

    # Reuse one canonical calculation. Cache is keyed by the actual price table.
    @st.cache_data(ttl=300, max_entries=2, show_spinner=False)
    def _compute(data):
        from sector_dashboard import calculate_sector_metrics
        return calculate_sector_metrics(data)
    try:
        metrics, info = _compute(raw)
        hour_vn = datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).hour
        rows, ctx = bridge_rows(prices, metrics, info, factor, today=today, hour_vn=hour_vn)
    except (KeyError, ValueError, TypeError, IndexError) as exc:
        st.warning(f'Không thể đối chiếu dữ liệu ngành một cách tin cậy ({type(exc).__name__}).')
        return
    if ctx.get('reason'):
        st.warning(ctx['reason'])
        return
    if ctx['market_date']:
        st.caption(f"Nguồn giá thị trường: **{ctx['market_date']:%d/%m/%Y}** · {ctx['rs_label']}. "
                   'Hiệu suất ngành là bình quân đều các mã có dữ liệu, KHÔNG phải chỉ số vốn hóa.')
    else:
        st.warning('Chưa xác định được ngày giá cổ phiếu; không tính xác nhận ngành.')
    if not ctx['price_ok']:
        st.warning('Số liệu giá hàng hóa đã quá 45 ngày. Không ghép với EOD hiện tại để kết luận tác động.')
    if not ctx['market_ok']:
        st.warning('Giá EOD thiếu hoặc chậm quá 2 phiên dự kiến T2–T6; không gắn nhãn sức mạnh ngành hiện tại.')
    elif ctx.get('market_lag_sessions', 0) > 0:
        st.info(f"EOD cách {ctx['market_lag_sessions']} phiên dự kiến T2–T6. "
                'Ngày nghỉ lễ/đóng cửa đặc biệt chưa được loại trừ; cần xác minh phiên mới nhất.')
    st.caption('Độ mới EOD xét theo số ngày phiên dự kiến T2–T6 sau kỳ EOD (tối đa 2); '
               'không thay thế lịch phiên chính thức, không mặc định ngày lễ là phiên giao dịch.')

    # Six-column overview; every missing value is shown as an em dash, not None/0.
    st.dataframe(pd.DataFrame(compact_rows(rows)), hide_index=True, use_container_width=True)
    st.markdown('##### Nhận định sức mạnh ngành từ dữ liệu hiện có')
    st.info(sector_evidence_summary(rows, ctx))

    # Keep long cost hypotheses outside the six-column overview.
    names = [r['Ngành'] for r in rows]
    if names:
        selected = st.selectbox('Chọn ngành để xem chi tiết bằng chứng', names,
                                key=f'mvn_cost_sector_detail_v2_{factor}')
        detail = next(r for r in rows if r['Ngành'] == selected)
        with st.expander(f'Chi tiết ngành: {selected}', expanded=True):
            st.write('**Kênh chi phí/doanh thu cần kiểm tra:** '
                     + detail['Kênh chi phí / doanh thu cần kiểm tra'])
            st.write('**Điều kiện cần xác nhận tại doanh nghiệp:** '
                     + detail['Cần xác nhận tại doanh nghiệp'])
            st.write('**Trạng thái bằng chứng:** ' + detail['Trạng thái bằng chứng'])
            st.write('**Quan sát giao dịch:** ' + detail['Quan sát giao dịch'])
            st.caption('Không có kết luận lợi nhuận, dòng tiền mua ròng hoặc khuyến nghị giao dịch.')
    st.caption('Độ rộng = tỷ lệ mã tăng ở phiên gần nhất; GTGD/TB20 dùng giá đóng cửa × khối lượng xấp xỉ. '
               'Cần xác nhận thêm doanh thu, chi phí mua vào, biên lợi nhuận, báo cáo doanh nghiệp và '
               'dòng tiền thực tế trước khi nói “ngành hưởng lợi”. Không phải khuyến nghị giao dịch.')
