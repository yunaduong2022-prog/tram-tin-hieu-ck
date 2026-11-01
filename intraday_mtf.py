"""Six-frame viewer. Reads local/GitHub CSV only. NEVER imports VNStock.

VN 4H convention: one aggregate per exchange session (approximately four continuous
matching hours, lunch excluded).  It is NOT an internationally standardized 4H bar.
"""
from __future__ import annotations

from pathlib import Path
import datetime as dt
import math

import pandas as pd

INTRADAY_FILE = Path('data/intraday_15m.csv')
COLS = ['symbol', 'time', 'open', 'high', 'low', 'close', 'volume', 'source']
OHLC = {'open': 'Giá mở cửa', 'high': 'Giá cao nhất', 'low': 'Giá thấp nhất',
        'close': 'Giá đóng cửa', 'volume': 'Khối lượng khớp lệnh'}
VIEW_TFS = ('15m', '1H', '4H', 'D', 'W', 'M')
VIEW_LABEL = {'15m': '15 phút', '1H': '1 giờ', '4H': '4 giờ (1 phiên VN)',
              'D': 'Ngày', 'W': 'Tuần', 'M': 'Tháng'}


def _localize(series):
    """Treat timezone-naive provider times as Vietnam-local; tz-aware as true instants."""
    out = pd.to_datetime(series, errors='coerce', utc=True)
    # Our collector always writes timezone-aware ISO; it never writes naive values.
    return out.dt.tz_convert('Asia/Ho_Chi_Minh').dt.tz_localize(None)


def read_intraday(path=INTRADAY_FILE, symbol=None, strict=False):
    p = Path(path)
    if not p.exists() or p.stat().st_size == 0:
        return pd.DataFrame(columns=COLS)
    raw = pd.read_csv(p, dtype={'symbol': str, 'time': str})
    if not set(COLS).issubset(raw.columns):
        raise ValueError('Intraday CSV is missing required columns')
    raw = raw[COLS].copy()
    initial_rows=len(raw)
    raw['symbol'] = raw['symbol'].astype(str).str.upper().str.strip()
    if symbol:
        raw = raw[raw['symbol'] == str(symbol).upper()].copy()
    if raw.empty:
        return raw
    raw['time'] = _localize(raw['time'])
    for field in ('open','high','low','close','volume'):
        raw[field] = pd.to_numeric(raw[field], errors='coerce')
    raw = raw.dropna(subset=['time','open','high','low','close','volume'])
    ok = (raw['low'] > 0) & (raw['high'] >= raw[['open','close','low']].max(axis=1)) & \
         (raw['low'] <= raw[['open','close','high']].min(axis=1)) & (raw['volume'] >= 0)
    result=raw.loc[ok].drop_duplicates(['symbol','time'],keep='last').sort_values(['symbol','time']).reset_index(drop=True)
    if strict and len(result)!=initial_rows:
        raise ValueError('Stored intraday file has malformed or duplicate rows; refusing overwrite')
    return result


def _aggregate(g, key):
    if g.empty:
        return pd.DataFrame(columns=g.columns)
    out = g.groupby(key, sort=True).agg({
        'symbol': 'first', 'time': 'last', 'open': 'first', 'high': 'max',
        'low': 'min', 'close': 'last', 'volume': 'sum', 'source': 'last'
    }).reset_index(drop=True)
    return out


def intraday_frames(d):
    if d.empty:
        return {key: d.copy() for key in ('15m','1H','4H')}
    g = d.sort_values('time').copy()
    # 1H anchored to exchange clock; lunch break produces an intentionally short bar.
    hour = g['time'].dt.floor('h')
    # VN trading day is approximately four matching hours. One 4H aggregate per day.
    session = g['time'].dt.normalize()
    return {'15m':g, '1H':_aggregate(g, hour), '4H':_aggregate(g, session)}


def _engine_frame(bars):
    if bars.empty:
        return pd.DataFrame()
    result = bars.rename(columns={'symbol':'Mã','time':'Ngày',**OHLC}).copy()
    return result[['Mã','Ngày','Giá mở cửa','Giá cao nhất','Giá thấp nhất','Giá đóng cửa','Khối lượng khớp lệnh']].reset_index(drop=True)


def build_six_frames(code, intraday, historical_eod):
    """Return {tf: {'df': indicator DataFrame, 'provisional':bool}}.

    Intraday is 15m only. In-progress D/W/M are built using a provisional day bar;
    canonical historical EOD CSV is NEVER overwritten.
    """
    import engine as E
    sym = str(code).upper()
    t = intraday[intraday['symbol'] == sym].copy() if not intraday.empty else pd.DataFrame(columns=COLS)
    blocks = intraday_frames(t)
    result = {}
    now = pd.Timestamp.now(tz='Asia/Ho_Chi_Minh').tz_localize(None)
    for tf, bars in blocks.items():
        g = _engine_frame(bars)
        last = pd.Timestamp(g['Ngày'].iloc[-1]) if len(g) else None
        if tf == '15m':
            provisional = bool(last is not None and now < last + pd.Timedelta(minutes=15))
        elif tf == '1H':
            provisional = bool(last is not None and now < last.floor('h') + pd.Timedelta(hours=1))
        else:
            provisional = bool(last is not None and last.date() == now.date() and now.time() < dt.time(15))
        result[tf] = {'df': E.add_indicators(g) if not g.empty else g,
                      'provisional': provisional, 'source':'15m intraday'}
    d = historical_eod.copy()
    if not d.empty:
        d = E.clean_raw(d[d['Mã'].astype(str).str.upper() == sym])
    else:
        d = pd.DataFrame(columns=['Mã','Ngày']+E.NUMERIC_COLS)
    has_provisional_day = False
    if len(t):
        day = _aggregate(t, t['time'].dt.normalize())
        if not day.empty:
            latest = pd.Timestamp(day['time'].iloc[-1]).normalize()
            eod_latest = d['Ngày'].max().normalize() if len(d) else pd.Timestamp.min
            if latest > eod_latest:
                temp = _engine_frame(day.tail(1))
                # Even when a day's quote coverage is incomplete it is clearly labelled provisional.
                d = pd.concat([d, temp], ignore_index=True)
                has_provisional_day = True
    d = d.sort_values('Ngày').drop_duplicates(['Mã','Ngày'],keep='last').reset_index(drop=True)
    for tf in ('D','W','M'):
        if d.empty:
            frame = d.copy()
        else:
            frame = E.add_indicators(E.resample_ohlcv(d,tf))
        result[tf] = {'df':frame, 'provisional':has_provisional_day,
                      'source':'EOD + 15m provisional' if has_provisional_day else 'EOD confirmed'}
    return result


def latest_row_summary(tf, item):
    import supertrend as SPT
    import wyckoff as WYK
    g = item['df']
    base = {'Khung':tf, 'Nến':'Tạm tính' if item['provisional'] else 'Đã đóng',
            'Thời điểm':'—', 'Giá':'—', 'MA20':'—', 'MA50':'—',
            'RSI14':'—', 'MACD':'—', 'Ichimoku':'—', 'Supertrend':'—', 'Wyckoff':'—', 'Điều kiện':'Chưa đủ dữ liệu'}
    if g.empty:
        base['Nến'] = 'Chưa có dữ liệu'
        return base
    r = g.iloc[-1]
    base['Thời điểm'] = str(pd.Timestamp(r['Ngày']).strftime('%d/%m/%Y %H:%M' if tf in ('15m','1H','4H') else '%d/%m/%Y'))
    def fmt(x, places=2):
        v = pd.to_numeric(x,errors='coerce')
        return f'{float(v):,.{places}f}' if pd.notna(v) and math.isfinite(float(v)) else '—'
    base['Giá'] = fmt(r['Giá đóng cửa'])
    base['MA20'] = fmt(r.get('MA20'))
    base['MA50'] = fmt(r.get('MA50'))
    base['RSI14'] = fmt(r.get('RSI'),1)
    base['MACD'] = fmt(r.get('MACD_hist'),3)
    if pd.notna(r.get('SpanA')) and pd.notna(r.get('SpanB')):
        px = r['Giá đóng cửa']
        top = max(r['SpanA'],r['SpanB'])
        bottom = min(r['SpanA'],r['SpanB'])
        base['Ichimoku'] = 'Trên mây' if px > top else 'Dưới mây' if px < bottom else 'Trong mây'
    if pd.notna(r.get('MA20')) and pd.notna(r.get('RSI')) and pd.notna(r.get('MACD_hist')):
        if r['Giá đóng cửa'] > r['MA20'] and r['RSI'] >= 50 and r['MACD_hist'] > 0:
            base['Điều kiện'] = 'Ưu thế tăng (tham khảo)'
        elif r['Giá đóng cửa'] < r['MA20'] and r['RSI'] < 50 and r['MACD_hist'] < 0:
            base['Điều kiện'] = 'Ưu thế giảm (tham khảo)'
        else:
            base['Điều kiện'] = 'Chưa đồng thuận'
    if len(g)>=SPT.PERIOD:
        st = SPT.compute(g)
        base['Supertrend'] = 'Tăng' if int(st['ST_trend'].iloc[-1])==1 else 'Giảm'
    if len(g) >= WYK.MIN_BARS:
        try:
            w = WYK.analyze(g)
            base['Wyckoff'] = str(WYK.label(w))[:55] if w is not None else '—'
        except Exception:
            pass
    return base


def plot_frame(tf, item):
    """D/W/M-compatible candlestick style for actual 15m / grouped 1H / VN-session 4H bars.

    MIN_HOURLY_CANDLE_STYLE_V1. Uses only OHLCV already stored; never fabricates an hour.
    """
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    import supertrend as SPT
    import theme as TH

    g = item['df']
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True,
                        row_heights=[.63, .19, .18], vertical_spacing=.045)
    if g.empty:
        return fig
    limit={'15m':200,'1H':160,'4H':120}.get(tf,250)
    g=g.tail(limit).copy()
    intraday = tf in ('15m','1H','4H')
    stamps=pd.to_datetime(g['Ngày'], errors='coerce')
    # Categorical bars skip nights, lunch and weekends without inventing missing 15m bars.
    x=stamps.dt.strftime('%d/%m %H:%M') if intraday else stamps
    rising = g['Giá đóng cửa'].ge(g['Giá mở cửa'])
    colors=['#089981' if up else '#F23645' for up in rising]
    volume=pd.to_numeric(g['Khối lượng khớp lệnh'], errors='coerce').fillna(0)
    tips=[f'<b>{pd.Timestamp(t):%d/%m/%Y %H:%M}</b><br>'
          f'Mở: {o:,.2f} · Cao: {h:,.2f}<br>'
          f'Thấp: {l:,.2f} · Đóng: {c:,.2f}<br>'
          f'KL: {v:,.0f} cp'
          for t,o,h,l,c,v in zip(stamps,g['Giá mở cửa'],g['Giá cao nhất'],
                  g['Giá thấp nhất'],g['Giá đóng cửa'],volume)]
    fig.add_trace(go.Candlestick(x=x,open=g['Giá mở cửa'],high=g['Giá cao nhất'],
            low=g['Giá thấp nhất'],close=g['Giá đóng cửa'],
            text=tips,hoverinfo='text',whiskerwidth=0,name='OHLC',
            increasing=dict(line=dict(color='#089981',width=1),fillcolor='#089981'),
            decreasing=dict(line=dict(color='#F23645',width=1),fillcolor='#F23645')),
            row=1,col=1)
    for fld,col in [('MA9','#9333ea'),('MA20','#db2777'),('MA50','#0d9488'),('MA200','#64748b')]:
        if fld in g.columns:
            fig.add_trace(go.Scatter(x=x,y=g[fld],name=fld,mode='lines',
                line=dict(color=col,width=1.5),hovertemplate='%{y:,.2f}<extra>'+fld+'</extra>'),row=1,col=1)
    if len(g)>=SPT.PERIOD:
        st=SPT.compute(g)
        for fld,name,color in [('ST_up','ST Tăng','#16a34a'),('ST_dn','ST Giảm','#dc2626')]:
            fig.add_trace(go.Scatter(x=x,y=st[fld],name=name,
                                    line=dict(color=color,width=1.5)),row=1,col=1)
    fig.add_trace(go.Bar(x=x,y=volume,name='Khối lượng',
                         marker_color=colors,opacity=.72),row=2,col=1)
    if 'RSI' in g.columns:
        fig.add_trace(go.Scatter(x=x,y=g['RSI'],name='RSI 14',
                                 line=dict(color='#f59e0b',width=1.5)),row=3,col=1)
    fig.add_hline(y=70,line_dash='dot',row=3,col=1,line_color='#8B95A5')
    fig.add_hline(y=30,line_dash='dot',row=3,col=1,line_color='#8B95A5')
    fig.update_layout(height=690,template=TH.plotly_template(),
        paper_bgcolor='rgba(0,0,0,0)',plot_bgcolor='rgba(0,0,0,0)',
        xaxis_rangeslider_visible=False,
        title=f'{VIEW_LABEL[tf]} | '+('Đang hình thành / thiếu nến 15m' if item['provisional']
              else 'Dữ liệu 15m đã thu thập' if intraday else 'Nến EOD đã xác nhận'),
        margin=dict(l=12,r=48,t=60,b=22),
        legend=dict(orientation='h',y=1.07,font=dict(size=11)),
        hovermode='x unified')
    if intraday:
        fig.update_xaxes(type='category',nticks=12)
    else:
        fig.update_xaxes(nticks=12)
    fig.update_xaxes(showgrid=False,showticklabels=False,row=1,col=1)
    fig.update_xaxes(showgrid=False,showticklabels=False,row=2,col=1)
    fig.update_xaxes(showgrid=False,showticklabels=True,row=3,col=1)
    return fig


def render_six_frame_panel(code, selected_tf, historical_eod=None, show_chart=True):
    """Streamlit viewer; no fetches or VNStock calls."""
    import streamlit as st
    import engine as E
    path = INTRADAY_FILE
    mtime = path.stat().st_mtime_ns if path.exists() else -1
    @st.cache_data(show_spinner=False, max_entries=8)
    def _load_intraday(fname, fingerprint):
        return read_intraday(fname)
    @st.cache_data(show_spinner=False, max_entries=8)
    def _load_symbol_daily(sym, file_mtime):
        p = Path('data/eod_prices.csv')
        if not p.exists():
            return pd.DataFrame(columns=['Mã','Ngày']+E.NUMERIC_COLS)
        # usecols avoids loading unneeded extras into memory
        frame = pd.read_csv(p, usecols=['Mã','Ngày']+E.NUMERIC_COLS)
        return frame[frame['Mã'].astype(str)==sym].copy()
    intraday = _load_intraday(str(path),mtime)
    eod = Path('data/eod_prices.csv')
    eod_mtime = eod.stat().st_mtime_ns if eod.exists() else -1
    old = historical_eod if historical_eod is not None else _load_symbol_daily(str(code),eod_mtime)
    frames = build_six_frames(code,intraday,old)
    if not intraday.empty and str(code) in set(intraday['symbol']):
        newest = intraday.loc[intraday['symbol']==str(code),'time'].max()
        st.caption(f'Nến 15m cập nhật đến: {newest:%H:%M %d/%m/%Y} (giờ VN) · Không phải realtime từng giây')
    else:
        st.warning(f'Chưa có dữ liệu nến 15 phút cho {code}. Xem khung D/W/M từ EOD; không tạo nến giả.')
    st.caption('Khung 4H theo quy ước thị trường Việt Nam = 1 phiên giao dịch (~4 giờ khớp lệnh), không phải 2 nến 4H/ngày. ' 
               'Nến D/W/M trong phiên là tạm tính từ dữ liệu 15m đã thu thập, có thể thiếu đầu phiên.')
    summary = pd.DataFrame([latest_row_summary(tf,frames[tf]) for tf in VIEW_TFS])
    st.dataframe(summary,hide_index=True,use_container_width=True)
    item=frames[selected_tf]
    if item['df'].empty:
        st.info('Khung đang chọn chưa có dữ liệu.')
        return
    if show_chart:
        st.plotly_chart(plot_frame(selected_tf,item),use_container_width=True)
    st.caption('Nhãn Tạm tính không phải tín hiệu mua/bán được xác nhận. Các bộ lọc EOD và backtest hiện tại vẫn dùng nến đóng.')
