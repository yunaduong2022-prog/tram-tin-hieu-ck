"""Choose genuine latest VNINDEX candles across index CSV and EOD sources.

No artificial candles, forward filling, or network access. An older index CSV
may contribute historical bars but must never truncate newer real EOD bars.
"""
from __future__ import annotations

import pandas as pd


def merge_index_candidates(candidates: list[tuple[str, pd.DataFrame]], codes: set,
                           ohlc: list[str], volume: str) -> pd.DataFrame:
    """Unify available candles, preferring index_prices on overlapping dates.

    Candidate order is ascending priority: EOD file, loaded EOD, index CSV.
    The source that supplies the latest trading date is recorded in attrs.
    """
    fields = ["Ngày", *ohlc, volume]
    prepared: list[pd.DataFrame] = []
    latest_dates: dict[str, pd.Timestamp] = {}
    for name, raw in candidates:
        if raw is None or raw.empty or not set(["Ngày", *ohlc]).issubset(raw.columns):
            continue
        if "Mã" in raw.columns:
            # Large stock EOD tables: select only VNINDEX rows BEFORE copying.
            keep = raw["Mã"].astype(str).str.upper().str.strip().isin(codes)
            d = raw.loc[keep].copy()
        else:
            d = raw.copy()
        if d.empty:
            continue
        d["Ngày"] = pd.to_datetime(d["Ngày"], errors="coerce", format="mixed", dayfirst=True).dt.normalize()
        for field in ohlc:
            d[field] = pd.to_numeric(d[field], errors="coerce")
        if volume not in d.columns:
            d[volume] = 0.0
        else:
            d[volume] = pd.to_numeric(d[volume], errors="coerce").fillna(0.0)
        d = d.dropna(subset=["Ngày", *ohlc])
        d = d[(d[ohlc] > 0).all(axis=1)]
        if d.empty:
            continue
        d = d[fields].drop_duplicates("Ngày", keep="last").sort_values("Ngày")
        latest_dates[name] = d["Ngày"].iloc[-1]
        prepared.append(d)
    if not prepared:
        return pd.DataFrame(columns=fields)
    # Preserve full history and never move back in time when another real source
    # contains newer sessions. Higher-priority sources resolve same-date ties.
    merged = (pd.concat(prepared, ignore_index=True)
              .drop_duplicates("Ngày", keep="last")
              .sort_values("Ngày")
              .reset_index(drop=True))
    latest = merged["Ngày"].iloc[-1]
    latest_source = next(name for name in reversed(list(latest_dates))
                         if latest_dates[name] == latest)
    merged.attrs["latest_source"] = latest_source
    merged.attrs["source_dates"] = {name: value.strftime("%d/%m/%Y")
                                   for name, value in latest_dates.items()}
    return merged
