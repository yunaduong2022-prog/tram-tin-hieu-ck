import hashlib,json,unittest
from datetime import date,timedelta
import pandas as pd
from dnse_online_private import decode,models_for,object_key
from dnse_online_card import card_html
from dnse_online_validate import SOURCE

class Tests(unittest.TestCase):
    def setUp(self):
        self.dates=[(date(2026,11,8)+timedelta(days=i)).isoformat() for i in range(20)]
        self.day=self.dates[-1];self.code='BSR'
        self.r=dict(symbol=self.code,date=self.day,board='G1',source=SOURCE,close_vnd='24000',eod_volume=100000,buy_vol=60000,sell_vol=39000,unknown_vol=1000,buy_val='1440000000',sell_val='936000000',unknown_val='24000000',total_val='2400000000')
        self.b=dict(version=1,target=self.day,dates=self.dates,scope=sorted([self.code]+[f'{i:03d}' for i in range(238)]),rows={self.code+'_'+d:dict(self.r,date=d) for d in self.dates},quotes={self.code:dict(close='24000',volume=100000,floor=False,ceiling=True,offer=None,bid=1402100)})
        self.df=pd.DataFrame([{'Mã':self.code,'Ngày':d,'Giá thấp nhất':23,'Giá cao nhất':24,'Giá đóng cửa':24,'Khối lượng khớp lệnh':100000} for d in self.dates])
    def test_complete(self):
        m,q=models_for(self.b,self.code,self.dates,self.df);self.assertEqual(m[20]['total'],(1200000,780000));self.assertEqual(m[20]['unknown'],20000);self.assertEqual(q['bid'],1402100)
    def test_missing(self):
        del self.b['rows'][self.code+'_'+self.dates[-2]];m,q=models_for(self.b,self.code,self.dates,self.df);self.assertEqual(m[5]['count'],4);self.assertIsNone(m[5]['total']);self.assertIsNotNone(m[1]['total'])
    def test_eod_mismatch(self):
        self.df.loc[19,'Khối lượng khớp lệnh']=1;m,q=models_for(self.b,self.code,self.dates,self.df);self.assertIsNone(m[1]['total']);self.assertIsNone(q)
    def test_wrong_dates(self):self.assertEqual(models_for(self.b,self.code,self.dates[:-1],self.df),(None,None))
    def test_outside_scope(self):self.assertEqual(models_for(self.b,'ZZZ',self.dates,self.df),(None,None))
    def test_hash(self):
        blob=json.dumps(self.b).encode();self.assertEqual(decode(blob,hashlib.sha256(blob).hexdigest(),self.day)['target'],self.day)
        with self.assertRaises(ValueError):decode(blob,'bad',self.day)
    def test_key(self):self.assertEqual(object_key({'prefix':'abc'},self.day),'abc/dnse-personal-v1/'+self.day+'.json')
    def test_html(self):
        m,q=models_for(self.b,self.code,self.dates,self.df);h=card_html(m,quote=q,code=self.code,date=self.day,source='DNSE');self.assertIn('ĐÁNH GIÁ DÒNG TIỀN CHỦ ĐỘNG',h);self.assertIn('1.402.100',h);self.assertIn('Chưa xác định',h)


class AccessTests(unittest.TestCase):
    def test_disabled_does_not_fetch(self):
        import sys
        from types import SimpleNamespace
        from unittest.mock import patch, Mock
        import dnse_online_private as mod
        st=SimpleNamespace(secrets={'dnse_personal':{'enabled':False}},container=Mock())
        with patch.dict(sys.modules,{'streamlit':st}), patch.object(mod,'_download') as download:
            mod.render('BSR',None,None,key='stock')
            download.assert_not_called();st.container.assert_not_called()
    def test_enabled_without_password_renders(self):
        import sys
        from types import SimpleNamespace
        from unittest.mock import patch, Mock
        from contextlib import nullcontext
        import dnse_online_private as mod
        fixture=Tests();fixture.setUp()
        st=SimpleNamespace(secrets={'dnse_personal':{'enabled':True}},container=lambda **kw:nullcontext(),cache_data=lambda **kw:lambda f:f,markdown=Mock(),caption=Mock())
        with patch.dict(sys.modules,{'streamlit':st}), patch.object(mod,'calendar_sessions',return_value=pd.to_datetime(fixture.dates)), patch.object(mod,'_download',return_value=fixture.b) as download:
            mod.render('BSR',fixture.df,fixture.day,key='stock')
            download.assert_called_once_with(fixture.day)
            st.markdown.assert_called_once();st.caption.assert_not_called()
