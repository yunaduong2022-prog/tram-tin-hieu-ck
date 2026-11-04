"""All symbols held in the actual daily EOD CSV, including stale/excluded ones.

Only local file reads. No VNStock/network, no portfolio files and no fake candles.
"""
from __future__ import annotations

import pandas as pd

REQUIRED = ['Mã', 'Ngày', 'Giá mở cửa', 'Giá cao nhất', 'Giá thấp nhất',
            'Giá đóng cửa', 'Khối lượng khớp lệnh']


def list_symbols(path):
    column = pd.read_csv(path, usecols=['Mã'], dtype={'Mã': str}, encoding='utf-8-sig')
    return sorted({x for x in column['Mã'].dropna().astype(str).str.strip().str.upper()
                   if x and x != 'NAN'})


def read_symbol(path, code):
    frame = pd.read_csv(path, usecols=REQUIRED, dtype={'Mã': str}, encoding='utf-8-sig')
    frame = frame.loc[frame['Mã'].astype(str).str.strip().str.upper().eq(str(code).upper())].copy()
    return frame
