"""Thị trường > Tổng quan: mở app là biết ngay thị trường đang thế nào.

Gồm 4 thẻ (Xu hướng, Độ rộng, Dòng tiền, Mức độ rủi ro), bản đồ sức mạnh ngành, nhóm dẫn dắt / suy yếu
và số cổ phiếu đang phát tín hiệu MUA / CHỜ MUA. Mọi nhãn đều theo quy tắc ở các hằng số bên dưới
(có thể kiểm tra, sửa tại chỗ). Phần tính toán (trend_state, liquidity_state, risk_state) không phụ thuộc Streamlit.

Số liệu giá lấy từ market_stats.py (cùng nguồn với trang Góc nhìn thị trường), sức mạnh ngành từ sector_dashboard.py.
Thanh khoản và độ rộng chỉ tính trên rổ mã theo dõi của app, không phải toàn thị trường.
"""
from __future__ import annotations

import html

import pandas as pd
import streamlit as st

import market_stats as MS
import market_view as MV
import nav as NAV
import sector_dashboard as SD

# ------------------------------------------------------------------ QUY TẮC (sửa ở đây)
LIQ_BAND = 10.0          # thanh khoản lệch trên / dưới trung bình 20 phiên quá ±10% thì coi là Tăng / Giảm
TREND_UP, TREND_DOWN = 0.75, 0.25    # tỷ lệ điều kiện xu hướng đạt: ≥ 0,75 là Tăng, ≤ 0,25 là Giảm
RISK_LOW, RISK_MID = 1 / 3 + 0.01, 2 / 3 + 0.01    # tỷ lệ điều kiện rủi ro đạt: ≤ ngưỡng đầu là Thấp, ≤ ngưỡng sau là Vừa
MIN_RISK_CHECKS = 3      # cần ít nhất ngần này điều kiện có dữ liệu mới kết luận mức rủi ro
MIN_SECTOR_STOCKS = 3    # ngành có ít hơn ngần này mã không được đưa vào danh sách dẫn dắt / suy yếu
LEADERS_N = 3

CSS = """
<style>
.ov-card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px 20px 14px;margin-bottom:14px;min-height:178px}
.ov-lab{font-size:12px;letter-spacing:.04em;text-transform:uppercase;color:var(--muted);margin-bottom:6px}
.ov-val{font-size:26px;font-weight:800;line-height:1.25;color:var(--txt2)}
.ov-sub{font-size:13px;color:var(--muted);margin:2px 0 8px}
.ov-ev{font-size:13px;line-height:1.65;color:var(--txt)}
.ov-up{color:var(--green)!important}.ov-dn{color:var(--red)!important}.ov-mid{color:var(--amber)!important}
.ov-h{font-weight:800;font-size:16px;color:var(--txt2);margin:10px 0 4px}
.ov-cap{font-size:12px;color:var(--muted);margin-bottom:8px}
.ov-map{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:8px;margin:8px 0 16px}
.ov-tile{border:1px solid var(--line);border-radius:10px;padding:9px 11px;color:var(--txt2)}
.ov-tile b{display:block;font-size:13.5px;line-height:1.3}
.ov-tile span{font-size:12px;color:var(--txt)}
.ov-list{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:12px 18px;margin-bottom:14px}
.ov-row{display:flex;justify-content:space-between;gap:10px;padding:6px 0;border-bottom:1px solid var(--line2);font-size:14px}
.ov-row:last-child{border-bottom:none}
.ov-row small{color:var(--muted);font-size:12px}
.ov-sig{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px 20px 8px;margin-bottom:6px}
.ov-sig .ov-val{font-size:30px}
</style>
"""


# ------------------------------------------------------------------ TÍNH TOÁN (không phụ thuộc Streamlit)
def trend_state(t: pd.DataFrame, day) -> dict | None:
    """Xu hướng theo giá VN-Index: Tăng / Đi ngang / Giảm, kèm các điều kiện đã dùng.

    Điều kiện (chỉ tính điều kiện đủ dữ liệu): đóng cửa > MA20 · MA20 dốc lên so với 5 phiên trước ·
    đóng cửa > MA50 · đáy 10 phiên gần nhất cao hơn đáy 10 phiên liền trước (theo giá đóng cửa).
    """
    if t is None or t.empty or "index" not in t:
        return None
    ix = t["index"].dropna()
    ix = ix[ix.index <= pd.Timestamp(day)]
    if len(ix) < 20 or ix.index[-1] != pd.Timestamp(day):
        return None
    close = float(ix.iloc[-1])
    ma20 = float(ix.tail(20).mean())
    checks: list[tuple[bool, str]] = [(close > ma20, "Đóng cửa trên MA20" if close > ma20 else "Đóng cửa dưới MA20")]
    if len(ix) >= 25:
        ma20_5 = float(ix.iloc[:-5].tail(20).mean())
        checks.append((ma20 > ma20_5, "MA20 dốc lên" if ma20 > ma20_5 else "MA20 dốc xuống"))
    if len(ix) >= 50:
        ma50 = float(ix.tail(50).mean())
        checks.append((close > ma50, "Đóng cửa trên MA50" if close > ma50 else "Đóng cửa dưới MA50"))
    lo_now, lo_prev = float(ix.tail(10).min()), float(ix.iloc[-20:-10].min())
    checks.append((lo_now > lo_prev, "Đáy sau cao hơn đáy trước" if lo_now > lo_prev else "Đáy sau không cao hơn đáy trước"))
    ratio = sum(ok for ok, _ in checks) / len(checks)
    label = "Tăng" if ratio >= TREND_UP else "Giảm" if ratio <= TREND_DOWN else "Đi ngang"
    return {"label": label, "checks": checks, "close": close, "ma20": ma20,
            "pts": float(ix.iloc[-1] - ix.iloc[-2]) if len(ix) > 1 else None,
            "pct": (close / float(ix.iloc[-2]) - 1) * 100 if len(ix) > 1 and ix.iloc[-2] else None}


def breadth_state(s: dict | None) -> dict | None:
    """Độ rộng: Tăng nếu số mã tăng nhiều hơn số mã giảm, Giảm nếu ngược lại."""
    if not s or "up" not in s:
        return None
    up, down = int(s["up"]), int(s["down"])
    label = "Tăng" if up > down else "Giảm" if down > up else "Cân bằng"
    tot = up + down + int(s["flat"])
    return {"label": label, "up": up, "down": down, "flat": int(s["flat"]), "n": int(s["n"]),
            "up_pct": up / tot * 100 if tot else None}


def liquidity_state(s: dict | None) -> dict | None:
    """Dòng tiền (thanh khoản) so với trung bình 20 phiên: Tăng / Đi ngang / Giảm."""
    if not s or s.get("value_avg20_pct") is None:
        return None
    v = s["value_avg20_pct"]
    label = "Tăng" if v > LIQ_BAND else "Giảm" if v < -LIQ_BAND else "Đi ngang"
    return {"label": label, "value": s["value"], "vs_prev": s.get("value_prev_pct"), "vs_avg20": v}


def risk_state(trend: dict | None, s: dict | None, fx: dict | None) -> dict | None:
    """Mức độ rủi ro = tỷ lệ điều kiện rủi ro đang xảy ra trên số điều kiện có dữ liệu (cần ≥ MIN_RISK_CHECKS)."""
    checks: list[tuple[bool, str]] = []
    if trend:
        checks.append((trend["close"] < trend["ma20"], "VN-Index dưới MA20"))
        dn = [ok for ok, txt in trend["checks"] if txt.startswith("MA20 dốc")]
        if dn:
            checks.append((not dn[0], "MA20 dốc xuống"))
    if s and "up" in s:
        checks.append((s["down"] > s["up"], "Số mã giảm nhiều hơn số mã tăng"))
    if s and s.get("value_avg20_pct") is not None:
        checks.append((s["value_avg20_pct"] < 0, "Thanh khoản thấp hơn trung bình 20 phiên"))
    if fx:
        checks.append((fx["value"] < 0, "Khối ngoại bán ròng"))
    if len(checks) < MIN_RISK_CHECKS:
        return None
    hits = [txt for ok, txt in checks if ok]
    ratio = len(hits) / len(checks)
    label = "Thấp" if ratio <= RISK_LOW else "Vừa" if ratio <= RISK_MID else "Cao"
    return {"label": label, "hits": hits, "n_hit": len(hits), "n": len(checks)}


# ------------------------------------------------------------------ GIAO DIỆN
def _cls(label: str, good: str = "Tăng", bad: str = "Giảm") -> str:
    return "ov-up" if label == good else "ov-dn" if label == bad else "ov-mid"


def _card(label: str, value: str, vcls: str, sub: str, ev: str) -> str:
    return (f'<div class="ov-card"><div class="ov-lab">{label}</div><div class="ov-val {vcls}">{value}</div>'
            f'<div class="ov-sub">{sub}</div><div class="ov-ev">{ev}</div></div>')


def _no_data(label: str, why: str) -> str:
    return _card(label, "Chưa đủ dữ liệu", "", why, "")


def _mark(ok: bool, txt: str) -> str:
    return f'<span class="{"ov-up" if ok else "ov-dn"}">{"✓" if ok else "✗"}</span> {html.escape(txt)}'


def _cards_html(trend, breadth, liq, risk, fx) -> list[str]:
    out = []
    if trend:
        sub = f'VN-Index {MV._n(trend["close"], 2)}'
        if trend["pts"] is not None:
            sub += f' ({MV._sg(trend["pts"], 2)} điểm, {MV._sg(trend["pct"], 2, "%")})'
        out.append(_card("Xu hướng", trend["label"], _cls(trend["label"]), sub,
                         "<br>".join(_mark(ok, txt.replace("Đóng cửa", "VN-Index đóng cửa")) for ok, txt in trend["checks"])))
    else:
        out.append(_no_data("Xu hướng", "Cần chuỗi VN-Index (mã VNINDEX) tối thiểu 20 phiên trong data/eod_prices.csv."))
    if breadth:
        ev = f'{breadth["flat"]} mã đứng giá · rổ {breadth["n"]} mã'
        if breadth["up_pct"] is not None:
            ev += f'<br>Mã tăng chiếm {MV._n(breadth["up_pct"], 0)}% số mã có biến động'
        out.append(_card("Độ rộng", breadth["label"], _cls(breadth["label"]),
                         f'<span class="ov-up">{breadth["up"]}</span> tăng / <span class="ov-dn">{breadth["down"]}</span> giảm', ev))
    else:
        out.append(_no_data("Độ rộng", "Chưa có giá của phiên này."))
    if liq:
        ev = []
        if liq["vs_prev"] is not None:
            ev.append(f'{MV._sg(liq["vs_prev"], 1, "%")} so với phiên trước')
        ev.append(f'{MV._sg(liq["vs_avg20"], 1, "%")} so với trung bình 20 phiên')
        if fx:
            ev.append(f'Khối ngoại {"mua" if fx["value"] > 0 else "bán"} ròng {MV._n(abs(fx["value"]), 0)} tỷ')
        out.append(_card("Dòng tiền (thanh khoản)", f'Thanh khoản {liq["label"].lower()}', _cls(liq["label"]),
                         f'{MV._n(liq["value"], 0)} tỷ đồng (rổ theo dõi)', "<br>".join(ev)))
    else:
        out.append(_no_data("Dòng tiền (thanh khoản)", "Cần khối lượng khớp lệnh tối thiểu 11 phiên."))
    if risk:
        ev = "<br>".join(f'<span class="ov-dn">✗</span> {html.escape(h)}' for h in risk["hits"]) or \
            '<span class="ov-up">✓</span> Không có điều kiện rủi ro nào xảy ra'
        out.append(_card("Mức độ rủi ro", risk["label"], _cls(risk["label"], "Thấp", "Cao"),
                         f'{risk["n_hit"]}/{risk["n"]} điều kiện rủi ro đang xảy ra', ev))
    else:
        out.append(_no_data("Mức độ rủi ro", f"Cần tối thiểu {MIN_RISK_CHECKS} điều kiện có dữ liệu."))
    return out


def _tile(name: str, rs: float, n: int) -> str:
    a = min(0.14 + abs(rs) / 12 * 0.5, 0.64)
    bg = f"rgba(45,212,167,{a:.2f})" if rs >= 0 else f"rgba(255,107,129,{a:.2f})"
    return f'<div class="ov-tile" style="background:{bg}"><b>{html.escape(name)}</b><span>{rs:+.1f} điểm · {n} mã</span></div>'


def _rank_rows(d: pd.DataFrame, rs_col: str) -> str:
    rows = "".join(f'<div class="ov-row"><span>{html.escape(str(r["Nhóm ngành"]))}<br><small>{html.escape(str(r["Trạng thái"]))}'
                   f' · {int(r["Số mã có dữ liệu"])} mã</small></span>'
                   f'<b class="{"ov-up" if r[rs_col] > 0 else "ov-dn"}">{r[rs_col]:+.1f}</b></div>' for _, r in d.iterrows())
    return f'<div class="ov-list">{rows or "<small>Chưa có nhóm phù hợp.</small>"}</div>'


def render(raw, data_key: str, buy_n: int | None = None, wait_n: int | None = None):
    st.markdown(CSS, unsafe_allow_html=True)
    st.title("🧭 Tổng quan thị trường")
    st.caption("Mở app là biết ngay thị trường đang thế nào. Nhãn tính theo quy tắc ghi ngay trên từng thẻ; "
               "thanh khoản và độ rộng chỉ tính trên rổ mã theo dõi của app, không phải toàn thị trường.")

    t = MV._daily(raw, data_key)
    if t is None or t.empty:
        st.info("Chưa có dữ liệu giá để tính tổng quan. Hãy cập nhật data/eod_prices.csv hoặc chọn nguồn dữ liệu ở thanh bên.")
        return
    day = t.index[-1]
    s = MS.stats_for(t, day)
    try:
        fx = MS.foreign_stats(MV._foreign_series(MV.load_entries(MV._stamp())), day)
    except Exception:  # noqa: BLE001  thiếu số khối ngoại thì bỏ qua, không làm hỏng trang
        fx = None
    trend, breadth, liq = trend_state(t, day), breadth_state(s), liquidity_state(s)
    risk = risk_state(trend, s, fx)

    st.markdown(f'<div class="ov-cap">Phiên <b>{day:%d/%m/%Y}</b></div>', unsafe_allow_html=True)
    cards = _cards_html(trend, breadth, liq, risk, fx)
    for (a, b) in ((0, 1), (2, 3)):
        c1, c2 = st.columns(2, gap="medium")
        c1.markdown(cards[a], unsafe_allow_html=True)
        c2.markdown(cards[b], unsafe_allow_html=True)

    # ---- bản đồ sức mạnh ngành
    st.markdown('<div class="ov-h">Bản đồ sức mạnh ngành</div>', unsafe_allow_html=True)
    period = st.segmented_control("Khung", list(SD.PERIODS), default="1 tháng", key="ov_period",
                                  label_visibility="collapsed") or "1 tháng"
    rs_col = f"RS {period} (điểm %) "
    try:
        metrics, info = _sector_cached(raw, data_key)
    except Exception as e:  # noqa: BLE001
        metrics, info = pd.DataFrame(), {"error": f"{type(e).__name__}"}
    if metrics.empty or rs_col not in metrics or metrics[rs_col].notna().sum() == 0:
        st.info("Chưa đủ dữ liệu để tính sức mạnh ngành.")
    else:
        m = metrics[(metrics["Số mã có dữ liệu"] > 0) & metrics[rs_col].notna()].sort_values(rs_col, ascending=False)
        bench, src = info["benchmark"][period]
        st.markdown(f'<div class="ov-cap">RS = hiệu suất {period} bình quân đều các mã trong ngành trừ hiệu suất tham chiếu '
                    f'({html.escape(src)}). Xanh = mạnh hơn tham chiếu, đỏ = yếu hơn.</div>', unsafe_allow_html=True)
        st.markdown('<div class="ov-map">' + "".join(_tile(r["Nhóm ngành"], r[rs_col], int(r["Số mã có dữ liệu"]))
                                                      for _, r in m.iterrows()) + "</div>", unsafe_allow_html=True)
        big = m[m["Số mã có dữ liệu"] >= MIN_SECTOR_STOCKS]
        lead = big[big[rs_col] > 0].head(LEADERS_N)
        weak = big[big[rs_col] < 0].sort_values(rs_col).head(LEADERS_N)
        l1, l2 = st.columns(2, gap="medium")
        l1.markdown('<div class="ov-h">Nhóm dẫn dắt</div>' + _rank_rows(lead, rs_col), unsafe_allow_html=True)
        l2.markdown('<div class="ov-h">Nhóm suy yếu</div>' + _rank_rows(weak, rs_col), unsafe_allow_html=True)
        st.caption(f"Danh sách dẫn dắt / suy yếu chỉ xét ngành có từ {MIN_SECTOR_STOCKS} mã có dữ liệu trở lên.")
        if st.button("Xem chi tiết Nhóm ngành →", key="ov_go_sector"):
            NAV.goto("Thị trường", "Nhóm ngành")

    # ---- số cổ phiếu đang phát tín hiệu
    st.markdown('<div class="ov-h">Cổ phiếu đang phát tín hiệu</div>', unsafe_allow_html=True)
    s1, s2 = st.columns(2, gap="medium")
    for col, lab, n, cls, main, sub, key in ((s1, "Tín hiệu MUA", buy_n, "ov-up", "Bộ lọc & Backtest", "Mua ngay", "ov_go_buy"),
                                             (s2, "Đang CHỜ MUA", wait_n, "ov-mid", "Bộ lọc & Backtest", "Chờ mua", "ov_go_wait")):
        with col:
            st.markdown(f'<div class="ov-sig"><div class="ov-lab">{lab}</div>'
                        f'<div class="ov-val {cls}">{"—" if n is None else f"{n} mã"}</div></div>', unsafe_allow_html=True)
            if st.button(f"Mở {sub} →", key=key, use_container_width=True):
                NAV.goto(main, sub)
    st.caption("Số mã lấy từ mục Mua ngay và Chờ mua (mã Mua ngay không đếm lại ở Chờ mua). "
               "Nội dung chỉ mang tính tham khảo, không phải khuyến nghị đầu tư.")


@st.cache_data(show_spinner="Đang tính sức mạnh ngành...")
def _sector_cached(_raw, key: str):
    return SD.calculate_sector_metrics(_raw)
