# 📈 Trạm Tín Hiệu Chứng Khoán Việt Nam

Streamlit app phân tích kỹ thuật cổ phiếu Việt Nam, giữ nguyên bộ lọc và trang chi tiết hiện có. Bản này bổ sung **nguồn dữ liệu Vnstock tự động** bên cạnh chế độ Excel.

## Chạy trên Windows

1. Cài Python 3.10+.
2. Giải nén ZIP, mở Terminal/CMD trong thư mục `tram-tin-hieu-ck`.
3. Tạo môi trường và cài thư viện:

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
streamlit run app.py
```

Trên macOS/Linux, kích hoạt môi trường bằng `source .venv/bin/activate`.

## Rổ mã theo nhóm ngành (mới)
- Ở chế độ **Vnstock tự động**, thanh bên có ô **Rổ mã**: chọn VN30 và các nhóm ngành (dầu khí, cảng biển, vận tải, cao su, phân bón, bán lẻ, ngân hàng, chứng khoán, bất động sản, khoáng sản, thép, thủy sản, dược phẩm). Mặc định chọn tất cả. Có thêm mục "Danh mục cũ của bạn" (130 mã cũ) và ô **Mã thêm tay**.
- VN30 lấy trực tiếp từ vnstock mỗi 12 giờ; nếu lấy lỗi, app dùng danh sách dự phòng trong `watchlist.py` và ghi rõ ở thanh bên. Hãy đối chiếu lại danh sách dự phòng với rổ VN30 hiện hành.
- Các nhóm ngành nằm trong `watchlist.py` (biến `GROUPS`). Đó là danh sách khởi đầu, hãy sửa theo cách bạn phân ngành. Một mã có thể thuộc nhiều nhóm (ví dụ GVR vừa ở VN30 vừa ở Cao su). Mã không thuộc nhóm nào hiện là "Khác".
- Trang **Bộ lọc** có thêm cột **Nhóm** và **Wyckoff**, cùng hai bộ lọc **Nhóm ngành** và **Wyckoff** (Tích lũy, Phân phối, hoặc đã có Spring/UT/SOS/SOW ở pha C–E). Bộ lọc nhóm hoạt động cả khi dùng file Excel.

## Phân tích Wyckoff (mới)
Lớp **Wyckoff** trên biểu đồ (bật/tắt cùng các lớp khác, mặc định bật) tự tìm vùng đi ngang gần nhất, phân loại tích lũy hoặc phân phối theo xu hướng trước đó và hướng thoát, rồi vẽ hộp vùng, các đường biên kéo dài và nhãn sự kiện:
- Tích lũy: SC, AR, ST, Spring, Test, SOS, LPS.
- Phân phối: BC, AR, ST, UT/UTAD, Test, SOW, LPSY.

Thẻ **Phân tích Wyckoff** ở cột bên phải cho biết pha A–E, mức khớp mẫu, mốc xác nhận, mốc vô hiệu và giải thích từng sự kiện. Code nằm trong `wyckoff.py`; ngưỡng (volume từ 1,5 lần cho SC, biên độ từ 1,2 ATR, biên tối thiểu 30 nến…) chỉnh ngay trong file đó.

Lưu ý: đây là quy tắc máy tính nên mang tính chủ quan, có thể gắn nhãn khác cách bạn đọc, và vẫn có thể cho ra "cấu trúc" trên dữ liệu ngẫu nhiên (thử trên 40 chuỗi giá ngẫu nhiên có khoảng 9 chuỗi hiện pha C–E). Chỉ dùng để quan sát cùng các chỉ báo khác, không tính vào điểm tín hiệu và backtest. Nến ngày đang chạy trong phiên có thể chưa đóng nên nhãn có thể đổi.

## Hai chế độ dữ liệu

### 1. Excel CafeF
- Chọn **Excel CafeF** ở thanh bên và tải file `.xlsx`, hoặc đặt file trong `data/`.
- Giữ nguyên quy trình và dữ liệu như phiên bản trước.

### 2. Vnstock tự động
- Chọn **Vnstock tự động** ở thanh bên.
- Nhập danh sách mã phân cách bằng dấu phẩy, ví dụ `FPT,HPG,VCB,SSI,VND,MBS`.
- Chọn ngày bắt đầu lịch sử và chu kỳ làm mới bảng giá.
- Lần đầu tải lịch sử theo từng mã; lịch sử được cache 60 phút. Bảng giá được polling lại theo TTL 10 giây và giao diện tự rerun theo chu kỳ đã chọn.
- Nguồn bảng giá thử KBS trước, sau đó VCI. Nếu nguồn từ chối truy cập, ứng dụng sẽ báo lỗi thay vì giả lập dữ liệu.

## Giới hạn quan trọng

- **Đây là polling qua REST/API, không phải kết nối WebSocket trực tiếp tới sở giao dịch.** Chu kỳ làm mới 5 giây chỉ là nhịp hỏi lại ứng dụng; nguồn dữ liệu có thể trễ hơn, giới hạn lượt gọi hoặc không trả dữ liệu.
- Không có API key vẫn có thể thử các tuyến được Vnstock cho phép ở cấp khách, nhưng hạn mức và nguồn khả dụng có thể thay đổi. Nếu dùng thường xuyên, hãy tạo tài khoản/khóa API theo hướng dẫn Vnstock và kiểm tra `vnstock policy`.
- Bộ lọc cổ phiếu với nhiều mã sẽ cần nhiều yêu cầu lịch sử. Hãy thử 5–10 mã trước; không nên đặt chu kỳ quá ngắn khi chưa xác minh hạn mức.
- Giá realtime được đưa vào nến ngày hiện tại **chỉ khi nguồn trả đủ Open/High/Low/Close**. Nếu bảng giá không trả đủ trường, ứng dụng giữ nguyên OHLCV lịch sử thay vì tự bịa nến. Vì vậy một số chỉ báo có thể vẫn dựa trên nến gần nhất đã có.
- Khung tuần/tháng được gộp từ dữ liệu ngày; nến tuần/tháng đang diễn ra chưa đóng. Tín hiệu trong phiên có thể thay đổi đến khi nến đóng cửa.
- Vnstock là thư viện kết nối tới nguồn bên thứ ba, không phải đơn vị phát hành dữ liệu. Cần tuân thủ điều khoản và quyền sử dụng dữ liệu của nguồn.
- Chỉ báo và tín hiệu dùng cho nghiên cứu, không phải khuyến nghị mua/bán.

## Cấu trúc

- `app.py`: giao diện Streamlit, bộ lọc, biểu đồ và điều hướng.
- `engine.py`: làm sạch dữ liệu, gộp nến, tính chỉ báo, điểm số, backtest.
- `realtime_data.py`: adapter dữ liệu Vnstock, chuẩn hóa OHLCV và bảng giá (tự chờ và thử lại khi nguồn báo giới hạn tần suất).
- `watchlist.py`: VN30 và các nhóm ngành.
- `wyckoff.py`: nhận diện vùng, sự kiện và pha Wyckoff.
- `requirements.txt`: các thư viện cần cài.

## Deploy

Có thể deploy Streamlit Community Cloud nếu môi trường deploy cho phép truy cập nguồn dữ liệu. Lưu ý máy chủ cloud cũng phải tuân thủ giới hạn truy cập và giấy phép dữ liệu. Với nhu cầu polling liên tục trong phiên, nên chạy trên máy/VPS ổn định và giám sát lỗi nguồn.
