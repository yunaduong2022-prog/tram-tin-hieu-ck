#!/usr/bin/env python3
"""Gửi Telegram các cổ phiếu có VÙNG MUA: "Vào được ngay", "Chờ mua" và "Phục hồi đang chờ mua".

Số liệu lấy đúng từ waiting_buy.build_waiting_buy (cùng bảng với trang Chờ mua / Mua ngay / Đang phục hồi):
vùng mua, cắt lỗ, mục tiêu 1-2, R:R. Mỗi mã là một khối chữ đơn cách (monospace), trắng đen như phác thảo:

    NTP         Giá 54.0  [✓ Vào được ngay]
    ────────────────────────────────────
    Mục tiêu 2  R:R 1:3     59.3 (+11.2%)
    Mục tiêu 1  R:R 1:2     57.3 (+7.5%)
    ▌VÙNG MUA▐              53.0 – 53.6
    Cắt lỗ                  51.3 (-3.7%)
    ────────────────────────────────────
    Trong vùng mua, nên chia lệnh
    Cản gần 54.8 (+2.8%)
    ────────────────────────────────────
    P/B 1.25 · P/E 10.3 · ROE 12.1%
    Vốn hóa 4,321 tỷ
    Min Trading 23/10/2026

Biến môi trường: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID (giống telegram_alert.py).

Cách chạy:
    python telegram_buy_alert.py --dry-run               # chỉ in ra, không gửi
    python telegram_buy_alert.py                         # gửi thật
    python telegram_buy_alert.py --max-wait 10 --max-recover 5
    python telegram_buy_alert.py --include-watch         # thêm nhóm "Theo dõi thêm" vào mục Chờ mua
"""
from __future__ import annotations

import argparse
import html
import os
import textwrap
import time
import unicodedata

import pandas as pd

import engine as E
import waiting_buy as WB
from telegram_alert import SKIP, send, TG_LIMIT

CSV_PATH = "data/eod_prices.csv"
W = 38                                   # độ rộng một dòng trong khối chữ đơn cách (vừa màn hình điện thoại)
SELL_ACTIONS = {"BÁN", "CHỐT LỜI"}       # giống trang Mua ngay: bỏ mã đã có tín hiệu bán / chốt lời


# ------------------------------------------------------------------ dữ liệu
def build_frames(path: str):
    raw = E.clean_raw(pd.read_csv(path, dtype={"Mã": str}))
    raw = raw[~raw["Mã"].isin(SKIP)]
    parts = {"D": [], "W": [], "M": []}
    for _, g in raw.groupby("Mã"):
        base = g[["Mã", "Ngày"] + E.NUMERIC_COLS]
        for tf in parts:
            parts[tf].append(E.add_indicators(E.resample_ohlcv(base, tf)))
    frames = {tf: pd.concat(p, ignore_index=True) for tf, p in parts.items()}
    frames["D"] = E.mask_chg_gaps(frames["D"])
    return raw, frames


def waiting_table(path: str) -> tuple[pd.DataFrame, pd.Timestamp]:
    raw, frames = build_frames(path)
    mkt, _ = E.market_series(raw)
    res = E.build_screener(frames, mkt)
    res["Nhóm"] = ""
    latest = pd.Timestamp(frames["D"]["Ngày"].max())
    return WB.build_waiting_buy(frames, res), latest


def _num(v):
    if not isinstance(v, str) or not v.strip():
        return None
    try:
        return float(v.replace("%", "").replace(" ", "").replace(",", "."))
    except ValueError:
        return None


def load_meta() -> tuple[dict, dict]:
    """(vốn hóa theo mã, {mã: {P/B, P/E, ROE}}): data/stock_metadata.csv + data/fundamentals.csv,
    số nhập tay ở data/nhap_tay.csv được ưu tiên (giống app)."""
    cap, fund = {}, {}
    try:
        m = pd.read_csv("data/stock_metadata.csv", dtype={"Mã": str})
        cap = dict(zip(m["Mã"].str.upper().str.strip(), m["Vốn hóa TT"]))
    except Exception:
        pass
    try:
        f = pd.read_csv("data/fundamentals.csv", dtype={"Mã": str})
        f["Mã"] = f["Mã"].str.upper().str.strip()
        fund = f.drop_duplicates("Mã", keep="last").set_index("Mã").to_dict("index")
    except Exception:
        pass
    try:
        mt = pd.read_csv("data/nhap_tay.csv", dtype=str, encoding="utf-8-sig")
        mt.columns = [str(c).strip() for c in mt.columns]
        for _, row in mt.iterrows():
            code = str(row.get("Mã", "")).strip().upper()
            if not code or code == "NAN":
                continue
            for col in ("P/B", "ROE", "P/E"):
                v = _num(row.get(col))
                if v is not None:
                    fund.setdefault(code, {})[col] = v
            c = _num(row.get("Vốn hóa TT"))
            if c is not None:
                cap[code] = c
    except Exception:
        pass
    return cap, fund


# ------------------------------------------------------------------ định dạng
def _px(v) -> str:
    return f"{float(v):,.1f}"


def _pct(v) -> str:
    return f"({float(v):+.1f}%)"


def _row(left: str, right: str) -> str:
    return left + " " * max(1, W - len(left) - len(right)) + right


def _fmt(v, f: str) -> str:
    try:
        return f.format(float(v)) if pd.notna(v) else "—"
    except (TypeError, ValueError):
        return "—"


def _wrap(text: str) -> list[str]:
    out: list[str] = []
    for seg in text.split(" · "):
        out += textwrap.wrap(seg.strip(), width=W) or []
    return out or [""]


def _note(r) -> str:
    if r.get("Hành động") == "Vào ngay":
        t = "Trong vùng mua, nên chia lệnh"
        can, t1 = r.get("Cản gần"), r.get("Mục tiêu 1")
        if pd.notna(can) and pd.notna(t1) and float(can) < float(t1):
            t += f" · Cản gần {_px(can)} {_pct((float(can) / float(r['Giá']) - 1) * 100)}"
        return t
    return WB._sentence(r.get("Ghi chú hành động") or "")


def card_text(r, meta: tuple[dict, dict], foot: str) -> str:
    cap_map, fund_map = meta
    code = str(r["Mã"]).upper()
    fd = fund_map.get(code, {})
    tag = "✓ Vào được ngay" if r.get("Hành động") == "Vào ngay" else "… Chờ mua"
    sep = "─" * W
    lines = [
        _row(code, f"Giá {_px(r['Giá'])}  [{tag}]"),
        sep,
        *([_row("Mục tiêu 2  R:R 1:3", f"{_px(r['Mục tiêu 2'])} {_pct(r['Lời 2 %'])}")] if pd.notna(r.get("Mục tiêu 2")) else []),
        _row("Mục tiêu 1  R:R 1:2", f"{_px(r['Mục tiêu 1'])} {_pct(r['Lời 1 %'])}"),
        _row("▌VÙNG MUA▐", f"{_px(r['Vùng mua từ'])} – {_px(r['Vùng mua đến'])}"),
        _row("Cắt lỗ", f"{_px(r['Cắt lỗ'])} {_pct(r['Cắt lỗ %'])}"),
        sep,
        *_wrap(_note(r)),
        sep,
        f"P/B {_fmt(fd.get('P/B'), '{:.2f}')} · P/E {_fmt(fd.get('P/E'), '{:.1f}')} · ROE {_fmt(fd.get('ROE'), '{:.1f}%')}",
        f"Vốn hóa {_fmt(cap_map.get(code), '{:,.0f} tỷ')}",
        foot,
    ]
    return unicodedata.normalize("NFC", "\n".join(lines))


# ------------------------------------------------------------------ chọn mã và gói tin nhắn
def select(t: pd.DataFrame, include_watch: bool) -> dict[str, pd.DataFrame]:
    ok = t["Vùng mua từ"].notna() & t["Vùng mua đến"].notna()
    if "Hành động bán" in t.columns:
        ok &= ~t["Hành động bán"].isin(SELL_ACTIONS)
    groups = (WB.G1, WB.G2, WB.G3) if include_watch else (WB.G1, WB.G2)
    buy = t[ok & t["Danh sách"].isin(WB.BUY_GROUPS)]
    now = buy[buy["Hành động"] == "Vào ngay"]
    now = WB.sort_group(now, WB.G1)
    wait = buy[(buy["Hành động"] != "Vào ngay") & buy["Danh sách"].isin(groups)]
    wait = pd.concat([WB.sort_group(wait[wait["Danh sách"] == g], g) for g in groups]) if len(wait) else wait
    rec = t[ok & (t["Danh sách"] == WB.L_RECOVER)].sort_values("Score", ascending=False)
    if "_liq" in t.columns:                  # bỏ mã thanh khoản thấp (nếu đã có số liệu)
        keep = lambda d: d[~(d["_liq"] < MIN_VALUE_BN)]
        now, wait, rec = keep(now), keep(wait), keep(rec)
    return {"now": now, "wait": wait, "recover": rec}


MIN_VALUE_BN = 2.0       # thanh khoản tối thiểu: giá trị khớp trung vị 20 phiên ≥ 2 tỷ đồng/phiên (loại mã khó mua bán)


def enrich(t: pd.DataFrame, path: str) -> pd.DataFrame:
    """Thêm cột phụ để chọn mã nổi bật: thanh khoản (tỷ đồng/phiên) và xác nhận từ bộ Phân loại trạng thái (setups.py)."""
    import setups as SU
    raw = E.clean_raw(pd.read_csv(path, dtype={"Mã": str}))
    codes = set(t["Mã"])
    liq, ext = {}, {}
    for code, g in raw[raw["Mã"].isin(codes)].groupby("Mã"):
        g = g.sort_values("Ngày")
        tail = g.tail(20)
        liq[code] = float((pd.to_numeric(tail[SU.C], errors="coerce") * pd.to_numeric(tail[SU.V], errors="coerce")).median() * 1000 / 1e9)
        try:
            p = SU.plan(g.reset_index(drop=True))
        except Exception:
            p = None
        if p:
            ext[code] = (p["state"], (p.get("macd") or {}).get("kind"), p["ext"])
    t = t.copy()
    t["_liq"] = t["Mã"].map(liq)
    t["_state"] = t["Mã"].map(lambda c: ext.get(c, (None,) * 3)[0])
    t["_macd"] = t["Mã"].map(lambda c: ext.get(c, (None,) * 3)[1])
    return t


def pick_top(d: pd.DataFrame, n: int) -> pd.DataFrame:
    """Chọn n mã tiêu biểu thay vì n mã đầu bảng: ưu tiên điểm tổng hợp cao, sức mạnh tương đối, R:R tốt, cắt lỗ không quá xa,
    được bộ Phân loại trạng thái xác nhận (bùng nổ / xu hướng tăng / MACD xác nhận), thanh khoản đủ và chưa chạy xa khỏi vùng mua."""
    if not n or len(d) <= n:
        return d
    x = d.copy()
    pr = lambda col: x[col].rank(pct=True) if col in x and x[col].notna().any() else pd.Series(0.5, index=x.index)
    rr = (pd.to_numeric(x["Lời 1 %"], errors="coerce") / pd.to_numeric(x["Cắt lỗ %"], errors="coerce").abs()).fillna(0)
    sc = 2.0 * pr("Score") + 1.0 * pr("RS20") + 1.0 * rr.rank(pct=True)
    sc += (pd.to_numeric(x["Cắt lỗ %"], errors="coerce").abs() > 9.5).map({True: -0.5, False: 0.0})
    sc += x.get("_state", pd.Series(index=x.index, dtype=object)).isin(["BOTTOM", "BASE_HL", "BREAKOUT", "TREND"]).map({True: 0.7, False: 0.0})
    sc += (x.get("_macd", pd.Series(index=x.index, dtype=object)) == "confirmed").map({True: 0.5, False: 0.0})
    sc += (x["Danh sách"] == WB.L_CONFIRMED if hasattr(WB, "L_CONFIRMED") else x["Danh sách"] == "Điểm mua đã xác nhận").map({True: 0.7, False: 0.0})
    if "Cách vùng mua %" in x:
        sc -= (pd.to_numeric(x["Cách vùng mua %"], errors="coerce").abs() > 5).map({True: 0.5, False: 0.0})
    return x.assign(_pick=sc).sort_values("_pick", ascending=False).head(n)


TITLES = {"now": "⚡ VÀO ĐƯỢC NGAY", "wait": "⏳ CHỜ MUA", "recover": "🌱 PHỤC HỒI · ĐANG CHỜ MUA"}


def build_messages(sel: dict[str, pd.DataFrame], limits: dict[str, int], meta, latest: pd.Timestamp) -> list[str]:
    foot = f"Min Trading {(latest + pd.Timedelta(days=1)):%d/%m/%Y}"
    total = sum(len(v) for v in sel.values())
    if total == 0:
        return [f"Phiên {latest:%d/%m/%Y}: chưa có cổ phiếu nào ở vùng mua."]
    head = (f"📊 <b>Trạm Tín Hiệu · vùng mua phiên {latest:%d/%m/%Y}</b>\n"
            f"Vào ngay: {len(sel['now'])} · Chờ mua: {len(sel['wait'])} · Phục hồi chờ mua: {len(sel['recover'])}")
    msgs, cur = [], head
    for key in ("now", "wait", "recover"):
        d = sel[key]
        if d.empty:
            continue
        cap = limits.get(key)
        shown = pick_top(d, cap)
        started = False
        for _, r in shown.iterrows():
            block = "<pre>" + html.escape(card_text(r, meta, foot)) + "</pre>"
            title = "" if started else f"<b>{TITLES[key]}</b>"
            piece = f"{title}\n{block}" if title else block
            if len(cur) + len(piece) + 2 > TG_LIMIT:
                msgs.append(cur)
                cur = f"<b>{TITLES[key]}{' (tiếp)' if started else ''}</b>\n{block}"
            else:
                cur = f"{cur}\n\n{piece}"
            started = True
        if cap and len(d) > cap:
            cur += f"\n… và {len(d) - cap} mã khác trong mục này"
    cur += "\n\n<i>Chỉ phục vụ nghiên cứu, không phải khuyến nghị đầu tư.</i>"
    msgs.append(cur)
    return msgs


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="chỉ in ra, không gửi")
    ap.add_argument("--max-now", type=int, default=0, help="số mã tối đa mục Vào ngay (0 = tất cả)")
    ap.add_argument("--max-wait", type=int, default=15, help="số mã tối đa mục Chờ mua (mặc định 15, 0 = tất cả)")
    ap.add_argument("--max-recover", type=int, default=10, help="số mã tối đa mục Phục hồi chờ mua (mặc định 10, 0 = tất cả)")
    ap.add_argument("--include-watch", action="store_true", help='thêm nhóm "Theo dõi thêm" vào mục Chờ mua')
    ap.add_argument("--csv", default=CSV_PATH)
    args = ap.parse_args()

    t, latest = waiting_table(args.csv)
    t = enrich(t, args.csv)
    sel = select(t, args.include_watch)
    msgs = build_messages(sel, {"now": args.max_now, "wait": args.max_wait, "recover": args.max_recover},
                          load_meta(), latest)
    if args.dry_run:
        for m in msgs:
            print(m, "\n" + "=" * 40)
        return
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN", ""), os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat:
        raise SystemExit("Thiếu TELEGRAM_BOT_TOKEN hoặc TELEGRAM_CHAT_ID (đặt trong GitHub Secrets).")
    for i, m in enumerate(msgs):
        send(token, chat, m)
        if i < len(msgs) - 1:
            time.sleep(1.2)
    print(f"Đã gửi {len(msgs)} tin nhắn.")


if __name__ == "__main__":
    main()
