"""Cổ phiếu chờ mua trong tuần: nhận diện 9 trạng thái chờ mua + 4 trạng thái cảnh báo / đứng ngoài.

Không phụ thuộc Streamlit. Chạy trên khung Ngày (EMA10, EMA20, MA50, Volume, nền giá, hỗ trợ/kháng cự)
và khung Tuần (MA10 tuần, MA20 tuần) do engine.add_indicators đã tính sẵn.

Mỗi mã được xếp vào ĐÚNG MỘT trạng thái theo thứ tự ưu tiên cố định (xem classify):
    1) Thiếu dữ liệu      -> "Không có điểm mua"
    2) Tăng quá đà        -> danh sách cảnh báo không mua đuổi
    3) Không có điểm mua  -> loại hoàn toàn
    4) Hạ tỷ trọng        -> danh sách cảnh báo rủi ro / bán
    5) Đang phục hồi      -> danh sách theo dõi phục hồi riêng
    6) 9 trạng thái chờ mua (nhóm 1 -> 2 -> 3)
Chỉ nhóm 6 mới vào tab "Cổ phiếu chờ mua trong tuần".
"""
from __future__ import annotations

import html as _html

import numpy as np
import pandas as pd

import engine as E

# ------------------------------------------------------------------ NGƯỠNG (chỉnh tại đây)
CFG = {
    "min_bars": 60,             # số phiên tối thiểu để có MA50 + độ dốc
    "buy_lookback": 5,          # tìm tín hiệu mua trong N phiên gần nhất
    "buy_max_chase": 5.0,       # % giá hiện tại được cao hơn giá lúc phát tín hiệu (>3% chỉ mua thận trọng)
    "buy_caution_chase": 3.0,
    "support_touch": 3.0,       # % giá được cao hơn hỗ trợ để coi là "đang ở vùng hỗ trợ"
    "dry_vol": 0.8,             # Vol(5 phiên) / MA20 Vol <= ngưỡng => cạn kiệt
    "min_rr": 2.0,              # R:R tối thiểu cho "Điểm mua đẹp"
    "stop_buffer": 3.0,         # % cắt lỗ dưới hỗ trợ
    "pullback_min": 3.0,        # % điều chỉnh từ đỉnh 20 phiên để coi là nhịp chỉnh
    "pullback_max": 12.0,
    "near_res": 2.5,            # % còn lại tới kháng cự để coi là "sát kháng cự"
    "tight_range5": 2.8,        # % biên độ TB nến 5 phiên gần nhất
    "tight_band10": 9.0,        # % (đỉnh - đáy) 10 phiên gần nhất
    "ma_spread": 5.0,           # % chênh lệch giữa EMA10, EMA20, MA50, MA10 tuần
    "ob_ext_ema20": 10.0,       # tăng quá đà: giá > EMA20 quá x%
    "ob_gain10": 15.0,          # hoặc tăng > x% trong 10 phiên
    "ob_ext_soft": 7.0,         # hoặc > x% kèm StochRSI >= 90
    "recover_bounce": 8.0,      # đang phục hồi: đã hồi >= x% từ đáy 20 phiên mà chưa lấy lại MA50
    "crash5": -7.0,             # rơi 5 phiên >= x% dưới EMA20 => cắm đầu
}

# ------------------------------------------------------------------ TRẠNG THÁI
G1, G2, G3 = "Điểm mua đã xác nhận", "Sắp có điểm mua", "Theo dõi thêm"
L_RECOVER, L_OVERBOUGHT, L_RISK, L_NONE = ("Theo dõi phục hồi", "Cảnh báo không mua đuổi",
                                           "Cảnh báo rủi ro / bán", "Loại khỏi mọi danh sách")

BUY_SIGNAL, GOOD_ENTRY = "Đã có tín hiệu mua theo chiến lược", "Điểm mua đẹp"
WATCH, NEAR_ZONE, EARLY_UP, ACCUM = ("Theo dõi điểm mua", "Gần vùng mua, cần thêm xác nhận",
                                     "Chớm tăng giá", "Tích lũy / Siết nền giá")
IMPROVING, WAIT_CONFIRM, MARGINAL = ("Có dấu hiệu cải thiện", "Chờ xác nhận",
                                     "Chỉ đưa vào khi xu hướng không quá yếu")
RECOVERING, OVERBOUGHT, WEAKENING, NO_BUY = ("Đang phục hồi", "Tăng quá đà",
                                             "Hạ tỷ trọng / Xu hướng suy yếu", "Không có điểm mua / Đứng ngoài")

STATE_GROUP = {BUY_SIGNAL: G1, GOOD_ENTRY: G1, WATCH: G2, NEAR_ZONE: G2, EARLY_UP: G2, ACCUM: G2,
               IMPROVING: G3, WAIT_CONFIRM: G3, MARGINAL: G3,
               RECOVERING: L_RECOVER, OVERBOUGHT: L_OVERBOUGHT, WEAKENING: L_RISK, NO_BUY: L_NONE}
BUY_GROUPS = (G1, G2, G3)

# ------------------------------------------------------------------ TAG TRẠNG THÁI TRÊN THẺ BỘ LỌC REALTIME
# 13 trạng thái chi tiết -> 9 tag hiển thị (nhãn, màu nền, màu chữ). Muốn đổi cách gom tag chỉ cần sửa TAG_OF_STATE.
TAG_STYLE = {
    "Điểm mua đẹp":            ("#DDF1EB", "#08785E"),
    "Chớm tăng giá":           ("#D9F0F4", "#0E7490"),
    "Theo dõi điểm mua":       ("#FDE6D6", "#C2570C"),
    "Tích lũy / Siết nền giá": ("#E0EAFB", "#2F5FC4"),
    "Đang phục hồi":           ("#ECE5FB", "#6B46C1"),
    "Tăng quá đà / Qua điểm mua": ("#FFF1C9", "#8A5A00"),
    "Xu hướng suy yếu":        ("#FCE4E8", "#C02645"),
    "Hạ tỷ trọng":             ("#F8CBD3", "#A3152F"),
    "Không có điểm mua":       ("#EEF1F5", "#626B78"),
}
TAG_OF_STATE = {
    "Đã có tín hiệu mua theo chiến lược": "Điểm mua đẹp", "Điểm mua đẹp": "Điểm mua đẹp",
    "Theo dõi điểm mua": "Theo dõi điểm mua", "Gần vùng mua, cần thêm xác nhận": "Theo dõi điểm mua",
    "Chỉ đưa vào khi xu hướng không quá yếu": "Theo dõi điểm mua",
    "Chớm tăng giá": "Chớm tăng giá", "Tích lũy / Siết nền giá": "Tích lũy / Siết nền giá",
    "Có dấu hiệu cải thiện": "Đang phục hồi", "Chờ xác nhận": "Đang phục hồi", "Đang phục hồi": "Đang phục hồi",
    "Tăng quá đà": "Tăng quá đà / Qua điểm mua",
    "Hạ tỷ trọng / Xu hướng suy yếu": "Xu hướng suy yếu",     # đổi thành "Hạ tỷ trọng" khi có tín hiệu bán (xem status_tag)
    "Không có điểm mua / Đứng ngoài": "Không có điểm mua",
}


def status_tag(state: str, reason: str = "") -> tuple[str, str, str]:
    """(nhãn, màu nền, màu chữ) của tag trạng thái. Trạng thái \"Hạ tỷ trọng / Xu hướng suy yếu\" được tách đôi:
    có tín hiệu bán trong 3 phiên (UPTHRUST, BREAKDOWN...) -> \"Hạ tỷ trọng\"; còn lại -> \"Xu hướng suy yếu\"."""
    label = TAG_OF_STATE.get(state, "Không có điểm mua")
    if state == WEAKENING and "tín hiệu bán" in (reason or ""):
        label = "Hạ tỷ trọng"
    bg, fg = TAG_STYLE[label]
    return label, bg, fg

STATES_BY_GROUP = {G1: [GOOD_ENTRY, BUY_SIGNAL], G2: [WATCH, NEAR_ZONE, EARLY_UP, ACCUM],
                   G3: [IMPROVING, WAIT_CONFIRM, MARGINAL]}
BEARISH_PV = {"BREAKDOWN", "UPTHRUST", "CLIMAX", "SELLOFF"}


def _f(x, default=np.nan) -> float:
    try:
        v = float(x)
        return v if np.isfinite(v) else default
    except (TypeError, ValueError):
        return default


def _nz(x):
    return 0.0 if x is None or (isinstance(x, float) and np.isnan(x)) else x


def _features(g: pd.DataFrame, w: pd.DataFrame | None, r: pd.Series) -> dict:
    """Gom mọi số liệu cần dùng cho một mã (khung Ngày g đã có chỉ báo, khung Tuần w, hàng screener r)."""
    c_s = g["Giá đóng cửa"]
    h, l, v = g["Giá cao nhất"], g["Giá thấp nhất"], g["Khối lượng khớp lệnh"]
    c = float(c_s.iat[-1])
    ema10 = c_s.ewm(span=10, adjust=False).mean()
    ema20 = c_s.ewm(span=20, adjust=False).mean()
    ma50 = g["MA50"]
    vol20 = _f(g["Vol_MA20"].iat[-1])
    f = {
        "c": c, "ema10": float(ema10.iat[-1]), "ema20": float(ema20.iat[-1]), "ma50": _f(ma50.iat[-1]),
        "ema20_5": float(ema20.iat[-6]) if len(g) > 6 else np.nan,
        "ma50_10": _f(ma50.iat[-11]) if len(g) > 11 else np.nan,
        "wma10": np.nan, "wma20": np.nan,
        "vol20": vol20,
        "vol_now": _f(v.iat[-1] / vol20) if vol20 else np.nan,
        "vol5": _f(v.tail(5).mean() / vol20) if vol20 else np.nan,
        "res": _f(r.get("Resistance_20")), "sup20": _f(r.get("Support_20")),
        "hi20": float(h.tail(20).max()), "hi10": float(h.tail(10).max()),
        "lo10": float(l.tail(10).min()), "lo10_prev": float(l.iloc[-20:-10].min()) if len(g) >= 20 else np.nan,
        "lo20": float(l.tail(20).min()), "lo5": float(l.tail(5).min()),
        "hi60": float(h.tail(60).max()), "hi52": _f(r.get("Hi52")),
        "rng5": _f(g["Range_%"].tail(5).mean()),
        "band10": (float(h.tail(10).max()) - float(l.tail(10).min())) / c * 100,
        "gain10": (c / float(c_s.iat[-11]) - 1) * 100 if len(g) > 11 else np.nan,
        "drop5": (c / float(c_s.iat[-6]) - 1) * 100 if len(g) > 6 else np.nan,
        "pos": _f(g["Position_%"].iat[-1]), "chg": _f(g["Chg_%"].iat[-1], 0.0),
        "srsi": _f(g["SRSI_K"].iat[-1]), "mfi": _f(g["MFI14"].iat[-1]),
        "ad_up": bool(g["AD_up"].iat[-1]), "early": bool(g["EarlyFlow"].tail(3).any()),
        "hist": g["MACD_hist"].tail(4).values, "rs20": _f(r.get("RS20")), "score": _f(r.get("Score"), 0.0),
        "pv_recent": set(g["PV_code"].tail(3)) - {""},
    }
    f["ema20_10ago"] = float(ema20.iat[-11]) if len(g) > 11 else np.nan
    f["crossed_ema20"] = bool(((c_s.tail(4) > ema20.tail(4)).values[-1]) and (c_s.tail(4).values[:-1] < ema20.tail(4).values[:-1]).any())
    f["ma_spread"] = (max(f["ema10"], f["ema20"], f["ma50"]) - min(f["ema10"], f["ema20"], f["ma50"])) / c * 100
    if w is not None and len(w) >= 20:
        f["wma10"], f["wma20"] = _f(w["MA10"].iat[-1]), _f(w["MA20"].iat[-1])
        f["ma_spread"] = (max(f["ema10"], f["ema20"], f["ma50"], f["wma10"])
                          - min(f["ema10"], f["ema20"], f["ma50"], f["wma10"])) / c * 100
    f["has_week"] = not (np.isnan(f["wma10"]) or np.isnan(f["wma20"]))
    # xu hướng: ngày + tuần (thiếu dữ liệu tuần thì không loại, chỉ ghi chú)
    f["up_d"] = bool(c > f["ma50"] and f["ema20"] > f["ma50"] and (np.isnan(f["ma50_10"]) or f["ma50"] >= f["ma50_10"]))
    f["up_w"] = True if not f["has_week"] else bool(c > f["wma20"] and f["wma10"] >= f["wma20"])
    f["up"] = f["up_d"] and f["up_w"]
    f["higher_low"] = bool(f["lo10"] > f["lo10_prev"] * 1.005) if not np.isnan(f["lo10_prev"]) else False
    f["res_far"] = f["res"] if (not np.isnan(f["res"]) and f["res"] > c * 1.01) else (f["hi60"] if f["hi60"] > c * 1.01 else np.nan)
    return f


def _levels(f: dict, support: float, entry_lo: float | None = None, entry_hi: float | None = None,
            stop: float | None = None) -> dict:
    """Vùng mua, giá vào tham chiếu, cắt lỗ, Mục tiêu 1/2, R:R (tính trên Mục tiêu 1).

    Giá vào tham chiếu = giá hiện tại nếu đang trong vùng mua; chưa tới vùng thì lấy cạnh dưới, đã vượt vùng thì lấy cạnh trên.
    Mục tiêu 1/2 = hai mức cản gần nhất phía trên (đỉnh 20 phiên, đỉnh 60 phiên, đỉnh 52 tuần); không có mức cản nào
    thì Mục tiêu 1 đo bằng 2R và không có Mục tiêu 2.
    """
    c = f["c"]
    lo = entry_lo if entry_lo is not None else support
    hi = entry_hi if entry_hi is not None else support * (1 + CFG["support_touch"] / 100)
    sl = stop if stop is not None else support * (1 - CFG["stop_buffer"] / 100)
    entry = min(max(c, lo), hi) if hi > lo else c
    risk = entry - sl
    base = max(c, entry)
    above = sorted({round(x, 4) for x in (f["res"], f["hi60"], f["hi52"]) if not np.isnan(x) and x > base * 1.01})
    t1 = above[0] if above else (entry + 2 * risk if risk > 0 else np.nan)
    t2 = next((x for x in above[1:] if x > t1 * 1.01), np.nan)
    rr = (t1 - entry) / risk if risk > 0 and not np.isnan(t1) else np.nan
    pct = lambda x: (x / entry - 1) * 100 if not np.isnan(x) and entry > 0 else np.nan
    return {"Vùng mua từ": lo, "Vùng mua đến": hi, "Giá vào": entry, "Cắt lỗ": sl, "Cắt lỗ %": pct(sl),
            "Mục tiêu 1": t1, "Lời 1 %": pct(t1), "Mục tiêu 2": t2, "Lời 2 %": pct(t2), "R:R": rr,
            "Cản gần": above[0] if above else np.nan,
            "Cách vùng mua %": (c / hi - 1) * 100 if c > hi else (c / lo - 1) * 100 if c < lo else 0.0}


def _chart_levels(lv: dict, fc: dict) -> dict:
    """Thay vùng mua / cắt lỗ / mục tiêu bằng số của trang biểu đồ (engine.forecast_levels). Phần cấu trúc (R:R tới cản gần nhất)
    đã dùng xong ở bước lọc "Điểm mua đẹp"; chỉ giữ lại "Cản gần" để cảnh báo."""
    c = fc["entry"]
    return {"Vùng mua từ": fc["lo"], "Vùng mua đến": fc["hi"], "Giá vào": c,
            "Cắt lỗ": fc["sl"], "Cắt lỗ %": -fc["sl_pct"],
            "Mục tiêu 1": fc["t1"], "Lời 1 %": (fc["t1"] / c - 1) * 100,
            "Mục tiêu 2": fc["t2"], "Lời 2 %": (fc["t2"] / c - 1) * 100,
            "R:R": 2.0, "Cản gần": lv.get("Cản gần", np.nan), "Cách vùng mua %": 0.0}


# Hành động theo trạng thái: vùng mua (theo trang biểu đồ) luôn quanh giá hiện tại, nên "vào ngay hay chờ" do trạng thái quyết định
ACT_NOW = {BUY_SIGNAL, GOOD_ENTRY}
ACT_WAIT_NOTE = {NEAR_ZONE: "chờ 1 phiên bứt phá có khối lượng hoặc phiên đảo chiều rõ ràng rồi mới vào vùng này",
                 EARLY_UP: "chờ giá bứt khỏi nền kèm khối lượng rồi mới vào vùng này",
                 ACCUM: "chờ giá phá khỏi biên độ nền kèm khối lượng rồi mới vào vùng này",
                 WATCH: "chờ giá điều chỉnh về sát hỗ trợ (xem lý do) rồi mới vào vùng này",
                 IMPROVING: "chỉ theo dõi, chưa nên giải ngân",
                 WAIT_CONFIRM: "chờ MA và thanh khoản xác nhận đảo chiều rồi mới vào",
                 MARGINAL: "chỉ theo dõi, chưa nên giải ngân"}


def action_of(state: str) -> tuple[str, str]:
    """(Hành động, ghi chú). Hành động là "Vào ngay" hoặc "Chờ mua"."""
    if state in ACT_NOW:
        return "Vào ngay", "giá đang trong vùng mua, có thể giải ngân (nên chia lệnh)"
    return "Chờ mua", ACT_WAIT_NOTE.get(state, "cần thêm xác nhận")


def _recent_buy_signal(g: pd.DataFrame, n: int):
    """Tín hiệu mua của thuật toán chính (PV Breakout/Spring hoặc Điểm Wyckoff >= 3.5) trong n phiên gần nhất."""
    for k in range(1, min(n, len(g)) + 1):
        row = g.iloc[-k]
        by_pv = int(row["PV_signal"]) > 0
        sig, _sc, _re, _e, sl, _tp, _rr = E.analyze_signal(row)
        if by_pv or sig != "WAIT":
            return {"ago": k - 1, "close": float(row["Giá đóng cửa"]), "low": float(row["Giá thấp nhất"]),
                    "stop": float(sl), "date": row["Ngày"], "kind": row["PV_code"] or sig}
    return None


def _support_candidates(f: dict) -> list[tuple[str, float]]:
    out = [("EMA20", f["ema20"]), ("MA50", f["ma50"]), ("MA10 tuần", f["wma10"]), ("MA20 tuần", f["wma20"]),
           ("đáy nền 20 phiên", f["sup20"])]
    return [(n, s) for n, s in out if not np.isnan(s) and s > 0]


def classify(g: pd.DataFrame, w: pd.DataFrame | None, r: pd.Series) -> dict:
    """Trả về {state, group, reason, + vùng mua/cắt lỗ/mục tiêu} cho một mã."""
    ctx: dict = {}

    def out(state, reason, **lv):
        if lv and ctx.get("fc"):
            lv = _chart_levels(lv, ctx["fc"])
        return {"Trạng thái": state, "Danh sách": STATE_GROUP[state], "Lý do": reason, **lv}

    if len(g) < CFG["min_bars"] or pd.isna(g["MA50"].iat[-1]):
        return out(NO_BUY, f"Chưa đủ dữ liệu (cần ≥ {CFG['min_bars']} phiên để tính MA50)")
    f = _features(g, w, r)
    ctx["fc"] = E.forecast_levels(f["c"], _f(g["ATR"].iat[-1]), 1)
    c, wk = f["c"], ("" if f["has_week"] else " (chưa đủ dữ liệu tuần)")
    ext20 = (c / f["ema20"] - 1) * 100

    # ---------- 4 trạng thái ngoài danh sách chờ mua
    if (ext20 >= CFG["ob_ext_ema20"] or (not np.isnan(f["gain10"]) and f["gain10"] >= CFG["ob_gain10"])
            or (ext20 >= CFG["ob_ext_soft"] and f["srsi"] >= 90)):
        return out(OVERBOUGHT, f"Giá cao hơn EMA20 {ext20:.1f}%, tăng {f['gain10']:.1f}% trong 10 phiên: không mua đuổi")

    down50 = not np.isnan(f["ma50_10"]) and f["ma50"] < f["ma50_10"]
    below_w = f["has_week"] and c < f["wma20"]
    crash = not np.isnan(f["drop5"]) and f["drop5"] <= CFG["crash5"] and c < f["ema20"]
    if (c < f["ma50"] and down50 and c < f["ema20"] < f["ma50"] and not f["higher_low"] and (below_w or not f["has_week"])) or crash:
        why = f"Rơi {f['drop5']:.1f}% trong 5 phiên, dưới EMA20" if crash else "Dưới EMA20 < MA50 đang dốc xuống, chưa tạo đáy sau cao hơn"
        return out(NO_BUY, why + ": đứng ngoài")

    bearish = f["pv_recent"] & BEARISH_PV
    if (bearish or (c < f["ma50"] and f["ema10"] < f["ema20"] and not f["higher_low"])
            or (c < f["ema20"] < f["ma50"] and f["has_week"] and f["wma10"] < f["wma20"])):
        why = (f"Có tín hiệu bán trong 3 phiên ({', '.join(E.PV_LABEL[b] for b in sorted(bearish))})" if bearish
               else "Giá dưới MA50, EMA10 < EMA20, chưa có đáy sau cao hơn: xu hướng suy yếu")
        return out(WEAKENING, why)

    lo20_bounce = (c / f["lo20"] - 1) * 100
    if (c < f["ma50"] and lo20_bounce >= CFG["recover_bounce"] and c > f["ema10"]):
        return out(RECOVERING, f"Hồi {lo20_bounce:.1f}% từ đáy 20 phiên nhưng chưa vượt MA50 ({f['ma50']:.2f}): chờ xác nhận phá MA/kháng cự")

    # ---------- NHÓM 1
    sig = _recent_buy_signal(g, CFG["buy_lookback"])
    if sig and c > f["ma50"] and c > f["ema20"] * 0.99 and f["up_w"]:
        chase = (c / sig["close"] - 1) * 100
        if chase <= CFG["buy_max_chase"] and c > sig["stop"]:
            lv = _levels(f, sig["close"], sig["close"], sig["close"] * (1 + CFG["buy_max_chase"] / 100), sig["stop"])
            lv["Cách vùng mua %"] = max(0.0, chase - CFG["buy_max_chase"]) if chase > CFG["buy_max_chase"] else 0.0
            note = " (đã chạy hơn 3%: mua thận trọng, ưu tiên khối lượng nhỏ)" if chase > CFG["buy_caution_chase"] else ""
            when = "hôm nay" if sig["ago"] == 0 else f"{sig['ago']} phiên trước"
            return out(BUY_SIGNAL, f"Tín hiệu mua {when} (giá {sig['close']:.2f}), hiện cao hơn {chase:+.1f}%{note}", **lv)

    if f["up"]:
        for name, s in sorted(_support_candidates(f), key=lambda x: abs(c / x[1] - 1)):
            gap = (c / s - 1) * 100
            touched = f["lo5"] <= s * 1.01 and c >= s * 0.985
            if (0 <= gap <= CFG["support_touch"] or touched) and f["vol5"] <= CFG["dry_vol"] and gap >= -1.5:
                lv = _levels(f, s)
                if lv["R:R"] >= CFG["min_rr"]:
                    return out(GOOD_ENTRY, f"Test lại {name} ({s:.2f}), cách {gap:+.1f}%, khối lượng 5 phiên bằng {f['vol5']:.2f} lần MA20 Vol, R:R {lv['R:R']:.1f}", **lv)

    # ---------- NHÓM 2
    if f["up"]:
        pull = (1 - c / f["hi20"]) * 100
        near = [(n, s) for n, s in _support_candidates(f) if s < c and (c / s - 1) * 100 <= 8.0]
        if CFG["pullback_min"] <= pull <= CFG["pullback_max"] and near and f["vol5"] < 1.0:
            n, s = max(near, key=lambda x: x[1])
            return out(WATCH, f"Uptrend, điều chỉnh {pull:.1f}% từ đỉnh 20 phiên, còn cách {n} ({s:.2f}) {(c / s - 1) * 100:.1f}%, khối lượng co lại", **_levels(f, s))

    res = f["res"]
    if (c > f["ma50"] or (f["has_week"] and c > f["wma20"])) and f["ema20"] >= f["ma50"] * 0.98:
        if not np.isnan(res) and c <= res and (res / c - 1) * 100 <= CFG["near_res"]:
            lv = _levels(f, f["ema20"], res, res * 1.03, f["ema20"] * (1 - CFG["stop_buffer"] / 100))
            return out(NEAR_ZONE, f"Sát kháng cự {res:.2f} (còn {(res / c - 1) * 100:.1f}%): chờ 1 phiên bứt phá có khối lượng", **lv)
        for name, s in _support_candidates(f):
            gap = (c / s - 1) * 100
            if 0 <= gap <= CFG["support_touch"] and f["up_d"]:
                return out(NEAR_ZONE, f"Sát {name} ({s:.2f}) nhưng khối lượng/R:R chưa đạt: chờ phiên đảo chiều rõ ràng", **_levels(f, s))

    early = f["early"] or (0.5 <= f["chg"] <= 4 and 1.2 <= _nz(f["vol_now"]) < 2.5 and f["pos"] >= 60)
    if early and c >= f["ema20"] and c > f["ma50"] * 0.97 and (np.isnan(res) or c <= res):
        return out(EARLY_UP, f"Dòng tiền vào sớm: Vol {f['vol_now']:.1f} lần MA20 Vol, nến xanh đóng cửa cao, chưa bứt khỏi nền",
                   **_levels(f, f["ema20"], f["hi10"], f["hi10"] * 1.03, f["lo10"] * 0.98))

    if (f["rng5"] <= CFG["tight_range5"] and f["band10"] <= CFG["tight_band10"] and f["vol5"] <= 0.9
            and f["ma_spread"] <= CFG["ma_spread"] and c >= f["ma50"] * 0.97):
        return out(ACCUM, f"Nền chặt: biên độ nến {f['rng5']:.1f}%, dải 10 phiên {f['band10']:.1f}%, khối lượng cạn, các MA hội tụ {f['ma_spread']:.1f}%{wk}",
                   **_levels(f, f["lo10"], f["hi10"], f["hi10"] * 1.03, f["lo10"] * 0.98))

    # ---------- NHÓM 3
    stall = np.isnan(f["ema20_5"]) or f["ema20"] >= f["ema20_5"] * 0.995
    if f["higher_low"] and c > f["ema10"] and lo20_bounce >= 3 and stall:
        return out(IMPROVING, f"Đáy 10 phiên gần nhất ({f['lo10']:.2f}) cao hơn đáy trước ({f['lo10_prev']:.2f}), giá trên EMA10, đà giảm chững lại",
                   **_levels(f, f["lo10"]))

    dbl_bottom = not np.isnan(f["lo10_prev"]) and abs(f["lo10"] / f["lo10_prev"] - 1) <= 0.03
    macd_up = len(f["hist"]) == 4 and bool(np.all(np.diff(f["hist"]) > 0))
    unconfirmed = not (f["ema10"] > f["ema20"] and c > f["ma50"])
    if (dbl_bottom or macd_up or f["crossed_ema20"]) and c > f["ema10"] and unconfirmed and _nz(f["vol_now"]) < 1.2:
        pat = "đáy đôi" if dbl_bottom else "MACD histogram tăng 3 phiên" if macd_up else "vừa lấy lại EMA20"
        return out(WAIT_CONFIRM, f"Có mô hình đảo chiều tiềm năng ({pat}) nhưng chưa được MA và thanh khoản xác nhận", **_levels(f, f["lo10"]))

    money_ok = f["ad_up"] and (np.isnan(f["mfi"]) or f["mfi"] >= 40) and (np.isnan(f["rs20"]) or f["rs20"] >= 0.95)
    if (f["up"] or (c >= f["ma50"] * 0.93 and c >= f["lo20"] * 1.03)) and money_ok:
        return out(MARGINAL, "Xu hướng không quá yếu, dòng tiền (A/D, MFI) hỗ trợ, nền giá có khả năng tạo điểm mua", **_levels(f, min(f["ema20"], c)))

    return out(NO_BUY, "Không thỏa điều kiện của trạng thái chờ mua nào, dòng tiền chưa hỗ trợ")


def build_waiting_buy(frames: dict, screener: pd.DataFrame) -> pd.DataFrame:
    """Phân loại toàn bộ rổ. Trả về bảng mỗi mã một dòng, kèm cột Danh sách để lọc."""
    wg = {code: gg for code, gg in frames["W"].groupby("Mã")}
    dg = {code: gg for code, gg in frames["D"].groupby("Mã")}
    rows = []
    for _, r in screener.iterrows():
        code = r["Mã"]
        g = dg.get(code)
        if g is None:
            continue
        try:
            res = classify(g.reset_index(drop=True), wg.get(code), r)
        except Exception as e:     # một mã lỗi dữ liệu không được làm sập cả trang
            res = {"Trạng thái": NO_BUY, "Danh sách": L_NONE, "Lý do": f"Lỗi khi phân loại: {e}"}
        res["Hành động"], res["Ghi chú hành động"] = action_of(res["Trạng thái"])
        can, t1 = res.get("Cản gần", np.nan), res.get("Mục tiêu 1", np.nan)
        if res["Hành động"] == "Vào ngay" and pd.notna(can) and pd.notna(t1) and can < t1:
            res["Ghi chú hành động"] += f"; lưu ý cản gần {can:.2f} (+{(can / r['Giá'] - 1) * 100:.1f}%) thấp hơn Mục tiêu 1"
        rows.append({"Mã": code, "Giá": r["Giá"], "Chg %": r.get("Chg_%", np.nan), "Score": r["Score"], "RS20": r["RS20"], "Nhóm": r.get("Nhóm", ""), **res})
    cols = ["Mã", "Giá", "Chg %", "Score", "RS20", "Nhóm", "Trạng thái", "Danh sách", "Lý do", "Hành động", "Ghi chú hành động",
            "Vùng mua từ", "Vùng mua đến", "Giá vào", "Cắt lỗ", "Cắt lỗ %", "Mục tiêu 1", "Lời 1 %", "Mục tiêu 2", "Lời 2 %",
            "R:R", "Cản gần", "Cách vùng mua %"]
    out = pd.DataFrame(rows)
    for col in cols:
        if col not in out:
            out[col] = np.nan
    return out[cols]


def sort_group(d: pd.DataFrame, group: str) -> pd.DataFrame:
    """Trong một nhóm: theo thứ tự trạng thái đã khai báo, rồi Score giảm dần."""
    order = {s: i for i, s in enumerate(STATES_BY_GROUP.get(group, []))}
    return (d.assign(_o=d["Trạng thái"].map(order).fillna(99)).sort_values(["_o", "Score"], ascending=[True, False])
            .drop(columns="_o"))


# ------------------------------------------------------------------ GIAO DIỆN THẺ (HTML/CSS, ăn theo biến màu của theme.py)
_BADGE = {G1: "g", G2: "a", G3: "n"}


def card_css(dark: bool) -> str:
    """CSS của thẻ. Màu lấy từ biến CSS của theme.py nên tự đổi theo nền Sáng / Tối; chỉ nền khối chiến lược chọn theo chế độ."""
    box = "var(--card2)" if dark else "var(--bg2)"
    return """
[class*="st-key-wbcard-"]{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:18px 18px 16px;
  box-shadow:0 2px 12px var(--shadow);gap:14px!important}
.wb-head{display:flex;justify-content:space-between;align-items:flex-start;gap:14px;flex-wrap:wrap;margin-bottom:16px}
.wb-id{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap}
.wb-code{font-size:28px;font-weight:800;line-height:1.1;color:var(--txt2);letter-spacing:-.3px}
.wb-px{font-size:20px;font-weight:700;line-height:1.1}
.wb-px.up{color:var(--green)}.wb-px.down{color:var(--red)}.wb-px.flat{color:var(--muted)}
.wb-px small{font-size:13px;margin-left:3px}
.wb-badge{display:inline-block;padding:6px 14px;border-radius:999px;font-size:11.5px;font-weight:800;letter-spacing:.4px;
  text-transform:uppercase;white-space:nowrap}
.wb-badge.g{background:var(--tag-green-bg);color:var(--tag-green-fg)}
.wb-badge.a{background:var(--tag-amber-bg);color:var(--tag-amber-fg)}
.wb-badge.n{background:var(--tag-gray-bg);color:var(--tag-gray-fg)}
.wb-pill{background:transparent;color:var(--muted);padding:0;font-size:13.5px;font-weight:500;margin-bottom:12px}
.wb-metrics{display:grid;grid-template-columns:1fr 1fr;gap:6px 12px;font-size:13px;color:var(--muted);margin-bottom:12px}
.wb-metrics b{color:var(--txt2)}
.wb-pill i{font-style:normal;margin:0 7px;opacity:.7}
.wb-note{font-size:13.5px;line-height:1.55;color:var(--txt);margin-bottom:12px}
.wb-box{background:BOXBG;border-radius:14px;padding:4px 16px 12px}
.wb-sec{padding:12px 0}
.wb-sec+.wb-sec{border-top:1px solid var(--line)}
.wb-line{display:flex;justify-content:space-between;align-items:center;gap:10px}
.wb-line+.wb-line{margin-top:9px}
.wb-lab{font-size:14.5px;font-weight:500;color:var(--txt)}
.wb-lab small{font-size:11.5px;font-weight:500;color:var(--muted);margin-left:8px}
.wb-zone{display:flex;align-items:center;justify-content:flex-end;gap:8px;flex-wrap:wrap}
.wb-zone b{font-size:15px;color:var(--txt2)}
.wb-go,.wb-wait{display:inline-block;padding:4px 11px;border-radius:999px;font-size:12px;font-weight:700;white-space:nowrap}
.wb-go{background:var(--tag-green-bg);color:var(--tag-green-fg)}
.wb-wait{background:var(--tag-amber-bg);color:var(--tag-amber-fg)}
.wb-sub{font-size:12.5px;line-height:1.5;color:var(--muted);margin-top:7px}
.wb-red{color:var(--red);font-size:15px}.wb-grn{color:var(--green);font-size:15px}
.wb-foot{font-size:11.5px;line-height:1.45;color:var(--muted);border-top:1px solid var(--line);padding-top:10px}
""".replace("BOXBG", box)


def _sentence(t: str) -> str:
    """Viết hoa đầu câu và thêm dấu chấm cuối câu."""
    t = str(t).strip()
    if not t:
        return t
    t = t[0].upper() + t[1:]
    return t if t[-1] in ".!?" else t + "."


BADGE_TEXT = {BUY_SIGNAL: "ĐIỂM MUA ĐẸP"}     # chữ hiển thị trên thẻ (tên trạng thái dùng để lọc giữ nguyên)


def card_html(r: pd.Series, group: str, meta: dict | None = None) -> str:
    """HTML phần thông tin của thẻ (nút "Xem biểu đồ" do Streamlit vẽ riêng bên dưới).

    meta = {"Ngành", "Vốn hóa", "P/B", "ROE"} đã định dạng sẵn (xem app._wb_meta).
    """
    esc = _html.escape
    state = str(r["Trạng thái"])
    px = lambda x: "-" if pd.isna(x) else f"{x:,.2f}"
    sg = lambda x: "" if pd.isna(x) else f" ({x:+.1f}%)"
    chg = r.get("Chg %", np.nan)
    cls, arrow = (("up", " ▲") if pd.notna(chg) and chg > 0 else ("down", " ▼") if pd.notna(chg) and chg < 0 else ("flat", ""))
    html = (f'<div class="wb-head"><div class="wb-id"><span class="wb-code">{esc(str(r["Mã"]))}</span>'
            f'<span class="wb-px {cls}">{px(r["Giá"])}<small>{arrow.strip()}</small></span></div>'
            f'<span class="wb-badge {_BADGE.get(group, "n")}">{esc(BADGE_TEXT.get(state, state))}</span></div>'
            f'<div class="wb-pill">Score: {r["Score"]:.1f}<i>•</i>RS: {px(r["RS20"])}</div>')
    if meta:
        html += ('<div class="wb-metrics">'
                 f'<div>Ngành: <b>{esc(str(meta["Ngành"]))}</b></div><div>Vốn hóa: <b>{esc(str(meta["Vốn hóa"]))}</b></div>'
                 f'<div>P/B: <b>{esc(str(meta["P/B"]))}</b></div><div>ROE: <b>{esc(str(meta["ROE"]))}</b></div></div>')
    html += f'<div class="wb-note">{esc(_sentence(r["Lý do"]))}</div>'
    if pd.isna(r.get("Vùng mua từ")):
        return html
    go = r.get("Hành động") == "Vào ngay"
    badge = '<span class="wb-go">✔ Vào được ngay</span>' if go else '<span class="wb-wait">⏳ Chờ mua</span>'
    html += (
        '<div class="wb-box">'
        f'<div class="wb-sec"><div class="wb-line"><span class="wb-lab">Vùng mua</span>'
        f'<span class="wb-zone"><b>{px(r["Vùng mua từ"])} – {px(r["Vùng mua đến"])}</b>{badge}</span></div>'
        f'<div class="wb-sub">{esc(_sentence(r["Ghi chú hành động"]))}</div></div>'
        f'<div class="wb-sec"><div class="wb-line"><span class="wb-lab">Cắt lỗ</span>'
        f'<b class="wb-red">{px(r["Cắt lỗ"])}{sg(r["Cắt lỗ %"])}</b></div></div>'
        f'<div class="wb-sec"><div class="wb-line"><span class="wb-lab">Mục tiêu 1<small>R:R 1:2</small></span>'
        f'<b class="wb-grn">{px(r["Mục tiêu 1"])}{sg(r["Lời 1 %"])}</b></div>'
        f'<div class="wb-line"><span class="wb-lab">Mục tiêu 2<small>R:R 1:3</small></span>'
        f'<b class="wb-grn">{px(r["Mục tiêu 2"])}{sg(r["Lời 2 %"])}</b></div></div>'
        f'<div class="wb-foot">Vùng mua, cắt lỗ, mục tiêu tính theo ATR, khớp với trang biểu đồ · % so với giá hiện tại {px(r["Giá vào"])}</div>'
        '</div>')
    return html
