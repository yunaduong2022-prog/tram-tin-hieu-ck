"""Giao diện "Cổ phiếu của tôi" theo vòng đời: 🟡 Chờ mua -> 🟢 Đang giữ -> 🔴 Đã bán, kèm lịch sử giao dịch để backtest.
Logic nằm ở my_trades.py (thuần pandas). Hàm build_* ở đây cũng không gọi Streamlit nên kiểm thử được.

Điểm cơ bản / kỹ thuật / tổng chấm đúng như mục Khuyến nghị khách hàng (vip_picks.py): FA = fa_score(P/E, ROE, P/B), TA = ta_score(30 phiên gần nhất),
Tổng điểm = Score x 10 (tối đa 100). Cần app truyền fund_map, frames_d (và ctx_fn để lấy số mặc định giống Khuyến nghị khách hàng) qua set_context();
chưa truyền thì điểm FA / TA để trống và số mặc định lấy từ bảng Chờ mua.
"""
from __future__ import annotations

import inspect

import numpy as np
import pandas as pd
import streamlit as st

import my_trades as MT

_DF = ({"width": "stretch"} if "width" in inspect.signature(st.dataframe).parameters else {"use_container_width": True})


# ------------------------------------------------------------------ ĐIỂM
_CTX: dict = {"fund_map": None, "frames_d": None, "ctx_fn": None}


def set_context(fund_map=None, frames_d=None, ctx_fn=None) -> None:
    """app.py (qua my_portfolio.render) truyền dữ liệu dùng chung với Khuyến nghị khách hàng: fund_map (P/E, ROE, P/B), frames_d (khung Ngày
    có MA20 / MA50 / MA200 / RSI) và ctx_fn(code) (ngữ cảnh của action_summary)."""
    _CTX.update(fund_map=fund_map, frames_d=frames_d, ctx_fn=ctx_fn)


def scores_for(code: str, res: pd.DataFrame) -> dict:
    """{"fund", "tech", "total"} chấm giống Khuyến nghị khách hàng: FA và TA thang 0-100 (vip_picks.fa_score / ta_score), Tổng điểm = Score x 10
    (tối đa 100). Thiếu dữ liệu thì NaN."""
    code = str(code).upper().strip()
    out = {"fund": np.nan, "tech": np.nan, "total": np.nan}
    if "Score" in res.columns:
        m = pd.to_numeric(res.loc[res["Mã"].astype(str).str.upper() == code, "Score"], errors="coerce").dropna()
        if len(m):
            out["total"] = float(min(100.0, max(0.0, m.iloc[0] * 10)))
    try:
        import vip_picks as VP
        fm, fd = _CTX.get("fund_map"), _CTX.get("frames_d")
        if fm is not None:
            f = (fm.get(code) or {})
            fa, _ = VP.fa_score(f.get("P/E"), f.get("ROE"), f.get("P/B"))
            if fa is not None:
                out["fund"] = float(fa)
        if fd is not None and len(fd):
            g = fd[fd["Mã"] == code].sort_values("Ngày").tail(30)
            if len(g):
                ta, _ = VP.ta_score(g)
                if ta is not None:
                    out["tech"] = float(ta)
    except Exception:  # noqa: BLE001  (thiếu dữ liệu hoặc lỗi chấm điểm thì để trống, không làm hỏng trang)
        pass
    return out


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
    for c in ("Vùng mua từ", "Vùng mua đến"):
        w[c] = pd.to_numeric(w[c], errors="coerce").astype(float)
    # ép về số thực: bảng rỗng hoặc cột kiểu chuỗi (pyarrow) sẽ làm phép so sánh với số báo TypeError
    w["Giá hiện tại"] = pd.to_numeric(w["Mã"].map(px), errors="coerce").astype(float)
    g, lo, hi = w["Giá hiện tại"], w["Vùng mua từ"], w["Vùng mua đến"]
    w["Cách vùng mua %"] = np.where(g > hi, (g / hi - 1) * 100, np.where(g < lo, (g / lo - 1) * 100, 0.0))
    w["Lệnh"] = np.where(g.isna(), "—", np.where((g.round(2) >= lo.round(2)) & (g.round(2) <= hi.round(2)), "MUA NGAY",
                                                  np.where(g > hi, "CHỜ MUA", "DƯỚI VÙNG")))
    w["Hành động"] = w["Lệnh"].map({"MUA NGAY": "Giá trong vùng mua: có thể mua, nên chia lệnh.",
                                    "CHỜ MUA": "Không mua đuổi. Chờ về vùng mua.",
                                    "DƯỚI VÙNG": "Giá đã xuống dưới vùng mua: chờ xác nhận, cân nhắc hủy kế hoạch."}).fillna("Chưa có giá")
    w["Vùng mua"] = pd.Series([f"{a:.2f} - {b:.2f}" for a, b in zip(lo, hi)], index=w.index, dtype=object)
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
                     "Tín hiệu hiện tại": sig.get(p["Mã"], "—"), "Khung thời gian": p["Khung thời gian"], "Điểm bán": p["Điểm bán"],
                     "Luận điểm": p["Luận điểm"]})
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    for c in ("Giá hiện tại", "Cắt lỗ", "Mục tiêu"):
        out[c] = pd.to_numeric(out[c], errors="coerce").astype(float)
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


FORM_TEXT = ["mtf_code", "mtf_zone", "mtf_target", "mtf_stop", "mtf_sell", "mtf_rec", "mtf_closepx", "mtf_closedate", "mtf_fill", "mtf_qty", "mtf_thesis"]


def sys_defaults(code: str, wb: pd.DataFrame, res: pd.DataFrame) -> dict:
    """Số mặc định của máy cho mã (mục Chờ mua): vùng mua, cắt lỗ, mục tiêu 1-2, Giá vào và giá hiện tại. Thiếu thì None."""
    code = str(code or "").upper().strip()
    z = wb[wb["Mã"].astype(str).str.upper() == code].head(1) if code and "Mã" in wb.columns else pd.DataFrame()

    def g(col):
        v = pd.to_numeric(z[col].iat[0], errors="coerce") if len(z) and col in z.columns else np.nan
        return float(v) if pd.notna(v) and v > 0 else None
    lo, hi = g("Vùng mua từ"), g("Vùng mua đến")
    out = {"zone": (lo, hi) if lo and hi else None, "stop": g("Cắt lỗ"), "t1": g("Mục tiêu 1"), "t2": g("Mục tiêu 2"),
           "entry_px": g("Giá vào"), "price": _prices(res, wb).get(code)}
    if _CTX.get("ctx_fn") and code:                              # cùng mốc hệ thống với Khuyến nghị khách hàng (vip_picks._system_levels)
        try:
            import vip_picks as VP
            row = z.iloc[0].to_dict() if len(z) else {}
            lv = VP._system_levels(code, _CTX["ctx_fn"], row)
            out["zone"] = lv.get("buy") or out["zone"]
            out["stop"] = lv.get("stop") or out["stop"]
            out["t1"] = lv.get("target") or out["t1"]
        except Exception:  # noqa: BLE001
            pass
    return out


def _table(df: pd.DataFrame, cfg: dict, key: str):
    """Hiện bảng cho chọn một dòng; trả chỉ số dòng (theo df.index) hoặc None. Streamlit cũ không có chọn dòng thì dùng ô chọn mã."""
    try:
        ev = st.dataframe(df, hide_index=True, column_config=cfg, on_select="rerun", selection_mode="single-row", key=key, **_DF)
        rows = ev.selection.rows
        return int(df.index[rows[0]]) if rows else None
    except TypeError:
        st.dataframe(df, hide_index=True, column_config=cfg, **_DF)
        code = st.selectbox("Chọn mã để sửa", [""] + list(df["Mã"]), key=key + "_sb")
        return int(df.index[df["Mã"] == code][0]) if code else None


def render(wb: pd.DataFrame, res: pd.DataFrame, asof, lots: pd.DataFrame, save_lots) -> None:
    """Gọi ở đầu trang Cổ phiếu của tôi. lots: bảng lô hiện có; save_lots(df) -> '' hoặc lỗi (my_portfolio.save)."""
    ss = st.session_state
    ver = ss.setdefault("mt_ver", 0)
    ss.setdefault("mtf_status", "Chờ mua")
    ss.setdefault("mtf_horizon", "Trung hạn")
    ss.setdefault("mtf_edit", None)
    for k in FORM_TEXT:
        ss.setdefault(k, "")
    plans, trades = MT.load_plans(), MT.load_trades()
    fixed = MT.reconcile(plans, lots, asof)                       # lô bị sửa ngoài sổ (xóa ở bảng quản lý) thì kế hoạch tự theo
    if not fixed.equals(plans):
        plans = fixed
        MT.save_plans(plans)

    wait, hold = build_wait(plans, res, wb), build_hold(plans, lots, res, wb)
    rt = MT.round_trips(plans, trades)

    # ---------- callbacks (chạy trước khi vẽ lại, nên được phép đặt giá trị cho các ô của form)
    def _reset():
        for k in FORM_TEXT:
            ss[k] = ""
        ss["mtf_status"], ss["mtf_horizon"], ss["mtf_edit"] = "Chờ mua", "Trung hạn", None

    def _load(pid: str):
        r = plans[plans["ID"] == pid].iloc[0]
        f2 = lambda v: "" if pd.isna(v) else f"{v:.2f}"      # noqa: E731
        _reset()
        ss["mtf_code"] = r["Mã"]
        lo, hi = r["Vùng mua từ"], r["Vùng mua đến"]
        ss["mtf_zone"] = "" if pd.isna(lo) else (f"{lo:.2f}" if lo == hi else f"{lo:.2f} - {hi:.2f}")
        ss["mtf_target"], ss["mtf_stop"], ss["mtf_sell"] = f2(r["Mục tiêu 1"]), f2(r["Cắt lỗ"]), r["Điểm bán"]
        ss["mtf_status"] = "Đang giữ" if r["Trạng thái"] == MT.HOLD else "Chờ mua"
        ss["mtf_horizon"] = r["Khung thời gian"] if r["Khung thời gian"] in MT.HORIZONS else "Trung hạn"
        ss["mtf_rec"] = "" if pd.isna(r["Ngày tạo"]) else f"{r['Ngày tạo']:%d/%m/%Y}"
        ss["mtf_thesis"] = r["Luận điểm"]
        ss["mtf_edit"] = pid

    def _on_save():
        code = str(ss.get("mtf_code", "")).upper().strip()
        e = {"code": code, "zone": ss["mtf_zone"], "target": ss["mtf_target"], "stop": ss["mtf_stop"], "sell": ss["mtf_sell"],
             "status": ss["mtf_status"], "horizon": ss["mtf_horizon"], "rec_date": ss["mtf_rec"], "close_px": ss["mtf_closepx"],
             "close_date": ss["mtf_closedate"], "fill_px": ss["mtf_fill"], "qty": ss["mtf_qty"], "thesis": ss["mtf_thesis"]}
        p2, t2_, l2, err, ok = MT.save_entry(plans, trades, lots, e, sys_defaults(code, wb, res), pd.Timestamp.today(), ss.get("mtf_edit"),
                                             scores_for(code, res) if code else None)
        if err:
            ss["mtf_msg"] = ("warn", err)
            return
        e2 = _save_all(p2, t2_, l2, save_lots)
        if e2:
            ss["mtf_msg"] = ("warn", f"Chưa lưu được vào file: {e2}")
            return
        ss["mtf_msg"] = ("ok", ok)
        ss["mt_ver"] = ss.get("mt_ver", 0) + 1
        _reset()

    # ---------- FORM NHẬP
    st.markdown("**⚡ BẢNG ĐIỀN ĐIỂM MUA - BÁN - TARGET**")
    st.caption("Điền các mức giá rồi bấm Lưu, hoặc chọn mã ở bảng bên dưới và bấm Sửa. Ô giá để trống sẽ tự điền theo hệ thống.")
    editing = ss.get("mtf_edit")
    if editing:
        st.info(f"Đang sửa {ss.get('mtf_code', '')}. Sửa xong bấm Lưu, hoặc bấm ↺ để thôi sửa.")
    profit = ""
    if editing and not hold.empty and (hold["ID"] == editing).any():
        v = hold.loc[hold["ID"] == editing, "Lãi/lỗ %"].iat[0]
        profit = "" if pd.isna(v) else f"{v:+.2f}%"
    r1 = st.columns([1.1, 1.7, 1.4, 1.1, 1.1, 1.2])
    r1[0].text_input("Mã CK *", placeholder="VD: IDC, HPG...", key="mtf_code", disabled=bool(editing))
    r1[1].text_input("Điểm Mua", placeholder="VD: 35.5 - 36.0", key="mtf_zone")
    r1[2].text_input("Lợi Nhuận", value=profit, placeholder="Tự tính theo giá khớp", disabled=True, key=f"mtf_profit_{editing}")
    r1[3].text_input("Target", placeholder="VD: 42.0", key="mtf_target")
    r1[4].text_input("Cutloss", placeholder="VD: 34.0", key="mtf_stop")
    r1[5].text_input("Điểm Bán", placeholder="VD: ≥ 42.0", key="mtf_sell")
    r2 = st.columns([1.1, 1.1, 1.4, 1.1, 1.1, 1.1, 1.0])
    r2[0].selectbox("Trạng thái", MT.STATUS_UI, key="mtf_status")
    r2[1].selectbox("Khung thời gian", MT.HORIZONS, key="mtf_horizon")
    r2[2].text_input("Ngày khuyến nghị", placeholder="dd/mm/yyyy (trống = hôm nay)", key="mtf_rec")
    r2[3].text_input("Giá đóng", placeholder="Chỉ khi Đã đóng", key="mtf_closepx")
    r2[4].text_input("Ngày đóng", placeholder="dd/mm/yyyy", key="mtf_closedate")
    r2[5].text_input("Giá khớp", placeholder="Chỉ khi Đang giữ", key="mtf_fill", help="Để trống = Giá vào của máy (mục Chờ mua), thiếu thì giá hiện tại")
    r2[6].text_input("Số lượng", placeholder="Khi Đang giữ", key="mtf_qty", help="Số cổ phiếu mua. Đang giữ mà nhập số lượng khi sửa = mua thêm")
    st.text_input("Luận điểm", placeholder="VD: Nền tích lũy pha C, chờ giá vượt MA20 kèm khối lượng (tối đa 300 ký tự)", max_chars=300, key="mtf_thesis")
    code_now = str(ss.get("mtf_code", "")).upper().strip()
    sd = sys_defaults(code_now, wb, res) if code_now else {}
    if code_now:
        zt = f"{sd['zone'][0]:.2f} - {sd['zone'][1]:.2f}" if sd.get("zone") else "—"
        f2 = lambda v: "—" if not v else f"{v:.2f}"      # noqa: E731
        st.caption(f"Mặc định của máy cho {code_now}: Điểm mua {zt} · Target {f2(sd.get('t1'))} · Cutloss {f2(sd.get('stop'))} · "
                   f"Giá vào {f2(sd.get('entry_px'))} · Giá hiện tại {f2(sd.get('price'))}. Ô nào để trống thì dùng số này.")
    b = st.columns([1.6, 0.7, 6])
    b[0].button("✓ Lưu", key="mtf_save", on_click=_on_save, use_container_width=True)
    b[1].button("↺", key="mtf_reset", on_click=_reset, help="Xóa form / thôi sửa", use_container_width=True)
    msg = ss.pop("mtf_msg", None)
    if msg:
        (st.success if msg[0] == "ok" else st.warning)(msg[1])

    # ---------- CÁC BẢNG
    t1, t2, t3 = st.tabs([f"🟡 Chờ mua ({len(wait)})", f"🟢 Đang giữ ({len(hold)})", f"🔴 Đã bán · Lịch sử ({len(rt)})"])
    nc = st.column_config.NumberColumn

    with t1:
        if wait.empty:
            st.info("Chưa có mã nào chờ mua. Nhập mã ở bảng điền phía trên (Trạng thái: Chờ mua) rồi bấm Lưu.")
        else:
            cols = ["Lệnh", "Mã", "Vùng mua", "Giá hiện tại", "Cách vùng mua %", "Cắt lỗ", "Mục tiêu 1", "Mục tiêu 2", "Điểm bán", "Khung thời gian",
                    "Điểm cơ bản", "Điểm kỹ thuật", "Tổng điểm", "Hành động", "Luận điểm"]
            i = _table(wait[cols], {"Giá hiện tại": nc(format="%.2f"), "Cách vùng mua %": nc(format="%+.1f%%"), "Cắt lỗ": nc(format="%.2f"),
                                    "Mục tiêu 1": nc(format="%.2f"), "Mục tiêu 2": nc(format="%.2f"), "Điểm cơ bản": nc(format="%.1f"),
                                    "Điểm kỹ thuật": nc(format="%.1f"), "Tổng điểm": nc(format="%.1f")}, "mtf_tbl_wait")
            if i is not None:
                st.button(f"✏️ Sửa {wait.loc[i, 'Mã']}", key="mtf_edit_w", on_click=_load, args=(wait.loc[i, "ID"],))

    with t2:
        if hold.empty:
            st.info("Chưa có mã nào đang giữ. Mã chờ mua sau khi bạn Lưu với Trạng thái Đang giữ (kèm Số lượng) sẽ chuyển sang đây "
                    "và được theo dõi tới khi đóng.")
        else:
            cols = ["Mã", "Ngày mua", "Khối lượng", "Giá vốn", "Giá hiện tại", "Lãi/lỗ (đồng)", "Lãi/lỗ %", "Cắt lỗ", "Mục tiêu", "Điểm bán",
                    "Khung thời gian", "Điểm cơ bản", "Điểm kỹ thuật", "Tổng điểm", "Tín hiệu hiện tại", "Hành động", "Luận điểm"]
            i = _table(hold[cols], {"Ngày mua": st.column_config.DateColumn(format="DD/MM/YYYY"), "Khối lượng": nc(format="%d"),
                                    "Giá vốn": nc(format="%.2f"), "Giá hiện tại": nc(format="%.2f"), "Lãi/lỗ (đồng)": nc(format="%+,.0f"),
                                    "Lãi/lỗ %": nc(format="%+.2f%%"), "Cắt lỗ": nc(format="%.2f"), "Mục tiêu": nc(format="%.2f"),
                                    "Điểm cơ bản": nc(format="%.1f"), "Điểm kỹ thuật": nc(format="%.1f"), "Tổng điểm": nc(format="%.1f")}, "mtf_tbl_hold")
            if i is not None:
                st.button(f"✏️ Sửa {hold.loc[i, 'Mã']}", key="mtf_edit_h", on_click=_load, args=(hold.loc[i, "ID"],))
            st.caption("Lãi/lỗ ròng tạm tính đã trừ phí mua, phí bán và thuế bán. Giá vốn là bình quân các lô chưa gồm phí. "
                       "Đóng toàn bộ: Sửa → Trạng thái Đã đóng → Lưu (Giá đóng để trống = giá hiện tại).")
            with st.expander("🔴 Bán một phần"):
                pick = st.selectbox("Mã", list(hold["Mã"]), key=f"mt_spick_{ver}")
                row = hold[hold["Mã"] == pick].iloc[0]
                held = int(row["Khối lượng"])
                cur_px = float(row["Giá hiện tại"]) if pd.notna(row["Giá hiện tại"]) else 0.0
                c = st.columns(4)
                q = c[0].number_input(f"Số lượng bán (đang giữ {held:,})", 0, held, 0, 100, key=f"mt_sq_{pick}_{ver}")
                px = c[1].number_input("Giá bán (nghìn đồng)", 0.0, step=0.05, format="%.2f", value=0.0, key=f"mt_sp_{pick}_{ver}",
                                       help=f"Để 0 = dùng giá hiện tại của máy ({cur_px:.2f})")
                dt = c[2].date_input("Ngày bán", value=pd.Timestamp(asof).date(), key=f"mt_sd_{ver}")
                sn = c[3].text_input("Ghi chú", key=f"mt_sn_{ver}", placeholder="Đạt mục tiêu / cắt lỗ...")
                if st.button("🔴 Ghi nhận đã bán", key=f"mt_sell_{ver}"):
                    p2, t2_, l2, err = MT.record_sell(plans, trades, lots, pick, int(q), float(px or cur_px), pd.Timestamp(dt), scores_for(pick, res),
                                                      str(row["Tín hiệu hiện tại"]), sn)
                    if err:
                        st.warning(err)
                    else:
                        e2 = _save_all(p2, t2_, l2, save_lots)
                        ss["mt_ver"] = ver + 1
                        st.warning(f"Chưa lưu được: {e2}") if e2 else st.rerun()

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
