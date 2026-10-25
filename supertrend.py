"""Chỉ báo Supertrend, chuyển từ mã Pine Script v4 "Supertrend" (ATR Period 10, Multiplier 3.0).

Giữ đúng logic của bản gốc:
- Nguồn (src) = hl2 = (cao + thấp) / 2; ATR theo phương pháp Wilder (hàm atr() của Pine, "Change ATR Calculation
  Method" = bật). Đặt ATR_WILDER = False để dùng SMA của True Range như khi tắt tùy chọn đó.
- up = src - mult*ATR, chỉ được nâng lên khi giá đóng cửa phiên trước còn trên up trước đó; dn ngược lại.
- Xu hướng đảo sang tăng khi đóng cửa vượt dn của nến trước, đảo sang giảm khi đóng cửa thủng up của nến trước.
- Tín hiệu Buy / Sell khi xu hướng đổi chiều; dải tô màu giữa ohlc4 và đường Supertrend (Highlighter).

Phải tính trên TOÀN BỘ lịch sử rồi mới cắt phần hiển thị, vì chỉ báo có trạng thái nhớ từ nến trước.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

PERIOD = 10          # ATR Period
MULTIPLIER = 3.0     # ATR Multiplier
ATR_WILDER = True    # True: atr(Periods) (RMA); False: sma(tr, Periods)
SHOW_SIGNALS = True  # nhãn Buy / Sell
HIGHLIGHT = True     # tô dải giữa giá và đường Supertrend

O, H, L, C = "Giá mở cửa", "Giá cao nhất", "Giá thấp nhất", "Giá đóng cửa"
GREEN, RED = "#1FA97A", "#E5586A"


def _atr(h: np.ndarray, l: np.ndarray, c: np.ndarray, n: int, wilder: bool) -> np.ndarray:
    pc = np.r_[np.nan, c[:-1]]
    tr = np.fmax(h - l, np.fmax(np.abs(h - pc), np.abs(l - pc)))
    tr[0] = h[0] - l[0]                       # nến đầu: tr = cao - thấp (như Pine)
    out = np.full(len(c), np.nan)
    if len(c) < n:
        return out
    if not wilder:
        return pd.Series(tr).rolling(n).mean().to_numpy()
    out[n - 1] = tr[:n].mean()                # RMA khởi tạo bằng SMA n nến đầu
    for i in range(n, len(c)):
        out[i] = (out[i - 1] * (n - 1) + tr[i]) / n
    return out


def compute(df: pd.DataFrame, period: int = PERIOD, mult: float = MULTIPLIER, wilder: bool = ATR_WILDER) -> pd.DataFrame:
    """Trả về DataFrame cùng index với df: ST_up, ST_dn (đường theo từng pha, NaN ở pha kia), ST_trend (1/-1),
    ST_buy, ST_sell (bool), ST_ohlc4. df cần các cột cao / thấp / đóng cửa (và mở cửa cho ohlc4)."""
    h = pd.to_numeric(df[H], errors="coerce").to_numpy(float)
    l = pd.to_numeric(df[L], errors="coerce").to_numpy(float)
    c = pd.to_numeric(df[C], errors="coerce").to_numpy(float)
    o = pd.to_numeric(df[O], errors="coerce").to_numpy(float) if O in df else c
    n = len(c)
    src = (h + l) / 2
    atr = _atr(h, l, c, period, wilder)
    up, dn = np.full(n, np.nan), np.full(n, np.nan)
    trend = np.ones(n, dtype=int)
    for i in range(n):
        prev_t = trend[i - 1] if i else 1
        if np.isnan(atr[i]) or np.isnan(src[i]) or np.isnan(c[i]):
            trend[i] = prev_t
            continue
        u, d = src[i] - mult * atr[i], src[i] + mult * atr[i]
        u1 = up[i - 1] if i and not np.isnan(up[i - 1]) else u     # nz(up[1], up)
        d1 = dn[i - 1] if i and not np.isnan(dn[i - 1]) else d     # nz(dn[1], dn)
        if i and c[i - 1] > u1:
            u = max(u, u1)
        if i and c[i - 1] < d1:
            d = min(d, d1)
        up[i], dn[i] = u, d
        if prev_t == -1 and c[i] > d1:
            trend[i] = 1
        elif prev_t == 1 and c[i] < u1:
            trend[i] = -1
        else:
            trend[i] = prev_t
    valid = ~np.isnan(up)
    prev = np.r_[1, trend[:-1]]
    out = pd.DataFrame(index=df.index)
    out["ST_up"] = np.where(valid & (trend == 1), up, np.nan)
    out["ST_dn"] = np.where(valid & (trend == -1), dn, np.nan)
    out["ST_trend"] = trend
    out["ST_buy"] = valid & (trend == 1) & (prev == -1)
    out["ST_sell"] = valid & (trend == -1) & (prev == 1)
    out["ST_ohlc4"] = (o + h + l + c) / 4
    out["ST_close"] = c                       # giá đóng cửa của nến báo Buy / Sell (hiện kèm nhãn)
    return out


def runs(mask) -> list[tuple[int, int]]:
    """Các đoạn liên tiếp (chỉ số đầu, chỉ số cuối) nơi mask = True."""
    idx = np.flatnonzero(np.asarray(mask, dtype=bool))
    if not idx.size:
        return []
    return [(int(g[0]), int(g[-1])) for g in np.split(idx, np.flatnonzero(np.diff(idx) > 1) + 1)]


def traces(x, st: pd.DataFrame, price_fmt: str = ",.2f", period: int = PERIOD, mult: float = MULTIPLIER,
           highlight: bool = HIGHLIGHT) -> list:
    """Các trace Plotly (đặt vào hàng giá). x: trục x của biểu đồ; st: kết quả compute() đã cắt đúng phần hiển thị.

    Mỗi pha xu hướng là MỘT trace riêng, không có ô trống (NaN) và không dùng fill='tonexty', để dải tô
    không bao giờ bị nối sai sang pha khác. Dải tô là đa giác kín giữa ohlc4 và đường Supertrend."""
    import plotly.graph_objects as go
    x = list(x)
    name = f"Supertrend ({period}, {mult:g})"
    ht = f"Supertrend: %{{y:{price_fmt}}}<extra></extra>"
    ohlc4 = st["ST_ohlc4"].to_numpy(float)
    out, first = [], True
    for col, color, fill_rgba in (("ST_up", GREEN, "rgba(31,169,122,0.12)"), ("ST_dn", RED, "rgba(229,88,106,0.12)")):
        y = st[col].to_numpy(float)
        for i0, i1 in runs(np.isfinite(y)):
            xs, ys = x[i0:i1 + 1], y[i0:i1 + 1]
            if highlight and i1 > i0:
                out.append(go.Scatter(x=xs + xs[::-1], y=np.r_[ys, ohlc4[i0:i1 + 1][::-1]], mode="none", fill="toself",
                                      fillcolor=fill_rgba, hoverinfo="skip", showlegend=False))
            out.append(go.Scatter(x=xs, y=ys, mode="lines", line=dict(width=2, color=color), name=name,
                                  legendgroup="supertrend", showlegend=first, hovertemplate=ht))
            first = False
    for col, line_col, color in (("ST_buy", "ST_up", GREEN), ("ST_sell", "ST_dn", RED)):
        m = st[col].to_numpy(bool)
        if m.any():
            out.append(go.Scatter(x=[xi for xi, mi in zip(x, m) if mi], y=st[line_col].to_numpy(float)[m], mode="markers",
                                  marker=dict(symbol="circle", size=7, color=color), legendgroup="supertrend",
                                  showlegend=False, hoverinfo="skip"))
    return out


def annotations(x, st: pd.DataFrame, show_signals: bool = SHOW_SIGNALS) -> list[dict]:
    """Nhãn hộp "Buy 19.5" (dưới đường xanh) và "Sell 23.9" (trên đường đỏ) như TradingView, kèm giá đóng cửa của nến báo tín hiệu (làm tròn 1 số lẻ);
    dùng với fig.add_annotation(**d, row=1, col=1)."""
    if not show_signals:
        return []
    x = list(x)
    out = []
    for col, line_col, color, text, shift in (("ST_buy", "ST_up", GREEN, "Buy", -16), ("ST_sell", "ST_dn", RED, "Sell", 16)):
        m = st[col].to_numpy(bool)
        y = st[line_col].to_numpy(float)
        px = st["ST_close"].to_numpy(float)
        for i in np.flatnonzero(m):
            out.append(dict(x=x[i], y=float(y[i]), text=f"{text} {px[i]:,.1f}", showarrow=False, yshift=shift, bgcolor=color,
                            font=dict(size=10, color="#FFFFFF"), borderpad=2, opacity=0.95))
    return out
