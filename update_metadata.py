#!/usr/bin/env python3
"""Tự động cập nhật data/stock_metadata.csv (cột: Mã, Vốn hóa TT; đơn vị: TỶ ĐỒNG).

Cách tính:  Vốn hóa = Giá đóng cửa mới nhất x Số cổ phiếu lưu hành
  - Giá đóng cửa lấy từ data/eod_prices.csv (đơn vị nghìn đồng) -> không tốn lượt gọi API mỗi ngày.
  - Số cổ phiếu lưu hành lấy từ vnstock, lưu đệm ở data/shares_outstanding.csv và chỉ hỏi lại
    sau --refresh-days ngày (mặc định 30) hoặc khi mã còn thiếu.
  - Nếu nguồn không trả được số cổ phiếu cho mã nào, bạn có thể điền tay vào data/shares_outstanding.csv
    (cột: Mã, Số CP lưu hành). Dòng điền tay sẽ không bị ghi đè nếu cột Cập nhật = "tay".

Chạy:   python update_metadata.py            (cập nhật bình thường)
        python update_metadata.py --probe VSC (xem nguồn vnstock trả về những cột nào, để chẩn đoán)
"""
from __future__ import annotations

import argparse
import os
import sys
import time

import pandas as pd

PRICES = "data/eod_prices.csv"
SHARES = "data/shares_outstanding.csv"
META = "data/stock_metadata.csv"
DATE_FMT = "%d/%m/%Y"

# Tên cột có thể chứa số cổ phiếu lưu hành, tùy phiên bản/nguồn vnstock
SHARE_KEYS = ("issue_share", "issued_share", "outstanding_share", "shares_outstanding", "share_outstanding",
              "listed_share", "listing_share", "so_cp_luu_hanh", "volume_outstanding", "sharesoutstanding")


# ------------------------------------------------------------------ LẤY SỐ CỔ PHIẾU TỪ VNSTOCK
def _first_share_value(df) -> float | None:
    """Tìm giá trị số cổ phiếu lưu hành trong DataFrame/Series/dict mà vnstock trả về."""
    if df is None:
        return None
    if isinstance(df, dict):
        df = pd.DataFrame([df])
    if isinstance(df, pd.Series):
        df = df.to_frame().T
    if not isinstance(df, pd.DataFrame) or df.empty:
        return None
    low = {str(c).strip().lower().replace(" ", "_"): c for c in df.columns}
    for key in SHARE_KEYS:
        if key in low:
            v = pd.to_numeric(df[low[key]], errors="coerce").dropna()
            if len(v) and float(v.iloc[0]) > 0:
                return float(v.iloc[0])
    return None


def _candidate_calls(sym: str):
    """Các cách gọi vnstock (thế hệ 5 rồi bản cũ). Cách nào chạy được và có số cổ phiếu thì dùng."""
    def v5_reference_company():
        from vnstock import Reference
        return Reference().company(sym).overview()

    def v5_reference_company_info():
        from vnstock import Reference
        return Reference().company(sym).info()

    def v5_reference_equity():
        from vnstock import Reference
        return Reference().equity(sym).info()

    def v5_market_equity():
        from vnstock import Market
        return Market().equity(sym).info()

    def legacy_vci():
        from vnstock import Vnstock
        return Vnstock().stock(symbol=sym, source="VCI").company.overview()

    def legacy_tcbs():
        from vnstock import Vnstock
        return Vnstock().stock(symbol=sym, source="TCBS").company.overview()

    return [v5_reference_company, v5_reference_company_info, v5_reference_equity, v5_market_equity,
            legacy_vci, legacy_tcbs]


def fetch_shares(sym: str, verbose: bool = False) -> float | None:
    for call in _candidate_calls(sym):
        try:
            df = call()
            val = _first_share_value(df)
            if verbose:
                cols = list(df.columns) if isinstance(df, pd.DataFrame) else type(df).__name__
                print(f"  [{call.__name__}] cột: {cols} -> số CP: {val}")
            if val:
                return val
        except Exception as e:  # noqa: BLE001
            if verbose:
                print(f"  [{call.__name__}] lỗi: {type(e).__name__}: {e}")
    return None


# ------------------------------------------------------------------ ĐỌC / GHI
def latest_close() -> pd.Series:
    if not os.path.exists(PRICES):
        sys.exit(f"Chưa có {PRICES}. Hãy chạy eod_fetch.py trước.")
    df = pd.read_csv(PRICES, dtype={"Mã": str})
    df["Ngày"] = pd.to_datetime(df["Ngày"], format=DATE_FMT, errors="coerce")
    df["Giá đóng cửa"] = pd.to_numeric(df["Giá đóng cửa"], errors="coerce")
    df = df.dropna(subset=["Mã", "Ngày", "Giá đóng cửa"]).sort_values(["Mã", "Ngày"])
    return df.groupby("Mã")["Giá đóng cửa"].last()


def read_shares() -> pd.DataFrame:
    cols = ["Mã", "Số CP lưu hành", "Cập nhật"]
    if not os.path.exists(SHARES):
        return pd.DataFrame(columns=cols)
    df = pd.read_csv(SHARES, dtype={"Mã": str, "Cập nhật": str})
    for c in cols:
        if c not in df:
            df[c] = None
    df["Mã"] = df["Mã"].str.upper().str.strip()
    df["Số CP lưu hành"] = pd.to_numeric(df["Số CP lưu hành"], errors="coerce")
    return df[cols].drop_duplicates("Mã", keep="last")


def needs_refresh(row, today: pd.Timestamp, days: int) -> bool:
    if pd.isna(row["Số CP lưu hành"]) or row["Số CP lưu hành"] <= 0:
        return True
    if str(row["Cập nhật"]).strip().lower() == "tay":
        return False
    d = pd.to_datetime(row["Cập nhật"], format=DATE_FMT, errors="coerce")
    return pd.isna(d) or (today - d).days >= days


# ------------------------------------------------------------------ MAIN
def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Cập nhật data/stock_metadata.csv (vốn hóa, tỷ đồng)")
    p.add_argument("--probe", default="", help="Chỉ thử 1 mã và in ra các cột nguồn trả về (chẩn đoán)")
    p.add_argument("--refresh-days", type=int, default=30, help="Hỏi lại số cổ phiếu sau từng ấy ngày")
    p.add_argument("--sleep", type=float, default=1.0, help="Giây nghỉ giữa hai mã")
    p.add_argument("--max-minutes", type=float, default=20)
    args = p.parse_args(argv)

    if args.probe:
        sym = args.probe.strip().upper()
        print(f"Thử lấy số cổ phiếu của {sym}:")
        print("Kết quả:", fetch_shares(sym, verbose=True))
        return 0

    try:
        import eod_fetch
        symbols = [s.upper() for s in eod_fetch.universe(eod_fetch.parse_args([]))]
    except Exception as e:  # noqa: BLE001
        print(f"Không lấy được rổ mã từ eod_fetch ({e}); dùng mọi mã có trong eod_prices.csv.")
        symbols = []

    close = latest_close()
    if not symbols:
        symbols = list(close.index)
    symbols = [s for s in dict.fromkeys(symbols) if s in close.index]

    today = pd.Timestamp.now(tz="Asia/Ho_Chi_Minh").tz_localize(None).normalize()
    shares = read_shares().set_index("Mã")
    for s in symbols:
        if s not in shares.index:
            shares.loc[s] = [float("nan"), None]

    todo = [s for s in symbols if needs_refresh(shares.loc[s], today, args.refresh_days)]
    print(f"Rổ {len(symbols)} mã · cần hỏi lại số cổ phiếu: {len(todo)} mã")
    t0, failed = time.time(), []
    for i, s in enumerate(todo, 1):
        if time.time() - t0 > args.max_minutes * 60:
            print("Quá thời gian, dừng; phần còn lại sẽ làm ở lần chạy sau.")
            break
        val = fetch_shares(s)
        if val:
            shares.loc[s] = [val, today.strftime(DATE_FMT)]
        else:
            failed.append(s)
            print(f"  ✗ {s}: nguồn không trả số cổ phiếu lưu hành", flush=True)
        if i % 20 == 0:
            print(f"  ... {i}/{len(todo)}", flush=True)
        time.sleep(args.sleep)

    out_shares = shares.reset_index().rename(columns={"index": "Mã"})
    out_shares = out_shares[out_shares["Số CP lưu hành"].notna() & (out_shares["Số CP lưu hành"] > 0)]
    out_shares["Số CP lưu hành"] = out_shares["Số CP lưu hành"].round(0).astype("int64")
    os.makedirs("data", exist_ok=True)
    out_shares.sort_values("Mã").to_csv(SHARES, index=False)

    # Vốn hóa (tỷ đồng) = giá (nghìn đồng) x 1000 x số CP / 1e9 = giá x số CP / 1e6
    sh = out_shares.set_index("Mã")["Số CP lưu hành"]
    rows = [(s, round(float(close[s]) * float(sh[s]) / 1e6)) for s in symbols if s in sh.index]
    if not rows:
        print("Không tính được vốn hóa cho mã nào; giữ nguyên file cũ.")
        return 1
    pd.DataFrame(rows, columns=["Mã", "Vốn hóa TT"]).sort_values("Mã").to_csv(META, index=False)
    print(f"Xong: vốn hóa {len(rows)}/{len(symbols)} mã · thiếu {len(symbols) - len(rows)} mã"
          + (f" ({', '.join(failed[:15])}{'...' if len(failed) > 15 else ''})" if failed else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
