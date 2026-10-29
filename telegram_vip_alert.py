#!/usr/bin/env python3
"""Gửi Telegram TÍN HIỆU của các cổ phiếu trong danh mục "Khuyến nghị khách hàng" (trang Khuyến nghị khách hàng, vip_picks.py).

Số liệu lấy đúng như trang đó: vip_picks.build_view + vip_picks.recommend, nên nhãn tín hiệu trên Telegram khớp nhãn "Khuyến nghị" trên app
(Điểm mua / Cutloss / Target / Điểm bán Admin nhập; ô trống thì tự điền theo hệ thống). Chỉ xét mã ở nhóm "Chờ mua" và "Đang nắm giữ" (nhóm "Đã đóng" bỏ qua).

Tín hiệu theo từng mã (vip_picks.recommend):
  Đang nắm giữ : CẮT LỖ · HẠ TỶ TRỌNG · CHỐT LỜI · CHỐT BỚT · NẮM GIỮ
  Chờ mua      : VÙNG MUA · CHỜ VỀ VÙNG MUA · DƯỚI VÙNG MUA · HỦY KỊCH BẢN · ĐÃ CHẠY QUÁ · CHƯA NÊN MUA · THEO DÕI

Tin nhắn gom theo mức độ cần chú ý:
  🔴 CẦN XỬ LÝ    CẮT LỖ, HẠ TỶ TRỌNG, HỦY KỊCH BẢN, CHƯA NÊN MUA     (thẻ đầy đủ)
  🟡 CHỐT LỜI     CHỐT LỜI, CHỐT BỚT                                  (thẻ đầy đủ)
  🟢 VÀO VÙNG MUA VÙNG MUA                                            (thẻ đầy đủ)
  📦 ĐANG NẮM GIỮ NẮM GIỮ                                             (một dòng / mã)
  ⏳ CHỜ MUA      CHỜ VỀ VÙNG MUA, DƯỚI VÙNG MUA, ĐÃ CHẠY QUÁ, THEO DÕI (một dòng / mã)
Mã vừa đổi tín hiệu so với lần gửi trước được đánh dấu 🔄 (kèm tín hiệu cũ), mã mới thêm vào danh mục đánh dấu 🆕.

Chống gửi lặp: nhớ tín hiệu đã gửi ở data/vip_alert_state.json. Mặc định chỉ gửi khi có phiên dữ liệu mới HOẶC có mã đổi tín hiệu / thêm / bỏ
(chạy lại cùng ngày không đổi gì thì không gửi lại). Dùng --force để gửi bất kể.

Danh mục đọc qua vip_picks.load(): nếu đã cấu hình đồng bộ GitHub (VIP_GITHUB_TOKEN + VIP_DATA_REPO hoặc VIP_GIST_ID) thì đọc bản mới nhất Admin vừa lưu
trên app, không thì đọc data/khuyen_nghi_khach_hang.csv trong kho.

Biến môi trường:
    VIP_TELEGRAM_BOT_TOKEN / VIP_TELEGRAM_CHAT_ID   bot và nhóm / kênh KHÁCH HÀNG (không đặt thì dùng TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID)
    VIP_GITHUB_TOKEN, VIP_DATA_REPO | VIP_GIST_ID, VIP_DATA_PATH, VIP_DATA_BRANCH     (giống app, tùy chọn)

Cách chạy:
    python telegram_vip_alert.py --dry-run          # chỉ in ra, không gửi và không ghi trạng thái
    python telegram_vip_alert.py                    # gửi thật (khi có phiên mới hoặc có thay đổi)
    python telegram_vip_alert.py --force            # gửi toàn bộ bất kể đã gửi hay chưa
    python telegram_vip_alert.py --changes-only     # chỉ gửi các mã đổi tín hiệu / mới thêm
    python telegram_vip_alert.py --only MWG,GMD     # chỉ xét các mã này
Chỉ phục vụ nghiên cứu, không phải khuyến nghị đầu tư.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import sys
import textwrap
import time
import types
import unicodedata

import numpy as np
import pandas as pd


def _ensure_streamlit() -> None:
    """vip_picks.py và xep_hang_nganh.py import streamlit (dùng cho giao diện). Máy chạy Actions không cài streamlit thì dùng bản giả tối thiểu."""
    try:
        import streamlit  # noqa: F401
        return
    except ImportError:
        pass
    m = types.ModuleType("streamlit")

    def cache_data(*a, **k):
        return a[0] if (len(a) == 1 and callable(a[0]) and not k) else (lambda f: f)

    m.cache_data = m.cache_resource = cache_data
    m.secrets, m.session_state = {}, {}
    sys.modules["streamlit"] = m


_ensure_streamlit()

import engine as E                      # noqa: E402
import fund_guard as FG                 # noqa: E402
import mtf_levels as ML                 # noqa: E402
import rsi_divergence as DV             # noqa: E402
import vip_picks as VP                  # noqa: E402
import waiting_buy as WB                # noqa: E402
import wyckoff as WY                    # noqa: E402
from telegram_alert import SKIP, TG_LIMIT, send          # noqa: E402
from telegram_supertrend_alert import now_vn, stamp     # noqa: E402

CSV_PATH = "data/eod_prices.csv"
STATE_PATH = "data/vip_alert_state.json"
ACTIVE = ("Chờ mua", "Đang nắm giữ")
W = 38                                    # độ rộng một dòng trong khối chữ đơn cách (vừa màn hình điện thoại)

# tín hiệu -> (mục, biểu tượng). Tín hiệu không có trong bảng này rơi vào mục "Chờ mua" hoặc "Đang nắm giữ" theo trạng thái.
SECTION_OF = {"CẮT LỖ": "risk", "HẠ TỶ TRỌNG": "risk", "HỦY KỊCH BẢN": "risk", "CHƯA NÊN MUA": "risk",
              "CHỐT LỜI": "profit", "CHỐT BỚT": "profit", "VÙNG MUA": "buy", "NẮM GIỮ": "hold"}
ICON = {"CẮT LỖ": "🔴", "HẠ TỶ TRỌNG": "🔴", "HỦY KỊCH BẢN": "🔴", "CHƯA NÊN MUA": "🔴", "CHỐT LỜI": "🟡", "CHỐT BỚT": "🟡",
        "VÙNG MUA": "🟢", "NẮM GIỮ": "📦"}
SECTIONS = [("risk", "🔴 CẦN XỬ LÝ", True), ("profit", "🟡 CHỐT LỜI", True), ("buy", "🟢 VÀO VÙNG MUA", True),
            ("hold", "📦 ĐANG NẮM GIỮ", False), ("wait", "⏳ CHỜ MUA", False)]


# ------------------------------------------------------------------ dữ liệu (cùng nguồn với app)
def build_frames(path: str, codes: set[str]):
    """Như telegram_buy_alert.build_frames nhưng chỉ dựng chỉ báo cho các mã trong danh mục (nhanh hơn nhiều).
    Chuỗi thị trường (RS) vẫn tính trên toàn bộ dữ liệu như app."""
    raw = E.clean_raw(pd.read_csv(path, dtype={"Mã": str}))
    latest = pd.Timestamp(raw["Ngày"].max())
    mkt, _ = E.market_series(raw)
    sub = raw[raw["Mã"].isin(codes) & ~raw["Mã"].isin(SKIP)]
    parts = {"D": [], "W": [], "M": []}
    for _, g in sub.groupby("Mã"):
        base = g[["Mã", "Ngày"] + E.NUMERIC_COLS]
        for tf in parts:
            parts[tf].append(E.add_indicators(E.resample_ohlcv(base, tf)))
    if not parts["D"]:
        return None, None, latest
    frames = {tf: pd.concat(p, ignore_index=True) for tf, p in parts.items()}
    frames["D"] = E.mask_chg_gaps(frames["D"])
    return frames, mkt, latest


def _num(v):
    if not isinstance(v, str) or not v.strip():
        return None
    try:
        return float(v.replace("%", "").replace(" ", "").replace(",", "."))
    except ValueError:
        return None


def load_fund_map() -> dict:
    """P/E, P/B, ROE cho điểm FA: fundamentals.csv (đã chặn số mặc định) + bảng xếp hạng ngành, số nhập tay (nhap_tay.csv) ưu tiên - giống app."""
    fund, cap = FG.load_fund_map(), {}
    try:
        import xep_hang_nganh as XH
        XH.apply_to_maps(fund, cap)
    except Exception as e:  # noqa: BLE001
        print(f"  bỏ qua bảng xếp hạng ngành: {e}")
    try:
        mt = pd.read_csv("data/nhap_tay.csv", dtype=str, encoding="utf-8-sig")
        mt.columns = [str(c).strip() for c in mt.columns]
        for _, row in mt.iterrows():
            code = str(row.get("Mã", "")).strip().upper()
            if not code or code == "NAN":
                continue
            name = row.get("Tên công ty")
            if isinstance(name, str) and name.strip():
                fund.setdefault(code, {})["Tên công ty"] = name.strip()
            for col in ("P/B", "ROE", "P/E"):
                v = _num(row.get(col))
                if v is not None:
                    fund.setdefault(code, {})[col] = v
    except Exception:  # noqa: BLE001
        pass
    return fund


def make_ctx_fn(frames: dict, wbmap: dict):
    """Ngữ cảnh 'Tóm tắt nhanh' của một mã (như app._action_ctx) để vip_picks tự điền Điểm mua / Cutloss / Target còn trống."""
    cache: dict = {}

    def ctx(code: str):
        if code in cache:
            return cache[code]
        out = None
        try:
            pick = lambda tf: frames[tf][frames[tf]["Mã"] == code]       # noqa: E731
            g = pick("D").sort_values("Ngày")
            c = pd.to_numeric(g["Giá đóng cửa"], errors="coerce")
            if not c.empty:
                ma = {n: (float(c.rolling(n).mean().iloc[-1]) if len(c) >= n else None) for n in (20, 50, 200)}
                w = wbmap.get(code, {})
                state = w.get("Trạng thái") if isinstance(w.get("Trạng thái"), str) else ""
                reason = w.get("Lý do") if isinstance(w.get("Lý do"), str) else ""
                try:
                    a = E.analyze_frame(pick("D"), "D")
                    lean = a.get("dir", 0) if a.get("enough") else 0
                except Exception:  # noqa: BLE001
                    lean = 0
                try:
                    d = ML.analyze_dwm_timeframe(pick("D"), pick("W"), pick("M"))["D"]
                except Exception:  # noqa: BLE001
                    d = {}
                try:
                    div = DV.analyze(frames, code, ("M", "W", "D"))
                except Exception:  # noqa: BLE001
                    div = []
                try:
                    wy = WY.compact(WY.analyze(g.reset_index(drop=True)))
                except Exception:  # noqa: BLE001
                    wy = None
                grp = WB.STATE_GROUP.get(state, "") if state else ""
                out = dict(code=code, close=float(c.iloc[-1]), ma20=ma[20], ma50=ma[50], ma200=ma[200],
                           label=WB.status_tag(state, reason)[0] if state else "", state=state, reason=reason,
                           lean=lean, div=div, wy=wy, sup=d.get("sup") if d.get("ok") else None,
                           res=d.get("res") if d.get("ok") else None,
                           zone=(w.get("Vùng mua từ"), w.get("Vùng mua đến")) if grp in WB.BUY_GROUPS else None)
        except Exception as e:  # noqa: BLE001
            print(f"  {code}: thiếu ngữ cảnh ({e})")
        cache[code] = out
        return out

    return ctx


def scan(path: str, only: set[str] | None) -> tuple[pd.DataFrame, pd.DataFrame, pd.Timestamp]:
    """Trả (bảng tín hiệu từng mã, bảng mã chưa có dữ liệu giá, ngày dữ liệu mới nhất)."""
    plans = VP.load()
    if VP._ERR:
        print(f"  ⚠ đọc danh mục: {VP._ERR}")
    plans = plans[plans["Trạng thái"].isin(ACTIVE)]
    if only:
        plans = plans[plans["Mã"].isin(only)]
    if plans.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.Timestamp.now().normalize()
    frames, mkt, latest = build_frames(path, set(plans["Mã"]))
    if frames is None:
        return pd.DataFrame(), plans[["Mã"]].assign(**{"_nodata": True}), latest
    res = E.build_screener(frames, mkt)
    res["Nhóm"] = ""
    wb = WB.build_waiting_buy(frames, res)
    cols = [c for c in ("Trạng thái", "Lý do", "Vùng mua từ", "Vùng mua đến") if c in wb.columns]
    wbmap = wb.drop_duplicates("Mã", keep="first").set_index("Mã")[cols].to_dict("index") if not wb.empty else {}
    fund = load_fund_map()
    meta = lambda code: (str((fund.get(code) or {}).get("Tên công ty") or ""), "")          # noqa: E731
    view = VP.build_view(plans, res, frames["D"], fund, wb, meta, make_ctx_fn(frames, wbmap))
    if view.empty:
        return view, pd.DataFrame(), latest
    nodata = view[view.get("_nodata", False) == True] if "_nodata" in view.columns else pd.DataFrame()      # noqa: E712
    ok = view[~view["Mã"].isin(nodata["Mã"])] if len(nodata) else view
    return ok.reset_index(drop=True), nodata, latest


# ------------------------------------------------------------------ định dạng
def px(v) -> str:
    return "—" if v is None or pd.isna(v) else f"{float(v):,.2f}"


def pct(v, signed: bool = True) -> str:
    return "" if v is None or pd.isna(v) else f"({float(v):+.1f}%)" if signed else f"{float(v):.1f}%"


def zone_txt(buy, sep: str = " – ") -> str:
    """Vùng mua dạng "lo – hi"; vùng một mốc (lo = hi) chỉ hiện một giá."""
    return px(buy[0]) if abs(buy[0] - buy[1]) < 1e-9 else f"{px(buy[0])}{sep}{px(buy[1])}"


def _row(left: str, right: str) -> str:
    return left + " " * max(1, W - len(left) - len(right)) + right


def _wrap(text: str) -> list[str]:
    return textwrap.wrap(str(text or "").strip(), width=W) or []


def section_of(r) -> str:
    label = r["Khuyến nghị"][0]
    return SECTION_OF.get(label) or ("hold" if r["Trạng thái"] == "Đang nắm giữ" else "wait")


def _zone_gap(price: float, buy) -> str:
    """Giá cách vùng mua bao nhiêu %: dương = giá cao hơn biên trên, âm = giá thấp hơn biên dưới, rỗng = đang trong vùng."""
    if not buy:
        return ""
    lo, hi = buy
    if price > hi * VP.NEAR_BUY:
        return f"cao hơn vùng {(price / hi - 1) * 100:.1f}%"
    if price < lo:
        return f"thấp hơn vùng {(1 - price / lo) * 100:.1f}%"
    return "trong vùng"


def _mark(code: str, prev: dict | None, label: str, status: str) -> str:
    """🆕 mã mới thêm vào danh mục; 🔄 đổi tín hiệu so với lần gửi trước (kèm tín hiệu cũ)."""
    if prev is None:
        return ""
    old = prev.get(code)
    if old is None:
        return "🆕 "
    return "🔄 " if old != f"{status}|{label}" else ""


def card_text(r, prev: dict | None) -> str:
    label, _, note = r["Khuyến nghị"]
    code, status, price = r["Mã"], r["Trạng thái"], float(r["Giá"])
    mark = _mark(code, prev, label, status)
    old = (prev or {}).get(code)
    was = f"  (trước: {old.split('|', 1)[1]})" if mark == "🔄 " and old and "|" in old else ""
    sep = "─" * W
    chg = r.get("Chg %")
    head = _row(f"{mark}{code}", f"Giá {px(price)} {pct(chg)}".rstrip())
    lines = [head, f"{ICON.get(label, '•')} {label}{was}", *_wrap(note), sep]
    buy, stop, tgt, sell = r.get("Điểm mua"), r.get("Cutloss"), r.get("Target"), r.get("Điểm bán")
    if status == "Đang nắm giữ":
        if pd.notna(r.get("Entry")):
            lines.append(_row(f"Giá vào {px(r['Entry'])}", f"Lãi/lỗ {r['Lãi %']:+.1f}%"))
        elif buy:
            lines.append(_row("Vùng mua KN", zone_txt(buy)))
    else:
        if buy:
            lines.append(_row("▌VÙNG MUA▐", zone_txt(buy)))
            gap = _zone_gap(price, buy)
            if gap and gap != "trong vùng":
                lines.append(f"Giá {gap}")
        else:
            lines.append("Chưa có vùng mua")
    if stop:
        lines.append(_row("Cắt lỗ", f"{px(stop)} {pct((stop / price - 1) * 100)}"))
    if tgt:
        lines.append(_row("Mục tiêu 1", f"{px(tgt)} {pct((tgt / price - 1) * 100)}"))
    if sell and (not tgt or abs(sell - tgt) > 1e-9):
        lines.append(_row("Điểm bán", f"{px(sell)} {pct((sell / price - 1) * 100)}"))
    sc = []
    if pd.notna(r.get("Tổng điểm")):
        sc.append(f"Điểm {r['Tổng điểm']:.0f}" + (f" ({r['Hạng']})" if r.get("Hạng") else ""))
    for k in ("FA", "TA"):
        if r.get(k) is not None and pd.notna(r.get(k)):
            sc.append(f"{k} {float(r[k]):.0f}")
    if sc:
        lines += [sep, " · ".join(sc)]
    if str(r.get("Luận điểm") or "").strip():
        lines += _wrap("Luận điểm: " + str(r["Luận điểm"]))
    meta = " · ".join(x for x in (r.get("Khung"), f"KN {r['Ngày KN']}" if r.get("Ngày KN") else "") if x)
    if meta:
        lines.append(meta)
    return unicodedata.normalize("NFC", "\n".join(lines))


def line_text(r, prev: dict | None) -> str:
    """Một dòng gọn cho mục Đang nắm giữ / Chờ mua."""
    label, _, _ = r["Khuyến nghị"]
    code, status, price = r["Mã"], r["Trạng thái"], float(r["Giá"])
    mark = _mark(code, prev, label, status)
    old = (prev or {}).get(code)
    was = f" ← {old.split('|', 1)[1]}" if mark == "🔄 " and old and "|" in old else ""
    parts = [f"{mark}<b>{html.escape(code)}</b> {px(price)} {pct(r.get('Chg %'))}".rstrip()]
    if status == "Đang nắm giữ":
        if pd.notna(r.get("Lãi %")):
            parts.append(f"lãi/lỗ {r['Lãi %']:+.1f}%")
        if r.get("Cutloss"):
            parts.append(f"cắt lỗ {px(r['Cutloss'])}")
        if r.get("Target"):
            parts.append(f"MT {px(r['Target'])}")
    else:
        buy = r.get("Điểm mua")
        if buy:
            parts.append(f"vùng mua {zone_txt(buy, '–')}")
            gap = _zone_gap(price, buy)
            if gap:
                parts.append(gap)
        else:
            parts.append("chưa có vùng mua")
    if label not in ("NẮM GIỮ", "CHỜ VỀ VÙNG MUA"):
        parts.append(f"<i>{html.escape(label)}{html.escape(was)}</i>")
    elif was:
        parts.append(f"<i>{html.escape(was.strip())}</i>")
    return " · ".join(parts)


def build_messages(view: pd.DataFrame, nodata: pd.DataFrame, removed: list[str], latest: pd.Timestamp,
                   prev: dict | None, changes_only: bool, changed: set[str]) -> list[str]:
    n_hold = int((view["Trạng thái"] == "Đang nắm giữ").sum())
    n_wait = int((view["Trạng thái"] == "Chờ mua").sum())
    secs = {k: [] for k, _, _ in SECTIONS}
    for _, r in view.iterrows():
        secs[section_of(r)].append(r)
    act = len(secs["risk"]) + len(secs["profit"]) + len(secs["buy"])
    head = (f"🔥 <b>Khuyến nghị khách hàng · phiên {latest:%d/%m/%Y}</b>\n"
            f"Đang nắm giữ: {n_hold} · Chờ mua: {n_wait} · Cần chú ý: {act}"
            + (f"\nĐổi tín hiệu / mới thêm: {len(changed)} mã" if prev is not None else ""))
    msgs, cur = [], head
    for key, title, full in SECTIONS:
        rows = secs[key]
        if changes_only:
            rows = [r for r in rows if r["Mã"] in changed]
        if not rows:
            continue
        if full:
            pieces = ["<pre>" + html.escape(card_text(r, prev)) + "</pre>" for r in rows]
        else:
            pieces = ["\n".join(line_text(r, prev) for r in rows)]
        started = False
        for p in pieces:
            piece = p if started else f"<b>{title}</b>\n{p}"
            if len(cur) + len(piece) + 2 > TG_LIMIT:
                msgs.append(cur)
                cur = f"<b>{title}{' (tiếp)' if started else ''}</b>\n{p}"
            else:
                cur = f"{cur}\n\n{piece}"
            started = True
    if removed:
        cur += f"\n\n■ Đã rời danh mục (đóng lệnh / bỏ theo dõi): {html.escape(', '.join(removed))}"
    if len(nodata):
        cur += f"\n\nChưa có dữ liệu giá: {html.escape(', '.join(nodata['Mã']))}"
    cur += "\n\n<i>Chỉ phục vụ nghiên cứu, không phải khuyến nghị đầu tư.</i>\n" + f"<i>{stamp(now_vn())}</i>"
    msgs.append(cur)
    return msgs


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


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="chỉ in ra, không gửi và không ghi trạng thái")
    ap.add_argument("--force", action="store_true", help="gửi bất kể đã gửi phiên này chưa")
    ap.add_argument("--changes-only", action="store_true", help="chỉ gửi các mã đổi tín hiệu / mới thêm")
    ap.add_argument("--only", default="", help="chỉ xét các mã này, ngăn cách bằng dấu phẩy")
    ap.add_argument("--csv", default=CSV_PATH)
    args = ap.parse_args()

    only = {c.strip().upper() for c in args.only.split(",") if c.strip()} or None
    view, nodata, latest = scan(args.csv, only)
    if view.empty and nodata.empty:
        print("Danh mục khuyến nghị không có mã nào ở nhóm Chờ mua / Đang nắm giữ.")
        return

    snapshot = {r["Mã"]: f"{r['Trạng thái']}|{r['Khuyến nghị'][0]}" for _, r in view.iterrows()}
    st = None if only else load_state()
    prev = st.get("state") if st else None
    changed = {c for c, s in snapshot.items() if prev is not None and prev.get(c) != s}
    removed = sorted(set(prev or {}) - set(snapshot) - set(nodata["Mã"])) if (prev is not None and not only) else []
    new_day = st is None or st.get("latest") != f"{latest:%Y-%m-%d}"

    if not args.force and not args.dry_run and prev is not None:
        if args.changes_only and not (changed or removed):
            print("Không có mã nào đổi tín hiệu, không gửi.")
            return
        if not args.changes_only and not (new_day or changed or removed):
            print("Phiên này đã gửi và không có thay đổi, không gửi lại (dùng --force để gửi lại).")
            return

    msgs = build_messages(view, nodata, removed, latest, prev, args.changes_only, changed)
    if args.dry_run:
        for m in msgs:
            print(m, "\n" + "=" * 40)
        return
    token = os.environ.get("VIP_TELEGRAM_BOT_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat = os.environ.get("VIP_TELEGRAM_CHAT_ID") or os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat:
        raise SystemExit("Thiếu VIP_TELEGRAM_CHAT_ID / TELEGRAM_CHAT_ID hoặc token bot (đặt trong GitHub Secrets).")
    for i, m in enumerate(msgs):
        send(token, chat, m)
        if i < len(msgs) - 1:
            time.sleep(1.2)
    if not only:
        save_state(snapshot, latest)
    print(f"Đã gửi {len(msgs)} tin nhắn ({len(view)} mã).")


if __name__ == "__main__":
    main()
