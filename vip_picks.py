"""Khuyến nghị khách hàng (VIP): danh mục cổ phiếu do Admin chọn, hiển thị cho khách kèm Điểm mua, Lợi nhuận, Target, Cutloss,
Điểm bán, điểm FA / TA và khuyến nghị. Khác mục "Cổ phiếu của tôi" (danh mục riêng của người dùng).

Quyền
- Khách chỉ xem bảng và mở đồ thị. Admin mở khóa bằng mật khẩu (biến môi trường hoặc Secrets VIP_ADMIN_PASSWORD) để thêm / sửa / xóa mã.
  Chưa đặt mật khẩu thì phần Admin luôn khóa (an toàn mặc định).

Dữ liệu
- data/khuyen_nghi_khach_hang.csv: mỗi dòng là một mã (Mã, Điểm mua, Target, Cutloss, Điểm bán). Giá tính bằng nghìn đồng như phần còn lại của app.
  Điểm mua nhập một giá ("35.5") hoặc một vùng ("35.5 - 36.0"); Điểm bán nhập "42.0" hoặc "≥ 42.0".
- Ô nào để trống thì tự điền theo hệ thống (đánh dấu "tự động" trên bảng):
    Điểm mua  <- vùng / mốc canh mua của "Tóm tắt nhanh · Kết luận hành động" (action_summary.plan), thiếu thì vùng mua của bảng Chờ mua
    Cutloss   <- mốc cắt lỗ của "Tóm tắt nhanh", thiếu thì cắt lỗ của bảng Chờ mua
    Target    <- Mục tiêu 1 của bảng Chờ mua, thiếu thì kháng cự gần của "Tóm tắt nhanh"
    Điểm bán  <- Mục tiêu 2 của bảng Chờ mua (nếu cao hơn Target), không thì bằng Target
- Lợi nhuận = giá khớp so với Điểm mua do Admin nhập (giữa vùng nếu là vùng); Điểm mua tự động thì để "—" vì chưa phải giá vào lệnh.
  Target / Cutloss tính % so với giá khớp.

Cách chấm điểm (sửa các hằng số / hàm fa_score, ta_score nếu muốn đổi):
- Tổng điểm = Score sẵn có của app (thang 0-10) × 10; hạng A ≥ 75, B ≥ 60, C ≥ 40, còn lại D.
- FA (0-100) chấm từ ROE, P/E, P/B (data/fundamentals.csv); chỉ tính các chỉ số có số liệu, cần ít nhất 2 chỉ số.
- TA (0-100, tối đa 90) chấm từ giá so với MA20, độ dốc MA20, độ xa MA20 và RSI(14) khung Ngày.
- Dòng "Khối ngoại gom / bán ròng" chỉ hiện khi có data/foreign_flow.csv (tổng 5 phiên gần nhất).
Chỉ phục vụ nghiên cứu, không phải khuyến nghị đầu tư.
"""
from __future__ import annotations

import hmac
import html as _html
import os
import re

import numpy as np
import pandas as pd
import streamlit as st

import action_summary as AS

PATH = "data/khuyen_nghi_khach_hang.csv"
FOREIGN_PATH = "data/foreign_flow.csv"
COLS = ["Mã", "Điểm mua", "Target", "Cutloss", "Điểm bán"]
GRADES = ((75, "A"), (60, "B"), (40, "C"), (0, "D"))        # (điểm tối thiểu, hạng)
NEAR_BUY = 1.01                                              # giá <= biên trên vùng mua × 1.01 vẫn coi là "trong vùng mua"
BELOW_BUY = 0.98                                             # giá < biên dưới vùng mua × 0.98 coi là đã lệch khỏi vùng mua
_NUM = re.compile(r"\d+(?:[.,]\d+)?")


# ------------------------------------------------------------------ DỮ LIỆU
def _nums(text) -> list[float]:
    return [float(x.replace(",", ".")) for x in _NUM.findall(str(text or ""))]


def parse_range(text) -> tuple[float, float] | None:
    n = _nums(text)
    if not n:
        return None
    return (min(n[:2]), max(n[:2])) if len(n) >= 2 else (n[0], n[0])


def parse_price(text) -> float | None:
    n = _nums(text)
    return n[0] if n else None


def _clean(d: pd.DataFrame) -> pd.DataFrame:
    d = d.copy()
    for c in COLS:
        if c not in d.columns:
            d[c] = ""
        d[c] = d[c].fillna("").astype(str).str.strip()
    d["Mã"] = d["Mã"].str.upper()
    d = d[d["Mã"].str.fullmatch(r"[A-Z0-9]{2,10}")]
    return d[COLS].drop_duplicates("Mã", keep="last").reset_index(drop=True)


def load(path: str = PATH) -> pd.DataFrame:
    if os.path.exists(path):
        try:
            return _clean(pd.read_csv(path, dtype=str, encoding="utf-8-sig"))
        except Exception:  # noqa: BLE001
            pass
    return _clean(pd.DataFrame(columns=COLS))


def save(d: pd.DataFrame, path: str = PATH) -> str:
    """Trả '' nếu lưu được, ngược lại là thông báo lỗi."""
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        _clean(d).to_csv(path, index=False, encoding="utf-8-sig")
        return ""
    except Exception as e:  # noqa: BLE001
        return str(e)


def upsert(d: pd.DataFrame, row: dict) -> pd.DataFrame:
    d = d[d["Mã"] != row["Mã"]]
    return _clean(pd.concat([d, pd.DataFrame([row])], ignore_index=True))


def remove(code: str, path: str = PATH) -> str:
    d = load(path)
    return save(d[d["Mã"] != code], path)


# ------------------------------------------------------------------ ĐIỂM FA / TA
def _f(v) -> float | None:
    try:
        x = float(v)
        return x if np.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def fa_score(pe, roe, pb) -> tuple[int | None, list[str]]:
    """Điểm cơ bản 0-100 từ ROE (tối đa 40), P/E (30), P/B (30). Chỉ tính chỉ số có số liệu, cần ít nhất 2; trả (None, []) nếu thiếu."""
    pe, roe, pb = _f(pe), _f(roe), _f(pb)
    got, mx, tags = 0.0, 0.0, []
    if roe is not None:
        mx += 40
        got += 40 if roe >= 25 else 34 if roe >= 18 else 26 if roe >= 12 else 16 if roe >= 8 else 6 if roe >= 0 else 0
        tags.append(f"ROE vượt trội ({roe:.1f}%)" if roe >= 20 else f"ROE thấp ({roe:.1f}%)" if roe < 8 else f"ROE {roe:.1f}%")
    if pe is not None:
        mx += 30
        got += 0 if pe <= 0 else 30 if pe < 8 else 26 if pe < 12 else 20 if pe < 16 else 12 if pe < 22 else 6 if pe < 30 else 0
        tags.append(f"P/E rẻ ({pe:.2f})" if 0 < pe < 12 else f"P/E cao ({pe:.2f})" if pe >= 25 else f"P/E {pe:.2f}")
    if pb is not None:
        mx += 30
        got += 0 if pb <= 0 else 30 if pb < 1 else 25 if pb < 1.5 else 18 if pb < 2.2 else 10 if pb < 3.2 else 3
        if 0 < pb < 1:
            tags.append(f"P/B dưới sổ sách ({pb:.2f})")
    if mx < 60:                       # chưa đủ 2 chỉ số
        return None, []
    return int(round(got / mx * 100)), tags


def ta_score(close, ma20, ma20_prev, rsi) -> tuple[int | None, list[str]]:
    """Điểm kỹ thuật 0-100 (tối đa 90): giá trên MA20 30, MA20 dốc lên 10, giá chưa xa MA20 (0-3%: 15, 3-8%: 10), RSI (50-62: 35,
    45-50 hoặc 62-70: 25, 40-45 hoặc 70-78: 12, còn lại 4)."""
    close, ma20, ma20_prev, rsi = _f(close), _f(ma20), _f(ma20_prev), _f(rsi)
    if close is None or ma20 is None or rsi is None or ma20 <= 0:
        return None, []
    gap = (close / ma20 - 1) * 100
    s, tags = 0, []
    if close > ma20:
        s += 30
        tags.append(f"Trên MA20 ({gap:+.2f}%)")
        if gap <= 3:
            s += 15
        elif gap <= 8:
            s += 10
        else:
            tags.append("Xa MA20, dễ điều chỉnh")
    else:
        tags.append(f"Dưới MA20 ({gap:+.2f}%)")
    if ma20_prev is not None and ma20 > ma20_prev:
        s += 10
    s += 35 if 50 <= rsi <= 62 else 25 if (45 <= rsi < 50 or 62 < rsi <= 70) else 12 if (40 <= rsi < 45 or 70 < rsi <= 78) else 4
    return int(s), tags


def grade_of(pct: float) -> str:
    return next(g for lo, g in GRADES if pct >= lo)


# ------------------------------------------------------------------ SỐ LIỆU HỆ THỐNG
@st.cache_data(show_spinner=False)
def _foreign_cached(mtime: float) -> dict[str, tuple[float, str]]:
    """{mã: (mua/bán ròng 5 phiên gần nhất, sàn)} từ data/foreign_flow.csv; không có file thì {}."""
    try:
        f = pd.read_csv(FOREIGN_PATH, dtype={"Mã": str}, encoding="utf-8-sig")
        f.columns = [str(c).strip() for c in f.columns]
        f["Mã"] = f["Mã"].astype(str).str.upper().str.strip()
        f["Ngày"] = pd.to_datetime(f["Ngày"], errors="coerce", format="mixed", dayfirst=True)
        f["net"] = pd.to_numeric(f["Giá trị mua"], errors="coerce") - pd.to_numeric(f["Giá trị bán"], errors="coerce")
        f = f.dropna(subset=["Ngày", "net"]).sort_values("Ngày")
        out = {}
        for code, g in f.groupby("Mã"):
            ex = str(g["Sàn"].iat[-1]).strip().upper() if "Sàn" in g.columns and pd.notna(g["Sàn"].iat[-1]) else ""
            out[code] = (float(g["net"].tail(5).sum()), ex)
        return out
    except Exception:  # noqa: BLE001
        return {}


def foreign_map() -> dict[str, tuple[float, str]]:
    try:
        return _foreign_cached(os.path.getmtime(FOREIGN_PATH))
    except OSError:
        return {}


def _system_levels(code: str, ctx_fn, wbrow: dict) -> dict:
    """Mốc hệ thống dùng để điền ô trống: {"buy": (lo, hi)|None, "stop", "target", "sell"} (xem docstring đầu file)."""
    pl: dict = {}
    try:
        ctx = ctx_fn(code) if ctx_fn else None
        pl = AS.plan(ctx) if ctx else {}
    except Exception:  # noqa: BLE001
        pl = {}
    buy = None
    b = pl.get("buy") or {}
    if b.get("zone"):
        buy = (float(b["zone"][0]), float(b["zone"][1]))
    elif b.get("levels"):
        buy = (min(b["levels"]), max(b["levels"]))
    else:
        lo, hi = _f(wbrow.get("Vùng mua từ")), _f(wbrow.get("Vùng mua đến"))
        if lo and hi:
            buy = (min(lo, hi), max(lo, hi))
    stop = _f(pl.get("stop")) or _f(wbrow.get("Cắt lỗ"))
    t1 = _f(wbrow.get("Mục tiêu 1")) or _f(pl.get("res"))
    t2 = _f(wbrow.get("Mục tiêu 2"))
    sell = t2 if (t2 and t1 and t2 > t1) else t1
    return {"buy": buy, "stop": stop, "target": t1, "sell": sell}


def recommend(price, buy, stop, sell, wbreason: str, buy_auto: bool = False) -> tuple[str, str, str]:
    """(nhãn, màu, ghi chú). Điểm mua do Admin nhập được coi là giá vào lệnh (giá trên vùng = NẮM GIỮ); điểm mua tự động chỉ là vùng
    canh mua của hệ thống (giá trên vùng = CHỜ VỀ VÙNG MUA)."""
    reason = str(wbreason or "")
    if stop and price <= stop:
        return "CẮT LỖ", "red", f"Giá thủng cutloss {stop:,.2f}"
    if sell and price >= sell:
        return "CHỐT LỜI", "amber", f"Giá đạt điểm bán {sell:,.2f}"
    if reason.startswith("BÁN"):
        return "HẠ TỶ TRỌNG", "red", "Hệ thống đang báo bán"
    if reason.startswith("CHỐT LỜI"):
        return "CHỐT BỚT", "amber", "Hệ thống đang báo chốt lời"
    if not buy:
        return "THEO DÕI", "gray", "Chưa có điểm mua"
    if price < buy[0] * BELOW_BUY:
        return "DƯỚI VÙNG MUA", "gray", "Giá đã lệch khỏi vùng mua"
    if price <= buy[1] * NEAR_BUY:
        return "VÙNG MUA", "green", "Giá trong vùng mua"
    if buy_auto:
        return "CHỜ VỀ VÙNG MUA", "gray", "Giá đang cao hơn vùng mua của hệ thống"
    return "NẮM GIỮ", "gold", "Giá trên vùng mua, đang có lãi"


# ------------------------------------------------------------------ BẢNG HIỂN THỊ
def build_view(plans: pd.DataFrame, res: pd.DataFrame, frames_d: pd.DataFrame, fund_map: dict, wb: pd.DataFrame,
               meta_fn, ctx_fn) -> pd.DataFrame:
    """Ghép kế hoạch của người dùng với giá, điểm và mốc hệ thống; sắp theo Tổng điểm giảm dần."""
    score = dict(zip(res["Mã"].astype(str).str.upper(), pd.to_numeric(res["Score"], errors="coerce"))) if "Score" in res.columns else {}
    wbmap = wb.drop_duplicates("Mã", keep="first").set_index("Mã").to_dict("index") if wb is not None and not wb.empty else {}
    fgn = foreign_map()
    rows = []
    for _, p in plans.iterrows():
        code = p["Mã"]
        g = frames_d[frames_d["Mã"] == code].sort_values("Ngày").tail(8)
        if g.empty:
            rows.append({"Mã": code, "_nodata": True})
            continue
        close = float(g["Giá đóng cửa"].iat[-1])
        prev = float(g["Giá đóng cửa"].iat[-2]) if len(g) > 1 else np.nan
        ma20_prev = g["MA20"].iat[-6] if len(g) >= 6 and "MA20" in g.columns else np.nan
        wbrow = wbmap.get(code, {})
        sysv = _system_levels(code, ctx_fn, wbrow)

        def pick(user_txt, kind):
            """(giá trị người dùng nhập, tự động?)"""
            if kind == "range":
                r = parse_range(user_txt)
                return (r, False) if r else (sysv["buy"], True)
            v = parse_price(user_txt)
            return (v, False) if v else (sysv[kind], True)

        buy, buy_auto = pick(p["Điểm mua"], "range")
        target, target_auto = pick(p["Target"], "target")
        stop, stop_auto = pick(p["Cutloss"], "stop")
        sell, sell_auto = pick(p["Điểm bán"], "sell")
        sell = sell or target
        if sell and target and sell_auto and sell < target:      # điểm bán tự động không được thấp hơn Target
            sell = target
        entry = (buy[0] + buy[1]) / 2 if buy and not buy_auto else None      # chỉ tính lợi nhuận khi Admin đã nhập điểm mua
        fd = fund_map.get(code, {}) or {}
        fa, fa_tags = fa_score(fd.get("P/E"), fd.get("ROE"), fd.get("P/B"))
        ta, ta_tags = ta_score(close, g["MA20"].iat[-1] if "MA20" in g.columns else np.nan, ma20_prev,
                               g["RSI"].iat[-1] if "RSI" in g.columns else np.nan)
        sc = score.get(code)
        total = None if sc is None or not np.isfinite(sc) else float(min(100.0, max(0.0, sc * 10)))
        wbreason = wbrow.get("Lý do", "") if isinstance(wbrow.get("Lý do", ""), str) else ""
        rec = recommend(close, buy, stop, sell, wbreason, buy_auto)
        name, sector = meta_fn(code) if meta_fn else ("", "")
        net5, exch = fgn.get(code, (None, ""))
        rows.append({
            "Mã": code, "Tên": name, "Ngành": sector, "Sàn": exch, "Giá": close,
            "Chg": close - prev if np.isfinite(prev) else np.nan, "Chg %": (close / prev - 1) * 100 if prev else np.nan,
            "KL": float(g["Khối lượng khớp lệnh"].iat[-1]),
            "Tổng điểm": total, "Hạng": grade_of(total) if total is not None else "",
            "Điểm mua": buy, "buy_auto": buy_auto, "Entry": entry,
            "Lãi": (close - entry) if entry else np.nan, "Lãi %": (close / entry - 1) * 100 if entry else np.nan,
            "Target": target, "target_auto": target_auto, "Cutloss": stop, "stop_auto": stop_auto,
            "Điểm bán": sell, "sell_auto": parse_price(p["Điểm bán"]) is None,
            "FA": fa, "FA tags": fa_tags, "TA": ta, "TA tags": ta_tags,
            "RSI": _f(g["RSI"].iat[-1]) if "RSI" in g.columns else None,
            "Khuyến nghị": rec, "Ngoại": net5,
        })
    v = pd.DataFrame(rows)
    if "Tổng điểm" in v:
        v = v.sort_values("Tổng điểm", ascending=False, na_position="last", kind="stable").reset_index(drop=True)
    return v


# ------------------------------------------------------------------ GIAO DIỆN
CSS = """
<style>
.tp-wrap{overflow-x:auto;border:1px solid var(--line);border-radius:14px;background:var(--card);margin:6px 0 10px}
.tp-tb{border-collapse:collapse;width:100%;min-width:1320px;font-size:13px;color:var(--txt)}
.tp-tb th{text-align:center;font-weight:700;font-size:12px;letter-spacing:.3px;color:var(--muted);padding:14px 8px;border-bottom:1px solid var(--line);white-space:nowrap}
.tp-tb td{padding:14px 8px;border-bottom:1px solid var(--line2);vertical-align:middle;text-align:center;line-height:1.45}
.tp-tb tr:last-child td{border-bottom:none}
.tp-tb td.l,.tp-tb th.l{text-align:left}
.tp-rank{display:inline-flex;align-items:center;justify-content:center;width:30px;height:30px;border-radius:50%;background:var(--accent);color:#1b1200;font-weight:800}
.tp-code{font-size:17px;font-weight:800;color:var(--txt2)}
.tp-ex{display:inline-block;margin-left:6px;padding:1px 7px;border-radius:6px;font-size:11px;font-weight:700;background:var(--tag-gray-bg);color:var(--tag-gray-fg)}
.tp-name{color:var(--muted);font-size:12px;max-width:230px;min-width:190px}
.tp-sec{display:inline-block;margin-top:4px;padding:1px 8px;border-radius:6px;font-size:11px;font-weight:700;background:var(--tag-amber-bg);color:var(--tag-amber-fg)}
.tp-px{font-size:17px;font-weight:800}
.tp-up{color:var(--green)}.tp-dn{color:var(--red)}.tp-mu{color:var(--muted)}
.tp-score{font-size:22px;font-weight:800;color:var(--txt2)}
.tp-grade{display:inline-block;margin-left:6px;padding:1px 7px;border-radius:6px;font-size:12px;font-weight:800;background:var(--tag-green-bg);color:var(--tag-green-fg);vertical-align:middle}
.tp-bar{height:5px;border-radius:3px;background:var(--line);margin:6px auto 0;width:96px;overflow:hidden}
.tp-bar i{display:block;height:100%;background:linear-gradient(90deg,var(--red),var(--accent),var(--green))}
.tp-pill{display:inline-block;min-width:68px;padding:7px 12px;border-radius:10px;font-weight:800;font-size:14px;border:1px solid var(--line);background:var(--card2)}
.tp-pill small{display:block;font-size:11px;font-weight:700;opacity:.85}
.tp-pill.g{background:var(--tag-green-bg);color:var(--tag-green-fg)}
.tp-pill.a{background:var(--tag-amber-bg);color:var(--tag-amber-fg)}
.tp-pill.r{background:var(--tag-red-bg);color:var(--red)}
.tp-auto{display:block;margin-top:3px;font-size:10.5px;color:var(--muted);font-style:italic}
.tp-sc{font-weight:800;font-size:15px;color:var(--txt2)}
.tp-sc small{font-weight:600;color:var(--muted);font-size:11px}
.tp-chip{display:block;margin:4px auto 0;padding:3px 8px;border-radius:6px;font-size:11.5px;max-width:150px;background:var(--card2);border:1px solid var(--line2);text-align:left}
.tp-rec{display:inline-block;padding:7px 14px;border-radius:10px;font-weight:800;font-size:13px;border:1px solid var(--line)}
.tp-rec.green{background:var(--tag-green-bg);color:var(--tag-green-fg)}
.tp-rec.gold,.tp-rec.amber{background:var(--tag-amber-bg);color:var(--tag-amber-fg)}
.tp-rec.red{background:var(--tag-red-bg);color:var(--red)}
.tp-rec.gray{background:var(--tag-gray-bg);color:var(--tag-gray-fg)}
.tp-note{margin-top:5px;font-size:11.5px;color:var(--muted)}
.vp-hero{display:flex;align-items:center;gap:16px;padding:18px 20px;border:1px solid var(--line);border-radius:16px;
  background:linear-gradient(135deg,rgba(245,165,36,.18),rgba(245,165,36,.04) 55%,transparent);margin-bottom:12px}
.vp-ico{flex:none;width:52px;height:52px;border-radius:14px;display:flex;align-items:center;justify-content:center;font-size:26px;
  background:linear-gradient(135deg,#ffb53d,#f08a12);box-shadow:0 4px 14px rgba(240,138,18,.35)}
.vp-title{font-size:22px;font-weight:800;color:var(--txt2);display:flex;align-items:center;flex-wrap:wrap;gap:8px}
.vp-badge{display:inline-block;padding:3px 10px;border-radius:999px;font-size:11.5px;font-weight:800;border:1px solid var(--accent);color:var(--accent);background:rgba(245,165,36,.1)}
.vp-badge.n{color:var(--txt2);border-color:var(--line);background:var(--card2)}
.vp-sub{margin-top:4px;color:var(--muted);font-size:13.5px;line-height:1.5}
.vp-adm{display:flex;align-items:center;flex-wrap:wrap;gap:10px;margin:6px 0 10px;font-size:13px;color:var(--muted)}
.vp-admtag{display:inline-block;padding:5px 12px;border-radius:999px;font-weight:800;font-size:12px;color:var(--accent);border:1px solid var(--accent);background:rgba(245,165,36,.1)}
.vp-foot{display:flex;align-items:center;gap:10px;margin-top:4px;color:var(--muted);font-size:13px}
.vp-disc{margin-top:2px;color:var(--muted);font-size:11.5px;opacity:.85}
</style>
"""


def _ok(v) -> bool:
    return v is not None and not (isinstance(v, float) and np.isnan(v))


def _e(x) -> str:
    return _html.escape(str(x))


def _px(v) -> str:
    return f"{float(v):,.2f}"


def _vol(v) -> str:
    v = float(v)
    return f"{v / 1e6:.2f}M" if v >= 1e6 else f"{v / 1e3:.0f}K" if v >= 1e3 else f"{v:.0f}"


def _auto(flag: bool) -> str:
    return '<span class="tp-auto">tự động</span>' if flag else ""


def _bar(pct) -> str:
    return f'<div class="tp-bar"><i style="width:{max(0, min(100, float(pct))):.0f}%"></i></div>'


def _row_html(i: int, r) -> str:
    nd = r.get("_nodata")
    if isinstance(nd, (bool, np.bool_)) and nd:
        return (f'<tr><td><span class="tp-rank">{i}</span></td><td class="l"><span class="tp-code">{_e(r["Mã"])}</span>'
                f'<div class="tp-name">Chưa có dữ liệu giá của mã này</div></td>' + '<td></td>' * 12 + '</tr>')
    up = (r["Chg"] or 0) >= 0 if pd.notna(r["Chg"]) else True
    cls = "tp-up" if up else "tp-dn"
    ex = f'<span class="tp-ex">{_e(r["Sàn"])}</span>' if r["Sàn"] else ""
    sec = f'<div><span class="tp-sec">{_e(r["Ngành"])}</span></div>' if r["Ngành"] else ""
    chg = (f'<div class="{cls}" style="font-weight:700">{r["Chg"]:+.2f}</div><div class="{cls}" style="font-size:12px">{r["Chg %"]:+.2f}%</div>'
           if pd.notna(r["Chg"]) else '<span class="tp-mu">—</span>')
    tot = (f'<span class="tp-score">{r["Tổng điểm"]:.0f}</span><span class="tp-grade">{_e(r["Hạng"])}</span>{_bar(r["Tổng điểm"])}'
           if _ok(r["Tổng điểm"]) else '<span class="tp-mu">—</span>')
    b = r["Điểm mua"]
    if isinstance(b, tuple):
        bt = _px(b[0]) if abs(b[0] - b[1]) < 1e-9 else f"{_px(b[0])} – {_px(b[1])}"
        buy = f'<span class="tp-pill g">● {bt}</span>{_auto(r["buy_auto"])}'
    else:
        buy = '<span class="tp-mu">—</span>'
    if pd.notna(r["Lãi %"]):
        pc = "g" if r["Lãi %"] >= 0 else "r"
        profit = f'<span class="tp-pill {pc}">{r["Lãi %"]:+.2f}%<small>{r["Lãi"]:+.2f}</small></span>'
    else:
        profit = '<span class="tp-mu">—</span>'
    def lvl(val, auto, tone):
        if not _ok(val) or not val:
            return '<span class="tp-mu">—</span>'
        d = (val / r["Giá"] - 1) * 100
        return f'<span class="tp-pill {tone}">{_px(val)}<small>{d:+.1f}%</small></span>{_auto(auto)}'
    sell = (f'<span class="tp-pill">≥ {_px(r["Điểm bán"])}</span>{_auto(r["sell_auto"])}' if _ok(r["Điểm bán"]) and r["Điểm bán"] else '<span class="tp-mu">—</span>')
    if _ok(r["FA"]):
        fa = f'<span class="tp-sc">{int(r["FA"])}<small>/100</small></span>{_bar(r["FA"])}' + "".join(f'<span class="tp-chip">{_e(t)}</span>' for t in r["FA tags"][:3])
    else:
        fa = '<span class="tp-mu">Chưa đủ số liệu</span>'
    if _ok(r["TA"]):
        rsi = f'<div class="tp-mu" style="font-size:11.5px">RSI {r["RSI"]:.1f}</div>' if _ok(r["RSI"]) else ""
        ta = f'<span class="tp-sc">{int(r["TA"])}<small>/100</small></span>{rsi}{_bar(r["TA"])}' + "".join(f'<span class="tp-chip">{_e(t)}</span>' for t in r["TA tags"][:2])
    else:
        ta = '<span class="tp-mu">Chưa đủ số liệu</span>'
    label, tone, note = r["Khuyến nghị"]
    ng = r["Ngoại"]
    foreign = (f'<div class="tp-note">{"Khối ngoại gom ròng" if ng > 0 else "Khối ngoại bán ròng"}</div>'
               if ng is not None and pd.notna(ng) and abs(ng) > 0 else "")
    rec = f'<span class="tp-rec {tone}">{_e(label)}</span><div class="tp-note">{_e(note)}</div>{foreign}'
    return (f'<tr><td><span class="tp-rank">{i}</span></td>'
            f'<td class="l"><span class="tp-code">{_e(r["Mã"])}</span>{ex}<div class="tp-name">{_e(r["Tên"])}</div>{sec}</td>'
            f'<td><span class="tp-px {cls}">{_px(r["Giá"])}</span></td><td>{chg}</td><td style="font-weight:700">{_vol(r["KL"])}</td>'
            f'<td>{tot}</td><td>{buy}</td><td>{profit}</td><td>{lvl(r["Target"], r["target_auto"], "a")}</td>'
            f'<td>{lvl(r["Cutloss"], r["stop_auto"], "r")}</td><td>{sell}</td><td>{fa}</td><td>{ta}</td><td>{rec}</td></tr>')


def table_html(v: pd.DataFrame) -> str:
    head = ["HẠNG", "MÃ CK", "GIÁ KHỚP", "+/-", "KHỐI LƯỢNG", "TỔNG ĐIỂM", "ĐIỂM MUA", "LỢI NHUẬN", "TARGET", "CUTLOSS", "ĐIỂM BÁN",
            "ĐIỂM CƠ BẢN (FA)", "ĐIỂM KỸ THUẬT (TA)", "KHUYẾN NGHỊ"]
    th = "".join(f'<th class="{"l" if h == "MÃ CK" else ""}">{h}</th>' for h in head)
    body = "".join(_row_html(i + 1, r) for i, (_, r) in enumerate(v.iterrows()))
    return f'<div class="tp-wrap"><table class="tp-tb"><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table></div>'


# ------------------------------------------------------------------ TRANG
_FIELDS = {"vp_code": "Mã", "vp_buy": "Điểm mua", "vp_target": "Target", "vp_cut": "Cutloss", "vp_sell": "Điểm bán"}


def _admin_password() -> str:
    pw = os.environ.get("VIP_ADMIN_PASSWORD", "")
    if not pw:
        try:
            pw = str(st.secrets.get("VIP_ADMIN_PASSWORD", "") or "")
        except Exception:  # noqa: BLE001  (chưa có file secrets)
            pw = ""
    return pw


def _unlock_cb() -> None:
    ss = st.session_state
    pw = _admin_password()
    typed = str(ss.get("vp_pw", "") or "")
    if pw and hmac.compare_digest(typed.encode(), pw.encode()):
        ss["vp_admin"] = True
        ss["vp_msg"] = ("ok", "Đã mở khóa Admin.")
    else:
        ss["vp_msg"] = ("err", "Mật khẩu chưa đúng.")
    ss["vp_pw"] = ""


def _lock_cb() -> None:
    st.session_state["vp_admin"] = False


def _clear_form() -> None:
    for k in _FIELDS:
        st.session_state[k] = ""


def _save_cb(available: set) -> None:
    ss = st.session_state
    if not ss.get("vp_admin"):
        return
    row = {col: str(ss.get(k, "") or "").strip() for k, col in _FIELDS.items()}
    row["Mã"] = row["Mã"].upper()
    if not re.fullmatch(r"[A-Z0-9]{2,10}", row["Mã"]):
        ss["vp_msg"] = ("err", "Nhập mã cổ phiếu hợp lệ vào ô Mã CK.")
        return
    if row["Mã"] not in available:
        ss["vp_msg"] = ("err", f"{row['Mã']} chưa có trong dữ liệu của app nên chưa thêm được.")
        return
    for col in ("Điểm mua", "Target", "Cutloss", "Điểm bán"):
        if row[col] and not _nums(row[col]):
            ss["vp_msg"] = ("err", f"Ô {col} cần là số, ví dụ 35.5 hoặc 35.5 - 36.0.")
            return
    t, c = parse_price(row["Target"]), parse_price(row["Cutloss"])
    if t and c and t <= c:
        ss["vp_msg"] = ("err", "Target phải cao hơn Cutloss.")
        return
    err = save(upsert(load(), row))
    ss["vp_msg"] = ("ok", f"Đã lưu {row['Mã']}" + (f" (chưa ghi được vào file: {err})" if err else ""))
    _clear_form()


def _add_cb(available: set) -> None:
    """Thêm nhanh nhiều mã (để trống các mốc: hệ thống tự điền); mã đã có thì giữ nguyên mốc đã nhập."""
    ss = st.session_state
    if not ss.get("vp_admin"):
        return
    codes = [c for c in re.split(r"[\s,;]+", str(ss.get("vp_add", "")).upper()) if c]
    if not codes:
        ss["vp_msg"] = ("err", "Nhập ít nhất một mã cổ phiếu, ví dụ HPG, IDC, MSH.")
        return
    d = load()
    have = set(d["Mã"])
    ok = [c for c in dict.fromkeys(codes) if c in available and c not in have]
    dup = [c for c in dict.fromkeys(codes) if c in have]
    bad = [c for c in dict.fromkeys(codes) if c not in available]
    if ok:
        d = _clean(pd.concat([d, pd.DataFrame([{"Mã": c, "Điểm mua": "", "Target": "", "Cutloss": "", "Điểm bán": ""} for c in ok])], ignore_index=True))
        err = save(d)
    else:
        err = ""
    parts = ([f"Đã thêm: {', '.join(ok)}"] if ok else []) + ([f"Đã có sẵn: {', '.join(dup)}"] if dup else []) \
        + ([f"Không có trong dữ liệu: {', '.join(bad)}"] if bad else []) + ([f"chưa ghi được vào file: {err}"] if err else [])
    ss["vp_msg"] = ("ok" if ok else "err", " · ".join(parts))
    ss["vp_add"] = ""


def _edit_cb(code: str) -> None:
    if not st.session_state.get("vp_admin"):
        return
    hit = load()
    hit = hit[hit["Mã"] == code]
    if hit.empty:
        return
    for k, col in _FIELDS.items():
        st.session_state[k] = str(hit.iloc[0][col])


def _delete_cb(code: str) -> None:
    if not st.session_state.get("vp_admin"):
        return
    err = remove(code)
    st.session_state["vp_msg"] = ("ok" if not err else "err", f"Đã xóa {code}" if not err else f"Chưa xóa được {code}: {err}")


def _hero_html(n: int) -> str:
    return (f'<div class="vp-hero"><div class="vp-ico">🔥</div><div><div class="vp-title">KHUYẾN NGHỊ KHÁCH HÀNG '
            f'<span class="vp-badge">VIP RECOMMENDATIONS</span><span class="vp-badge n">{n} mã</span></div>'
            f'<div class="vp-sub">Danh mục cổ phiếu chọn lọc bởi Admin • Tự động tính điểm FA, TA và trạng thái khuyến nghị theo dữ liệu cuối phiên</div></div></div>')


def _admin_panel(available: set) -> None:
    ss = st.session_state
    for k in _FIELDS:
        ss.setdefault(k, "")
    st.markdown('<div class="vp-adm"><span class="vp-admtag">⚡ BẢNG ĐIỀN ĐIỂM MUA - BÁN - TARGET (ADMIN)</span>'
                '<span>Điền các mức giá bên dưới rồi bấm Lưu, hoặc chọn mã dưới bảng và bấm Sửa. Ô để trống sẽ tự điền theo hệ thống.</span></div>',
                unsafe_allow_html=True)
    c = st.columns([1.1, 1.5, 1.3, 1, 1, 1.3])
    c[0].text_input("Mã CK *", key="vp_code", placeholder="VD: IDC, HPG...")
    c[1].text_input("Điểm Mua", key="vp_buy", placeholder="VD: 35.5 - 36.0")
    c[2].text_input("Lợi Nhuận", key="vp_profit", placeholder="Tự tính theo giá khớp", disabled=True)
    c[3].text_input("Target", key="vp_target", placeholder="VD: 42.0")
    c[4].text_input("Cutloss", key="vp_cut", placeholder="VD: 34.0")
    c[5].text_input("Điểm Bán", key="vp_sell", placeholder="VD: ≥ 42.0")
    b1, b2, _ = st.columns([1.2, 0.5, 6])
    b1.button("✓ Lưu", type="primary", on_click=_save_cb, args=(available,), use_container_width=True)
    b2.button("↺", on_click=_clear_form, help="Xóa trắng form", use_container_width=True)
    q1, q2, q3, _ = st.columns([3, 1.6, 1, 3])
    q1.text_input("Nhập mã CP", key="vp_add", placeholder="Nhập mã CP (VD: HPG, IDC, MSH...)", label_visibility="collapsed")
    q2.button("＋ Thêm mã vào VIP", on_click=_add_cb, args=(available,), use_container_width=True)
    q3.button("🔓 Khóa", on_click=_lock_cb, use_container_width=True, help="Thoát chế độ Admin")


def render(res: pd.DataFrame, frames_d: pd.DataFrame, wb: pd.DataFrame, fund_map: dict, meta_fn, ctx_fn, on_chart, on_filter=None) -> None:
    """res: res_df; frames_d: frames["D"]; wb: bảng Chờ mua; fund_map: {mã: {P/E, ROE, P/B…}}; meta_fn(code)->(tên, ngành);
    ctx_fn(code)->ngữ cảnh "Tóm tắt nhanh" của app; on_chart(code): mở biểu đồ; on_filter(): mở Bộ lọc cổ phiếu."""
    ss = st.session_state
    admin = bool(ss.get("vp_admin"))
    available = set(res["Mã"].astype(str).str.upper())
    plans = load()
    st.markdown(CSS + _hero_html(len(plans)), unsafe_allow_html=True)

    if admin:
        _admin_panel(available)
    else:
        with st.expander("🔒 Admin"):
            if _admin_password():
                st.text_input("Mật khẩu Admin", type="password", key="vp_pw", on_change=_unlock_cb)
            else:
                st.caption("Chưa đặt mật khẩu Admin. Thêm VIP_ADMIN_PASSWORD vào Secrets (hoặc biến môi trường) để mở khóa phần chỉnh sửa.")
    msg = ss.pop("vp_msg", None)
    if msg:
        (st.success if msg[0] == "ok" else st.error)(msg[1])

    plans = load()
    if plans.empty:
        st.info("Danh mục khuyến nghị đang trống." + (" Nhập mã ở phần Admin phía trên rồi bấm Lưu." if admin else ""))
    else:
        v = build_view(plans, res, frames_d, fund_map, wb, meta_fn, ctx_fn)
        st.markdown(table_html(v), unsafe_allow_html=True)
        codes = list(v["Mã"])
        cols = [1.4, 1, 1, 1] if admin else [1.4, 1]
        row = st.columns(cols + [4])
        pick = row[0].selectbox("Mã cần thao tác", codes, key="vp_pick", label_visibility="collapsed")
        if row[1].button("📈 Đồ thị", use_container_width=True):
            on_chart(pick)                      # on_chart gọi NAV.goto -> st.rerun, nên không dùng on_click
        if admin:
            row[2].button("✏️ Sửa", on_click=_edit_cb, args=(pick,), use_container_width=True)
            row[3].button("🗑 Xóa", on_click=_delete_cb, args=(pick,), use_container_width=True)

    f1, f2 = st.columns([5, 1.6])
    f1.markdown('<div class="vp-foot">🛡️ Danh mục Khuyến nghị độc quyền dành cho khách hàng VIP • Cập nhật giá &amp; chỉ báo tự động</div>'
                '<div class="vp-disc">Tổng điểm = Score của app × 10 (hạng A ≥ 75, B ≥ 60, C ≥ 40). FA chấm từ ROE, P/E, P/B; TA chấm từ MA20 và RSI. '
                'Chỉ phục vụ nghiên cứu, không phải khuyến nghị đầu tư.</div>', unsafe_allow_html=True)
    if on_filter and f2.button("🔽 Mở trong Bộ lọc cổ phiếu", use_container_width=True):
        on_filter()
