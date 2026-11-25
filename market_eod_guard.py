
import pandas as pd
import market_calendar as MC

def expected_eod(now=None):
    return MC.expected_session(
        now,
        cutoff=(15, 30)
    )

def stale(latest, now=None):
    try:
        if pd.isna(latest):
            return True

        day = MC.local_timestamp(latest).normalize()
        current = MC.local_timestamp(now)
        expected = expected_eod(current)

        # Fail closed when an annual calendar is unverified.
        if not MC.calendar_verified(current):
            return True

        if not MC.calendar_verified(expected):
            return True

        if not MC.is_trading_day(day):
            return True

        return day != expected

    except (TypeError, ValueError, OverflowError):
        return True
