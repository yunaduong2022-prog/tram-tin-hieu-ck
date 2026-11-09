"""Sync VNINDEX leading sectors with the canonical Dong dan song ranking.

This module does not infer verified buying/net inflow from EOD turnover.
"""
from __future__ import annotations

import pandas as pd
from pathlib import Path
from vnindex_market_cap import load_shares, threshold_for_group, filtered_top_codes

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
    # Shares are the public-market-data snapshot already mirrored by R2.
    # The groups and their price-strength ranking must remain unchanged.
    shares = load_shares(Path(__file__).resolve().parent / 'data' / 'shares_outstanding.csv',
                         as_of=end.date())
    result = []
    for _, row in leaders.iterrows():
        group = str(row["Dòng"])
        members = groups.get(group, [])
        threshold = threshold_for_group(group, len(set(members)))
        # IMPORTANT: rank ALL representatives first, then filter capitalization;
        # otherwise an undersized Top-5 code would block an eligible #6 code.
        reps = ND.rep_stocks(P, members, n, meta.get(group, {}).get("leaders"), top=None)
        codes = filtered_top_codes(reps.to_dict("records") if not reps.empty else [],
                                   shares, threshold, top=5)
        # Keep the TOP-3 sector group even if no representative passes the cap.
        result.append({"group": group, "return": float(row["Giai đoạn"]),
                       "codes": codes, "rank": int(row["#"]), "min_cap_bil": threshold})
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
    for x in rows:
        codes = x.get("codes", [])
        if codes:
            label = x["group"] + ": " + ", ".join(codes)
        else:
            amount = x.get("min_cap_bil", 0)
            cap_text = f"{amount:,.0f}".replace(",", ".")
            label = (f'{x["group"]}: Chưa có mã đạt vốn hóa ≥{cap_text} tỷ '
                     'hoặc chưa đủ dữ liệu để xác minh.')
        items.append(dict(tone="xanh" if codes else "vang", text=label, subs=[]))
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
