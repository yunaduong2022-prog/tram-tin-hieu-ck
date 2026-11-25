
import pandas as pd

def expected_eod(now=None):
    if now is None:
        now = pd.Timestamp.now(tz="Asia/Ho_Chi_Minh")

    now = pd.Timestamp(now)

    if now.tzinfo is not None:
        now = now.tz_convert(
            "Asia/Ho_Chi_Minh"
        ).tz_localize(None)

    day = now.normalize()

    if day.dayofweek >= 5 or (
        now.hour,now.minute
    ) < (15,30):
        day -= pd.Timedelta(days=1)

    while day.dayofweek >= 5:
        day -= pd.Timedelta(days=1)

    return day

def stale(latest,now=None):
    if pd.isna(latest):
        return True
    return pd.Timestamp(latest).normalize() < expected_eod(now)
