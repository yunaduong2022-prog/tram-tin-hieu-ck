"""VNINDEX regression: compact right blank space, one x-axis below volume."""
from __future__ import annotations

from pathlib import Path
import unittest

from plotly.subplots import make_subplots
import plotly.graph_objects as go

from vnindex_chart_right_pad import RIGHT_EXTRA_RATIO, right_axis_range

SOURCE = (Path(__file__).resolve().parent / "vnindex_view.py").read_text(encoding="utf-8")


class TestVNIndexSingleTimeAxis(unittest.TestCase):
    def test_ratios_are_new_compact_values(self):
        self.assertEqual(RIGHT_EXTRA_RATIO, {"D": 0.14, "W": 0.25, "M": 0.20, "Q": 0.28})

    def test_right_gap_is_reduced_from_previous_release(self):
        old = {"D": 0.18, "W": 0.37, "M": 0.26, "Q": 0.40}
        for tf in old:
            with self.subTest(tf=tf):
                n = 52
                self.assertEqual(right_axis_range(n, tf)[0], -0.5)
                self.assertLess(right_axis_range(n, tf)[1], n - 0.5 + n * old[tf])
                self.assertGreater(right_axis_range(n, tf)[1], n - 0.5)

    def test_shared_x_plotly_axes_hide_top_show_bottom(self):
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True)
        candles = [f"T{k}" for k in range(52)]
        fig.add_trace(go.Candlestick(x=candles, open=[5]*52, high=[6]*52,
                                     low=[4]*52, close=[5]*52), row=1, col=1)
        fig.add_trace(go.Bar(x=candles, y=[100]*52), row=2, col=1)
        xr = right_axis_range(52, "W")
        fig.update_xaxes(type="category", range=xr, showticklabels=False, row=1, col=1)
        fig.update_xaxes(type="category", range=xr, showticklabels=True, row=2, col=1)
        fig.update_xaxes(tickmode="array", tickvals=[candles[0], candles[26]],
                         ticktext=["Th1", "Th7"], showticklabels=True, row=2, col=1)
        self.assertFalse(fig.layout.xaxis.showticklabels)
        self.assertTrue(fig.layout.xaxis2.showticklabels)
        self.assertIsNone(fig.layout.xaxis.tickvals)
        self.assertEqual(tuple(fig.layout.xaxis2.tickvals), (candles[0], candles[26]))
        self.assertEqual(tuple(fig.layout.xaxis.range), tuple(xr))
        self.assertEqual(tuple(fig.layout.xaxis2.range), tuple(xr))
        self.assertEqual(len(fig.data), 2)
        self.assertEqual(len(fig.data[0].x), 52)

    def test_source_has_two_explicit_x_panes(self):
        self.assertEqual(SOURCE.count('range=visible_x_range, rangeslider_visible=False,'), 2)
        self.assertIn('showticklabels=False, row=1, col=1)', SOURCE)
        self.assertIn('showticklabels=bool(P["ticks"]), row=2, col=1)', SOURCE)
        self.assertIn('showticklabels=True, row=2, col=1)', SOURCE)

    def test_only_bottom_axis_receives_tick_values(self):
        self.assertEqual(SOURCE.count('tickvals=[x[i] for i, _ in P["ticks"]]'), 1)
        self.assertIn('tickfont=dict(size=11),\n                         showticklabels=True, row=2, col=1)', SOURCE)
        self.assertNotIn('nhãn tháng hiện cả dưới biểu đồ nến', SOURCE)

    def test_no_fake_candles_and_indicator_preservation(self):
        self.assertIn('fig.add_trace(go.Candlestick(', SOURCE)
        self.assertIn('fig.add_trace(go.Bar(', SOURCE)
        self.assertIn('g = g.join(SPT.compute(g)).join(HUL.compute(g))', SOURCE)
        self.assertIn('P = chart_range_view(P, d_all["Ngày"], chart_range)', SOURCE)
        self.assertIn('st.pills("Khoảng thời gian hiển thị", list(RANGE_OPTIONS)', SOURCE)

    def test_flow_card_not_pushed_away(self):
        self.assertIn('chart_col, flow_col = st.columns([2, 1], gap="medium")', SOURCE)
        self.assertIn('margin=dict(l=8, r=72, t=8, b=34)', SOURCE)

    def test_report_logic_unchanged(self):
        self.assertIn('flow_action_items(sections, leading, action_panel, index_day, tf)', SOURCE)
        self.assertIn('leading_from_eod(source_raw, d_all, tf, _WL.GROUPS)', SOURCE)
        self.assertNotIn('st.caption(f"VNINDEX: {index_day:', SOURCE)

    def test_many_viewport_sizes(self):
        for n in (1, 2, 5, 13, 52, 120, 250, 800):
            for tf in ("D", "W", "M", "Q"):
                with self.subTest(n=n, tf=tf):
                    low, high = right_axis_range(n, tf)
                    self.assertGreater(high, n - 0.5)
                    self.assertGreater(high - low, n)


if __name__ == "__main__":
    unittest.main(verbosity=2)
