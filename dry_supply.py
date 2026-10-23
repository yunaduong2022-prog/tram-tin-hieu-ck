"""Mục "Cạn cung" (Bộ lọc & Backtest, ngay sau Giảm mạnh).

Gom MỌI cổ phiếu mà các mục khác của app đang mô tả là cạn cung / khối lượng cạn, không đặt thêm điều kiện mới:

  1. Lọc tất cả CP  : cờ "Cạn cung" (engine.py, cột DryUp): khối lượng phiên cuối < 0.7 lần MA20 Vol,
                      giá đóng cửa >= MA20 và biên độ phiên |%| < 2.
  2. Chờ mua / Mua ngay:
       - "Điểm mua đẹp"            : test lại hỗ trợ với khối lượng 5 phiên <= dry_vol (0.8) lần MA20 Vol (waiting_buy.py)
       - "Tích lũy / Siết nền giá" : nền chặt, khối lượng 5 phiên <= 0.9 lần MA20 Vol, các MA hội tụ
  3. Wyckoff (khung Ngày): cấu trúc TÍCH LŨY đang ở Pha C / D mà sự kiện mới nhất là Spring, Test hoặc LPS
                      với volume thấp hơn trung bình (cung đã cạn), xảy ra trong MAX_EV_AGE phiên gần nhất
                      và phiên cuối chưa bùng nổ volume (khối lượng phiên cuối <= MAX_LAST_VOL lần MA20 Vol).

Các trạng thái chỉ ghi "khối lượng co lại" (Theo dõi điểm mua) không tính vì chưa phải cạn.
Phần dựng dữ liệu không phụ thuộc Streamlit.
"""
from __future__ import annotations

import html as _h

import numpy as np
import pandas as pd

import waiting_buy as WB
import wyckoff as WYK

MAX_EV_AGE = 10                    # sự kiện Wyckoff (Spring/Test/LPS) phải nằm trong N phiên gần nhất
WY_PHASES = ("C", "D")             # pha E đã rời vùng tích lũy: không còn là "cạn cung trong nền"
MAX_LAST_VOL = 1.0                 # Wyckoff: phiên cuối đã nổ volume (> MA20 Vol) thì cung không còn "cạn" nữa
DRYUP_RATIO = 0.7                  # trùng ngưỡng DryUp ở engine.py (chỉ dùng để ghi chú)

SRC_FILTER, SRC_ENTRY, SRC_BASE, SRC_WYCKOFF = "Lọc CP: Cạn cung", "Điểm mua đẹp", "Siết nền giá", "Wyckoff"
SOURCES = (SRC_FILTER, SRC_ENTRY, SRC_BASE, SRC_WYCKOFF)
SRC_HELP = {
    SRC_FILTER: "Mục Lọc tất cả CP, bộ lọc dòng tiền «Cạn cung»: khối lượng phiên cuối < 0.7 lần MA20 Vol, giá giữ trên MA20, biên độ phiên < 2%.",
    SRC_ENTRY: "Mục Chờ mua / Mua ngay, trạng thái «Điểm mua đẹp»: test lại hỗ trợ với khối lượng 5 phiên cạn (≤ 0.8 lần MA20 Vol).",
    SRC_BASE: "Mục Chờ mua, trạng thái «Tích lũy / Siết nền giá»: nền giá chặt, khối lượng cạn, các MA hội tụ.",
    SRC_WYCKOFF: f"Phân tích Wyckoff khung Ngày: tích lũy Pha C/D, Spring / Test / LPS với volume thấp trong {MAX_EV_AGE} phiên gần nhất.",
}


def _fnum(x):
    try:
        v = float(x)
        return v if np.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def last_volume_ratio(df_d: pd.DataFrame) -> dict:
    """{mã: khối lượng phiên cuối / MA20 Vol} từ khung Ngày (cột Vol_MA20 do engine.add_indicators tạo)."""
    need = {"Mã", "Ngày", "Khối lượng khớp lệnh", "Vol_MA20"}
    if df_d is None or not need.issubset(df_d.columns):
        return {}
    last = df_d.sort_values("Ngày").groupby("Mã").tail(1)
    ratio = pd.to_numeric(last["Khối lượng khớp lệnh"], errors="coerce") / pd.to_numeric(last["Vol_MA20"], errors="coerce").replace(0, np.nan)
    return dict(zip(last["Mã"].astype(str), ratio))


def wyckoff_dry_event(w, dates_d: pd.DatetimeIndex | None, max_age: int = MAX_EV_AGE, last_ratio=None):
    """Sự kiện cạn cung của Wyckoff nếu có: dict(label, date, vx, age) hoặc None.

    Điều kiện: kind = acc, pha C/D, sự kiện MỚI NHẤT của vùng là Spring/Test/LPS có low_vol (volume < trung bình),
    và cách nến cuối không quá max_age phiên (đếm theo các ngày giao dịch của khung Ngày).
    """
    if not w or w.get("kind") != "acc" or w.get("phase") not in WY_PHASES:
        return None
    last_ev = w.get("last_ev")
    if not last_ev:
        return None
    cands = [x for x in (w.get("dry_ev") or []) if x.get("low_vol") and pd.Timestamp(x["date"]) == pd.Timestamp(last_ev["date"])]
    if not cands:
        return None
    x = cands[-1]
    if dates_d is None or len(dates_d) == 0:
        age = 0
    else:
        age = int((dates_d > pd.Timestamp(x["date"])).sum())
    if age > max_age:
        return None
    lr = _fnum(last_ratio)
    if lr is not None and lr > MAX_LAST_VOL:      # sau sự kiện, phiên cuối đã bùng nổ volume: không còn cạn cung
        return None
    return {"label": x["label"], "date": pd.Timestamp(x["date"]), "vx": _fnum(x.get("vx")), "age": age, "phase": w.get("phase")}


def collect(res: pd.DataFrame, t: pd.DataFrame, wy_map: dict, df_d: pd.DataFrame, max_age: int = MAX_EV_AGE) -> dict:
    """{mã: [(nguồn, câu giải thích), ...]} cho mọi mã đang cạn cung theo bất kỳ mục nào.

    res: bảng screener (cột Mã, DryUp); t: bảng Chờ mua (waiting_buy); wy_map: {mã: wyckoff.compact()}; df_d: khung Ngày có chỉ báo.
    """
    out: dict[str, list[tuple[str, str]]] = {}
    vr = last_volume_ratio(df_d)

    # 1. Lọc tất cả CP: cờ Cạn cung
    if res is not None and "DryUp" in res.columns:
        for code in res.loc[res["DryUp"].fillna(False).astype(bool), "Mã"].astype(str):
            x = _fnum(vr.get(code))
            vt = f"khối lượng phiên cuối chỉ bằng {x:.2f} lần MA20 Vol (dưới {DRYUP_RATIO:g})" if x is not None else f"khối lượng phiên cuối dưới {DRYUP_RATIO:g} lần MA20 Vol"
            out.setdefault(code, []).append((SRC_FILTER, f"Cạn cung theo bộ lọc dòng tiền: {vt}, giá giữ trên MA20 và biên độ phiên dưới 2%."))

    # 2. Chờ mua / Mua ngay
    if t is not None and not t.empty:
        for _, r in t[t["Trạng thái"].isin([WB.GOOD_ENTRY, WB.ACCUM])].iterrows():
            src = SRC_ENTRY if r["Trạng thái"] == WB.GOOD_ENTRY else SRC_BASE
            why = str(r.get("Lý do") or "").strip().rstrip(".")
            out.setdefault(str(r["Mã"]), []).append((src, f"{r['Trạng thái']}: {why}." if why else f"{r['Trạng thái']}."))

    # 3. Wyckoff
    dates = pd.DatetimeIndex(sorted(pd.to_datetime(df_d["Ngày"]).unique())) if df_d is not None and "Ngày" in df_d.columns else None
    for code, w in (wy_map or {}).items():
        ev = wyckoff_dry_event(w, dates, max_age, vr.get(str(code)))
        if ev:
            vx = f" với volume {ev['vx']:.2f} lần trung bình" if ev["vx"] is not None else " với volume thấp"
            when = "phiên cuối" if ev["age"] == 0 else f"{ev['age']} phiên trước"
            out.setdefault(str(code), []).append((SRC_WYCKOFF, f"Tích lũy Pha {ev['phase']}: {ev['label']} ngày {ev['date']:%d/%m} ({when}){vx}, nguồn cung đã cạn."))
    return out


def build(res: pd.DataFrame, t: pd.DataFrame, wy_map: dict, df_d: pd.DataFrame, now_codes=(), max_age: int = MAX_EV_AGE) -> pd.DataFrame:
    """Bảng Cạn cung: các cột của bảng Chờ mua + Nguồn cạn cung (list), Số nguồn, Lý do (đã gộp), Vol / MA20 Vol, Mua ngay."""
    found = collect(res, t, wy_map, df_d, max_age)
    if not found or t is None or t.empty:
        return pd.DataFrame(columns=list(t.columns) + ["Nguồn cạn cung", "Số nguồn", "Vol / MA20 Vol", "Mua ngay"] if t is not None else [])
    d = t[t["Mã"].astype(str).isin(found)].copy()
    order = {s: i for i, s in enumerate(SOURCES)}
    d["Nguồn cạn cung"] = d["Mã"].astype(str).map(lambda c: [s for s, _ in sorted(found[c], key=lambda z: order[z[0]])])
    d["Số nguồn"] = d["Nguồn cạn cung"].map(len)
    vr = last_volume_ratio(df_d)
    d["Vol / MA20 Vol"] = d["Mã"].astype(str).map(vr)
    now = set(map(str, now_codes))
    d["Mua ngay"] = d["Mã"].astype(str).isin(now)

    def _why(r):
        parts = [txt for _, txt in sorted(found[str(r["Mã"])], key=lambda z: order[z[0]])]
        return " ".join(parts) + f" Trạng thái hiện tại ở mục Chờ mua: {r['Danh sách']}."
    d["Lý do"] = d.apply(_why, axis=1)
    return d.sort_values(["Số nguồn", "Score"], ascending=[False, False]).reset_index(drop=True)


def chips_html(d: pd.DataFrame, chip, lean: dict) -> str:
    """Danh sách tổng hợp chia theo DỰ BÁO của biểu đồ (khung Ngày): nghiêng tăng / nghiêng giảm.
    lean: {mã: +1 / -1 / 0} (cùng phép tính với dòng "DỰ BÁO NGHIÊNG TĂNG / GIẢM" trên thẻ). Mã không nghiêng rõ (0) xếp nhóm cuối, nhóm rỗng không hiện.
    chip(mã) -> HTML của mã (app._chip: liên kết sc-jump cuộn tới thẻ). Thứ tự trong nhóm giữ theo bảng (nhiều nguồn báo trước)."""
    if d.empty:
        return ""
    groups = ((1, "▲ DỰ BÁO NGHIÊNG TĂNG", "var(--green)"), (-1, "▼ DỰ BÁO NGHIÊNG GIẢM", "var(--red)"), (0, "Chưa nghiêng rõ", "var(--muted)"))
    out = []
    for k, name, col in groups:
        codes = [str(c) for c in d["Mã"] if int(lean.get(str(c), 0) or 0) == k]
        if not codes:
            continue
        out.append(f'<div style="margin-top:10px"><div style="font-size:12px;font-weight:700;color:{col};letter-spacing:.03em;margin-bottom:2px">'
                   f'{_h.escape(name)} · {len(codes)} mã</div>{", ".join(chip(c) for c in codes)}</div>')
    return "".join(out)
