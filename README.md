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

## Ngành > Cảnh báo luân chuyển dòng tiền (mới)
Code ở `sector_rotation.py`, ngưỡng ở `CFG`. Chỉ số ngành = bình quân đều các mã trong `watchlist.GROUPS`; RS ngành = chỉ số ngành / VN-Index. Năm cảnh báo:
- **Ngành tăng RS liên tục**: RS ngành tăng 5 phiên liền nhau.
- **Độ rộng tăng nhanh**: tỷ lệ mã trên MA20 tăng ≥ 15 điểm % trong 5 phiên.
- **Tiền vào, giá chưa chạy xa**: GTGD ngành TB5 ≥ 1.2 lần TB20 nhưng giá ngành tăng ≤ 8% trong 10 phiên.
- **Cổ phiếu dẫn đầu vừa vượt nền**: mã top 3 RS ngành, trong 3 phiên gần nhất đóng cửa vượt đỉnh 20 phiên với khối lượng ≥ 1.5 lần TB20.
- **Ngành mạnh bắt đầu mất RS**: RS 20 phiên cách đây 10 phiên > 1, RS ngành nay thấp hơn 10 phiên trước, và độ rộng giảm ≥ 15 điểm % hoặc ≥ 25% mã vừa thủng MA20.
Bốn cảnh báo đầu là dòng tiền đang vào, cảnh báo cuối là dòng tiền đang rời. Ngành dưới 3 mã có dữ liệu bị bỏ qua.

## Mục Cạn cung (mới)
Nằm ở **Bộ lọc & Backtest**, ngay sau **Giảm mạnh**. Code ở `dry_supply.py`, không đặt thêm điều kiện mới mà gom mọi nơi app đang nói mã cạn cung:
- **Lọc CP: Cạn cung**: cờ `DryUp` ở Lọc tất cả CP (khối lượng phiên cuối < 0.7 lần MA20 Vol, giá ≥ MA20, biên độ phiên < 2%).
- **Điểm mua đẹp** (Chờ mua / Mua ngay): test lại hỗ trợ với khối lượng 5 phiên ≤ 0.8 lần MA20 Vol.
- **Siết nền giá** (Chờ mua): nền chặt, khối lượng 5 phiên ≤ 0.9 lần MA20 Vol.
- **Wyckoff**: tích lũy Pha C/D, sự kiện mới nhất là Spring / Test / LPS với volume thấp, trong 10 phiên gần nhất và phiên cuối chưa nổ volume (`MAX_EV_AGE`, `MAX_LAST_VOL`).
Mã được nhiều nguồn cùng báo xếp trước. Trạng thái chỉ ghi "khối lượng co lại" (Theo dõi điểm mua) không tính. Mục này cũng hiện trong sơ đồ của **Bộ lọc Realtime**.

## Thị trường > Tổng quan (mới)
Tab đầu tiên của mục **Thị trường** và cũng là trang mở đầu khi vào app (đổi `DEFAULT_MAIN` trong `nav.py` nếu muốn như cũ). Code nằm trong `market_overview.py`, các ngưỡng ở đầu file.
- **Xu hướng** (VN-Index): Tăng / Đi ngang / Giảm theo tỷ lệ điều kiện đạt: đóng cửa trên MA20, MA20 dốc lên, đóng cửa trên MA50, đáy 10 phiên sau cao hơn đáy trước. Cần mã `VNINDEX` trong `data/eod_prices.csv`.
- **Độ rộng**: số mã tăng so với số mã giảm trong rổ theo dõi.
- **Dòng tiền**: thanh khoản rổ so với trung bình 20 phiên (lệch quá ±10% là Tăng / Giảm), kèm dòng khối ngoại nếu có.
- **Mức độ rủi ro**: Thấp / Vừa / Cao theo số điều kiện rủi ro đang xảy ra (VN-Index dưới MA20, MA20 dốc xuống, mã giảm nhiều hơn mã tăng, thanh khoản dưới trung bình 20 phiên, khối ngoại bán ròng). Cần ít nhất 3 điều kiện có dữ liệu.
- Bên dưới: bản đồ sức mạnh ngành (RS 1 tuần / 1 tháng / 3 tháng), nhóm dẫn dắt và suy yếu, số mã **MUA** (mục Mua ngay) và **CHỜ MUA**, kèm nút chuyển nhanh sang các mục đó.
- Tab **Nhóm ngành** của mục Thị trường nay hiển thị trang Sức mạnh ngành (`sector_dashboard.py`) thay cho trang chờ.

## Ngành > Vị thế cổ phiếu ngành (mới)
Code trong `sector_ranking.py` (ngưỡng ở `CFG`). Chọn một ngành để xem bảng xếp hạng RS của mọi mã trong ngành (giá, Score, RS, RS so với ngành, GTGD 5p/TB20, ROE, trạng thái, vị thế) và 4 góc nhìn dạng thẻ MUA / CHỜ MUA có thêm khối **Vị thế trong ngành**: Mạnh nhất theo RS · Xu hướng tăng + thanh khoản · Tích lũy / gần điểm mua · Yếu hơn ngành / suy yếu. ROE lấy từ `data/fundamentals.csv` hoặc `data/nhap_tay.csv`; thiếu thì hiện trống.

## Cảnh báo phân kỳ RSI & giá (mới)
Thẻ ở **Lọc tất cả CP** và **Chờ mua** có thêm khối cảnh báo phân kỳ RSI(14) so với giá, tính trên khung **D** và **W** từ 2 đỉnh / 2 đáy (pivot) gần nhất. Code nằm trong `rsi_divergence.py`.
- **Cảnh báo đảo chiều**: Phân kỳ thường giảm (giá HH, RSI LH), phân kỳ thường tăng (giá LL, RSI HL), phân kỳ phóng đại (2 đỉnh / 2 đáy giá bằng nhau, RSI đỉnh sau thấp hơn / đáy sau cao hơn) → nhãn `TẠI VÙNG CẢN`.
- **Xác nhận tiếp diễn**: Phân kỳ ẩn tăng (giá HL, RSI LL), phân kỳ ẩn giảm (giá LH, RSI HH).
- Ngưỡng (số nến xác nhận pivot, khoảng cách giữa 2 pivot, độ "tươi" của tín hiệu, dung sai "bằng nhau", chênh lệch RSI tối thiểu) chỉnh ở `PARAMS` và `RSI_MIN_DIFF`. Khung 15m / 1h / 4h đã có sẵn tham số nhưng app chưa có dữ liệu nến này nên chưa hiển thị.
- Tín hiệu tự hết hạn khi giá vượt đỉnh (thủng đáy) của pivot sau. Pivot cần vài nến để xác nhận nên tín hiệu luôn trễ vài nến. Chỉ để tham khảo, không tính vào điểm tín hiệu / backtest và không phải khuyến nghị đầu tư.

## Rổ mã theo nhóm ngành (mới)
- Ở chế độ **Vnstock tự động**, thanh bên có ô **Rổ mã**: chọn VN30 và các nhóm ngành (dầu khí, cảng biển, vận tải, cao su, phân bón, bán lẻ, ngân hàng, chứng khoán, bất động sản, khoáng sản, thép, thủy sản, dược phẩm). Mặc định chọn tất cả. Có thêm mục "Danh mục cũ của bạn" (130 mã cũ) và ô **Mã thêm tay**.
- VN30 lấy trực tiếp từ vnstock mỗi 12 giờ; nếu lấy lỗi, app dùng danh sách dự phòng trong `watchlist.py` và ghi rõ ở thanh bên. Hãy đối chiếu lại danh sách dự phòng với rổ VN30 hiện hành.
- Các nhóm ngành nằm trong `watchlist.py` (biến `GROUPS`). Đó là danh sách khởi đầu, hãy sửa theo cách bạn phân ngành. Một mã có thể thuộc nhiều nhóm (ví dụ GVR vừa ở VN30 vừa ở Cao su). Mã không thuộc nhóm nào hiện là "Khác".
- Trang **Bộ lọc** có thêm cột **Nhóm** và **Wyckoff**, cùng hai bộ lọc **Nhóm ngành** và **Wyckoff** (Tích lũy, Phân phối, hoặc đã có Spring/UT/SOS/SOW ở pha C–E). Bộ lọc nhóm hoạt động cả khi dùng file Excel.

## Phân tích Wyckoff (mới)
Lớp **Wyckoff** trên biểu đồ (bật/tắt cùng các lớp khác, mặc định tắt, bấm vào mới hiện) tự tìm vùng đi ngang gần nhất, phân loại tích lũy hoặc phân phối theo xu hướng trước đó và hướng thoát, rồi vẽ hộp vùng, các đường biên kéo dài và nhãn sự kiện:
- Tích lũy: SC, AR, ST, Spring, Test, SOS, LPS.
- Phân phối: BC, AR, ST, UT/UTAD, Test, SOW, LPSY.

Vùng đi ngang chỉ tính khi biên độ (đỉnh − đáy) / đáy không quá **10%** (`MAX_AMP` trong `wyckoff.py`). Phiên đóng cửa vượt khung này rồi các phiên sau quay lại khung cũ (tối đa 3 phiên liên tiếp) được ghi là **breakout giả**: vẫn tính vào số nến đi ngang nhưng không tính vào biên trên/dưới.

Thẻ **Phân tích Wyckoff** ở cột bên phải cho biết pha A–E, mức khớp mẫu, mốc xác nhận, mốc vô hiệu và giải thích từng sự kiện. Code nằm trong `wyckoff.py`; ngưỡng (volume từ 1,5 lần cho SC, biên độ từ 1,2 ATR, biên tối thiểu 30 nến…) chỉnh ngay trong file đó.

Lưu ý: đây là quy tắc máy tính nên mang tính chủ quan, có thể gắn nhãn khác cách bạn đọc, và vẫn có thể cho ra "cấu trúc" trên dữ liệu ngẫu nhiên (thử trên 40 chuỗi giá ngẫu nhiên có khoảng 9 chuỗi hiện pha C–E). Chỉ dùng để quan sát cùng các chỉ báo khác, không tính vào điểm tín hiệu và backtest. Nến ngày đang chạy trong phiên có thể chưa đóng nên nhãn có thể đổi.

## Dữ liệu cuối phiên tự động (khuyến nghị)

Thay vì gọi nguồn dữ liệu liên tục mỗi khi mở app (dễ bị giới hạn tần suất), một lịch tự động chạy **1 lần mỗi ngày giao dịch lúc 15:45 giờ VN**, lấy OHLCV ngày của cả rổ mã rồi lưu vào `data/eod_prices.csv`. App chỉ đọc file này nên mở nhanh và không tốn hạn mức.

**Thiết lập (làm một lần):**
1. Đưa toàn bộ thư mục lên GitHub, gồm cả `.github/workflows/eod.yml`. Thư mục `.github` bị ẩn nên kéo thả web thường bỏ sót; hãy vào repo → **Add file → Create new file**, gõ tên `.github/workflows/eod.yml` và dán nội dung file.
2. (Khuyến nghị) Tạo khóa API Cộng đồng miễn phí tại https://vnstocks.com/account#api-key, rồi vào repo → **Settings → Secrets and variables → Actions → New repository secret**, tên `VNSTOCK_API_KEY`. Không có khóa thì chạy ở cấp Khách với hạn mức chặt nhất.
3. Vào tab **Actions → Cập nhật dữ liệu cuối phiên → Run workflow**, tick **Tải lại toàn bộ lịch sử**, bấm chạy. Lần đầu mất vài phút đến vài chục phút (mỗi mã một yêu cầu).
4. Từ đó lịch tự chạy; mỗi lần có dữ liệu mới, bot commit `data/eod_prices.csv` và Streamlit Cloud tự cập nhật app. Ở thanh bên của app chọn **Cuối phiên (tự cập nhật)**.

**Cách hoạt động** (`eod_fetch.py`):
- Rổ mã = VN30 + các nhóm ngành + danh mục cũ trong `watchlist.py` + mã thêm tay trong `data/extra_symbols.txt` (≈190 mã). Thêm `--no-old` để bỏ danh mục cũ.
- Thử lần lượt các nguồn vnstock **vci → kbs → vnd** (đổi bằng `--sources`); `data/eod_meta.json` ghi nguồn đã dùng, mã lỗi và thời điểm cập nhật, app hiển thị ở thanh bên.
- Cập nhật tăng dần: mỗi ngày lấy lại ~14 ngày gần nhất. Nếu giá cũ lệch giá nguồn (cổ phiếu vừa điều chỉnh cổ tức/chia tách) thì tự tải lại toàn bộ lịch sử mã đó để chuỗi giá không đứt đoạn.
- Chạy khi phiên chưa đóng (trước 15:10) thì bỏ nến hôm nay, chỉ giữ dữ liệu đã chốt. Ngày lễ không có nến mới thì không có gì thay đổi.
- Nếu hết hạn mức hoặc quá nhiều mã lỗi, workflow báo đỏ (kèm email của GitHub) nhưng phần đã lấy được vẫn được lưu.

**Phương án dự phòng nếu GitHub bị nguồn chặn:** nguồn dữ liệu có thể từ chối IP của máy chủ GitHub. Khi đó chạy trên máy bạn: `pip install -r requirements-eod.txt`, rồi `python eod_fetch.py` (lần đầu thêm `--full`), sau đó đẩy `data/eod_prices.csv` và `data/eod_meta.json` lên repo. Trên Windows có sẵn `update_eod.bat` làm cả hai bước; đặt trong Task Scheduler chạy 15:45 các ngày thứ Hai đến thứ Sáu.

## Các chế độ dữ liệu khác

### 1. Excel CafeF
- Chọn **Excel CafeF** ở thanh bên và tải file `.xlsx`, hoặc đặt file trong `data/`.
- Giữ nguyên quy trình và dữ liệu như phiên bản trước.

### 2. Vnstock tự động
- Chọn **Vnstock tự động** ở thanh bên.
- Nhập danh sách mã phân cách bằng dấu phẩy, ví dụ `FPT,HPG,VCB,SSI,VND,MBS`.
- Chọn ngày bắt đầu lịch sử và chu kỳ làm mới bảng giá.
- Lần đầu tải lịch sử theo từng mã; lịch sử được cache 60 phút. Bảng giá được polling lại theo TTL 10 giây và giao diện tự rerun theo chu kỳ đã chọn.
- Nguồn bảng giá thử KBS trước, sau đó VCI. Nếu nguồn từ chối truy cập, ứng dụng sẽ báo lỗi thay vì giả lập dữ liệu.

## Tên công ty, P/B, ROE trong thẻ Kết quả lọc (mới)

Thẻ mỗi mã ở trang **Bộ lọc** hiện: Mã (kèm tên công ty bên dưới) · Giá · Ngành · Vốn hóa TT · **P/B** · **ROE** · Dự báo.

- Dữ liệu nằm ở `data/fundamentals.csv` (cột Mã, Tên công ty, P/B, ROE, Cập nhật), do `update_fundamentals.py` tự cập nhật trong workflow cuối phiên.
- **Tên công ty**: lấy hàng loạt từ danh sách mã của vnstock (1 yêu cầu). Muốn đặt tên theo ý bạn, tạo `data/ten_cong_ty_tay.csv` với cột `Mã,Tên công ty`; tên tay luôn được ưu tiên.
- **P/B, ROE**: lấy từ `Fundamental().equity(mã).ratio()` (kỳ báo cáo mới nhất nguồn trả về), mỗi mã một yêu cầu và chỉ hỏi lại sau 7 ngày vì số liệu đổi theo quý. Chức năng này **cần khóa API vnstock cấp Cộng đồng** (secret `VNSTOCK_API_KEY`); cấp Khách không được cấp quyền. ROE nếu nguồn trả dạng tỷ lệ (0,15) sẽ tự đổi thành phần trăm.
- Điền tay P/B, ROE: sửa `data/fundamentals.csv`, đặt cột Cập nhật = `tay` thì không bị ghi đè.
- Không có số thì thẻ hiện "Chưa có dữ liệu". Cột P/B âm hoặc lớn hơn 200 bị bỏ qua.
- **Chẩn đoán**: vnstock đổi tên cột theo phiên bản nên việc đọc P/B, ROE là tự dò. Nếu thẻ vẫn trống, vào tab Actions → Run workflow → điền mã (ví dụ `HPG`) vào ô **probe** để xem nguồn trả về những cột nào (hoặc chạy `python update_fundamentals.py --probe HPG` trên máy).

## Nhập tay tên công ty, vốn hóa, P/B, ROE (mới)

Mở `data/nhap_tay.csv` (đã liệt kê sẵn ~190 mã, 4 cột để trống), điền vào ô nào thì thẻ Kết quả lọc hiện số đó. **Số nhập tay luôn ưu tiên hơn dữ liệu tự động**, ô để trống thì dùng dữ liệu tự động, và workflow không bao giờ ghi đè file này.

- Cột: `Mã, Tên công ty, Vốn hóa TT, P/B, ROE`.
- Vốn hóa TT: đơn vị **tỷ đồng** (ví dụ `150000`). P/B: số lần (ví dụ `1.45`). ROE: phần trăm (ví dụ `14.2`, gõ `14.2%` cũng được).
- Số thập phân dùng dấu chấm; không dùng dấu phân cách hàng nghìn.
- Có thể thêm dòng cho mã mới. Lưu file ở dạng CSV UTF-8 để không lỗi tiếng Việt.
- Sửa ngay trên GitHub: mở file → bút chì → sửa → Commit changes.

## Đa khung Ngày · Tuần · Tháng (mới)

- **Trong thẻ Kết quả lọc**: mỗi thẻ có thêm khối "Phân tích đa khung (D - W - M)" và hộp chiến lược của chính mã đó; tắt/bật bằng công tắc phía trên danh sách thẻ. Muốn thẻ rộng hơn, đổi `per_row = 3` trong `page_filter` thành 2 hoặc 1.
- **Tab riêng**: Cổ phiếu → Đa khung D-W-M (thẻ lớn cho từng khung và chiến lược).
- Logic nằm trong `mtf_levels.py` (hàm `analyze_dwm_timeframe(df_d, df_w, df_m)`): xu hướng theo mây Ichimoku 9-17-26 (Tăng / Tích lũy / Giảm), hỗ trợ, kháng cự và một câu nhận xét cho mỗi khung. Hàm `analyze_multi_timeframe` (1h - D - W) vẫn còn trong file nhưng giao diện không dùng vì app không có nến giờ.
- Hỗ trợ luôn nằm **dưới** giá và kháng cự luôn nằm **trên** giá. Khi giá nằm trên mây, hỗ trợ hiện dạng khoảng "đáy mây – đỉnh mây" (cả dải mây là vùng đỡ); vùng gom của chiến lược lấy từ đáy mây. Hỗ trợ = đáy mây; nếu giá đã xuống dưới mây thì dùng đáy 20 hoặc 60 nến gần nhất. Kháng cự = đỉnh 20 nến; nếu giá đang ở đỉnh thì dùng đỉnh 60 nến, không còn mức nào thì ghi "—".
- Chiến lược theo khung Ngày: vùng gom = hỗ trợ → hỗ trợ +2%; cắt lỗ = hỗ trợ −4%; chốt lời = kháng cự; R:R tính từ giữa vùng gom, ≥ 1.8 là "Khả thi". Có cảnh báo khi khung Ngày, Tuần hoặc Tháng đang giảm.
- Mỗi khung cần ≥ 52 nến (mây Ichimoku cần đủ lịch sử). Khung Tháng cần khoảng 4,5 năm dữ liệu ngày; thiếu thì hiện "Không đủ dữ liệu" thay vì báo lỗi.

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
- `update_fundamentals.py`: tên công ty, P/B, ROE (ghi `data/fundamentals.csv`).
- `eod_fetch.py`: lấy dữ liệu cuối phiên mỗi ngày (chạy bởi `.github/workflows/eod.yml`), ghi `data/eod_prices.csv`.
- `realtime_data.py`: adapter dữ liệu Vnstock, chuẩn hóa OHLCV và bảng giá (tự chờ và thử lại khi nguồn báo giới hạn tần suất).
- `watchlist.py`: VN30 và các nhóm ngành.
- `wyckoff.py`: nhận diện vùng, sự kiện và pha Wyckoff.
- `requirements.txt`: các thư viện cần cài.

## Deploy

Có thể deploy Streamlit Community Cloud nếu môi trường deploy cho phép truy cập nguồn dữ liệu. Lưu ý máy chủ cloud cũng phải tuân thủ giới hạn truy cập và giấy phép dữ liệu. Với nhu cầu polling liên tục trong phiên, nên chạy trên máy/VPS ổn định và giám sát lỗi nguồn.


## Bộ lọc nâng cao, Score, RS và popup chi tiết (v5)
- **Trang Bộ lọc** có thêm: Cảnh báo (MUA/BÁN/Crossover/Đáy KT), Score 0-10, RS vs VNI, Vol/Avg10, MA Alignment, cấu trúc MA ngắn/trung/dài, đỉnh/đáy 52 tuần, trên MA200, dòng tiền sớm (Vol tăng 3 phiên, gom ngầm, cạn cung, NR4/NR7), cùng bộ lọc Nhóm ngành và Wyckoff (Tích lũy, Phân phối, Pha C/D/E) có sẵn.
- **Bảng** có thêm cột Score, RS vs VNI, MACD và Fisher (Ngày/Tuần), MA align, Nhận xét.
- **Popup chi tiết**: chọn một dòng rồi bấm "Chi tiết": cảnh báo sớm kèm lời khuyên có số, MACD/Fisher đa khung, trạng thái nhóm ngành, dòng tiền nội tại.
- **Trang "Chờ mua"** (thay cho "Khung cấu trúc MA", menu Bộ lọc & Backtest): nhận diện 9 trạng thái chờ mua chia 3 nhóm (Điểm mua đã xác nhận / Sắp có điểm mua / Theo dõi thêm) bằng EMA10, EMA20, MA50 ngày + MA10, MA20 tuần, Vol so với MA20 Vol, biên độ nền và hỗ trợ/kháng cự. Mỗi mã chỉ vào đúng một trạng thái, kèm lý do, vùng mua, cắt lỗ, mục tiêu, R:R. Logic nằm ở `waiting_buy.py`, ngưỡng chỉnh trong `CFG`.
- **Trang "Danh sách cảnh báo"**: 3 danh sách nằm ngoài tab chờ mua: Đang phục hồi, Tăng quá đà (không mua đuổi), Hạ tỷ trọng / suy yếu (rủi ro / bán). Nhóm "Không có điểm mua" bị loại khỏi mọi danh sách.
- **RS vs VNI**: nếu dữ liệu có mã `VNINDEX` thì dùng nó; nếu không (mặc định với rổ cổ phiếu) thì dùng trung bình cộng các mã trong dữ liệu làm "thị trường". Dòng chú thích đầu trang ghi rõ đang dùng loại nào.
- Phần tính toán mới nằm trong `engine.py` (`build_screener`, các cột MACD/Fisher/WaveTrend/MFI trong `add_indicators`).

## Giao diện thẻ Bộ lọc (bản tùy chỉnh)
Trang **Bộ lọc** hiển thị từng mã dạng thẻ: mã chứng khoán, giá mới nhất và % thay đổi, nhóm/ngành, vốn hóa thị trường (nếu có metadata), nhãn dự báo và 8 trạng thái kỹ thuật có màu xanh/đỏ/xám. Nút **Xem biểu đồ** mở trang biểu đồ và tự chọn đúng mã.

**Lưu ý vốn hóa:** nguồn OHLCV hiện tại không bảo đảm trả về vốn hóa thị trường cho mọi mã. Để hiển thị con số vốn hóa, điền `data/stock_metadata.csv` theo mẫu gồm hai cột `Mã,Vốn hóa TT`; đơn vị của `Vốn hóa TT` là tỷ đồng. Nếu chưa có dữ liệu, giao diện ghi rõ “Chưa có dữ liệu” thay vì tự ước lượng.

Nhãn dự báo được suy ra từ số lượng trạng thái kỹ thuật tích cực/tiêu cực trên thẻ, là bộ lọc định hướng tham khảo chứ không phải xác suất đã hiệu chuẩn. Trạng thái sóng ngắn/trung/trục chính dựa trên cấu trúc MA; Ichimoku/MACD/Volume/RSI dựa trên dữ liệu nến hiện có. Tín hiệu có thể thay đổi khi nến mới cập nhật.


## Dòng tiền khối ngoại (mới)

Tab **Thị trường → Dòng tiền khối ngoại** đã có dashboard để đọc dữ liệu mua/bán ròng theo mã: tổng quan phiên, Top mua/bán ròng, lịch sử lũy kế 5/20 phiên, phân tích theo nhóm ngành, bảng chi tiết và xuất CSV.

**Nạp dữ liệu:** mở tab này, tải `foreign_flow_template.csv`, điền dữ liệu từ nguồn dữ liệu chứng khoán phù hợp rồi tải CSV lên. Các cột bắt buộc: `Ngày`, `Mã`, `Giá trị mua`, `Giá trị bán`. Các cột bổ sung được hỗ trợ: `Sàn`, `Khối lượng mua`, `Khối lượng bán`, `Giá đóng cửa`, `Tổng GTGD`, `Nhóm ngành`. Giá trị mua/bán và tổng GTGD phải cùng đơn vị (khuyến nghị tỷ đồng).

File sau khi nạp được lưu tại `data/foreign_flow.csv`. Để dữ liệu tồn tại sau các lần deploy và được chia sẻ với người dùng app, cần commit file này lên repo; không nên dùng upload trong app làm phương thức nhập dữ liệu sản xuất lâu dài. Tự động cập nhật qua API chưa được bật vì cần chọn nhà cung cấp có dữ liệu khối ngoại, xác thực API và điều kiện cấp phép. App không suy ra giao dịch khối ngoại từ dữ liệu OHLCV.


## Chặn số giả và backtest thực tế (mới)
- `fund_guard.py`: P/B, P/E, ROE chỉ hiển thị khi là số thật. Cột có từ 80% ô cùng một giá trị (ví dụ cả rổ P/B 3.0, ROE 17) bị ẩn kèm cảnh báo ở trang Bộ lọc; giá trị ngoài miền hợp lý bị bỏ. Chạy `python fund_guard.py` để kiểm tra, thêm `--fix` để làm sạch `data/fundamentals.csv`. `update_fundamentals.py` cũng dùng bộ chặn này khi ghi file.
- `engine.run_backtest` mặc định mô phỏng giao dịch thực: vào ở giá mở cửa phiên kế tiếp, phí môi giới 0,15%/chiều, thuế bán 0,1%, trượt giá 0,1%/chiều, bước giá HOSE, T+2 (khung Ngày), gap qua cắt lỗ, phiên khóa trần (không mua được) và khóa sàn (không bán được). Chỉnh ở `BT_COST` đầu mục BACKTEST trong `engine.py`. `realistic=False` giữ mô hình lý tưởng cũ để so sánh; thẻ Backtest hiển thị cả hai.


## Cổ phiếu của tôi (mới)
Menu **Bộ lọc & Backtest → Cổ phiếu của tôi** (code ở `my_portfolio.py`) theo dõi danh mục đang NẮM GIỮ, khác Watchlist chỉ để theo dõi.
- Mỗi dòng dữ liệu là một lô mua (Mã, Số lượng, Giá vốn, Ngày mua, Cắt lỗ, Mục tiêu, Ghi chú), một mã có thể có nhiều lô. Lưu ở `data/co_phieu_cua_toi.csv`; tiền mặt và các ngưỡng cảnh báo lưu ở `data/danh_muc_cai_dat.json`.
- Hiển thị: giá trị cổ phiếu, NAV (cổ phiếu + tiền mặt), lãi/lỗ ròng (đã trừ phí, thuế bán), rủi ro nếu mọi lô chạm cắt lỗ (% NAV), số lượng đã bán được theo T+2, tỷ trọng theo mã và theo ngành, tín hiệu hệ thống cho từng vị thế và gợi ý theo kế hoạch của bạn.
- Cảnh báo: chạm hoặc gần cắt lỗ, hệ thống báo bán / chốt lời, đạt mục tiêu, mã hoặc ngành vượt ngưỡng tỷ trọng, tổng rủi ro vượt ngưỡng, lô chưa đặt cắt lỗ.
- Máy tính khối lượng: số cổ phiếu (lô 100) để nếu chạm cắt lỗ chỉ mất đúng % NAV bạn chấp nhận, có tính phí, thuế, tỷ trọng tối đa và tiền mặt.
- Đây là dữ liệu tài chính cá nhân: để repo private hoặc không đẩy hai file dữ liệu trên lên GitHub. Trên Streamlit Cloud file ghi lúc chạy mất khi app khởi động lại nên hãy bấm Sao lưu thường xuyên. App chưa lưu lịch sử lệnh đã bán.


## Dual Ichimoku trên biểu đồ (mới)
Lớp **Dual Ichimoku** (bật mặc định trong "Lớp hiển thị", code ở `ichimoku_dual.py`, tham số ở `CFG`) vẽ hai bộ Ichimoku cùng lúc, theo bản Pine "Min Invest - Dual Ichimoku Setup":
- **Bộ 1 (9-17-26, dịch 26):** chỉ vẽ mây Kumo gồm Lead 1 (Senkou Span A), Leading Span B và nền mây (xanh khi Span A trên Span B, đỏ khi ngược lại). Mây vẽ lệch 25 nến về tương lai như Pine (offset = displacement - 1). Không vẽ Tenkan, Kijun, Chikou.
- **Bộ 2 (65-129, Span B 52):** chỉ vẽ Tenkan-sen 65 (xanh dương) và Kijun-sen 129 (cam), không mây, không Chikou, không dịch.
- Lớp **Ichimoku** cũ trên biểu đồ đã bị xóa, chỉ còn Dual Ichimoku (phần chấm điểm trong `engine.py` vẫn tính Ichimoku 9-26-52 ở nền, không vẽ). Khung Tháng thường chưa đủ 129 nến nên Kijun 129 không hiện.
