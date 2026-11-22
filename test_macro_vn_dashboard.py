"""Safety checks for curated macro data; runs with python -m unittest."""
import importlib
import sys
import tempfile
import types
import unittest
from pathlib import Path

import pandas as pd

# Only pure helpers are tested; Streamlit UI is independently guarded at render time.
if "streamlit" not in sys.modules:
    try:
        import streamlit  # noqa: F401
    except ImportError:
        sys.modules["streamlit"] = types.ModuleType("streamlit")

MVN = importlib.import_module("macro_vn_dashboard")


class MacroDataTests(unittest.TestCase):
    def test_official_snapshot_readable(self):
        df = MVN.read_data()
        self.assertGreaterEqual(len(df), 12)
        self.assertTrue(set(["GDP_Q", "CPI_OCT_YOY", "PUBLIC_INV_10M"]).issubset(set(df.id)))
        self.assertTrue(df.source_url.str.startswith("https://").all())

    def test_latest_gdp_quarter_and_provenance(self):
        df = MVN.read_data()
        gdp = MVN.latest(df, "GDP_Q")
        self.assertEqual(gdp["period"], "Q3/2026")
        self.assertAlmostEqual(gdp["value"], 9.95)
        self.assertIn("nso.gov.vn", gdp["source_url"])
        self.assertIsNone(MVN.latest(df, "CREDIT_YTD"))

    def test_numeric_and_units_are_not_confused(self):
        df = MVN.read_data()
        self.assertAlmostEqual(MVN.latest(df, "CPI_OCT_YOY")["value"], 5.09)
        self.assertAlmostEqual(MVN.latest(df, "CPI_10M")["value"], 4.57)
        self.assertNotEqual(MVN.latest(df, "CPI_OCT_YOY")["unit"], MVN.latest(df, "CPI_10M")["unit"])
        self.assertAlmostEqual(MVN.latest(df, "PUBLIC_INV_AMOUNT_10M")["value"], 708.57)
        self.assertEqual(MVN.latest(df, "TRADE_BALANCE_10M")["value"], -12.07)

    def test_invalid_source_and_duplicates_fail_closed(self):
        df = MVN.read_data()
        first = df.iloc[0].copy()
        self.assertGreater(len(df), 0)
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "test.csv"
            invalid = first.copy(); invalid["source_url"] = "http://example.org"
            bad = pd.DataFrame([first, first, invalid], columns=MVN.COLS)
            bad.to_csv(p, index=False)
            self.assertTrue(MVN.read_data(p).empty)
            bad = pd.DataFrame([first, invalid], columns=MVN.COLS)
            bad.to_csv(p, index=False)
            result = MVN.read_data(p)
            self.assertEqual(len(result), 1)

    def test_staleness_period_aware(self):
        from datetime import date
        df = MVN.read_data()
        self.assertFalse(MVN.stale(MVN.latest(df, "GDP_Q"), date(2026, 11, 22)))
        self.assertTrue(MVN.stale(MVN.latest(df, "GDP_Q"), date(2027, 3, 1)))
        self.assertTrue(MVN.stale(None))

    def test_international_dispatch_uses_original_renderer(self):
        from unittest.mock import Mock, patch
        st = Mock()
        st.pills.return_value = "Quốc tế"
        original = Mock()
        with patch.object(MVN, "st", st):
            MVN.render(original)
        original.assert_called_once_with()

    def test_missing_file_never_fabricates(self):
        x = MVN.read_data(Path("/absent/unknown.csv"))
        self.assertTrue(x.empty)
        self.assertEqual(MVN.value_text(None), "Chưa có số liệu")

    def test_sections_preserve_international(self):
        self.assertIn("Quốc tế", MVN.SECTIONS)
        self.assertIn("Tiền tệ & Thanh khoản", MVN.SECTIONS)


if __name__ == "__main__":
    unittest.main()
