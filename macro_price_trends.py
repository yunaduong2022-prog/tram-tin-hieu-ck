"""Price-pressure history: only verified nationwide CPI subgroup MoM snapshots.

Input rows are validated by macro_price_pressures.read_prices(). Missing months
are kept as None; never interpolate and never sum nested CPI contributions.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

MONITORED = (
    ('food', 'Thực phẩm'),
    ('fuel', 'Giá xăng'),
    ('power', 'Điện sinh hoạt'),
    ('housing', 'Nhà ở, điện nước, chất đốt & VLXD'),
)
RELATED = (
    {'Yếu tố': 'Giá thực phẩm', 'Kênh truyền dẫn có điều kiện': 'Chi phí đầu vào ngành thực phẩm, tiêu dùng và sức mua', 'Cần kiểm tra': 'Giá bán, biên lợi nhuận, sức mua thực tế'},
    {'Yếu tố': 'Giá xăng dầu', 'Kênh truyền dẫn có điều kiện': 'Chi phí vận tải, hóa chất và kỳ vọng lạm phát', 'Cần kiểm tra': 'Giá dầu thực tế, vận tải, tỷ giá và hợp đồng đầu vào'},
    {'Yếu tố': 'Điện sinh hoạt', 'Kênh truyền dẫn có điều kiện': 'CPI nhóm nhà ở; không đồng nhất với biểu giá điện sản xuất', 'Cần kiểm tra': 'Biểu giá áp dụng và chi phí điện của từng doanh nghiệp'},
    {'Yếu tố': 'Nhà ở & VLXD', 'Kênh truyền dẫn có điều kiện': 'Chi phí xây dựng, thuê nhà và nhu cầu vật liệu', 'Cần kiểm tra': 'Đơn hàng, giá thép, lợi nhuận và khối lượng xây dựng'},
    {'Yếu tố': 'Nguyên vật liệu sản xuất', 'Kênh truyền dẫn có điều kiện': 'Giá vốn ngành công nghiệp (khác CPI tiêu dùng)', 'Cần kiểm tra': 'Giá nguyên liệu mua thực, tồn kho và giá bán đầu ra'},
)


def _add_month(month: date) -> date:
    return date(month.year + (month.month == 12), month.month % 12 + 1, 1)


def monthly_grid(rows: list[dict], category: str) -> list[dict[str, Any]]:
    """Full monthly axis with None for months absent from official reports."""
    if category not in {x[0] for x in MONITORED}:
        raise ValueError('PRICE_TREND_UNKNOWN_CATEGORY')
    observations = {date(r['date'].year, r['date'].month, 1): r
                    for r in rows if r['category'] == category and r['basis'] == 'mom'}
    if not observations:
        return []
    if len(observations) != len([r for r in rows if r['category'] == category and r['basis'] == 'mom']):
        raise ValueError('PRICE_TREND_DUPLICATE_MONTH')
    start, end = min(observations), max(observations)
    result = []
    month = start
    while month <= end:
        r = observations.get(month)
        result.append({'month': month, 'rate': r['rate'] if r else None,
                       'source_url': r['source_url'] if r else None,
                       'contribution': r['contribution'] if r else None})
        month = _add_month(month)
    return result


def consecutive_change(grid: list[dict[str, Any]]) -> Decimal | None:
    """Only compare two adjacent published months, not May vs October."""
    if len(grid) < 2 or grid[-1]['rate'] is None or grid[-2]['rate'] is None:
        return None
    return grid[-1]['rate'] - grid[-2]['rate']


def contribution_rows(rows: list[dict]) -> list[dict]:
    """Only values attributed to the exact named national category."""
    result = []
    for r in sorted(rows, key=lambda x: (x['date'], x['category'])):
        if r['basis'] != 'mom' or r['contribution_scope'] != 'same_group' or r['contribution'] is None:
            continue
        result.append({'Nhóm': next((label for category, label in MONITORED if category == r['category']), r['category']),
                       'Kỳ': r['period'], 'Đóng góp (điểm %)': float(r['contribution']),
                       'Nguồn chính thức': r['source_url']})
    return result


def render_price_trends(rows: list[dict]) -> None:
    import streamlit as st
    import pandas as pd
    try:
        import plotly.graph_objects as go
    except ImportError:
        st.info('Không có Plotly để hiển thị đồ thị nhóm giá.')
        return

    st.markdown('#### Lịch sử biến động giá theo nhóm')
    st.caption('Chỉ so sánh mức biến động MoM cùng nhóm, cùng phạm vi toàn quốc. '
               'Tháng thiếu số liệu là khoảng trống; không nội suy và không nối chuỗi qua kỳ thiếu.')
    tabs = st.tabs([label for _, label in MONITORED])
    for tab, (category, label) in zip(tabs, MONITORED):
        with tab:
            grid = monthly_grid(rows, category)
            if len(grid) < 2:
                st.info('Chưa có ít nhất hai kỳ MoM cùng phương pháp đo để dựng lịch sử.')
                continue
            missing = [g['month'].strftime('%m/%Y') for g in grid if g['rate'] is None]
            fig = go.Figure(go.Bar(
                x=[g['month'].strftime('%m/%Y') for g in grid],
                y=[float(g['rate']) if g['rate'] is not None else None for g in grid],
                text=[f"{g['rate']:+.2f}%" if g['rate'] is not None else '' for g in grid],
                textposition='outside',
                hovertemplate='%{x}: %{y:.2f}% MoM<extra></extra>',
            ))
            fig.update_layout(height=310, margin=dict(l=10, r=10, t=18, b=8),
                              paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                              xaxis=dict(title=None, categoryorder='array',
                                         categoryarray=[g['month'].strftime('%m/%Y') for g in grid]),
                              yaxis=dict(title='% MoM', zeroline=True), showlegend=False)
            st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
            if missing:
                st.caption('Không có số liệu xác minh: ' + ', '.join(missing) + '. Không nối thành xu hướng liên tục.')
            change = consecutive_change(grid)
            if change is None:
                st.info('Hai kỳ mới nhất chưa liên tiếp và đủ dữ liệu: chưa kết luận nhóm giá đang tăng tốc hay hạ nhiệt.')
            else:
                st.caption(f'Mức thay đổi MoM giữa hai tháng liền nhau: {change:+.2f} điểm phần trăm. '
                           'Đây là biến động tỷ lệ, không phải đóng góp CPI.')

    st.markdown('#### Đóng góp CPI đã công bố đúng phạm vi')
    contrib = contribution_rows(rows)
    if contrib:
        st.dataframe(pd.DataFrame(contrib), hide_index=True, use_container_width=True,
                     column_config={'Nguồn chính thức': st.column_config.LinkColumn('Báo cáo Cục Thống kê')})
    else:
        st.caption('Chưa có mức đóng góp CPI của đúng nhóm được công bố để so sánh.')
    st.caption('Không cộng đóng góp nhóm nhà ở với điện sinh hoạt; không gán đóng góp nhóm giao thông cho giá xăng.')
    st.markdown('#### Kênh ảnh hưởng đến doanh nghiệp và ngành')
    st.dataframe(pd.DataFrame(RELATED), hide_index=True, use_container_width=True)
    st.caption('Bảng kênh ảnh hưởng là khung phân tích có điều kiện, không phải chỉ báo dòng tiền, xếp hạng ngành hay khuyến nghị mua bán.')
