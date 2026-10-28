#!/usr/bin/env python3
"""Quét cả thị trường theo "Phân loại trạng thái" (setups.py) và gửi Telegram.

Nhóm tin nhắn (chỉ mã đủ thanh khoản: giá trung vị 20 phiên ≥ 5, khối lượng trung vị 20 phiên ≥ 100.000):
  1. Bùng nổ mới (BOTTOM / BASE_HL / BREAKOUT báo trong 3 phiên): điểm vào, cắt lỗ, mục tiêu, nhãn sóng hồi / sóng tăng
  2. Theo dõi sớm (WATCH): giá kích hoạt, cắt lỗ
  3. MACD xác nhận (MACD cắt lên 0 khi giá trên Kijun và Supertrend tăng)

Mỗi mã là một khối riêng, ngăn cách bằng gạch ngang, gồm:
  - Trạng thái (Phân loại trạng thái) và cờ cảnh báo: đã chạy xa, giá dưới điểm vào...
  - Vùng gom · Cắt lỗ · Chốt lời lấy theo mục "Kết luận hành động" của thẻ cổ phiếu (action_summary.plan, vị thế cầm tiền mặt);
    % cắt lỗ / chốt lời tính từ giữa vùng gom
  - Dự báo nghiêng Tăng / nghiêng Giảm (khung Ngày, giống biểu đồ) kèm nhãn theo giá so với vùng gom:
    giá nằm trong vùng gom -> MUA NGAY; giá cao hơn vùng gom -> CHỜ MUA; giá dưới vùng gom -> CHƯA MUA.

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

import action_summary as AS
import engine as E
import mtf_levels as ML
import rsi_divergence as DV
import setups as SU
import waiting_buy as WB
import wyckoff as WY
from telegram_alert import SKIP, send, TG_LIMIT

CSV_PATH = "data/eod_prices.csv"
FRESH = {"BOTTOM", "BASE_HL", "BREAKOUT"}
MIN_PRICE, MIN_VOL = 5.0, 100_000
SEP = "─" * 22                      # gạch ngang phân cách giữa các mã


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
        _cl = pd.to_numeric(g[SU.C], errors="coerce")
        _chg = float((_cl.iat[-1] / _cl.iat[-2] - 1) * 100) if len(_cl) > 1 and _cl.iat[-2] > 0 else None
        rows.append({"Mã": code, "Chg %": _chg, "Trạng thái": p["state"], "Nhãn": p["label"], "Giá": p["close"], "Báo cách (phiên)": p["bars_ago"],
                     "Điểm vào": p["entry"], "Cắt lỗ": p["stop"], "Target": _tg, "R:R": _rr,
                     "Đã chạy xa (%)": None if p["ext"] is None else round(p["ext"] * 100, 1),
                     "Sóng": None if not rb else rb["kind"], "MACD": mc.get("kind"), "RSI": round(p["rsi"]),
                     "KL/TB": p.get("vr"), "Dưới điểm vào": bool(p.get("below_entry"))})
    return pd.DataFrame(rows), latest


def _f(x) -> str:
    return "–" if x is None or pd.isna(x) else f"{x:,.1f}"


def _px(x) -> str:
    return "–" if x is None or pd.isna(x) else f"{float(x):,.2f}"


def _pct(v, ref) -> str:
    return f" ({(float(v) / float(ref) - 1) * 100:+.1f}%)" if ref else ""


def _rank_fresh(d: pd.DataFrame) -> pd.DataFrame:
    """Mã tiêu biểu lên đầu: chưa chạy xa, MACD xác nhận, khối lượng bùng nổ mạnh, R:R tốt, báo càng mới càng tốt."""
    x = d.copy()
    x["_s"] = ((~x["chay"]).astype(float) * 2 - x["Dưới điểm vào"].astype(float) * 2 + (x["MACD"] == "confirmed").astype(float)
               + pd.to_numeric(x["KL/TB"], errors="coerce").rank(pct=True).fillna(0.5)
               + pd.to_numeric(x["R:R"], errors="coerce").rank(pct=True).fillna(0.5)
               - 0.2 * x["Báo cách (phiên)"].fillna(0))
    return x.sort_values("_s", ascending=False)


# ------------------------------------------------------------------ kế hoạch theo "Kết luận hành động" + dự báo
class PlanSource:
    """Dựng đúng ngữ cảnh mà thẻ cổ phiếu trong app đưa cho action_summary (bảng Chờ mua, MA, hỗ trợ - kháng cự đa khung,
    Wyckoff, phân kỳ RSI, dự báo khung Ngày), rồi lấy vùng gom / cắt lỗ / chốt lời / dự báo. Tính lười: chỉ tính cho mã được hiện trong tin."""

    def __init__(self, path: str):
        import telegram_buy_alert as TB          # dùng lại build_frames của tin Vùng mua (cùng cách dựng khung D / W / M)
        raw, self.frames = TB.build_frames(path)
        self.d = {c: g.reset_index(drop=True) for c, g in self.frames["D"].groupby("Mã")}
        self.w = {c: g for c, g in self.frames["W"].groupby("Mã")}
        self.m = {c: g for c, g in self.frames["M"].groupby("Mã")}
        try:
            mkt, _ = E.market_series(raw)
            res = E.build_screener(self.frames, mkt)
            res["Nhóm"] = ""
            wb = WB.build_waiting_buy(self.frames, res)
            self.wb = wb.drop_duplicates("Mã", keep="first").set_index("Mã").to_dict("index")
        except Exception as e:  # noqa: BLE001
            print(f"  không dựng được bảng Chờ mua, dùng mốc của kết luận hành động: {e}")
            self.wb = {}
        self._cache: dict = {}

    def get(self, code: str) -> dict:
        if code not in self._cache:
            try:
                self._cache[code] = self._build(code)
            except Exception as e:  # noqa: BLE001
                print(f"  không dựng được kế hoạch {code}: {e}")
                self._cache[code] = {}
        return self._cache[code]

    @staticmethod
    def _levels(pl: dict) -> dict:
        """Đổi kết quả action_summary.plan (vị thế cầm tiền mặt) thành {zone, stop, tp, note}.
        Vùng gom: vùng mua của bảng Chờ mua nếu có; mốc "canh mua quanh x" thì mở thành x đến x +2% (giống vùng gom ở trang Đa khung);
        hai mốc thì lấy khoảng giữa hai mốc. Chốt lời = kháng cự gần (res). Cắt lỗ phải thấp hơn vùng gom, chốt lời phải cao hơn vùng gom."""
        buy = (pl or {}).get("buy") or {}
        zone = None
        if buy.get("zone"):
            zone = (min(buy["zone"]), max(buy["zone"]))
        elif buy.get("levels"):
            lv = sorted(float(x) for x in buy["levels"])
            zone = (lv[0], lv[-1]) if len(lv) >= 2 else (lv[0], lv[0] * 1.02)
        stop, tp = (pl or {}).get("stop"), (pl or {}).get("res")
        if zone:
            stop = stop if stop is not None and stop < zone[0] else None
            tp = tp if tp is not None and tp > zone[1] else None
        wait = (pl or {}).get("wait")
        note = "" if zone else (f"chưa mua, chờ giá lấy lại {wait[0]} {wait[1]:,.2f}" if wait else "chưa có hỗ trợ rõ phía dưới giá")
        return {"zone": zone, "stop": stop, "tp": tp, "note": note}

    def _build(self, code: str) -> dict:
        d = self.d[code]
        close = float(d["Giá đóng cửa"].iat[-1])
        last = lambda col: float(d[col].iat[-1]) if col in d.columns and pd.notna(d[col].iat[-1]) else None  # noqa: E731
        try:                                               # dự báo nghiêng tăng / giảm: cùng phép tính với biểu đồ khung Ngày
            fa = E.analyze_frame(d, "D")
            lean = int(fa["dir"]) if fa["enough"] else 0
        except Exception:  # noqa: BLE001
            lean = 0
        try:
            mtf = ML.analyze_dwm_timeframe(d, self.w.get(code), self.m.get(code))["D"]
        except Exception:  # noqa: BLE001
            mtf = {"ok": False}
        try:
            wy = WY.compact(WY.analyze(d))
        except Exception:  # noqa: BLE001
            wy = None
        try:
            div = DV.analyze(self.frames, code)
        except Exception:  # noqa: BLE001
            div = []
        w = self.wb.get(code, {})
        state, reason = str(w.get("Trạng thái", "") or ""), str(w.get("Lý do", "") or "")
        in_buy = bool(state in WB.STATE_GROUP and WB.STATE_GROUP[state] in WB.BUY_GROUPS
                      and pd.notna(w.get("Vùng mua từ")) and pd.notna(w.get("Vùng mua đến")))
        ctx = dict(code=code, close=close, ma20=last("MA20"), ma50=last("MA50"), ma200=last("MA200"),
                   label=WB.status_tag(state, reason)[0] if state else "", state=state, reason=reason, lean=lean, div=div, wy=wy,
                   sup=mtf.get("sup") if mtf.get("ok") else None, res=mtf.get("res") if mtf.get("ok") else None,
                   zone=(w["Vùng mua từ"], w["Vùng mua đến"]) if in_buy else None)
        out = self._levels(AS.plan(ctx))
        out["lean"], out["close"] = lean, close
        return out


def _forecast_line(plan: dict) -> str:
    """Dòng dự báo + nhãn theo vị trí giá so với vùng gom: trong vùng = MUA NGAY, trên vùng = CHỜ MUA, dưới vùng = CHƯA MUA."""
    lean = plan.get("lean", 0)
    fc = "▲ Dự báo nghiêng Tăng" if lean > 0 else "▼ Dự báo nghiêng Giảm" if lean < 0 else "Dự báo chưa nghiêng rõ"
    z, c = plan.get("zone"), plan.get("close")
    if not z or c is None:
        return fc
    c, lo, hi = round(c, 2), round(z[0], 2), round(z[1], 2)
    tag = "<b>MUA NGAY</b>" if lo <= c <= hi else "<b>CHỜ MUA</b>" if c > hi else "<b>CHƯA MUA</b> (giá dưới vùng gom)"
    return f"{fc} → {tag}"


def _block(r, plan: dict | None) -> str:
    """Khối của một mã: tiêu đề, trạng thái, vùng gom / cắt lỗ / chốt lời, dự báo. Gạch ngang phân cách do build_messages thêm."""
    chg = "" if r.get("Chg %") is None or pd.isna(r.get("Chg %")) else f" ({r['Chg %']:+.1f}%)"
    lines = [f"<b>{html.escape(r['Mã'])}</b> · Giá {_px(r['Giá'])}{chg}"]
    tag = {"hoi": " [khả năng sóng hồi]", "tang": " [sóng tăng]", "cho": " [chờ xác nhận sóng tăng]"}.get(r["Sóng"], "")
    st = f"Trạng thái: {html.escape(r['Nhãn'])}{tag}"
    if r["Trạng thái"] == "WATCH" and pd.notna(r["Điểm vào"]):
        st += f" · chờ vượt {_px(r['Điểm vào'])}"
    if r.get("chay"):
        st += " ⚠ đã chạy xa >5%, tránh đuổi"
    if r["Dưới điểm vào"]:
        st += " ⏸ giá đang dưới điểm vào, chờ lấy lại"
    lines.append(st)
    if plan:
        z = plan.get("zone")
        ref = (z[0] + z[1]) / 2 if z else r["Giá"]
        lines.append(f"Vùng gom: {_px(z[0])} – {_px(z[1])}" if z else f"Vùng gom: chưa có ({html.escape((plan.get('note') or 'chưa đủ dữ liệu').rstrip('.'))})")
        if z and plan.get("stop") is not None:        # cắt lỗ / chốt lời chỉ có nghĩa khi có vùng gom
            lines.append(f"Cắt lỗ: {_px(plan['stop'])}{_pct(plan['stop'], ref)}")
        if z and plan.get("tp") is not None:
            lines.append(f"Chốt lời: {_px(plan['tp'])}{_pct(plan['tp'], ref)}")
        lines.append(_forecast_line(plan))
    return "\n".join(lines)


def build_messages(t: pd.DataFrame, latest: pd.Timestamp, max_each: int = 15, src: PlanSource | None = None) -> list[str]:
    head = f"<b>Phân loại trạng thái · {latest:%d/%m/%Y}</b>"
    sec = []
    fresh = t[t["Trạng thái"].isin(FRESH) & (t["Báo cách (phiên)"].fillna(99) <= 3)].copy()
    if len(fresh):
        fresh["chay"] = fresh["Đã chạy xa (%)"].fillna(0) > 5
        sec.append(("Bùng nổ mới (báo trong 3 phiên)", _rank_fresh(fresh).head(max_each), len(fresh)))
    w = t[t["Trạng thái"] == "WATCH"]
    if len(w):
        w = w.assign(_rr=pd.to_numeric(w["R:R"], errors="coerce")).sort_values("_rr", ascending=False)
        sec.append(("Theo dõi sớm (chờ vượt đỉnh vùng)", w.head(max_each), len(w)))
    m = t[t["MACD"] == "confirmed"]
    if len(m):
        sec.append(("MACD xác nhận (cắt lên 0, giá trên Kijun, Supertrend tăng)", m.head(max_each), len(m)))
    foot = ("Bộ lọc, không phải lệnh chắc thắng: thắng khoảng 1/3 số lệnh, lãi đến từ vài lệnh lớn. Chia nhỏ vốn, luôn đặt cắt lỗ.\n"
            "Vùng gom, cắt lỗ, chốt lời theo mục Kết luận hành động; % tính từ giữa vùng gom. Chỉ để tham khảo, không phải khuyến nghị đầu tư.")
    if not sec:
        return [head + "\nHôm nay không có mã nào vào nhóm cần báo.\n" + foot]
    msgs, cur = [], head
    for title, d, n in sec:
        title_html = f"<b>{title}</b> ({n} mã" + (f", hiện {len(d)}" if n > len(d) else "") + ")"
        started = False
        for _, r in d.iterrows():
            r = r.copy()
            r["chay"] = bool(r.get("chay", False)) if "chay" in r.index and pd.notna(r.get("chay")) else False
            block = _block(r, src.get(r["Mã"]) if src else None)
            piece = (("" if started else title_html + "\n") + block + "\n" + SEP)
            if len(cur) + len(piece) + 2 > TG_LIMIT:
                msgs.append(cur)
                cur = head + (f"\n\n<b>{title}</b> (tiếp)\n" + block + "\n" + SEP if started else "\n\n" + piece)
            else:
                cur += "\n\n" + piece
            started = True
    if len(cur) + len(foot) + 2 > TG_LIMIT:
        msgs.append(cur)
        cur = head
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
    src = None
    if len(t):
        try:
            src = PlanSource(a.csv)
        except Exception as e:  # noqa: BLE001
            print(f"Không dựng được kế hoạch hành động, tin sẽ không có vùng gom / dự báo: {e}")
    msgs = build_messages(t, latest, a.max_each, src)
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
