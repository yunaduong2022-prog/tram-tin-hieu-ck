"""Thanh công cụ vẽ kiểu TradingView cho biểu đồ nến cổ phiếu (máy tính).

Chạy ở trình duyệt, cùng cách với crosshair.py: gắn một lớp SVG nằm trên khung nến chính của biểu đồ Plotly, nên không
đụng vào figure do Python dựng. Nét vẽ lưu theo toạ độ dữ liệu (ngày, giá) nên bám đúng nến khi kéo, zoom, đổi khung
thời gian hiển thị; và lưu trong localStorage của trình duyệt theo từng mã + khung D/W/M (chạy lại app vẫn còn).

Công cụ: đường xu hướng, mũi tên, đường song song (kênh giá, 3 điểm), hình chữ nhật, hình tròn, đường ngang, đường dọc, đo khoảng giá, đo khoảng ngày,
đo giá + ngày, chữ, ghi chú có mũi tên; nam châm hít vào Mở/Cao/Thấp/Đóng; chọn màu; hoàn tác; xoá nét đang chọn /
xoá tất cả; ẩn/hiện nét vẽ. Phím tắt: Esc huỷ, Delete xoá nét đang chọn, Ctrl+Z hoàn tác.
Lưu ý: nút chụp ảnh của Plotly chỉ chụp phần biểu đồ, không có nét vẽ (lớp vẽ nằm ngoài figure).
"""
import inspect
import json

import streamlit as st

DRAW_JS = r"""
(function () {
  var KEY = __KEY__, CODE = __CODE__, TF = __TF__;
  var P = window;
  try { if (window.frameElement) P = window.parent; } catch (e) {}
  var D = P.document;
  var SLOT = '__vnDraw_' + TF;
  try { if (P[SLOT]) P[SLOT](); } catch (e) {}                       // gỡ bản cũ của cùng khung (Streamlit chạy lại script / đổi mã)
  if (!P.matchMedia || !P.matchMedia('(hover: hover) and (pointer: fine)').matches) return;   // cảm ứng: không dùng

  var NS = 'http://www.w3.org/2000/svg', DAY = 86400000;
  var FONT = '"Source Sans Pro","Open Sans",Arial,sans-serif';
  var UPC = '#089981', DNC = '#F23645', INK = '#0E1C18';
  var LSK = 'vn_draw_v1:' + KEY, LSB = 'vn_draw_bar_v1', LSC = 'vn_draw_cfg_v1', LSO = 'vn_draw_open_v1';

  function lsGet(k) { try { return JSON.parse(P.localStorage.getItem(k)); } catch (e) { return null; } }
  function lsSet(k, v) { try { P.localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} }

  var cfg = lsGet(LSC) || {};
  var S = {
    shapes: lsGet(LSK) || [], tool: null, sel: null, draft: null, undo: [],
    color: cfg.color || '#F5C542', magnet: !!cfg.magnet, hidden: false, barPos: null, dockOpen: lsGet(LSO) !== false, rev: 0
  };
  if (!Array.isArray(S.shapes)) S.shapes = [];

  // ---------------------------------------------------------------- công cụ
  var ICON = function (inner) {
    return '<svg viewBox="0 0 20 20" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">' + inner + '</svg>';
  };
  var TOOLS = [
    { id: 'cursor',  tip: 'Con trỏ (thoát công cụ vẽ)', pts: 0, icon: ICON('<path d="M5 3l10 6.5-4.2 1.4L9.3 15z"/>') },
    { id: 'line',    tip: 'Đường xu hướng', pts: 2, icon: ICON('<path d="M4 16L16 4"/><circle cx="4" cy="16" r="1.8"/><circle cx="16" cy="4" r="1.8"/>') },
    { id: 'arrow',   tip: 'Mũi tên', pts: 2, icon: ICON('<path d="M4 16L16 4M16 4h-6M16 4v6"/>') },
    { id: 'rect',    tip: 'Hình chữ nhật', pts: 2, icon: ICON('<rect x="4" y="5" width="12" height="10" rx="1"/>') },
    { id: 'ellipse', tip: 'Hình tròn / elip', pts: 2, icon: ICON('<ellipse cx="10" cy="10" rx="7" ry="5.5"/>') },
    { id: 'hline',   tip: 'Đường ngang (mức giá)', pts: 1, icon: ICON('<path d="M2.5 10h15"/><circle cx="10" cy="10" r="1.8"/>') },
    { id: 'vline',   tip: 'Đường dọc (mốc ngày)', pts: 1, icon: ICON('<path d="M10 2.5v15"/><circle cx="10" cy="10" r="1.8"/>') },
    { id: 'channel', tip: 'Đường song song (kênh giá): bấm 2 điểm vẽ đường gốc, bấm điểm thứ 3 để đặt đường song song', pts: 3, icon: ICON('<path d="M3 11.5L12 4M8 16.5L17 9"/><circle cx="3" cy="11.5" r="1.4"/><circle cx="12" cy="4" r="1.4"/><circle cx="8" cy="16.5" r="1.4"/>') },
    { sep: true },
    { id: 'prange',  tip: 'Đo khoảng giá', pts: 2, icon: ICON('<path d="M10 3v14M7 6l3-3 3 3M7 14l3 3 3-3M5.5 3h9M5.5 17h9"/>') },
    { id: 'drange',  tip: 'Đo khoảng ngày', pts: 2, icon: ICON('<path d="M3 10h14M6 7l-3 3 3 3M14 7l3 3-3 3M3 5.5v9M17 5.5v9"/>') },
    { id: 'measure', tip: 'Đo giá + ngày', pts: 2, icon: ICON('<rect x="3.5" y="5" width="13" height="10" rx="1" stroke-dasharray="2 2"/><path d="M10 6.5v7M6.5 10h7"/>') },
    { sep: true },
    { id: 'text',    tip: 'Chữ ghi chú', pts: 1, icon: ICON('<path d="M5 5.5h10M10 5.5v10.5"/>') },
    { id: 'callout', tip: 'Ghi chú có mũi tên (kéo từ điểm cần chỉ ra chỗ đặt chữ)', pts: 2, icon: ICON('<path d="M4 4.5h12v8H9l-3.2 3v-3H4z"/>') },
    { sep: true },
    { id: 'magnet',  tip: 'Nam châm: hít vào Mở / Cao / Thấp / Đóng của nến', act: 'magnet', icon: ICON('<path d="M5.5 3.5v7a4.5 4.5 0 009 0v-7M5.5 6.5h3M11.5 6.5h3"/>') },
    { id: 'color',   tip: 'Màu nét vẽ', act: 'color' },
    { sep: true },
    { id: 'undo',    tip: 'Hoàn tác (Ctrl+Z)', act: 'undo', icon: ICON('<path d="M7 5.5L4 8.5l3 3M4 8.5h8a4 4 0 010 8H8"/>') },
    { id: 'del',     tip: 'Xoá nét đang chọn (Delete)', act: 'del', icon: ICON('<path d="M4.5 6h11M8 6V4h4v2M6 6l.8 10h6.4L14 6"/>') },
    { id: 'clear',   tip: 'Xoá tất cả nét vẽ của mã này', act: 'clear', icon: ICON('<path d="M4 4l12 12M16 4L4 16"/>') },
    { id: 'hide',    tip: 'Ẩn / hiện nét vẽ', act: 'hide', icon: ICON('<path d="M2 10s3-5.5 8-5.5S18 10 18 10s-3 5.5-8 5.5S2 10 2 10z"/><circle cx="10" cy="10" r="2.3"/>') }
  ];
  var DEF = {};
  TOOLS.forEach(function (t) { if (t.id) DEF[t.id] = t; });

  // ---------------------------------------------------------------- tiện ích
  function uid() { return 's' + Date.now().toString(36) + Math.random().toString(36).slice(2, 6); }
  function save() { lsSet(LSK, S.shapes); lsSet(LSC, { color: S.color, magnet: S.magnet }); }
  function pushUndo() { S.undo.push(JSON.stringify(S.shapes)); if (S.undo.length > 60) S.undo.shift(); }
  function byId(id) { for (var i = 0; i < S.shapes.length; i++) if (S.shapes[i].id === id) return S.shapes[i]; return null; }
  function axName(id, letter) { id = id || letter; return letter + 'axis' + (id.length > 1 ? id.slice(1) : ''); }
  function tfOk(gd) {                                               // biểu đồ do app.py gắn meta.vn_tf; không có meta thì coi là khớp
    var m = (gd.layout && gd.layout.meta) || (gd._fullLayout && gd._fullLayout.meta);
    return !m || !m.vn_tf || m.vn_tf === TF;
  }
  function candleOf(gd) {
    if (!tfOk(gd)) return null;
    var d = gd.data || [];
    for (var i = 0; i < d.length; i++) if (d[i] && d[i].type === 'candlestick' && d[i].name === CODE) return d[i];
    return null;
  }
  function fmtP(v) { return isFinite(v) ? v.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : ''; }
  function fmtDate(ms) {
    var d = new Date(ms), w = d.getUTCDay();
    function z(n) { return n < 10 ? '0' + n : '' + n; }
    return (w === 0 ? 'CN' : 'T' + (w + 1)) + ', ' + z(d.getUTCDate()) + '/' + z(d.getUTCMonth() + 1) + '/' + d.getUTCFullYear();
  }
  function mkEl(parent, name, attrs, text) {
    var e = D.createElementNS(NS, name);
    for (var k in attrs) if (attrs[k] != null) e.setAttribute(k, attrs[k]);
    if (text != null) e.textContent = text;
    if (parent) parent.appendChild(e);
    return e;
  }
  function html(tag, cls, css) {
    var e = D.createElement(tag);
    if (cls) e.className = cls;
    if (css) e.style.cssText = css;
    return e;
  }

  // ---------------------------------------------------------------- trạng thái từng biểu đồ
  var I = null;          // { gd, box, svg, cap, bar, hint, G, xs, xsKey, sig, timer, off }
  var G = null;          // hình học hiện tại của khung nến chính

  function geo(gd) {
    var fl = gd._fullLayout, tr = candleOf(gd);
    if (!fl || !tr) return null;
    var cx = fl[axName(tr.xaxis, 'x')], cy = fl[axName(tr.yaxis, 'y')];
    if (!cx || !cy || typeof cx.l2p !== 'function' || !(cx._length > 0) || !(cy._length > 0)) return null;
    var pc = gd.querySelector('.plot-container') || gd;
    var ref = gd.querySelector('.svg-container') || gd.querySelector('.main-svg') || pc;
    var rr = ref.getBoundingClientRect(), pr = pc.getBoundingClientRect();
    return { tr: tr, cx: cx, cy: cy, pc: pc, ox: rr.left - pr.left, oy: rr.top - pr.top,
             left: cx._offset, top: cy._offset, w: cx._length, h: cy._length };
  }
  function X(t) { return G.cx.l2p(t); }
  function Y(v) { return G.cy.l2p(v); }
  function times() {                                              // mốc thời gian (ms) của các nến
    var tr = G.tr;
    if (I.xsKey !== tr.x || !I.xs || I.xs.length !== tr.x.length) {
      var out = [];
      for (var i = 0; i < tr.x.length; i++) { var m = G.cx.d2l(tr.x[i]); out.push(isFinite(m) ? m : NaN); }
      I.xs = out; I.xsKey = tr.x;
    }
    return I.xs;
  }
  function nearestIdx(ms) {
    var xs = times(), best = -1, bd = Infinity;
    for (var i = 0; i < xs.length; i++) { var d = Math.abs(xs[i] - ms); if (d < bd) { bd = d; best = i; } }
    return best;
  }
  function fromPx(x, y, magnet) {                                  // toạ độ pixel trong khung nến -> {t, v}
    var t = G.cx.p2l(x), v = G.cy.p2l(y);
    if (magnet) {
      var i = nearestIdx(t);
      if (i >= 0 && Math.abs(X(times()[i]) - x) < 28) {
        t = times()[i];
        var tr = G.tr, c = [tr.open, tr.high, tr.low, tr.close], bd = 38, bv = null;
        for (var k = 0; k < 4; k++) {
          var pv = c[k] && +c[k][i];
          if (isFinite(pv)) { var d = Math.abs(Y(pv) - y); if (d < bd) { bd = d; bv = pv; } }
        }
        if (bv != null) v = bv;
      }
    }
    return { t: t, v: v };
  }
  function futureBars(a, b) {                                      // số nến "ảo" từ nến cuối a đến mốc b (vùng dự báo)
    var n = 0, d;
    if (TF === 'D') { for (d = a + DAY; d <= b + 1; d += DAY) { var w = new Date(d).getUTCDay(); if (w !== 0 && w !== 6) n++; } return n; }
    if (TF === 'W') return Math.max(0, Math.round((b - a) / (7 * DAY)));
    return Math.max(0, Math.round((b - a) / (30.44 * DAY)));
  }
  function barsBetween(ta, tb) {
    var lo = Math.min(ta, tb), hi = Math.max(ta, tb), xs = times(), n = 0, last = -Infinity;
    for (var i = 0; i < xs.length; i++) { if (xs[i] > last) last = xs[i]; if (xs[i] > lo && xs[i] <= hi) n++; }
    if (hi > last) n += futureBars(Math.max(lo, last), hi);
    return n;
  }

  // ---------------------------------------------------------------- vẽ
  function label(g, x, y, txt, bg, o) {
    o = o || {};
    var lg = mkEl(g, 'g', {});
    var t = mkEl(lg, 'text', { x: x, y: y, fill: o.fg || INK, 'font-size': o.size || 11, 'font-weight': 600,
      'font-family': FONT, 'text-anchor': o.anchor || 'middle', 'dominant-baseline': 'central' }, txt);
    var b = t.getBBox(), pad = 5;
    var r = mkEl(null, 'rect', { x: b.x - pad, y: b.y - 2, width: b.width + 2 * pad, height: b.height + 4, rx: 3,
      fill: bg, 'fill-opacity': o.bgo == null ? 1 : o.bgo, stroke: o.stroke || 'none' });
    lg.insertBefore(r, t);
    var dx = 0, dy = 0, x0 = b.x - pad, x1 = b.x + b.width + pad, y0 = b.y - 2, y1 = b.y + b.height + 2;
    if (x0 < 2) dx = 2 - x0; else if (x1 > G.w - 2) dx = G.w - 2 - x1;
    if (y0 < 2) dy = 2 - y0; else if (y1 > G.h - 2) dy = G.h - 2 - y1;
    if (dx || dy) lg.setAttribute('transform', 'translate(' + dx + ',' + dy + ')');
    if (o.sid) { [r, t].forEach(function (e) { e.setAttribute('data-sid', o.sid); e.style.pointerEvents = 'all'; e.style.cursor = 'move'; }); }
    return lg;
  }
  function head(g, a, b, col, w) {                                  // đầu mũi tên tại b
    var ang = Math.atan2(b.y - a.y, b.x - a.x), L = 11 + w, sp = 0.46;
    var p1 = [b.x - L * Math.cos(ang - sp), b.y - L * Math.sin(ang - sp)];
    var p2 = [b.x - L * Math.cos(ang + sp), b.y - L * Math.sin(ang + sp)];
    mkEl(g, 'polygon', { points: b.x + ',' + b.y + ' ' + p1.join(',') + ' ' + p2.join(','), fill: col });
  }
  function hitLine(g, x1, y1, x2, y2, sid) {
    mkEl(g, 'line', { x1: x1, y1: y1, x2: x2, y2: y2, stroke: '#fff', 'stroke-opacity': 0, 'stroke-width': 12,
      'data-sid': sid, style: 'pointer-events:stroke;cursor:move' });
  }
  function rangeText(s) {
    var a = s.p[0], b = s.p[1], dv = b.v - a.v, pct = a.v ? dv / a.v * 100 : 0;
    var bars = barsBetween(a.t, b.t), days = Math.round(Math.abs(b.t - a.t) / DAY);
    return { dv: dv, pct: pct, bars: bars, days: days,
      price: (dv >= 0 ? '+' : '') + fmtP(dv) + ' (' + (pct >= 0 ? '+' : '') + pct.toFixed(2) + '%)',
      time: bars + ' nến · ' + days + ' ngày' };
  }

  function drawShape(s, svg, isDraft) {
    var g = mkEl(svg, 'g', { 'data-g': s.id });
    var c = s.c || '#F5C542', w = s.w || 1.6, ty = s.type;
    var a = s.p[0] ? { x: X(s.p[0].t), y: Y(s.p[0].v) } : null;
    var b = s.p[1] ? { x: X(s.p[1].t), y: Y(s.p[1].v) } : null;
    var dash = isDraft ? '5 4' : null;
    function ln(x1, y1, x2, y2, col, ww, da) {
      var at = { x1: x1, y1: y1, x2: x2, y2: y2, stroke: col || c, 'stroke-width': ww || w, 'stroke-linecap': 'round', style: 'pointer-events:none' };
      if (da || dash) at['stroke-dasharray'] = da || dash;
      return mkEl(g, 'line', at);
    }
    var sid = isDraft ? null : s.id, chn = null;

    if (ty === 'line' || ty === 'arrow') {
      ln(a.x, a.y, b.x, b.y);
      if (ty === 'arrow') head(g, a, b, c, w);
      if (sid) hitLine(g, a.x, a.y, b.x, b.y, sid);
    } else if (ty === 'hline') {
      ln(0, a.y, G.w, a.y);
      label(g, G.w - 4, a.y, fmtP(s.p[0].v), c, { anchor: 'end', sid: sid });
      if (sid) hitLine(g, 0, a.y, G.w, a.y, sid);
    } else if (ty === 'vline') {
      ln(a.x, 0, a.x, G.h);
      label(g, a.x, G.h - 12, fmtDate(s.p[0].t), c, { anchor: 'middle', sid: sid });
      if (sid) hitLine(g, a.x, 0, a.x, G.h, sid);
    } else if (ty === 'rect' || ty === 'ellipse') {
      var x = Math.min(a.x, b.x), y = Math.min(a.y, b.y), rw = Math.abs(b.x - a.x), rh = Math.abs(b.y - a.y);
      var at = { fill: c, 'fill-opacity': 0.12, stroke: c, 'stroke-width': w, style: 'pointer-events:none' };
      if (dash) at['stroke-dasharray'] = dash;
      var hit = { fill: 'none', stroke: '#fff', 'stroke-opacity': 0, 'stroke-width': 12, 'data-sid': sid, style: 'pointer-events:stroke;cursor:move' };
      if (ty === 'rect') { at.x = x; at.y = y; at.width = rw; at.height = rh; mkEl(g, 'rect', at); hit.x = x; hit.y = y; hit.width = rw; hit.height = rh; if (sid) mkEl(g, 'rect', hit); }
      else { at.cx = x + rw / 2; at.cy = y + rh / 2; at.rx = rw / 2; at.ry = rh / 2; mkEl(g, 'ellipse', at);
             hit.cx = at.cx; hit.cy = at.cy; hit.rx = at.rx; hit.ry = at.ry; if (sid) mkEl(g, 'ellipse', hit); }
    } else if (ty === 'channel') {
      var a2 = null, b2 = null;
      if (s.p[2]) {                                               // đường song song: cùng độ dốc theo (ngày, giá), qua điểm thứ 3
        var t0 = s.p[0].t, t1 = s.p[1].t, v0 = s.p[0].v, v1 = s.p[1].v;
        var lv = t1 !== t0 ? v0 + (v1 - v0) * (s.p[2].t - t0) / (t1 - t0) : v0, dv = s.p[2].v - lv;
        a2 = { x: a.x, y: Y(v0 + dv) }; b2 = { x: b.x, y: Y(v1 + dv) };
        chn = { a2: a2, b2: b2 };
        mkEl(g, 'polygon', { points: [a.x + ',' + a.y, b.x + ',' + b.y, b2.x + ',' + b2.y, a2.x + ',' + a2.y].join(' '),
          fill: c, 'fill-opacity': 0.1, style: 'pointer-events:none' });
        ln((a.x + a2.x) / 2, (a.y + a2.y) / 2, (b.x + b2.x) / 2, (b.y + b2.y) / 2, c, 1, '4 4');
      }
      ln(a.x, a.y, b.x, b.y);
      if (sid) hitLine(g, a.x, a.y, b.x, b.y, sid);
      if (a2) { ln(a2.x, a2.y, b2.x, b2.y); if (sid) hitLine(g, a2.x, a2.y, b2.x, b2.y, sid); }
    } else if (ty === 'prange' || ty === 'drange' || ty === 'measure') {
      var r = rangeText(s), col = r.dv >= 0 ? UPC : DNC;
      var x0 = Math.min(a.x, b.x), x1 = Math.max(a.x, b.x), y0 = Math.min(a.y, b.y), y1 = Math.max(a.y, b.y);
      var xm = (a.x + b.x) / 2, ym = (a.y + b.y) / 2;
      var txt, ly;
      if (ty === 'drange') {
        mkEl(g, 'rect', { x: x0, y: 0, width: x1 - x0, height: G.h, fill: c, 'fill-opacity': 0.06, style: 'pointer-events:none' });
        ln(x0, 0, x0, G.h, c, 1, '4 4'); ln(x1, 0, x1, G.h, c, 1, '4 4');
        ln(a.x, a.y, b.x, a.y, c, 1.6, null);
        head(g, { x: x0, y: a.y }, { x: x1, y: a.y }, c, 1.6); head(g, { x: x1, y: a.y }, { x: x0, y: a.y }, c, 1.6);
        txt = r.time; ly = a.y - 16;
        if (sid) hitLine(g, x0, a.y, x1, a.y, sid);
        label(g, xm, ly, txt, c, { sid: sid });
      } else {
        mkEl(g, 'rect', { x: x0, y: y0, width: x1 - x0, height: y1 - y0, fill: col, 'fill-opacity': 0.12, stroke: col, 'stroke-width': 1,
          'stroke-dasharray': ty === 'measure' ? '4 3' : null, style: 'pointer-events:none' });
        ln(xm, a.y, xm, b.y, col, 1.6, null); head(g, { x: xm, y: a.y }, { x: xm, y: b.y }, col, 1.6);
        if (ty === 'measure') { ln(a.x, ym, b.x, ym, col, 1.6, null); head(g, { x: a.x, y: ym }, { x: b.x, y: ym }, col, 1.6); }
        if (ty === 'prange') { ln(x0, a.y, x1, a.y, col, 1, '4 4'); ln(x0, b.y, x1, b.y, col, 1, '4 4'); }
        txt = ty === 'measure' ? r.price + ' · ' + r.time : r.price;
        ly = r.dv >= 0 ? y0 - 14 : y1 + 14;
        if (sid) {
          hitLine(g, xm, a.y, xm, b.y, sid);
          mkEl(g, 'rect', { x: x0, y: y0, width: x1 - x0, height: y1 - y0, fill: 'none', stroke: '#fff', 'stroke-opacity': 0, 'stroke-width': 12,
            'data-sid': sid, style: 'pointer-events:stroke;cursor:move' });
        }
        label(g, xm, ly, txt, col, { sid: sid });
      }
    } else if (ty === 'text') {
      label(g, a.x, a.y, s.txt || 'Ghi chú', '#14261F', { anchor: 'start', fg: c, size: 13, bgo: 0.92, stroke: c, sid: sid });
    } else if (ty === 'callout') {
      ln(a.x, a.y, b.x, b.y, c, 1.4, null);
      mkEl(g, 'circle', { cx: a.x, cy: a.y, r: 3.5, fill: c, style: 'pointer-events:none' });
      if (sid) hitLine(g, a.x, a.y, b.x, b.y, sid);
      label(g, b.x, b.y, s.txt || 'Ghi chú', c, { anchor: 'middle', size: 12, sid: sid });
    }

    if (!isDraft && S.sel === s.id) {                              // điểm kéo của nét đang chọn
      var hs = [];
      if (ty === 'hline') hs.push({ i: 0, x: G.w / 2, y: a.y });
      else if (ty === 'vline') hs.push({ i: 0, x: a.x, y: G.h / 2 });
      else if (ty === 'channel' && chn) { hs.push({ i: 0, x: a.x, y: a.y }, { i: 1, x: b.x, y: b.y }, { i: 2, x: (chn.a2.x + chn.b2.x) / 2, y: (chn.a2.y + chn.b2.y) / 2 }); }
      else s.p.forEach(function (q, i) { hs.push({ i: i, x: X(q.t), y: Y(q.v) }); });
      hs.forEach(function (h) {
        mkEl(g, 'circle', { cx: h.x, cy: h.y, r: 5.5, fill: '#fff', stroke: c, 'stroke-width': 2,
          'data-sid': s.id, 'data-h': h.i, style: 'pointer-events:all;cursor:grab' });
      });
    }
  }

  function render() {
    if (!I || !G) return;
    var svg = I.svg;
    while (svg.firstChild) svg.removeChild(svg.firstChild);
    S.shapes.forEach(function (s) { try { drawShape(s, svg, false); } catch (e) {} });
    if (S.draft) { try { drawShape(S.draft, svg, true); } catch (e) {} }
    refreshBar();
  }

  // ---------------------------------------------------------------- thanh công cụ
  function injectStyle() {
    if (D.getElementById('vnd-style')) return;
    var st = D.createElement('style');
    st.id = 'vnd-style';
    st.textContent =
      '.vnd-bar{position:absolute;z-index:1003;display:flex;flex-direction:column;align-items:center;gap:2px;width:42px;box-sizing:border-box;padding:6px 4px;' +
      'overflow-y:auto;overflow-x:hidden;scrollbar-width:none;' +
      'background:rgba(20,38,31,.96);border:1px solid rgba(230,239,233,.16);border-radius:8px;box-shadow:0 4px 16px rgba(0,0,0,.45);' +
      'user-select:none;-webkit-user-select:none;font-family:' + FONT + '}' +
      '.vnd-bar::-webkit-scrollbar{display:none}' +
      '.vnd-b{position:relative;flex:none;width:32px;height:32px;display:flex;align-items:center;justify-content:center;border-radius:6px;' +
      'color:#CBD2DC;background:transparent;border:0;cursor:pointer;padding:0}' +
      '.vnd-b:hover{background:rgba(230,239,233,.12);color:#fff}' +
      '.vnd-b.on{background:rgba(45,212,167,.22);color:#2DD4A7}' +
      '.vnd-b.off{opacity:.38}' +
      '.vnd-sep{flex:none;width:24px;height:1px;background:rgba(230,239,233,.18);margin:4px 0}' +
      '.vnd-col{width:22px;height:22px;padding:0;border:2px solid rgba(230,239,233,.5);border-radius:50%;background:none;cursor:pointer;overflow:hidden}' +
      '.vnd-col::-webkit-color-swatch-wrapper{padding:0}.vnd-col::-webkit-color-swatch{border:0;border-radius:50%}' +
      '.vnd-tab{position:absolute;z-index:1003;width:16px;height:40px;display:flex;align-items:center;justify-content:center;box-sizing:border-box;' +
      'background:rgba(20,38,31,.96);border:1px solid rgba(230,239,233,.16);border-radius:0 8px 8px 0;color:#CBD2DC;cursor:pointer;padding:0}' +
      '.vnd-tab:hover{color:#fff;background:rgba(45,70,60,.98)}' +
      '.vnd-tip{position:absolute;z-index:1005;transform:translateY(-50%);background:#0B1512;color:#E6EFE9;border:1px solid rgba(230,239,233,.2);' +
      'padding:4px 9px;border-radius:5px;font:600 12px ' + FONT + ';white-space:nowrap;pointer-events:none}' +
      '.vnd-hint{position:absolute;z-index:1003;font:600 12px ' + FONT + ';color:#E6EFE9;background:rgba(11,21,18,.92);' +
      'border:1px solid rgba(45,212,167,.5);padding:3px 9px;border-radius:5px;pointer-events:none;white-space:nowrap}';
    D.head.appendChild(st);
  }

  function showTip(el, text) {
    if (!I || !G) return;
    var br = el.getBoundingClientRect(), pr = G.pc.getBoundingClientRect();
    I.tip.textContent = text;
    I.tip.style.left = (br.right - pr.left + 8) + 'px';
    I.tip.style.top = (br.top - pr.top + br.height / 2) + 'px';
    I.tip.style.display = 'block';
  }
  function hideTip() { if (I) I.tip.style.display = 'none'; }
  function stopEv(el) {
    ['pointerdown', 'mousedown', 'click', 'dblclick', 'wheel'].forEach(function (n) { el.addEventListener(n, function (e) { e.stopPropagation(); }); });
  }
  function buildBar() {
    var bar = html('div', 'vnd-bar');
    TOOLS.forEach(function (t) {
      if (t.sep) { bar.appendChild(html('div', 'vnd-sep')); return; }
      var b;
      if (t.act === 'color') {
        b = html('div', 'vnd-b');
        var inp = html('input', 'vnd-col');
        inp.type = 'color'; inp.value = S.color; inp.id = 'vnd-color-' + TF;
        inp.addEventListener('input', function () {
          S.color = inp.value;
          var s = byId(S.sel);
          if (s) { s.c = S.color; }
          save(); render();
        });
        b.appendChild(inp);
      } else {
        b = html('button', 'vnd-b'); b.type = 'button'; b.innerHTML = t.icon;
        b.addEventListener('click', function (e) { e.preventDefault(); e.stopPropagation(); onBtn(t); });
      }
      b.setAttribute('data-id', t.id);
      b.addEventListener('mouseenter', function () { showTip(b, t.tip); });
      b.addEventListener('mouseleave', hideTip);
      bar.appendChild(b);
    });
    stopEv(bar);
    bar.addEventListener('scroll', hideTip);
    return bar;
  }
  var CHEV_L = ICON('<path d="M12 5l-5 5 5 5"/>'), CHEV_R = ICON('<path d="M8 5l5 5-5 5"/>');
  function buildTab() {                                              // nút nhỏ ở mép thanh dọc: bấm để ẩn / hiện thanh công cụ vẽ
    var tab = html('button', 'vnd-tab'); tab.type = 'button';
    tab.addEventListener('click', function (e) {
      e.preventDefault(); e.stopPropagation();
      S.dockOpen = !S.dockOpen; lsSet(LSO, S.dockOpen); hideTip(); refreshBar();
    });
    tab.addEventListener('mouseenter', function () { showTip(tab, S.dockOpen ? 'Ẩn thanh công cụ vẽ' : 'Hiện thanh công cụ vẽ'); });
    tab.addEventListener('mouseleave', hideTip);
    stopEv(tab);
    return tab;
  }
  function refreshBar() {
    if (!I) return;
    var bs = I.bar.querySelectorAll('.vnd-b');
    for (var i = 0; i < bs.length; i++) {
      var id = bs[i].getAttribute('data-id'), on = false, off = false;
      if (id === 'cursor') on = !S.tool;
      else if (DEF[id] && DEF[id].pts) on = S.tool === id;
      else if (id === 'magnet') on = S.magnet;
      else if (id === 'hide') on = S.hidden;
      else if (id === 'undo') off = !S.undo.length;
      else if (id === 'del') off = !S.sel;
      else if (id === 'clear') off = !S.shapes.length;
      bs[i].classList.toggle('on', on); bs[i].classList.toggle('off', off);
    }
    var ci = D.getElementById('vnd-color-' + TF); if (ci) ci.value = S.color;
    I.svg.style.display = S.hidden ? 'none' : 'block';
    I.cap.style.pointerEvents = S.tool && !S.hidden ? 'auto' : 'none';
    I.cap.style.cursor = 'crosshair';
    var hint = '';                                               // không hiện dòng hướng dẫn phía trên biểu đồ
    I.hint.textContent = hint; I.hint.style.display = hint ? 'block' : 'none';
    placeBar();
  }
  function placeBar() {
    if (!G) return;
    var open = S.dockOpen, top = G.oy + G.top + 6, left = G.ox + 2;
    I.bar.style.display = open ? 'flex' : 'none';
    I.bar.style.maxHeight = Math.max(120, (G.pc.clientHeight || 600) - top - 24) + 'px';
    I.bar.style.left = left + 'px'; I.bar.style.top = top + 'px';
    var bw = open ? I.bar.offsetWidth : 0, bh = open ? I.bar.offsetHeight : 0;
    I.tab.style.display = 'flex';
    I.tab.style.left = (left + bw - (open ? 1 : 0)) + 'px';
    I.tab.style.top = (open ? top + Math.max(0, bh / 2 - 20) : top) + 'px';
    if (I.tabOpen !== open) { I.tab.innerHTML = open ? CHEV_L : CHEV_R; I.tabOpen = open; }
    I.hint.style.left = (left + bw + 24) + 'px'; I.hint.style.top = top + 'px';
  }

  function setTool(id) {
    S.draft = null; S.tool = id; if (id) { S.hidden = false; S.sel = null; }
    render();
  }
  function onBtn(t) {
    if (t.act === 'magnet') { S.magnet = !S.magnet; save(); render(); return; }
    if (t.act === 'undo') { doUndo(); return; }
    if (t.act === 'del') { delSel(); return; }
    if (t.act === 'clear') {
      if (!S.shapes.length) return;
      if (P.confirm('Xoá tất cả nét vẽ của ' + CODE + ' (' + TF + ')?')) { pushUndo(); S.shapes = []; S.sel = null; save(); render(); }
      return;
    }
    if (t.act === 'hide') { S.hidden = !S.hidden; if (S.hidden) { S.tool = null; S.draft = null; } render(); return; }
    if (t.id === 'cursor') { setTool(null); return; }
    setTool(S.tool === t.id ? null : t.id);
  }
  function doUndo() {
    if (!S.undo.length) return;
    try { S.shapes = JSON.parse(S.undo.pop()); } catch (e) { return; }
    S.sel = null; S.draft = null; save(); render();
  }
  function delSel() {
    if (!S.sel) return;
    pushUndo(); S.shapes = S.shapes.filter(function (s) { return s.id !== S.sel; }); S.sel = null; save(); render();
  }

  // ---------------------------------------------------------------- tạo nét vẽ bằng chuột
  function chanNext(pt) {                                           // đường song song: xong đường gốc (điểm 1, 2) -> chuyển sang chọn điểm thứ 3
    var d = S.draft, a = { x: X(d.p[0].t), y: Y(d.p[0].v) }, b = { x: X(pt.t), y: Y(pt.v) };
    if (Math.abs(a.x - b.x) + Math.abs(a.y - b.y) < 4) return;
    d.p[1] = pt; d.stage = 2; d.dragging = false; d.p[2] = { t: pt.t, v: pt.v }; render();
  }
  function finishDraft() {
    var d = S.draft; S.draft = null;
    if (!d) return;
    if (d.type === 'channel' && !d.p[2]) { setTool(null); return; }
    var a = { x: X(d.p[0].t), y: Y(d.p[0].v) }, b = { x: X(d.p[1].t), y: Y(d.p[1].v) };
    if (Math.abs(a.x - b.x) + Math.abs(a.y - b.y) < 4) { setTool(null); return; }       // hai điểm trùng nhau: bỏ
    delete d.down; delete d.dragging;
    if (d.type === 'callout') {
      var tx = P.prompt('Nội dung ghi chú:', '');
      if (!tx) { setTool(null); return; }
      d.txt = tx;
    }
    pushUndo(); S.shapes.push(d); S.sel = d.id; S.tool = null; save(); render();
  }
  function capPos(e) { var r = I.cap.getBoundingClientRect(); return { x: e.clientX - r.left, y: e.clientY - r.top }; }

  function onCapDown(e) {
    if (!S.tool || e.button !== 0) return;
    e.preventDefault(); e.stopPropagation();
    var m = capPos(e), pt = fromPx(m.x, m.y, S.magnet), def = DEF[S.tool];
    if (def.pts === 1) {
      var s = { id: uid(), type: S.tool, p: [pt], c: S.color, w: 1.6 };
      if (S.tool === 'text') {
        var tx = P.prompt('Nội dung ghi chú:', '');
        if (!tx) { setTool(null); return; }
        s.txt = tx;
      }
      pushUndo(); S.shapes.push(s); S.sel = s.id; S.tool = null; save(); render();
      return;
    }
    if (!S.draft) {
      S.draft = { id: uid(), type: S.tool, p: [pt, { t: pt.t, v: pt.v }], c: S.color, w: 1.6, down: m, dragging: true };
      try { I.cap.setPointerCapture(e.pointerId); } catch (err) {}
    } else {
      if (S.draft.type === 'channel') {
        if (S.draft.stage === 2) { S.draft.p[2] = pt; finishDraft(); } else chanNext(pt);
        return;
      }
      S.draft.p[1] = pt; finishDraft(); return;
    }
    render();
  }
  function onCapMove(e) {
    if (!S.draft) return;
    var m = capPos(e); S.draft.p[S.draft.stage === 2 ? 2 : 1] = fromPx(m.x, m.y, S.magnet); render();
  }
  function onCapUp(e) {
    if (!S.draft || !S.draft.dragging) return;
    var m = capPos(e), dd = Math.abs(m.x - S.draft.down.x) + Math.abs(m.y - S.draft.down.y);
    try { I.cap.releasePointerCapture(e.pointerId); } catch (err) {}
    if (dd > 8) { if (S.draft.type === 'channel') chanNext(fromPx(m.x, m.y, S.magnet)); else { S.draft.p[1] = fromPx(m.x, m.y, S.magnet); finishDraft(); } }
    else { S.draft.dragging = false; render(); }                    // bấm - bấm: chờ điểm thứ hai
  }

  // ---------------------------------------------------------------- chọn / kéo / sửa nét vẽ
  function onSvgDown(e) {
    var el = e.target && e.target.closest ? e.target.closest('[data-sid]') : null;
    if (!el || S.tool || e.button !== 0) return;
    var s = byId(el.getAttribute('data-sid'));
    if (!s) return;
    e.preventDefault(); e.stopPropagation();
    S.sel = s.id;
    var hi = el.hasAttribute('data-h') ? +el.getAttribute('data-h') : -1;
    var orig = s.p.map(function (q) { return { t: q.t, v: q.v, x: X(q.t), y: Y(q.v) }; });
    var r0 = I.cap.getBoundingClientRect(), sx = e.clientX, sy = e.clientY, moved = false;
    render();
    function mv(ev) {
      var dx = ev.clientX - sx, dy = ev.clientY - sy;
      if (!moved) { if (Math.abs(dx) + Math.abs(dy) < 3) return; moved = true; pushUndo(); }
      if (hi >= 0) {
        var q = fromPx(ev.clientX - r0.left, ev.clientY - r0.top, S.magnet);
        if (s.type === 'hline') s.p[0].v = q.v;
        else if (s.type === 'vline') s.p[0].t = q.t;
        else s.p[hi] = q;
      } else {
        s.p.forEach(function (pp, i) {
          var nq = fromPx(orig[i].x + (s.type === 'hline' ? 0 : dx), orig[i].y + (s.type === 'vline' ? 0 : dy), false);
          pp.t = nq.t; pp.v = nq.v;
        });
      }
      render();
    }
    function up() {
      D.removeEventListener('pointermove', mv, true); D.removeEventListener('pointerup', up, true);
      if (moved) save();
    }
    D.addEventListener('pointermove', mv, true); D.addEventListener('pointerup', up, true);
  }
  function onSvgDbl(e) {
    var el = e.target && e.target.closest ? e.target.closest('[data-sid]') : null;
    var s = el && byId(el.getAttribute('data-sid'));
    if (!s || (s.type !== 'text' && s.type !== 'callout')) return;
    var tx = P.prompt('Sửa ghi chú:', s.txt || '');
    if (tx == null) return;
    if (tx === '') { delSel(); return; }
    pushUndo(); s.txt = tx; save(); render();
  }

  function onKey(e) {
    var t = e.target, tag = t && t.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || (t && t.isContentEditable)) return;
    if (e.key === 'Escape') { if (S.draft || S.tool || S.sel) { S.draft = null; S.tool = null; S.sel = null; render(); } }
    else if ((e.key === 'Delete' || e.key === 'Backspace') && S.sel) { e.preventDefault(); delSel(); }
    else if ((e.ctrlKey || e.metaKey) && (e.key === 'z' || e.key === 'Z') && S.undo.length && (!P.__vnAct || P.__vnAct === TF)) { e.preventDefault(); doUndo(); }
  }
  function onDocDown(e) {                                           // bấm ra ngoài nét vẽ: bỏ chọn
    if (!S.sel || S.tool) return;
    var t = e.target;
    if (t && t.closest && (t.closest('[data-sid]') || t.closest('.vnd-bar') || t.closest('.vnd-tab'))) return;
    S.sel = null; render();
  }

  // ---------------------------------------------------------------- gắn vào biểu đồ
  function sigOf() {
    var cx = G.cx, cy = G.cy;
    return [G.left, G.top, G.w, G.h, G.ox, G.oy, String(cx.range && cx.range[0]), String(cx.range && cx.range[1]),
            cy.range && cy.range[0], cy.range && cy.range[1]].join('|');
  }
  function layout() {
    var g = geo(I.gd);
    if (!g) { I.box.style.display = 'none'; I.bar.style.display = 'none'; I.tab.style.display = 'none'; I.tip.style.display = 'none'; I.hint.style.display = 'none'; return false; }
    G = g;
    if (I.box.parentNode !== g.pc) { g.pc.appendChild(I.box); g.pc.appendChild(I.bar); g.pc.appendChild(I.tab); g.pc.appendChild(I.tip); g.pc.appendChild(I.hint); }
    I.box.style.cssText = 'position:absolute;pointer-events:none;overflow:hidden;z-index:1000;left:' + (g.ox + g.left) + 'px;top:' + (g.oy + g.top) +
                          'px;width:' + g.w + 'px;height:' + g.h + 'px;';
    return true;
  }
  function attach(gd) {
    injectStyle();
    var box = html('div', 'vnd-box');
    var svg = D.createElementNS(NS, 'svg');
    svg.setAttribute('style', 'position:absolute;left:0;top:0;width:100%;height:100%;overflow:hidden;pointer-events:none');
    var cap = html('div', 'vnd-cap', 'position:absolute;left:0;top:0;width:100%;height:100%;pointer-events:none;touch-action:none');
    box.appendChild(svg); box.appendChild(cap);
    I = { gd: gd, box: box, svg: svg, cap: cap, bar: null, hint: html('div', 'vnd-hint', 'display:none'), xs: null, xsKey: null, sig: '' };
    I.bar = buildBar();
    I.tab = buildTab(); I.tip = html('div', 'vnd-tip', 'display:none');
    [I.bar, I.tab, cap, svg].forEach(function (el) { el.addEventListener('pointerdown', function () { P.__vnAct = TF; }, true); });
    cap.addEventListener('pointerdown', onCapDown);
    cap.addEventListener('pointermove', onCapMove);
    cap.addEventListener('pointerup', onCapUp);
    svg.addEventListener('pointerdown', onSvgDown);
    svg.addEventListener('dblclick', onSvgDbl);
    D.addEventListener('keydown', onKey, true);
    D.addEventListener('pointerdown', onDocDown, true);
    var sched = function () { if (I && I.gd === gd) { var ok = layout(); if (ok) { I.sig = sigOf(); render(); } } };
    try { gd.on('plotly_afterplot', sched); gd.on('plotly_relayout', sched); gd.on('plotly_relayouting', sched); } catch (e) {}
    I.timer = P.setInterval(function () {
      if (!gd.isConnected || !tfOk(gd)) { teardown(); return; }       // biểu đồ bị thay / đổi sang khung khác: nhả ra cho bản đúng khung gắn
      var g = geo(gd);
      if (!g) return;
      G = g;
      if (I.box.parentNode !== g.pc || I.sig !== sigOf()) { if (layout()) { I.sig = sigOf(); render(); } }
    }, 100);
    gd.__vnDrawOn = true;
    if (layout()) { I.sig = sigOf(); render(); }
  }
  function teardown() {
    if (!I) return;
    var cur = I; I = null;
    P.clearInterval(cur.timer);
    try { cur.gd.removeListener('plotly_afterplot'); } catch (e) {}
    D.removeEventListener('keydown', onKey, true);
    D.removeEventListener('pointerdown', onDocDown, true);
    [cur.box, cur.bar, cur.tab, cur.tip, cur.hint].forEach(function (e) { if (e && e.parentNode) e.parentNode.removeChild(e); });
    cur.gd.__vnDrawOn = false;
  }
  function scan() {
    if (I) return;
    var list = D.querySelectorAll('.js-plotly-plot');
    for (var i = 0; i < list.length; i++) {
      var gd = list[i];
      if (!gd.__vnDrawOn && gd._fullLayout && candleOf(gd)) { attach(gd); return; }
    }
  }
  scan();
  var timer = P.setInterval(scan, 800);                             // biểu đồ vẽ sau / vẽ lại khi đổi mã, khung thời gian
  P[SLOT] = function () { P.clearInterval(timer); teardown(); P[SLOT] = null; };
})();
"""


def _script(code: str, tf: str) -> str:
    key = f"{code}|{tf}"
    js = (DRAW_JS.replace("__KEY__", json.dumps(key)).replace("__CODE__", json.dumps(str(code)))
          .replace("__TF__", json.dumps(str(tf))))
    return "<script>" + js + "</script>"


def inject(code: str, tf: str):
    """Gắn thanh công cụ vẽ vào biểu đồ nến của `code` ở khung `tf` (D/W/M). Cùng cách gắn với crosshair.inject()."""
    html = _script(code, tf)
    try:
        import streamlit.components.v1 as components
        components.html(html, height=0)
        return
    except Exception:  # noqa: BLE001
        pass
    try:
        if "unsafe_allow_javascript" in inspect.signature(st.html).parameters:
            st.html(html, unsafe_allow_javascript=True)
    except Exception:  # noqa: BLE001
        pass
