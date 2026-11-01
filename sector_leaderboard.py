"""Bảng xếp hạng ngành EOD/Intraday cho nghiên cứu cá nhân.

Không gọi VNStock, không ghi dữ liệu; đọc CSV 15m hiện đã đồng bộ qua R2.
Điểm 0-100 là nghiên cứu chưa backtest, không phải tín hiệu giao dịch.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

import watchlist as WL

PRICE = 'Giá đóng cửa'
VOLUME = 'Khối lượng khớp lệnh'
INDICATORS = ('Sức mạnh giá', 'GTGD/TB20', 'Độ rộng', 'Trên MA20')
SCORE_WEIGHTS = {'Sức mạnh giá': 0.35, 'GTGD/TB20': 0.30, 'Độ rộng': 0.20, 'Trên MA20': 0.15}
EXTRA_GROUPS = ('Họ Vingroup', 'Họ Gelex')
PERIOD_COLUMNS = {
    '1 phiên': 'Hiệu suất 1 phiên (%)',
    '1 tuần': 'Hiệu suất 1 tuần (%)',
    '1 tháng': 'Hiệu suất 1 tháng (%)',
    '3 tháng': 'Hiệu suất 3 tháng (%)',
}


def _float(value):
    try:
        x = float(value)
        return x if np.isfinite(x) else np.nan
    except (ValueError, TypeError):
        return np.nan


def _compact_eod(raw: pd.DataFrame) -> pd.DataFrame:
    cols = ['Mã', 'Ngày', PRICE, VOLUME]
    d = raw.copy()[[c for c in cols if c in raw.columns]]
    if not set(cols[:3]).issubset(d.columns):
        return pd.DataFrame(columns=cols)
    if VOLUME not in d:
        d[VOLUME] = np.nan
    d['Mã'] = d['Mã'].astype(str).str.upper().str.strip()
    if not pd.api.types.is_datetime64_any_dtype(d['Ngày']):
        d['Ngày'] = pd.to_datetime(d['Ngày'], errors='coerce', dayfirst=True)
    for c in (PRICE, VOLUME):
        d[c] = pd.to_numeric(d[c], errors='coerce')
    return d.dropna(subset=['Ngày',PRICE]).sort_values(['Mã','Ngày']).drop_duplicates(['Mã','Ngày'],keep='last')


def _members(item) -> list[str]:
    return [x.strip().upper() for x in str(item.get('Mã thành viên', '')).split(',') if x.strip()]


def _eod_snapshot(d: pd.DataFrame, asof: pd.Timestamp) -> pd.DataFrame:
    """Only include stocks with actual candles on market's latest two sessions."""
    dates = pd.DatetimeIndex(d['Ngày'].unique()).sort_values()
    dates = dates[dates <= asof]
    if len(dates) < 2:
        return pd.DataFrame(columns=['Mã','Giá','% phiên','GTGD (tỷ)','Ngày'])
    current, previous = dates[-1], dates[-2]
    today = d[d['Ngày'] == current].set_index('Mã')
    before = d[d['Ngày'] == previous].set_index('Mã')
    joined = today.join(before[[PRICE]].rename(columns={PRICE:'_prev'}), how='left')
    joined['% phiên'] = (joined[PRICE] / joined['_prev'] - 1) * 100
    joined.loc[(joined['_prev'].isna()) | (joined['_prev'] <= 0), '% phiên'] = np.nan
    joined['GTGD (tỷ)'] = joined[PRICE] * joined[VOLUME] / 1e6
    joined['Giá'] = joined[PRICE]
    joined['Ngày'] = current
    return joined[['Giá','% phiên','GTGD (tỷ)','Ngày']].reset_index()


def _score_board(board: pd.DataFrame) -> pd.DataFrame:
    """Cross-sector percentile for price & volume; breadth/trend already 0..100.

    Require >=3 valid components & >=3 current symbols. Unavailable metrics never become zero.
    """
    d = board.copy()
    if d.empty:
        d['Điểm EOD'] = pd.Series(dtype=float)
        return d
    d['_score_price'] = d['RS 1 phiên'].rank(pct=True, method='average').mul(100)
    d['_score_money'] = d['GTGD/TB20'].rank(pct=True, method='average').mul(100)
    d['_score_breadth'] = d['Độ rộng'].clip(0,100)
    d['_score_trend'] = d['Trên MA20'].clip(0,100)
    cols = ['_score_price','_score_money','_score_breadth','_score_trend']
    weights = np.array([.35,.30,.20,.15])
    values = d[cols].to_numpy(dtype=float)
    valid = np.isfinite(values)
    sums = np.where(valid, values, 0) @ weights
    den = valid.astype(float) @ weights
    score = np.divide(sums,den,out=np.full(len(d),np.nan),where=den>0)
    score[(valid.sum(axis=1) < 3) | (d['Số mã hợp lệ'].fillna(0).to_numpy() < 3)] = np.nan
    d['Điểm EOD'] = np.round(score,1)
    return d.drop(columns=cols)


def build_eod_board(raw: pd.DataFrame, metrics: pd.DataFrame, info: dict, period='1 phiên') -> pd.DataFrame:
    """Return ranked row data using exact sector universe from sector_dashboard."""
    if metrics is None or metrics.empty or period not in PERIOD_COLUMNS:
        return pd.DataFrame()
    d = _compact_eod(raw)
    if d.empty:
        return pd.DataFrame()
    asof = pd.Timestamp(info['latest_date'])
    snap = _eod_snapshot(d, asof).set_index('Mã')
    rows = []
    for item in metrics.to_dict('records'):
        name = str(item['Nhóm ngành'])
        members = _members(item)
        g = snap.reindex(members).dropna(subset=['Giá'])
        valid_change = g.dropna(subset=['% phiên'])
        liquid = valid_change[valid_change['GTGD (tỷ)'] >= 1]
        leader_candidates = liquid if not liquid.empty else valid_change
        lead = leader_candidates.sort_values('% phiên',ascending=False).head(1)
        code = str(lead.index[0]) if not lead.empty else '—'
        leader_change = float(lead['% phiên'].iloc[0]) if not lead.empty else np.nan
        turnover = g['GTGD (tỷ)'].sum(min_count=1)
        rows.append({
            'Ngành': name, 'Loại': 'Hệ sinh thái' if name in EXTRA_GROUPS else 'Ngành',
            'Hiệu suất (%)': _float(item.get(PERIOD_COLUMNS[period])),
            'GTGD (tỷ)': _float(turnover),
            'Mã dẫn đầu': code, '% mã dẫn đầu': leader_change,
            'Số mã hợp lệ': int(len(valid_change)), 'Số mã trong danh sách': len(members),
            'Độ phủ (%)': 100 * len(valid_change)/len(members) if members else np.nan,
            'RS 1 phiên': _float(item.get('RS 1 phiên (điểm %) ')),
            'GTGD/TB20': _float(item.get('GTGD so TB20 (%)')),
            'Độ rộng': _float(item.get('Độ rộng tăng giá (%)')),
            'Trên MA20': _float(item.get('Trên MA20 (%)')),
            'Thời điểm': pd.Timestamp(asof),
            'Trạng thái': 'EOD xác nhận',
        })
    return _score_board(pd.DataFrame(rows))


def _intraday_snapshot(path, asof=None) -> tuple[pd.DataFrame,pd.Timestamp|None]:
    from intraday_mtf import read_intraday
    bars = read_intraday(path)
    if bars.empty:
        return pd.DataFrame(),None
    now = pd.Timestamp.now(tz='Asia/Ho_Chi_Minh').tz_localize(None) if asof is None else pd.Timestamp(asof)
    # The time field marks candle start, so require 15 minutes to have elapsed.
    bars = bars[bars['time'] + pd.Timedelta(minutes=15) <= now].copy()
    if bars.empty:
        return pd.DataFrame(),None
    bars['date'] = bars['time'].dt.normalize()
    latest_date = bars['date'].max()
    day = bars[bars['date'] == latest_date].copy()
    # Only compare a reasonably synchronized snapshot: max lag <= 30 minutes.
    latest_bar = day['time'].max()
    agg = day.groupby('symbol',sort=False).agg(
        last_time=('time','max'),close=('close','last'),open=('open','first'),
    )
    tmp = day.assign(bar_value=day['close']*day['volume']/1e6)
    gtgd = tmp.groupby('symbol')['bar_value'].sum(min_count=1)
    agg['GTGD (tỷ)'] = gtgd
    agg['fresh'] = (latest_bar - agg['last_time']) <= pd.Timedelta(minutes=30)
    agg = agg[agg['fresh']]
    agg['Ngày'] = latest_date
    return agg, latest_bar


def build_intraday_board(raw:pd.DataFrame, metrics:pd.DataFrame, info:dict, intraday_path='data/intraday_15m.csv', asof=None) -> tuple[pd.DataFrame,dict]:
    """Intraday signals use CLOSED 15m bars, comparisons to prior EOD, plus EOD base score.

    Missing/not synchronized symbols are excluded instead of silently using stale quotes.
    """
    snap,latest_time = _intraday_snapshot(intraday_path,asof)
    if snap.empty:
        return pd.DataFrame(), {'message':'Chưa có nến 15 phút đã đóng để xếp hạng.'}
    d=_compact_eod(raw)
    cutoff = pd.Timestamp(snap['Ngày'].iloc[0])
    prev = d[d['Ngày'] < cutoff].sort_values('Ngày').groupby('Mã').tail(1).set_index('Mã')[PRICE]
    snap['% phiên'] = (snap['close']/prev.reindex(snap.index)-1)*100
    snap.loc[prev.reindex(snap.index).isna() | (prev.reindex(snap.index)<=0),'% phiên'] = np.nan
    # If EOD for the same day is already present, this is a historical confirmed trading day.
    base=build_eod_board(raw,metrics,info)
    if base.empty:
        return pd.DataFrame(), {'message':'Không có dữ liệu EOD nền.'}
    scores=base.set_index('Ngành')['Điểm EOD'].to_dict()
    rows=[]
    for item in metrics.to_dict('records'):
        members=_members(item)
        group=snap.reindex(members).dropna(subset=['close','% phiên'])
        if group.empty:continue
        returns=group['% phiên']
        # Keep equal-weight means in line with existing sector_dashboard returns logic.
        price=float(returns.mean())
        turnover=float(group['GTGD (tỷ)'].sum(min_count=1))
        liquid=group[group['GTGD (tỷ)'] >= 1]
        lead=(liquid if not liquid.empty else group).sort_values('% phiên',ascending=False).head(1)
        sector=str(item['Nhóm ngành'])
        rows.append({
            'Ngành':sector,'Loại':'Hệ sinh thái' if sector in EXTRA_GROUPS else 'Ngành',
            'Hiệu suất (%)':price,'GTGD (tỷ)':turnover,
            'Mã dẫn đầu':str(lead.index[0]),'% mã dẫn đầu':float(lead['% phiên'].iloc[0]),
            'Số mã hợp lệ':len(group),'Số mã trong danh sách':len(members),
            'Độ phủ (%)':len(group)*100/len(members) if members else np.nan,
            'Điểm EOD': scores.get(sector,np.nan),
            'Thời điểm':latest_time,'Trạng thái':'Nến 15m đã đóng · tạm tính',
        })
    report={'last_bar':latest_time,'last_date':cutoff,'covered_symbols':len(snap),
            'historical': pd.Timestamp(info['latest_date']).normalize() >= cutoff}
    return pd.DataFrame(rows),report


def _fmt_pct(n):
    x=_float(n)
    return '—' if not np.isfinite(x) else f'{x:+.2f}%'


def _fmt_gtgd(n):
    x=_float(n)
    return '—' if not np.isfinite(x) else f'{x:,.0f} tỷ'



@st.cache_data(show_spinner=False, max_entries=5)
def _cached_eod_board(raw: pd.DataFrame, metrics: pd.DataFrame, eod_date: str, period: str):
    return build_eod_board(raw, metrics, {'latest_date': pd.Timestamp(eod_date)}, period)


@st.cache_data(show_spinner=False, max_entries=4)
def _cached_intraday_board(raw: pd.DataFrame, metrics: pd.DataFrame, eod_date: str,
                           path: str, file_modified_ns: int, minute_bucket: str):
    # CSV modification and 15-minute clock boundary both invalidate this cache.
    # Unused path/time args are deliberately part of Streamlit's cache key.
    return build_intraday_board(raw, metrics, {'latest_date': pd.Timestamp(eod_date)}, path)



def _show_sector_detail(raw:pd.DataFrame,group_name:str,member_list:list[str],source:str,asof, intraday_path='data/intraday_15m.csv'):
    with st.container(border=True):
        st.markdown('#### Cổ phiếu ngành ' + str(group_name))
        import sector_dashboard as SD
        stocks=SD._sector_map_stock_rows(raw,', '.join(member_list)) if hasattr(SD,'_sector_map_stock_rows') else pd.DataFrame()
        if stocks.empty:
            st.info('Nhóm này hiện chưa có dữ liệu EOD của cổ phiếu thành viên.')
            return
        st.caption(f'Giá và % thay đổi trên bảng mã: EOD. Số liệu nhóm phía trên: {source}.')
        st.dataframe(stocks,hide_index=True,use_container_width=True)
        tickers=stocks['Mã'].tolist()
        ticker=st.selectbox('Mã mở biểu đồ sáu khung',tickers,key='slead_chart_'+group_name)
        b1,b2=st.columns(2)
        if b1.button('📈 Mở biểu đồ '+ticker,key='slead_go_'+group_name,use_container_width=True):
            import nav as NAV
            for k in ('selected_code','mtf_code','tab_code'):
                st.session_state[k]=ticker
            NAV.goto('Cổ phiếu','Biểu đồ')
        if b2.button('Đóng chi tiết',key='slead_close_'+group_name,use_container_width=True):
            st.session_state['slead_focus']=None
            st.rerun()


def render_board(raw:pd.DataFrame,metrics:pd.DataFrame,info:dict):
    st.subheader('🔥 Xếp hạng sức mạnh nhóm ngành')
    st.caption('Bảng EOD xác nhận và bảng theo dõi nến 15 phút đã đóng. Bảng ngành chính không cộng chung các nhóm hệ sinh thái doanh nghiệp.')
    mode=st.segmented_control('Nguồn bảng xếp hạng',['EOD xác nhận','Trong phiên · 15 phút'],default='EOD xác nhận',key='slead_mode') or 'EOD xác nhận'
    a,b,c=st.columns([2,2,1.3])
    with a:
        period=st.selectbox('Khung EOD',list(PERIOD_COLUMNS),key='slead_period',disabled=mode!='EOD xác nhận')
    with b:
        sort_by=st.selectbox('Sắp xếp',['Hiệu suất (%)','GTGD (tỷ)','Điểm EOD'],key='slead_sort')
    with c:
        include_extra=st.toggle('Hệ sinh thái',value=False,key='slead_ecosystems')

    if mode=='EOD xác nhận':
        data=_cached_eod_board(raw, metrics, str(pd.Timestamp(info['latest_date'])), period)
        st.caption(f'✅ EOD đã xác nhận: {pd.Timestamp(info["latest_date"]):%d/%m/%Y}. GTGD xấp xỉ, tính từ giá đóng cửa × khối lượng.')
    else:
        path=Path('data/intraday_15m.csv')
        if not path.exists():
            st.info('Chưa có CSV nến 15 phút trên website. Bảng EOD bên dưới vẫn hoạt động bình thường.')
            return
        now_vn=pd.Timestamp.now(tz='Asia/Ho_Chi_Minh').tz_localize(None)
        minute_bucket=str(now_vn.floor('15min'))
        data,ctx=_cached_intraday_board(raw, metrics, str(pd.Timestamp(info['latest_date'])),
                                         str(path), path.stat().st_mtime_ns, minute_bucket)
        if data.empty:
            st.info(ctx.get('message','Chưa có dữ liệu nến 15 phút đã đóng.'))
            return
        last=ctx['last_bar']
        label='Phiên 15m lịch sử' if ctx['historical'] else 'Theo dõi trong phiên'
        st.caption(f'🕒 {label} đến {last:%H:%M %d/%m/%Y} · chỉ nến đã đóng · {ctx["covered_symbols"]} mã có dữ liệu ở thời điểm gần nhất (không phải realtime từng giây).')
    if not include_extra:
        data=data[data['Loại']=='Ngành']
    if data.empty:
        st.info('Chưa có ngành nào đáp ứng yêu cầu dữ liệu ở nguồn đã chọn.')
        return
    data=data.sort_values(sort_by,ascending=False,na_position='last').reset_index(drop=True)
    # Dense but readable ranking with click-to-select row and explicit fallback selector.
    half=(len(data)+1)//2
    display=['Ngành','Hiệu suất (%)','GTGD (tỷ)','Mã dẫn đầu','Điểm EOD']
    view=data[display].copy()
    view.insert(0,'#',range(1,len(view)+1))
    view['Mã dẫn đầu']=[(f'{sym} {_fmt_pct(pct)}' if sym!='—' else '—') for sym,pct in zip(data['Mã dẫn đầu'],data['% mã dẫn đầu'])]
    col1,col2=st.columns(2)
    for which,(col,part) in enumerate(((col1,view.iloc[:half].reset_index(drop=True)),(col2,view.iloc[half:].reset_index(drop=True)))):
        with col:
            choice=st.dataframe(
                part,hide_index=True,use_container_width=True,selection_mode='single-row',
                on_select='rerun',key=f'slead_table_{which}_{mode}_{sort_by}_{period}',
                column_config={
                    'Hiệu suất (%)':st.column_config.NumberColumn('Hiệu suất',format='%+.2f%%'),
                    'GTGD (tỷ)':st.column_config.NumberColumn('GTGD · tỷ',format='%.0f'),
                    'Điểm EOD':st.column_config.NumberColumn('Điểm thử',format='%.1f'),
                },
            )
            selected=choice.selection.rows if hasattr(choice,'selection') else []
            # Observe selection changes only; an old selection in the other table
            # must not override a newly clicked row.
            seen_key=f'slead_seen_{which}_{mode}_{sort_by}_{period}'
            current_rows=tuple(selected)
            if current_rows != st.session_state.get(seen_key, ()):
                st.session_state[seen_key]=current_rows
                if current_rows:
                    pos=current_rows[0]
                    if 0 <= pos < len(part):
                        st.session_state['slead_focus']=str(part.iloc[pos]['Ngành'])
    st.caption('Chạm/chọn một dòng trong bảng để xem mã ngành. Điểm EOD 0–100 là chỉ số thử nghiệm: giá tương đối 35%, GTGD/TB20 30%, độ rộng 20%, xu hướng MA20 15%. Không dùng làm tín hiệu mua bán.')
    opts=data['Ngành'].tolist()
    focus=st.session_state.get('slead_focus')
    if focus in opts:
        st.markdown(f'**Ngành đã chọn: {focus}**')
        record=data[data['Ngành']==focus].iloc[0]
        st.caption(f'Độ phủ: {record["Số mã hợp lệ"]}/{record["Số mã trong danh sách"]} mã có dữ liệu hợp lệ.')
        member_list=WL.GROUPS.get(focus,[])
        _show_sector_detail(raw,focus,member_list,mode,record['Thời điểm'])
