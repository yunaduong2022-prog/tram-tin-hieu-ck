"""Private-market foreign net flow dashboard. Does not call VNStock on Cloud."""
from __future__ import annotations
from pathlib import Path
import pandas as pd
import streamlit as st
import plotly.express as px

DATA_PATH=Path('data/foreign_net_flow.csv')

@st.cache_data(show_spinner=False, max_entries=3)
def _read_net(mtime_ns, path):
    data=pd.read_csv(path,dtype={'symbol':str,'trading_date':str})
    from foreign_net_collector import validate_table
    data=validate_table(data)
    data['trading_date']=pd.to_datetime(data['trading_date'],format='%Y-%m-%d')
    return data

def _membership():
    try:
        import watchlist as wl
        groups=wl.membership(wl.VN30_DU_PHONG)
        return {code: next((name for name in names if name not in (wl.VN30,wl.OLD) and not name.startswith('Họ ')), 'Khác') for code,names in groups.items()}
    except (ImportError,AttributeError):
        return {}

def render():
    st.title('🌐 Dòng tiền khối ngoại')
    st.caption('Nguồn: SSI iBoard / VNStock Insights trên Windows → R2. **Chỉ phản ánh mua/bán RÒNG**, không phải tổng giá trị mua hoặc tổng giá trị bán.')
    from foreign_market_totals import render as render_totals
    render_totals()
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
    try:
        idx=pd.read_csv('data/index_prices.csv',usecols=['Mã','Ngày'],encoding='utf-8-sig')
    except (OSError,ValueError,KeyError):
        st.warning('Chưa có lịch phiên VNINDEX.'); return
    calendar=pd.to_datetime(idx.loc[idx['Mã'].astype(str).str.strip().str.upper().eq('VNINDEX'),'Ngày'],format='mixed',dayfirst=True,errors='coerce').dropna().dt.normalize().drop_duplicates().sort_values()
    dates=sorted(calendar.dt.date.unique())
    if not dates:
        st.warning('Chưa có lịch phiên VNINDEX.'); return
    period=st.radio('Khung thời gian',['Phiên','Tuần','Tháng','Quý'],horizontal=True,key='foreign_detail_period')
    n={'Phiên':1,'Tuần':5,'Tháng':21,'Quý':63}[period]
    st.caption('Khung lũy kế: 1 / 5 / 21 / 63 phiên giao dịch gần nhất, không phải kỳ lịch cố định.')
    a,b=st.columns([1,1])
    with a:
        day=st.selectbox('Ngày giao dịch',dates,index=len(dates)-1,format_func=lambda x:x.strftime('%d/%m/%Y'),key='foreign_net_date')
    sessions=calendar[calendar.le(pd.Timestamp(day))].tail(n)
    rows=data[data.trading_date.isin(sessions)].copy()
    if rows.empty:
        st.warning('Không có dữ liệu khối ngoại trong khung đã chọn.'); return
    observed=rows.groupby('symbol').trading_date.nunique()
    if n==1:
        selected=rows.copy()
    else:
        selected=rows.sort_values('trading_date').drop_duplicates('symbol',keep='last').copy()
        selected['net_value_vnd']=selected.symbol.map(rows.groupby('symbol').net_value_vnd.sum(min_count=1))
        volume=rows.groupby('symbol').net_volume
        selected['net_volume']=selected.symbol.map(volume.sum(min_count=1).where(volume.count().eq(volume.size())))
        selected['net_10d_vnd']=float('nan')
        selected['source_scope']=selected.symbol.map(rows.groupby('symbol').source_scope.agg(lambda v:' / '.join(sorted(set(v.dropna().astype(str))))))
    selected['Số phiên có dữ liệu']=selected.symbol.map(observed)
    st.caption(f'Có dữ liệu {rows.trading_date.nunique()}/{n} phiên yêu cầu; {int(observed.eq(n).sum())}/{len(observed)} mã đủ phiên. Tổng chỉ cộng các quan sát có thật, không điền 0 cho dữ liệu thiếu.')
    scopes=rows['source_scope'].dropna().unique().tolist()
    full=(len(scopes)==1 and scopes[0]=='FLOW_VERIFIED_FULL')
    with b:
        if full:
            st.success('Theo dõi danh sách mã nguồn trả về (3 sàn, tùy độ phủ)')
        elif 'SSI_WATCHLIST_SAMPLE' in scopes:
            st.warning(
                f'Dữ liệu khối ngoại SSI: {len(selected)} mã có số liệu. '
                'Độ phủ không đầy đủ; không đại diện toàn thị trường.'
            )
        else:
            st.warning('Chỉ các mã thuộc TOP mua/bán ròng — KHÔNG đại diện toàn thị trường')
    industry=_membership()
    selected['Nhóm ngành']=selected['symbol'].map(industry).fillna('Khác')
    st.caption('Đồng bộ lúc (UTC): '+str(rows['observed_at_utc'].dropna().astype(str).max())+'. Phân ngành theo danh sách tham khảo nội bộ; tổng theo ngành chỉ là các mã có trong dữ liệu.')
    net=selected['net_value_vnd']/1e9
    buy=int((net>0).sum()); sell=int((net<0).sum())
    k1,k2,k3=st.columns(3)
    k1.metric('Giá trị ròng đã ghi nhận',f'{net.sum():+,.1f} tỷ đồng')
    k2.metric('Số mã có dữ liệu',f'{len(selected):,}')
    k3.metric('Số mã mua ròng / bán ròng',f'{buy} / {sell}')
    st.caption('Không hiển thị tổng mua hoặc tổng bán vì bảng tổng hợp này chỉ lưu giá trị ròng. Không cộng lũy kế dài hạn từ các ngày chưa lưu.')
    ranked=selected.assign(net_ty=net.values)
    l,r=st.columns(2)
    with l:
        st.markdown('**Top mua ròng**')
        data_buy=ranked[ranked.net_ty>0].nlargest(12,'net_ty').sort_values('net_ty')
        if data_buy.empty: st.info('Không có mã mua ròng trong dữ liệu')
        else: st.plotly_chart(px.bar(data_buy,y='symbol',x='net_ty',orientation='h',labels={'symbol':'Mã','net_ty':'Tỷ đồng'},color_discrete_sequence=['#229970'],text_auto='.2f').update_traces(textposition='outside',cliponaxis=False).update_layout(margin=dict(l=45,r=65,t=15,b=25)),use_container_width=True)
    with r:
        st.markdown('**Top bán ròng**')
        data_sell=ranked[ranked.net_ty<0].nsmallest(12,'net_ty').sort_values('net_ty',ascending=False)
        if data_sell.empty: st.info('Không có mã bán ròng trong dữ liệu')
        else: st.plotly_chart(px.bar(data_sell,y='symbol',x='net_ty',orientation='h',labels={'symbol':'Mã','net_ty':'Tỷ đồng'},color_discrete_sequence=['#dd5660'],text_auto='.2f').update_traces(textposition='outside',cliponaxis=False).update_layout(margin=dict(l=65,r=45,t=15,b=25)),use_container_width=True)
    st.subheader('Dòng tiền khối ngoại theo ngành')
    from flow_sector_chart import sector_figure
    st.plotly_chart(sector_figure(ranked,'net_ty',industry),use_container_width=True)
    st.caption('Tỷ lệ mã tính trên kho EOD và phân ngành nội bộ, không phải toàn bộ số mã niêm yết. Khác gồm các mã chưa có phân ngành. Số liệu chỉ phản ánh dữ liệu đã ghi nhận.')
    st.subheader('Lịch sử đã thu thập')
    available=sorted(data.symbol.dropna().unique())
    defaults=ranked.reindex(ranked.net_ty.abs().sort_values(ascending=False).index)['symbol'].head(3).tolist()
    chosen=st.multiselect('Chọn mã',available,default=defaults,key='foreign_net_history_symbols')
    if chosen:
        series=data[data.symbol.isin(chosen)].copy().sort_values(['symbol','trading_date'])
        series['Giá trị ròng (tỷ)']=series['net_value_vnd']/1e9
        st.plotly_chart(px.line(series,x='trading_date',y='Giá trị ròng (tỷ)',color='symbol',markers=True,labels={'trading_date':'Ngày giao dịch','symbol':'Mã cổ phiếu'}).update_traces(mode='markers').update_xaxes(tickformat='%d/%m/%Y'),use_container_width=True)
        if data.trading_date.nunique()<5:
            st.info('Chưa đủ 5 ngày lịch sử đã lưu để tính lũy kế 5/20 phiên một cách đáng tin cậy.')
    st.subheader('Bảng chi tiết')
    shown=ranked[['symbol','exchange','Nhóm ngành','net_ty','net_volume','net_10d_vnd','source_scope','Số phiên có dữ liệu']].copy()
    shown=shown.rename(columns={'symbol':'Mã','exchange':'Sàn','net_ty':'Mua/bán ròng (tỷ)','net_volume':'KL ròng','net_10d_vnd':'Ròng 10 phiên (VND)','source_scope':'Độ phủ nguồn'})

    # MIN_FOREIGN_DISPLAY_V2
    _exchange = "S\u00e0n"
    _net10 = "R\u00f2ng 10 phi\u00ean (VND)"
    _scope = "\u0110\u1ed9 ph\u1ee7 ngu\u1ed3n"
    _code = "M\u00e3"

    shown[_exchange] = shown[_exchange].fillna(
        "Ch\u01b0a x\u00e1c \u0111\u1ecbnh"
    ).replace(
        "", "Ch\u01b0a x\u00e1c \u0111\u1ecbnh"
    )

    shown[_net10] = pd.to_numeric(
        shown[_net10],errors="coerce"
    ) / 1e9

    shown = shown.rename(columns={
        _net10:"R\u00f2ng 10 phi\u00ean (t\u1ef7)"
    })

    shown[_scope] = shown[_scope].replace({
        "SSI_WATCHLIST_SAMPLE":"M\u1eabu SSI",
        "FLOW_VERIFIED_FULL":"Danh s\u00e1ch ngu\u1ed3n",
        "RANKING_TOP_ONLY":"Ch\u1ec9 TOP mua/b\u00e1n"
    })

    try:
        directory = pd.read_csv(
            "data/company_directory.csv",
            encoding="utf-8-sig"
        )

        names = dict(zip(
            directory.symbol,
            directory.company_name
        ))

        shown.insert(
            1,
            "T\u00ean doanh nghi\u1ec7p",
            shown[_code].map(names).fillna("")
        )
    except (OSError,ValueError,KeyError):
        pass

    st.dataframe(shown.sort_values('Mua/bán ròng (tỷ)',ascending=False),use_container_width=True,hide_index=True)
    st.download_button('Xuất bảng CSV',shown.to_csv(index=False).encode('utf-8-sig'),file_name='foreign_net_flow_selected.csv',mime='text/csv')
    with st.expander('📥 Nhập CSV riêng (phương án dự phòng)'):
        st.info('Nếu muốn dùng dữ liệu tổng mua/tổng bán từ nguồn khác, có thể chuyển sang trình nhập CSV cũ khi chưa có foreign_net_flow.csv. Không ghi dữ liệu lên GitHub.')
