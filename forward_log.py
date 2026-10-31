#!/usr/bin/env python3
"""Theo dõi tín hiệu thực (forward test): mỗi ngày ghi lại setup mới báo, rồi đo kết quả khi đủ phiên.

Khác backtest: tín hiệu được ghi tại thời điểm nó xuất hiện, bằng đúng quy tắc đang chạy trong app, nên không thể tối ưu lại sau khi đã biết kết quả.
Đây là bằng chứng đáng tin hơn backtest quá khứ; sau vài tháng so với số liệu backtest (data/setup_stats.csv) để biết setup còn hiệu quả không.

Mỗi lần chạy:
  1. Ghi tín hiệu mới của ngày dữ liệu mới nhất (hoặc các ngày chưa ghi kể từ lần chạy trước, tối đa CATCH_UP_MAX ngày).
     Lần chạy đầu tiên chỉ ghi ngày mới nhất, KHÔNG tái dựng quá khứ (đó là việc của backtest).
  2. Cập nhật kết quả của các tín hiệu cũ: giá vào (mở cửa phiên sau), lợi suất sau 20 / 40 / 60 phiên, kết quả lệnh mô phỏng
     (cùng hàm simulate() với backtest: cắt lỗ, thủng Supertrend, T+2, phí, thuế, trượt giá) và chênh lệch so với VNINDEX.
  3. Tổng hợp theo setup ra data/forward_summary.csv, kèm so sánh với backtest.

Kết quả:
  data/forward_signals.csv   mỗi dòng một tín hiệu (chỉ ghi thêm / cập nhật, không xóa)
  data/forward_summary.csv   tổng hợp theo setup  <- app đọc file này

    python forward_log.py              # ghi + cập nhật + tổng hợp
    python forward_log.py --report     # chỉ in tổng hợp
    python forward_log.py --dry-run    # in tín hiệu sẽ ghi, không ghi file
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

import backtest_setups as BT
import engine as E
import setups as SU
from telegram_alert import SKIP

CSV_PATH = "data/eod_prices.csv"
OUT_LOG, OUT_SUM = "data/forward_signals.csv", "data/forward_summary.csv"
CATCH_UP_MAX = 10                 # tối đa số ngày giao dịch ghi bù nếu bỏ lỡ vài ngày
HORIZONS = (20, 40, 60)
MIN_CLOSED = 30                   # dưới mức này thì tổng hợp ghi "chưa đủ mẫu"
KEY = ["Ngày tín hiệu", "Mã", "Setup"]
COLS = ["Ngày tín hiệu", "Mã", "Setup", "Giá đóng cửa", "Điểm vào tham chiếu", "Cắt lỗ", "Ngày vào", "Giá vào", "Trạng thái",
        "Ngày ra", "Giá ra", "Lý do thoát", "R", "Lãi %", "Giữ (phiên)",
        *[f"Lãi {h}p %" for h in HORIZONS], *[f"Vs VNI {h}p %" for h in HORIZONS], "Ghi lúc", "Cập nhật lúc"]


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def load_log() -> pd.DataFrame:
    p = Path(OUT_LOG)
    if not p.exists():
        return pd.DataFrame(columns=COLS)
    d = pd.read_csv(p, dtype={"Mã": str}, encoding="utf-8-sig")
    for c in COLS:
        if c not in d.columns:
            d[c] = np.nan
    return d[COLS]


def _vni_series(raw: pd.DataFrame) -> pd.DataFrame | None:
    v = raw[raw["Mã"].str.upper().isin(E.INDEX_CODES)]
    if v.empty:
        return None
    return v.sort_values("Ngày").drop_duplicates("Ngày").set_index("Ngày")[["Giá mở cửa", "Giá đóng cửa"]].reset_index()


def _vni_ret(vni: pd.DataFrame | None, entry_date: pd.Timestamp, h: int) -> float | None:
    """Lợi suất VNINDEX từ mở cửa ngày vào tới đóng cửa phiên thứ h (phiên vào = phiên 1)."""
    if vni is None:
        return None
    idx = vni.index[vni["Ngày"] == entry_date]
    if len(idx) == 0 or idx[0] + h - 1 >= len(vni):
        return None
    j = idx[0]
    o = vni["Giá mở cửa"].iat[j]
    o = o if pd.notna(o) and o > 0 else vni["Giá đóng cửa"].iat[j]
    return float(vni["Giá đóng cửa"].iat[j + h - 1] / o - 1) * 100


def _fill(row: dict, g: pd.DataFrame, f: pd.DataFrame, i: int, vni) -> dict:
    """Điền / cập nhật kết quả cho một tín hiệu tại nến i của mã (g, f)."""
    res = BT.simulate(g, f, i, float(row["Cắt lỗ"]))
    now = _now()
    row["Cập nhật lúc"] = now
    if res is None or res.get("entry_i") is None:
        row["Trạng thái"] = "Chờ vào"
        return row
    e = res["entry_i"]
    row["Ngày vào"] = g["Ngày"].iat[e].strftime("%Y-%m-%d")
    if res["status"] in ("khóa trần", "gap dưới cắt lỗ"):
        row["Trạng thái"] = "Không khớp: " + res["status"]
        return row
    row["Giá vào"] = res["entry"]
    row["Trạng thái"] = "Đang mở" if res["status"] == "mở" else "Đã đóng"
    row["Ngày ra"] = g["Ngày"].iat[res["exit_i"]].strftime("%Y-%m-%d") if res["status"] != "mở" else np.nan
    row["Giá ra"] = res["exit"] if res["status"] != "mở" else np.nan
    row["Lý do thoát"] = res["reason"] if res["status"] != "mở" else ""
    row["R"], row["Lãi %"], row["Giữ (phiên)"] = (res["R"], res["ret_pct"], res["hold"]) if res["status"] != "mở" else (np.nan, np.nan, res["hold"])
    cl = pd.to_numeric(g["Giá đóng cửa"], errors="coerce").to_numpy(float)
    for h in HORIZONS:
        if e + h - 1 < len(g):
            r = (cl[e + h - 1] / res["entry"] - 1) * 100
            row[f"Lãi {h}p %"] = round(float(r), 2)
            vr = _vni_ret(vni, g["Ngày"].iat[e], h)
            row[f"Vs VNI {h}p %"] = round(float(r - vr), 2) if vr is not None else np.nan
    return row


def run(path: str = CSV_PATH, dry: bool = False) -> pd.DataFrame:
    raw = BT.load_prices(path)
    vni = _vni_series(raw)
    latest = pd.Timestamp(raw["Ngày"].max())
    log = load_log()
    log["Ngày tín hiệu"] = log["Ngày tín hiệu"].astype(str).str[:10]
    # các ngày cần ghi
    all_days = sorted(raw["Ngày"].unique())
    if log.empty:
        todo = {latest}
    else:
        last = pd.Timestamp(log["Ngày tín hiệu"].max())
        todo = {pd.Timestamp(d) for d in all_days if last < pd.Timestamp(d) <= latest}
        todo = set(sorted(todo)[-CATCH_UP_MAX:]) or set()
        if last == latest:
            todo = {latest}                      # chạy lại trong ngày: bổ sung mã còn thiếu, khóa (ngày, mã, setup) chống trùng
    pending_keys = set(map(tuple, log[KEY].astype(str).to_numpy()))
    new_rows, updated = [], 0
    log_rows = log.to_dict("records")
    for code, g in raw.groupby("Mã"):
        if str(code).upper() in SKIP or str(code).upper() in E.INDEX_CODES:
            continue
        g = g.sort_values("Ngày").reset_index(drop=True)
        if len(g) < BT.WARMUP or g["Ngày"].iat[-1] < latest - pd.Timedelta(days=7):
            continue
        try:
            f = SU.features(g)
            ev = BT.signal_events(f)
        except Exception as ex:
            print(f"  bỏ {code}: {ex}", file=sys.stderr)
            continue
        date_idx = {d: k for k, d in enumerate(g["Ngày"])}
        # 1) tín hiệu mới
        for setup in BT.SETUPS:
            evset = set(int(x) for x in ev[setup])
            for d in todo:
                i = date_idx.get(d)
                if i is None or i not in evset or not BT.liquid_ok(g, i):
                    continue
                key = (d.strftime("%Y-%m-%d"), code, setup)
                if key in pending_keys:
                    continue
                ref, stop = BT.entry_reference(f, i, setup)
                row = {c: np.nan for c in COLS}
                row.update({"Ngày tín hiệu": key[0], "Mã": code, "Setup": setup, "Giá đóng cửa": float(g["Giá đóng cửa"].iat[i]),
                            "Điểm vào tham chiếu": round(ref, 3), "Cắt lỗ": round(stop, 3), "Trạng thái": "Chờ vào", "Ghi lúc": _now()})
                new_rows.append((row, g, f, i))
                pending_keys.add(key)
        # 2) cập nhật các tín hiệu cũ chưa đóng
        for idx, r in enumerate(log_rows):
            if r["Mã"] != code or str(r["Trạng thái"]).startswith("Không khớp"):
                continue
            if r["Trạng thái"] == "Đã đóng" and not any(pd.isna(r[f"Lãi {h}p %"]) for h in HORIZONS):
                continue                                  # đã đóng và đủ lợi suất 20/40/60: không cần tính lại
            i = date_idx.get(pd.Timestamp(r["Ngày tín hiệu"]))
            if i is None:
                continue
            log_rows[idx] = _fill(dict(r), g, f, i, vni)
            updated += 1
    final = list(log_rows)
    for row, g, f, i in new_rows:
        final.append(_fill(row, g, f, i, vni))
    out = pd.DataFrame(final, columns=COLS)
    out = out.drop_duplicates(KEY, keep="last").sort_values(["Ngày tín hiệu", "Setup", "Mã"]).reset_index(drop=True)
    if dry:
        print(out[out["Ghi lúc"] == out["Ghi lúc"].max()][["Ngày tín hiệu", "Mã", "Setup", "Giá đóng cửa", "Điểm vào tham chiếu", "Cắt lỗ"]].to_string(index=False)
              if not out.empty else "Không có tín hiệu.")
        return out
    Path(OUT_LOG).parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT_LOG, index=False, encoding="utf-8-sig")
    print(f"Ghi mới {len(new_rows)} tín hiệu, cập nhật {updated} dòng; tổng {len(out)} tín hiệu trong {OUT_LOG}")
    return out


def summarize(log: pd.DataFrame | None = None) -> pd.DataFrame:
    """Tổng hợp theo setup, kèm kỳ vọng từ backtest (R TB toàn kỳ và OOS) để đối chiếu."""
    log = load_log() if log is None else log
    bt = None
    if Path(BT.OUT_STATS).exists():
        bt = pd.read_csv(BT.OUT_STATS, encoding="utf-8-sig")
    rows = []
    for setup in BT.SETUPS:
        s = log[log["Setup"] == setup]
        if s.empty:
            continue
        closed = s[s["Trạng thái"] == "Đã đóng"]
        entered = s[s["Trạng thái"].isin(["Đã đóng", "Đang mở"])]
        row = {"Setup": setup, "Nhãn": BT.LABEL.get(setup, setup), "Tín hiệu": len(s), "Đã vào": len(entered), "Đã đóng": len(closed),
               "Đang mở": int((s["Trạng thái"] == "Đang mở").sum()), "Ngày đầu": s["Ngày tín hiệu"].min(), "Ngày cuối": s["Ngày tín hiệu"].max()}
        if len(closed):
            r = pd.to_numeric(closed["R"], errors="coerce")
            row.update({"Thắng %": round((r > 0).mean() * 100, 1), "R TB": round(r.mean(), 3), "Lãi TB %": round(pd.to_numeric(closed["Lãi %"]).mean(), 2)})
        for h in HORIZONS:
            x = pd.to_numeric(s[f"Lãi {h}p %"], errors="coerce").dropna()
            v = pd.to_numeric(s[f"Vs VNI {h}p %"], errors="coerce").dropna()
            row[f"Lãi {h}p % (TB)"], row[f"Vs VNI {h}p % (TB)"], row[f"N {h}p"] = (round(x.mean(), 2) if len(x) else np.nan,
                                                                               round(v.mean(), 2) if len(v) else np.nan, len(x))
        if bt is not None:
            for grp, name in (("ALL", "R backtest (toàn kỳ)"), ("OOS", "R backtest (OOS)")):
                m = bt[(bt["Setup"] == setup) & (bt["Nhóm"] == grp)]
                row[name] = float(m["R TB"].iat[0]) if len(m) else np.nan
        row["Đủ mẫu"] = len(closed) >= MIN_CLOSED
        rows.append(row)
    return pd.DataFrame(rows)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", default=CSV_PATH)
    ap.add_argument("--report", action="store_true", help="chỉ in tổng hợp")
    ap.add_argument("--dry-run", action="store_true", help="in tín hiệu sẽ ghi, không ghi file")
    a = ap.parse_args()
    if a.report:
        log = load_log()
    else:
        log = run(a.csv, a.dry_run)
        if a.dry_run:
            return
    s = summarize(log)
    if s.empty:
        print("Chưa có tín hiệu nào được ghi.")
        return
    s.to_csv(OUT_SUM, index=False, encoding="utf-8-sig")
    print(s.drop(columns=["Nhãn"]).to_string(index=False))
    if not s["Đủ mẫu"].any():
        print(f"\nChưa setup nào đủ {MIN_CLOSED} lệnh đã đóng: chưa kết luận được gì, chỉ theo dõi.")


if __name__ == "__main__":
    main()
