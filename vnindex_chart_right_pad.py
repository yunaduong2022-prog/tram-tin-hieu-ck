"""Timeframe-sensitive empty plot space to the right of VNINDEX candles.

Plotly category axes use numeric candle positions 0..n-1, even when x labels
are strings. Extending the axis range is *display only*: no fictional candles,
no extra volumes, no change to technical indicators or report timestamps.
"""
from __future__ import annotations

# Extra axis lengths relative to the number of real candles.
# Visible blank share = ratio / (1 + ratio) for typical n > 3.
RIGHT_EXTRA_RATIO = {"D": 0.18, "W": 0.37, "M": 0.26, "Q": 0.40}


def right_axis_range(n_bars: int, tf: str) -> list[float]:
    """Return a numeric category range with trailing empty plot area.

    Weekly/quarterly get wider spacing (~27-29%) as requested. Daily (~15%)
    and monthly (~21%) stay proportional for every 5D/1M/1Y/all preset.
    Both price and volume panes must receive the same x range.
    """
    if isinstance(n_bars, bool) or not isinstance(n_bars, int) or n_bars < 1:
        raise ValueError("n_bars must be a positive integer")
    if tf not in RIGHT_EXTRA_RATIO:
        raise ValueError(f"unsupported VNINDEX timeframe: {tf!r}")
    extra = max(0.70, n_bars * RIGHT_EXTRA_RATIO[tf])
    return [-0.5, n_bars - 0.5 + extra]
