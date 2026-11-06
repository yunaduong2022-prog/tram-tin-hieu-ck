"""Read-only EOD exit-risk context for T+2; does not write orders or change signals."""
from __future__ import annotations

import numpy as np
import pandas as pd

COLS = ('Mã', 'Ngày', 'Giá mở cửa', 'Giá cao nhất', 'Giá thấp nhất',
        'Giá đóng cửa', 'Khối lượng khớp lệnh')
BEARISH_PV = {'BREAKDOWN', 'UPTHRUST', 'CLIMAX', 'SELLOFF'}


def _num(value):
    v = pd.to_numeric(value, errors='coerce')
    return float(v) if pd.notna(v) and np.isfinite(float(v)) else np.nan


def prepare_code(daily, code, asof, start=None):
    """EOD bars limited to the data window actually needed.

    Current MA assessment: discard only an invalid *older prefix*; preserve
    every genuine valid observation after the newest invalid candle.
    Signal lifecycle: validate the complete inclusive signal-to-asof window;
    one missing or malformed observation makes the outcome indeterminate.
    Never replace a missing candle, and never make a historical fill claim.
    """
    if daily is None or daily.empty or not set(COLS).issubset(daily.columns):
        return pd.DataFrame()
    asof_day = pd.Timestamp(asof).normalize()
    t = daily.loc[daily['Mã'].astype(str).str.upper().str.strip() == str(code).upper()].copy()
    if t.empty:
        return pd.DataFrame()
    t['Ngày'] = pd.to_datetime(t['Ngày'], errors='coerce').dt.normalize()
    for col in COLS[2:]:
        t[col] = pd.to_numeric(t[col], errors='coerce')
    # Ambiguous duplicates in the requested window cannot establish a unique candle.
    t = t.loc[t['Ngày'].notna() & (t['Ngày'] <= asof_day)].sort_values('Ngày')
    if start is not None:
        start_day = pd.Timestamp(start).normalize()
        t = t.loc[t['Ngày'] >= start_day]
    else:
        start_day = None
    if t.empty or t.iloc[-1]['Ngày'] != asof_day:
        return pd.DataFrame()
    if bool(t['Ngày'].duplicated().any()):
        # Do not silently choose a favorable duplicate OHLC candle.
        if start_day is not None:
            return pd.DataFrame()
        last_duplicate = t.index[t['Ngày'].duplicated(keep=False)][-1]
        t = t.loc[t['Ngày'] > t.loc[last_duplicate, 'Ngày']]
        if t.empty:
            return pd.DataFrame()
    valid = (t[list(COLS[2:])].notna().all(axis=1) &
             (t['Giá thấp nhất'] > 0) &
             (t['Giá cao nhất'] >= t['Giá thấp nhất']) &
             t['Giá mở cửa'].between(t['Giá thấp nhất'], t['Giá cao nhất']) &
             t['Giá đóng cửa'].between(t['Giá thấp nhất'], t['Giá cao nhất']) &
             (t['Khối lượng khớp lệnh'] >= 0))
    if start_day is not None:
        if not bool(valid.all()) or t.iloc[0]['Ngày'] != start_day:
            return pd.DataFrame()
    elif not bool(valid.all()):
        # An old invalid candle must not mask an otherwise valid recent MA20.
        last_bad = t.loc[~valid, 'Ngày'].max()
        t = t.loc[t['Ngày'] > last_bad]
        if t.empty:
            return pd.DataFrame()
    return t.reset_index(drop=True)


def exit_condition(daily, code, asof):
    """MA20 is SMA(20); EMA20 independently computed (not interchangeable)."""
    g = prepare_code(daily, code, asof)
    if len(g) < 21:
        return {'status': 'CHƯA ĐỦ DỮ LIỆU', 'reason': 'Cần 21 phiên EOD hợp lệ để đánh giá MA20 và phiên trước.', 'ma20': np.nan, 'ema20': np.nan}
    c = g['Giá đóng cửa']
    v = g['Khối lượng khớp lệnh']
    ma = c.rolling(20, min_periods=20).mean()
    # Same EMA20 settings as waiting_buy._features, no min_periods.
    ema = c.ewm(span=20, adjust=False).mean() if len(g) >= 60 else None
    price, prev = float(c.iloc[-1]), float(c.iloc[-2])
    m, pm = float(ma.iloc[-1]), float(ma.iloc[-2])
    em, pem = (float(ema.iloc[-1]), float(ema.iloc[-2])) if ema is not None else (np.nan, np.nan)
    vr = float(v.iloc[-1] / v.iloc[-21:-1].mean()) if v.iloc[-21:-1].mean() > 0 else np.nan
    hi, lo = float(g['Giá cao nhất'].iloc[-1]), float(g['Giá thấp nhất'].iloc[-1])
    pos = (price - lo) / (hi - lo) if hi > lo else 0.5
    below = price < m
    first = below and prev >= pm
    twice = below and prev < pm
    # Reuse existing engine alert when present; only when attached to EOD row.
    pv = str(g.iloc[-1].get('PV_code', '') or '').strip().upper()
    # Original frame may contain PV_code from engine; prepare_code retains extra columns.
    bearish_pv = pv in BEARISH_PV
    # Stop/position management is evaluated separately from the current MA warning.
    if bearish_pv:
        status, reason = 'CẢNH BÁO BÁN', f'Engine EOD: {pv}; cần đánh giá giảm/hạ tỷ trọng.'
    elif first and np.isfinite(vr) and vr >= 1.2 and pos <= .35:
        status, reason = 'BÁN / HẠ TỶ TRỌNG', 'Đóng dưới MA20 lần đầu, Vol/TB20 ≥1.2x, Position ≤35%.'
    elif twice:
        status, reason = 'CẢNH BÁO BÁN', 'Giá đóng dưới MA20 ít nhất hai phiên liên tiếp; kiểm tra vị thế.'
    elif first:
        status, reason = 'SUY YẾU', 'Giá vừa đóng xuống dưới MA20; chưa đủ xác nhận bán theo khối lượng và nến.'
    elif below:
        status, reason = 'SUY YẾU', 'Giá đang dưới MA20; cần theo dõi lực cầu và mức cắt lỗ.'
    else:
        status, reason = 'THEO DÕI GIỮ', 'Giá chưa đóng dưới MA20; không có cảnh báo bán theo điều kiện MA20 hiện tại.'
    if np.isfinite(em) and price < em:
        reason += ' Giá dưới EMA20.'
    elif not np.isfinite(em):
        reason += ' EMA20 chưa đủ 60 phiên liên tục sau nến lỗi để khởi tạo đáng tin cậy.'
    return {'status': status, 'reason': reason, 'ma20': m, 'ema20': em,
            'prev_ma20': pm, 'prev_ema20': pem, 'price': price,
            'vol_ratio': vr, 'position': pos * 100, 'pv_code': pv,
            'asof': g.iloc[-1]['Ngày']}


def signal_lifecycle(daily, signal, asof):
    """Historical EOD touch detection for ORIGINAL stop/TP; no fills inferred.

    Start checking the bar after the signal. If a bar touches both stop and
    TP, the intraday order is unknown: prioritize conservative stop status.
    Never treat raised dynamic stop as if active since the signal day.
    """
    code = str(signal.get('Mã', '')).upper()
    dt = pd.to_datetime(signal.get('Ngày tín hiệu'), errors='coerce')
    if pd.isna(dt):
        return {'status': 'CHƯA ĐỦ DỮ LIỆU', 'note': 'Ngày tín hiệu không hợp lệ.', 'date': None}
    g = prepare_code(daily, code, asof, start=dt)
    if g.empty:
        return {'status': 'CHƯA ĐỦ DỮ LIỆU', 'note': 'Không xác minh được lịch sử EOD của tín hiệu.', 'date': None}
    dt = pd.Timestamp(dt).normalize()
    # Missing ticker bars on market trading days may conceal stop/TP touches.
    # Suspension/no-trading and a missing data feed cannot be distinguished here.
    market_days = pd.to_datetime(daily['Ngày'], errors='coerce').dt.normalize()
    market_days = set(market_days.loc[(market_days >= dt) &
                                     (market_days <= pd.Timestamp(asof).normalize())].dropna())
    symbol_days = set(g['Ngày'])
    if market_days - symbol_days:
        return {'status': 'CHƯA ĐỦ DỮ LIỆU',
                'note': 'Có phiên thị trường thiếu OHLC của mã trong giai đoạn từ tín hiệu; không suy ra chạm cắt lỗ/TP.',
                'date': None}
    ids = g.index[g['Ngày'] == dt].tolist()
    if len(ids) != 1:
        return {'status': 'CHƯA ĐỦ DỮ LIỆU', 'note': 'Không tìm thấy đúng một nến của ngày tín hiệu.', 'date': None}
    i = ids[0]
    stop = _num(signal.get('Cắt lỗ gốc', signal.get('Cắt lỗ tham khảo')))
    tp1 = _num(signal.get('TP1 gốc', signal.get('Mục tiêu 1')))
    tp2 = _num(signal.get('TP2 gốc', signal.get('Mục tiêu 2')))
    entry = _num(signal.get('Giá tín hiệu'))
    if not np.isfinite(stop) or not np.isfinite(entry) or not 0 < stop < entry:
        return {'status': 'CHƯA ĐỦ DỮ LIỆU', 'note': 'Thiếu giá tín hiệu hoặc cắt lỗ gốc hợp lệ.', 'date': None}
    tp1_seen = None
    for j in range(i + 1, len(g)):
        candle = g.iloc[j]
        low, high = float(candle['Giá thấp nhất']), float(candle['Giá cao nhất'])
        touched_stop = low <= stop
        touched_tp1 = np.isfinite(tp1) and high >= tp1
        touched_tp2 = np.isfinite(tp2) and high >= tp2
        if touched_stop and (touched_tp1 or touched_tp2):
            return {'status': 'CHẠM CẢ CẮT LỖ VÀ TP TRONG CÙNG PHIÊN',
                    'note': 'Không xác định thứ tự chạm trong phiên từ OHLC; không suy ra giao dịch đã khớp.',
                    'date': candle['Ngày']}
        if touched_stop:
            prior_tp = ' Đã từng chạm TP1 gốc trước đó.' if tp1_seen is not None else ''
            return {'status': 'ĐÃ CHẠM CẮT LỖ GỐC',
                    'note': f'Low EOD {low:.2f} ≤ cắt lỗ gốc {stop:.2f}.' + prior_tp + ' Không suy ra đã khớp lệnh.',
                    'date': candle['Ngày']}
        if touched_tp2:
            return {'status': 'ĐÃ CHẠM TP2 GỐC',
                    'note': 'High EOD chạm TP2 gốc; chưa tính phí hoặc khả năng khớp.', 'date': candle['Ngày']}
        if touched_tp1 and tp1_seen is None:
            tp1_seen = candle['Ngày']
    if tp1_seen is not None:
        return {'status': 'ĐÃ CHẠM TP1 GỐC', 'note': 'High EOD từng chạm TP1 gốc; chưa có bằng chứng chạm TP2/cắt lỗ gốc sau đó.', 'date': tp1_seen}
    return {'status': 'CHƯA CHẠM CẮT LỖ/TP GỐC',
            'note': 'Chỉ kiểm tra các mức gốc từ phiên sau tín hiệu; không kiểm tra stop dời động.',
            'date': None}


def render_guard(context, viewed, daily):
    import streamlit as st
    code = str(context.get('code', '')).upper()
    selected = viewed[viewed['Mã'] == code].sort_values('Ngày tín hiệu', ascending=False)
    if selected.empty:
        return
    risk = exit_condition(daily, code, context['asof'])
    with st.container(border=True):
        st.markdown('**QUẢN TRỊ VỊ THẾ T+ · CẢNH BÁO BÁN / CHỐT LỜI (EOD)**')
        if 'price' in risk:
            a,b,c = st.columns(3)
            a.metric('Giá EOD', f"{risk['price']:.2f}")
            b.metric('MA20 ngày', f"{risk['ma20']:.2f}")
            c.metric('EMA20 ngày', f"{risk['ema20']:.2f}" if np.isfinite(risk['ema20']) else '—')
        st.write('Cảnh báo kỹ thuật hiện tại:', risk['status'])
        st.caption(risk['reason'])
        latest = selected.iloc[0]
        life = signal_lifecycle(daily, latest, context['asof'])
        st.write('Tín hiệu mua gần nhất:', f"{pd.Timestamp(latest['Ngày tín hiệu']):%d/%m/%Y}", '·', life['status'])
        if life['date'] is not None:
            st.caption(f"Ngày ghi nhận: {pd.Timestamp(life['date']):%d/%m/%Y} · {life['note']}")
        else:
            st.caption(life['note'])
        # For past events, historical RR is NOT actionable from today's EOD.
        st.caption('Kiểm tra chạm cắt lỗ/TP dùng High–Low EOD từng phiên sau tín hiệu và các mức GỐC. '
                   'Không suy ra lệnh đã khớp, không dùng R:R lịch sử làm R:R mua mới. '
                   'Cảnh báo MA20 và EMA20 là tín hiệu kỹ thuật quan sát, không phải lệnh bán tự động.')
