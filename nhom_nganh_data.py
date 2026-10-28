"""Lớp dữ liệu CHUNG cho hai bảng nhóm ngành:
  - Thị trường > Nhóm ngành: "Xếp hạng sức mạnh nhóm ngành hôm nay" (nhom_nganh_homnay.py)
  - Ngành > Dòng dẫn sóng: bảng xếp hạng dòng theo giai đoạn + cổ phiếu đại diện (dong_dan_song.py)

Cách tính bám sector_rotation.py (cùng bảng pivot giá/khối lượng, cùng RS ngành so với VN-Index) nên số liệu khớp trang "Cảnh báo luân chuyển dòng tiền".
Hiệu suất của một nhóm = TRUNG VỊ % của các mã khi nhóm có từ MIN_FOR_MEDIAN mã trở lên (không bị một mã tăng đột biến kéo lệch);
nhóm ít mã hơn thì dùng TRUNG BÌNH. Giá tính theo nghìn đồng, khối lượng theo cổ phiếu => GTGD (tỷ đồng) = giá x KL / 1e6.

Danh sách dòng: data/dong_dan_song.csv (cột Dòng, Mã, [Mô tả], [Leader]; mỗi mã một dòng, Leader = 1/x/có để gắn nhãn LEADER).
Không có file này thì dùng nhóm ngành mặc định của watchlist.GROUPS.
Chỉ phục vụ nghiên cứu, không phải khuyến nghị đầu tư.
"""
from __future__ import annotations

import inspect

import numpy as np
import pandas as pd
import streamlit as st

import sector_rotation as SRT

CSV_PATH = "data/dong_dan_song.csv"
MIN_MEMBERS = 2            # nhóm có ít hơn số mã này (có dữ liệu) thì bỏ qua
MIN_FOR_MEDIAN = 5         # từ số mã này trở lên dùng trung vị, ít hơn dùng trung bình
PERIODS = {"1 tuần": 5, "1 tháng": 21, "2 tháng": 42, "3 tháng": 63, "6 tháng": 126}   # số phiên của từng mốc giai đoạn
TOP_LEAD = 6               # nhãn DẪN SÓNG: nằm trong top này theo biến động giai đoạn,
LEAD_MIN_POS = 0.5         # ... có ít nhất ngần này số mã tăng trong giai đoạn,
#                            ... và mạnh hơn VN-Index cùng giai đoạn
REP_MAX = 8                # số cổ phiếu đại diện hiện ở bảng bên phải (chọn theo GTGD bình quân 20 phiên)
LEADER_LABELS = {"1", "x", "có", "co", "true", "y", "leader"}


def stretch(fn) -> dict:
    """Tham số giãn hết chiều ngang, tương thích mọi bản Streamlit (width='stretch' ở bản mới, use_container_width ở bản cũ)."""
    p = inspect.signature(fn).parameters
    if "width" in p and ("stretch" in str(p["width"].annotation) or p["width"].default == "stretch"):
        return {"width": "stretch"}
    return {"use_container_width": True} if "use_container_width" in p else {}


def load_groups(default: dict) -> tuple[dict, dict]:
    """(groups {dòng: [mã]}, meta {dòng: {'desc': str, 'leaders': set}}). Không có CSV hợp lệ thì trả về nhóm mặc định, meta rỗng."""
    try:
        d = pd.read_csv(CSV_PATH, dtype=str, encoding="utf-8-sig")
    except Exception:  # noqa: BLE001
        return {k: list(v) for k, v in default.items()}, {}
    d.columns = [str(c).strip() for c in d.columns]
    if not {"Dòng", "Mã"} <= set(d.columns):
        return {k: list(v) for k, v in default.items()}, {}
    groups: dict[str, list[str]] = {}
    meta: dict[str, dict] = {}
    for _, r in d.dropna(subset=["Dòng", "Mã"]).iterrows():
        g, code = str(r["Dòng"]).strip(), str(r["Mã"]).strip().upper()
        if not g or not code or code == "NAN":
            continue
        groups.setdefault(g, []).append(code)
        m = meta.setdefault(g, {"desc": "", "leaders": set()})
        desc = str(r.get("Mô tả", "") or "").strip()
        if desc and desc.lower() != "nan" and not m["desc"]:
            m["desc"] = desc
        if str(r.get("Leader", "") or "").strip().lower() in LEADER_LABELS:
            m["leaders"].add(code)
    return (groups or {k: list(v) for k, v in default.items()}), meta


@st.cache_resource(show_spinner=False, max_entries=4)
def pivots(_raw: pd.DataFrame, key: str) -> dict:
    """Bảng pivot ngày x mã (đóng cửa 'c', khối lượng 'v'), dùng lại hàm của sector_rotation."""
    return SRT._prep(_raw)


def _agg(s: pd.Series) -> float:
    s = pd.to_numeric(s, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if s.empty:
        return float("nan")
    return float(s.median() if len(s) >= MIN_FOR_MEDIAN else s.mean())


def _members(syms, cols) -> list[str]:
    return [m for m in dict.fromkeys(str(s).upper() for s in syms) if m in cols]


def day_stats(P: dict, groups: dict, mkt: pd.Series, lead_min_val: float = 0.0) -> pd.DataFrame:
    """Hiệu suất phiên gần nhất của từng nhóm: %, GTGD (tỷ), mã dẫn đầu, số mã tăng/giảm, RS 5 phiên."""
    c, v = P.get("c"), P.get("v")
    if c is None or len(c) < 2:
        return pd.DataFrame()
    chg = ((c.iloc[-1] / c.iloc[-2] - 1) * 100).replace([np.inf, -np.inf], np.nan)
    vol = v.iloc[-1].reindex(c.columns) if v is not None and not v.empty else pd.Series(np.nan, index=c.columns)
    val = c.iloc[-1] * vol / 1e6
    rows = []
    for name, syms in groups.items():
        mem = [m for m in _members(syms, chg.index) if pd.notna(chg[m])]
        if len(mem) < MIN_MEMBERS:
            continue
        g, gv = chg[mem], val.reindex(mem)
        pool = g[gv.fillna(0) >= lead_min_val] if lead_min_val > 0 else g
        if pool.empty:
            pool = g
        lead = pool.idxmax()
        try:
            a = SRT.analyze_sector(mem, P, mkt)
        except Exception:  # noqa: BLE001
            a = None
        rows.append({"Nhóm": name, "Số mã": len(mem), "Hiệu suất": _agg(g), "GTGD": float(gv.sum(min_count=1)) if gv.notna().any() else float("nan"),
                     "Mã dẫn đầu": lead, "% dẫn đầu": float(g[lead]), "Tăng": int((g > 0).sum()), "Giảm": int((g < 0).sum()),
                     "RS 5 phiên": (a or {}).get("rs_chg5", float("nan"))})
    return pd.DataFrame(rows)


def _bench(mkt: pd.Series, idx: pd.Index, n: int) -> tuple[float, float]:
    """(% VN-Index trong n phiên, % VN-Index phiên cuối)."""
    try:
        m = mkt.reindex(idx).ffill()
        return float((m.iloc[-1] / m.iloc[-1 - n] - 1) * 100), float((m.iloc[-1] / m.iloc[-2] - 1) * 100)
    except Exception:  # noqa: BLE001
        return float("nan"), float("nan")


def period_stats(P: dict, groups: dict, mkt: pd.Series, n: int) -> tuple[pd.DataFrame, dict]:
    """Xếp hạng dòng theo biến động n phiên + biến động ngày + cờ DẪN SÓNG. Trả (bảng, {'per':..., 'day':...} của VN-Index)."""
    c = P.get("c")
    if c is None or len(c) < n + 2:
        return pd.DataFrame(), {}
    day = ((c.iloc[-1] / c.iloc[-2] - 1) * 100).replace([np.inf, -np.inf], np.nan)
    per = ((c.iloc[-1] / c.iloc[-1 - n] - 1) * 100).replace([np.inf, -np.inf], np.nan)
    bper, bday = _bench(mkt, c.index, n)
    rows = []
    for name, syms in groups.items():
        mem = [m for m in _members(syms, c.columns) if pd.notna(per[m])]
        if len(mem) < MIN_MEMBERS:
            continue
        p = per[mem]
        rows.append({"Dòng": name, "Số mã": len(mem), "Giai đoạn": _agg(p), "Ngày": _agg(day[mem]), "Tỷ lệ tăng": float((p > 0).mean())})
    d = pd.DataFrame(rows)
    if d.empty:
        return d, {"per": bper, "day": bday}
    d = d.sort_values("Giai đoạn", ascending=False).reset_index(drop=True)
    d["#"] = np.arange(1, len(d) + 1)
    d["Dẫn sóng"] = (d["#"] <= TOP_LEAD) & (d["Tỷ lệ tăng"] >= LEAD_MIN_POS) & (d["Giai đoạn"] > (bper if pd.notna(bper) else -1e9)) & (d["Giai đoạn"] > 0)
    return d, {"per": bper, "day": bday}


def rep_stocks(P: dict, members, n: int, leaders: set | None = None, top: int = REP_MAX) -> pd.DataFrame:
    """Cổ phiếu đại diện của một dòng: top theo GTGD bình quân 20 phiên, hiện theo biến động giai đoạn giảm dần; LEADER lấy từ CSV, không có thì mã tăng mạnh nhất."""
    c, v = P["c"], P.get("v")
    mem = [m for m in _members(members, c.columns) if c[m].notna().sum() > n + 1]
    if not mem:
        return pd.DataFrame()
    last = c[mem].iloc[-1]
    day = (c[mem].iloc[-1] / c[mem].iloc[-2] - 1) * 100
    per = (c[mem].iloc[-1] / c[mem].iloc[-1 - n] - 1) * 100
    if v is not None and not v.empty:
        liq = (c[mem] * v.reindex(columns=mem)).tail(20).mean() / 1e6
    else:
        liq = pd.Series(0.0, index=mem)
    d = pd.DataFrame({"Mã": mem, "Giá": last.to_numpy(), "Ngày": day.to_numpy(), "Giai đoạn": per.to_numpy(), "GTGD20": liq.reindex(mem).fillna(0).to_numpy()})
    d = d.sort_values("GTGD20", ascending=False).head(top).sort_values("Giai đoạn", ascending=False).reset_index(drop=True)
    lead = [x for x in d["Mã"] if x in (leaders or set())]
    d["Leader"] = d["Mã"].isin(lead) if lead else (d.index == 0)
    return d


def compare_frame(P: dict, codes, n: int) -> pd.DataFrame:
    """Giá quy về 100 tại đầu giai đoạn, để so sánh các mã."""
    c = P["c"][list(codes)].tail(n + 1)
    return c / c.iloc[0] * 100
