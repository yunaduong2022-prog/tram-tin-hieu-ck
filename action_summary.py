"""Tóm tắt nhanh cuối thẻ: từ các tag đang có trên thẻ (MA, trạng thái chờ mua / bán, Dự báo, phân kỳ RSI, Wyckoff, hỗ trợ - kháng cự)
suy ra hành động cụ thể cho 3 vị thế: đang giữ cổ phiếu, đang cầm tiền mặt, đang dùng margin. Không phụ thuộc Streamlit.

Cách đọc quy tắc (sửa ở đây nếu muốn đổi):
  Ngắn hạn  : tiêu cực  = có tín hiệu bán / hạ tỷ trọng, hoặc giá dưới cả MA20 lẫn MA50
              trung tính = giá dưới MA20 nhưng còn trên MA50 (điều chỉnh)
              tích cực  = giá trên MA20 và không có tín hiệu bán
  Trung hạn : tích cực  = giá trên MA50 và MA200 (Wyckoff đang phân phối thì hạ xuống trung tính)
              tiêu cực  = giá dưới cả MA50 và MA200
              trung tính = còn lại
  Ghép (Trung hạn, Ngắn hạn) thành 5 kịch bản A-E rồi chọn hành động; các tag phụ (phân kỳ RSI, Wyckoff, Dự báo, quá đà)
  chỉ thêm / bớt ý trong câu và hiện ở dòng "Căn cứ".
Quy tắc mang tính chủ quan; chỉ để tham khảo, không phải khuyến nghị đầu tư.

ctx (dict): close, ma20, ma50, ma200 (float | None), label (nhãn tag trạng thái: "Hạ tỷ trọng", "BÁN", "CHỐT LỜI", "Điểm mua đẹp"...),
  state (trạng thái chi tiết), reason (lý do), lean (+1 / -1 / 0: dự báo trên biểu đồ), div (list phân kỳ RSI của app),
  wy (dict wyckoff.compact | None), sup, res (hỗ trợ / kháng cự khung Ngày | None), zone (vùng mua từ-đến | None).
"""
from __future__ import annotations

import html as _html

SELL_LABELS = ("BÁN", "CHỐT LỜI", "Hạ tỷ trọng")
BUY_STATES = ("Điểm mua đẹp", "Đã có tín hiệu mua theo chiến lược")
NEAR_STATES = ("Theo dõi điểm mua", "Gần vùng mua, cần thêm xác nhận", "Chớm tăng giá", "Tích lũy / Siết nền giá")
OVERBOUGHT = "Tăng quá đà"


def _ok(x) -> bool:
    try:
        return x is not None and float(x) == float(x) and float(x) > 0
    except (TypeError, ValueError):
        return False


def _p(x) -> str:
    return f"{float(x):,.2f}"


def _signals(c: dict) -> dict:
    close = c.get("close")
    ma = {n: c.get(f"ma{n}") for n in (20, 50, 200)}
    above = {n: (_ok(ma[n]) and _ok(close) and float(close) >= float(ma[n])) for n in ma}
    label, state, reason = str(c.get("label") or ""), str(c.get("state") or ""), str(c.get("reason") or "")
    sell = (label in SELL_LABELS or reason.startswith(("BÁN", "CHỐT LỜI")) or "tín hiệu bán" in reason)
    wy = c.get("wy") or None
    dist = bool(wy and wy.get("kind") == "dist")
    acc = bool(wy and wy.get("kind") == "acc")
    divs = [d for d in (c.get("div") or []) if d.get("tf") in ("D", "W")]
    div_up = any(d.get("kind") in ("hid_bull", "reg_bull", "exa_bull") for d in divs)
    div_dn = any(d.get("kind") in ("reg_bear", "exa_bear", "hid_bear") for d in divs)
    if sell or (_ok(ma[20]) and not above[20] and _ok(ma[50]) and not above[50]):
        short = "-"
    elif above[20]:
        short = "+"
    else:
        short = "~"
    if _ok(ma[50]) and _ok(ma[200]):
        mid = "+" if above[50] and above[200] else "-" if not above[50] and not above[200] else "~"
    else:
        mid = "~"
    if dist and mid == "+":
        mid = "~"
    return dict(ma=ma, above=above, sell=sell, dist=dist, acc=acc, div_up=div_up, div_dn=div_dn, short=short, mid=mid, wy=wy,
                lean=int(c.get("lean") or 0), buy=state in BUY_STATES, near=state in NEAR_STATES, over=state == OVERBOUGHT,
                label=label, state=state)


def _levels(c: dict, s: dict) -> dict:
    """Mốc giá dùng trong câu: vùng canh mua (hỗ trợ dưới giá), kháng cự gần, mốc cắt lỗ cuối cùng."""
    close = float(c["close"]) if _ok(c.get("close")) else None
    ma, wy = s["ma"], s["wy"]
    buy = []
    if close:
        if _ok(ma[50]) and ma[50] < close * 0.99:
            buy.append(float(ma[50]))
        if wy and close > wy["top"] * 1.01:               # biên trên vùng Wyckoff vừa bị vượt = kháng cự cũ thành hỗ trợ
            buy.append(float(wy["top"]))
        if not buy and _ok(c.get("sup")) and c["sup"] < close * 0.99:
            buy.append(float(c["sup"]))
    buy = sorted(set(round(b, 2) for b in buy), reverse=True)
    if len(buy) == 2 and buy[0] / buy[1] - 1 < 0.015:     # hai mốc sát nhau thì gộp một
        buy = buy[:1]
    stop = None
    if close:
        if wy and _ok(wy.get("bot")) and wy["bot"] < close:
            stop = float(wy["bot"])
        elif _ok(ma[200]) and ma[200] < close:
            stop = float(ma[200])
        elif _ok(c.get("sup")) and c["sup"] < close:
            stop = float(c["sup"]) * 0.97
    res = None
    if close:
        for x in (ma[20], ma[50], c.get("res")):
            if _ok(x) and x > close * 1.005:
                res = float(x)
                break
    return dict(buy=buy, stop=stop, res=res)


def _scenario(s: dict) -> str:
    m, sh = s["mid"], s["short"]
    if m == "+":
        return "B" if sh == "+" else "A"
    if m == "-":
        return "C" if sh == "+" else "D"
    return "E"


def _basis(s: dict) -> list[str]:
    out = []
    if s["label"]:
        out.append(s["label"])
    if s["lean"]:
        out.append("Dự báo nghiêng tăng" if s["lean"] > 0 else "Dự báo nghiêng giảm")
    out.append({"+": "Ngắn hạn tích cực", "~": "Ngắn hạn điều chỉnh", "-": "Ngắn hạn tiêu cực"}[s["short"]])
    out.append({"+": "Trung hạn tích cực", "~": "Trung hạn trung tính", "-": "Trung hạn suy yếu"}[s["mid"]])
    if s["div_up"]:
        out.append("RSI phân kỳ tăng")
    if s["div_dn"]:
        out.append("RSI phân kỳ giảm")
    wy = s["wy"]
    if wy:
        ph = f" · Pha {wy['phase']}" if wy.get("phase") else ""
        out.append(f"Wyckoff {str(wy.get('kind_name') or '').capitalize()}{ph}".strip())
    return out


def _picture(s: dict) -> str:
    short_r = []
    if s["sell"]:
        short_r.append("có tín hiệu bán / hạ tỷ trọng")
    if not s["above"][20] and _ok(s["ma"][20]):
        short_r.append("giá dưới MA20")
    if s["above"][20] and not s["sell"]:
        short_r.append("giá trên MA20")
    mid_r = []
    for n in (50, 200):
        if _ok(s["ma"][n]):
            mid_r.append(f"{'trên' if s['above'][n] else 'dưới'} MA{n}")
    if s["div_up"]:
        mid_r.append("phân kỳ RSI tăng")
    if s["div_dn"]:
        mid_r.append("phân kỳ RSI giảm")
    if s["wy"]:
        mid_r.append(f"Wyckoff {s['wy'].get('kind_name')}" + (f" pha {s['wy']['phase']}" if s["wy"].get("phase") else ""))
    name = {"+": "Tích cực", "~": "Trung tính", "-": "Tiêu cực"}
    return (f'<div class="ac-pic"><div><b>Ngắn hạn:</b> {name[s["short"]]}' + (f" ({'; '.join(short_r)})" if short_r else "") + "</div>"
            f'<div><b>Trung hạn:</b> {name[s["mid"]]}' + (f" ({'; '.join(mid_r)})" if mid_r else "") + "</div></div>")


def _rows(c: dict, s: dict, lv: dict) -> list[tuple[str, str, str, str]]:
    """[(tên vị thế, kết luận in đậm, giải thích, mốc giá)] cho 3 vị thế."""
    sc = _scenario(s)
    ma20, ma50 = s["ma"][20], s["ma"][50]
    stop, res, buy = lv["stop"], lv["res"], lv["buy"]
    buy_txt = " hoặc ".join(_p(b) for b in buy) if buy else None
    stop_txt = f"Dừng lỗ toàn bộ nếu thủng {_p(stop)}." if stop else ""
    zone = c.get("zone")
    zone_txt = f"{_p(zone[0])} – {_p(zone[1])}" if zone and _ok(zone[0]) and _ok(zone[1]) else None
    hold = cash = margin = None

    if sc == "A":       # Trung hạn tốt, ngắn hạn đang điều chỉnh
        if s["sell"]:
            hold = ("BÁN BỚT 30–50%", "ở nhịp hồi ngắn hạn, giữ phần còn lại theo trung hạn.",
                    (f"Bán khi giá hồi tới MA20 {_p(ma20)}. " if _ok(ma20) else "") + (f"Siết cắt lỗ ở MA50 {_p(ma50)}. " if _ok(ma50) else "") + stop_txt)
        else:
            hold = ("GIỮ, KHÔNG MUA THÊM", "chờ giá lấy lại MA20 để xác nhận lại nhịp tăng.",
                    (f"Cắt lỗ nếu thủng MA50 {_p(ma50)}. " if _ok(ma50) else "") + stop_txt)
        extra = " Ưu tiên khi lực bán cạn (vol giảm) hoặc có nến rút chân." if (s["div_up"] or s["acc"]) else ""
        cash = ("ĐỨNG YÊN", "chờ giá lùi về vùng hỗ trợ mới mua, không mua đuổi; chia 2–3 phần.",
                (f"Canh mua quanh {buy_txt}." if buy_txt else "Chờ giá về hỗ trợ gần nhất.") + extra)
        margin = (("HẠ MARGIN NGAY", "đưa tài khoản về mức an toàn.", f"Rủi ro call margin nếu thủng MA50 {_p(ma50)}." if _ok(ma50) else "")
                  if s["sell"] else
                  ("KHÔNG TĂNG MARGIN", "giữ tỷ lệ vay thấp cho tới khi giá lấy lại MA20.", f"Hạ margin nếu thủng MA50 {_p(ma50)}." if _ok(ma50) else ""))
    elif sc == "B":     # Trung hạn tốt, ngắn hạn tốt
        if s["sell"] or s["over"]:
            hold = ("CHỐT BỚT 20–30%", "giá đã chạy xa / có tín hiệu bán, bảo vệ lợi nhuận, giữ phần còn lại.",
                    (f"Nâng cắt lỗ lên MA20 {_p(ma20)}." if _ok(ma20) else ""))
        else:
            hold = ("GIỮ", "có thể gia tăng khi giá lùi về MA20.",
                    (f"Cắt lỗ nếu thủng MA20 {_p(ma20)}. " if _ok(ma20) else "") + (f"Mục tiêu gần: {_p(res)}." if res else ""))
        if s["over"] or s["sell"]:
            cash = ("KHÔNG MUA ĐUỔI", "chờ nhịp lùi về MA20 / hỗ trợ.", (f"Canh mua quanh {_p(ma20)}." if _ok(ma20) else ""))
        elif s["buy"] or s["near"]:
            cash = ("GIẢI NGÂN THĂM DÒ 30–50%", "chia lệnh, phần còn lại mua khi giá lùi về hỗ trợ.",
                    (f"Vùng mua: {zone_txt}. " if zone_txt else "") + (f"Cắt lỗ dưới {_p(ma20)}." if _ok(ma20) else ""))
        else:
            cash = ("CHỜ NHỊP LÙI", "chưa có điểm mua rõ, ưu tiên mua khi giá về hỗ trợ.",
                    (f"Canh mua quanh {_p(ma20)}." if _ok(ma20) else ""))
        margin = (("HẠN CHẾ MARGIN", "có tín hiệu bán / quá đà, không dùng thêm đòn bẩy.", "")
                  if (s["sell"] or s["over"]) else
                  ("ĐƯỢC DÙNG MARGIN THẤP", "kỷ luật cắt lỗ.", f"Hạ margin nếu thủng MA20 {_p(ma20)}." if _ok(ma20) else ""))
    elif sc == "C":     # Hồi kỹ thuật trong xu hướng yếu
        hold = ("CHỦ ĐỘNG BÁN / HẠ TỶ TRỌNG", "khi giá hồi tới kháng cự; xu hướng trung hạn chưa tốt.",
                (f"Kháng cự gần: {_p(res)}. " if res else "") + stop_txt)
        cash = ("KHÔNG MUA", "đây mới là nhịp hồi kỹ thuật, chờ giá lấy lại MA50 kèm vol rồi mới xét.",
                (f"Mốc xét lại: trên MA50 {_p(ma50)}." if _ok(ma50) else ""))
        margin = ("KHÔNG DÙNG MARGIN", "xu hướng trung hạn chưa xác nhận tăng.", "")
    elif sc == "D":     # Yếu cả ngắn và trung hạn
        hold = ("HẠ TỶ TRỌNG MẠNH / THOÁT HÀNG", "bán ở nhịp hồi, không gồng lỗ.", stop_txt or (f"Thủng MA20 {_p(ma20)} chưa lấy lại thì bán tiếp." if _ok(ma20) else ""))
        cash = ("ĐỨNG NGOÀI", "không bắt đáy khi chưa có tín hiệu đảo chiều." + (" Có phân kỳ / tích lũy: chỉ theo dõi, chờ xác nhận." if (s["div_up"] or s["acc"]) else ""),
                (f"Xét lại khi giá lấy lại MA20 {_p(ma20)} kèm vol." if _ok(ma20) else ""))
        margin = ("HẠ TOÀN BỘ MARGIN", "rủi ro call margin cao.", "")
    else:               # E: trung hạn trung tính
        hold = (("BÁN BỚT 30%", "có tín hiệu bán, giữ phần còn lại.", stop_txt) if s["sell"] else
                ("GIỮ, THEO DÕI", "chưa có xu hướng rõ, không mua thêm.", (f"Cắt lỗ nếu thủng MA50 {_p(ma50)}. " if _ok(ma50) else "") + stop_txt))
        cash = ("CHỜ XÁC NHẬN", "chỉ thăm dò nhỏ khi giá giữ được hỗ trợ và vol cải thiện.",
                (f"Canh mua quanh {buy_txt}." if buy_txt else (f"Vùng mua: {zone_txt}." if zone_txt else "")))
        margin = ("HẠN CHẾ MARGIN", "xu hướng chưa rõ.", "")

    if s["dist"] and sc in ("A", "B", "E"):          # Wyckoff đang phân phối: thận trọng hơn một bậc
        hold = (hold[0], hold[1] + " Wyckoff đang nghiêng phân phối, thận trọng hơn.", hold[2])
    return [("Có cổ phiếu", *hold), ("Cầm tiền mặt", *cash), ("Đang margin", *margin)]


def rules() -> str:
    """CSS thuần (không có thẻ <style>) để nhét vào waiting_buy.card_css."""
    return """
.ac-box{margin-top:12px;border:1px solid var(--line);border-radius:14px;background:var(--card2);padding:12px 14px 10px}
.ac-hd{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap;padding-bottom:10px;margin-bottom:10px;border-bottom:1px solid var(--line);
  font-size:32px;font-weight:800;line-height:1.1;color:var(--txt2)}
.ac-hd .sep{font-weight:400;color:var(--muted)}
.ac-t{font-size:12px;font-weight:800;letter-spacing:.4px;text-transform:uppercase;color:var(--muted);margin-bottom:8px}
.ac-pic{font-size:13px;line-height:1.55;color:var(--txt);margin-bottom:10px}
.ac-pic b{color:var(--txt2)}
.ac-tb{border-collapse:collapse;width:100%;font-size:13px;color:var(--txt)}
.ac-tb th{text-align:left;font-weight:700;color:var(--muted);font-size:12px;padding:6px 8px;border-bottom:1px solid var(--line)}
.ac-tb td{vertical-align:top;padding:9px 8px;border-bottom:1px solid var(--line2);line-height:1.5}
.ac-tb tr:last-child td{border-bottom:none}
.ac-tb td.pos{font-weight:800;color:var(--txt2);white-space:nowrap;width:1%}
.ac-tb td b{color:var(--txt2)}
.ac-tb td.lv{color:var(--txt)}
.ac-bs{font-size:11.5px;color:var(--muted);margin-top:8px;line-height:1.5}
.ac-ft{font-size:11px;color:var(--muted);font-style:italic;margin-top:4px}
"""


def css() -> str:
    return "<style>" + rules() + "</style>"


def html(ctx: dict) -> str:
    """Khối HTML liền một dòng (không thụt lề, tránh Markdown coi là code). Thiếu giá / MA thì trả chuỗi rỗng."""
    if not _ok(ctx.get("close")):
        return ""
    s = _signals(ctx)
    lv = _levels(ctx, s)
    esc = _html.escape
    body = "".join(
        f'<tr><td class="pos">{esc(pos)}</td><td><b>{esc(head)}</b> {esc(why)}</td><td class="lv">{esc(zone)}</td></tr>'
        for pos, head, why, zone in _rows(ctx, s, lv))
    code = esc(str(ctx.get("code") or ""))
    head = (f'<div class="ac-hd"><span>{code}</span><span class="sep">|</span><span>{float(ctx["close"]):,.1f}</span></div>'
            if code else "")
    return ('<div class="ac-box">' + head + '<div class="ac-t">📝 Tóm tắt nhanh · Kết luận hành động</div>' + _picture(s) +
            '<table class="ac-tb"><thead><tr><th>Vị thế tài khoản</th><th>Hành động</th><th>Vùng giá / Mốc lưu ý</th></tr></thead>'
            f'<tbody>{body}</tbody></table>'
            f'<div class="ac-bs">Căn cứ: {esc(" · ".join(_basis(s)))}</div>'
            '<div class="ac-ft">Quy tắc mang tính chủ quan; chỉ để tham khảo, không phải khuyến nghị đầu tư.</div></div>')
