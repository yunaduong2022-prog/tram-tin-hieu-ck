"""Ngành > Vị thế cổ phiếu ngành: chọn một ngành, xem cổ phiếu nào đang dẫn đầu và cổ phiếu nào tụt lại.

Mục tiêu: tìm MÃ DẪN ĐẦU, không chỉ tìm ngành mạnh. Với ngành được chọn, trang hiển thị:
    1) Bảng xếp hạng toàn bộ mã trong ngành (hạng RS, giá, Score, RS, ROE, trạng thái, vị thế).
    2) Bốn góc nhìn, mỗi góc nhìn là danh sách thẻ (cùng bố cục thẻ MUA / CHỜ MUA của app):
       - Mạnh nhất ngành theo RS
       - Xu hướng tăng và thanh khoản cải thiện
       - Đang tích lũy, gần điểm mua hoặc đã vượt nền
       - Yếu hơn ngành hoặc có tín hiệu suy yếu
    Thẻ chỉ bổ sung một khối "Vị thế trong ngành" (hạng RS, RS so với ngành, thanh khoản), không thêm chỉ báo mới.

Mọi nhãn theo quy tắc ở CFG bên dưới. Phần tính (build_sector_frame) không phụ thuộc Streamlit.
Chỉ để tham khảo, không phải khuyến nghị đầu tư.
"""
from __future__ import annotations

import html as _html
import inspect

import numpy as np
import pandas as pd
import streamlit as st

import engine as E
import sector_dashboard as SD
import waiting_buy as WB

# ------------------------------------------------------------------ QUY TẮC (sửa ở đây)
CFG = {
    "leader_top_n": 3,        # số mã dẫn đầu RS tối đa (ngành ít mã thì lấy tối đa 1/2 số mã)
    "leader_min_rs": E.RS_STABLE,   # mã dẫn đầu phải có RS20 >= ngưỡng này (không gọi "dẫn đầu" khi chính nó cũng thua thị trường)
    "ret_sessions": 20,       # luật "yếu hơn ngành" luôn đo trên 20 phiên (không phụ thuộc khung xếp hạng đang chọn, tránh nhiễu 1 phiên)
    "liq_up": 1.10,           # GTGD TB 5 phiên / TB 20 phiên >= ngưỡng => thanh khoản cải thiện
    "weak_gap": -3.0,         # yếu hơn ngành: hiệu suất 20 phiên thấp hơn TB ngành từ x điểm % ...
    "min_stocks": 3,          # ngành có ít hơn ngần này mã thì xếp hạng chỉ mang tính tham khảo
}

# Khung xếp hạng RS: số phiên giao dịch. Tháng = 20 phiên để khớp RS20 của app.
PERIODS = {"Ngày": 1, "Tuần": 5, "Tháng": 20, "3 Tháng": 63}
DEFAULT_PERIOD = "Tháng"

VIEW_LEAD, VIEW_TREND, VIEW_ACCUM, VIEW_WEAK = (
    "Mạnh nhất theo RS", "Xu hướng tăng + thanh khoản", "Tích lũy / gần điểm mua", "Yếu hơn ngành / suy yếu")
VIEWS = [VIEW_LEAD, VIEW_TREND, VIEW_ACCUM, VIEW_WEAK]
VIEW_HELP = {
    VIEW_LEAD: "Các mã có RS cao nhất ngành ở khung đang chọn (Ngày / Tuần / Tháng / 3 Tháng, so với VN-Index hoặc proxy thị trường), chưa có tín hiệu suy yếu.",
    VIEW_TREND: "Giá trên MA20, MA10 trên MA20, trung hạn không giảm, và dòng tiền đang quay lại (GTGD 5 phiên so với TB20, "
                "khối lượng tăng dần hoặc dòng tiền sớm).",
    VIEW_ACCUM: "Các mã thuộc nhóm *Điểm mua đã xác nhận* hoặc *Sắp có điểm mua* của mục Chờ mua: đã có tín hiệu mua, "
                "đang test hỗ trợ, siết nền giá hoặc gần vùng mua.",
    VIEW_WEAK: "Mã có tín hiệu hạ tỷ trọng / suy yếu, tín hiệu bán giá-khối lượng, hoặc thua trung bình ngành rõ rệt "
               "khi giá nằm dưới MA20.",
}
# Thứ tự ưu tiên trong góc nhìn "Tích lũy / gần điểm mua" (mã có thể mua ngay trước, rồi tới các trạng thái chờ)
_ACCUM_ORDER = {WB.GOOD_ENTRY: 0, WB.BUY_SIGNAL: 1, WB.WATCH: 2, WB.NEAR_ZONE: 3, WB.EARLY_UP: 4, WB.ACCUM: 5}

CSS = """
<style>
.srt-wrap{overflow-x:auto;border:1px solid var(--line);border-radius:10px;background:var(--card);margin-bottom:10px}
.srt{border-collapse:collapse;width:100%;font-size:13px;color:var(--txt);table-layout:auto}
.srt th{background:var(--bg2);color:var(--txt2);font-weight:700;text-align:center;padding:9px 6px;border-bottom:1px solid var(--line);
  line-height:1.3;white-space:normal;vertical-align:middle}
.srt td{padding:8px 6px;border-bottom:1px solid var(--line2);text-align:center;vertical-align:middle;line-height:1.4}
.srt tbody tr:hover td{background:var(--line2)}
.srt td.code{font-weight:800;color:var(--accent);white-space:nowrap}
.srt td.txt{text-align:left;white-space:normal;word-break:break-word;min-width:190px}
.srt td.num{white-space:nowrap}
.srt .pos{color:var(--green)}.srt .neg{color:var(--red)}
.sr-ctx{background:var(--card2);border:1px solid var(--line2);border-radius:12px;padding:10px 12px;margin:2px 0 14px}
.sr-ctx-t{font-size:11.5px;font-weight:800;letter-spacing:.4px;text-transform:uppercase;color:var(--muted);margin-bottom:7px}
.sr-chips{display:flex;flex-wrap:wrap;gap:6px}
.sr-chip{display:inline-block;padding:3px 10px;border-radius:999px;font-size:12.5px;font-weight:700;
  background:var(--tag-gray-bg);color:var(--tag-gray-fg)}
.sr-chip.g{background:var(--tag-green-bg);color:var(--tag-green-fg)}
.sr-chip.a{background:var(--tag-amber-bg);color:var(--tag-amber-fg)}
.sr-chip.r{background:var(--tag-red-bg);color:var(--red)}
.sr-why{font-size:13px;line-height:1.5;color:var(--txt);margin-top:8px}
.sr-sec{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px 18px;margin:6px 0 16px}
.sr-sec b{color:var(--txt2)}
.sr-sec span{display:inline-block;margin-right:18px;font-size:13.5px;color:var(--muted)}
</style>
"""


# ------------------------------------------------------------------ TÍNH TOÁN (không phụ thuộc Streamlit)
def _num(x, default=np.nan) -> float:
    try:
        v = float(x)
        return v if np.isfinite(v) else default
    except (TypeError, ValueError):
        return default


def _stock_stats(raw: pd.DataFrame, symbols: list[str], mkt: pd.Series) -> pd.DataFrame:
    """Hiệu suất và RS theo từng khung (Ngày / Tuần / Tháng / 3 Tháng) + GTGD 5 phiên / TB20.

    RS = (giá cuối / giá đầu kỳ của mã) / (chỉ số thị trường cuối / đầu kỳ), cùng công thức RS20 của engine.
    GTGD xấp xỉ = giá đóng cửa × khối lượng.
    """
    d = SD._clean(raw)
    rows = []
    for sym in symbols:
        g = d[d["Mã"] == sym].sort_values("Ngày")
        close, dates = g["Giá đóng cửa"].to_numpy(float), g["Ngày"].to_numpy()
        hi_a = pd.to_numeric(g["Giá cao nhất"], errors="coerce").to_numpy(float) if "Giá cao nhất" in g else np.full(len(g), np.nan)
        lo_a = pd.to_numeric(g["Giá thấp nhất"], errors="coerce").to_numpy(float) if "Giá thấp nhất" in g else np.full(len(g), np.nan)
        row = {"Mã": sym}
        for label, n in PERIODS.items():
            ret = rs = np.nan
            if len(close) > n and close[-n - 1] > 0:
                ret = (close[-1] / close[-n - 1] - 1) * 100
                m0, m1 = mkt.get(pd.Timestamp(dates[-n - 1]), np.nan), mkt.get(pd.Timestamp(dates[-1]), np.nan)
                if pd.notna(m0) and pd.notna(m1) and m0 > 0 and m1 > 0:
                    rs = (close[-1] / close[-n - 1]) / (m1 / m0)
            row[f"Hiệu suất {label}"], row[f"RS {label}"] = ret, rs
            # Biên độ giá: thấp nhất / cao nhất trong đúng n phiên gần nhất (Ngày = nến của phiên mới nhất)
            hi, lo = (np.nanmax(hi_a[-n:]), np.nanmin(lo_a[-n:])) if len(close) >= n and not np.isnan(hi_a[-n:]).all() and not np.isnan(lo_a[-n:]).all() else (np.nan, np.nan)
            row[f"Cao {label}"], row[f"Thấp {label}"] = hi, lo
        liq = np.nan
        vol = g["Khối lượng khớp lệnh"].to_numpy(float)
        if len(g) >= 20 and not np.isnan(vol[-20:]).any():
            val = close * vol
            m20 = val[-20:].mean()
            liq = val[-5:].mean() / m20 if m20 > 0 else np.nan
        row["Thanh khoản 5p/TB20"] = liq
        rows.append(row)
    return pd.DataFrame(rows)


def build_sector_frame(symbols: list[str], res_df: pd.DataFrame, wait_df: pd.DataFrame, raw: pd.DataFrame,
                       fund_map: dict | None = None, mkt: pd.Series | None = None, period: str = DEFAULT_PERIOD) -> pd.DataFrame:
    """Bảng một dòng / mã trong ngành, kèm hạng RS, RS so với ngành và các cờ phân loại 4 góc nhìn."""
    fund_map = fund_map or {}
    syms = list(dict.fromkeys(str(s).upper() for s in symbols))
    scr = res_df[res_df["Mã"].isin(syms)].copy()
    if scr.empty:
        return pd.DataFrame()
    wcols = [c for c in ("Mã", "Trạng thái", "Danh sách", "Hành động", "Hành động bán", "Lý do") if c in wait_df.columns]
    d = scr.merge(wait_df[wcols], on="Mã", how="left")
    if mkt is None:
        mkt = E.market_series(raw)[0]
    d = d.merge(_stock_stats(raw, list(d["Mã"]), mkt), on="Mã", how="left")
    n = len(d)

    # Hạng RS ở cả 4 khung (để thấy mã mạnh bền hay chỉ bật 1-2 phiên) và chênh lệch với trung bình đều của ngành
    for label in PERIODS:
        d[f"Hạng {label}"] = d[f"RS {label}"].rank(ascending=False, method="min").astype("Int64")
        d[f"Chênh {label}"] = d[f"Hiệu suất {label}"] - d[f"Hiệu suất {label}"].mean()
    # Cột của khung đang chọn
    d["RS"] = d[f"RS {period}"]
    d["Hạng RS"] = d[f"Hạng {period}"]
    d["Hiệu suất (%)"] = d[f"Hiệu suất {period}"]
    d["Cao nhất"], d["Thấp nhất"] = d[f"Cao {period}"], d[f"Thấp {period}"]
    d["Biên độ (%)"] = (d["Cao nhất"] / d["Thấp nhất"] - 1) * 100
    d["Biên độ giá"] = [("—" if pd.isna(lo) or pd.isna(hi) else f"{lo:,.2f} – {hi:,.2f}")
                        for lo, hi in zip(d["Thấp nhất"], d["Cao nhất"])]
    d["RS vs ngành"] = d[f"Chênh {period}"]          # điểm %, so với trung bình đều của ngành cùng kỳ
    sector_ret = d["Hiệu suất (%)"].mean()
    d["ROE (%)"] = d["Mã"].map(lambda c: _num((fund_map.get(c) or {}).get("ROE")))

    price, ma20 = pd.to_numeric(d["Giá"], errors="coerce"), pd.to_numeric(d["MA20"], errors="coerce")
    above_ma20 = price > ma20
    liq = d["Thanh khoản 5p/TB20"]

    # --- Yếu hơn ngành / suy yếu
    risk_list = d["Danh sách"].eq(WB.L_RISK)
    sell_sig = d["Hành động bán"].eq("BÁN") | (pd.to_numeric(d["PV_signal"], errors="coerce") < 0)
    gap_ref = d["Chênh Tháng"]          # luật yếu hơn ngành luôn đo trên 20 phiên
    lag = (gap_ref <= CFG["weak_gap"]) & ~above_ma20
    d["_weak"] = (risk_list | sell_sig | lag).fillna(False)
    d["Lý do yếu"] = [
        "; ".join(x for x in (
            "đã có tín hiệu hạ tỷ trọng / xu hướng suy yếu" if rl else "",
            "có tín hiệu bán (giá-khối lượng)" if ss else "",
            f"thua trung bình ngành {abs(gap):.1f} điểm % và nằm dưới MA20" if lg else "") if x)
        for rl, ss, lg, gap in zip(risk_list, sell_sig, lag, gap_ref)]

    # --- Mạnh nhất theo RS
    top_n = max(1, min(CFG["leader_top_n"], n // 2))
    d["_lead"] = ((d["Hạng RS"] <= top_n) & (d["RS"] >= CFG["leader_min_rs"]) & ~d["_weak"]).fillna(False)

    # --- Xu hướng tăng + thanh khoản cải thiện
    trend_up = above_ma20 & d["Trend_NganHan"].eq("TĂNG") & d["Trend_TrungHan"].ne("GIẢM")
    liq_ok = (liq >= CFG["liq_up"]) | d["VolStep"].fillna(False).astype(bool) | d["EarlyFlow"].fillna(False).astype(bool)
    d["_trend_up"] = trend_up.fillna(False)
    d["_liq_ok"] = liq_ok.fillna(False)
    d["_trend"] = (d["_trend_up"] & d["_liq_ok"] & ~d["_weak"])

    # --- Tích lũy / gần điểm mua / đã vượt nền
    d["_accum"] = d["Danh sách"].isin([WB.G1, WB.G2]) & ~d["_weak"]

    # Cột Trạng thái trên bảng: ghi chú Wyckoff (đứng trước) + trạng thái Chờ mua (bỏ khi Wyckoff chưa xác định: "-" hoặc "Đi ngang")
    wy = d["Wyckoff"].fillna("-").astype(str).str.strip() if "Wyckoff" in d else pd.Series("-", index=d.index)
    d["Trạng thái + Wyckoff"] = [st_ if w in ("-", "", "Đi ngang") else f"Wyckoff: {w} · {st_}" for st_, w in zip(d["Trạng thái"].astype(str), wy)]

    d["Xu hướng"] = np.where(d["_trend_up"], "Tăng", np.where(above_ma20.fillna(False), "Trung tính", "Yếu"))

    def tags(r):
        t = []
        if r["_lead"]: t.append("Dẫn đầu RS")
        if r["_trend"]: t.append("Tăng + dòng tiền")
        if r["_accum"]: t.append("Có thể mua ngay" if r.get("Hành động") == "Vào ngay" else "Tích lũy / gần điểm mua")
        if r["_weak"]: t.append("Yếu / suy yếu")
        return " · ".join(t) if t else "Trung tính"
    d["Vị thế"] = d.apply(tags, axis=1)
    d.attrs["sector_ret"] = float(sector_ret) if pd.notna(sector_ret) else np.nan
    d.attrs["n"] = n
    d.attrs["top_n"] = top_n
    d.attrs["period"] = period
    return d.sort_values(["Hạng RS", "Score"], ascending=[True, False], na_position="last").reset_index(drop=True)


def view_frame(d: pd.DataFrame, view: str) -> pd.DataFrame:
    """Các mã thuộc một góc nhìn, đã sắp xếp theo thứ tự ưu tiên của góc nhìn đó."""
    if d.empty:
        return d
    if view == VIEW_LEAD:
        return d[d["_lead"]].sort_values("Hạng RS")
    if view == VIEW_TREND:
        return d[d["_trend"]].sort_values(["Score", "RS"], ascending=False)
    if view == VIEW_ACCUM:
        x = d[d["_accum"]].copy()
        x["_o"] = x["Trạng thái"].map(_ACCUM_ORDER).fillna(9)
        return x.sort_values(["_o", "Score"], ascending=[True, False]).drop(columns="_o")
    return d[d["_weak"]].sort_values("Chênh Tháng")


# ------------------------------------------------------------------ KHỐI "VỊ THẾ TRONG NGÀNH" TRÊN THẺ
def _fmt(x, f="{:.2f}", na="—"):
    return na if pd.isna(x) else f.format(x)


def context_html(r: pd.Series, view: str, n: int, period: str = DEFAULT_PERIOD) -> str:
    """Khối ngữ cảnh ngành gắn vào thẻ MUA / CHỜ MUA: hạng RS, RS so với ngành, thanh khoản và lý do mã nằm ở góc nhìn này."""
    esc = _html.escape
    rank, gap, liq = r["Hạng RS"], r["RS vs ngành"], r["Thanh khoản 5p/TB20"]
    chips = []
    if pd.notna(rank):
        chips.append((f"Hạng RS {period} {int(rank)}/{n}", "g" if int(rank) <= max(1, n // 3) else "r" if int(rank) > n - max(1, n // 3) else ""))
    if pd.notna(gap):
        chips.append((f"{gap:+.1f} điểm % so với ngành ({period})", "g" if gap > 0 else "r"))
    if pd.notna(liq):
        chips.append((f"GTGD 5p/TB20 {liq:.1f}x", "g" if liq >= CFG["liq_up"] else "a" if liq < 0.9 else ""))
    if pd.notna(r.get("Thấp nhất")) and pd.notna(r.get("Cao nhất")):
        chips.append((f"Biên độ {period}: {r['Thấp nhất']:,.2f} – {r['Cao nhất']:,.2f}", ""))
    chips.append((f"Xu hướng {str(r['Xu hướng']).lower()}", {"Tăng": "g", "Yếu": "r"}.get(r["Xu hướng"], "")))
    if view == VIEW_LEAD:
        why = f"RS {period} {_fmt(r['RS'])}, đứng thứ {int(rank)} trong {n} mã của ngành." if pd.notna(rank) else ""
    elif view == VIEW_TREND:
        why = "Giá trên MA20, MA10 trên MA20 và dòng tiền đang quay lại."
    elif view == VIEW_ACCUM:
        why = f"Mục Chờ mua xếp ở trạng thái: {r['Trạng thái']}."
    else:
        why = (str(r["Lý do yếu"])[:1].upper() + str(r["Lý do yếu"])[1:] + ".") if r.get("Lý do yếu") else ""
    return ('<div class="sr-ctx"><div class="sr-ctx-t">Vị thế trong ngành</div><div class="sr-chips">'
            + "".join(f'<span class="sr-chip {c}">{esc(t)}</span>' for t, c in chips)
            + "</div>" + (f'<div class="sr-why">{esc(why)}</div>' if why else "") + "</div>")


# ------------------------------------------------------------------ GIAO DIỆN
@st.cache_data(show_spinner=False)
def _sector_metrics(_raw: pd.DataFrame, key: str):
    return SD.calculate_sector_metrics(_raw)


_STRETCH_DF = ({"width": "stretch"} if "width" in inspect.signature(st.dataframe).parameters
               else {"use_container_width": True})
PER_VIEW = 9
_TXT_COLS = ("Trạng thái", "Vị thế")


def _rank_table_html(show: pd.DataFrame, period: str) -> str:
    """Bảng xếp hạng dạng HTML: cột chữ dài (Trạng thái, Vị thế) tự xuống dòng, bảng vừa khung nên đọc hết không phải cuộn ngang.
    Viết liền không thụt lề để Markdown không coi là khối code."""
    esc = _html.escape
    rank_cols = [f"Hạng RS ({period})", *[f"Hạng {p}" for p in PERIODS]]
    fmt = {"Giá": "{:.2f}", "% phiên": "{:+.2f}%", f"Biên độ {period} (%)": "{:.1f}%", "Score": "{:.1f}", f"RS {period}": "{:.2f}",
           "RS so với ngành (điểm %)": "{:+.1f}", f"Hiệu suất {period}": "{:+.1f}%", "GTGD 5p / TB20": "{:.2f}x", "ROE (%)": "{:.1f}%"}
    signed = {"% phiên", "RS so với ngành (điểm %)", f"Hiệu suất {period}"}
    head = "".join(f"<th>{esc(str(c)).replace(' (', '<br>(')}</th>" for c in show.columns)   # phần trong ngoặc xuống dòng riêng
    rows = []
    for _, r in show.iterrows():
        tds = []
        for c in show.columns:
            v = r[c]
            if c in _TXT_COLS:
                tds.append(f'<td class="txt">{esc("" if pd.isna(v) else str(v))}</td>')
            elif c == "Mã":
                tds.append(f'<td class="code">{esc(str(v))}</td>')
            elif c in rank_cols:
                tds.append(f'<td class="num">{"" if pd.isna(v) else f"{int(v)}"}</td>')
            elif c in fmt:
                if pd.isna(v):
                    tds.append('<td class="num">-</td>')
                else:
                    cls = (" pos" if float(v) > 0 else " neg" if float(v) < 0 else "") if c in signed else ""
                    tds.append(f'<td class="num{cls}">{fmt[c].format(float(v))}</td>')
            else:
                tds.append(f'<td class="num">{esc("" if pd.isna(v) else str(v))}</td>')
        rows.append("<tr>" + "".join(tds) + "</tr>")
    return f'<div class="srt-wrap"><table class="srt"><thead><tr>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>'


def render(raw: pd.DataFrame, data_key: str, res_df: pd.DataFrame, wait_df: pd.DataFrame, groups: dict,
           fund_map: dict, card_renderer, mkt: pd.Series | None = None):
    """card_renderer(row_chờ_mua, ctx_html, view_key) vẽ một thẻ (do app.py cung cấp để dùng đúng thẻ MUA / CHỜ MUA)."""
    st.title("🏆 Vị thế cổ phiếu trong ngành")
    st.caption("Tìm mã dẫn đầu, không chỉ tìm ngành mạnh. RS = hiệu suất của mã chia hiệu suất VN-Index (hoặc proxy thị trường) cùng kỳ; "
               "\"so với ngành\" là chênh lệch hiệu suất của mã với trung bình đều của ngành cùng kỳ. "
               "Chọn khung Ngày / Tuần / Tháng / 3 Tháng để đổi cách xếp hạng. "
               "Chỉ để tham khảo, không phải khuyến nghị đầu tư.")
    st.markdown(CSS, unsafe_allow_html=True)

    metrics, info = _sector_metrics(raw, data_key)
    have = set(res_df["Mã"])
    sectors = [s for s, syms in groups.items() if any(str(x).upper() in have for x in syms)]
    if metrics.empty or not sectors:
        st.info("Chưa đủ dữ liệu để xếp hạng cổ phiếu theo ngành.")
        return
    order = metrics.sort_values("RS 1 tháng (điểm %) ", ascending=False, na_position="last")["Nhóm ngành"].tolist()
    size = {s: sum(str(x).upper() in have for x in groups[s]) for s in sectors}
    # Ngành đủ mã (>= min_stocks) xếp trước, mỗi nhóm theo RS ngành giảm dần; ngành chỉ 1-2 mã không làm ngành mặc định
    sectors = sorted(sectors, key=lambda s: (size[s] < CFG["min_stocks"], order.index(s) if s in order else 999))

    # Mở từ bản đồ ngành ở Tổng quan ngành thì giữ đúng ngành đó
    pre = st.session_state.get("sector_detail")
    if "sr_sector" not in st.session_state or st.session_state["sr_sector"] not in sectors:
        st.session_state["sr_sector"] = pre if pre in sectors else sectors[0]
    sector = st.selectbox("Chọn ngành", sectors, key="sr_sector",
                          help="Sắp theo RS 1 tháng của ngành, ngành mạnh nhất ở đầu danh sách.")

    st.session_state.setdefault("sr_period", DEFAULT_PERIOD)
    period = st.segmented_control("Khung xếp hạng", list(PERIODS), key="sr_period",
                                  help="Ngày = 1 phiên, Tuần = 5 phiên, Tháng = 20 phiên, 3 Tháng = 63 phiên giao dịch.") or DEFAULT_PERIOD
    d = build_sector_frame(groups[sector], res_df, wait_df, raw, fund_map, mkt, period)
    if d.empty:
        st.info("Ngành này chưa có mã nào có dữ liệu giá mới nhất.")
        return
    n = d.attrs["n"]

    # --- Ngữ cảnh ngành
    row = metrics[metrics["Nhóm ngành"] == sector]
    if not row.empty:
        row = row.iloc[0]
        c = st.columns(5)
        c[0].metric("Trạng thái ngành", str(row["Trạng thái"]))
        c[1].metric("Hiệu suất 1 tháng", SD._fmt_pct(row["Hiệu suất 1 tháng (%)"]))
        c[2].metric("RS ngành 1 tháng", SD._fmt_pct(row["RS 1 tháng (điểm %) "]))
        c[3].metric("Trên MA20", SD._fmt_pct(row["Trên MA20 (%)"], 0).replace("+", ""))
        c[4].metric("Số mã có dữ liệu", f"{n}")
    if n < CFG["min_stocks"]:
        st.warning(f"Ngành này chỉ có {n} mã có dữ liệu, thứ hạng chỉ mang tính tham khảo.")

    # --- Bảng xếp hạng
    st.subheader(f"Bảng xếp hạng theo RS · {period}")
    st.caption("Cột Hạng Ngày / Tuần / Tháng / 3 Tháng cho thấy mã mạnh bền (hạng cao ở mọi khung) hay chỉ bật vài phiên gần đây.")
    rank_cols = [f"Hạng {p}" for p in PERIODS]
    show = d[["Hạng RS", "Mã", *rank_cols, "Giá", "Chg_%", "Biên độ giá", "Biên độ (%)", "Score", "RS", "RS vs ngành", "Hiệu suất (%)",
              "Thanh khoản 5p/TB20", "ROE (%)", "Xu hướng", "Trạng thái + Wyckoff", "Vị thế"]].rename(columns={
        "Trạng thái + Wyckoff": "Trạng thái",
        "Hạng RS": f"Hạng RS ({period})", "Chg_%": "% phiên",
        "Biên độ giá": f"Thấp nhất – Cao nhất ({period})", "Biên độ (%)": f"Biên độ {period} (%)", "RS": f"RS {period}",
        "RS vs ngành": "RS so với ngành (điểm %)", "Hiệu suất (%)": f"Hiệu suất {period}",
        "Thanh khoản 5p/TB20": "GTGD 5p / TB20"})
    st.markdown(_rank_table_html(show, period), unsafe_allow_html=True)
    if d["ROE (%)"].isna().all():
        st.caption("Chưa có dữ liệu ROE cho ngành này (data/fundamentals.csv hoặc data/nhap_tay.csv).")

    # --- Bốn góc nhìn
    st.subheader("Cổ phiếu theo vị thế")
    counts = {v: len(view_frame(d, v)) for v in VIEWS}
    labels = {v: f"{v} ({counts[v]})" for v in VIEWS}
    default = next((v for v in VIEWS if counts[v]), VIEW_LEAD)
    st.session_state.setdefault("sr_view", default)
    view = st.segmented_control("Góc nhìn", VIEWS, key="sr_view", format_func=lambda v: labels[v]) or default
    st.caption(VIEW_HELP[view])
    vd = view_frame(d, view)
    if vd.empty:
        st.info("Không có mã nào ở góc nhìn này trong ngành đang chọn.")
        return
    codes_now = vd
    show_all = len(codes_now) > PER_VIEW and st.checkbox(f"Hiện tất cả {len(codes_now)} mã", key=f"sr_all_{view}")
    cols = st.columns(3)
    for i, (_, r) in enumerate(codes_now.head(len(codes_now) if show_all else PER_VIEW).iterrows()):
        w = wait_df[wait_df["Mã"] == r["Mã"]]
        if w.empty:
            continue
        with cols[i % 3]:
            card_renderer(w.iloc[0], context_html(r, view, n, period), VIEWS.index(view))
    if len(codes_now) > PER_VIEW and not show_all:
        st.caption(f"Đang hiển thị {PER_VIEW}/{len(codes_now)} mã đứng đầu góc nhìn này.")
    with st.expander("ℹ️ Quy tắc phân loại"):
        st.markdown(
            f"- **Mạnh nhất theo RS**: hạng RS ở khung đang chọn ({period}) thuộc top {d.attrs['top_n']} (ngành ít mã thì lấy tối đa một nửa), "
            f"RS ≥ {CFG['leader_min_rs']:.2f}, chưa có tín hiệu suy yếu.\n"
            f"- **Xu hướng tăng + thanh khoản**: giá trên MA20, MA10 > MA20, trung hạn không phải GIẢM; và GTGD 5 phiên ≥ "
            f"{CFG['liq_up']:.1f} lần TB20, hoặc khối lượng tăng 3 phiên liên tiếp, hoặc có dòng tiền sớm.\n"
            "- **Tích lũy / gần điểm mua**: nhóm *Điểm mua đã xác nhận* và *Sắp có điểm mua* ở mục Chờ mua (gồm Tích lũy / Siết nền giá, "
            "Gần vùng mua, Điểm mua đẹp và Đã có tín hiệu mua theo chiến lược, tức đã bứt khỏi nền).\n"
            f"- **Yếu hơn ngành / suy yếu**: nhóm *Hạ tỷ trọng / Xu hướng suy yếu*, hoặc có tín hiệu bán, hoặc hiệu suất 20 phiên (cố định, không đổi theo khung) thấp hơn "
            f"trung bình ngành từ {abs(CFG['weak_gap']):.0f} điểm % trở lên khi giá dưới MA20.\n\n"
            "Một mã có thể xuất hiện ở nhiều góc nhìn. Ngưỡng nằm trong `CFG` của `sector_ranking.py`. "
            "Hiệu suất ngành là trung bình đều các mã, chưa theo vốn hóa.")
