"""Giao diện "Cổ phiếu của tôi" theo vòng đời: 🟡 Chờ mua -> 🟢 Đang giữ -> 🔴 Đã bán, kèm lịch sử giao dịch để backtest.
Logic nằm ở my_trades.py (thuần pandas). Hàm build_* ở đây cũng không gọi Streamlit nên kiểm thử được.

Điểm kỹ thuật tạm lấy từ cột Score của bảng lọc chính (0-10, engine.internal_score). Điểm cơ bản và Tổng điểm CHƯA có công thức
nên để trống: khi có công thức của mục khuyến nghị khách hàng, sửa duy nhất hàm scores_for().
"""
from __future__ import annotations

import inspect

import numpy as np
import pandas as pd
import streamlit as st

import my_trades as MT

_DF = ({"width": "stretch"} if "width" in inspect.signature(st.dataframe).parameters else {"use_container_width": True})


# ------------------------------------------------------------------ ĐIỂM
def scores_for(code: str, res: pd.DataFrame) -> dict:
    """{"fund", "tech", "total"} của mã. Chỉ có điểm kỹ thuật (Score) vì chưa có công thức điểm cơ bản; thiếu thì NaN."""
    tech = np.nan
    if "Score" in res.columns:
        m = res.loc[res["Mã"].astype(str).str.upper() == code.upper(), "Score"]
        if len(m) and pd.notna(m.iloc[0]):
            tech = float(m.iloc[0])
    return {"fund": np.nan, "tech": tech, "total": np.nan}


# ------------------------------------------------------------------ BẢNG (thuần pandas)
def _prices(res: pd.DataFrame, wb: pd.DataFrame) -> dict:
    p = {}
    if "Giá" in res.columns:
        p = dict(zip(res["Mã"].astype(str).str.upper(), pd.to_numeric(res["Giá"], errors="coerce")))
    if "Giá" in wb.columns:
        p.update({str(c).upper(): v for c, v in zip(wb["Mã"], pd.to_numeric(wb["Giá"], errors="coerce")) if pd.notna(v)})
    return p


def build_wait(plans: pd.DataFrame, res: pd.DataFrame, wb: pd.DataFrame) -> pd.DataFrame:
    """Bảng CHỜ MUA: giá hiện tại, cách vùng mua, hành động (trong vùng = MUA NGAY, trên vùng = CHỜ MUA, dưới vùng = vùng đã thủng)."""
    w = plans[plans["Trạng thái"] == MT.WAIT].copy()
    px = _prices(res, wb)
    w["Giá hiện tại"] = w["Mã"].map(px)
    g, lo, hi = w["Giá hiện tại"], w["Vùng mua từ"], w["Vùng mua đến"]
    w["Cách vùng mua %"] = np.where(g > hi, (g / hi - 1) * 100, np.where(g < lo, (g / lo - 1) * 100, 0.0))
    w["Lệnh"] = np.where(g.isna(), "—", np.where((g.round(2) >= lo.round(2)) & (g.round(2) <= hi.round(2)), "MUA NGAY",
                                                  np.where(g > hi, "CHỜ MUA", "DƯỚI VÙNG")))
    w["Hành động"] = w["Lệnh"].map({"MUA NGAY": "Giá trong vùng mua: có thể mua, nên chia lệnh.",
                                    "CHỜ MUA": "Không mua đuổi. Chờ về vùng mua.",
                                    "DƯỚI VÙNG": "Giá đã xuống dưới vùng mua: chờ xác nhận, cân nhắc hủy kế hoạch."}).fillna("Chưa có giá")
    w["Vùng mua"] = w.apply(lambda r: f"{r['Vùng mua từ']:.2f} - {r['Vùng mua đến']:.2f}", axis=1)
    return w.sort_values("Cách vùng mua %", key=lambda s: s.abs()).reset_index(drop=True)


def build_hold(plans: pd.DataFrame, lots: pd.DataFrame, res: pd.DataFrame, wb: pd.DataFrame) -> pd.DataFrame:
    """Bảng ĐANG GIỮ: khối lượng, giá vốn bình quân (có phí mua), lãi/lỗ ròng tạm tính, tín hiệu hệ thống hiện tại."""
    import engine as E
    h = plans[plans["Trạng thái"] == MT.HOLD].copy()
    px = _prices(res, wb)
    fee, tax = E.BT_COST["fee"], E.BT_COST["sell_tax"]
    sig = {}
    if "Trạng thái" in wb.columns:
        sig = dict(zip(wb["Mã"].astype(str).str.upper(), wb["Trạng thái"]))
    rows = []
    for _, p in h.iterrows():
        g = lots[lots["Mã"] == p["Mã"]]
        q = int(g["Số lượng"].sum())
        if q <= 0:
            continue
        cost = float((g["Số lượng"] * g["Giá vốn"]).sum() * 1000 * (1 + fee))
        price = px.get(p["Mã"], np.nan)
        net = q * price * 1000 * (1 - fee - tax) - cost if pd.notna(price) else np.nan
        sl = g["Cắt lỗ"].dropna()
        tp = g["Mục tiêu"].dropna()
        rows.append({"ID": p["ID"], "Mã": p["Mã"], "Ngày mua": g["Ngày mua"].min(), "Khối lượng": q, "Giá vốn": cost / q / 1000 / (1 + fee) if q else np.nan,
                     "Giá hiện tại": price, "Lãi/lỗ (đồng)": net, "Lãi/lỗ %": net / cost * 100 if cost > 0 and pd.notna(net) else np.nan,
                     "Cắt lỗ": float(sl.iloc[-1]) if len(sl) else np.nan, "Mục tiêu": float(tp.iloc[-1]) if len(tp) else np.nan,
                     "Điểm cơ bản": p["Điểm cơ bản"], "Điểm kỹ thuật": p["Điểm kỹ thuật"], "Tổng điểm": p["Tổng điểm"],
                     "Tín hiệu hiện tại": sig.get(p["Mã"], "—")})
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    px_, sl_, tp_ = out["Giá hiện tại"], out["Cắt lỗ"], out["Mục tiêu"]
    out["Hành động"] = np.where((sl_ > 0) & (px_ <= sl_), "Chạm cắt lỗ: thực hiện theo kế hoạch.",
                        np.where((tp_ > 0) & (px_ >= tp_), "Đạt mục tiêu: cân nhắc chốt lời, dời cắt lỗ lên.", "Nắm giữ"))
    return out


# ------------------------------------------------------------------ GIAO DIỆN
def _vnd(x) -> str:
    return "—" if pd.isna(x) else f"{x:,.0f} đ"


def _save_all(plans, trades, lots, save_lots) -> str:
    """Ghi sổ giao dịch TRƯỚC (quan trọng nhất), rồi kế hoạch, rồi lô. Trả lỗi gộp ('' nếu ổn)."""
    errs = [MT.save_trades(trades), MT.save_plans(plans), save_lots(lots)]
    return "; ".join(e for e in errs if e)


def render(wb: pd.DataFrame, res: pd.DataFrame, asof, lots: pd.DataFrame, save_lots) -> None:
    """Gọi ở đầu trang Cổ phiếu của tôi. lots: bảng lô hiện có; save_lots(df) -> '' hoặc lỗi (my_portfolio.save)."""
    ver = st.session_state.setdefault("mt_ver", 0)
    plans, trades = MT.load_plans(), MT.load_trades()
    fixed = MT.reconcile(plans, lots, asof)                       # lô bị sửa ngoài sổ (xóa ở bảng quản lý) thì kế hoạch tự theo
    if not fixed.equals(plans):
        plans = fixed
        MT.save_plans(plans)

    wait, hold = build_wait(plans, res, wb), build_hold(plans, lots, res, wb)
    rt = MT.round_trips(plans, trades)
    t1, t2, t3 = st.tabs([f"🟡 Chờ mua ({len(wait)})", f"🟢 Đang giữ ({len(hold)})", f"🔴 Đã bán · Lịch sử ({len(rt)})"])
    nc = st.column_config.NumberColumn

    # ---------- CHỜ MUA
    with t1:
        if wait.empty:
            st.info("Chưa có mã nào chờ mua. Thêm ở phần bên dưới.")
        else:
            cols = ["Lệnh", "Mã", "Vùng mua", "Giá hiện tại", "Cách vùng mua %", "Tỷ trọng %", "Cắt lỗ", "Mục tiêu 1", "Mục tiêu 2",
                    "Điểm cơ bản", "Điểm kỹ thuật", "Tổng điểm", "Hành động"]
            st.dataframe(wait[cols], hide_index=True, column_config={
                "Giá hiện tại": nc(format="%.2f"), "Cách vùng mua %": nc(format="%+.1f%%"), "Tỷ trọng %": nc(format="%.0f%%"),
                "Cắt lỗ": nc(format="%.2f"), "Mục tiêu 1": nc(format="%.2f"), "Mục tiêu 2": nc(format="%.2f"),
                "Điểm cơ bản": nc(format="%.1f"), "Điểm kỹ thuật": nc(format="%.1f"), "Tổng điểm": nc(format="%.1f")}, **_DF)
        with st.expander("➕ Thêm mã chờ mua", expanded=wait.empty):
            codes = sorted(set(wb["Mã"].astype(str).str.upper())) if "Mã" in wb.columns else []
            code = st.selectbox("Mã", codes, key=f"mt_wcode_{ver}") if codes else st.text_input("Mã", key=f"mt_wcode_{ver}").upper().strip()
            z = wb[wb["Mã"].astype(str).str.upper() == code].head(1) if codes and code else pd.DataFrame()
            def _d(col, default=0.0):
                return float(z[col].iat[0]) if len(z) and col in z.columns and pd.notna(z[col].iat[0]) else default
            a = st.columns(4)
            lo = a[0].number_input("Vùng mua từ", 0.0, step=0.05, format="%.2f", value=_d("Vùng mua từ"), key=f"mt_lo_{code}_{ver}")
            hi = a[1].number_input("Vùng mua đến", 0.0, step=0.05, format="%.2f", value=_d("Vùng mua đến"), key=f"mt_hi_{code}_{ver}")
            wgt = a[2].number_input("Tỷ trọng (%)", 0.0, 100.0, 30.0, 5.0, key=f"mt_wg_{code}_{ver}", help="Phần vốn dự định dành cho mã này")
            sl = a[3].number_input("Cắt lỗ", 0.0, step=0.05, format="%.2f", value=_d("Cắt lỗ"), key=f"mt_sl_{code}_{ver}")
            b = st.columns([1, 1, 3])
            m1 = b[0].number_input("Mục tiêu 1", 0.0, step=0.05, format="%.2f", value=_d("Mục tiêu 1"), key=f"mt_t1_{code}_{ver}")
            m2 = b[1].number_input("Mục tiêu 2", 0.0, step=0.05, format="%.2f", value=_d("Mục tiêu 2"), key=f"mt_t2_{code}_{ver}")
            note = b[2].text_input("Ghi chú", key=f"mt_wn_{ver}")
            if len(z):
                st.caption("Vùng mua, cắt lỗ, mục tiêu được điền sẵn từ bảng Chờ mua của app; sửa nếu bạn muốn khác.")
            if st.button("➕ Thêm vào chờ mua", key=f"mt_wadd_{ver}"):
                p2, err = MT.add_plan(plans, code, asof, (lo, hi), wgt or None, sl or None, m1 or None, m2 or None, scores_for(code, res), note)
                if err:
                    st.warning(err)
                else:
                    e2 = MT.save_plans(p2)
                    st.session_state["mt_ver"] = ver + 1
                    st.warning(f"Chưa lưu được: {e2}") if e2 else st.rerun()
        if not wait.empty:
            with st.expander("✅ Khớp lệnh mua / ✖ Hủy kế hoạch"):
                pick = st.selectbox("Mã", list(wait["Mã"]), key=f"mt_bpick_{ver}")
                cur = float(wait.loc[wait["Mã"] == pick, "Giá hiện tại"].iat[0]) if pd.notna(wait.loc[wait["Mã"] == pick, "Giá hiện tại"].iat[0]) else 0.0
                c = st.columns(4)
                q = c[0].number_input("Số lượng (cp)", 0, step=100, value=0, key=f"mt_bq_{ver}")
                px = c[1].number_input("Giá khớp (nghìn đồng)", 0.0, step=0.05, format="%.2f", value=cur, key=f"mt_bp_{pick}_{ver}")
                dt = c[2].date_input("Ngày mua", value=pd.Timestamp(asof).date(), key=f"mt_bd_{ver}")
                bn = c[3].text_input("Ghi chú", key=f"mt_bn_{ver}")
                x = st.columns([1, 1, 3])
                if x[0].button("✅ Ghi nhận đã mua", key=f"mt_buy_{ver}"):
                    p2, t2_, l2, err = MT.record_buy(plans, trades, lots, pick, int(q), float(px), pd.Timestamp(dt), scores_for(pick, res),
                                                     str(wait.loc[wait["Mã"] == pick, "Lệnh"].iat[0]), bn)
                    if err:
                        st.warning(err)
                    else:
                        e2 = _save_all(p2, t2_, l2, save_lots)
                        st.session_state["mt_ver"] = ver + 1
                        st.warning(f"Chưa lưu được: {e2}") if e2 else st.rerun()
                if x[1].button("✖ Hủy kế hoạch", key=f"mt_cancel_{ver}"):
                    pid = wait.loc[wait["Mã"] == pick, "ID"].iat[0]
                    e2 = MT.save_plans(MT.cancel_plan(plans, pid, asof))
                    st.session_state["mt_ver"] = ver + 1
                    st.warning(f"Chưa lưu được: {e2}") if e2 else st.rerun()

    # ---------- ĐANG GIỮ
    with t2:
        if hold.empty:
            st.info("Chưa có mã nào đang giữ. Mã chờ mua sau khi bạn ghi nhận khớp lệnh mua sẽ chuyển sang đây và được theo dõi tới khi bán hết.")
        else:
            cols = ["Mã", "Ngày mua", "Khối lượng", "Giá vốn", "Giá hiện tại", "Lãi/lỗ (đồng)", "Lãi/lỗ %", "Cắt lỗ", "Mục tiêu",
                    "Điểm cơ bản", "Điểm kỹ thuật", "Tổng điểm", "Tín hiệu hiện tại", "Hành động"]
            st.dataframe(hold[cols], hide_index=True, column_config={
                "Ngày mua": st.column_config.DateColumn(format="DD/MM/YYYY"), "Khối lượng": nc(format="%d"), "Giá vốn": nc(format="%.2f"),
                "Giá hiện tại": nc(format="%.2f"), "Lãi/lỗ (đồng)": nc(format="%+,.0f"), "Lãi/lỗ %": nc(format="%+.2f%%"),
                "Cắt lỗ": nc(format="%.2f"), "Mục tiêu": nc(format="%.2f"), "Điểm cơ bản": nc(format="%.1f"),
                "Điểm kỹ thuật": nc(format="%.1f"), "Tổng điểm": nc(format="%.1f")}, **_DF)
            st.caption("Lãi/lỗ ròng tạm tính đã trừ phí mua, phí bán và thuế bán. Giá vốn là bình quân các lô chưa gồm phí.")
            with st.expander("🔴 Ghi nhận bán"):
                pick = st.selectbox("Mã", list(hold["Mã"]), key=f"mt_spick_{ver}")
                row = hold[hold["Mã"] == pick].iloc[0]
                held = int(row["Khối lượng"])
                c = st.columns(4)
                q = c[0].number_input(f"Số lượng bán (đang giữ {held:,})", 0, held, 0, 100, key=f"mt_sq_{pick}_{ver}")
                px = c[1].number_input("Giá bán (nghìn đồng)", 0.0, step=0.05, format="%.2f",
                                       value=float(row["Giá hiện tại"]) if pd.notna(row["Giá hiện tại"]) else 0.0, key=f"mt_sp_{pick}_{ver}")
                dt = c[2].date_input("Ngày bán", value=pd.Timestamp(asof).date(), key=f"mt_sd_{ver}")
                sn = c[3].text_input("Ghi chú", key=f"mt_sn_{ver}", placeholder="Đạt mục tiêu / cắt lỗ...")
                if st.button("🔴 Ghi nhận đã bán", key=f"mt_sell_{ver}"):
                    p2, t2_, l2, err = MT.record_sell(plans, trades, lots, pick, int(q), float(px), pd.Timestamp(dt), scores_for(pick, res),
                                                      str(row["Tín hiệu hiện tại"]), sn)
                    if err:
                        st.warning(err)
                    else:
                        e2 = _save_all(p2, t2_, l2, save_lots)
                        st.session_state["mt_ver"] = ver + 1
                        st.warning(f"Chưa lưu được: {e2}") if e2 else st.rerun()

    # ---------- ĐÃ BÁN · LỊCH SỬ
    with t3:
        sm = MT.summary(rt)
        m = st.columns(4)
        m[0].metric("SỐ KẾ HOẠCH ĐÃ BÁN", sm["n"])
        m[1].metric("TỶ LỆ THẮNG", "—" if pd.isna(sm["win"]) else f"{sm['win']:.0f}%")
        m[2].metric("LÃI/LỖ TRUNG BÌNH", "—" if pd.isna(sm["avg_pct"]) else f"{sm['avg_pct']:+.1f}%")
        m[3].metric("TỔNG LÃI/LỖ ĐÃ CHỐT", _vnd(sm["pnl"]), help="Ròng sau phí và thuế")
        if rt.empty:
            st.info("Chưa có lệnh bán nào được ghi nhận.")
        else:
            st.dataframe(rt.sort_values("Ngày bán cuối", ascending=False), hide_index=True, column_config={
                "Ngày mua đầu": st.column_config.DateColumn(format="DD/MM/YYYY"), "Ngày bán cuối": st.column_config.DateColumn(format="DD/MM/YYYY"),
                "SL đã bán": nc(format="%d"), "Lãi/lỗ ròng (đồng)": nc(format="%+,.0f"), "Lãi/lỗ %": nc(format="%+.2f%%"),
                "Điểm cơ bản": nc(format="%.1f"), "Điểm kỹ thuật": nc(format="%.1f"), "Tổng điểm": nc(format="%.1f")}, **_DF)
        with st.expander("📜 Toàn bộ sổ giao dịch (mua và bán, chỉ ghi thêm)"):
            st.dataframe(trades.sort_values("Ngày", ascending=False), hide_index=True, column_config={
                "Ngày": st.column_config.DateColumn(format="DD/MM/YYYY"), "Giá": nc(format="%.2f"), "Số lượng": nc(format="%d"),
                "Phí và thuế (đồng)": nc(format="%,.0f"), "Lãi/lỗ ròng (đồng)": nc(format="%+,.0f"), "Lãi/lỗ %": nc(format="%+.2f%%")}, **_DF)
        d = st.columns(2)
        _t = trades.assign(Ngày=trades["Ngày"].dt.strftime("%d/%m/%Y"))
        _p = plans.assign(**{"Ngày tạo": plans["Ngày tạo"].dt.strftime("%d/%m/%Y"), "Ngày đóng": plans["Ngày đóng"].dt.strftime("%d/%m/%Y")})
        d[0].download_button("⬇️ Sao lưu sổ giao dịch (CSV)", _t.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig"),
                             file_name="lich_su_giao_dich.csv", mime="text/csv")
        d[1].download_button("⬇️ Sao lưu kế hoạch (CSV)", _p.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig"),
                             file_name="ke_hoach_giao_dich.csv", mime="text/csv")
        st.caption("Sổ giao dịch chỉ ghi thêm, app không có nút xóa. Kế hoạch đã bán hoặc đã hủy vẫn nằm lại để backtest. "
                   "⚠ Trên Streamlit Cloud, file ghi lúc chạy mất khi app khởi động lại: hãy tải sao lưu thường xuyên và đẩy "
                   "data/lich_su_giao_dich.csv, data/ke_hoach_giao_dich.csv lên GitHub (repo private). Đây là dữ liệu cá nhân.")
