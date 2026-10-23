"""Server-rendered SVG charts."""
from __future__ import annotations

import math
import statistics
from html import escape

from . import engine
from .engine import VARS, Analysis, _finite


def fmt(n, d: int = 2) -> str:
    try:
        n = float(n)
    except (TypeError, ValueError):
        return "—"
    return f"{n:.{d}f}" if math.isfinite(n) else "—"


def num(v) -> str:
    """Display a stored measurement without a trailing .0; blank values show as —."""
    if v is None or v == "":
        return "—"
    if isinstance(v, float):
        if v.is_integer():
            return str(int(v))
        return f"{round(v, 3):.6g}"   # averages of coupons can carry long binary tails
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
                     f'fill="{"#c66955" if hit else "#427e6d"}" onclick="fsBuild({a.idx[i]})">'
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
                     f'onclick="fsBuild({a.idx[i]})"><title>{escape(str(a.records[i]["id"]))}: MR {fmt(m, 1)} {unit}</title></circle>')
    return (f'<svg class="chart" viewBox="0 0 {W} {H}" role="img" aria-label="Moving range chart">'
            + "".join(parts) + "</svg>")


def histogram(x: list[float], label: str, lsl: float | None = None, usl: float | None = None,
              bins: int | None = None, width: int = 350, curves: list | None = None) -> str:
    """Histogram; spec limits (if given) are drawn and included in the axis range.

    width=350 suits a narrow card; use width=760 for a full-width card.
    curves: optional fitted normal curves [(mean, sigma, colour, dashed, label)], scaled to counts
    (expected count per bin = n · bin width · normal pdf).
    """
    specs = [s for s in (lsl, usl) if s is not None]
    lo = min(*x, *specs) - 10
    hi = max(*x, *specs) + 10
    nb = bins or (20 if len(specs) == 2 else 12)
    bw = (hi - lo) / nb
    counts = [0] * nb
    for v in x:
        counts[min(nb - 1, max(0, math.floor((v - lo) / (hi - lo) * nb)))] += 1
    curves = [c for c in (curves or []) if _finite(c[0]) and _finite(c[1]) and c[1] > 0]
    peaks = [len(x) * bw / (c[1] * math.sqrt(2 * math.pi)) for c in curves]
    mx = max([*counts, *peaks]) or 1
    W = width
    pw = W - 60                       # plot width
    xx = lambda v: 25 + (v - lo) / (hi - lo) * pw
    yy = lambda c: 116 - c / mx * 86

    def out(mid):
        return (lsl is not None and mid < lsl) or (usl is not None and mid > usl)
    rects = "".join(
        f'<rect x="{_c(25 + i * pw / nb)}" y="{_c(yy(b))}" width="{_c(max(pw / nb - 2, 1))}" '
        f'height="{_c(b / mx * 86)}" rx="1.5" fill="{"#dba08f" if out(lo + (i + 0.5) * bw) else "#9bbcaf"}">'
        f'<title>{fmt(lo + i * bw, 1)}–{fmt(lo + (i + 1) * bw, 1)}: {b}</title></rect>'
        for i, b in enumerate(counts))
    paths, legend = "", ""
    for (m, sd, col, dashed, name) in curves:
        nd = statistics.NormalDist(m, sd)
        pts = [lo + (hi - lo) * k / 160 for k in range(161)]
        d = " ".join(("L" if k else "M") + f"{_c(xx(v))},{_c(yy(len(x) * bw * nd.pdf(v)))}" for k, v in enumerate(pts))
        paths += (f'<path d="{d}" fill="none" stroke="{col}" stroke-width="1.6"'
                  + (' stroke-dasharray="5 3"' if dashed else "") + f'><title>{escape(name)}</title></path>')
    if curves:
        legend = "".join(
            f'<line x1="{_c(30 + i * 150)}" x2="{_c(48 + i * 150)}" y1="150" y2="150" stroke="{col}" stroke-width="1.6"'
            + (' stroke-dasharray="5 3"' if dashed else "") + f'/><text x="{_c(52 + i * 150)}" y="153">{escape(name)}</text>'
            for i, (_, _, col, dashed, name) in enumerate(curves))
    lines = ""
    for s, name, anchor, dx in ((lsl, "LSL", "start", 4), (usl, "USL", "end", -4)):
        if s is not None:
            lines += (f'<line x1="{_c(xx(s))}" x2="{_c(xx(s))}" y1="18" y2="120" stroke="#bb6556" stroke-dasharray="4 3"/>'
                      f'<text x="{_c(xx(s) + dx)}" y="15" text-anchor="{anchor}" style="fill:#bb6556">{name} {num(s)}</text>')
    H = 162 if curves else 155
    return (f'<svg class="chart" viewBox="0 0 {W} {H}" aria-label="{escape(label)} histogram" role="img">{rects}{paths}{lines}'
            f'<text x="25" y="134">{fmt(lo, 0)}</text><text x="{W / 2}" y="134" text-anchor="middle">{escape(label)}</text>'
            f'<text x="{25 + pw}" y="134" text-anchor="end">{fmt(hi, 0)}</text>{legend}</svg>')


def qq_plot(values: list[float], label: str, normal: dict | None = None, idx: list[int] | None = None) -> str:
    """Normal probability (Q-Q) plot: sorted data against standard-normal quantiles, with the
    reference line mean + SD·z. Points near the line → approximately normal."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ys = [values[i] for i in order]
    n = len(ys)
    if n < 3:
        return ""
    zs = engine.normal_quantiles(n)
    m, sd = statistics.fmean(ys), statistics.stdev(ys)
    W, H, left, right, top, bot = 760, 250, 50, 30, 18, 34
    zlo, zhi = zs[0] - 0.2, zs[-1] + 0.2
    lo, hi = min(ys[0], m + sd * zlo), max(ys[-1], m + sd * zhi)
    pad = (hi - lo) * 0.05 or 1
    lo, hi = lo - pad, hi + pad
    X = lambda z: left + (z - zlo) / (zhi - zlo) * (W - left - right)
    Y = lambda v: top + (hi - v) / (hi - lo) * (H - top - bot)
    parts = []
    for k in range(5):
        v = lo + (hi - lo) * k / 4
        parts.append(f'<line x1="{left}" x2="{W - right}" y1="{_c(Y(v))}" y2="{_c(Y(v))}" stroke="#f0f3f1"/>'
                     f'<text x="4" y="{_c(Y(v) + 3)}">{fmt(v, 0)}</text>')
    for z in (-2, -1, 0, 1, 2):
        if zlo <= z <= zhi:
            parts.append(f'<text x="{_c(X(z))}" y="{H - 18}" text-anchor="middle">{z}</text>')
    parts.append(f'<line x1="{_c(X(zlo))}" y1="{_c(Y(m + sd * zlo))}" x2="{_c(X(zhi))}" y2="{_c(Y(m + sd * zhi))}" '
                 f'stroke="#c36a57" stroke-dasharray="5 4" stroke-width="1.4"/>')
    for z, v, i in zip(zs, ys, order):
        tgt = (idx[i] if idx else i)
        parts.append(f'<circle cx="{_c(X(z))}" cy="{_c(Y(v))}" r="2.8" fill="#427e6d" opacity=".85" onclick="fsBuild({tgt})">'
                     f'<title>{fmt(v, 1)} (z = {fmt(z, 2)})</title></circle>')
    parts.append(f'<text x="{W / 2}" y="{H - 3}" text-anchor="middle">Standard normal quantile (z)</text>')
    if normal and _finite(normal.get("p")):
        verdict = "consistent with a normal distribution" if normal["normal"] else "not normal (p < 0.05)"
        parts.append(f'<text x="{left + 8}" y="{top + 10}" style="fill:#4f5e60">Anderson-Darling A² = {fmt(normal["ad"], 3)}, '
                     f'p {_pfmt(normal["p"])} · {verdict}</text>')
    return (f'<svg class="chart" viewBox="0 0 {W} {H}" role="img" aria-label="{escape(label)} normal probability plot">'
            + "".join(parts) + "</svg>")


def _pfmt(p: float) -> str:
    return "< 0.005" if p < 0.005 else "= " + fmt(p, 3)


def _stepped(X, Y, vals) -> str:
    """Path for per-subgroup limits: flat across each point, stepping half-way between points."""
    pts = [(i, v) for i, v in enumerate(vals) if v is not None]
    if not pts:
        return ""
    d = []
    for k, (i, v) in enumerate(pts):
        x0 = X(i - 0.5) if k else X(i)
        x1 = X(i + 0.5) if k < len(pts) - 1 else X(i)
        d.append(("L" if k else "M") + f"{_c(x0)},{_c(Y(v))} L{_c(x1)},{_c(Y(v))}")
    return " ".join(d)


def _sub_chart(a: Analysis, ys, center, lcl, ucl, hits, title, unit, aria, zones=False, floor0=False) -> str:
    xs = a.xs
    W, H, left, right, top, bot = 760, 230, 43, 92, 18, 29
    vals = [v for v in ys if v is not None]
    lims = [v for v in (*lcl, *ucl) if v is not None]
    lo, hi = min(*vals, *lims), max(*vals, *lims)
    pad = (hi - lo) * 0.08 or 1
    lo, hi = lo - pad, hi + pad
    if floor0:
        lo = max(0.0, lo)          # a standard deviation can't be negative
    n = len(ys)
    X = lambda i: left + i * (W - left - right) / max(n - 1, 1)
    Y = lambda v: top + (hi - v) / (hi - lo) * (H - top - bot)
    parts = [f'<rect x="{left}" y="{top}" width="{_c(X(xs.baseline - 1) - left)}" height="{H - top - bot}" fill="#f1f6f3"/>']
    for k in range(5):
        v = lo + (hi - lo) * k / 4
        parts.append(f'<text x="4" y="{_c(Y(v) + 3)}">{fmt(v, 0 if hi - lo > 20 else 1)}</text>')
    if zones and xs.equal_n and xs.sigma > 0:
        se = xs.sigma / math.sqrt(xs.n[0])
        for k in (-2, -1, 1, 2):
            parts.append(f'<line x1="{left}" x2="{W - right}" y1="{_c(Y(xs.center + k * se))}" y2="{_c(Y(xs.center + k * se))}" '
                         f'stroke="{ZONE_LINE}" stroke-dasharray="2 4"/>')
        for lab, k in (("A", 2.5), ("B", 1.5), ("C", 0.5), ("C", -0.5), ("B", -1.5), ("A", -2.5)):
            parts.append(f'<text x="{W - right - 12}" y="{_c(Y(xs.center + k * se) + 3)}" class="zone">{lab}</text>')
    last = lambda seq: next((v for v in reversed(seq) if v is not None), None)
    for seq, name, col in ((ucl, "UCL", "#a1b4ac"), (center, "Mean" if title == "X̄" else "S̄", "#5b9685"), (lcl, "LCL", "#a1b4ac")):
        path = _stepped(X, Y, seq)
        if path:
            parts.append(f'<path d="{path}" fill="none" stroke="{col}" stroke-dasharray="5 5"/>'
                         f'<text x="{W - right + 8}" y="{_c(Y(last(seq)) + 3)}" style="fill:{col}">{name} {fmt(last(seq), 1)}</text>')
    pts = [(i, v) for i, v in enumerate(ys) if v is not None]
    parts.append('<path d="' + " ".join(("L" if k else "M") + f"{_c(X(i))},{_c(Y(v))}" for k, (i, v) in enumerate(pts))
                 + '" fill="none" stroke="#427e6d" stroke-width="1.6"/>')
    for i, v in pts:
        hit = i in hits
        rid = escape(str(a.records[i]["id"]))
        parts.append(f'<circle cx="{_c(X(i))}" cy="{_c(Y(v))}" r="{3.6 if hit else 2.6}" fill="{"#c66955" if hit else "#427e6d"}" '
                     f'onclick="fsBuild({i})"><title>{rid}: {title} {fmt(v, 1)} {unit} (n = {xs.n[i]})</title></circle>')
    for i in sorted({0, n // 4, n // 2, int(n * 0.75), n - 1}):
        parts.append(f'<text x="{_c(X(i) - 7)}" y="{H - 5}">{i + 1}</text>')
    return (f'<svg class="chart" viewBox="0 0 {W} {H}" role="img" aria-label="{aria}">' + "".join(parts) + "</svg>")


def xbar_chart(a: Analysis) -> str:
    """X̄ chart: mean strength of each build's coupons, centre x̿, limits x̿ ± 3σ̂/√n (stepped if n varies)."""
    xs = a.xs
    legend = ('<div class="legend"><span>Build mean (MPa)</span><span class="control">Control limits</span>'
              + ('<span class="zones">Zone lines (±1σ, ±2σ of the mean)</span>' if xs.equal_n else "") + "</div>")
    return legend + _sub_chart(a, xs.means, [xs.center] * len(xs.means), xs.x_lcl, xs.x_ucl, xs.x_hits, "X̄", "MPa",
                               "X-bar chart of mean strength per build", zones=True)


def s_chart(a: Analysis) -> str:
    """S chart: standard deviation of each build's coupons, centre c4·σ̂, limits B3/B4 equivalents."""
    xs = a.xs
    return _sub_chart(a, xs.sds, xs.s_center, xs.s_lcl, xs.s_ucl, xs.s_hits, "S", "MPa",
                      "S chart of within-build standard deviation", floor0=True)


def boxplot(x: list[float], desc: dict, label: str, idx: list[int] | None = None) -> str:
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
                     f'opacity=".85" onclick="fsBuild({idx[i] if idx else i})"><title>{fmt(v, 1)}</title></circle>')
    crowded = min(X(med) - X(q1), X(q3) - X(med)) < 75      # stagger labels that would overlap
    for v, name, y in ((q1, "Q1", 18 if crowded else 14), (med, "Median", 8 if crowded else 14),
                       (q3, "Q3", 18 if crowded else 14)):
        anchor = "end" if crowded and name == "Q1" else ("start" if crowded and name == "Q3" else "middle")
        parts.append(f'<text x="{_c(X(v))}" y="{y}" text-anchor="{anchor}">{name} {fmt(v, 1)}</text>')
    parts.append(f'<text x="{left}" y="{H - 4}">{fmt(lo, 0)}</text>'
                 f'<text x="{W / 2}" y="{H - 4}" text-anchor="middle">{escape(label)}</text>'
                 f'<text x="{W - right}" y="{H - 4}" text-anchor="end">{fmt(hi, 0)}</text>')
    return (f'<svg class="chart" viewBox="0 0 {W} {H}" role="img" aria-label="{escape(label)} box plot">'
            + "".join(parts) + "</svg>")


def scatter(a: Analysis, lsl: float, var: str = "oxygen") -> str:
    """Scatter of a process variable (x) against strength (y); rows missing `var` are skipped."""
    pts_in = [(i, r) for i, r in enumerate(a.records) if r.get(var) is not None]
    xs = [float(r[var]) for _, r in pts_in]
    ys = [float(r["strength"]) for _, r in pts_in]
    pad = (max(xs) - min(xs)) * 0.05 or 1
    lo, hi = min(xs) - pad, max(xs) + pad
    yl, yh = min(*ys, lsl) - 10, max(ys) + 10
    X = lambda x: 50 + (x - lo) / (hi - lo) * 650
    Y = lambda y: 230 - (y - yl) / (yh - yl) * 200
    label, unit = VARS[var]
    dec = 0 if hi - lo > 20 else 1
    grid = "".join(
        f'<line x1="50" x2="700" y1="{_c(Y(yl + (yh - yl) * i / 4))}" y2="{_c(Y(yl + (yh - yl) * i / 4))}" stroke="#e5ece7"/>'
        f'<text x="5" y="{_c(Y(yl + (yh - yl) * i / 4))}">{fmt(yl + (yh - yl) * i / 4, 0)}</text>'
        f'<text x="{_c(X(lo + (hi - lo) * i / 4))}" y="250" text-anchor="middle">{fmt(lo + (hi - lo) * i / 4, dec)}</text>'
        for i in range(5))
    pts = "".join(
        f'<circle cx="{_c(X(x))}" cy="{_c(Y(y))}" r="4" fill="{"#bd6c56" if a.is_fail(r) else "#628e7e"}" opacity=".8" '
        f'onclick="fsBuild({a.idx[i] if a.idx else i})"><title>{escape(str(r["id"]))} · {num(r[var])} {unit} · {num(r["strength"])} MPa</title></circle>'
        for (i, r), x, y in zip(pts_in, xs, ys))
    return (f'<svg class="chart" viewBox="0 0 760 280" role="img" aria-label="{escape(label)} and tensile strength scatterplot">'
            f'{grid}<line x1="50" x2="700" y1="{_c(Y(lsl))}" y2="{_c(Y(lsl))}" stroke="#bd6c56" stroke-dasharray="5 4"/>'
            f'{pts}<text x="375" y="275" text-anchor="middle">{escape(label)} ({unit})</text>'
            f'<text x="5" y="15">Strength (MPa)</text></svg>')
