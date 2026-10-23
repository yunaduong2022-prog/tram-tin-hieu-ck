"""Phân tích Wyckoff cho một khung thời gian (không phụ thuộc Streamlit).

Quy trình:
1. Tìm vùng đi ngang gần nhất (biên chạm nhiều lần, giá cắt đường giữa nhiều lần).
2. Phân loại tích lũy / phân phối theo xu hướng trước đó và hướng giá thoát khỏi vùng.
3. Dò các sự kiện theo volume và biên độ nến: SC, AR, ST, Spring, Test, SOS, LPS (tích lũy)
   hoặc BC, AR, ST, UT/UTAD, Test, SOW, LPSY (phân phối). Kịch bản phân phối chạy trên dữ liệu
   đảo dấu (gương) nên dùng chung một hàm dò.
4. Xác định pha A-E, mốc xác nhận, mốc vô hiệu.

Đây là quy tắc máy tính áp lên giá và volume nên mang tính chủ quan; chỉ để quan sát.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

OPEN, HIGH, LOW, CLOSE, VOL = "Giá mở cửa", "Giá cao nhất", "Giá thấp nhất", "Giá đóng cửa", "Khối lượng khớp lệnh"
MIN_BARS = 120
# Vùng đi ngang chỉ tính khi (đỉnh - đáy) / đáy <= MAX_AMP. Phiên làm giá vượt khỏi khung này nhưng các phiên sau quay lại
# trong khung cũ (cụm tối đa MAX_FB_RUN phiên liên tiếp) là BREAKOUT GIẢ: vẫn tính vào số nến đi ngang, loại khỏi biên trên/dưới.
MAX_AMP = 0.10
MAX_FB_RUN = 3
MAX_FB_SHARE = 0.10      # tổng phiên breakout giả tối đa 10% độ dài vùng (tối thiểu cho phép 3 phiên): vùng phải phần lớn nằm trong khung
OFFSETS = (0, 3, 6, 10, 15, 20, 30, 45)


PHASE_TEXT = {
    "dist": {"A": "Đà tăng bị chặn (BC, AR). Lực mua bắt đầu cạn nhưng chưa xác nhận đỉnh.",
             "B": "Xây dựng nguyên nhân. Giá dao động trong biên, các nhịp ST kiểm tra lại đỉnh. Cần chờ UT hoặc SOW.",
             "C": "Upthrust đã xuất hiện, bước thử cầu cuối cùng. Chờ SOW để xác nhận phân phối.",
             "D": "SOW đã thủng biên dưới, giá chuyển từ đi ngang sang xu hướng giảm. LPSY là vùng hồi tham khảo.",
             "E": "Giá đã rời biên theo hướng giảm (markdown)."},
    "acc": {"A": "Đà giảm bị chặn (SC, AR). Cung bắt đầu cạn nhưng chưa xác nhận đáy.",
            "B": "Xây dựng nguyên nhân. Giá dao động trong biên, các nhịp ST kiểm tra lại đáy. Cần chờ Spring hoặc SOS.",
            "C": "Spring đã xuất hiện, bước thử cung cuối cùng. Chờ SOS để xác nhận tích lũy.",
            "D": "SOS đã vượt biên trên, giá chuyển từ đi ngang sang xu hướng tăng. LPS là vùng lùi tham khảo.",
            "E": "Giá đã rời biên theo hướng tăng (markup)."},
}


def _fmt(x: float) -> str:
    return f"{x:,.2f}"


def _edges(h, l, s, e, fb=(), frame=None):
    """Biên trên / dưới của vùng [s, e]: bỏ các phiên breakout giả (đóng cửa vượt khung rồi quay lại) và các phiên có bóng nến
    chọc ra ngoài khung 10% (đó là Spring / Upthrust, không phải biên của vùng)."""
    skip = set(fb)
    keep = [i for i in range(s, e + 1) if i not in skip and (frame is None or (l[i] >= frame[0] and h[i] <= frame[1]))]
    if not keep:
        keep = [i for i in range(s, e + 1) if i not in skip] or list(range(s, e + 1))
    return float(np.max(h[keep])), float(np.min(l[keep]))


def _find_range(h, l, c, atr, end):
    """Tìm vùng đi ngang dài nhất kết thúc tại `end` mà phần lớn các phiên nằm trong một khung biên độ <= MAX_AMP.

    Với mỗi khung ứng viên [x, x*(1+MAX_AMP)] (bước 0,5%), quét ngược từ nến cuối: phiên nằm trong khung là phiên đi ngang;
    cụm <= MAX_FB_RUN phiên liên tiếp ĐÓNG CỬA ngoài khung rồi giá lại quay vào khung cũ là breakout giả (vẫn tính vào độ dài vùng);
    cụm dài hơn thì vùng dừng lại ở đó. Sau đó kiểm tra như cũ: biên đủ rộng (>= 2,5 ATR), chạm mỗi biên >= 2 lần, giá cắt đường giữa >= 4 lần.
    """
    a = atr[end]
    if not np.isfinite(a) or a <= 0 or end < 40:
        return None
    back = min(260, end + 1)
    s0 = end - back + 1
    H, Lw = h[s0:end + 1], l[s0:end + 1]
    ok = np.isfinite(H) & np.isfinite(Lw) & (Lw > 0)
    if not ok[-1]:
        return None
    lo_all, hi_all = float(np.min(Lw[ok])), float(np.max(H[ok]))
    nk = int(math.ceil(math.log(max(hi_all / lo_all, 1.0001)) / math.log(1.005))) + 1
    xs = lo_all * 1.005 ** np.arange(0, nk + 1)
    C = c[s0:end + 1]
    ok &= np.isfinite(C)
    # phiên "đi ngang" = đóng cửa nằm trong khung; bóng nến chọc ra ngoài (kiểu Spring / Upthrust) vẫn là đi ngang, chỉ không tính vào biên
    inside = (C[None, :] >= xs[:, None]) & (C[None, :] <= xs[:, None] * (1 + MAX_AMP)) & ok[None, :]
    full = inside & (Lw[None, :] >= xs[:, None]) & (H[None, :] <= xs[:, None] * (1 + MAX_AMP))
    alive = inside[:, -1].copy()
    if not alive.any():
        return None
    ext = np.full(len(xs), back - 1)
    run = np.zeros(len(xs), dtype=int)
    for j in range(back - 2, -1, -1):
        ins = inside[:, j]
        run = np.where(ins, 0, run + 1)
        alive &= run <= MAX_FB_RUN
        if not alive.any():
            break
        ext = np.where(alive & ins, j, ext)
    span = np.where(inside[:, -1], back - ext, 0)
    order = [int(i) for i in np.argsort(-span, kind="stable") if span[i] >= 30][:12]
    best = None
    for xi in order:
        L0 = int(span[xi])
        for Lt in range(L0, 29, -5):
            sl_ = back - Lt
            m = inside[xi, sl_:]
            if not m.any():
                continue
            sl_ += int(np.argmax(m))
            m = inside[xi, sl_:]
            L = back - sl_
            if L < 30:
                break
            nfb = int((~m).sum())
            if nfb > max(3, MAX_FB_SHARE * L):
                continue
            mf = full[xi, sl_:]
            if not mf.any():
                continue
            sh, sl2 = H[sl_:][mf], Lw[sl_:][mf]
            hi, lo = float(np.max(sh)), float(np.min(sl2))
            W = hi - lo
            if W < 2.5 * a:
                continue
            mid = (hi + lo) / 2
            idx = np.flatnonzero(mf)
            ti, bi = idx[sh >= hi - 0.2 * W], idx[sl2 <= lo + 0.2 * W]
            top_t = 1 + int((np.diff(ti) >= 5).sum()) if len(ti) else 0
            bot_t = 1 + int((np.diff(bi) >= 5).sum()) if len(bi) else 0
            s = s0 + sl_
            side = np.where(c[s:end + 1] > mid, 1, -1)
            cross = int((np.diff(side) != 0).sum())
            if top_t >= 2 and bot_t >= 2 and cross >= 4:
                cand = {"s": s, "e": end, "L": L, "top": hi, "bot": lo, "mid": mid, "W": W,
                        "fb": [s + int(i) for i in np.flatnonzero(~m)],
                        "frame": (float(xs[xi]), float(xs[xi]) * (1 + MAX_AMP))}
                if best is None or (L, -nfb) > (best["L"], -len(best["fb"])):
                    best = cand
                break
    return best


def _events(o, h, l, c, vr, spr, tr, prior, last):
    """Dò sự kiện theo kịch bản TÍCH LŨY (dữ liệu phân phối đã được đảo dấu trước khi vào đây)."""
    s, top, bot, W = tr["s"], tr["top"], tr["bot"], tr["W"]
    ev = []

    def swing_low(i):
        return all(l[j] >= l[i] for j in range(max(0, i - 2), min(last, i + 2) + 1))

    # SC: nến bán tháo gần đáy, volume lớn, biên độ rộng
    sc, best = -1, -1.0
    if prior != "up":
        hi_i = min(last, s + max(25, int(math.floor(0.6 * (tr["e"] - s + 1) + 0.5))))
        for i in range(max(1, s - 8), hi_i + 1):
            if l[i] <= bot + 0.3 * W and vr[i] >= 1.5 and spr[i] >= 1.2:
                q = vr[i] * spr[i]
                if q > best:
                    best, sc = q, i
    if sc >= 0:
        ev.append({"k": "CLIMAX", "i": sc, "pos": "lo"})
    # AR: nhịp hồi tự động sau SC, định ra biên trên
    ar = -1
    if sc >= 0:
        m = -np.inf
        for i in range(sc + 2, min(last, sc + 30) + 1):
            if h[i] > m:
                m, ar = h[i], i
    if ar >= 0:
        ev.append({"k": "AR", "i": ar, "pos": "hi"})
    R = h[ar] if ar >= 0 else top
    Sup = l[sc] if sc >= 0 else bot
    start = max(s + 10, ar + 5 if ar >= 0 else s + 10)
    # ST: kiểm tra lại đáy với volume nhỏ hơn SC
    st_idx = []
    if sc >= 0 and ar >= 0:
        last_st = -99
        for i in range(ar + 5, last + 1):
            if len(st_idx) >= 3:
                break
            if (Sup - 0.1 * W <= l[i] <= Sup + 0.25 * W and vr[i] < 0.85 * vr[sc]
                    and i - last_st >= 8 and swing_low(i)):
                st_idx.append(i)
                last_st = i
    # Spring: thủng đáy đã hình thành rồi đóng cửa trở lại trên đáy trong 3 nến
    sp = -1
    run = float(np.min(l[s:start])) if start > s else np.inf
    for i in range(start, last + 1):
        if run - 0.35 * W <= l[i] < run - 0.02 * W:
            for k in range(i, min(last, i + 3) + 1):
                if c[k] > run:
                    sp = i
                    break
        if l[i] < run:
            run = l[i]
    for i in st_idx:
        if i != sp:
            ev.append({"k": "ST", "i": i, "pos": "lo"})
    if sp >= 0:
        ev.append({"k": "SPRING", "i": sp, "pos": "lo"})
        for i in range(sp + 3, last + 1):
            if l[sp] <= l[i] <= l[sp] + 0.15 * W and vr[i] < 0.8 and swing_low(i):
                ev.append({"k": "TEST", "i": i, "pos": "lo"})
                break
    # SOS: nến tăng mạnh đóng cửa vượt biên trên với volume lớn (sau Spring nếu có)
    sos = -1
    for i in range(max(start, sp + 1 if sp >= 0 else start), last + 1):
        if c[i] > R and c[i] > o[i] and vr[i] >= 1.3 and spr[i] >= 0.9:
            sos = i
            break
    if sos >= 0:
        ev.append({"k": "SOS", "i": sos, "pos": "hi"})
        lp, m = -1, np.inf
        for i in range(sos + 2, min(last, sos + 25) + 1):
            if l[i] < m:
                m, lp = l[i], i
        if lp >= 0 and m >= R - 0.4 * W and m > Sup and vr[lp] <= 1.0:
            ev.append({"k": "LPS", "i": lp, "pos": "lo"})
    weak = -1
    if sos < 0:
        for i in range(start, last + 1):
            if c[i] > R and c[i] > o[i]:
                weak = i
                break
    ev.sort(key=lambda x: x["i"])
    return {"ev": ev, "R": R, "Sup": Sup, "sc": sc, "ar": ar, "sp": sp, "sos": sos, "weak": weak}


def analyze(g: pd.DataFrame):
    """Trả về dict mô tả cấu trúc Wyckoff của khung g, hoặc None nếu chưa thấy vùng đi ngang đủ rõ."""
    n = len(g)
    if n < MIN_BARS:
        return None
    o, h, l, c = (g[k].to_numpy(float) for k in (OPEN, HIGH, LOW, CLOSE))
    v = g[VOL].to_numpy(float)
    atr = g["ATR"].to_numpy(float) if "ATR" in g.columns else pd.Series(h - l).ewm(alpha=1 / 14, adjust=False).mean().to_numpy()
    vs = pd.Series(v).rolling(20, min_periods=5).mean().to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        vr = np.where(np.isfinite(vs) & (vs > 0), v / vs, 1.0)
        spr = np.where(np.isfinite(atr) & (atr > 0), (h - l) / atr, 1.0)
    vr = np.nan_to_num(vr, nan=1.0)
    spr = np.nan_to_num(spr, nan=1.0)
    dates = g["Ngày"].to_numpy()

    last = n - 1
    tr = None
    for off in OFFSETS:
        tr = _find_range(h, l, c, atr, last - off)
        if tr:
            break
    if not tr:
        return None
    s, e, top, bot, mid, W = tr["s"], tr["e"], tr["top"], tr["bot"], tr["mid"], tr["W"]
    lc = c[last]
    post = "up" if lc > top else "down" if lc < bot else "in"
    pre = c[s] - c[max(0, s - 80)]
    prior = "down" if pre < -W else "up" if pre > W else "flat"
    kind = ("acc" if post == "up" else "dist" if post == "down" else
            "acc" if prior == "down" else "dist" if prior == "up" else "unk")
    re_ = (post == "up" and prior == "up") or (post == "down" and prior == "down")
    kind_name = ("tái tích lũy" if re_ else "tích lũy") if kind == "acc" else \
        ("tái phân phối" if re_ else "phân phối") if kind == "dist" else "đi ngang (chưa phân loại)"

    def tr_dict(tr_):
        return dict(tr_, s_date=pd.Timestamp(dates[tr_["s"]]), e_date=pd.Timestamp(dates[tr_["e"]]))

    def fb_list(tr_):
        out = []
        for i in tr_.get("fb", ()):
            up = (h[i] - tr_["top"]) >= (tr_["bot"] - l[i])
            out.append({"i": int(i), "date": pd.Timestamp(dates[i]), "dir": "up" if up else "down",
                        "p": float(h[i] if up else l[i])})
        return out

    def fb_note(fbs):
        if not fbs:
            return ""
        part = ", ".join(f"{x['date']:%d/%m} ({'vượt biên trên' if x['dir'] == 'up' else 'thủng biên dưới'})" for x in fbs[:4])
        more = f" và {len(fbs) - 4} phiên khác" if len(fbs) > 4 else ""
        return (f"Có {len(fbs)} phiên breakout giả: {part}{more}. Giá vượt khỏi khung biên độ {MAX_AMP * 100:.0f}% nhưng các phiên sau "
                "đã quay lại khung cũ, nên vẫn tính là đi ngang và không coi là thoát vùng.")

    def span_txt(tr_):
        n = len(tr_.get("fb", ()))
        return f"{tr_['L']} nến, biên độ không quá {MAX_AMP * 100:.0f}%" + (f", gồm {n} phiên breakout giả" if n else "")

    base = {"kind": kind, "re": re_, "post": post, "prior": prior, "events": [], "phase": None,
            "phase_text": None, "lean": "wait", "score": 0, "notes": [], "kind_name": kind_name,
            "bars": n}

    if kind == "unk":
        fbs = fb_list(tr)
        base.update(tr=tr_dict(tr), pos=(lc - bot) / W, fb=fbs, notes=[fb_note(fbs)] if fbs else [],
                    title=f"Vùng {kind_name} {_fmt(bot)}–{_fmt(top)}",
                    summary=(f"Có vùng đi ngang {_fmt(bot)}–{_fmt(top)} kéo dài {span_txt(tr)}, nhưng xu hướng trước đó không rõ "
                             "nên chưa phân biệt được tích lũy hay phân phối. Theo dõi hướng giá thoát khỏi biên: đóng cửa trên "
                             f"{_fmt(top)} kèm volume lớn nghiêng về tích lũy, dưới {_fmt(bot)} kèm volume lớn nghiêng về phân phối."),
                    trigger={"p": top, "txt": f"Đóng cửa trên {_fmt(top)} kèm volume lớn"},
                    inval={"p": bot, "txt": f"Đóng cửa dưới {_fmt(bot)} kèm volume lớn"})
        return base

    dist = kind == "dist"
    if dist:   # gương: đảo dấu giá, hoán đổi cao/thấp
        P = (-o, -l, -h, -c)
        prior_g = "down" if prior == "up" else "up" if prior == "down" else "flat"
    else:
        P = (o, h, l, c)
        prior_g = prior

    def mir_tr(t_):
        return dict(t_, top=-t_["bot"], bot=-t_["top"], mid=-t_["mid"]) if dist else dict(t_)

    r = _events(*P, vr, spr, mir_tr(tr), prior_g, last)
    if r["sc"] > s + 3:  # thu hẹp vùng về đúng điểm bắt đầu (SC/BC) rồi dò lại
        s = r["sc"]
        top, bot = _edges(h, l, s, e, tr.get("fb", ()), tr.get("frame"))
        W, mid = top - bot, (top + bot) / 2
        tr = {"s": s, "e": e, "L": e - s + 1, "top": top, "bot": bot, "mid": mid, "W": W,
              "fb": [i for i in tr.get("fb", ()) if i >= s], "frame": tr.get("frame")}
        r = _events(*P, vr, spr, mir_tr(tr), prior_g, last)
    pos = (lc - bot) / W
    title = f"Vùng {kind_name} {_fmt(bot)}–{_fmt(top)}"
    dur = max(1, e - s + 1)

    LBL = ({"CLIMAX": "BC", "AR": "AR", "ST": "ST", "SPRING": "UT", "TEST": "Test", "SOS": "SOW", "LPS": "LPSY"} if dist else
           {"CLIMAX": "SC", "AR": "AR", "ST": "ST", "SPRING": "Spring", "TEST": "Test", "SOS": "SOS", "LPS": "LPS"})
    RG = r["R"]
    events = []
    for x in r["ev"]:
        i = x["i"]
        o_pos = ("hi" if x["pos"] == "lo" else "lo") if dist else x["pos"]
        p = float(l[i] if o_pos == "lo" else h[i])
        vx = f"{vr[i]:.1f}"
        label = LBL[x["k"]]
        if dist and x["k"] == "SPRING":
            label = "UTAD" if (i - s) / dur >= 0.6 else "UT"
        low_vol = vr[i] < 1
        if not dist:
            txt = {
                "CLIMAX": f"Selling Climax: nến bán tháo mạnh gần đáy, volume gấp {vx} lần trung bình. Lực bán dồn dập thường đánh dấu điểm dừng của đà giảm",
                "AR": f"Automatic Rally: nhịp hồi tự động sau SC, đỉnh nhịp này định ra biên trên của vùng ({_fmt(p)})",
                "ST": f"Secondary Test: kiểm tra lại đáy với volume {vx} lần trung bình, thấp hơn lúc SC. Lực bán đã yếu đi",
                "SPRING": "Spring: giá thủng đáy vùng rồi đóng cửa trở lại phía trên. " + (
                    "Volume thấp: nguồn cung đã cạn, Spring có chất lượng tốt hơn" if low_vol else
                    f"Volume gấp {vx} lần trung bình: có thể là cú rũ bỏ mạnh, cần nhịp Test hoặc SOS để xác nhận"),
                "TEST": f"Test: kiểm tra lại đáy Spring với volume thấp ({vx} lần trung bình) và không tạo đáy mới",
                "SOS": f"Sign of Strength: nến tăng mạnh đóng cửa vượt biên trên {_fmt(RG)} với volume gấp {vx} lần trung bình",
                "LPS": f"Last Point of Support: nhịp lùi sau SOS, giữ được trên vùng kháng cự cũ với volume cạn ({vx} lần trung bình)",
            }[x["k"]]
        else:
            txt = {
                "CLIMAX": f"Buying Climax: nến mua đuổi mạnh gần đỉnh, volume gấp {vx} lần trung bình. Lực mua dồn dập thường đánh dấu điểm dừng của đà tăng",
                "AR": f"Automatic Reaction: nhịp giảm tự động sau BC, đáy nhịp này định ra biên dưới của vùng ({_fmt(p)})",
                "ST": f"Secondary Test: kiểm tra lại đỉnh với volume {vx} lần trung bình, thấp hơn lúc BC. Lực mua đã yếu đi",
                "SPRING": "Upthrust: giá vượt đỉnh vùng rồi đóng cửa trở lại phía dưới. " + (
                    "Volume thấp: lực mua yếu, cú vượt đỉnh thiếu sức" if low_vol else
                    f"Volume gấp {vx} lần trung bình: có thể là bẫy tăng giá, cần SOW để xác nhận"),
                "TEST": f"Test: kiểm tra lại đỉnh Upthrust với volume thấp ({vx} lần trung bình), không vượt được đỉnh",
                "SOS": f"Sign of Weakness: nến giảm mạnh đóng cửa thủng biên dưới {_fmt(-RG)} với volume gấp {vx} lần trung bình",
                "LPS": f"Last Point of Supply: nhịp hồi yếu sau SOW, không vượt nổi vùng hỗ trợ cũ, volume cạn ({vx} lần trung bình)",
            }[x["k"]]
        events.append({"k": x["k"], "label": label, "i": i, "date": pd.Timestamp(dates[i]), "p": p, "pos": o_pos, "txt": txt})

    kinds = {x["k"] for x in r["ev"]}
    # pha (theo hệ quy chiếu tích lũy: kịch bản phân phối đã đảo dấu nên so sánh dùng giá đảo)
    phase = None
    lc_g = -lc if dist else lc
    if r["sos"] >= 0:
        phase = "E" if lc_g > RG + 0.5 * W else "D"
    elif r["sp"] >= 0:
        phase = "C"
    elif r["sc"] >= 0 and r["ar"] >= 0:
        phase = "B" if ("ST" in kinds or last - r["ar"] >= 15) else "A"
    PH = ({"A": "Pha A: đà tăng bị chặn (BC, AR). Lực mua bắt đầu cạn nhưng chưa xác nhận đỉnh.",
           "B": "Pha B: xây dựng nguyên nhân. Giá dao động trong biên, các nhịp ST kiểm tra lại đỉnh. Cần chờ UT hoặc SOW.",
           "C": "Pha C: Upthrust đã xuất hiện, bước thử cầu cuối cùng. Chờ SOW để xác nhận phân phối.",
           "D": "Pha D: SOW đã thủng biên dưới, giá chuyển từ đi ngang sang xu hướng giảm. LPSY là vùng hồi tham khảo.",
           "E": "Pha E: giá đã rời biên theo hướng giảm (markdown)."} if dist else
          {"A": "Pha A: đà giảm bị chặn (SC, AR). Cung bắt đầu cạn nhưng chưa xác nhận đáy.",
           "B": "Pha B: xây dựng nguyên nhân. Giá dao động trong biên, các nhịp ST kiểm tra lại đáy. Cần chờ Spring hoặc SOS.",
           "C": "Pha C: Spring đã xuất hiện, bước thử cung cuối cùng. Chờ SOS để xác nhận tích lũy.",
           "D": "Pha D: SOS đã vượt biên trên, giá chuyển từ đi ngang sang xu hướng tăng. LPS là vùng lùi tham khảo.",
           "E": "Pha E: giá đã rời biên theo hướng tăng (markup)."})
    lean = ("sell" if dist else "buy") if phase in ("C", "D", "E") else "wait"

    pts = (1 if r["sc"] >= 0 else 0) + (1 if r["ar"] >= 0 else 0) + min(2, sum(1 for x in r["ev"] if x["k"] == "ST"))
    pts += (2 if r["sp"] >= 0 else 0) + (1 if "TEST" in kinds else 0) + (2 if r["sos"] >= 0 else 0) + (1 if "LPS" in kinds else 0)
    score = min(100, int(round(pts / 10 * 100)))

    fbs = fb_list(tr)
    notes = [fb_note(fbs)] if fbs else []
    if r["sc"] < 0 and prior != "flat":
        notes.append(f"Chưa thấy {'BC' if dist else 'SC'} rõ ràng (cần nến volume lớn, biên độ rộng gần {'đỉnh' if dist else 'đáy'} của vùng).")
    if r["weak"] >= 0:
        notes.append(f"Giá đã đóng cửa {'dưới' if dist else 'trên'} biên nhưng volume không đủ lớn để gọi là {'SOW' if dist else 'SOS'}: chưa xác nhận.")
    if re_:
        notes.append(f"Giá đi tiếp theo hướng xu hướng trước đó nên đây có thể là {'tái phân phối' if dist else 'tái tích lũy'} giữa xu hướng, độ tin cậy thấp hơn so với đảo chiều.")
    if last - e > 0:
        notes.append(f"Vùng đi ngang kết thúc cách đây {last - e} nến.")

    if dist:
        trigger = {"p": -RG, "txt": (f"Vùng hỗ trợ cũ {_fmt(-RG)} nay thành kháng cự" if r["sos"] >= 0
                                     else f"Đóng cửa dưới {_fmt(-RG)} kèm volume lớn (SOW)")}
        inval = {"p": top, "txt": f"Đóng cửa trên {_fmt(top)}: kịch bản phân phối bị vô hiệu"}
        res_lv, sup_lv = -r["Sup"], -RG
    else:
        trigger = {"p": RG, "txt": (f"Vùng kháng cự cũ {_fmt(RG)} nay thành hỗ trợ" if r["sos"] >= 0
                                    else f"Đóng cửa trên {_fmt(RG)} kèm volume lớn (SOS)")}
        inval = {"p": bot, "txt": f"Đóng cửa dưới {_fmt(bot)}: kịch bản tích lũy bị vô hiệu"}
        res_lv, sup_lv = RG, r["Sup"]
    if post == "up":
        where = f"Giá đã đóng cửa trên biên trên {_fmt(top)}"
    elif post == "down":
        where = f"Giá đã đóng cửa dưới biên dưới {_fmt(bot)}"
    else:
        where = f"Giá đang ở {round(min(1.0, max(0.0, pos)) * 100)}% biên độ vùng (đáy 0%, đỉnh 100%)"
    prior_txt = {"down": "giảm", "up": "tăng", "flat": "đi ngang"}[prior]
    summary = (f"{title}, kéo dài {span_txt(tr)}, xu hướng trước đó {prior_txt}. "
               + (PH[phase] if phase else f"Chưa thấy đủ dấu hiệu đặc trưng của Wyckoff ({'BC, AR, UT, SOW' if dist else 'SC, AR, Spring, SOS'}), nên coi đây mới là vùng đi ngang.")
               + f" {where}.")
    base.update(tr=tr_dict(tr), pos=float(pos), title=title, events=events, phase=phase, fb=fbs,
                phase_text=PH[phase] if phase else None, lean=lean, score=score, notes=notes,
                trigger=trigger, inval=inval, summary=summary, where=where,
                resistance=float(res_lv), support=float(sup_lv))
    return base


def label(w) -> str:
    """Nhãn ngắn dùng cho bảng lọc."""
    if not w:
        return "-"
    if w["kind"] == "unk":
        return "Đi ngang"
    name = ("Tái tích lũy" if w["re"] else "Tích lũy") if w["kind"] == "acc" else ("Tái phân phối" if w["re"] else "Phân phối")
    return f"{name} · Pha {w['phase']}" if w["phase"] else f"{name} · chưa rõ pha"


# ------------------------------------------------------------------ KHỐI GHI CHÚ DÙNG TRONG CÁC THẺ
import html as _html

PHASE_NAME = {
    "acc": {"A": "Dừng đà giảm", "B": "Xây dựng nguyên nhân", "C": "Thử cung cuối (Spring)",
            "D": "Cầu thắng thế (SOS)", "E": "Markup, rời vùng"},
    "dist": {"A": "Chặn đà tăng", "B": "Xây dựng nguyên nhân", "C": "Thử cầu cuối (Upthrust)",
             "D": "Cung thắng thế (SOW)", "E": "Markdown, rời vùng"},
}
PHASE_HINT = {
    "acc": {"A": "Chưa phải điểm mua: chờ đáy được kiểm tra lại bằng các nhịp ST với volume nhỏ dần.",
            "B": "Giai đoạn đi ngang dài nhất. Quan sát, chưa vào lệnh; chờ Spring hoặc SOS.",
            "C": "Spring là bước thử cung cuối. Nếu có Test volume thấp rồi SOS thì xác suất tích lũy tăng; thủng đáy Spring thì kịch bản hỏng.",
            "D": "SOS đã vượt biên trên. Vùng kháng cự cũ thành hỗ trợ; nhịp lùi LPS là vùng quan sát.",
            "E": "Giá đã rời vùng tích lũy. Đã cách xa biên, rủi ro mua đuổi cao hơn."},
    "dist": {"A": "Chưa phải điểm bán: chờ đỉnh được kiểm tra lại bằng các nhịp ST với volume nhỏ dần.",
             "B": "Giai đoạn đi ngang dài nhất. Quan sát; chờ UT/UTAD hoặc SOW.",
             "C": "Upthrust là bước thử cầu cuối. Nếu có Test volume thấp rồi SOW thì xác suất phân phối tăng; đóng cửa trên đỉnh UT thì kịch bản hỏng.",
             "D": "SOW đã thủng biên dưới. Vùng hỗ trợ cũ thành kháng cự; nhịp hồi LPSY là vùng quan sát.",
             "E": "Giá đã rời vùng phân phối theo hướng giảm. Đã cách xa biên, rủi ro bán đáy cao hơn."},
}

CSS = "<style>" + " ".join("""
.wy{margin:10px 0 4px;padding:11px 13px;border-radius:10px;background:var(--card2);border:1px solid var(--line);
 border-left:3px solid var(--wy-c,#8FA89D);text-align:left;font-size:13px;line-height:1.5;color:var(--txt)}
.wy.acc{--wy-c:#2DD4A7}.wy.dist{--wy-c:#FF6B81}.wy.unk{--wy-c:#F5B942}.wy.none{--wy-c:#8FA89D}
.wy-top{display:flex;align-items:center;justify-content:space-between;gap:8px;flex-wrap:wrap}
.wy-k{font-size:11.5px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--muted)}
.wy-tag{display:inline-block;padding:3px 10px;border-radius:999px;font-size:12px;font-weight:700;white-space:nowrap;
 background:var(--tag-gray-bg);color:var(--tag-gray-fg)}
.wy.acc .wy-tag{background:var(--tag-green-bg);color:var(--tag-green-fg)}
.wy.dist .wy-tag{background:var(--tag-red-bg);color:var(--red)}
.wy.unk .wy-tag{background:var(--tag-amber-bg);color:var(--tag-amber-fg)}
.wy-steps{display:flex;gap:4px;margin:9px 0 7px}
.wy-steps span{flex:1;text-align:center;padding:2px 0;border-radius:5px;font-size:11px;font-weight:700;
 background:var(--bg2);color:var(--muted);border:1px solid var(--line2)}
.wy-steps span.on{background:var(--wy-c);color:#0E1C18;border-color:var(--wy-c)}
.wy-steps span.done{color:var(--txt);border-color:var(--wy-c)}
.wy-ph{font-weight:700;color:var(--txt2);margin-bottom:2px}
.wy-tx{color:var(--txt);font-size:12.5px}
.wy-hint{margin-top:5px;font-size:12.5px;color:var(--muted)}
.wy-lv{display:grid;grid-template-columns:1fr auto;gap:2px 10px;margin-top:8px;padding-top:7px;border-top:1px solid var(--line);
 font-size:12.5px;color:var(--muted)}
.wy-lv b{color:var(--txt2);font-variant-numeric:tabular-nums;text-align:right}
.wy-ev{margin-top:6px;font-size:12px;color:var(--muted)}
.wy-ev b{color:var(--txt2)}
.wy-ft{margin-top:6px;font-size:11px;color:var(--muted);font-style:italic}
""".split()) + "</style>"


def compact(w) -> dict | None:
    """Rút gọn kết quả analyze() thành dict nhỏ để cache cho cả rổ mã và dựng khối ghi chú."""
    if not w:
        return None
    ev = max(w["events"], key=lambda x: x["i"]) if w.get("events") else None
    return {
        "kind": w["kind"], "re": w["re"], "phase": w["phase"], "lean": w["lean"], "score": w["score"], "title": w["title"],
        "kind_name": w["kind_name"], "prior": w["prior"], "post": w["post"],
        "top": float(w["tr"]["top"]), "bot": float(w["tr"]["bot"]), "bars": int(w["tr"]["L"]),
        "trigger": w.get("trigger"), "inval": w.get("inval"),
        "last_ev": None if ev is None else {"label": ev["label"], "date": ev["date"], "p": ev["p"]},
        "notes": list(w.get("notes") or []),
        "fb": [{"date": x["date"], "p": x["p"], "dir": x["dir"]} for x in (w.get("fb") or [])],
        "amp": float((w["tr"]["top"] - w["tr"]["bot"]) / w["tr"]["bot"] * 100),
    }


def fb_line(c) -> str:
    """Dòng ghi chú breakout giả (rỗng nếu không có)."""
    fb = c.get("fb") or []
    if not fb:
        return ""
    part = "; ".join(f"<b>{pd.Timestamp(x['date']):%d/%m}</b> {'vượt biên trên' if x['dir'] == 'up' else 'thủng biên dưới'} ({fmt2(x['p'])})"
                     for x in fb[:3])
    more = f" và {len(fb) - 3} phiên khác" if len(fb) > 3 else ""
    return (f'<div class="wy-ev">Breakout giả: {part}{more}. Giá quay lại khung biên độ {MAX_AMP * 100:.0f}% cũ nên vẫn tính là đi ngang.</div>')


def note_html(c, compact_view: bool = False) -> str:
    """Khối "Wyckoff" đặt trong thẻ: pha hiện tại (A–E), tên pha, chú thích pha, mốc xác nhận / vô hiệu, sự kiện mới nhất.
    c là dict từ compact() hoặc None. Một dòng HTML liền để Streamlit không coi là code."""
    esc = _html.escape
    head = '<div class="wy-top"><span class="wy-k">Wyckoff</span>'
    foot = '<div class="wy-ft">Quy tắc mang tính chủ quan; chỉ để quan sát, không phải khuyến nghị.</div>'
    if not c:
        return (f'<div class="wy none">{head}<span class="wy-tag">Chưa có cấu trúc</span></div>'
                '<div class="wy-tx" style="margin-top:6px">Chưa thấy vùng đi ngang đủ rõ (tối thiểu 30 nến trong khung biên độ không quá 10%, chạm cả hai biên từ 2 lần): '
                'giá đang trong xu hướng hoặc biên quá rộng, nên chưa xác định được pha Wyckoff.</div>' + foot + '</div>')
    kind = c["kind"]
    cls = kind if kind in ("acc", "dist") else "unk"
    tag = esc(label(c))
    tagline = f'<span class="wy-tag">{tag}</span>'
    if kind == "unk":
        body = (f'<div class="wy-ph">Vùng đi ngang {fmt2(c["bot"])}–{fmt2(c["top"])} ({c["bars"]} nến, biên độ ≤ {MAX_AMP * 100:.0f}%)</div>'
                '<div class="wy-tx">Xu hướng trước đó không rõ nên chưa phân biệt tích lũy hay phân phối, và chưa gán được pha.</div>'
                f'<div class="wy-hint">Theo dõi hướng thoát: đóng cửa trên {fmt2(c["top"])} kèm volume lớn nghiêng về tích lũy; '
                f'dưới {fmt2(c["bot"])} nghiêng về phân phối.</div>')
        return f'<div class="wy {cls}">{head}{tagline}</div>{body}{fb_line(c)}{foot}</div>'
    ph = c["phase"]
    steps = ""
    if ph:
        idx = "ABCDE".index(ph)
        steps = '<div class="wy-steps">' + "".join(
            f'<span class="{"on" if i == idx else "done" if i < idx else ""}">{p}</span>' for i, p in enumerate("ABCDE")) + '</div>'
        pname = PHASE_NAME[kind][ph]
        body = (f'<div class="wy-ph">Đang ở Pha {ph}: {esc(pname)}</div>'
                f'<div class="wy-tx">{esc(PHASE_TEXT[kind][ph])}</div>')
        if not compact_view:
            body += f'<div class="wy-hint">{esc(PHASE_HINT[kind][ph])}</div>'
    else:
        what = "tích lũy" if kind == "acc" else "phân phối"
        sig = "SC, AR, Spring, SOS" if kind == "acc" else "BC, AR, UT, SOW"
        body = (f'<div class="wy-ph">Chưa xác định được pha</div>'
                f'<div class="wy-tx">Có vùng đi ngang nghiêng về {what} nhưng chưa thấy đủ dấu hiệu đặc trưng ({sig}), '
                'nên mới coi là vùng đi ngang, chưa vào Pha A.</div>')
    lv = (f'<div class="wy-lv"><span>Biên trên / dưới</span><b>{fmt2(c["top"])} / {fmt2(c["bot"])}</b>'
          f'<span>{esc(c["trigger"]["txt"])}</span><b>{fmt2(c["trigger"]["p"])}</b>'
          f'<span>{esc(c["inval"]["txt"])}</span><b>{fmt2(c["inval"]["p"])}</b></div>') if c.get("trigger") and c.get("inval") else ""
    ev = c.get("last_ev")
    evh = (f'<div class="wy-ev">Sự kiện gần nhất: <b>{esc(ev["label"])}</b> · {pd.Timestamp(ev["date"]):%d/%m/%Y} · {fmt2(ev["p"])}'
           f' · khớp mẫu {c["score"]}%</div>') if ev else f'<div class="wy-ev">Khớp mẫu {c["score"]}%</div>'
    if compact_view:
        lv = ""
    return f'<div class="wy {cls}">{head}{tagline}</div>{steps}{body}{lv}{evh}{fb_line(c)}{foot}</div>'


def fmt2(x) -> str:
    return _fmt(float(x))
