"""Offline safety tests for guarded CPI sync. Numeric fixtures are SYNTHETIC."""
import csv
from datetime import date
from decimal import Decimal
import io
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from macro_cpi_auto import (article_values, candidates_from_index, title_matches,
                            safe_official_url, month_next, build_history,
                            build_macro, planned_update, find_verified_release,
                            MACRO_COLUMNS, METRICS)

YEAR, MONTH = 2026, 11
TITLE = 'Chỉ số giá tiêu dùng, chỉ số giá vàng và đô la Mỹ tháng Mười Một và mười một tháng năm 2026'
URL = 'https://www.nso.gov.vn/du-lieu-va-so-lieu-thong-ke/2026/12/chi-so-gia-tieu-dung-thang-muoi-mot-va-11-thang-2026/'
INDEX_URL = 'https://www.nso.gov.vn/cpi-vi/'
# These November values exist only inside tests; they are NOT claimed or written as real observations.
ARTICLE = f'''<html><body><h1>{TITLE}</h1><div><p>Chỉ số giá tiêu dùng (CPI) tháng Mười Một tăng 0,31% so với tháng trước; tăng 4,71% so với tháng 12/2025 và tăng 5,12% so với cùng kỳ năm trước.</p><p>Bình quân mười một tháng năm 2026, CPI tăng 4,63% so với cùng kỳ năm trước; lạm phát cơ bản tăng 4,29%.</p></div></body></html>'''
PROPOSAL = {'year_month':'2026-11', 'cpi_yoy_pct':'5.12', 'cpi_mom_pct':'0.31',
            'cpi_ytd_avg_yoy_pct':'4.63', 'core_ytd_avg_yoy_pct':'4.29',
            'source':'Cục Thống kê','source_url':URL}


def macro_fixture(line_ending='\n'):
    recs = [
      ['CPI_OCT_YOY','inflation','CPI tháng 10','10/2026','2026-10-31','5.09','% YoY','So cùng kỳ','Cục Thống kê',URL,'Source note'],
      ['CPI_OCT_MOM','inflation','CPI tháng 10','10/2026','2026-10-31','0.20','% MoM','So tháng trước','Cục Thống kê',URL,'Source note'],
      ['CPI_10M','inflation','CPI bình quân 10 tháng','10T/2026','2026-10-31','4.57','% YoY bình quân','So bình quân','Cục Thống kê',URL,'Source note'],
      ['CORE_CPI_10M','inflation','Lạm phát cơ bản 10 tháng','10T/2026','2026-10-31','4.24','% YoY bình quân','So bình quân','Cục Thống kê',URL,'Source note'],
      ['GDP_Q','cycle','GDP','Q3/2026','2026-09-30','9.95','% YoY','So quý','Cục Thống kê',URL,'Unchanged, GDP'],
    ]
    o=io.StringIO(newline='');w=csv.writer(o,lineterminator=line_ending)
    w.writerow(MACRO_COLUMNS);w.writerows(recs)
    return o.getvalue().encode('utf-8')


def history_fixture(line_ending='\n'):
    o=io.StringIO(newline='');w=csv.writer(o,lineterminator=line_ending)
    w.writerow(('year_month',)+METRICS+('source','source_url'))
    # 10 contiguous months; old numbers synthetic except Oct.
    for month in range(1,11):
        w.writerow([f'2026-{month:02d}', '5.09','0.20','4.57','4.24','Cục Thống kê',URL])
    return o.getvalue().encode('utf-8')


class TestOfficialParser(unittest.TestCase):
    def test_exact_month_title(self):
        self.assertTrue(title_matches(TITLE, YEAR, MONTH))
        self.assertFalse(title_matches(TITLE, 2025, MONTH))
        self.assertFalse(title_matches('CPI tháng Mười năm 2026', YEAR, MONTH))

    def test_candidate_discovery_only_official(self):
        index=f'<html><body><a href="{URL}">{TITLE}</a><a href="https://nso.gov.vn.evil.com/a">{TITLE}</a></body></html>'
        self.assertEqual(candidates_from_index(index,INDEX_URL,YEAR,MONTH),[URL])

    def test_all_four_independent_metrics(self):
        vals=article_values(ARTICLE,YEAR,MONTH)
        self.assertEqual(tuple(vals[k] for k in METRICS), tuple(Decimal(v) for v in ('5.12','0.31','4.63','4.29')))

    def test_negative_mom(self):
        html=ARTICLE.replace('tăng 0,31%', 'giảm 0,31%')
        self.assertEqual(article_values(html,YEAR,MONTH)['cpi_mom_pct'],Decimal('-0.31'))

    def test_wrong_title_month_blocks(self):
        with self.assertRaisesRegex(ValueError,'TITLE_MONTH'):
            article_values(ARTICLE.replace('tháng Mười Một', 'tháng Mười'),YEAR,MONTH)

    def test_missing_core_blocks(self):
        with self.assertRaisesRegex(ValueError,'AVERAGE'):
            article_values(ARTICLE.replace('lạm phát cơ bản','lạm phát kỳ vọng'),YEAR,MONTH)

    def test_ambiguous_duplicate_intro_blocks(self):
        html=ARTICLE.replace('</div>','<p>Chỉ số giá tiêu dùng (CPI) tháng Mười Một tăng 0,33% so với tháng trước; tăng 5,99% so với cùng kỳ năm trước.</p></div>')
        with self.assertRaisesRegex(ValueError,'MAIN_PARAGRAPH_AMBIGUOUS'):
            article_values(html,YEAR,MONTH)

    def test_cannot_confuse_comparison_december_vs_yoy(self):
        vals=article_values(ARTICLE,YEAR,MONTH)
        self.assertNotEqual(vals['cpi_yoy_pct'],Decimal('4.71'))

    def test_url_allowlist_and_fragment(self):
        self.assertTrue(safe_official_url(URL))
        for bad in ('http://www.nso.gov.vn/a','https://nso.gov.vn.evil.com/a','https://evil.com/a',URL+'#x'):
            with self.subTest(bad=bad):self.assertFalse(safe_official_url(bad))

    def test_two_official_reports_conflict(self):
        extra='https://www.nso.gov.vn/tin-tuc-thong-ke/2026/12/chi-so-gia-tieu-dung-muoi-mot-2026/'
        listing=f'<html><a href="{URL}">{TITLE}</a><a href="{extra}">{TITLE}</a></html>'
        def fetch(url):
            if url in (URL,extra):
                return ARTICLE if url==URL else ARTICLE.replace('tăng 5,12%', 'tăng 5,15%')
            return listing
        with self.assertRaisesRegex(ValueError,'CONFLICT'):
            find_verified_release(YEAR,MONTH,fetch)

    def test_index_empty_no_proposal(self):
        self.assertIsNone(find_verified_release(YEAR,MONTH,lambda _: '<html><body>Chưa công bố</body></html>'))

    def test_index_fetch_unavailable_rejected(self):
        with self.assertRaisesRegex(ValueError,'UNAVAILABLE'):
            find_verified_release(YEAR,MONTH,lambda _: (_ for _ in ()).throw(OSError('network')))

    def test_new_page_unreadable_blocks(self):
        listing=f'<html><a href="{URL}">{TITLE}</a></html>'
        with self.assertRaisesRegex(ValueError,'REVIEW'):
            find_verified_release(YEAR,MONTH,lambda link: listing if link in (('https://www.nso.gov.vn/cpi-vi/',)) else '<html>Wrong format</html>')

    def test_next_month_crosses_year(self):
        self.assertEqual(month_next('2026-10'),'2026-11')
        self.assertEqual(month_next('2026-12'),'2027-01')


class TestSafeCSV(unittest.TestCase):
    def test_append_history_keeps_identical_prefix(self):
        old=history_fixture('\r\n')
        new=build_history(old,PROPOSAL,date(2026,12,3))
        self.assertTrue(new.startswith(old))
        self.assertEqual(new.count(b'2026-11'),1)
        self.assertEqual(newline_type(new),'\r\n')

    def test_prevents_skipped_month(self):
        proposal=PROPOSAL.copy();proposal['year_month']='2026-12'
        with self.assertRaisesRegex(ValueError,'EXPECTED_NEXT'):
            build_history(history_fixture(),proposal,date(2027,1,3))

    def test_prevents_future_date(self):
        with self.assertRaisesRegex(ValueError,'FUTURE'):
            build_history(history_fixture(),PROPOSAL,date(2026,11,24))

    def test_macro_exact_four_and_unrelated_bytes(self):
        old=macro_fixture('\r\n')
        new=build_macro(old,PROPOSAL)
        self.assertIn(b'GDP_Q,cycle,GDP,Q3/2026,2026-09-30,9.95',new)
        self.assertEqual(new.count(b'2026-11-30'),4)
        self.assertNotIn(b'2026-10-31',new)
        self.assertEqual(newline_type(new),'\r\n')

    def test_macro_missing_one_fails(self):
        raw=macro_fixture().replace(b'CORE_CPI_10M',b'CORE_XPI_10M')
        with self.assertRaisesRegex(ValueError,'INCOMPLETE'):
            build_macro(raw,PROPOSAL)

    def test_macro_same_date_refuses_overwrite(self):
        new=build_macro(macro_fixture(),PROPOSAL)
        with self.assertRaisesRegex(ValueError,'REGRESSION'):
            build_macro(new,PROPOSAL)

    def test_plan_writes_neither_file_when_invalid(self):
        with tempfile.TemporaryDirectory() as d:
            hp=Path(d)/'h.csv'; mp=Path(d)/'m.csv'
            hp.write_bytes(history_fixture());mp.write_bytes(macro_fixture().replace(b'CORE_CPI_10M',b'CORE_XPI_10M'))
            old_h,old_m=hp.read_bytes(),mp.read_bytes()
            with self.assertRaises(ValueError):
                planned_update(hp,mp,PROPOSAL,date(2026,12,3))
            self.assertEqual(hp.read_bytes(),old_h)
            self.assertEqual(mp.read_bytes(),old_m)


def newline_type(raw):
    return '\r\n' if b'\r\n' in raw else '\n'

if __name__=='__main__': unittest.main()
