"""Private read-only proprietary-flow panel for Stock > General information.

Reads only validated local R2-mirrored CSV; never calls VNStock or credentials.
"""
from __future__ import annotations

from pathlib import Path
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

PATH=Path('data/proprietary_flow.csv')

@st.cache_data(show_spinner=False,max_entries=4)
def load_data(path,mtime):
    data=pd.read_csv(path,encoding='utf-8-sig',dtype={'symbol':str,'trading_date':str},low_memory=False)
    from proprietary_flow_collector import validate
    data=validate(data)
    data['date']=pd.to_datetime(data['trading_date'],format='%Y-%m-%d')
    return data

def for_code(code):
    if not PATH.is_file():return pd.DataFrame()
    try:
        data=load_data(str(PATH),PATH.stat().st_mtime_ns)
        data=data[data['symbol'].eq(str(code).upper().strip())].copy()
        return data.sort_values('date').drop_duplicates('date',keep='last')
    except (OSError,ValueError,KeyError,TypeError,UnicodeDecodeError):
        return pd.DataFrame()

def _money(n):
    if pd.isna(n):return '—'
    return f'{n/1e9:+,.2f}'

def render_compact(code):
    """Compact 20-session preview for existing stock-profile cashflow row."""
    d=for_code(code)
    if d.empty:
        st.caption('Chưa có dữ liệu tự doanh đã kiểm chứng cho mã này; không suy ra từ OHLCV.')
        return
    last=d.iloc[-1]
    st.metric('Ròng phiên gần nhất (tỷ)',_money(last['net_val']))
    st.caption(f'{last["date"]:%d/%m/%Y} · VNStock/VCI · {len(d)} phiên đã lưu')
    window=d.tail(20)
    if len(window)>=20:
        st.metric('Lũy kế 20 phiên (tỷ)',_money(window['net_val'].sum()))
    else:
        st.caption(f'Mới lưu {len(window)}/20 phiên; chưa đủ để kết luận lũy kế 20 phiên.')

def _bar(d):
    y=d['net_val']/1e9
    fig=go.Figure()
    fig.add_trace(go.Bar(x=d['date'],y=y,marker_color=['#25b98a' if n>=0 else '#e15a68' for n in y],name='Ròng (tỷ VNĐ)'))
    fig.add_hline(y=0,line_color='rgba(175,182,191,.55)',line_width=1)
    fig.update_layout(template='plotly_dark',height=275,
                      margin=dict(l=5,r=5,t=8,b=10),paper_bgcolor='rgba(0,0,0,0)',
                      plot_bgcolor='rgba(0,0,0,0)',xaxis_title=None,
                      yaxis_title='Tỷ VNĐ',showlegend=False)
    return fig

def render_detail(code,eod=None):
    d=for_code(code)
    if d.empty:
        st.info('Chưa có dữ liệu tự doanh cho mã này trên R2. Windows sẽ thu thập luân phiên sau phiên.')
        return
    options=[v for v in (5,10,20,60) if v<=len(d)]
    if not options:options=[len(d)]
    a,b=st.columns([1,3])
    with a:
        length=st.selectbox('Số phiên',options,index=len(options)-1,key=f'min_prop_len_{code}',format_func=lambda v:f'{v} phiên')
    q=d.tail(length).copy()
    with b:
        st.caption(f'Nguồn VNStock 5 / VCI · Ngày mới nhất: {q.iloc[-1]["date"]:%d/%m/%Y} · {len(q)} phiên thực có dữ liệu. Không phải realtime.')
    c1,c2,c3=st.columns(3)
    c1.metric(f'Mua/bán ròng {length} phiên (tỷ)',_money(q['net_val'].sum()))
    c2.metric('Số phiên mua ròng',int(q['net_val'].gt(0).sum()))
    c3.metric('Số phiên bán ròng',int(q['net_val'].lt(0).sum()))
    left,right=st.columns([1,1],gap='medium')
    with left:
        st.markdown('**Lịch sử tự doanh**')
        shown=q.iloc[::-1][['date','buy_vol','buy_val','sell_vol','sell_val','net_vol','net_val']].copy()
        for name in ('buy_val','sell_val','net_val'):shown[name]=shown[name]/1e9
        shown=shown.rename(columns={'date':'Ngày','buy_vol':'KL mua (cp)','buy_val':'GT mua (tỷ)',
                            'sell_vol':'KL bán (cp)','sell_val':'GT bán (tỷ)',
                            'net_vol':'KL ròng (cp)','net_val':'GT ròng (tỷ)'})
        shown['Ngày']=shown['Ngày'].dt.strftime('%d/%m/%Y')
        st.dataframe(shown,use_container_width=True,hide_index=True,height=330)
    with right:
        st.markdown('**Giá trị mua/bán ròng**')
        st.plotly_chart(_bar(q),use_container_width=True,key=f'min_prop_chart_{code}_{length}')
    if eod is not None and not eod.empty and {'Ngày','Giá đóng cửa'}.issubset(eod):
        chart=eod[['Ngày','Giá đóng cửa']].copy()
        chart['date']=pd.to_datetime(chart['Ngày'],errors='coerce',dayfirst=True,format='mixed')
        chart['price']=pd.to_numeric(chart['Giá đóng cửa'],errors='coerce')
        chart=chart.dropna(subset=['date','price']).drop_duplicates('date',keep='last')
        chart=chart[chart['date'].ge(q['date'].min()) & chart['date'].le(q['date'].max())].sort_values('date')
        if len(chart)>1:
            fig=go.Figure()
            fig.add_trace(go.Bar(x=q['date'],y=q['net_val']/1e9,name='Ròng tự doanh (tỷ)',
                                 marker_color=['#25b98a' if x>=0 else '#e15a68' for x in q['net_val']]))
            fig.add_trace(go.Scatter(x=chart['date'],y=chart['price'],mode='lines+markers',
                                     yaxis='y2',name='Giá EOD (nghìn)'))
            fig.update_layout(template='plotly_dark',height=300,paper_bgcolor='rgba(0,0,0,0)',
                              plot_bgcolor='rgba(0,0,0,0)',margin=dict(l=10,r=10,t=10,b=15),
                              yaxis=dict(title='Ròng (tỷ)'),yaxis2=dict(title='Giá EOD (nghìn)',overlaying='y',side='right'))
            st.markdown('**So sánh dòng tiền tự doanh với giá EOD**')
            st.plotly_chart(fig,use_container_width=True,key=f'min_prop_vs_price_{code}_{length}')
    st.caption('Thiếu trường mua/bán được giữ là dấu —. Số âm biểu thị bán ròng. Dữ liệu theo từng mã từ nguồn VCI, không suy ra hoạt động tự doanh toàn thị trường.')
