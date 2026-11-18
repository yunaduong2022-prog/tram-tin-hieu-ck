"""Regression tests: only the Livestream commentary Markdown tables are rendered."""
import re
import unittest
from pathlib import Path
from stock_drivers import _comment_html, commentary_card


class TestLiveCommentaryTable(unittest.TestCase):
    def test_kdh_source_becomes_semantic_three_column_table(self):
        text = (Path(__file__).parent / "data" / "nhan_dinh_ma" / "KDH.md").read_text(encoding="utf-8-sig")
        title, body = _comment_html(text)
        self.assertIn("Khang Điền", body)
        self.assertEqual(body.count("<table class='live-table'"), 1)
        self.assertEqual(body.count("<thead><tr>"), 1)
        self.assertEqual(body.count("<tbody><tr>"), 1)
        self.assertEqual(body.count("</tr>"), 5)  # 1 header + 4 source rows
        for x in ("Doanh thu thuần", "483 tỷ đồng", "-83,1%",
                  "LNST hợp nhất", "1.268 tỷ đồng", "+50,8%",
                  "LNST cổ đông mẹ", "1.209 tỷ đồng", "+117%",
                  "Tổng thu nhập bất thường", "1.311 tỷ đồng"):
            self.assertIn(x, body)
        self.assertIn("Ba khoản thu nhập bất thường", body)
        self.assertNotIn("Chỉ tiêu 9T/2026 Kết quả", body)

    def test_code_commentary_card_keeps_header_and_foot(self):
        html = commentary_card("KDH")
        self.assertIsNotNone(html)
        self.assertIn("NHẬN ĐỊNH · KDH", html)
        self.assertIn("số liệu trong đoạn là chữ cố định", html)
        self.assertIn("<table class='live-table'", html)

    def test_normal_prose_and_bullets_unchanged(self):
        title, body = _comment_html("# A title\n\nThis is ordinary prose.\n\n* First bullet\n")
        self.assertEqual(title, "A title")
        self.assertIn("This is ordinary prose.", body)
        self.assertIn("First bullet", body)
        self.assertNotIn("<table", body)

    def test_bad_markdown_separator_kept_as_text(self):
        _, body = _comment_html("# X\n| A | B |\n| --- | not a separator |\n| 1 | 2 |")
        self.assertNotIn("<table", body)
        self.assertIn("not a separator", body)

    def test_html_escaped_in_table_cells(self):
        _, body = _comment_html("# X\n| Key | 9T | YoY |\n|---|---:|---:|\n| <script> | 10 | -5% |")
        self.assertIn("&lt;script&gt;", body)
        self.assertNotIn("<script>", body)
        self.assertIn("color:#ff8e9f", body)

    def test_percentage_color_only_on_signed_last_column(self):
        _, body = _comment_html("# X\n| Name | Value | Rate |\n|---|---:|---:|\n| Good | 1 | +12% |\n| Bad | 2 | -1.5% |")
        self.assertIn("color:#43d6a1", body)
        self.assertIn("color:#ff8e9f", body)

    def test_other_ticker_not_modified(self):
        _, body = _comment_html("# Example\nNo source table for this ticker.")
        self.assertNotIn("<table", body)
        self.assertIn("No source table", body)

if __name__ == "__main__":
    unittest.main(verbosity=2)
