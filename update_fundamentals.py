#!/usr/bin/env python3
"""Tự động cập nhật data/fundamentals.csv: Tên công ty, P/B, ROE, P/E cho cả rổ mã (nguồn vnstock).

- Tên công ty: lấy hàng loạt từ danh sách mã của vnstock (1 yêu cầu). Muốn sửa tay, ghi vào
  data/ten_cong_ty_tay.csv (cột: Mã, Tên công ty); dòng tay luôn được ưu tiên.
- P/B, ROE: lấy từ Fundamental().equity(mã).ratio() (kỳ báo cáo mới nhất nguồn trả về), mỗi mã 1 yêu cầu,
  chỉ hỏi lại sau --refresh-days ngày (mặc định 7) vì số liệu này đổi theo quý, không đổi mỗi ngày.
  Chức năng này cần khóa API vnstock cấp Cộng đồng (miễn phí); cấp Khách không được cấp quyền.
- Điền tay P/B, ROE: sửa data/fundamentals.csv, đặt cột Cập nhật = "tay" thì sẽ không bị ghi đè.

Chạy:  python update_fundamentals.py              (cập nhật bình thường)
       python update_fundamentals.py --probe HPG  (xem nguồn trả về cột gì và đọc được gì, để chẩn đoán)
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time
import unicodedata

import pandas as pd

import eod_fetch as EF

FUND = "data/fundamentals.csv"
MANUAL_NAMES = "data/ten_cong_ty_tay.csv"
DATE_FMT = "%d/%m/%Y"
COLS = ["Mã", "Tên công ty", "P/B", "ROE", "P/E", "P/B TB 3N", "P/E TB 3N", "Cập nhật"]

PB_RE = re.compile(r"^(pb|ptb|pricetobook(value)?)(ratio|x|ttm|value|quarter|year|4q|lan)?$")
PE_RE = re.compile(r"^(pe|priceearning|pricetoearning|pricetoearnings|ptoe)(ratio|x|ttm|value|quarter|year|4q|lan)?$")
ROE_RE = re.compile(r"^(roe|returnonequity)(ratio|x|ttm|pct|percent|quarter|year|4q|a|avg|average)?$")
NAME_ORDER = ("organname", "companyname", "tencongty", "companynamevi", "organnamevi", "namevi", "fullname", "name",
              "organshortname", "shortname")
SYM_KEYS = ("symbol", "ticker", "stockcode", "code", "ma", "mack")


def _norm(s) -> str:
    s = str(s).replace("đ", "d").replace("Đ", "D")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "", s)


def _flat(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df, pd.Series):
        df = df.to_frame().T
    if isinstance(df, dict):
        df = pd.DataFrame([df])
    if not isinstance(df, pd.DataFrame):
        return pd.DataFrame()
    df = df.copy()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [" ".join(str(x) for x in c if str(x) and not str(x).startswith("Unnamed")).strip() for c in df.columns]
    df.columns = [str(c) for c in df.columns]
    return df


def _is_metric(key: str, kind: str) -> bool:
    if kind == "pe":
        return bool(PE_RE.match(key))
    if kind == "pb":
        return bool(PB_RE.match(key)) or (key.endswith("pb") and len(key) > 2 and not key.endswith("bpb"))
    return bool(ROE_RE.match(key)) or key.endswith("roe")


def _period_key(label):
    s = str(label)
    y = re.search(r"(19|20)\d{2}", s)
    if not y:
        return None
    q = re.search(r"[Qq]\s*([1-4])|([1-4])\s*[Qq]", s)
    return (int(y.group(0)), int(next(g for g in q.groups() if g)) if q else 5)


def _num(v):
    v = pd.to_numeric(pd.Series([v]), errors="coerce").iloc[0]
    return None if pd.isna(v) else float(v)


def extract_metric(raw, kind: str):
    """Tìm P/B ('pb') hoặc ROE ('roe') mới nhất trong bảng vnstock trả về (cột = chỉ tiêu hoặc hàng = chỉ tiêu)."""
    df = _flat(raw)
    if df.empty:
        return None
    # Dạng 1: mỗi cột là một chỉ tiêu, mỗi hàng là một kỳ
    for c in df.columns:
        if _is_metric(_norm(c), kind):
            s = pd.to_numeric(df[c], errors="coerce")
            order = None
            for tc in df.columns:
                if _norm(tc) in ("date", "reportdate", "time", "tradingdate", "period", "ngay", "kybaocao"):
                    t = pd.to_datetime(df[tc], errors="coerce")
                    if t.notna().mean() > 0.5:
                        order = t
                        break
            if order is None:
                ycol = next((tc for tc in df.columns if _norm(tc) in ("year", "yearreport", "nam")), None)
                qcol = next((tc for tc in df.columns if _norm(tc) in ("quarter", "lengthreport", "quy")), None)
                if ycol is not None:
                    y = pd.to_numeric(df[ycol], errors="coerce")
                    q = pd.to_numeric(df[qcol], errors="coerce").fillna(5) if qcol is not None else 5
                    order = y * 10 + q
            if order is not None:
                s = s.loc[order.sort_values(ascending=True, na_position="first").index]
                s = s.dropna()
                return float(s.iloc[-1]) if len(s) else None
            s = s.dropna()                      # không rõ thứ tự: giả định dòng đầu là kỳ mới nhất
            return float(s.iloc[0]) if len(s) else None
    # Dạng 2: mỗi hàng là một chỉ tiêu (nhãn nằm ở cột chữ), mỗi cột số là một kỳ
    label_cols = [c for c in df.columns if not pd.api.types.is_numeric_dtype(df[c])]
    for c in label_cols:
        hit = df[df[c].map(lambda x: _is_metric(_norm(x), kind) if isinstance(x, str) else False)]
        if hit.empty:
            continue
        row = hit.iloc[0]
        cands = [(col, _num(row[col])) for col in df.columns if col not in label_cols]
        cands = [(col, v) for col, v in cands if v is not None]
        if not cands:
            continue
        keyed = [(k, v) for (col, v) in cands if (k := _period_key(col)) is not None]
        if keyed:
            return sorted(keyed)[-1][1]
        return cands[0][1]
    return None


def extract_names(raw) -> dict[str, str]:
    df = _flat(raw)
    if df.empty:
        return {}
    low = {_norm(c): c for c in df.columns}
    sym = next((low[k] for k in SYM_KEYS if k in low), None)
    nm = next((low[k] for k in NAME_ORDER if k in low), None)
    if sym is None or nm is None:
        return {}
    out = {}
    for s, n in zip(df[sym], df[nm]):
        if isinstance(s, str) and isinstance(n, str) and n.strip():
            out[s.strip().upper()] = re.sub(r"\s+", " ", n).strip()
    return out


# ------------------------------------------------------------------ GỌI VNSTOCK
def _call_safely(fn, tries: int = 3):
    """Chạy fn; nếu bị giới hạn tần suất thì chờ rồi thử lại; hết hạn mức thì ném Fatal."""
    for attempt in range(tries):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001
            if EF._is_fatal(e):
                raise EF.Fatal(str(e)) from e
            if EF._is_rate(e) and attempt < tries - 1:
                print(f"  bị giới hạn tần suất, chờ {EF.RATE_WAIT}s...", flush=True)
                time.sleep(EF.RATE_WAIT)
                continue
            raise


def _name_calls():
    def v5_list():
        from vnstock import Reference
        return Reference().equity.list()

    def legacy_listing():
        from vnstock import Listing
        return Listing(source="VCI").all_symbols()

    def legacy_vnstock():
        from vnstock import Vnstock
        return Vnstock().stock(symbol="ACB", source="VCI").listing.all_symbols()

    return [v5_list, legacy_listing, legacy_vnstock]


def fetch_names(verbose: bool = False) -> dict[str, str]:
    for fn in _name_calls():
        try:
            raw = _call_safely(fn)
            names = extract_names(raw)
            if verbose:
                cols = list(_flat(raw).columns)[:15]
                print(f"  [{fn.__name__}] cột: {cols} -> {len(names)} tên")
            if len(names) >= 50:
                return names
        except EF.Fatal:
            raise
        except Exception as e:  # noqa: BLE001
            if verbose:
                print(f"  [{fn.__name__}] lỗi: {type(e).__name__}: {e}")
    return {}


def _history(raw, kind: str) -> list:
    """Chuỗi giá trị của chỉ tiêu trong ~3 năm gần nhất, xếp từ cũ đến mới (rỗng nếu không đọc được)."""
    df = _flat(raw)
    if df.empty:
        return []
    for c in df.columns:  # Dạng 1: mỗi cột là một chỉ tiêu, mỗi hàng là một kỳ
        if not _is_metric(_norm(c), kind):
            continue
        s = pd.to_numeric(df[c], errors="coerce")
        for tc in df.columns:
            if _norm(tc) in ("date", "reportdate", "time", "tradingdate", "period", "ngay", "kybaocao"):
                t = pd.to_datetime(df[tc], errors="coerce")
                if t.notna().mean() > 0.5:
                    ok = t.notna() & s.notna()
                    t, s2 = t[ok], s[ok]
                    s2 = s2.loc[t.sort_values().index]
                    t = t.sort_values()
                    return [float(v) for v in s2[t >= t.max() - pd.DateOffset(years=3)]]
        ycol = next((tc for tc in df.columns if _norm(tc) in ("year", "yearreport", "nam")), None)
        qcol = next((tc for tc in df.columns if _norm(tc) in ("quarter", "lengthreport", "quy")), None)
        if ycol is not None:
            y = pd.to_numeric(df[ycol], errors="coerce")
            q = pd.to_numeric(df[qcol], errors="coerce").fillna(5) if qcol is not None else pd.Series(5, index=df.index)
            order = (y * 10 + q)
            ok = order.notna() & s.notna()
            vals = [float(v) for v in s[ok].loc[order[ok].sort_values().index]]
            return vals[-(12 if (q[ok] != 5).any() else 3):]
        vals = [float(v) for v in s.dropna()]      # không rõ thứ tự: giả định dòng đầu là kỳ mới nhất
        return vals[:12][::-1]
    label_cols = [c for c in df.columns if not pd.api.types.is_numeric_dtype(df[c])]
    for c in label_cols:  # Dạng 2: mỗi hàng là một chỉ tiêu, mỗi cột số là một kỳ
        hit = df[df[c].map(lambda x: _is_metric(_norm(x), kind) if isinstance(x, str) else False)]
        if hit.empty:
            continue
        row = hit.iloc[0]
        cands = [(col, _num(row[col])) for col in df.columns if col not in label_cols]
        cands = [(col, v) for col, v in cands if v is not None]
        keyed = sorted((k, v) for col, v in cands if (k := _period_key(col)) is not None)
        if keyed:
            return [v for _, v in keyed][-(12 if any(k[1] != 5 for k, _ in keyed) else 3):]
        return [v for _, v in cands][:12][::-1]
    return []


def avg3(raw, kind: str, lo: float, hi: float):
    """Trung bình 3 năm của P/B hoặc P/E (bỏ giá trị âm/ngoại lai); cần tối thiểu 3 điểm, ngược lại trả None."""
    vals = [v for v in _history(raw, kind) if lo < v < hi]
    return float(sum(vals) / len(vals)) if len(vals) >= 3 else None


def _ratio_calls(sym: str):
    def v5():
        from vnstock import Fundamental
        return Fundamental().equity(sym).ratio()

    def v5_kbs():
        from vnstock import Fundamental
        return Fundamental().equity(sym).ratio(source="kbs")

    def v5_series():
        from vnstock import Fundamental
        return Fundamental().equity(sym).ratio(orient="series")

    def legacy():
        from vnstock import Vnstock
        return Vnstock().stock(symbol=sym, source="VCI").finance.ratio(period="quarter")

    return [v5, v5_kbs, v5_series, legacy]


def fetch_ratios(sym: str, verbose: bool = False):
    """Trả về (P/B, ROE, P/E, P/B TB 3 năm, P/E TB 3 năm); thử lần lượt các cách gọi cho đến khi đủ."""
    pb = roe = pe = pb3 = pe3 = None
    for fn in _ratio_calls(sym):
        try:
            raw = _call_safely(fn)
            b, r, e_ = extract_metric(raw, "pb"), extract_metric(raw, "roe"), extract_metric(raw, "pe")
            if verbose:
                df = _flat(raw)
                print(f"  [{fn.__name__}] kích thước {df.shape} · cột: {list(df.columns)[:14]}")
                print(df.head(3).to_string()[:900])
                print(f"    -> P/B={b} · ROE={r} · P/E={e_}")
            pb = pb if pb is not None else b
            roe = roe if roe is not None else r
            pe = pe if pe is not None else e_
            pb3 = pb3 if pb3 is not None else avg3(raw, "pb", 0, 200)
            pe3 = pe3 if pe3 is not None else avg3(raw, "pe", 0, 1000)
            if verbose:
                print(f"    -> P/B TB 3N={pb3} · P/E TB 3N={pe3}")
            if None not in (pb, roe, pe, pb3, pe3):
                break
        except EF.Fatal:
            raise
        except Exception as e:  # noqa: BLE001
            if verbose:
                print(f"  [{fn.__name__}] lỗi: {type(e).__name__}: {e}")
    return pb, roe, pe, pb3, pe3


# ------------------------------------------------------------------ ĐỌC / GHI
def read_cache() -> pd.DataFrame:
    if not os.path.exists(FUND):
        return pd.DataFrame(columns=COLS)
    df = pd.read_csv(FUND, dtype={"Mã": str, "Tên công ty": str, "Cập nhật": str})
    for c in COLS:
        if c not in df:
            df[c] = None
    df["Mã"] = df["Mã"].str.upper().str.strip()
    for c in ("P/B", "ROE", "P/E", "P/B TB 3N", "P/E TB 3N"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df[COLS].drop_duplicates("Mã", keep="last")


def read_manual_names() -> dict[str, str]:
    if not os.path.exists(MANUAL_NAMES):
        return {}
    try:
        df = pd.read_csv(MANUAL_NAMES, dtype=str)
        return {str(a).strip().upper(): str(b).strip() for a, b in zip(df["Mã"], df["Tên công ty"]) if isinstance(b, str)}
    except Exception:  # noqa: BLE001
        return {}


def needs_refresh(row, today: pd.Timestamp, days: int) -> bool:
    if str(row["Cập nhật"]).strip().lower() == "tay":
        return False
    if pd.isna(row["P/B"]) and pd.isna(row["ROE"]) and pd.isna(row["P/E"]):
        return True
    d = pd.to_datetime(row["Cập nhật"], format=DATE_FMT, errors="coerce")
    return pd.isna(d) or (today - d).days >= days


# ------------------------------------------------------------------ MAIN
def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Cập nhật data/fundamentals.csv (tên công ty, P/B, ROE)")
    p.add_argument("--probe", default="", help="Chỉ thử 1 mã và in ra những gì nguồn trả về (chẩn đoán)")
    p.add_argument("--refresh-days", type=int, default=7, help="Hỏi lại P/B, ROE sau từng ấy ngày")
    p.add_argument("--sleep", type=float, default=1.0, help="Giây nghỉ giữa hai mã")
    p.add_argument("--max-minutes", type=float, default=25)
    args = p.parse_args(argv)
    EF.maybe_login()

    if args.probe:
        sym = args.probe.strip().upper()
        print(f"== Tên công ty (danh sách chung) ==")
        names = fetch_names(verbose=True)
        print(f"Tên {sym}: {names.get(sym)}")
        print(f"== P/B, ROE của {sym} ==")
        print("Kết quả (P/B, ROE, P/E, P/B TB 3N, P/E TB 3N):", fetch_ratios(sym, verbose=True))
        return 0

    try:
        symbols = [s.upper() for s in EF.universe(EF.parse_args([]))]
    except Exception as e:  # noqa: BLE001
        print(f"Không lấy được rổ mã từ eod_fetch ({e}).")
        return 1

    today = pd.Timestamp.now(tz="Asia/Ho_Chi_Minh").tz_localize(None).normalize()
    cache = read_cache().set_index("Mã")
    cache = cache.reindex(sorted(set(cache.index) | set(symbols))).astype({"Tên công ty": object, "Cập nhật": object})

    fatal = None
    try:
        names = fetch_names()
    except EF.Fatal as e:
        names, fatal = {}, str(e)
    print(f"Tên công ty lấy được: {len(names)} mã" + ("" if names else " (nguồn không trả danh sách; giữ tên cũ)"))
    for s, n in names.items():
        if s in cache.index:
            cache.loc[s, "Tên công ty"] = n
    for s, n in read_manual_names().items():
        if s in cache.index:
            cache.loc[s, "Tên công ty"] = n

    todo = [s for s in symbols if needs_refresh(cache.loc[s], today, args.refresh_days)] if not fatal else []
    print(f"Rổ {len(symbols)} mã · cần hỏi lại P/B, ROE: {len(todo)} mã")
    t0, fresh, failed = time.time(), {}, []
    for i, s in enumerate(todo, 1):
        if time.time() - t0 > args.max_minutes * 60:
            print("Quá thời gian, dừng; phần còn lại sẽ làm ở lần chạy sau.")
            break
        try:
            pb, roe, pe, pb3, pe3 = fetch_ratios(s)
        except EF.Fatal as e:
            fatal = str(e)
            print(f"Dừng: {e}")
            break
        if pb is None and roe is None and pe is None:
            failed.append(s)
            print(f"  ✗ {s}: nguồn không trả P/B, ROE", flush=True)
        else:
            fresh[s] = (pb, roe, pe, pb3, pe3)
        if i % 20 == 0:
            print(f"  ... {i}/{len(todo)}", flush=True)
        time.sleep(args.sleep)

    # ROE có nguồn trả dạng tỷ lệ (0,15) thay vì phần trăm (15): đổi về phần trăm
    roes = [abs(v[1]) for v in fresh.values() if v[1] is not None]
    scale = 100.0 if roes and float(pd.Series(roes).median()) < 1.5 else 1.0
    for s, (pb, roe, pe, pb3, pe3) in fresh.items():
        cache.loc[s, "P/B"] = pb if pb is not None and 0 < pb < 200 else float("nan")
        cache.loc[s, "ROE"] = roe * scale if roe is not None else float("nan")
        cache.loc[s, "P/B TB 3N"] = pb3 if pb3 is not None else float("nan")
        cache.loc[s, "P/E TB 3N"] = pe3 if pe3 is not None else float("nan")
        cache.loc[s, "P/E"] = pe if pe is not None and 0 < pe < 1000 else float("nan")
        cache.loc[s, "Cập nhật"] = today.strftime(DATE_FMT)

    out = cache.reset_index().rename(columns={"index": "Mã"})[COLS]
    out = out[out["Mã"].isin(symbols) | out["Tên công ty"].notna()].sort_values("Mã")
    os.makedirs("data", exist_ok=True)
    out.round({"P/B": 2, "ROE": 1, "P/E": 1, "P/B TB 3N": 2, "P/E TB 3N": 1}).to_csv(FUND, index=False)
    n_pb, n_roe, n_nm = int(out["P/B"].notna().sum()), int(out["ROE"].notna().sum()), int(out["Tên công ty"].notna().sum())
    n_pe = int(out["P/E"].notna().sum())
    print(f"Xong: tên {n_nm} · P/B {n_pb} · ROE {n_roe} · P/E {n_pe} / {len(symbols)} mã · lỗi {len(failed)}"
          + (f" ({', '.join(failed[:15])}{'...' if len(failed) > 15 else ''})" if failed else "")
          + (f" · DỪNG: {fatal}" if fatal else ""))
    return 0 if (n_pb or n_roe or n_nm) else 1


if __name__ == "__main__":
    sys.exit(main())
