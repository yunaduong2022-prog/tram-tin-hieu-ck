#!/usr/bin/env python3
"""Gửi Telegram cấu trúc WYCKOFF sau mỗi phiên: các mã TÍCH LŨY và CẢNH BÁO các mã PHÂN PHỐI.

Dùng đúng wyckoff.analyze() như thẻ Wyckoff / biểu đồ trong app (khung Ngày, dữ liệu qua engine.add_indicators).
  🟢 TÍCH LŨY (gồm tái tích lũy): sắp theo pha C, D, E, B, A (C/D = đã có Spring / SOS; A/B chỉ để quan sát)
  🔴 CẢNH BÁO PHÂN PHỐI (gồm tái phân phối): sắp theo pha D, E, C, B, A (D/E = đã thủng biên dưới / đang markdown)
Mỗi mã có thêm dòng "Dự báo nghiêng Tăng / Giảm" (cùng phép tính với biểu đồ khung Ngày). Mục phân phối ghi gọn (kèm Ngắn hạn / Trung hạn);
nếu nghiêng Tăng thì thêm Vùng chờ mua, Cắt lỗ, Target.
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
import re
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
# Quy tắc kế hoạch giá (tính từ vùng Wyckoff: Bot = biên dưới, Top = biên trên, H = Top − Bot). Sửa ở đây.
PLAN = {
    "zone_low_frac": 0.35,       # pha A/B/C: vùng thăm dò = Bot → Bot + 35% H (không cao hơn giá hiện tại)
    "retest_frac": 0.25,         # pha D/E: vùng thăm dò = Top − 25% H → Top × 1.01 (nhịp test lại biên trên)
    "stop_buffer": 0.01,         # cắt lỗ nằm dưới Bot 1% (tránh quét râu)
    "retest_stop": 0.03,         # pha D/E: cắt lỗ dưới biên dưới vùng thăm dò 3%, nhưng không thấp hơn Bot
    "targets": (0.0, 0.5, 1.0, 1.5),   # mốc target = Top + k × H; T1 là mốc đầu tiên cao hơn giá ≥ 3%, T2 là mốc kế tiếp
    "min_gain": 0.03,
    "fallback": (0.08, 0.15),    # không có mốc nào phù hợp (giá đã chạy xa): +8% / +15%
}
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


def _recent_low(d: pd.DataFrame, close: float):
    """Đáy gần nhất (swing low đã xác nhận, k = 3 nến) thấp hơn giá hiện tại: (giá, ngày). Không có thì lấy đáy 20 phiên (Support_20) nếu thấp hơn giá."""
    try:
        _, _, stack = E.swing_state(d["Giá cao nhất"].to_numpy(float), d["Giá thấp nhất"].to_numpy(float), 3)
        for j, t, p in reversed(stack):
            if t == "L" and p < close:
                return float(p), pd.Timestamp(d["Ngày"].iat[j])
    except Exception:  # noqa: BLE001
        pass
    sup = _last(d, "Support_20")
    return (sup, None) if sup == sup and 0 < sup < close else None


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
        try:                                          # dự báo nghiêng tăng / giảm: cùng phép tính với biểu đồ khung Ngày trong app
            fa = E.analyze_frame(d, "D")
            lean, fc = (int(fa["dir"]), fa["fc"]) if fa["enough"] else (0, None)
        except Exception as e:  # noqa: BLE001
            print(f"  không tính được dự báo {code}: {e}")
            lean, fc = 0, None
        c = g["Giá đóng cửa"].astype(float).to_numpy()
        v = g["Khối lượng khớp lệnh"].astype(float).to_numpy()
        liq = float(np.median(c[-20:] * v[-20:]) * 1000 / 1e9)
        if liq < min_value:
            continue
        low_pv = _recent_low(d, float(c[-1]))
        chg = d["Chg_%"].iat[-1] if "Chg_%" in d.columns else np.nan
        ev = max(w["events"], key=lambda x: x["i"]) if w["events"] else None
        rows.append({
            "Mã": code, "Loại": w["kind"], "Tái": bool(w["re"]), "Pha": w["phase"], "Nhãn": WY.label(w),
            "Giá": float(c[-1]), "Chg": float(chg) if pd.notna(chg) else np.nan,
            "Bot": float(w["tr"]["bot"]), "Top": float(w["tr"]["top"]), "Nến": int(w["tr"]["L"]), "Khớp": int(w["score"]),
            "SK": f"{ev['label']} {pd.Timestamp(ev['date']):%d/%m}" if ev else "",
            "Xác nhận": (w["trigger"]["txt"], float(w["trigger"]["p"])) if w.get("trigger") else None,
            "Vô hiệu": (w["inval"]["txt"], float(w["inval"]["p"])) if w.get("inval") else None,
            "GTGD": liq, "Lean": lean, "FC": fc,
            "tenkan": _last(d, "Tenkan"), "kijun": _last(d, "Kijun"), "spanA": _last(d, "SpanA"), "spanB": _last(d, "SpanB"),
            "atr": _last(d, "ATR"), "low_pv": low_pv,
            "wy": WY.compact(w),
            "ma20": _last(d, "MA20"), "ma50": _last(d, "MA50"), "ma200": _last(d, "MA200"),
            "sup": _last(d, "Support_20"), "res": _last(d, "Resistance_20"),
        })
    return pd.DataFrame(rows), latest


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
def _lean_line(r) -> str:
    """Dòng dự báo của biểu đồ khung Ngày: nghiêng Tăng / Giảm (|độ nghiêng| >= 1.0); chưa nghiêng rõ thì ghi trung tính."""
    lean = int(r["Lean"]) if pd.notna(r["Lean"]) else 0
    return "Dự báo nghiêng Tăng" if lean > 0 else "Dự báo nghiêng Giảm" if lean < 0 else "Dự báo chưa nghiêng rõ"


SUP_STOP_ATR = 0.5            # dự báo chưa rõ: cắt lỗ nằm dưới hỗ trợ này 0,5 ATR


def _support_zone(r):
    """Dự báo chưa nghiêng rõ: (thấp, cao, nguồn) của vùng hỗ trợ để đặt mốc tham gia.
    - Giá nằm trên cả Tenkan và Kijun: hai đường này là hỗ trợ.
    - Giá dưới mây Ichimoku: đáy gần nhất là hỗ trợ.
    Không thuộc hai trường hợp thì trả None."""
    c = float(r["Giá"])
    tk, kj, a, b = r["tenkan"], r["kijun"], r["spanA"], r["spanB"]
    ok = lambda x: x == x and x > 0  # noqa: E731
    if ok(tk) and ok(kj) and c > max(tk, kj):
        return min(tk, kj), max(tk, kj), "Tenkan–Kijun"
    if ok(a) and ok(b) and c < min(a, b) and r["low_pv"]:
        p, dt = r["low_pv"]
        atr = r["atr"] if r["atr"] == r["atr"] and r["atr"] > 0 else c * 0.02
        return p, p + 0.25 * atr, f"đáy {dt:%d/%m}" if dt is not None else "đáy 20 phiên"
    return None


def _lean_plan(r) -> list[str]:
    """Vùng chờ mua / cắt lỗ / target.
    - Nghiêng Tăng: lấy từ dự báo của biểu đồ (vùng vào = giá ± 0,25 ATR, cắt lỗ 1,5 ATR, T1 = 2R, T2 = 3R).
    - Chưa nghiêng rõ: vùng chờ mua = hỗ trợ (Tenkan–Kijun hoặc đáy gần nhất), cắt lỗ dưới hỗ trợ 0,5 ATR, T1 / T2 = 2R / 3R tính từ giữa vùng (% cắt lỗ / target cũng tính từ giữa vùng).
    - Nghiêng Giảm: không đưa kế hoạch mua."""
    lean, c = int(r["Lean"] or 0), float(r["Giá"])
    ref = c                                   # mốc tính % của cắt lỗ / target: giá hiện tại, hoặc giữa vùng chờ mua nếu vùng nằm thấp hơn giá
    src = ""
    if lean > 0 and isinstance(r["FC"], dict):
        fc = r["FC"]
        lo, hi, sl, t1, t2 = fc["lo"], fc["hi"], fc["sl"], fc["t1"], fc["t2"]
    elif lean == 0 and (z := _support_zone(r)):
        lo, hi, src = z
        hi = min(max(hi, lo * 1.005), c)
        atr = r["atr"] if r["atr"] == r["atr"] and r["atr"] > 0 else c * 0.02
        sl = lo - SUP_STOP_ATR * atr
        mid = (lo + hi) / 2
        risk = mid - sl
        t1, t2 = mid + 2 * risk, mid + 3 * risk
        ref = mid
        src = f" ({src}" + (f" · cách giá {(mid / c - 1) * 100:+.1f}%" if mid < c * 0.995 else "") + ")"
    else:
        return []
    pct = lambda x: (float(x) / ref - 1) * 100  # noqa: E731
    return [f"  🎯 VÙNG CHỜ MUA {lo:,.2f} – {hi:,.2f}{src}",     # khối <pre> không in đậm được nên nhấn bằng icon + chữ hoa
            f"  Cắt lỗ {sl:,.2f} ({pct(sl):+.1f}%)",
            f"  Target 1 {t1:,.2f} ({pct(t1):+.1f}%) · Target 2 {t2:,.2f} ({pct(t2):+.1f}%)"]


def _picture_plain(r) -> list[str]:
    """Hai dòng Ngắn hạn / Trung hạn (cùng quy tắc với tin riêng từng mã), bỏ thẻ HTML để đưa vào khối <pre>."""
    ctx = {"code": r["Mã"], "close": r["Giá"], "ma20": r["ma20"], "ma50": r["ma50"], "ma200": r["ma200"], "wy": r["wy"],
           "sup": r["sup"], "res": r["res"], "label": "", "state": "", "reason": "", "lean": int(r["Lean"] or 0), "div": [], "zone": None}
    try:
        pic = AS.parts(ctx).get("picture", "")
    except Exception as e:  # noqa: BLE001
        print(f"  không dựng được ngắn/trung hạn {r['Mã']}: {e}")
        return []
    return ["  " + re.sub(r"</?b>", "", ln).strip() for ln in pic.split("\n") if ln.strip()]


def _block(r, held: set[str], watch: set[str]) -> str:
    """Mục cảnh báo phân phối, mỗi mã 3 dòng (nghiêng Tăng thì thêm vùng chờ mua / cắt lỗ / target)."""
    mark = "📌 " if r["Mã"] in held else ("👁 " if r["Mã"] in watch else "")
    chg = "" if pd.isna(r["Chg"]) else f" ({r['Chg']:+.1f}%)"
    note = PHASE_NOTE[r["Loại"]][r["Pha"]]
    lines = [f"{mark}{r['Mã']}  Giá {r['Giá']:,.2f}{chg}",
             f"  {r['Nhãn']} · {note}",
             *_picture_plain(r),
             _lean_line(r)] + _lean_plan(r)
    return html.escape("\n".join(lines))


def _plan_levels(r) -> dict:
    """Vùng mua thăm dò, giá cắt lỗ, Target 1, Target 2 (theo PLAN). Thiếu dữ liệu thì trả {}."""
    close, top, bot = float(r["Giá"]), float(r["Top"]), float(r["Bot"])
    if not (close > 0 and top > bot > 0):
        return {}
    H = top - bot
    if r["Pha"] in ("D", "E"):
        lo, hi = top - PLAN["retest_frac"] * H, top * 1.01
    else:
        lo, hi = bot, bot + PLAN["zone_low_frac"] * H
    hi = min(hi, close)                          # không canh mua cao hơn giá hiện tại
    lo = min(lo, hi * 0.98)                      # vùng rộng tối thiểu ~2%
    if r["Pha"] in ("D", "E"):
        stop = max(bot, lo * (1 - PLAN["retest_stop"]))
    else:
        stop = bot * (1 - PLAN["stop_buffer"])
    levels = [top + k * H for k in PLAN["targets"]]
    ups = [x for x in levels if x > close * (1 + PLAN["min_gain"])]
    ups += [close * (1 + g) for g in PLAN["fallback"]]
    t1, t2 = ups[0], ups[1]
    return {"lo": lo, "hi": hi, "stop": stop, "t1": t1, "t2": t2,
            "stop_pct": (stop / close - 1) * 100, "t1_pct": (t1 / close - 1) * 100, "t2_pct": (t2 / close - 1) * 100}


def _stock_msg(r, held: set[str], watch: set[str]) -> str:
    """Một tin riêng cho 1 mã: Wyckoff, Ngắn/Trung hạn, hướng xử lý khi cầm tiền mặt, vùng mua thăm dò, cắt lỗ, Target 1-2."""
    mark = "📌 " if r["Mã"] in held else ("👁 " if r["Mã"] in watch else "")
    chg = "" if pd.isna(r["Chg"]) else f" ({r['Chg']:+.1f}%)"
    esc = html.escape
    icon = "🟢" if r["Loại"] == "acc" else "🔴"
    head = f"{icon} {mark}<b>{esc(r['Mã'])}</b> · Giá {r['Giá']:,.2f}{chg} · GTGD {r['GTGD']:,.0f} tỷ"
    wy_line = f"<b>Wyckoff</b> {esc(r['Nhãn'])} · {esc(PHASE_NOTE[r['Loại']][r['Pha']])}"
    ctx = {"code": r["Mã"], "close": r["Giá"], "ma20": r["ma20"], "ma50": r["ma50"], "ma200": r["ma200"],
           "wy": r["wy"], "sup": r["sup"], "res": r["res"], "label": "", "state": "", "reason": "", "lean": int(r["Lean"] or 0), "div": [], "zone": None}
    try:
        pt = AS.parts(ctx)
    except Exception as e:  # noqa: BLE001
        print(f"  không dựng được tóm tắt {r['Mã']}: {e}")
        pt = {}
    block1 = wy_line + ("\n" + pt["picture"] if pt.get("picture") else "") + "\n" + f"<b>{esc(_lean_line(r))}</b>"
    cash = pt.get("cash")
    action = ""
    if cash:
        _, why, zone = cash
        action = (why[:1].upper() + why[1:]) + (f"\n   ↳ {zone}" if zone else "")
    lv = _plan_levels(r)
    plan = ""
    try:
        mid_pos = AS._signals(ctx)["mid"] == "+"
    except Exception:  # noqa: BLE001
        mid_pos = False
    zone_name = "Vùng chờ mua" if mid_pos else "Vùng mua thăm dò"      # trung hạn tích cực thì gọi là vùng chờ mua
    if lv:
        plan = (f"{zone_name}: {lv['lo']:,.2f} – {lv['hi']:,.2f}\n"
                f"Cắt lỗ nếu sai: {lv['stop']:,.2f} ({lv['stop_pct']:+.1f}%)\n"
                f"Target 1: {lv['t1']:,.2f} ({lv['t1_pct']:+.1f}%)\n"
                f"Target 2: {lv['t2']:,.2f} ({lv['t2_pct']:+.1f}%)")
    foot = "<i>Quy tắc mang tính chủ quan, chỉ để tham khảo, không phải khuyến nghị đầu tư.</i>"
    mid = "\n".join(x for x in (action, plan) if x)
    return "\n\n".join(x for x in (head, block1, mid, foot) if x)


def build_acc_messages(show: pd.DataFrame, held: set[str], watch: set[str], cap: int) -> list[str]:
    """Tích lũy: tách theo từng pha (C, D, E, B, A); mỗi pha có 1 tin mở đầu rồi mỗi mã 1 tin riêng."""
    acc = _sorted(show, "acc", held, watch)
    msgs: list[str] = []
    for ph in ORDER["acc"]:
        g = acc[acc["Pha"] == ph]
        if g.empty:
            continue
        shown = g.head(cap) if cap else g
        title = WY.PHASE_NAME["acc"][ph] if hasattr(WY, "PHASE_NAME") else PHASE_NOTE["acc"][ph]
        hint = WY.PHASE_HINT["acc"][ph] if hasattr(WY, "PHASE_HINT") else ""
        more = f" · hiển thị {len(shown)}/{len(g)} mã" if len(g) > len(shown) else ""
        msgs.append(f"🟢 <b>TÍCH LŨY · PHA {ph} — {html.escape(title)}</b> ({len(g)} mã{more})"
                    + (f"\n<i>{html.escape(hint)}</i>" if hint else ""))
        msgs.extend(_stock_msg(r, held, watch) for _, r in shown.iterrows())
    return msgs


def _sorted(d: pd.DataFrame, kind: str, held: set[str], watch: set[str]) -> pd.DataFrame:
    d = d[d["Loại"] == kind].copy()
    d["_p"] = d["Mã"].map(lambda c: 0 if c in held else 1 if c in watch else 2)
    d["_o"] = d["Pha"].map({p: i for i, p in enumerate(ORDER[kind])})
    return d.sort_values(["_p", "_o", "Khớp"], ascending=[True, True, False])


SEP = "─" * 26                  # đường kẻ ngăn cách các mã trong mục cảnh báo phân phối


def _section_chunks(title: str, total: int, items: list[str], more: str, limit: int = TG_LIMIT) -> list[str]:
    """Chia 1 mục (tích lũy / phân phối) thành nhiều khối <pre>, mỗi khối không vượt quá giới hạn Telegram.
    Mỗi khối tự đóng/mở thẻ <pre> riêng nên tin nhắn nào cũng hợp lệ."""
    def render(body: list[str], first: bool) -> str:
        t = f"{title} ({total} mã)" if first else f"{title} (tiếp)"
        return f"<b>{t}</b>\n<pre>{(chr(10) + SEP + chr(10)).join(body)}</pre>"

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


def _by_sector(codes: list[str], smap: dict[str, str]) -> str:
    """"Ngân hàng: HDB, VPB\nChứng khoán: HCM, TCX" (ngành nhiều mã đứng trước, "Khác" đứng cuối)."""
    groups: dict[str, list[str]] = {}
    for c in codes:
        groups.setdefault(smap.get(c.upper(), "Khác"), []).append(c)
    order = sorted(groups, key=lambda k: (k == "Khác", -len(groups[k]), k))
    return "\n".join(f"{html.escape(k)}: {html.escape(', '.join(groups[k]))}" for k in order)


def build_summary(show: pd.DataFrame, held: set[str], watch: set[str]) -> list[str]:
    """Tin tổng hợp gửi trước các tin riêng lẻ: canh mua, từng pha tích lũy, cảnh báo phân phối; mỗi mục gom theo ngành."""
    smap = _sector_map()
    acc = _sorted(show, "acc", held, watch)
    blocks: list[str] = []
    buy = acc[acc["Pha"].isin(BUY_PHASES)]
    if not buy.empty:
        blocks.append(f"<b>🎯 Cổ phiếu canh mua</b> (tích lũy pha {', '.join(BUY_PHASES)}) · {len(buy)} mã\n" + _by_sector(list(buy["Mã"]), smap))
    for ph in ORDER["acc"]:
        g = acc[acc["Pha"] == ph]
        if not g.empty:
            blocks.append(f"<b>🟢 Cổ phiếu tích lũy pha {ph}, {html.escape(PHASE_NOTE['acc'][ph])}</b> · {len(g)} mã\n" + _by_sector(list(g["Mã"]), smap))
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
                   mode_txt: str, sent_at: datetime | None = None, cap_acc: int = 10) -> list[str]:
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
    return _pack([head] + build_summary(show, held, watch)) + build_acc_messages(show, held, watch, cap_acc) + _pack(dist_blocks + [foot])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="chỉ in ra, không gửi và không ghi trạng thái")
    ap.add_argument("--all", action="store_true", help="gửi toàn bộ danh sách hiện tại, không chỉ mã mới / đổi pha")
    ap.add_argument("--only", default="", help="chỉ xét các mã này, ngăn cách bằng dấu phẩy")
    ap.add_argument("--max", type=int, default=20, help="số mã tối đa của mục phân phối (mặc định 20, 0 = tất cả)")
    ap.add_argument("--max-acc", type=int, default=10, help="số mã tối đa MỖI PHA của mục tích lũy, mỗi mã 1 tin (mặc định 10, 0 = tất cả)")
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
    msgs = build_messages(show, totals, latest, held, watch, args.max, mode_txt, cap_acc=args.max_acc)
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
