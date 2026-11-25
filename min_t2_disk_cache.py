
from pathlib import Path
import hashlib
import os
import pickle
import tempfile
import time

import pandas as pd
import numpy as np
import min_t2_buy_now as T2
import startup_accel as SC

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / "data/.startup_cache/t2_cache.pkl"

def signature(daily, asof):

    h = hashlib.sha256()

    h.update(str(pd.Timestamp(asof)).encode())
    h.update(pd.__version__.encode())
    h.update(np.__version__.encode())

    h.update(
        pd.util.hash_pandas_object(
            daily,index=True
        ).values.tobytes()
    )

    for name in (
        "engine.py",
        "min_t2_swing.py",
        "min_t2_buy_now.py",
        "min_t2_disk_cache.py"
    ):
        h.update((ROOT/name).read_bytes())

    return h.hexdigest()


def load(daily, asof):

    if not CACHE.is_file():
        return None

    try:

        with CACHE.open("rb") as f:
            package = pickle.load(f)

        if package["signature"] != signature(daily,asof):
            return None

        buy, wait = package["result"]

        if not isinstance(buy,pd.DataFrame):
            return None

        if not isinstance(wait,pd.DataFrame):
            return None

        return buy.copy(),wait.copy()

    except Exception:
        return None


def build():

    bundle = SC.load_if_valid()

    if bundle is None:
        raise RuntimeError("STARTUP_CACHE_NOT_READY")

    daily = bundle["frames"]["D"]

    date = "Ng\u00e0y"
    code = "M\u00e3"

    asof = daily[date].max()

    cached = load(daily,asof)

    if cached is not None:
        print("T2_CACHE_ALREADY_CURRENT")
        return

    print(
        "T2_SCAN_START:",
        daily[code].nunique(),
        "symbols",
        flush=True
    )

    started = time.monotonic()

    buy,wait = T2.candidates_both(daily,asof)

    assert isinstance(buy,pd.DataFrame)
    assert isinstance(wait,pd.DataFrame)

    assert not set(buy[code]) & set(wait[code])

    dates = daily.groupby(code)[date].max()

    fresh = set(
        dates[dates.eq(asof)].index
    )

    assert set(buy[code]).issubset(fresh)
    assert set(wait[code]).issubset(fresh)

    CACHE.parent.mkdir(
        parents=True,exist_ok=True
    )

    fd,tmp = tempfile.mkstemp(
        dir=CACHE.parent
    )

    try:

        with os.fdopen(fd,"wb") as f:

            pickle.dump(
                {
                    "signature":signature(daily,asof),
                    "result":(buy,wait)
                },
                f,
                protocol=pickle.HIGHEST_PROTOCOL
            )

        os.replace(tmp,CACHE)

    finally:

        if os.path.exists(tmp):
            os.remove(tmp)

    assert load(daily,asof) is not None

    print("T2_BUY_COUNT:",len(buy))
    print("T2_WAIT_COUNT:",len(wait))
    print("T2_STALE_GUARD_OK")
    print("T2_SCAN_SECONDS:",
          round(time.monotonic()-started,2))
    print("T2_CACHE_VERIFIED")


if __name__ == "__main__":
    build()
