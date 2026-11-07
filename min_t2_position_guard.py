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


# MIN_T2_GUARD_THREE_SECTION_UI_V1

# MIN_T2_FLOW_LABELS_V2

def _flow_classification(volume):
    """Two independent EOD descriptions: volume intensity and candle dominance.

    OHLC and volume cannot reveal aggressive buy/sell order-flow. Every
    'mua/bán thắng' label is explicitly a price-candle proxy, not tape data.
    """
    if volume is None:
        return ('Chưa đủ dữ liệu khối lượng', 'Chưa đủ dữ liệu nến', 'Không xác định')
    vr = _num(volume.get('vol_ratio'))
    close = _num(volume.get('close'))
    opened = _num(volume.get('open'))
    prior = _num(volume.get('prev_close'))
    pos = _num(volume.get('close_pos'))
    body = _num(volume.get('body_pct'))
    if not np.isfinite(vr) or vr < 0:
        intensity = 'Chưa đủ dữ liệu khối lượng'
    elif vr >= 1.5:
        intensity = 'Khối lượng mạnh'
    elif vr >= 1.0:
        intensity = 'Khối lượng bình thường/khá'
    else:
        intensity = 'Khối lượng thấp'
    if volume.get('flat_candle'):
        return intensity, 'Nến một giá · Chưa xác định thắng thế', 'Chưa xác nhận'
    if not all(np.isfinite(x) for x in (close, opened, pos, body)) or not 0 <= pos <= 1 or not 0 <= body <= 100:
        return intensity, 'Chưa đủ dữ liệu nến', 'Chưa xác nhận'
    if body < 25 or (0.40 <= pos <= 0.60 and body < 50):
        dominance = 'Hai bên giằng co'
    elif close > opened and pos >= 0.70 and body >= 50:
        dominance = 'Bên mua thắng theo nến'
    elif close < opened and pos <= 0.30 and body >= 50:
        dominance = 'Bên bán thắng theo nến'
    elif close > opened and pos >= 0.60:
        dominance = 'Bên mua chiếm ưu thế về giá'
    elif close < opened and pos <= 0.40:
        dominance = 'Bên bán chiếm ưu thế về giá'
    else:
        dominance = 'Chưa rõ bên thắng thế'
    if (vr >= 1.5 and dominance == 'Bên mua thắng theo nến'
            and np.isfinite(prior) and close > prior):
        combined = 'Lực mua mạnh được xác nhận theo giá–khối lượng'
    elif vr >= 1.5 and dominance == 'Bên bán thắng theo nến' and np.isfinite(prior) and close < prior:
        combined = 'Lực bán mạnh được xác nhận theo giá–khối lượng'
    elif vr >= 1.5:
        combined = 'Giao dịch mạnh nhưng chưa xác nhận bên thắng thế'
    else:
        combined = 'Chưa xác nhận lực mua/bán mạnh theo khối lượng'
    return intensity, dominance, combined


def _position_interpretation(risk, life, latest=None, volume=None):
    """Conditional holding commentary; never assert an actual order execution."""
    risk_status = str(risk.get('status', 'CHƯA ĐỦ DỮ LIỆU'))
    lifecycle = str(life.get('status', 'CHƯA ĐỦ DỮ LIỆU'))
    if lifecycle == 'CHƯA ĐỦ DỮ LIỆU':
        return ('Không đủ lịch sử để xác nhận kết quả tín hiệu gốc; đối chiếu dữ liệu trước khi quyết định.')
    if lifecycle.startswith('CHẠM CẢ CẮT LỖ VÀ TP'):
        return ('Cùng phiên chạm cắt lỗ và TP gốc; OHLC không cho biết thứ tự. '
                'Không suy ra kết quả khớp lệnh.')
    if lifecycle == 'ĐÃ CHẠM CẮT LỖ GỐC':
        return ('Đã vi phạm mức cắt lỗ gốc theo High–Low lịch sử. Nếu còn nắm giữ, '
                'ưu tiên quản trị rủi ro, không coi TP phía trên là tín hiệu mua mới.')
    if risk_status in ('BÁN / HẠ TỶ TRỌNG', 'CẢNH BÁO BÁN'):
        return ('Đang có cảnh báo bán EOD. Nếu còn nắm giữ, ưu tiên bảo vệ thành quả '
                'và rà soát mức dừng, không mặc định chờ TP tiếp theo.')
    if risk_status == 'SUY YẾU':
        return ('Xu hướng EOD suy yếu. Nếu còn nắm giữ, theo dõi MA20/EMA20 và mức dừng '
                'trước khi quyết định tiếp tục chờ TP.')
    if risk_status != 'THEO DÕI GIỮ':
        return 'Chưa có đủ bằng chứng về xu hướng kỹ thuật để đánh giá giữ/chốt lời.'
    intensity, dominance, combined = _flow_classification(volume)
    if lifecycle in ('ĐÃ CHẠM TP1 GỐC', 'ĐÃ CHẠM TP2 GỐC'):
        tp1 = _num(latest.get('Mục tiêu 1')) if latest is not None else np.nan
        tp2 = _num(latest.get('Mục tiêu 2')) if latest is not None else np.nan
        price = _num(risk.get('price'))
        future = []
        if np.isfinite(price):
            if np.isfinite(tp1) and tp1 > price:
                future.append(f'TP1 động {tp1:.2f}')
            if np.isfinite(tp2) and tp2 > price:
                future.append(f'TP2 động {tp2:.2f}')
        label = 'Đã đạt mục tiêu gốc theo High–Low. ' + combined + '. '
        if not future:
            return label + ('Chưa có TP động hợp lệ phía trên EOD; nếu còn nắm giữ, '
                            'ưu tiên kế hoạch thoát và mức dừng hiệu lực.')
        return (label + 'Nếu vẫn nắm giữ, có thể theo dõi mục tiêu tiếp theo: '
                + ', '.join(future) + '. Luôn đối chiếu cản gần và mức dừng; '
                'không khẳng định lực mua chủ động, không suy ra lệnh đã khớp.')
    return ('Chưa có cảnh báo bán theo MA20 hiện tại. ' + combined
            + '. Nếu còn nắm giữ, theo dõi xu hướng, hỗ trợ và mức dừng hiệu lực.')

def render_guard(context, viewed, daily):
    import streamlit as st
    code = str(context.get('code', '')).upper()
    selected = viewed[viewed['Mã'] == code].sort_values('Ngày tín hiệu', ascending=False)
    if selected.empty:
        return
    risk = exit_condition(daily, code, context['asof'])
    latest = selected.iloc[0]
    life = signal_lifecycle(daily, latest, context['asof'])
    with st.container(border=True):
        st.markdown('**QUẢN TRỊ VỊ THẾ T+ · CẢNH BÁO BÁN / CHỐT LỜI (EOD)**')
        st.markdown('**1. XU HƯỚNG KỸ THUẬT HIỆN TẠI**')
        if 'price' in risk:
            a, b, c = st.columns(3)
            a.metric('Giá EOD', f"{risk['price']:.2f}")
            b.metric('MA20 ngày', f"{risk['ma20']:.2f}")
            c.metric('EMA20 ngày', f"{risk['ema20']:.2f}" if np.isfinite(risk['ema20']) else '—')
        st.write('Trạng thái kỹ thuật EOD:', risk['status'])
        st.caption(risk['reason'])
        st.caption('Chỉ nhận xét xu hướng giá hiện tại; không khẳng định có vị thế và không tự phát lệnh bán.')

        st.markdown('**2. KẾT QUẢ TÍN HIỆU MUA GỐC**')
        st.write('Ngày tín hiệu:', f"{pd.Timestamp(latest['Ngày tín hiệu']):%d/%m/%Y}")
        st.write('Kết quả kiểm tra High–Low:', life['status'])
        if life['date'] is not None:
            st.caption(f"Ngày ghi nhận: {pd.Timestamp(life['date']):%d/%m/%Y} · {life['note']}")
        else:
            st.caption(life['note'])
        # Explicitly distinguish original targets from the displayed, dynamic targets.
        orig_tp1 = _num(latest.get('TP1 gốc', latest.get('Mục tiêu 1')))
        orig_tp2 = _num(latest.get('TP2 gốc', latest.get('Mục tiêu 2')))
        dyn_tp1 = _num(latest.get('Mục tiêu 1'))
        dyn_tp2 = _num(latest.get('Mục tiêu 2'))
        fmt = lambda n: f'{n:.2f}' if np.isfinite(n) else '—'
        st.caption('Mục tiêu GỐC: TP1 ' + fmt(orig_tp1) + ' · TP2 ' + fmt(orig_tp2)
                   + ' | Mục tiêu đang HIỂN THỊ: TP1 ' + fmt(dyn_tp1) + ' · TP2 ' + fmt(dyn_tp2)
                   + '. Kiểm tra lịch sử chỉ dùng mức gốc.')

        # MIN_T2_COLORED_HOLDING_V1
        # Preserve the existing risk/lifecycle/volume rules; change presentation only.
        from html import escape as _escape_html
        from min_three_tab_context import _eod_volume_context
        eod_volume = _eod_volume_context(daily, code, context['asof'])
        if eod_volume is not None and ('price' not in risk or
                abs(float(eod_volume['close']) - float(risk['price'])) > 0.011):
            eod_volume = None
        intensity, dominance, combined = _flow_classification(eod_volume)
        commentary = _position_interpretation(risk, life, latest, eod_volume)
        # Priority: missing/ambiguous and stop/bearish are never promoted as "hold for TP".
        lifecycle_status = str(life.get('status', 'CHƯA ĐỦ DỮ LIỆU'))
        risk_status = str(risk.get('status', 'CHƯA ĐỦ DỮ LIỆU'))
        red = (lifecycle_status == 'ĐÃ CHẠM CẮT LỖ GỐC' or
               risk_status in ('BÁN / HẠ TỶ TRỌNG', 'CẢNH BÁO BÁN'))
        uncertain = (lifecycle_status == 'CHƯA ĐỦ DỮ LIỆU' or
                     lifecycle_status.startswith('CHẠM CẢ CẮT LỖ VÀ TP'))
        amber = (risk_status == 'SUY YẾU' or dominance == 'Hai bên giằng co' or
                 combined == 'Giao dịch mạnh nhưng chưa xác nhận bên thắng thế')
        bullish = (combined == 'Lực mua mạnh được xác nhận theo giá–khối lượng' and
                   risk_status == 'THEO DÕI GIỮ')
        if red:
            palette = ('#3A2025', '#B85A68', '#FFACB5', 'ƯU TIÊN QUẢN TRỊ RỦI RO')
        elif uncertain:
            palette = ('#252C31', '#748995', '#D1DCE2', 'CẦN XÁC MINH DỮ LIỆU')
        elif amber:
            palette = ('#372B1A', '#B58A43', '#FFD18A', 'THEO DÕI THẬN TRỌNG')
        elif bullish:
            palette = ('#17352B', '#438D69', '#A0EAC0', 'THEO DÕI MỤC TIÊU')
        else:
            palette = ('#24312C', '#587769', '#D0E7DB', 'THEO DÕI VỊ THẾ')
        bg, outline, accent, headline = palette
        safe = lambda value: _escape_html(str(value), quote=True)
        # Goal chips are informational and only shown if genuinely above latest EOD.
        goal_html = ''
        if (not red and not uncertain and risk_status == 'THEO DÕI GIỮ' and
                lifecycle_status in ('ĐÃ CHẠM TP1 GỐC', 'ĐÃ CHẠM TP2 GỐC')):
            current_price = _num(risk.get('price'))
            candidates = []
            for name, field in (('TP1 ĐỘNG', 'Mục tiêu 1'), ('TP2 ĐỘNG', 'Mục tiêu 2')):
                target = _num(latest.get(field))
                if np.isfinite(current_price) and np.isfinite(target) and target > current_price:
                    candidates.append((name, target))
            if candidates:
                goal_html = '<div style="display:flex;flex-wrap:wrap;gap:12px;margin:12px 0 2px">' + ''.join(
                    '<div style="min-width:124px;padding:9px 13px;border:1px solid '+outline+';'
                    'border-radius:8px;background:rgba(255,255,255,.035)">'
                    '<div style="font-size:11px;letter-spacing:.04em;opacity:.85">'+safe(name)+'</div>'
                    '<div style="font-size:21px;font-weight:700;color:'+accent+'">'+f'{price:.2f}'+'</div></div>'
                    for name, price in candidates) + '</div>'
        # MIN_T2_HOLDING_HIERARCHY_V1: presentation only; retain calculation rules above.
        # Concise badges let readers scan volume and candle dominance first.
        # The decision headline is the visual focus, not the data labels.
        decision = headline
        if red:
            decision = 'Ưu tiên quản trị rủi ro'
        elif uncertain:
            decision = 'Cần xác minh tín hiệu gốc'
        elif amber:
            decision = 'Theo dõi thận trọng'
        elif bullish:
            decision = 'Theo dõi mục tiêu tiếp theo' if goal_html else 'Theo dõi vị thế'
        elif goal_html:
            decision = 'Theo dõi mục tiêu tiếp theo'
        else:
            decision = 'Theo dõi vị thế'
        # Reuse escaped strings and existing semantic color palette.
        html = (
            '<section style="box-sizing:border-box;width:100%;max-width:950px;background:'+bg+';'
            'border:1px solid '+outline+';border-left:4px solid '+outline+';'
            'border-radius:11px;padding:clamp(12px,2vw,20px);margin:10px 0 12px;'
            'color:#F0F4F1;font-size:14px;line-height:1.6;overflow-wrap:anywhere">'
            '<div style="color:'+accent+';font-size:12px;font-weight:700;'
            'letter-spacing:.04em;margin-bottom:8px">03 / LƯU Ý NẾU VẪN ĐANG NẮM GIỮ</div>'
            '<div style="font-size:clamp(18px,2.2vw,23px);line-height:1.3;'
            'font-weight:750;letter-spacing:-.015em;margin-bottom:12px">'+safe(decision)+'</div>'
            '<div style="display:flex;flex-wrap:wrap;gap:7px;margin-bottom:10px">'
            '<span style="display:inline-block;max-width:100%;padding:4px 10px;'
            'border:1px solid '+outline+';border-radius:8px;'
            'background:rgba(255,255,255,.045);font-size:13px">'
            '<b>Khối lượng:</b> '+safe(intensity)+'</span>'
            '<span style="display:inline-block;max-width:100%;padding:4px 10px;'
            'border:1px solid '+outline+';border-radius:8px;'
            'background:rgba(255,255,255,.045);font-size:13px">'
            '<b>Ưu thế nến:</b> '+safe(dominance)+'</span></div>'
            '<div style="color:#D3DFD7;font-size:13px;line-height:1.55">'
            '<b>Xác nhận giá–khối lượng:</b> '+safe(combined)+'</div>'
            +goal_html+
            '<p style="margin:12px 0 0;font-size:14px;line-height:1.7;'
            'max-width:850px">'+safe(commentary)+'</p>'
            '</section>'
        )
        st.markdown(html, unsafe_allow_html=True)
        st.caption('Không có dữ liệu tài khoản, giá vốn, khối lượng nắm giữ hoặc lệnh đã khớp. '
                   'Chạm ngưỡng bằng High–Low EOD không có nghĩa lệnh đã được thực hiện; '
                   'cảnh báo kỹ thuật hiện tại độc lập với kết quả tín hiệu gốc. '
                   'Chưa mô phỏng đầy đủ cắt lỗ dời động theo từng phiên.')
