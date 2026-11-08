"""Read-only foreign/proprietary net trade lists for VNINDEX report."""
from __future__ import annotations

from pathlib import Path
import re
import pandas as pd

PERIODS = {"D": ("phiên", 1), "W": ("tuần", 5), "M": ("tháng", 21), "Q": ("quý", 63)}
SOURCES = (
    ("Khối ngoại", "foreign_net_flow.csv", "net_value_vnd"),
    ("Tự doanh", "proprietary_flow.csv", "net_val"),
)


def _load(path: Path, field: str) -> pd.DataFrame:
    """Validate minimum schema; don't modify mirrored files or call external APIs."""
    if not path.is_file():
        return pd.DataFrame()
    try:
        d = pd.read_csv(path, encoding="utf-8-sig", dtype={"symbol": str, "trading_date": str})
        required = {"symbol", "trading_date", field}
        if not required.issubset(d.columns):
            return pd.DataFrame()
        d = d.copy()
        d["symbol"] = d["symbol"].astype(str).str.strip().str.upper()
        d["date"] = pd.to_datetime(d["trading_date"], format="%Y-%m-%d", errors="coerce")
        d["net"] = pd.to_numeric(d[field], errors="coerce")
        d = d[d["symbol"].str.fullmatch(r"[A-Z][A-Z0-9]{1,5}", na=False) & d["date"].notna() & d["net"].notna()]
        d = d[d["net"].abs().le(1e16)]
        # Duplicate dates/symbols are not summed twice.
        d = d.drop_duplicates(["date", "symbol"], keep="last")
        if field == "net_value_vnd" and "source_scope" in d.columns:
            d = d[d["source_scope"].isin(["FLOW_VERIFIED_FULL", "RANKING_TOP_ONLY"])]
        return d
    except (OSError, ValueError, pd.errors.ParserError, UnicodeError):
        return pd.DataFrame()


def _expected_sessions(index_dates, tf: str):
    if tf not in PERIODS:
        raise ValueError("Unsupported timeframe")
    dates = pd.to_datetime(pd.Series(index_dates), errors="coerce").dropna().dt.normalize().drop_duplicates().sort_values()
    if dates.empty:
        return []
    return list(dates.tail(PERIODS[tf][1]))


def _summary(df: pd.DataFrame, dates: list, field: str):
    if df.empty or not dates:
        return None
    within = df[df["date"].isin(dates)].copy()
    if within.empty:
        return None
    found = within["date"].nunique()
    # Data are sample-based for RANKING_TOP_ONLY and per-stock round-robin sources.
    scope = ("mẫu TOP" if field == "net_value_vnd" and
             ("source_scope" in within and within["source_scope"].eq("RANKING_TOP_ONLY").any())
             else "mẫu mã đã thu thập" if field == "net_val" else "mẫu nguồn trả về")
    net = within.groupby("symbol")["net"].sum()
    buy = net[net.gt(0)].sort_values(ascending=False).head(5)
    sell = net[net.lt(0)].sort_values().head(5)
    return {"buy": list(buy.index), "sell": list(sell.index),
            "coverage": f"{found}/{len(dates)} phiên", "scope": scope,
            "complete": found == len(dates), "dates": (min(within["date"]), max(within["date"]))}


def net_flow_sections(index_dates, tf: str, root: Path | str = "data") -> dict:
    """Return one separate VNINDEX report card; no aggregation over future dates."""
    dates = _expected_sessions(index_dates, tf)
    root = Path(root)
    items = []
    for name, filename, field in SOURCES:
        data = _load(root / filename, field)
        summary = _summary(data, dates, field)
        items.append(dict(tone="", text=name.upper(), subs=[]))
        if summary is None:
            items.append(dict(tone="vang", text=f"Chưa có dữ liệu {name.lower()} đúng giai đoạn để xếp hạng.", subs=[]))
            continue
        if summary["complete"]:
            note = f"Độ phủ ngày: {summary['coverage']} · {summary['scope']}"
        else:
            note = f"Dữ liệu CHƯA ĐỦ KỲ: {summary['coverage']} · {summary['scope']} (không phải tổng ròng toàn kỳ)"
        items.append(dict(tone="vang", text=note, subs=[]))
        items.append(dict(tone="xanh", text="Mua ròng: " + (", ".join(summary["buy"]) if summary["buy"] else "Chưa có mã"), subs=[]))
        items.append(dict(tone="do", text="Bán ròng: " + (", ".join(summary["sell"]) if summary["sell"] else "Chưa có mã"), subs=[]))
    return {"name": "KHỐI NGOẠI – TỰ DOANH", "items": items}
