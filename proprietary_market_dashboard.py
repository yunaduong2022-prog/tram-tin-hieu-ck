"""Read-only market proprietary dashboard; no network or writes."""
from pathlib import Path
import pandas as pd
import streamlit as st
import plotly.express as px
from proprietary_dashboard import load_data, source_label
from foreign_net_dashboard import _membership
from vnindex_institutional_flow import _market_proprietary

ROOT = Path('data')
PERIODS = {'Phiên': 1, 'Tuần': 5, 'Tháng': 21, 'Quý': 63}

def sessions(index, day, n):
    d = pd.to_datetime(pd.Series(index), errors='coerce').dropna().dt.normalize().drop_duplicates().sort_values()
    return list(d[d.le(pd.Timestamp(day))].tail(n))

def aggregate(q):
    g = q.groupby('symbol')
    a = g[['buy_val','sell_val','net_val','buy_vol','sell_vol','net_vol']].sum(min_count=1)
    # Do not show partial gross sums as complete gross totals.
    for c in ['buy_val','sell_val','buy_vol','sell_vol','net_vol']:
        a.loc[g[c].count().lt(g.size()),c] = float('nan')
    a['sessions'] = g['date'].nunique()
    return a.reset_index()

def money(x):
    return '—' if pd.isna(x) else f'{x/1e9:+,.2f} tỷ'

def render(index_dates):
    st.title('🏛️ Dòng tiền tự doanh')
    st.caption('CafeF / VNStock VCI · Dữ liệu cuối phiên qua R2. Tổng VNINDEX từ báo cáo CafeF; xếp hạng từng mã chỉ trong mẫu đã lưu.')
    calendar = pd.to_datetime(pd.Series(index_dates),errors='coerce').dropna().dt.normalize().drop_duplicates().sort_values()
    if calendar.empty:
        st.warning('Chưa có lịch phiên VNINDEX đã xác nhận.'); return
    a,b = st.columns(2)
    with a:
        day = st.selectbox('Ngày kết thúc',list(calendar.dt.date.iloc[::-1]),format_func=lambda x:x.strftime('%d/%m/%Y'),key='prop_market_day')
    with b:
        period = st.radio('Khung thời gian',list(PERIODS),horizontal=True,key='prop_market_period')
    n = PERIODS[period]; dates = sessions(calendar,day,n)
    st.caption(f'{dates[0]:%d/%m/%Y} – {dates[-1]:%d/%m/%Y} · {n} phiên giao dịch gần nhất theo lịch VNINDEX, không phải kỳ lịch cố định.')
    market = _market_proprietary(ROOT/'proprietary_vnindex.csv',dates)
    st.subheader('Tổng giao dịch tự doanh VNINDEX')
    if market and market['found']==n and len(dates)==n:
        a,b,c=st.columns(3)
        a.metric('Tổng mua',money(market['buy'])); b.metric('Tổng bán',money(market['sell'])); c.metric('Mua/bán ròng',money(market['net']))
    else:
        found=market['found'] if market else 0
        st.warning(f'CafeF: {found}/{n} phiên có báo cáo tổng hợp. Chưa đủ dữ liệu để công bố tổng toàn kỳ.')
    # Historical totals shown only for individually validated sessions.
    hist=[]
    for dt in dates:
        m=_market_proprietary(ROOT/'proprietary_vnindex.csv',[dt])
        if m: hist.append({'Ngày':dt,'Ròng (tỷ)':m['net']/1e9})
    if hist:
        h=pd.DataFrame(hist); h['Chiều']=h['Ròng (tỷ)'].ge(0).map({True:'Mua ròng',False:'Bán ròng'})
        st.plotly_chart(px.bar(h,x='Ngày',y='Ròng (tỷ)',color='Chiều',color_discrete_map={'Mua ròng':'#229970','Bán ròng':'#dd5660'}),use_container_width=True)
    path=ROOT/'proprietary_flow.csv'
    if not path.is_file(): st.info('Chưa có dữ liệu chi tiết.'); return
    try: data=load_data(str(path),path.stat().st_mtime_ns)
    except Exception: st.error('File tự doanh không đạt kiểm định.'); return
    q=data[data.date.isin(dates)].copy()
    if q.empty: st.info('Chưa có bản ghi từng mã trong kỳ đã chọn.'); return
    st.subheader('Dòng tiền từng mã trong mẫu')
    st.warning(f'{q.symbol.nunique()} mã · {q.date.nunique()}/{n} phiên có bản ghi · {source_label(q)}. Không đại diện toàn thị trường; thiếu bản ghi không phải bằng 0.')
    ranked=aggregate(q); ranked['Nhóm ngành']=ranked.symbol.map(_membership()).fillna('Khác'); ranked['Ròng (tỷ)']=ranked.net_val/1e9
    a,b,c=st.columns(3)
    a.metric('Ròng các bản ghi trong mẫu',money(q.net_val.sum())); b.metric('Số mã trong mẫu',len(ranked)); c.metric('Mã mua / bán ròng',f'{ranked.net_val.gt(0).sum()} / {ranked.net_val.lt(0).sum()}')
    l,r=st.columns(2)
    for col,positive,label,color in [(l,True,'Top 10 mua ròng','#229970'),(r,False,'Top 10 bán ròng','#dd5660')]:
        with col:
            st.markdown('**'+label+' (trong mẫu)**')
            d=ranked[ranked.net_val.gt(0) if positive else ranked.net_val.lt(0)].sort_values('net_val',ascending=not positive).head(10).iloc[::-1]
            if d.empty: st.info('Không có mã phù hợp.')
            else: st.plotly_chart(px.bar(d,x='Ròng (tỷ)',y='symbol',orientation='h',hover_data=['sessions'],labels={'symbol':'Mã','sessions':'Số phiên có dữ liệu'},color_discrete_sequence=[color]),use_container_width=True)
    st.subheader('Dòng tiền theo ngành trong mẫu')
    g=ranked.groupby('Nhóm ngành',as_index=False)['Ròng (tỷ)'].sum().sort_values('Ròng (tỷ)'); g['Chiều']=g['Ròng (tỷ)'].ge(0).map({True:'Mua ròng',False:'Bán ròng'})
    st.plotly_chart(px.bar(g,x='Ròng (tỷ)',y='Nhóm ngành',orientation='h',color='Chiều',color_discrete_map={'Mua ròng':'#229970','Bán ròng':'#dd5660'}),use_container_width=True)
    st.subheader('Bảng chi tiết trong mẫu')
    search=st.text_input('Tìm mã',key='prop_market_search').strip().upper(); sectors=st.multiselect('Nhóm ngành',sorted(ranked['Nhóm ngành'].unique()),key='prop_market_sectors')
    shown=ranked.copy()
    if search: shown=shown[shown.symbol.str.contains(search,regex=False)]
    if sectors: shown=shown[shown['Nhóm ngành'].isin(sectors)]
    for c in ['buy_val','sell_val']: shown[c]=shown[c]/1e9
    shown=shown.sort_values('net_val',ascending=False)[['symbol','Nhóm ngành','sessions','buy_val','sell_val','Ròng (tỷ)','buy_vol','sell_vol','net_vol']].rename(columns={'symbol':'Mã','sessions':'Số phiên có dữ liệu','buy_val':'Mua (tỷ)','sell_val':'Bán (tỷ)','buy_vol':'KL mua','sell_vol':'KL bán','net_vol':'KL ròng'})
    st.dataframe(shown,hide_index=True,use_container_width=True,column_config={c:st.column_config.NumberColumn(format='%.2f') for c in ['Mua (tỷ)','Bán (tỷ)','Ròng (tỷ)']})
    st.download_button('Xuất bảng CSV',shown.to_csv(index=False).encode('utf-8-sig'),file_name='proprietary_sample.csv',mime='text/csv')
    st.caption('Xếp hạng và tổng ngành chỉ cộng các bản ghi có sẵn; số phiên mỗi mã có thể khác nhau. Giá trị mua/bán thiếu được giữ trống.')
    st.subheader('Lịch sử từng mã')
    chosen=st.multiselect('Chọn mã',sorted(q.symbol.unique()),default=ranked.assign(absnet=ranked.net_val.abs()).nlargest(3,'absnet').symbol.tolist(),key='prop_market_history')
    if chosen:
        h=q[q.symbol.isin(chosen)].copy(); h['Ròng (tỷ)']=h.net_val/1e9
        st.plotly_chart(px.scatter(h,x='date',y='Ròng (tỷ)',color='symbol',labels={'date':'Ngày','symbol':'Mã'}),use_container_width=True)

def render_from_index():
    try:
        d=pd.read_csv(ROOT/'index_prices.csv',encoding='utf-8-sig',usecols=['Mã','Ngày'])
        dates=pd.to_datetime(d.loc[d['Mã'].astype(str).str.upper().str.strip().eq('VNINDEX'),'Ngày'],format='mixed',dayfirst=True,errors='coerce')
    except (OSError,ValueError,KeyError):
        dates=[]
    return render(dates)
