
from datetime import timedelta
import pandas as pd

# Vietnam exchange trading holidays for 2026.
# Sources:
# HOSE notice 2294/TB-SGDHCM and updated New Year notice.
# HNX notice 4892/TB-SGDHN, November 10, 2026.
# VSDC notice 3043/TB-VSDC, July 21, 2026.
# Official sources:
# https://vsdc.vn/vi/ad/198399
# https://vsdc.vn/vi/ad1/202680
# https://knowledge.hnx.vn/vi-vn/chi-tiet-lich-nghi-gd-60023839.html?_page=1

HOLIDAYS = frozenset({
    "2026-01-01",
    "2026-01-02",
    "2026-02-16",
    "2026-02-17",
    "2026-02-18",
    "2026-02-19",
    "2026-02-20",
    "2026-04-27",
    "2026-04-30",
    "2026-05-01",
    "2026-08-31",
    "2026-09-01",
    "2026-09-02",
    "2026-11-24",
})

VERIFIED_YEARS = frozenset({2026})

def local_timestamp(value=None):
    if value is None:
        value = pd.Timestamp.now(tz="Asia/Ho_Chi_Minh")

    value = pd.Timestamp(value)

    if pd.isna(value):
        raise ValueError("INVALID_DATE")

    if value.tzinfo is not None:
        value = value.tz_convert(
            "Asia/Ho_Chi_Minh"
        ).tz_localize(None)

    return value

def is_trading_day(value):
    day = local_timestamp(value).normalize()

    return (
        day.dayofweek < 5
        and day.strftime("%Y-%m-%d") not in HOLIDAYS
    )

def calendar_verified(value):
    return local_timestamp(value).year in VERIFIED_YEARS

def previous_session(value):
    day = local_timestamp(value).normalize()

    for _ in range(366):
        day -= pd.Timedelta(days=1)

        if is_trading_day(day):
            return day

    raise RuntimeError("PREVIOUS_SESSION_NOT_FOUND")

def expected_session(now=None, cutoff=(15, 30)):
    now = local_timestamp(now)
    day = now.normalize()

    if (
        is_trading_day(day)
        and (now.hour, now.minute) >= cutoff
    ):
        return day

    return previous_session(day)

def add_sessions(value, count):
    day = local_timestamp(value).normalize()

    if not is_trading_day(day):
        raise ValueError("START_NOT_TRADING_DAY")

    if count < 0:
        raise ValueError("NEGATIVE_SESSION_COUNT")

    while count:
        day += pd.Timedelta(days=1)

        if not calendar_verified(day):
            raise ValueError("CALENDAR_YEAR_NOT_VERIFIED")

        if is_trading_day(day):
            count -= 1

    return day
