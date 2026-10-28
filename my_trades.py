"""Vòng đời một mã trong "Cổ phiếu của tôi": CHỜ MUA -> ĐANG GIỮ -> ĐÃ BÁN, kèm sổ giao dịch giữ lại mãi để backtest.
Thuần pandas (không phụ thuộc Streamlit) nên kiểm thử được.

Hai file (giá tính bằng nghìn đồng, giống phần còn lại của app):
- data/ke_hoach_giao_dich.csv: mỗi dòng là MỘT KẾ HOẠCH của một mã, đi theo mã từ lúc chờ mua tới khi bán hết.
  Trạng thái: CHỜ MUA / ĐANG GIỮ / ĐÃ BÁN / HỦY. Ghi lại vùng mua, tỷ trọng, cắt lỗ, mục tiêu và điểm lúc lập kế hoạch.
- data/lich_su_giao_dich.csv: sổ giao dịch CHỈ GHI THÊM (mỗi lần mua / bán một dòng). Không có hàm nào xóa hay sửa dòng cũ.
  Dòng BÁN có lãi/lỗ ròng đã chốt (sau phí và thuế, tính theo từng lô FIFO), kèm điểm và tín hiệu tại lúc giao dịch.

Lô đang nắm giữ vẫn ở data/co_phieu_cua_toi.csv (my_portfolio); bán thì trừ lô cũ nhất trước (FIFO).
Điểm cơ bản / kỹ thuật / tổng: nhận từ bên ngoài (xem scores trong add_plan / record_buy / record_sell), module này chỉ lưu lại.
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd

import engine as E

PLANS_PATH = "data/ke_hoach_giao_dich.csv"
TRADES_PATH = "data/lich_su_giao_dich.csv"
WAIT, HOLD, SOLD, CANCEL = "CHỜ MUA", "ĐANG GIỮ", "ĐÃ BÁN", "HỦY"
PLAN_COLS = ["ID", "Mã", "Trạng thái", "Ngày tạo", "Vùng mua từ", "Vùng mua đến", "Tỷ trọng %", "Cắt lỗ", "Mục tiêu 1", "Mục tiêu 2",
             "Điểm cơ bản", "Điểm kỹ thuật", "Tổng điểm", "Ghi chú", "Ngày đóng"]
TRADE_COLS = ["ID kế hoạch", "Mã", "Loại", "Ngày", "Giá", "Số lượng", "Phí và thuế (đồng)", "Lãi/lỗ ròng (đồng)", "Lãi/lỗ %",
              "Điểm cơ bản", "Điểm kỹ thuật", "Tổng điểm", "Tín hiệu", "Ghi chú"]
_PLAN_NUM = ["Vùng mua từ", "Vùng mua đến", "Tỷ trọng %", "Cắt lỗ", "Mục tiêu 1", "Mục tiêu 2", "Điểm cơ bản", "Điểm kỹ thuật", "Tổng điểm"]
_TRADE_NUM = ["Giá", "Số lượng", "Phí và thuế (đồng)", "Lãi/lỗ ròng (đồng)", "Lãi/lỗ %", "Điểm cơ bản", "Điểm kỹ thuật", "Tổng điểm"]
_LOT_COLS = ["Mã", "Số lượng", "Giá vốn", "Ngày mua", "Cắt lỗ", "Mục tiêu", "Ghi chú"]       # giống my_portfolio.COLS


# ------------------------------------------------------------------ ĐỌC / GHI
def _plans_clean(d: pd.DataFrame) -> pd.DataFrame:
    d = d.copy()
    for c in PLAN_COLS:
        if c not in d.columns:
            d[c] = np.nan if c in _PLAN_NUM else ""
    for c in _PLAN_NUM:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    for c in ("Ngày tạo", "Ngày đóng"):
        d[c] = pd.to_datetime(d[c], errors="coerce", format="mixed", dayfirst=True)
    d["Mã"] = d["Mã"].astype(str).str.upper().str.strip()
    for c in ("ID", "Trạng thái", "Ghi chú"):
        d[c] = d[c].fillna("").astype(str)
    return d[PLAN_COLS].reset_index(drop=True)


def _trades_clean(d: pd.DataFrame) -> pd.DataFrame:
    d = d.copy()
    for c in TRADE_COLS:
        if c not in d.columns:
            d[c] = np.nan if c in _TRADE_NUM else ""
    for c in _TRADE_NUM:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d["Ngày"] = pd.to_datetime(d["Ngày"], errors="coerce", format="mixed", dayfirst=True)
    d["Mã"] = d["Mã"].astype(str).str.upper().str.strip()
    for c in ("ID kế hoạch", "Loại", "Tín hiệu", "Ghi chú"):
        d[c] = d[c].fillna("").astype(str)
    return d[TRADE_COLS].reset_index(drop=True)


def _read(path: str, clean, cols) -> pd.DataFrame:
    if os.path.exists(path):
        try:
            return clean(pd.read_csv(path, dtype=str, encoding="utf-8-sig"))
        except Exception:  # noqa: BLE001
            pass
    return clean(pd.DataFrame(columns=cols))


def _write(d: pd.DataFrame, path: str, date_cols: tuple[str, ...]) -> str:
    """Ghi qua file tạm rồi thay thế, để mất điện / lỗi giữa chừng không làm hỏng file cũ. Trả '' nếu ổn, ngược lại là thông báo lỗi."""
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        out = d.copy()
        for c in date_cols:
            out[c] = out[c].dt.strftime("%d/%m/%Y")
        tmp = path + ".tmp"
        out.to_csv(tmp, index=False, encoding="utf-8-sig")
        os.replace(tmp, path)
        return ""
    except Exception as e:  # noqa: BLE001
        return str(e)


def load_plans(path: str = PLANS_PATH) -> pd.DataFrame:
    return _read(path, _plans_clean, PLAN_COLS)


def save_plans(d: pd.DataFrame, path: str = PLANS_PATH) -> str:
    return _write(_plans_clean(d), path, ("Ngày tạo", "Ngày đóng"))


def load_trades(path: str = TRADES_PATH) -> pd.DataFrame:
    return _read(path, _trades_clean, TRADE_COLS)


def save_trades(d: pd.DataFrame, path: str = TRADES_PATH) -> str:
    """Chỉ dùng nội bộ sau khi đã ghi thêm dòng mới. Giữ nguyên mọi dòng cũ."""
    return _write(_trades_clean(d), path, ("Ngày",))


# ------------------------------------------------------------------ KẾ HOẠCH
def _new_id(plans: pd.DataFrame, code: str, when) -> str:
    base = f"{code}-{pd.Timestamp(when):%Y%m%d}"
    n = int(plans["ID"].astype(str).str.startswith(base).sum())
    return base if n == 0 else f"{base}-{n + 1}"


def active_plan(plans: pd.DataFrame, code: str):
    """Kế hoạch còn mở (CHỜ MUA hoặc ĐANG GIỮ) của mã, ưu tiên ĐANG GIỮ; không có thì None."""
    m = plans[(plans["Mã"] == code.upper()) & plans["Trạng thái"].isin([HOLD, WAIT])]
    if m.empty:
        return None
    m = m.assign(_p=(m["Trạng thái"] == WAIT).astype(int)).sort_values(["_p", "Ngày tạo"], ascending=[True, False])
    return m.iloc[0]


def _scores(scores: dict | None) -> dict:
    s = scores or {}
    return {"Điểm cơ bản": s.get("fund", np.nan), "Điểm kỹ thuật": s.get("tech", np.nan), "Tổng điểm": s.get("total", np.nan)}


def add_plan(plans: pd.DataFrame, code: str, asof, zone: tuple[float, float], weight: float | None = None, stop: float | None = None,
             t1: float | None = None, t2: float | None = None, scores: dict | None = None, note: str = "") -> tuple[pd.DataFrame, str]:
    """Thêm kế hoạch CHỜ MUA. Trả (bảng mới, thông báo lỗi). Mỗi mã chỉ có một kế hoạch mở."""
    code = str(code).upper().strip()
    lo, hi = sorted((float(zone[0]), float(zone[1])))
    if not (lo > 0 and hi > 0):
        return plans, "Vùng mua phải lớn hơn 0."
    if stop and stop >= lo:
        return plans, "Cắt lỗ phải thấp hơn vùng mua."
    if t1 and t1 <= hi:
        return plans, "Mục tiêu 1 phải cao hơn vùng mua."
    if t2 and t1 and t2 <= t1:
        return plans, "Mục tiêu 2 phải cao hơn mục tiêu 1."
    if active_plan(plans, code) is not None:
        return plans, f"{code} đã có kế hoạch đang mở (chờ mua hoặc đang giữ)."
    row = {"ID": _new_id(plans, code, asof), "Mã": code, "Trạng thái": WAIT, "Ngày tạo": pd.Timestamp(asof), "Vùng mua từ": lo, "Vùng mua đến": hi,
           "Tỷ trọng %": weight, "Cắt lỗ": stop or np.nan, "Mục tiêu 1": t1 or np.nan, "Mục tiêu 2": t2 or np.nan, **_scores(scores),
           "Ghi chú": note, "Ngày đóng": pd.NaT}
    return _plans_clean(pd.concat([plans, pd.DataFrame([row])], ignore_index=True)), ""


def cancel_plan(plans: pd.DataFrame, plan_id: str, asof) -> pd.DataFrame:
    """Hủy kế hoạch CHỜ MUA (chưa mua). Kế hoạch vẫn nằm trong bảng với trạng thái HỦY."""
    p = plans.copy()
    m = (p["ID"] == plan_id) & (p["Trạng thái"] == WAIT)
    p.loc[m, "Trạng thái"] = CANCEL
    p.loc[m, "Ngày đóng"] = pd.Timestamp(asof)
    return p


# ------------------------------------------------------------------ MUA / BÁN
def record_buy(plans: pd.DataFrame, trades: pd.DataFrame, lots: pd.DataFrame, code: str, qty: int, px: float, when,
               scores: dict | None = None, signal: str = "", note: str = "", stop: float | None = None,
               target: float | None = None) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, str]:
    """Ghi một lần MUA: thêm lô, thêm dòng vào sổ, chuyển kế hoạch CHỜ MUA sang ĐANG GIỮ (chưa có kế hoạch thì tạo kế hoạch 'mua trực tiếp').
    Cắt lỗ / mục tiêu của lô lấy từ stop / target nếu có, không thì từ kế hoạch. Trả (plans, trades, lots, lỗi)."""
    code = str(code).upper().strip()
    if qty <= 0 or px <= 0:
        return plans, trades, lots, "Cần số lượng và giá mua lớn hơn 0."
    p = active_plan(plans, code)
    plans = plans.copy()
    if p is None:
        plans = _plans_clean(pd.concat([plans, pd.DataFrame([{
            "ID": _new_id(plans, code, when), "Mã": code, "Trạng thái": HOLD, "Ngày tạo": pd.Timestamp(when), "Vùng mua từ": px, "Vùng mua đến": px,
            "Cắt lỗ": stop or np.nan, "Mục tiêu 1": target or np.nan, **_scores(scores), "Ghi chú": "Mua trực tiếp, không qua chờ mua"}])], ignore_index=True))
        p = plans.iloc[-1]
    pid = p["ID"]
    plans.loc[plans["ID"] == pid, "Trạng thái"] = HOLD
    for k, v in _scores(scores).items():                           # điểm tại lúc mua thay điểm lúc lập kế hoạch (nếu có)
        if pd.notna(v):
            plans.loc[plans["ID"] == pid, k] = v
    fee = E.BT_COST["fee"]
    lot = {"Mã": code, "Số lượng": int(qty), "Giá vốn": float(px), "Ngày mua": pd.Timestamp(when),
           "Cắt lỗ": stop or p["Cắt lỗ"], "Mục tiêu": target or p["Mục tiêu 1"], "Ghi chú": note or str(p["Ghi chú"])}
    lots = pd.concat([lots, pd.DataFrame([lot])], ignore_index=True)
    sc = _scores(scores)
    tr = {"ID kế hoạch": pid, "Mã": code, "Loại": "MUA", "Ngày": pd.Timestamp(when), "Giá": float(px), "Số lượng": int(qty),
          "Phí và thuế (đồng)": qty * px * 1000 * fee, "Lãi/lỗ ròng (đồng)": np.nan, "Lãi/lỗ %": np.nan, **sc, "Tín hiệu": signal, "Ghi chú": note}
    trades = _trades_clean(pd.concat([trades, pd.DataFrame([tr])], ignore_index=True))
    return plans, trades, lots, ""


def record_sell(plans: pd.DataFrame, trades: pd.DataFrame, lots: pd.DataFrame, code: str, qty: int, px: float, when,
                scores: dict | None = None, signal: str = "", note: str = "") -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, str]:
    """Ghi một lần BÁN: trừ lô cũ nhất trước (FIFO), tính lãi/lỗ ròng đã chốt, thêm dòng vào sổ. Bán hết thì kế hoạch chuyển ĐÃ BÁN
    (vẫn nằm lại trong bảng và sổ). Không bán quá số đang giữ. Trả (plans, trades, lots, lỗi)."""
    code = str(code).upper().strip()
    if qty <= 0 or px <= 0:
        return plans, trades, lots, "Cần số lượng và giá bán lớn hơn 0."
    L = lots.copy()
    mine = L[L["Mã"] == code].sort_values("Ngày mua", na_position="first")
    held = int(mine["Số lượng"].sum())
    if held <= 0:
        return plans, trades, lots, f"Không có lô {code} nào đang giữ."
    if qty > held:
        return plans, trades, lots, f"Chỉ đang giữ {held:,} cp {code}, không thể bán {int(qty):,}."
    fee, tax = E.BT_COST["fee"], E.BT_COST["sell_tax"]
    left, cost, pids = int(qty), 0.0, []
    for i, r in mine.iterrows():
        if left <= 0:
            break
        take = min(left, int(r["Số lượng"]))
        cost += take * r["Giá vốn"] * 1000 * (1 + fee)             # vốn gồm phí mua
        L.loc[i, "Số lượng"] = int(r["Số lượng"]) - take
        left -= take
    L = L[L["Số lượng"] > 0].reset_index(drop=True)
    proceeds = qty * px * 1000 * (1 - fee - tax)
    pnl = proceeds - cost
    p = active_plan(plans, code)
    plans = plans.copy()
    if p is None:                                               # lô nhập tay từ trước, chưa có kế hoạch: tạo để lịch sử có chỗ bám
        plans = _plans_clean(pd.concat([plans, pd.DataFrame([{
            "ID": _new_id(plans, code, when), "Mã": code, "Trạng thái": HOLD, "Ngày tạo": pd.Timestamp(when), "Vùng mua từ": np.nan,
            "Vùng mua đến": np.nan, "Ghi chú": "Lô có sẵn trước khi dùng sổ giao dịch"}])], ignore_index=True))
        p = plans.iloc[-1]
    pid = p["ID"]
    still = int(L.loc[L["Mã"] == code, "Số lượng"].sum())
    if still == 0:
        plans.loc[plans["ID"] == pid, ["Trạng thái", "Ngày đóng"]] = [SOLD, pd.Timestamp(when)]
    tr = {"ID kế hoạch": pid, "Mã": code, "Loại": "BÁN", "Ngày": pd.Timestamp(when), "Giá": float(px), "Số lượng": int(qty),
          "Phí và thuế (đồng)": qty * px * 1000 * (fee + tax), "Lãi/lỗ ròng (đồng)": pnl, "Lãi/lỗ %": pnl / cost * 100 if cost > 0 else np.nan,
          **_scores(scores), "Tín hiệu": signal, "Ghi chú": note}
    trades = _trades_clean(pd.concat([trades, pd.DataFrame([tr])], ignore_index=True))
    return plans, trades, L[_LOT_COLS], ""


# ------------------------------------------------------------------ TỔNG HỢP ĐỂ BACKTEST
def round_trips(plans: pd.DataFrame, trades: pd.DataFrame) -> pd.DataFrame:
    """Mỗi kế hoạch đã có lệnh bán là một dòng: vốn, tiền thu về, lãi/lỗ ròng đã chốt, số ngày giữ, điểm lúc mua. Kế hoạch còn giữ một phần
    chỉ tính phần đã bán (cột Đã đóng = False)."""
    if trades.empty:
        return pd.DataFrame(columns=["ID", "Mã", "Ngày mua đầu", "Ngày bán cuối", "Ngày giữ", "SL đã bán", "Lãi/lỗ ròng (đồng)", "Lãi/lỗ %",
                                     "Điểm cơ bản", "Điểm kỹ thuật", "Tổng điểm", "Đã đóng"])
    rows = []
    for pid, g in trades.groupby("ID kế hoạch", sort=False):
        s, b = g[g["Loại"] == "BÁN"], g[g["Loại"] == "MUA"]
        if s.empty:
            continue
        pnl = float(s["Lãi/lỗ ròng (đồng)"].sum())
        cost = float((s["Lãi/lỗ ròng (đồng)"] / (s["Lãi/lỗ %"] / 100)).sum())    # vốn của phần đã bán, suy ra từ lãi/lỗ và %
        first_buy = b["Ngày"].min() if not b.empty else pd.NaT
        last_sell = s["Ngày"].max()
        sc = b.iloc[0] if not b.empty else s.iloc[0]
        st = plans.loc[plans["ID"] == pid, "Trạng thái"]
        rows.append({"ID": pid, "Mã": g["Mã"].iat[0], "Ngày mua đầu": first_buy, "Ngày bán cuối": last_sell,
                     "Ngày giữ": (last_sell - first_buy).days if pd.notna(first_buy) else np.nan, "SL đã bán": int(s["Số lượng"].sum()),
                     "Lãi/lỗ ròng (đồng)": pnl, "Lãi/lỗ %": pnl / cost * 100 if cost else np.nan,
                     "Điểm cơ bản": sc["Điểm cơ bản"], "Điểm kỹ thuật": sc["Điểm kỹ thuật"], "Tổng điểm": sc["Tổng điểm"],
                     "Đã đóng": bool(len(st) and st.iat[0] == SOLD)})
    return pd.DataFrame(rows)


def summary(rt: pd.DataFrame) -> dict:
    """Thống kê nhanh trên các kế hoạch đã bán: số lệnh, tỷ lệ thắng, lãi/lỗ trung bình, tổng lãi/lỗ."""
    if rt.empty:
        return {"n": 0, "win": np.nan, "avg_pct": np.nan, "pnl": 0.0, "avg_days": np.nan}
    return {"n": len(rt), "win": float((rt["Lãi/lỗ ròng (đồng)"] > 0).mean() * 100), "avg_pct": float(rt["Lãi/lỗ %"].mean()),
            "pnl": float(rt["Lãi/lỗ ròng (đồng)"].sum()), "avg_days": float(rt["Ngày giữ"].mean())}


def reconcile(plans: pd.DataFrame, lots: pd.DataFrame, asof) -> pd.DataFrame:
    """Đồng bộ trạng thái khi lô bị sửa ngoài sổ (ví dụ xóa lô ở bảng quản lý): kế hoạch ĐANG GIỮ mà không còn lô thì chuyển ĐÃ BÁN;
    mã có lô mà kế hoạch còn CHỜ MUA thì chuyển ĐANG GIỮ. Không đụng vào sổ giao dịch."""
    p = plans.copy()
    held = set(lots["Mã"]) if len(lots) else set()
    gone = (p["Trạng thái"] == HOLD) & ~p["Mã"].isin(held)
    p.loc[gone, ["Trạng thái", "Ngày đóng"]] = [SOLD, pd.Timestamp(asof)]
    p.loc[(p["Trạng thái"] == WAIT) & p["Mã"].isin(held), "Trạng thái"] = HOLD
    return p
