"""Khuyến nghị khách hàng (VIP): danh mục cổ phiếu do Admin chọn, hiển thị cho khách kèm Điểm mua, Lợi nhuận, Target, Cutloss,
Điểm bán, điểm FA / TA và khuyến nghị. Khác mục "Cổ phiếu của tôi" (danh mục riêng của người dùng).

Ba nhóm (vòng đời một khuyến nghị): Chờ mua -> Đang nắm giữ -> Đã đóng. Admin chọn "Trạng thái" khi lưu (hoặc dùng nút ▶ Đã mua / ■ Đóng lệnh).
- Chờ mua: chưa vào lệnh; Điểm mua là vùng canh mua (Admin nhập, hoặc hệ thống tự điền), chưa tính lợi nhuận.
- Đang nắm giữ: bắt buộc có Điểm mua (giá vào lệnh); tính lợi nhuận, theo dõi cutloss / điểm bán.
- Đã đóng: có Giá đóng và Ngày đóng; hiện kết quả (% lãi / lỗ) và số ngày kể từ ngày khuyến nghị.
Mỗi mã có Khung thời gian (Trung hạn / Dài hạn), Ngày khuyến nghị và Luận điểm (một dòng giải thích vì sao khuyến nghị).
Nhóm Đang nắm giữ có form riêng: Hạng | Lệnh | Mã CP | Vùng mua KN | Giá khớp lệnh | Giá hiện tại | Khối lượng | Lãi/Lỗ dự kiến | FA | TA | Tổng điểm |
Tín hiệu hiện tại | Khuyến nghị; hai cột CSV mới "Giá khớp" (giá vào lệnh thật) và "Khối lượng" (số cổ phiếu đang giữ) dùng để tính lãi/lỗ bằng đồng.
Bảng nhóm Chờ mua trình bày theo form riêng (màu và ô Khuyến nghị như các nhóm khác): Hạng | Lệnh | Mã CP + ngày KN | Vùng mua KN | Giá hiện tại | Cách vùng mua | Tỷ trọng |
Ví dụ | Cắt lỗ | Giá Mục Tiêu 1 | Giá Mục Tiêu 2 | FA | TA | Tổng điểm | Khuyến nghị. Cột Tỷ trọng và Ví dụ lấy từ hai cột mới của file CSV:
"Tỷ trọng %" (vd 30) và "Dự định mua" (số cổ phiếu, vd 1000); câu Ví dụ tự ghép: "Dự định mua 1000 CP. Tỷ trọng 30% = 300 CP".

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
- Lợi nhuận = giá hiện tại so với Điểm mua do Admin nhập (giữa vùng nếu là vùng); Điểm mua tự động thì để "—" vì chưa phải giá vào lệnh.
  Target / Cutloss tính % so với giá hiện tại.

Cách chấm điểm (sửa các hằng số / hàm fa_score, ta_score nếu muốn đổi):
- Tổng điểm = Score sẵn có của app (thang 0-10) × 10; hạng A ≥ 75, B ≥ 60, C ≥ 40, còn lại D.
- FA (0-100) chấm từ ROE, P/E, P/B (data/fundamentals.csv); chỉ tính các chỉ số có số liệu, cần ít nhất 2 chỉ số.
- TA (0-100) chấm từ MA20, MA50, MA200, RSI(14) và khối lượng khung Ngày (chi tiết ở docstring của ta_score).
- Dòng "Khối ngoại gom / bán ròng" chỉ hiện khi có data/foreign_flow.csv (tổng 5 phiên gần nhất).
Chỉ phục vụ nghiên cứu, không phải khuyến nghị đầu tư.
"""
from __future__ import annotations

import hmac
import html as _html
import io
import os
import re
import unicodedata
from datetime import date, datetime

import numpy as np
import pandas as pd
import streamlit as st

import action_summary as AS

PATH = "data/khuyen_nghi_khach_hang.csv"
FOREIGN_PATH = "data/foreign_flow.csv"
STATUSES = ("Chờ mua", "Đang nắm giữ", "Đã đóng")
FRAMES = ("Trung hạn", "Dài hạn")
COLS = ["Mã", "Điểm mua", "Target", "Cutloss", "Điểm bán", "Trạng thái", "Khung thời gian", "Ngày khuyến nghị", "Luận điểm", "Giá đóng", "Ngày đóng", "Tỷ trọng %", "Dự định mua", "Giá khớp", "Khối lượng"]
_ERR = ""                                                    # thông báo lỗi đọc file gần nhất ("" = tốt)
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


def _norm(x) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", str(x)).replace("\ufeff", "")).strip().casefold()


_COLS_MAP = {_norm(c): c for c in COLS}


def _today() -> date:
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date()
    except Exception:  # noqa: BLE001
        return date.today()


def parse_date(text) -> date | None:
    t = str(text or "").strip()
    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d", "%d-%m-%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(t, fmt).date()
        except ValueError:
            continue
    return None


def fmt_date(d: date | None) -> str:
    return d.strftime("%d/%m/%Y") if d else ""


def _clean(d: pd.DataFrame) -> pd.DataFrame:
    d = d.copy()
    for c in COLS:
        if c not in d.columns:
            d[c] = ""
        d[c] = d[c].fillna("").astype(str).str.strip()
    d["Mã"] = d["Mã"].str.upper()
    d = d[d["Mã"].str.fullmatch(r"[A-Z0-9]{2,10}")]
    d["Trạng thái"] = d["Trạng thái"].where(d["Trạng thái"].isin(STATUSES), "Chờ mua")        # file cũ chưa có cột này -> Chờ mua
    d["Khung thời gian"] = d["Khung thời gian"].where(d["Khung thời gian"].isin(FRAMES), "Trung hạn")
    for c in ("Ngày khuyến nghị", "Ngày đóng"):
        d[c] = d[c].map(lambda x: fmt_date(parse_date(x)) if parse_date(x) else x)
    return d[COLS].drop_duplicates("Mã", keep="last").reset_index(drop=True)


def load(path: str = PATH) -> pd.DataFrame:
    """Đọc danh mục; tự nhận dấu phân cách (, ; Tab), mã hóa và tên cột lệch dấu / hoa thường. Lỗi thì trả bảng rỗng và ghi _ERR."""
    global _ERR
    _ERR = ""
    if os.path.exists(path):
        try:
            raw = open(path, "rb").read()
            text = next((raw.decode(e) for e in ("utf-8-sig", "utf-16", "cp1258", "cp1252") if _can(raw, e)), raw.decode("utf-8", errors="replace"))
            first = next((ln for ln in text.splitlines() if ln.strip()), "")
            sep = max((",", ";", "\t"), key=first.count)
            d = pd.read_csv(io.StringIO(text), sep=sep, dtype=str, keep_default_na=False)
            d.columns = [_COLS_MAP.get(_norm(c), str(c).strip()) for c in d.columns]
            if "Mã" not in d.columns:
                _ERR = f"thiếu cột Mã; các cột tìm thấy: {', '.join(map(str, d.columns))}"
            else:
                return _clean(d)
        except Exception as e:  # noqa: BLE001
            _ERR = f"{type(e).__name__}: {e}"
    return _clean(pd.DataFrame(columns=COLS))


def _can(raw: bytes, enc: str) -> bool:
    try:
        raw.decode(enc)
        return True
    except UnicodeError:
        return False


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


def ta_score(g: pd.DataFrame) -> tuple[int | None, list[str]]:
    """Điểm kỹ thuật 0-100 chấm trên khung Ngày từ MA20, MA50, MA200, RSI(14) và khối lượng. g = các phiên gần nhất của một mã (cần ≥ 26 phiên
    để chấm khối lượng), có cột Giá đóng cửa, Khối lượng khớp lệnh, MA20, MA50, MA200, RSI.

    Thang điểm (tối đa 100):
      Xu hướng MA (60):  MA20 20 (giá trên MA20 12, giá cách MA20 ≤ 8% thì +3, MA20 dốc lên so với 5 phiên trước +5)
                         MA50 15 (giá trên MA50 10, MA50 dốc lên +5) · MA200 10 (giá trên MA200)
                         Thứ tự MA 15 (MA20 > MA50 > MA200: 15; MA20 > MA50 nhưng MA50 chưa vượt MA200: 8; MA50 > MA200 nhưng MA20 chưa trên MA50: 5)
      RSI(14) (20):      50-62: 20 · 45-50 hoặc 62-70: 14 · 40-45 hoặc 70-78: 7 · còn lại 2
      Khối lượng (20):   thanh khoản 5 phiên / TB 20 phiên trước đó (≥ 1.2: 10, ≥ 0.9: 7, ≥ 0.7: 4, còn lại 1)
                         + tỷ trọng khối lượng ở các phiên giá tăng trong 10 phiên (≥ 60%: 10, ≥ 50%: 7, ≥ 40%: 4, còn lại 1)
    Thành phần nào thiếu dữ liệu (ví dụ mã mới lên sàn chưa đủ 200 phiên cho MA200) thì bỏ khỏi cả điểm đạt lẫn điểm tối đa rồi quy về thang 100;
    cần tối thiểu MA20 và RSI. Trả (None, []) nếu không đủ."""
    if g is None or len(g) < 5:
        return None, []
    last = g.iloc[-1]
    close, ma20, ma50, ma200, rsi = (_f(last.get(c)) for c in ("Giá đóng cửa", "MA20", "MA50", "MA200", "RSI"))
    if close is None or ma20 is None or ma20 <= 0 or rsi is None:
        return None, []

    def prev(col: str, k: int = 5) -> float | None:
        return _f(g[col].iat[-1 - k]) if col in g.columns and len(g) > k else None

    got = mx = 0.0
    tags: list[str] = []

    # --- MA20 (20)
    gap = (close / ma20 - 1) * 100
    p = 0
    if close > ma20:
        p += 12
        p += 3 if gap <= 8 else 0
        tags.append(f"Trên MA20 ({gap:+.2f}%)" if gap <= 8 else f"Xa MA20 ({gap:+.1f}%), dễ điều chỉnh")
    else:
        tags.append(f"Dưới MA20 ({gap:+.2f}%)")
    m20p = prev("MA20")
    p += 5 if (m20p is not None and ma20 > m20p) else 0
    got, mx = got + p, mx + 20

    # --- MA50 (15) và MA200 (10)
    if ma50 is not None:
        m50p = prev("MA50")
        got += (10 if close > ma50 else 0) + (5 if (m50p is not None and ma50 > m50p) else 0)
        mx += 15
    if ma200 is not None:
        got += 10 if close > ma200 else 0
        mx += 10
    if ma50 is not None and ma200 is not None:
        tags.append("Trên MA50 và MA200" if close > max(ma50, ma200) else "Dưới MA50 và MA200" if close < min(ma50, ma200)
                    else "Trên MA50, dưới MA200" if close > ma50 else "Trên MA200, dưới MA50")
        got += 15 if ma20 > ma50 > ma200 else 8 if ma20 > ma50 else 5 if ma50 > ma200 else 0
        mx += 15
    elif ma50 is not None:
        tags.append("Trên MA50" if close > ma50 else "Dưới MA50")
        got += 8 if ma20 > ma50 else 0
        mx += 8

    # --- RSI (20)
    got += 20 if 50 <= rsi <= 62 else 14 if (45 <= rsi < 50 or 62 < rsi <= 70) else 7 if (40 <= rsi < 45 or 70 < rsi <= 78) else 2
    mx += 20

    # --- Khối lượng (20)
    vcol = "Khối lượng khớp lệnh"
    if vcol in g.columns and "Giá đóng cửa" in g.columns and len(g) >= 16:
        v = pd.to_numeric(g[vcol], errors="coerce")
        base = v.iloc[:-5].tail(20)
        if v.tail(5).notna().all() and base.notna().sum() >= 10 and base.mean() > 0:
            r = float(v.tail(5).mean() / base.mean())
            c10 = pd.to_numeric(g["Giá đóng cửa"], errors="coerce").tail(11)
            v10 = v.tail(10).reset_index(drop=True)
            up = (c10.diff().tail(10).reset_index(drop=True) > 0)
            share = float(v10[up].sum() / v10.sum()) if v10.sum() > 0 else 0.5
            got += (10 if r >= 1.2 else 7 if r >= 0.9 else 4 if r >= 0.7 else 1) + (10 if share >= 0.6 else 7 if share >= 0.5 else 4 if share >= 0.4 else 1)
            mx += 20
            tags.append(f"KL cạn ({r:.1f}x TB20)" if r < 0.7 else "Lực bán áp đảo" if share < 0.4
                        else f"Dòng tiền vào (KL {r:.1f}x TB20)" if (r >= 1.0 and share >= 0.55) else f"KL {r:.1f}x TB20")
    if ma200 is None:
        tags.append("Chưa đủ dữ liệu MA200")
    return (int(round(got / mx * 100)), tags) if mx >= 40 else (None, [])


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


def recommend(price, buy, stop, sell, wbreason: str, status: str = "Chờ mua") -> tuple[str, str, str]:
    """(nhãn, màu, ghi chú) theo trạng thái của khuyến nghị. Đang nắm giữ: Điểm mua là giá vào lệnh (CẮT LỖ / CHỐT LỜI / HẠ TỶ TRỌNG / NẮM GIỮ).
    Chờ mua: Điểm mua là vùng canh mua (VÙNG MUA / CHỜ VỀ VÙNG MUA / DƯỚI VÙNG MUA / HỦY KỊCH BẢN / CHƯA NÊN MUA)."""
    reason = str(wbreason or "")
    if status == "Đang nắm giữ":
        if stop and price <= stop:
            return "CẮT LỖ", "red", f"Giá thủng cutloss {stop:,.2f}"
        if sell and price >= sell:
            return "CHỐT LỜI", "amber", f"Giá đạt điểm bán {sell:,.2f}"
        if reason.startswith("BÁN"):
            return "HẠ TỶ TRỌNG", "red", "Hệ thống đang báo bán"
        if reason.startswith("CHỐT LỜI"):
            return "CHỐT BỚT", "amber", "Hệ thống đang báo chốt lời"
        return "NẮM GIỮ", "gold", "Giá còn trên cutloss, chưa tới điểm bán"
    if stop and price <= stop:
        return "HỦY KỊCH BẢN", "red", f"Giá thủng {stop:,.2f} khi chưa vào lệnh"
    if sell and price >= sell:
        return "ĐÃ CHẠY QUÁ", "gray", "Giá đã tới điểm bán khi chưa vào lệnh"
    if reason.startswith("BÁN"):
        return "CHƯA NÊN MUA", "red", "Hệ thống đang báo bán"
    if not buy:
        return "THEO DÕI", "gray", "Chưa có vùng mua"
    if price < buy[0] * BELOW_BUY:
        return "DƯỚI VÙNG MUA", "gray", "Giá đã lệch xuống dưới vùng mua"
    if price <= buy[1] * NEAR_BUY:
        return "VÙNG MUA", "green", "Giá đang trong vùng mua"
    return "CHỜ VỀ VÙNG MUA", "gray", f"Giá cao hơn vùng mua {(price / buy[1] - 1) * 100:.1f}%"


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
        g = frames_d[frames_d["Mã"] == code].sort_values("Ngày").tail(30)
        if g.empty:
            rows.append({"Mã": code, "_nodata": True})
            continue
        close = float(g["Giá đóng cửa"].iat[-1])
        prev = float(g["Giá đóng cửa"].iat[-2]) if len(g) > 1 else np.nan
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
        status = (p.get("Trạng thái", "Chờ mua") or "Chờ mua")
        fill, qty = parse_price(p.get("Giá khớp", "")), parse_price(p.get("Khối lượng", ""))
        mid = (buy[0] + buy[1]) / 2 if (status == "Đang nắm giữ" and buy and not buy_auto) else None
        entry = (fill or mid) if status == "Đang nắm giữ" else None      # chỉ tính lợi nhuận khi đã vào lệnh; ưu tiên Giá khớp, không có thì giữa vùng Điểm mua do Admin nhập
        fd = fund_map.get(code, {}) or {}
        fa, fa_tags = fa_score(fd.get("P/E"), fd.get("ROE"), fd.get("P/B"))
        ta, ta_tags = ta_score(g)
        sc = score.get(code)
        total = None if sc is None or not np.isfinite(sc) else float(min(100.0, max(0.0, sc * 10)))
        wbreason = wbrow.get("Lý do", "") if isinstance(wbrow.get("Lý do", ""), str) else ""
        rec = recommend(close, buy, stop, sell, wbreason, status)
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
            "Trạng thái": status, "Khung": p.get("Khung thời gian", "Trung hạn"), "Ngày KN": p.get("Ngày khuyến nghị", ""), "Luận điểm": p.get("Luận điểm", ""),
            "Tỷ trọng": p.get("Tỷ trọng %", ""), "Dự định": p.get("Dự định mua", ""),
            "Giá khớp": fill, "KL nắm": qty, "Tín hiệu": wbrow.get("Trạng thái", "") if isinstance(wbrow.get("Trạng thái", ""), str) else "",
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
.tp-meta{margin-top:5px}
.tp-chip2{display:inline-block;margin:2px 4px 0 0;padding:1px 8px;border-radius:6px;font-size:11px;background:var(--card2);border:1px solid var(--line2);color:var(--muted)}
.tp-tb tr.hasth td{border-bottom:none}
.tp-tb tr.th td{padding:0 12px 14px;text-align:left;color:var(--muted);font-size:12.5px;line-height:1.5}
.tp-tb tr.th b{color:var(--txt)}
/* Bảng Chờ mua: tông xanh lá đậm + mint (phong cách app VPBankS). Chỉ đổi biến màu trong khung .vpb nên các bảng khác giữ nguyên */
.tp-wrap.vpb{--card:#0f2b27;--card2:#173a34;--line:#21504a;--line2:#1a403a;--txt:#f1f8f5;--txt2:#fff;--muted:#80ab9e;--accent:#3fd68f;--green:#3fd68f;--red:#ff6168;
  --tag-green-bg:#14463a;--tag-green-fg:#3fd68f;--tag-amber-bg:#14463a;--tag-amber-fg:#3fd68f;--tag-red-bg:#3a2024;--tag-gray-bg:#1b3d37;--tag-gray-fg:#9cc7ba;
  background:linear-gradient(135deg,#0d2622 0%,#113029 100%);border:1px solid #21504a;border-radius:18px;
  font-family:Inter,Roboto,"Segoe UI",system-ui,-apple-system,"Helvetica Neue",Arial,sans-serif;font-variant-numeric:tabular-nums}
.vpb .tp-tb{table-layout:fixed;width:100%;min-width:1660px;font-size:13px;font-family:inherit}
.vpb .tp-tb th{color:var(--muted);font-weight:700;font-size:11px;letter-spacing:.5px;text-transform:uppercase;padding:15px 4px;border-bottom:1px solid var(--line);line-height:1.3}
.vpb .tp-tb td{padding:15px 6px;border-bottom:1px solid var(--line2);overflow:hidden}
.vpb .tp-tb tbody tr:hover td{background:rgba(63,214,143,.045)}
.vpb .tp-tb tr.th td{padding:0 12px 14px;overflow:visible;background:none!important}
/* Cột Hạng → Giá Mục Tiêu 2: chữ phẳng, đậm vừa, số căn đều */
.vpb .tp-tb td.pl{font-weight:600;font-size:13.5px;color:#fff}
.vpb .tp-tb td.pl:first-child{color:var(--muted);font-weight:500}
.vpb .cmd-t{font-size:13px;font-weight:800;letter-spacing:.4px;color:#ffd966;white-space:nowrap}
.vpb .cmd-t.green{color:#4fd18b}.vpb .cmd-t.red{color:#ff5a4d}.vpb .cmd-t.gray{color:#b9d3d7}
.vpb .pl-code{font-size:15px;font-weight:800;letter-spacing:.4px;color:#fff}
.vpb .pl-date{font-size:11px;font-weight:500;color:var(--muted);margin-top:3px}
.vpb .tp-tb td.pl.ex{text-align:left;font-size:12px;line-height:1.5;font-weight:500;color:#b7d3c8;white-space:normal}
.vpb .tp-tb td.pl.rt{text-align:right;padding-right:16px}
.vpb .tp-tb td.pl.key{font-size:15.5px;font-weight:700;letter-spacing:.2px}
.vpb .lv{font-size:15.5px;font-weight:700;line-height:1.4;letter-spacing:.2px}.vpb .lv+.lv{font-size:12px;font-weight:600;letter-spacing:0}
.vpb .lv.dn{color:#ff5a4d}.vpb .lv.up{color:#4fd18b}.vpb .lv.fl{color:#ffb02e}
.vpb .st{color:var(--muted);font-weight:500;margin-left:2px}
.vpb .tp-tb td.pl.sig{font-size:12px;font-weight:700;letter-spacing:.3px;color:#cfe5dc;white-space:normal}
.vpb .tp-mu{color:var(--muted)}
/* FA / TA / Tổng điểm: điểm + thanh + nhãn hiển thị sẵn (để chụp gửi khách), nhãn viết gọn dạng dòng chữ */
.vpb .tp-sc{font-size:17px;font-weight:700;color:#fff}.vpb .tp-sc small{font-size:11px;font-weight:500;color:var(--muted)}
.vpb .tp-score{font-size:20px;font-weight:700}
.vpb .tp-grade{background:#14463a;color:#3fd68f;border-radius:6px}
.vpb .tp-bar{background:#21504a;width:70%;margin:6px auto 8px}
.vpb .tp-chip{display:block;max-width:none;width:auto;margin:2px 0 0 6%;padding:0;border:0;background:none;text-align:left;
  font-size:10.5px;line-height:1.4;color:#b7d3c8;white-space:nowrap}
.vpb .tp-chip:before{content:"•";color:#3fd68f;margin-right:6px}
/* Khuyến nghị: chữ đậm, không khối màu để không tranh mắt với cột Lệnh */
.vpb .tp-rec{display:block;padding:0;border:0;background:none;border-radius:0;font-size:12px;font-weight:800;letter-spacing:.4px;line-height:1.35;color:#e8f3ef}
.vpb .tp-rec.green{color:#3fd68f}.vpb .tp-rec.red{color:#ff6168}.vpb .tp-rec.gray{color:#9cc7ba}
.vpb .tp-note{font-size:11px;line-height:1.45;color:var(--muted);margin-top:4px}
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


def _row_html(i: int, r, mode: str = "hold") -> str:
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
    if mode == "wait":
        profit = '<span class="tp-mu">—</span>'
        if isinstance(b, tuple):
            if r["Giá"] > b[1]:
                profit = f'<span class="tp-pill">{(r["Giá"] / b[1] - 1) * 100:+.1f}%<small>cao hơn vùng</small></span>'
            elif r["Giá"] < b[0]:
                profit = f'<span class="tp-pill">{(r["Giá"] / b[0] - 1) * 100:+.1f}%<small>thấp hơn vùng</small></span>'
            else:
                profit = '<span class="tp-pill g">0%<small>trong vùng</small></span>'
    elif pd.notna(r["Lãi %"]):
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
        ta = f'<span class="tp-sc">{int(r["TA"])}<small>/100</small></span>{rsi}{_bar(r["TA"])}' + "".join(f'<span class="tp-chip">{_e(t)}</span>' for t in r["TA tags"][:3])
    else:
        ta = '<span class="tp-mu">Chưa đủ số liệu</span>'
    label, tone, note = r["Khuyến nghị"]
    ng = r["Ngoại"]
    foreign = (f'<div class="tp-note">{"Khối ngoại gom ròng" if ng > 0 else "Khối ngoại bán ròng"}</div>'
               if ng is not None and pd.notna(ng) and abs(ng) > 0 else "")
    rec = f'<span class="tp-rec {tone}">{_e(label)}</span><div class="tp-note">{_e(note)}</div>{foreign}'
    kn = fmt_date(parse_date(r.get("Ngày KN"))) or ""
    meta = ('<div class="tp-meta">' + (f'<span class="tp-chip2">{_e(r["Khung"])}</span>' if r.get("Khung") else "")
            + (f'<span class="tp-chip2">KN {_e(kn)}</span>' if kn else "") + "</div>")
    thesis = str(r.get("Luận điểm") or "").strip()
    main = (f'<tr class="{"hasth" if thesis else ""}"><td><span class="tp-rank">{i}</span></td>'
            f'<td class="l"><span class="tp-code">{_e(r["Mã"])}</span>{ex}<div class="tp-name">{_e(r["Tên"])}</div>{sec}{meta}</td>'
            f'<td><span class="tp-px {cls}">{_px(r["Giá"])}</span></td><td>{chg}</td><td style="font-weight:700">{_vol(r["KL"])}</td>'
            f'<td>{tot}</td><td>{buy}</td><td>{profit}</td><td>{lvl(r["Target"], r["target_auto"], "a")}</td>'
            f'<td>{lvl(r["Cutloss"], r["stop_auto"], "r")}</td><td>{sell}</td><td>{fa}</td><td>{ta}</td><td>{rec}</td></tr>')
    if thesis:
        main += f'<tr class="th"><td></td><td colspan="13">💡 <b>Luận điểm:</b> {_e(thesis)}</td></tr>'
    return main


# Nhóm Chờ mua trình bày theo form riêng: Hạng | Lệnh | Mã CP (+ngày KN) | Vùng mua KN | Giá hiện tại | Cách vùng mua | Tỷ trọng | Ví dụ |
# Cắt lỗ | Giá Mục Tiêu 1 | Giá Mục Tiêu 2 | Điểm cơ bản (FA) | Điểm kỹ thuật (TA) | Tổng điểm | Khuyến nghị
WAIT_HEAD = ["Hạng", "Lệnh", "Mã CP", "Vùng mua KN", "Giá hiện tại", "Cách vùng mua", "Tỷ trọng", "Ví dụ", "Cắt lỗ",
             "Giá Mục Tiêu 1", "Giá Mục Tiêu 2", "Điểm cơ bản (FA)", "Điểm kỹ thuật (TA)", "Tổng điểm", "Khuyến nghị"]
WAIT_WIDTH = [2.5, 6.5, 5.5, 8.5, 5.5, 7, 4.5, 9, 6, 6, 6, 9, 9.5, 5.5, 9]            # % bề rộng từng cột, tổng 100
_WAIT_CMD = {"CHỜ VỀ VÙNG MUA": ("CHỜ MUA", "gold"), "VÙNG MUA": ("MUA NGAY", "green"), "DƯỚI VÙNG MUA": ("DƯỚI VÙNG", "gray")}


def _star(flag: bool) -> str:
    return '<sup class="st">*</sup>' if flag else ""


def example_text(weight, qty) -> str:
    """Câu minh họa giải ngân: "Dự định mua 1000 CP. Tỷ trọng 30% = 300 CP". Thiếu tỷ trọng hoặc số lượng thì để trống."""
    w, q = _f(weight), _f(qty)
    if not w or not q or w <= 0 or q <= 0:
        return ""
    return f"Dự định mua {q:.0f} CP. Tỷ trọng {w:g}% = {q * w / 100:.0f} CP"


def _price_html(r) -> str:
    """Giá hiện tại tô màu theo phiên: xanh tăng, đỏ giảm, cam vàng đứng giá; dòng dưới là ▲/▼/■ % so với phiên trước."""
    chg, chgp = _f(r.get("Chg")), _f(r.get("Chg %"))
    if chg is None:
        return _px(r["Giá"])
    pc, ar = ("up", "▲") if round(chg, 2) > 0 else ("dn", "▼") if round(chg, 2) < 0 else ("fl", "■")
    return f'<div class="lv {pc}">{_px(r["Giá"])}</div><div class="lv {pc}">{ar} {abs(chgp or 0):.2f}%</div>'


def _score_cells(r) -> tuple[str, str, str, str]:
    """(Tổng điểm, FA, TA, Khuyến nghị) dạng HTML, dùng chung cho nhóm Chờ mua và Đang nắm giữ."""
    mu = '<span class="tp-mu">—</span>'
    tot = (f'<span class="tp-score">{r["Tổng điểm"]:.0f}</span><span class="tp-grade">{_e(r["Hạng"])}</span>{_bar(r["Tổng điểm"])}'
           if _ok(r["Tổng điểm"]) else mu)
    if _ok(r["FA"]):
        fa = f'<span class="tp-sc">{int(r["FA"])}<small>/100</small></span>{_bar(r["FA"])}' + "".join(f'<span class="tp-chip">{_e(t)}</span>' for t in r["FA tags"][:3])
    else:
        fa = '<span class="tp-mu">Chưa đủ số liệu</span>'
    if _ok(r["TA"]):
        rsi = f'<div class="tp-mu" style="font-size:11.5px">RSI {r["RSI"]:.1f}</div>' if _ok(r["RSI"]) else ""
        ta = f'<span class="tp-sc">{int(r["TA"])}<small>/100</small></span>{rsi}{_bar(r["TA"])}' + "".join(f'<span class="tp-chip">{_e(t)}</span>' for t in r["TA tags"][:3])
    else:
        ta = '<span class="tp-mu">Chưa đủ số liệu</span>'
    label, tone, note = r["Khuyến nghị"]
    ng = r["Ngoại"]
    foreign = (f'<div class="tp-note">{"Khối ngoại gom ròng" if ng > 0 else "Khối ngoại bán ròng"}</div>'
               if ng is not None and pd.notna(ng) and abs(ng) > 0 else "")
    rec = f'<span class="tp-rec {tone}">{_e(label)}</span><div class="tp-note">{_e(note)}</div>{foreign}'      # giữ nguyên như cũ
    return tot, fa, ta, rec


def _wait_row_html(i: int, r) -> str:
    mu = '<span class="tp-mu">—</span>'
    nd = r.get("_nodata")
    if isinstance(nd, (bool, np.bool_)) and nd:
        return (f'<tr><td><span class="tp-rank">{i}</span></td><td></td><td class="l"><span class="tp-code">{_e(r["Mã"])}</span>'
                f'<div class="tp-name">Chưa có dữ liệu giá của mã này</div></td>' + '<td></td>' * 12 + '</tr>')
    price = r["Giá"]
    label, tone, note = r["Khuyến nghị"]
    cmd, ctone = _WAIT_CMD.get(label, (label, tone))
    kn = fmt_date(parse_date(r.get("Ngày KN"))) or ""
    b = r["Điểm mua"]
    if isinstance(b, tuple):
        bt = _px(b[0]) if abs(b[0] - b[1]) < 1e-9 else f"{_px(b[0])} – {_px(b[1])}"
        bt = bt.replace(" – ", " - ")
        buy = f'{bt}{_star(r["buy_auto"])}'
        gap = (f'{(price / b[1] - 1) * 100:+.1f}%' if price > b[1] else f'{(price / b[0] - 1) * 100:+.1f}%' if price < b[0] else "0.0%")
    else:
        buy = gap = mu

    def lvl(val, auto, tone_):
        if not _ok(val) or not val:
            return mu
        d = (val / price - 1) * 100
        return f'<div class="lv {tone_}">{_px(val)}{_star(auto)}</div><div class="lv {tone_}">{"▲" if d >= 0 else "▼"} {abs(d):.2f}%</div>'
    t1, t2 = r["Target"], r["Điểm bán"]
    t2_show = t2 if (_ok(t2) and t2 and _ok(t1) and t1 and t2 > t1) else None            # Mục tiêu 2 chỉ hiện khi cao hơn Mục tiêu 1
    px_html = _price_html(r)
    w = _f(r.get("Tỷ trọng"))
    ex = example_text(r.get("Tỷ trọng"), r.get("Dự định"))
    tot, fa, ta, rec = _score_cells(r)
    thesis = str(r.get("Luận điểm") or "").strip()
    main = (f'<tr class="{"hasth" if thesis else ""}"><td class="pl">{i}</td>'
            f'<td class="pl cmd"><span class="cmd-t {ctone}">{_e(cmd)}</span></td>'
            f'<td class="pl l"><div class="pl-code">{_e(r["Mã"])}</div>' + (f'<div class="pl-date">{_e(kn)}</div>' if kn else "") + '</td>'
            f'<td class="pl key">{buy}</td><td class="pl key">{px_html}</td><td class="pl">{gap}</td><td class="pl">{f"{w:g}%" if w else mu}</td>'
            f'<td class="pl ex">{_e(ex) if ex else mu}</td>'
            f'<td class="pl rt">{lvl(r["Cutloss"], r["stop_auto"], "dn")}</td><td class="pl rt">{lvl(t1, r["target_auto"], "up")}</td>'
            f'<td class="pl rt">{lvl(t2_show, r["sell_auto"], "up")}</td>'
            f'<td>{fa}</td><td>{ta}</td><td>{tot}</td><td>{rec}</td></tr>')
    if thesis:
        main += f'<tr class="th"><td></td><td colspan="14">💡 <b>Luận điểm:</b> {_e(thesis)}</td></tr>'
    return main


def wait_table_html(v: pd.DataFrame) -> str:
    cg = "".join(f'<col style="width:{w}%">' for w in WAIT_WIDTH)
    th = "".join(f'<th class="{"l" if h == "Mã CP" else ""}">{h}</th>' for h in WAIT_HEAD)
    body = "".join(_wait_row_html(i + 1, r) for i, (_, r) in enumerate(v.iterrows()))
    foot = ('<div class="vp-disc">* Mức giá do hệ thống tự điền theo dữ liệu cuối phiên.</div>'
            if any(bool(r.get(k)) for _, r in v.iterrows() for k in ("buy_auto", "target_auto", "stop_auto", "sell_auto")) else "")
    return f'<div class="tp-wrap vpb"><table class="tp-tb"><colgroup>{cg}</colgroup><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table></div>{foot}'


# Nhóm Đang nắm giữ: Hạng | Lệnh | Mã CP (+ngày KN) | Vùng mua KN | Giá khớp lệnh | Giá hiện tại | Khối lượng | Lãi/Lỗ dự kiến (%) |
# Điểm cơ bản (FA) | Điểm kỹ thuật (TA) | Tổng điểm | Tín hiệu hiện tại | Khuyến nghị
HOLD_HEAD = ["Hạng", "Lệnh", "Mã CP", "Vùng mua KN", "Giá khớp lệnh", "Giá hiện tại", "Khối lượng", "Lãi/Lỗ dự kiến (%)",
             "Điểm cơ bản (FA)", "Điểm kỹ thuật (TA)", "Tổng điểm", "Tín hiệu hiện tại", "Khuyến nghị"]
HOLD_WIDTH = [2.5, 5.5, 6.5, 10, 8, 8, 7, 11.5, 9, 9.5, 5.5, 7.5, 9.5]            # % bề rộng từng cột, tổng 100


def _hold_row_html(i: int, r) -> str:
    mu = '<span class="tp-mu">—</span>'
    nd = r.get("_nodata")
    if isinstance(nd, (bool, np.bool_)) and nd:
        return (f'<tr><td class="pl">{i}</td><td></td><td class="pl l"><div class="pl-code">{_e(r["Mã"])}</div></td>'
                f'<td colspan="10" class="tp-mu" style="text-align:left">Chưa có dữ liệu giá của mã này</td></tr>')
    price = r["Giá"]
    kn = fmt_date(parse_date(r.get("Ngày KN"))) or ""
    b = r["Điểm mua"]
    if isinstance(b, tuple):
        bt = _px(b[0]) if abs(b[0] - b[1]) < 1e-9 else f"{_px(b[0])} - {_px(b[1])}"
        zone = f'{bt}{_star(r["buy_auto"])}'
    else:
        zone = mu
    fill = r.get("Giá khớp")
    if _ok(fill) and fill:
        fill_html = _px(fill)
    elif _ok(r.get("Entry")) and r.get("Entry"):
        fill_html = f'{_px(r["Entry"])}{_star(True)}'                  # chưa nhập Giá khớp: tạm lấy giữa vùng mua
    else:
        fill_html = mu
    q = r.get("KL nắm")
    qty = f"{q:.0f}" if _ok(q) and q else mu
    if pd.notna(r["Lãi %"]):
        pct = r["Lãi %"]
        pc, ar = ("up", "▲") if round(pct, 2) > 0 else ("dn", "▼") if round(pct, 2) < 0 else ("fl", "■")
        pl_pct = f'<div class="lv {pc}">{ar} {abs(pct):.2f}%</div>'
        if _ok(q) and q:
            amt = r["Lãi"] * q * 1000
            pl = (f'<div class="lv {pc}">{"+" if amt > 0 else "-" if amt < 0 else ""}{abs(amt):,.0f} đ</div>'
                  f'<div class="lv {pc}">{ar} {abs(pct):.2f}%</div>')
        else:
            pl = pl_pct
    else:
        pl = mu
    sig = str(r.get("Tín hiệu") or "").strip()
    tot, fa, ta, rec = _score_cells(r)
    thesis = str(r.get("Luận điểm") or "").strip()
    main = (f'<tr class="{"hasth" if thesis else ""}"><td class="pl">{i}</td>'
            f'<td class="pl cmd"><span class="cmd-t green">MUA</span></td>'
            f'<td class="pl l"><div class="pl-code">{_e(r["Mã"])}</div>' + (f'<div class="pl-date">{_e(kn)}</div>' if kn else "") + '</td>'
            f'<td class="pl key">{zone}</td><td class="pl key">{fill_html}</td><td class="pl key">{_price_html(r)}</td><td class="pl">{qty}</td>'
            f'<td class="pl rt">{pl}</td><td>{fa}</td><td>{ta}</td><td>{tot}</td>'
            f'<td class="pl sig">{_e(sig) if sig else mu}</td><td>{rec}</td></tr>')
    if thesis:
        main += f'<tr class="th"><td></td><td colspan="12">💡 <b>Luận điểm:</b> {_e(thesis)}</td></tr>'
    return main


def hold_table_html(v: pd.DataFrame) -> str:
    cg = "".join(f'<col style="width:{w}%">' for w in HOLD_WIDTH)
    th = "".join(f'<th class="{"l" if h == "Mã CP" else ""}">{h}</th>' for h in HOLD_HEAD)
    body = "".join(_hold_row_html(i + 1, r) for i, (_, r) in enumerate(v.iterrows()))
    notes = []
    if any((not (_ok(r.get("Giá khớp")) and r.get("Giá khớp"))) and _ok(r.get("Entry")) and r.get("Entry") for _, r in v.iterrows()):
        notes.append("Chưa nhập giá khớp: tạm tính theo giữa vùng mua.")
    if any(bool(r.get("buy_auto")) for _, r in v.iterrows()):
        notes.append("Mức giá do hệ thống tự điền theo dữ liệu cuối phiên.")
    foot = f'<div class="vp-disc">* {" ".join(notes)}</div>' if notes else ""
    return f'<div class="tp-wrap vpb"><table class="tp-tb" style="min-width:1560px"><colgroup>{cg}</colgroup><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table></div>{foot}'


def table_html(v: pd.DataFrame, mode: str = "hold") -> str:
    """mode="wait": nhóm Chờ mua (xem wait_table_html); mode="hold": nhóm Đang nắm giữ (xem hold_table_html)."""
    if mode == "wait":
        return wait_table_html(v)
    if mode == "hold":
        return hold_table_html(v)
    head = ["HẠNG", "MÃ CK", "GIÁ HIỆN TẠI", "+/-", "KHỐI LƯỢNG", "TỔNG ĐIỂM", "VÙNG MUA" if mode == "wait" else "GIÁ MUA",
            "CÁCH VÙNG MUA" if mode == "wait" else "LỢI NHUẬN", "TARGET", "CUTLOSS", "ĐIỂM BÁN", "ĐIỂM CƠ BẢN (FA)", "ĐIỂM KỸ THUẬT (TA)", "KHUYẾN NGHỊ"]
    th = "".join(f'<th class="{"l" if h == "MÃ CK" else ""}">{h}</th>' for h in head)
    body = "".join(_row_html(i + 1, r, mode) for i, (_, r) in enumerate(v.iterrows()))
    return f'<div class="tp-wrap"><table class="tp-tb"><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table></div>'


def closed_html(d: pd.DataFrame, meta_fn) -> str:
    """Bảng nhóm Đã đóng: giá mua, giá đóng, kết quả (%) và số ngày từ ngày khuyến nghị đến ngày đóng; mới đóng xếp trước."""
    rows = []
    for _, p in d.iterrows():
        e, c = parse_range(p["Điểm mua"]), parse_price(p["Giá đóng"])
        entry = (e[0] + e[1]) / 2 if e else None
        res = (c / entry - 1) * 100 if (entry and c) else None
        d0, d1 = parse_date(p["Ngày khuyến nghị"]), parse_date(p["Ngày đóng"])
        days = (d1 - d0).days if (d0 and d1) else None
        name, sector = meta_fn(p["Mã"]) if meta_fn else ("", "")
        rows.append({"p": p, "res": res, "days": days, "name": name, "sector": sector, "d1": d1 or date.min, "entry": entry, "close": c})
    rows.sort(key=lambda x: x["d1"], reverse=True)
    out = []
    for r in rows:
        p = r["p"]
        pill = ('<span class="tp-mu">—</span>' if r["res"] is None
                else f'<span class="tp-pill {"g" if r["res"] >= 0 else "r"}">{r["res"]:+.2f}%</span>')
        sec = f'<div><span class="tp-sec">{_e(r["sector"])}</span></div>' if r["sector"] else ""
        th = str(p["Luận điểm"] or "").strip()
        out.append(
            f'<tr class="{"hasth" if th else ""}"><td class="l"><span class="tp-code">{_e(p["Mã"])}</span><div class="tp-name">{_e(r["name"])}</div>{sec}'
            f'<div class="tp-meta"><span class="tp-chip2">{_e(p["Khung thời gian"])}</span></div></td>'
            f'<td>{_e(p["Ngày khuyến nghị"]) or "—"}</td><td>{_px(r["entry"]) if r["entry"] else "—"}</td>'
            f'<td>{_e(p["Ngày đóng"]) or "—"}</td><td>{_px(r["close"]) if r["close"] else "—"}</td><td>{pill}</td>'
            f'<td>{r["days"] if r["days"] is not None else "—"}</td></tr>'
            + (f'<tr class="th"><td colspan="7">💡 <b>Luận điểm:</b> {_e(th)}</td></tr>' if th else ""))
    head = ["MÃ CK", "NGÀY KHUYẾN NGHỊ", "GIÁ MUA", "NGÀY ĐÓNG", "GIÁ ĐÓNG", "KẾT QUẢ", "SỐ NGÀY"]
    th = "".join(f'<th class="{"l" if h == "MÃ CK" else ""}">{h}</th>' for h in head)
    return f'<div class="tp-wrap"><table class="tp-tb" style="min-width:760px"><thead><tr>{th}</tr></thead><tbody>{"".join(out)}</tbody></table></div>'


# ------------------------------------------------------------------ TRANG
_FIELDS = {"vp_code": "Mã", "vp_buy": "Điểm mua", "vp_target": "Target", "vp_cut": "Cutloss", "vp_sell": "Điểm bán",
           "vp_status": "Trạng thái", "vp_frame": "Khung thời gian", "vp_date": "Ngày khuyến nghị", "vp_note": "Luận điểm",
           "vp_close": "Giá đóng", "vp_cdate": "Ngày đóng", "vp_weight": "Tỷ trọng %", "vp_qty": "Dự định mua", "vp_fill": "Giá khớp", "vp_hold": "Khối lượng"}
_DEFAULT = {"vp_status": "Chờ mua", "vp_frame": "Trung hạn", "vp_weight": "30", "vp_qty": "1000"}
_GROUP_KEY = {"Chờ mua": "wait", "Đang nắm giữ": "hold", "Đã đóng": "closed"}
_GROUP_ICON = {"Chờ mua": "🎯", "Đang nắm giữ": "📈", "Đã đóng": "✅"}
_GROUP_HINT = {
    "Chờ mua": "Cổ phiếu Admin đang theo dõi, chờ giá về vùng mua. Chưa vào lệnh: bạn tự cân nhắc theo vùng mua, cutloss và target.",
    "Đang nắm giữ": "Các khuyến nghị đã vào lệnh. Lợi nhuận tính từ giá mua khuyến nghị đến giá hiện tại.",
    "Đã đóng": "Các khuyến nghị đã kết thúc (chốt lời hoặc cắt lỗ). Kết quả tính từ giá mua khuyến nghị đến giá đóng.",
}


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
        st.session_state[k] = _DEFAULT.get(k, "")


def _save_cb(available: set) -> None:
    ss = st.session_state
    if not ss.get("vp_admin"):
        return
    row = {col: str(ss.get(k, _DEFAULT.get(k, "")) or "").strip() for k, col in _FIELDS.items()}
    row["Mã"] = row["Mã"].upper()
    row["Luận điểm"] = re.sub(r"\s+", " ", row["Luận điểm"])[:300]
    err = lambda m: ss.__setitem__("vp_msg", ("err", m))       # noqa: E731
    if not re.fullmatch(r"[A-Z0-9]{2,10}", row["Mã"]):
        return err("Nhập mã cổ phiếu hợp lệ vào ô Mã CK.")
    if row["Mã"] not in available:
        return err(f"{row['Mã']} chưa có trong dữ liệu của app nên chưa thêm được.")
    for col in ("Điểm mua", "Target", "Cutloss", "Điểm bán", "Giá đóng"):
        if row[col] and not _nums(row[col]):
            return err(f"Ô {col} cần là số, ví dụ 35.5 hoặc 35.5 - 36.0.")
    w, q = parse_price(row["Tỷ trọng %"]), parse_price(row["Dự định mua"])
    if (row["Tỷ trọng %"] and not (w and 0 < w <= 100)) or (row["Dự định mua"] and not (q and q > 0)):
        return err("Tỷ trọng là số từ 1 đến 100 (%), Dự định mua là số cổ phiếu lớn hơn 0.")
    row["Tỷ trọng %"] = f"{w:g}" if w else ""
    row["Dự định mua"] = f"{q:.0f}" if q else ""
    fl, hq = parse_price(row["Giá khớp"]), parse_price(row["Khối lượng"])
    if (row["Giá khớp"] and not (fl and fl > 0)) or (row["Khối lượng"] and not (hq and hq > 0)):
        return err("Giá khớp và Khối lượng nắm giữ cần là số lớn hơn 0.")
    row["Giá khớp"] = f"{fl:g}" if fl else ""
    row["Khối lượng"] = f"{hq:.0f}" if hq else ""
    t, c = parse_price(row["Target"]), parse_price(row["Cutloss"])
    if t and c and t <= c:
        return err("Target phải cao hơn Cutloss.")
    if row["Trạng thái"] not in STATUSES:
        row["Trạng thái"] = "Chờ mua"
    if row["Khung thời gian"] not in FRAMES:
        row["Khung thời gian"] = "Trung hạn"
    d0 = parse_date(row["Ngày khuyến nghị"]) if row["Ngày khuyến nghị"] else _today()
    if d0 is None:
        return err("Ngày khuyến nghị cần có dạng dd/mm/yyyy, ví dụ 28/10/2026 (để trống = hôm nay).")
    row["Ngày khuyến nghị"] = fmt_date(d0)
    if row["Trạng thái"] in ("Đang nắm giữ", "Đã đóng") and not parse_range(row["Điểm mua"]):
        return err(f"Trạng thái \"{row['Trạng thái']}\" cần có Điểm mua (giá vào lệnh).")
    if row["Trạng thái"] == "Đã đóng":
        if not parse_price(row["Giá đóng"]):
            return err("Trạng thái \"Đã đóng\" cần có Giá đóng.")
        d1 = parse_date(row["Ngày đóng"]) if row["Ngày đóng"] else _today()
        if d1 is None:
            return err("Ngày đóng cần có dạng dd/mm/yyyy (để trống = hôm nay).")
        if d1 < d0:
            return err("Ngày đóng không được trước Ngày khuyến nghị.")
        row["Ngày đóng"] = fmt_date(d1)
    else:
        row["Giá đóng"] = row["Ngày đóng"] = ""
    werr = save(upsert(load(), row))
    ss["vp_msg"] = ("ok", f"Đã lưu {row['Mã']} ({row['Trạng thái']})" + (f" (chưa ghi được vào file: {werr})" if werr else ""))
    _clear_form()


def _add_cb(available: set) -> None:
    """Thêm nhanh nhiều mã vào nhóm Chờ mua (các mốc để trống: hệ thống tự điền); mã đã có thì giữ nguyên."""
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
    werr = ""
    if ok:
        new = [{"Mã": c, "Trạng thái": "Chờ mua", "Khung thời gian": "Trung hạn", "Ngày khuyến nghị": fmt_date(_today()),
                "Tỷ trọng %": _DEFAULT["vp_weight"], "Dự định mua": _DEFAULT["vp_qty"]} for c in ok]
        werr = save(pd.concat([d, pd.DataFrame(new)], ignore_index=True))
    parts = ([f"Đã thêm vào Chờ mua: {', '.join(ok)}"] if ok else []) + ([f"Đã có sẵn: {', '.join(dup)}"] if dup else []) \
        + ([f"Không có trong dữ liệu: {', '.join(bad)}"] if bad else []) + ([f"chưa ghi được vào file: {werr}"] if werr else [])
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
    werr = remove(code)
    st.session_state["vp_msg"] = ("ok" if not werr else "err", f"Đã xóa {code}" if not werr else f"Chưa xóa được {code}: {werr}")


def _bought_cb(code: str) -> None:
    """Chờ mua -> Đang nắm giữ (cần Điểm mua do Admin nhập: giá vào lệnh)."""
    ss = st.session_state
    if not ss.get("vp_admin"):
        return
    d = load()
    hit = d[d["Mã"] == code]
    if hit.empty:
        return
    if not parse_range(hit.iloc[0]["Điểm mua"]):
        ss["vp_msg"] = ("err", f"{code}: nhập Điểm mua (giá vào lệnh) bằng nút ✏️ Sửa trước khi chuyển sang Đang nắm giữ.")
        return
    d.loc[d["Mã"] == code, "Trạng thái"] = "Đang nắm giữ"
    werr = save(d)
    ss["vp_msg"] = ("ok" if not werr else "err", f"{code} đã chuyển sang Đang nắm giữ" if not werr else f"Chưa lưu được: {werr}")


def _close_prep_cb(code: str) -> None:
    """Nạp mã vào form với trạng thái Đã đóng để Admin nhập Giá đóng rồi bấm Lưu."""
    if not st.session_state.get("vp_admin"):
        return
    _edit_cb(code)
    st.session_state["vp_status"] = "Đã đóng"
    st.session_state["vp_cdate"] = fmt_date(_today())
    st.session_state["vp_msg"] = ("ok", f"Nhập Giá đóng của {code} ở form phía trên rồi bấm Lưu.")


def _hero_html(n: int) -> str:
    return (f'<div class="vp-hero"><div class="vp-ico">🔥</div><div><div class="vp-title">KHUYẾN NGHỊ KHÁCH HÀNG '
            f'<span class="vp-badge">VIP RECOMMENDATIONS</span><span class="vp-badge n">{n} mã đang mở</span></div>'
            f'<div class="vp-sub">Danh mục cổ phiếu chọn lọc bởi Admin • Tự động tính điểm FA, TA và trạng thái khuyến nghị theo dữ liệu cuối phiên</div></div></div>')


def _admin_panel(available: set) -> None:
    ss = st.session_state
    for k in _FIELDS:
        ss.setdefault(k, _DEFAULT.get(k, ""))
    st.markdown('<div class="vp-adm"><span class="vp-admtag">⚡ BẢNG ĐIỀN ĐIỂM MUA - BÁN - TARGET (ADMIN)</span>'
                '<span>Điền các mức giá rồi bấm Lưu, hoặc chọn mã dưới bảng và bấm Sửa. Ô giá để trống sẽ tự điền theo hệ thống.</span></div>',
                unsafe_allow_html=True)
    c = st.columns([1.1, 1.5, 1.3, 1, 1, 1.3])
    c[0].text_input("Mã CK *", key="vp_code", placeholder="VD: IDC, HPG...")
    c[1].text_input("Điểm Mua", key="vp_buy", placeholder="VD: 35.5 - 36.0")
    c[2].text_input("Lợi Nhuận", key="vp_profit", placeholder="Tự tính theo giá hiện tại", disabled=True)
    c[3].text_input("Target", key="vp_target", placeholder="VD: 42.0")
    c[4].text_input("Cutloss", key="vp_cut", placeholder="VD: 34.0")
    c[5].text_input("Điểm Bán", key="vp_sell", placeholder="VD: ≥ 42.0")
    c2 = st.columns([1.1, 1.5, 1.3, 1, 1, 1.3])
    c2[0].selectbox("Trạng thái", STATUSES, key="vp_status")
    c2[1].selectbox("Khung thời gian", FRAMES, key="vp_frame")
    c2[2].text_input("Ngày khuyến nghị", key="vp_date", placeholder="dd/mm/yyyy (trống = hôm nay)")
    c2[3].text_input("Giá đóng", key="vp_close", placeholder="Chỉ khi Đã đóng")
    c2[4].text_input("Ngày đóng", key="vp_cdate", placeholder="dd/mm/yyyy")
    c3 = st.columns([1.1, 1.5, 1.3, 1, 1, 1.3])
    c3[0].text_input("Tỷ trọng (%)", key="vp_weight", placeholder="VD: 30")
    c3[1].text_input("Dự định mua (cổ phiếu)", key="vp_qty", placeholder="VD: 1000")
    c3[2].text_input("Giá khớp lệnh (Đang nắm giữ)", key="vp_fill", placeholder="VD: 20.8 (trống = giữa vùng mua)")
    c3[3].text_input("Khối lượng nắm giữ", key="vp_hold", placeholder="VD: 3000")
    st.text_input("Luận điểm", key="vp_note", placeholder="VD: Nền tích lũy pha C, chờ giá vượt MA20 kèm khối lượng (tối đa 300 ký tự)")
    b1, b2, _ = st.columns([1.2, 0.5, 6])
    b1.button("✓ Lưu", type="primary", on_click=_save_cb, args=(available,), use_container_width=True)
    b2.button("↺", on_click=_clear_form, help="Xóa trắng form", use_container_width=True)
    q1, q2, q3, _ = st.columns([3, 1.6, 1, 3])
    q1.text_input("Nhập mã CP", key="vp_add", placeholder="Nhập mã CP (VD: HPG, IDC, MSH...)", label_visibility="collapsed")
    q2.button("＋ Thêm mã vào VIP", on_click=_add_cb, args=(available,), use_container_width=True)
    q3.button("🔓 Khóa", on_click=_lock_cb, use_container_width=True, help="Thoát chế độ Admin")


def _render_group(status: str, d: pd.DataFrame, res, frames_d, fund_map, wb, meta_fn, ctx_fn, on_chart, admin: bool) -> None:
    k = _GROUP_KEY[status]
    st.caption(_GROUP_HINT[status])
    if d.empty:
        st.info(f"Chưa có mã nào ở nhóm {status}." + (" Dùng form Admin phía trên để thêm." if admin else ""))
        return
    if status == "Đã đóng":
        d = d.assign(_d=d["Ngày đóng"].map(lambda x: parse_date(x) or date.min)).sort_values("_d", ascending=False, kind="stable")
        st.markdown(closed_html(d, meta_fn), unsafe_allow_html=True)
        codes = list(d["Mã"])
    else:
        v = build_view(d, res, frames_d, fund_map, wb, meta_fn, ctx_fn)
        st.markdown(table_html(v, k), unsafe_allow_html=True)
        codes = list(v["Mã"])
    n_btn = 1 + (2 if admin else 0) + (1 if admin and status != "Đã đóng" else 0)
    row = st.columns([1.4] + [1] * n_btn + [4])
    pick = row[0].selectbox("Mã cần thao tác", codes, key=f"vp_pick_{k}", label_visibility="collapsed")
    if row[1].button("📈 Đồ thị", key=f"vp_chart_{k}", use_container_width=True):
        on_chart(pick)                      # on_chart gọi NAV.goto -> st.rerun, nên không dùng on_click
    if admin:
        row[2].button("✏️ Sửa", key=f"vp_edit_{k}", on_click=_edit_cb, args=(pick,), use_container_width=True)
        row[3].button("🗑 Xóa", key=f"vp_del_{k}", on_click=_delete_cb, args=(pick,), use_container_width=True)
        if status == "Chờ mua":
            row[4].button("▶ Đã mua", key="vp_bought", on_click=_bought_cb, args=(pick,), use_container_width=True)
        elif status == "Đang nắm giữ":
            row[4].button("■ Đóng lệnh", key="vp_closeprep", on_click=_close_prep_cb, args=(pick,), use_container_width=True)


def render(res: pd.DataFrame, frames_d: pd.DataFrame, wb: pd.DataFrame, fund_map: dict, meta_fn, ctx_fn, on_chart, on_filter=None) -> None:
    """res: res_df; frames_d: frames["D"]; wb: bảng Chờ mua; fund_map: {mã: {P/E, ROE, P/B…}}; meta_fn(code)->(tên, ngành);
    ctx_fn(code)->ngữ cảnh "Tóm tắt nhanh" của app; on_chart(code): mở biểu đồ; on_filter(): mở Bộ lọc cổ phiếu."""
    ss = st.session_state
    admin = bool(ss.get("vp_admin"))
    available = set(res["Mã"].astype(str).str.upper())
    plans = load()
    groups = {s_: plans[plans["Trạng thái"] == s_] for s_ in STATUSES}
    st.markdown(CSS + _hero_html(len(groups["Chờ mua"]) + len(groups["Đang nắm giữ"])), unsafe_allow_html=True)

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
    if _ERR:
        st.warning(f"Không đọc được {PATH}: {_ERR}. Kiểm tra dòng tiêu đề có cột Mã.")

    plans = load()
    if plans.empty:
        st.info("Danh mục khuyến nghị đang trống." + (" Nhập mã ở phần Admin phía trên rồi bấm Lưu." if admin else ""))
    else:
        tabs = st.tabs([f"{_GROUP_ICON[s_]} {s_} ({len(groups[s_])})" for s_ in STATUSES])
        for tab, s_ in zip(tabs, STATUSES):
            with tab:
                _render_group(s_, groups[s_], res, frames_d, fund_map, wb, meta_fn, ctx_fn, on_chart, admin)

    f1, f2 = st.columns([5, 1.6])
    f1.markdown('<div class="vp-foot">🛡️ Danh mục Khuyến nghị độc quyền dành cho khách hàng VIP • Cập nhật giá &amp; chỉ báo tự động</div>'
                '<div class="vp-disc">Tổng điểm = Score của app × 10 (hạng A ≥ 75, B ≥ 60, C ≥ 40). FA chấm từ ROE, P/E, P/B; TA chấm từ MA20, MA50, MA200, RSI và khối lượng. '
                'Chỉ phục vụ nghiên cứu, không phải khuyến nghị đầu tư.</div>', unsafe_allow_html=True)
    if on_filter and f2.button("🔽 Mở trong Bộ lọc cổ phiếu", use_container_width=True):
        on_filter()
