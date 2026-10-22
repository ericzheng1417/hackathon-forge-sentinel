"""Server-rendered SVG charts."""
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
    """Display a stored measurement without a trailing .0."""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def _c(v: float) -> str:
    return f"{v:.2f}"


ZONE_LINE = "#d9e3de"


def control_chart(a: Analysis, lsl: float, usl: float | None = None, zones: bool = True) -> str:
    """Individuals chart with baseline shading, ±1σ/±2σ zone lines and spec limits."""
    v = a.metric
    W, H, left, right, top, bot = 760, 260, 43, 92, 23, 29
    is_s = v == "strength"
    lo = min(*a.x, a.lcl, lsl if is_s else math.inf) - 10
    hi = max(*a.x, a.ucl) + 10
    span = (hi - lo) or 1
    n = len(a.x)
    X = lambda i: left + i * (W - left - right) / max(n - 1, 1)
    Y = lambda y: top + (hi - y) / span * (H - top - bot)
    unit = VARS[v][1]
    parts = [f'<rect x="{left}" y="{top}" width="{_c(X(a.baseline - 1) - left)}" height="{H - top - bot}" fill="#f1f6f3"/>']
    for i in range(5):
        y = lo + span * i / 4
        parts.append(f'<line x1="{left}" y1="{_c(Y(y))}" x2="{W - right}" y2="{_c(Y(y))}" stroke="#f3f6f4"/>'
                     f'<text x="4" y="{_c(Y(y) + 3)}">{fmt(y, 0)}</text>')
    if zones and a.sigma > 0:
        for k in (-2, -1, 1, 2):
            yv = a.center + k * a.sigma
            parts.append(f'<line x1="{left}" x2="{W - right}" y1="{_c(Y(yv))}" y2="{_c(Y(yv))}" stroke="{ZONE_LINE}" stroke-dasharray="2 4"/>')
        for label, k in (("A", 2.5), ("B", 1.5), ("C", 0.5), ("C", -0.5), ("B", -1.5), ("A", -2.5)):
            parts.append(f'<text x="{W - right - 12}" y="{_c(Y(a.center + k * a.sigma) + 3)}" class="zone">{label}</text>')
    marks = [(a.ucl, "UCL", "#a1b4ac"), (a.center, "Mean", "#5b9685"), (a.lcl, "LCL", "#a1b4ac")]
    if is_s:
        marks.append((lsl, "LSL", "#c36a57"))
        if usl is not None and lo <= usl <= hi:
            marks.append((usl, "USL", "#c36a57"))
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
        why = (" — " + "; ".join(flagged[i])) if hit else ""
        parts.append(f'<circle cx="{_c(X(i))}" cy="{_c(Y(y))}" r="{3.6 if hit else 2.6}" '
                     f'fill="{"#c66955" if hit else "#427e6d"}" onclick="fsBuild({i})">'
                     f'<title>{rid}: {num(a.records[i][v])} {unit}{escape(why)}</title></circle>')
    for i in sorted({0, n // 4, n // 2, int(n * 0.75), n - 1}):
        parts.append(f'<text x="{_c(X(i) - 7)}" y="{H - 5}">{i + 1}</text>')
    legend = (f'<div class="legend"><span>Measured {unit}</span><span class="control">Control limits</span>'
              + ('<span class="zones">Zone lines (±1σ, ±2σ)</span>' if zones else "")
              + ('<span class="spec">Specification</span>' if is_s else "") + "</div>")
    return (legend + f'<svg class="chart" viewBox="0 0 {W} {H}" role="img" '
            f'aria-label="{VARS[v][0]} individuals control chart">' + "".join(parts) + "</svg>")


def mr_chart(a: Analysis) -> str:
    """Moving-range chart: MR_i = |x_i − x_{i−1}|, centre MR̄, UCL = 3.267·MR̄, LCL = 0."""
    W, H, left, right, top, bot = 760, 170, 43, 92, 14, 24
    vals = [m for m in a.mr if m is not None]
    hi = max(*vals, a.mr_ucl) * 1.1 or 1
    n = len(a.mr)
    X = lambda i: left + i * (W - left - right) / max(n - 1, 1)
    Y = lambda y: top + (hi - y) / hi * (H - top - bot)
    unit = VARS[a.metric][1]
    parts = [f'<rect x="{left}" y="{top}" width="{_c(X(a.baseline - 1) - left)}" height="{H - top - bot}" fill="#f1f6f3"/>']
    for k in range(3):
        y = hi * k / 2
        parts.append(f'<text x="4" y="{_c(Y(y) + 3)}">{fmt(y, 0)}</text>')
    for val, label, col in ((a.mr_ucl, "UCL", "#a1b4ac"), (a.mr_bar, "MR̄", "#5b9685"), (0, "LCL", "#a1b4ac")):
        parts.append(f'<line x1="{left}" x2="{W - right}" y1="{_c(Y(val))}" y2="{_c(Y(val))}" stroke="{col}" '
                     f'stroke-dasharray="5 5"/><text x="{W - right + 8}" y="{_c(Y(val) + 3)}" style="fill:{col}">'
                     f'{label} {fmt(val, 1)}</text>')
    pts = [(i, m) for i, m in enumerate(a.mr) if m is not None]
    parts.append('<path d="' + " ".join(("L" if k else "M") + f"{_c(X(i))},{_c(Y(m))}" for k, (i, m) in enumerate(pts))
                 + '" fill="none" stroke="#7aa598" stroke-width="1.4"/>')
    for i, m in pts:
        hit = m > a.mr_ucl
        parts.append(f'<circle cx="{_c(X(i))}" cy="{_c(Y(m))}" r="{3.4 if hit else 2.2}" fill="{"#c66955" if hit else "#7aa598"}" '
                     f'onclick="fsBuild({i})"><title>{escape(str(a.records[i]["id"]))}: MR {fmt(m, 1)} {unit}</title></circle>')
    return (f'<svg class="chart" viewBox="0 0 {W} {H}" role="img" aria-label="Moving range chart">'
            + "".join(parts) + "</svg>")


def histogram(x: list[float], label: str, lsl: float | None = None, usl: float | None = None,
              bins: int | None = None, width: int = 350) -> str:
    """Histogram; spec limits (if given) are drawn and included in the axis range.

    width=350 suits a narrow card; use width=760 for a full-width card.
    """
    specs = [s for s in (lsl, usl) if s is not None]
    lo = min(*x, *specs) - 10
    hi = max(*x, *specs) + 10
    nb = bins or (20 if len(specs) == 2 else 12)
    counts = [0] * nb
    for v in x:
        counts[min(nb - 1, max(0, math.floor((v - lo) / (hi - lo) * nb)))] += 1
    mx = max(counts) or 1
    W = width
    pw = W - 60                       # plot width
    xx = lambda v: 25 + (v - lo) / (hi - lo) * pw

    def out(mid):
        return (lsl is not None and mid < lsl) or (usl is not None and mid > usl)
    rects = "".join(
        f'<rect x="{_c(25 + i * pw / nb)}" y="{_c(116 - b / mx * 86)}" width="{_c(max(pw / nb - 2, 1))}" '
        f'height="{_c(b / mx * 86)}" rx="1.5" fill="{"#dba08f" if out(lo + (i + 0.5) * (hi - lo) / nb) else "#9bbcaf"}">'
        f'<title>{fmt(lo + i * (hi - lo) / nb, 1)}–{fmt(lo + (i + 1) * (hi - lo) / nb, 1)}: {b}</title></rect>'
        for i, b in enumerate(counts))
    lines = ""
    for s, name, anchor, dx in ((lsl, "LSL", "start", 4), (usl, "USL", "end", -4)):
        if s is not None:
            lines += (f'<line x1="{_c(xx(s))}" x2="{_c(xx(s))}" y1="18" y2="120" stroke="#bb6556" stroke-dasharray="4 3"/>'
                      f'<text x="{_c(xx(s) + dx)}" y="15" text-anchor="{anchor}" style="fill:#bb6556">{name} {num(s)}</text>')
    return (f'<svg class="chart" viewBox="0 0 {W} 155" aria-label="{escape(label)} histogram" role="img">{rects}{lines}'
            f'<text x="25" y="140">{fmt(lo, 0)}</text><text x="{W / 2}" y="140" text-anchor="middle">{escape(label)}</text>'
            f'<text x="{25 + pw}" y="140" text-anchor="end">{fmt(hi, 0)}</text></svg>')


def boxplot(x: list[float], desc: dict, label: str) -> str:
    """Horizontal box-and-whisker (1.5×IQR whiskers) with the individual points underneath."""
    W, H, left, right = 760, 130, 30, 30
    lo, hi = desc["min"], desc["max"]
    pad = (hi - lo) * 0.06 or 1
    lo, hi = lo - pad, hi + pad
    X = lambda v: left + (v - lo) / (hi - lo) * (W - left - right)
    q1, q3, med, mean = desc["q1"], desc["q3"], desc["median"], desc["mean"]
    fence_lo, fence_hi = q1 - 1.5 * desc["iqr"], q3 + 1.5 * desc["iqr"]
    w_lo = min(v for v in x if v >= fence_lo)
    w_hi = max(v for v in x if v <= fence_hi)
    y0, y1, ym = 22, 62, 42
    parts = [
        f'<line x1="{_c(X(w_lo))}" x2="{_c(X(q1))}" y1="{ym}" y2="{ym}" stroke="#7aa598"/>',
        f'<line x1="{_c(X(q3))}" x2="{_c(X(w_hi))}" y1="{ym}" y2="{ym}" stroke="#7aa598"/>',
        f'<line x1="{_c(X(w_lo))}" x2="{_c(X(w_lo))}" y1="{y0 + 10}" y2="{y1 - 10}" stroke="#7aa598"/>',
        f'<line x1="{_c(X(w_hi))}" x2="{_c(X(w_hi))}" y1="{y0 + 10}" y2="{y1 - 10}" stroke="#7aa598"/>',
        f'<rect x="{_c(X(q1))}" y="{y0}" width="{_c(X(q3) - X(q1))}" height="{y1 - y0}" fill="#e9f2ee" stroke="#5b9685" rx="3"/>',
        f'<line x1="{_c(X(med))}" x2="{_c(X(med))}" y1="{y0}" y2="{y1}" stroke="#216957" stroke-width="2.2"/>',
        f'<path d="M{_c(X(mean))},{ym - 6} l6,6 l-6,6 l-6,-6z" fill="#e3ad56"><title>Mean {fmt(mean, 2)}</title></path>',
    ]
    for i, v in enumerate(x):
        outlier = v < fence_lo or v > fence_hi
        jitter = 84 + (i * 7919 % 17) - 8
        parts.append(f'<circle cx="{_c(X(v))}" cy="{jitter}" r="2.6" fill="{"#c66955" if outlier else "#9bbcaf"}" '
                     f'opacity=".85" onclick="fsBuild({i})"><title>{fmt(v, 1)}</title></circle>')
    for v, name in ((q1, "Q1"), (med, "Median"), (q3, "Q3")):
        parts.append(f'<text x="{_c(X(v))}" y="14" text-anchor="middle">{name} {fmt(v, 1)}</text>')
    parts.append(f'<text x="{left}" y="{H - 4}">{fmt(lo, 0)}</text>'
                 f'<text x="{W / 2}" y="{H - 4}" text-anchor="middle">{escape(label)}</text>'
                 f'<text x="{W - right}" y="{H - 4}" text-anchor="end">{fmt(hi, 0)}</text>')
    return (f'<svg class="chart" viewBox="0 0 {W} {H}" role="img" aria-label="{escape(label)} box plot">'
            + "".join(parts) + "</svg>")


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
        f'<circle cx="{_c(X(x))}" cy="{_c(Y(y))}" r="4" fill="{"#bd6c56" if a.is_fail(r) else "#628e7e"}" opacity=".8" '
        f'onclick="fsBuild({i})"><title>{escape(str(r["id"]))} · {num(r["oxygen"])} ppm · {num(r["strength"])} MPa</title></circle>'
        for i, (r, x, y) in enumerate(zip(recs, xs, ys)))
    return (f'<svg class="chart" viewBox="0 0 760 280" role="img" aria-label="Oxygen and tensile strength scatterplot">'
            f'{grid}<line x1="50" x2="700" y1="{_c(Y(lsl))}" y2="{_c(Y(lsl))}" stroke="#bd6c56" stroke-dasharray="5 4"/>'
            f'{pts}<text x="330" y="275">Oxygen (ppm)</text><text x="5" y="15">Strength (MPa)</text></svg>')
