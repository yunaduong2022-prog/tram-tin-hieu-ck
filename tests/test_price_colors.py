import unittest,tempfile,csv
from pathlib import Path
from unittest.mock import patch
import price_colors as pc
from sync_price_limits import normalize

DAY='2026-11-27'
DATA={(DAY,'BSR'):('HOSE',22.55,24.10,21.00),(DAY,'ABC'):('HNX',10.,11.,9.),(DAY,'XYZ'):('UPCOM',10.,11.5,8.5),(DAY,'NEW'):('HOSE',10.,12.,8.)}
class Fake:
    def __init__(self,rows): self.rows=rows
    def to_dict(self,mode): return self.rows
class TestColors(unittest.TestCase):
    def setUp(self):
        self.p=patch.object(pc,'limits',return_value=DATA);self.p.start();self.addCleanup(self.p.stop)
        self.token=pc._CTX.set(('',{}));self.addCleanup(pc._CTX.reset,self.token)
    def test_bsr(self):
        v=pc.display('BSR',24.1,6.87,day=DAY);self.assertEqual(v.color,'#D946EF');self.assertEqual(v.state,'ceiling');self.assertAlmostEqual(v.pct,6.8736,3);self.assertTrue(v.verified)
    def test_five(self):
        self.assertEqual([pc.display('ABC',p,day=DAY).state for p in [11,10.1,10,9.9,9]],['ceiling','up','flat','down','floor'])
    def test_upcom_uses_reference(self):
        v=pc.display('XYZ',11.5,-3,day=DAY,prev=12);self.assertEqual(v.state,'ceiling');self.assertAlmostEqual(v.pct,15.)
    def test_special_session(self):
        self.assertEqual(pc.display('NEW',12,20,day=DAY).state,'ceiling')
    def test_missing_no_guess(self):
        v=pc.display('AAA',11,10,day=DAY);self.assertEqual(v.state,'up');self.assertFalse(v.verified)
    def test_stale(self):
        self.assertEqual(pc.display('BSR',24.1,6.87,day='2026-11-26').state,'up')
    def test_intraday_bar(self):
        self.assertEqual(pc.display('BSR',24.1,day=DAY,prev=23,session=False).state,'up')
    def test_context(self):
        pc._CTX.set((DAY,{'BSR':(24.1,6.87)}))
        self.assertEqual(pc.display('BSR',24.1).state,'ceiling');self.assertEqual(pc.display('BSR',24.,6.4).state,'up')
    def test_invalid(self):
        for p in [None,0,float('nan'),float('inf')]:self.assertEqual(pc.display('BSR',p,day=DAY).state,'unknown')
    def test_outside_band(self):
        self.assertFalse(pc.display('BSR',25,8,day=DAY).verified)
    def test_adjusted_off_grid(self):
        self.assertFalse(pc.display('BSR',24.099,6.87,day=DAY).verified)
    def test_rounding(self):
        self.assertEqual(pc.ordinary_limits(22.55,'HOSE'),(24.1,21.0));self.assertEqual(pc.ordinary_limits(10,'HNX'),(11.,9.));self.assertEqual(pc.ordinary_limits(10,'UPCOM'),(11.5,8.5))
    def test_duplicates(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'test.csv';p.write_text('trading_date,symbol,exchange,reference_price,ceiling_price,floor_price\n'+DAY+',BSR,HOSE,22.55,24.10,21.00\n'+DAY+',BSR,HOSE,22.55,24.05,21.00\n',encoding='utf8')
            self.assertEqual(pc._read(str(p),0),{})
    def test_provider_guard(self):
        rows=[dict(trading_date=DAY,symbol='A'+str(i).zfill(2),exchange='HNX',reference_price=10,ceiling_price=11,floor_price=9) for i in range(100)]
        prices={r['symbol']:10. for r in rows};self.assertEqual(normalize(Fake(rows),DAY,'ssi',prices)[1],100)
        for date,pr in [('2026-11-26',prices),(DAY,{k:10000 for k in prices})]:
            with self.assertRaises(RuntimeError):normalize(Fake(rows),date,'ssi',pr)
    def test_source_date_format(self):
        self.assertEqual(pc.day_key('27/11/2026'),DAY)

class TestDirectSSI(unittest.TestCase):
    def setUp(self):
        self.r=dict(stockSymbol='BSR',tradingDate='20261127',refPrice=22550,ceiling=24100,floor=21000,matchedPrice=24100)
        self.p={'BSR':24.1}
    def norm(self,r,market='HOSE',source='SSI_IBOARD_PUBLIC'):
        from sync_price_limits import normalize_ssi_row
        return normalize_ssi_row(r,DAY,market,self.p,source)
    def test_public_valid(self):
        v=self.norm(self.r);self.assertEqual(v['ceiling_price'],24.1);self.assertEqual(v['reference_price'],22.55)
    def test_missing_and_old_date(self):
        for d in (None,'20261126','15:00:00'):self.assertIsNone(self.norm(dict(self.r,tradingDate=d)))
    def test_adjusted_or_wrong_units(self):
        for p in (24.1,24000,24101):self.assertIsNone(self.norm(dict(self.r,matchedPrice=p)))
    def test_invalid_exchange(self):self.assertIsNone(self.norm(dict(self.r,exchange='HNX')))
    def test_bad_limits(self):self.assertIsNone(self.norm(dict(self.r,ceiling=24110)))
    def test_direct_v2(self):
        r=dict(Symbol='BSR',TradingDate='27/11/2026',RefPrice='22550',CeilingPrice='24100',FloorPrice='21000',ClosePrice='24100')
        self.assertEqual(self.norm(r,source='SSI_FASTCONNECT_DIRECT')['ceiling_price'],24.1)
    def test_payload_schema(self):
        from sync_price_limits import api_rows
        self.assertEqual(api_rows(dict(code='SUCCESS',data={'stockData':[self.r]})),[self.r])
        with self.assertRaises(RuntimeError):api_rows(dict(code='ERROR',data=[self.r]))
    def test_three_boards(self):
        from sync_price_limits import collect_public
        with patch('sync_price_limits.request_json',side_effect=[dict(code='SUCCESS',data=[]),dict(code='SUCCESS',data=[self.r]),dict(code='SUCCESS',data=[]),dict(code='SUCCESS',data=[])]):
            self.assertEqual(len(collect_public(DAY,self.p).rows),1)

    def test_vnall_requires_explicit_exchange(self):
        self.assertIsNone(self.norm(self.r,market='VNALL'))
        self.assertEqual(self.norm(dict(self.r,exchange='HOSE'),market='VNALL')['exchange'],'HOSE')
        self.assertEqual(self.norm(dict(self.r,board='HOSE'),market='VNALL')['exchange'],'HOSE')
    def test_vnall_full_stops_extra_requests(self):
        from sync_price_limits import collect_public
        rows=[dict(self.r,stockSymbol='A'+str(i).zfill(2),exchange='HOSE') for i in range(100)]
        rows.append(dict(self.r,exchange='HOSE'))
        prices={r['stockSymbol']:24.1 for r in rows}
        with patch('sync_price_limits.request_json',return_value=dict(code='SUCCESS',data={'stockData':rows})) as req:
            self.assertEqual(len(collect_public(DAY,prices).rows),101)
            req.assert_called_once_with('https://iboard-query.ssi.com.vn/stock/group/VNALL')
    def test_vnall_wrong_day_rejected(self):
        self.assertIsNone(self.norm(dict(self.r,exchange='HOSE',tradingDate='20261126'),market='VNALL'))
    def test_headers(self):
        from sync_price_limits import request_json
        from unittest.mock import MagicMock
        resp=MagicMock();resp.__enter__.return_value.read.return_value=b'{"code":"SUCCESS","data":[]}'
        with patch('sync_price_limits.urlopen',return_value=resp) as call:
            request_json('https://iboard-query.ssi.com.vn/stock/group/VNALL')
            req=call.call_args.args[0]
            self.assertEqual(req.get_header('Origin'),'https://iboard.ssi.com.vn')
            self.assertEqual(req.get_header('Referer'),'https://iboard.ssi.com.vn/')

if __name__=='__main__':unittest.main()
