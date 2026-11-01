"""Private-market foreign net flow dashboard. Does not call VNStock on Cloud."""
from __future__ import annotations
from pathlib import Path
import pandas as pd
import streamlit as st
import plotly.express as px

DATA_PATH=Path('data/foreign_net_flow.csv')

@st.cache_data(show_spinner=False, max_entries=3)
def _read_net(_mtime, path):
    data=pd.read_csv(path,dtype={'symbol':str,'trading_date':str})
    from foreign_net_collector import validate_table
    data=validate_table(data)
    data['trading_date']=pd.to_datetime(data['trading_date'],format='%Y-%m-%d')
    return data

def _membership():
    try:
        import watchlist as wl
        groups=wl.membership(wl.VN30_DU_PHONG)
        return {code: next((name for name in names if name!='VN30' and not name.startswith('Họ ')), 'Khác') for code,names in groups.items()}
    except (ImportError,AttributeError):
        return {}

def render():
    st.title('🌐 Dòng tiền khối ngoại')
    st.caption('Nguồn: VNStock Insights trên Windows → R2. **Chỉ phản ánh mua/bán RÒNG**, không phải tổng giá trị mua hoặc tổng giá trị bán.')
    if not DATA_PATH.is_file():
        st.warning('Chưa có dữ liệu khối ngoại đồng bộ. Giữ lịch thu thập Windows và đợi phiên hợp lệ; không suy diễn từ OHLCV.')
        return
    try:
        data=_read_net(DATA_PATH.stat().st_mtime_ns,str(DATA_PATH))
    except Exception:
        st.error('File khối ngoại không hợp lệ hoặc bị lỗi. Giữ dữ liệu an toàn, không hiển thị số liệu suy đoán.')
        return
    if data.empty:
        st.info('Chưa có dữ liệu khối ngoại.')
        return
    dates=sorted(data['trading_date'].dt.date.unique())
    a,b=st.columns([1,1])
    with a:
        day=st.selectbox('Ngày giao dịch',dates,index=len(dates)-1,format_func=lambda x:x.strftime('%d/%m/%Y'),key='foreign_net_date')
    selected=data[data['trading_date'].dt.date.eq(day)].copy()
    scopes=selected['source_scope'].dropna().unique().tolist()
    full=(len(scopes)==1 and scopes[0]=='FLOW_VERIFIED_FULL')
    with b:
        if full:
            st.success('Theo dõi danh sách mã nguồn trả về (3 sàn, tùy độ phủ)')
        else:
            st.warning('Chỉ các mã thuộc TOP mua/bán ròng — KHÔNG đại diện toàn thị trường')
    industry=_membership()
    selected['Nhóm ngành']=selected['symbol'].map(industry).fillna('Khác')
    st.caption('Đồng bộ lúc (UTC): '+str(selected['observed_at_utc'].iloc[0])+'. Phân ngành theo danh sách tham khảo nội bộ; tổng theo ngành chỉ là các mã có trong dữ liệu.')
    net=selected['net_value_vnd']/1e9
    buy=int((net>0).sum()); sell=int((net<0).sum())
    k1,k2,k3=st.columns(3)
    k1.metric('Giá trị ròng trong mẫu',f'{net.sum():+,.1f} tỷ đồng')
    k2.metric('Số mã trong mẫu',f'{len(selected):,}')
    k3.metric('Số mã mua ròng / bán ròng',f'{buy} / {sell}')
    st.caption('Không hiển thị tổng mua hoặc tổng bán vì nguồn Insights chỉ có giá trị ròng. Không cộng lũy kế dài hạn từ các ngày chưa lưu.')
    ranked=selected.assign(net_ty=net.values)
    l,r=st.columns(2)
    with l:
        st.markdown('**Top mua ròng (trong mẫu)**')
        data_buy=ranked[ranked.net_ty>0].nlargest(12,'net_ty').sort_values('net_ty')
        if data_buy.empty: st.info('Không có mã mua ròng trong dữ liệu')
        else: st.plotly_chart(px.bar(data_buy,y='symbol',x='net_ty',orientation='h',labels={'symbol':'Mã','net_ty':'Tỷ đồng'},color_discrete_sequence=['#229970']),use_container_width=True)
    with r:
        st.markdown('**Top bán ròng (trong mẫu)**')
        data_sell=ranked[ranked.net_ty<0].nsmallest(12,'net_ty').sort_values('net_ty',ascending=False)
        if data_sell.empty: st.info('Không có mã bán ròng trong dữ liệu')
        else: st.plotly_chart(px.bar(data_sell,y='symbol',x='net_ty',orientation='h',labels={'symbol':'Mã','net_ty':'Tỷ đồng'},color_discrete_sequence=['#dd5660']),use_container_width=True)
    st.subheader('Dòng tiền ròng theo ngành trong mẫu')
    g=ranked.groupby('Nhóm ngành',dropna=False)['net_ty'].sum().reset_index().sort_values('net_ty')
    st.plotly_chart(px.bar(g,y='Nhóm ngành',x='net_ty',orientation='h',labels={'net_ty':'Tỷ đồng'},color='net_ty',color_continuous_scale=['#d85260','#c1b05d','#229970']),use_container_width=True)
    st.subheader('Lịch sử đã thu thập')
    available=sorted(data.symbol.dropna().unique())
    defaults=ranked.reindex(ranked.net_ty.abs().sort_values(ascending=False).index)['symbol'].head(3).tolist()
    chosen=st.multiselect('Chọn mã',available,default=defaults,key='foreign_net_history_symbols')
    if chosen:
        series=data[data.symbol.isin(chosen)].copy()
        series['Giá trị ròng (tỷ)']=series['net_value_vnd']/1e9
        st.plotly_chart(px.line(series,x='trading_date',y='Giá trị ròng (tỷ)',color='symbol',markers=True),use_container_width=True)
        if data.trading_date.nunique()<5:
            st.info('Chưa đủ 5 ngày lịch sử đã lưu để tính lũy kế 5/20 phiên một cách đáng tin cậy.')
    st.subheader('Bảng chi tiết')
    shown=ranked[['symbol','exchange','Nhóm ngành','net_ty','net_volume','net_10d_vnd','source_scope']].copy()
    shown=shown.rename(columns={'symbol':'Mã','exchange':'Sàn','net_ty':'Mua/bán ròng (tỷ)','net_volume':'KL ròng','net_10d_vnd':'Ròng 10 phiên (VND)','source_scope':'Độ phủ nguồn'})
    st.dataframe(shown.sort_values('Mua/bán ròng (tỷ)',ascending=False),use_container_width=True,hide_index=True)
    st.download_button('Xuất bảng CSV',shown.to_csv(index=False).encode('utf-8-sig'),file_name='foreign_net_flow_selected.csv',mime='text/csv')
    with st.expander('📥 Nhập CSV riêng (phương án dự phòng)'):
        st.info('Nếu muốn dùng dữ liệu tổng mua/tổng bán từ nguồn khác, có thể chuyển sang trình nhập CSV cũ khi chưa có foreign_net_flow.csv. Không ghi dữ liệu lên GitHub.')
