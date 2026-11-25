import engine as E

def calculate_symbol(task):
    base, daily_keep, weekly_keep = task
    result = {}

    for tf in ("D", "W", "M"):
        frame = E.add_indicators(
            E.resample_ohlcv(base, tf)
        )

        keep = (
            daily_keep if tf == "D"
            else weekly_keep if tf == "W"
            else 0
        )

        result[tf] = (
            frame.tail(keep).copy()
            if keep else frame
        )

    return result
