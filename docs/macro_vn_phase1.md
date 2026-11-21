# Trạm Tín Hiệu · Vĩ mô Việt Nam (Giai đoạn 1)

## Phạm vi

- Tạo 6 chuyên mục tại `Vĩ mô`: Tổng quan; Chu kỳ & Lạm phát; Tiền tệ & Thanh khoản; Tài khóa; Quốc tế; Tác động ngành.
- Mục **Quốc tế** gọi nguyên `us_overnight_macro.render()` (9 công cụ cũ, bao gồm trang phân tích chi tiết và tự làm mới khi đang mở).
- Dữ liệu Việt Nam ở `data/macro_vn.csv`: snapshot kiểm chứng bằng nguồn công bố, không phải giá realtime hoặc dữ liệu EOD.
- Các mục tín dụng, OMO, lãi suất liên ngân hàng, USD/VND không có bản ghi xác thực sẽ hiện **Chưa có số liệu**, KHÔNG dùng dữ liệu quá khứ hoặc giá khác nguồn thay thế.
- Hồ sơ NHNN đã có ở VNINDEX được gọi lại (tùy chọn) chứ không sao chép sang bảng vĩ mô.
- Trạng thái chu kỳ kinh tế chưa được phân loại tự động cho tới khi đủ PMI, lạm phát, lãi suất, tín dụng và nhiều kỳ tăng trưởng.
- Không động chạm `engine.py`, nguồn EOD/DNSE, VIP, Backtest, xu hướng/mua bán, bảng VNINDEX, luồng RSI hoặc mô hình dự báo.

## Cập nhật snapshot an toàn

File `data/macro_vn.csv` gồm `id,group,label,period,asof,value,unit,comparison,source,source_url,note`.

1. Mở nguồn gốc từ cơ quan công bố (NSO, NHNN, Bộ Tài chính), kiểm tra kỳ gốc và mẫu số.
2. Thêm hàng có `id` cố định, `period` và ngày cuối kỳ `asof` ISO `YYYY-MM-DD`. Không dùng ngày tải dữ liệu thay cho kỳ kinh tế.
3. Chỉ nhập `value` khi có số cụ thể từ nguồn; không ghi giá tham khảo hoặc nhận định vào cột số.
4. Không đặt trùng `id + period + asof`. Trùng hoặc sai URL bị loại khỏi hiển thị.
5. Chạy `python -m unittest -v test_macro_vn_dashboard` trước khi commit.
6. Nếu số liệu bị sửa lại, thay bản ghi cũ theo cùng kỳ và ghi chú nguồn; không giữ hai bản ghi mâu thuẫn.

## Nguồn snapshot ban đầu

- GDP quý I, II, III/2026 và 9T/2026: Cục Thống kê, báo cáo quý III và 9T: https://www.nso.gov.vn/bai-top/2026/10/bao-cao-tinh-hinh-kinh-te-xa-hoi-quy-iii-va-9-thang-nam-2026/
- CPI tháng 10, CPI lõi bình quân 10 tháng, IIP 10 tháng, thu NSNN 10 tháng, cán cân thương mại 10 tháng: Cục Thống kê, báo cáo tháng 10 và 10T: https://www.nso.gov.vn/bai-top/2026/11/bao-cao-tinh-hinh-kinh-te-xa-hoi-thang-muoi-va-10-thang-nam-2026/
- Giải ngân đầu tư công 10T: Bộ Tài chính, ngày 5/11/2026, 74,1% kế hoạch TTCP giao tương ứng 708.567,4 tỷ VND: https://www.mof.gov.vn/tin-tuc-tai-chinh/thoi-su/10-thang-2026-ca-nuoc-giai-ngan-dat-741percent-ke-hoach

**Quan trọng:** 74,1% dùng kế hoạch 955.867,4 tỷ làm mẫu số. Tỷ lệ 76,6% trong báo cáo khác loại trừ một phần kế hoạch, không so sánh trực tiếp. GDP quý III không phải GDP 9 tháng; CPI cùng kỳ tháng Mười không phải CPI bình quân 10 tháng. Tăng trưởng GDP theo quý ở đây là so với *cùng kỳ năm trước*.

## Kiểm thử

`python -m unittest -v test_macro_vn_dashboard`

Cảnh báo dữ liệu quá kỳ chỉ giúp người xem kiểm tra bản công bố mới; không tự động tải số từ trang báo điện tử. Giai đoạn kế tiếp có thể kết nối API chính thức có schema ổn định và lưu provenance theo từng lần đồng bộ.
