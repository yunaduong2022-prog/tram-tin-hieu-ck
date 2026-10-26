"""Phân loại trạng thái giá và kế hoạch giao dịch (điểm mua / cắt lỗ / mục tiêu) dựa trên Dual Ichimoku, Supertrend, khối lượng và cấu trúc giá.

Các trạng thái (ưu tiên từ trên xuống, xem classify()):
  BOTTOM    Bùng nổ sau khi GIẢM SÂU ≥ 40% rồi đi ngang (kiểu VSC)
  BASE_HL   Bùng nổ sau tích lũy ĐÁY NÂNG + từng cạn cung (kiểu ORS)
  BREAKOUT  Bùng nổ thường: vượt đỉnh 25 phiên kèm khối lượng ≥ 1,5 lần MA10
  WATCH     Theo dõi sớm: đáy nâng, đi ngang, cạn cung, giá sát đỉnh vùng nhưng chưa vượt
  TREND     Xu hướng tăng: giá trên mây, trên cả Tenkan 65 và Kijun 129, Supertrend tăng
  RANGE     Giữa Tenkan và Kijun: đường trên là kháng cự, đường dưới là hỗ trợ, chưa có lợi thế
  WEAK      Dưới mây, dưới cả hai đường, Supertrend giảm
  NEUTRAL   Còn lại

Mây dùng bộ 1 của Dual Ichimoku (9-17-26, dịch 25 nến); Tenkan 65 / Kijun 129 là bộ 2; thông số ở ichimoku_dual.CFG.
Mọi chỉ báo có trạng thái nhớ (Supertrend) đều tính trên TOÀN BỘ lịch sử rồi mới lấy nến cuối.
Chỉ để nghiên cứu, không phải khuyến nghị đầu tư.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import ichimoku_dual as IDU
import rsi_divergence as DV
import supertrend as SPT

H, L, C, O, V = "Giá cao nhất", "Giá thấp nhất", "Giá đóng cửa", "Giá mở cửa", "Khối lượng khớp lệnh"

# Tham số (đã chọn qua backtest, xem README mục "Phân loại trạng thái")
BASE_WIN = 25          # số phiên của hộp đi ngang liền trước nến bùng nổ
BASE_MAX_RANGE = 0.20  # biên độ tối đa của hộp (cao nhất / thấp nhất - 1)
DEEP_DD = -0.40        # "giảm sâu": đáy 60 phiên cách đỉnh 250 phiên từ 40% trở lên
VOL_BREAK = 1.5        # khối lượng bùng nổ ≥ 1,5 lần MA10 (của 10 phiên trước)
ACTIVE_BARS = 3        # tín hiệu bùng nổ còn hiệu lực trong 3 phiên
SL_ATR = 2.0           # cắt lỗ = vào - 2 ATR(14); xem choose_stop()
SL_MAX_PCT = 0.12      # rủi ro tối đa mỗi lệnh (không đặt cắt lỗ xa hơn mức này)
SL_MIN_PCT = 0.03      # và không chặt hơn mức này (tránh bị quét bởi nhiễu thường ngày)

LABEL = {
    "BOTTOM": "Bùng nổ sau khi giảm sâu (đáy)",
    "BASE_HL": "Bùng nổ sau tích lũy đáy nâng",
    "BREAKOUT": "Bùng nổ vượt đỉnh + khối lượng",
    "WATCH": "Theo dõi sớm: đang tích lũy sát đỉnh vùng",
    "TREND": "Xu hướng tăng",
    "RANGE": "Giữa Tenkan và Kijun: chờ",
    "WEAK": "Yếu: dưới mây và dưới Tenkan/Kijun",
    "NEUTRAL": "Trung tính",
}
# màu thẻ: green / amber / gray / red (dùng cho tag() của app)
TAG = {"BOTTOM": "green", "BASE_HL": "green", "BREAKOUT": "green", "WATCH": "amber", "TREND": "green",
       "RANGE": "gray", "WEAK": "red", "NEUTRAL": "gray"}


def features(g: pd.DataFrame) -> pd.DataFrame:
    """Đặc trưng theo từng nến (g đã sắp xếp theo ngày, đủ lịch sử). Trả về DataFrame cùng index với g."""
    h, l, c, v = (pd.to_numeric(g[k], errors="coerce") for k in (H, L, C, V))
    D = IDU._donchian
    cfg = IDU.CFG
    off = int(cfg["disp1"]) - 1
    a = ((D(h, l, cfg["t1"]) + D(h, l, cfg["k1"])) / 2).shift(off)
    b = D(h, l, cfg["b1"]).shift(off)
    f = pd.DataFrame(index=g.index)
    f["c"] = c
    f["cloud_top"], f["cloud_bot"] = np.maximum(a, b), np.minimum(a, b)
    t, k = D(h, l, cfg["t2"]), D(h, l, cfg["k2"])
    f["tenkan"], f["kijun"] = t, k
    f["tk_hi"], f["tk_lo"] = np.maximum(t, k), np.minimum(t, k)
    st = SPT.compute(g)
    f["st_up"] = st["ST_trend"].to_numpy() == 1
    f["st_line"] = np.where(f["st_up"], st["ST_up"], st["ST_dn"])
    f["st_buy"] = st["ST_buy"].to_numpy()
    f["atr"] = SPT._atr(h.to_numpy(float), l.to_numpy(float), c.to_numpy(float), 14, True)
    f["vr"] = v / v.rolling(10).mean().shift(1)
    # cấu trúc giá
    f["res25"] = h.shift(1).rolling(BASE_WIN).max()
    f["low25"] = l.shift(1).rolling(BASE_WIN).min()
    f["res60"] = h.shift(1).rolling(60).max()
    rng = f["res25"] / f["low25"] - 1
    f["base"] = rng <= BASE_MAX_RANGE
    f["deep"] = (l.rolling(60).min() / h.rolling(250, min_periods=120).max() - 1) <= DEEP_DD
    f["hl"] = l.rolling(20).min() > l.shift(20).rolling(40).min() * 1.01
    dry5 = (v.rolling(5).mean() / v.rolling(50).mean()) < 0.7
    f["dry10"] = dry5.rolling(10).max().fillna(0).astype(bool)
    box60 = (h.rolling(60).max() / l.rolling(60).min() - 1) <= 0.30
    f["watch"] = f["hl"] & box60 & f["dry10"] & (c >= 0.90 * f["res60"]) & (c <= f["res60"])
    f["brk"] = (c > f["res25"]) & (f["vr"] >= VOL_BREAK)
    # loại bùng nổ
    f["bottom"] = f["brk"] & f["base"] & f["deep"]
    f["base_hl"] = f["brk"] & f["hl"] & f["dry10"] & ~f["bottom"]
    f["breakout"] = f["brk"] & ~f["bottom"] & ~f["base_hl"]
    f["trend"] = (c > f["cloud_top"]) & (c > f["tk_hi"]) & f["st_up"]
    f["range"] = (c < f["tk_hi"]) & (c > f["tk_lo"])
    f["weak"] = (c < f["cloud_bot"]) & (c < f["tk_lo"]) & ~f["st_up"]
    return f


def choose_stop(entry: float, f_row: pd.Series, kind: str) -> float:
    """Cắt lỗ theo loại tín hiệu. Mặc định entry - SL_ATR*ATR, kẹp trong [SL_MIN_PCT, SL_MAX_PCT] rủi ro.
    BOTTOM / BASE_HL / WATCH: không đặt trên đáy hộp (đáy 25 phiên - 1%) nếu đáy hộp nằm trong giới hạn rủi ro."""
    atr = f_row["atr"]
    stop = entry - SL_ATR * atr if pd.notna(atr) else entry * (1 - SL_MAX_PCT)
    if kind in ("BOTTOM", "BASE_HL", "WATCH") and pd.notna(f_row["low25"]):
        box = f_row["low25"] * 0.99
        if box < entry and (entry - box) / entry <= SL_MAX_PCT:
            stop = min(stop, box)                      # đặt dưới đáy hộp
    if kind == "TREND" and pd.notna(f_row["st_line"]) and f_row["st_line"] < entry:
        stop = max(stop, f_row["st_line"])             # xu hướng tăng: lấy đường Supertrend nếu chặt hơn
    stop = min(stop, entry * (1 - SL_MIN_PCT))
    stop = max(stop, entry * (1 - SL_MAX_PCT))
    return float(stop)


def classify(f: pd.DataFrame) -> pd.Series:
    """Trạng thái tại từng nến (xem đầu file về thứ tự ưu tiên)."""
    act = lambda s: s.rolling(ACTIVE_BARS, min_periods=1).max().fillna(0).astype(bool)
    cond = [act(f["bottom"]), act(f["base_hl"]), act(f["breakout"]), f["watch"], f["trend"], f["range"], f["weak"]]
    name = ["BOTTOM", "BASE_HL", "BREAKOUT", "WATCH", "TREND", "RANGE", "WEAK"]
    return pd.Series(np.select(cond, name, default="NEUTRAL"), index=f.index)


def bull_divergence(g: pd.DataFrame, f: pd.DataFrame) -> dict | None:
    """Phân kỳ tăng (thường hoặc 2 đáy bằng nhau) gần nhất còn hiệu lực ở khung Ngày, kèm trạng thái xác nhận bằng giá.
    Xác nhận = trong 10 phiên sau khi báo, có phiên đóng cửa vượt đỉnh 10 phiên trước VÀ (Supertrend tăng hoặc giá trên Kijun).
    Trả None nếu không có tín hiệu còn hiệu lực. state: 'pending' (chưa xác nhận) | 'confirmed' (đã xác nhận)."""
    prm = DV.PARAMS["D"]
    k = prm["k"]
    n = len(g)
    c = pd.to_numeric(g[C], errors="coerce").to_numpy(float)
    lo = pd.to_numeric(g[L], errors="coerce").to_numpy(float)
    hi = pd.to_numeric(g[H], errors="coerce").to_numpy(float)
    rsi = DV.rsi14(g[C]).to_numpy(float)
    piv = [i for i in DV._pivots(lo, k, max(DV.RSI_PERIOD, n - 160), False) if not np.isnan(rsi[i])]
    if len(piv) < 2:
        return None
    a, b = piv[-2], piv[-1]
    t = b + k                                                  # nến mà pivot đáy sau được xác nhận
    if t > n - 1 or not (prm["min_gap"] <= b - a <= prm["max_gap"]) or n - 1 - t > 10:
        return None
    pc, rc = DV._cmp(lo[b], lo[a], prm["eq"]), DV._rsi_cmp(rsi[b], rsi[a])
    if not (pc <= 0 and rc > 0):                               # giá đáy sau thấp hơn / bằng, RSI đáy sau cao hơn
        return None
    if n - 1 > t and lo[b + 1:].min() < lo[b] * (1 - prm["eq"]):
        return None                                            # giá đã thủng đáy sau: hết hiệu lực
    hh10 = pd.Series(hi).shift(1).rolling(10).max().to_numpy()
    kij, stup = f["kijun"].to_numpy(float), f["st_up"].to_numpy(bool)
    conf = next((j for j in range(t + 1, min(t + 11, n)) if c[j] > hh10[j] and (stup[j] or c[j] > kij[j])), None)
    return {"state": "confirmed" if conf is not None else "pending", "kind": "exa" if pc == 0 else "reg",
            "bars_ago": n - 1 - t, "conf_ago": (n - 1 - conf) if conf is not None else None, "level": float(hh10[-1]) if n else None}


def rsi_view(g: pd.DataFrame, f: pd.DataFrame, state: str) -> dict:
    """Động lượng RSI(14) kết hợp trạng thái giá + phân kỳ tăng có xác nhận (số liệu backtest 147 mã, khung Ngày, 20 phiên sau)."""
    rsi = float(DV.rsi14(g[C]).iloc[-1])
    uptrend = state in ("TREND", "BOTTOM", "BASE_HL", "BREAKOUT")
    if state == "WEAK" and rsi < 30:
        note, kind = ("Giá yếu và RSI quá bán: không bắt đáy. Nhóm này lịch sử sụt sâu nhất (trung vị −7,9% trong 20 phiên); "
                      "chỉ xét lại khi giá vượt Kijun và Supertrend tăng."), "red"
    elif uptrend and rsi >= 75:
        note, kind = ("Động lượng rất mạnh. Trong xu hướng tăng / bùng nổ, RSI ≥ 75 không phải cảnh báo bán: "
                      "lịch sử +4,5% sau 20 phiên, thắng 59% (mức nền +1,7%, 52%). Không bán chỉ vì RSI cao; theo dõi Supertrend để thoát."), "green"
    elif uptrend and rsi >= 65:
        note, kind = "Động lượng mạnh, phù hợp xu hướng tăng.", "green"
    elif uptrend and rsi >= 50:
        note, kind = "Động lượng bình thường (RSI 50–65): lịch sử +2,7%, thắng 55%.", "gray"
    elif uptrend:
        note, kind = "RSI dưới 50 dù giá đang mạnh: động lượng yếu hơn giá, thận trọng hơn.", "amber"
    else:
        note, kind = "RSI chỉ có ý nghĩa tốt khi giá đã ở xu hướng tăng hoặc vừa bùng nổ; ở trạng thái khác chưa thấy lợi thế.", "gray"
    div = bull_divergence(g, f)
    dnote = None
    if div and div["state"] == "pending":
        dnote = ("Có phân kỳ tăng nhưng giá CHƯA xác nhận: chưa phải tín hiệu mua. Lịch sử vào ngay lúc báo chỉ +1,1%, thắng 48%. "
                 f"Chờ giá đóng cửa vượt {div['level']:,.2f} (đỉnh 10 phiên) và Supertrend tăng hoặc giá trên Kijun.")
    elif div and div["state"] == "confirmed":
        dnote = ("Phân kỳ tăng đã được giá xác nhận (vượt đỉnh 10 phiên, Supertrend tăng hoặc giá trên Kijun): "
                 "lịch sử +2,6% sau 20 phiên, thắng 52%, cao hơn vào ngay lúc báo (+1,1%) nhưng chỉ hơn mức nền khoảng 1 điểm phần trăm.")
    return {"rsi": rsi, "rsi_note": note, "rsi_kind": kind, "div": div, "div_note": dnote}


def plan(g: pd.DataFrame) -> dict | None:
    """Trạng thái và kế hoạch cho nến cuối cùng của g. Trả None nếu chưa đủ lịch sử (cần ≥ 130 nến cho Kijun 129)."""
    if len(g) < 130:
        return None
    f = features(g)
    r = f.iloc[-1]
    if pd.isna(r["tk_hi"]) or pd.isna(r["cloud_top"]):
        return None
    state = classify(f).iloc[-1]
    c = float(r["c"])
    out = {"state": state, "label": LABEL[state], "tag": TAG[state], "close": c,
           "tenkan": float(r["tenkan"]), "kijun": float(r["kijun"]), "res": float(r["tk_hi"]), "sup": float(r["tk_lo"]),
           "cloud_top": float(r["cloud_top"]), "cloud_bot": float(r["cloud_bot"]), "st_line": float(r["st_line"]) if pd.notna(r["st_line"]) else None,
           "st_up": bool(r["st_up"]), "vr": float(r["vr"]) if pd.notna(r["vr"]) else None,
           "deep": bool(r["deep"]), "entry": None, "stop": None, "t1": None, "t2": None, "rr": None, "text": "", "bars_ago": None, "ext": None}
    # ngày của tín hiệu bùng nổ gần nhất còn hiệu lực
    if state in ("BOTTOM", "BASE_HL", "BREAKOUT"):
        col = {"BOTTOM": "bottom", "BASE_HL": "base_hl", "BREAKOUT": "breakout"}[state]
        idx = np.flatnonzero(f[col].to_numpy(bool)[-ACTIVE_BARS:]) + (len(f) - ACTIVE_BARS)   # tín hiệu đầu tiên trong cụm còn hiệu lực
        out["bars_ago"] = len(f) - 1 - int(idx[0]) if len(idx) else 0
    if state in ("BOTTOM", "BASE_HL", "BREAKOUT", "TREND", "WATCH"):
        # điểm vào tham chiếu: BREAKOUT/BOTTOM/BASE_HL = đỉnh hộp (vượt đỉnh hộp là điểm mua); WATCH = đỉnh vùng 60 phiên (lệnh chờ);
        # TREND = giá hiện tại
        rs = r                                                         # nến dùng để tính mức vào / cắt lỗ
        if state == "WATCH":
            entry = float(r["res60"])
        elif state == "TREND":
            entry = c
        else:                                                          # bùng nổ: lấy đỉnh nền TẠI nến báo, không phải nến hôm nay
            rs = f.iloc[-1 - int(out["bars_ago"] or 0)]
            entry = float(rs["res25"]) if pd.notna(rs["res25"]) else c
        stop = choose_stop(entry, rs, state)
        risk = entry - stop
        out.update(entry=entry, stop=stop, t1=entry + 2 * risk, t2=entry + 3 * risk, rr=2.0, ext=c / entry - 1)
    out["text"] = _text(out)
    out.update(rsi_view(g, f, state))
    return out


def _text(p: dict) -> str:
    s, c = p["state"], p["close"]
    if s == "BOTTOM":
        return "Giá đã giảm sâu, đi ngang tạo nền rồi vượt đỉnh nền kèm khối lượng lớn. Lịch sử kiểu này có tỷ lệ thắng nhỉnh hơn bùng nổ thường, nhưng cắt lỗ xa; nên chia vốn."
    if s == "BASE_HL":
        return "Tích lũy với đáy nâng dần, từng cạn cung rồi vượt đỉnh nền kèm khối lượng. Bùng nổ có tích lũy trước thường tốt hơn bùng nổ không có."
    if s == "BREAKOUT":
        return "Vượt đỉnh 25 phiên kèm khối lượng ≥ 1,5 lần trung bình. Bùng nổ thường không hơn mua ngẫu nhiên trong backtest; chỉ nên mua khi cùng lúc giá trên cả Tenkan và Kijun, hoặc có đáy nâng / giảm sâu trước đó."
    if s == "WATCH":
        return "Đáy nâng, đi ngang, khối lượng cạn, giá sát đỉnh vùng nhưng chưa vượt. Chưa mua: đặt cảnh báo ở đỉnh vùng, mua khi vượt kèm khối lượng."
    if s == "TREND":
        return "Giá trên mây và trên cả Tenkan, Kijun; Supertrend đang tăng. Nhóm có kỳ vọng khá trong lịch sử; giữ theo xu hướng và thoát khi đóng cửa dưới Supertrend."
    if s == "RANGE":
        return (f"Giá nằm giữa hai đường: kháng cự {p['res']:,.2f} (đường trên), hỗ trợ {p['sup']:,.2f} (đường dưới). "
                "Mua ở hỗ trợ không có lợi thế trong lịch sử; chờ vượt kháng cự kèm khối lượng.")
    if s == "WEAK":
        return "Giá dưới mây, dưới cả hai đường và Supertrend giảm. Không mua mới."
    return "Chưa rơi vào trạng thái nào có lợi thế rõ ràng."
