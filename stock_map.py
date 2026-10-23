"""Trang "Bộ lọc Realtime": Lọc theo ngành + Lọc cổ phiếu -> sơ đồ tư duy của một mã.

Chọn một mã, trang vẽ một cây nhánh (giống sơ đồ tư duy, xếp dọc để vừa màn hình điện thoại):

    MÃ (giá, % phiên)
     ├─ Đang nằm ở các mục      -> từng mục: Mua ngay / Chờ mua / Đang phục hồi / Cảnh báo /
     │                              Bán - Chốt lời / Tăng mạnh / Giảm mạnh / Watchlist, kèm Ý CHÍNH của mục đó
     └─ Cơ bản cổ phiếu         -> Tên, Ngành, Vốn hóa, P/B, P/E, ROE

Không tính lại gì cả: mọi mục lấy đúng điều kiện của các trang tương ứng (cùng bảng waiting_buy):
  - Mua ngay      : Danh sách thuộc BUY_GROUPS, Hành động = Vào ngay, có vùng mua, không có tín hiệu BÁN/CHỐT LỜI
  - Chờ mua       : Danh sách thuộc BUY_GROUPS và không nằm ở Mua ngay
  - Đang phục hồi : Danh sách = L_RECOVER, không có tín hiệu bán
  - Cảnh báo      : L_RISK (xu hướng suy yếu) hoặc L_OVERBOUGHT (tăng quá đà), không có tín hiệu bán
  - Bán / Chốt lời: Hành động bán là BÁN hoặc CHỐT LỜI
  - Tăng mạnh / Giảm mạnh: theo ngưỡng mặc định của hai trang đó (xem hằng số bên dưới)
  - Watchlist     : mã có trong data/watchlist_cua_toi.csv
  - Kết luận đa khung: thẻ ở trang Biểu đồ (engine.mtf_conclusion), chỉ tính khi chọn một mã
  - Wyckoff       : pha / vùng đi ngang / mốc xác nhận của khung Ngày (wyckoff.compact), liên kết tới thẻ Wyckoff ở Biểu đồ
Phần dựng dữ liệu và HTML không phụ thuộc Streamlit; chỉ render() mới import streamlit.
"""
from __future__ import annotations

import html as _h

import numpy as np
import pandas as pd

import waiting_buy as WB
import wyckoff as WYK

SELL = ("BÁN", "CHỐT LỜI")
# Ngưỡng mặc định của trang Tăng mạnh / Giảm mạnh (app.py, _move_page)
SURGE_SESSION, SURGE_VOL = 4.0, 1.0      # tăng >= 4% trong phiên cuối và khối lượng >= 1.0x TB10
SURGE_LEG = 30.0                         # hoặc tăng từ đáy 120 phiên >= 30%
PLUNGE_SESSION = 4.0                     # giảm >= 4% trong phiên cuối (cùng điều kiện khối lượng)
PLUNGE_LEG = 20.0                        # hoặc giảm từ đỉnh 120 phiên >= 20%

TF_VN = {"M": "Tháng", "W": "Tuần", "D": "Ngày"}
TONE = {"buy": "var(--green)", "wait": "var(--amber)", "recover": "#5BC0EB", "warn": "var(--amber)",
        "sell": "var(--red)", "none": "var(--muted)", "up": "var(--green)", "down": "var(--red)",
        "watch": "var(--gold)"}


# ------------------------------------------------------------------ dữ liệu
def _f(v):
    try:
        x = float(v)
        return x if np.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def _px(v) -> str:
    x = _f(v)
    return "—" if x is None else f"{x:,.1f}"


def _pc(v, signed=True) -> str:
    x = _f(v)
    if x is None:
        return "—"
    return f"{x:+.1f}%" if signed else f"{x:.1f}%"


def sectors(t: pd.DataFrame) -> list[str]:
    s = {x.strip() for v in t["Nhóm"].dropna() for x in str(v).split(",") if x.strip()}
    return sorted(s)


def codes_in(t: pd.DataFrame, sector: str | None) -> list[str]:
    d = t
    if sector:
        d = t[t["Nhóm"].apply(lambda v: sector in [x.strip() for x in str(v).split(",")])]
    return sorted(d["Mã"].astype(str).unique())


def _parts(text, limit=210) -> list[str]:
    """Lý do của app có dạng 'hiện trạng: khuyến nghị'. Tách theo ': ' thành các ý ngắn, mỗi ý một dòng."""
    out = []
    for p in str(text or "").split(": "):
        p = p.strip().rstrip(".")
        if p and p not in SELL:      # nhãn BÁN / CHỐT LỜI đầu câu đã có ở thẻ nhãn của mục
            out.append(p if len(p) <= limit else p[: limit - 1].rstrip() + "…")
    return out[:3]


def _levels(r) -> list[str]:
    pts = []
    if _f(r.get("Vùng mua từ")) is not None and _f(r.get("Vùng mua đến")) is not None:
        pts.append(f"Vùng mua {_px(r['Vùng mua từ'])} – {_px(r['Vùng mua đến'])} · "
                   f"Cắt lỗ {_px(r.get('Cắt lỗ'))} ({_pc(r.get('Cắt lỗ %'))})")
        if _f(r.get("Mục tiêu 1")) is not None:
            t2 = f" · MT2 {_px(r.get('Mục tiêu 2'))} ({_pc(r.get('Lời 2 %'))})" if _f(r.get("Mục tiêu 2")) is not None else ""
            pts.append(f"MT1 {_px(r['Mục tiêu 1'])} ({_pc(r.get('Lời 1 %'))}){t2}")
    return pts


def wyckoff_points(c) -> tuple[str, str, list[str]]:
    """(nhãn, tông màu, ý chính) từ kết quả wyckoff.compact() của khung Ngày. c = None: chưa có cấu trúc."""
    if not c:
        return ("Chưa có cấu trúc", "none",
                ["Chưa thấy vùng đi ngang đủ rõ (≥ 30 nến, chạm cả hai biên từ 2 lần): giá đang trong xu hướng hoặc biên quá rộng"])
    kind, ph = c.get("kind"), c.get("phase")
    tone = {"buy": "buy", "sell": "sell"}.get(c.get("lean"), "wait")
    pts = []
    if kind in ("acc", "dist") and ph:
        txt = str(WYK.PHASE_TEXT[kind][ph]).split(". ")[0].rstrip(".")
        pts.append(f"Pha {ph}: {WYK.PHASE_NAME[kind][ph]}. {txt}")
    elif kind == "unk":
        pts.append("Xu hướng trước đó không rõ nên chưa phân biệt tích lũy hay phân phối, chưa gán được pha")
    pts.append(f"Vùng đi ngang {WYK.fmt2(c['bot'])} – {WYK.fmt2(c['top'])} ({c.get('bars')} nến), khớp mẫu {c.get('score')}%")
    for key, lab in (("trigger", "Xác nhận"), ("inval", "Vô hiệu")):
        d = c.get(key)
        if d and d.get("txt"):
            pts.append(f"{lab}: {d['txt']}")
    ev = c.get("last_ev")
    if ev:
        try:
            pts.append(f"Sự kiện mới nhất: {ev['label']} ngày {pd.Timestamp(ev['date']):%d/%m/%Y} ({WYK.fmt2(ev['p'])})")
        except Exception:
            pass
    return (WYK.label(c), tone, pts)


def memberships(code: str, t: pd.DataFrame, now_codes: set, wl_codes: set, vol_map=None, conc=None, A=None, wy=False, wc=None) -> list[dict]:
    """Các mục mã đang nằm trong, mỗi mục: {title, icon, tag, tone, points[]}."""
    rows = t[t["Mã"].astype(str).str.upper() == code.upper()]
    if rows.empty:
        return []
    r = rows.iloc[0]
    dsh, hd = r.get("Danh sách"), r.get("Hành động bán")
    sell = hd in SELL
    out: list[dict] = []

    def add(icon, title, tag, tone, points, go=""):
        out.append({"icon": icon, "title": title, "tag": tag, "tone": tone, "go": go, "points": [p for p in points if p]})

    if code in now_codes:
        add("⚡", "Mua ngay", str(r.get("Trạng thái") or ""), "buy",
            [f"Giá {_px(r.get('Giá'))} đang trong vùng mua, vào được ngay (nên chia lệnh)"] + _parts(r.get("Lý do"))[:1] + _levels(r), "buynow")
    elif dsh in WB.BUY_GROUPS:
        pts = _parts(r.get("Lý do"))
        lv = _levels(r)
        gap = _f(r.get("Cách vùng mua %"))
        if lv and gap is not None:
            lv[0] += f" · giá cách vùng mua {_pc(gap)}"
        add("🛒", "Chờ mua", f"{dsh} · {r.get('Trạng thái')}", "wait", pts + lv, "wait")
    if dsh == WB.L_RECOVER and not sell:
        add("🌱", "Đang phục hồi", str(r.get("Trạng thái") or ""), "recover", _parts(r.get("Lý do")) + _levels(r), "recover")
    if dsh == WB.L_RISK and not sell:
        add("⚠️", "Danh sách cảnh báo", "Xu hướng suy yếu", "warn", _parts(r.get("Lý do")), "risk")
    if dsh == WB.L_OVERBOUGHT and not sell:
        add("⚠️", "Danh sách cảnh báo", "Tăng quá đà", "warn", _parts(r.get("Lý do")), "over")
    if sell:
        add("🔴", "Bán / Chốt lời", str(hd), "sell", _parts(r.get("Lý do")), "sell")
    if dsh == WB.L_NONE:
        add("⛔", "Đứng ngoài", "Không có điểm mua", "none",
            ["Bị loại khỏi mọi danh sách cơ hội"] + _parts(r.get("Lý do"))[:2])

    chg, vol = _f(r.get("Chg %")), None
    if vol_map is not None:
        try:
            vol = _f(vol_map.get(code))
        except Exception:
            vol = None
    leg_up, leg_dn = _f(r.get("Tăng từ đáy hiện tại %")), _f(r.get("Giảm từ đỉnh %"))
    up_pts, dn_pts = [], []
    if chg is not None and chg >= SURGE_SESSION and vol is not None and vol >= SURGE_VOL:
        up_pts.append(f"Phiên cuối {_pc(chg)}, khối lượng {vol:.1f}× TB10")
    if leg_up is not None and leg_up >= SURGE_LEG:
        up_pts.append(f"Đã tăng {_pc(leg_up, False)} từ đáy 120 phiên: không mua đuổi, chờ nhịp lùi về hỗ trợ")
    if chg is not None and chg <= -PLUNGE_SESSION and vol is not None and vol >= SURGE_VOL:
        dn_pts.append(f"Phiên cuối {_pc(chg)}, khối lượng {vol:.1f}× TB10")
    if leg_dn is not None and leg_dn >= PLUNGE_LEG:
        dn_pts.append(f"Đã giảm {_pc(leg_dn, False)} từ đỉnh 120 phiên: chưa nên bắt đáy sớm, chờ giá dừng giảm")
    sess_up = chg is not None and chg >= SURGE_SESSION and vol is not None and vol >= SURGE_VOL
    sess_dn = chg is not None and chg <= -PLUNGE_SESSION and vol is not None and vol >= SURGE_VOL
    if up_pts:
        add("🚀", "Tăng mạnh", "", "up", up_pts, "surge-s" if sess_up else "surge-l")
    if dn_pts:
        add("💥", "Giảm mạnh", "", "down", dn_pts, "plunge-s" if sess_dn else "plunge-l")
    if conc:      # Kết luận đa khung: thẻ ở trang Biểu đồ (cột bên phải)
        pts = [conc.get("text"), f"Điểm đa khung {float(conc['score']):+.0f}/100 (−100 đến +100)"]
        if A:
            segs = []
            for tf in ("M", "W", "D"):
                a = A.get(tf) or {}
                if a.get("enough"):
                    lab = "Tăng" if a["dir"] > 0 else "Giảm" if a["dir"] < 0 else "Ngang"
                    segs.append(f"{TF_VN[tf]} {lab} {abs(a['bias']):.0f}/100")
                else:
                    segs.append(f"{TF_VN[tf]} thiếu dữ liệu")
            pts.append(" · ".join(segs))
        add("📊", "Kết luận đa khung", str(conc.get("verdict") or ""), {"green": "buy", "red": "sell"}.get(conc.get("kind"), "wait"), pts, "chart")
    if wy:        # Wyckoff khung Ngày: thẻ chi tiết ở trang Biểu đồ (cột bên phải)
        tag, tone, pts = wyckoff_points(wc)
        add("🧱", "Wyckoff", tag, tone, pts, "wyckoff")
    if code.upper() in wl_codes:
        add("⭐", "Watchlist", "", "watch", ["Có trong danh sách theo dõi của bạn"], "watch")
    return out


def fundamentals(code: str, row, cap_map: dict, fund_map: dict) -> list[tuple[str, str]]:
    fd = (fund_map or {}).get(code.upper(), {}) or {}

    def fmt(v, f):
        x = _f(v)
        return "Chưa có" if x is None else f.format(x)

    name = fd.get("Tên công ty")
    sector = str(row.get("Nhóm") or "").strip() if row is not None else ""
    return [("Tên công ty", str(name).strip() if isinstance(name, str) and name.strip() else "Chưa có"),
            ("Ngành", sector or "Chưa phân loại"),
            ("Vốn hóa", fmt((cap_map or {}).get(code.upper()), "{:,.0f} tỷ")),
            ("P/B", fmt(fd.get("P/B"), "{:.2f}")),
            ("P/E", fmt(fd.get("P/E"), "{:.1f}")),
            ("ROE", fmt(fd.get("ROE"), "{:.1f}%"))]


# ------------------------------------------------------------------ HTML
CSS = """<style>
.mm{margin:6px 0 18px}
.mm-root{display:flex;align-items:center;flex-wrap:wrap;gap:6px 14px;background:var(--card2);border:1px solid var(--line);border-radius:14px;padding:12px 16px}
.mm-code{font-size:28px;font-weight:700;color:var(--txt2);letter-spacing:.5px}
.mm-px{font-size:15px;color:var(--txt)}
.mm-sub{flex-basis:100%;font-size:13px;color:var(--muted)}
.mm-tree{margin:0 0 0 26px;border-left:2px solid var(--line);padding-top:4px}
.mm-b{position:relative;padding:12px 0 2px 24px}
.mm-b:before{content:"";position:absolute;left:0;top:30px;width:22px;border-top:2px solid var(--line)}
.mm-bt{display:inline-block;background:var(--card);border:1px solid var(--line);border-left:5px solid var(--c);border-radius:10px;padding:7px 14px;font-weight:700;color:var(--txt2);font-size:15px}
.mm-bt small{font-weight:400;color:var(--muted);margin-left:6px}
.mm-kids{margin:8px 0 0 20px;border-left:2px solid var(--line)}
.mm-k{position:relative;padding:5px 0 5px 20px}
.mm-k:before{content:"";position:absolute;left:0;top:22px;width:16px;border-top:2px solid var(--line)}
a.mm-card{display:block;text-decoration:none;color:inherit}
a.mm-card:hover{background:var(--card2)}
.mm-go{float:right;font-size:12px;color:var(--c);font-weight:500;margin-left:10px;white-space:nowrap}
.mm-card{background:var(--card);border:1px solid var(--line);border-left:4px solid var(--c);border-radius:10px;padding:9px 13px}
.mm-ct{font-weight:600;color:var(--txt2);font-size:15px}
.mm-tag{display:inline-block;margin-left:8px;padding:1px 9px;border-radius:999px;border:1px solid var(--c);color:var(--c);font-size:12px;font-weight:500;vertical-align:1px}
.mm-pt{font-size:13.5px;color:var(--txt);line-height:1.55;margin-top:4px;padding-left:14px;text-indent:-14px}
.mm-pt:before{content:"• ";color:var(--c)}
.mm-fk{display:flex;justify-content:space-between;gap:14px;background:var(--card);border:1px solid var(--line);border-radius:10px;padding:7px 13px;font-size:14px}
.mm-fk span:first-child{color:var(--muted)}
.mm-fk span:last-child{color:var(--txt2);font-weight:600;text-align:right}
.mm-empty{color:var(--muted);font-size:14px;padding:6px 0}
</style>"""


def _e(x) -> str:
    return _h.escape(str(x))


def tree_html(code: str, row, mems: list[dict], funda: list[tuple[str, str]]) -> str:
    price = _px(row.get("Giá")) if row is not None else "—"
    chg = _f(row.get("Chg %")) if row is not None else None
    chg_html = ""
    if chg is not None:
        col = "var(--green)" if chg > 0 else "var(--red)" if chg < 0 else "var(--muted)"
        chg_html = f' <span style="color:{col};font-weight:600">{chg:+.2f}%</span>'
    name = dict(funda).get("Tên công ty", "")
    sub = f'<div class="mm-sub">{_e(name)}</div>' if name and name != "Chưa có" else ""
    root = f'<div class="mm-root"><span class="mm-code">{_e(code)}</span><span class="mm-px">Giá {price}{chg_html}</span>{sub}</div>'

    # nhánh 1: các mục mã đang nằm trong
    if mems:
        kids = ""
        for m in mems:
            tag = f'<span class="mm-tag">{_e(m["tag"])}</span>' if m["tag"] else ""
            pts = "".join(f'<div class="mm-pt">{_e(p)}</div>' for p in m["points"])
            if m.get("go"):
                lab = "Mở biểu đồ ›" if m["go"] in ("chart", "wyckoff") else "Mở thẻ ›"
                kids += (f'<div class="mm-k"><a class="mm-card" href="?rtgo={m["go"]}~{_e(code)}" target="_self" style="--c:{TONE[m["tone"]]}">'
                         f'<div class="mm-ct">{m["icon"]} {_e(m["title"])}{tag}<span class="mm-go">{lab}</span></div>{pts}</a></div>')
            else:
                kids += (f'<div class="mm-k"><div class="mm-card" style="--c:{TONE[m["tone"]]}">'
                         f'<div class="mm-ct">{m["icon"]} {_e(m["title"])}{tag}</div>{pts}</div></div>')
        b1 = (f'<div class="mm-b" style="--c:var(--accent)"><div class="mm-bt">🧭 Đang nằm ở {len(mems)} mục</div>'
              f'<div class="mm-kids">{kids}</div></div>')
    else:
        b1 = ('<div class="mm-b" style="--c:var(--muted)"><div class="mm-bt">🧭 Chưa nằm trong mục nào</div>'
              '<div class="mm-kids"><div class="mm-k"><div class="mm-empty">Mã chưa thỏa điều kiện của các mục '
              'Mua ngay, Chờ mua, Đang phục hồi, Cảnh báo, Bán / Chốt lời, Tăng / Giảm mạnh, Watchlist.</div></div></div></div>')

    # nhánh 2: cơ bản
    fk = "".join(f'<div class="mm-k"><div class="mm-fk"><span>{_e(k)}</span><span>{_e(v)}</span></div></div>' for k, v in funda)
    note = ""
    if all(v in ("Chưa có", "Chưa phân loại") for k, v in funda if k in ("Vốn hóa", "P/B", "P/E", "ROE")):
        note = '<div class="mm-k"><div class="mm-empty">Chưa có số liệu cơ bản cho mã này (cần data/fundamentals.csv hoặc data/nhap_tay.csv).</div></div>'
    b2 = f'<div class="mm-b" style="--c:var(--gold)"><div class="mm-bt">🏢 Cơ bản cổ phiếu</div><div class="mm-kids">{fk}{note}</div></div>'
    return f'<div class="mm">{root}<div class="mm-tree">{b1}{b2}</div></div>'


# ------------------------------------------------------------------ giao diện Streamlit
def render(t: pd.DataFrame, cap_map: dict, fund_map: dict, now_codes: set, wl_codes: set, vol_map, open_chart=None, mtf_fn=None, wy_fn=None) -> None:
    import streamlit as st

    st.caption("Chọn ngành rồi chọn mã để xem mã đang nằm ở mục nào và ý chính của từng mục. "
               "Điều kiện từng mục lấy đúng như các trang Mua ngay, Chờ mua, Đang phục hồi, Danh sách cảnh báo, Bán / Chốt lời. "
               "Chỉ phục vụ nghiên cứu, không phải khuyến nghị đầu tư.")
    st.markdown(CSS, unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    sec = c1.selectbox("Lọc theo ngành", ["Tất cả ngành"] + sectors(t), key="rt_sector")
    sector = None if sec == "Tất cả ngành" else sec
    codes = codes_in(t, sector)
    code = c2.selectbox(f"Lọc cổ phiếu ({len(codes)} mã)", codes, index=None, key=f"rt_code_{sec}",
                        placeholder="Gõ hoặc chọn mã…")

    if not code:
        if sector:      # chưa chọn mã: tóm tắt cả ngành để chọn nhanh
            rows = []
            for c in codes:
                r = t[t["Mã"] == c].iloc[0]
                ms = memberships(c, t, now_codes, wl_codes, vol_map)
                rows.append({"Mã": c, "Giá": _f(r.get("Giá")), "Chg %": _f(r.get("Chg %")),
                             "Đang ở mục": " · ".join(m["title"] + (f" ({m['tag']})" if m["tag"] else "") for m in ms) or "—"})
            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True,
                         column_config={"Giá": st.column_config.NumberColumn(format="%.2f"),
                                        "Chg %": st.column_config.NumberColumn(format="%+.2f")})
        else:
            st.info("Chọn một mã ở ô **Lọc cổ phiếu** để xem sơ đồ. Có thể chọn ngành trước để thu hẹp danh sách.")
        return

    row = t[t["Mã"].astype(str).str.upper() == code.upper()].iloc[0]
    conc, A = mtf_fn(code) if mtf_fn else (None, None)
    st.markdown(tree_html(code, row, memberships(code, t, now_codes, wl_codes, vol_map, conc, A, wy_fn is not None, wy_fn(code) if wy_fn else None),
                          fundamentals(code, row, cap_map, fund_map)), unsafe_allow_html=True)
    st.caption("Bấm vào từng mục để mở đúng thẻ của mã ở trang đó.")
    if open_chart is not None and st.button("📈 Xem biểu đồ", key=f"rt_chart_{code}"):
        open_chart(code)      # NAV.goto đã tự chạy lại trang
