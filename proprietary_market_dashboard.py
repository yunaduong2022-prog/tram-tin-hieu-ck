"""Read-only market proprietary dashboard; no network or writes."""
from pathlib import Path
import pandas as pd
import streamlit as st
import plotly.express as px
from proprietary_quality import audit, read_prices
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

@st.cache_data(show_spinner=False,max_entries=3)
def checked_data(path,mtime_ns,price_path,price_mtime_ns):
    return audit(load_data(path,mtime_ns),read_prices(price_path))


def _style_map(frame, func, **kwargs):
    styler = frame.style
    if hasattr(styler, "map"):
        return styler.map(func, **kwargs)
    return styler.applymap(func, **kwargs)


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
        a.metric('Tổng mua',f"{market['buy']/1e9:,.2f} tỷ"); b.metric('Tổng bán',f"{market['sell']/1e9:,.2f} tỷ"); c.metric('Mua/bán ròng',money(market['net']))
    else:
        found=market['found'] if market else 0
        st.warning(f'CafeF: {found}/{n} phiên có báo cáo tổng hợp. Chưa đủ dữ liệu để công bố tổng toàn kỳ.')
    # Historical totals shown only for individually validated sessions.
    hist=[]
    for dt in dates:
        m=_market_proprietary(ROOT/'proprietary_vnindex.csv',[dt])
        if m: hist.append({'Ngày':dt,'Ròng (tỷ)':m['net']/1e9})
    if hist:
        h=pd.DataFrame(hist); h['Ngày']=pd.to_datetime(h['Ngày']).dt.strftime('%d/%m/%Y'); h['Chiều']=h['Ròng (tỷ)'].ge(0).map({True:'Mua ròng',False:'Bán ròng'})
        fig=px.bar(h,x='Ngày',y='Ròng (tỷ)',color='Chiều',color_discrete_map={'Mua ròng':'#229970','Bán ròng':'#dd5660'},text_auto='.2f')
        fig.update_xaxes(type='category',categoryorder='array',categoryarray=h['Ngày'].tolist())
        fig.update_traces(width=.3 if len(h)==1 else .65,textposition='outside',cliponaxis=False)
        fig.update_layout(height=300,showlegend=False,margin=dict(t=35,b=30))
        st.plotly_chart(fig,use_container_width=True)
    path=ROOT/'proprietary_flow.csv'
    if not path.is_file(): st.info('Chưa có dữ liệu chi tiết.'); return
    try:
        price_path=ROOT/'eod_prices.csv'
        data,suspect=checked_data(str(path),path.stat().st_mtime_ns,str(price_path),price_path.stat().st_mtime_ns)
    except Exception: st.error('File tự doanh không đạt kiểm định.'); return
    flagged=suspect[suspect.date.isin(dates)]
    if not flagged.empty:
        st.warning(f'{len(flagged)} bản ghi CafeF cần xác minh giá/KL; tạm loại khỏi thống kê mẫu. Tổng VNINDEX nguồn CafeF vẫn độc lập, chưa đối soát toàn bộ.')
        with st.expander('Bản ghi cần xác minh (giữ nguyên dữ liệu gốc)'):
            st.dataframe(flagged[['trading_date','symbol','buy_vol','buy_val','sell_vol','sell_val','close','buy_ratio','sell_ratio','quality_reason']],hide_index=True,use_container_width=True)
    q=data[data.date.isin(dates)].copy()
    if q.empty: st.info('Chưa có bản ghi từng mã trong kỳ đã chọn.'); return
    st.subheader('Dòng tiền tự doanh theo mã')
    st.warning(f'{q.symbol.nunique()} mã · {q.date.nunique()}/{n} phiên có bản ghi · {source_label(q)}. Không đại diện toàn thị trường; thiếu bản ghi không phải bằng 0.')
    ranked=aggregate(q); ranked['Nhóm ngành']=ranked.symbol.map(_membership()).fillna('Khác'); ranked['Ròng (tỷ)']=ranked.net_val/1e9
    a,b,c=st.columns(3)
    a.metric('Giá trị ròng đã ghi nhận',money(q.net_val.sum())); b.metric('Số mã có dữ liệu',len(ranked)); c.metric('Mã mua / bán ròng',f'{ranked.net_val.gt(0).sum()} / {ranked.net_val.lt(0).sum()}')
    l,r=st.columns(2)
    for col,positive,label,color in [(l,True,'Top 10 mua ròng','#229970'),(r,False,'Top 10 bán ròng','#dd5660')]:
        with col:
            st.markdown('**'+label+'**')
            d=ranked[ranked.net_val.gt(0) if positive else ranked.net_val.lt(0)].sort_values('net_val',ascending=not positive).head(10).iloc[::-1]
            if d.empty: st.info('Không có mã phù hợp.')
            else:
                fig=px.bar(d,x='Ròng (tỷ)',y='symbol',orientation='h',hover_data=['sessions'],labels={'symbol':'Mã','sessions':'Số phiên có dữ liệu'},color_discrete_sequence=[color],text_auto='.2f')
                fig.update_traces(textposition='outside',cliponaxis=False)
                fig.update_layout(margin=dict(l=45,r=65,t=15,b=25))
                st.plotly_chart(fig,use_container_width=True)
    st.subheader('Dòng tiền tự doanh theo ngành')
    from flow_sector_chart import sector_figure
    st.plotly_chart(sector_figure(ranked,'Ròng (tỷ)',_membership()),use_container_width=True)
    st.caption('Số mã có dữ liệu / tổng mã trong kho EOD theo phân ngành nội bộ. Không đại diện toàn bộ ngành niêm yết.')
    st.subheader('Bảng chi tiết')
    search=st.text_input('Tìm mã',key='prop_market_search').strip().upper(); sectors=st.multiselect('Nhóm ngành',sorted(ranked['Nhóm ngành'].unique()),key='prop_market_sectors')
    shown=ranked.copy()
    if search: shown=shown[shown.symbol.str.contains(search,regex=False)]
    if sectors: shown=shown[shown['Nhóm ngành'].isin(sectors)]
    for c in ['buy_val','sell_val']: shown[c]=shown[c]/1e9
    shown=shown.sort_values('net_val',ascending=False)[['symbol','Nhóm ngành','sessions','buy_val','sell_val','Ròng (tỷ)','buy_vol','sell_vol','net_vol']].rename(columns={'symbol':'Mã','sessions':'Số phiên có dữ liệu','buy_val':'Mua (tỷ)','sell_val':'Bán (tỷ)','buy_vol':'KL mua','sell_vol':'KL bán','net_vol':'KL ròng'})
    st.dataframe(_style_map(shown, lambda v: 'color: #229970' if v>0 else ('color: #dd5660' if v<0 else ''),subset=['Ròng (tỷ)']),hide_index=True,use_container_width=True,column_config={c:st.column_config.NumberColumn(format='%.2f') for c in ['Mua (tỷ)','Bán (tỷ)','Ròng (tỷ)']})
    st.download_button('Xuất bảng CSV',shown.to_csv(index=False).encode('utf-8-sig'),file_name='proprietary_sample.csv',mime='text/csv')
    st.caption('Xếp hạng và tổng ngành chỉ cộng các bản ghi có sẵn; số phiên mỗi mã có thể khác nhau. Giá trị mua/bán thiếu được giữ trống.')
    st.subheader('Lịch sử từng mã')
    length=st.radio('Số phiên lịch sử', [5,10,20,60],index=2,horizontal=True,key='prop_history_length_v2')
    history_dates=sessions(calendar,day,length)
    history=data[data.date.isin(history_dates)].copy()
    available=sorted(history.symbol.unique())
    defaults=[x for x in ranked.assign(absnet=ranked.net_val.abs()).nlargest(3,'absnet').symbol.tolist() if x in available]
    chosen=st.multiselect('Chọn mã',available,default=defaults,key='prop_market_history_v2')
    if chosen:
        h=history[history.symbol.isin(chosen)].copy()
        h['Ròng (tỷ)']=h.net_val/1e9
        h=h.sort_values('date'); h['Ngày']=h.date.dt.strftime('%d/%m/%Y')
        order=[x.strftime('%d/%m/%Y') for x in history_dates]
        fig=px.scatter(h,x='Ngày',y='Ròng (tỷ)',color='symbol',labels={'symbol':'Mã'})
        fig.update_xaxes(type='category',categoryorder='array',categoryarray=order)
        fig.update_layout(height=340)
        st.plotly_chart(fig,use_container_width=True)
        st.caption('Mỗi điểm là một bản ghi có dữ liệu; không nối qua ngày thiếu. Lịch sử theo ngày kết thúc đã chọn, độc lập khung tổng quan.')

def render_from_index():
    try:
        d=pd.read_csv(ROOT/'index_prices.csv',encoding='utf-8-sig',usecols=['Mã','Ngày'])
        dates=pd.to_datetime(d.loc[d['Mã'].astype(str).str.upper().str.strip().eq('VNINDEX'),'Ngày'],format='mixed',dayfirst=True,errors='coerce')
    except (OSError,ValueError,KeyError):
        dates=[]
    return render(dates)
