"""Read-only EOD and moving-average reconciliation for three Min Invest tabs.

Never changes the trading engines, stored signals, stop/targets or data.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def eod_consistency(daily, asof):
    """Check all three tabs' global EOD argument against the underlying bars."""
    if daily is None or daily.empty or 'Ngày' not in daily or 'Mã' not in daily:
        return False, 'Không có dữ liệu EOD hợp lệ.'
    expected = pd.to_datetime(asof, errors='coerce')
    if pd.isna(expected):
        return False, 'Ngày EOD tham chiếu không hợp lệ.'
    expected = expected.normalize()
    actual = pd.to_datetime(daily['Ngày'], errors='coerce', dayfirst=True).dropna()
    if actual.empty:
        return False, 'Không có ngày giao dịch hợp lệ.'
    latest = actual.max().normalize()
    if latest != expected:
        return False, f'Ngày EOD của dữ liệu ({latest:%d/%m/%Y}) khác ngày chung của website ({expected:%d/%m/%Y}).'
    return True, f'EOD chung {expected:%d/%m/%Y}'


def render_eod_guard(daily, asof):
    """Same check shared by MA Structure, State Map and Trading T+2."""
    import streamlit as st
    good, message = eod_consistency(daily, asof)
    if not good:
        st.error('DỮ LIỆU BA TAB CHƯA ĐỒNG BỘ: ' + message + ' Dừng phân tích để tránh trộn phiên.')
        return False
    st.caption('Liên kết 3 tab · ' + message + ' · Cùng nguồn nến EOD; mã tìm kiếm đơn lẻ được đồng bộ khi chuyển tab.')
    return True


def ma_audit(daily, ma_row, code, asof):
    """Compare *display* SMA levels without changing any existing classifier.

    MA9 (T+2) and MA10 (MA Structure) are different lookbacks and must not
    be treated as equal. All averages use confirmed closes through asof.
    """
    empty = {'status': 'CHƯA ĐỦ DỮ LIỆU', 'reason': '', 'ma9_t2': np.nan,
             'ma10_calc': np.nan, 'ma10_structure': np.nan,
             'ma20_calc': np.nan, 'ma20_structure': np.nan,
             'ma20_match': None, 'ma10_match': None, 'date': None}
    if daily is None or daily.empty or not {'Mã', 'Ngày', 'Giá đóng cửa'}.issubset(daily):
        return dict(empty, reason='Thiếu OHLCV EOD.')
    expected = pd.Timestamp(asof).normalize()
    g = daily.loc[daily['Mã'].astype(str).str.upper().str.strip() == str(code).upper(),
                  ['Ngày', 'Giá đóng cửa']].copy()
    g['Ngày'] = pd.to_datetime(g['Ngày'], errors='coerce', dayfirst=True).dt.normalize()
    g['Giá đóng cửa'] = pd.to_numeric(g['Giá đóng cửa'], errors='coerce')
    g = g.loc[g['Ngày'].notna() & (g['Ngày'] <= expected)]
    if g.empty or g['Ngày'].duplicated().any():
        return dict(empty, reason='Thiếu nến hoặc có ngày EOD trùng, không đối chiếu MA.')
    g = g.sort_values('Ngày')
    if g.iloc[-1]['Ngày'] != expected:
        return dict(empty, reason='Cổ phiếu không có giá đóng cửa đúng phiên EOD chung.')
    if len(g) < 20 or not (g['Giá đóng cửa'].tail(20).notna().all() and (g['Giá đóng cửa'].tail(20) > 0).all()):
        return dict(empty, reason='Cần 20 giá đóng cửa hợp lệ để đối chiếu MA20.')
    closes = g['Giá đóng cửa']
    ma9, ma10, ma20 = (float(closes.tail(n).mean()) for n in (9, 10, 20))
    stored10 = pd.to_numeric(ma_row.get('MA10'), errors='coerce')
    stored20 = pd.to_numeric(ma_row.get('MA20'), errors='coerce')
    def same(a, b):
        return bool(pd.notna(b) and np.isfinite(float(b)) and abs(float(a)-float(b)) <= 0.015)
    return {'status': 'ĐỒNG BỘ' if same(ma10, stored10) and same(ma20, stored20) else 'CẦN ĐỐI CHIẾU',
            'reason': 'MA9 là SMA9 của T+2; MA10 là SMA10 của Cấu trúc MA. SMA20 dùng 20 giá đóng cửa.',
            'ma9_t2': ma9, 'ma10_calc': ma10, 'ma10_structure': stored10,
            'ma20_calc': ma20, 'ma20_structure': stored20,
            'ma10_match': same(ma10, stored10), 'ma20_match': same(ma20, stored20), 'date': expected}


def render_ma_audit(audit):
    """A single-ticker transparent comparison inside T+2 context only."""
    import streamlit as st
    if not audit:
        return
    with st.expander('Đối chiếu MA giữa ba tab · cùng phiên EOD', expanded=False):
        if audit['status'] == 'CHƯA ĐỦ DỮ LIỆU':
            st.warning(audit['reason'])
            return
        def fmt(x):
            v = pd.to_numeric(x, errors='coerce')
            return f'{float(v):.2f}' if pd.notna(v) else '—'
        st.dataframe(pd.DataFrame([
            {'Chỉ báo': 'MA9 · Trading T+2', 'Tính từ EOD': fmt(audit['ma9_t2']), 'Hiển thị Cấu trúc MA': 'Không dùng MA9', 'Khớp': 'Khác chu kỳ MA10'},
            {'Chỉ báo': 'MA10 · Cấu trúc MA', 'Tính từ EOD': fmt(audit['ma10_calc']), 'Hiển thị Cấu trúc MA': fmt(audit['ma10_structure']), 'Khớp': 'Có' if audit['ma10_match'] else 'Không'},
            {'Chỉ báo': 'MA20 · dùng chung chu kỳ', 'Tính từ EOD': fmt(audit['ma20_calc']), 'Hiển thị Cấu trúc MA': fmt(audit['ma20_structure']), 'Khớp': 'Có' if audit['ma20_match'] else 'Không'},
        ]), hide_index=True, use_container_width=True)
        if audit['status'] != 'ĐỒNG BỘ':
            st.warning('MA10 hoặc MA20 đang lệch dữ liệu EOD nguồn. Không thay đổi tín hiệu T+2 tự động; cần kiểm tra nguồn và cách tính MA.')
        st.caption('Hỗ trợ/kháng cự từ Bản đồ trạng thái, cắt lỗ gốc và TP động của T+2 được tính theo các quy tắc khác nhau. Không thay mức của tab này bằng mức của tab khác; chỉ so sánh khi cùng mã, cùng EOD và có dữ liệu hợp lệ.')
