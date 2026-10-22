"""Thẻ "BÁN / CHỐT LỜI" cho trang Bán / Chốt lời.

Dùng:
    import sell_card
    st.markdown(sell_card.cards_html(d), unsafe_allow_html=True)

d là DataFrame lấy từ _wb_table() đã lọc "Hành động bán", cần các cột:
Mã, Giá, Chg %, Score, RS20, Nhóm, Lý do và (tuỳ chọn) "Tăng từ đáy %", "Tên công ty"; as_of là ngày nến cuối.
Màu lấy từ các biến CSS của theme.py (--card, --line, --txt2, --muted, --red, --green...).
"""
import html
import re

import pandas as pd

_CSS = """
.sc-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:16px;margin:8px 0 18px}
.sc{--sc-c:#D92D4A;--sc-bg:#3A1A22;--sc-fg:#fff;background:var(--card);border:1px solid var(--line);border-radius:10px;overflow:hidden;box-shadow:0 10px 26px rgba(0,0,0,.4)}
.sc{scroll-margin-top:110px;transition:box-shadow .3s,border-color .3s}
.sc.sc-flash{border-color:var(--accent,#2dd4a8);box-shadow:0 0 0 3px var(--accent,#2dd4a8),0 10px 26px rgba(0,0,0,.4)}
.sc-head{display:flex;justify-content:space-between;align-items:flex-start;gap:12px;padding:14px 16px 12px;
 border-left:4px solid var(--sc-c);border-bottom:1px solid var(--line);background:linear-gradient(180deg,var(--sc-bg),transparent 140%)}
.sc-tkr{font-size:25px;font-weight:700;line-height:1.1;color:var(--txt2);letter-spacing:.01em}
.sc-name{margin-top:3px;font-size:12.5px;color:var(--muted);line-height:1.35;max-width:210px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.sc-grp{display:inline-block;margin-top:6px;padding:2px 9px;border-radius:999px;background:var(--card2);
 border:1px solid var(--line);color:var(--muted);font-size:12px}
.sc-badge{display:inline-flex;align-items:center;gap:7px;padding:6px 12px;border-radius:6px;background:var(--sc-c);color:var(--sc-fg);
 font-weight:700;font-size:13px;letter-spacing:.04em;white-space:nowrap}
.sc-badge i{width:7px;height:7px;border-radius:50%;background:currentColor;display:inline-block}
.sc-px{display:flex;align-items:baseline;gap:12px;padding:14px 16px 0;font-variant-numeric:tabular-nums}
.sc-p{font-size:32px;font-weight:600;color:var(--txt2);letter-spacing:-.01em}
.sc-chg{font-size:15px;font-weight:600}
.sc-gain{padding:2px 16px 0;font-size:12.5px;color:var(--muted)}
.sc-up{color:var(--green)}.sc-dn{color:var(--red)}
.sc-stats{display:grid;grid-template-columns:1fr 1.5fr;margin:12px 16px 0;border:1px solid var(--line2);border-radius:8px;background:var(--bg2)}
.sc-stat{padding:10px 13px}.sc-stat+.sc-stat{border-left:1px solid var(--line2)}
.sc-k{font-size:12px;color:var(--muted)}
.sc-v{font-size:20px;font-weight:600;color:var(--txt2);margin-top:1px;font-variant-numeric:tabular-nums}
.sc-rsrow{display:flex;align-items:baseline;justify-content:space-between;gap:8px}
.sc-rsnote{font-size:12px;font-weight:500}
.sc-bar{position:relative;height:6px;margin-top:9px;border-radius:3px;background:var(--line)}
.sc-fill{position:absolute;top:0;bottom:0;border-radius:3px}
.sc-mid{position:absolute;top:-4px;bottom:-4px;width:2px;background:var(--muted);border-radius:1px}
.sc-scale{display:flex;justify-content:space-between;margin-top:6px;font-size:11px;color:var(--muted)}
.sc-ma{display:grid;grid-template-columns:1fr 1fr;margin:10px 16px 0;border:1px solid var(--line2);border-radius:8px;background:var(--bg2)}
.sc-ma .sc-v{font-size:17px}
.sc-ma small{font-size:12px;font-weight:600;margin-left:6px}
.sc-why{margin:12px 16px 16px;padding:11px 13px;border-radius:8px;background:var(--card2);border-left:3px solid var(--sc-c)}
.sc-why p{margin:0;color:var(--txt);font-size:13.5px;line-height:1.6}
.sc.t-risk{--sc-c:#C8506A;--sc-bg:#33202A}
.sc.t-over{--sc-c:#F5B942;--sc-bg:#3A2E12;--sc-fg:#3A2E12}
.sc.t-recover{--sc-c:#8B6FE0;--sc-bg:#2A2347}
.sc.t-surge{--sc-c:#1FA97A;--sc-bg:#12332B}
.sc.t-plunge{--sc-c:#D92D4A;--sc-bg:#3A1A22}
.sc-foot{margin:-6px 16px 14px;font-size:12px;color:var(--muted);text-align:right;font-style:italic}
.sc-why .sc-hint{margin-top:8px;padding-top:8px;border-top:1px solid var(--line);font-size:12.5px;color:var(--muted)}
"""
CSS = "<style>" + " ".join(_CSS.split()) + "</style>"

TONES = {
    "sell":    {"label": "BÁN / CHỐT LỜI", "hint": "Đang có lãi: chốt lời. Đang lỗ: cân nhắc cắt lỗ hoặc hạ tỷ trọng."},
    "risk":    {"label": "THEO DÕI SUY YẾU", "hint": "Xu hướng suy yếu, chưa có tín hiệu bán: không mua mới, theo dõi sát."},
    "over":    {"label": "KHÔNG MUA ĐUỔI", "hint": "Cảnh báo không mua đuổi (Overbought)."},
    "surge":   {"label": "TĂNG MẠNH", "hint": "Giá tăng mạnh trong phiên. Không mua đuổi: chờ nhịp lùi về vùng hỗ trợ hoặc xem thẻ ở mục Chờ mua."},
    "plunge":  {"label": "GIẢM MẠNH", "hint": "Giá giảm mạnh trong phiên. Không bắt đáy vội: chờ giá dừng giảm, khối lượng cạn và lấy lại hỗ trợ."},
    "recover": {"label": "ĐANG PHỤC HỒI", "hint": "Chỉ chuyển sang tab Chờ mua khi vượt MA50 / kháng cự (xác nhận xu hướng)."},
}

_PREFIX = re.compile(r"^\s*(BÁN|CHỐT LỜI)\s*:\s*", re.I)


_NAME_RULES = [
    (re.compile(r"\s*-\s*CTCP\s*$", re.I), ""),
    (re.compile(r"^Ngân hàng (Thương mại )?(Cổ phần|TNHH)\s+", re.I), "Ngân hàng "),
    (re.compile(r"^Tổng Công ty (Cổ phần )?", re.I), "Tổng công ty "),
    (re.compile(r"^(Công ty (Cổ phần|TNHH)|CTCP)\s+", re.I), ""),
]


def short_name(name) -> str:
    """Rút gọn tên pháp lý cho vừa thẻ: bỏ "Công ty Cổ phần", "- CTCP"; "Ngân hàng Thương mại Cổ phần X" -> "Ngân hàng X"."""
    if not isinstance(name, str) or not name.strip():
        return ""
    out = name.strip()
    for rx, rep in _NAME_RULES:
        out = rx.sub(rep, out).strip()
    return out or name.strip()


def _tidy_sentence(text: str) -> str:
    """Viết hoa chữ cái đầu và thêm dấu chấm cuối câu (nếu chưa có dấu kết câu)."""
    t = str(text or "").strip().rstrip(";,: ")
    if not t:
        return ""
    t = t[0].upper() + t[1:]
    return t if t[-1] in ".!?…" else t + "."


def _f(x, nd=2):
    """Định dạng số; thiếu dữ liệu -> dấu gạch."""
    try:
        return f"{float(x):.{nd}f}" if pd.notna(x) else "–"
    except (TypeError, ValueError):
        return "–"


def _rs_bar(rs) -> str:
    """Thanh RS vs VNI: thang 0.5 – 1.5, vạch mốc 1.0 (bằng VN-Index)."""
    if pd.isna(rs):
        return ""
    pos = lambda v: max(0.0, min(1.0, (float(v) - 0.5) / 1.0)) * 100
    a, b = pos(1.0), pos(rs)
    col = "var(--green)" if rs >= 1 else "var(--red)"
    return (f'<div class="sc-bar"><div class="sc-fill" style="left:{min(a, b):.1f}%;width:{abs(a - b):.1f}%;background:{col}"></div>'
            f'<div class="sc-mid" style="left:calc({a:.1f}% - 1px)"></div></div>'
            '<div class="sc-scale"><span>0.5</span><span>1.0 = VN-Index</span><span>1.5</span></div>')


def _fmt_date(x) -> str:
    """dd/mm/yyyy; không hiểu được ngày thì trả về rỗng."""
    try:
        return pd.Timestamp(x).strftime("%d/%m/%Y") if pd.notna(x) else ""
    except (TypeError, ValueError):
        return ""


def _ma_cell(label, ma, pct) -> str:
    if pd.isna(ma):
        return f'<div class="sc-stat"><div class="sc-k">{label}</div><div class="sc-v">–</div></div>'
    cls = "" if pd.isna(pct) else ("sc-up" if float(pct) >= 0 else "sc-dn")
    sub = "" if pd.isna(pct) else f'<small class="{cls}">{float(pct):+.1f}%</small>'
    return f'<div class="sc-stat"><div class="sc-k">{label}</div><div class="sc-v">{_f(ma)}{sub}</div></div>'


def _ma_html(r) -> str:
    """Hàng MA20 / MA50 (giá trị + % giá hiện tại so với MA); chỉ hiện khi dữ liệu có cột MA20 / MA50."""
    if "MA20" not in r.index and "MA50" not in r.index:
        return ""
    return ('<div class="sc-ma">' + _ma_cell("MA20", r.get("MA20"), r.get("MA20 %")) +
            _ma_cell("MA50", r.get("MA50"), r.get("MA50 %")) + '</div>')


def card_html(r, as_of=None, tone="sell") -> str:
    """HTML một thẻ. Viết liền một dòng: Streamlit coi dòng thụt 4 ô trở lên là code."""
    tn = TONES.get(tone, TONES["sell"])
    esc = lambda s: html.escape(str(s if pd.notna(s) else ""))
    chg = r.get("Chg %")
    up = pd.notna(chg) and float(chg) >= 0
    rs = r.get("RS20")
    rs_ok = pd.notna(rs) and float(rs) >= 1
    gain = r.get("Tăng từ đáy %")
    gain_html = f'<div class="sc-gain">Đã tăng {float(gain):.0f}% từ đáy</div>' if pd.notna(gain) else ""
    nm = short_name(r.get("Tên công ty"))
    name_html = f'<div class="sc-name" title="{esc(r.get("Tên công ty"))}">{esc(nm)}</div>' if nm else ""
    dt = _fmt_date(as_of)
    foot_html = f'<div class="sc-foot">Theo nến cuối phiên {dt}</div>' if dt else ""
    reason = _tidy_sentence(_PREFIX.sub("", str(r.get("Lý do") or "")))
    chg_html = (f'<span class="sc-chg {"sc-up" if up else "sc-dn"}">{"▲" if up else "▼"} {float(chg):+.2f}%</span>'
                if pd.notna(chg) else "")
    rs_note = "" if pd.isna(rs) else (
        f'<span class="sc-rsnote {"sc-up" if rs_ok else "sc-dn"}">{"Mạnh hơn" if rs_ok else "Yếu hơn"} VN-Index</span>')
    return (
        f'<article id="sc-{esc(r.get("Mã"))}" class="sc t-{tone if tone in TONES else "sell"}">'
        f'<header class="sc-head"><div><div class="sc-tkr">{esc(r.get("Mã"))}</div>{name_html}<span class="sc-grp">{esc(r.get("Nhóm"))}</span></div>'
        f'<span class="sc-badge"><i></i>{tn["label"]}</span></header>'
        f'<div class="sc-px"><span class="sc-p">{_f(r.get("Giá"))}</span>{chg_html}</div>'
        f'{gain_html}'
        '<div class="sc-stats">'
        f'<div class="sc-stat"><div class="sc-k">Score</div><div class="sc-v">{_f(r.get("Score"), 1)}</div></div>'
        f'<div class="sc-stat"><div class="sc-k">RS vs VNI</div><div class="sc-rsrow"><div class="sc-v">{_f(rs)}</div>{rs_note}</div>{_rs_bar(rs)}</div>'
        '</div>'
        f'{_ma_html(r)}'
        f'<div class="sc-why"><div class="sc-k" style="margin-bottom:3px">Lý do</div><p>{esc(reason)}</p>'
        f'<p class="sc-hint">{esc(tn["hint"])}</p></div>'
        f'{foot_html}'
        '</article>'
    )


def cards_html(d: pd.DataFrame, as_of=None, tone="sell") -> str:
    """Lưới thẻ cho toàn bộ DataFrame (kèm CSS). as_of: ngày nến cuối (vd latest_date của app) hiện ở đáy thẻ.
    tone: "sell" (BÁN / CHỐT LỜI), "risk" (theo dõi suy yếu), "over" (không mua đuổi), "recover" (đang phục hồi)."""
    return CSS + '<div class="sc-grid">' + "".join(card_html(r, as_of, tone) for _, r in d.iterrows()) + "</div>"


def add_names(d: pd.DataFrame, fund_map: dict) -> pd.DataFrame:
    """Gắn cột "Tên công ty" từ fund_map (kết quả của _wb_meta_maps trong app.py)."""
    return d.assign(**{"Tên công ty": d["Mã"].map(lambda c: (fund_map.get(str(c).upper()) or {}).get("Tên công ty", ""))})
