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
MAX_MARKET_AGE_DAYS = 7
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


def latest_factor(prices, factor):
    """Select only numeric, correctly based (MoM / YTD YoY) national reports."""
    if factor not in dict(PRICE_FACTORS):
        raise ValueError('COST_UNKNOWN_FACTOR')
    expected = 'ytd_yoy' if factor == 'inputs' else 'mom'
    items = [p for p in prices if p.get('category') == factor and p.get('basis') == expected and
             p.get('rate') is not None and _as_date(p.get('date')) is not None]
    return max(items, key=lambda x: _as_date(x['date']), default=None)


def bridge_rows(prices, sector_metrics, info, factor, *, today):
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
    market_ok = market_date is not None and 0 <= (today - market_date).days <= MAX_MARKET_AGE_DAYS
    price_ok = 0 <= (today - price_date).days <= MAX_PRICE_AGE_DAYS
    sessions_ok = _number(info.get('sessions')) is not None and _number(info['sessions']) >= MIN_SESSIONS if isinstance(info, dict) else False
    has_index = bool(info.get('has_index')) if isinstance(info, dict) else False
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
        adequate = bool(market_ok and price_ok and sessions_ok and count is not None and count >= MIN_SECTOR_MEMBERS
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
        'rs_label': 'RS so VN-Index' if has_index else 'RS so proxy trung vị cổ phiếu',
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
        rows, ctx = bridge_rows(prices, metrics, info, factor, today=today)
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
        st.warning('Dữ liệu giá cổ phiếu thiếu hoặc quá 7 ngày. Không gắn nhãn sức mạnh/dòng tiền hiện tại.')
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True,
                 column_config={
                     'Hiệu suất 1 tháng (%)': st.column_config.NumberColumn(format='%+.2f'),
                     'RS 1 tháng (điểm %)': st.column_config.NumberColumn(format='%+.2f'),
                     'Độ rộng tăng giá (%)': st.column_config.NumberColumn(format='%.1f'),
                     'GTGD/TB20 (lần)': st.column_config.NumberColumn(format='%.2f'),
                 })
    st.caption('Độ rộng = tỷ lệ mã tăng ở phiên gần nhất; GTGD/TB20 dùng giá đóng cửa × khối lượng xấp xỉ. '
               'Cần xác nhận thêm doanh thu, chi phí mua vào, biên lợi nhuận, báo cáo doanh nghiệp và '
               'dòng tiền thực tế trước khi nói “ngành hưởng lợi”. Không phải khuyến nghị giao dịch.')
