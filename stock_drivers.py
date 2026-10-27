"""Khung bên phải trang Livestream: thông tin RIÊNG của mã đang chọn (không còn gắn cứng ngành cao su).

Ba thẻ, đều tạo HTML (dùng class live-card / live-kpi / live-table của trang Livestream):
- valuation_card: vốn hóa, P/B, P/E, ROE, EPS và so sánh với trung vị của ngành, với trung bình 3 năm.
- drivers_card:   động lực tăng trưởng, yếu tố đầu vào / đầu ra, chỉ số theo dõi, rủi ro của ngành (hoặc riêng từng mã),
                  đọc từ data/dong_luc_nganh.csv; ô có số (giá hàng hóa...) hiện kèm % thay đổi, ngày cập nhật, nguồn.
- peers_card:     các mã mạnh nhất CÙNG NGÀNH của mã đang xem (xếp theo RS20), tô sáng mã đang xem.

Số liệu hàng hóa (giá cao su thế giới, cước container...) không có nguồn tự động trong app nên nhập tay vào CSV;
chưa nhập thì chỉ hiện phần mô tả, không bao giờ hiện số giả lập.
"""
from __future__ import annotations

import html
import os

import numpy as np
import pandas as pd

DRIVERS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "dong_luc_nganh.csv")
KINDS = ["Động lực", "Đầu vào", "Đầu ra", "Chỉ số theo dõi", "Rủi ro"]
KIND_TITLE = {"Động lực": "Động lực tăng trưởng", "Đầu vào": "Yếu tố đầu vào", "Đầu ra": "Yếu tố đầu ra",
              "Chỉ số theo dõi": "Chỉ số theo dõi", "Rủi ro": "Rủi ro cần để ý"}
NOT_SECTORS = {"VN30", "Danh mục cũ của bạn", "Họ Vingroup"}      # nhóm danh mục / tập đoàn, không phải ngành
_cache: dict = {"sig": None, "df": None}


def esc(x) -> str:
    return html.escape("" if x is None else str(x))


def _num(x):
    try:
        v = float(str(x).replace(" ", "").replace(",", "."))
        return v if np.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def sectors_of(code: str, member: dict, groups: dict) -> list[str]:
    """Các ngành thật của mã (loại VN30 / danh mục cũ / họ tập đoàn), giữ thứ tự khai báo trong watchlist."""
    return [g for g in member.get(str(code).upper(), member.get(code, [])) if g in groups and g not in NOT_SECTORS]


def load_drivers() -> pd.DataFrame:
    """data/dong_luc_nganh.csv; tự đọc lại khi file đổi."""
    sig = os.path.getmtime(DRIVERS_PATH) if os.path.exists(DRIVERS_PATH) else None
    if _cache["sig"] == sig and _cache["df"] is not None:
        return _cache["df"]
    cols = ["Phạm vi", "Loại", "Nội dung", "Giá trị", "Đơn vị", "Thay đổi %", "Cập nhật", "Nguồn"]
    df = pd.DataFrame(columns=cols)
    if sig is not None:
        try:
            df = pd.read_csv(DRIVERS_PATH, dtype=str, encoding="utf-8-sig").fillna("")
            for c in cols:
                if c not in df:
                    df[c] = ""
            df = df[cols]
            df = df[(df["Phạm vi"].str.strip() != "") & (df["Nội dung"].str.strip() != "")]
        except Exception:  # noqa: BLE001  file lỗi định dạng thì coi như chưa có dữ liệu, không làm hỏng trang
            df = pd.DataFrame(columns=cols)
    _cache["sig"], _cache["df"] = sig, df
    return df


def _card(title: str, body: str) -> str:
    return f"<div class='live-card'><div class='live-card-title'>{title}</div>{body}</div>"


# ---------------------------------------------------------------- định giá
def _median_of(vals: list) -> float | None:
    v = [x for x in vals if x is not None and np.isfinite(x)]
    return float(np.median(v)) if len(v) >= 3 else None


def _vs(now, ref, name: str, lower_is_cheaper: bool = True) -> str | None:
    if now is None or ref is None or ref == 0:
        return None
    d = (now / ref - 1) * 100
    word = "cao hơn" if d > 0 else "thấp hơn"
    return f"{name}: {now:.2f} so với {ref:.2f} ({word} {abs(d):.0f}%)"


def valuation_card(code: str, sector: str | None, meta: dict, fund_map: dict, cap_map: dict, groups: dict, cap_note: str = "") -> str:
    """Vốn hóa, P/B, P/E, ROE, EPS + so sánh với ngành và với trung bình 3 năm."""
    fd = fund_map.get(str(code).upper(), {}) or {}
    members = [str(m).upper() for m in groups.get(sector, [])] if sector else []

    def f(m, k):
        return _num((fund_map.get(m, {}) or {}).get(k))
    kp = [("VỐN HÓA", meta.get("Vốn hóa", "Chưa có")), ("P/B", meta.get("P/B", "Chưa có")), ("P/E", meta.get("P/E", "Chưa có")),
          ("ROE", meta.get("ROE", "Chưa có")), ("EPS", meta.get("EPS", "Chưa có")), ("GIÁ TRỊ SỔ SÁCH", meta.get("BVPS", "Chưa có"))]
    grid = "".join(f"<div class='live-kpi'><span>{esc(k)}</span><b>{esc(v)}</b></div>" for k, v in kp)
    lines = []
    if cap_note:
        lines.append(esc(cap_note).replace("\n", " "))
    if members:
        pb_m, pe_m, roe_m = (_median_of([f(m, k) for m in members if m != str(code).upper()]) for k in ("P/B", "P/E", "ROE"))
        for now, ref, name in ((_num(fd.get("P/B")), pb_m, "P/B so với trung vị ngành"),
                               (_num(fd.get("P/E")), pe_m, "P/E so với trung vị ngành"),
                               (_num(fd.get("ROE")), roe_m, "ROE so với trung vị ngành (%)")):
            t = _vs(now, ref, name)
            if t:
                lines.append(t)
    for k, ref_k, name in (("P/B", "P/B TB 3N", "P/B so với trung bình 3 năm"), ("P/E", "P/E TB 3N", "P/E so với trung bình 3 năm")):
        t = _vs(_num(fd.get(k)), _num(fd.get(ref_k)), name)
        if t:
            lines.append(t)
    if meta.get("Xếp hạng"):
        lines.append(f"Xếp hạng cơ bản: {esc(meta['Xếp hạng'])}")
    body = f"<div style='display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px'>{grid}</div>"
    if lines:
        body += "<div style='color:#dce5f0;font-size:13px;line-height:1.75;margin-top:10px'>" + "".join(f"<div>• {t}</div>" for t in lines) + "</div>"
    else:
        body += "<div class='live-muted' style='margin-top:9px'>Chưa có đủ dữ liệu P/B, P/E, ROE để so sánh với ngành. Bổ sung ở data/fundamentals.csv hoặc nhap_tay.csv.</div>"
    body += "<div class='live-muted' style='margin-top:6px'>So sánh với trung vị của các mã cùng ngành đang có số liệu (cần ít nhất 3 mã); không phải khuyến nghị mua hay bán.</div>"
    return _card(f"💰 VỐN HÓA & ĐỊNH GIÁ · {esc(code)}", body)


# ---------------------------------------------------------------- động lực / đầu vào / đầu ra
def _value_chip(r: pd.Series) -> str:
    val = str(r["Giá trị"]).strip()
    if not val:
        unit = str(r["Đơn vị"]).strip()
        if unit and str(r["Loại"]).strip().casefold() == "chỉ số theo dõi":
            return f" <span class='live-muted'>· chưa có số ({esc(unit)}), nhập ở cột Giá trị</span>"
        return ""
    chg = _num(r["Thay đổi %"])
    out = f" <span class='live-positive' style='color:#f1f5f9'>{esc(val)} {esc(r['Đơn vị'])}</span>"
    if chg is not None:
        col = "#43d6a1" if chg > 0 else "#ef5b6b" if chg < 0 else "#8fa1b8"
        out += f" <span style='color:{col};font-weight:700'>({chg:+.1f}%)</span>"
    meta = " · ".join(x for x in (f"cập nhật {esc(r['Cập nhật'])}" if str(r["Cập nhật"]).strip() else "",
                                  f"nguồn {esc(r['Nguồn'])}" if str(r["Nguồn"]).strip() else "") if x)
    return out + (f" <span class='live-muted'>{meta}</span>" if meta else "")


def drivers_card(code: str, sectors: list[str]) -> str:
    """Các dòng riêng của mã (Phạm vi = mã) rồi tới các dòng của ngành (Phạm vi = tên ngành)."""
    df = load_drivers()
    code_u = str(code).upper()
    sec_cf = [s.casefold() for s in sectors]
    scope = df["Phạm vi"].str.strip()
    mine = df[scope.str.upper() == code_u]
    sect = df[scope.str.casefold().isin(sec_cf)].copy()
    sect["_o"] = sect["Phạm vi"].str.strip().str.casefold().map({s: i for i, s in enumerate(sec_cf)})
    sect = sect.sort_values("_o", kind="stable")
    title = f"🚀 ĐỘNG LỰC TĂNG TRƯỞNG & YẾU TỐ THEO NGÀNH · {esc(sectors[0].upper())}" if sectors else f"🚀 ĐỘNG LỰC TĂNG TRƯỞNG · {esc(code)}"
    if mine.empty and sect.empty:
        txt = (f"Chưa có nội dung động lực cho {esc(code)}" + (f" / ngành {esc(', '.join(sectors))}" if sectors else "") +
               ". Thêm dòng vào <b>data/dong_luc_nganh.csv</b> với cột Phạm vi = tên ngành (hoặc mã cổ phiếu), "
               "Loại = Động lực / Đầu vào / Đầu ra / Chỉ số theo dõi / Rủi ro.")
        return _card(title, f"<div class='live-muted'>{txt}</div>")
    allr = pd.concat([mine, sect], ignore_index=True)
    body = []
    for kind in KINDS:
        rows = allr[allr["Loại"].str.strip().str.casefold() == kind.casefold()]
        if rows.empty:
            continue
        items = []
        for _, r in rows.iterrows():
            tag = ""
            sc = str(r["Phạm vi"]).strip()
            if sc.upper() == code_u:
                tag = f" <span class='live-muted'>[riêng {esc(code_u)}]</span>"
            elif len(sectors) > 1:
                tag = f" <span class='live-muted'>[{esc(sc)}]</span>"
            items.append(f"<div>• {esc(r['Nội dung'])}{_value_chip(r)}{tag}</div>")
        body.append(f"<div style='margin-top:8px'><div class='live-muted' style='font-weight:800;letter-spacing:.3px'>{esc(KIND_TITLE[kind].upper())}</div>"
                    f"<div style='color:#dce5f0;font-size:13px;line-height:1.7'>{''.join(items)}</div></div>")
    body.append("<div class='live-muted' style='margin-top:8px'>Nội dung do bạn tự cập nhật trong data/dong_luc_nganh.csv; các con số hàng hóa không được app lấy tự động.</div>")
    return _card(title, "".join(body))


# ---------------------------------------------------------------- cổ phiếu mạnh cùng ngành
def peers_card(res_df: pd.DataFrame, code: str, sector: str | None, groups: dict, top_n: int = 5) -> str:
    if not sector:
        return _card(f"🏆 CỔ PHIẾU CÙNG NGÀNH · {esc(code)}", "<div class='live-muted'>Mã này chưa được xếp vào ngành nào trong watchlist.py.</div>")
    members = {str(m).upper() for m in groups.get(sector, [])} | {str(code).upper()}
    t = res_df[res_df["Mã"].astype(str).str.upper().isin(members)].copy()
    rs_col = "RS20" if "RS20" in t else "RS vs VNI"
    t["_rs"] = pd.to_numeric(t[rs_col], errors="coerce")
    t = t.sort_values("_rs", ascending=False, na_position="last").reset_index(drop=True)
    t["_rank"] = np.arange(1, len(t) + 1)
    n = len(t)
    cur = t[t["Mã"].astype(str).str.upper() == str(code).upper()]
    top = t.head(top_n)
    show = pd.concat([top, cur[~cur["Mã"].isin(top["Mã"])]]) if len(cur) else top
    head = f"🏆 TOP CỔ PHIẾU MẠNH CÙNG NGÀNH {esc(sector.upper())}"
    if not len(show):
        return _card(head, "<div class='live-muted'>Chưa có mã nào của ngành này trong dữ liệu.</div>")
    rows = []
    for _, r in show.iterrows():
        rs = r["_rs"]
        status = "Khỏe" if pd.notna(rs) and rs >= 1.05 else ("Theo dõi" if pd.notna(rs) and rs >= 0.95 else ("Yếu / chờ" if pd.notna(rs) else "—"))
        align = str(r.get("MA align", ""))
        trend = "📈 Tăng" if "Đã align" in align else ("🔄 Tích lũy" if pd.notna(r.get("Score")) and r.get("Score") >= 4 else "↔ Trung tính")
        me = str(r["Mã"]).upper() == str(code).upper()
        sty = " style='background:#17314a'" if me else ""
        mark = " ◀" if me else ""
        rows.append(f"<tr{sty}><td>#{int(r['_rank'])}</td><td><b>{esc(r['Mã'])}</b>{mark}</td><td>{'—' if pd.isna(rs) else f'{rs:.2f}'}</td>"
                    f"<td>{trend}</td><td>{status}</td></tr>")
    pos = ""
    if len(cur):
        rk = int(cur["_rank"].iat[0])
        pos = f"<div class='live-muted' style='margin-bottom:6px'>{esc(code)} xếp hạng RS #{rk}/{n} trong ngành {esc(sector)}.</div>"
    tbl = ("<table class='live-table'><thead><tr><th>Hạng</th><th>Mã CP</th><th>RS20</th><th>Xu hướng</th><th>Trạng thái</th></tr></thead><tbody>"
           + "".join(rows) + "</tbody></table>")
    note = "<div class='live-muted' style='margin-top:6px'>RS20 = sức mạnh 20 phiên so với VN-Index (&gt;1 là mạnh hơn thị trường); xếp hạng chỉ gồm các mã của ngành có trong dữ liệu.</div>"
    return _card(head, pos + tbl + note)
