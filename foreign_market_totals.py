
from pathlib import Path
import pandas as pd
import streamlit as st
import plotly.express as px

from vnindex_institutional_flow import _market_proprietary

ROOT = Path("data")
PERIODS = {
    "Phien": 1,
    "Tuan": 5,
    "Thang": 21,
    "Quy": 63
}

LABELS = {
    "Phien": "Phi\u00ean",
    "Tuan": "Tu\u1ea7n",
    "Thang": "Th\u00e1ng",
    "Quy": "Qu\u00fd"
}

def money(value):
    return f"{value / 1e9:+,.2f}"

def render():
    st.subheader(
        "T\u1ed5ng giao d\u1ecbch kh\u1ed1i ngo\u1ea1i VNINDEX"
    )
    st.caption(
        "CafeF | VND quy \u0111\u1ed5i sang t\u1ef7 \u0111\u1ed3ng"
    )

    path = ROOT / "foreign_vnindex_flow.csv"

    if not path.is_file():
        st.info(
            "Ch\u01b0a c\u00f3 d\u1eef li\u1ec7u t\u1ed5ng "
            "kh\u1ed1i ngo\u1ea1i CafeF tr\u00ean R2."
        )
        return

    try:
        idx = pd.read_csv(
            ROOT / "index_prices.csv",
            encoding="utf-8-sig",
            usecols=["M\u00e3","Ng\u00e0y"]
        )
        calendar = pd.to_datetime(
            idx.loc[
                idx["M\u00e3"].astype(str)
                .str.upper().str.strip().eq("VNINDEX"),
                "Ng\u00e0y"
            ],
            format="mixed",
            dayfirst=True,
            errors="coerce"
        ).dropna().dt.normalize().drop_duplicates().sort_values()
    except (OSError, ValueError, KeyError):
        st.warning("VNINDEX calendar unavailable.")
        return

    if calendar.empty:
        return

    a,b = st.columns(2)

    day = a.selectbox(
        "Ng\u00e0y k\u1ebft th\u00fac",
        list(calendar.dt.date.iloc[::-1]),
        format_func=lambda d: d.strftime("%d/%m/%Y"),
        key="cafef_foreign_market_day"
    )

    period = b.radio(
        "Khung th\u1eddi gian",
        list(PERIODS),
        format_func=lambda x: LABELS[x],
        horizontal=True,
        key="cafef_foreign_market_period"
    )

    n = PERIODS[period]

    dates = list(
        calendar[calendar.le(pd.Timestamp(day))].tail(n)
    )

    summary = _market_proprietary(path, dates)

    found = summary["found"] if summary else 0

    if summary and found == n and len(dates) == n:
        a,b,c = st.columns(3)
        a.metric("T\u1ed5ng mua (t\u1ef7)",money(summary["buy"]))
        b.metric("T\u1ed5ng b\u00e1n (t\u1ef7)",money(summary["sell"]))
        c.metric("Gi\u00e1 tr\u1ecb r\u00f2ng (t\u1ef7)",money(summary["net"]))
    else:
        st.warning(
            f"CafeF: {found}/{n} phi\u00ean c\u00f3 d\u1eef li\u1ec7u. "
            "Ch\u01b0a \u0111\u1ee7 \u0111\u1ec3 t\u00ednh t\u1ed5ng to\u00e0n k\u1ef3."
        )

    hist = []

    for date in dates:
        report = _market_proprietary(path,[date])
        if report:
            hist.append({
                "Date": date.strftime("%d/%m/%Y"),
                "Net": report["net"]/1e9
            })

    if hist:
        h = pd.DataFrame(hist)

        fig = px.bar(
            h,
            x="Date",
            y="Net",
            text="Net",
            labels={
                "Date":"Ng\u00e0y",
                "Net":"R\u00f2ng (t\u1ef7 \u0111\u1ed3ng)"
            }
        )

        fig.update_traces(
            marker_color=[
                "#229970" if x >= 0 else "#dd5660"
                for x in h.Net
            ],
            texttemplate="%{text:+,.2f}",
            textposition="outside",
            cliponaxis=False,
            width=0.28 if len(h)==1 else 0.65
        )

        fig.update_xaxes(type="category")

        fig.update_layout(
            height=300,
            showlegend=False,
            margin=dict(t=30,b=10)
        )

        st.plotly_chart(
            fig,use_container_width=True,
            key="cafef_foreign_market_chart"
        )

    st.caption(
        "T\u1ed5ng VNINDEX CafeF v\u00e0 m\u1eabu c\u1ed5 phi\u1ebfu SSI "
        "l\u00e0 hai ph\u1ea1m vi d\u1eef li\u1ec7u ri\u00eang."
    )
    st.divider()
