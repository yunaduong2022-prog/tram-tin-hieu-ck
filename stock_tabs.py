"""Các tab con của mục CỔ PHIẾU (dùng dữ liệu giá/khối lượng sẵn có + data/fundamentals.csv)."""
import os

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import theme as TH

VOL = "Khối lượng khớp lệnh"
NOTE_PATH = "data/ghi_chu.csv"


def _fmt(v, f="{:,.2f}", na="chưa có dữ liệu"):
    return na if v is None or (isinstance(v, float) and np.isnan(v)) or pd.isna(v) else f.format(v)


def _fund(code, fund_map):
    return (fund_map or {}).get(code.upper(), {})


def _hist(df, code):
    return df[df["Mã"] == code].sort_values("Ngày").reset_index(drop=True)


def _ret(c, n):
    return (c.iloc[-1] / c.iloc[-1 - n] - 1) * 100 if len(c) > n else np.nan


def _plot(fig, h=320):
    fig.update_layout(template=TH.plotly_template(), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", height=h, margin=dict(l=10, r=10, t=30, b=10),
                      legend=dict(orientation="h", y=1.1))
    st.plotly_chart(fig, use_container_width=True)


def tab_general(g, code, fund):
    c = g["Giá đóng cửa"]
    chg = _ret(c, 1)
    t = g.tail(250)
    a, b, d, e = st.columns(4)
    a.metric("Giá đóng cửa", f"{c.iloc[-1]:,.2f}", f"{chg:+.2f}%" if pd.notna(chg) else None)
    b.metric("Vốn hóa TT (tỷ)", _fmt(fund.get("Vốn hóa TT"), "{:,.0f}"))
    d.metric("Đỉnh 52 tuần", f"{t['Giá cao nhất'].max():,.2f}")
    e.metric("Đáy 52 tuần", f"{t['Giá thấp nhất'].min():,.2f}")
    st.markdown(f"**Tên công ty:** {fund.get('Tên công ty') or 'chưa có dữ liệu'}  \n"
                f"**Mã:** {code}  \n**Dữ liệu:** {len(g)} phiên, từ {g['Ngày'].min():%d/%m/%Y} đến {g['Ngày'].max():%d/%m/%Y}")
    fig = go.Figure(go.Scatter(x=g["Ngày"].tail(250), y=c.tail(250), line=dict(color="#0E8A6D", width=2), name="Giá"))
    _plot(fig, 300)


def _val_row(code, fund_map):
    f = _fund(code, fund_map)
    g = lambda k: (None if pd.isna(pd.to_numeric(f.get(k), errors="coerce")) else float(pd.to_numeric(f.get(k), errors="coerce")))
    pe, pe3, pb, pb3 = g("P/E"), g("P/E TB 3N"), g("P/B"), g("P/B TB 3N")
    dev = lambda x, m: (x / m - 1) * 100 if x is not None and m else None
    return pe, pe3, dev(pe, pe3), pb, pb3, dev(pb, pb3)


def _verdict(d):
    return "chưa đủ dữ liệu" if d is None else ("thấp hơn TB 3 năm" if d <= -10 else "cao hơn TB 3 năm" if d >= 10 else "quanh TB 3 năm")


def tab_valuation(g, code, fund_map):
    pe, pe3, dpe, pb, pb3, dpb = _val_row(code, fund_map)
    st.markdown("**P/E**")
    a, b, c, d = st.columns(4)
    a.metric("P/E hiện tại", _fmt(pe, "{:.1f}"))
    b.metric("P/E TB 3 năm", _fmt(pe3, "{:.1f}"))
    c.metric("Chênh lệch so với TB", _fmt(dpe, "{:+.1f}%"))
    d.metric("Nhận định", _verdict(dpe))
    st.markdown("**P/B**")
    a, b, c, d = st.columns(4)
    a.metric("P/B hiện tại", _fmt(pb, "{:.2f}"))
    b.metric("P/B TB 3 năm", _fmt(pb3, "{:.2f}"))
    c.metric("Chênh lệch so với TB", _fmt(dpb, "{:+.1f}%"))
    d.metric("Nhận định", _verdict(dpb))
    st.caption("TB 3 năm = trung bình các kỳ quý trong 3 năm gần nhất (bỏ kỳ lỗ/ngoại lai, cần ≥ 3 kỳ). "
               "“Nhận định” chỉ là so sánh mức ±10% với trung bình, không phải khuyến nghị. "
               "Số liệu từ data/fundamentals.csv (update_fundamentals.py) hoặc điền tay ở data/nhap_tay.csv.")


def tab_valuation_table(codes, fund_map):
    base = pd.DataFrame({"Mã": list(codes)})
    if os.path.exists(BCTC_PATH):
        try:
            x = pd.read_csv(BCTC_PATH, encoding="utf-8-sig")
            x["Mã"] = x["Mã"].astype(str).str.upper().str.strip()
            base = base.merge(x[[c for c in ("Mã", "Ngành", "Sàn") if c in x.columns]].drop_duplicates("Mã", keep="last"), on="Mã", how="left")
        except Exception:
            pass
    cols = [("Mã CK", "txt"), ("Ngành", "txt"), ("Sàn", "txt"), ("P/E", "num1"), ("P/E TB 3 năm", "num1"),
            ("P/E so với TB (%)", "pct"), ("P/B", "num2"), ("P/B TB 3 năm", "num2"), ("P/B so với TB (%)", "pct")]
    rows = []
    for _, r in base.iterrows():
        v = _val_row(r["Mã"], fund_map)
        rows.append([r["Mã"], None if pd.isna(r.get("Ngành")) else r.get("Ngành"), None if pd.isna(r.get("Sàn")) else r.get("Sàn"),
                     v[0], v[1], v[2], v[3], v[4], v[5]])
    _dark_table(cols, rows)


BCTC_PATH = "data/bctc.csv"
BCTC_COLS = [  # (cột trong CSV, tiêu đề hiển thị, kiểu)
    ("Ngành", "Ngành", "txt"), ("Sàn", "Sàn", "txt"), ("Kỳ BCTC", "Kỳ BCTC", "txt"),
    ("DT thuần TTM (tỷ)", "DT thuần-TTM (tỷ)", "num1"), ("Tăng trưởng DT thuần (%)", "Tăng trưởng DT thuần (%)", "pct"),
    ("LN sau thuế TTM (tỷ)", "LN sau thuế-TTM (tỷ)", "num1"), ("Tăng trưởng LN sau thuế (%)", "Tăng trưởng LN sau thuế (%)", "pct"),
    ("Biên LN ròng TTM (%)", "Biên LN ròng-TTM (%)", "pct"), ("ROA TTM (%)", "ROA-TTM (%)", "pct"),
    ("ROE TTM (%)", "ROE-TTM (%)", "pct"),
]

_TABLE_HTML = """<style>
*{box-sizing:border-box}body{margin:0;background:#12161F;font-family:Inter,'Segoe UI',Arial,sans-serif;color:#E6EDF3}
.wrap{max-height:__H__px;overflow:auto;border:1px solid #2A313C;border-radius:8px}
table{border-collapse:collapse;width:100%;min-width:1100px;font-size:15px}
th{position:sticky;top:0;background:#1B2130;color:#E6EDF3;font-weight:600;text-align:center;padding:12px 10px;line-height:1.3;
 border:1px solid #2A313C;cursor:pointer;user-select:none;white-space:normal}
th .ar{color:#8B949E;margin-left:6px;font-size:13px}th.on .ar{color:#7C6CF0}
td{padding:16px 10px;text-align:center;border:1px solid #2A313C;white-space:nowrap}
tbody tr:nth-child(odd){background:#161B26}tbody tr:nth-child(even){background:#12161F}
tbody tr:hover{background:#1F2635}td.code{color:#7C6CF0;font-weight:700}td.pos{color:#3FD6AE}td.neg{color:#FF7B72}td.na{color:#566070}
</style><div class="wrap"><table><thead><tr id="h"></tr></thead><tbody id="b"></tbody></table></div>
<script>
const COLS=__COLS__,ROWS=__ROWS__;let sk=null,asc=true;
const fmt=(v,t)=>v===null||v===undefined||v===""?null:t==="txt"?String(v):t==="num1"?Number(v).toLocaleString("en-US",{minimumFractionDigits:1,maximumFractionDigits:1}):t==="num2"?Number(v).toLocaleString("en-US",{minimumFractionDigits:2,maximumFractionDigits:2}):t==="num0"?Math.round(Number(v)).toLocaleString("en-US"):t==="mult"?Number(v).toFixed(2)+"x":t==="chg"?(Number(v)>0?"+":"")+Number(v).toFixed(2)+"%":Number(v).toLocaleString("en-US",{maximumFractionDigits:2})+"%";
function draw(){const h=document.getElementById("h");h.innerHTML="";
 COLS.forEach((c,i)=>{const th=document.createElement("th");th.className=sk===i?"on":"";th.innerHTML=c[0]+'<span class="ar">'+(sk===i?(asc?"↑":"↓"):"⇅")+"</span>";
  th.onclick=()=>{asc=sk===i?!asc:true;sk=i;draw()};h.appendChild(th)});
 let r=ROWS.slice();if(sk!==null){const t=COLS[sk][1];r.sort((a,b)=>{let x=a[sk],y=b[sk];
  if(x===null||x==="")return 1;if(y===null||y==="")return -1;
  const c=t==="txt"?String(x).localeCompare(String(y)):x-y;return asc?c:-c})}
 const b=document.getElementById("b");b.innerHTML="";
 r.forEach(row=>{const tr=document.createElement("tr");row.forEach((v,i)=>{const td=document.createElement("td");const f=fmt(v,COLS[i][1]);
  if(i===0)td.className="code";if(COLS[i][1]==="chg"&&v!==null&&v!==""){td.className=Number(v)>0?"pos":Number(v)<0?"neg":""}if(f===null){td.className="na";td.textContent="—"}else td.textContent=f;tr.appendChild(td)});b.appendChild(tr)})}
draw();
</script>"""


def _dark_table(cols, rows, height=600):
    """Bảng ngang nền tối, bấm tiêu đề để sắp xếp. cols = [(tiêu đề, 'txt'|'num1'|'num2'|'pct')]."""
    import json
    import streamlit.components.v1 as components
    html = (_TABLE_HTML.replace("__COLS__", json.dumps(cols, ensure_ascii=False))
            .replace("__ROWS__", json.dumps(rows, ensure_ascii=False)).replace("__H__", str(height)))
    components.html(html, height=height + 20, scrolling=False)


def _bctc_frame(codes, fund_map):
    base = pd.DataFrame({"Mã": list(codes)})
    if os.path.exists(BCTC_PATH):
        try:
            x = pd.read_csv(BCTC_PATH, encoding="utf-8-sig")
            x.columns = [str(c).strip() for c in x.columns]
            x["Mã"] = x["Mã"].astype(str).str.upper().str.strip()
            base = base.merge(x.drop_duplicates("Mã", keep="last"), on="Mã", how="left")
        except Exception as e:
            st.warning(f"Không đọc được {BCTC_PATH}: {e}")
    for col, _, kind in BCTC_COLS:
        if col not in base.columns:
            base[col] = np.nan
    # ROE: nếu bctc.csv chưa có thì dùng ROE trong fundamentals / nhap_tay
    roe = base["Mã"].map(lambda c: _fund(c, fund_map).get("ROE"))
    base["ROE TTM (%)"] = base["ROE TTM (%)"].fillna(roe)
    return base


def tab_fundamental_table(codes, fund_map):
    f = _bctc_frame(codes, fund_map)
    cols = [("Mã CK", "txt")] + [(h, k) for _, h, k in BCTC_COLS]
    rows = []
    for _, r in f.iterrows():
        row = [r["Mã"]]
        for col, _, kind in BCTC_COLS:
            v = r[col]
            row.append(None if pd.isna(v) else (str(v) if kind == "txt" else float(pd.to_numeric(v, errors="coerce"))))
        rows.append([None if (isinstance(v, float) and np.isnan(v)) else v for v in row])
    _dark_table(cols, rows)
    filled = int(f[[c for c, _, _ in BCTC_COLS if c != "ROE TTM (%)"]].notna().any(axis=1).sum())
    st.caption(f"{len(f)} mã · {filled} mã đã có số liệu BCTC. Bấm tiêu đề cột để sắp xếp. "
               f"Điền số liệu vào {BCTC_PATH} (mẫu đã tạo sẵn); ô trống hiển thị “—”.")


def tab_volatility(g, code, fund):
    c = g["Giá đóng cửa"]
    cols = st.columns(6)
    for col, (lb, n) in zip(cols, [("1 phiên", 1), ("1 tuần", 5), ("1 tháng", 21), ("3 tháng", 63), ("6 tháng", 126), ("1 năm", 250)]):
        v = _ret(c, n)
        col.metric(lb, _fmt(v, "{:+.2f}%"))
    r = c.pct_change() * 100
    rng = (g["Giá cao nhất"] - g["Giá thấp nhất"]) / c.shift(1) * 100
    a, b = st.columns(2)
    a.metric("Độ lệch chuẩn 20 phiên (%/ngày)", _fmt(r.tail(20).std()))
    b.metric("Biên độ TB 20 phiên (%)", _fmt(rng.tail(20).mean()))
    t = r.tail(60)
    fig = go.Figure(go.Bar(x=g["Ngày"].tail(60), y=t, marker_color=np.where(t >= 0, "#0E8A6D", "#C93A52"), name="% ngày"))
    _plot(fig)


def tab_range(g, code, fund):
    c = g["Giá đóng cửa"].iloc[-1]
    rows = []
    for lb, n in [("20 phiên", 20), ("60 phiên", 60), ("120 phiên", 120), ("52 tuần", 250)]:
        t = g.tail(n)
        hi, lo = t["Giá cao nhất"].max(), t["Giá thấp nhất"].min()
        rows.append({"Khoảng": lb, "Đáy": lo, "Đỉnh": hi, "Vị trí giá (%)": (c - lo) / (hi - lo) * 100 if hi > lo else np.nan,
                     "Cách đỉnh (%)": (hi / c - 1) * 100, "Cách đáy (%)": (c / lo - 1) * 100})
    st.dataframe(TH.style_df(pd.DataFrame(rows).round(2)), hide_index=True, use_container_width=True)
    t = g.tail(250)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=t["Ngày"], y=t["Giá đóng cửa"], name="Giá", line=dict(color="#0E8A6D")))
    fig.add_hline(y=t["Giá cao nhất"].max(), line_dash="dot", line_color="#C93A52", annotation_text="Đỉnh 52T")
    fig.add_hline(y=t["Giá thấp nhất"].min(), line_dash="dot", line_color="#3B82F6", annotation_text="Đáy 52T")
    _plot(fig)


def tab_liquidity(g, code, fund):
    v = g[VOL]
    ma10 = v.rolling(10).mean()
    a, b, d, e = st.columns(4)
    a.metric("KL phiên mới nhất", f"{v.iloc[-1]:,.0f}")
    b.metric("KL TB 10 phiên", _fmt(ma10.iloc[-1], "{:,.0f}"))
    d.metric("KL vs MA10", _fmt(v.iloc[-1] / ma10.iloc[-1] if ma10.iloc[-1] else np.nan, "{:.2f}x"))
    e.metric("KL TB 60 phiên", _fmt(v.tail(60).mean(), "{:,.0f}"))
    t = g.tail(120)
    fig = go.Figure()
    fig.add_trace(go.Bar(x=t["Ngày"], y=t[VOL], name="Khối lượng", marker_color="#94A3B8"))
    fig.add_trace(go.Scatter(x=t["Ngày"], y=v.rolling(20).mean().tail(120), name="MA20", line=dict(color="#F59E0B")))
    _plot(fig)


def tab_notes(g, code, fund):
    notes = pd.read_csv(NOTE_PATH, dtype=str).fillna("") if os.path.exists(NOTE_PATH) else pd.DataFrame(columns=["Mã", "Ghi chú"])
    cur = notes.loc[notes["Mã"] == code, "Ghi chú"]
    txt = st.text_area(f"Ghi chú cho {code}", value=cur.iloc[0] if len(cur) else "", height=220, key=f"note_{code}")
    if st.button("Lưu ghi chú", key=f"save_note_{code}"):
        notes = notes[notes["Mã"] != code]
        notes = pd.concat([notes, pd.DataFrame([{"Mã": code, "Ghi chú": txt}])], ignore_index=True)
        os.makedirs("data", exist_ok=True)
        notes.to_csv(NOTE_PATH, index=False, encoding="utf-8-sig")
        st.success("Đã lưu.")
    st.caption("Ghi chú lưu trong data/ghi_chu.csv trên máy chạy app (trên Streamlit Cloud sẽ mất khi khởi động lại).")


NEWS_REFRESH_SEC = 300


@st.cache_data(ttl=NEWS_REFRESH_SEC, show_spinner="Đang tải tin tức...")
def _news_cached(code: str, name):
    import news_feed
    return news_feed.fetch_news(code, name=name)


def tab_news(g, code, fund):
    try:  # tự tải lại định kỳ khi đang mở tab này (rời tab thì dừng)
        from streamlit_autorefresh import st_autorefresh
        st_autorefresh(interval=NEWS_REFRESH_SEC * 1000, key="news_autorefresh")
    except Exception:  # noqa: BLE001
        pass
    items, errs, meta = _news_cached(code, fund.get("Tên công ty"))
    c1, c2 = st.columns([4, 1])
    c1.caption(f"Tin liên quan {code} · tự cập nhật mỗi {NEWS_REFRESH_SEC // 60} phút · "
               f"lấy lúc {meta['fetched']:%H:%M:%S %d/%m/%Y}" + (" · ⚠ nguồn đang lỗi, hiển thị bản đã lưu" if meta["stale"] else ""))
    if c2.button("🔄 Làm mới", key=f"news_refresh_{code}", use_container_width=True):
        _news_cached.clear()
        st.rerun()
    if not items:
        st.info(f"Chưa lấy được tin cho {code}. Cần vnstock hoạt động (có VNSTOCK_API_KEY) hoặc RSS hợp lệ trong data/rss_feeds.txt.")
        if errs:
            st.caption("Chi tiết lỗi: " + " · ".join(errs[:6]))
        return
    seen_key = f"news_seen_{code}"
    seen = st.session_state.get(seen_key)          # None = lần xem đầu, không đánh dấu MỚI
    for it in items:
        d = f"{it['date']:%d/%m/%Y %H:%M}" if it["date"] is not None else ""
        new = seen is not None and it["link"] + it["title"] not in seen
        badge = "🆕 " if new else ""
        title = f"[{it['title']}]({it['link']})" if it["link"] else it["title"]
        st.markdown(f"{badge}**{title}**  \n<span style='color:var(--muted);font-size:12px'>{d} · {it['source']}</span>", unsafe_allow_html=True)
        st.divider()
    st.session_state[seen_key] = {it["link"] + it["title"] for it in items}


def _article_html(it, codes_hit=None, groups_hit=None):
    import html as H
    d = f"{it['date']:%d/%m/%Y %H:%M}" if it.get("date") is not None else ""
    t = H.escape(it["title"])
    title = f'<a href="{H.escape(it["link"])}" target="_blank" style="color:var(--txt);font-weight:600;text-decoration:none">{t}</a>' if it.get("link") else f"<b>{t}</b>"
    chips = "".join(f'<span class="tag tag-green" style="margin-right:4px">{H.escape(c)}</span>' for c in (codes_hit or []))
    chips += "".join(f'<span class="tag tag-gray" style="margin-right:4px">{H.escape(g)}</span>' for g in (groups_hit or []))
    return (f'<div style="padding:8px 0;border-bottom:1px solid var(--line)">{title}<br>'
            f'<span style="color:var(--muted);font-size:12px">{d} · {H.escape(str(it.get("source","")))}</span> {chips}</div>')


@st.cache_data(ttl=300, show_spinner="Đang tải tin tức...")
def _feed_cached():
    import news_feed
    return news_feed.fetch_feed_items()


def _portfolio_news(codes, groups, view, fund_map=None):
    import news_feed as NF
    items, errs, ok, total = _feed_cached()
    now = pd.Timestamp.now(tz="Asia/Ho_Chi_Minh").tz_localize(None)
    days = st.session_state.get("news_days", 3)
    if days:
        items = [x for x in items if x["date"] is None or (now - x["date"]).days < days]
    st.caption(f"Cập nhật lúc {now:%H:%M:%S %d/%m/%Y} · {len(items)} bài từ {ok}/{total} nguồn RSS"
               + (" · lỗi: " + "; ".join(errs[:4]) if errs else ""))
    if not ok:
        st.warning("Không tải được nguồn RSS nào. Kiểm tra mạng và danh sách trong data/rss_feeds.txt.")
        return
    codes_set = set(codes)
    rx = NF.codes_regex(codes_set)
    names = NF.name_index(fund_map, codes_set)
    tagged = []
    for it in items:
        ch = NF.match_codes(it, rx, codes_set, names)
        tagged.append((it, ch, NF.match_groups(it, ch, groups)))
    if view == "Danh mục (theo mã)":
        pick = st.multiselect("Lọc theo mã (bỏ trống = tất cả mã trong danh mục)", sorted(codes_set), key="news_codes")
        rows = [(it, ch, []) for it, ch, _ in tagged if ch and (not pick or set(pick) & set(ch))]
        st.markdown(f"**{len(rows)} bài nhắc đến mã trong danh mục**")
        for it, ch, _ in rows[:80]:
            st.markdown(_article_html(it, ch), unsafe_allow_html=True)
        if not rows:
            st.info("Chưa có bài nào nhắc đến mã trong danh mục trong khoảng thời gian đã chọn.")
    else:
        pick = st.multiselect("Nhóm ngành", list(groups), default=list(groups), key="news_groups")
        by_g = {g: [(it, ch, [g]) for it, ch, gs in tagged if g in gs] for g in pick}
        for g in sorted(by_g, key=lambda x: -len(by_g[x])):
            with st.expander(f"{g} · {len(by_g[g])} bài", expanded=len(by_g[g]) > 0 and g == max(by_g, key=lambda x: len(by_g[x]))):
                for it, ch, _ in by_g[g][:30]:
                    st.markdown(_article_html(it, ch), unsafe_allow_html=True)
                if not by_g[g]:
                    st.caption("Chưa có bài phù hợp.")


def news_page(codes, groups, df, fund_map):
    c1, c2, c3, c4 = st.columns([2.2, 1.3, 1.3, 1])
    view = c1.radio("Chế độ xem", ["Danh mục (theo mã)", "Nhóm ngành", "Từng mã (vnstock)"], horizontal=True, key="news_view")
    interval = c2.selectbox("Tự động cập nhật", ["Tắt", "5 phút", "15 phút", "30 phút"], index=1, key="news_auto")
    c3.selectbox("Hiển thị tin trong", [1, 3, 7, 30], index=1, format_func=lambda d: f"{d} ngày gần nhất", key="news_days")
    if c4.button("Cập nhật ngay", use_container_width=True):
        _feed_cached.clear()
        _news_cached.clear()
    if view == "Từng mã (vnstock)":
        saved = st.session_state.get("selected_code")
        code = st.selectbox("Mã cổ phiếu", codes, index=codes.index(saved) if saved in codes else 0, key="tab_code")
        st.session_state["selected_code"] = code
        tab_news(None, code, _fund(code, fund_map))
        return
    run_every = None if interval == "Tắt" else f"{interval.split()[0]}m"

    @st.fragment(run_every=run_every)
    def _live():
        _portfolio_news(codes, groups or {}, view, fund_map)
    _live()
    st.caption("Tin lấy từ các RSS trong data/rss_feeds.txt, khớp theo mã (ghi đúng chữ in hoa) và từ khóa ngành "
               "(news_feed.SECTOR_KEYWORDS). Danh mục = các mã đang nạp trong app; nhóm ngành lấy từ watchlist.py.")


TABS = {"Thông tin chung": tab_general, "Định giá": tab_valuation, "Cơ bản": None,
        "Biến động giá": tab_volatility, "Phạm vi giá": tab_range, "Thanh khoản": tab_liquidity,
        "Ghi chú": tab_notes, "Tin tức": tab_news}


@st.cache_data(show_spinner=False)
def _market_stats(_df, key: str) -> pd.DataFrame:
    rows = []
    for code, g in _df.groupby("Mã"):
        g = g.sort_values("Ngày")
        c, v = g["Giá đóng cửa"], g[VOL]
        r = c.pct_change() * 100
        rng = (g["Giá cao nhất"] - g["Giá thấp nhất"]) / c.shift(1) * 100
        t52 = g.tail(250)
        hi, lo = t52["Giá cao nhất"].max(), t52["Giá thấp nhất"].min()

        def pos(n):
            t = g.tail(n)
            h, l = t["Giá cao nhất"].max(), t["Giá thấp nhất"].min()
            return (c.iloc[-1] - l) / (h - l) * 100 if h > l else np.nan
        ma = lambda n: v.tail(n).mean() if len(v) >= n else np.nan
        rows.append({
            "Mã": code, "Giá": c.iloc[-1], "r1": _ret(c, 1), "r5": _ret(c, 5), "r21": _ret(c, 21), "r63": _ret(c, 63),
            "r126": _ret(c, 126), "r250": _ret(c, 250), "sd20": r.tail(20).std(), "rng20": rng.tail(20).mean(),
            "lo52": lo, "hi52": hi, "toHi": (hi / c.iloc[-1] - 1) * 100, "toLo": (c.iloc[-1] / lo - 1) * 100,
            "pos52": pos(250), "pos20": pos(20), "pos60": pos(60),
            "vol": v.iloc[-1], "ma10": ma(10), "ma20": ma(20), "ma60": ma(60),
            "x10": v.iloc[-1] / ma(10) if ma(10) else np.nan, "x20": v.iloc[-1] / ma(20) if ma(20) else np.nan,
            "gtgd20": (c * v).tail(20).mean(),
        })
    return pd.DataFrame(rows).set_index("Mã")


MARKET_SPECS = {  # (tiêu đề, khóa trong _market_stats, kiểu)
    "Biến động giá": [("Giá", "Giá", "num2"), ("1 phiên", "r1", "chg"), ("1 tuần", "r5", "chg"), ("1 tháng", "r21", "chg"),
                      ("3 tháng", "r63", "chg"), ("6 tháng", "r126", "chg"), ("1 năm", "r250", "chg"),
                      ("Độ lệch chuẩn 20 phiên (%/ngày)", "sd20", "num2"), ("Biên độ TB 20 phiên (%)", "rng20", "num2")],
    "Phạm vi giá": [("Giá", "Giá", "num2"), ("Đáy 52 tuần", "lo52", "num2"), ("Đỉnh 52 tuần", "hi52", "num2"),
                    ("Cách đỉnh (%)", "toHi", "num2"), ("Cách đáy (%)", "toLo", "num2"), ("Vị trí giá 52 tuần (%)", "pos52", "num2"),
                    ("Vị trí giá 20 phiên (%)", "pos20", "num2"), ("Vị trí giá 60 phiên (%)", "pos60", "num2")],
    "Thanh khoản": [("KL phiên mới nhất", "vol", "num0"), ("KL TB 10 phiên", "ma10", "num0"), ("KL TB 20 phiên", "ma20", "num0"),
                    ("KL TB 60 phiên", "ma60", "num0"), ("KL vs MA10", "x10", "mult"), ("KL vs MA20", "x20", "mult"),
                    ("GTGD TB 20 phiên (giá × KL)", "gtgd20", "num0")],
}


def _sector_exchange(codes) -> pd.DataFrame:
    base = pd.DataFrame({"Mã": list(codes)})
    if os.path.exists(BCTC_PATH):
        try:
            x = pd.read_csv(BCTC_PATH, encoding="utf-8-sig")
            x["Mã"] = x["Mã"].astype(str).str.upper().str.strip()
            base = base.merge(x[[c for c in ("Mã", "Ngành", "Sàn") if c in x.columns]].drop_duplicates("Mã", keep="last"), on="Mã", how="left")
        except Exception:
            pass
    for c in ("Ngành", "Sàn"):
        if c not in base.columns:
            base[c] = None
    return base


def market_table(sub, df, codes):
    st_ = _market_stats(df, f"{len(df)}-{df['Ngày'].max():%Y%m%d}")
    spec = MARKET_SPECS[sub]
    cols = [("Mã CK", "txt"), ("Ngành", "txt"), ("Sàn", "txt")] + [(h, k) for h, _, k in spec]
    rows = []
    for _, r in _sector_exchange(codes).iterrows():
        code = r["Mã"]
        s_ = st_.loc[code] if code in st_.index else None
        vals = [None if s_ is None or pd.isna(s_[key]) else float(s_[key]) for _, key, _ in spec]
        rows.append([code, None if pd.isna(r["Ngành"]) else r["Ngành"], None if pd.isna(r["Sàn"]) else r["Sàn"]] + vals)
    _dark_table(cols, rows)
    st.caption(f"{len(rows)} mã · tính từ dữ liệu giá/khối lượng đang nạp. Bấm tiêu đề cột để sắp xếp. "
               "Ngành, Sàn lấy từ data/bctc.csv (nếu đã điền).")


def render(sub, df, codes, fund_map, groups=None):
    if sub == "Tin tức":
        news_page(codes, groups, df, fund_map)
        st.caption("Chỉ phục vụ nghiên cứu, không phải khuyến nghị đầu tư.")
        return
    if sub == "Cơ bản":
        tab_fundamental_table(codes, fund_map)
        return
    if sub == "Định giá":
        tab_valuation_table(codes, fund_map)
    elif sub in MARKET_SPECS:
        market_table(sub, df, codes)
    st.subheader("Chi tiết theo mã")
    saved = st.session_state.get("selected_code")
    code = st.selectbox("Mã cổ phiếu", codes, index=codes.index(saved) if saved in codes else 0, key="tab_code")
    st.session_state["selected_code"] = code
    if sub == "Định giá":
        tab_valuation(_hist(df, code), code, fund_map)
    else:
        TABS[sub](_hist(df, code), code, _fund(code, fund_map))
    st.caption("Chỉ phục vụ nghiên cứu, không phải khuyến nghị đầu tư.")
