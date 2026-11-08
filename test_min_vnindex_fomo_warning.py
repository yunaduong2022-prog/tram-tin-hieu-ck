"""Regression tests for concise VNINDEX FOMO warning."""
import unittest
import numpy as np
import pandas as pd
import vnindex_auto as A

class FomoTests(unittest.TestCase):
    def sample(self):
        dates = pd.bdate_range("2026-08-01", periods=60)
        data = pd.DataFrame({
            "MSR": np.linspace(10, 14, 60),
            "STB": np.linspace(15, 20, 60),
            "AAA": np.linspace(20, 21, 60),
        }, index=dates)
        return dates, data

    def test_only_codes_no_percent_per_stock(self):
        dates, frame = self.sample()
        items = A.fomo_warning_items({"close": frame}, dates[-1])
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["text"],
            "Tránh FOMO mua cổ phiếu đã tăng trên 30% từ đáy 60 phiên: MSR, STB.")
        self.assertEqual(items[0]["subs"], [])

    def test_no_qualifying_codes_hides_warning(self):
        dates, frame = self.sample()
        frame["MSR"] = 10
        frame["STB"] = 15
        self.assertEqual(A.fomo_warning_items({"close": frame}, dates[-1]), [])

    def test_no_future_data(self):
        dates = pd.bdate_range("2026-08-01", periods=60)
        frame = pd.DataFrame({"MSR": [10.0] * 59 + [20.0]}, index=dates)
        self.assertEqual(A.fomo_warning_items({"close": frame}, dates[-2]), [])

    def test_missing_data_or_insufficient_history(self):
        self.assertEqual(A.fomo_warning_items(None, pd.Timestamp("2026-11-06")), [])
        dates = pd.bdate_range("2026-10-01", periods=20)
        frame = pd.DataFrame({"MSR": np.linspace(10, 20, 20)}, index=dates)
        self.assertEqual(A.fomo_warning_items({"close": frame}, dates[-1]), [])

    def test_exactly_30_percent_not_flagged(self):
        dates = pd.bdate_range("2026-08-01", periods=60)
        frame = pd.DataFrame({"MSR": [10.0] * 59 + [13.0]}, index=dates)
        self.assertEqual(A.fomo_warning_items({"close": frame}, dates[-1]), [])

if __name__ == "__main__":
    unittest.main()
