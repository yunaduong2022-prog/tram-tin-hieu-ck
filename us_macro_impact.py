"""Rules-based, cautious Vietnam equity sector context for the nine macro tiles.

No prediction engine, securities recommendation, live sector prices, or LLM calls.
Uses ONLY verified quotes passed by us_overnight_macro.py; no fabricated values.
"""
from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo
from html import escape
from math import isfinite

# Values are potential channels, not direction guarantees or individual stock calls.
# source = international price only, no correlation or causality asserted.
RULES = {
    '^DJI': {
        'threshold': 0.4,
        'up': (
            'Cổ phiếu công nghiệp Mỹ tăng có thể hỗ trợ tâm lý chấp nhận rủi ro toàn cầu, nhưng không quyết định xu hướng VN-Index.',
            'Chứng khoán, ngân hàng, công nghiệp và bán lẻ nếu dòng tiền trong nước đồng thuận.',
            'Chưa có nhóm chịu bất lợi trực tiếp; nhóm phòng thủ có thể kém nổi bật tương đối.',
            'Xác nhận bằng độ rộng VN-Index, thanh khoản và giao dịch khối ngoại.'),
        'down': (
            'Nhịp giảm của Dow Jones gợi ý tâm lý thận trọng với chu kỳ kinh tế; tác động sang Việt Nam chủ yếu qua khẩu vị rủi ro.',
            'Điện, nước và hàng tiêu dùng thiết yếu có thể chống chịu tương đối.',
            'Chứng khoán, bất động sản, bán lẻ và cổ phiếu chu kỳ nhạy tâm lý.',
            'Theo dõi VIX và dòng vốn ngoại; không suy ra VN-Index nhất định giảm.'),
    },
    '^GSPC': {
        'threshold': 0.4,
        'up': (
            'S&P 500 tăng phản ánh phiên tích cực ở thị trường Mỹ; có thể hỗ trợ tâm lý tài sản rủi ro tại Việt Nam.',
            'Chứng khoán, ngân hàng, bất động sản và bán lẻ nếu thanh khoản VN cải thiện.',
            'Không có nhóm bất lợi trực tiếp chỉ từ S&P 500 tăng.',
            'Đối chiếu thêm DXY, lợi suất Mỹ, VIX và độ rộng thị trường Việt Nam.'),
        'down': (
            'S&P 500 giảm có thể khiến dòng tiền thận trọng hơn tại các thị trường mới nổi.',
            'Điện, nước, tiêu dùng thiết yếu có thể giữ nhịp tương đối.',
            'Chứng khoán, bất động sản, bán lẻ và nhóm định giá cao.',
            'Nếu DXY và VIX cùng tăng, áp lực tâm lý có thể rõ hơn.'),
    },
    '^IXIC': {
        'threshold': 0.5,
        'up': (
            'Nasdaq tăng phản ánh khẩu vị đối với cổ phiếu tăng trưởng/công nghệ tại Mỹ; tín hiệu lan tỏa chỉ mang tính tâm lý.',
            'Công nghệ thông tin, viễn thông; chứng khoán nếu dòng tiền tăng trưởng lan rộng.',
            'Không có nhóm ngành Việt Nam chịu bất lợi trực tiếp.',
            'Không đồng nhất Nasdaq với kết quả kinh doanh của doanh nghiệp công nghệ Việt Nam.'),
        'down': (
            'Nasdaq giảm có thể làm tâm lý với nhóm tăng trưởng/định giá cao thận trọng hơn.',
            'Hàng tiêu dùng thiết yếu, điện nước có thể mang tính phòng thủ tương đối.',
            'Công nghệ, chứng khoán và nhóm tăng trưởng định giá cao.',
            'Kiểm tra lợi suất Mỹ và mức giảm S&P 500 trước khi kết luận.'),
    },
    'DX-Y.NYB': {
        'threshold': 0.15,
        'up': (
            'USD mạnh lên có thể gây sức ép lên VND và dòng vốn nước ngoài; DXY không đồng nghĩa tỷ giá USD/VND.',
            'Dệt may, thủy sản, gỗ có thu USD có thể hưởng lợi tỷ giá nếu chi phí USD thấp.',
            'Hàng không, doanh nghiệp nhập khẩu nhiều, doanh nghiệp vay USD.',
            'Đối chiếu USD/VND, cơ cấu doanh thu/chi phí ngoại tệ và mua bán ròng khối ngoại.'),
        'down': (
            'USD suy yếu có thể giảm áp lực tỷ giá và hỗ trợ dòng vốn vào tài sản mới nổi.',
            'Hàng không, doanh nghiệp nhập khẩu, bất động sản và chứng khoán nếu lãi suất/tỷ giá thuận lợi.',
            'Doanh nghiệp xuất khẩu thu USD với chi phí VND có thể giảm lợi thế quy đổi.',
            'Kiểm tra tỷ giá USD/VND và khả năng phòng hộ của từng doanh nghiệp.'),
    },
    '^TNX': {
        'threshold_bp': 2.0,
        'up': (
            'Lợi suất trái phiếu Mỹ 10 năm tăng có thể làm chi phí vốn toàn cầu cao hơn và gây áp lực lên tài sản rủi ro.',
            'Chưa có nhóm hưởng lợi trực tiếp, nhất quán tại Việt Nam.',
            'Bất động sản, chứng khoán và doanh nghiệp sử dụng nhiều vốn vay.',
            'Quan sát DXY, dòng vốn ngoại và lãi suất trong nước; không suy ra ngay Fed tăng lãi suất.'),
        'down': (
            'Lợi suất Mỹ giảm có thể giảm áp lực chiết khấu và hỗ trợ kỳ vọng dòng vốn vào tài sản rủi ro.',
            'Bất động sản, chứng khoán và nhóm nhạy lãi suất nếu điều kiện trong nước đồng thuận.',
            'Không có nhóm chịu bất lợi trực tiếp, rõ ràng chỉ từ lợi suất giảm.',
            'Xác định lợi suất giảm do lạm phát hạ nhiệt hay do lo ngại suy thoái.'),
    },
    '^VIX': {
        'threshold': 3.0,
        'up': (
            'VIX tăng nghĩa là biến động kỳ vọng 30 ngày của S&P 500 tăng, không tự động đồng nghĩa giá chứng khoán sẽ giảm.',
            'Điện, nước, hàng tiêu dùng thiết yếu có thể phòng thủ tương đối.',
            'Chứng khoán, bất động sản và cổ phiếu đầu cơ có thể nhạy với tâm lý rủi ro.',
            'Theo dõi mức VIX, S&P 500 và thanh khoản VN; tránh biến VIX thành lệnh bán máy móc.'),
        'down': (
            'VIX giảm thể hiện kỳ vọng biến động thấp hơn, có thể cải thiện khẩu vị rủi ro.',
            'Chứng khoán, ngân hàng và nhóm chu kỳ khi dòng tiền thị trường xác nhận.',
            'Không có nhóm chịu áp lực trực tiếp; nhóm phòng thủ có thể kém nổi bật tương đối.',
            'VIX giảm không đủ để xác nhận VN-Index bước vào xu hướng tăng.'),
    },
    'BZ=F': {
        'threshold': 0.6,
        'up': (
            'Dầu Brent tăng có thể nâng triển vọng hoạt động thượng nguồn nhưng tăng chi phí nhiên liệu cho nhiều doanh nghiệp.',
            'Thăm dò, khoan và dịch vụ dầu khí có thể được hỗ trợ nếu giá dầu cao duy trì.',
            'Hàng không, vận tải đường bộ, nhựa và ngành tiêu thụ nhiều năng lượng.',
            'Lọc dầu phụ thuộc biên lọc dầu; phân biệt giá dầu tăng do cầu mạnh hay gián đoạn nguồn cung.'),
        'down': (
            'Brent giảm có thể hạ chi phí nhiên liệu, nhưng nếu giảm vì cầu toàn cầu yếu thì lợi ích sẽ không đồng đều.',
            'Hàng không, vận tải đường bộ, nhựa và ngành dùng nhiều nhiên liệu.',
            'Thăm dò, khoan và dịch vụ dầu khí nếu dầu thấp kéo dài.',
            'Theo dõi biên lọc dầu, giá xăng trong nước và nguyên nhân dầu giảm.'),
    },
    'CL=F': {
        'threshold': 0.6,
        'up': (
            'WTI tăng củng cố tín hiệu giá dầu; ảnh hưởng ngành ở Việt Nam phụ thuộc giá thành nhiên liệu thực tế.',
            'Nhóm khai thác và dịch vụ dầu khí khi xu hướng giá đủ bền.',
            'Hàng không, vận tải, hóa chất/nhựa sử dụng đầu vào dầu.',
            'Kiểm tra Brent cùng chiều và biên lợi nhuận từng doanh nghiệp.'),
        'down': (
            'WTI giảm có thể giảm áp lực giá nhiên liệu, nhưng không đảm bảo giá bán trong nước giảm ngay.',
            'Hàng không, vận tải và doanh nghiệp tiêu thụ nhiều nhiên liệu.',
            'Dịch vụ khoan/khai thác dầu khí khi đà giảm kéo dài.',
            'Đối chiếu Brent, thuế/phí và chu kỳ điều hành giá nhiên liệu.'),
    },
    'GC=F': {
        'threshold': 0.5,
        'up': (
            'Giá vàng tương lai tăng có thể phản ánh phòng thủ, kỳ vọng lạm phát hoặc biến động USD; không có quan hệ cố định với VN-Index.',
            'Kinh doanh vàng/trang sức chỉ có thể hưởng lợi nếu biên giá, tồn kho và sức mua thuận lợi.',
            'Cổ phiếu chu kỳ và chứng khoán có thể chịu tâm lý phòng thủ nếu VIX cũng tăng.',
            'Không mặc định cổ phiếu bán lẻ trang sức hưởng lợi; kiểm tra DXY, VIX và giá vàng trong nước.'),
        'down': (
            'Vàng giảm không đồng nghĩa chứng khoán sẽ tăng; có thể do USD mạnh, lợi suất lên hoặc nhu cầu phòng thủ yếu đi.',
            'Trang sức có thể hưởng lợi chi phí đầu vào nếu sức mua và chính sách tồn kho phù hợp.',
            'Đơn vị nắm tồn kho vàng lớn có thể chịu rủi ro biến động giá.',
            'Đối chiếu DXY, lợi suất Mỹ và chênh lệch giá vàng trong nước.'),
    },
}


def interpret(item: dict, today: date | None = None) -> dict:
    """Return deterministic commentary, without interpreting missing or stale quotes."""
    symbol = str(item.get('symbol', ''))
    rule = RULES.get(symbol)
    if not rule or not item.get('ok'):
        return {'status': 'missing', 'note': 'Chưa đủ dữ liệu để đánh giá tác động.'}
    try:
        session = date.fromisoformat(item['session_date'])
        days_old = ((today or datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).date()) - session).days
        change = float(item['change_pct'])
        price = float(item['price'])
        previous = float(item['previous'])
        if not all(map(isfinite, (change, price, previous))) or previous <= 0 or price <= 0:
            raise ValueError('nonfinite')
        if days_old > 5:
            return {'status': 'stale', 'note': f'Dữ liệu phiên {session:%d/%m/%Y} đã cũ; không đánh giá tác động mới.'}
        if symbol == '^TNX':
            bp = (price - previous) * 100.0
            threshold = rule['threshold_bp']
            move = abs(bp)
            move_text = f'{"tăng" if bp > 0 else "giảm"} {abs(bp):.1f} điểm cơ bản'
            rising = bp > 0
        else:
            threshold = rule['threshold']
            move = abs(change)
            move_text = f'{"tăng" if change > 0 else "giảm"} {abs(change):.2f}%'
            rising = change > 0
        if move < threshold:
            return {'status': 'neutral', 'note': f'Biến động {move_text}, chưa đủ lớn theo ngưỡng tham khảo để suy luận thay đổi tác động theo ngày. Theo dõi diễn biến nhiều phiên và dữ liệu trong nước.'}
        note, benefits, pressures, check = rule['up' if rising else 'down']
        return {
            'status': 'up' if rising else 'down',
            'move': move_text,
            'note': note,
            'benefits': benefits,
            'pressures': pressures,
            'check': check,
        }
    except (KeyError, ValueError, TypeError, OverflowError):
        return {'status': 'missing', 'note': 'Không thể xác minh đủ giá hoặc ngày dữ liệu.'}


def render_html(item: dict) -> str:
    result = interpret(item)
    status = result['status']
    label = 'NHẬN ĐỊNH TỰ ĐỘNG · THAM KHẢO'
    note = escape(result['note'])
    if status in ('missing', 'stale', 'neutral'):
        return (f'<div class="usn-impact usn-impact-{status}">'
                f'<div class="usn-impact-title">{label}</div>'
                f'<div class="usn-impact-note">{note}</div></div>')
    return (
        f'<div class="usn-impact usn-impact-{status}">'
        f'<div class="usn-impact-title">{label}</div>'
        f'<div class="usn-impact-move">{escape(result["move"])}</div>'
        f'<div class="usn-impact-note">{note}</div>'
        f'<div class="usn-impact-line"><b>Có thể hưởng lợi:</b> {escape(result["benefits"])}</div>'
        f'<div class="usn-impact-line"><b>Có thể chịu áp lực:</b> {escape(result["pressures"])}</div>'
        f'<div class="usn-impact-check"><b>Cần xác nhận:</b> {escape(result["check"])}</div>'
        '</div>'
    )
