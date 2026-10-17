# 📈 Trạm Tín Hiệu Chứng Khoán Việt Nam

Streamlit app: screener + thẻ lý do (Wyckoff, Volume, Ichimoku, MA) + biểu đồ nến + backtest từ chính dữ liệu bạn tải lên.

## Chạy local
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploy (Streamlit Community Cloud)
1. Push repo này lên GitHub.
2. Vào https://share.streamlit.io → **New app** → chọn repo, branch `main`, file `app.py`.
3. Bấm **Deploy**.

## Dữ liệu
- Đặt file Excel CafeF (cột: Mã, Ngày, Giá mở cửa, Giá cao nhất, Giá thấp nhất, Giá đóng cửa, Khối lượng khớp lệnh) vào thư mục `data/` của repo, **hoặc** tải lên trực tiếp trên thanh bên của app.
- Cần tối thiểu ~60 phiên mỗi mã để các chỉ báo (Ichimoku, MA50) và backtest có ý nghĩa; MA200 cần 200 phiên.

> Chỉ phục vụ nghiên cứu, không phải khuyến nghị đầu tư.
