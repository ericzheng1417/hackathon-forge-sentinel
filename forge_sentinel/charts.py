"""Server-rendered SVG charts (ported 1:1 from the original dashboard)."""
from __future__ import annotations

import math
from html import escape

from .engine import VARS, Analysis


def fmt(n, d: int = 2) -> str:
    try:
        n = float(n)
    except (TypeError, ValueError):
        return "—"
    return f"{n:.{d}f}" if math.isfinite(n) else "—"


def num(v) -> str:
    """Display a stored measurement the way the JS app did (no trailing .0)."""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def _c(v: float) -> str:
    return f"{v:.2f}"


def control_chart(a: Analysis, lsl: float) -> str:
    v = a.metric
    W, H, left, right, top, bot = 760, 260, 43, 84, 23, 29
    lo = min(*a.x, a.lcl, lsl if v == "strength" else math.inf) - 10
    hi = max(*a.x, a.ucl) + 10
    span = (hi - lo) or 1
    n = len(a.x)
    X = lambda i: left + i * (W - left - right) / max(n - 1, 1)
    Y = lambda y: top + (hi - y) / span * (H - top - bot)
    unit = VARS[v][1]
    parts = []
    parts.append(f'<rect x="{left}" y="{top}" width="{_c(X(a.baseline - 1) - left)}" height="{H - top - bot}" fill="#f1f6f3"/>')
    for i in range(5):
        y = lo + span * i / 4
        parts.append(f'<line x1="{left}" y1="{_c(Y(y))}" x2="{W - right}" y2="{_c(Y(y))}" stroke="#edf1ef"/>'
                     f'<text x="4" y="{_c(Y(y) + 3)}">{fmt(y, 0)}</text>')
    marks = [(a.ucl, "UCL", "#a1b4ac"), (a.center, "Mean", "#5b9685"), (a.lcl, "LCL", "#a1b4ac")]
    if v == "strength":
        marks.append((lsl, "LSL", "#c36a57"))
    for val, label, col in marks:
        parts.append(f'<line x1="{left}" x2="{W - right}" y1="{_c(Y(val))}" y2="{_c(Y(val))}" stroke="{col}" '
                     f'stroke-dasharray="5 5"/><text x="{W - right + 8}" y="{_c(Y(val) + 3)}" '
                     f'style="fill:{col}">{label} {fmt(val, 0)}</text>')
    path = " ".join(("L" if i else "M") + f"{_c(X(i))},{_c(Y(y))}" for i, y in enumerate(a.x))
    parts.append(f'<path d="{path}" fill="none" stroke="#427e6d" stroke-width="1.7"/>')
    flagged = a.flagged
    for i, y in enumerate(a.x):
        hit = i in flagged
        rid = escape(str(a.records[i]["id"]))
        parts.append(f'<circle cx="{_c(X(i))}" cy="{_c(Y(y))}" r="{3.6 if hit else 2.6}" '
                     f'fill="{"#c66955" if hit else "#427e6d"}" onclick="fsBuild({i})">'
                     f'<title>{rid}: {num(a.records[i][v])} {unit}</title></circle>')
    for i in sorted({0, n // 4, n // 2, int(n * 0.75), n - 1}):
        parts.append(f'<text x="{_c(X(i) - 7)}" y="{H - 5}">{i + 1}</text>')
    legend = (f'<div class="legend"><span>Measured {unit}</span><span class="control">Control limits</span>'
              + ('<span class="spec">Specification</span>' if v == "strength" else "") + "</div>")
    return (legend + f'<svg class="chart" viewBox="0 0 {W} {H}" role="img" '
            f'aria-label="{VARS[v][0]} individuals control chart">' + "".join(parts) + "</svg>")


def histogram(a: Analysis, lsl: float) -> str:
    lo = min(*a.x, lsl) - 10
    hi = max(a.x) + 10
    nb = 12
    bins = [0] * nb
    for x in a.x:
        bins[min(nb - 1, math.floor((x - lo) / (hi - lo) * nb))] += 1
    mx = max(bins) or 1
    xx = lambda x: 25 + (x - lo) / (hi - lo) * 290
    rects = "".join(
        f'<rect x="{_c(25 + i * 290 / nb)}" y="{_c(116 - b / mx * 86)}" width="{_c(290 / nb - 3)}" '
        f'height="{_c(b / mx * 86)}" rx="2" fill="{"#dba08f" if lo + (i + 0.5) * (hi - lo) / nb < lsl else "#9bbcaf"}"/>'
        for i, b in enumerate(bins))
    return (f'<svg class="chart" viewBox="0 0 350 155" aria-label="Strength histogram" role="img">{rects}'
            f'<line x1="{_c(xx(lsl))}" x2="{_c(xx(lsl))}" y1="18" y2="120" stroke="#bb6556" stroke-dasharray="4 3"/>'
            f'<text x="{_c(xx(lsl) + 4)}" y="15" style="fill:#bb6556">LSL {num(lsl)}</text>'
            f'<text x="25" y="140">{fmt(lo, 0)}</text><text x="145" y="140">Strength (MPa)</text>'
            f'<text x="290" y="140">{fmt(hi, 0)}</text></svg>')


def scatter(a: Analysis, lsl: float) -> str:
    recs = a.records
    xs = [float(r["oxygen"]) for r in recs]
    ys = [float(r["strength"]) for r in recs]
    lo, hi = min(xs) - 5, max(xs) + 5
    yl, yh = min(*ys, lsl) - 10, max(ys) + 10
    X = lambda x: 50 + (x - lo) / (hi - lo) * 650
    Y = lambda y: 230 - (y - yl) / (yh - yl) * 200
    grid = "".join(
        f'<line x1="50" x2="700" y1="{_c(Y(yl + (yh - yl) * i / 4))}" y2="{_c(Y(yl + (yh - yl) * i / 4))}" stroke="#e5ece7"/>'
        f'<text x="5" y="{_c(Y(yl + (yh - yl) * i / 4))}">{fmt(yl + (yh - yl) * i / 4, 0)}</text>'
        f'<text x="{_c(X(lo + (hi - lo) * i / 4))}" y="250">{fmt(lo + (hi - lo) * i / 4, 0)}</text>'
        for i in range(5))
    pts = "".join(
        f'<circle cx="{_c(X(x))}" cy="{_c(Y(y))}" r="4" fill="{"#bd6c56" if y < lsl else "#628e7e"}" opacity=".8" '
        f'onclick="fsBuild({i})"><title>{escape(str(r["id"]))} · {num(r["oxygen"])} ppm · {num(r["strength"])} MPa</title></circle>'
        for i, (r, x, y) in enumerate(zip(recs, xs, ys)))
    return (f'<svg class="chart" viewBox="0 0 760 280" role="img" aria-label="Oxygen and tensile strength scatterplot">'
            f'{grid}<line x1="50" x2="700" y1="{_c(Y(lsl))}" y2="{_c(Y(lsl))}" stroke="#bd6c56" stroke-dasharray="5 4"/>'
            f'{pts}<text x="330" y="275">Oxygen (ppm)</text><text x="5" y="15">Strength (MPa)</text></svg>')
