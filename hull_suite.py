"""Chỉ báo Hull Suite (by InSilico), chuyển từ mã Pine Script v4.

Giữ đúng logic của bản gốc:
- Ba biến thể: HMA, THMA, EHMA. Mặc định HMA, length 55, hệ số length 1.0, nguồn = giá đóng cửa.
  (THMA được gọi với length/2 như hàm Mode() trong bản gốc.)
- MHULL = HULL, SHULL = HULL lùi 2 nến. Màu xanh (#00ff00) khi HULL > HULL[2], đỏ (#ff0000) ngược lại.
- Hiển thị dạng dải: hai đường MHULL/SHULL và phần tô giữa chúng (Band Transparency 40).
Không đưa sang: "Show Hull MA from X timeframe" (khung lớn hơn: hãy đổi khung Ngày/Tuần/Tháng của biểu đồ)
và "Color candles" (tô màu nến theo xu hướng Hull; mặc định của bản gốc cũng tắt).

Phải tính trên TOÀN BỘ lịch sử rồi mới cắt phần hiển thị (WMA/EMA nhiều tầng cần đủ nến khởi động).
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

MODE = "Hma"          # "Hma" | "Thma" | "Ehma"
LENGTH = 55           # 180-200 cho hỗ trợ/kháng cự trôi, 55 cho điểm vào theo sóng
LENGTH_MULT = 1.0
LINE_WIDTH = 1
BAND_TRANSP = 40      # độ trong suốt của dải, như tham số gốc (0 = đặc, 100 = trong suốt hoàn toàn)
LINE_ALPHA = 0.5      # transp=50 của đường trong bản gốc
UP, DOWN = (0, 255, 0), (255, 0, 0)
C = "Giá đóng cửa"


def _i(x: float) -> int:
    """Pine ép độ dài về số nguyên bằng cách bỏ phần thập phân."""
    return max(1, int(x))


def wma(s: pd.Series, n: float) -> pd.Series:
    n = _i(n)
    w = np.arange(1, n + 1, dtype=float)
    return s.rolling(n).apply(lambda a: float(np.dot(a, w) / w.sum()), raw=True)


def ema(s: pd.Series, n: float) -> pd.Series:
    return s.ewm(span=_i(n), adjust=False).mean()          # khởi tạo từ giá trị đầu, như hàm ema() của Pine


def hma(s, n):
    return wma(2 * wma(s, n / 2) - wma(s, n), round(math.sqrt(n)))


def ehma(s, n):
    return ema(2 * ema(s, n / 2) - ema(s, n), round(math.sqrt(n)))


def thma(s, n):
    return wma(wma(s, n / 3) * 3 - wma(s, n / 2) - wma(s, n), n)


def compute(df: pd.DataFrame, mode: str = MODE, length: int = LENGTH, mult: float = LENGTH_MULT) -> pd.DataFrame:
    """Trả về DataFrame cùng index: HU_M (MHULL), HU_S (SHULL = lùi 2 nến), HU_up (HULL > HULL[2])."""
    s = pd.to_numeric(df[C], errors="coerce").reset_index(drop=True)
    n = int(length * mult)
    if mode == "Ehma":
        hull = ehma(s, n)
    elif mode == "Thma":
        hull = thma(s, n / 2)                                  # Mode(): THMA(src, len/2)
    else:
        hull = hma(s, n)
    out = pd.DataFrame(index=df.index)
    out["HU_M"] = hull.to_numpy()
    out["HU_S"] = hull.shift(2).to_numpy()
    out["HU_up"] = (hull > hull.shift(2)).to_numpy()
    return out


def traces(x, h: pd.DataFrame, width: int = LINE_WIDTH, band_transp: int = BAND_TRANSP, name: str | None = None) -> list:
    """Trace Plotly cho hàng giá: mỗi màu (xanh/đỏ) một cặp đường SHULL + MHULL, MHULL tô dải xuống SHULL."""
    import plotly.graph_objects as go
    x = list(x)
    m, s = h["HU_M"].to_numpy(float), h["HU_S"].to_numpy(float)
    up = h["HU_up"].to_numpy(bool) & np.isfinite(m) & np.isfinite(s)
    dn = ~h["HU_up"].to_numpy(bool) & np.isfinite(m) & np.isfinite(s)
    label = name or f"Hull {MODE.upper()} {int(LENGTH * LENGTH_MULT)}"
    out = []
    for mask, rgb, nm in ((up, UP, label), (dn, DOWN, label + " giảm")):
        seg = mask | np.r_[mask[1:], False]            # nối đoạn chuyển màu: đoạn i-1 -> i mang màu của nến i
        seg &= np.isfinite(m) & np.isfinite(s)
        if not mask.any():
            continue
        line = dict(width=width, color=f"rgba({rgb[0]},{rgb[1]},{rgb[2]},{LINE_ALPHA})")
        fill = f"rgba({rgb[0]},{rgb[1]},{rgb[2]},{(100 - band_transp) / 100:.2f})"
        out.append(go.Scatter(x=x, y=np.where(seg, s, np.nan), mode="lines", line=line, showlegend=False,
                              hoverinfo="skip", connectgaps=False))
        out.append(go.Scatter(x=x, y=np.where(seg, m, np.nan), mode="lines", line=line, fill="tonexty", fillcolor=fill,
                              name=nm, legendgroup="hull", showlegend=(rgb == UP), connectgaps=False,
                              hovertemplate="Hull: %{y:,.2f}<extra></extra>"))
    return out
