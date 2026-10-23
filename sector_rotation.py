"""Ngành > Cảnh báo luân chuyển dòng tiền: phát hiện dòng tiền đổi hướng giữa các ngành TRƯỚC khi nhìn vào VN-Index.

Chỉ số ngành = bình quân đều lợi suất ngày của các mã trong ngành (watchlist.GROUPS) có dữ liệu; RS ngành = chỉ số ngành / VN-Index
(hoặc proxy thị trường nếu file không có VN-Index, giống phần còn lại của app). Năm loại cảnh báo (ngưỡng ở CFG):

  1. RS_UP     Ngành tăng RS liên tục: RS ngành tăng trong `rs_streak` phiên liền nhau.
  2. BREADTH   Tỷ lệ cổ phiếu trên MA20 tăng nhanh: tăng >= `breadth_jump` điểm % so với `breadth_lag` phiên trước (và đã >= `breadth_min`%).
  3. LIQ       Thanh khoản ngành cao hơn trung bình nhưng giá chưa tăng quá xa: GTGD TB 5 phiên >= `liq_ratio` lần TB20 và
               giá ngành tăng <= `liq_max_gain`% trong 10 phiên.
  4. LEADER    Cổ phiếu dẫn đầu vừa vượt nền với khối lượng xác nhận: trong `brk_recent` phiên gần nhất, đóng cửa vượt đỉnh `brk_base` phiên
               trước đó với khối lượng >= `brk_vol` lần TB20, và mã nằm trong `leader_top` mã RS 20 phiên cao nhất ngành.
  5. WEAK      Ngành từng mạnh bắt đầu mất RS: RS 20 phiên cách đây `weak_lag` phiên > 1, RS ngành hiện thấp hơn `weak_lag` phiên trước,
               và độ rộng suy yếu (tỷ lệ trên MA20 giảm >= `breadth_jump` điểm %, hoặc >= `break_share`% mã vừa thủng MA20 trong `breadth_lag` phiên).

1-4 là tín hiệu dòng tiền đang vào ngành; 5 là dòng tiền đang rời ngành. Chỉ để tham khảo, không phải khuyến nghị đầu tư.
Phần tính không phụ thuộc Streamlit.
"""
from __future__ import annotations

import html as _h

import numpy as np
import pandas as pd

CFG = {
    "min_members": 3,       # ngành có ít hơn x mã có dữ liệu thì bỏ qua (chỉ số ngành không đủ đại diện)
    "min_sessions": 45,     # số phiên tối thiểu
    "rs_streak": 5,
    "breadth_lag": 5, "breadth_jump": 15.0, "breadth_min": 30.0,
    "liq_ratio": 1.2, "liq_max_gain": 8.0, "liq_days": 10,
    "brk_recent": 3, "brk_base": 20, "brk_vol": 1.5, "leader_top": 3, "leader_rs_days": 20,
    "weak_lag": 10, "break_share": 25.0,
}

RS_UP, BREADTH, LIQ, LEADER, WEAK = "RS_UP", "BREADTH", "LIQ", "LEADER", "WEAK"
ALERTS = {
    RS_UP:   ("📈", "Ngành tăng RS liên tục", "in", f"RS ngành so với VN-Index tăng liên tiếp {CFG['rs_streak']} phiên."),
    BREADTH: ("🌊", "Độ rộng tăng nhanh", "in", f"Tỷ lệ cổ phiếu trên MA20 tăng ≥ {CFG['breadth_jump']:.0f} điểm % trong {CFG['breadth_lag']} phiên."),
    LIQ:     ("💧", "Tiền vào, giá chưa chạy xa", "in", f"GTGD ngành TB5 ≥ {CFG['liq_ratio']:.1f} lần TB20 nhưng giá ngành tăng ≤ {CFG['liq_max_gain']:.0f}% trong {CFG['liq_days']} phiên."),
    LEADER:  ("🚀", "Cổ phiếu dẫn đầu vừa vượt nền", "in", f"Mã nằm top {CFG['leader_top']} RS ngành, đóng cửa vượt đỉnh {CFG['brk_base']} phiên với khối lượng ≥ {CFG['brk_vol']:.1f} lần TB20."),
    WEAK:    ("⚠️", "Ngành mạnh bắt đầu mất RS", "out", "Ngành từng mạnh, RS đang giảm và độ rộng suy yếu / nhiều mã thủng MA20."),
}
ORDER = [RS_UP, BREADTH, LIQ, LEADER, WEAK]


def _prep(raw: pd.DataFrame) -> dict:
    """Bảng pivot ngày x mã: đóng cửa, cao nhất, khối lượng."""
    d = raw.copy()
    d["Mã"] = d["Mã"].astype(str).str.strip().str.upper()
    d["Ngày"] = pd.to_datetime(d["Ngày"], errors="coerce", dayfirst=True)
    out = {}
    for key, col in (("c", "Giá đóng cửa"), ("h", "Giá cao nhất"), ("v", "Khối lượng khớp lệnh")):
        if col not in d.columns:
            out[key] = pd.DataFrame()
            continue
        x = d.assign(**{col: pd.to_numeric(d[col], errors="coerce")}).dropna(subset=["Ngày"])
        out[key] = x.drop_duplicates(["Mã", "Ngày"], keep="last").pivot(index="Ngày", columns="Mã", values=col).sort_index()
    return out


def _streak_up(s: pd.Series) -> int:
    """Số phiên tăng liên tiếp tính từ phiên cuối."""
    diff = s.dropna().diff().dropna().to_numpy()
    n = 0
    for x in diff[::-1]:
        if x > 0:
            n += 1
        else:
            break
    return n


def analyze_sector(members: list[str], P: dict, mkt: pd.Series) -> dict | None:
    """Số liệu + cờ cảnh báo của một ngành; None nếu thiếu dữ liệu."""
    c, h, v = P["c"], P["h"], P["v"]
    cols = [m for m in members if m in c.columns and c[m].notna().sum() >= CFG["min_sessions"]]
    if len(cols) < CFG["min_members"]:
        return None
    px = c[cols]
    ret = px.pct_change(fill_method=None)
    idx = (1 + ret.mean(axis=1, skipna=True).fillna(0)).cumprod()
    m = mkt.reindex(idx.index).ffill()
    if m.isna().all():
        return None
    rs = (idx / m).dropna()
    if len(rs) < CFG["min_sessions"]:
        return None

    out = {"members": cols, "n": len(cols), "alerts": {}, "leaders": []}
    lag = CFG["breadth_lag"]
    ma20 = px.rolling(20).mean()
    above = (px > ma20).where(ma20.notna())

    def breadth_at(i):      # % mã trên MA20 tại phiên thứ i từ cuối (i = 0 là hôm nay)
        row = above.iloc[-1 - i].dropna()
        return float(row.mean() * 100) if len(row) else np.nan
    b_now, b_prev = breadth_at(0), breadth_at(lag)
    out["breadth"], out["breadth_chg"] = b_now, b_now - b_prev if pd.notna(b_now) and pd.notna(b_prev) else np.nan

    # 1. RS tăng liên tục
    st_ = _streak_up(rs)
    out["rs_streak"] = st_
    out["rs_chg5"] = float((rs.iloc[-1] / rs.iloc[-1 - lag] - 1) * 100)
    out["rs_20"] = float(rs.iloc[-1] / rs.iloc[-21]) if len(rs) > 21 else np.nan
    if st_ >= CFG["rs_streak"]:
        out["alerts"][RS_UP] = f"RS ngành tăng {st_} phiên liên tiếp (+{out['rs_chg5']:.1f}% trong {lag} phiên)."

    # 2. Độ rộng tăng nhanh
    if pd.notna(out["breadth_chg"]) and out["breadth_chg"] >= CFG["breadth_jump"] and b_now >= CFG["breadth_min"]:
        out["alerts"][BREADTH] = f"{b_now:.0f}% mã trên MA20, tăng {out['breadth_chg']:.0f} điểm % so với {lag} phiên trước ({b_prev:.0f}%)."

    # 3. Thanh khoản cao, giá chưa tăng xa
    if not v.empty:
        val = (px * v.reindex(columns=cols)).where(px.notna()).sum(axis=1, min_count=1)
        if val.notna().sum() >= 20:
            r5, a20 = float(val.tail(5).mean()), float(val.tail(20).mean())
            ratio = r5 / a20 if a20 > 0 else np.nan
            g10 = float((idx.iloc[-1] / idx.iloc[-1 - CFG["liq_days"]] - 1) * 100)
            out["liq_ratio"], out["gain10"] = ratio, g10
            if pd.notna(ratio) and ratio >= CFG["liq_ratio"] and g10 <= CFG["liq_max_gain"]:
                out["alerts"][LIQ] = f"GTGD TB5 = {ratio:.2f} lần TB20, giá ngành chỉ {g10:+.1f}% trong {CFG['liq_days']} phiên."

    # 4. Cổ phiếu dẫn đầu vừa vượt nền
    n_rs = CFG["leader_rs_days"]
    mm = m.reindex(px.index)
    leaders = []
    if len(px) > n_rs + 1 and not h.empty and not v.empty:
        rs_stock = (px.iloc[-1] / px.iloc[-1 - n_rs]) / (mm.iloc[-1] / mm.iloc[-1 - n_rs])
        top = set(rs_stock.dropna().sort_values(ascending=False).head(CFG["leader_top"]).index)
        for s in top:
            hs, vs, cs = h[s], v[s], px[s]
            for k in range(CFG["brk_recent"]):      # k = 0 là hôm nay
                end = len(cs) - k
                if end - CFG["brk_base"] - 1 < 0:
                    break
                base_hi = hs.iloc[end - 1 - CFG["brk_base"]:end - 1].max()
                avg_v = vs.iloc[end - 1 - 20:end - 1].mean()
                if pd.notna(base_hi) and cs.iloc[end - 1] > base_hi and avg_v > 0 and vs.iloc[end - 1] >= CFG["brk_vol"] * avg_v:
                    leaders.append({"Mã": s, "ago": k, "px": float(cs.iloc[-1]), "brk": float(base_hi),
                                    "vol": float(vs.iloc[end - 1] / avg_v), "rs": float(rs_stock[s])})
                    break
    out["leaders"] = sorted(leaders, key=lambda x: (x["ago"], -x["rs"]))
    if leaders:
        txt = ", ".join(f"{x['Mã']} ({'hôm nay' if x['ago'] == 0 else str(x['ago']) + ' phiên trước'}, vol {x['vol']:.1f}×)" for x in out["leaders"])
        out["alerts"][LEADER] = f"Dẫn đầu vừa vượt nền: {txt}."

    # 5. Ngành từng mạnh bắt đầu mất RS
    wl = CFG["weak_lag"]
    if len(rs) > 20 + wl:
        rs20_then = float(rs.iloc[-1 - wl] / rs.iloc[-1 - wl - 20])
        out["rs20_then"] = rs20_then
        was_strong = rs20_then > 1.0
        falling = rs.iloc[-1] < rs.iloc[-1 - wl]
        crossed = 0
        elig = 0
        for s in cols:
            a, mm20 = px[s], ma20[s]
            if pd.isna(mm20.iloc[-1]) or pd.isna(mm20.iloc[-1 - lag]):
                continue
            elig += 1
            if a.iloc[-1] < mm20.iloc[-1] and a.iloc[-1 - lag] >= mm20.iloc[-1 - lag]:
                crossed += 1
        share = crossed / elig * 100 if elig else np.nan
        out["break_share"] = share
        breadth_weak = pd.notna(out["breadth_chg"]) and out["breadth_chg"] <= -CFG["breadth_jump"]
        many_breaks = pd.notna(share) and share >= CFG["break_share"]
        if was_strong and falling and (breadth_weak or many_breaks):
            why = []
            if breadth_weak:
                why.append(f"độ rộng giảm {abs(out['breadth_chg']):.0f} điểm % ({b_now:.0f}% mã trên MA20)")
            if many_breaks:
                why.append(f"{share:.0f}% mã vừa thủng MA20")
            out["alerts"][WEAK] = (f"RS 20 phiên cách đây {wl} phiên = {rs20_then:.2f} (mạnh), nay RS ngành thấp hơn {wl} phiên trước; " + "; ".join(why) + ".")
    return out


def build(raw: pd.DataFrame, mkt: pd.Series, groups: dict) -> pd.DataFrame:
    """Bảng ngành x cảnh báo. Cột: Nhóm ngành, Số mã, các cờ (bool) theo ORDER, 'Chi tiết' (dict), 'Số cảnh báo vào', 'Số liệu'."""
    P = _prep(raw)
    if P["c"].empty:
        return pd.DataFrame()
    rows = []
    for sector, syms in groups.items():
        members = list(dict.fromkeys(str(s).upper() for s in syms))
        a = analyze_sector(members, P, mkt)
        if a is None:
            continue
        row = {"Nhóm ngành": sector, "Số mã": a["n"], "Mã": ", ".join(a["members"]), "Chi tiết": a["alerts"], "Số liệu": a,
               "RS 5 phiên %": a["rs_chg5"], "Trên MA20 %": a["breadth"], "Độ rộng Δ": a["breadth_chg"],
               "GTGD TB5/TB20": a.get("liq_ratio", np.nan), "Giá 10 phiên %": a.get("gain10", np.nan)}
        for k in ORDER:
            row[k] = k in a["alerts"]
        row["Số cảnh báo vào"] = sum(row[k] for k in (RS_UP, BREADTH, LIQ, LEADER))
        rows.append(row)
    if not rows:
        return pd.DataFrame()
    d = pd.DataFrame(rows)
    return d.sort_values(["Số cảnh báo vào", WEAK, "RS 5 phiên %"], ascending=[False, True, False]).reset_index(drop=True)


# ------------------------------------------------------------------ HTML
CSS = """<style>
.rt-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(330px,1fr));gap:14px;margin:8px 0 18px}
.rt-card{background:var(--card);border:1px solid var(--line);border-left:4px solid var(--rt-c);border-radius:10px;padding:14px 16px}
.rt-card.in{--rt-c:var(--green)}.rt-card.out{--rt-c:var(--red)}
.rt-h{display:flex;justify-content:space-between;align-items:center;gap:8px}
.rt-n{font-size:18px;font-weight:700;color:var(--txt2)}
.rt-b{font-size:11.5px;font-weight:700;padding:3px 10px;border-radius:999px;background:var(--tag-green-bg);color:var(--tag-green-fg);white-space:nowrap}
.rt-card.out .rt-b{background:var(--tag-red-bg);color:var(--red)}
.rt-m{display:grid;grid-template-columns:repeat(3,1fr);gap:6px;margin:10px 0;font-size:12px;color:var(--muted)}
.rt-m b{display:block;font-size:15px;color:var(--txt2);font-variant-numeric:tabular-nums}
.rt-w{margin-top:8px;padding:8px 10px;border-radius:8px;background:var(--card2);font-size:13px;line-height:1.5;color:var(--txt)}
.rt-w small{display:block;color:var(--muted);font-size:11px;font-weight:700;letter-spacing:.04em;text-transform:uppercase;margin-bottom:2px}
.rt-mem{margin-top:8px;font-size:12px;color:var(--muted)}
</style>"""


def _f(x, fmt="{:+.1f}", na="—"):
    return na if x is None or (isinstance(x, float) and not np.isfinite(x)) else fmt.format(x)


def card_html(r: pd.Series, only: str | None = None) -> str:
    """Thẻ một ngành. only = mã cảnh báo cần nêu (None: nêu tất cả cảnh báo của ngành)."""
    e = _h.escape
    a = r["Số liệu"]
    keys = [only] if only else [k for k in ORDER if k in a["alerts"]]
    kind = "out" if WEAK in keys and len(keys) == 1 else "in"
    badges = (f'<span class="rt-b">{ALERTS[only][0]} {e(ALERTS[only][1])}</span>' if only
              else "".join(f'<span class="rt-b" style="margin-left:4px">{ALERTS[k][0]}</span>' for k in keys))
    why = "".join(f'<div class="rt-w"><small>{e(ALERTS[k][1])}</small>{e(a["alerts"][k])}</div>' for k in keys)
    return (f'<div class="rt-card {kind}"><div class="rt-h"><span class="rt-n">{e(str(r["Nhóm ngành"]))}</span><span>{badges}</span></div>'
            f'<div class="rt-m"><div>RS 5 phiên<b>{_f(r["RS 5 phiên %"])}%</b></div>'
            f'<div>Trên MA20<b>{_f(r["Trên MA20 %"], "{:.0f}")}%</b></div>'
            f'<div>GTGD TB5/TB20<b>{_f(r["GTGD TB5/TB20"], "{:.2f}")}</b></div></div>'
            f'{why}<div class="rt-mem">{a["n"]} mã: {e(r["Mã"])}</div></div>')


def render(raw: pd.DataFrame, mkt: pd.Series, groups: dict, mkt_src: str = "") -> None:
    import streamlit as st

    st.title("🔔 Cảnh báo luân chuyển dòng tiền")
    st.caption("Phát hiện thay đổi dòng tiền giữa các ngành trước khi nhìn vào VN-Index. "
               "Chỉ số ngành = bình quân đều các mã trong ngành; RS ngành so với " + (mkt_src or "VN-Index") + ". "
               "Chỉ để tham khảo, không phải khuyến nghị đầu tư.")
    st.markdown(CSS, unsafe_allow_html=True)
    d = build(raw, mkt, groups)
    if d.empty:
        st.info("Chưa đủ dữ liệu (cần ít nhất %d phiên và %d mã/ngành)." % (CFG["min_sessions"], CFG["min_members"]))
        return
    m = st.columns(5)
    for col, k in zip(m, ORDER):
        col.metric(f"{ALERTS[k][0]} {ALERTS[k][1]}", int(d[k].sum()), help=ALERTS[k][3])

    tab_all, *tabs = st.tabs(["Tổng hợp"] + [f"{ALERTS[k][0]} {ALERTS[k][1]} ({int(d[k].sum())})" for k in ORDER])
    with tab_all:
        hit = d[d[ORDER].any(axis=1)]
        if hit.empty:
            st.info("Hiện chưa có ngành nào phát cảnh báo luân chuyển.")
        else:
            st.markdown(CSS + '<div class="rt-grid">' + "".join(card_html(r) for _, r in hit.iterrows()) + "</div>", unsafe_allow_html=True)
        with st.expander("Xem dạng bảng (tất cả ngành)"):
            show = d[["Nhóm ngành", "Số mã", "RS 5 phiên %", "Trên MA20 %", "Độ rộng Δ", "GTGD TB5/TB20", "Giá 10 phiên %"] + ORDER].rename(
                columns={k: ALERTS[k][1] for k in ORDER} | {"Độ rộng Δ": "Δ trên MA20 (điểm %)"})
            st.dataframe(show, hide_index=True, use_container_width=True,
                         column_config={"RS 5 phiên %": st.column_config.NumberColumn(format="%+.1f"),
                                        "Trên MA20 %": st.column_config.NumberColumn(format="%.0f"),
                                        "Δ trên MA20 (điểm %)": st.column_config.NumberColumn(format="%+.0f"),
                                        "GTGD TB5/TB20": st.column_config.NumberColumn(format="%.2f"),
                                        "Giá 10 phiên %": st.column_config.NumberColumn(format="%+.1f")})
    for tab, k in zip(tabs, ORDER):
        with tab:
            st.caption(ALERTS[k][3])
            sub = d[d[k]]
            if sub.empty:
                st.info("Hiện chưa có ngành nào.")
            else:
                st.markdown('<div class="rt-grid">' + "".join(card_html(r, k) for _, r in sub.iterrows()) + "</div>", unsafe_allow_html=True)
