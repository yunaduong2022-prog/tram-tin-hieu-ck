"""Cổ phiếu của tôi: danh mục đang NẮM GIỮ (khác Watchlist là danh sách chỉ để theo dõi).

Dữ liệu
- data/co_phieu_cua_toi.csv: mỗi dòng là một LÔ MUA (Mã, Số lượng, Giá vốn, Ngày mua, Cắt lỗ, Mục tiêu, Ghi chú).
  Một mã có thể có nhiều lô. Giá tính bằng nghìn đồng (22.75 = 22.750 đồng) giống phần còn lại của app.
- data/danh_muc_cai_dat.json: tiền mặt (đồng) và các ngưỡng cảnh báo.
Đây là thông tin tài chính cá nhân: để repo ở chế độ private, hoặc chỉ giữ bản sao lưu trên máy.

Quy ước tính
- Lãi/lỗ ròng = giá trị bán ước tính trừ phí bán và thuế bán, so với vốn đã bỏ ra gồm phí mua (xem engine.BT_COST).
- T+2: lô mua ở phiên T chỉ bán được từ phiên T+2 (đếm theo ngày làm việc T2-T6, chưa trừ ngày lễ).
- Rủi ro đến cắt lỗ = số tiền sẽ mất thêm nếu giá đi từ giá hiện tại xuống đúng mức cắt lỗ của các lô đã đặt cắt lỗ.
- Tín hiệu hệ thống lấy lại từ my_watchlist.build_view (cùng nguồn với Chờ mua / Bán - Chốt lời). Chỉ để tham khảo,
  không phải khuyến nghị đầu tư.
"""
from __future__ import annotations

import html as _html
import inspect
import json
import os
import re

import numpy as np
import pandas as pd
import streamlit as st

import engine as E
import my_watchlist as MW

PATH = "data/co_phieu_cua_toi.csv"
SETTINGS_PATH = "data/danh_muc_cai_dat.json"
COLS = ["Mã", "Số lượng", "Giá vốn", "Ngày mua", "Cắt lỗ", "Mục tiêu", "Ghi chú"]
DEFAULTS = {"cash": 0.0,            # tiền mặt (đồng)
            "max_pos": 20.0,        # % NAV tối đa cho một mã
            "max_sector": 40.0,     # % NAV tối đa cho một ngành
            "max_risk": 6.0,        # % NAV tối đa có thể mất nếu mọi lô chạm cắt lỗ
            "risk_per_trade": 1.0}  # % NAV rủi ro cho một lệnh mới (dùng ở máy tính khối lượng)
NEAR_STOP = 3.0                      # % cách cắt lỗ để cảnh báo "gần cắt lỗ"
LOT = 100
_DF = ({"width": "stretch"} if "width" in inspect.signature(st.dataframe).parameters else {"use_container_width": True})


# ------------------------------------------------------------------ DỮ LIỆU LÔ MUA
def _clean(d: pd.DataFrame) -> pd.DataFrame:
    d = d.copy()
    for c in COLS:
        if c not in d.columns:
            d[c] = np.nan if c not in ("Mã", "Ghi chú") else ""
    d["Mã"] = d["Mã"].astype(str).str.upper().str.strip()
    d = d[d["Mã"].str.fullmatch(r"[A-Z0-9]{2,10}")]
    for c in ("Số lượng", "Giá vốn", "Cắt lỗ", "Mục tiêu"):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d["Ngày mua"] = pd.to_datetime(d["Ngày mua"], errors="coerce", format="mixed", dayfirst=True)
    d["Ghi chú"] = d["Ghi chú"].fillna("").astype(str)
    d = d[(d["Số lượng"] > 0) & (d["Giá vốn"] > 0)]
    d["Số lượng"] = d["Số lượng"].round().astype(int)
    for c in ("Cắt lỗ", "Mục tiêu"):
        d.loc[d[c] <= 0, c] = np.nan
    return d[COLS].reset_index(drop=True)


def load(path: str = PATH) -> pd.DataFrame:
    if os.path.exists(path):
        try:
            return _clean(pd.read_csv(path, dtype={"Mã": str, "Ghi chú": str}, encoding="utf-8-sig"))
        except Exception:  # noqa: BLE001
            pass
    return _clean(pd.DataFrame(columns=COLS))


def save(d: pd.DataFrame, path: str = PATH) -> str:
    """Trả '' nếu lưu được, ngược lại là thông báo lỗi."""
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        out = _clean(d)
        out["Ngày mua"] = out["Ngày mua"].dt.strftime("%d/%m/%Y")
        out.to_csv(path, index=False, encoding="utf-8-sig")
        return ""
    except Exception as e:  # noqa: BLE001
        return str(e)


def load_settings(path: str = SETTINGS_PATH) -> dict:
    s = dict(DEFAULTS)
    try:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                s.update({k: float(v) for k, v in json.load(f).items() if k in DEFAULTS})
    except Exception:  # noqa: BLE001
        pass
    return s


def save_settings(s: dict, path: str = SETTINGS_PATH) -> str:
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({k: float(s[k]) for k in DEFAULTS}, f, ensure_ascii=False, indent=1)
        return ""
    except Exception as e:  # noqa: BLE001
        return str(e)


# ------------------------------------------------------------------ TÍNH TOÁN (thuần pandas, dễ kiểm thử)
def sellable_mask(lots: pd.DataFrame, asof) -> pd.Series:
    """Lô đã bán được theo T+2. Không có ngày mua thì coi như bán được."""
    asof = pd.Timestamp(asof).normalize()
    ok = []
    for d in lots["Ngày mua"]:
        if pd.isna(d):
            ok.append(True)
        else:
            ok.append(int(np.busday_count(d.date(), asof.date())) >= E.BT_COST["lock_bars"])
    return pd.Series(ok, index=lots.index, dtype=bool)


def _wavg(values: pd.Series, weights: pd.Series) -> float:
    m = values.notna() & (weights > 0)
    return float(np.average(values[m], weights=weights[m])) if m.any() else np.nan


def aggregate(lots: pd.DataFrame, prices: dict, asof, sectors: dict | None = None) -> pd.DataFrame:
    """Gộp các lô theo mã. Tiền tính bằng đồng (giá nghìn đồng x 1000)."""
    cols = ["Mã", "Số lượng", "Bán được", "Giá vốn", "Giá", "Giá trị", "Vốn bỏ ra", "Lãi/lỗ", "Lãi/lỗ %", "Cắt lỗ", "Mục tiêu",
            "Rủi ro đến cắt lỗ", "Giá trị chưa đặt cắt lỗ", "Ngành", "Ngày mua đầu", "Ghi chú"]
    if lots.empty:
        return pd.DataFrame(columns=cols)
    fee, tax = E.BT_COST["fee"], E.BT_COST["sell_tax"]
    L = lots.copy()
    L["_ok"] = sellable_mask(L, asof)
    L["_px"] = L["Mã"].map(lambda c: prices.get(c, np.nan))
    rows = []
    for code, g in L.groupby("Mã", sort=False):
        px = g["_px"].iloc[0]
        q = int(g["Số lượng"].sum())
        cost_px = _wavg(g["Giá vốn"], g["Số lượng"])
        invested = float((g["Số lượng"] * g["Giá vốn"]).sum() * 1000 * (1 + fee))
        value = q * px * 1000 if pd.notna(px) else np.nan
        net = value * (1 - fee - tax) - invested if pd.notna(value) else np.nan
        has_sl = g["Cắt lỗ"].notna()
        risk = float((g.loc[has_sl, "Số lượng"] * (px - g.loc[has_sl, "Cắt lỗ"]).clip(lower=0)).sum() * 1000) if pd.notna(px) else np.nan
        unprot = float(g.loc[~has_sl, "Số lượng"].sum() * px * 1000) if pd.notna(px) else np.nan
        notes = "; ".join(dict.fromkeys(n.strip() for n in g["Ghi chú"] if n.strip()))
        rows.append({"Mã": code, "Số lượng": q, "Bán được": int(g.loc[g["_ok"], "Số lượng"].sum()), "Giá vốn": cost_px, "Giá": px,
                     "Giá trị": value, "Vốn bỏ ra": invested, "Lãi/lỗ": net,
                     "Lãi/lỗ %": net / invested * 100 if invested > 0 and pd.notna(net) else np.nan,
                     "Cắt lỗ": _wavg(g["Cắt lỗ"], g["Số lượng"]), "Mục tiêu": _wavg(g["Mục tiêu"], g["Số lượng"]),
                     "Rủi ro đến cắt lỗ": risk, "Giá trị chưa đặt cắt lỗ": unprot,
                     "Ngành": (sectors or {}).get(code, "Khác"), "Ngày mua đầu": g["Ngày mua"].min(), "Ghi chú": notes})
    return pd.DataFrame(rows, columns=cols)


def portfolio_totals(pos: pd.DataFrame, cash: float) -> dict:
    mv = float(pos["Giá trị"].sum(skipna=True)) if not pos.empty else 0.0
    nav = mv + max(cash, 0.0)
    inv = float(pos["Vốn bỏ ra"].sum()) if not pos.empty else 0.0
    pl = float(pos["Lãi/lỗ"].sum(skipna=True)) if not pos.empty else 0.0
    risk = float(pos["Rủi ro đến cắt lỗ"].sum(skipna=True)) if not pos.empty else 0.0
    return {"mv": mv, "cash": max(cash, 0.0), "nav": nav, "invested": inv, "pl": pl, "pl_pct": pl / inv * 100 if inv > 0 else np.nan,
            "risk": risk, "risk_pct": risk / nav * 100 if nav > 0 else np.nan,
            "unprot": float(pos["Giá trị chưa đặt cắt lỗ"].sum(skipna=True)) if not pos.empty else 0.0}


def sector_weights(pos: pd.DataFrame, nav: float) -> pd.DataFrame:
    if pos.empty or nav <= 0:
        return pd.DataFrame(columns=["Ngành", "Giá trị", "% NAV"])
    s = pos.groupby("Ngành")["Giá trị"].sum().sort_values(ascending=False).reset_index()
    s["% NAV"] = s["Giá trị"] / nav * 100
    return s


def action_text(signal: str, sellable_all: bool, near_stop: bool) -> str:
    """Gợi ý theo kế hoạch của bạn + tín hiệu hệ thống (tham khảo, không phải khuyến nghị)."""
    wait = "" if sellable_all else " (một phần chưa về T+2, chỉ bán được phần đã về)"
    if "Chạm cắt lỗ" in signal:
        return "Đã chạm mức cắt lỗ bạn đặt: thực hiện theo kế hoạch" + wait
    if "BÁN" in signal:
        return "Hệ thống báo bán: cân nhắc hạ tỷ trọng hoặc thoát" + wait
    if "Đạt mục tiêu" in signal:
        return "Đạt mục tiêu: cân nhắc chốt lời một phần và dời cắt lỗ lên"
    if "CHỐT LỜI" in signal:
        return "Hệ thống báo chốt lời: cân nhắc chốt một phần"
    if "Cảnh báo" in signal:
        return "Có cảnh báo rủi ro / quá đà: không mua thêm, theo dõi sát"
    if near_stop:
        return "Gần mức cắt lỗ: chuẩn bị kịch bản"
    return "Tiếp tục nắm giữ theo kế hoạch"


def build_positions_view(lots: pd.DataFrame, wb: pd.DataFrame, res: pd.DataFrame, asof, cash: float = 0.0):
    """Trả (bảng vị thế đã gắn tín hiệu, tổng hợp, bảng ngành)."""
    prices = {}
    if "Giá" in res.columns:
        prices = dict(zip(res["Mã"].astype(str).str.upper(), pd.to_numeric(res["Giá"], errors="coerce")))
    if "Giá" in wb.columns:                                  # giá trong bảng Chờ mua (nếu có) ưu tiên
        prices.update({str(c).upper(): p for c, p in zip(wb["Mã"], pd.to_numeric(wb["Giá"], errors="coerce")) if pd.notna(p)})
    sectors = {}
    if "Nhóm" in res.columns:
        sectors = {str(c).upper(): (str(g).split(",")[0].strip() or "Khác") for c, g in zip(res["Mã"], res["Nhóm"])}
    pos = aggregate(lots, prices, asof, sectors)
    tot = portfolio_totals(pos, cash)
    if pos.empty:
        return pos, tot, sector_weights(pos, tot["nav"])
    base = tot["nav"] if tot["nav"] > 0 else np.nan
    pos["% NAV"] = pos["Giá trị"] / base * 100
    v = MW.build_view(pos[["Mã", "Giá vốn", "Mục tiêu", "Cắt lỗ", "Ghi chú"]], wb, res)
    keep = [c for c in ("Mã", "Tín hiệu", "Trạng thái", "Lý do", "Hành động", "Score", "RS20", "Wyckoff") if c in v.columns]
    pos = pos.merge(v[keep], on="Mã", how="left")
    pos["Cách cắt lỗ %"] = np.where(pos["Cắt lỗ"] > 0, (pos["Giá"] / pos["Cắt lỗ"] - 1) * 100, np.nan)
    pos["Cách mục tiêu %"] = np.where(pos["Mục tiêu"] > 0, (pos["Mục tiêu"] / pos["Giá"] - 1) * 100, np.nan)
    sig = pos["Tín hiệu"].fillna("— Chưa có dữ liệu")
    pos["Gợi ý"] = [action_text(s, int(b) >= int(q), pd.notna(d) and 0 <= d <= NEAR_STOP)
                    for s, b, q, d in zip(sig, pos["Bán được"], pos["Số lượng"], pos["Cách cắt lỗ %"])]
    pri = sig.map(lambda s: 0 if "Chạm cắt lỗ" in s else 1 if ("BÁN" in s or "CHỐT LỜI" in s) else 2 if "Cảnh báo" in s
                  else 3 if "Đạt mục tiêu" in s else 4)
    pos = pos.assign(_p=pri.values).sort_values(["_p", "% NAV"], ascending=[True, False]).drop(columns="_p").reset_index(drop=True)
    return pos, tot, sector_weights(pos, tot["nav"])


def alerts(pos: pd.DataFrame, tot: dict, sec: pd.DataFrame, cfg: dict) -> list[tuple[int, str]]:
    """Danh sách (mức độ 0 = gấp nhất, nội dung)."""
    out = []
    if pos.empty:
        return out
    for _, r in pos.iterrows():
        s = str(r.get("Tín hiệu", ""))
        if "Chạm cắt lỗ" in s:
            out.append((0, f"{r['Mã']}: giá đã chạm mức cắt lỗ của bạn ({r['Cắt lỗ']:.1f})."
                           + ("" if r["Bán được"] >= r["Số lượng"] else f" Mới bán được {int(r['Bán được']):,}/{int(r['Số lượng']):,} cp (T+2).")))
        elif pd.notna(r.get("Cách cắt lỗ %")) and 0 <= r["Cách cắt lỗ %"] <= NEAR_STOP:
            out.append((1, f"{r['Mã']}: chỉ cách cắt lỗ {r['Cách cắt lỗ %']:.1f}%."))
        if "BÁN" in s:
            out.append((1, f"{r['Mã']}: hệ thống đang báo BÁN ({str(r.get('Lý do', ''))[:90]})."))
        elif "CHỐT LỜI" in s:
            out.append((2, f"{r['Mã']}: hệ thống báo CHỐT LỜI."))
        elif "Đạt mục tiêu" in s:
            out.append((2, f"{r['Mã']}: đã đạt mục tiêu {r['Mục tiêu']:.1f}."))
        if pd.notna(r.get("% NAV")) and r["% NAV"] > cfg["max_pos"]:
            out.append((2, f"{r['Mã']}: chiếm {r['% NAV']:.1f}% NAV, vượt ngưỡng {cfg['max_pos']:.0f}%."))
    for _, r in sec.iterrows():
        if r["% NAV"] > cfg["max_sector"] and r["Ngành"] != "Khác":
            out.append((2, f"Ngành {r['Ngành']}: {r['% NAV']:.1f}% NAV, vượt ngưỡng {cfg['max_sector']:.0f}%."))
    if pd.notna(tot["risk_pct"]) and tot["risk_pct"] > cfg["max_risk"]:
        out.append((1, f"Tổng rủi ro nếu mọi lô chạm cắt lỗ là {tot['risk_pct']:.1f}% NAV, vượt ngưỡng {cfg['max_risk']:.0f}%."))
    if tot["unprot"] > 0:
        n = int((pos["Giá trị chưa đặt cắt lỗ"] > 0).sum())
        out.append((2, f"{n} mã có lô chưa đặt cắt lỗ, tổng {tot['unprot'] / 1e6:,.1f} triệu đồng không nằm trong con số rủi ro."))
    return sorted(out, key=lambda x: x[0])


def size_new_position(nav: float, risk_pct: float, entry: float, stop: float, cash: float | None = None,
                      max_pos_pct: float | None = None, risk_room_pct: float | None = None) -> dict:
    """Số cổ phiếu (làm tròn xuống lô 100) sao cho nếu chạm cắt lỗ chỉ mất risk_pct % NAV. Giá nghìn đồng."""
    if nav <= 0 or entry <= 0 or stop <= 0 or stop >= entry:
        return {"qty": 0, "why": "Cần NAV > 0 và giá cắt lỗ thấp hơn giá mua."}
    fee, tax = E.BT_COST["fee"], E.BT_COST["sell_tax"]
    loss_per_share = (entry - stop) * 1000 + entry * 1000 * fee + stop * 1000 * (fee + tax)      # lỗ khi cắt lỗ, đã gồm phí và thuế
    budget = nav * risk_pct / 100
    if risk_room_pct is not None:
        budget = min(budget, nav * max(risk_room_pct, 0) / 100)
    q = budget / loss_per_share
    limits = {"rủi ro": q}
    if max_pos_pct:
        limits["tỷ trọng tối đa một mã"] = nav * max_pos_pct / 100 / (entry * 1000)
    if cash is not None and cash > 0:
        limits["tiền mặt"] = cash / (entry * 1000 * (1 + fee))
    why = min(limits, key=limits.get)
    qty = int(min(limits.values()) // LOT * LOT)
    return {"qty": qty, "why": why, "value": qty * entry * 1000, "risk": qty * loss_per_share, "risk_pct": qty * loss_per_share / nav * 100,
            "weight": qty * entry * 1000 / nav * 100}


# ------------------------------------------------------------------ GIAO DIỆN
def _vnd(x: float) -> str:
    return "—" if pd.isna(x) else f"{x / 1e6:,.1f} tr"


def render(wb: pd.DataFrame, res: pd.DataFrame, on_chart, asof) -> None:
    """wb: bảng _wb_table(); res: res_df; on_chart(code): mở biểu đồ; asof: ngày dữ liệu mới nhất."""
    ver = st.session_state.setdefault("pf_ver", 0)
    st.caption("Danh mục bạn đang NẮM GIỮ (khác Watchlist chỉ để theo dõi). Mỗi dòng nhập là một lô mua, một mã có thể có nhiều lô. "
               "Chỉ để tham khảo, không phải khuyến nghị đầu tư.")
    cfg = load_settings()
    lots = load()
    available = set(res["Mã"].astype(str).str.upper())

    pos, tot, sec = build_positions_view(lots, wb, res, asof, cfg["cash"])

    # 1) tổng quan
    if lots.empty:
        st.info("Chưa có lô nào. Thêm lô mua ở phần \"Thêm lô mua\" bên dưới, hoặc nhập từ file CSV ở mục Quản lý.")
    else:
        m = st.columns(5)
        m[0].metric("GIÁ TRỊ CỔ PHIẾU", _vnd(tot["mv"]))
        m[1].metric("TỔNG TÀI SẢN (NAV)", _vnd(tot["nav"]), help="Cổ phiếu + tiền mặt bạn nhập ở mục Cài đặt." if cfg["cash"] > 0 else
                    "Chưa nhập tiền mặt nên NAV chỉ gồm cổ phiếu và tỷ trọng tính trên giá trị cổ phiếu.")
        m[2].metric("LÃI/LỖ RÒNG TẠM TÍNH", _vnd(tot["pl"]), None if pd.isna(tot["pl_pct"]) else f"{tot['pl_pct']:+.1f}%",
                    help="Đã trừ phí mua, phí bán và thuế bán 0,1%.")
        m[3].metric("RỦI RO ĐẾN CẮT LỖ", "—" if tot["risk"] == 0 else _vnd(tot["risk"]),
                    None if pd.isna(tot["risk_pct"]) or tot["risk"] == 0 else f"{tot['risk_pct']:.1f}% NAV", delta_color="off",
                    help="Số tiền sẽ mất thêm nếu giá hiện tại đi xuống đúng mức cắt lỗ của các lô đã đặt cắt lỗ.")
        m[4].metric("SỐ MÃ", len(pos), f"{int((pos['Số lượng'] > pos['Bán được']).sum())} mã còn lô chờ T+2" if len(pos) else None, delta_color="off")

        al = alerts(pos, tot, sec, cfg)
        if al:
            st.subheader("Cần chú ý")
            for lvl, msg in al:
                (st.error if lvl == 0 else st.warning if lvl == 1 else st.info)(msg)
        else:
            st.success("Không có cảnh báo nào theo kế hoạch và ngưỡng bạn đặt.")

        st.subheader("Vị thế")
        cols = ["Mã", "Tín hiệu", "Gợi ý", "Số lượng", "Bán được", "Giá vốn", "Giá", "Lãi/lỗ %", "% NAV", "Cắt lỗ", "Cách cắt lỗ %",
                "Mục tiêu", "Cách mục tiêu %", "Ngành", "Ghi chú"]
        show = pos[[c for c in cols if c in pos.columns]]
        nc = st.column_config.NumberColumn
        st.dataframe(show, hide_index=True, column_config={
            "Số lượng": nc(format="%d"), "Bán được": nc(format="%d", help="Số cổ phiếu đã về tài khoản theo T+2"),
            "Giá vốn": nc(format="%.2f", help="Bình quân gia quyền các lô, chưa gồm phí"), "Giá": nc(format="%.2f"),
            "Lãi/lỗ %": nc(format="%+.1f%%", help="Ròng sau phí và thuế nếu bán ở giá hiện tại"), "% NAV": nc(format="%.1f%%"),
            "Cắt lỗ": nc(format="%.2f"), "Cách cắt lỗ %": nc(format="%+.1f%%"), "Mục tiêu": nc(format="%.2f"),
            "Cách mục tiêu %": nc(format="%+.1f%%")}, **_DF)

        c1, c2 = st.columns([3, 2])
        with c1:
            st.subheader("Tỷ trọng theo ngành")
            if len(sec):
                st.bar_chart(sec.set_index("Ngành")["% NAV"], horizontal=True) if "horizontal" in inspect.signature(st.bar_chart).parameters \
                    else st.bar_chart(sec.set_index("Ngành")["% NAV"])
                st.caption(f"Ngưỡng cảnh báo mỗi ngành: {cfg['max_sector']:.0f}% NAV. Mỗi mã tính vào nhóm đầu tiên trong cột Nhóm.")
        with c2:
            st.subheader("Xem chi tiết mã")
            pick = st.selectbox("Chọn mã", list(pos["Mã"]), key="pf_pick", label_visibility="collapsed")
            r = pos[pos["Mã"] == pick].iloc[0]
            st.markdown(f"**{pick}** · {r.get('Tín hiệu', '—')}")
            if pd.notna(r.get("Lý do")):
                st.write(str(r["Lý do"]))
            st.caption(f"Gợi ý: {r['Gợi ý']}")
            if st.button("📊 Xem biểu đồ", key="pf_chart", use_container_width=True):
                on_chart(pick)

    # 2) thêm lô mua
    st.subheader("Thêm lô mua")
    with st.form("pf_add", clear_on_submit=True):
        a = st.columns([1.2, 1.2, 1.2, 1.4])
        code = a[0].text_input("Mã", placeholder="HPG").upper().strip()
        qty = a[1].number_input("Số lượng (cp)", min_value=0, step=LOT, value=0)
        px = a[2].number_input("Giá mua (nghìn đồng)", min_value=0.0, step=0.05, format="%.2f", help="Ví dụ 26.45 = 26.450 đồng")
        dt = a[3].date_input("Ngày mua", value=pd.Timestamp(asof).date())
        b = st.columns([1.2, 1.2, 2.6])
        sl = b[0].number_input("Cắt lỗ (nghìn đồng)", min_value=0.0, step=0.05, format="%.2f", help="0 = chưa đặt")
        tp = b[1].number_input("Mục tiêu (nghìn đồng)", min_value=0.0, step=0.05, format="%.2f", help="0 = chưa đặt")
        note = b[2].text_input("Ghi chú", placeholder="Lý do mua, kế hoạch...")
        go = st.form_submit_button("➕ Thêm lô", use_container_width=False)
    if go:
        if not re.fullmatch(r"[A-Z0-9]{2,10}", code or ""):
            st.warning("Mã chưa hợp lệ.")
        elif qty <= 0 or px <= 0:
            st.warning("Cần số lượng và giá mua lớn hơn 0.")
        elif sl and sl >= px:
            st.warning("Giá cắt lỗ phải thấp hơn giá mua.")
        elif tp and tp <= px:
            st.warning("Mục tiêu phải cao hơn giá mua.")
        else:
            new = pd.DataFrame([{"Mã": code, "Số lượng": qty, "Giá vốn": px, "Ngày mua": pd.Timestamp(dt), "Cắt lỗ": sl or np.nan,
                                 "Mục tiêu": tp or np.nan, "Ghi chú": note}])
            err = save(pd.concat([lots, new], ignore_index=True))
            st.session_state["pf_ver"] = ver + 1
            if err:
                st.warning(f"Chưa lưu được vào file: {err}")
            else:
                if code not in available:
                    st.session_state["pf_msg"] = f"Đã thêm {code}. Lưu ý: app chưa có dữ liệu giá của mã này nên chưa tính được lãi/lỗ và tín hiệu."
                st.rerun()
    if st.session_state.get("pf_msg"):
        st.warning(st.session_state.pop("pf_msg"))

    # 3) máy tính khối lượng
    with st.expander("🧮 Tính khối lượng mua theo rủi ro", expanded=False):
        st.caption("Cho biết nên mua bao nhiêu cổ phiếu để nếu chạm cắt lỗ chỉ mất đúng % NAV bạn chấp nhận (đã gồm phí và thuế).")
        s = st.columns(4)
        e = s[0].number_input("Giá dự kiến mua", min_value=0.0, step=0.05, format="%.2f", key="pf_e")
        sp = s[1].number_input("Giá cắt lỗ", min_value=0.0, step=0.05, format="%.2f", key="pf_s")
        rp = s[2].number_input("Rủi ro cho lệnh này (% NAV)", min_value=0.1, max_value=10.0, step=0.1, value=float(cfg["risk_per_trade"]), key="pf_r")
        base_nav = tot["nav"]
        s[3].metric("NAV dùng để tính", _vnd(base_nav))
        if e > 0 and sp > 0:
            room = cfg["max_risk"] - (tot["risk_pct"] if pd.notna(tot["risk_pct"]) else 0)
            z = size_new_position(base_nav, rp, e, sp, cash=cfg["cash"] if cfg["cash"] > 0 else None, max_pos_pct=cfg["max_pos"], risk_room_pct=room)
            if z["qty"] > 0:
                st.success(f"Nên mua tối đa **{z['qty']:,} cp** (giá trị {z['value'] / 1e6:,.1f} triệu, {z['weight']:.1f}% NAV). "
                           f"Nếu chạm cắt lỗ mất khoảng {z['risk'] / 1e6:,.2f} triệu ({z['risk_pct']:.2f}% NAV). Giới hạn bởi: {z['why']}.")
            else:
                st.warning(f"Không mua được lô nào: {z['why']}" if z.get("why") and base_nav <= 0 else
                           f"Với các giới hạn hiện tại không đủ để mua một lô {LOT} cp (giới hạn bởi: {z['why']}).")
            if room <= 0:
                st.caption("Tổng rủi ro danh mục đã chạm ngưỡng nên không còn room cho lệnh mới.")
        if base_nav <= 0:
            st.caption("Hãy nhập tiền mặt ở mục Cài đặt hoặc thêm lô mua để có NAV.")

    # 4) quản lý / cài đặt
    with st.expander("⚙️ Quản lý lô mua · Cài đặt · Sao lưu", expanded=False):
        st.markdown("**Cài đặt**")
        c = st.columns(5)
        new_cfg = {
            "cash": c[0].number_input("Tiền mặt (đồng)", min_value=0.0, step=1_000_000.0, value=float(cfg["cash"]), format="%.0f", key=f"pf_cash_{ver}"),
            "max_pos": c[1].number_input("Tối đa / mã (% NAV)", 1.0, 100.0, float(cfg["max_pos"]), 1.0, key=f"pf_mp_{ver}"),
            "max_sector": c[2].number_input("Tối đa / ngành (% NAV)", 1.0, 100.0, float(cfg["max_sector"]), 1.0, key=f"pf_ms_{ver}"),
            "max_risk": c[3].number_input("Tổng rủi ro tối đa (% NAV)", 0.5, 50.0, float(cfg["max_risk"]), 0.5, key=f"pf_mr_{ver}"),
            "risk_per_trade": c[4].number_input("Rủi ro mỗi lệnh (% NAV)", 0.1, 10.0, float(cfg["risk_per_trade"]), 0.1, key=f"pf_rt_{ver}"),
        }
        if st.button("💾 Lưu cài đặt", key="pf_save_cfg"):
            err = save_settings(new_cfg)
            st.session_state["pf_ver"] = ver + 1
            st.warning(f"Chưa lưu được: {err}") if err else st.rerun()

        if not lots.empty:
            st.markdown("**Các lô mua** (sửa trực tiếp, tick Xóa rồi bấm Lưu để bỏ lô; bán một phần thì giảm Số lượng)")
            ed = st.data_editor(lots.assign(**{"Xóa": False}), hide_index=True, key=f"pf_editor_{ver}", disabled=["Mã"],
                                column_config={"Số lượng": st.column_config.NumberColumn(format="%d", min_value=0, step=LOT),
                                               "Giá vốn": st.column_config.NumberColumn(format="%.2f", min_value=0.0),
                                               "Ngày mua": st.column_config.DateColumn(format="DD/MM/YYYY"),
                                               "Cắt lỗ": st.column_config.NumberColumn(format="%.2f", min_value=0.0),
                                               "Mục tiêu": st.column_config.NumberColumn(format="%.2f", min_value=0.0),
                                               "Xóa": st.column_config.CheckboxColumn("Xóa", default=False)}, **_DF)
            if st.button("💾 Lưu thay đổi lô mua", key="pf_save"):
                keep = ed[~ed["Xóa"].astype(bool)][COLS]
                err = save(keep)
                st.session_state["pf_ver"] = ver + 1
                st.warning(f"Chưa lưu được: {err}") if err else st.rerun()
            _o = lots.assign(**{"Ngày mua": lots["Ngày mua"].dt.strftime("%d/%m/%Y")})
            st.download_button("⬇️ Sao lưu lô mua (tải CSV)", _o.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig"),
                               file_name="co_phieu_cua_toi.csv", mime="text/csv")
        up = st.file_uploader("Nhập từ CSV (cột Mã, Số lượng, Giá vốn, Ngày mua, Cắt lỗ, Mục tiêu, Ghi chú)", type=["csv"], key=f"pf_up_{ver}")
        mode = st.radio("Cách nhập", ["Thêm vào các lô hiện có", "Thay thế toàn bộ"], horizontal=True, key=f"pf_mode_{ver}")
        if up is not None and st.button("📥 Nhập", key="pf_import"):
            try:
                inc = _clean(pd.read_csv(up, dtype={"Mã": str, "Ghi chú": str}, encoding="utf-8-sig"))
                merged = inc if mode.startswith("Thay") else pd.concat([lots, inc], ignore_index=True)
                err = save(merged)
                st.session_state["pf_ver"] = ver + 1
            except Exception as ex:  # noqa: BLE001
                st.error(f"Không đọc được file: {ex}")
            else:
                st.warning(f"Chưa lưu được: {err}") if err else st.rerun()
        st.caption("⚠ Đây là dữ liệu tài chính cá nhân. Nếu repo GitHub ở chế độ public thì file data/co_phieu_cua_toi.csv và "
                   "data/danh_muc_cai_dat.json sẽ lộ ra ngoài: hãy để repo private hoặc không đẩy hai file này lên (thêm vào .gitignore). "
                   "Trên Streamlit Cloud, file ghi lúc chạy mất khi app khởi động lại: hãy bấm Sao lưu thường xuyên. "
                   "App chưa lưu lịch sử lệnh đã bán nên lãi/lỗ đã chốt cần ghi riêng.")
