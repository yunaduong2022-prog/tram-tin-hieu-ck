@echo off
rem Lay du lieu cuoi phien tren may nay roi day len GitHub (phuong an du phong khi GitHub Actions bi nguon chan).
cd /d %~dp0
python eod_fetch.py
git add data/eod_prices.csv data/eod_meta.json
git commit -m "Du lieu cuoi phien (chay tren may)"
git push
pause
