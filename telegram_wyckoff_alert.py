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
    python telegram_wyckoff_alert.py --max 30          # số mã tối đa mỗi mục (mặc định 20, 0 = tất cả)
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

import engine as E
import wyckoff as WY
from telegram_alert import SKIP, TG_LIMIT, send
from telegram_supertrend_alert import HOLD_PATH, WATCH_PATH, _codes, now_vn, stamp

CSV_PATH = "data/eod_prices.csv"
STATE_PATH = "data/wy_alert_state.json"
MIN_VALUE_BN = 2.0            # bỏ mã có giá trị khớp trung vị 20 phiên dưới 2 tỷ đồng
MIN_BARS = WY.MIN_BARS
ORDER = {"acc": ["C", "D", "E", "B", "A"], "dist": ["D", "E", "C", "B", "A"]}
PHASE_NOTE = {
    "acc": {"A": "dừng đà giảm", "B": "xây nền, chỉ quan sát", "C": "Spring, thử cung cuối",
            "D": "SOS, cầu thắng thế", "E": "đã rời vùng, markup"},
    "dist": {"A": "chặn đà tăng", "B": "xây nền, chỉ quan sát", "C": "Upthrust, thử cầu cuối",
             "D": "SOW, thủng biên dưới", "E": "đã rời vùng, markdown"},
}


# ------------------------------------------------------------------ dữ liệu
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


def _sorted(d: pd.DataFrame, kind: str, held: set[str], watch: set[str]) -> pd.DataFrame:
    d = d[d["Loại"] == kind].copy()
    d["_p"] = d["Mã"].map(lambda c: 0 if c in held else 1 if c in watch else 2)
    d["_o"] = d["Pha"].map({p: i for i, p in enumerate(ORDER[kind])})
    return d.sort_values(["_p", "_o", "Khớp"], ascending=[True, True, False])


def build_messages(show: pd.DataFrame, totals: dict, latest: pd.Timestamp, held: set[str], watch: set[str], cap: int,
                   mode_txt: str, sent_at: datetime | None = None) -> list[str]:
    head = (f"🏗 <b>Wyckoff · cấu trúc khung Ngày cuối phiên {latest:%d/%m/%Y}</b>\n"
            f"Đang tích lũy: {totals['acc']} mã · Đang phân phối: {totals['dist']} mã\n"
            f"{mode_txt}\n"
            f"🕖 Gửi lúc {stamp(sent_at)}")
    foot = ("<i>Wyckoff do máy dò theo giá và volume nên mang tính chủ quan. Pha A/B chỉ để quan sát; "
            "chỉ phục vụ nghiên cứu, không phải khuyến nghị đầu tư.</i>")
    blocks = [head]
    for kind, title in (("acc", "🟢 TÍCH LŨY"), ("dist", "🔴 CẢNH BÁO PHÂN PHỐI")):
        d = _sorted(show, kind, held, watch)
        if d.empty:
            continue
        shown = d.head(cap) if cap else d
        body = "\n\n".join(_block(r, held, watch) for _, r in shown.iterrows())
        more = f"\n… và {len(d) - len(shown)} mã khác" if len(d) > len(shown) else ""
        blocks.append(f"<b>{title} ({len(d)} mã)</b>\n<pre>{body}</pre>{more}")
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
    ap.add_argument("--all", action="store_true", help="gửi toàn bộ danh sách hiện tại, không chỉ mã mới / đổi pha")
    ap.add_argument("--only", default="", help="chỉ xét các mã này, ngăn cách bằng dấu phẩy")
    ap.add_argument("--max", type=int, default=20, help="số mã tối đa mỗi mục (mặc định 20, 0 = tất cả)")
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
    msgs = build_messages(show, totals, latest, held, watch, args.max, mode_txt)
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
    save_state({r["Mã"]: sig_of(r) for _, r in res.iterrows()}, latest)
    print(f"Đã gửi {len(msgs)} tin nhắn ({int((show['Loại'] == 'acc').sum())} tích lũy, {int((show['Loại'] == 'dist').sum())} phân phối).")


if __name__ == "__main__":
    main()
