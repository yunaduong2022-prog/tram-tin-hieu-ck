"""Date-based VNINDEX chart viewport; does not recalculate indicator history.

The daily EOD series fixes the time anchor. 5D means five actual EOD trading
sessions, while M/Y choices mean calendar months/years back from that EOD.
"""
from __future__ import annotations

import pandas as pd

RANGE_OPTIONS = ("5D", "1M", "3M", "6M", "1Y", "2Y", "3Y", "Tất cả")
_OFFSETS = {
    "1M": pd.DateOffset(months=1),
    "3M": pd.DateOffset(months=3),
    "6M": pd.DateOffset(months=6),
    "1Y": pd.DateOffset(years=1),
    "2Y": pd.DateOffset(years=2),
    "3Y": pd.DateOffset(years=3),
}


def range_start(daily_dates, selected: str) -> pd.Timestamp | None:
    """Return inclusive cutoff, or None for all history; never use wall clock."""
    if selected not in RANGE_OPTIONS:
        raise ValueError(f"Unknown VNINDEX chart range: {selected!r}")
    if selected == "Tất cả":
        return None
    dates = pd.DatetimeIndex(pd.to_datetime(list(daily_dates), errors="coerce"))
    dates = dates.dropna().normalize().unique().sort_values()
    if not len(dates):
        return None
    if selected == "5D":
        return pd.Timestamp(dates[max(len(dates) - 5, 0)])
    return pd.Timestamp(dates[-1]) - _OFFSETS[selected]


MAX_TIME_TICKS = 8  # Avoid overlapping month labels on 2Y/3Y/All charts.


def _ticks(frame: pd.DataFrame, tf: str) -> list[tuple[int, str]]:
    """Return readable, calendar-aligned time labels for the visible window.

    Tick *density* is display-only: every real candle, volume bar, hover date,
    indicator and shared x-axis range remains unchanged. For dense D/W ranges,
    prefer Jan/Jul, or other evenly spaced calendar months; never show every
    month of a 3-year weekly chart on a single narrow row.
    """
    if frame.empty:
        return []
    dates = pd.to_datetime(frame["Ngày"], errors="coerce")
    candidates: list[tuple[int, pd.Timestamp]] = []
    previous_month = None
    previous_year = None
    for i, day in enumerate(dates):
        if pd.isna(day):
            continue
        year, month = int(day.year), int(day.month)
        if tf in ("D", "W"):
            if previous_month != (year, month):
                candidates.append((i, day))
            previous_month = (year, month)
        else:
            if previous_year != year:
                candidates.append((i, day))
            previous_year = year

    if len(candidates) > MAX_TIME_TICKS:
        if tf in ("D", "W"):
            # Calendar-aligned cadence: every 2/3/4/6/12 months, then years.
            # This preserves meaningful Jan/year markers instead of arbitrarily
            # choosing every Nth trading bar.
            for stride in (2, 3, 4, 6, 12, 24, 36, 60, 120, 240):
                chosen = [(i, d) for i, d in candidates
                          if (int(d.year) * 12 + int(d.month) - 1) % stride == 0]
                if 1 <= len(chosen) <= MAX_TIME_TICKS:
                    candidates = chosen
                    break
            else:  # Sparse, irregular dates may miss every calendar anchor.
                step = (len(candidates) + MAX_TIME_TICKS - 1) // MAX_TIME_TICKS
                candidates = candidates[::step]
        else:
            # Very long monthly/quarterly history: label fewer years too.
            for stride in (2, 3, 4, 5, 10, 20, 50):
                chosen = [(i, d) for i, d in candidates if int(d.year) % stride == 0]
                if 1 <= len(chosen) <= MAX_TIME_TICKS:
                    candidates = chosen
                    break
            else:
                step = (len(candidates) + MAX_TIME_TICKS - 1) // MAX_TIME_TICKS
                candidates = candidates[::step]

    ticks: list[tuple[int, str]] = []
    last_labeled_year = None
    for pos, day in candidates:
        year, month = int(day.year), int(day.month)
        if tf in ("D", "W"):
            # Show year at the first selected label of each year, not only Jan.
            with_year = last_labeled_year != year or month == 1
            text = f"Th{month}/{year}" if with_year else f"Th{month}"
        else:
            text = str(year)
        ticks.append((pos, text))
        last_labeled_year = year
    if len(ticks) > 1 and ticks[1][0] - ticks[0][0] < 3:
        ticks = ticks[1:]
    return ticks


def chart_range_view(chart: dict, daily_dates, selected: str) -> dict:
    """Return display-only copy of a FULL-HISTORY prep_chart result.

    P['g'] already contains the full-series MA, Supertrend and Hull values.
    Slice the finished candle/indicator rows together, never recalculate them.
    """
    if chart is None or not isinstance(chart.get("g"), pd.DataFrame):
        return chart
    frame = chart["g"]
    if frame.empty:
        return chart
    labels = list(chart["labels"])
    if len(labels) != len(frame):
        raise ValueError("VNINDEX chart bars and labels are out of sync")
    cutoff = range_start(daily_dates, selected)
    if cutoff is None:
        positions = list(range(len(frame)))
    else:
        day = pd.to_datetime(frame["Ngày"], errors="coerce").dt.normalize()
        positions = [i for i, is_visible in enumerate((day >= cutoff).tolist()) if is_visible]
        if not positions:
            # An uncommon incomplete/partial bucket must still show its last bar.
            positions = [len(frame) - 1]
    visible = frame.iloc[positions].copy().reset_index(drop=True)
    return {**chart, "g": visible, "labels": [labels[i] for i in positions],
            "ticks": _ticks(visible, chart["tf"])}
