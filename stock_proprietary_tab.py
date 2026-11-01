"""Cổ phiếu > Tự doanh: read-only VCI proprietary trading by ticker.

All market data is already locally mirrored by R2 into data/proprietary_flow.csv.
No vendor API, network, credential or portfolio read happens in this page.
"""
from __future__ import annotations

from pathlib import Path
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from proprietary_dashboard import for_code

_DATA = Path('data/proprietary_flow.csv')
_EOD_COLS = ('Ngày', 'Giá đóng cửa')


def _eod_for_code(df, code):
    """Look up verified EOD closes; never infer missing dates or prices."""
    if df is None or df.empty or not {'Mã', *_EOD_COLS}.issubset(df.columns):
        return pd.DataFrame(columns=['date', 'price', 'pct'])
    d = df.loc[df['Mã'].astype(str).str.upper().eq(code), list(_EOD_COLS)].copy()
    if d.empty:
        return pd.DataFrame(columns=['date', 'price', 'pct'])
    d['date'] = pd.to_datetime(d['Ngày'], errors='coerce', format='mixed', dayfirst=True)
    d['price'] = pd.to_numeric(d['Giá đóng cửa'], errors='coerce')
    d = d.dropna(subset=['date', 'price'])
    d = d[d['price'].gt(0)].sort_values('date').drop_duplicates('date', keep='last')
    d['pct'] = d['price'].pct_change() * 100
    return d[['date', 'price', 'pct']]


def _merge_price(flows, prices):
    base = flows.copy()
    if 'date' not in base:
        base['date'] = pd.to_datetime(base['trading_date'], errors='coerce')
    if prices.empty:
        base['price'] = float('nan')
        base['pct'] = float('nan')
        return base
    return base.merge(prices, on='date', how='left', validate='one_to_one')


def _table(flows):
    """Data is VND and shares; show monetary values in billions of VND."""
    d = flows.sort_values('date', ascending=False)
    cols = ['date', 'price', 'pct', 'buy_vol', 'buy_val', 'sell_vol',
            'sell_val', 'net_vol', 'net_val']
    t = d[cols].copy()
    for c in ('buy_val', 'sell_val', 'net_val'):
        t[c] = t[c].div(1e9)
    t = t.rename(columns={
        'date': 'Ngày', 'price': 'Giá (nghìn)', 'pct': 'Giá ±%',
        'buy_vol': 'KL mua (cp)', 'buy_val': 'GT mua (tỷ)',
        'sell_vol': 'KL bán (cp)', 'sell_val': 'GT bán (tỷ)',
        'net_vol': 'KL ròng (cp)', 'net_val': 'GT ròng (tỷ)'})
    t['Ngày'] = t['Ngày'].dt.strftime('%d/%m/%Y')
    return t


def _bar_chart(flows):
    ordered = flows.sort_values('date')
    net = ordered['net_val'] / 1e9
    fig = go.Figure(go.Bar(
        x=ordered['date'], y=net,
        marker_color=['#26B788' if v >= 0 else '#E15B6A' for v in net],
        name='Tự doanh ròng (tỷ)'))
    fig.add_hline(y=0, line_color='rgba(180,190,190,.45)', line_width=1)
    fig.update_layout(template='plotly_dark', height=340,
                      paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                      margin=dict(l=5, r=5, t=12, b=8),
                      xaxis_title=None, yaxis_title='Tỷ đồng', showlegend=False,
                      hovermode='x unified')
    return fig


def _compare_chart(flows):
    d = flows.sort_values('date')
    has = d.loc[d['price'].notna()]
    if len(has) < 2:
        return None
    fig = go.Figure()
    net = d['net_val'] / 1e9
    fig.add_trace(go.Bar(x=d['date'], y=net, name='Tự doanh ròng (tỷ)',
                         marker_color=['#26B788' if n >= 0 else '#E15B6A' for n in net]))
    fig.add_trace(go.Scatter(x=has['date'], y=has['price'], mode='lines+markers',
                             name='Giá EOD (nghìn)', yaxis='y2', line=dict(color='#F5BF63')))
    fig.update_layout(template='plotly_dark', height=315,
                      paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                      margin=dict(l=5, r=5, t=12, b=8),
                      yaxis=dict(title='Tỷ đồng'),
                      yaxis2=dict(title='Giá (nghìn)', overlaying='y', side='right'),
                      legend=dict(orientation='h', y=1.12), hovermode='x unified')
    return fig


def _f_money(n):
    return f'{n/1e9:+,.2f}'


def render(df, codes, fund_map=None):
    """Dedicated tab alongside Cổ phiếu / Thông tin chung / Biểu đồ."""
    st.markdown('### Giao dịch tự doanh theo cổ phiếu')
    st.caption('Nguồn VNStock / VCI · Dữ liệu đã lưu sau phiên trên Windows và đồng bộ qua R2. '
               'Không phải dữ liệu giao dịch trong thời gian thực.')
    if not codes:
        st.info('Chưa có danh sách mã trong dữ liệu EOD.')
        return
    selected = st.session_state.get('selected_code')
    idx = codes.index(selected) if selected in codes else 0
    code = st.selectbox('Mã cổ phiếu', codes, index=idx,
                        key='min_proprietary_selected_code_v1')
    st.session_state['selected_code'] = code
    name = (fund_map or {}).get(code, {}).get('Tên công ty')
    st.markdown(f'**{code}**' + (f' · {name}' if isinstance(name, str) and name.strip() else ''))

    if not _DATA.is_file():
        st.warning('Chưa có file dữ liệu tự doanh trên Streamlit Cloud. '
                   'Windows đã thu thập, nhưng bản R2 chưa được nạp vào môi trường ứng dụng.')
        st.caption('Nguồn cần có: data/proprietary_flow.csv · Kiểm tra manifest R2 và sync_enabled. '
                   'Không cần gọi VNStock từ Cloud.')
        return
    flows = for_code(code)
    if flows.empty:
        st.info(f'Chưa có dữ liệu tự doanh hợp lệ cho {code} trong file đã đồng bộ. '
                'Các mã được thu thập luân phiên sau phiên; không mặc định số 0.')
        st.caption('Dữ liệu file R2 có mặt, nhưng chưa có mã được chọn hoặc dữ liệu không đạt kiểm định.')
        return

    count = len(flows)
    choices = [v for v in (5,10,20,60) if v <= count]
    if not choices:
        choices = [count]
    default = 20 if 20 in choices else choices[-1]
    c1, c2 = st.columns([1,3])
    with c1:
        period = st.selectbox('Số phiên hiển thị', choices, index=choices.index(default),
                              key=f'min_prop_tab_period_{code}',
                              format_func=lambda x: f'{x} phiên')
    with c2:
        st.caption(f'Dữ liệu mới nhất: {flows.iloc[-1]["date"]:%d/%m/%Y} · '
                   f'{count} ngày có bản ghi · Đang xem {period} ngày gần nhất có dữ liệu')

    q = flows.tail(period)
    price = _eod_for_code(df, code)
    combo = _merge_price(q, price)
    a, b, c, d = st.columns(4)
    a.metric(f'Giá trị ròng {len(q)} phiên (tỷ)', _f_money(q['net_val'].sum()))
    b.metric('Phiên mua ròng', int(q['net_val'].gt(0).sum()))
    c.metric('Phiên bán ròng', int(q['net_val'].lt(0).sum()))
    d.metric('Ròng phiên gần nhất (tỷ)', _f_money(q.iloc[-1]['net_val']))

    left, right = st.columns([1.65, 1], gap='medium')
    with left:
        st.markdown('**Bảng giao dịch tự doanh theo ngày**')
        st.dataframe(_table(combo), hide_index=True, use_container_width=True, height=430,
                     column_config={
                         'Giá (nghìn)': st.column_config.NumberColumn(format='%.2f'),
                         'Giá ±%': st.column_config.NumberColumn(format='%+.2f'),
                         'GT mua (tỷ)': st.column_config.NumberColumn(format='%.2f'),
                         'GT bán (tỷ)': st.column_config.NumberColumn(format='%.2f'),
                         'GT ròng (tỷ)': st.column_config.NumberColumn(format='%+.2f'),
                         'KL mua (cp)': st.column_config.NumberColumn(format='%.0f'),
                         'KL bán (cp)': st.column_config.NumberColumn(format='%.0f'),
                         'KL ròng (cp)': st.column_config.NumberColumn(format='%.0f'),
                     })
    with right:
        st.markdown(f'**Biểu đồ giá trị ròng {len(q)} phiên**')
        st.plotly_chart(_bar_chart(combo), use_container_width=True,
                        key=f'min_prop_tab_bar_{code}_{period}')

    comparison = _compare_chart(combo)
    if comparison is not None:
        st.markdown('**So sánh giá EOD và tự doanh ròng**')
        st.plotly_chart(comparison, use_container_width=True,
                        key=f'min_prop_tab_compare_{code}_{period}')
    else:
        st.caption('Chưa có đủ giá EOD khớp ngày để so sánh hai chuỗi.')

    st.caption('Giá trị tính bằng tỷ đồng; khối lượng là cổ phiếu. Chỉ hiển thị ngày đã có dữ liệu từ nguồn. '
               'Dữ liệu mua/bán thiếu sẽ để trống, không suy ra từ khối lượng giao dịch toàn thị trường.')
