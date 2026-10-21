"""Gán nhãn tín hiệu phân kỳ RSI(14) & giá dựa trên đỉnh/đáy (pivot) gần nhất. Không phụ thuộc Streamlit.

Hai nhóm nhãn:
  1) CẢNH BÁO ĐẢO CHIỀU  - phân kỳ thường (Giá HH / RSI LH, Giá LL / RSI HL) và phân kỳ phóng đại (2 đỉnh / 2 đáy bằng nhau).
  2) XÁC NHẬN TIẾP DIỄN  - phân kỳ ẩn (Giá HL / RSI LL = tăng ; Giá LH / RSI HH = giảm).

Cách làm:
  - RSI(14) Wilder tính từ giá đóng cửa của từng khung.
  - Đỉnh/đáy giá = pivot: nến có High (Low) cao nhất (thấp nhất) trong K nến trước và K nến sau (cần K nến để xác nhận).
  - Lấy 2 đỉnh gần nhất (cho phân kỳ giảm) và 2 đáy gần nhất (cho phân kỳ tăng), so giá với RSI tại đúng nến pivot.
  - Chỉ báo tín hiệu còn "tươi": pivot sau nằm trong vài nến gần nhất và giá chưa vượt / thủng pivot đó.

Khung hỗ trợ: D (Ngày), W (Tuần), M (Tháng). App hiện chưa có dữ liệu 15m / 1h / 4h nên các khung này chưa được tính;
hàm `detect()` nhận tên khung bất kỳ có trong `PARAMS`, thêm khung mới chỉ cần thêm một dòng vào `PARAMS` và đưa DataFrame tương ứng vào.
"""
from __future__ import annotations

import html as _html

import numpy as np
import pandas as pd

# ------------------------------------------------------------------ NGƯỠNG (chỉnh tại đây)
PARAMS = {
    #        K: số nến mỗi bên xác nhận pivot | min_gap/max_gap: khoảng cách (nến) giữa 2 pivot | fresh: pivot sau phải nằm
    #        trong N nến gần nhất | eq: dung sai coi 2 đỉnh/đáy giá "bằng nhau" | lookback: số nến xét
    "15m": dict(k=5, min_gap=8, max_gap=80, fresh=20, eq=0.002, lookback=300),
    "1h":  dict(k=4, min_gap=6, max_gap=70, fresh=20, eq=0.003, lookback=300),
    "4h":  dict(k=3, min_gap=5, max_gap=60, fresh=15, eq=0.004, lookback=250),
    "D":   dict(k=4, min_gap=5, max_gap=60, fresh=25, eq=0.005, lookback=160),
    "W":   dict(k=2, min_gap=3, max_gap=30, fresh=10, eq=0.010, lookback=104),
    "M":   dict(k=2, min_gap=3, max_gap=24, fresh=6, eq=0.020, lookback=72),   # cần ≥ ~31 nến tháng (≈ 2,6 năm lịch sử)
}
RSI_MIN_DIFF = 2.0           # RSI 2 pivot phải lệch nhau ít nhất ngần này điểm mới tính là cao hơn / thấp hơn
RSI_PERIOD = 14
TF_NAME = {"15m": "15m", "1h": "1h", "4h": "4h", "D": "D", "W": "W", "M": "M"}

REVERSAL, CONTINUATION = "Cảnh báo đảo chiều", "Xác nhận tiếp diễn"

# kind -> (nhóm, nhãn gán theo quy tắc, tên loại phân kỳ, hướng, gợi ý)
KINDS = {
    "reg_bear":  (REVERSAL, "[CẢNH BÁO ĐẢO CHIỀU - GIẢM]", "Phân kỳ thường giảm", "down",
                  "Xu hướng tăng có khả năng đảo chiều giảm."),
    "reg_bull":  (REVERSAL, "[CẢNH BÁO ĐẢO CHIỀU - TĂNG]", "Phân kỳ thường tăng", "up",
                  "Xu hướng giảm có khả năng đảo chiều tăng."),
    "exa_bear":  (REVERSAL, "[CẢNH BÁO ĐẢO CHIỀU - TẠI VÙNG CẢN]", "Phân kỳ phóng đại giảm (2 đỉnh bằng nhau)", "down",
                  "Hai đỉnh giá bằng nhau nhưng RSI đỉnh sau thấp hơn tại vùng kháng cự."),
    "exa_bull":  (REVERSAL, "[CẢNH BÁO ĐẢO CHIỀU - TẠI VÙNG CẢN]", "Phân kỳ phóng đại tăng (2 đáy bằng nhau)", "up",
                  "Hai đáy giá bằng nhau nhưng RSI đáy sau cao hơn tại vùng hỗ trợ."),
    "hid_bull":  (CONTINUATION, "[XÁC NHẬN TIẾP DIỄN - XU HƯỚNG TĂNG]", "Phân kỳ ẩn tăng", "up",
                  "Xu hướng tăng được duy trì: tìm điểm BUY khi giá test hỗ trợ / MA."),
    "hid_bear":  (CONTINUATION, "[XÁC NHẬN TIẾP DIỄN - XU HƯỚNG GIẢM]", "Phân kỳ ẩn giảm", "down",
                  "Xu hướng giảm được duy trì: SELL / thoát hàng khi giá hồi kháng cự."),
}


# ------------------------------------------------------------------ RSI & PIVOT
def rsi14(close: pd.Series, n: int = RSI_PERIOD) -> pd.Series:
    """RSI Wilder (cùng công thức với engine.add_indicators)."""
    delta = close.astype(float).diff()
    ag = delta.clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    al = (-delta.clip(upper=0)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    return (100 - 100 / (1 + ag / al.replace(0, np.nan))).where(al != 0, 100.0).where(ag.notna())


def _pivots(s: np.ndarray, k: int, start: int, high: bool) -> list[int]:
    """Vị trí các pivot: nến cực trị trong k nến trước và k nến sau. Hai nến bằng nhau liền kề chỉ lấy nến đầu."""
    n = len(s)
    out = []
    for i in range(max(k, start), n - k):
        left, right = s[i - k:i], s[i + 1:i + k + 1]
        if np.isnan(s[i]) or np.isnan(left).any() or np.isnan(right).any():
            continue
        ok = (s[i] > left.max() and s[i] >= right.max()) if high else (s[i] < left.min() and s[i] <= right.min())
        if ok:
            out.append(i)
    return out


def _cmp(a: float, b: float, eq: float) -> int:
    """So giá sau (a) với giá trước (b): +1 cao hơn, 0 bằng nhau (trong dung sai eq), -1 thấp hơn."""
    if b == 0 or np.isnan(a) or np.isnan(b):
        return 0
    d = a / b - 1
    return 1 if d > eq else -1 if d < -eq else 0


def _rsi_cmp(a: float, b: float) -> int:
    d = a - b
    return 1 if d >= RSI_MIN_DIFF else -1 if d <= -RSI_MIN_DIFF else 0


# ------------------------------------------------------------------ PHÁT HIỆN
def detect(df: pd.DataFrame, tf: str = "D") -> list[dict]:
    """Tìm tín hiệu phân kỳ trên một khung. df cần cột tiếng Việt của app (Giá cao nhất / Giá thấp nhất / Giá đóng cửa, Ngày).

    Trả về list dict (tối đa 2 phần tử: một từ đỉnh, một từ đáy), mới nhất trước:
      tf, kind, group, label, name, dir, hint, p1/p2 (giá), r1/r2 (RSI), d1/d2 (ngày), bars_ago, text
    """
    prm = PARAMS.get(tf)
    need = {"Giá cao nhất", "Giá thấp nhất", "Giá đóng cửa"}
    if prm is None or df is None or not need <= set(df.columns):
        return []
    g = df.sort_values("Ngày").reset_index(drop=True) if "Ngày" in df.columns else df.reset_index(drop=True)
    n = len(g)
    if n < RSI_PERIOD + 2 * prm["k"] + prm["min_gap"] + 10:
        return []
    hi, lo = g["Giá cao nhất"].to_numpy(float), g["Giá thấp nhất"].to_numpy(float)
    rsi = rsi14(g["Giá đóng cửa"]).to_numpy(float)
    dates = g["Ngày"].to_numpy() if "Ngày" in g.columns else np.arange(n)
    start = max(RSI_PERIOD, n - prm["lookback"])
    out = []

    for high in (True, False):
        price = hi if high else lo
        piv = [i for i in _pivots(price, prm["k"], start, high) if not np.isnan(rsi[i])]
        if len(piv) < 2:
            continue
        i1, i2 = piv[-2], piv[-1]
        if not (prm["min_gap"] <= i2 - i1 <= prm["max_gap"]) or (n - 1 - i2) > prm["fresh"]:
            continue
        p1, p2, r1, r2 = price[i1], price[i2], rsi[i1], rsi[i2]
        # Tín hiệu hết hạn nếu giá đã vượt (đỉnh) / thủng (đáy) pivot sau
        after = price[i2 + 1:]
        if len(after) and ((after.max() > p2 * (1 + prm["eq"])) if high else (after.min() < p2 * (1 - prm["eq"]))):
            continue
        pc, rc = _cmp(p2, p1, prm["eq"]), _rsi_cmp(r2, r1)
        kind = None
        if high:
            if pc > 0 and rc < 0: kind = "reg_bear"       # giá HH, RSI LH
            elif pc == 0 and rc < 0: kind = "exa_bear"     # 2 đỉnh bằng nhau, RSI LH
            elif pc < 0 and rc > 0: kind = "hid_bear"      # giá LH, RSI HH
        else:
            if pc < 0 and rc > 0: kind = "reg_bull"       # giá LL, RSI HL
            elif pc == 0 and rc > 0: kind = "exa_bull"     # 2 đáy bằng nhau, RSI HL
            elif pc > 0 and rc < 0: kind = "hid_bull"      # giá HL, RSI LL
        if kind is None:
            continue
        grp, label, name, direction, hint = KINDS[kind]
        pt, rt = ("đỉnh", "đỉnh") if high else ("đáy", "đáy")
        word = lambda c, h_: {1: "cao hơn", 0: "bằng", -1: "thấp hơn"}[c]
        out.append({
            "tf": tf, "kind": kind, "group": grp, "label": label, "name": name, "dir": direction, "hint": hint,
            "p1": float(p1), "p2": float(p2), "r1": float(r1), "r2": float(r2),
            "d1": dates[i1], "d2": dates[i2], "bars_ago": int(n - 1 - i2),
            "text": f"Giá {pt} sau {word(pc, high)} {pt} trước ({p1:,.2f} → {p2:,.2f}); "
                    f"RSI {rt} sau {word(rc, high)} ({r1:.0f} → {r2:.0f}).",
        })
    return sorted(out, key=lambda x: x["bars_ago"])


def analyze(frames: dict, code: str, tfs: tuple[str, ...] = ("D", "W", "M")) -> list[dict]:
    """Chạy detect trên các khung có trong `frames` cho một mã; mới nhất / khung lớn đứng trước."""
    res = []
    for tf in tfs:
        f = frames.get(tf)
        if f is None or f.empty:
            continue
        res += detect(f[f["Mã"] == code], tf)
    order = {t: i for i, t in enumerate(("M", "W", "D", "4h", "1h", "15m"))}
    return sorted(res, key=lambda s: (order.get(s["tf"], 9), s["bars_ago"]))


# ------------------------------------------------------------------ HIỂN THỊ
def css() -> str:
    """CSS dùng chung cho thẻ Bộ lọc và thẻ Cổ phiếu chờ mua (màu lấy từ biến theme)."""
    return """
.dv-wrap{margin:2px 0 12px;display:flex;flex-direction:column;gap:7px}
.dv-item{border-radius:10px;padding:8px 11px;border:1px solid var(--line);font-size:12.5px;line-height:1.45}
.dv-item.rev.down{background:var(--tag-red-bg);border-color:var(--red)}
.dv-item.rev.up{background:var(--tag-green-bg);border-color:var(--green)}
.dv-item.con.up{background:var(--tag-green-bg);border-color:var(--line)}
.dv-item.con.down{background:var(--tag-amber-bg);border-color:var(--line)}
.dv-top{display:flex;align-items:center;flex-wrap:wrap;gap:6px 8px;font-weight:750}
.dv-tf{display:inline-block;min-width:22px;text-align:center;padding:1px 7px;border-radius:6px;font-size:11px;font-weight:800;
  background:var(--card2);color:var(--txt2);border:1px solid var(--line)}
.dv-tag{display:inline-block;padding:2px 9px;border-radius:999px;font-size:11px;font-weight:800;letter-spacing:.2px;white-space:nowrap}
.dv-item.rev.down .dv-tag{background:var(--red);color:#2a0b12}
.dv-item.rev.up .dv-tag{background:var(--green);color:#06271e}
.dv-item.con.up .dv-tag{background:var(--tag-green-fg);color:#06271e}
.dv-item.con.down .dv-tag{background:var(--amber);color:#2e2106}
.dv-name{color:var(--txt2)}
.dv-det{margin-top:4px;color:var(--txt)}
.dv-hint{margin-top:2px;color:var(--muted);font-size:11.5px}
"""


def html(signals: list[dict]) -> str:
    """Khối HTML cảnh báo cho thẻ; rỗng nếu không có tín hiệu."""
    if not signals:
        return ""
    esc = _html.escape
    items = []
    for s in signals:
        rev = s["group"] == REVERSAL
        icon = "⚠" if rev else "✔"
        ago = "nến cuối" if s["bars_ago"] == 0 else f"{s['bars_ago']} nến trước"
        items.append(
            f'<div class="dv-item {"rev" if rev else "con"} {s["dir"]}">'
            f'<div class="dv-top"><span class="dv-tf">{esc(TF_NAME.get(s["tf"], s["tf"]))}</span>'
            f'<span class="dv-name">{icon} {esc(s["name"])}</span>'
            f'<span class="dv-tag">{esc(s["group"])} · {esc(s["label"].strip("[]").split(" - ", 1)[1])}</span></div>'
            f'<div class="dv-det">{esc(s["text"])} <i>(pivot sau: {ago})</i></div>'
            f'<div class="dv-hint">{esc(s["hint"])}</div></div>')
    return '<div class="dv-wrap" aria-label="Phân kỳ RSI">' + "".join(items) + '</div>'
