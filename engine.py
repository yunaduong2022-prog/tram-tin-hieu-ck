"""Lõi tính toán của Trạm Tín Hiệu (không phụ thuộc Streamlit).

- Gộp nến Ngày -> Tuần -> Tháng từ chính dữ liệu người dùng đưa vào
- Chỉ báo: MA/EMA, Ichimoku, Bollinger, MACD, KDJ, StochRSI, ATR
- Chấm điểm đa chỉ báo (thang -6.5 .. +6.5), dự báo, backtest, vùng giá, Fibonacci, Elliott
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import wyckoff as WYCK

NUMERIC_COLS = ["Giá mở cửa", "Giá cao nhất", "Giá thấp nhất", "Giá đóng cửa", "Khối lượng khớp lệnh"]
VOL = "Khối lượng khớp lệnh"

TF_NAME = {"D": "Ngày", "W": "Tuần", "M": "Tháng"}
TF_ROLE = {"M": "Xu hướng lớn", "W": "Xác nhận", "D": "Điểm vào"}
TF_UNIT = {"D": "phiên", "W": "tuần", "M": "tháng"}
TF_WEIGHT = {"M": 0.30, "W": 0.30, "D": 0.40}
PIVOT_K = {"D": 5, "W": 3, "M": 2}

MIN_BARS = 35          # tối thiểu để chấm điểm (MACD cần ~34 nến)
FULL_BARS = 80         # đủ cho Ichimoku (52 + 26)
SIG_TH = 2.0           # ngưỡng điểm sinh tín hiệu Mua/Bán
MAX_SCORE = 6.5
HORIZON = 10           # số nến của kịch bản dự báo
MAX_PTS = {"Ichimoku": 1.5, "MACD": 1.0, "KDJ": 0.5, "StochRSI": 0.5,
           "Bollinger": 0.5, "Fibonacci": 1.0, "Xu hướng": 1.5}


# ------------------------------------------------------------------ DỮ LIỆU
def clean_raw(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    for col in NUMERIC_COLS:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["Ngày"] = pd.to_datetime(df["Ngày"], errors="coerce", format="mixed", dayfirst=True)
    return df.dropna(subset=["Mã", "Ngày", "Giá đóng cửa"]).sort_values(["Mã", "Ngày"]).reset_index(drop=True)


def resample_ohlcv(g: pd.DataFrame, tf: str) -> pd.DataFrame:
    """Gộp nến ngày thành tuần (W-FRI) hoặc tháng. Khối lượng = tổng."""
    g = g.sort_values("Ngày")
    if tf == "D":
        r = g.copy()
        r["Số phiên"] = 1
        return r.reset_index(drop=True)
    key = g["Ngày"].dt.to_period("W-FRI" if tf == "W" else "M")
    r = g.groupby(key).agg(**{
        "Mã": ("Mã", "first"), "Ngày": ("Ngày", "last"),
        "Giá mở cửa": ("Giá mở cửa", "first"), "Giá cao nhất": ("Giá cao nhất", "max"),
        "Giá thấp nhất": ("Giá thấp nhất", "min"), "Giá đóng cửa": ("Giá đóng cửa", "last"),
        VOL: (VOL, "sum"), "Số phiên": ("Ngày", "size"),
    })
    return r.reset_index(drop=True)


def add_indicators(g: pd.DataFrame) -> pd.DataFrame:
    g = g.copy()
    c, h, l, v = g["Giá đóng cửa"], g["Giá cao nhất"], g["Giá thấp nhất"], g[VOL]
    g["Chg_%"] = c.pct_change() * 100
    for n in (9, 20, 50, 200):
        g[f"MA{n}"] = c.rolling(n).mean()
    g["EMA50"] = c.ewm(span=50, adjust=False, min_periods=50).mean()
    g["EMA200"] = c.ewm(span=200, adjust=False, min_periods=200).mean()
    g["Vol_MA10"] = v.shift(1).rolling(10).mean()
    g["Vol_vs_MA10"] = v / g["Vol_MA10"]
    rng = h - l
    g["Position_%"] = np.where(rng > 0, (c - l) / rng.replace(0, np.nan) * 100, 50.0)
    g["Range_%"] = np.where(l > 0, rng / l * 100, np.nan)

    # Ichimoku (mây tại ngày i được tính từ 26 nến trước)
    g["Tenkan"] = (h.rolling(9).max() + l.rolling(9).min()) / 2
    g["Kijun"] = (h.rolling(26).max() + l.rolling(26).min()) / 2
    g["SpanA"] = ((g["Tenkan"] + g["Kijun"]) / 2).shift(26)
    g["SpanB"] = ((h.rolling(52).max() + l.rolling(52).min()) / 2).shift(26)
    g["Chikou_ref"] = c.shift(26)
    g["Resistance_20"] = h.shift(1).rolling(20).max()
    g["Support_20"] = l.shift(1).rolling(20).min()

    # Bollinger 20, 2
    sd = c.rolling(20).std(ddof=0)
    g["BB_mid"], g["BB_up"], g["BB_lo"] = g["MA20"], g["MA20"] + 2 * sd, g["MA20"] - 2 * sd

    # MACD 12-26-9
    macd = c.ewm(span=12, adjust=False).mean() - c.ewm(span=26, adjust=False, min_periods=26).mean()
    g["MACD"] = macd
    g["MACD_sig"] = macd.ewm(span=9, adjust=False, min_periods=9).mean()
    g["MACD_hist"] = g["MACD"] - g["MACD_sig"]

    # KDJ 9-3-3
    rsv = (c - l.rolling(9).min()) / (h.rolling(9).max() - l.rolling(9).min()).replace(0, np.nan) * 100
    k = rsv.ewm(alpha=1 / 3, adjust=False).mean()
    d = k.ewm(alpha=1 / 3, adjust=False).mean()
    g["KDJ_K"], g["KDJ_D"], g["KDJ_J"] = k, d, 3 * k - 2 * d

    # StochRSI 14-3-3-3
    delta = c.diff()
    ag = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    al = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    rsi = (100 - 100 / (1 + ag / al.replace(0, np.nan))).where(al != 0, 100.0).where(ag.notna())
    st = (rsi - rsi.rolling(14).min()) / (rsi.rolling(14).max() - rsi.rolling(14).min()).replace(0, np.nan) * 100
    g["SRSI_K"] = st.rolling(3).mean()
    g["SRSI_D"] = g["SRSI_K"].rolling(3).mean()

    # ATR 14
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    g["ATR"] = tr.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    return add_pv_signals(g)


# ------------------------------------------------------------------ CẢNH BÁO MUA / BÁN THEO GIÁ + KHỐI LƯỢNG
PV_LABEL = {"BREAKOUT": "Phá kháng cự + vol lớn", "SPRING": "Quét đáy rồi rút chân (Spring)",
            "BREAKDOWN": "Phá hỗ trợ + vol lớn", "UPTHRUST": "Vượt đỉnh thất bại (bẫy tăng)",
            "CLIMAX": "Vol đột biến, đóng xa đỉnh (phân phối)", "SELLOFF": "Xả mạnh + vol lớn"}
PV_SIDE = {"BREAKOUT": 1, "SPRING": 1, "BREAKDOWN": -1, "UPTHRUST": -1, "CLIMAX": -1, "SELLOFF": -1}


def add_pv_signals(g: pd.DataFrame) -> pd.DataFrame:
    """Mua/Bán thuần theo giá + khối lượng (Wyckoff/VSA), tính được cho mọi khung D/W/M.
    Vol_vs_MA10 = khối lượng nến / TB 10 nến trước. Position = vị trí giá đóng trong biên độ nến."""
    c, h, l = g["Giá đóng cửa"], g["Giá cao nhất"], g["Giá thấp nhất"]
    pos, vr, chg = g["Position_%"], g["Vol_vs_MA10"], g["Chg_%"]
    res, sup, ma20 = g["Resistance_20"], g["Support_20"], g["MA20"]
    conds = [
        (c > res) & (pos >= 70) & (vr >= 1.5),                 # MUA: phá kháng cự, đóng sát đỉnh, vol lớn
        (l < sup) & (c >= sup) & (pos >= 50) & (vr >= 1.2),    # MUA: quét thủng hỗ trợ rồi đóng trên hỗ trợ
        (c < sup) & (pos <= 30) & (vr >= 1.5),                 # BÁN: phá hỗ trợ, đóng sát đáy, vol lớn
        (h > res) & (c < res) & (pos <= 50) & (vr >= 1.2),     # BÁN: vượt đỉnh nhưng đóng dưới kháng cự
        (chg > 0) & (vr >= 2.0) & (pos <= 40),                 # BÁN: vol đột biến, đóng xa đỉnh
        (chg < 0) & (vr >= 1.5) & (pos <= 30) & (c < ma20),    # BÁN: giảm mạnh + vol lớn, dưới MA20
    ]
    codes = ["BREAKOUT", "SPRING", "BREAKDOWN", "UPTHRUST", "CLIMAX", "SELLOFF"]
    g["PV_code"] = np.select(conds, codes, "")
    g["PV_signal"] = g["PV_code"].map(PV_SIDE).fillna(0).astype(int)
    return g


def pv_text(r) -> str:
    code, vr, pos = r["PV_code"], r["Vol_vs_MA10"], r["Position_%"]
    if code == "BREAKOUT":
        return f"Phá kháng cự 20 nến ({r['Resistance_20']:.2f}), đóng cửa sát đỉnh (Position {pos:.0f}%), khối lượng gấp {vr:.1f} lần MA10"
    if code == "SPRING":
        return f"Quét thủng hỗ trợ ({r['Support_20']:.2f}) rồi đóng cửa trên hỗ trợ, khối lượng gấp {vr:.1f} lần MA10: lực cầu bắt đáy"
    if code == "BREAKDOWN":
        return f"Phá hỗ trợ 20 nến ({r['Support_20']:.2f}), đóng cửa sát đáy (Position {pos:.0f}%), khối lượng gấp {vr:.1f} lần MA10"
    if code == "UPTHRUST":
        return f"Vượt kháng cự ({r['Resistance_20']:.2f}) nhưng đóng cửa dưới kháng cự, khối lượng gấp {vr:.1f} lần: bẫy tăng giá"
    if code == "CLIMAX":
        return f"Giá tăng, khối lượng đột biến gấp {vr:.1f} lần nhưng đóng cửa xa đỉnh (Position {pos:.0f}%): dấu hiệu phân phối"
    if code == "SELLOFF":
        return f"Giá giảm {abs(r['Chg_%']):.1f}% kèm khối lượng gấp {vr:.1f} lần, đóng dưới MA20: áp lực xả mạnh"
    return ""


def latest_pv(g: pd.DataFrame):
    """Cảnh báo ở nến mới nhất + cảnh báo gần nhất trước đó."""
    s = g["PV_signal"].values
    now = None
    if len(g) and s[-1] != 0:
        now = {"side": int(s[-1]), "code": g["PV_code"].iat[-1], "text": pv_text(g.iloc[-1])}
    idx = np.where(s != 0)[0]
    prev = None
    if len(idx):
        i = int(idx[-1])
        prev = {"side": int(s[i]), "code": g["PV_code"].iat[i], "text": pv_text(g.iloc[i]),
                "date": g["Ngày"].iat[i], "ago": len(g) - 1 - i}
    return now, prev


# ------------------------------------------------------------------ TÍN HIỆU WYCKOFF (bộ lọc)
def analyze_signal(row, stop_buffer=0.03, target_r=2.0):
    c, l = row["Giá đóng cửa"], row["Giá thấp nhất"]
    v_ratio, pos = row["Vol_vs_MA10"], row["Position_%"]
    res, sup = row["Resistance_20"], row["Support_20"]
    score, reasons = 0.0, []

    if pd.notna(res) and pd.notna(pos) and c > res and pos >= 70:
        score += 2.0
        reasons.append(("Wyckoff", 2.0, f"Phá kháng cự 20 phiên ({res:.2f}), đóng cửa sát đỉnh (Position {pos:.0f}%)"))
    elif pd.notna(sup) and pd.notna(pos) and l < sup and c >= sup and pos >= 50:
        score += 1.5
        reasons.append(("Wyckoff", 1.5, f"Quét thủng hỗ trợ ({sup:.2f}) rồi đóng cửa trên hỗ trợ (Spring/Test)"))

    if pd.notna(v_ratio):
        if v_ratio >= 1.5:
            score += 1.5
            reasons.append(("Volume", 1.5, f"Khối lượng gấp {v_ratio:.1f} lần MA10 Vol"))
        elif v_ratio >= 1.2:
            score += 1.0
            reasons.append(("Volume", 1.0, f"Khối lượng gấp {v_ratio:.1f} lần MA10 Vol"))

    sa, sb = row["SpanA"], row["SpanB"]
    if pd.notna(sa) and pd.notna(sb) and c > max(sa, sb):
        score += 1.5
        reasons.append(("Ichimoku", 1.5, f"Giá nằm trên mây Kumo ({max(sa, sb):.2f})"))

    if pd.notna(row["MA9"]) and c > row["MA9"]:
        score += 0.5
        reasons.append(("MA Trend", 0.5, "Giá trên MA9"))

    if score >= 3.5:
        signal = "MUA MỚI (BREAKOUT)" if (pd.notna(pos) and pos >= 70) else "MUA GOM (SPRING)"
    else:
        signal = "WAIT"

    entry = c
    stoploss = l * (1 - stop_buffer)
    risk = entry - stoploss
    takeprofit = entry + target_r * risk if risk > 0 else entry
    rr = round((takeprofit - entry) / risk, 2) if risk > 0 else 0
    return signal, score, reasons, entry, stoploss, takeprofit, rr


# ------------------------------------------------------------------ BẢNG THEO DÕI (kiểu Google Sheet)
def zone_of(pos):
    if pd.isna(pos):
        return "-"
    return "High" if pos >= 70 else "Low" if pos <= 30 else "Mid-Sell"


def comment_of(zone, chg):
    if zone == "High":
        return "Tăng khỏe / Tiền vào" if chg > 0 else "Cầu đỡ / Rút chân" if chg < 0 else "Giữ giá cao / Chờ bứt phá"
    if zone == "Low":
        return "Rụt đầu / Tăng yếu" if chg > 0 else "Giảm mạnh / Áp lực xả" if chg < 0 else "Lình xình tích lũy"
    if zone == "Mid-Sell":
        return "Còn tăng" if chg > 0 else "Giảm lành tính" if chg < 0 else "Lình xình tích lũy"
    return "-"


def month_vol_change(monthly: pd.DataFrame) -> dict:
    """Vol tháng hiện tại so với tháng trước (so theo KL trung bình/phiên để công bằng khi tháng chưa đủ)."""
    out = {}
    for code, g in monthly.groupby("Mã"):
        if len(g) < 2:
            continue
        cur, prev = g.iloc[-1], g.iloc[-2]
        a, b = cur[VOL] / max(cur["Số phiên"], 1), prev[VOL] / max(prev["Số phiên"], 1)
        out[code] = a / b if b > 0 else np.nan
    return out


# ------------------------------------------------------------------ SÓNG / PIVOT
def swing_state(h: np.ndarray, l: np.ndarray, k: int):
    """Zigzag không nhìn trước: pivot tại j chỉ được xác nhận sau k nến.
    Trả về (last[i], prev[i], stack_cuối) với phần tử (idx, 'H'|'L', giá)."""
    n = len(h)
    stack, last, prev = [], [None] * n, [None] * n
    for i in range(n):
        j = i - k
        if j >= k:
            ish = h[j] >= h[j - k:i + 1].max()
            isl = l[j] <= l[j - k:i + 1].min()
            cand = ("H", h[j]) if (ish and not isl) else ("L", l[j]) if (isl and not ish) else None
            if cand:
                t, p = cand
                if stack and stack[-1][1] == t:
                    if (t == "H" and p >= stack[-1][2]) or (t == "L" and p <= stack[-1][2]):
                        stack[-1] = (j, t, p)
                else:
                    stack.append((j, t, p))
        last[i] = stack[-1] if stack else None
        prev[i] = stack[-2] if len(stack) > 1 else None
    return last, prev, stack


def fib_eval(prev, last, price):
    if prev is None or last is None or prev[2] == last[2]:
        return 0.0, "Chưa đủ nhịp sóng để áp dụng Fibonacci"
    p0, p1, leg = prev[2], last[2], abs(last[2] - prev[2])
    if last[1] == "H":                      # nhịp tăng p0 -> p1
        ret = (p1 - price) / leg
        if price > p1:
            return 1.0, f"Giá vượt đỉnh nhịp tăng gần nhất ({p1:.2f}): xu hướng tăng tiếp diễn"
        if ret < 0.382:
            return 1.0, f"Giá hồi nông (<38,2%) sau nhịp tăng {p0:.2f}-{p1:.2f}: cấu trúc tăng còn mạnh"
        if ret < 0.618:
            return 0.5, f"Giá hồi {ret:.0%} sau nhịp tăng {p0:.2f}-{p1:.2f}: nhịp hồi bình thường"
        if ret <= 1:
            return 0.0, f"Giá hồi sâu {ret:.0%} nhịp tăng {p0:.2f}-{p1:.2f}: cấu trúc tăng yếu đi"
        return -1.0, f"Giá đã đi ngược và phá hết nhịp tăng gần nhất ({p0:.2f}-{p1:.2f}): cấu trúc tăng bị vô hiệu"
    ret = (price - p1) / leg                # nhịp giảm p0 -> p1
    if price < p1:
        return -1.0, f"Giá phá đáy nhịp giảm gần nhất ({p1:.2f}): xu hướng giảm tiếp diễn"
    if ret < 0.382:
        return -0.5, f"Giá hồi yếu (<38,2%) sau nhịp giảm {p0:.2f}-{p1:.2f}: phe bán còn áp đảo"
    if ret < 0.618:
        return 0.0, f"Giá hồi {ret:.0%} sau nhịp giảm {p0:.2f}-{p1:.2f}: chưa rõ hướng"
    if ret <= 1:
        return 0.5, f"Giá hồi mạnh {ret:.0%} nhịp giảm {p0:.2f}-{p1:.2f}: lực cầu đang tốt dần"
    return 1.0, f"Giá vượt hết nhịp giảm gần nhất ({p0:.2f}-{p1:.2f}): cấu trúc giảm bị vô hiệu"


def elliott(stack):
    note = ("Nhận diện bằng quy tắc cứng (sóng 2 không thủng đáy sóng 1, sóng 3 không ngắn nhất, "
            "sóng 4 không chồng sóng 1). Elliott mang tính chủ quan cao nên chỉ để tham khảo, không cộng vào điểm.")
    res = {"title": "Chưa nhận diện được cấu trúc sóng", "tag": "gray", "points": [],
           "text": "Chưa thấy cấu trúc 5 sóng rõ ràng theo quy tắc cứng. " + note}

    def valid(pts):
        up = pts[0][1] == "L"
        p = [x[2] if up else -x[2] for x in pts]
        if not (p[1] > p[0] and p[0] < p[2] < p[1] and p[3] > p[1] and p[1] < p[4] < p[3]):
            return None
        w1, w3 = p[1] - p[0], p[3] - p[2]
        if len(p) == 6:
            if p[5] <= p[3]:
                return None
            if w3 < w1 and w3 < p[5] - p[4]:
                return None
        return up

    for size in (6, 5):
        if len(stack) < size:
            continue
        pts = stack[-size:]
        up = valid(pts)
        if up is None:
            continue
        res["points"] = [(x[0], x[2], str(i)) for i, x in enumerate(pts)]
        if size == 6 and up:
            res.update(title="Sóng 5 có thể đã hoàn tất", tag="red",
                       text="Elliott: 5 sóng tăng có vẻ đã hoàn tất. Sau đó thường có nhịp điều chỉnh A-B-C "
                            "ngược chiều, nên chốt lời hoặc hạn chế mua đuổi. " + note)
        elif size == 6:
            res.update(title="Sóng 5 giảm có thể đã xong", tag="green",
                       text="Elliott: 5 sóng giảm có vẻ đã hoàn tất. Sau đó thường có nhịp hồi A-B-C, "
                            "có thể canh nhịp hồi kỹ thuật. " + note)
        elif up:
            res.update(title="Có thể đang ở sóng 5 (tăng)", tag="green",
                       text="Elliott: đã xong sóng 4, nhiều khả năng còn một nhịp đẩy sóng 5 nhưng gần cuối chu kỳ. " + note)
        else:
            res.update(title="Có thể đang ở sóng 5 (giảm)", tag="red",
                       text="Elliott: đã xong sóng 4 giảm, có thể còn một nhịp giảm sóng 5 cuối chu kỳ. " + note)
        return res
    return res


def price_zones(g: pd.DataFrame, k: int = 3, lookback: int = 250):
    """Gom đỉnh/đáy thành vùng hỗ trợ - kháng cự, đếm số lần chạm."""
    t = g.tail(lookback).reset_index(drop=True)
    h, l = t["Giá cao nhất"].values, t["Giá thấp nhất"].values
    pts = []
    for j in range(k, len(t) - k):
        if h[j] >= h[j - k:j + k + 1].max():
            pts.append(h[j])
        if l[j] <= l[j - k:j + k + 1].min():
            pts.append(l[j])
    if not pts:
        return []
    c = float(t["Giá đóng cửa"].iloc[-1])
    atr = t["ATR"].iloc[-1]
    width = max(1.2 * (atr if pd.notna(atr) else 0), 0.008 * c)
    pts.sort()
    clusters, cur = [], [pts[0]]
    for p in pts[1:]:
        if p - cur[0] <= width:
            cur.append(p)
        else:
            clusters.append(cur)
            cur = [p]
    clusters.append(cur)
    zones = []
    for cl in clusters:
        if len(cl) < 2:
            continue
        lo, hi = min(cl), max(cl)
        kind = "Hỗ trợ" if hi < c else "Kháng cự" if lo > c else ("Kháng cự" if c < (lo + hi) / 2 else "Hỗ trợ")
        zones.append({"lo": lo, "hi": hi, "n": len(cl), "kind": kind})
    res = sorted([z for z in zones if z["kind"] == "Kháng cự"], key=lambda z: z["lo"])[:4]
    sup = sorted([z for z in zones if z["kind"] == "Hỗ trợ"], key=lambda z: -z["hi"])[:3]
    return sorted(res + sup, key=lambda z: -z["lo"])


# ------------------------------------------------------------------ CHẤM ĐIỂM
def score_frame(g: pd.DataFrame, tf: str):
    c = g["Giá đóng cửa"]
    top, bot = np.maximum(g["SpanA"], g["SpanB"]), np.minimum(g["SpanA"], g["SpanB"])
    g["S_Ichimoku"] = (np.select([c > top, c < bot], [0.75, -0.75], 0.0)
                       + np.select([g["Tenkan"] > g["Kijun"], g["Tenkan"] < g["Kijun"]], [0.4, -0.4], 0.0)
                       + np.select([c > g["Chikou_ref"], c < g["Chikou_ref"]], [0.35, -0.35], 0.0))
    hist = g["MACD_hist"]
    rising = hist > hist.shift(1)
    g["S_MACD"] = np.select([(hist > 0) & rising, (hist > 0) & ~rising, (hist < 0) & rising, (hist < 0) & ~rising],
                            [1.0, 0.5, 0.0, -1.0], 0.0)
    for name, a, b in (("KDJ", "KDJ_K", "KDJ_D"), ("StochRSI", "SRSI_K", "SRSI_D")):
        k, d = g[a], g[b]
        g[f"S_{name}"] = np.select([(k > d) & (k < 80), (k > d), (k < d) & (k > 20), (k < d)],
                                   [0.5, 0.0, -0.5, 0.0], 0.0)
    width = (g["BB_up"] - g["BB_mid"]).replace(0, np.nan)
    g["S_Bollinger"] = (((c - g["BB_mid"]) / width).clip(-1, 1) * 0.5).fillna(0.0)
    diff = (g["EMA50"] - g["EMA200"]) / g["EMA200"]
    g["S_Xu hướng"] = np.select([(diff > 0.01) & (c > g["EMA50"]), diff > 0.01,
                                 (diff < -0.01) & (c < g["EMA50"]), diff < -0.01],
                                [1.5, 0.5, -1.5, -0.5], 0.0)
    last, prev, stack = swing_state(g["Giá cao nhất"].values, g["Giá thấp nhất"].values, PIVOT_K[tf])
    fib = [fib_eval(prev[i], last[i], c.iat[i]) for i in range(len(g))]
    g["S_Fibonacci"] = [x[0] for x in fib]
    cols = [f"S_{k}" for k in MAX_PTS]
    g["Total"] = g[cols].sum(axis=1)
    g["Bias"] = g["Total"] / MAX_SCORE * 100
    return g, stack, fib[-1][1], (prev[-1], last[-1])


def describe_items(g, fib_text):
    r = g.iloc[-1]
    c = r["Giá đóng cửa"]
    f = lambda x: f"{x:.2f}"

    parts = []
    if pd.notna(r["SpanA"]) and pd.notna(r["SpanB"]):
        hi, lo = max(r["SpanA"], r["SpanB"]), min(r["SpanA"], r["SpanB"])
        pos = "trên" if c > hi else "dưới" if c < lo else "trong"
        parts.append(f"Giá nằm {pos} mây ({f(lo)}-{f(hi)})")
    if pd.notna(r["Tenkan"]) and pd.notna(r["Kijun"]):
        parts.append("Tenkan trên Kijun" if r["Tenkan"] > r["Kijun"] else "Tenkan dưới Kijun")
    if pd.notna(r["Chikou_ref"]):
        parts.append("Chikou trên giá 26 nến trước" if c > r["Chikou_ref"] else "Chikou dưới giá 26 nến trước")
    t_ichi = ", ".join(parts) or "Chưa đủ nến để tính Ichimoku (cần ≥ 78 nến)"

    hist = r["MACD_hist"]
    if pd.isna(hist):
        t_macd = "Chưa đủ nến để tính MACD"
    else:
        up = hist > g["MACD_hist"].iloc[-2] if len(g) > 1 else False
        t_macd = ("Histogram MACD dương và đang tăng dần: động lượng tăng mạnh lên" if hist > 0 and up else
                  "Histogram MACD dương nhưng đang giảm dần: đà tăng suy yếu" if hist > 0 else
                  "Histogram MACD âm và đang tăng dần: động lượng giảm đang suy yếu" if up else
                  "Histogram MACD âm và đang giảm dần: động lượng giảm mạnh thêm")

    def osc(name, k, d):
        if pd.isna(k) or pd.isna(d):
            return f"Chưa đủ nến để tính {name}"
        s = f"{name}: K {k:.0f} {'trên' if k > d else 'dưới'} D {d:.0f}"
        return s + (", vùng quá bán, dễ hồi" if k < 20 else ", vùng quá mua, dễ điều chỉnh" if k >= 80 else "")

    if pd.isna(r["BB_mid"]):
        t_bb = "Chưa đủ nến để tính Bollinger"
    else:
        t_bb = f"Giá {'trên' if c >= r['BB_mid'] else 'dưới'} đường giữa Bollinger ({f(r['BB_mid'])})"
        t_bb += ", chạm dải trên" if c >= r["BB_up"] else ", chạm dải dưới" if c <= r["BB_lo"] else ""

    if pd.isna(r["EMA200"]):
        t_tr = "EMA50/EMA200 chưa cho xu hướng chính rõ ràng (chưa đủ nến cho EMA200)"
    else:
        d = (r["EMA50"] - r["EMA200"]) / r["EMA200"]
        t_tr = ("EMA50/EMA200 chưa cho xu hướng chính rõ ràng" if abs(d) <= 0.01 else
                f"EMA50 {'trên' if d > 0 else 'dưới'} EMA200 và giá {'trên' if c > r['EMA50'] else 'dưới'} EMA50: "
                f"xu hướng {'tăng' if d > 0 else 'giảm'}")
    texts = {"Ichimoku": t_ichi, "MACD": t_macd, "KDJ": osc("KDJ", r["KDJ_K"], r["KDJ_D"]),
             "StochRSI": osc("StochRSI", r["SRSI_K"], r["SRSI_D"]), "Bollinger": t_bb,
             "Fibonacci": fib_text, "Xu hướng": t_tr}
    return [(k, float(r[f"S_{k}"]), MAX_PTS[k], texts[k]) for k in MAX_PTS]


# ------------------------------------------------------------------ BACKTEST
def run_backtest(g: pd.DataFrame, max_hold=20, sl_atr=1.5, rr=2.0) -> pd.DataFrame:
    """Tín hiệu = cảnh báo Mua/Bán theo giá + khối lượng. Vào tại giá đóng cửa, SL = 1.5 ATR, TP = 2R."""
    sig, sell = g["PV_signal"] == 1, g["PV_signal"] == -1
    c, hi, lo, atr = (g["Giá đóng cửa"].values, g["Giá cao nhất"].values,
                      g["Giá thấp nhất"].values, g["ATR"].values)
    n, rows = len(g), []
    for i in np.where(sig | sell)[0]:
        d = 1 if sig.iat[i] else -1
        if not (atr[i] > 0):
            continue
        risk = sl_atr * atr[i]
        sl, tp = c[i] - d * risk, c[i] + d * rr * risk
        end = min(n, i + 1 + max_hold)
        r, is_open = None, False
        if i + 1 >= n:
            r, is_open = np.nan, True
        else:
            for j in range(i + 1, end):
                if (lo[j] <= sl) if d == 1 else (hi[j] >= sl):
                    r = -1.0
                    break
                if (hi[j] >= tp) if d == 1 else (lo[j] <= tp):
                    r = rr
                    break
            if r is None:
                r = d * (c[end - 1] - c[i]) / risk
                is_open = (end == n and end - i - 1 < max_hold)
        rows.append({"idx": i, "Ngày": g["Ngày"].iat[i], "dir": d, "R": r, "open": is_open, "code": g["PV_code"].iat[i]})
    return pd.DataFrame(rows, columns=["idx", "Ngày", "dir", "R", "open", "code"])


def backtest_stats(t: pd.DataFrame, n_bars: int, include_short: bool):
    if t.empty:
        return None
    t = t[~t["open"].astype(bool)]
    if not include_short:
        t = t[t["dir"] == 1]
    if t.empty:
        return None
    r = t["R"]
    wins, losses = r[r > 0], r[r <= 0]
    pf = wins.sum() / abs(losses.sum()) if losses.sum() != 0 else float("inf")
    eq = r.cumsum().values
    peak = np.maximum.accumulate(np.r_[0.0, eq])[1:]
    rec = t[t["idx"] >= 0.7 * n_bars]
    return {"n": len(t), "buy": int((t["dir"] == 1).sum()), "sell": int((t["dir"] == -1).sum()),
            "win": len(wins) / len(t) * 100, "exp": r.mean(), "pf": pf,
            "mdd": float(abs((eq - peak).min())), "rec_n": len(rec),
            "rec_exp": rec["R"].mean() if len(rec) else np.nan}


# ------------------------------------------------------------------ PHÂN TÍCH 1 KHUNG
def analyze_frame(g: pd.DataFrame, tf: str) -> dict:
    g = g.reset_index(drop=True).copy()
    n = len(g)
    out = {"tf": tf, "g": g, "n": n, "enough": n >= MIN_BARS, "partial": n < FULL_BARS,
           "total": 0.0, "bias": 0.0, "dir": 0, "items": [], "fc": None,
           "trades": pd.DataFrame(columns=["idx", "Ngày", "dir", "R", "open", "code"]),
           "zones": [], "fib": None, "wy": None,
           "elliott": {"title": "", "tag": "gray", "points": [], "text": ""}}
    out["trades"] = run_backtest(g)
    out["pv_now"], out["pv_prev"] = latest_pv(g)
    if not out["enough"]:
        return out
    g, stack, fib_text, (fprev, flast) = score_frame(g, tf)
    out["g"] = g
    out["total"], out["bias"] = float(g["Total"].iat[-1]), float(g["Bias"].iat[-1])
    out["dir"] = 1 if out["total"] >= 1.0 else -1 if out["total"] <= -1.0 else 0
    out["items"] = describe_items(g, fib_text)
    out["zones"] = price_zones(g, k=3)
    out["elliott"] = elliott(stack)
    try:
        out["wy"] = WYCK.analyze(g)
    except Exception:   # Wyckoff chỉ để quan sát, không được làm hỏng phần phân tích còn lại
        out["wy"] = None
    out["stack"] = stack
    if fprev and flast:
        out["fib"] = {"A": fprev, "B": flast}

    c, atr = g["Giá đóng cửa"].iat[-1], g["ATR"].iat[-1]
    atr = atr if pd.notna(atr) and atr > 0 else c * 0.02
    d, risk = out["dir"], 1.5 * atr
    if d != 0:
        out["fc"] = {"dir": d, "lo": c - 0.25 * atr, "hi": c + 0.25 * atr, "entry": c,
                     "sl": c - d * risk, "sl_pct": risk / c * 100,
                     "t1": c + d * 2 * risk, "t2": c + d * 3 * risk}
    return out


# ------------------------------------------------------------------ KẾT LUẬN ĐA KHUNG
def vn_join(xs):
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " và " + xs[-1]


def mtf_conclusion(A: dict):
    avail = [t for t in ("M", "W", "D") if A[t]["enough"]]
    if not avail:
        return None
    wsum = sum(TF_WEIGHT[t] for t in avail)
    score = sum(TF_WEIGHT[t] * A[t]["bias"] for t in avail) / wsum
    big = [A[t]["dir"] for t in ("M", "W") if t in avail]
    if score >= 40 and not any(x < 0 for x in big):
        verdict, kind = "ƯU TIÊN MUA", "green"
    elif score >= 15 and not any(x < 0 for x in big):
        verdict, kind = "CÓ THỂ MUA (VÀO NHỎ)", "green"
    elif score <= -15 or (big and all(x < 0 for x in big)):
        verdict, kind = "TRÁNH MUA", "red"
    else:
        verdict, kind = "CHỜ", "amber"
    ups = [TF_NAME[t] for t in avail if A[t]["dir"] > 0]
    downs = [TF_NAME[t] for t in avail if A[t]["dir"] < 0]
    flats = [TF_NAME[t] for t in avail if A[t]["dir"] == 0]
    if downs and not ups and not flats:
        text = f"{vn_join(downs)} cùng nghiêng giảm. Không bắt đáy lúc này."
    elif ups and not downs and not flats:
        text = f"{vn_join(ups)} cùng nghiêng tăng. Ưu tiên canh mua theo xu hướng và đặt cắt lỗ."
    elif ups and downs:
        text = f"{vn_join(ups)} nghiêng tăng nhưng {vn_join(downs)} nghiêng giảm: các khung chưa đồng thuận, nên chờ."
    elif downs:
        text = f"{vn_join(downs)} nghiêng giảm, các khung còn lại đi ngang: chưa có lý do để mua."
    elif ups:
        text = f"{vn_join(ups)} nghiêng tăng, các khung còn lại đi ngang: có thể theo dõi điểm vào."
    else:
        text = "Các khung đều đi ngang, chưa có lợi thế rõ ràng."
    return {"score": score, "verdict": verdict, "kind": kind, "text": text, "avail": avail}
