"""Regressions for on-air formatting of *existing* stock commentary wording."""
import html
import re
import unittest
from live_detail_format import render_detail_section


def inline(t):
    return html.escape(t, quote=True)


def md(t):
    # Lightweight test double: every word is retained, but special HTML escaped.
    return '', '<section>' + html.escape(t, quote=True) + '</section>'


def stripped(s):
    return html.unescape(re.sub(r'<[^>]*>', '', s)).replace('\xa0', ' ')


PART1 = '''Khang Điền là doanh nghiệp bất động sản tập trung phát triển các dự án nhà ở tại TP.HCM, gồm nhà phố, biệt thự, căn hộ và các khu đô thị quy mô lớn.

Lợi thế cạnh tranh của doanh nghiệp đến từ:

Thứ nhất, quỹ đất có vị trí chiến lược. KDH có các dự án tập trung tại khu Đông và khu Nam TP.HCM, nổi bật với Bình Trưng, The Solina và Tân Tạo. Đây là những khu vực có tiềm năng phát triển nhà ở nhờ quá trình mở rộng đô thị và đầu tư hạ tầng.

Thứ hai, khả năng phát triển dự án theo nhiều giai đoạn. Các quỹ đất lớn có thể tạo nguồn cung dài hạn, giúp doanh nghiệp duy trì hoạt động kinh doanh trong nhiều năm nếu hoàn thiện được pháp lý và đảm bảo nguồn vốn triển khai.

Thứ ba, hợp tác với đối tác quốc tế. KDH hợp tác với Keppel tại dự án Gladia. Việc hợp tác hỗ trợ năng lực phát triển dự án, phân bổ vốn và tiếp cận phân khúc nhà ở cao cấp.

Tuy nhiên, quy mô quỹ đất lớn không tự động tạo ra lợi nhuận. Yếu tố quyết định vẫn là khả năng hoàn tất pháp lý, phát triển sản phẩm phù hợp nhu cầu và chuyển đổi hàng tồn kho thành dòng tiền.'''

PART2 = '''Kết quả 9 tháng đầu năm 2026 cho thấy sự chênh lệch đáng kể giữa doanh thu bán bất động sản và lợi nhuận ghi nhận.

Ba khoản thu nhập bất thường đáng chú ý gồm:

Lãi thoái vốn Bình Trưng Mới khoảng 896 tỷ đồng.

Lãi từ giao dịch mua rẻ doanh nghiệp An Lập khoảng 285 tỷ đồng.

Khoản bồi thường chấm dứt hợp đồng khoảng 129 tỷ đồng.

Các khoản này giúp kết quả lợi nhuận tăng mạnh dù doanh thu bàn giao bất động sản suy giảm.

Đặc biệt, trong quý III/2026, doanh thu thuần chỉ đạt khoảng 41 tỷ đồng. Lợi nhuận được hỗ trợ đáng kể bởi phần lãi từ công ty liên kết và thu nhập khác.

Điều này cho thấy lợi nhuận kế toán đang cao nhưng khả năng sinh lời từ hoạt động bán và bàn giao nhà chưa phục hồi tương ứng.

Vì vậy, nhà đầu tư cần phân biệt giữa lợi nhuận tổng thể và lợi nhuận từ hoạt động kinh doanh cốt lõi.'''


class DetailFormatTests(unittest.TestCase):
    def render(self, source):
        return render_detail_section(source.splitlines(), md, inline)

    def test_three_advantages_are_distinct_source_cards(self):
        out = self.render(PART1)
        self.assertEqual(out.count("class='min-nd-point'"), 3)
        self.assertEqual(out.count("class='min-nd-income'"), 0)
        for paragraph in PART1.split('\n\n'):
            self.assertIn(paragraph, stripped(out))
        self.assertIn('KDH hợp tác với Keppel', stripped(out))

    def test_three_cash_items_are_number_highlighted_without_new_figures(self):
        out = self.render(PART2)
        self.assertEqual(out.count("class='min-nd-income'"), 3)
        self.assertEqual(out.count("class='min-nd-takeaway'"), 1)
        for amount in ('896 tỷ đồng', '285 tỷ đồng', '129 tỷ đồng'):
            self.assertIn('>'+amount+'</strong>', out)
        for paragraph in PART2.split('\n\n'):
            self.assertIn(paragraph, stripped(out))
        self.assertNotIn('1.311 tỷ', out)

    def test_plain_prose_is_unmodified(self):
        sample='NLG hoạt động tại các khu đô thị.\n\nKhông có bảng nguồn.'
        out=self.render(sample)
        self.assertEqual(out, md(sample)[1])

    def test_existing_technical_bullets_use_existing_markdown(self):
        sample='* Cổ phiếu đang tích lũy.\n* Khối lượng còn thấp.\n\nTạm theo dõi.'
        self.assertEqual(self.render(sample), md(sample)[1])

    def test_single_ordinal_does_not_force_reformat(self):
        sample='Thứ nhất, doanh thu phục hồi. Chưa có xác nhận.\n\nCâu khác.'
        self.assertEqual(self.render(sample), md(sample)[1])

    def test_no_auto_financial_labels(self):
        out = self.render('Không có dữ liệu doanh thu và LNST.\n\nKhông thể lập nhận định.')
        self.assertNotIn('KDH', out)
        self.assertNotIn('896', out)
        self.assertNotIn('min-nd-income', out)

    def test_html_escaped_and_text_preserved(self):
        sample='Thứ nhất, tập trung <script>. Phần còn lại & dự án.\n\nThứ hai, lợi thế mới. Không thêm số liệu.'
        out=self.render(sample)
        self.assertIn('&lt;script&gt;', out)
        self.assertNotIn('<script>', out)
        self.assertIn('Phần còn lại & dự án.', stripped(out))

    def test_interruption_cancels_income_run(self):
        sample='Ba khoản thu nhập bất thường đáng chú ý gồm:\n\nKhoản A khoảng 10 tỷ đồng.\n\nCó thêm thông tin cần kiểm tra.\n\nKhoản B khoảng 20 tỷ đồng.'
        out=self.render(sample)
        self.assertEqual(out.count("class='min-nd-income'"), 1)
        self.assertIn('Khoản B khoảng 20 tỷ đồng.', stripped(out))

    def test_unstructured_notes_are_unchanged(self):
        sample='Ghi chú cho người dẫn: Vì sao tăng vốn?\nMột đoạn dài.\n\n* Luận điểm A.\n* Luận điểm B.'
        self.assertEqual(self.render(sample), md(sample)[1])


if __name__ == '__main__':
    unittest.main(verbosity=2)