# -*- coding: utf-8 -*-
"""Read-only production market panel: EOD first; DNSE only after explicit verification.

Designed to add a quote strip to the existing Streamlit app without changing
its trading analytics, EOD updater, CSV data, or private portfolio state.
"""
from __future__ import annotations

import csv
import json
import math
import os
import time
from datetime import datetime, date, time as daytime
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import streamlit as st

HERE = Path(__file__).resolve().parent
SNAPSHOT_KEY = "min:market:snapshot:v1"
MARKET_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def _parse_date(value):
    s = str(value or "").strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _parse_price(value):
    s = str(value or "").strip().replace(" ", "")
    if not s:
        return None
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        p = float(s)
        return p if math.isfinite(p) and p > 0 else None
    except ValueError:
        return None


@st.cache_data(ttl=300, show_spinner=False, max_entries=4)
def _latest_eod(csv_path: str, mtime_ns: int):
    """Read-only scan; returns last valid close by symbol and actual trading date."""
    del mtime_ns
    result = {}
    today = datetime.now(MARKET_TZ).date()
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        required = {"Mã", "Ngày", "Giá đóng cửa"}
        if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
            raise ValueError("EOD_CSV_UNEXPECTED_COLUMNS")
        for row in reader:
            symbol = (row.get("Mã") or "").strip().upper()
            day = _parse_date(row.get("Ngày"))
            close = _parse_price(row.get("Giá đóng cửa"))
            if not symbol or day is None or close is None or day > today:
                continue
            old = result.get(symbol)
            if old is None or day >= old[0]:
                result[symbol] = (day, close)
    return result


def _get_secret(name):
    value = os.environ.get(name, "").strip()
    if value:
        return value
    try:
        return str(st.secrets.get(name, "")).strip()
    except (FileNotFoundError, KeyError, AttributeError, OSError):
        return ""


@st.cache_data(ttl=10, show_spinner=False, max_entries=2)
def _get_redis_snapshot(url: str, token: str):
    """REST GET only. Never requests DNSE credentials or writes to Redis."""
    parsed = urlparse(url)
    if (parsed.scheme != "https" or not parsed.hostname or
            not parsed.hostname.endswith(".upstash.io") or
            parsed.username or parsed.password or parsed.port or not token):
        return None, "REDIS_NOT_CONFIGURED"
    payload = json.dumps(["GET", SNAPSHOT_KEY]).encode("utf-8")
    req = Request(
        url.rstrip("/"), data=payload,
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=3) as response:
            data = json.loads(response.read(3_000_000))
        value = data.get("result")
        if value is None:
            return None, "REDIS_SNAPSHOT_EMPTY"
        if isinstance(value, str):
            value = json.loads(value)
        if not isinstance(value, dict):
            return None, "REDIS_SNAPSHOT_BAD_FORMAT"
        return value, "REDIS_CONNECTED"
    except Exception:
        # Never print REST responses or token. EOD remains the safe fallback.
        return None, "REDIS_READ_UNAVAILABLE"


def _trading_now(now):
    t = now.timetz().replace(tzinfo=None)
    return now.weekday() < 5 and ((daytime(9, 0) <= t <= daytime(11, 30)) or
                                  (daytime(13, 0) <= t <= daytime(14, 45)))


def _valid_live_quote(symbol: str, eod_close: float | None, snapshot: dict, now_epoch: float, permitted: bool):
    if not permitted or not _trading_now(datetime.now(MARKET_TZ)):
        return None
    if not isinstance(snapshot, dict) or snapshot.get("quote_unit") != "nghin_vnd":
        return None
    item = (snapshot.get("quotes") or {}).get(symbol) or {}
    try:
        price = float(item["price_kvnd"])
        stamp = float(item["received_at"])
        if not (math.isfinite(price) and 0 < price and 0 <= now_epoch - stamp <= 120):
            return None
        if eod_close is not None and not (0.7 <= price / eod_close <= 1.3):
            return None
        return price
    except (ValueError, TypeError, KeyError, ZeroDivisionError, OverflowError):
        return None


def _valid_live_index(snapshot: dict, now_epoch: float, permitted: bool):
    if not permitted or not _trading_now(datetime.now(MARKET_TZ)):
        return None
    item = ((snapshot or {}).get("indices") or {}).get("VNINDEX") or {}
    try:
        val = float(item["value"])
        stamp = float(item["received_at"])
        if math.isfinite(val) and val > 0 and 0 <= now_epoch - stamp <= 120:
            return val
    except (ValueError, TypeError, KeyError, OverflowError):
        pass
    return None


def _render():
    with st.expander("📈 Giá thị trường | EOD + DNSE", expanded=True):
        st.caption("Giá đóng cửa phiên gần nhất luôn có ưu tiên an toàn. DNSE chỉ hiển thị nếu dữ liệu đang trong phiên, đúng đơn vị và đã xác minh.")
        stock_path = HERE / "data" / "eod_prices.csv"
        index_path = HERE / "data" / "index_prices.csv"
        stock = {}
        index = {}
        errors = []
        for path, target in ((stock_path, "stock"), (index_path, "index")):
            if not path.is_file():
                if target == "stock":
                    errors.append("Không tìm thấy data/eod_prices.csv trên máy chủ Streamlit")
                continue
            try:
                rows = _latest_eod(str(path), path.stat().st_mtime_ns)
                if target == "stock":
                    stock = rows
                else:
                    index = rows
            except Exception:
                errors.append("Không đọc được dữ liệu " + target + " (cấu trúc CSV chưa khớp)")

        url = _get_secret("UPSTASH_REDIS_REST_URL")
        token = _get_secret("UPSTASH_REDIS_REST_TOKEN")
        snapshot, status = _get_redis_snapshot(url, token) if url and token else (None, "REDIS_NOT_CONFIGURED")
        verified = _get_secret("DNSE_PRICE_UNIT_VERIFIED").lower() == "true"
        now_epoch = time.time()

        if errors:
            for msg in errors:
                st.warning(msg + ". Không tạo giá giả.")

        requested = st.text_input("Mã theo dõi", value="HPG,MBB,VIX", key="min_eod_dnse_symbols_v1")
        symbols = list(dict.fromkeys(x.strip().upper() for x in requested.split(",") if x.strip()))[:18]
        for offset in range(0, len(symbols), 4):
            columns = st.columns(min(4, len(symbols) - offset))
            for col, sym in zip(columns, symbols[offset:offset + 4]):
                with col:
                    baseline = stock.get(sym)
                    d = baseline[0] if baseline else None
                    close = baseline[1] if baseline else None
                    live = _valid_live_quote(sym, close, snapshot or {}, now_epoch, verified)
                    show = live if live is not None else close
                    st.metric(sym, f"{show:,.2f}" if show is not None else "—")
                    if live is not None:
                        st.caption("DNSE realtime · nghìn đồng/cp")
                    elif d is not None:
                        st.caption(f"EOD {d:%d/%m/%Y} · nghìn đồng/cp")
                    else:
                        st.caption("Chưa có giá đóng cửa")

        vn = index.get("VNINDEX")
        vni_live = _valid_live_index(snapshot or {}, now_epoch, verified)
        vni = vni_live if vni_live is not None else (vn[1] if vn else None)
        st.metric("VNINDEX", f"{vni:,.2f}" if vni is not None else "—")
        if vni_live is not None:
            st.caption("VNINDEX · DNSE trong phiên")
        elif vn:
            st.caption(f"VNINDEX · EOD {vn[0]:%d/%m/%Y}")
        else:
            st.caption("VNINDEX · chưa có dữ liệu chỉ số cuối phiên trong data/index_prices.csv")

        last_day = max((item[0] for item in stock.values()), default=None)
        if last_day:
            st.caption(f"Dữ liệu EOD gần nhất trong file: {last_day:%d/%m/%Y} · {len(stock)} mã")
            if (datetime.now(MARKET_TZ).date() - last_day).days > 4:
                st.warning("File EOD có thể chưa cập nhật; hãy kiểm tra đồng bộ dữ liệu cuối phiên hiện có.")
        st.caption("Redis: " + status + (" · DNSE: đã mở sau xác minh" if verified else " · DNSE: chỉ đọc, chưa thay giá EOD"))
        if status == "REDIS_CONNECTED" and snapshot:
            st.caption("Worker publish: " + str(snapshot.get("publisher_at") or "Chưa có") +
                       f" · quotes={len(snapshot.get('quotes') or {})} · indices={len(snapshot.get('indices') or {})}")


def render_market_price_panel():
    """Entrypoint called once by app.py. Only new quote panel, no core data mutations."""
    _render()


# Streamlit's fragments refresh only this panel, not the rest of the heavy app.
if hasattr(st, "fragment"):
    render_market_price_panel = st.fragment(run_every="20s")(render_market_price_panel)
