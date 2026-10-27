#!/usr/bin/env python3
"""Gửi Telegram cấu trúc WYCKOFF sau mỗi phiên: các mã TÍCH LŨY và CẢNH BÁO các mã PHÂN PHỐI.

Dùng đúng wyckoff.analyze() như thẻ Wyckoff / biểu đồ trong app (khung Ngày, dữ liệu qua engine.add_indicators).
  🟢 TÍCH LŨY (gồm tái tích lũy): sắp theo pha C, D, E, B, A (C/D = đã có Spring / SOS; A/B chỉ để quan sát)
  🔴 CẢNH BÁO PHÂN PHỐI (gồm tái phân phối): sắp theo pha D, E, C, B, A (D/E = đã thủng biên dưới / đang markdown)
Mã trong data/co_phieu_cua_toi.csv được đánh dấu 📌 và xếp lên đầu; watchlist 👁.

Mặc định chỉ gửi mã MỚI xuất hiện hoặc ĐỔI loại / ĐỔI pha so với lần gửi trước (nhớ trong data/wy_alert_state.json),
để tin không lặp lại mỗi ngày. Lần chạy đầu tiên (chưa có file nhớ) gửi bản tổng hợp rồi ghi nhớ toàn bộ.
Dùng --all để gửi toàn bộ danh sách hiện tại.

Biến môi trường: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID (giống telegram_alert.py).

Cách chạy:
    python telegram_wyckoff_alert.py --dry-run         # chỉ in ra, không gửi và không ghi trạng thái
    python telegram_wyckoff_alert.py                   # gửi thật (chỉ mã mới / đổi pha)
    python telegram_wyckoff_alert.py --all             # gửi toàn bộ danh sách tích lũy + phân phối hiện tại
    python telegram_wyckoff_alert.py --only HPG,FPT    # chỉ xét các mã này
    python telegram_wyckoff_alert.py --max 30          # số mã tối đa của mục phân phối (mặc định 20, 0 = tất cả)
    python telegram_wyckoff_alert.py --max-acc 5       # số mã tối đa mỗi pha tích lũy (mặc định 10)
"""
from __future__ import annotations

import argparse
import html
import json
import os
import time
from datetime import datetime

import numpy as np
import pandas as pd

import action_summary as AS
import engine as E
import wyckoff as WY
from telegram_alert import SKIP, TG_LIMIT, send
from telegram_supertrend_alert import HOLD_PATH, WATCH_PATH, _codes, now_vn, stamp

CSV_PATH = "data/eod_prices.csv"
STATE_PATH = "data/wy_alert_state.json"
MIN_VALUE_BN = 2.0            # bỏ mã có giá trị khớp trung vị 20 phiên dưới 2 tỷ đồng
MIN_BARS = WY.MIN_BARS
# Target 1-2 (Tóm tắt nhanh chưa có mục tiêu): lấy từ biên trên vùng Wyckoff (Top) và độ cao vùng H = Top − Bot. Sửa ở đây.
# Vùng mua và giá cắt lỗ KHÔNG nằm ở đây: lấy đúng từ khối "Tóm tắt nhanh · Kết luận hành động" (action_summary.plan).
PLAN = {
    "targets": (0.0, 0.5, 1.0, 1.5),   # mốc target = Top + k × H; T1 là mốc đầu tiên cao hơn giá ≥ 3%, T2 là mốc kế tiếp
    "min_gain": 0.03,
    "fallback": (0.08, 0.15),          # không có mốc nào phù hợp (giá đã chạy xa): +8% / +15%
}
# Phân loại theo "Trạng thái" của bộ lọc Chờ mua (waiting_buy.STATE_GROUP), theo thứ tự ưu tiên hiển thị
STATE_ORDER = ["Điểm mua đã xác nhận", "Sắp có điểm mua", "Theo dõi thêm", "Theo dõi phục hồi",
               "Cảnh báo không mua đuổi", "Cảnh báo rủi ro / bán", "Loại khỏi mọi danh sách"]
STATE_ICON = {"Điểm mua đã xác nhận": "✅", "Sắp có điểm mua": "🎯", "Theo dõi thêm": "👀", "Theo dõi phục hồi": "🔄",
              "Cảnh báo không mua đuổi": "⚠️", "Cảnh báo rủi ro / bán": "🔻", "Loại khỏi mọi danh sách": "⛔"}
NO_STATE = "Chưa có trạng thái Chờ mua"
BUY_PHASES = ("C", "D")        # "canh mua" = tích lũy đã có Spring (pha C) hoặc SOS (pha D); sửa ở đây nếu muốn đổi
ORDER = {"acc": ["C", "D", "E", "B", "A"], "dist": ["D", "E", "C", "B", "A"]}
PHASE_NOTE = {
    "acc": {"A": "dừng đà giảm", "B": "xây nền, chỉ quan sát", "C": "Spring, thử cung cuối",
            "D": "SOS, cầu thắng thế", "E": "đã rời vùng, markup"},
    "dist": {"A": "chặn đà tăng", "B": "xây nền, chỉ quan sát", "C": "Upthrust, thử cầu cuối",
             "D": "SOW, thủng biên dưới", "E": "đã rời vùng, markdown"},
}


# ------------------------------------------------------------------ dữ liệu
def _last(d: pd.DataFrame, col: str) -> float:
    return float(d[col].iat[-1]) if col in d.columns and pd.notna(d[col].iat[-1]) else float("nan")


def scan(path: str, only: set[str] | None, min_value: float) -> tuple[pd.DataFrame, pd.Timestamp]:
    """Trả (bảng mã có cấu trúc tích lũy / phân phối, ngày dữ liệu mới nhất)."""
    raw = E.clean_raw(pd.read_csv(path, dtype={"Mã": str}))
    raw = raw[~raw["Mã"].isin(SKIP)]
    latest = pd.Timestamp(raw["Ngày"].max())
    rows = []
    for code, g in raw.groupby("Mã"):
        if only and code.upper() not in only:
            continue
        g = g.sort_values("Ngày")
        if len(g) < MIN_BARS or pd.Timestamp(g["Ngày"].iat[-1]) != latest:      # bỏ mã dữ liệu cũ / tạm ngừng giao dịch
            continue
        try:
            d = E.mask_chg_gaps(E.add_indicators(E.resample_ohlcv(g[["Mã", "Ngày"] + E.NUMERIC_COLS], "D"))).reset_index(drop=True)
            w = WY.analyze(d)
        except Exception as e:  # noqa: BLE001
            print(f"  bỏ qua {code}: {e}")
            continue
        if not w or w["kind"] not in ("acc", "dist") or not w["phase"]:
            continue
        c = g["Giá đóng cửa"].astype(float).to_numpy()
        v = g["Khối lượng khớp lệnh"].astype(float).to_numpy()
        liq = float(np.median(c[-20:] * v[-20:]) * 1000 / 1e9)
        if liq < min_value:
            continue
        chg = d["Chg_%"].iat[-1] if "Chg_%" in d.columns else np.nan
        ev = max(w["events"], key=lambda x: x["i"]) if w["events"] else None
        rows.append({
            "Mã": code, "Loại": w["kind"], "Tái": bool(w["re"]), "Pha": w["phase"], "Nhãn": WY.label(w),
            "Giá": float(c[-1]), "Chg": float(chg) if pd.notna(chg) else np.nan,
            "Bot": float(w["tr"]["bot"]), "Top": float(w["tr"]["top"]), "Nến": int(w["tr"]["L"]), "Khớp": int(w["score"]),
            "SK": f"{ev['label']} {pd.Timestamp(ev['date']):%d/%m}" if ev else "",
            "Xác nhận": (w["trigger"]["txt"], float(w["trigger"]["p"])) if w.get("trigger") else None,
            "Vô hiệu": (w["inval"]["txt"], float(w["inval"]["p"])) if w.get("inval") else None,
            "GTGD": liq,
            "wy": WY.compact(w),
            "ma20": _last(d, "MA20"), "ma50": _last(d, "MA50"), "ma200": _last(d, "MA200"),
            "sup": _last(d, "Support_20"), "res": _last(d, "Resistance_20"),
        })
    return pd.DataFrame(rows), latest


def enrich(res: pd.DataFrame, path: str) -> pd.DataFrame:
    """Gắn "Trạng thái" Chờ mua và ngữ cảnh y hệt app (phân kỳ RSI, hỗ trợ / kháng cự khung Ngày, dự báo, vùng mua) vào từng mã,
    để kết luận hành động / giá mua / cắt lỗ trên Telegram khớp thẻ "Tóm tắt nhanh" trong bộ lọc. Lỗi thì giữ bảng cũ (không có trạng thái)."""
    res = res.copy()
    res["Trạng thái"], res["Nhóm TT"] = "", ""
    res["ctx"] = pd.Series([None] * len(res), index=res.index, dtype=object)
    try:
        import mtf_levels as ML
        import rsi_divergence as DV
        import telegram_buy_alert as TB
        import waiting_buy as WB
        raw, frames = TB.build_frames(path)
        mkt, _ = E.market_series(raw)
        scr = E.build_screener(frames, mkt)
        scr["Nhóm"] = ""
        wb = WB.build_waiting_buy(frames, scr)
        cols = [c for c in ("Trạng thái", "Lý do", "Vùng mua từ", "Vùng mua đến") if c in wb.columns]
        wbmap = wb.drop_duplicates("Mã", keep="first").set_index("Mã")[cols].to_dict("index")
    except Exception as e:  # noqa: BLE001
        print(f"  không dựng được trạng thái Chờ mua: {e}")
        return res
    states, groups, ctxs = [], [], []
    for _, r in res.iterrows():
        code = r["Mã"]
        try:
            pick = lambda tf: frames[tf][frames[tf]["Mã"] == code]       # noqa: E731
            a = E.analyze_frame(pick("D"), "D")
            d = ML.analyze_dwm_timeframe(pick("D"), pick("W"), pick("M"))["D"]
            div = DV.analyze(frames, code, ("M", "W", "D"))
        except Exception as e:  # noqa: BLE001
            print(f"  {code}: thiếu ngữ cảnh app ({e})")
            a, d, div = {}, {}, []
        w = wbmap.get(code, {})
        state = w.get("Trạng thái") if isinstance(w.get("Trạng thái"), str) else ""
        reason = w.get("Lý do") if isinstance(w.get("Lý do"), str) else ""
        grp = WB.STATE_GROUP.get(state, "") if state else ""
        in_buy = bool(grp) and grp in WB.BUY_GROUPS
        ctxs.append(dict(
            code=code, close=r["Giá"], ma20=r["ma20"], ma50=r["ma50"], ma200=r["ma200"],
            label=WB.status_tag(state, reason)[0] if state else "", state=state, reason=reason,
            lean=(a.get("dir", 0) if a.get("enough") else 0), div=div, wy=r["wy"],
            sup=d.get("sup") if d.get("ok") else None, res=d.get("res") if d.get("ok") else None,
            zone=(w.get("Vùng mua từ"), w.get("Vùng mua đến")) if in_buy else None))
        states.append(state)
        groups.append(grp or NO_STATE)
    res["Trạng thái"], res["Nhóm TT"] = states, groups
    res["ctx"] = pd.Series(ctxs, index=res.index, dtype=object)
    return res


# ------------------------------------------------------------------ trạng thái đã gửi
def load_state(path: str = STATE_PATH) -> dict | None:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return None


def save_state(snapshot: dict[str, str], latest: pd.Timestamp, path: str = STATE_PATH) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"latest": f"{latest:%Y-%m-%d}", "state": snapshot}, f, ensure_ascii=False, indent=1, sort_keys=True)


def sig_of(r) -> str:
    return f"{r['Loại']}|{r['Pha']}"


# ------------------------------------------------------------------ định dạng
def _block(r, held: set[str], watch: set[str]) -> str:
    mark = "📌 " if r["Mã"] in held else ("👁 " if r["Mã"] in watch else "")
    chg = "" if pd.isna(r["Chg"]) else f" ({r['Chg']:+.1f}%)"
    note = PHASE_NOTE[r["Loại"]][r["Pha"]]
    lines = [f"{mark}{r['Mã']}  Giá {r['Giá']:,.2f}{chg}",
             f"  {r['Nhãn']} · {note}",
             f"  Vùng {r['Bot']:,.2f} – {r['Top']:,.2f} · {r['Nến']} nến · khớp mẫu {r['Khớp']}%"]
    if r["SK"]:
        lines.append(f"  Sự kiện gần nhất: {r['SK']}")
    if r["Xác nhận"]:
        lines.append(f"  {r['Xác nhận'][0]}")
    if r["Vô hiệu"]:
        lines.append(f"  {r['Vô hiệu'][0]}")
    lines.append(f"  GTGD {r['GTGD']:,.0f} tỷ")
    return html.escape("\n".join(lines))


def _targets(r) -> tuple[float, float] | None:
    """(Target 1, Target 2) từ vùng Wyckoff: các mốc Top + k×H cao hơn giá hiện tại ≥ 3%; không có thì +8% / +15%."""
    close, top, bot = float(r["Giá"]), float(r["Top"]), float(r["Bot"])
    if not (close > 0 and top > bot > 0):
        return None
    H = top - bot
    ups = [x for x in (top + k * H for k in PLAN["targets"]) if x > close * (1 + PLAN["min_gain"])]
    ups += [close * (1 + g) for g in PLAN["fallback"]]
    return ups[0], ups[1]


def _stock_msg(r, held: set[str], watch: set[str]) -> str:
    """Tin riêng 1 mã: trạng thái, Wyckoff, Ngắn/Trung hạn, hướng xử lý của người cầm tiền mặt, vùng mua thăm dò, cắt lỗ (cùng
    "Tóm tắt nhanh · Kết luận hành động" trong bộ lọc), Target 1-2."""
    mark = "📌 " if r["Mã"] in held else ("👁 " if r["Mã"] in watch else "")
    chg = "" if pd.isna(r["Chg"]) else f" ({r['Chg']:+.1f}%)"
    esc = html.escape
    icon = "🟢" if r["Loại"] == "acc" else "🔴"
    head = f"{icon} {mark}<b>{esc(r['Mã'])}</b> · Giá {r['Giá']:,.2f}{chg} · GTGD {r['GTGD']:,.0f} tỷ"
    ctx = r.get("ctx") if isinstance(r.get("ctx"), dict) else {
        "code": r["Mã"], "close": r["Giá"], "ma20": r["ma20"], "ma50": r["ma50"], "ma200": r["ma200"], "wy": r["wy"],
        "sup": r["sup"], "res": r["res"], "label": "", "state": "", "reason": "", "lean": 0, "div": [], "zone": None}
    grp, state = str(r.get("Nhóm TT") or ""), str(r.get("Trạng thái") or "")
    st_line = f"<b>Trạng thái:</b> {esc(grp)}" + (f" · {esc(state)}" if state and state != grp else "") if grp else ""
    wy_line = f"<b>Wyckoff</b> {esc(r['Nhãn'])} · {esc(PHASE_NOTE[r['Loại']][r['Pha']])}"
    try:
        pt, pl = AS.parts(ctx), AS.plan(ctx)
    except Exception as e:  # noqa: BLE001
        print(f"  không dựng được tóm tắt {r['Mã']}: {e}")
        pt, pl = {}, {}
    block1 = wy_line + ("\n" + pt["picture"] if pt.get("picture") else "")
    action = ""
    if pt.get("cash"):
        _, why, zone = pt["cash"]
        action = (why[:1].upper() + why[1:]) + (f"\n   ↳ {zone}" if zone else "")
    px = lambda v: f"{float(v):,.2f}"        # noqa: E731
    close = float(r["Giá"])
    buy, wait = pl.get("buy"), pl.get("wait")
    if buy and buy.get("zone"):
        bl = f"{px(buy['zone'][0])} – {px(buy['zone'][1])}"
    elif buy and buy.get("levels"):
        bl = "quanh " + " hoặc ".join(px(x) for x in buy["levels"])
    elif wait:
        bl = f"chưa mua, chờ giá lấy lại {wait[0]} {px(wait[1])}"
    else:
        bl = "chưa có vùng rõ, chờ giá về hỗ trợ gần nhất"
    lines = [f"Vùng mua thăm dò: {bl}"]
    stop = pl.get("stop")
    lines.append(f"Cắt lỗ nếu sai: {px(stop)} ({(float(stop) / close - 1) * 100:+.1f}%)" if stop else "Cắt lỗ nếu sai: chưa xác định")
    tg = _targets(r)
    if tg:
        lines += [f"Target 1: {px(tg[0])} ({(tg[0] / close - 1) * 100:+.1f}%)", f"Target 2: {px(tg[1])} ({(tg[1] / close - 1) * 100:+.1f}%)"]
    foot = "<i>Quy tắc mang tính chủ quan, chỉ để tham khảo, không phải khuyến nghị đầu tư.</i>"
    mid = "\n".join(x for x in (action, "\n".join(lines)) if x)
    return "\n\n".join(x for x in (head, st_line, block1, mid, foot) if x)


def build_acc_messages(show: pd.DataFrame, held: set[str], watch: set[str], cap: int, by: str = "state") -> list[str]:
    """Tích lũy: tách theo nhóm (trạng thái Chờ mua hoặc pha); mỗi nhóm có 1 tin mở đầu rồi mỗi mã 1 tin riêng."""
    msgs: list[str] = []
    for title, icon, hint, g in _acc_groups(show, held, watch, by):
        shown = g.head(cap) if cap else g
        more = f" · hiển thị {len(shown)}/{len(g)} mã" if len(g) > len(shown) else ""
        msgs.append(f"{icon} <b>{html.escape(title)}</b> ({len(g)} mã{more})" + (f"\n<i>{html.escape(hint)}</i>" if hint else ""))
        msgs.extend(_stock_msg(r, held, watch) for _, r in shown.iterrows())
    return msgs


def _sorted(d: pd.DataFrame, kind: str, held: set[str], watch: set[str]) -> pd.DataFrame:
    d = d[d["Loại"] == kind].copy()
    d["_p"] = d["Mã"].map(lambda c: 0 if c in held else 1 if c in watch else 2)
    d["_o"] = d["Pha"].map({p: i for i, p in enumerate(ORDER[kind])})
    return d.sort_values(["_p", "_o", "Khớp"], ascending=[True, True, False])


def _section_chunks(title: str, total: int, items: list[str], more: str, limit: int = TG_LIMIT) -> list[str]:
    """Chia 1 mục (tích lũy / phân phối) thành nhiều khối <pre>, mỗi khối không vượt quá giới hạn Telegram.
    Mỗi khối tự đóng/mở thẻ <pre> riêng nên tin nhắn nào cũng hợp lệ."""
    def render(body: list[str], first: bool) -> str:
        t = f"{title} ({total} mã)" if first else f"{title} (tiếp)"
        return f"<b>{t}</b>\n<pre>{chr(10).join(body)}</pre>"

    budget = limit - len(more) - 40            # chừa chỗ cho dòng "… và N mã khác" và khoảng trắng nối tin
    chunks: list[str] = []
    cur: list[str] = []
    for it in items:
        # đo bằng bản đã escape HTML (dài hơn thực tế) nên luôn an toàn
        if cur and len(render(cur + [it], not chunks)) > budget:
            chunks.append(render(cur, not chunks))
            cur = [it]
        else:
            cur.append(it)
    if cur:
        chunks.append(render(cur, not chunks))
    if chunks and more:
        chunks[-1] += more
    return chunks


def _sector_map() -> dict[str, str]:
    """Mã -> ngành theo watchlist.GROUPS (mã thuộc nhiều nhóm thì lấy nhóm đứng trước); mã chưa có nhóm sẽ vào "Khác"."""
    try:
        import watchlist as WL
        out: dict[str, str] = {}
        for sec, codes in WL.GROUPS.items():
            for c in codes:
                out.setdefault(str(c).strip().upper(), sec)
        return out
    except Exception as e:  # noqa: BLE001
        print(f"  không đọc được nhóm ngành: {e}")
        return {}


def _acc_groups(show: pd.DataFrame, held: set[str], watch: set[str], by: str) -> list[tuple[str, str, str, pd.DataFrame]]:
    """Tích lũy chia thành các nhóm theo thứ tự hiển thị: [(tiêu đề, icon, gợi ý, bảng mã)]. by="state": theo trạng thái Chờ mua; by="phase": theo pha."""
    acc = _sorted(show, "acc", held, watch)
    out: list[tuple[int, str, str, str, pd.DataFrame]] = []
    if by == "phase":
        for i, ph in enumerate(ORDER["acc"]):
            g = acc[acc["Pha"] == ph]
            if not g.empty:
                hint = WY.PHASE_HINT["acc"][ph] if hasattr(WY, "PHASE_HINT") else ""
                out.append((i, f"TÍCH LŨY · PHA {ph} — {PHASE_NOTE['acc'][ph]}", "🟢", hint, g))
    else:
        col = acc["Nhóm TT"] if "Nhóm TT" in acc.columns else pd.Series(NO_STATE, index=acc.index)
        for name in dict.fromkeys(col):
            g = acc[col == name]
            idx = STATE_ORDER.index(name) if name in STATE_ORDER else len(STATE_ORDER)
            out.append((idx, name, STATE_ICON.get(name, "⚪"), "", g))
    out.sort(key=lambda t: t[0])
    return [(t, ic, h, g) for _, t, ic, h, g in out]


def _by_sector(codes: list[str], smap: dict[str, str], tags: dict[str, str] | None = None) -> str:
    """"Ngân hàng: HDB (C), VPB (D)\nChứng khoán: HCM, TCX" (ngành nhiều mã đứng trước, "Khác" đứng cuối)."""
    groups: dict[str, list[str]] = {}
    for c in codes:
        groups.setdefault(smap.get(c.upper(), "Khác"), []).append(c)
    order = sorted(groups, key=lambda k: (k == "Khác", -len(groups[k]), k))
    lab = lambda c: f"{c} ({tags[c]})" if tags and tags.get(c) else c      # noqa: E731
    return "\n".join(f"{html.escape(k)}: {html.escape(', '.join(lab(c) for c in groups[k]))}" for k in order)


def build_summary(show: pd.DataFrame, held: set[str], watch: set[str], by: str = "state") -> list[str]:
    """Tin tổng hợp gửi trước các tin riêng lẻ: mỗi nhóm (trạng thái hoặc pha) gom theo ngành, mã kèm pha Wyckoff trong ngoặc."""
    smap = _sector_map()
    blocks: list[str] = []
    for title, icon, _, g in _acc_groups(show, held, watch, by):
        tags = {r["Mã"]: r["Pha"] for _, r in g.iterrows()} if by == "state" else None
        blocks.append(f"<b>{icon} {html.escape(title)}</b> · {len(g)} mã\n" + _by_sector(list(g["Mã"]), smap, tags))
    dist = _sorted(show, "dist", held, watch)
    if not dist.empty:
        blocks.append(f"<b>🔴 Cảnh báo phân phối</b> · {len(dist)} mã\n" + _by_sector(list(dist["Mã"]), smap))
    return blocks


def _pack(blocks: list[str]) -> list[str]:
    msgs, cur = [], ""
    for b in blocks:
        if cur and len(cur) + len(b) + 2 > TG_LIMIT:
            msgs.append(cur)
            cur = ""
        cur = f"{cur}\n\n{b}" if cur else b
    if cur:
        msgs.append(cur)
    return msgs


def build_messages(show: pd.DataFrame, totals: dict, latest: pd.Timestamp, held: set[str], watch: set[str], cap: int,
                   mode_txt: str, sent_at: datetime | None = None, cap_acc: int = 10, by: str = "state") -> list[str]:
    head = (f"🏗 <b>Wyckoff · cấu trúc khung Ngày cuối phiên {latest:%d/%m/%Y}</b>\n"
            f"Đang tích lũy: {totals['acc']} mã · Đang phân phối: {totals['dist']} mã\n"
            f"{mode_txt}\n"
            f"🕖 Gửi lúc {stamp(sent_at)}")
    foot = ("<i>Wyckoff do máy dò theo giá và volume nên mang tính chủ quan. Pha A/B chỉ để quan sát; "
            "chỉ phục vụ nghiên cứu, không phải khuyến nghị đầu tư.</i>")
    dist_blocks: list[str] = []
    d = _sorted(show, "dist", held, watch)
    if not d.empty:
        shown = d.head(cap) if cap else d
        items = [_block(r, held, watch) for _, r in shown.iterrows()]
        more = f"\n… và {len(d) - len(shown)} mã khác" if len(d) > len(shown) else ""
        dist_blocks = _section_chunks("🔴 CẢNH BÁO PHÂN PHỐI", len(d), items, more)
    return _pack([head] + build_summary(show, held, watch, by)) + build_acc_messages(show, held, watch, cap_acc, by) + _pack(dist_blocks + [foot])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="chỉ in ra, không gửi và không ghi trạng thái")
    ap.add_argument("--all", action="store_true", help="gửi toàn bộ danh sách hiện tại, không chỉ mã mới / đổi pha")
    ap.add_argument("--only", default="", help="chỉ xét các mã này, ngăn cách bằng dấu phẩy")
    ap.add_argument("--max", type=int, default=20, help="số mã tối đa của mục phân phối (mặc định 20, 0 = tất cả)")
    ap.add_argument("--max-acc", type=int, default=10, help="số mã tối đa MỖI NHÓM của mục tích lũy, mỗi mã 1 tin (mặc định 10, 0 = tất cả)")
    ap.add_argument("--by", choices=("state", "phase"), default="state", help="phân loại tích lũy theo trạng thái Chờ mua (mặc định) hoặc theo pha Wyckoff")
    ap.add_argument("--min-value", type=float, default=MIN_VALUE_BN, help="giá trị khớp trung vị 20 phiên tối thiểu, tỷ đồng (mặc định 2)")
    ap.add_argument("--csv", default=CSV_PATH)
    args = ap.parse_args()

    only = {c.strip().upper() for c in args.only.split(",") if c.strip()} or None
    res, latest = scan(args.csv, only, args.min_value)
    if res.empty:
        print(f"Phiên {latest:%d/%m/%Y}: không có mã nào ở cấu trúc tích lũy / phân phối.")
        return
    held, watch = _codes(HOLD_PATH), _codes(WATCH_PATH)
    totals = {"acc": int((res["Loại"] == "acc").sum()), "dist": int((res["Loại"] == "dist").sum())}
    state = load_state()
    old = (state or {}).get("state", {})
    first_run = state is None
    if args.all or first_run:
        show = res
        mode_txt = ("Lần đầu: bản tổng hợp, từ phiên sau chỉ báo mã mới / đổi pha." if first_run and not args.all
                    else "Toàn bộ danh sách hiện tại.")
    else:
        show = res[res.apply(lambda r: old.get(r["Mã"]) != sig_of(r), axis=1)]
        mode_txt = "Chỉ gồm mã mới xuất hiện hoặc đổi loại / đổi pha so với lần gửi trước."
        if show.empty:
            print(f"Phiên {latest:%d/%m/%Y}: không có mã Wyckoff mới hoặc đổi pha để gửi.")
            if not args.dry_run:
                save_state({r["Mã"]: sig_of(r) for _, r in res.iterrows()}, latest)
            return
    show = enrich(show, args.csv) if int((show['Loại'] == 'acc').sum()) or int((show['Loại'] == 'dist').sum()) else show
    msgs = build_messages(show, totals, latest, held, watch, args.max, mode_txt, cap_acc=args.max_acc, by=args.by)
    if args.dry_run:
        for m in msgs:
            print(m, "\n" + "=" * 40)
        return
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN", ""), os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat:
        raise SystemExit("Thiếu TELEGRAM_BOT_TOKEN hoặc TELEGRAM_CHAT_ID (đặt trong GitHub Secrets).")
    pause = 3.2 if str(chat).startswith("-") else 1.1      # nhóm / kênh: tối đa ~20 tin mỗi phút
    for i, m in enumerate(msgs):
        send(token, chat, m)
        if i < len(msgs) - 1:
            time.sleep(pause)
    save_state({r["Mã"]: sig_of(r) for _, r in res.iterrows()}, latest)
    print(f"Đã gửi {len(msgs)} tin nhắn ({int((show['Loại'] == 'acc').sum())} tích lũy, {int((show['Loại'] == 'dist').sum())} phân phối).")


if __name__ == "__main__":
    main()
