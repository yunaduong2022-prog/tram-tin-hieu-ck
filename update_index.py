#!/usr/bin/env python3
"""Lấy dữ liệu OHLCV cuối phiên của các CHỈ SỐ NHÓM VỐN HÓA (VN30, VNMidcap, VNSmallcap, VN100),
ghi vào data/index_prices.csv (cập nhật tăng dần).

Vì sao ghi ra file riêng mà không gộp vào data/eod_prices.csv:
các bộ lọc cổ phiếu của app (Mua ngay, Chờ mua, Tăng mạnh...) đọc toàn bộ mã trong eod_prices.csv và coi
mỗi mã là một cổ phiếu. Đưa VN30/VNMidcap/VNSmallcap vào đó sẽ làm chúng lọt vào các bảng cổ phiếu.
File riêng giữ nguyên mọi bộ lọc hiện có.

Dùng lại hàm lấy dữ liệu của eod_fetch.py (cùng nguồn vnstock, cùng cách xử lý giới hạn tần suất).
Mỗi chỉ số thử lần lượt vài tên gọi (alias) vì mỗi nguồn đặt tên một kiểu, ví dụ VNMIDCAP / VNMidCap.
Ngoài 4 chỉ số, script còn lấy giá các cổ phiếu trong danh sách data/nhom_von_hoa.csv (VNMidcap, VNSmallcap)
mà data/eod_prices.csv chưa có, ghi vào data/nhom_von_hoa_gia.csv. Cũng ghi riêng vì cùng lý do trên: các mã này
không được lọt vào bộ lọc Mua ngay / Chờ mua. Chỉ lấy khoảng 400 ngày gần nhất (đủ để xếp hạng), tắt bằng --no-members.

Chạy:  python update_index.py            (cập nhật tăng dần)
       python update_index.py --full     (tải lại toàn bộ lịch sử)
"""
from __future__ import annotations

import argparse
import os
import sys
import time

import pandas as pd

import eod_fetch as EF

CSV_PATH = "data/index_prices.csv"
MEMBERS_LIST = "data/nhom_von_hoa.csv"          # danh sách thành viên nhóm (Mã, Nhóm): tự lập, cập nhật tay mỗi kỳ cơ cấu
MEMBERS_CSV = "data/nhom_von_hoa_gia.csv"       # giá các mã thành viên chưa có trong eod_prices.csv
MEMBER_GROUPS = ("VNMIDCAP", "VNSMALLCAP")
EOD_PRICES = "data/eod_prices.csv"
# mã chuẩn lưu trong file -> các tên gọi thử lần lượt ở nguồn dữ liệu
TARGETS = {
    "VN30": ["VN30"],
    "VNMIDCAP": ["VNMIDCAP", "VNMidCap", "VNMID"],
    "VNSMALLCAP": ["VNSMALLCAP", "VNSmallCap", "VNSML", "VNSMALL"],
    "VN100": ["VN100"],
}
for _aliases in TARGETS.values():                 # chỉ số: giữ nguyên điểm số, không chia 1000 như giá cổ phiếu
    EF.INDEX_SYMS.update(a.upper() for a in _aliases)


def read_index_store() -> pd.DataFrame:
    if not os.path.exists(CSV_PATH):
        return pd.DataFrame(columns=EF.COLS)
    df = pd.read_csv(CSV_PATH, dtype={"Mã": str})
    df["Ngày"] = pd.to_datetime(df["Ngày"], format=EF.DATE_FMT, errors="coerce")
    for c in EF.PRICE + [EF.VOL]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.dropna(subset=["Mã", "Ngày", "Giá đóng cửa"])[EF.COLS]


def _write(df: pd.DataFrame, path: str) -> None:
    df = df.copy()
    df["Ngày"] = pd.to_datetime(df["Ngày"])
    df[EF.PRICE] = df[EF.PRICE].round(2)
    df[EF.VOL] = df[EF.VOL].fillna(0).round(0).astype("int64")
    df = df.drop_duplicates(["Mã", "Ngày"], keep="last").sort_values(["Mã", "Ngày"]).reset_index(drop=True)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    df[EF.COLS].to_csv(path, index=False, date_format=EF.DATE_FMT)


def member_codes() -> list[str]:
    """Mã thuộc VNMidcap / VNSmallcap trong data/nhom_von_hoa.csv."""
    if not os.path.exists(MEMBERS_LIST):
        return []
    d = pd.read_csv(MEMBERS_LIST, dtype=str, encoding="utf-8-sig")
    d.columns = [c.strip() for c in d.columns]
    if "Mã" not in d or "Nhóm" not in d:
        print(f"File {MEMBERS_LIST} cần hai cột 'Mã' và 'Nhóm'.")
        return []
    d["Mã"] = d["Mã"].astype(str).str.upper().str.strip()
    d["Nhóm"] = d["Nhóm"].astype(str).str.upper().str.strip()
    return list(dict.fromkeys(d.loc[d["Nhóm"].isin(MEMBER_GROUPS), "Mã"]))


def update_members(args, market, now: pd.Timestamp, end: str, session_open: bool, sources: tuple) -> None:
    """Lấy giá các mã thành viên mà eod_prices.csv chưa có. Lỗi ở phần này không làm hỏng phần chỉ số."""
    codes = member_codes()
    if not codes:
        print("Không có danh sách thành viên (data/nhom_von_hoa.csv), bỏ qua phần cổ phiếu.")
        return
    have_eod = set()
    if os.path.exists(EOD_PRICES):
        have_eod = set(pd.read_csv(EOD_PRICES, usecols=["Mã"], dtype=str)["Mã"].unique())
    need = [c for c in codes if c not in have_eod]
    print(f"Thành viên nhóm: {len(codes)} mã, {len(codes) - len(need)} mã đã có trong eod_prices.csv, cần lấy thêm {len(need)} mã.")
    if not need:
        return
    store = _read(MEMBERS_CSV)
    by_code = {c: g for c, g in store.groupby("Mã")}
    start_full = (now.tz_localize(None).normalize() - pd.Timedelta(days=args.member_days)).strftime("%Y-%m-%d")
    t0, updated, failed, fatal = time.time(), {}, [], None
    for i, code in enumerate(need, 1):
        if time.time() - t0 > args.member_minutes * 60:
            fatal = f"Quá {args.member_minutes:g} phút, dừng ở mã thứ {i}/{len(need)} (chạy lại để làm tiếp)"
            break
        old = by_code.get(code)
        full = args.full or old is None or old.empty
        start = start_full if full else (old["Ngày"].max() - pd.Timedelta(days=args.overlap_days)).strftime("%Y-%m-%d")
        try:
            new, _src = EF.fetch_one(market, code, start, end, sources, accept_empty=not full)
        except EF.Fatal as e:
            fatal = str(e)
            break
        except Exception as e:  # noqa: BLE001
            failed.append(f"{code}: {e}")
            continue
        if full:
            merged = new
        elif new.empty:
            merged = old
        else:
            merged = pd.concat([old[old["Ngày"] < new["Ngày"].min()], new], ignore_index=True)
        if merged is not None and not merged.empty:
            updated[code] = merged
        time.sleep(1.0)
    if not updated:
        print("Cổ phiếu thành viên: không cập nhật được mã nào." + (f" Lý do: {fatal}" if fatal else ""))
        return
    keep = store[~store["Mã"].isin(updated)]
    result = pd.concat(([keep] if len(keep) else []) + list(updated.values()), ignore_index=True)
    if session_open:
        result = result[pd.to_datetime(result["Ngày"]) < now.normalize().tz_localize(None)]
    _write(result, MEMBERS_CSV)
    print(f"Cổ phiếu thành viên: cập nhật {len(updated)}/{len(need)} mã · lỗi {len(failed)}" + (f" · DỪNG: {fatal}" if fatal else ""))
    for x in failed[:15]:
        print("  ✗", x)


def _read(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        return pd.DataFrame(columns=EF.COLS)
    df = pd.read_csv(path, dtype={"Mã": str})
    df["Ngày"] = pd.to_datetime(df["Ngày"], format=EF.DATE_FMT, errors="coerce")
    for c in EF.PRICE + [EF.VOL]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.dropna(subset=["Mã", "Ngày", "Giá đóng cửa"])[EF.COLS]


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Lấy dữ liệu cuối phiên của VN30, VNMidcap, VNSmallcap, VN100")
    p.add_argument("--start", default=os.getenv("EOD_START", "2018-11-01"), help="Ngày bắt đầu khi tải đầy đủ")
    p.add_argument("--sources", default="vci,kbs,vnd", help="Thứ tự nguồn vnstock thử lần lượt")
    p.add_argument("--overlap-days", type=int, default=14, help="Số ngày lấy lại khi cập nhật tăng dần")
    p.add_argument("--full", action="store_true", help="Tải lại toàn bộ lịch sử từ --start")
    p.add_argument("--no-members", action="store_true", help="Không lấy giá cổ phiếu thành viên nhóm vốn hóa")
    p.add_argument("--member-days", type=int, default=400, help="Số ngày lịch sử lấy cho cổ phiếu thành viên")
    p.add_argument("--member-minutes", type=float, default=20, help="Dừng phần cổ phiếu thành viên nếu chạy quá số phút này")
    p.add_argument("--now", default="", help="Giả lập giờ VN 'YYYY-MM-DD HH:MM' (kiểm thử)")
    return p.parse_args(argv)


def main(argv=None, market=None) -> int:
    args = parse_args(argv)
    now = pd.Timestamp(args.now, tz=EF.TZ) if args.now else pd.Timestamp.now(tz=EF.TZ)
    end = now.strftime("%Y-%m-%d")
    session_open = now.weekday() < 5 and (now.hour, now.minute) < EF.CLOSE_TIME
    sources = tuple(s.strip() for s in args.sources.split(",") if s.strip())

    if market is None:
        try:
            from vnstock import Market
        except ImportError:
            print("Chưa cài vnstock. Chạy: pip install -r requirements-eod.txt")
            return 1
        EF.maybe_login()
        market = Market()

    store = read_index_store()
    by_code = {c: g for c, g in store.groupby("Mã")}
    updated, failed, fatal = {}, [], None

    for code, aliases in TARGETS.items():
        old = by_code.get(code)
        full = args.full or old is None or old.empty
        start = args.start if full else (old["Ngày"].max() - pd.Timedelta(days=args.overlap_days)).strftime("%Y-%m-%d")
        new, errs = None, []
        for alias in aliases:
            try:
                df, src = EF.fetch_one(market, alias, start, end, sources, accept_empty=not full)
            except EF.Fatal as e:
                fatal = str(e)
                break
            except Exception as e:  # noqa: BLE001
                errs.append(f"{alias}: {e}")
                continue
            if df.empty and full:
                errs.append(f"{alias}: không trả dữ liệu")
                continue
            new = df.assign(**{"Mã": code})
            print(f"  ✓ {code} (tên gọi '{alias}', nguồn {src}): {len(df)} nến")
            break
        if fatal:
            break
        if new is None:
            failed.append(f"{code}: " + " | ".join(errs))
            print(f"  ✗ {code}: " + " | ".join(errs), flush=True)
            continue
        if full or new.empty:
            merged = new if full else old
        else:
            merged = pd.concat([old[old["Ngày"] < new["Ngày"].min()], new], ignore_index=True)
        updated[code] = merged
        time.sleep(1.0)

    if not updated:
        print("Không cập nhật được chỉ số nào." + (f" Lý do: {fatal}" if fatal else ""))
        return 1

    keep = store[~store["Mã"].isin(updated)]
    result = pd.concat(([keep] if len(keep) else []) + list(updated.values()), ignore_index=True)
    result["Ngày"] = pd.to_datetime(result["Ngày"])
    if session_open:                                   # phiên chưa đóng: bỏ nến hôm nay, chỉ giữ dữ liệu đã chốt
        result = result[result["Ngày"] < now.normalize().tz_localize(None)]
    _write(result, CSV_PATH)

    latest = pd.to_datetime(result["Ngày"]).max()
    print(f"Xong: {len(updated)}/{len(TARGETS)} chỉ số · ngày mới nhất {latest:%d/%m/%Y} · lỗi {len(failed)}"
          + (f" · DỪNG: {fatal}" if fatal else ""))
    if not args.no_members and not fatal:
        try:
            update_members(args, market, now, end, session_open, sources)
        except Exception as e:  # noqa: BLE001
            print(f"Phần cổ phiếu thành viên lỗi ({type(e).__name__}: {e}); phần chỉ số đã lưu bình thường.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
