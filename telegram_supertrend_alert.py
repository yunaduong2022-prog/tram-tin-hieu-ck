#!/usr/bin/env python3
"""Gửi Telegram ĐIỂM BÁN theo Supertrend (ATR 10, hệ số 3.0) sau mỗi phiên. (Mặc định chỉ báo BÁN; thêm --include-buy để báo cả điểm mua.)

Dùng đúng supertrend.compute() như biểu đồ trong app (tính trên toàn bộ lịch sử rồi mới lấy nến cuối), nên nhãn
"Buy / Sell" trên biểu đồ và tin nhắn luôn trùng nhau. Tín hiệu chỉ phát ở nến Supertrend ĐẢO CHIỀU:
    Buy  = xu hướng đảo sang tăng (đóng cửa vượt đường dn phía trên)  -> điểm mua, đường Supertrend là mức cắt lỗ tham khảo (chỉ gửi khi bật --include-buy)
    Sell = xu hướng đảo sang giảm (đóng cửa thủng đường up phía dưới) -> điểm bán / thoát

Tín hiệu xác nhận khi đóng cửa nên chỉ vào lệnh được từ phiên kế tiếp. Giá trong tin nhắn là giá đóng cửa nến báo (tham chiếu).
Mã đang nắm giữ trong data/co_phieu_cua_toi.csv (nếu có) được đánh dấu 📌 và xếp lên đầu.

Biến môi trường: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID (giống telegram_alert.py).

Cách chạy:
    python telegram_supertrend_alert.py --dry-run         # chỉ in ra, không gửi
    python telegram_supertrend_alert.py                   # gửi thật (chỉ các tín hiệu CHƯA gửi của phiên mới nhất)
    python telegram_supertrend_alert.py --days 2          # gồm cả tín hiệu của 2 phiên gần nhất
    python telegram_supertrend_alert.py --only HPG,FPT    # chỉ xét các mã này
    python telegram_supertrend_alert.py --force           # gửi lại dù đã gửi rồi
    python telegram_supertrend_alert.py --include-buy     # báo cả điểm mua (mặc định chỉ báo điểm bán)
"""
from __future__ import annotations

import argparse
import html
import json
import os
import time
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

import engine as E
import supertrend as ST
from telegram_alert import SKIP, TG_LIMIT, send

CSV_PATH = "data/eod_prices.csv"
STATE_PATH = "data/st_alert_state.json"        # nhớ tín hiệu đã gửi để chạy lại không bị gửi trùng
HOLD_PATH = "data/co_phieu_cua_toi.csv"        # danh mục đang nắm giữ (tùy chọn)
WATCH_PATH = "data/watchlist_cua_toi.csv"      # watchlist (tùy chọn)
MIN_VALUE_BN = 2.0                             # bỏ mã có giá trị khớp trung vị 20 phiên dưới 2 tỷ đồng (khó mua bán)
MIN_BARS = 60
WIDE_STOP = 10.0                               # cắt lỗ Supertrend xa hơn mức này (% giá) thì gắn cảnh báo để giảm khối lượng


# ------------------------------------------------------------------ dữ liệu
def _codes(path: str) -> set[str]:
    try:
        d = pd.read_csv(path, dtype={"Mã": str}, encoding="utf-8-sig")
        return {c.strip().upper() for c in d["Mã"].dropna()}
    except Exception:  # noqa: BLE001
        return set()


def scan(path: str, only: set[str] | None, days: int, min_value: float,
         include_buy: bool = False) -> tuple[pd.DataFrame, pd.Timestamp]:
    """Trả (bảng tín hiệu, ngày dữ liệu mới nhất). Mỗi dòng là một tín hiệu Sell (và Buy nếu include_buy) trong `days` phiên gần nhất."""
    raw = E.clean_raw(pd.read_csv(path, dtype={"Mã": str}))
    raw = raw[~raw["Mã"].isin(SKIP)]
    latest = pd.Timestamp(raw["Ngày"].max())
    rows = []
    for code, g in raw.groupby("Mã"):
        if only and code.upper() not in only:
            continue
        g = g.sort_values("Ngày").reset_index(drop=True)
        if len(g) < MIN_BARS or pd.Timestamp(g["Ngày"].iat[-1]) != latest:   # bỏ mã dữ liệu cũ / tạm ngừng giao dịch
            continue
        st = ST.compute(g)
        c = g[ST.C].astype(float).to_numpy()
        v = g["Khối lượng khớp lệnh"].astype(float).to_numpy()
        liq = float(np.median(c[-20:] * v[-20:]) * 1000 / 1e9)
        if liq < min_value:
            continue
        ma50 = pd.Series(c).rolling(50).mean().to_numpy()
        n = len(g)
        for k in range(1, days + 1):
            i = n - k
            for side, flag, line_col in (("buy", "ST_buy", "ST_up"), ("sell", "ST_sell", "ST_dn")):
                if side == "buy" and not include_buy:
                    continue
                if not bool(st[flag].iat[i]):
                    continue
                line = float(st[line_col].iat[i])
                vol_ma = np.nanmean(v[max(0, i - 20):i]) if i > 0 else np.nan
                rows.append({"Mã": code, "Hướng": side, "Ngày": pd.Timestamp(g["Ngày"].iat[i]), "Trước": k - 1,
                             "Giá": float(c[i]), "Chg": (c[i] / c[i - 1] - 1) * 100 if i > 0 else np.nan,
                             "ST": line, "Cách ST": (c[i] / line - 1) * 100,
                             "KL": v[i] / vol_ma if vol_ma and vol_ma > 0 else np.nan, "GTGD": liq,
                             "MA50": (c[i] > ma50[i]) if np.isfinite(ma50[i]) else None})
    return pd.DataFrame(rows), latest


# ------------------------------------------------------------------ trạng thái đã gửi
def load_state(path: str = STATE_PATH) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return {}


def save_state(sent: set[str], latest: pd.Timestamp, path: str = STATE_PATH) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    cut = f"{latest - pd.Timedelta(days=20):%Y-%m-%d}"               # chỉ nhớ 20 ngày gần nhất để file không phình ra
    keep = sorted(k for k in sent if k.rsplit("|", 1)[-1] >= cut)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"latest": f"{latest:%Y-%m-%d}", "sent": keep}, f, ensure_ascii=False, indent=1)


def key(r) -> str:
    return f"{r['Mã']}|{r['Hướng']}|{pd.Timestamp(r['Ngày']):%Y-%m-%d}"


# ------------------------------------------------------------------ định dạng
def now_vn() -> datetime:
    """Giờ Việt Nam (UTC+7), kể cả khi chạy trên máy GitHub (UTC) hoặc Windows thiếu dữ liệu múi giờ."""
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))
    except Exception:  # noqa: BLE001
        return datetime.now(timezone(timedelta(hours=7)))


def stamp(t: datetime | None = None) -> str:
    """Giờ gửi tin, ví dụ "7:00PM | 26/10/2026"."""
    t = t or now_vn()
    return f"{int(t.strftime('%I'))}:{t.minute:02d}{t.strftime('%p').upper()} | {t:%d/%m/%Y}"


def _block(r, held: set[str], watch: set[str]) -> str:
    mark = "📌 " if r["Mã"] in held else ("👁 " if r["Mã"] in watch else "")
    chg = "" if pd.isna(r["Chg"]) else f" ({r['Chg']:+.1f}%)"
    ago = f"  [{r['Trước']} phiên trước]" if r["Trước"] else ""
    head = f"{mark}{r['Mã']}  Giá {r['Giá']:,.1f}{chg}{ago}"
    if r["Hướng"] == "buy":
        risk = (1 - r["ST"] / r["Giá"]) * 100
        l2 = f"  Cắt lỗ ST {r['ST']:,.1f} (cách giá {risk:.1f}%)" + ("  ⚠ cắt lỗ xa" if risk > WIDE_STOP else "")
    else:
        l2 = f"  Đường ST {r['ST']:,.1f} (trên giá {(r['ST'] / r['Giá'] - 1) * 100:.1f}%)"
    ctx = []
    if pd.notna(r["KL"]):
        ctx.append(f"KL {r['KL']:.1f}x TB20")
    ctx.append(f"GTGD {r['GTGD']:,.0f} tỷ")
    if r["MA50"] is not None and not pd.isna(r["MA50"]):
        ctx.append("trên MA50" if r["MA50"] else "dưới MA50")
    return html.escape(f"{head}\n{l2}\n  " + " · ".join(ctx))


def build_messages(sig: pd.DataFrame, latest: pd.Timestamp, held: set[str], watch: set[str], cap: int,
                   total: tuple[int, int] | None = None, sent_at: datetime | None = None,
                   include_buy: bool = False) -> list[str]:
    nb, ns = (int((sig["Hướng"] == "buy").sum()), int((sig["Hướng"] == "sell").sum())) if total is None else total
    counts = f"Điểm bán: {ns}" + (f" · Điểm mua: {nb}" if include_buy else "")
    head = (f"📈 <b>Supertrend (10, 3) · theo nến cuối phiên {latest:%d/%m/%Y}</b>\n"
            f"{counts}\n"
            f"🕖 Gửi lúc {stamp(sent_at)}")
    foot = ((f"Vào lệnh được từ phiên {(latest + pd.Timedelta(days=1)):%d/%m/%Y} (tín hiệu xác nhận khi đóng cửa).\n" if include_buy
             else "Tín hiệu xác nhận khi đóng cửa; giá trong tin là giá đóng cửa nến báo (tham chiếu).\n")
            + "<i>Supertrend hay nhiễu khi giá đi ngang; chỉ phục vụ nghiên cứu, không phải khuyến nghị đầu tư.</i>")
    blocks = [head]
    sections = [("sell", "🔴 ĐIỂM BÁN · xu hướng đảo sang giảm")] + ([("buy", "🟢 ĐIỂM MUA · xu hướng đảo sang tăng")] if include_buy else [])
    for side, title in sections:
        d = sig[sig["Hướng"] == side].copy()
        if d.empty:
            continue
        d["_p"] = d["Mã"].map(lambda c: 0 if c in held else 1 if c in watch else 2)
        d = d.sort_values(["Trước", "_p", "KL"], ascending=[True, True, False])
        shown = d.head(cap) if cap else d
        body = "\n\n".join(_block(r, held, watch) for _, r in shown.iterrows())
        more = f"\n… và {len(d) - len(shown)} mã khác" if len(d) > len(shown) else ""
        blocks.append(f"<b>{title}</b>\n<pre>{body}</pre>{more}")
    blocks.append(foot)
    msgs, cur = [], ""
    for b in blocks:
        if cur and len(cur) + len(b) + 2 > TG_LIMIT:
            msgs.append(cur)
            cur = ""
        cur = f"{cur}\n\n{b}" if cur else b
    if cur:
        msgs.append(cur)
    return msgs


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="chỉ in ra, không gửi và không ghi trạng thái")
    ap.add_argument("--days", type=int, default=1, help="lấy tín hiệu của N phiên gần nhất (mặc định 1 = chỉ phiên mới nhất)")
    ap.add_argument("--only", default="", help="chỉ xét các mã này, ngăn cách bằng dấu phẩy")
    ap.add_argument("--max", type=int, default=25, help="số mã tối đa mỗi mục (mặc định 25, 0 = tất cả)")
    ap.add_argument("--min-value", type=float, default=MIN_VALUE_BN, help="giá trị khớp trung vị 20 phiên tối thiểu, tỷ đồng (mặc định 2)")
    ap.add_argument("--force", action="store_true", help="gửi lại cả tín hiệu đã gửi")
    ap.add_argument("--include-buy", action="store_true", help="báo cả điểm mua (mặc định chỉ báo điểm bán)")
    ap.add_argument("--csv", default=CSV_PATH)
    args = ap.parse_args()

    only = {c.strip().upper() for c in args.only.split(",") if c.strip()} or None
    sig, latest = scan(args.csv, only, max(1, args.days), args.min_value, args.include_buy)
    held, watch = _codes(HOLD_PATH), _codes(WATCH_PATH)
    state = load_state()
    done = set(state.get("sent", [])) if not args.force else set()
    if len(sig):
        sig = sig[~sig.apply(key, axis=1).isin(done)]
    if sig.empty:
        print(f"Phiên {latest:%d/%m/%Y}: không có tín hiệu Supertrend {'mới ' if args.include_buy else 'bán mới '}để gửi.")
        return
    msgs = build_messages(sig, latest, held, watch, args.max, include_buy=args.include_buy)
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
    save_state(set(state.get("sent", [])) | set(sig.apply(key, axis=1)), latest)
    print(f"Đã gửi {len(msgs)} tin nhắn ({int((sig['Hướng'] == 'buy').sum())} mua, {int((sig['Hướng'] == 'sell').sum())} bán).")


if __name__ == "__main__":
    main()
