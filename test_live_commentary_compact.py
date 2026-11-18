"""Offline regression tests for compact Livestream commentary, no Streamlit UI."""
import html
import unittest
from live_commentary_layout import compact_commentary, _split_sections


def inline(x):
    return html.escape(x)


def fake_table(lines, i):
    if i + 2 >= len(lines):
        return '', i
    cells = [c.strip() for c in lines[i].strip('|').split('|')]
    line2 = [c.strip() for c in lines[i + 1].strip('|').split('|')]
    if len(cells) != len(line2) or any(set(c) - set(':-') for c in line2):
        return '', i
    j = i + 2
    while j < len(lines) and lines[j].strip().startswith('|'):
        j += 1
    rows = [html.escape(x) for x in lines[i:j]]
    return '<table>' + ''.join(rows) + '</table>', j


def fake_md(text):
    return '', '<article>' + html.escape(text) + '</article>'


KDH = '''# 1. Tổng quan doanh nghiệp và lợi thế cạnh tranh

Khang Điền là doanh nghiệp phát triển bất động sản TP.HCM.

Hợp tác với đối tác quốc tế là một lợi thế.

# 2. Vì sao lợi nhuận tăng mạnh?

Kết quả 9 tháng cho thấy chênh lệch doanh thu và lợi nhuận.

| Chỉ tiêu | 9T/2026 | So với cùng kỳ |
| :--- | ---: | ---: |
| Doanh thu thuần | 483 tỷ đồng | -83,1% |
| LNST cổ đông mẹ | 1.209 tỷ đồng | +117% |

Ba khoản thu nhập bất thường đáng chú ý gồm:

Lãi thoái vốn Bình Trưng Mới khoảng 896 tỷ đồng.

Vì vậy cần phân biệt lợi nhuận kế toán và hoạt động cốt lõi.
'''


def render(source):
    return compact_commentary(source, fake_md, fake_table, inline)


class CompactLayoutTests(unittest.TestCase):
    def test_kdh_two_sections_and_table_always_visible(self):
        title, output = render(KDH)
        self.assertEqual(title, '')
        self.assertEqual(output.count('<details'), 2)
        self.assertEqual(output.count('<table>'), 1)
        self.assertLess(output.index('<table>'), output.index('<details'))
        self.assertIn('483 tỷ đồng', output)
        self.assertIn('1.209 tỷ đồng', output)
        self.assertIn('Khang Điền', output)
        self.assertIn('TÓM TẮT NHANH', output)
        self.assertNotIn('nd-scroll', output)

    def test_body_after_lift_preserved_once(self):
        _, result = render(KDH)
        self.assertEqual(result.count('Lãi thoái vốn Bình Trưng Mới khoảng 896 tỷ đồng.'), 1)
        self.assertEqual(result.count('<table>'), 1)
        self.assertIn('Ba khoản thu nhập bất thường', result)

    def test_document_title_and_multilevel_section_headings(self):
        s = '# Một báo cáo\n\n## [Phần 1: Xu hướng]\n\nĐoạn gốc.\n\n## Rủi ro\n\nChưa rõ.'
        title, result = render(s)
        self.assertEqual(title, 'Một báo cáo')
        self.assertEqual(result.count('<details'), 2)
        self.assertIn('[Phần 1: Xu hướng]', result)
        self.assertIn('Chưa rõ.', result)

    def test_missing_table_does_not_create_one(self):
        _, result = render('# Mã X\n\nMột nhận định ngắn.')
        self.assertNotIn('<table>', result)
        self.assertIn('Một nhận định ngắn.', result)

    def test_bad_table_separator_unchanged(self):
        _, result = render('# 1. KQKD\n\n| Chỉ tiêu | Kỳ |\n|---| Không hợp lệ |\n| Doanh thu | 123 |')
        self.assertNotIn('<table>', result)
        self.assertIn('Không hợp lệ', result)

    def test_html_source_escaped(self):
        _, result = render('# 1. Báo cáo <script>\n\n<script>alert(1)</script>')
        self.assertNotIn('<script>', result)
        self.assertIn('&lt;script&gt;', result)

    def test_heading_only_keeps_text(self):
        title, result = render('# ACB đang chờ siết nền')
        self.assertEqual(title, 'ACB đang chờ siết nền')
        self.assertEqual(result, '')  # headline is displayed once by commentary_card

    def test_intro_before_heading_not_dropped(self):
        _, result = render('Mở đầu quan trọng.\n\n# 1. Phân tích\n\nNội dung.')
        self.assertIn('Mở đầu quan trọng.', result)
        self.assertEqual(result.count('<details'), 2)

    def test_actual_kdh_with_existing_parser_when_available(self):
        from pathlib import Path
        import sys
        try:
            from stock_drivers import commentary_card
        except ModuleNotFoundError:
            self.skipTest('Integration test runs inside cloned repository')
        if not (Path(__file__).parent / 'data' / 'nhan_dinh_ma' / 'KDH.md').is_file():
            self.skipTest('Repository KDH.md unavailable')
        rendered = commentary_card('KDH')
        self.assertEqual(rendered.count("<table class='live-table'"), 1)
        self.assertEqual(rendered.count("class='min-nd-detail'"), 2)
        self.assertIn('TÓM TẮT NHANH', rendered)
        self.assertIn('483 tỷ đồng', rendered)
        self.assertIn('1.209 tỷ đồng', rendered)
        self.assertIn('Lãi thoái vốn Bình Trưng Mới khoảng 896 tỷ đồng.', rendered)
        self.assertNotIn('nd-scroll', rendered)
        self.assertIn('số liệu trong đoạn là chữ cố định', rendered)

    def test_no_hardcoded_company_values(self):
        _, result = render('# 1. Mã ABC\n\nDoanh nghiệp này có doanh thu 234 tỷ.')
        self.assertNotIn('KDH', result)
        self.assertNotIn('483 tỷ', result)
        self.assertIn('234 tỷ', result)


if __name__ == '__main__':
    unittest.main(verbosity=2)
