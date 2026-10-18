"""Optional Vnstock connector for live-ish Vietnamese equity data.

Historical OHLCV is cached by the caller; the quote board is polled separately.
This is REST polling, not a guaranteed exchange-direct WebSocket feed.
"""
from __future__ import annotations
import pandas as pd

ALIASES = {
    "Mã": ["symbol", "ticker", "stock_code", "code"],
    "Ngày": ["time", "date", "trading_date", "datetime"],
    "Giá mở cửa": ["open", "open_price", "o"],
    "Giá cao nhất": ["high", "high_price", "h"],
    "Giá thấp nhất": ["low", "low_price", "l"],
    "Giá đóng cửa": ["close", "close_price", "match_price", "price", "last_price", "last"],
    "Khối lượng khớp lệnh": ["volume", "total_volume", "match_volume", "matched_volume", "kl"],
}

def _rename(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    lowmap = {str(c).strip().lower(): c for c in out.columns}
    ren = {}
    for target, aliases in ALIASES.items():
        if target in out.columns:
            continue
        for a in aliases:
            if a in lowmap:
                ren[lowmap[a]] = target
                break
    return out.rename(columns=ren)

def _ohlcv_retry(market, symbol: str, start: str):
    """Gọi ohlcv; nếu nguồn báo giới hạn tần suất thì chờ rồi thử lại tối đa 2 lần."""
    import time
    last = None
    for wait in (0, 20, 40):
        if wait:
            time.sleep(wait)
        try:
            return market.equity(symbol).ohlcv(start=start, source="vci")
        except Exception as e:
            last = e
            if not any(k in str(e).lower() for k in ("429", "rate", "limit", "too many", "quota")):
                raise
    raise last

def fetch_history(symbols: list[str], start: str = "2024-01-01") -> pd.DataFrame:
    """Fetch daily OHLCV history. One provider request per ticker."""
    try:
        from vnstock import Market
    except ImportError as e:
        raise RuntimeError("Chưa cài vnstock. Chạy: pip install -r requirements.txt") from e
    pieces = []
    errors = []
    market = Market()
    for symbol in symbols:
        try:
            raw = _ohlcv_retry(market, symbol, start)
            raw = _rename(raw)
            if raw.empty:
                errors.append(f"{symbol}: nguồn không trả dữ liệu lịch sử")
                continue
            raw["Mã"] = symbol
            if "Ngày" not in raw:
                errors.append(f"{symbol}: thiếu cột thời gian")
                continue
            raw["Ngày"] = pd.to_datetime(raw["Ngày"], errors="coerce", utc=True).dt.tz_convert("Asia/Ho_Chi_Minh").dt.tz_localize(None)
            for c in ["Giá mở cửa", "Giá cao nhất", "Giá thấp nhất", "Giá đóng cửa", "Khối lượng khớp lệnh"]:
                if c not in raw:
                    raw[c] = float("nan")
                raw[c] = pd.to_numeric(raw[c], errors="coerce")
            pieces.append(raw[["Mã", "Ngày", "Giá mở cửa", "Giá cao nhất", "Giá thấp nhất", "Giá đóng cửa", "Khối lượng khớp lệnh"]])
        except Exception as e:
            errors.append(f"{symbol}: {type(e).__name__}: {e}")
    if not pieces:
        raise RuntimeError("Không lấy được lịch sử. " + " | ".join(errors[:5]))
    result = pd.concat(pieces, ignore_index=True).dropna(subset=["Ngày", "Giá đóng cửa"])
    result.attrs["provider_errors"] = errors
    return result

def fetch_quote_board(symbols: list[str]) -> tuple[pd.DataFrame, str]:
    """Fetch a bulk quote board through Vnstock; source and columns vary by provider."""
    from vnstock import Market
    last_error = None
    for source in ("kbs", "vci"):
        try:
            q = Market().quote(symbols, source=source)
            q = _rename(q)
            if q is not None and not q.empty:
                return q, source.upper()
        except Exception as e:
            last_error = e
    raise RuntimeError(f"Không lấy được bảng giá từ KBS/VCI: {last_error}")

def apply_live_quotes(history: pd.DataFrame, quotes: pd.DataFrame) -> pd.DataFrame:
    """Append/update today's bar only when the quote source returns enough OHLC fields."""
    if history.empty or quotes is None or quotes.empty:
        return history
    h = history.copy()
    q = quotes.copy()
    if "Mã" not in q:
        for c in q.columns:
            if str(c).lower() in ("symbol", "ticker", "stock_code", "code"):
                q = q.rename(columns={c: "Mã"}); break
    if "Mã" not in q:
        return h
    q["Mã"] = q["Mã"].astype(str).str.upper().str.strip()
    today = pd.Timestamp.now(tz="Asia/Ho_Chi_Minh").tz_localize(None).normalize()
    additions = []
    for _, qr in q.iterrows():
        sym = qr["Mã"]
        subset = h[h["Mã"].astype(str).str.upper() == sym]
        if subset.empty:
            continue
        last_idx = subset.index[-1]
        last = h.loc[last_idx]
        vals = {}
        for col in ("Giá mở cửa", "Giá cao nhất", "Giá thấp nhất", "Giá đóng cửa", "Khối lượng khớp lệnh"):
            if col in q.columns:
                v = pd.to_numeric(pd.Series([qr[col]]), errors="coerce").iloc[0]
                if pd.notna(v):
                    vals[col] = float(v)
        # Never synthesize an OHLC candle from a last-traded price alone.
        if not all(c in vals for c in ("Giá mở cửa", "Giá cao nhất", "Giá thấp nhất", "Giá đóng cửa")):
            continue
        vals["Mã"] = sym
        vals["Ngày"] = today
        if "Khối lượng khớp lệnh" not in vals:
            vals["Khối lượng khớp lệnh"] = float(last.get("Khối lượng khớp lệnh", 0) or 0)
        if pd.Timestamp(last["Ngày"]).normalize() == today:
            for c, v in vals.items():
                if c in h.columns:
                    h.at[last_idx, c] = v
        else:
            additions.append(vals)
    if additions:
        h = pd.concat([h, pd.DataFrame(additions)], ignore_index=True)
    return h.sort_values(["Mã", "Ngày"]).reset_index(drop=True)
