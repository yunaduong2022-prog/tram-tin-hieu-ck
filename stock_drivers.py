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
import re

import numpy as np
import pandas as pd

DRIVERS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "dong_luc_nganh.csv")
KINDS = ["Động lực", "Đầu vào", "Đầu ra", "Chỉ số theo dõi", "Rủi ro"]
KIND_TITLE = {"Động lực": "Động lực tăng trưởng", "Đầu vào": "Yếu tố đầu vào", "Đầu ra": "Yếu tố đầu ra",
              "Chỉ số theo dõi": "Chỉ số theo dõi", "Rủi ro": "Rủi ro cần để ý"}
COMMENT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "nhan_dinh_ma")
NOT_SECTORS = {"VN30", "Danh mục cũ của bạn", "Họ Vingroup", "Họ Gelex"}      # nhóm danh mục / tập đoàn, không phải ngành
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


# ---------------------------------------------------------------- nhận định riêng của mã
def _inline(t: str) -> str:
    """Escape HTML rồi đổi **chữ đậm** thành <b>."""
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", esc(t))


COMMENT_MAX_H = 380      # chiều cao tối đa (px) của phần nội dung nhận định; dài hơn thì cuộn dọc ngay trong khung


NOTE_STARTS = ("mẹo điều phối", "ghi chú cho người dẫn")


def _note_details(title: str, lines: list[str]) -> str:
    """Ghi chú cho người dẫn: khối <details> đóng sẵn; gạch đầu dòng ("* ", "- ", "•", "👉 *") hiện thành ý riêng, dòng giải thích ngay sau ý thì thụt vào."""
    body, after_bullet = [], False
    muted = "color:#8fa1b8;font-size:13px;line-height:1.7"
    for ln in lines:
        if not ln:
            after_bullet = False
            continue
        m = re.match(r"^(👉\s*)?(?:•|[-*–])\s+(.*)$", ln)
        if m:
            mark = "👉" if m.group(1) else "•"
            body.append(f"<div style='{muted};margin-top:8px;padding-left:16px;text-indent:-14px'><span style='color:#43d6a1'>{mark}</span>&nbsp;{_inline(m.group(2))}</div>")
            after_bullet = True
        else:
            body.append(f"<div style='{muted};margin-top:6px;padding-left:{16 if after_bullet else 0}px'>{_inline(ln)}</div>")
    label = "🎙️ Ghi chú cho người dẫn" + (f" · {_inline(title)}" if title else "")
    return ("<details style='margin-top:14px;border:1px dashed #3b4d66;border-radius:8px;padding:6px 11px'>"
            f"<summary style='cursor:pointer;color:#8fa1b8;font-size:12.5px'>{label} <span style='opacity:.7'>(bấm để mở, khán giả không thấy khi đóng)</span></summary>"
            f"{''.join(body)}</details>")


def _comment_html(text: str) -> tuple[str, str]:
    """Đổi nội dung file nhận định thành (tiêu đề, phần thân HTML).

    Hiểu: "# " dòng đầu = tiêu đề; "## [Phần 1: ...]" hoặc "## ..." = tiêu đề phần (bỏ dấu ngoặc vuông);
    dòng bắt đầu bằng "•", "- ", "* " hoặc "– " (và các ý nối nhau bằng " • " trên cùng một dòng) = gạch đầu dòng;
    các dòng thường liên tiếp = một đoạn;
    khối bắt đầu bằng "Vị thế" (đến dòng trống kế tiếp) = khung nổi bật, gồm cả các gạch đầu dòng và câu kết trong khối;
    ghi chú cho người dẫn (thu gọn sẵn, không hiện trên màn hình livestream): bắt đầu từ dòng "Ghi chú cho người dẫn: <tiêu đề>" hoặc "Mẹo điều phối ...",
    kéo dài đến tiêu đề phần "##", khối "Vị thế" hoặc ghi chú kế tiếp; đặt ở đâu trong file thì hiện ở đúng chỗ đó; có thể có nhiều ghi chú.
    """
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    title, out, para = "", [], []
    BODY = "color:#dce5f0;font-size:13.5px;line-height:1.75"

    def li(it: str) -> str:
        return ("<div style='color:#dce5f0;font-size:13.5px;line-height:1.7;margin-top:5px;padding-left:16px;text-indent:-12px'>"
                f"<span style='color:#43d6a1'>•</span>&nbsp;{_inline(it)}</div>")

    def flush(target):
        if para:
            target.append(f"<div style='{BODY};margin-top:9px'>{_inline(' '.join(para))}</div>")
            para.clear()

    def bullets(t: str, target):
        for it in re.split(r"\s+•\s+", t.strip()):
            it = it.strip().lstrip("•").strip()
            if it:
                target.append(li(it))

    def mixed(t: str, target):
        """Chuỗi có ý nối bằng " • ": phần trước dấu • đầu tiên là câu dẫn (đoạn thường), phần sau là các gạch đầu dòng."""
        t = t.strip()
        if t.startswith("•"):
            bullets(t, target)
            return
        intro, _, rest = t.partition(" • ")
        if intro.strip():
            para.append(intro.strip())
            flush(target)
        if rest:
            bullets("• " + rest, target)

    def is_bullet(ln: str) -> bool:
        return bool(re.match(r"^(•|[-*–]\s)", ln)) or " • " in ln

    i, first, n = 0, True, len(lines)
    while i < n:
        ln = lines[i].strip()
        i += 1
        if not ln:
            flush(out)
            continue
        if first and re.match(r"^#\s", ln):
            title, first = ln.lstrip("#").strip(), False
            continue
        first = False
        low = ln.casefold()
        if low.startswith(NOTE_STARTS):                          # ghi chú cho người dẫn: thu gọn sẵn
            flush(out)
            if low.startswith("ghi chú cho người dẫn"):
                note_title = ln.partition(":")[2].strip()
                note = []
            else:
                note_title, note = "", [ln]
            while i < n:
                nx = lines[i].strip()
                if re.match(r"^#{1,6}\s", nx) or nx.casefold().startswith("vị thế") or nx.casefold().startswith(NOTE_STARTS):
                    break
                note.append(nx)
                i += 1
            out.append(_note_details(note_title, note))
            continue
        if ln.casefold().startswith("vị thế"):                 # khung nổi bật: gom cả khối đến dòng trống
            flush(out)
            blk = [ln]
            while i < n and lines[i].strip():
                blk.append(lines[i].strip())
                i += 1
            head, _, rest = _inline(blk[0]).partition(":")
            inner = [f"<div><b>{head}:</b>{rest}</div>"]
            for x in blk[1:]:
                if is_bullet(x):
                    mixed(re.sub(r"^[-*–]\s+", "• ", x), inner)
                else:
                    inner.append(f"<div style='margin-top:8px'>{_inline(x)}</div>")
            out.append("<div style='margin-top:14px;background:#0b1422;border:1px solid #26364b;border-left:3px solid #43d6a1;border-radius:8px;"
                       f"padding:10px 13px;color:#f1f5f9;font-size:13.5px;line-height:1.7'>{''.join(inner)}</div>")
            continue
        m = re.match(r"^#{1,6}\s*(.*)$", ln)
        if m:                                                   # tiêu đề phần: "## [Phần 1: X] nội dung..." hoặc "## X"
            flush(out)
            rest = m.group(1).strip()
            mb = re.match(r"^\[([^\]]+)\]\s*(.*)$", rest)
            if mb:
                head, rest = mb.group(1).strip(), mb.group(2).strip()
            else:
                head, _, tail = rest.partition(" • ")
                head, rest = head.strip(), ("• " + tail.strip() if tail else "")
            out.append(f"<div style='color:#43d6a1;font-size:13.5px;font-weight:800;margin-top:14px;letter-spacing:.2px'>{_inline(head)}</div>")
            if rest:
                mixed(rest, out)
            continue
        if is_bullet(ln):                                       # gạch đầu dòng (kể cả nhiều ý nối bằng " • ")
            flush(out)
            mixed(re.sub(r"^[-*–]\s+", "• ", ln), out)
            continue
        para.append(ln)
    flush(out)
    return title, "".join(out)


def commentary_card(code: str) -> str | None:
    """Thẻ nhận định riêng của mã, đọc từ data/nhan_dinh_ma/<MÃ>.md; trả None nếu chưa có file (trang sẽ hiện thẻ vốn hóa & định giá).

    Khung có chiều cao tối đa COMMENT_MAX_H: nội dung dài hơn thì hiện thanh cuộn dọc bên trong khung (tiêu đề và ghi chú cuối đứng yên).
    """
    path = os.path.join(COMMENT_DIR, f"{str(code).upper()}.md")
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            text = f.read()
    except OSError:
        return None
    title, body = _comment_html(text)
    if not (title or body):
        return None
    c = esc(str(code).upper())
    head = (f"<div style='font-size:15px;font-weight:800;color:#f1f5f9;line-height:1.5;margin-bottom:4px'>{_inline(title)}</div>" if title else "")
    scroll = ("<style>.nd-scroll{scrollbar-width:thin;scrollbar-color:#3b4d66 #0b1422}"
              ".nd-scroll::-webkit-scrollbar{width:8px}.nd-scroll::-webkit-scrollbar-track{background:#0b1422;border-radius:6px}"
              ".nd-scroll::-webkit-scrollbar-thumb{background:#3b4d66;border-radius:6px}</style>"
              f"<div class='nd-scroll' style='max-height:{COMMENT_MAX_H}px;overflow-y:auto;padding:0 10px 4px 0;"
              f"border-top:1px solid #26364b;border-bottom:1px solid #26364b'>{body}</div>")
    foot = (f"<div class='live-muted' style='margin-top:9px'>Nhận định do bạn tự cập nhật trong data/nhan_dinh_ma/{c}.md; "
            "số liệu trong đoạn là chữ cố định, không tự đổi theo dữ liệu của app; không phải khuyến nghị mua hay bán.</div>")
    return _card(f"📝 NHẬN ĐỊNH · {c}", head + scroll + foot)


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
