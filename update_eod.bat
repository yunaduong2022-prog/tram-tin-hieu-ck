@echo off
rem Lay du lieu cuoi phien tren may nay roi day len GitHub (phuong an du phong khi GitHub Actions bi nguon chan).
cd /d %~dp0
python eod_fetch.py
python update_index.py
python update_metadata.py
rem Ghi tin hieu moi cua ngay va do ket qua cac tin hieu cu (forward test)
python forward_log.py
git add data/eod_prices.csv data/eod_meta.json data/stock_metadata.csv data/shares_outstanding.csv data/index_prices.csv
if exist data\nhom_von_hoa_gia.csv git add data/nhom_von_hoa_gia.csv
if exist data\forward_signals.csv git add data/forward_signals.csv data/forward_summary.csv
git commit -m "Du lieu cuoi phien (chay tren may)"
git push
pause
