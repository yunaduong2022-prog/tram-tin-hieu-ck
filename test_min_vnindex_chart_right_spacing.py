"""Check VNINDEX right-side spacing without touching chart indicators or report logic."""
from __future__ import annotations

from pathlib import Path
import unittest

SRC = (Path(__file__).resolve().parent / "vnindex_view.py").read_text(encoding="utf-8")


class TestVNIndexRightSpacing(unittest.TestCase):
    def test_compact_chart_to_flow_gap(self):
        self.assertEqual(SRC.count('chart_col, flow_col = st.columns([2, 1], gap="medium")'), 1)

    def test_large_gap_no_longer_present(self):
        self.assertNotIn('chart_col, flow_col = st.columns([2, 1], gap="large")', SRC)

    def test_right_plotly_margin_restored(self):
        self.assertEqual(SRC.count('fig.update_layout(height=620, margin=dict(l=8, r=72, t=8, b=34)'), 1)

    def test_plotly_other_margins_preserved(self):
        self.assertIn('margin=dict(l=8, r=72, t=8, b=34)', SRC)
        self.assertNotIn('margin=dict(l=8, r=96, t=8, b=34)', SRC)

    def test_chart_to_flow_ratio_unchanged(self):
        self.assertIn('st.columns([2, 1], gap="medium")', SRC)

    def test_time_range_pills_untouched(self):
        self.assertIn('st.pills("Khoảng thời gian hiển thị", list(RANGE_OPTIONS)', SRC)
        self.assertIn('key="vnv_chart_range"', SRC)
        self.assertIn('P = chart_range_view(P, d_all["Ngày"], chart_range)', SRC)

    def test_technical_indicators_untouched(self):
        self.assertIn('g = g.join(SPT.compute(g)).join(HUL.compute(g))', SRC)
        self.assertIn('fig = build_chart(P, show_st, show_hull)', SRC)

    def test_report_rule_hooks_untouched(self):
        self.assertIn('flow_action_items(sections, leading, action_panel, index_day, tf)', SRC)
        self.assertIn('A.refresh_fomo_sections(view["sections"]', SRC)
        self.assertIn('leading_from_eod(source_raw, d_all, tf, _WL.GROUPS)', SRC)

    def test_chart_and_flow_same_main_row(self):
        first = SRC.index('chart_col, flow_col = st.columns([2, 1], gap="medium")')
        left = SRC.index('with chart_col:', first)
        right = SRC.index('with flow_col:', left)
        self.assertLess(first, left)
        self.assertLess(left, right)


if __name__ == "__main__":
    unittest.main(verbosity=2)
