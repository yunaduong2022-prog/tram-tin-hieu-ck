"""VNINDEX drawing toolbar adapter; reuses the existing stock drawing tools.

The VNINDEX Plotly chart has a categorical x-axis, unlike the stock charts.
Translate between real ISO trading dates and Plotly's category indices to keep
annotations anchored to dates when the visible chart range changes.
"""
import json
import streamlit.components.v1 as components
import draw_tools as BASE


def _drawing_javascript() -> str:
    js = BASE.DRAW_JS
    patches = [
        (
            "  function X(t) { return G.cx.l2p(t); }",
            r"""  // MIN_VNINDEX_DRAW_TOOLBAR_V1: convert timestamp anchors to category indices.
  // For regular stock date axes, preserve the exact original behavior.
  function catIndex(t) {
    var xs = times(), n = xs.length;
    if (!n) return 0;
    if (n === 1) return 0;
    var i;
    if (t <= xs[0]) return (t - xs[0]) / (xs[1] - xs[0]);
    if (t >= xs[n-1]) return (n-1) + (t - xs[n-1]) / (xs[n-1] - xs[n-2]);
    var lo = 0, hi = n-1;
    while (hi - lo > 1) { var mid = (lo + hi) >> 1;
      if (xs[mid] <= t) lo = mid; else hi = mid; }
    return lo + (t - xs[lo]) / (xs[hi] - xs[lo]);
  }
  function catDate(i) {
    var xs = times(), n = xs.length;
    if (!n) return Date.now();
    if (n === 1) return xs[0];
    if (i <= 0) return xs[0] + i * (xs[1] - xs[0]);
    if (i >= n-1) return xs[n-1] + (i - (n-1)) * (xs[n-1] - xs[n-2]);
    var k = Math.floor(i);
    return xs[k] + (i - k) * (xs[k+1] - xs[k]);
  }
  function X(t) { return G.cx.l2p(G.cx.type === 'category' ? catIndex(t) : t); }"""
        ),
        (
            "var m = G.cx.d2l(tr.x[i]); out.push(isFinite(m) ? m : NaN);",
            "var m = (G.cx.type === 'category' && tr.customdata && tr.customdata[i]) ? Date.parse(tr.customdata[i]) : G.cx.d2l(tr.x[i]); out.push(isFinite(m) ? m : NaN);"
        ),
        (
            "var t = G.cx.p2l(x), v = G.cy.p2l(y);",
            "var idx = G.cx.p2l(x), t = G.cx.type === 'category' ? catDate(idx) : idx, v = G.cy.p2l(y);"
        ),
        (
            "return Math.max(0, Math.round((b - a) / (30.44 * DAY)));",
            "return Math.max(0, Math.round((b - a) / ((TF === 'Q' ? 91.3 : 30.44) * DAY)));"
        ),
    ]
    for old, new in patches:
        if js.count(old) != 1:
            raise RuntimeError('Incompatible draw_tools.py JavaScript anchor: ' + old[:70])
        js = js.replace(old, new, 1)
    return js


def inject(tf: str) -> None:
    if tf not in {'D', 'W', 'M', 'Q'}:
        return
    js = _drawing_javascript()
    js = (js.replace('__KEY__', json.dumps('VNINDEX|' + tf))
              .replace('__CODE__', json.dumps('VNINDEX'))
              .replace('__TF__', json.dumps(tf)))
    components.html('<script>' + js + '</script>', height=0)
