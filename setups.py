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


def _swing_high_above(h: np.ndarray, i: int, level: float, look: int = 120, k: int = 4) -> float | None:
    """Đỉnh pivot (cao nhất trong k nến mỗi bên) gần nhất NẰM TRÊN `level` (+1%) mà từ đó tới nến i giá chưa vượt qua. None nếu không còn đỉnh nào."""
    best = None
    for p in range(max(k, i - look + k), i - k + 1):
        if h[p] == h[p - k:p + k + 1].max() and h[p] > level * 1.01 and (p >= i or h[p + 1:i + 1].max() <= h[p]):
            best = h[p] if best is None else min(best, h[p])
    return None if best is None else float(best)


# Xác suất giá chạm mục tiêu trong 40 phiên (backtest 147 mã 2019-2026) và kỳ vọng nếu chốt hết ở đó
TARGET_STATS = {"A": 56, "B": 51, "C1": 56, "C2": 38}


def targets(g: pd.DataFrame, f: pd.DataFrame, entry: float, risk: float) -> dict:
    """Mục tiêu theo vị trí giá so với Tenkan 65 / Kijun 129:
      A  dưới cả hai đường      -> đường gần nhất phía trên giá (rồi tới đường còn lại)
      B  giữa hai đường         -> đường nằm trên (kháng cự)
      C1 trên cả hai, còn đỉnh cũ chưa vượt -> đỉnh pivot gần nhất phía trên
      C2 trên cả hai, đã tạo đỉnh mới       -> 2R và 3R tính từ giá vào"""
    r = f.iloc[-1]
    c = float(r["c"])
    lo, hi = float(r["tk_lo"]), float(r["tk_hi"])
    if c < lo:
        case = "A"
        lv = [("Đường gần nhất phía trên", lo), ("Đường còn lại", hi)] if lo > c * 1.005 else [("Đường trên (Tenkan/Kijun)", hi)]
    elif c < hi:
        case, lv = "B", [("Đường trên (kháng cự Tenkan/Kijun)", hi)]
    else:
        sw = _swing_high_above(pd.to_numeric(g[H], errors="coerce").to_numpy(float), len(g) - 1, c)
        if sw is None:
            case, lv = "C2", [("Mục tiêu 1 (2R)", entry + 2 * risk), ("Mục tiêu 2 (3R)", entry + 3 * risk)]
        else:
            case, lv = "C1", [("Đỉnh gần nhất chưa vượt", sw)]
    lv = [(n, float(v)) for n, v in lv if v > max(c, entry)]          # chỉ giữ mốc nằm trên cả giá hiện tại lẫn giá vào (lệnh chờ WATCH có giá vào cao hơn giá hiện tại)
    if not lv:                                                         # không còn mốc cản nào phía trên -> mục tiêu theo rủi ro
        case, lv = "C2", [("Mục tiêu 1 (2R)", float(entry + 2 * risk)), ("Mục tiêu 2 (3R)", float(entry + 3 * risk))]
    names = {"A": "Dưới cả hai đường", "B": "Giữa hai đường", "C1": "Trên hai đường, còn đỉnh chưa vượt", "C2": "Trên hai đường, đã tạo đỉnh mới"}
    return {"case": case, "case_name": names[case], "levels": lv, "prob": TARGET_STATS[case]}


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


def macd_view(g: pd.DataFrame, f: pd.DataFrame) -> dict:
    """MACD(12,26,9) kết hợp giá. Tín hiệu duy nhất có lợi thế trong backtest: DIF cắt lên 0 KHI giá đã trên Kijun và Supertrend tăng
    (20 phiên sau +3,9%, thắng 58%; mức nền +1,8%, 52%). DIF cắt lên 0 mà giá còn yếu thì ngang mức nền; nối 2 đáy MACD hướng lên không có lợi thế."""
    cs = pd.to_numeric(g[C], errors="coerce")
    dif = cs.ewm(span=12, adjust=False).mean() - cs.ewm(span=26, adjust=False).mean()
    sig = dif.ewm(span=9, adjust=False).mean()
    d = dif.to_numpy(float)
    cross = [i for i in range(max(1, len(d) - 5), len(d)) if d[i] > 0 >= d[i - 1]]      # DIF cắt lên 0 trong 5 phiên gần nhất
    r = f.iloc[-1]
    strong = bool(r["c"] > r["kijun"] and r["st_up"])
    out = {"dif": float(d[-1]), "sig": float(sig.iloc[-1]), "cross_ago": (len(d) - 1 - cross[-1]) if cross else None}
    if cross and strong:
        out.update(kind="confirmed", tone="green", note=("MACD vừa cắt lên 0 khi giá đã trên Kijun và Supertrend tăng: xác nhận. "
                   "Lịch sử +3,9% sau 20 phiên, thắng 58% (mức nền +1,8%, 52%)."))
    elif cross:
        out.update(kind="unconfirmed", tone="amber", note=("MACD vừa cắt lên 0 nhưng giá chưa trên Kijun hoặc Supertrend chưa tăng: chưa xác nhận. "
                   "Lịch sử chỉ +1,7%, thắng 51%, ngang mức nền."))
    elif d[-1] < 0:
        out.update(kind="neg", tone="gray", note="MACD đang dưới 0. Nối hai đáy MACD hướng lên không phải tín hiệu mua (backtest +0,7%, thắng 49%); chờ MACD cắt lên 0 cùng lúc giá trên Kijun.")
    else:
        out.update(kind="pos", tone="gray", note="MACD đang trên 0, chưa có tín hiệu cắt mới.")
    return out


def rebound_view(g: pd.DataFrame, f: pd.DataFrame, state: str) -> dict | None:
    """Phân biệt SÓNG HỒI và SÓNG TĂNG cho cổ phiếu đã giảm sâu ≥ 40% (đỉnh 250 phiên → đáy 60 phiên) đang có tín hiệu tích cực.
    Dưới Kijun 129: sóng hồi, mục tiêu theo mức hồi 38,2 / 50 / 61,8% của đoạn giảm (Kijun thường nằm gần mốc 38,2%).
    Trên Kijun + trên mây + Supertrend tăng: sóng tăng. Còn lại: đang vượt Kijun, chờ xác nhận.
    Số liệu: backtest 515 lần giảm sâu → đi ngang → bùng nổ, 147 mã, 2019-2026, 60 phiên sau."""
    r = f.iloc[-1]
    if state not in ("BOTTOM", "BASE_HL", "BREAKOUT", "WATCH") or not bool(r["deep"]):
        return None
    h = pd.to_numeric(g[H], errors="coerce")
    l = pd.to_numeric(g[L], errors="coerce")
    peak, trough = float(h.iloc[-250:].max()), float(l.iloc[-60:].min())
    drop = peak - trough
    c, k = float(r["c"]), float(r["kijun"])
    if drop <= 0 or c >= peak:
        return None
    if c < k:
        kind, tone = "hoi", "amber"
        title = "KHẢ NĂNG CÓ SÓNG HỒI"
        text = ("Giá đã giảm sâu và vẫn dưới Kijun 129: nhiều khả năng đây là sóng hồi chứ chưa phải sóng tăng mới. "
                "Backtest: mức hồi trung vị chỉ khoảng 38% đoạn giảm; 49% lần hồi tới 38,2%, 32% tới 50%, 20% tới 61,8%, chỉ 7% về lại đỉnh cũ. "
                "62% lần giá chạm Kijun trong 60 phiên, và khoảng một nửa số đó vượt thật qua Kijun.")
        probs = {0.382: 49, 0.5: 32, 0.618: 20}
    elif c > float(r["cloud_top"]) and bool(r["st_up"]):
        kind, tone = "tang", "green"
        title = "SÓNG TĂNG (sau giảm sâu)"
        text = ("Giá đã vượt Kijun 129 và mây, Supertrend tăng: coi là sóng tăng. Backtest: mức hồi trung vị 65% đoạn giảm, "
                "83% lần hồi tới 38,2%, 65% tới 50%, 54% tới 61,8%, 26% về lại đỉnh cũ.")
        probs = {0.382: 83, 0.5: 65, 0.618: 54}
    else:
        kind, tone = "cho", "amber"
        title = "ĐANG VƯỢT KIJUN: CHỜ XÁC NHẬN SÓNG TĂNG"
        text = "Giá đã trên Kijun 129 nhưng chưa trên mây hoặc Supertrend chưa tăng: chưa xác nhận sóng tăng, vẫn có thể chỉ là sóng hồi."
        probs = {0.382: 83, 0.5: 65, 0.618: 54}
    lv = [{"label": f"Hồi {int(round(x * 100 - 0.0))}%".replace("38%", "38,2%").replace("62%", "61,8%") + " đoạn giảm", "price": trough + x * drop,
           "pct": ((trough + x * drop) / c - 1) * 100, "prob": pr} for x, pr in probs.items()]
    return {"kind": kind, "tone": tone, "title": title, "text": text, "peak": peak, "trough": trough, "levels": lv}


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
           "deep": bool(r["deep"]), "entry": None, "stop": None, "t1": None, "t2": None, "rr": None, "text": "", "bars_ago": None, "ext": None, "targets": None, "rebound": None, "macd": None}
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
        out.update(entry=entry, stop=stop, t1=entry + 2 * risk, t2=entry + 3 * risk, rr=2.0, ext=c / entry - 1,
                   targets=targets(g, f, entry, risk))
    out["broken"] = False
    if out["entry"] is not None and state in ("BOTTOM", "BASE_HL", "BREAKOUT", "WATCH") and c <= out["stop"]:
        # giá đã thủng mức cắt lỗ của kế hoạch: nền / tín hiệu hỏng, bỏ kế hoạch (không báo điểm vào nữa)
        out.update(state="NEUTRAL", label="Nền / tín hiệu đã hỏng: giá thủng mức cắt lỗ", tag="red", entry=None, stop=None, t1=None, t2=None,
                   rr=None, ext=None, targets=None, bars_ago=None, broken=True)
        state = "NEUTRAL"
    out["below_entry"] = bool(out["entry"] is not None and state in ("BOTTOM", "BASE_HL", "BREAKOUT") and c < out["entry"])
    out["text"] = _text(out)
    out.update(rsi_view(g, f, state))
    out["macd"] = macd_view(g, f)
    out["rebound"] = rebound_view(g, f, state)
    return out


def _text(p: dict) -> str:
    s, c = p["state"], p["close"]
    if p.get("broken"):
        return "Giá đã đóng cửa dưới mức cắt lỗ của kế hoạch trước đó: nền hoặc tín hiệu bùng nổ đã hỏng. Không còn điểm vào; chờ cấu trúc mới."
    if p.get("below_entry"):
        return ("Tín hiệu bùng nổ còn hiệu lực nhưng giá đã quay về dưới điểm vào (đỉnh nền vừa vượt): chưa nên mua lúc này, "
                "chờ giá đóng cửa lấy lại trên điểm vào. Cắt lỗ vẫn tính từ điểm vào đó.")
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
