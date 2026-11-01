"""EOD confirmations and clearly separated 15-minute observation layer.

This module has NO data fetch, no writes, and changes no existing trade signal,
indicator, ranking, cache, recommendation or backtest computation.

EOD is authoritative for trading signals. Intraday is an *observational* overlay:
latest valid, fully closed 15m candle, session freshness and reference to a
previous *confirmed* EOD day. Neither touches canonical EOD prices.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
import math
import pandas as pd

EOD_ONLY = frozenset({'Mua ngay', 'Lọc tất cả CP', 'Backtest chiến lược'})
INTRADAY_FIRST = frozenset({'Bộ lọc Realtime', 'Giảm mạnh', 'Danh sách cảnh báo'})
HYBRID = frozenset({'Chờ mua','Tăng mạnh','Cạn cung','Đang phục hồi',
                    'Watchlist','Cổ phiếu của tôi','Khuyến nghị khách hàng','Bán / Chốt lời'})
OVERLAY_TABLE = frozenset({'Chờ mua','Tăng mạnh','Cạn cung','Đang phục hồi',
                           'Watchlist','Cổ phiếu của tôi','Bán / Chốt lời',
                           'Bộ lọc Realtime','Giảm mạnh','Danh sách cảnh báo'})
COLS = ('symbol','time','open','high','low','close','volume','source')
VN_TZ = 'Asia/Ho_Chi_Minh'


def bucket(main: str, sub: str) -> str:
    if main == 'Bộ lọc & Backtest':
        if sub in EOD_ONLY: return 'EOD'
        if sub in INTRADAY_FIRST: return 'INTRADAY_ALERT'
        if sub in HYBRID: return 'EOD_PLUS_15M'
        return 'EOD'
    if main == 'Vĩ mô': return 'MACRO'
    if main in ('Thị trường','Ngành','Cổ phiếu','Livestream'): return 'EOD_PLUS_15M'
    return 'EOD'


def _vn_naive(now=None) -> pd.Timestamp:
    ts = pd.Timestamp.now(tz=VN_TZ) if now is None else pd.Timestamp(now)
    if ts.tzinfo is not None:
        return ts.tz_convert(VN_TZ).tz_localize(None)
    return ts


def _business_day_before(date):
    date = pd.Timestamp(date).normalize() - pd.Timedelta(days=1)
    while date.dayofweek >= 5:
        date -= pd.Timedelta(days=1)
    return date


def expected_session(now=None):
    """Expected last *active* trading date; does not model exchange holidays.

    Before 09:15 on trading days, expect previous weekday's last candle.
    During/after the session expect today's closed bars. Holidays may be marked
    'not updated' rather than silently reusing old prices as current.
    """
    now = _vn_naive(now)
    day = now.normalize()
    if day.dayofweek >= 5 or (now.hour,now.minute) < (9,15):
        return _business_day_before(day) if day.dayofweek < 5 else _business_day_before(day + pd.Timedelta(days=1))
    return day


def _parse_15m_time(series):
    """Collector timestamps are ISO with timezone; reject timezone-naive records.

    Naive timestamps could silently shift bar times when passed through the
    older UTC normalizer. These should not generate trading alerts.
    """
    strings = series.astype(str)
    ok = strings.str.contains(r'(?:Z|[+-]\d{2}:?\d{2})$', regex=True, case=False)
    dt = pd.to_datetime(strings.where(ok), errors='coerce', utc=True)
    return dt.dt.tz_convert(VN_TZ).dt.tz_localize(None)


def clean_intraday(bars: pd.DataFrame, now=None) -> pd.DataFrame:
    """Accept only valid, completed 15m bars in VN session; deduplicate symbol-time.

    The source timestamps mark the **beginning** of a 15-minute candle.
    """
    if bars is None or bars.empty or not set(COLS).issubset(bars):
        return pd.DataFrame(columns=[*COLS, 'closed_at'])
    now = _vn_naive(now)
    b = bars[list(COLS)].copy()
    b['symbol'] = b['symbol'].astype(str).str.upper().str.strip()
    b['time'] = _parse_15m_time(b['time'])
    for field in ('open','high','low','close','volume'):
        b[field] = pd.to_numeric(b[field], errors='coerce')
    b = b.dropna(subset=['time','open','high','low','close','volume'])
    if b.empty: return pd.DataFrame(columns=[*COLS,'closed_at'])
    tm = b['time'].dt.strftime('%H:%M')
    # Excluding 11:30--13:00 lunch and after 14:45, including the closing 14:45 bar.
    session_ok = ((tm >= '09:00') & (tm < '11:30')) | ((tm >= '13:00') & (tm <= '14:45'))
    b = b[session_ok & (b['low'] > 0) & (b['volume'] >= 0) &
          (b['high'] >= b[['open','close','low']].max(axis=1)) &
          (b['low'] <= b[['open','close','high']].min(axis=1))].copy()
    if b.empty: return pd.DataFrame(columns=[*COLS,'closed_at'])
    b['closed_at'] = b['time'] + pd.Timedelta(minutes=15)
    b = b[b['closed_at'] <= now]
    b = b.sort_values(['symbol','time']).drop_duplicates(['symbol','time'],keep='last')
    return b.reset_index(drop=True)


def _reference_day_prices(eod: pd.DataFrame, intraday_days: dict) -> tuple[dict,dict,dict]:
    """Reference is last EOD candle strictly earlier than intraday date.

    Never compare a Friday 15m close to the same Friday's EOD close and label
    0% 'change today'.
    """
    prices,ma20,ma50 = {},{},{}
    if eod is None or eod.empty or not {'Mã','Ngày','Giá đóng cửa'}.issubset(eod):
        return prices,ma20,ma50
    d=eod.copy()
    d['Mã'] = d['Mã'].astype(str).str.upper().str.strip()
    d['Ngày'] = pd.to_datetime(d['Ngày'],errors='coerce').dt.normalize()
    for k in ('Giá đóng cửa','MA20','MA50'):
        if k in d: d[k] = pd.to_numeric(d[k],errors='coerce')
    d=d.dropna(subset=['Ngày','Giá đóng cửa'])
    d=d.sort_values(['Mã','Ngày']).drop_duplicates(['Mã','Ngày'],keep='last')
    for symbol,g in d.groupby('Mã',sort=False):
        asof=intraday_days.get(symbol)
        if asof is None: continue
        ref=g[g['Ngày'] < asof]
        # If a new intraday day appears after last EOD, use the last EOD close.
        if ref.empty: continue
        prices[symbol]=float(ref['Giá đóng cửa'].iloc[-1])
        # MA indicators are last confirmed day before intraday day.
        for field,container in [('MA20',ma20),('MA50',ma50)]:
            if field in ref:
                x=ref[field].iloc[-1]
                if pd.notna(x) and math.isfinite(float(x)):container[symbol]=float(x)
    return prices,ma20,ma50


def make_snapshot(bars: pd.DataFrame, eod: pd.DataFrame, now=None) -> pd.DataFrame:
    """Pure calculation. Only closed candles, only expected current exchange session.

    This intentionally does not produce EOD buy/sell orders or overwrite scores.
    """
    cleaned = clean_intraday(bars,now=now)
    columns=['Mã','Nến 15m đóng lúc','Giá 15m','Thay đổi từ EOD trước (%)',
             'KL 15m / TB10','Theo dõi Intraday','Tình trạng']
    if cleaned.empty:return pd.DataFrame(columns=columns)
    exp=expected_session(now)
    close=cleaned.groupby('symbol',sort=False).tail(1).copy()
    close=close[close['time'].dt.normalize()==exp]
    if close.empty:return pd.DataFrame(columns=columns)
    intraday_days={r['symbol']:r['time'].normalize() for _,r in close.iterrows()}
    prev,ma20,ma50=_reference_day_prices(eod,intraday_days)
    vol_ratio={}
    for sym,g in cleaned.groupby('symbol',sort=False):
        valid=g[g['time'].dt.normalize()==exp].sort_values('time')
        if len(valid)<11:continue
        avg=float(valid['volume'].iloc[-11:-1].mean())
        if avg>0:vol_ratio[sym]=float(valid['volume'].iloc[-1])/avg
    out=[]
    for _,r in close.iterrows():
        sym=r['symbol'];px=float(r['close']);base=prev.get(sym)
        pct=100*(px/base-1) if base and base>0 else None
        vr=vol_ratio.get(sym)
        flags=[]
        if pct is not None and pct<=-3:flags.append('Giảm ≥3%')
        if pct is not None and pct>=3:flags.append('Tăng ≥3%')
        if vr is not None and vr>=2:flags.append('KL 15m ≥2× TB10')
        if ma20.get(sym) and px < ma20[sym]:flags.append('Dưới MA20 D')
        if ma50.get(sym) and px < ma50[sym]:flags.append('Dưới MA50 D')
        out.append({'Mã':sym,'Nến 15m đóng lúc':pd.Timestamp(r['closed_at']).strftime('%d/%m/%Y %H:%M'),
                    'Giá 15m':px,'Thay đổi từ EOD trước (%)':round(pct,2) if pct is not None else float('nan'),
                    'KL 15m / TB10':round(vr,2) if vr is not None else float('nan'),
                    'Theo dõi Intraday':', '.join(flags) if flags else 'Không có điều kiện theo dõi',
                    'Tình trạng':'Đã đóng 15m · không phải tín hiệu EOD'})
    return pd.DataFrame(out,columns=columns)


def select_rows(snapshot, sub, watchlist=None, portfolio=None):
    """Only select observational data; never modify existing EOD classification."""
    if snapshot is None or snapshot.empty:return snapshot
    s=snapshot.copy()
    c='Thay đổi từ EOD trước (%)'
    if sub in ('Watchlist','Cổ phiếu của tôi'):
        allow = set(watchlist if sub=='Watchlist' else portfolio or [])
        return s[s['Mã'].isin(allow)].sort_values(c,ascending=True).head(30) if allow else s.iloc[0:0]
    if sub == 'Tăng mạnh':return s[s[c] >= 3].sort_values(c,ascending=False).head(30)
    if sub == 'Giảm mạnh':return s[s[c] <= -3].sort_values(c).head(30)
    if sub in ('Bán / Chốt lời','Danh sách cảnh báo'):
        mask=s['Theo dõi Intraday'].str.contains(r'Giảm ≥3%|Dưới MA20 D|Dưới MA50 D|SL cá nhân|mục tiêu cá nhân',regex=True)
        return s[mask].sort_values(c).head(30)
    if sub == 'Cạn cung':
        # Only low 15m turnover, not an EOD Wyckoff confirmation.
        return s[(s['KL 15m / TB10']<=0.6) & (s[c].abs()<=2)].sort_values('KL 15m / TB10').head(20)
    if sub == 'Đang phục hồi':
        # Positive intraday observation, not a new confirmed EOD classification.
        return s[s[c]>=1].sort_values(c,ascending=False).head(20)
    if sub == 'Chờ mua':
        return s[s[c].notna()].sort_values(c,ascending=True).head(20)
    return s.sort_values(c,ascending=False,na_position='last').head(30)


def annotate_personal_levels(snapshot: pd.DataFrame, levels: pd.DataFrame) -> pd.DataFrame:
    """Optional 15m-close monitoring of user-entered SL and targets, no orders."""
    if snapshot is None or snapshot.empty or levels is None or levels.empty:
        return snapshot
    if not {'Mã','Cắt lỗ','Mục tiêu'}.issubset(levels):
        return snapshot
    out=snapshot.copy()
    l=levels[['Mã','Cắt lỗ','Mục tiêu']].copy()
    l['Mã']=l['Mã'].astype(str).str.strip().str.upper()
    l['Cắt lỗ']=pd.to_numeric(l['Cắt lỗ'],errors='coerce')
    l['Mục tiêu']=pd.to_numeric(l['Mục tiêu'],errors='coerce')
    l.loc[l['Cắt lỗ']<=0,'Cắt lỗ']=float('nan')
    l.loc[l['Mục tiêu']<=0,'Mục tiêu']=float('nan')
    # For multiple lots: highest stop is first protective stop reached as price falls;
    # lowest take-profit target is first target as price rises.
    per=l.groupby('Mã').agg({'Cắt lỗ':'max','Mục tiêu':'min'})
    for i,row in out.iterrows():
        code=row['Mã'];px=row['Giá 15m']
        if code not in per.index:continue
        stop=per.at[code,'Cắt lỗ'];target=per.at[code,'Mục tiêu']
        extra=[]
        if pd.notna(stop) and px<=stop:extra.append('Đóng 15m dưới SL cá nhân')
        if pd.notna(target) and px>=target:extra.append('Đóng 15m trên mục tiêu cá nhân')
        if extra:
            old=str(out.at[i,'Theo dõi Intraday'])
            if old=='Không có điều kiện theo dõi':old=''
            out.at[i,'Theo dõi Intraday']=', '.join([*([old] if old else []),*extra])
    return out


def _personal_levels(sub):
    try:
        import my_watchlist as MW
        import my_portfolio as MP
        if sub=='Watchlist':return MW.load()
        if sub=='Cổ phiếu của tôi':return MP.load()
        if sub in ('Bán / Chốt lời','Danh sách cảnh báo'):
            return pd.concat([MW.load(),MP.load()],ignore_index=True)
    except (ImportError,ValueError,OSError,KeyError):
        pass
    return pd.DataFrame(columns=['Mã','Cắt lỗ','Mục tiêu'])


def _watched_codes(sub):
    try:
        if sub == 'Watchlist':
            import my_watchlist as MW
            d=MW.load()
        elif sub == 'Cổ phiếu của tôi':
            import my_portfolio as MP
            d=MP.load()
        else:return []
        if 'Mã' in d:
            return d['Mã'].dropna().astype(str).str.upper().unique().tolist()
    except (ImportError,ValueError,OSError,KeyError):
        pass
    return []


def render_page(main, sub, eod_date, eod_daily, allow_intraday=True):
    """Streamlit labels and intraday overlay, invoked once per requested page.

    Does not download prices and does not invoke VNStock.
    """
    import streamlit as st
    policy=bucket(main,sub)
    try:
        stamp=f'{pd.Timestamp(eod_date):%d/%m/%Y}'
    except (TypeError,ValueError):stamp='không rõ'
    if policy=='EOD':
        st.caption(f'✅ **EOD đã xác nhận** · {stamp} · Tín hiệu/bảng xếp hạng/backtest chỉ từ nến ngày đóng.')
    elif policy=='MACRO':
        st.caption('🌐 **Vĩ mô** · Nguồn và lịch công bố riêng; không suy ra từ nến 15 phút.')
    elif policy=='INTRADAY_ALERT':
        st.caption(f'⚠️ **Theo dõi Intraday 15m** · EOD nền: {stamp}. Nến chưa đóng không tạo cảnh báo. Các thẻ EOD cũ vẫn là kết quả cuối phiên.')
    else:
        st.caption(f'✅ **EOD xác nhận:** {stamp}  |  🕒 **Intraday:** cảnh báo tham khảo từ nến 15m đã đóng (nếu có).')
    need_filter = main=='Bộ lọc & Backtest' and sub in OVERLAY_TABLE
    need_market = main in ('Thị trường', 'Ngành', 'Livestream')
    if not need_filter and not need_market:
        return
    if not allow_intraday:
        st.caption('Nguồn Excel đang được chọn: không ghép dữ liệu Intraday của nguồn Windows với Excel.')
        return
    path=Path('data/intraday_15m.csv')
    if not path.is_file():
        st.caption('⚪ Chưa có dữ liệu 15m trên máy chủ này; các kết quả EOD vẫn dùng bình thường.')
        return
    try:
        mtime=path.stat().st_mtime_ns
        eod_file=Path('data/eod_prices.csv')
        eod_sig=eod_file.stat().st_mtime_ns if eod_file.is_file() else -1
        @st.cache_data(show_spinner=False,max_entries=3,ttl=120)
        def _snapshot_cached(file_name, intraday_sig, daily_sig, _eod_daily):
            raw=pd.read_csv(file_name,dtype={'symbol':str,'time':str},usecols=list(COLS))
            return make_snapshot(raw,_eod_daily)
        snap=_snapshot_cached(str(path),mtime,eod_sig,eod_daily)
    except (OSError,ValueError,KeyError,pd.errors.ParserError) as exc:
        st.warning(f'Không đọc được dữ liệu Intraday: {type(exc).__name__}. Bộ lọc EOD vẫn hoạt động.')
        return
    if snap.empty:
        st.info('Chưa có nến 15 phút đã đóng của phiên dự kiến trên R2/Windows. Không phát cảnh báo Intraday từ dữ liệu cũ.')
        return
    if need_market:
        if main=='Thị trường':
            change=snap['Thay đổi từ EOD trước (%)'].dropna()
            st.caption(f'📡 Theo dõi 15m (chỉ mẫu mã đã cập nhật): {len(snap)} mã có nến đóng đúng phiên; '
                       f'{int((change>0).sum())} tăng, {int((change<0).sum())} giảm. '
                       'Không thay thế thống kê độ rộng toàn thị trường hoặc VN-Index EOD.')
        elif main=='Ngành':
            try:
                import watchlist as WL
                metric=snap.set_index('Mã')['Thay đổi từ EOD trước (%)']
                results=[]
                for name,codes in WL.GROUPS.items():
                    values=metric.reindex([x for x in codes if x in metric.index]).dropna()
                    if len(values)>=3:
                        results.append({'Ngành':name,'Có nến 15m':len(values),
                                        'Mã trong nhóm':len(codes),'TB % mã có dữ liệu':round(float(values.mean()),2)})
                if results:
                    with st.expander('📡 Quan sát ngành trong phiên · mẫu nến 15m',expanded=False):
                        st.caption('Trung bình giản đơn trên các mã đã có nến 15m; không phải chỉ số ngành hoặc bảng xếp hạng EOD. Nhóm có dưới 3 mã cập nhật không hiển thị.')
                        st.dataframe(pd.DataFrame(results).sort_values('TB % mã có dữ liệu',ascending=False).head(15),hide_index=True,use_container_width=True)
            except (ImportError,KeyError,ValueError):
                pass
        elif main=='Livestream':
            code=str(st.session_state.get('selected_code','')).upper().strip()
            found=snap[snap['Mã']==code]
            if not found.empty:
                z=found.iloc[-1]
                st.caption(f'📡 {code}: 15m đã đóng {z["Nến 15m đóng lúc"]}, giá {z["Giá 15m"]:,.2f}. '
                           'Tín hiệu trên nến D/W vẫn theo EOD đã xác nhận.')
        return
    levels=_personal_levels(sub)
    snap=annotate_personal_levels(snap,levels)
    watched=_watched_codes(sub)
    rows=select_rows(snap,sub,watched,watched)
    with st.expander(f'📡 Theo dõi nến 15m đã đóng · {len(rows)} mã (tham khảo)',expanded=sub in INTRADAY_FIRST or sub in ('Bán / Chốt lời','Cổ phiếu của tôi')):
        st.caption('Không phải tín hiệu Mua ngay/Bán chính thức. So sánh với EOD phiên trước; chỉ nến 15m đã đóng. KL/TB10 là khối lượng so với 10 nến 15m trước trong cùng ngày; SL/mục tiêu cá nhân chỉ được theo dõi nếu đã nhập vào danh sách riêng.')
        if rows.empty:
            st.info('Không có mã thỏa điều kiện theo dõi hoặc danh sách mã cá nhân đang trống.')
        else:
            st.dataframe(rows,hide_index=True,use_container_width=True)
        st.caption('EOD tiếp tục quyết định tín hiệu xác nhận. Dữ liệu Intraday có thể thiếu các mã thanh khoản thấp hoặc những nến chưa được nguồn cập nhật.')
