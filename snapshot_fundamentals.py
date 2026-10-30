#!/usr/bin/env python3
"""Chụp lại dữ liệu cơ bản của mọi mã mỗi tháng vào data/fundamentals_history.csv, để sau này có dữ liệu THEO THỜI ĐIỂM kiểm chứng điểm FA.

Vì sao cần: app chỉ giữ P/E, P/B, ROE của hôm nay. Muốn biết điểm cơ bản có dự báo được lợi nhuận hay không phải có số của đúng thời điểm đó,
nếu không sẽ bị nhìn trước tương lai. Sau khoảng 12-24 tháng chụp đều là có thể backtest.

Mỗi lần chạy ghi một "ảnh chụp" gồm số liệu đã gộp đúng như app dùng (fundamentals.csv + bảng xếp hạng ngành + số nhập tay) cùng điểm FA tại thời điểm đó.
Mặc định mỗi tháng chỉ chụp một lần (đã có tháng này thì bỏ qua); --force để chụp lại và thay ảnh của tháng.
Cách chạy:  python snapshot_fundamentals.py [--force] [--out data/fundamentals_history.csv]
Chỉ cần pandas, numpy (không cần streamlit).
"""
from __future__ import annotations

import argparse
import os
from datetime import date

import pandas as pd

import telegram_vip_alert as TG      # dùng lại cách gộp dữ liệu cơ bản của app (tự dùng streamlit giả nếu máy chưa cài)
import vip_picks as VP

KEYS = ["P/E", "P/B", "ROE", "ROA", "NIM", "EPS", "Tăng trưởng LNST", "Margin/VCSH"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/fundamentals_history.csv")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    month = date.today().strftime("%Y-%m")
    old = pd.read_csv(a.out, dtype={"Mã": str}, encoding="utf-8-sig") if os.path.exists(a.out) else None
    if old is not None and (old["Tháng"] == month).any():
        if not a.force:
            print(f"Đã có ảnh chụp tháng {month}, bỏ qua (dùng --force để chụp lại).")
            return
        old = old[old["Tháng"] != month]
    fund = TG.load_fund_map()
    rows = []
    for code in sorted(fund):
        fd = fund[code] or {}
        fa, _ = VP.fa_score_fd(fd)
        r = {"Tháng": month, "Ngày chụp": date.today().isoformat(), "Mã": code}
        r.update({k: fd.get(k) for k in KEYS})
        r["Ngành FA"] = fd.get("FA ngành")
        r["Điểm FA"] = fa
        if any(r[k] is not None for k in KEYS):
            rows.append(r)
    new = pd.DataFrame(rows)
    out = pd.concat([old, new], ignore_index=True) if old is not None else new
    out.to_csv(a.out, index=False, encoding="utf-8-sig")
    print(f"Đã chụp {len(new)} mã cho tháng {month} -> {a.out} (tổng {len(out)} dòng, {out['Tháng'].nunique()} tháng)")


if __name__ == "__main__":
    main()
