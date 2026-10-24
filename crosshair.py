"""Đường gióng kiểu TradingView cho biểu đồ nến Plotly trong Streamlit (dùng chung cho biểu đồ cổ phiếu và VN-Index).

Chạy ở trình duyệt: khi rê chuột hiện đường dọc (bám vào nến gần nhất) + đường ngang theo chuột, nhãn ngày
("Thứ 4 16 Tháng 9 '26") ở dải ngày ngay dưới biểu đồ nến và nhãn giá / giá trị của khung đang trỏ ở cột bên phải.
Tự gắn vào mọi biểu đồ Plotly có trace 'candlestick' trong trang. Trục thời gian (date) lấy ngày từ chính trục;
trục nhóm (category) lấy chữ nhãn từ trace.meta (danh sách chữ, mỗi nến một mục), không có thì dùng nhãn trục.
"""
import inspect

import streamlit as st

CROSSHAIR_JS = r"""
(function () {
  var P = window;
  try { if (window.frameElement) P = window.parent; } catch (e) {}
  var D = P.document;
  try { if (P.__vnCross) P.__vnCross(); } catch (e) {}          // gỡ bản cũ (khi Streamlit chạy lại script)
  if (!P.matchMedia || !P.matchMedia('(hover: hover) and (pointer: fine)').matches) return;   // cảm ứng: không có con trỏ để gióng

  var LINE = 'rgba(230,239,233,.6)', BOX_BG = '#E6EFE9', BOX_FG = '#0E1C18';
  var DAY = 86400000, cleanups = [];

  function axName(id, letter) { id = id || letter; return letter + 'axis' + (id.length > 1 ? id.slice(1) : ''); }
  function candleOf(gd) {
    var d = gd.data || [];
    for (var i = 0; i < d.length; i++) if (d[i] && d[i].type === 'candlestick') return d[i];
    return null;
  }
  function mk(css) {
    var e = D.createElement('div');
    e.style.cssText = 'position:absolute;pointer-events:none;display:none;box-sizing:border-box;' + css;
    return e;
  }
  function put(el, css) { for (var k in css) el.style[k] = css[k]; }
  function boxCss() {
    return 'background:' + BOX_BG + ';color:' + BOX_FG + ';font:600 11px/16px "Source Sans Pro","Open Sans",Arial,sans-serif;' +
           'padding:1px 6px;border-radius:3px;white-space:nowrap;z-index:1002;';
  }
  function fmtDate(ms) {
    var d = new Date(ms), w = d.getUTCDay();
    return (w === 0 ? 'Chủ nhật' : 'Thứ ' + (w + 1)) + ' ' + d.getUTCDate() + ' Tháng ' + (d.getUTCMonth() + 1) + " '" + String(d.getUTCFullYear()).slice(-2);
  }
  function fmtVal(v, ya, isPrice) {
    if (!isFinite(v)) return '';
    var r = ya.range || [0, 1], big = Math.max(Math.abs(r[0]), Math.abs(r[1]));
    if (!isPrice && big >= 1e4) {
      var a = Math.abs(v);
      return a >= 1e6 ? (v / 1e6).toFixed(2) + 'M' : a >= 1e3 ? (v / 1e3).toFixed(1) + 'K' : v.toFixed(0);
    }
    return v.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  function attach(gd) {
    var st = { xs: null, key: null };
    var ov = mk('left:0;top:0;width:0;height:0;z-index:1001;');
    ov.style.display = 'block';
    var vl = mk('width:0;border-left:1px dashed ' + LINE + ';z-index:1001;');
    var hl = mk('height:0;border-top:1px dashed ' + LINE + ';z-index:1001;');
    var dl = mk(boxCss()), pl = mk(boxCss());
    [vl, hl, dl, pl].forEach(function (e) { ov.appendChild(e); });

    function host() { return gd.querySelector('.plot-container') || gd; }
    function hideAll() { [vl, hl, dl, pl].forEach(function (e) { e.style.display = 'none'; }); }

    function times(tr, xa) {                                       // mốc thời gian (ms) của các nến, lưu tạm theo mảng x
      var key = tr.x;
      if (st.key !== key || !st.xs || st.xs.length !== tr.x.length) {
        var out = [];
        for (var i = 0; i < tr.x.length; i++) { var m = xa.d2l(tr.x[i]); if (isFinite(m)) out.push(m); }
        out.sort(function (p, q) { return p - q; });
        st.xs = out; st.key = key;
      }
      return st.xs;
    }
    function snap(xs, ms) {                                        // mốc nến gần nhất; vượt nến cuối (vùng dự báo) thì chia theo bước phiên
      var n = xs.length;
      if (!n) return ms;
      var lo = 0, hi = n - 1;
      while (lo < hi) { var mid = (lo + hi) >> 1; if (xs[mid] < ms) lo = mid + 1; else hi = mid; }
      var best = lo;
      if (lo > 0 && Math.abs(xs[lo - 1] - ms) <= Math.abs(xs[lo] - ms)) best = lo - 1;
      var last = xs[n - 1];
      if (ms <= last || n < 2) return xs[best];
      var step = Math.round((last - xs[Math.max(0, n - 6)]) / Math.min(5, n - 1) / DAY);     // ~1 ngày / 7 ngày / ~30 ngày
      var k = Math.max(1, Math.round((ms - last) / (Math.max(1, step) * DAY)));
      if (step >= 25) { var d = new Date(last); d.setUTCMonth(d.getUTCMonth() + k); return d.getTime(); }
      var t = last + k * Math.max(1, step) * DAY;
      var wd = new Date(t).getUTCDay();
      if (step < 5) { if (wd === 6) t += 2 * DAY; else if (wd === 0) t += DAY; }              // khung ngày: bỏ qua thứ 7, chủ nhật
      return t;
    }

    function onMove(e) {
      try {
        var fl = gd._fullLayout, tr = candleOf(gd), pc = host();
        if (!fl || !tr || !fl._plots || !tr.x || !tr.x.length) return hideAll();
        if (ov.parentNode !== pc) pc.appendChild(ov);
        var ref = gd.querySelector('.svg-container') || gd.querySelector('.main-svg') || pc;
        var rr = ref.getBoundingClientRect(), pr = pc.getBoundingClientRect();
        var ox = rr.left - pr.left, oy = rr.top - pr.top;
        var mx = e.clientX - rr.left, my = e.clientY - rr.top;

        var cx = fl[axName(tr.xaxis, 'x')], cy = fl[axName(tr.yaxis, 'y')];
        if (!cx || !cy || typeof cx.p2l !== 'function') return hideAll();
        var left = cx._offset, right = cx._offset + cx._length, top = 1e9, bot = -1e9, hov = null;
        Object.keys(fl._plots).forEach(function (k) {
          var p = fl._plots[k], ya = p.yaxis;
          if (!ya) return;
          top = Math.min(top, ya._offset); bot = Math.max(bot, ya._offset + ya._length);
          if (my >= ya._offset && my <= ya._offset + ya._length) hov = ya;
        });
        if (mx < left || mx > right || my < top || my > bot) return hideAll();

        var px, text, ms = null;
        if (cx.type === 'category') {                                 // trục nhóm (biểu đồ VN-Index): mỗi nến là một mốc; chữ nhãn lấy từ trace.meta
          var n = tr.x.length, idx = Math.max(0, Math.min(n - 1, Math.round(cx.p2l(mx - left))));
          px = left + cx.l2p(idx);
          text = (Array.isArray(tr.meta) && tr.meta[idx]) ? String(tr.meta[idx]) : String(tr.x[idx]);
        } else {
          var xs = times(tr, cx);
          ms = snap(xs, cx.p2l(mx - left));
          px = left + cx.l2p(ms);
          text = fmtDate(ms);
        }
        if (!isFinite(px)) return hideAll();
        px = Math.max(left, Math.min(right, px));

        put(vl, { display: 'block', left: (ox + px) + 'px', top: (oy + top) + 'px', height: (bot - top) + 'px' });
        dl.textContent = text;
        put(dl, { display: 'block' });
        var dw = dl.offsetWidth, dx = Math.max(left, Math.min(right - dw, px - dw / 2));
        put(dl, { left: (ox + dx) + 'px', top: (oy + cy._offset + cy._length + 2) + 'px' });   // ngay trên dải ngày, dưới biểu đồ nến

        if (hov) {
          put(hl, { display: 'block', left: (ox + left) + 'px', top: (oy + my) + 'px', width: (right - left) + 'px' });
          pl.textContent = fmtVal(hov.p2l(my - hov._offset), hov, hov === cy);
          put(pl, { display: 'block', left: (ox + right + 3) + 'px', top: (oy + my - 9) + 'px' });
        } else { hl.style.display = 'none'; pl.style.display = 'none'; }
      } catch (err) { hideAll(); }
    }

    gd.addEventListener('mousemove', onMove);
    gd.addEventListener('mouseleave', hideAll);
    gd.__vnCrossOn = true;
    cleanups.push(function () {
      gd.removeEventListener('mousemove', onMove);
      gd.removeEventListener('mouseleave', hideAll);
      gd.__vnCrossOn = false;
      if (ov.parentNode) ov.parentNode.removeChild(ov);
    });
  }

  function scan() {
    var list = D.querySelectorAll('.js-plotly-plot');
    for (var i = 0; i < list.length; i++) {
      var gd = list[i];
      if (!gd.__vnCrossOn && gd._fullLayout && candleOf(gd)) attach(gd);
    }
  }
  scan();
  var timer = P.setInterval(scan, 1000);                          // biểu đồ vẽ sau / được vẽ lại khi đổi mã, khung thời gian
  var obs = null;
  try { obs = new P.MutationObserver(function () { scan(); }); obs.observe(D.body, { childList: true, subtree: true }); } catch (e) {}
  P.__vnCross = function () {
    P.clearInterval(timer);
    if (obs) obs.disconnect();
    cleanups.forEach(function (f) { try { f(); } catch (e) {} });
    P.__vnCross = null;
  };
})();
"""


def inject():
    """Streamlit mới: st.html chạy JS thẳng trong trang; bản cũ: qua iframe components (cùng nguồn nên chạm được trang cha)."""
    html = "<script>" + CROSSHAIR_JS + "</script>"
    try:
        if "unsafe_allow_javascript" in inspect.signature(st.html).parameters:
            st.html(html, unsafe_allow_javascript=True)
            return
    except Exception:  # noqa: BLE001
        pass
    try:
        import streamlit.components.v1 as components
        components.html(html, height=0)
    except Exception:  # noqa: BLE001
        pass
