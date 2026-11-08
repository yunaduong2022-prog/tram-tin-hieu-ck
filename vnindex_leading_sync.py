"""Sync VNINDEX leading sectors with the canonical Dong dan song ranking.

This module does not infer verified buying/net inflow from EOD turnover.
"""
from __future__ import annotations

import pandas as pd

PERIOD_FOR_TF = {"D": ("1 phiên", 1), "W": ("1 tuần", 5),
                 "M": ("1 tháng", 21), "Q": ("3 tháng", 63)}
TF_VI = {"D": "phiên", "W": "tuần", "M": "tháng", "Q": "quý"}


def leading_from_eod(raw: pd.DataFrame, index_daily: pd.DataFrame, tf: str,
                     default_groups: dict) -> list[dict]:
    """Use *exactly* the group universe and period_stats/rep_stocks of Dong dan song.

    Both stock and VNINDEX prices are truncated at the same EOD date.  If data
    are insufficient, return an empty list rather than fabricate leaders.
    """
    import nhom_nganh_data as ND
    import sector_rotation as SRT

    if tf not in PERIOD_FOR_TF or raw is None or raw.empty or index_daily is None or index_daily.empty:
        return []
    name, n = PERIOD_FOR_TF[tf]
    end = pd.Timestamp(index_daily["Ngày"].max()).normalize()
    stock = raw.copy()
    stock["Ngày"] = pd.to_datetime(stock["Ngày"], errors="coerce", format="mixed", dayfirst=True).dt.normalize()
    stock = stock[stock["Ngày"].notna() & (stock["Ngày"] <= end)]
    if stock.empty:
        return []
    P = SRT._prep(stock)  # same pivot implementation used by ND.pivots
    if P.get("c") is None or P["c"].empty or len(P["c"]) < n + 2:
        return []
    groups, meta = ND.load_groups(default_groups)
    ix = index_daily.copy()
    ix["Ngày"] = pd.to_datetime(ix["Ngày"], errors="coerce").dt.normalize()
    ix = ix[ix["Ngày"] <= end].drop_duplicates("Ngày", keep="last")
    mkt = pd.to_numeric(ix["Giá đóng cửa"], errors="coerce")
    mkt.index = pd.DatetimeIndex(ix["Ngày"])
    mkt = mkt.sort_index()
    board, _ = ND.period_stats(P, groups, mkt, n)
    if board.empty:
        return []
    leaders = board.loc[board["Dẫn sóng"].fillna(False)].sort_values("#").head(3)
    result = []
    for _, row in leaders.iterrows():
        group = str(row["Dòng"])
        reps = ND.rep_stocks(P, groups.get(group, []), n,
                             meta.get(group, {}).get("leaders"), top=5)
        codes = [str(code) for code in reps["Mã"]] if not reps.empty else []
        if not codes:
            continue
        result.append({"group": group, "return": float(row["Giai đoạn"]),
                       "codes": codes, "rank": int(row["#"])})
    return result


def leading_items(rows: list[dict], tf: str) -> list[dict]:
    period, n = PERIOD_FOR_TF[tf]
    if not rows:
        return [dict(tone="vang", text=f"Chưa có nhóm đủ tiêu chí DẪN SÓNG trên giai đoạn {period}.", subs=[])]
    groups = ", ".join(x["group"] for x in rows)
    performance = "; ".join(f'{x["group"]} {x["return"]:+.1f}%' for x in rows)
    reason = (f"Nhận định {TF_VI[tf]}: {groups} dẫn dắt về sức mạnh giá trong {n} phiên "
              f"({performance}); đây là hiệu suất giá, không phải dòng tiền mua ròng.")
    items = [dict(tone="xanh", text=f"TOP {len(rows)} NHÓM DẪN SÓNG ({period}):", subs=[]),
             dict(tone="", text=reason, subs=[])]
    items.extend(dict(tone="xanh", text=x["group"] + ": " + ", ".join(x["codes"]), subs=[])
                 for x in rows)
    return items


def replace_strong_sector_block(sections: list[dict], rows: list[dict], tf: str) -> list[dict]:
    """Replace only strong-sector block; preserve index totals, weak groups and FOMO."""
    result = []
    for section in sections:
        if section.get("name") != "DÒNG TIỀN":
            result.append(section)
            continue
        items = list(section.get("items", []))
        start = next((i for i, x in enumerate(items)
                      if x.get("text", "").startswith(("TOP 3 NHÓM HÚT TIỀN", "TOP NHÓM HÚT TIỀN", "TOP 3 NHÓM DẪN SÓNG"))), None)
        stop = next((i for i, x in enumerate(items)
                     if x.get("text", "").startswith(("TOP 3 NHÓM YẾU", "TOP NHÓM YẾU"))), None)
        if start is not None:
            end = stop if stop is not None and stop > start else len(items)
            new = items[:start] + leading_items(rows, tf) + items[end:]
        else:
            at = stop if stop is not None else len(items)
            new = items[:at] + leading_items(rows, tf) + items[at:]
        result.append({**section, "items": new})
    return result
