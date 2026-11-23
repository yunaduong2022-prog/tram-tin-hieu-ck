"""Offline regression suite for the official NHNN HTML extractor and CSV guards."""
from datetime import date
from decimal import Decimal
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from macro_sbv_sync import (Observation, SourceError, parse_official_page, update_history,
                            history_rows, COLUMNS)


def fixture(day='20/11/2026', rate='5,26'):
    return f'''<html><body>
<h2>Các mức lãi suất do Ngân hàng Nhà nước quy định</h2>
<table><tr><th>Loại lãi suất</th><th>Giá trị</th></tr>
<tr><td>Lãi suất tái cấp vốn</td><td>4,500%</td></tr></table>
<h2>Lãi suất thị trường liên ngân hàng</h2>
<p>Ngày áp dụng: <strong>{day}</strong></p>
<table><thead><tr><th>Thời hạn</th><th>Lãi suất BQ liên Ngân hàng (% năm)</th><th>Doanh số (Tỷ đồng)</th></tr></thead>
<tbody><tr><td>Qua đêm</td><td>{rate}</td><td>888.178,0</td></tr>
<tr><td>1 Tuần</td><td>5,36</td><td>6.590,0</td></tr></tbody></table>
<footer>Ngày 07/08/2026 của bản tin cũ không phải ngày bảng này</footer>
</body></html>'''


def initial_csv():
    return ','.join(COLUMNS) + '\n' + (',MONETARY' if False else
            'GDP_Q,cycle,GDP,Q3/2026,2026-09-30,9.95,% YoY,YoY,Cục Thống kê,https://nso.gov.vn/,Quý III\n'
            'INTERBANK_ON,monetary,Lãi suất liên ngân hàng O/N,07/08/2026,2026-08-07,5.97,%/năm,Qua đêm,Ngân hàng Nhà nước,https://sbv.gov.vn/vi/lãi-suất1,Lịch sử\n'
            'INTERBANK_ON,monetary,Lãi suất liên ngân hàng O/N,20/11/2026,2026-11-20,5.26,%/năm,Qua đêm,Ngân hàng Nhà nước,https://sbv.gov.vn/vi/lãi-suất1,Ảnh người dùng\n')


class TestOfficialHTML(unittest.TestCase):
    def test_correct_table_date_not_policy_table(self):
        got = parse_official_page(fixture(), today=date(2026,11,23))
        self.assertEqual(got.asof, date(2026,11,20))
        self.assertEqual(got.rate, Decimal('5.26'))

    def test_old_page_parses_but_cannot_regress(self):
        got = parse_official_page(fixture('07/08/2026', '5,97'), today=date(2026,11,23))
        self.assertEqual(got.rate, Decimal('5.97'))

    def test_reject_missing_date(self):
        with self.assertRaises(SourceError):
            parse_official_page(fixture().replace('Ngày áp dụng:', 'Ngày khác:'), today=date(2026,11,23))

    def test_reject_future_date(self):
        with self.assertRaises(SourceError):
            parse_official_page(fixture('25/11/2026'), today=date(2026,11,23))

    def test_reject_wrong_table_rate_label(self):
        with self.assertRaises(SourceError):
            parse_official_page(fixture().replace('Qua đêm', 'Kỳ hạn khác'), today=date(2026,11,23))

    def test_reject_outlier(self):
        with self.assertRaises(SourceError):
            parse_official_page(fixture(rate='29,99'), today=date(2026,11,23))

    def test_reject_two_matching_tables(self):
        html = fixture()
        with self.assertRaises(SourceError):
            parse_official_page(html.replace('</body>', '<h2>Lãi suất thị trường liên ngân hàng</h2><p>Ngày áp dụng: 20/11/2026</p><table><tr><th>Thời hạn</th><th>Lãi suất BQ liên Ngân hàng</th></tr><tr><td>Qua đêm</td><td>5,26</td></tr></table></body>'), today=date(2026,11,23))


class TestGuardedCSV(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.file = Path(self.dir.name) / 'macro_vn.csv'
        self.file.write_bytes(initial_csv().encode('utf-8'))
        self.original = self.file.read_bytes()

    def tearDown(self):
        self.dir.cleanup()

    def test_same_date_same_value_no_write(self):
        outcome = update_history(self.file, Observation(date(2026,11,20), Decimal('5.26')), today=date(2026,11,23))
        self.assertEqual(outcome, 'ALREADY_CURRENT')
        self.assertEqual(self.file.read_bytes(), self.original)

    def test_prevent_outdated_cached_page(self):
        with self.assertRaisesRegex(SourceError, 'SOURCE_REGRESSED'):
            update_history(self.file, Observation(date(2026,8,7), Decimal('5.97')), today=date(2026,11,23))
        self.assertEqual(self.file.read_bytes(), self.original)

    def test_prevent_source_stale(self):
        with self.assertRaisesRegex(SourceError, 'SOURCE_STALE'):
            update_history(self.file, Observation(date(2026,11,20), Decimal('5.26')), today=date(2026,12,5))
        self.assertEqual(self.file.read_bytes(), self.original)

    def test_same_date_changed_rate_requires_review(self):
        with self.assertRaisesRegex(SourceError, 'SAME_DATE_DIFFERENT'):
            update_history(self.file, Observation(date(2026,11,20), Decimal('5.90')), today=date(2026,11,23))
        self.assertEqual(self.file.read_bytes(), self.original)

    def test_append_latest_only_and_keep_existing_bytes(self):
        outcome = update_history(self.file, Observation(date(2026,11,23), Decimal('4.50')), today=date(2026,11,23))
        self.assertEqual(outcome, 'NEW_DATE_APPENDED')
        self.assertTrue(self.file.read_bytes().startswith(self.original))
        _, records = history_rows(self.file)
        self.assertEqual(records[-1]['asof'], '2026-11-23')
        self.assertEqual(records[-1]['value'], '4.50')
        self.assertEqual(len(records), 4)

    def test_append_preserves_crlf_bytes(self):
        before = self.original.replace(b"\n", b"\r\n")
        self.file.write_bytes(before)
        result = update_history(self.file, Observation(date(2026, 11, 23), Decimal('4.50')),
                                today=date(2026, 11, 23))
        after = self.file.read_bytes()
        self.assertEqual(result, 'NEW_DATE_APPENDED')
        self.assertTrue(after.startswith(before))
        self.assertTrue(after[len(before):].startswith(b'INTERBANK_ON,'))
        self.assertTrue(after.endswith(b'\r\n'))
        self.assertEqual(len(history_rows(self.file)[1]), 4)

    def test_append_preserves_bom_and_crlf(self):
        before = b"\xef\xbb\xbf" + self.original.replace(b"\n", b"\r\n")
        self.file.write_bytes(before)
        result = update_history(self.file, Observation(date(2026, 11, 23), Decimal('4.50')),
                                today=date(2026, 11, 23))
        after = self.file.read_bytes()
        self.assertEqual(result, 'NEW_DATE_APPENDED')
        self.assertTrue(after.startswith(before))
        self.assertEqual(after.count(b"\xef\xbb\xbf"), 1)
        self.assertEqual(len(history_rows(self.file)[1]), 4)

    def test_append_without_terminal_newline(self):
        before = self.original.rstrip(b"\n")
        self.file.write_bytes(before)
        result = update_history(self.file, Observation(date(2026, 11, 23), Decimal('4.50')),
                                today=date(2026, 11, 23))
        after = self.file.read_bytes()
        self.assertEqual(result, 'NEW_DATE_APPENDED')
        self.assertTrue(after.startswith(before))
        self.assertTrue(after[len(before):].startswith(b'\nINTERBANK_ON,'))
        self.assertEqual(len(history_rows(self.file)[1]), 4)

    def test_append_preserves_existing_mixed_newlines(self):
        before = self.original.replace(b"\n", b"\r\n", 1)
        self.file.write_bytes(before)
        update_history(self.file, Observation(date(2026, 11, 23), Decimal('4.50')),
                       today=date(2026, 11, 23))
        self.assertTrue(self.file.read_bytes().startswith(before))
        self.assertEqual(len(history_rows(self.file)[1]), 4)

    def test_idempotence_after_append(self):
        obs = Observation(date(2026, 11, 23), Decimal('4.50'))
        update_history(self.file, obs, today=date(2026, 11, 23))
        once = self.file.read_bytes()
        result = update_history(self.file, obs, today=date(2026, 11, 23))
        self.assertEqual(result, 'ALREADY_CURRENT')
        self.assertEqual(self.file.read_bytes(), once)

    def test_invalid_header_cannot_write(self):
        self.file.write_text('foo,bar\na,b\n', encoding='utf-8')
        prior = self.file.read_bytes()
        with self.assertRaisesRegex(SourceError, 'UNEXPECTED_COLUMNS'):
            update_history(self.file, Observation(date(2026,11,23), Decimal('5.00')), today=date(2026,11,23))
        self.assertEqual(self.file.read_bytes(), prior)


if __name__ == '__main__':
    unittest.main()
