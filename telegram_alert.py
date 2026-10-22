#!/usr/bin/env python3
"""Gửi Telegram danh sách cổ phiếu "DỰ BÁO NGHIÊNG TĂNG" và "DỰ BÁO NGHIÊNG GIẢM" sau mỗi phiên.

Cùng phép tính với dòng dự báo trên thẻ và trang Biểu đồ: khung Ngày, engine.analyze_frame,
độ nghiêng = tổng điểm đa chỉ báo; >= +1.0 là nghiêng tăng, <= -1.0 là nghiêng giảm.
Không dùng Streamlit nên chạy được trên GitHub Actions ngay sau bước cập nhật dữ liệu cuối phiên.

Biến môi trường (đặt trong GitHub: Settings > Secrets and variables > Actions):
    TELEGRAM_BOT_TOKEN   token do @BotFather cấp
    TELEGRAM_CHAT_ID     id người nhận / nhóm / kênh (nhóm và kênh thường bắt đầu bằng -100)

Cách chạy:
    python telegram_alert.py --dry-run          # chỉ in tin nhắn ra màn hình, không gửi
    python telegram_alert.py                    # gửi thật
    python telegram_alert.py --top 25           # mỗi nhóm tối đa 25 mã (mặc định 30)
    python telegram_alert.py --only HPG,FPT     # chỉ xét các mã này
"""
from __future__ import annotations

import argparse
import html
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

import pandas as pd

import engine as E

CSV_PATH = "data/eod_prices.csv"
SKIP = {"VNINDEX", "VN30", "HNXINDEX", "UPCOMINDEX"}      # chỉ số, không phải cổ phiếu
TG_LIMIT = 4000                                           # Telegram cho tối đa 4096 ký tự / tin nhắn


def load_daily(path: str) -> pd.DataFrame:
    raw = E.clean_raw(pd.read_csv(path, dtype={"Mã": str}))
    parts = []
    for code, g in raw.groupby("Mã"):
        if code in SKIP:
            continue
        base = g[["Mã", "Ngày"] + E.NUMERIC_COLS]
        parts.append(E.add_indicators(E.resample_ohlcv(base, "D")))
    d = pd.concat(parts, ignore_index=True)
    return E.mask_chg_gaps(d)


def scan(daily: pd.DataFrame, only: set[str] | None) -> pd.DataFrame:
    rows = []
    for code, g in daily.groupby("Mã"):
        if only and code.upper() not in only:
            continue
        try:
            a = E.analyze_frame(g, "D")
        except Exception as e:
            print(f"  bỏ qua {code}: {e}", file=sys.stderr)
            continue
        if not a.get("enough") or a.get("dir", 0) == 0:
            continue
        last = a["g"]
        close = float(last["Giá đóng cửa"].iat[-1])
        chg = last["Chg_%"].iat[-1] if "Chg_%" in last.columns else float("nan")
        rows.append({"Mã": code, "Giá": close, "Chg": float(chg) if pd.notna(chg) else float("nan"),
                     "Điểm": a["total"], "Hướng": a["dir"], "Ngày": last["Ngày"].iat[-1]})
    return pd.DataFrame(rows)


def _line(r) -> str:
    chg = "" if pd.isna(r["Chg"]) else f" ({r['Chg']:+.2f}%)"
    return f"<b>{html.escape(r['Mã'])}</b> {r['Giá']:,.2f}{chg} · điểm {r['Điểm']:+.1f}"


def build_messages(res: pd.DataFrame, top: int) -> list[str]:
    if res.empty:
        return ["Không có cổ phiếu nào nghiêng tăng / nghiêng giảm ở phiên này."]
    date = pd.Timestamp(res["Ngày"].max())
    up = res[res["Hướng"] > 0].sort_values("Điểm", ascending=False)
    dn = res[res["Hướng"] < 0].sort_values("Điểm", ascending=True)
    head = f"📊 <b>Trạm Tín Hiệu · phiên {date:%d/%m/%Y}</b>\n▲ Nghiêng tăng: {len(up)} mã · ▼ Nghiêng giảm: {len(dn)} mã"
    blocks = [head]
    for title, d in (("▲ DỰ BÁO NGHIÊNG TĂNG", up), ("▼ DỰ BÁO NGHIÊNG GIẢM", dn)):
        if d.empty:
            continue
        lines = [_line(r) for _, r in d.head(top).iterrows()]
        more = len(d) - len(lines)
        if more > 0:
            lines.append(f"… và {more} mã khác")
        blocks.append(f"<b>{title}</b>\n" + "\n".join(lines))
    blocks.append("<i>Chỉ phục vụ nghiên cứu, không phải khuyến nghị đầu tư.</i>")
    # gói các khối vào tin nhắn, không vượt giới hạn ký tự của Telegram
    msgs, cur = [], ""
    for b in blocks:
        if cur and len(cur) + len(b) + 2 > TG_LIMIT:
            msgs.append(cur)
            cur = ""
        cur = f"{cur}\n\n{b}" if cur else b
    if cur:
        msgs.append(cur)
    return msgs


def send(token: str, chat_id: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": text, "parse_mode": "HTML",
                                   "disable_web_page_preview": "true"}).encode()
    for attempt in range(1, 4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=30) as resp:
                body = json.loads(resp.read().decode())
                if not body.get("ok"):
                    raise RuntimeError(body)
                return
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")
            if e.code == 429 and attempt < 3:      # gửi quá nhanh: chờ theo yêu cầu của Telegram
                try:
                    wait = json.loads(detail)["parameters"]["retry_after"]
                except Exception:
                    wait = 5
                time.sleep(wait + 1)
                continue
            raise SystemExit(f"Telegram trả lỗi {e.code}: {detail}")
        except Exception as e:
            if attempt == 3:
                raise SystemExit(f"Không gửi được Telegram: {e}")
            time.sleep(3 * attempt)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="chỉ in ra, không gửi")
    ap.add_argument("--top", type=int, default=30, help="số mã tối đa mỗi nhóm (mặc định 30)")
    ap.add_argument("--only", default="", help="chỉ xét các mã này, ngăn cách bằng dấu phẩy")
    ap.add_argument("--csv", default=CSV_PATH)
    args = ap.parse_args()

    only = {c.strip().upper() for c in args.only.split(",") if c.strip()} or None
    res = scan(load_daily(args.csv), only)
    msgs = build_messages(res, args.top)

    if args.dry_run:
        for m in msgs:
            print(m, "\n" + "-" * 40)
        return
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN", ""), os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat:
        raise SystemExit("Thiếu TELEGRAM_BOT_TOKEN hoặc TELEGRAM_CHAT_ID (đặt trong GitHub Secrets).")
    for i, m in enumerate(msgs):
        send(token, chat, m)
        if i < len(msgs) - 1:
            time.sleep(1.2)
    print(f"Đã gửi {len(msgs)} tin nhắn ({len(res)} mã).")


if __name__ == "__main__":
    main()
