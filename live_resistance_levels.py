"""Transparent price-level labels for the Livestream tab (no trading decisions).

Three independent concepts:
- Previous 20 daily bars high (Resistance_20, EXCLUDES current daily bar).
- Long-term Ichimoku-2 Kijun (129 days; uses exactly the chart's Donchian formula).
- Hypothetical +15% PRICE scenario (NOT technical resistance or a price target).

The page must never claim that an invented percentage price is chart resistance.
"""
from __future__ import annotations

import math

import pandas as pd


def _finite_positive(value):
    try:
        n = float(value)
    except (ValueError, TypeError, OverflowError):
        return None
    return n if math.isfinite(n) and n > 0 else None


def _last_valid(g, field):
    if g is None or getattr(g, 'empty', True) or field not in g:
        return None
    return _finite_positive(g[field].iloc[-1])


def _kijun_period():
    # Keep this synced to Ichimoku 2 on the daily price chart; no hardwired price.
    from ichimoku_dual import CFG
    n = int(CFG['k2'])
    if n < 2:
        raise ValueError('Invalid Ichimoku Kijun setting')
    return n


def _kijun_long(g):
    if g is None or getattr(g, 'empty', True):
        return None
    n = _kijun_period()
    if len(g) < n or not {'Giá cao nhất', 'Giá thấp nhất'}.issubset(g.columns):
        return None
    highs = pd.to_numeric(g['Giá cao nhất'].iloc[-n:], errors='coerce')
    lows = pd.to_numeric(g['Giá thấp nhất'].iloc[-n:], errors='coerce')
    if not (highs.notna().all() and lows.notna().all()):
        return None
    if not (highs.map(math.isfinite).all() and lows.map(math.isfinite).all()):
        return None
    return _finite_positive((highs.max() + lows.min()) / 2)


def _fmt(n):
    return '—' if n is None else f'{n:,.2f}'


def _location(price, level):
    if price is None or level is None:
        return 'Chưa đủ dữ liệu'
    # Comparisons use raw values, without visually rounded-price inference.
    if price > level:
        return 'Giá đã vượt'
    if price == level:
        return 'Đang chạm mốc'
    return 'Chưa vượt'


def build_ladder(analyses):
    """Return the same daily price hierarchy for panel, top KPI and spoken notes."""
    analyses = analyses if isinstance(analyses, dict) else {}
    day = analyses.get('D')
    g = day.get('g') if isinstance(day, dict) and day.get('enough') else None
    close = _last_valid(g, 'Giá đóng cửa')
    res20 = _last_valid(g, 'Resistance_20') if close is not None else None
    kijun = _kijun_long(g) if close is not None else None
    assumed15 = (close * 1.15) if close is not None else None

    if close is not None and kijun is not None:
        kijun_state = ('Cản theo Kijun phía trên' if kijun > close else
                       'Đang chạm Kijun' if kijun == close else
                       'Kijun đã nằm dưới giá')
    else:
        kijun_state = 'Chưa đủ 129 nến ngày' if close is not None else 'Thiếu giá hợp lệ'

    return {
        'close': close,
        'res20': res20,
        'kijun129': kijun,
        'kijun_period': _kijun_period(),
        'hyp15': assumed15,
        'overhead_kijun': kijun if close is not None and kijun is not None and kijun > close else None,
        'rows': [
            {'Nguồn mốc': 'Đỉnh 20 phiên trước', 'Giá': _fmt(res20), 'Ý nghĩa': _location(close, res20)},
            {'Nguồn mốc': f'Kijun {_kijun_period()} ngày', 'Giá': _fmt(kijun), 'Ý nghĩa': kijun_state},
            {'Nguồn mốc': 'Giả định +15% từ giá EOD', 'Giá': _fmt(assumed15),
             'Ý nghĩa': 'Không phải kháng cự kỹ thuật'},
        ],
    }


def spoken_summary(ladder):
    """A qualified explanation that cannot mislabel the +15% what-if as resistance."""
    if not isinstance(ladder, dict) or ladder.get('close') is None:
        return 'Chưa đủ dữ liệu để phân tầng các mốc giá.'
    close, res, kijun = ladder['close'], ladder['res20'], ladder['kijun129']
    if res is None:
        prior = 'Chưa xác định được đỉnh 20 phiên trước.'
    elif close > res:
        prior = f'Đỉnh 20 phiên trước {_fmt(res)} đã được vượt trên giá đóng cửa.'
    elif close == res:
        prior = f'Giá đang chạm đỉnh 20 phiên trước {_fmt(res)}, chưa vượt.'
    else:
        prior = f'Giá chưa vượt đỉnh 20 phiên trước {_fmt(res)}.'

    if kijun is None:
        long_line = f'Chưa đủ dữ liệu Kijun {ladder["kijun_period"]} ngày.'
    elif kijun > close:
        long_line = (f'Cản Kijun {ladder["kijun_period"]} ngày trên biểu đồ ở {_fmt(kijun)} '
                     'vẫn nằm phía trên giá; đây là loại cản khác với đỉnh 20 phiên.')
    elif kijun == close:
        long_line = f'Giá đang chạm Kijun {ladder["kijun_period"]} ngày {_fmt(kijun)}.'
    else:
        long_line = (f'Kijun {ladder["kijun_period"]} ngày {_fmt(kijun)} hiện nằm dưới giá, '
                     'không phải cản phía trên.')

    return (f'{prior} {long_line} Mức {_fmt(ladder["hyp15"])} chỉ là giả định tăng 15% '
            'từ giá đóng cửa, không phải mục tiêu đã xác nhận hay kháng cự kỹ thuật.')
