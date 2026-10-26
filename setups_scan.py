#!/usr/bin/env python3
"""Quét cả thị trường theo "Phân loại trạng thái" (setups.py) và gửi Telegram.

Nhóm tin nhắn (chỉ mã đủ thanh khoản: giá trung vị 20 phiên ≥ 5, khối lượng trung vị 20 phiên ≥ 100.000):
  1. Bùng nổ mới (BOTTOM / BASE_HL / BREAKOUT báo trong 3 phiên): điểm vào, cắt lỗ, mục tiêu, nhãn sóng hồi / sóng tăng
  2. Theo dõi sớm (WATCH): giá kích hoạt, cắt lỗ
  3. MACD xác nhận (MACD cắt lên 0 khi giá trên Kijun và Supertrend tăng)

Đây là bộ lọc, không phải lệnh chắc thắng: backtest cho thấy thắng khoảng 1/3 số lệnh, lợi nhuận đến từ vài lệnh lớn.

    python setups_scan.py --dry-run          # chỉ in ra
    python setups_scan.py                    # gửi thật (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
    python setups_scan.py --csv-out ket_qua.csv
"""
from __future__ import annotations

import argparse
import html
import os
import time

import pandas as pd

import engine as E
import setups as SU
from telegram_alert import SKIP, send, TG_LIMIT

CSV_PATH = "data/eod_prices.csv"
FRESH = {"BOTTOM", "BASE_HL", "BREAKOUT"}
MIN_PRICE, MIN_VOL = 5.0, 100_000


def scan(path: str = CSV_PATH) -> tuple[pd.DataFrame, pd.Timestamp]:
    raw = E.clean_raw(pd.read_csv(path, dtype={"Mã": str}))
    raw = raw[~raw["Mã"].isin(SKIP)]
    latest = pd.Timestamp(raw["Ngày"].max())
    rows = []
    for code, g in raw.groupby("Mã"):
        g = g.sort_values("Ngày").reset_index(drop=True)
        if g["Ngày"].iat[-1] < latest - pd.Timedelta(days=7):      # mã đã ngừng giao dịch
            continue
        tail = g.tail(20)
        if pd.to_numeric(tail[SU.C], errors="coerce").median() < MIN_PRICE or pd.to_numeric(tail[SU.V], errors="coerce").median() < MIN_VOL:
            continue
        try:
            p = SU.plan(g)
        except Exception:
            continue
        if not p:
            continue
        rb, mc = p.get("rebound"), p.get("macd") or {}
        _tgs = p.get("targets")
        _tg = _tgs["levels"][0][1] if _tgs and _tgs["levels"] else None            # mục tiêu gần nhất theo trường hợp giá / Tenkan / Kijun
        _rr = (_tg - p["entry"]) / (p["entry"] - p["stop"]) if _tg and p["entry"] and p["stop"] and p["entry"] > p["stop"] else None
        rows.append({"Mã": code, "Trạng thái": p["state"], "Nhãn": p["label"], "Giá": p["close"], "Báo cách (phiên)": p["bars_ago"],
                     "Điểm vào": p["entry"], "Cắt lỗ": p["stop"], "Target": _tg, "R:R": _rr,
                     "Đã chạy xa (%)": None if p["ext"] is None else round(p["ext"] * 100, 1),
                     "Sóng": None if not rb else rb["kind"], "MACD": mc.get("kind"), "RSI": round(p["rsi"]),
                     "KL/TB": p.get("vr"), "Dưới điểm vào": bool(p.get("below_entry"))})
    return pd.DataFrame(rows), latest


def _f(x) -> str:
    return "–" if x is None or pd.isna(x) else f"{x:,.1f}"


def _line(r) -> str:
    risk = (r["Điểm vào"] - r["Cắt lỗ"]) / r["Điểm vào"] * 100 if pd.notna(r["Điểm vào"]) and pd.notna(r["Cắt lỗ"]) else None
    s = f"<b>{html.escape(r['Mã'])}</b> giá {_f(r['Giá'])}"
    if pd.notna(r["Điểm vào"]):
        s += f" · vào {_f(r['Điểm vào'])} · cắt lỗ {_f(r['Cắt lỗ'])}" + (f" (−{risk:.1f}%)" if risk else "")
    if pd.notna(r["Target"]):
        s += f" · Target: {_f(r['Target'])} ({(r['Target'] / r['Giá'] - 1) * 100:+.1f}%)"
        if pd.notna(r["R:R"]):
            s += f" · R:R 1:{r['R:R']:.1f}"
    tag = {"hoi": " [khả năng sóng hồi]", "tang": " [sóng tăng]", "cho": " [chờ xác nhận sóng tăng]"}.get(r["Sóng"], "")
    return s + tag


def _rank_fresh(d: pd.DataFrame) -> pd.DataFrame:
    """Mã tiêu biểu lên đầu: chưa chạy xa, MACD xác nhận, khối lượng bùng nổ mạnh, R:R tốt, báo càng mới càng tốt."""
    x = d.copy()
    x["_s"] = ((~x["chay"]).astype(float) * 2 - x["Dưới điểm vào"].astype(float) * 2 + (x["MACD"] == "confirmed").astype(float)
               + pd.to_numeric(x["KL/TB"], errors="coerce").rank(pct=True).fillna(0.5)
               + pd.to_numeric(x["R:R"], errors="coerce").rank(pct=True).fillna(0.5)
               - 0.2 * x["Báo cách (phiên)"].fillna(0))
    return x.sort_values("_s", ascending=False)


def build_messages(t: pd.DataFrame, latest: pd.Timestamp, max_each: int = 15) -> list[str]:
    head = f"<b>Phân loại trạng thái · {latest:%d/%m/%Y}</b>"
    sec = []
    fresh = t[t["Trạng thái"].isin(FRESH) & (t["Báo cách (phiên)"].fillna(99) <= 3)].copy()
    if len(fresh):
        fresh["chay"] = fresh["Đã chạy xa (%)"].fillna(0) > 5
        sec.append(("Bùng nổ mới (báo trong 3 phiên)", [_line(r) + (" ⚠ đã chạy xa >5%, tránh đuổi" if r["chay"] else "") + (" ⏸ giá đang dưới điểm vào, chờ lấy lại" if r["Dưới điểm vào"] else "")
                                                       for _, r in _rank_fresh(fresh).head(max_each).iterrows()], len(fresh)))
    w = t[t["Trạng thái"] == "WATCH"]
    if len(w):
        w = w.assign(_rr=pd.to_numeric(w["R:R"], errors="coerce")).sort_values("_rr", ascending=False)
        sec.append(("Theo dõi sớm (chờ vượt đỉnh vùng)", [_line(r) for _, r in w.head(max_each).iterrows()], len(w)))
    m = t[t["MACD"] == "confirmed"]
    if len(m):
        sec.append(("MACD xác nhận (cắt lên 0, giá trên Kijun, Supertrend tăng)",
                    [f"<b>{html.escape(r['Mã'])}</b> giá {_f(r['Giá'])} · trạng thái: {html.escape(r['Nhãn'])}" for _, r in m.head(max_each).iterrows()], len(m)))
    foot = "Bộ lọc, không phải lệnh chắc thắng: thắng khoảng 1/3 số lệnh, lãi đến từ vài lệnh lớn. Chia nhỏ vốn, luôn đặt cắt lỗ."
    if not sec:
        return [head + "\nHôm nay không có mã nào vào nhóm cần báo.\n" + foot]
    msgs, cur = [], head
    for title, lines, n in sec:
        block = f"\n\n<b>{title}</b> ({n} mã" + (f", hiện {len(lines)}" if n > len(lines) else "") + ")\n" + "\n".join(lines)
        if len(cur) + len(block) > TG_LIMIT:
            msgs.append(cur)
            cur = head
        cur += block
    msgs.append(cur + "\n\n" + foot)
    return msgs


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--csv", default=CSV_PATH)
    ap.add_argument("--csv-out", default="")
    ap.add_argument("--max-each", type=int, default=15)
    a = ap.parse_args()
    t, latest = scan(a.csv)
    if a.csv_out:
        t.to_csv(a.csv_out, index=False, encoding="utf-8-sig")
    msgs = build_messages(t, latest, a.max_each)
    if a.dry_run:
        for m in msgs:
            print(m, "\n" + "=" * 40)
        return
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN", ""), os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat:
        raise SystemExit("Thiếu TELEGRAM_BOT_TOKEN hoặc TELEGRAM_CHAT_ID.")
    for i, m in enumerate(msgs):
        send(token, chat, m)
        if i < len(msgs) - 1:
            time.sleep(1.2)
    print(f"Đã gửi {len(msgs)} tin nhắn.")


if __name__ == "__main__":
    main()
