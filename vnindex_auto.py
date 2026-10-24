"""Tự động soạn nhận định VNINDEX (phiên / tuần / tháng / quý) từ dữ liệu, không cần viết tay và không phụ thuộc Streamlit.

Cách làm: dùng luật cố định trên giá, khối lượng, độ rộng, dòng tiền theo nhóm ngành, khối ngoại (nếu có) và tin RSS.
KHÔNG phải mô hình ngôn ngữ: câu chữ theo mẫu, các con số và mốc giá đều tính trực tiếp từ dữ liệu nên kiểm tra lại được.

    compose(...) -> {"title", "meta", "sections"}      cùng định dạng với parse_text() của vnindex_view
    to_md(res)   -> văn bản .md (người dùng sửa tay được, rồi lưu thành data/vnindex_nhan_dinh/YYYY-MM-DD.md)

Thứ tự ưu tiên của từng khung:
  TIN TỨC   tin RSS liên quan thị trường kể từ phiên gần nhất -> mở rộng cửa sổ (đánh dấu "gần nhất") -> bản tin Góc nhìn thị trường
            gần nhất -> bối cảnh kỹ thuật khung tuần / tháng / quý (luôn có, để khung không bao giờ trống)
  DÒNG TIỀN tính từ giá + khối lượng của rổ mã, độ rộng, nhóm ngành, khối ngoại
  HÀNH ĐỘNG suy ra từ trạng thái xu hướng, vùng hỗ trợ / kháng cự, so sánh lực mua - bán
"""
from __future__ import annotations

import re
import unicodedata

import numpy as np
import pandas as pd

O, H, L, C, V = "Giá mở cửa", "Giá cao nhất", "Giá thấp nhất", "Giá đóng cửa", "Khối lượng khớp lệnh"
INDEX_CODES = {"VNINDEX", "VN-INDEX", "VNI", "VN INDEX", "^VNINDEX"}

TF_LABEL = {"D": "Phiên", "W": "Tuần", "M": "Tháng", "Q": "Quý"}
TF_NOUN = {"D": "phiên", "W": "tuần", "M": "tháng", "Q": "quý"}
TF_BARS = {"D": 1, "W": 5, "M": 21, "Q": 63}                     # số phiên của một kỳ, dùng cho dòng tiền
TF_PREV = {"D": ("20 phiên gần nhất", 20), "W": ("4 tuần trước", 4), "M": ("3 tháng trước", 3), "Q": ("2 quý trước", 2)}
MA_SET = {"D": (20, 50, 200), "W": (10, 30, 52), "M": (6, 12, 24), "Q": (4, 8, 12)}
OFFS = {"D": (0, 3, 6, 16), "W": (0, 2, 4, 10), "M": (0, 1, 2, 6), "Q": (0, 1, 2, 4)}     # số nến sau nến cuối của mũi tên kịch bản
ZONE_BACK = {"D": 7, "W": 4, "M": 3, "Q": 2}
RIGHT = {"D": 36, "W": 26, "M": 16, "Q": 10}
N_SHOW = {"D": 75, "W": 80, "M": 60, "Q": 40}
MIN_BARS = {"D": 30, "W": 30, "M": 24, "Q": 15}                # số nến tối thiểu để tính chỉ báo
ZONE_K = {"D": 1.0, "W": 0.5, "M": 0.35, "Q": 0.3}             # nến tuần/tháng/quý có ATR lớn nên hộp vùng thu hẹp lại
STATE_TXT = {"tăng": "xu hướng tăng", "hồi": "nhịp hồi phục", "ngang": "đi ngang tích lũy", "giảm": "xu hướng giảm"}

THEMES = {           # từ khóa (đã bỏ dấu, chữ thường) -> trọng số liên quan tới chỉ số
    "vn-index": 3, "vnindex": 3, "chung khoan": 2, "thi truong": 1, "lai suat": 3, "ty gia": 2, "dxy": 2, "fed": 2,
    "khoi ngoai": 2, "margin": 2, "thanh khoan": 1, "trai phieu": 1, "nang hang": 3, "ftse": 2, "lam phat": 2, "cpi": 1,
    "gdp": 2, "ngan hang nha nuoc": 2, "nhnn": 2, "gia dau": 1, "thue quan": 2, "tang truong": 1, "vingroup": 1, "vic": 1,
    "nghi quyet": 1, "bat dong san": 1, "dau tu cong": 1, "xuat khau": 1, "kinh te": 1,
}


def plain(s: str) -> str:
    s = unicodedata.normalize("NFD", str(s).replace("đ", "d").replace("Đ", "D"))
    return "".join(ch for ch in s if unicodedata.category(ch) != "Mn").lower()


# ------------------------------------------------------------------ GIÁ THEO KỲ
def resample_period(d: pd.DataFrame, tf: str) -> pd.DataFrame:
    """Gộp nến Ngày thành Tuần (T2-T6) / Tháng / Quý. Nến kỳ cuối có thể chưa đủ kỳ (đang hình thành)."""
    if tf == "D":
        return d.reset_index(drop=True)
    key = {"W": d["Ngày"].dt.to_period("W-FRI"), "M": d["Ngày"].dt.to_period("M"), "Q": d["Ngày"].dt.to_period("Q")}[tf]
    g = d.groupby(key)
    return pd.DataFrame({"Ngày": g["Ngày"].last(), O: g[O].first(), H: g[H].max(), L: g[L].min(), C: g[C].last(),
                         V: g[V].sum()}).reset_index(drop=True)


def next_session(last: pd.Timestamp, tf: str) -> tuple[pd.Timestamp, str]:
    """(ngày phiên đầu tiên của kỳ được nhận định, tiêu đề). Dữ liệu đến `last` nên nhận định cho kỳ chứa phiên kế tiếp."""
    nxt = (pd.Timestamp(last) + pd.offsets.BDay(1)).normalize()
    if tf == "D":
        return nxt, f"VNINDEX · NHẬN ĐỊNH PHIÊN {nxt:%d/%m}"
    if tf == "W":
        a = nxt - pd.Timedelta(days=nxt.weekday())
        return nxt, f"VNINDEX · NHẬN ĐỊNH TUẦN {a:%d/%m} - {a + pd.Timedelta(days=4):%d/%m}"
    if tf == "M":
        return nxt, f"VNINDEX · NHẬN ĐỊNH THÁNG {nxt.month}/{nxt.year}"
    return nxt, f"VNINDEX · NHẬN ĐỊNH QUÝ {(nxt.month - 1) // 3 + 1}/{nxt.year}"


def _rsi(c: pd.Series, n: int = 14) -> pd.Series:
    d = c.diff()
    up, dn = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean(), (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


def _pivots(s: np.ndarray, w: int, kind: str) -> list[int]:
    out = []
    for i in range(w, len(s) - w):
        seg = s[i - w:i + w + 1]
        if (kind == "low" and s[i] == seg.min()) or (kind == "high" and s[i] == seg.max()):
            out.append(i)
    return out


def technical_view(d: pd.DataFrame, tf: str) -> dict | None:
    """Trạng thái xu hướng, hỗ trợ / kháng cự gần nhất, RSI, ATR, so sánh lực mua - bán của 10 nến cuối."""
    if len(d) < MIN_BARS[tf]:
        return None
    c, h, l = d[C].astype(float), d[H].astype(float), d[L].astype(float)
    k1, k2, k3 = MA_SET[tf]
    m1, m2, m3 = (c.rolling(k).mean() for k in (k1, k2, k3))
    close = float(c.iloc[-1])
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    atr = float(tr.rolling(14).mean().iloc[-1])
    rsi = float(_rsi(c).iloc[-1])
    a1, a2, a3 = (float(m.iloc[-1]) if pd.notna(m.iloc[-1]) else None for m in (m1, m2, m3))

    s = 0
    for m in (a1, a2, a3):
        if m is not None:
            s += 1 if close > m else -1
    if a1 is not None and a2 is not None:
        s += 1 if a1 > a2 else -1
    if len(m1) > 6 and pd.notna(m1.iloc[-6]) and a1 is not None:
        s += 1 if a1 > float(m1.iloc[-6]) else -1
    s += 1 if rsi > 55 else -1 if rsi < 45 else 0
    r5 = close / float(c.iloc[-6]) - 1
    s += 1 if r5 > 0.015 else -1 if r5 < -0.015 else 0
    state = "tăng" if s >= 4 else "hồi" if s >= 1 else "ngang" if s >= -1 else "giảm"

    w = 3 if tf == "D" else 2
    lo_arr, hi_arr = l.to_numpy()[-130:], h.to_numpy()[-130:]
    sup_c = [float(lo_arr[i]) for i in _pivots(lo_arr, w, "low") if 0.88 * close < lo_arr[i] < 0.997 * close]
    res_c = [float(hi_arr[i]) for i in _pivots(hi_arr, w, "high") if 1.003 * close < hi_arr[i] < 1.15 * close]
    base = float(l.tail(5).min())
    support = max(sup_c) if sup_c else min(base, close - 1.5 * atr)
    resist = min(res_c) if res_c else (float(h.tail(60).max()) if float(h.tail(60).max()) > close * 1.003 else close + 3 * atr)

    t = d.tail(11)
    chg = t[C].diff().iloc[1:]
    vol = t[V].iloc[1:]
    up_vol, dn_vol = float(vol[chg > 0].sum()), float(vol[chg < 0].sum())
    return dict(close=close, atr=atr, rsi=rsi, state=state, score=s, ma=(a1, a2, a3), ma_n=(k1, k2, k3), base=base,
                support=float(support), resist=float(resist), buyers=up_vol >= dn_vol, up_vol=up_vol, dn_vol=dn_vol,
                near_support=(close - float(support)) <= 1.5 * atr, ret5=r5)


def _r5(x: float, up: bool = False) -> float:
    return float(np.ceil(x / 5) * 5 if up else np.floor(x / 5) * 5)


def scenario(v: dict, tf: str) -> dict:
    """Vùng hộp + mũi tên kịch bản + nhãn, tính từ trạng thái xu hướng."""
    c, st = v["close"], v["state"]
    atr = max(v["atr"], c * 0.004)
    z = atr * ZONE_K[tf]
    a1 = v["ma"][0]
    sup, base = v["support"], v["base"]
    if st == "tăng":
        anchor = sup if abs(sup - c) < 4 * atr else (a1 or c - 2 * atr)
        zlo, zhi = anchor - 0.5 * z, anchor + 0.8 * z
    elif st == "giảm" and not v["near_support"]:
        zlo, zhi = sup - 0.5 * z, sup + 0.8 * z
    else:       # hồi / ngang / giảm sát hỗ trợ: neo vào hỗ trợ gần nhất nếu nó nằm trên đáy gần đây và không quá xa giá
        anchor = sup if (sup >= base and c - sup <= 3 * atr) else base
        zlo, zhi = anchor - 0.3 * z, anchor + 1.4 * z
    zlo, zhi = _r5(zlo), _r5(zhi, True)
    mid = round((zlo + zhi) / 20) * 10
    buyers = v["buyers"]
    kind = "VÙNG TEST LẠI" if st == "tăng" else "VÙNG MUA GOM" if buyers else "VÙNG HỖ TRỢ"
    label = f"{kind} ~{mid:.0f}đ ({'MUA > BÁN' if buyers else 'BÁN > MUA'})"

    R = v["resist"]
    rebound = st in ("tăng", "hồi") or (st == "giảm" and buyers and v["near_support"]) or (st == "ngang" and buyers)
    if rebound:
        if st in ("tăng", "hồi"):
            tgt = R if R - c >= 0.8 * atr else R + 0.8 * atr          # sát kháng cự thì kịch bản là vượt kháng cự
        else:
            tgt = c + 0.5 * (R - c)
        tgt = max(tgt, c + 0.8 * atr)
        color, tag = "xanh", ("TIẾP ĐÀ TĂNG" if st == "tăng" else "HỒI PHỤC" if st == "hồi" else "NHỊP HỒI KỸ THUẬT")
    elif st == "ngang":
        tgt, color, tag = c + 0.3 * atr, "vang", "ĐI NGANG BIÊN ĐỘ"
    else:
        tgt, color, tag = min(zlo - 0.8 * atr, c - 1.5 * atr), "do", "RỦI RO GIẢM THÊM"
    o = OFFS[tf]
    sgn = 1 if tgt >= c else -1
    pts = [(o[0], c), (o[1], c + sgn * 0.5 * atr), (o[2], c + 0.03 * (tgt - c)), (o[3], tgt)]
    return dict(zlo=zlo, zhi=zhi, mid=mid, label=label, kind=kind, tgt=float(tgt), color=color, tag=tag,
                path=", ".join(f"{a}:{b:.2f}" for a, b in pts), rebound=rebound, extended=c > zhi + atr)


# ------------------------------------------------------------------ HÀNH ĐỘNG / BỐI CẢNH
def action_items(v: dict, sc: dict, tf: str) -> list[dict]:
    zlo, zhi, R, S = sc["zlo"], sc["zhi"], v["resist"], v["support"]
    zone = f"{zlo:,.0f}-{zhi:,.0f}"
    st, k1 = v["state"], MA_SET[tf][0]
    items = []
    if sc["rebound"] and st in ("tăng", "hồi"):
        buy = (f"CHIỀU MUA : chờ nhịp rung lắc về {zone} để giải ngân từng phần, không mua đuổi ở {v['close']:,.0f}"
               if sc["extended"] else f"CHIỀU MUA : giải ngân từng phần quanh {zone}, dừng lỗ nếu thủng {zlo:,.0f}")
        items.append(dict(tone="xanh", text=buy, subs=[f"Đang nắm giữ => tiếp tục nắm giữ khi chỉ số còn trên {zlo:,.0f}"]))
        items.append(dict(tone="do", text=f"CHIỀU BÁN : chốt từng phần khi chạm kháng cự {R:,.0f} hoặc cổ phiếu tăng nóng 10 - 15% => xoay vòng", subs=[]))
    elif st == "ngang" or sc["rebound"]:
        items.append(dict(tone="xanh", text=f"CHIỀU MUA : chỉ mua ở biên dưới {zone}, không mua đuổi khi chỉ số tiến sát {R:,.0f}",
                          subs=[f"Đang nắm giữ => giữ tỷ trọng vừa phải, thủng {zlo:,.0f} thì hạ bớt"]))
        items.append(dict(tone="do", text=f"CHIỀU BÁN : hạ tỷ trọng khi chạm biên trên {R:,.0f} mà thanh khoản không tăng", subs=[]))
    else:
        items.append(dict(tone="xanh", text=f"CHIỀU MUA : chưa mua mới, chờ nến đảo chiều và thanh khoản tăng quanh {zone}",
                          subs=[f"Đang nắm giữ => hạ tỷ trọng nếu thủng {zlo:,.0f}"]))
        ma1 = v["ma"][0]
        extra = f"; hồi lên MA{k1} ({ma1:,.0f}) là nhịp để giảm hàng" if ma1 and ma1 > v["close"] else ""
        items.append(dict(tone="do", text=f"CHIỀU BÁN : thủng {zlo:,.0f} => cắt lỗ / hạ tỷ trọng{extra}", subs=[]))
    items.append(dict(tone="vang", text=f"* {sc['kind']} {zone} = {'MUA > BÁN' if v['buyers'] else 'BÁN > MUA'} (khối lượng 10 nến gần nhất)", subs=[]))
    items.append(dict(tone="vang", text=f"* Kháng cự {R:,.0f} · Hỗ trợ {S:,.0f} · Kịch bản vô hiệu nếu đóng cửa dưới {zlo:,.0f}", subs=[]))
    return items


def context_line(v: dict, tf: str) -> str:
    k1 = MA_SET[tf][0]
    m1 = v["ma"][0]
    pos = "" if m1 is None else f", {'trên' if v['close'] > m1 else 'dưới'} MA{k1} ({m1:,.0f})"
    return f"Khung {TF_NOUN[tf]}: {STATE_TXT[v['state']]}{pos}, RSI {v['rsi']:.0f}, hỗ trợ {v['support']:,.0f}, kháng cự {v['resist']:,.0f}"


# ------------------------------------------------------------------ DÒNG TIỀN
def build_panel(raw: pd.DataFrame) -> dict:
    """Bảng Ngày x Mã của rổ cổ phiếu (không gồm chỉ số): giá đóng cửa và giá trị khớp (tỷ đồng, giá nghìn đồng x cổ phiếu / 1e6)."""
    r = raw[["Mã", "Ngày", C, V]].copy()
    r["Mã"] = r["Mã"].astype(str).str.upper().str.strip()
    r = r[~r["Mã"].isin(INDEX_CODES)].drop_duplicates(["Ngày", "Mã"], keep="last")
    close = r.pivot(index="Ngày", columns="Mã", values=C).sort_index()
    vol = r.pivot(index="Ngày", columns="Mã", values=V).reindex(close.index).fillna(0)
    return {"close": close, "value": close.fillna(0) * vol / 1e6}


def _window_sum(s: pd.Series, i: int, k: int, j: int) -> float | None:
    a, b = i - k * j - k + 1, i - k * j + 1
    return float(s.iloc[a:b].sum()) if a >= 0 else None


def flow_lines(panel: dict, groups: dict, end: pd.Timestamp, tf: str, foreign: pd.Series | None = None) -> list[tuple[str, str]]:
    close, value = panel["close"], panel["value"]
    pos = close.index[close.index <= pd.Timestamp(end)]
    if len(pos) == 0:
        return []
    i = close.index.get_loc(pos[-1])
    k = TF_BARS[tf]
    desc, m = TF_PREV[tf]
    if i < k * 2 + 2:
        return []
    out: list[tuple[str, str]] = []
    ret = (close.iloc[i] / close.iloc[i - k] - 1).dropna()
    tot = value.sum(axis=1)
    cur = _window_sum(tot, i, k, 0)
    prev = [x for x in (_window_sum(tot, i, k, j) for j in range(1, m + 1)) if x is not None]
    if cur is not None and prev:
        ratio = cur / (sum(prev) / len(prev)) - 1
        out.append(("", f"GTGD rổ theo dõi {cur:,.0f} tỷ, {'tăng' if ratio >= 0 else 'giảm'} {abs(ratio) * 100:.0f}% so với trung bình {desc}"))
    flat = 0.0005 if tf == "D" else 0.0
    up, dn = int((ret > flat).sum()), int((ret < -flat).sum())
    if up + dn:
        out.append(("", f"Độ rộng {TF_NOUN[tf]}: {up} mã tăng / {dn} mã giảm ({up / (up + dn) * 100:.0f}% mã tăng) trong rổ {len(ret)} mã"))
    rows = []
    for g, codes in groups.items():
        cs = [c for c in codes if c in close.columns]
        if len(cs) < 3:
            continue
        gv = value[cs].sum(axis=1)
        gc = _window_sum(gv, i, k, 0)
        gp = [x for x in (_window_sum(gv, i, k, j) for j in range(1, m + 1)) if x is not None and x > 0]
        gr = ret.reindex(cs).dropna()
        if gc is None or not gp or gr.empty or not cur or gc / cur < 0.02:
            continue
        rows.append((g, gc / (sum(gp) / len(gp)) - 1, float(gr.median()) * 100))
    inflow = sorted([r for r in rows if r[1] > 0.1 and r[2] > 0], key=lambda r: r[1], reverse=True)[:3]
    outflow = sorted([r for r in rows if r[2] < 0 and r[1] < 0], key=lambda r: r[2])[:2]
    if inflow:
        out.append(("xanh", "Tiền vào: " + ", ".join(f"{g} (GTGD +{a * 100:.0f}%, giá {b:+.1f}%)" for g, a, b in inflow)))
    if outflow:
        out.append(("do", "Nhóm yếu: " + ", ".join(f"{g} (giá {b:+.1f}%, GTGD {a * 100:+.0f}%)" for g, a, b in outflow)))
    if foreign is not None and len(foreign):
        a, b = close.index[i - k + 1], close.index[i]
        f = foreign[(foreign.index >= a) & (foreign.index <= b)]
        if len(f):
            x = float(f.sum())
            out.append(("xanh" if x > 0 else "do", f"Khối ngoại {'mua' if x > 0 else 'bán'} ròng {abs(x):,.0f} tỷ đồng ({TF_NOUN[tf]})"))
    return out


# ------------------------------------------------------------------ TIN TỨC
def _short(t: str, n: int = 96) -> str:
    t = re.sub(r"\s+", " ", t).strip()
    return t if len(t) <= n else t[:n].rsplit(" ", 1)[0] + "…"


def _score(title: str) -> int:
    p = " " + re.sub(r"[^a-z0-9\- ]+", " ", plain(title)) + " "
    return sum(w for k, w in THEMES.items() if (f" {k} " in p if len(k) <= 4 else k in p))


def pick_news(items: list[dict], last_data: pd.Timestamp, session: pd.Timestamp, tf: str, limit: int = 4) -> tuple[list[str], str | None]:
    """Chọn tin liên quan chỉ số. Trả về (các dòng, ghi chú nếu phải dùng tin cũ hơn cửa sổ chuẩn)."""
    wins = {"D": [(last_data, None), (last_data - pd.Timedelta(days=3), "gần nhất"), (last_data - pd.Timedelta(days=10), "gần nhất")],
            "W": [(session - pd.Timedelta(days=7), None), (session - pd.Timedelta(days=14), "gần nhất")],
            "M": [(session - pd.Timedelta(days=31), None), (session - pd.Timedelta(days=62), "gần nhất")],
            "Q": [(session - pd.Timedelta(days=92), None), (session - pd.Timedelta(days=183), "gần nhất")]}[tf]
    dated = [x for x in items if x.get("date") is not None and pd.Timestamp(x["date"]) < session + pd.Timedelta(days=1)]
    out, seen, note_used = [], set(), None
    for start, note in wins:
        cand = sorted(((_score(x["title"]), pd.Timestamp(x["date"]), x) for x in dated if pd.Timestamp(x["date"]) >= start and _score(x["title"]) >= 2),
                      key=lambda t: (t[0], t[1]), reverse=True)
        for _, dt, x in cand:
            key = " ".join(plain(x["title"]).split()[:6])
            if key in seen:
                continue
            seen.add(key)
            out.append(_short(x["title"]))
            if note:
                note_used = note
            if len(out) >= limit:
                return out, note_used
        if len(out) >= 2:          # cửa sổ chuẩn đã đủ tin thì dừng, không kéo tin cũ vào
            break
    return out, note_used


# ------------------------------------------------------------------ GHÉP KẾT QUẢ
def compose(d_daily: pd.DataFrame, panel: dict | None, groups: dict, tf: str, news_items: list[dict] | None = None,
            manual_entries: list[dict] | None = None, foreign: pd.Series | None = None) -> dict | None:
    """d_daily: nến Ngày VNINDEX đã sắp xếp. Trả về {"title","meta","sections"} hoặc None nếu thiếu dữ liệu."""
    if d_daily is None or d_daily.empty:
        return None
    last = pd.Timestamp(d_daily["Ngày"].iloc[-1])
    dtf = resample_period(d_daily, tf)
    v = technical_view(dtf, tf)
    if v is None:
        return None
    session, title = next_session(last, tf)
    sc = scenario(v, tf)
    meta = {"khung": tf, "du_lieu_den": f"{last:%Y-%m-%d}", "vung": f"{sc['zlo']:.0f}-{sc['zhi']:.0f}", "vung_tu": str(ZONE_BACK[tf]),
            "nhan_vung": sc["label"], "duong_di": sc["path"], "nhan_duong_di": sc["tag"], "mau_duong_di": sc["color"],
            "so_nen": str(N_SHOW[tf]), "khoang_phai": str(RIGHT[tf]), "chan_trang": "NHẬN ĐỊNH TỰ ĐỘNG · THAM KHẢO",
            "nguon": "Dữ liệu EOD + RSS"}

    # --- TIN TỨC
    news, note = pick_news(news_items or [], last, session, tf)
    name = "TIN TỨC" + (f" · {note.upper()}" if note else "")
    items = [dict(tone="", text=t, subs=[]) for t in news]
    if len(items) < 2:
        me = next((e for e in (manual_entries or []) if pd.Timestamp(e["date"]) <= session), None)
        if me:
            items.append(dict(tone="", text=f"Nhận định gần nhất ({pd.Timestamp(me['date']):%d/%m}): {_short(me['title'], 110)}", subs=[]))
    if len(items) < 3:       # luôn có bối cảnh các khung lớn hơn để khung không trống
        for big in ("W", "M", "Q"):
            if big == tf or len(items) >= 4:
                continue
            vb = technical_view(resample_period(d_daily, big), big)
            if vb:
                items.append(dict(tone="", text=context_line(vb, big), subs=[]))
        if not news:
            name = "TIN TỨC · CHƯA CÓ TIN MỚI"
    sections = [dict(name=name, items=items)]

    # --- DÒNG TIỀN
    fl = flow_lines(panel, groups, last, tf, foreign) if panel is not None else []
    fl_items = [dict(tone=t, text=x, subs=[]) for t, x in fl] or [dict(tone="", text="Chưa đủ dữ liệu rổ cổ phiếu để tính dòng tiền", subs=[])]
    fl_items.insert(0, dict(tone="", text=f"VN-Index {v['close']:,.0f}đ, lực mua {'>' if v['buyers'] else '<'} lực bán (khối lượng 10 nến gần nhất)", subs=[]))
    sections.append(dict(name="DÒNG TIỀN", items=fl_items))

    # --- HÀNH ĐỘNG
    sections.append(dict(name="HÀNH ĐỘNG", items=action_items(v, sc, tf)))
    return {"title": title, "meta": meta, "sections": sections, "session": session, "view": v, "scenario": sc}


def to_md(res: dict) -> str:
    lines = [f"# {res['title']}"]
    lines += [f"@{k}: {v}" for k, v in res["meta"].items()]
    for s in res["sections"]:
        lines += ["", f"## {s['name']}"]
        for it in s["items"]:
            lines.append(f"- {'[' + it['tone'] + '] ' if it['tone'] else ''}{it['text']}")
            lines += [f"  {x}" for x in it["subs"]]
    return "\n".join(lines) + "\n"
