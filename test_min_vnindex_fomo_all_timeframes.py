"""Regression checks: the VNINDEX FOMO note is identical in D/W/M/Q."""
import unittest
import numpy as np
import pandas as pd
import vnindex_auto as A


class AllTimeframeWarningTests(unittest.TestCase):
    @staticmethod
    def sample():
        dates = pd.bdate_range("2026-08-01", periods=60)
        data = pd.DataFrame({
            "MSR": np.linspace(10, 14, 60),
            "STB": np.linspace(15, 20, 60),
            "AAA": np.linspace(20, 21, 60),
        }, index=dates)
        return dates, {"close": data}

    @staticmethod
    def old_report():
        return [{"name": "TIN TỨC", "items": []},
                {"name": "DÒNG TIỀN", "items": []},
                {"name": "HÀNH ĐỘNG", "items": []}]

    def test_all_four_timeframes_same_note(self):
        dates, panel = self.sample()
        results = {}
        for tf in ("D", "W", "M", "Q"):
            # Each timeframe may have a previously cached three-section report.
            sections = A.refresh_fomo_sections(self.old_report(), panel, dates[-1])
            self.assertEqual(len(sections), 4, tf)
            self.assertEqual(sections[-1]["name"], "LƯU Ý", tf)
            results[tf] = sections[-1]["items"][0]["text"]
        self.assertEqual(len(set(results.values())), 1)
        self.assertEqual(results["D"],
            "Tránh FOMO mua cổ phiếu đã tăng trên 30% từ đáy 60 phiên: MSR, STB.")

    def test_replaces_old_cached_warning(self):
        dates, panel = self.sample()
        old = self.old_report() + [{"name": "LƯU Ý", "items": [{"text": "OLD"}]}]
        sections = A.refresh_fomo_sections(old, panel, dates[-1])
        self.assertEqual(len(sections), 4)
        self.assertNotIn("OLD", str(sections))
        self.assertEqual(old[-1]["items"][0]["text"], "OLD")

    def test_hides_warning_when_no_qualifiers(self):
        dates, panel = self.sample()
        flat = {"close": panel["close"].copy()}
        flat["close"]["MSR"] = 10
        flat["close"]["STB"] = 15
        old = self.old_report() + [{"name": "LƯU Ý", "items": [{"text": "OLD"}]}]
        sections = A.refresh_fomo_sections(old, flat, dates[-1])
        self.assertEqual([s["name"] for s in sections], ["TIN TỨC", "DÒNG TIỀN", "HÀNH ĐỘNG"])

    def test_no_future_data(self):
        dates, panel = self.sample()
        close = panel["close"].copy()
        close["MSR"] = [10.0] * 59 + [20.0]
        close["STB"] = [15.0] * 59 + [24.0]
        sections = A.refresh_fomo_sections(self.old_report(), {"close": close}, dates[-2])
        self.assertEqual(len(sections), 3)

    def test_no_mutation_of_cached_report(self):
        dates, panel = self.sample()
        original = self.old_report()
        updated = A.refresh_fomo_sections(original, panel, dates[-1])
        self.assertEqual(len(original), 3)
        self.assertEqual(len(updated), 4)
        self.assertIsNot(original, updated)

    def test_missing_panel_does_not_break_render(self):
        _, panel = self.sample()
        result = A.refresh_fomo_sections(self.old_report(), None, pd.Timestamp("2026-11-06"))
        self.assertEqual(len(result), 3)


if __name__ == "__main__":
    unittest.main()
