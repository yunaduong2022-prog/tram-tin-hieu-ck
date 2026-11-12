"""VNINDEX macro context: verified Yahoo daily bars, rule-based commentary, compact cards.

Separate from VNINDEX EOD and signal logic.  No SDK, secrets, or persistence.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import theme as TH

SOURCES = (
    ("USD/VND", "USDVND=X", "https://finance.yahoo.com/quote/USDVND=X/"),
    ("NASDAQ Composite", "^IXIC", "https://finance.yahoo.com/quote/%5EIXIC/"),
)
USER_AGENT = "Mozilla/5.0"


class MacroDataUnavailable(ValueError):
    """An outside quote could not be verified; never fabricate missing bars."""


@st.cache_data(ttl=1800, show_spinner=False)
def fetch_daily(symbol: str) -> pd.DataFrame:
    """Fetch six months of 1D OHLC, sorted and stamped in the exchange timezone.

    Yahoo chart v8 is an unofficial, rate-limited endpoint: failure is handled
    independently per card. A cached quote is not presented as streaming/live.
    """
    if symbol not in {item[1] for item in SOURCES}:
        raise MacroDataUnavailable("Mã nguồn không được hỗ trợ")
    url = ("https://query1.finance.yahoo.com/v8/finance/chart/"
           + quote(symbol, safe="") + "?range=6mo&interval=1d")
    request = Request(url, headers={"User-Agent": USER_AGENT,
                                    "Accept": "application/json"})
    try:
        with urlopen(request, timeout=9) as response:
            raw = response.read(2_000_000)
        payload = json.loads(raw)
        chart = payload.get("chart") or {}
        error = chart.get("error")
        matches = chart.get("result") or []
        if error or not matches:
            raise MacroDataUnavailable("Dữ liệu Yahoo không sẵn sàng")
        obj = matches[0]
        timestamps = obj.get("timestamp") or []
        quotes = (obj.get("indicators") or {}).get("quote") or []
        if not timestamps or not quotes:
            raise MacroDataUnavailable("Nguồn chưa trả đủ lịch sử")
        series = quotes[0]
        tzname = (obj.get("meta") or {}).get("exchangeTimezoneName") or "UTC"
        try:
            dates = pd.to_datetime(timestamps, unit="s", utc=True).tz_convert(tzname)
        except (TypeError, ValueError, KeyError):
            dates = pd.to_datetime(timestamps, unit="s", utc=True)
        rows = pd.DataFrame({
            "date": dates.date,
            "open": series.get("open", []),
            "high": series.get("high", []),
            "low": series.get("low", []),
            "close": series.get("close", []),
        })
        for col in ("open", "high", "low", "close"):
            rows[col] = pd.to_numeric(rows[col], errors="coerce")
        rows["date"] = pd.to_datetime(rows["date"], errors="coerce")
        rows = (rows.replace([np.inf, -np.inf], np.nan)
                    .dropna(subset=["date", "close"])
                    .loc[lambda df: df["close"] > 0]
                    .sort_values("date")
                    .drop_duplicates(subset="date", keep="last")
                    .reset_index(drop=True))
        if len(rows) < 5:
            raise MacroDataUnavailable("Lịch sử giá không đủ để hiển thị")
        return rows
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        # The app must still render VNINDEX when an external provider blocks us.
        raise MacroDataUnavailable(type(exc).__name__) from exc


def summarize(rows: pd.DataFrame, symbol: str) -> tuple[float, float, str]:
    """Latest value, close-to-previous-bar return and cautious Vietnamese note."""
    latest = float(rows["close"].iloc[-1])
    prior = float(rows["close"].iloc[-2])
    pct = (latest / prior - 1) * 100 if prior > 0 else 0.0
    if symbol == "USDVND=X":
        if pct >= 0.3:
            note = "USD/VND tăng so với phiên trước; theo dõi áp lực tỷ giá."
        elif pct <= -0.3:
            note = "USD/VND giảm so với phiên trước; áp lực tỷ giá có dấu hiệu hạ nhiệt."
        else:
            note = "USD/VND biến động hẹp; chưa đủ tín hiệu để kết luận về chính sách tiền tệ."
    else:
        if pct >= 1:
            note = "NASDAQ tăng mạnh; tâm lý thị trường Mỹ ngắn hạn tích cực hơn."
        elif pct <= -1:
            note = "NASDAQ giảm mạnh; cần chú ý rủi ro tâm lý từ thị trường Mỹ."
        else:
            note = "NASDAQ biến động chưa lớn; tác động đến VNINDEX không thể suy ra trực tiếp."
    return latest, pct, note


def strategy_note(stats: dict) -> tuple[str, str]:
    """Neutral VNINDEX commentary derived only from verified internal EOD stats."""
    close, ma20, vol_vs = stats.get("close"), stats.get("ma20"), stats.get("vol_vs")
    if close is None or ma20 is None or not np.isfinite(float(ma20)):
        return "THEO DÕI VNINDEX", "Chưa đủ dữ liệu MA20 để đánh giá xu hướng ngắn hạn."
    if float(close) < float(ma20):
        title = "ƯU TIÊN KIỂM SOÁT RỦI RO"
        body = "VNINDEX đang dưới MA20; ưu tiên quan sát tín hiệu xác nhận và sức mạnh riêng từng cổ phiếu."
    elif vol_vs is not None and np.isfinite(float(vol_vs)) and float(vol_vs) < -5:
        title = "CHỜ XÁC NHẬN THANH KHOẢN"
        body = "VNINDEX trên MA20 nhưng khối lượng thấp hơn trung bình 20 phiên; chưa nên suy ra lực mua lan tỏa."
    else:
        title = "QUAN SÁT CỔ PHIẾU MẠNH HƠN CHỈ SỐ"
        body = "VNINDEX đang trên MA20; theo dõi thêm dòng tiền và sức mạnh tương đối trước khi đưa ra quyết định."
    return title, body


def _figure(rows: pd.DataFrame, *, symbol: str) -> go.Figure:
    """A compact 3-month mini-chart with price-only indicators."""
    frame = rows.tail(65)
    fx = symbol == "USDVND=X"
    accent = "#35C999" if fx else "#F4B23C"
    fig = go.Figure()
    if not fx and frame[["open", "high", "low", "close"]].notna().all().all():
        fig.add_trace(go.Candlestick(
            x=frame["date"], open=frame["open"], high=frame["high"],
            low=frame["low"], close=frame["close"], name="NASDAQ",
            increasing_line_color="#21BD94", decreasing_line_color="#F54F68",
            increasing_fillcolor="#21BD94", decreasing_fillcolor="#F54F68"))
    else:
        fig.add_trace(go.Scatter(x=frame["date"], y=frame["close"],
                                 mode="lines", name="USD/VND" if fx else "NASDAQ",
                                 line=dict(color=accent, width=2.2)))
    p = TH.palette()
    fig.update_layout(
        template=TH.plotly_template(), height=225,
        margin=dict(l=8, r=12, t=8, b=12),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=p["txt"], size=11), showlegend=False,
        hovermode="x unified", dragmode=False,
        xaxis=dict(showgrid=False, tickformat="Th%m", rangeslider=dict(visible=False)),
        yaxis=dict(side="right", showgrid=True, gridcolor="rgba(128,128,128,.12)",
                   tickformat=",.0f", zeroline=False),
    )
    return fig


def _render_card(title: str, symbol: str, link: str) -> None:
    with st.container(border=True):
        st.markdown(f"**{title}**")
        try:
            rows = fetch_daily(symbol)
            latest, pct, note = summarize(rows, symbol)
        except (MacroDataUnavailable, ValueError, KeyError, IndexError, TypeError) as exc:
            st.info("Chưa lấy được dữ liệu từ nguồn ngoài; không hiển thị giá thay thế.")
            st.caption(f"Nguồn: [Yahoo Finance]({link}) · {type(exc).__name__}")
            return
        st.metric("Giá gần nhất (có thể chưa chốt phiên)", f"{latest:,.0f}",
                  f"{pct:+.2f}% so với phiên trước", delta_color="off")
        st.plotly_chart(_figure(rows, symbol=symbol), use_container_width=True,
                        config={"displayModeBar": False, "scrollZoom": False})
        last_day = pd.Timestamp(rows["date"].iloc[-1]).date()
        today = datetime.now(timezone.utc).astimezone(ZoneInfo("Asia/Ho_Chi_Minh")).date()
        if (today - last_day).days > 5:
            st.warning("Dữ liệu ngoài đã cũ, không dùng nhận định để suy ra trạng thái hôm nay.")
        else:
            st.markdown(note)
        st.caption(f"Nguồn: [Yahoo Finance]({link}) · Ngày dữ liệu: {last_day:%d/%m/%Y} · Có thể trễ")


def render(index_daily: pd.DataFrame, stats: dict) -> None:
    """Draw independent panels below VNINDEX and cash-flow chart row."""
    st.markdown("#### BỐI CẢNH QUỐC TẾ · USD/VND & NASDAQ")
    try:
        from streamlit_autorefresh import st_autorefresh
        st_autorefresh(interval=30 * 60 * 1000, key="vni_macro_auto_refresh_30m")
    except ImportError:
        pass  # st.cache_data still refreshes on the next user rerun.
    left, right = st.columns(2, gap="medium")
    with left:
        _render_card(*SOURCES[0])
    with right:
        _render_card(*SOURCES[1])
    # NHNN intervention context is independent of Yahoo price moves.
    from vnindex_nhnn_fx import render_fx_interventions
    render_fx_interventions()
    headline, body = strategy_note(stats)
    with st.container(border=True):
        st.markdown(f"**{headline}**")
        st.write(body)
        st.caption("Nhận định theo quy tắc từ EOD VNINDEX, không phải tin tức hoặc khuyến nghị giao dịch. "
                   "USD/VND là báo giá tham khảo, không phải tỷ giá chính thức NHNN.")
