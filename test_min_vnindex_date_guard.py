"""Regression tests for VNINDEX date selection and R2 downgrade protection."""
from __future__ import annotations

import csv
from datetime import date
from pathlib import Path
import tempfile
import unittest

import pandas as pd

from vnindex_freshness_guard import merge_index_candidates
from vnindex_market_cap import capitalization_bil, filtered_top_codes, load_shares
from r2_bridge import _preserve_newer_local_eod

FIELDS = ["Mã", "Ngày", "Giá mở cửa", "Giá cao nhất", "Giá thấp nhất", "Giá đóng cửa", "Khối lượng khớp lệnh"]
OHLC = FIELDS[2:6]
VOL = FIELDS[6]


def candles(*dates: str, code: str = "VNINDEX", price: float = 1725.36):
    return pd.DataFrame([[code, d, price, price + 5, price - 5, price, 1_000_000]
                         for d in dates], columns=FIELDS)


class TestDateGuard(unittest.TestCase):
    def choose(self, *sources):
        return merge_index_candidates(list(sources), {"VNINDEX"}, OHLC, VOL)

    def test_stale_index_cannot_override_newer_eod(self):
        index = candles("30/10/2026", price=1741.62)
        eod = candles("30/10/2026", "02/11/2026", "06/11/2026")
        out = self.choose(("raw EOD", eod), ("index_prices.csv", index))
        self.assertEqual(out["Ngày"].iloc[-1], pd.Timestamp("2026-11-06"))
        self.assertEqual(out.attrs["latest_source"], "raw EOD")
        self.assertEqual(len(out), 3)
        self.assertEqual(out.iloc[0]["Giá đóng cửa"], 1741.62)

    def test_newer_index_wins_and_preserves_history(self):
        old = candles("30/10/2026")
        idx = candles("30/10/2026", "06/11/2026")
        out = self.choose(("raw EOD", old), ("index_prices.csv", idx))
        self.assertEqual(out.attrs["latest_source"], "index_prices.csv")
        self.assertEqual(len(out), 2)

    def test_index_priority_on_same_session(self):
        raw = candles("06/11/2026", price=1000)
        index = candles("06/11/2026", price=1725.36)
        out = self.choose(("raw EOD", raw), ("index_prices.csv", index))
        self.assertEqual(out["Giá đóng cửa"].iloc[-1], 1725.36)

    def test_invalid_and_non_index_rows_ignored(self):
        d = candles("06/11/2026", code="VND")
        self.assertTrue(self.choose(("raw EOD", d)).empty)
        bad = candles("bad date")
        self.assertTrue(self.choose(("raw EOD", bad)).empty)

    def test_missing_volume_can_be_normalized(self):
        d = candles("06/11/2026").drop(columns=[VOL])
        out = self.choose(("raw EOD", d))
        self.assertEqual(out[VOL].iloc[0], 0)

    def write(self, path: Path, entries: list[tuple[str, str, float]]):
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS)
            writer.writeheader()
            for code, day, price in entries:
                writer.writerow(dict(zip(FIELDS, [code, day, price, price+1, price-1, price, 1000000])))

    def test_r2_index_cannot_downgrade_new_local_candle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            local, remote = root/"local.csv", root/"r2.csv"
            self.write(local, [("VNINDEX", "30/10/2026", 1741.62),
                               ("VNINDEX", "06/11/2026", 1725.36)])
            self.write(remote, [("VNINDEX", "30/10/2026", 1741.62)])
            output = _preserve_newer_local_eod(local, remote, root)
            with Path(output).open(encoding="utf-8") as f:
                vals = list(csv.DictReader(f))
            self.assertEqual(len(vals), 2)
            self.assertIn("06/11/2026", [x["Ngày"] for x in vals])
            with remote.open(encoding="utf-8") as f:
                self.assertEqual(len(list(csv.DictReader(f))), 1)  # no edit to R2 file

    def test_r2_newer_index_is_respected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            local, remote = root/"local.csv", root/"r2.csv"
            self.write(local, [("VNINDEX", "30/10/2026", 1741.62)])
            self.write(remote, [("VNINDEX", "30/10/2026", 1741.62),
                                ("VNINDEX", "06/11/2026", 1725.36)])
            result = _preserve_newer_local_eod(local, remote, root)
            self.assertEqual(result, remote)

    def test_cap_filter_still_excludes_bms(self):
        rows = [{"Mã":"BMS", "Giá":11.9}, {"Mã":"VIX", "Giá":13.35}]
        shares = {"BMS":215148036, "VIX":1458000000}
        self.assertAlmostEqual(capitalization_bil(11.9, shares["BMS"]), 2560.261628, places=5)
        self.assertEqual(filtered_top_codes(rows, shares, 5000), ["VIX"])

    def test_no_share_data_never_passes(self):
        self.assertEqual(filtered_top_codes([{"Mã":"BMS", "Giá":11.9}], {}, 5000), [])

    def test_main_shares_bms_when_available(self):
        path = Path(__file__).parent / "data" / "shares_outstanding.csv"
        if path.exists():
            self.assertEqual(load_shares(path, as_of=date(2026,11,6)).get("BMS"), 215148036)

    def test_literal_guard_is_active(self):
        source = (Path(__file__).parent / "r2_bridge.py").read_text(encoding="utf-8")
        self.assertIn("if name in ('data/eod_prices.csv', 'data/index_prices.csv') and local.is_file():", source)

    def test_freshness_is_used_in_render(self):
        text = (Path(__file__).parent / "vnindex_view.py").read_text(encoding="utf-8")
        self.assertIn("merge_index_candidates", text)
        self.assertIn("Bộ lọc vốn hóa", text)
        self.assertIn("index_mtime", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
