"""Watchlist cá nhân: danh sách mã tự theo dõi, kèm giá vốn / mục tiêu / cắt lỗ / ghi chú và tín hiệu từ hệ thống.

- Danh sách lưu ở data/watchlist_cua_toi.csv (cột: Mã, Giá vốn, Mục tiêu, Cắt lỗ, Ghi chú). Giống data/ghi_chu.csv:
  trên Streamlit Cloud file này mất khi app khởi động lại; muốn giữ lâu dài hãy tải CSV về (nút Sao lưu) rồi
  đẩy lên GitHub vào thư mục data/ - app tự đọc file đó làm danh sách ban đầu.
- Tín hiệu lấy từ bảng "Cổ phiếu chờ mua" (waiting_buy) và bảng lọc chính, không tính lại ở đây.
- Giá vốn / Mục tiêu / Cắt lỗ cùng đơn vị với giá trong app (nghìn đồng, ví dụ 22.75).
"""
from __future__ import annotations

import html as _html
import inspect
import os
import re

import numpy as np
import pandas as pd
import streamlit as st

import waiting_buy as WB

PATH = "data/watchlist_cua_toi.csv"
COLS = ["Mã", "Giá vốn", "Mục tiêu", "Cắt lỗ", "Ghi chú"]
NUM = ["Giá vốn", "Mục tiêu", "Cắt lỗ"]
_DF = ({"width": "stretch"} if "width" in inspect.signature(st.dataframe).parameters else {"use_container_width": True})


# ------------------------------------------------------------------ DỮ LIỆU (thuần pandas, dễ kiểm thử)
def parse_codes(text: str) -> list[str]:
    out = []
    for t in re.split(r"[,\s;]+", str(text or "").upper()):
        if re.fullmatch(r"[A-Z0-9]{2,10}", t) and t not in out:
            out.append(t)
    return out


def _clean(d: pd.DataFrame) -> pd.DataFrame:
    d = d.copy()
    for c in COLS:
        if c not in d.columns:
            d[c] = np.nan if c in NUM else ""
    d["Mã"] = d["Mã"].astype(str).str.upper().str.strip()
    d = d[d["Mã"].str.fullmatch(r"[A-Z0-9]{2,10}")]
    for c in NUM:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d["Ghi chú"] = d["Ghi chú"].fillna("").astype(str)
    return d.drop_duplicates("Mã", keep="last")[COLS].reset_index(drop=True)


def load(path: str = PATH) -> pd.DataFrame:
    if os.path.exists(path):
        try:
            return _clean(pd.read_csv(path, dtype={"Mã": str, "Ghi chú": str}, encoding="utf-8-sig"))
        except Exception:
            pass
    return _clean(pd.DataFrame(columns=COLS))


def save(d: pd.DataFrame, path: str = PATH) -> str:
    """Trả '' nếu lưu được, ngược lại là thông báo lỗi."""
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        _clean(d).to_csv(path, index=False, encoding="utf-8-sig")
        return ""
    except Exception as e:
        return str(e)


def remove_code(code: str, path: str = PATH) -> str:
    w = load(path)
    return save(w[w["Mã"] != str(code).upper()], path)


def add_codes(w: pd.DataFrame, codes: list[str]) -> pd.DataFrame:
    new = [c for c in codes if c not in set(w["Mã"])]
    return _clean(pd.concat([w, pd.DataFrame({"Mã": new})], ignore_index=True)) if new else w


_SIGNAL = {**{g: "Chờ mua" for g in WB.BUY_GROUPS}, WB.L_RECOVER: "Cảnh báo", WB.L_OVERBOUGHT: "Cảnh báo",
           WB.L_RISK: "Cảnh báo", WB.L_NONE: "Không có điểm mua"}
_PRIO = {WB.L_RISK: 1, WB.L_OVERBOUGHT: 1, WB.G1: 2, WB.G2: 3, WB.G3: 4, WB.L_RECOVER: 5}


def build_view(w: pd.DataFrame, wb: pd.DataFrame, res: pd.DataFrame) -> pd.DataFrame:
    """Ghép danh sách của người dùng với tín hiệu hệ thống và tính lãi/lỗ, khoảng cách tới cắt lỗ / mục tiêu."""
    wbc = wb[[c for c in ["Mã", "Giá", "Chg %", "Score", "RS20", "Trạng thái", "Danh sách", "Lý do", "Hành động",
                          "Vùng mua từ", "Vùng mua đến", "Cắt lỗ", "Mục tiêu 1"] if c in wb.columns]].copy()
    wbc = wbc.rename(columns={"Cắt lỗ": "SL hệ thống", "Mục tiêu 1": "MT1 hệ thống"}).drop_duplicates("Mã")
    rc = res[[c for c in ["Mã", "Giá", "Nhóm", "Wyckoff", "MA align", "Cảnh báo"] if c in res.columns]] \
        .rename(columns={"Giá": "_Giá res"}).drop_duplicates("Mã")
    m = w.merge(wbc, on="Mã", how="left").merge(rc, on="Mã", how="left")
    if "_Giá res" in m:
        m["Giá"] = m["Giá"].fillna(m["_Giá res"]) if "Giá" in m else m["_Giá res"]
        m = m.drop(columns="_Giá res")
    g = m["Giá"].astype(float)
    m["Lãi/lỗ %"] = np.where(m["Giá vốn"] > 0, (g / m["Giá vốn"] - 1) * 100, np.nan)
    m["Cách cắt lỗ %"] = np.where(m["Cắt lỗ"] > 0, (g / m["Cắt lỗ"] - 1) * 100, np.nan)
    m["Cách mục tiêu %"] = np.where(m["Mục tiêu"] > 0, (m["Mục tiêu"] / g - 1) * 100, np.nan)
    sl_hit = (m["Cắt lỗ"] > 0) & (g <= m["Cắt lỗ"])
    tp_hit = (m["Mục tiêu"] > 0) & (g >= m["Mục tiêu"])
    sig = m["Danh sách"].map(_SIGNAL).fillna("Chưa có dữ liệu") if "Danh sách" in m else "Chưa có dữ liệu"
    base = pd.Series(sig, index=m.index).map({"Chờ mua": "🟢 Chờ mua", "Cảnh báo": "🟠 Cảnh báo",
                                              "Không có điểm mua": "⚪ Không có điểm mua"}).fillna("— Chưa có dữ liệu")
    rs = m["Lý do"].fillna("").astype(str) if "Lý do" in m else pd.Series("", index=m.index)
    is_tp, is_sell = rs.str.startswith("CHỐT LỜI"), rs.str.startswith("BÁN")      # tiền tố do waiting_buy.classify ghi
    base = base.mask(is_tp, "🟠 CHỐT LỜI").mask(is_sell, "🔴 BÁN")
    m["Tín hiệu"] = base.mask(tp_hit, "🟢 Đạt mục tiêu").mask(sl_hit, "🔴 Chạm cắt lỗ")
    prio = m["Danh sách"].map(_PRIO).fillna(6) if "Danh sách" in m else pd.Series(6, index=m.index)
    prio = pd.Series(np.where(is_sell | is_tp, 1, prio), index=m.index)
    m["_p"] = np.where(sl_hit, 0, np.where(tp_hit, 2.5, prio))
    sort_cols = ["_p"] + (["Score"] if "Score" in m else [])
    m = m.sort_values(sort_cols, ascending=[True] + [False] * (len(sort_cols) - 1)).drop(columns="_p")
    return m.reset_index(drop=True)


def summary(v: pd.DataFrame) -> dict:
    return {"n": len(v),
            "buy": int((v["Tín hiệu"] == "🟢 Chờ mua").sum()),
            "warn": int(v["Tín hiệu"].isin(["🟠 Cảnh báo", "🟠 CHỐT LỜI", "🔴 BÁN"]).sum()),
            "sl": int((v["Tín hiệu"] == "🔴 Chạm cắt lỗ").sum()),
            "tp": int((v["Tín hiệu"] == "🟢 Đạt mục tiêu").sum()),
            "win": int((v["Lãi/lỗ %"] > 0).sum()), "lose": int((v["Lãi/lỗ %"] < 0).sum()),
            "avg_pl": float(v["Lãi/lỗ %"].mean()) if v["Lãi/lỗ %"].notna().any() else np.nan}


# ------------------------------------------------------------------ GIAO DIỆN
def position_html(u, price) -> str:
    """Khối "Vị thế của tôi" dưới thẻ: giá vốn, lãi/lỗ, cắt lỗ / mục tiêu tự đặt, ghi chú. Rỗng nếu chưa nhập gì."""
    gv, sl, tp = (u.get(k, np.nan) for k in ("Giá vốn", "Cắt lỗ", "Mục tiêu"))
    note = str(u.get("Ghi chú", "") or "").strip()
    rows = []
    line = lambda lab, val, col="var(--txt2)": (
        f'<div style="display:flex;justify-content:space-between;gap:8px;padding:2px 0"><span style="color:var(--muted)">{lab}</span>'
        f'<b style="color:{col}">{val}</b></div>')
    ok = pd.notna(price)
    if pd.notna(gv) and gv > 0:
        if ok:
            pl = (price / gv - 1) * 100
            rows.append(line("Giá vốn", f"{gv:,.2f} ({pl:+.1f}%)", "var(--green)" if pl >= 0 else "var(--red)"))
        else:
            rows.append(line("Giá vốn", f"{gv:,.2f}"))
    if pd.notna(sl) and sl > 0:
        hit = ok and price <= sl
        rows.append(line("Cắt lỗ của tôi", f"{sl:,.2f}" + (f" ({(price / sl - 1) * 100:+.1f}% so với giá)" if ok else "")
                         + (" · ĐÃ CHẠM" if hit else ""), "var(--red)"))
    if pd.notna(tp) and tp > 0:
        hit = ok and price >= tp
        rows.append(line("Mục tiêu của tôi", f"{tp:,.2f}" + (f" ({(tp / price - 1) * 100:+.1f}% so với giá)" if ok else "")
                         + (" · ĐÃ ĐẠT" if hit else ""), "var(--green)"))
    if note:
        rows.append(f'<div style="margin-top:4px;color:var(--muted)">📝 {_html.escape(note)}</div>')
    if not rows:
        return ""
    return ('<div style="margin-top:10px;padding:10px 12px;border:1px dashed var(--line);border-radius:12px;font-size:13px">'
            '<div style="font-weight:700;color:var(--txt2);margin-bottom:4px">Vị thế của tôi</div>' + "".join(rows) + "</div>")


def _empty_card(code: str, ver: int) -> None:
    with st.container(key=f"wbcard-wl-{code}"):
        st.markdown(f'<div class="wb-head"><div class="wb-id"><span class="wb-code">{_html.escape(code)}</span></div>'
                    '<span class="wb-badge n">CHƯA CÓ DỮ LIỆU</span></div>'
                    '<div class="wb-note">App chưa có dữ liệu giá của mã này nên chưa tính được tín hiệu. '
                    'Thêm mã vào data/extra_symbols.txt rồi chạy workflow cập nhật dữ liệu cuối phiên.</div>',
                    unsafe_allow_html=True)
        if st.button("🗑 Bỏ theo dõi", key=f"wl_rm_{code}", use_container_width=True):
            remove_code(code)
            st.session_state["wl_ver"] = ver + 1
            st.rerun()


def render(wb: pd.DataFrame, res: pd.DataFrame, on_chart, card_fn=None) -> None:
    """wb: bảng _wb_table(); res: res_df; on_chart(code): mở biểu đồ; card_fn(wb_row, user_row): vẽ thẻ giống mục Chờ mua."""
    ver = st.session_state.setdefault("wl_ver", 0)
    available = set(res["Mã"].astype(str).str.upper())
    st.caption("Danh sách mã bạn tự theo dõi, hiển thị thẻ giống mục Cổ phiếu chờ mua trong tuần, kèm giá vốn, mục tiêu, cắt lỗ "
               "và tín hiệu của hệ thống. Chỉ phục vụ nghiên cứu, không phải khuyến nghị đầu tư.")

    # 1) thêm mã
    with st.form("wl_add", clear_on_submit=True):
        c1, c2 = st.columns([4, 1])
        txt = c1.text_input("Thêm mã vào Watchlist", placeholder="Ví dụ: HDB, FRT, GMD (cách nhau bằng dấu phẩy hoặc khoảng trắng)",
                            label_visibility="collapsed")
        go = c2.form_submit_button("➕ Thêm", use_container_width=True)
    w = load()
    if go:
        codes = parse_codes(txt)
        ok = [c for c in codes if c in available]
        bad = [c for c in codes if c not in available]
        if not codes:
            st.warning("Chưa nhập mã hợp lệ.")
        else:
            if ok:
                w = add_codes(w, ok)
                err = save(w)
                st.session_state["wl_ver"] = ver = ver + 1
                st.success("Đã thêm: " + ", ".join(ok) + ("" if not err else f" (chưa lưu được vào file: {err})"))
            if bad:
                st.warning("Không có trong dữ liệu của app nên chưa thêm: " + ", ".join(bad)
                           + ". Thêm mã mới vào rổ theo dõi (data/extra_symbols.txt) rồi cập nhật dữ liệu.")

    if w.empty:
        st.info("Watchlist đang trống. Nhập mã ở ô phía trên để bắt đầu, hoặc nhập danh sách từ file CSV ở mục Quản lý bên dưới.")
    else:
        v = build_view(w, wb, res)
        s = summary(v)
        m = st.columns(5)
        m[0].metric("SỐ MÃ", s["n"])
        m[1].metric("CHỜ MUA", s["buy"])
        m[2].metric("CẢNH BÁO", s["warn"])
        m[3].metric("CHẠM CẮT LỖ / MỤC TIÊU", f"{s['sl']} / {s['tp']}")
        m[4].metric("LÃI/LỖ TB (mã có giá vốn)", "—" if np.isnan(s["avg_pl"]) else f"{s['avg_pl']:+.1f}%",
                    help="Trung bình cộng % lãi/lỗ của các mã đã nhập giá vốn." if s["win"] + s["lose"] else None)
        no_data = int(v["Giá"].isna().sum())
        if no_data:
            st.caption(f"⚠ {no_data} mã chưa có dữ liệu giá trong app: " + ", ".join(v.loc[v["Giá"].isna(), "Mã"])
                       + ". Thêm vào data/extra_symbols.txt rồi chạy workflow cập nhật dữ liệu cuối phiên.")
        st.session_state.setdefault("wl_view", "Thẻ")
        view = st.segmented_control("Kiểu hiển thị", ["Thẻ", "Bảng"], key="wl_view") or "Thẻ"
        if view == "Thẻ" and card_fn is not None:
            st.caption("Sắp xếp theo mức cần chú ý: chạm cắt lỗ → cảnh báo → điểm mua đã xác nhận → sắp có điểm mua → còn lại.")
            wbi = wb.drop_duplicates("Mã").set_index("Mã")
            ui = w.set_index("Mã")
            cols3 = st.columns(3)
            for i, code in enumerate(v["Mã"]):
                with cols3[i % 3]:
                    if code in wbi.index:
                        r = wbi.loc[code].copy()
                        r["Mã"] = code
                        card_fn(r, ui.loc[code], ver)
                    else:
                        _empty_card(code, ver)
        else:
            cols = ["Mã", "Tín hiệu", "Trạng thái", "Giá", "Chg %", "Giá vốn", "Lãi/lỗ %", "Cắt lỗ", "Cách cắt lỗ %", "Mục tiêu",
                    "Cách mục tiêu %", "Score", "RS20", "Wyckoff", "MA align", "Nhóm", "Ghi chú"]
            cols = [c for c in cols if c in v.columns]
            pr = st.column_config.NumberColumn
            st.dataframe(v[cols], hide_index=True, column_config={
                "Giá": pr(format="%.2f"), "Chg %": pr(format="%+.2f%%"), "Giá vốn": pr(format="%.2f"),
                "Lãi/lỗ %": pr(format="%+.1f%%"), "Cắt lỗ": pr(format="%.2f"), "Cách cắt lỗ %": pr(format="%+.1f%%"),
                "Mục tiêu": pr(format="%.2f"), "Cách mục tiêu %": pr(format="%+.1f%%"),
                "Score": pr(format="%.1f"), "RS20": pr("RS vs VNI", format="%.2f")}, **_DF)
            st.caption("“Cách cắt lỗ %” dương nghĩa là giá còn trên mức cắt lỗ bạn đặt.")
            st.subheader("Chi tiết một mã")
            pick = st.selectbox("Chọn mã", list(v["Mã"]), key="wl_pick", label_visibility="collapsed")
            r = v[v["Mã"] == pick].iloc[0]
            d1, d2 = st.columns([3, 2])
            with d1:
                st.markdown(f"**{pick}** · {r['Tín hiệu']}" + (f" · {r['Trạng thái']}" if pd.notna(r.get("Trạng thái")) else ""))
                if pd.notna(r.get("Lý do")):
                    st.write(str(r["Lý do"]))
                if pd.notna(r.get("Hành động")):
                    st.caption(f"Hành động gợi ý của hệ thống: {r['Hành động']}")
                if str(r.get("Ghi chú", "")).strip():
                    st.info(f"📝 {r['Ghi chú']}")
            with d2:
                lines = []
                if pd.notna(r.get("Vùng mua từ")) and pd.notna(r.get("Vùng mua đến")):
                    lines.append(f"Vùng mua hệ thống: {r['Vùng mua từ']:.2f} – {r['Vùng mua đến']:.2f}")
                if pd.notna(r.get("SL hệ thống")):
                    lines.append(f"Cắt lỗ hệ thống: {r['SL hệ thống']:.2f}")
                if pd.notna(r.get("MT1 hệ thống")):
                    lines.append(f"Mục tiêu 1 hệ thống: {r['MT1 hệ thống']:.2f}")
                if str(r.get("Cảnh báo", "")).strip() not in ("", "nan", "Không có"):
                    lines.append(f"Cảnh báo kỹ thuật: {r['Cảnh báo']}")
                for ln in lines:
                    st.markdown(f"- {ln}")
                if st.button("📊 Xem biểu đồ", key="wl_chart", use_container_width=True):
                    on_chart(pick)

    # 2) quản lý / sao lưu
    with st.expander("⚙️ Quản lý danh sách: sửa giá vốn, mục tiêu, cắt lỗ, ghi chú · xóa mã · sao lưu", expanded=False):
        if not w.empty:
            ed = st.data_editor(w.assign(**{"Xóa": False}), hide_index=True, key=f"wl_editor_{ver}", disabled=["Mã"],
                                column_config={"Giá vốn": st.column_config.NumberColumn(format="%.2f", min_value=0.0),
                                               "Mục tiêu": st.column_config.NumberColumn(format="%.2f", min_value=0.0),
                                               "Cắt lỗ": st.column_config.NumberColumn(format="%.2f", min_value=0.0),
                                               "Xóa": st.column_config.CheckboxColumn("Xóa", default=False)}, **_DF)
            if st.button("💾 Lưu thay đổi", key="wl_save"):
                keep = ed[~ed["Xóa"].astype(bool)][COLS]
                err = save(keep)
                st.session_state["wl_ver"] = ver + 1
                if err:
                    st.warning(f"Không ghi được file ({err}).")
                else:
                    st.rerun()
            st.download_button("⬇️ Sao lưu (tải CSV)", _clean(w).to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig"),
                               file_name="watchlist_cua_toi.csv", mime="text/csv")
        up = st.file_uploader("Nhập danh sách từ CSV (cột Mã; có thể thêm Giá vốn, Mục tiêu, Cắt lỗ, Ghi chú)", type=["csv"], key=f"wl_up_{ver}")
        if up is not None and st.button("📥 Nhập vào Watchlist", key="wl_import"):
            try:
                inc = _clean(pd.read_csv(up, dtype={"Mã": str, "Ghi chú": str}, encoding="utf-8-sig"))
                merged = _clean(pd.concat([w, inc], ignore_index=True))      # mã trùng: lấy dòng từ file nhập
                err = save(merged)
                st.session_state["wl_ver"] = ver + 1
            except Exception as e:
                st.error(f"Không đọc được file: {e}")
            else:
                if err:
                    st.warning(f"Không ghi được file ({err}).")
                else:
                    st.rerun()
        st.caption("Danh sách lưu ở data/watchlist_cua_toi.csv trên máy chạy app. Trên Streamlit Cloud file này mất khi app khởi động lại: "
                   "hãy bấm Sao lưu rồi tải file lên thư mục data/ trong GitHub để giữ lâu dài.")
