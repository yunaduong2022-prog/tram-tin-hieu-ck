
import multiprocessing as mp
import os
import time
from concurrent.futures import ProcessPoolExecutor

import pandas as pd
import engine as E
import startup_accel as SC

from parallel_frame_worker import calculate_symbol


def main():

    original_extract = SC._extract_app_functions

    def extract(source):

        ns = original_extract(source)

        def build_frames(raw, ver=""):

            code = "M\u00e3"
            date = "Ng\u00e0y"

            tasks = [
                (
                    g[[code,date] + E.NUMERIC_COLS],
                    ns["DAILY_KEEP"],
                    ns["W_KEEP"]
                )
                for _,g in raw.groupby(code)
            ]

            total = len(tasks)

            workers = min(
                4,
                max(1,(os.cpu_count() or 2)-1)
            )

            print(
                f"OFFLINE_START | {total} symbols | {workers} workers",
                flush=True
            )

            started = time.monotonic()

            def collect(results):

                parts = {"D":[],"W":[],"M":[]}

                for done,result in enumerate(results,1):

                    for tf in parts:
                        parts[tf].append(
                            ns["_slim_f32"](result[tf])
                        )

                    if done % 10 == 0 or done == total:

                        elapsed = time.monotonic()-started

                        print(
                            f"PROGRESS: {done}/{total} | {elapsed:.1f}s",
                            flush=True
                        )

                frames = {
                    tf:pd.concat(p,ignore_index=True)
                    for tf,p in parts.items()
                }

                frames["D"] = E.mask_chg_gaps(frames["D"])

                for frame in frames.values():
                    ns["_slim_f32"](frame)

                return frames

            try:

                with ProcessPoolExecutor(
                    max_workers=workers,
                    mp_context=mp.get_context("spawn")
                ) as pool:

                    frames = collect(
                        pool.map(
                            calculate_symbol,
                            tasks,
                            chunksize=1
                        )
                    )

            except Exception as exc:

                print(
                    "PARALLEL_FALLBACK:",
                    type(exc).__name__,
                    str(exc),
                    flush=True
                )

                frames = collect(
                    map(calculate_symbol,tasks)
                )

            print(
                "OFFLINE_FRAMES_OK",
                flush=True
            )

            return frames

        ns["build_frames"] = build_frames

        return ns

    SC._extract_app_functions = extract

    SC.warmup()

    bundle = SC.load_if_valid()

    assert bundle is not None

    assert len(bundle["frames"]["D"]) > 0
    assert len(bundle["screener"]) > 0

    print("STARTUP_CACHE_VERIFIED",flush=True)


if __name__ == "__main__":

    mp.freeze_support()

    main()
