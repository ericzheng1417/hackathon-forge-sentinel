"""HTML builders for each dashboard page.

Pure functions (no Shiny import) so they can be unit-tested. Interactive
elements call small JS helpers defined in app.py (fsGo, fsBuild, fsMachine,
fsMetric, fsAction, fsOpen), which forward events to the Shiny server.
"""
from __future__ import annotations

import math
from html import escape as esc

from . import charts
from .charts import fmt, num
from .engine import SPECIAL_TESTS, VARS, Analysis, associations, available_vars, decision_text, wilson

PAGES = ["Overview", "Process control", "Statistics", "Capability", "Parameter analysis", "Build records",
         "Corrective actions", "Methods"]
ICONS = ["▦", "⌁", "Σ", "◫", "⤢", "☷", "✓", "⚙"]
TAGLINES = {
    "Overview": "Know your process. Build with confidence.",
    "Process control": "Detect special causes before they become recurring failures.",
    "Statistics": "Describe the centre, spread and shape of every measured variable.",
    "Capability": "Separate observed performance from demonstrated capability.",
    "Parameter analysis": "Connect environmental conditions with final part strength.",
    "Build records": "One ordered build, one representative tensile result.",
    "Corrective actions": "Turn signals into documented investigations.",
    "Methods": "Transparent calculations. Explicit engineering assumptions.",
}
STATUSES = ["Open", "Investigating", "Awaiting verification", "Closed"]
TASKS = [
    ("contain", "Contain affected production",
     "Segregate builds with failed tests or unresolved special-cause signals. Trace the affected time window and "
     "retain records for engineering disposition.", "Quality lead"),
    ("gas", "Investigate chamber atmosphere",
     "Check oxygen-sensor calibration, purge logs, seals and shielding-gas flow. Compare excursion timing to layer "
     "data; do not infer cause from correlation alone.", "Process engineer"),
    ("material", "Inspect material and thermal history",
     "Review powder chemistry/reuse, porosity and fracture surfaces. Verify heat treatment and residual-stress "
     "measurements against the approved route.", "Materials engineer"),
    ("validate", "Verify corrective action",
     "Plan controlled trials, verify the measurement system, then collect a new representative baseline. Reassess "
     "stability and capability before client review.", "Quality engineer"),
]


def js(s: str) -> str:
    """Quote a Python string as a JS string literal safe inside an HTML attribute."""
    return esc("'" + s.replace("\\", "\\\\").replace("'", "\\'") + "'")


# -- chrome ---------------------------------------------------------------

def nav(page: str) -> str:
    return "".join(f'<button class="{"active" if p == page else ""}" onclick="fsGo({js(p)})"><i>{ICONS[i]}</i>{p}</button>'
                   for i, p in enumerate(PAGES))


def heading(page: str) -> str:
    title = "Process overview" if page == "Overview" else page
    return (f'<div class="heading"><div><div class="eyebrow">PROCESS ASSURANCE / TITANIUM BRACKETS</div>'
            f'<h1>{title}</h1><p>{TAGLINES[page]}</p></div><div class="actions">'
            f'<button onclick="fsOpen(\'import\')">↥ &nbsp; Import data</button>'
            f'<a id="export_report" class="shiny-download-link primary" href="" target="_blank" download>↓ &nbsp; Export report</a>'
            f'</div></div>')


def tests_label(a: Analysis, mr_rule: bool) -> str:
    t = list(a.tests)
    if t == list(range(1, 9)):
        lab = "Tests 1–8"
    elif t:
        lab = "Tests " + ", ".join(map(str, t))
    else:
        lab = "No pattern tests"
    return lab + (" + MR" if mr_rule else "")


def filters(machines: list[str], machine: str, a: Analysis, mr_rule: bool = True) -> str:
    opts = "".join(f'<option value="{esc(m)}" {"selected" if m == machine else ""}>{esc(m)}</option>' for m in machines)
    return (f'<div class="filters"><label>Machine <select aria-label="Machine" onchange="fsMachine(this.value)">{opts}'
            f'</select></label><span>Ti-6Al-4V &nbsp; <span class="tag">Bracket family A</span></span>'
            f'<span class="right">{a.n} sequential builds · Baseline: first {a.baseline} · {tests_label(a, mr_rule)}</span>'
            f'<button class="link" onclick="fsOpen(\'config\')">Configure ↗</button></div>')


# -- shared pieces ----------------------------------------------------------

def spec_text(a: Analysis) -> str:
    return (f"outside the {num(a.lsl)}–{num(a.usl)} MPa specification" if a.usl is not None
            else f"below the {num(a.lsl)} MPa minimum")


def banner(a: Analysis) -> str:
    return (f'<div class="fs-alert"><span class="symbol">△</span><div><strong>{decision_text(a)}</strong>'
            f'<p>{len(a.post)} monitored builds with SPC signals · {len(a.fails)} {spec_text(a)}. '
            f'{"Baseline has signals; review before use." if a.baseflags else "Limits are frozen from the baseline."}'
            f'</p></div><button onclick="fsGo(\'Corrective actions\')">Review actions ↗</button></div>')


def metric_card(label, value, note, badge="", cls="") -> str:
    pill = f'<span class="pill {cls}">{badge}</span>' if badge else ""
    return (f'<div class="fs-card metric"><div class="label">{label}</div>{pill}<div class="value">{value}</div>'
            f'<div class="note">{note}</div></div>')


def table(rows: list[dict], a: Analysis) -> str:
    index = {id(r): i for i, r in enumerate(a.records)}
    body = "".join(
        f'<tr><td><strong>{esc(str(r["id"]))}</strong></td><td>{num(r["strength"])} <span style="color:#96a19c">MPa</span></td>'
        f'<td>{num(r["oxygen"])}</td><td>{num(r["stress"])}</td><td><span class="pill {"red" if a.is_fail(r) else ""}">'
        f'{"FAIL" if a.is_fail(r) else "PASS"}</span></td><td><button class="link" onclick="fsBuild({index[id(r)]})" '
        f'aria-label="View build {esc(str(r["id"]))}">↗</button></td></tr>' for r in rows)
    return ('<div class="tablewrap"><table><thead><tr><th>BUILD ID</th><th>STRENGTH</th><th>O₂ / ppm</th>'
            f'<th>STRESS / MPa</th><th>TEST RESULT</th><th></th></tr></thead><tbody>{body}</tbody></table></div>')


def _bar_width(r: float) -> float:
    return abs(r) * 100 if math.isfinite(r) else 0


NO_PROCESS_DATA = ('<div class="empty" style="padding:24px">Only strength was provided. Add process columns '
                   '(oxygen, humidity, temperature, power, speed, stress) to see which conditions move with strength.</div>')


def drivers(a: Analysis) -> str:
    if not associations(a.records):
        return NO_PROCESS_DATA
    return "".join(
        f'<div class="driver"><div class="driverhead">{VARS[d["v"]][0]}<span>r = {fmt(d["r"])}</span></div>'
        f'<div class="bar"><div style="width:{_bar_width(d["r"]):.1f}%"></div></div></div>'
        for d in associations(a.records)[:4])


# -- pages ----------------------------------------------------------------

def overview(a: Analysis, cfg: dict) -> str:
    pass_pct = 100 * a.passes / a.n
    cap_note = (f"Ppk {fmt(a.cap['Ppk'])} (overall spread) · target ≥ {num(cfg['target'])}"
                + ("" if a.usl is not None else " · one-sided"))
    metrics = (
        metric_card("Observed pass rate", fmt(pass_pct, 1) + "<small> %</small>",
                    f"{a.passes} of {a.n} strength results pass", "Measured")
        + metric_card("Process capability · Cpk", fmt(a.cpk), cap_note,
                      "Estimate" if a.stable else "Provisional", "" if a.stable else "amber")
        + metric_card("Mean tensile strength", fmt(a.avg, 0) + "<small> MPa</small>",
                      f"Median {fmt(a.desc['median'], 0)} · SD {fmt(a.desc['sd'], 1)} · CV {fmt(a.desc['cv_pct'], 1)}%")
        + metric_card("SPC alerts", len(a.post), "Monitored builds after baseline", "Review", "red"))
    recent = list(reversed(a.records[-5:]))
    usl_row = (f'<div class="keyline"><span>Specification</span><strong>{num(a.lsl)} – {num(a.usl)} MPa</strong></div>'
               if a.usl is not None else f'<div class="keyline"><span>Lower spec limit</span><strong>{num(a.lsl)} MPa</strong></div>')
    return (banner(a) + f'<div class="metrics">{metrics}</div>'
            '<div class="grid"><section class="fs-card"><div class="cardhead"><div><h2>Strength stability</h2>'
            '<p>Individuals chart · sequential build order</p></div><button onclick="fsGo(\'Process control\')">Explore chart ↗</button></div>'
            f'{charts.control_chart(a, a.lsl, a.usl)}<div class="chartnote"><span>Baseline builds 1–{a.baseline} · 3σ control limits</span>'
            f'<strong>{"No signals detected" if a.stable else "Special-cause signals detected"}</strong></div></section>'
            '<section class="fs-card"><div class="cardhead"><div><h2>Capability snapshot</h2><p>Tensile strength against specification</p></div>'
            f'<span class="pill amber">{"REVIEW" if a.stable else "UNSTABLE"}</span></div>'
            f'{charts.histogram(a.x, "Strength (MPa)", a.lsl, a.usl)}{usl_row}'
            f'<div class="keyline"><span>Cp / Cpk</span><strong>{fmt(a.cap["Cp"])} / {fmt(a.cap["Cpk"])}</strong></div>'
            f'<div class="keyline"><span>Pp / Ppk</span><strong>{fmt(a.cap["Pp"])} / {fmt(a.cap["Ppk"])}</strong></div>'
            f'<div class="keyline"><span>Within / overall σ</span><strong>{fmt(a.sigma, 1)} / {fmt(a.overall_sd, 1)} MPa</strong></div>'
            '</section></div><div class="grid"><section class="fs-card"><div class="sectionhead"><h2>Recent builds</h2>'
            f'<button onclick="fsGo(\'Build records\')">View all builds ↗</button></div>{table(recent, a)}</section>'
            '<section class="fs-card"><div class="sectionhead"><h2>Strength associations</h2>'
            f'<button onclick="fsGo(\'Parameter analysis\')">Explore ↗</button></div>{drivers(a)}'
            '<p>Correlation is exploratory, not proof of cause.</p></section></div>')


def variable_select(v: str, avail: list[str] | None = None) -> str:
    keys = avail or list(VARS)
    opts = "".join(f'<option value="{k}" {"selected" if k == v else ""}>{VARS[k][0]}</option>' for k in keys)
    return f'<select aria-label="Variable" onchange="fsMetric(this.value)">{opts}</select>'


def tests_reference(am: Analysis, mr_rule: bool) -> str:
    counts = am.test_counts()

    def cell(key, enabled):
        if not enabled:
            return "Off"
        k = counts.get(key, 0)
        return f'<span class="pill red">{k}</span>' if k else "0"

    rows = "".join(
        f'<tr class="{"" if t in am.tests else "off"}"><td><strong>Test {t}</strong></td><td>{pat}</td><td>{sig}</td>'
        f'<td>{cell(t, t in am.tests)}</td></tr>'
        for t, (_, pat, sig) in SPECIAL_TESTS.items())
    rows += (f'<tr class="{"" if mr_rule else "off"}"><td><strong>MR</strong></td><td>One moving range above the MR-chart '
             f'UCL (3.267 × MR̄)</td><td>A sudden jump between consecutive builds</td><td>{cell("MR", mr_rule)}</td></tr>')
    return ('<div class="tablewrap"><table class="tests"><thead><tr><th>TEST</th><th>PATTERN TO LOOK FOR</th>'
            f'<th>WHAT IT USUALLY SIGNALS</th><th>POINTS FLAGGED</th></tr></thead><tbody>{rows}</tbody></table></div>')


def missing_note(am: Analysis) -> str:
    return (f' {am.n_missing} build(s) without a recorded {VARS[am.metric][0].lower()} are skipped.'
            if am.n_missing else "")


def control(am: Analysis, cfg: dict, avail: list[str] | None = None) -> str:
    v = am.metric
    unit = VARS[v][1]
    if am.flags:
        rows = "".join(
            f'<tr><td><button class="link" onclick="fsBuild({am.idx[f.index]})">{esc(str(am.records[f.index]["id"]))}</button></td>'
            f'<td>{"Baseline review" if f.index < am.baseline else "Monitoring"}</td>'
            f'<td>{num(am.records[f.index][v])} {unit}</td><td>{" · ".join(f.reasons)}</td></tr>'
            for f in reversed(am.flags))
        log = f'<table><thead><tr><th>BUILD</th><th>PHASE</th><th>VALUE</th><th>SIGNAL</th></tr></thead><tbody>{rows}</tbody></table>'
    else:
        log = '<div class="empty">No signals under the selected tests.</div>'
    sig = am.sigma
    return ('<div class="fs-card"><div class="cardhead"><div><h2>Individuals (I) chart</h2>'
            '<p>Baseline and chronological order are preserved for the selected machine. Zones A, B and C are marked on the right.</p></div>'
            f'{variable_select(v, avail)}</div>{charts.control_chart(am, cfg["lsl"], am.usl)}'
            f'<div class="statsrow"><div><span>CENTRE (BASELINE MEAN)</span><strong>{fmt(am.center, 1)}</strong></div>'
            f'<div><span>BASELINE σ (MR̄ / 1.128)</span><strong>{fmt(sig, 2)}</strong></div>'
            f'<div><span>LCL / UCL</span><strong>{fmt(am.lcl, 1)} / {fmt(am.ucl, 1)}</strong></div>'
            f'<div><span>MONITORING SIGNALS</span><strong>{len(am.post)}</strong></div></div>'
            f'<p>Zone C: within ±1σ ({fmt(am.center - sig, 1)}–{fmt(am.center + sig, 1)}) · Zone B: 1–2σ · '
            f'Zone A: 2–3σ ({fmt(am.center - 3 * sig, 1)}–{fmt(am.center + 3 * sig, 1)}). Limits are frozen from the first '
            f'{am.baseline} builds (shaded). Click a point for build detail.{missing_note(am)}</p></div>'
            '<div class="fs-card" style="margin-top:20px"><div class="cardhead"><div><h2>Moving range (MR) chart</h2>'
            '<p>Absolute difference between consecutive builds · |xᵢ − xᵢ₋₁|</p></div></div>'
            f'{charts.mr_chart(am)}<div class="statsrow"><div><span>MR̄ (BASELINE)</span><strong>{fmt(am.mr_bar, 2)}</strong></div>'
            f'<div><span>MR UCL (3.267 × MR̄)</span><strong>{fmt(am.mr_ucl, 1)}</strong></div>'
            f'<div><span>MR LCL</span><strong>0</strong></div></div></div>'
            '<div class="fs-card" style="margin-top:20px"><div class="cardhead"><div><h2>The 8 tests for special causes</h2>'
            '<p>Western Electric / Nelson rules applied to the I chart. Tests 2 and 3 count only points on one side of '
            'the centreline. Turn tests on or off in Configure.</p></div></div>'
            f'{tests_reference(am, cfg.get("mr_rule", True))}</div>'
            f'<div class="fs-card" style="margin-top:20px"><h2>Signal log</h2>{log}</div>')


STAT_ROWS = [  # key, label, short column header, decimals, suffix
    ("n", "Count (n)", "N", 0, ""), ("mean", "Mean", "MEAN", 2, ""), ("median", "Median", "MEDIAN", 2, ""),
    ("sd", "Standard deviation (s)", "SD", 2, ""), ("variance", "Variance (s²)", "VAR", 2, ""),
    ("cv_pct", "Coefficient of variation", "CV", 2, "%"), ("se_mean", "Standard error of mean", "SE MEAN", 3, ""),
    ("min", "Minimum", "MIN", 1, ""), ("q1", "Q1 (25th percentile)", "Q1", 2, ""), ("q3", "Q3 (75th percentile)", "Q3", 2, ""),
    ("max", "Maximum", "MAX", 1, ""), ("range", "Range (max − min)", "RANGE", 1, ""),
    ("iqr", "Interquartile range (Q3 − Q1)", "IQR", 2, ""),
]


def statistics_page(am: Analysis, all_desc: dict, avail: list[str] | None = None) -> str:
    v = am.metric
    label, unit = VARS[v]
    d = am.desc
    u = f"<small> {unit}</small>"
    cards1 = (metric_card("Mean", fmt(d["mean"], 2) + u, f"Median {fmt(d['median'], 2)} {unit}")
              + metric_card("Standard deviation", fmt(d["sd"], 2) + u, f"Variance {fmt(d['variance'], 2)} {unit}²")
              + metric_card("Coefficient of variation", fmt(d["cv_pct"], 2) + "<small> %</small>", "SD ÷ mean × 100")
              + metric_card("Standard error", fmt(d["se_mean"], 3) + u, f"SD ÷ √n · n = {d['n']}"))
    cards2 = (metric_card("Range", fmt(d["range"], 1) + u, f"{fmt(d['min'], 1)} to {fmt(d['max'], 1)}")
              + metric_card("Interquartile range", fmt(d["iqr"], 2) + u, f"Q1 {fmt(d['q1'], 2)} · Q3 {fmt(d['q3'], 2)}")
              + metric_card("Baseline σ (within)", fmt(am.sigma, 2) + u, "MR̄ ÷ 1.128 · short-term spread")
              + metric_card("Overall σ", fmt(d["sd"], 2) + u, f"Ratio overall / within {fmt(d['sd'] / am.sigma if am.sigma else float('nan'), 2)}"))
    detail = "".join(f'<div class="keyline"><span>{lab}</span><strong>{fmt(d[k], dec)}{suf}{"" if k in ("n", "cv_pct") else " " + unit}</strong></div>'
                     for k, lab, _, dec, suf in STAT_ROWS)
    head = "<th>VARIABLE</th>" + "".join(f'<th title="{lab}">{short}</th>' for _, lab, short, _, _ in STAT_ROWS)
    body = "".join(
        f'<tr class="{"sel" if k == v else ""}"><td><button class="link" onclick="fsMetric({js(k)})">{VARS[k][0]}</button>'
        f' <span style="color:#96a19c">{VARS[k][1]}</span></td>'
        + "".join(f"<td>{fmt(all_desc[k][s], dec)}{suf}</td>" for s, _, _, dec, suf in STAT_ROWS) + "</tr>"
        for k in VARS if k in all_desc)
    return ('<div class="fs-card" style="margin-bottom:20px"><div class="cardhead"><div><h2>Descriptive statistics</h2>'
            f'<p>{label} · {am.n} builds · selected machine · sample statistics (n − 1).{missing_note(am)}</p></div>'
            f'{variable_select(v, avail)}</div></div>'
            f'<div class="metrics">{cards1}</div><div class="metrics">{cards2}</div>'
            f'<div class="grid"><section class="fs-card"><h2>Spread and shape</h2><p>Box = Q1 to Q3, line = median, '
            f'◆ = mean, whiskers = 1.5 × IQR; red points fall outside the whiskers.</p>{charts.boxplot(am.x, d, f"{label} ({unit})", am.idx)}'
            f'<h3>Distribution</h3>{charts.histogram(am.x, f"{label} ({unit})", bins=24, width=760)}</section>'
            f'<section class="fs-card"><h2>Summary · {label}</h2>{detail}</section></div>'
            '<div class="fs-card"><h2>All variables</h2><p>Click a variable to inspect it above. SD = standard deviation, VAR = variance, '
            'CV = coefficient of variation, SE MEAN = standard error of the mean, IQR = interquartile range. Quartiles use the '
            'inclusive method (Excel QUARTILE.INC).</p>'
            f'<div class="tablewrap"><table class="stats"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div></div>')


def capability(a: Analysis, cfg: dict) -> str:
    p, lo, hi = wilson(a.passes, a.n)
    t = num(cfg["target"])
    c = a.cap
    yn = lambda b: "Yes" if b else "No"
    two = a.usl is not None
    spec = f"{num(a.lsl)} – {num(a.usl)} MPa" if two else f"≥ {num(a.lsl)} MPa (one-sided)"
    need_usl = "Set an upper spec (USL) in Configure"
    row1 = (metric_card("Cp · potential", fmt(c["Cp"]), "(USL − LSL) / 6σ within" if two else need_usl)
            + metric_card("Cpk · actual", fmt(c["Cpk"]), f"min(Cpl, Cpu) · target ≥ {t}",
                          "Meets target" if c["Cpk"] >= cfg["target"] else "Below target",
                          "" if c["Cpk"] >= cfg["target"] else "red")
            + metric_card("Pp · overall potential", fmt(c["Pp"]), "(USL − LSL) / 6s overall" if two else need_usl)
            + metric_card("Ppk · overall actual", fmt(c["Ppk"]), "min(Ppl, Ppu) · overall s"))
    row2 = (metric_card("Cpl / Cpu", f"{fmt(c['Cpl'])}<small> / {fmt(c['Cpu'])}</small>", "(mean − LSL) / 3σ · (USL − mean) / 3σ")
            + metric_card("Centering · Cpk ÷ Cp", fmt(c["Cpk"] / c["Cp"] if two and c["Cp"] else float("nan")),
                          "1.00 = centred between limits" if two else need_usl)
            + metric_card("Observed conformance", fmt(p * 100, 1) + "<small>%</small>", f"{a.passes} in spec / {a.n} tests")
            + metric_card("95% Wilson interval", fmt(lo * 100, 1) + "<small>–" + fmt(hi * 100, 1) + "%</small>",
                          "Binomial interval; independent builds assumed"))
    return (banner(a) + f'<div class="metrics">{row1}</div><div class="metrics">{row2}</div>'
            '<div class="grid"><div class="fs-card"><h2>Strength distribution against specification</h2>'
            f'{charts.histogram(a.x, "Strength (MPa)", a.lsl, a.usl, bins=36, width=760)}'
            f'<div class="keyline"><span>Specification</span><strong>{spec}</strong></div>'
            f'<div class="keyline"><span>Mean / within σ / overall s</span><strong>{fmt(a.avg, 1)} / {fmt(a.sigma, 2)} / {fmt(a.overall_sd, 2)} MPa</strong></div>'
            '<p>Cp and Pp measure potential (spread only); Cpk and Ppk also account for where the process is centred. '
            'Cp/Cpk use within (short-term) σ = MR̄ ÷ 1.128 from the baseline; Pp/Ppk use the overall sample standard '
            f'deviation. The {t} target and the default limits are configurable demonstration values, not aerospace '
            'requirements.</p></div><div class="fs-card"><h2>Evidence checklist</h2>'
            f'<div class="keyline"><span>Baseline free of selected signals</span><b>{yn(not a.baseflags)}</b></div>'
            f'<div class="keyline"><span>Monitoring free of selected signals</span><b>{yn(not a.post)}</b></div>'
            f'<div class="keyline"><span>Cpk ≥ {t}</span><b>{yn(c["Cpk"] >= cfg["target"])}</b></div>'
            f'<div class="keyline"><span>Ppk ≥ {t}</span><b>{yn(c["Ppk"] >= cfg["target"])}</b></div>'
            '<div class="keyline"><span>Measurement system / normality</span><b>Not validated</b></div>'
            '<p>Capability indices are only meaningful for a stable process. Passing these numerical screens alone does '
            'not establish capability. Verify representative sampling, independence, measurement uncertainty and '
            'distribution fit with the client.</p></div></div>'
            '<div class="fs-card"><h2>Reliability interpretation</h2><p>The pass-rate interval quantifies uncertainty in '
            'observed strength-test conformance only. It does not estimate in-service fatigue life, survival probability '
            'at mission loads, or bracket structural reliability. Those require load spectra, geometry, material allowables '
            'and fatigue or life-test data, including censored results.</p></div>')

def parameters(a: Analysis, cfg: dict) -> str:
    assoc = associations(a.records)
    if assoc:
        bars = "".join(
            f'<div class="driver"><div class="driverhead">{VARS[d["v"]][0]}<strong>{fmt(d["r"])}</strong></div>'
            f'<div class="bar"><div style="width:{_bar_width(d["r"]):.1f}%;background:{"#bf8b78" if d["r"] < 0 else "#6f9d8a"}"></div></div></div>'
            for d in assoc)
    else:
        bars = NO_PROCESS_DATA
    excursions = ""
    for var, key, unit in (("oxygen", "oxygen", " ppm"), ("humidity", "humidity", "%")):
        vals = [r[var] for r in a.records if r.get(var) is not None]
        label = VARS[var][0].split()[-1].capitalize()
        excursions += (f'<div class="keyline"><span>{label} &gt; {num(cfg[key])}{unit}</span>'
                       f'<strong>{sum(v > cfg[key] for v in vals)} builds</strong></div>' if vals else
                       f'<div class="keyline"><span>{label} &gt; {num(cfg[key])}{unit}</span><strong>Not recorded</strong></div>')
    if assoc:
        top = assoc[0]["v"]
        scatter = (f'<div class="fs-card"><h2>{VARS[top][0]} versus tensile strength</h2>'
                   f'<p>Strongest association in this stream (r = {fmt(assoc[0]["r"])}).</p>{charts.scatter(a, a.lsl, top)}'
                   '<p>Each point is one matched build and test record. Red points fail the strength specification. '
                   'Click a point for build detail.</p></div>')
    else:
        scatter = ""
    return ('<div class="grid"><div class="fs-card"><h2>Associations with tensile strength</h2>'
            f'<p>Pearson correlation · {a.n} builds · selected machine · pairwise-complete records</p>{bars}'
            '<p>Common time trends and confounding can create strong correlations. Use controlled trials and '
            'metallurgical evidence to test a suspected mechanism.</p></div><div class="fs-card"><h2>Environmental excursions</h2>'
            f'{excursions}'
            '<p>Thresholds are illustrative engineering alarms, editable in Configure. Recorded values represent one '
            'build-level summary; layer-level peaks and exposure duration are not captured.</p>'
            '<h3>Recommended traceability additions</h3><p>Powder lot and reuse count · particle size / chemistry · gas flow · '
            'melt-pool intensity · layer thickness · build orientation and location · heat-treatment/HIP cycle · surface '
            'finish · porosity · test specimen and instrument ID.</p>'
            '<button onclick="fsGo(\'Corrective actions\')">Open investigation workspace ↗</button></div></div>'
            + scatter)


def records(a: Analysis) -> str:
    return ('<div class="fs-card"><div class="sectionhead"><h2>Build &amp; test traceability</h2>'
            '<a id="download_csv" class="shiny-download-link dl link" href="" target="_blank" download>Download CSV ↓</a></div>'
            f'<p>File order defines acquisition order within each machine. All {a.n} records shown, newest first.</p>'
            f'{table(list(reversed(a.records)), a)}</div>')


def tasks(a: Analysis, actions: dict) -> str:
    items = []
    for i, (tid, title, desc, owner) in enumerate(TASKS):
        cur = actions.get(tid, {})
        opts = "".join(f'<option {"selected" if cur.get("status") == s else ""}>{s}</option>' for s in STATUSES)
        items.append(
            f'<div class="task"><div class="tasktop"><h3><span style="color:#98aaa1">0{i + 1} &nbsp;</span>{title}</h3>'
            f'<select aria-label="{title} status" onchange="fsAction({js(tid)},\'status\',this.value)">{opts}</select></div>'
            f'<p>{desc}</p><label>Suggested owner: {owner}<input aria-label="{title} investigation note" '
            f'placeholder="Record evidence, owner and next step…" value="{esc(cur.get("note", ""))}" '
            f'onchange="fsAction({js(tid)},\'note\',this.value)"></label>'
            + (f'<p style="font-size:10px;margin:-8px 0 0">Last updated {esc(cur["updated"])}</p>' if cur.get("updated") else "")
            + '</div>')
    return (banner(a) + '<div class="fs-card"><h2>Investigation &amp; corrective-action register</h2>'
            '<p>Suggested failure-analysis workflow. Status and notes are saved on the Shiny server '
            '(<code>data/actions.json</code>) and shared by everyone using this app instance; this is not an auditable '
            'quality-management system.</p>' + "".join(items) + "</div>")



def methods() -> str:
    tests = "".join(f"<li><b>Test {t}</b> — {pat}. <i>{sig}.</i></li>" for t, (_, pat, sig) in SPECIAL_TESTS.items())
    return ('<div class="fs-card method"><h2>How this workspace makes a decision</h2>'
            '<h3>1. Preserve a comparable process stream</h3><p>Analyze one machine and one consistent part / material / '
            'process route at a time. Demo data contains 60 builds per machine with one representative destructive tensile '
            'result per build. LPBF-01 includes synthetic late-run deterioration; LPBF-02 is a comparison stream. All values '
            'and limits are illustrative, not Ti-6Al-4V design allowables.</p>'
            '<h3>2. Describe the data</h3><p>Mean x̄ = Σx / n; median = middle ordered value; sample variance s² = Σ(x − x̄)² / (n − 1); '
            'standard deviation s = √s²; coefficient of variation CV = s / x̄ × 100%; standard error of the mean SE = s / √n; '
            'range = max − min; quartiles Q1/Q3 by the inclusive method (Excel QUARTILE.INC); IQR = Q3 − Q1. Box-plot whiskers '
            'reach the furthest points within 1.5 × IQR of the box.</p>'
            '<h3>3. Establish a fixed baseline (I-MR chart)</h3><p>The first N ordered builds estimate the centre line and '
            'within-process variation. Moving range MRᵢ = |xᵢ − xᵢ₋₁|; σ = MR̄ / 1.128 (d₂ for n = 2). Individuals limits are '
            'x̄ ± 3σ. MR-chart limits are 0 and 3.267 × MR̄ (D₄). Zones: C within ±1σ, B between 1σ and 2σ, A between 2σ and '
            '3σ. Limits stay frozen from the baseline, and baseline points are tested too: a baseline containing signals needs '
            'investigation before it can support monitoring.</p>'
            f'<h3>4. Test for special causes</h3><p>The I chart is checked with the 8 standard tests (Western Electric / '
            f'Nelson rules). A point is flagged when it completes the pattern. For tests 2 and 3 the flagged point must itself '
            f'be beyond the zone, on the same side. Test 7 requires points on both sides of the centre line. Optionally, a '
            f'moving range above the MR UCL is also flagged. Tests can be turned on or off in Configure; using more tests raises '
            f'the false-alarm rate.</p><ul>{tests}</ul>'
            '<p>A signal is an investigation trigger, not a diagnosis.</p>'
            '<h3>5. Assess capability</h3><p>Cp = (USL − LSL) / 6σ; Cpl = (x̄ − LSL) / 3σ; Cpu = (USL − x̄) / 3σ; '
            'Cpk = min(Cpl, Cpu), using within σ from the baseline. Pp, Ppl, Ppu and Ppk use the same formulas with the overall '
            'sample standard deviation s. If no upper limit is set, Cp and Pp are not defined and Cpk = Cpl. Indices assume a '
            'stable, approximately normal process; on an unstable stream they are descriptive, provisional numbers, not '
            'future-performance claims.</p>'
            '<h3>6. Keep uncertainty visible</h3><p>The 95% Wilson interval uses independent pass/fail outcomes. Repeated '
            'coupons from one build are not independent builds. This prototype does not validate normality, measurement '
            'uncertainty, fatigue life or statistical power, and it does not predict defect PPM or certify release.</p>'
            '<h3>7. Close the evidence gap</h3><p>Production integration should retain timestamps, sensor calibration, units, '
            'part and powder genealogy, layer-level sensor histories, process revisions, test methods, heat-treatment records, '
            'and user audit trails. Real-time ingestion is not connected. Imported CSVs are held in the server session memory '
            'only; corrective-action notes are saved to the server. Export before closing.</p>'
            '<h3>Run and extend the tool</h3><p><a id="download_source" class="shiny-download-link" href="" target="_blank" '
            'download>Download Shiny app + Python analysis source ↓</a>. Run with <code>shiny run app.py</code>, or analyze '
            'exported CSVs offline with <code>python/analyze.py</code> — both share <code>forge_sentinel/engine.py</code>.</p>'
            '<h3>Statistical references</h3><p><a href="https://www.itl.nist.gov/div898/handbook/pmc/section3/pmc322.htm" '
            'target="_blank" rel="noopener">NIST — Individuals control charts ↗</a><br>'
            '<a href="https://www.itl.nist.gov/div898/handbook/pmc/section1/pmc16.htm" target="_blank" rel="noopener">'
            'NIST — Process capability ↗</a><br>'
            '<a href="https://www.itl.nist.gov/div898/handbook/pmc/section3/pmc32.htm" target="_blank" rel="noopener">'
            'NIST — What are control charts? (run rules) ↗</a></p></div>')


def build_detail(a: Analysis, i: int) -> str:
    r = a.records[i]
    lines = "".join(f'<div class="keyline"><span>{lab}</span><strong>{num(r[k])} {u}</strong></div>'
                    for k, (lab, u) in VARS.items())
    sig = " · ".join(a.flagged.get(i, [])) or "No strength SPC signals."
    return (f'<h2>Build {esc(str(r["id"]))}</h2><p>{esc(str(r["machine"]))} · Sequence {i + 1} · '
            f'{"Baseline" if i < a.baseline else "Monitoring"}</p>{lines}'
            f'<p>Strength result: <strong>{"FAIL" if a.is_fail(r) else "PASS"}</strong>. {sig} '
            'A passing test does not override an unresolved process signal.</p>')


def render_page(page: str, a: Analysis, am: Analysis, cfg: dict, actions: dict, all_desc: dict | None = None) -> str:
    """HTML for one page. `a` = strength analysis of the full stream; `am` = analysis of the
    variable selected on Process control / Statistics; `all_desc` = describe() per variable."""
    avail = available_vars(a.records)
    if page == "Overview":
        return overview(a, cfg)
    if page == "Process control":
        return control(am, cfg, avail)
    if page == "Statistics":
        return statistics_page(am, all_desc or {}, avail)
    if page == "Capability":
        return capability(a, cfg)
    if page == "Parameter analysis":
        return parameters(a, cfg)
    if page == "Build records":
        return records(a)
    if page == "Corrective actions":
        return tasks(a, actions)
    return methods()
