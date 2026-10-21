"""Chờ mua: nhận diện 9 trạng thái chờ mua + 4 trạng thái cảnh báo / đứng ngoài.

Không phụ thuộc Streamlit. Chạy trên khung Ngày (EMA10, EMA20, MA50, Volume, nền giá, hỗ trợ/kháng cự)
và khung Tuần (MA10 tuần, MA20 tuần) do engine.add_indicators đã tính sẵn.

Mỗi mã được xếp vào ĐÚNG MỘT trạng thái theo thứ tự ưu tiên cố định (xem classify):
    1) Thiếu dữ liệu      -> "Không có điểm mua"
    2) Tăng quá đà        -> danh sách cảnh báo không mua đuổi
    3) Không có điểm mua  -> loại hoàn toàn
    4) Hạ tỷ trọng        -> danh sách cảnh báo rủi ro / bán
    5) Đang phục hồi      -> danh sách theo dõi phục hồi riêng
    6) 9 trạng thái chờ mua (nhóm 1 -> 2 -> 3)
Chỉ nhóm 6 mới vào tab "Chờ mua".
"""
from __future__ import annotations

import html as _html

import numpy as np
import pandas as pd

import engine as E
import rsi_divergence as DV

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
    "sell_drop": -3.0,          # nến đỏ giảm >= x% trong 1 phiên mà đóng dưới EMA20 => cảnh báo bán
    "sell_drop_vol": 1.2,       # ...kèm khối lượng >= x lần MA20 Vol (hoặc thủng EMA20 lần đầu)
    "leg_lookback": 120,        # tìm đáy của đợt tăng trong N phiên gần nhất
    "leg_min_gain": 30.0,       # đợt tăng từ đáy lên đỉnh tối thiểu x% mới xét nhịp chỉnh
    "leg_max_age": 30,          # đỉnh phải nằm trong N phiên gần nhất (đợt tăng còn "nóng")
    "leg_min_dd": 8.0,          # nhịp chỉnh từ đỉnh phải >= x% (và sâu hơn mọi nhịp chỉnh trước trong đợt tăng)
    "sell_max_dd": 20.0,        # đã giảm >= x% từ đỉnh (leg_lookback phiên) thì bán đã quá muộn: giữ nhãn "Không có điểm mua", không ghi BÁN
    "base_since_low": 5,        # tích lũy đáy: đã >= x phiên không thủng đáy thấp nhất 60 phiên
    "base_bounce": 3.0,         # ...và đã hồi >= x% từ đáy đó
    "base_upvol": 1.1,          # ...khối lượng phiên tăng / phiên giảm (10 phiên) >= x
    "base_vol5": 1.0,           # ...khối lượng 5 phiên >= x lần MA20 Vol (vol tăng dần trở lại)
    "base_min_signals": 3,      # cần >= x trong 4 dấu hiệu: upvol (bắt buộc), vol5, A/D tăng (hoặc MFI >= 40), giá trên EMA10
    "profit_zone_gain": 50.0,   # giá hiện tại đã tăng >= x% so với đáy thấp nhất leg_lookback phiên (và còn trên MA50) => nhãn "CHỐT LỜI", không mua mới
    "take_profit_gain": 20.0,   # tín hiệu bán + đã tăng >= x% từ đáy + còn trên MA50 => nhãn "CHỐT LỜI"; còn lại => "BÁN"
    "sell_big_drop": -4.5,      # nến đỏ giảm >= x% đóng dưới EMA20 => cảnh báo bán bất kể khối lượng
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
    "CHỐT LỜI":                ("#FFD9A0", "#7A3E00"),
    "BÁN":                     ("#D92D4A", "#FFFFFF"),
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
    reason = reason or ""
    if reason.startswith("CHỐT LỜI"):          # lý do do classify ghi tiền tố "CHỐT LỜI: " / "BÁN: "
        label = "CHỐT LỜI"
    elif reason.startswith("BÁN"):
        label = "BÁN"
    elif state == WEAKENING and "tín hiệu bán" in reason:
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


def _leg_structure(g: pd.DataFrame) -> dict:
    """Cấu trúc đợt tăng gần nhất: đáy thấp nhất trong leg_lookback phiên -> đỉnh cao nhất sau đáy.
    leg_gain   = % tăng từ đáy lên đỉnh.
    leg_dd     = % chỉnh từ đỉnh (giá cao nhất) xuống giá đóng cửa hiện tại.
    leg_prev_pb = nhịp chỉnh sâu nhất TRƯỚC đỉnh, trong cùng đợt tăng (đo từ đỉnh chạy xuống giá thấp nhất, như cách đo trên chart).
    leg_age    = số phiên từ đỉnh tới nay."""
    n = min(len(g), CFG["leg_lookback"])
    h = g["Giá cao nhất"].to_numpy(float)[-n:]
    l = g["Giá thấp nhất"].to_numpy(float)[-n:]
    c = float(g["Giá đóng cửa"].iat[-1])
    i_lo = int(np.argmin(l))
    i_pk = i_lo + int(np.argmax(h[i_lo:]))
    peak, low = float(h[i_pk]), float(l[i_lo])
    run = np.maximum.accumulate(h[i_lo:i_pk + 1])
    pbs = (run - l[i_lo:i_pk + 1]) / run * 100
    return {"leg_gain": (peak / low - 1) * 100 if low > 0 else np.nan,
            "leg_dd": (1 - c / peak) * 100 if peak > 0 else np.nan,
            "leg_prev_pb": float(pbs.max()) if len(pbs) else 0.0,
            "leg_age": n - 1 - i_pk, "leg_peak": peak, "leg_low": low}


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
    f.update(_leg_structure(g))
    # dấu hiệu tích lũy đáy sau đà giảm
    low60 = g["Giá thấp nhất"].tail(60)
    f["low60"] = float(low60.min())
    f["since_low"] = len(low60) - 1 - int(np.argmin(low60.to_numpy(float)))
    f["bounce_low"] = (c / f["low60"] - 1) * 100 if f["low60"] > 0 else np.nan
    d10, v10 = c_s.diff().tail(10), v.tail(10)
    f["upvol"] = _f(v10[d10 > 0].sum() / v10[d10 < 0].sum()) if v10[d10 < 0].sum() > 0 else (np.inf if v10[d10 > 0].sum() > 0 else np.nan)
    f["lost_ema20"] = bool(len(g) > 2 and c < float(ema20.iat[-1]) and float(c_s.iat[-2]) >= float(ema20.iat[-2]))   # phiên này vừa đóng thủng EMA20
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


def sell_action_of(reason) -> str:
    """\"BÁN\" / \"CHỐT LỜI\" nếu lý do do classify ghi tiền tố tương ứng, ngược lại rỗng. Dùng cho trang Bán / Chốt lời."""
    r = str(reason or "")
    return "CHỐT LỜI" if r.startswith("CHỐT LỜI") else "BÁN" if r.startswith("BÁN") else ""


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


def _rsi_confirms_uptrend(g: pd.DataFrame, w: pd.DataFrame | None) -> dict | None:
    """Phân kỳ ẩn tăng RSI (nhãn \"Xác nhận tiếp diễn · XU HƯỚNG TĂNG\") còn hiệu lực trên khung Ngày hoặc Tuần.
    Cùng nguồn với khối cảnh báo phân kỳ hiển thị trên thẻ (rsi_divergence.detect), nên thẻ và trạng thái luôn khớp nhau."""
    for tf, df in (("D", g), ("W", w)):
        if df is None or len(df) == 0:
            continue
        try:
            for sg in DV.detect(df, tf):
                if sg["kind"] == "hid_bull":
                    return sg
        except Exception:
            continue
    return None


def _rsi_bearish(g: pd.DataFrame, w: pd.DataFrame | None) -> dict | None:
    """Phân kỳ RSI xấu (hướng giảm: thường giảm, phóng đại giảm, ẩn giảm) còn hiệu lực trên khung Ngày hoặc Tuần."""
    for tf, df in (("W", w), ("D", g)):
        if df is None or len(df) == 0:
            continue
        try:
            for sg in DV.detect(df, tf):
                if sg["dir"] == "down":
                    return sg
        except Exception:
            continue
    return None


def _classify_base(g: pd.DataFrame, w: pd.DataFrame | None, r: pd.Series) -> dict:
    """Phân loại theo 9 trạng thái chờ mua (chưa xét RSI). Kết quả có thêm khóa _zone = vùng mua theo cấu trúc (hỗ trợ / kháng cự)."""
    ctx: dict = {}

    def out(state, reason, alt=None, **lv):
        """alt = vùng mua dự phòng (dict từ _levels) cho trạng thái không có vùng mua riêng: chỉ dùng khi được nâng lên Điểm mua đẹp."""
        zone = (lv["Vùng mua từ"], lv["Vùng mua đến"]) if lv else None
        if lv and ctx.get("fc"):
            lv = _chart_levels(lv, ctx["fc"])
        extra = {}
        if alt is not None:
            zone = (alt["Vùng mua từ"], alt["Vùng mua đến"])
            extra["_alt"] = _chart_levels(alt, ctx["fc"]) if ctx.get("fc") else alt
        return {"Trạng thái": state, "Danh sách": STATE_GROUP[state], "Lý do": reason, "_zone": zone, **extra, **lv}

    if len(g) < CFG["min_bars"] or pd.isna(g["MA50"].iat[-1]):
        return out(NO_BUY, f"Chưa đủ dữ liệu (cần ≥ {CFG['min_bars']} phiên để tính MA50)")
    f = _features(g, w, r)
    ctx["fc"] = E.forecast_levels(f["c"], _f(g["ATR"].iat[-1]), 1)
    c, wk = f["c"], ("" if f["has_week"] else " (chưa đủ dữ liệu tuần)")
    ext20 = (c / f["ema20"] - 1) * 100
    gain_now = (c / f["leg_low"] - 1) * 100 if f["leg_low"] > 0 else 0.0      # % đã tăng từ đáy thấp nhất leg_lookback phiên tới giá hiện tại

    # ---------- 4 trạng thái ngoài danh sách chờ mua
    if (ext20 >= CFG["ob_ext_ema20"] or (not np.isnan(f["gain10"]) and f["gain10"] >= CFG["ob_gain10"])
            or (ext20 >= CFG["ob_ext_soft"] and f["srsi"] >= 90)):
        tp = f"CHỐT LỜI: đã tăng {gain_now:.0f}% từ đáy; " if gain_now >= CFG["profit_zone_gain"] and c >= f["ma50"] else ""
        return out(OVERBOUGHT, tp + f"Giá cao hơn EMA20 {ext20:.1f}%, tăng {f['gain10']:.1f}% trong 10 phiên: không mua đuổi")

    down50 = not np.isnan(f["ma50_10"]) and f["ma50"] < f["ma50_10"]
    below_w = f["has_week"] and c < f["wma20"]
    crash = not np.isnan(f["drop5"]) and f["drop5"] <= CFG["crash5"] and c < f["ema20"]
    bearish = f["pv_recent"] & BEARISH_PV

    # ---------- CẢNH BÁO BÁN cho mã còn khỏe (chưa nằm dưới MA50 đang dốc xuống). Đặt TRƯỚC nhóm "Không có điểm mua"
    # vì nhóm đó bị loại khỏi mọi danh sách: mã đang Điểm mua đẹp mà rơi mạnh phải hiện ở Danh sách cảnh báo, không được biến mất.
    dd_hi = (1 - c / float(g["Giá cao nhất"].tail(CFG["leg_lookback"]).max())) * 100
    deep = dd_hi >= CFG["sell_max_dd"]          # rơi quá sâu: không báo BÁN / CHỐT LỜI nữa
    healthy = not (c < f["ma50"] and down50) and not deep
    # CHỐT LỜI: còn trên MA50 và đã có lãi lớn từ đáy (xu hướng chưa gãy nhưng đà đang yếu); BÁN: các trường hợp còn lại
    act = "CHỐT LỜI" if (c >= f["ma50"] and f["leg_gain"] >= CFG["take_profit_gain"]) else "BÁN"
    vol_now = _nz(f["vol_now"])
    # (1) nến đỏ mạnh đóng dưới EMA20 (không cần thỏa đủ điều kiện "Xả mạnh" của engine)
    sell_candle = (c < f["ema20"] and (
        f["chg"] <= CFG["sell_big_drop"]
        or (f["chg"] <= CFG["sell_drop"] and (vol_now >= CFG["sell_drop_vol"] or f["lost_ema20"]))))
    # (2) đợt tăng >= 30% từ đáy, nhịp chỉnh từ đỉnh sâu hơn MỌI nhịp chỉnh trước trong đợt tăng và giá thủng EMA20
    leg_break = (c < f["ema20"] and f["leg_gain"] >= CFG["leg_min_gain"] and f["leg_age"] <= CFG["leg_max_age"]
                 and f["leg_dd"] >= CFG["leg_min_dd"] and f["leg_dd"] > f["leg_prev_pb"])
    if healthy:
        if bearish:
            return out(WEAKENING, f"{act}: có tín hiệu bán trong 3 phiên ({', '.join(E.PV_LABEL[b_] for b_ in sorted(bearish))})")
        if leg_break:
            return out(WEAKENING, f"{act}: giá chỉnh {f['leg_dd']:.1f}% từ đỉnh {f['leg_peak']:.2f}, sâu hơn mọi nhịp chỉnh trước "
                                  f"(tối đa {f['leg_prev_pb']:.1f}%) trong đợt tăng {f['leg_gain']:.0f}% từ đáy, đã thủng EMA20: hạ tỷ trọng / không mua mới")
        if sell_candle:
            return out(WEAKENING, f"{act}: nến đỏ {f['chg']:.1f}%, đóng cửa dưới EMA20 ({f['ema20']:.2f}), "
                                  f"khối lượng {vol_now:.1f} lần MA20 Vol: hạ tỷ trọng / không mua mới")
        if crash:
            return out(WEAKENING, f"{act}: rơi {f['drop5']:.1f}% trong 5 phiên, đóng cửa dưới EMA20 ({f['ema20']:.2f}): hạ tỷ trọng / không mua mới")

    # ---------- Vùng chốt lời: đã tăng >= 50% từ đáy mà xu hướng chưa gãy (còn trên MA50) => không còn là điểm mua, chuyển sang CHỐT LỜI
    if gain_now >= CFG["profit_zone_gain"] and c >= f["ma50"] and not deep:
        return out(OVERBOUGHT, f"CHỐT LỜI: đã tăng {gain_now:.0f}% từ đáy {f['leg_low']:.2f} (trong {CFG['leg_lookback']} phiên), giá {c:.2f} "
                               f"cách đỉnh {f['leg_dd']:.1f}%: không mua mới, cân nhắc chốt lời từng phần và dời cắt lỗ lên")

    # ---------- Rơi sâu nhưng có dấu hiệu tích lũy / phục hồi => "Đang phục hồi" (theo dõi), không xếp vào "Không có điểm mua"
    if deep:
        held = f["since_low"] >= CFG["base_since_low"] and not np.isnan(f["bounce_low"]) and f["bounce_low"] >= CFG["base_bounce"]
        sig = {"upvol": bool(f["upvol"] >= CFG["base_upvol"]),
               "vol5": bool(not np.isnan(f["vol5"]) and f["vol5"] >= CFG["base_vol5"]),
               "flow": bool(f["ad_up"] or (not np.isnan(f["mfi"]) and f["mfi"] >= 40)),
               "price": bool(c > f["ema10"])}
        # bắt buộc: giữ được đáy + khối lượng phiên tăng > phiên giảm (có lực mua ròng); còn lại cần thêm tối thiểu số dấu hiệu quy định
        if held and sig["upvol"] and sum(sig.values()) >= CFG["base_min_signals"]:
            uv = "∞" if np.isinf(f["upvol"]) else f"{f['upvol']:.1f}"
            return out(RECOVERING, f"Đã giảm {dd_hi:.0f}% từ đỉnh nhưng có dấu hiệu tích lũy: {f['since_low']} phiên không thủng đáy {f['low60']:.2f}, "
                                   f"hồi {f['bounce_low']:.1f}% từ đáy, KL phiên tăng/phiên giảm {uv}, KL 5 phiên {f['vol5']:.1f} lần MA20 Vol "
                                   f"({sum(sig.values())}/4 dấu hiệu): theo dõi, chờ vượt MA50 / kháng cự để xác nhận nhịp tăng mới")

    # ---------- Không có điểm mua / Đứng ngoài (loại khỏi mọi danh sách)
    if (c < f["ma50"] and down50 and c < f["ema20"] < f["ma50"] and not f["higher_low"] and (below_w or not f["has_week"])) or crash:
        why = f"Rơi {f['drop5']:.1f}% trong 5 phiên, dưới EMA20" if crash else "Dưới EMA20 < MA50 đang dốc xuống, chưa tạo đáy sau cao hơn"
        if deep:
            return out(NO_BUY, why + f" (đã giảm {dd_hi:.0f}% từ đỉnh): đứng ngoài")
        return out(NO_BUY, "BÁN: " + why + ": không mua, cân nhắc thoát vị thế")

    if (bearish or (c < f["ma50"] and f["ema10"] < f["ema20"] and not f["higher_low"])
            or (c < f["ema20"] < f["ma50"] and f["has_week"] and f["wma10"] < f["wma20"])):
        why = (f"{'' if deep else 'BÁN: '}có tín hiệu bán trong 3 phiên ({', '.join(E.PV_LABEL[b] for b in sorted(bearish))})" if bearish
               else "Giá dưới MA50, EMA10 < EMA20, chưa có đáy sau cao hơn: xu hướng suy yếu")
        return out(WEAKENING, why)

    lo20_bounce = (c / f["lo20"] - 1) * 100
    if (c < f["ma50"] and lo20_bounce >= CFG["recover_bounce"] and c > f["ema10"]):
        near = [x for x in _support_candidates(f) if 0 <= (c / x[1] - 1) * 100 <= CFG["support_touch"]]
        alt = _levels(f, max(near, key=lambda x: x[1])[1]) if near else None
        return out(RECOVERING, f"Hồi {lo20_bounce:.1f}% từ đáy 20 phiên nhưng chưa vượt MA50 ({f['ma50']:.2f}): chờ xác nhận phá MA/kháng cự", alt=alt)

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


# Các trạng thái được phép nâng lên Điểm mua đẹp
UPGRADABLE = tuple(STATES_BY_GROUP[G2]) + tuple(STATES_BY_GROUP[G3]) + (RECOVERING,)   # Tăng quá đà / Suy yếu / Không có điểm mua: giữ nguyên (cảnh báo rủi ro)


def classify(g: pd.DataFrame, w: pd.DataFrame | None, r: pd.Series) -> dict:
    """Trả về {state, group, reason, + vùng mua/cắt lỗ/mục tiêu} cho một mã.

    Quy tắc nâng cấp: mã đang ở bất kỳ trạng thái chờ mua nào thuộc nhóm "Sắp có điểm mua" / "Theo dõi thêm" mà
    (1) RSI có phân kỳ ẩn tăng (\"Xác nhận tiếp diễn · XU HƯỚNG TĂNG\") còn hiệu lực và (2) giá đang nằm trong vùng mua
    (theo hỗ trợ / kháng cự của trạng thái đó, cho phép lệch 1.5% bên dưới như quy tắc test hỗ trợ) -> \"Điểm mua đẹp\"."""
    res = _classify_base(g, w, r)
    zone, alt = res.pop("_zone", None), res.pop("_alt", None)
    bear = _rsi_bearish(g, w)
    tfn = lambda sg: "tuần" if sg["tf"] == "W" else "ngày"
    if bear is not None:
        # RSI xấu: không nâng cấp; mã đang là Điểm mua đẹp / Đã có tín hiệu mua thì hạ xuống Theo dõi điểm mua
        if res["Trạng thái"] in (GOOD_ENTRY, BUY_SIGNAL):
            res["Lý do"] = (f"{str(res['Lý do']).rstrip('.')}; nhưng RSI cảnh báo đảo chiều ({bear['name'].lower()} khung {tfn(bear)}): "
                            f"chờ RSI hết cảnh báo mới vào")
            res["Trạng thái"], res["Danh sách"] = WATCH, STATE_GROUP[WATCH]
        return res
    if res["Trạng thái"] in UPGRADABLE and zone is not None:
        lo, hi = zone
        c = float(g["Giá đóng cửa"].iat[-1])
        if pd.notna(lo) and pd.notna(hi) and lo * 0.985 <= c <= hi:
            dv = _rsi_confirms_uptrend(g, w)
            if dv is not None:
                res["Lý do"] = (f"{str(res['Lý do']).rstrip('.')}; giá đang trong vùng mua ({lo:.2f} – {hi:.2f}) và RSI phân kỳ ẩn tăng "
                                f"khung {tfn(dv)} xác nhận tiếp diễn xu hướng tăng")
                res["Trạng thái"], res["Danh sách"] = GOOD_ENTRY, STATE_GROUP[GOOD_ENTRY]
                if alt:
                    res.update(alt)
    return res


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
        res["Hành động bán"] = sell_action_of(res.get("Lý do"))
        try:
            res["Tăng từ đáy %"] = _leg_structure(g.reset_index(drop=True))["leg_gain"]
        except Exception:
            res["Tăng từ đáy %"] = np.nan
        can, t1 = res.get("Cản gần", np.nan), res.get("Mục tiêu 1", np.nan)
        if res["Hành động"] == "Vào ngay" and pd.notna(can) and pd.notna(t1) and can < t1:
            res["Ghi chú hành động"] += f"; lưu ý cản gần {can:.2f} (+{(can / r['Giá'] - 1) * 100:.1f}%) thấp hơn Mục tiêu 1"
        rows.append({"Mã": code, "Giá": r["Giá"], "Chg %": r.get("Chg_%", np.nan), "Score": r["Score"], "RS20": r["RS20"], "Nhóm": r.get("Nhóm", ""), **res})
    cols = ["Mã", "Giá", "Chg %", "Score", "RS20", "Nhóm", "Trạng thái", "Danh sách", "Lý do", "Hành động", "Hành động bán", "Tăng từ đáy %", "Ghi chú hành động",
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
.wb-name{font-size:14px;color:var(--txt);opacity:.85;margin:-6px 0 14px;line-height:1.4}
.wb-kv{display:grid;grid-template-columns:1.3fr 1fr 1fr;gap:14px 16px;border-top:1px solid var(--line);padding-top:14px;margin-bottom:14px}
.wb-kv span{display:block;font-size:13.5px;font-weight:500;color:var(--muted);margin-bottom:5px}
.wb-kv b{display:block;font-size:17px;font-weight:800;color:var(--txt2);line-height:1.3;overflow-wrap:anywhere}
.wb-kv .wide{grid-column:1 / span 2}
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
/* Bảng kết quả */
.wbt-wrap{overflow-x:auto;border:1px solid var(--line);border-radius:10px;background:var(--card)}
.wbt{border-collapse:collapse;width:100%;min-width:1250px;font-size:13.5px;color:var(--txt)}
.wbt th{position:sticky;top:0;background:var(--bg2);color:var(--txt2);font-weight:700;text-align:center;padding:11px 8px;
  border:1px solid var(--line);line-height:1.3;white-space:normal}
.wbt td{padding:11px 8px;border:1px solid var(--line);text-align:center;vertical-align:middle}
.wbt tbody tr:hover td{background:var(--line2)}
.wbt .code{font-weight:800;color:var(--accent);white-space:nowrap}
.wbt td.na{color:var(--muted)}
.wbt a.more{color:var(--accent);font-weight:700;text-decoration:none;white-space:nowrap;padding:4px 8px;border-radius:6px}
.wbt a.more:hover{background:var(--line2);text-decoration:underline}
[class*="st-key-wbcard-"].wb-focus{box-shadow:0 0 0 2px var(--accent),0 2px 12px var(--shadow)}
.wbt .st{white-space:nowrap;font-weight:700;text-align:left}
.wbt .dot{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:7px;vertical-align:middle}
.wbt .dot.g{background:var(--green)}.wbt .dot.a{background:#E5B34C}.wbt .dot.n{background:var(--muted)}
.wbt td.sl{background:rgba(224,82,96,.16);color:var(--red);font-weight:700}
.wbt td.tp{background:rgba(37,168,121,.16);color:var(--green);font-weight:700}
.wbt td small{display:block;font-weight:600;font-size:11.5px;opacity:.9}
.wbt .up{color:var(--green);font-weight:700}.wbt .down{color:var(--red);font-weight:700}
.wbt .go{display:block;font-size:11.5px;color:var(--muted);font-weight:600;margin-top:2px}
""".replace("BOXBG", box)


def table_html(d: pd.DataFrame, group: str, sector_of=None, ma_of=None) -> str:
    """Bảng kết quả của một nhóm (cùng nội dung với thẻ). sector_of(mã) -> tên ngành; ma_of(mã) -> {20|50|200: (giá trị MA, % giá so với MA)}."""
    esc = _html.escape
    px = lambda x: "—" if pd.isna(x) else f"{x:,.2f}"
    pc = lambda x: "" if pd.isna(x) else f"{x:+.1f}%"
    heads = ["Mã CP", "Ngành", "Vùng mua", "Giá hiện tại", "Trạng thái", "MA20", "MA50", "MA200", "Cắt lỗ",
             "Giá mục tiêu 1", "Giá mục tiêu 2", "% Lợi nhuận kỳ vọng", "Xem thêm"]
    out = ['<div class="wbt-wrap"><table class="wbt"><thead><tr>' + "".join(f"<th>{h}</th>" for h in heads) + "</tr></thead><tbody>"]
    for _, r in d.iterrows():
        state = str(r["Trạng thái"])
        chg = r.get("Chg %", np.nan)
        cc = "up" if pd.notna(chg) and chg > 0 else "down" if pd.notna(chg) and chg < 0 else ""
        zone = "—" if pd.isna(r.get("Vùng mua từ")) else f'{px(r["Vùng mua từ"])} – {px(r["Vùng mua đến"])}'
        act = r.get("Hành động")
        act_html = f'<span class="go">{"✔ Vào được ngay" if act == "Vào ngay" else "⏳ Chờ mua"}</span>' if pd.notna(r.get("Vùng mua từ")) else ""
        mas = (ma_of(str(r["Mã"])) if ma_of else None) or {}

        def ma_cell(n):
            v = mas.get(n)
            if not v or pd.isna(v[0]):
                return '<td class="na">—</td>'
            cls = "up" if v[1] > 0.05 else "down" if v[1] < -0.05 else ""
            return f'<td><b>{v[0]:,.2f}</b><small class="{cls}">{"Trên" if v[1] > 0 else "Dưới"} MA {v[1]:+.1f}%</small></td>'
        l1, l2 = r.get("Lời 1 %", np.nan), r.get("Lời 2 %", np.nan)
        gain = "—" if pd.isna(l1) and pd.isna(l2) else " / ".join(f"{x:.1f}%" for x in (l1, l2) if pd.notna(x))
        out.append(
            f'<tr><td class="code">{esc(str(r["Mã"]))}</td>'
            f'<td>{esc(str(sector_of(str(r["Mã"])) if sector_of else r.get("Nhóm", "")))}</td>'
            f'<td>{zone}{act_html}</td>'
            f'<td><b>{px(r["Giá"])}</b>' + (f'<small class="{cc}">{chg:+.2f}%</small>' if pd.notna(chg) else "") + '</td>'
            f'<td class="st"><span class="dot {_BADGE.get(group, "n")}"></span>{esc(BADGE_TEXT.get(state, state))}</td>'
            + ma_cell(20) + ma_cell(50) + ma_cell(200) +
            f'<td class="sl">{px(r["Cắt lỗ"])}<small>{pc(r["Cắt lỗ %"])}</small></td>'
            f'<td class="tp">{px(r["Mục tiêu 1"])}<small>{pc(r["Lời 1 %"])}</small></td>'
            f'<td class="tp">{px(r["Mục tiêu 2"])}<small>{pc(r["Lời 2 %"])}</small></td>'
            f'<td class="up">{gain}</td>'
            f'<td><a class="more" href="?wbgo={esc(str(r["Mã"]))}" target="_self">Xem thêm</a></td></tr>')
    out.append("</tbody></table></div>")
    return "".join(out)


def _sentence(t: str) -> str:
    """Viết hoa đầu câu và thêm dấu chấm cuối câu."""
    t = str(t).strip()
    if not t:
        return t
    t = t[0].upper() + t[1:]
    return t if t[-1] in ".!?" else t + "."


BADGE_TEXT = {BUY_SIGNAL: "ĐIỂM MUA ĐẸP"}     # chữ hiển thị trên thẻ (tên trạng thái dùng để lọc giữ nguyên)


def card_html(r: pd.Series, group: str, meta: dict | None = None, div_html: str = "", ma_html: str = "") -> str:
    """HTML phần thông tin của thẻ (nút "Xem biểu đồ" do Streamlit vẽ riêng bên dưới).

    meta = {"Tên", "Ngành", "Vốn hóa", "P/B", "ROE"} đã định dạng sẵn (xem app._wb_meta).
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
            f'<div class="wb-name">{esc(str((meta or {}).get("Tên") or "Chưa có tên công ty"))}</div>'
            f'<div class="wb-kv">'
            f'<div><span>Score · RS</span><b>{r["Score"]:.1f} · {px(r["RS20"])}</b></div>'
            f'<div><span>P/B</span><b>{esc(str((meta or {}).get("P/B", "Chưa có")))}</b></div>'
            f'<div><span>ROE</span><b>{esc(str((meta or {}).get("ROE", "Chưa có")))}</b></div>'
            f'<div class="wide"><span>Ngành</span><b>{esc(str((meta or {}).get("Ngành", "Chưa có")))}</b></div>'
            f'<div><span>Vốn hóa</span><b>{esc(str((meta or {}).get("Vốn hóa", "Chưa có")))}</b></div></div>')
    html += ma_html       # MA20/50/200 + chip Ngắn hạn/Trung hạn (app._ma_summary_html, cùng thẻ ở Bộ lọc)
    html += f'<div class="wb-note">{esc(_sentence(r["Lý do"]))}</div>'
    html += div_html      # cảnh báo phân kỳ RSI (rsi_divergence.html), rỗng nếu không có tín hiệu
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
