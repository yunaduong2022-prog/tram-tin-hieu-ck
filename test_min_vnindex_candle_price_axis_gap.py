"""Regression tests: candle-to-price-axis padding, NOT space to flow card."""
from __future__ import annotations

from pathlib import Path
import unittest

from vnindex_chart_right_pad import RIGHT_EXTRA_RATIO, right_axis_range

SRC = (Path(__file__).resolve().parent / "vnindex_view.py").read_text(encoding="utf-8")


class TestCandleToPriceAxisSpacing(unittest.TestCase):
    def test_all_four_timeframes_supported(self):
        self.assertEqual(set(RIGHT_EXTRA_RATIO), {"D", "W", "M", "Q"})

    def test_left_boundary_stable(self):
        for n in (1, 5, 25, 52, 250):
            for tf in ("D", "W", "M", "Q"):
                with self.subTest(n=n, tf=tf):
                    self.assertEqual(right_axis_range(n, tf)[0], -0.5)

    def test_right_boundary_beyond_last_candle(self):
        for tf in ("D", "W", "M", "Q"):
            for n in (1, 5, 13, 52):
                self.assertGreater(right_axis_range(n, tf)[1], n - 0.5)

    def test_weekly_and_quarterly_more_spacious_than_daily(self):
        n = 52
        d = right_axis_range(n, "D")[1]
        w = right_axis_range(n, "W")[1]
        m = right_axis_range(n, "M")[1]
        q = right_axis_range(n, "Q")[1]
        self.assertLess(d, m)
        self.assertLess(m, w)
        self.assertLess(w, q)

    def test_weekly_and_quarterly_visible_empty_area_is_compact(self):
        for tf, minimum, maximum in (("W", 0.19, 0.21), ("Q", 0.21, 0.23)):
            with self.subTest(tf=tf):
                start, end = right_axis_range(52, tf)
                extra = end - 51.5
                portion = extra / (end-start)
                self.assertGreaterEqual(portion, minimum)
                self.assertLessEqual(portion, maximum)

    def test_daily_not_overpadded(self):
        start, end = right_axis_range(250, "D")
        self.assertLess((end-249.5)/(end-start), 0.17)

    def test_minimal_window_remains_visible(self):
        for tf in ("D", "W", "M", "Q"):
            start, end = right_axis_range(1, tf)
            self.assertGreater(end-start, 1.0)
            self.assertLess(end-start, 2.0)

    def test_invalid_inputs_rejected(self):
        for bad in (0, -1, True, 2.5, "3", None):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                right_axis_range(bad, "W")
        with self.assertRaises(ValueError):
            right_axis_range(5, "H")

    def test_use_numeric_category_range_in_chart(self):
        self.assertIn('from vnindex_chart_right_pad import right_axis_range', SRC)
        self.assertIn('visible_x_range = right_axis_range(n, tf)', SRC)
        self.assertEqual(SRC.count('range=visible_x_range, rangeslider_visible=False,'), 2)
        self.assertIn('showticklabels=False, row=1, col=1)', SRC)
        self.assertIn('showticklabels=True, row=2, col=1)', SRC)
        self.assertNotIn('fig.update_xaxes(type="category", range=right_axis_range(n, tf),', SRC)

    def test_full_price_and_volume_panels_share_the_range(self):
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True)
        bars = [f"W{k}" for k in range(1, 53)]
        fig.add_trace(go.Candlestick(x=bars, open=[2]*52, high=[3]*52,
                                      low=[1]*52, close=[2]*52), row=1, col=1)
        fig.add_trace(go.Bar(x=bars, y=[10]*52), row=2, col=1)
        fig.update_xaxes(type="category", range=right_axis_range(52, "W"))
        self.assertEqual(tuple(fig.layout.xaxis.range), tuple(right_axis_range(52, "W")))
        self.assertEqual(tuple(fig.layout.xaxis2.range), tuple(right_axis_range(52, "W")))
        self.assertEqual(len(fig.data), 2)
        self.assertEqual(len(fig.data[0].x), 52)

    def test_existing_outer_gap_margins_unchanged(self):
        self.assertIn('chart_col, flow_col = st.columns([2, 1], gap="medium")', SRC)
        self.assertIn('margin=dict(l=8, r=72, t=8, b=34)', SRC)

    def test_buttons_indicators_and_bulletins_unchanged(self):
        self.assertIn('st.pills("Khoảng thời gian hiển thị", list(RANGE_OPTIONS)', SRC)
        self.assertIn('P = chart_range_view(P, d_all["Ngày"], chart_range)', SRC)
        self.assertIn('g = g.join(SPT.compute(g)).join(HUL.compute(g))', SRC)
        self.assertIn('flow_action_items(sections, leading, action_panel, index_day, tf)', SRC)
        self.assertIn('leading_from_eod(source_raw, d_all, tf, _WL.GROUPS)', SRC)

    def test_metadata_caption_stays_hidden(self):
        self.assertNotIn('st.caption(f"VNINDEX: {index_day:', SRC)


if __name__ == "__main__":
    unittest.main(verbosity=2)
