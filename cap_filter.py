"""Bộ lọc vốn hóa dùng chung cho app và các script Telegram: bỏ cổ phiếu có vốn hóa dưới MIN_CAP_BN tỷ đồng khỏi dữ liệu giá
ngay từ khi đọc (đỡ tốn RAM, không báo tín hiệu cho mã nhỏ). Không phụ thuộc Streamlit.

Cách tính vốn hóa (tăng dần độ ưu tiên): data/stock_metadata.csv -> giá đóng cửa mới nhất x SLCP lưu hành
(data/thong_tin_chung.csv, thiếu thì data/shares_outstanding.csv) -> ô "Vốn hóa TT" nhập tay trong data/nhap_tay.csv.

Giữ lại (không bỏ): chỉ số (VNINDEX...), mã chưa biết vốn hóa, và mã đang nắm giữ trong data/co_phieu_cua_toi.csv (KEEP_HELD),
để không mất cảnh báo bán / cắt lỗ của vị thế đang có.
"""
from __future__ import annotations

import os

import pandas as pd

MIN_CAP_BN = 900           # ngưỡng vốn hóa (tỷ đồng); đặt 0 để tắt bộ lọc
KEEP_HELD = True           # True: mã đang nắm giữ vẫn được giữ dù vốn hóa nhỏ; False: bỏ hết không ngoại lệ
HOLD_PATH = "data/co_phieu_cua_toi.csv"
META_PATH, INFO_PATH, SHARES_PATH, MANUAL_PATH = ("data/stock_metadata.csv", "data/thong_tin_chung.csv",
                                                  "data/shares_outstanding.csv", "data/nhap_tay.csv")
INDEX_CODES = {"VNINDEX", "VN-INDEX", "VNI", "VN INDEX", "^VNINDEX", "VN30", "HNXINDEX", "UPCOMINDEX"}


def _by_code(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        return pd.DataFrame()
    try:
        d = pd.read_csv(path, dtype={"Mã": str}, encoding="utf-8-sig")
        d["Mã"] = d["Mã"].astype(str).str.strip().str.upper()
        return d.drop_duplicates("Mã", keep="last").set_index("Mã")
    except Exception:  # noqa: BLE001
        return pd.DataFrame()


def market_cap_map(prices: dict) -> dict:
    """{mã: vốn hóa tỷ đồng}. prices: {mã (chữ hoa): giá đóng cửa mới nhất, nghìn đồng}."""
    meta, info, shares, manual = (_by_code(p) for p in (META_PATH, INFO_PATH, SHARES_PATH, MANUAL_PATH))
    caps: dict = {}
    if "Vốn hóa TT" in meta.columns:
        caps = {c: v for c, v in pd.to_numeric(meta["Vốn hóa TT"], errors="coerce").items() if pd.notna(v)}
    for code, px in prices.items():
        n = float("nan")
        if code in info.index and "SLCP lưu hành (cp)" in info.columns:
            n = pd.to_numeric(info.at[code, "SLCP lưu hành (cp)"], errors="coerce")
        if pd.isna(n) and code in shares.index and "Số CP lưu hành" in shares.columns:
            n = pd.to_numeric(shares.at[code, "Số CP lưu hành"], errors="coerce")
        if pd.notna(n) and pd.notna(px) and n > 0:
            caps[code] = round(float(px) * float(n) / 1e6)
    if "Vốn hóa TT" in manual.columns:           # số nhập tay ưu tiên cao nhất (dấu phẩy thập phân cũng được)
        for code, v in manual["Vốn hóa TT"].items():
            if pd.isna(v) or not str(v).strip():     # ô trống: dùng số tự tính
                continue
            try:
                caps[code] = float(str(v).replace("%", "").replace(" ", "").replace(",", "."))
            except ValueError:
                pass
    return caps


def held_codes(path: str = HOLD_PATH) -> set[str]:
    d = _by_code(path)
    return set(d.index) if len(d) else set()


def drop_small_caps(raw: pd.DataFrame, min_bn: float = MIN_CAP_BN, keep: set[str] | None = None) -> pd.DataFrame:
    """Bỏ các mã vốn hóa dưới min_bn tỷ khỏi bảng giá (cột Mã, Ngày, Giá đóng cửa). keep: mã luôn giữ (mặc định: mã đang nắm giữ)."""
    if not min_bn or raw.empty:
        return raw
    last = raw.sort_values("Ngày").groupby("Mã")["Giá đóng cửa"].last()
    caps = market_cap_map({str(c).upper(): float(p) for c, p in last.items() if pd.notna(p)})
    keep = {c.upper() for c in (keep if keep is not None else (held_codes() if KEEP_HELD else set()))}
    small = {c for c in last.index
             if str(c).upper() not in INDEX_CODES and str(c).upper() not in keep
             and pd.notna(caps.get(str(c).upper())) and float(caps[str(c).upper()]) < min_bn}
    return raw[~raw["Mã"].isin(small)] if small else raw
