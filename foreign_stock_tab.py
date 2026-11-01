"""Cổ phiếu > Khối ngoại: verified per-ticker buy/sell trading history.

Cloud only reads the local file mirrored from private R2. Never calls VNStock or
accesses secrets. Existing ranking-only snapshots are displayed distinctly if
per-ticker data has not been collected yet.
"""
from __future__ import annotations
from pathlib import Path
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from stock_proprietary_tab import _eod_for_code, _merge_price

DATA=Path('data/foreign_stock_flow.csv')
RANKS=Path('data/foreign_net_flow.csv')


def read_verified(path=DATA):
    if not path.is_file():return pd.DataFrame()
    from proprietary_flow_collector import validate
    frame=pd.read_csv(path,encoding='utf-8-sig',dtype={'trading_date':str,'symbol':str},low_memory=False)
    frame=validate(frame)
    if not frame.data_source.astype(str).str.startswith('VNSTOCK5_VCI_FOREIGN').all():
        raise ValueError('Wrong foreign-flow source')
    frame['date']=pd.to_datetime(frame.trading_date,format='%Y-%m-%d')
    return frame.sort_values(['symbol','date']).reset_index(drop=True)


def _table(frame):
    cols=['date','price','pct','buy_vol','buy_val','sell_vol','sell_val','net_vol','net_val']
    table=frame.sort_values('date',ascending=False)[cols].copy()
    for key in ['buy_val','sell_val','net_val']:
        table[key]/=1e9
    table=table.rename(columns={
        'date':'Ngày','price':'Giá EOD (nghìn)','pct':'Giá ±%',
        'buy_vol':'KL mua (cp)','buy_val':'GT mua (tỷ)',
        'sell_vol':'KL bán (cp)','sell_val':'GT bán (tỷ)',
        'net_vol':'KL ròng (cp)','net_val':'GT ròng (tỷ)'})
    table['Ngày']=table['Ngày'].dt.strftime('%d/%m/%Y')
    return table


def _bar_chart(frame):
    d=frame.sort_values('date')
    net=d.net_val/1e9
    fig=go.Figure(go.Bar(x=d.date,y=net,name='Khối ngoại ròng (tỷ)',
        marker_color=['#26B788' if x>=0 else '#E15B6A' for x in net]))
    fig.add_hline(y=0,line_color='rgba(180,190,190,.4)',line_width=1)
    fig.update_layout(template='plotly_dark',height=330,paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',margin=dict(l=5,r=5,t=15,b=5),
        xaxis_title=None,yaxis_title='Tỷ đồng',showlegend=False,hovermode='x unified')
    return fig


def _compare_chart(frame):
    d=frame.sort_values('date')
    prices=d.loc[d.price.notna()]
    if len(prices)<2:return None
    net=d.net_val/1e9
    fig=go.Figure()
    fig.add_trace(go.Bar(x=d.date,y=net,name='Khối ngoại ròng (tỷ)',
        marker_color=['#26B788' if v>=0 else '#E15B6A' for v in net]))
    fig.add_trace(go.Scatter(x=prices.date,y=prices.price,mode='lines+markers',
        name='Giá EOD (nghìn)',yaxis='y2',line=dict(color='#F5BF63')))
    fig.update_layout(template='plotly_dark',height=315,paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',margin=dict(l=5,r=5,t=15,b=6),
        yaxis=dict(title='Tỷ đồng'),yaxis2=dict(title='Giá (nghìn)',overlaying='y',side='right'),
        legend=dict(orientation='h',y=1.12),hovermode='x unified')
    return fig


def _rank_snapshot(code):
    if not RANKS.is_file():return None
    try:
        from foreign_net_collector import validate_table
        d=pd.read_csv(RANKS,encoding='utf-8-sig',dtype={'symbol':str,'trading_date':str})
        d=validate_table(d)
        d=d.loc[d.symbol.astype(str).eq(code)].sort_values('trading_date')
        if d.empty:return None
        return d.iloc[-1]
    except (OSError,ValueError,KeyError,ImportError):return None


def render(df,codes,fund_map=None):
    st.markdown('### 🌐 Giao dịch khối ngoại theo cổ phiếu')
    st.caption('Nguồn VNStock / VCI · Thu thập trên Windows → R2. Theo ngày nguồn công bố; không phải realtime.')
    if not codes:
        st.info('Chưa có danh sách mã EOD.')
        return
    selected=st.session_state.get('selected_code')
    idx=codes.index(selected) if selected in codes else 0
    code=st.selectbox('Mã cổ phiếu',codes,index=idx,key='min_foreign_stock_selected_v1')
    st.session_state['selected_code']=code
    name=(fund_map or {}).get(code,{}).get('Tên công ty')
    st.markdown(f'**{code}**'+(f' · {name}' if isinstance(name,str) and name.strip() else ''))
    if not DATA.is_file():
        st.warning('Chưa có dữ liệu khối ngoại từng mã trên Streamlit. File cần đồng bộ: data/foreign_stock_flow.csv.')
        ranking=_rank_snapshot(code)
        if ranking is not None:
            v=float(ranking['net_value_vnd'])/1e9
            st.metric('Mua/bán ròng gần nhất trong bảng TOP (tỷ)',f'{v:+,.2f}')
            st.caption(f'Bảng TOP, ngày {ranking["trading_date"]} · RANKING_TOP_ONLY; '
                       'không có tổng mua/bán và không đủ để dựng lịch sử 20 phiên.')
        else:
            st.info('Mã chưa xuất hiện trong dữ liệu TOP hiện có; không có nghĩa giao dịch ròng bằng 0.')
        return
    try:
        flows=read_verified()
    except (ValueError,KeyError,OSError,ImportError):
        st.error('File dữ liệu khối ngoại chưa hợp lệ. Không hiển thị số liệu suy đoán.')
        return
    own=flows.loc[flows.symbol.eq(code)].sort_values('date').copy()
    if own.empty:
        st.info(f'Chưa thu thập lịch sử khối ngoại cho {code}. Các mã được cập nhật luân phiên theo lịch Windows.')
        ranking=_rank_snapshot(code)
        if ranking is not None:
            st.metric('Khối ngoại ròng trong bảng TOP (tỷ)',f'{float(ranking["net_value_vnd"])/1e9:+,.2f}')
            st.caption('Giá trị TOP chỉ là một ngày có dữ liệu, không phải tổng dòng tiền 20 phiên.')
        return
    choices=[v for v in (5,10,20,60) if v<=len(own)] or [len(own)]
    default=20 if 20 in choices else choices[-1]
    a,b=st.columns([1,3])
    with a:
        period=st.selectbox('Số phiên hiển thị',choices,index=choices.index(default),
            key=f'min_foreign_stock_period_{code}',format_func=lambda v:f'{v} phiên')
    with b:
        st.caption(f'Dữ liệu mới nhất: {own.iloc[-1].date:%d/%m/%Y} · '
            f'{len(own)} ngày có bản ghi · xem {period} ngày gần nhất có dữ liệu')
    q=own.tail(period)
    price=_eod_for_code(df,code)
    merged=_merge_price(q,price)
    a,b,c,d=st.columns(4)
    a.metric(f'Giá trị ròng {period} phiên (tỷ)',f'{q.net_val.sum()/1e9:+,.2f}')
    b.metric('Phiên mua ròng',int(q.net_val.gt(0).sum()))
    c.metric('Phiên bán ròng',int(q.net_val.lt(0).sum()))
    d.metric('Ròng gần nhất (tỷ)',f'{q.net_val.iloc[-1]/1e9:+,.2f}')
    left,right=st.columns([1.65,1],gap='medium')
    with left:
        st.markdown('**Bảng giao dịch khối ngoại theo ngày**')
        st.dataframe(_table(merged),hide_index=True,use_container_width=True,height=420,
            column_config={
                'Giá EOD (nghìn)':st.column_config.NumberColumn(format='%.2f'),
                'Giá ±%':st.column_config.NumberColumn(format='%+.2f'),
                'KL mua (cp)':st.column_config.NumberColumn(format='%.0f'),
                'KL bán (cp)':st.column_config.NumberColumn(format='%.0f'),
                'KL ròng (cp)':st.column_config.NumberColumn(format='%.0f'),
                'GT mua (tỷ)':st.column_config.NumberColumn(format='%.2f'),
                'GT bán (tỷ)':st.column_config.NumberColumn(format='%.2f'),
                'GT ròng (tỷ)':st.column_config.NumberColumn(format='%+.2f')})
    with right:
        st.markdown(f'**Khối ngoại mua/bán ròng {period} phiên**')
        st.plotly_chart(_bar_chart(merged),use_container_width=True,
                        key=f'min_foreign_stock_bar_{code}_{period}')
    cmp=_compare_chart(merged)
    if cmp is not None:
        st.markdown('**So sánh giá EOD và khối ngoại ròng**')
        st.plotly_chart(cmp,use_container_width=True,
                        key=f'min_foreign_stock_compare_{code}_{period}')
    else:
        st.caption('Chưa có đủ giá EOD trùng ngày để so sánh.')
    if q[['buy_val','sell_val']].isna().any().any():
        st.caption('Một số ngày thiếu giá trị mua/bán gộp; chỉ hiển thị dữ liệu thực có, không suy ra từ giá trị ròng.')
    st.caption('Đơn vị: tỷ đồng (giá trị giao dịch) và cổ phiếu (khối lượng). '
               'Số phiên là số ngày thực sự có dữ liệu, có thể không liên tiếp.')
