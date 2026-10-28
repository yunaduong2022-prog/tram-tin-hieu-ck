"""Phần THÊM VÀO CUỐI action_summary.py (text, parts, plan). Không sửa hàm cũ nào; dùng _signals, _levels, _scenario, _rows, _picture,
_ok, re, _html có sẵn trong action_summary.py."""


def text(ctx: dict) -> str:
    """Bản chữ của "Tóm tắt nhanh · Kế hoạch hành động" để gửi Telegram (parse_mode=HTML, đã escape). Thiếu giá thì trả chuỗi rỗng.
    Dùng chung quy tắc với html(): cùng _signals / _levels / _rows nên nội dung khớp thẻ trong app."""
    if not _ok(ctx.get("close")):
        return ""
    s = _signals(ctx)
    lv = _levels(ctx, s)
    esc = _html.escape
    pic = _picture(s).replace("</div><div>", "\n")
    pic = re.sub(r"</?div[^>]*>", "", pic)
    rows = []
    for pos, head, why, zone in _rows(ctx, s, lv):
        rows.append(f"• <b>{esc(pos)}:</b> <b>{esc(head)}</b> {esc(why)}" + (f"\n   ↳ {esc(zone)}" if zone else ""))
    return "<b>📝 Tóm tắt nhanh</b>\n" + pic + "\n\n<b>🎯 Kế hoạch hành động</b>\n" + "\n".join(rows)


def parts(ctx: dict) -> dict:
    """Các phần rời để Telegram tự ghép: {"picture": "Ngắn hạn…\\nTrung hạn…", "cash": (kết luận, giải thích, mốc giá) của vị thế Cầm tiền mặt}.
    Thiếu giá thì trả {}."""
    if not _ok(ctx.get("close")):
        return {}
    s = _signals(ctx)
    lv = _levels(ctx, s)
    pic = _picture(s).replace("</div><div>", "\n")
    pic = re.sub(r"</?div[^>]*>", "", pic)
    rows = {pos: (head, why, zone) for pos, head, why, zone in _rows(ctx, s, lv)}
    return {"picture": pic, "cash": rows.get("Cầm tiền mặt")}


def plan(ctx: dict) -> dict:
    """Giá mua / giá cắt lỗ đúng như khối "Tóm tắt nhanh · Kết luận hành động" cho vị thế CẦM TIỀN MẶT (cùng nhánh quy tắc với _rows).
    Trả {"scenario", "buy": {"zone": (lo, hi)} | {"levels": [giá…]} | None, "wait": (tên mốc, giá) | None, "stop": giá | None, "res": giá | None};
    {} nếu thiếu giá. `buy` = vùng / mốc canh mua; `wait` = mốc phải lấy lại trước khi xét mua (khi kết luận là chưa mua)."""
    if not _ok(ctx.get("close")):
        return {}
    s = _signals(ctx)
    lv = _levels(ctx, s)
    sc = _scenario(s)
    ma20, ma50 = s["ma"][20], s["ma"][50]
    z = ctx.get("zone")
    zone = (float(z[0]), float(z[1])) if z and _ok(z[0]) and _ok(z[1]) else None
    buy = wait = None
    stop = lv["stop"]
    if sc == "A":
        buy = {"levels": list(lv["buy"])} if lv["buy"] else None
    elif sc == "B":
        if s["over"] or s["sell"]:
            buy = {"levels": [float(ma20)]} if _ok(ma20) else None
        elif s["buy"] or s["near"]:
            buy = {"zone": zone} if zone else None
            if _ok(ma20):
                stop = float(ma20)                      # thẻ ghi "Cắt lỗ dưới MA20" cho nhánh giải ngân thăm dò
        else:
            buy = {"levels": [float(ma20)]} if _ok(ma20) else None
    elif sc == "C":
        wait = ("MA50", float(ma50)) if _ok(ma50) else None
    elif sc == "D":
        wait = ("MA20", float(ma20)) if _ok(ma20) else None
    else:
        buy = {"levels": list(lv["buy"])} if lv["buy"] else ({"zone": zone} if zone else None)
    return {"scenario": sc, "buy": buy, "wait": wait, "stop": stop, "res": lv["res"]}
