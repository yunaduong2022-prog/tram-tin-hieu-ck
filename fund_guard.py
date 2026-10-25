"""Chặn dữ liệu cơ bản (P/B, P/E, ROE) không đáng tin trước khi hiển thị.

Nguyên tắc: không có số thật thì để trống, không bao giờ điền số mặc định.

- Giá trị ngoài miền hợp lý bị bỏ (P/B <= 0 hoặc > 200, P/E <= 0 hoặc > 1000, ROE ngoài -100..100 %).
- Cột có >= MIN_N ô số mà >= SAME_SHARE trong đó là cùng một giá trị bị coi là số giả (placeholder) và bị xóa cả cột.
  Thị trường thật không bao giờ có 200 mã cùng P/B 3,0 và cùng ROE 17 %.
- Số nhập tay (data/nhap_tay.csv) không đi qua bước này và vẫn luôn được ưu tiên.

Dùng trong app:   fund_map = FG.load_fund_map();  FG.warnings()  -> danh sách cảnh báo để hiện cho người dùng.
Làm sạch file:    python fund_guard.py --fix        (ghi đè data/fundamentals.csv bằng bản đã làm sạch)
"""
from __future__ import annotations

import os
import sys

import pandas as pd

PATH = "data/fundamentals.csv"
METRICS = ("P/B", "P/E", "ROE", "P/B TB 3N", "P/E TB 3N")
VALID = {"P/B": (0, 200), "P/E": (0, 1000), "ROE": (-100, 100), "P/B TB 3N": (0, 200), "P/E TB 3N": (0, 1000)}
MIN_N = 10          # cần ít nhất ngần này ô số mới kết luận được một cột là số giả
SAME_SHARE = 0.8    # tỷ lệ ô trùng một giá trị để coi là số giả

_WARN: list[str] = []


def sanitize(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Trả về (bảng đã làm sạch, danh sách cảnh báo)."""
    df, warns = df.copy(), []
    for col in METRICS:
        if col not in df.columns:
            continue
        s = pd.to_numeric(df[col], errors="coerce")
        lo, hi = VALID[col]
        bad = s.notna() & ((s <= lo) | (s > hi)) if col != "ROE" else s.notna() & ((s < lo) | (s > hi))
        if bad.any():
            warns.append(f"{col}: bỏ {int(bad.sum())} giá trị ngoài miền hợp lý.")
            s = s.mask(bad)
        v = s.dropna().round(4)
        if len(v) >= MIN_N:
            top = v.value_counts()
            if top.iloc[0] / len(v) >= SAME_SHARE:
                warns.append(f"{col}: {int(top.iloc[0])}/{len(v)} mã cùng giá trị {top.index[0]:g} - đây là số mặc định, "
                             f"không phải dữ liệu thật nên đã bị ẩn. Cập nhật lại từ nguồn hoặc nhập tay ở data/nhap_tay.csv.")
                s = s.mask(s.notna())
        df[col] = s
    return df, warns


def load_fund_map(path: str = PATH) -> dict:
    """Đọc data/fundamentals.csv đã làm sạch thành {mã: {cột: giá trị}}. Lỗi đọc file -> {}."""
    global _WARN
    _WARN = []
    if not os.path.exists(path):
        return {}
    try:
        df = pd.read_csv(path, dtype={"Mã": str})
        df["Mã"] = df["Mã"].str.upper().str.strip()
        df, _WARN = sanitize(df)
        return df.drop_duplicates("Mã", keep="last").set_index("Mã").to_dict("index")
    except Exception:  # noqa: BLE001
        return {}


def warnings() -> list[str]:
    """Cảnh báo của lần load_fund_map gần nhất."""
    return list(_WARN)


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not os.path.exists(PATH):
        print(f"Không thấy {PATH}")
        return 1
    df = pd.read_csv(PATH, dtype={"Mã": str})
    clean, warns = sanitize(df)
    for w in warns:
        print("-", w)
    if not warns:
        print("Không phát hiện số giả.")
    if "--fix" in argv:
        clean.to_csv(PATH, index=False)
        print(f"Đã ghi {PATH}")
    else:
        print("(Chạy thêm --fix để ghi đè file)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
