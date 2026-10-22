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
from .engine import VARS, Analysis, associations, decision_text, wilson

PAGES = ["Overview", "Process control", "Capability", "Parameter analysis", "Build records",
         "Corrective actions", "Methods"]
ICONS = ["▦", "⌁", "◫", "⤢", "☷", "✓", "⚙"]
TAGLINES = {
    "Overview": "Know your process. Build with confidence.",
    "Process control": "Detect special causes before they become recurring failures.",
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


def filters(machines: list[str], machine: str, a: Analysis) -> str:
    opts = "".join(f'<option value="{esc(m)}" {"selected" if m == machine else ""}>{esc(m)}</option>' for m in machines)
    return (f'<div class="filters"><label>Machine <select aria-label="Machine" onchange="fsMachine(this.value)">{opts}'
            f'</select></label><span>Ti-6Al-4V &nbsp; <span class="tag">Bracket family A</span></span>'
            f'<span class="right">{a.n} sequential builds · Baseline: first {a.baseline}</span>'
            f'<button class="link" onclick="fsOpen(\'config\')">Configure ↗</button></div>')


# -- shared pieces ----------------------------------------------------------

def banner(a: Analysis) -> str:
    return (f'<div class="fs-alert"><span class="symbol">△</span><div><strong>{decision_text(a)}</strong>'
            f'<p>{len(a.post)} monitored builds with SPC signals · {len(a.fails)} below the {num(a.lsl)} MPa minimum. '
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
        f'<td>{num(r["oxygen"])}</td><td>{num(r["stress"])}</td><td><span class="pill {"red" if r["strength"] < a.lsl else ""}">'
        f'{"FAIL" if r["strength"] < a.lsl else "PASS"}</span></td><td><button class="link" onclick="fsBuild({index[id(r)]})" '
        f'aria-label="View build {esc(str(r["id"]))}">↗</button></td></tr>' for r in rows)
    return ('<div class="tablewrap"><table><thead><tr><th>BUILD ID</th><th>STRENGTH</th><th>O₂ / ppm</th>'
            f'<th>STRESS / MPa</th><th>TEST RESULT</th><th></th></tr></thead><tbody>{body}</tbody></table></div>')


def _bar_width(r: float) -> float:
    return abs(r) * 100 if math.isfinite(r) else 0


def drivers(a: Analysis) -> str:
    return "".join(
        f'<div class="driver"><div class="driverhead">{VARS[d["v"]][0]}<span>r = {fmt(d["r"])}</span></div>'
        f'<div class="bar"><div style="width:{_bar_width(d["r"]):.1f}%"></div></div></div>'
        for d in associations(a.records)[:4])


# -- pages ----------------------------------------------------------------

def overview(a: Analysis, cfg: dict) -> str:
    pass_pct = 100 * a.passes / a.n
    metrics = (
        metric_card("Observed pass rate", fmt(pass_pct, 1) + "<small> %</small>",
                    f"{a.passes} of {a.n} strength results pass", "Measured")
        + metric_card("Lower capability · Cpl", fmt(a.cpl), f"Target ≥ {num(cfg['target'])} · baseline σ",
                      "Estimate" if a.stable else "Provisional", "" if a.stable else "amber")
        + metric_card("Mean tensile strength", fmt(a.avg, 0) + "<small> MPa</small>",
                      f"Minimum specification: {num(cfg['lsl'])} MPa")
        + metric_card("SPC alerts", len(a.post), "Monitored builds after baseline", "Review", "red"))
    recent = list(reversed(a.records[-5:]))
    return (banner(a) + f'<div class="metrics">{metrics}</div>'
            '<div class="grid"><section class="fs-card"><div class="cardhead"><div><h2>Strength stability</h2>'
            '<p>Individuals chart · sequential build order</p></div><button onclick="fsGo(\'Process control\')">Explore chart ↗</button></div>'
            f'{charts.control_chart(a, cfg["lsl"])}<div class="chartnote"><span>Baseline builds 1–{a.baseline} · 3σ control limits</span>'
            f'<strong>{"No signals detected" if a.stable else "Special-cause signals detected"}</strong></div></section>'
            '<section class="fs-card"><div class="cardhead"><div><h2>Capability snapshot</h2><p>One-sided tensile strength specification</p></div>'
            f'<span class="pill amber">{"REVIEW" if a.stable else "UNSTABLE"}</span></div>{charts.histogram(a, cfg["lsl"])}'
            f'<div class="keyline"><span>Lower spec limit</span><strong>{num(cfg["lsl"])} MPa</strong></div>'
            f'<div class="keyline"><span>Overall performance · Ppl</span><strong>{fmt(a.ppl)}</strong></div>'
            f'<div class="keyline"><span>Within estimate / overall σ</span><strong>{fmt(a.sigma, 1)} / {fmt(a.overall_sd, 1)} MPa</strong></div>'
            '</section></div><div class="grid"><section class="fs-card"><div class="sectionhead"><h2>Recent builds</h2>'
            f'<button onclick="fsGo(\'Build records\')">View all builds ↗</button></div>{table(recent, a)}</section>'
            '<section class="fs-card"><div class="sectionhead"><h2>Strength associations</h2>'
            f'<button onclick="fsGo(\'Parameter analysis\')">Explore ↗</button></div>{drivers(a)}'
            '<p>Correlation is exploratory, not proof of cause.</p></section></div>')


def control(am: Analysis, cfg: dict) -> str:
    v = am.metric
    opts = "".join(f'<option value="{k}" {"selected" if k == v else ""}>{lab}</option>' for k, (lab, _) in VARS.items())
    if am.flags:
        rows = "".join(
            f'<tr><td>{esc(str(am.records[f.index]["id"]))}</td><td>{"Baseline review" if f.index < am.baseline else "Monitoring"}</td>'
            f'<td>{num(am.records[f.index][v])} {VARS[v][1]}</td><td>{" · ".join(f.reasons)}</td></tr>'
            for f in reversed(am.flags))
        log = f'<table><thead><tr><th>BUILD</th><th>PHASE</th><th>VALUE</th><th>SIGNAL</th></tr></thead><tbody>{rows}</tbody></table>'
    else:
        log = '<div class="empty">No signals under the selected rules.</div>'
    return ('<div class="fs-card"><div class="cardhead"><div><h2>Individuals &amp; moving-range signals</h2>'
            '<p>Baseline and chronological order are preserved for the selected machine.</p></div>'
            f'<select aria-label="Variable" onchange="fsMetric(this.value)">{opts}</select></div>{charts.control_chart(am, cfg["lsl"])}'
            f'<div class="statsrow"><div><span>BASELINE MEAN</span><strong>{fmt(am.center, 1)}</strong></div>'
            f'<div><span>BASELINE σ</span><strong>{fmt(am.sigma, 2)}</strong></div>'
            f'<div><span>MR UPPER LIMIT</span><strong>{fmt(am.mr_bar * 3.267, 1)}</strong></div>'
            f'<div><span>MONITORING SIGNALS</span><strong>{len(am.post)}</strong></div></div>'
            '<p>Rules: outside ±3σ; nine consecutive points on one side of the baseline mean; moving range above 3.267 × '
            'baseline mean moving range. Baseline shading is for reference, not qualification.</p></div>'
            f'<div class="fs-card" style="margin-top:20px"><h2>Signal log</h2>{log}</div>')


def capability(a: Analysis, cfg: dict) -> str:
    p, lo, hi = wilson(a.passes, a.n)
    t = num(cfg["target"])
    yn = lambda b: "Yes" if b else "No"
    return (banner(a) + '<div class="metrics">'
            + metric_card("Lower capability · Cpl", fmt(a.cpl), "(mean − LSL) / (3 × baseline σ)")
            + metric_card("Lower performance · Ppl", fmt(a.ppl), "(mean − LSL) / (3 × overall s)")
            + metric_card("Observed conformance", fmt(p * 100, 1) + "<small>%</small>", f"{a.passes} successes / {a.n} tests")
            + metric_card("95% Wilson interval", fmt(lo * 100, 1) + "<small>–" + fmt(hi * 100, 1) + "%</small>",
                          "Binomial interval; independent builds assumed")
            + '</div><div class="grid"><div class="fs-card"><h2>Observed strength distribution</h2>'
            f'{charts.histogram(a, cfg["lsl"])}<p>Strength has a lower specification only. Cp and two-sided Cpk are not '
            f'reported; Cpl and Ppl are the appropriate lower-sided indices. The {t} threshold is a configurable '
            'demonstration requirement, not an aerospace standard.</p></div><div class="fs-card"><h2>Evidence checklist</h2>'
            f'<div class="keyline"><span>Baseline free of selected signals</span><b>{yn(not a.baseflags)}</b></div>'
            f'<div class="keyline"><span>Monitoring free of selected signals</span><b>{yn(not a.post)}</b></div>'
            f'<div class="keyline"><span>Cpl ≥ {t}</span><b>{yn(a.cpl >= cfg["target"])}</b></div>'
            '<div class="keyline"><span>Measurement system / normality</span><b>Not validated</b></div>'
            '<p>Passing these numerical screens alone does not establish capability. Verify representative sampling, '
            'independence, measurement uncertainty and distribution fit with the client.</p></div></div>'
            '<div class="fs-card"><h2>Reliability interpretation</h2><p>The pass-rate interval quantifies uncertainty in '
            'observed strength-test conformance only. It does not estimate in-service fatigue life, survival probability '
            'at mission loads, or bracket structural reliability. Those require load spectra, geometry, material allowables '
            'and fatigue or life-test data, including censored results.</p></div>')


def parameters(a: Analysis, cfg: dict) -> str:
    bars = "".join(
        f'<div class="driver"><div class="driverhead">{VARS[d["v"]][0]}<strong>{fmt(d["r"])}</strong></div>'
        f'<div class="bar"><div style="width:{_bar_width(d["r"]):.1f}%;background:{"#bf8b78" if d["r"] < 0 else "#6f9d8a"}"></div></div></div>'
        for d in associations(a.records))
    ox = sum(r["oxygen"] > cfg["oxygen"] for r in a.records)
    hu = sum(r["humidity"] > cfg["humidity"] for r in a.records)
    return ('<div class="grid"><div class="fs-card"><h2>Associations with tensile strength</h2>'
            f'<p>Pearson correlation · {a.n} matched records · selected machine</p>{bars}'
            '<p>Common time trends and confounding can create strong correlations. Use controlled trials and '
            'metallurgical evidence to test a suspected mechanism.</p></div><div class="fs-card"><h2>Environmental excursions</h2>'
            f'<div class="keyline"><span>Oxygen &gt; {num(cfg["oxygen"])} ppm</span><strong>{ox} builds</strong></div>'
            f'<div class="keyline"><span>Humidity &gt; {num(cfg["humidity"])}%</span><strong>{hu} builds</strong></div>'
            '<p>Thresholds are illustrative engineering alarms, editable in Configure. Recorded values represent one '
            'build-level summary; layer-level peaks and exposure duration are not captured.</p>'
            '<h3>Recommended traceability additions</h3><p>Powder lot and reuse count · particle size / chemistry · gas flow · '
            'melt-pool intensity · layer thickness · build orientation and location · heat-treatment/HIP cycle · surface '
            'finish · porosity · test specimen and instrument ID.</p>'
            '<button onclick="fsGo(\'Corrective actions\')">Open investigation workspace ↗</button></div></div>'
            f'<div class="fs-card"><h2>Oxygen versus tensile strength</h2>{charts.scatter(a, cfg["lsl"])}'
            '<p>Each point is one matched build and test record. Red points fail the strength specification. '
            'Click a point for build detail.</p></div>')


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
    return ('<div class="fs-card method"><h2>How this workspace makes a decision</h2>'
            '<h3>1. Preserve a comparable process stream</h3><p>Analyze one machine and one consistent part / material / '
            'process route at a time. Demo data contains 60 builds per machine with one representative destructive tensile '
            'result per build. LPBF-01 includes synthetic late-run deterioration; LPBF-02 is a comparison stream. All values '
            'and limits are illustrative, not Ti-6Al-4V design allowables.</p>'
            '<h3>2. Establish a fixed baseline</h3><p>The first N ordered builds estimate the center line and moving-range '
            'variation. σ = average |xᵢ − xᵢ₋₁| / 1.128. Individuals limits are mean ± 3σ; the moving-range upper limit is '
            '3.267 × average moving range. The app checks baseline signals too. A baseline containing signals needs '
            'investigation before it can support monitoring.</p>'
            '<h3>3. Assess stability, then capability</h3><p>The implemented rules flag points beyond 3σ, nine consecutive '
            'points on the same side of the baseline mean, and moving-range excursions. A signal is an investigation trigger, '
            'not a diagnosis. Cpl = (overall mean − LSL) / (3 × baseline σ); Ppl uses the overall sample standard deviation '
            'instead. All records for the selected machine contribute to the overall mean. On an unstable stream these are '
            'descriptive, provisional numbers, not future-performance claims.</p>'
            '<h3>4. Keep uncertainty visible</h3><p>The 95% Wilson interval uses independent pass/fail outcomes. Repeated '
            'coupons from one build are not independent builds. This prototype does not validate normality, measurement '
            'uncertainty, fatigue life or statistical power. Cpl needs a stable and representative process; distribution-based '
            'predictions require an appropriate distribution. The app intentionally does not predict defect PPM or certify '
            'release.</p>'
            '<h3>5. Close the evidence gap</h3><p>Production integration should retain timestamps, sensor calibration, units, '
            'part and powder genealogy, layer-level sensor histories, process revisions, test methods, heat-treatment records, '
            'and user audit trails. Real-time ingestion is not connected. Imported CSVs are held in the server session memory '
            'only and are discarded when the browser tab closes; corrective-action notes are saved to the server. Export before '
            'closing.</p>'
            '<h3>Run and extend the tool</h3><p><a id="download_source" class="shiny-download-link" href="" target="_blank" '
            'download>Download Shiny app + Python analysis source ↓</a>. Run with <code>shiny run app.py</code>, or analyze '
            'exported CSVs offline with the standard-library engine in <code>python/analyze.py</code> — the dashboard and the '
            'CLI share the same <code>forge_sentinel/engine.py</code>.</p>'
            '<h3>Statistical references</h3><p><a href="https://www.itl.nist.gov/div898/handbook/pmc/section3/pmc322.htm" '
            'target="_blank" rel="noopener">NIST — Individuals control charts ↗</a><br>'
            '<a href="https://www.itl.nist.gov/div898/handbook/pmc/section1/pmc16.htm" target="_blank" rel="noopener">'
            'NIST — Process capability ↗</a></p></div>')


def build_detail(a: Analysis, i: int) -> str:
    r = a.records[i]
    lines = "".join(f'<div class="keyline"><span>{lab}</span><strong>{num(r[k])} {u}</strong></div>'
                    for k, (lab, u) in VARS.items())
    sig = " · ".join(a.flagged.get(i, [])) or "No strength SPC signals."
    return (f'<h2>Build {esc(str(r["id"]))}</h2><p>{esc(str(r["machine"]))} · Sequence {i + 1} · '
            f'{"Baseline" if i < a.baseline else "Monitoring"}</p>{lines}'
            f'<p>Strength result: <strong>{"FAIL" if r["strength"] < a.lsl else "PASS"}</strong>. {sig} '
            'A passing test does not override an unresolved process signal.</p>')


def render_page(page: str, a: Analysis, am: Analysis, cfg: dict, actions: dict) -> str:
    if page == "Overview":
        return overview(a, cfg)
    if page == "Process control":
        return control(am, cfg)
    if page == "Capability":
        return capability(a, cfg)
    if page == "Parameter analysis":
        return parameters(a, cfg)
    if page == "Build records":
        return records(a)
    if page == "Corrective actions":
        return tasks(a, actions)
    return methods()
