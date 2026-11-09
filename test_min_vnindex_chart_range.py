"""Regression tests for the VNINDEX chart-only time-range selector."""
from __future__ import annotations

from pathlib import Path
import unittest
import pandas as pd

from vnindex_chart_range import RANGE_OPTIONS, range_start, chart_range_view


class TestVNIndexChartRanges(unittest.TestCase):
    def setUp(self):
        self.days = pd.bdate_range("2023-01-02", periods=920)
        self.frame = pd.DataFrame({
            "Ngày": self.days,
            "Giá đóng cửa": [1600.0 + n / 10 for n in range(len(self.days))],
            "MA10": [1500.0 + n / 20 for n in range(len(self.days))],
            "ST_trend": [1] * len(self.days),
            "HU_M": [1490.0 + n / 20 for n in range(len(self.days))],
            "Khối lượng khớp lệnh": [n * 100 for n in range(len(self.days))],
        })
        self.chart = {"g": self.frame.copy(), "tf": "D", "mas": (10,),
                      "labels": [f"D{n}" for n in range(len(self.days))],
                      "ticks": [(0, "old")], "extra": {"original": True}}

    def test_options_exactly_match_stock_chart(self):
        self.assertEqual(RANGE_OPTIONS, ("5D", "1M", "3M", "6M", "1Y", "2Y", "3Y", "Tất cả"))

    def test_5d_means_five_trading_sessions_not_calendar_days(self):
        self.assertEqual(range_start(self.days, "5D"), self.days[-5])
        view = chart_range_view(self.chart, self.days, "5D")
        self.assertEqual(len(view["g"]), 5)
        self.assertEqual(view["g"]["Ngày"].iloc[0], self.days[-5])
        self.assertEqual(view["labels"], self.chart["labels"][-5:])

    def test_5d_handles_less_than_five_rows(self):
        days = self.days[:3]
        self.assertEqual(range_start(days, "5D"), days[0])

    def test_time_presets_anchor_to_last_actual_eod_date(self):
        end = self.days[-1]
        for key, offset in (("1M", pd.DateOffset(months=1)),
                            ("3M", pd.DateOffset(months=3)),
                            ("6M", pd.DateOffset(months=6)),
                            ("1Y", pd.DateOffset(years=1)),
                            ("2Y", pd.DateOffset(years=2)),
                            ("3Y", pd.DateOffset(years=3))):
            with self.subTest(key=key):
                self.assertEqual(range_start(self.days, key), end - offset)
                shown = chart_range_view(self.chart, self.days, key)["g"]
                self.assertTrue((shown["Ngày"] >= end - offset).all())
                self.assertEqual(shown["Ngày"].iloc[-1], end)

    def test_all_shows_full_available_history(self):
        view = chart_range_view(self.chart, self.days, "Tất cả")
        self.assertEqual(len(view["g"]), len(self.days))
        self.assertIsNone(range_start(self.days, "Tất cả"))

    def test_no_wall_clock_reference(self):
        old = pd.bdate_range("2020-01-01", periods=60)
        self.assertEqual(range_start(old, "1M"), old[-1] - pd.DateOffset(months=1))

    def test_weekly_5d_includes_only_latest_one_or_two_weekly_bars(self):
        weekly = self.frame.groupby(self.frame["Ngày"].dt.to_period("W-FRI"), sort=True).last().reset_index(drop=True)
        chart = {**self.chart, "g": weekly, "tf": "W", "labels": [str(x) for x in weekly["Ngày"]]}
        view = chart_range_view(chart, self.days, "5D")
        self.assertGreaterEqual(len(view["g"]), 1)
        self.assertLessEqual(len(view["g"]), 2)
        self.assertEqual(view["g"]["Ngày"].iloc[-1], weekly["Ngày"].iloc[-1])

    def test_monthly_and_quarterly_keep_real_period_bars(self):
        for period, tf in (("M", "M"), ("Q", "Q")):
            grouped = self.frame.groupby(self.frame["Ngày"].dt.to_period(period), sort=True).last().reset_index(drop=True)
            chart = {**self.chart, "g": grouped, "tf": tf, "labels": [str(x) for x in grouped["Ngày"]]}
            view = chart_range_view(chart, self.days, "1Y")
            self.assertGreater(len(view["g"]), 1)
            self.assertLessEqual(len(view["g"]), 13 if tf == "M" else 5)
            self.assertEqual(view["g"]["Ngày"].iloc[-1], grouped["Ngày"].iloc[-1])

    def test_indicators_do_not_recompute_and_last_values_preserved(self):
        view = chart_range_view(self.chart, self.days, "1M")
        for field in ("MA10", "ST_trend", "HU_M", "Giá đóng cửa"):
            self.assertEqual(view["g"][field].iloc[-1], self.chart["g"][field].iloc[-1])
        self.assertEqual(self.chart["g"]["Ngày"].iloc[0], self.days[0])
        self.assertEqual(len(self.chart["g"]), len(self.days))
        self.assertIsNot(view["g"], self.chart["g"])

    def test_preserves_metadata(self):
        view = chart_range_view(self.chart, self.days, "5D")
        self.assertEqual(view["extra"], self.chart["extra"])
        self.assertEqual(view["mas"], self.chart["mas"])

    def test_ticks_have_valid_visible_indices(self):
        for tf in ("D", "W", "M", "Q"):
            with self.subTest(tf=tf):
                c = {**self.chart, "tf": tf}
                view = chart_range_view(c, self.days, "6M")
                self.assertTrue(all(0 <= i < len(view["g"]) for i, _ in view["ticks"]))
                self.assertTrue(view["ticks"])

    def test_short_range_uses_month_year_label(self):
        view = chart_range_view(self.chart, self.days, "5D")
        self.assertTrue(any(txt.startswith("Th") for _, txt in view["ticks"]))

    def test_year_transition_tick(self):
        days = pd.bdate_range("2025-12-15", "2026-01-12")
        frame = pd.DataFrame({"Ngày": days, "MA10": range(len(days))})
        chart = {"g": frame, "tf": "D", "labels": [str(x) for x in days], "ticks": []}
        view = chart_range_view(chart, days, "Tất cả")
        self.assertIn("Th1/2026", [txt for _, txt in view["ticks"]])

    def test_invalid_choice_rejected(self):
        with self.assertRaises(ValueError):
            range_start(self.days, "4Y")

    def test_sparse_index_and_duplicates(self):
        days = [self.days[-4], self.days[-4], pd.NaT, self.days[-2], self.days[-1]]
        self.assertEqual(range_start(days, "5D"), self.days[-4])

    def test_empty_chart_returns_original(self):
        c = {"g": self.frame.head(0), "tf": "D", "labels": [], "ticks": []}
        self.assertIs(chart_range_view(c, self.days, "1M"), c)

    def test_module_only_changes_vnindex_view_and_not_market_data(self):
        root = Path(__file__).resolve().parent
        code = (root / "vnindex_view.py").read_text(encoding="utf-8")
        self.assertIn('st.pills("Khoảng thời gian hiển thị", list(RANGE_OPTIONS)', code)
        self.assertIn('key="vnv_chart_range"', code)
        self.assertIn('P = prep_chart(d_all, tf, len(d_all))', code)
        self.assertIn('P = chart_range_view(P, d_all["Ngày"], chart_range)', code)
        self.assertNotIn('int(n_show)', code)
        self.assertIn('flow_action_items(sections, leading, action_panel, index_day, tf)', code)
        self.assertIn('A.refresh_fomo_sections(view["sections"]', code)


if __name__ == "__main__":
    unittest.main(verbosity=2)
