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
OFFSETS = (0, 3, 6, 10, 15, 20, 30, 45)


def _fmt(x: float) -> str:
    return f"{x:,.2f}"


def _find_range(h, l, c, atr, end):
    a = atr[end]
    if not np.isfinite(a) or a <= 0 or end < 40:
        return None
    best = None
    for L in range(30, min(260, end + 1) + 1, 5):
        s = end - L + 1
        sh, sl = h[s:end + 1], l[s:end + 1]
        hi, lo = float(np.max(sh)), float(np.min(sl))
        if not (np.isfinite(hi) and np.isfinite(lo)):
            continue
        W = hi - lo
        if W > 9 * a:          # biên quá rộng so với biến động: đã là xu hướng
            break
        if W < 2.5 * a:        # biên quá hẹp: chưa đủ ý nghĩa
            continue
        mid = (hi + lo) / 2
        ti = np.flatnonzero(sh >= hi - 0.2 * W)
        bi = np.flatnonzero(sl <= lo + 0.2 * W)
        top_t = 1 + int((np.diff(ti) >= 5).sum()) if len(ti) else 0
        bot_t = 1 + int((np.diff(bi) >= 5).sum()) if len(bi) else 0
        side = np.where(c[s:end + 1] > mid, 1, -1)
        cross = int((np.diff(side) != 0).sum())
        if top_t >= 2 and bot_t >= 2 and cross >= 4:
            best = {"s": s, "e": end, "L": L, "top": hi, "bot": lo, "mid": mid, "W": W}
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

    base = {"kind": kind, "re": re_, "post": post, "prior": prior, "events": [], "phase": None,
            "phase_text": None, "lean": "wait", "score": 0, "notes": [], "kind_name": kind_name,
            "bars": n}

    if kind == "unk":
        base.update(tr=tr_dict(tr), pos=(lc - bot) / W,
                    title=f"Vùng {kind_name} {_fmt(bot)}–{_fmt(top)}",
                    summary=(f"Có vùng đi ngang {_fmt(bot)}–{_fmt(top)} kéo dài {tr['L']} nến, nhưng xu hướng trước đó không rõ "
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
        top, bot = float(np.max(h[s:e + 1])), float(np.min(l[s:e + 1]))
        W, mid = top - bot, (top + bot) / 2
        tr = {"s": s, "e": e, "L": e - s + 1, "top": top, "bot": bot, "mid": mid, "W": W}
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

    notes = []
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
    summary = (f"{title}, kéo dài {tr['L']} nến, xu hướng trước đó {prior_txt}. "
               + (PH[phase] if phase else f"Chưa thấy đủ dấu hiệu đặc trưng của Wyckoff ({'BC, AR, UT, SOW' if dist else 'SC, AR, Spring, SOS'}), nên coi đây mới là vùng đi ngang.")
               + f" {where}.")
    base.update(tr=tr_dict(tr), pos=float(pos), title=title, events=events, phase=phase,
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
