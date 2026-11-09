"""Regression tests: remove yellow-circled provenance row, retain guardrails."""
from __future__ import annotations

from pathlib import Path
import unittest

VIEW = (Path(__file__).resolve().parent / "vnindex_view.py").read_text(encoding="utf-8")


class TestVNIndexNoMetadataCaption(unittest.TestCase):
    def test_heading_still_exists(self):
        self.assertIn('st.subheader(_bulletin_heading(view["title"]))', VIEW)

    def test_metadata_caption_removed(self):
        self.assertNotIn('st.caption(f"VNINDEX:', VIEW)
        self.assertNotIn('index_source = d_all.attrs.get(', VIEW)

    def test_only_caption_specific_cap_lookup_removed(self):
        self.assertNotIn('from vnindex_market_cap import load_shares as _load_shares', VIEW)
        self.assertNotIn('share_rows = _load_shares(', VIEW)
        self.assertNotIn('cap_label = (', VIEW)

    def test_date_still_used_for_integrity_checks(self):
        self.assertIn('index_day = pd.Timestamp(d_all["Ngày"].iloc[-1]).normalize()', VIEW)
        self.assertIn('stock_day = pd.Timestamp(parsed.max()).normalize()', VIEW)
        self.assertIn('sector_data_behind = stock_day is not None and stock_day < index_day', VIEW)

    def test_stale_sector_warning_still_shows(self):
        self.assertIn('if sector_data_behind:', VIEW)
        self.assertIn('st.warning(f"Dữ liệu nhóm ngành chỉ đến', VIEW)

    def test_sector_cap_filter_pipeline_untouched(self):
        self.assertIn('leading_from_eod(source_raw, d_all, tf, _WL.GROUPS)', VIEW)
        self.assertIn('replace_strong_sector_block(sections, leading, tf)', VIEW)

    def test_actions_untouched(self):
        self.assertIn('flow_action_items(sections, leading, action_panel, index_day, tf)', VIEW)
        self.assertIn('replace_action_section(sections, action_lines)', VIEW)

    def test_other_chart_caption_stays(self):
        self.assertIn('st.caption(f"Dữ liệu cuối phiên đến', VIEW)
        self.assertIn('st.pills("Khoảng thời gian hiển thị", list(RANGE_OPTIONS)', VIEW)

    def test_indicators_and_layout_unchanged(self):
        self.assertIn('g = g.join(SPT.compute(g)).join(HUL.compute(g))', VIEW)
        self.assertIn('fig = build_chart(P, show_st, show_hull)', VIEW)
        self.assertIn('chart_col, flow_col = st.columns([2, 1], gap="medium")', VIEW)

    def test_no_unwanted_replacement_of_report(self):
        self.assertIn('A.refresh_fomo_sections(view["sections"]', VIEW)
        self.assertIn('sections = replace_action_section(sections, action_lines)', VIEW)


if __name__ == "__main__":
    unittest.main(verbosity=2)
