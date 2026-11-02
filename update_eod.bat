@echo off
setlocal
cd /d "%~dp0"
set "PY=%USERPROFILE%\.venv\Scripts\python.exe"
set "GIT=C:\Program Files\Git\cmd\git.exe"
if not exist "%PY%" goto fail
if not exist "%GIT%" goto fail
"%GIT%" diff --cached --quiet
if errorlevel 1 goto fail
"%PY%" eod_fetch.py
if errorlevel 1 goto fail
"%PY%" update_index.py
if errorlevel 1 goto fail
"%PY%" update_metadata.py
if errorlevel 1 goto fail
"%PY%" forward_log.py
if errorlevel 1 goto fail
"%PY%" validate_eod.py %*
if errorlevel 1 goto fail
"%GIT%" add -- data/eod_prices.csv data/eod_meta.json data/stock_metadata.csv data/shares_outstanding.csv data/index_prices.csv
if errorlevel 1 goto fail
if exist data\nhom_von_hoa_gia.csv "%GIT%" add -- data/nhom_von_hoa_gia.csv
if errorlevel 1 goto fail
if exist data\forward_signals.csv "%GIT%" add -- data/forward_signals.csv
if errorlevel 1 goto fail
if exist data\forward_summary.csv "%GIT%" add -- data/forward_summary.csv
if errorlevel 1 goto fail
"%GIT%" diff --cached --quiet
if not errorlevel 1 goto nochange
"%GIT%" diff --cached --name-only | findstr /r /c:"^data/" >nul
if errorlevel 1 goto fail
"%GIT%" commit -m "Cap nhat du lieu cuoi phien tu Windows"
if errorlevel 1 goto fail
"%GIT%" push origin main
if errorlevel 1 goto fail
 echo THANH CONG: da dong bo GitHub.
exit /b 0
:nochange
 echo Khong co du lieu thay doi; khong can push.
exit /b 0
:fail
 echo BLOCK: cap nhat hoac kiem tra that bai. KHONG TU DONG PUSH.
exit /b 1