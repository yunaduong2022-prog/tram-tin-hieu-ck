"""VNINDEX flow-first actions, based on verified strong/weak sector rankings.

Read-only EOD analysis. Strong sectors are PRICE leaders, NOT verified net buys.
No order signal, return promise, price fabrication, or cross-timeframe mixing.
"""
from __future__ import annotations

import math
from typing import Any

import pandas as pd

LOOKBACK_SESSIONS = 60
MIN_VALID_SESSIONS = 45
HOT_RISE_PCT = 25.0
MIN_PULLBACK_PCT = 8.0  # lower than 8% off post-low peak => still near recent high
TF_TEXT = {"D": "phiên", "W": "tuần", "M": "tháng", "Q": "quý"}


def weak_groups_from_flow(sections: list[dict]) -> list[str]:
    """Use precisely the already-rendered TOP NHÓM YẾU block, not a new rank."""
    flow = next((x for x in sections if x.get("name") == "DÒNG TIỀN"), None)
    if not flow:
        return []
    inside = False
    result: list[str] = []
    for row in flow.get("items", []):
        msg = str(row.get("text", "")).strip()
        if msg.startswith(("TOP 3 NHÓM YẾU", "TOP NHÓM YẾU")):
            inside = True
            continue
        if not inside:
            continue
        if row.get("tone") != "do" or ": " not in msg:
            continue
        group, _ = msg.split(": ", 1)
        group = group.strip()
        if group and group not in result:
            result.append(group)
    return result[:3]


def _close_window(close_panel: pd.DataFrame | None, code: str, end: pd.Timestamp) -> pd.Series | None:
    if close_panel is None or not isinstance(close_panel, pd.DataFrame) or code not in close_panel.columns:
        return None
    # Validate real dates, real positive prices, and never use future EOD rows.
    data = pd.DataFrame({"date": pd.to_datetime(close_panel.index, errors="coerce"),
                         "price": pd.to_numeric(close_panel[code].to_numpy(), errors="coerce")})
    data = data.dropna(subset=["date", "price"])
    data = data[(data["date"] <= end) & (data["price"] > 0)]
    if data.empty:
        return None
    data = data.drop_duplicates("date", keep="last").sort_values("date").tail(LOOKBACK_SESSIONS)
    if len(data) < MIN_VALID_SESSIONS or data["date"].iloc[-1].normalize() != end:
        return None
    return pd.Series(data["price"].to_numpy(dtype="float64"), index=pd.DatetimeIndex(data["date"]))


def heat_check(close_panel: pd.DataFrame | None, code: str, end: pd.Timestamp) -> dict | None:
    """Flag >=25% over last-60-session close low and <8% under the post-low peak.

    A recent meaningful pullback can unflag a stock, but is NOT a buy signal.
    None = insufficient or stale ticker data; do not claim a stock is cool.
    """
    end = pd.Timestamp(end).normalize()
    prices = _close_window(close_panel, str(code).upper(), end)
    if prices is None:
        return None
    lowest = float(prices.min())
    recent_peak = float(prices.loc[prices.index >= prices.idxmin()].max())
    last = float(prices.iloc[-1])
    if not all(map(math.isfinite, (lowest, recent_peak, last))) or lowest <= 0 or recent_peak <= 0:
        return None
    rise = (last / lowest - 1.0) * 100.0
    pullback = (recent_peak - last) / recent_peak * 100.0
    return {"rise_pct": rise, "pullback_pct": pullback,
            "hot": rise >= HOT_RISE_PCT and pullback < MIN_PULLBACK_PCT}


def unavailable_action(reason: str = "") -> list[dict]:
    extra = (" " + reason) if reason else ""
    return [{"tone": "vang", "text": "Chưa xác minh được nhóm dẫn sóng và nhóm yếu theo cùng kỳ dữ liệu."
             + extra + " Tạm thời không đưa danh sách canh mua.", "subs": []}]


def flow_action_items(sections: list[dict], strong_rows: list[dict] | None,
                      close_panel: pd.DataFrame | None, end: pd.Timestamp,
                      tf: str) -> list[dict]:
    """Compose a compact action card from the SAME ranking as DÒNG TIỀN."""
    if tf not in TF_TEXT or not strong_rows:
        return unavailable_action()
    strong = [row for row in strong_rows if str(row.get("group", "")).strip()]
    if not strong:
        return unavailable_action()
    strong_names = list(dict.fromkeys(str(row["group"]).strip() for row in strong))
    weak = [x for x in weak_groups_from_flow(sections) if x not in strong_names]
    end = pd.Timestamp(end).normalize()

    hot: dict[str, dict] = {}
    unknown: list[str] = []
    watch: list[tuple[str, list[str]]] = []
    seen: set[str] = set()
    for row in strong:
        candidates: list[str] = []
        for value in row.get("codes", []):
            code = str(value).strip().upper()
            if not code or code in seen:
                continue
            seen.add(code)
            check = heat_check(close_panel, code, end)
            if check is None:
                unknown.append(code)
            elif check["hot"]:
                hot[code] = check
            else:
                candidates.append(code)
        watch.append((str(row["group"]), candidates))

    items = [{"tone": "xanh", "text":
              f"ƯU TIÊN NHÓM DẪN SÓNG ({TF_TEXT[tf]}): " + ", ".join(strong_names) + ".",
              "subs": []}]
    qualified = [f"{group}: {', '.join(codes[:3])}" for group, codes in watch if codes]
    if qualified:
        items.append({"tone": "xanh", "text":
                      "CANH CHỈNH, KHÔNG MUA ĐUỔI: " + "; ".join(qualified) + ".",
                      "subs": ["Chỉ xem xét khi giá điều chỉnh/tích lũy về hỗ trợ, khối lượng co lại "
                               "và có tín hiệu hồi phục xác nhận; chưa phải điểm mua tự động."]})
    else:
        items.append({"tone": "vang", "text":
                      "Chưa có mã đại diện được xác minh là không tăng nóng để đưa vào danh sách canh chỉnh.",
                      "subs": []})
    if hot:
        sample = list(hot.items())[:6]
        msg = ", ".join(f"{code} (+{check['rise_pct']:.0f}%)" for code, check in sample)
        more = f" và {len(hot) - 6} mã khác" if len(hot) > 6 else ""
        items.append({"tone": "do", "text":
                      f"TẠM TRÁNH MUA ĐUỔI (≥25%/60 phiên, chưa chỉnh ≥8%): {msg}{more}.",
                      "subs": []})
    if unknown:
        preview = ", ".join(unknown[:7])
        more = f" và {len(unknown)-7} mã khác" if len(unknown) > 7 else ""
        items.append({"tone": "vang", "text":
                      "CHƯA ĐỦ DỮ LIỆU 60 PHIÊN ĐỂ ĐÁNH GIÁ FOMO: " + preview + more + ".",
                      "subs": []})
    if weak:
        items.append({"tone": "do", "text":
                      "HẠN CHẾ MUA MỚI NHÓM YẾU: " + ", ".join(weak) +
                      "; tránh bắt đáy khi chưa có tín hiệu phục hồi.", "subs": []})
    else:
        items.append({"tone": "vang", "text":
                      "Chưa xác minh được nhóm yếu trong DÒNG TIỀN; không tự suy đoán nhóm cần tránh.",
                      "subs": []})
    items.append({"tone": "vang", "text":
                  "KỶ LUẬT: Tăng ≥25% từ đáy đóng cửa 60 phiên và cách đỉnh sau đáy <8% "
                  "là cảnh báo không mua đuổi; chỉ đánh giá lại sau nhịp chỉnh và tín hiệu xác nhận.",
                  "subs": []})
    return items


def replace_action_section(sections: list[dict], items: list[dict]) -> list[dict]:
    """Replace HÀNH ĐỘNG only; preserve other sections and cached inputs."""
    updated = [{**s, "items": items} if s.get("name") == "HÀNH ĐỘNG" else s
               for s in sections]
    if not any(s.get("name") == "HÀNH ĐỘNG" for s in sections):
        updated.append({"name": "HÀNH ĐỘNG", "items": items})
    return updated
