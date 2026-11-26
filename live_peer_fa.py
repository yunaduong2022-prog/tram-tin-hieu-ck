"""Display-only FA for the Livestream RS peer table; reuse the existing FA engine."""
from math import isfinite
import pandas as pd


def fa_cell(value, scale=100, reference=False):
    try:
        value = float(value)
        if scale not in (85, 100) or not isfinite(value) or not 0 <= value <= scale:
            return '—'
    except (TypeError, ValueError, OverflowError):
        return '—'
    number = f'{value:.2f}'.rstrip('0').rstrip('.')
    return f'{number}/{scale}' + ('*' if reference else '')


def make_lookup(frames_d, fundamentals, asof, *, st=None, vip=None):
    if vip is None:
        import vip_picks as vip
    import bank_fa
    import port_fa
    import bds_fa
    import ck_fa
    cache = {}
    bank_data = None
    bank_loaded = False
    bank_prices = {}
    expected = pd.to_datetime(asof, errors='coerce')
    def lookup(symbol):
        nonlocal bank_data, bank_loaded, bank_prices
        code = str(symbol).strip().upper()
        if code in cache:
            return cache[code]
        try:
            daily = frames_d.loc[frames_d['Mã'].astype(str).str.upper().eq(code), ['Ngày', 'Giá đóng cửa']].copy()
            daily['Ngày'] = pd.to_datetime(daily['Ngày'], errors='coerce')
            daily = daily.dropna(subset=['Ngày']).sort_values('Ngày')
            day = daily['Ngày'].iat[-1] if len(daily) else None
            close = daily['Giá đóng cửa'].iat[-1] if len(daily) else None
            # Match the existing scoring entry point, with the symbol's own EOD date.
            fa, tags, bank = vip.fa_score_for_symbol(code, (fundamentals or {}).get(code, {}) or {}, price_k=close, price_date=day, asof=asof)
            reference = code in (port_fa.SYMBOLS | bds_fa.SYMBOLS | ck_fa.SYMBOLS)
            scale = 100
            if bank is not None and fa is None and st is not None:
                import bank_web_review as review
                if not bank_loaded:
                    bank_loaded = True
                    try:
                        config = st.secrets.get('bank_fixed_v2')
                    except (FileNotFoundError, KeyError):
                        config = None
                    bank_data = review.fixed_rows(config) if config is not None else st.session_state.get(review.STATE)
                    bank_prices = review.current_prices(frames_d, asof)
                if bank_data and code in bank_data:
                    result = review.score(bank_data[code], *bank_prices.get(code, (None, None, False)))
                    fa = result.get('FA tham khảo /100')
                    if fa is None:
                        fa = result.get('Tài chính /85')
                        scale = 85
                    reference = True
            # Even general financial scores are not real-time prices; stale EOD is explicit.
            if day is None or pd.isna(expected) or day.date() != expected.date():
                reference = True
            cache[code] = fa_cell(fa, scale, reference)
        except Exception:
            # A single unavailable FA must never hide the RS table.
            cache[code] = '—'
        return cache[code]
    return lookup
