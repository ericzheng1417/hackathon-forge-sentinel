"""Forge Sentinel analysis engine. Python 3.10+, standard library only.

Shared by the Shiny dashboard (app.py) and the offline CLI (python/analyze.py),
so both always produce the same numbers.

Contents
- Descriptive statistics (mean, median, SD, variance, CV, SE, range, quartiles, IQR)
- Individuals (I) and moving-range (MR) control charts with baseline-frozen limits
- The 8 standard tests for special causes (Western Electric / Nelson rules)
- Capability and performance indices: Cp, Cpk, Cpl, Cpu, Pp, Ppk, Ppl, Ppu
- Wilson score interval for the observed pass rate, Pearson correlations, JSON report
"""
from __future__ import annotations

import math
import statistics as st
from dataclasses import dataclass, field

# key -> (label, unit)
VARS: dict[str, tuple[str, str]] = {
    "strength": ("Tensile strength", "MPa"),
    "oxygen": ("Chamber oxygen", "ppm"),
    "humidity": ("Relative humidity", "%"),
    "temperature": ("Build plate temperature", "°C"),
    "power": ("Laser power", "W"),
    "speed": ("Scan speed", "mm/s"),
    "stress": ("Residual stress", "MPa"),
}
FIELDS = tuple(VARS)
COLUMNS = ("id", "machine", *FIELDS)
REQUIRED_COLUMNS = ("id", "machine", "strength")          # the only inputs a contractor must supply
OPTIONAL_FIELDS = tuple(v for v in FIELDS if v != "strength")
MIN_VALUES = 10   # a variable needs at least this many recorded values to be charted or correlated

ALL_TESTS = (1, 2, 3, 4, 5, 6, 7, 8)
DEFAULT_CONFIG = {
    "lsl": 900.0,          # lower specification limit for strength (MPa)
    "usl": 1100.0,         # upper specification limit for strength (MPa); None = one-sided spec
    "target": 1.33,        # capability target applied to Cpk
    "baseline": 25,        # builds used to freeze the centre line and limits
    "oxygen": 100.0,       # oxygen alarm (ppm)
    "humidity": 40.0,      # humidity alarm (%)
    "tests": list(ALL_TESTS),
    "mr_rule": True,       # also flag moving ranges above the MR-chart UCL
}

D2 = 1.128      # bias constant for moving range of 2
D4 = 3.267      # MR chart upper-limit factor

# number -> (short name, pattern, what it usually signals)
SPECIAL_TESTS: dict[int, tuple[str, str, str]] = {
    1: ("Beyond zone A", "One point beyond zone A (outside the control limits)",
        "A sporadic shift, or the beginning of a sustained shift"),
    2: ("2 of 3 beyond zone B", "Two out of three points in a row beyond zone B (same side)",
        "An early warning of a shift"),
    3: ("4 of 5 beyond zone C", "Four out of five points in a row beyond zone C (same side)",
        "An early warning of a sustained shift"),
    4: ("8 on one side", "Eight points in a row on the same side of the centerline",
        "A sustained shift in the process mean"),
    5: ("6 trending", "Six points in a row steadily increasing or decreasing",
        "An upward or downward trend, such as tool wear or drift"),
    6: ("15 in zone C", "Fifteen points in a row in zone C (above and below the centerline)",
        "Less variation than expected: a faulty gauge, reduced variability, or wrong control limits"),
    7: ("8 outside zone C", "Eight points in a row on both sides of the centerline, with none in zone C",
        "Subgroups drawn from two different distributions (a mix of process streams)"),
    8: ("14 alternating", "Fourteen points in a row alternating up and down",
        "A systematic factor, such as alternating machines, suppliers, or operators"),
}
MR_RULE_TEXT = "Moving range above MR-chart UCL"


def _div(a: float, b: float) -> float:
    if b == 0 or not math.isfinite(b):
        return math.nan if a == 0 or not math.isfinite(b) else math.copysign(math.inf, a)
    return a / b


def _finite(v) -> bool:
    return isinstance(v, (int, float)) and math.isfinite(v)


# -- descriptive statistics -----------------------------------------------

def present(v) -> bool:
    """True if a measurement was recorded (optional columns may be blank → None)."""
    return v is not None and v != ""


def available_vars(records: list[dict]) -> list[str]:
    """Variables with enough recorded values to analyse. Strength is always included."""
    return [v for v in FIELDS
            if v == "strength" or sum(present(r.get(v)) for r in records) >= MIN_VALUES]


def describe(values: list) -> dict:
    """Lean Six Sigma descriptive summary (sample statistics, n−1 denominator).

    Blank values (None) are ignored. Quartiles use the inclusive method
    (same as Excel QUARTILE.INC / numpy default).
    """
    x = [float(v) for v in values if present(v)]
    n = len(x)
    if n == 0:
        raise ValueError("No values to describe")
    mean = st.fmean(x)
    sd = st.stdev(x) if n > 1 else math.nan
    var = st.variance(x) if n > 1 else math.nan
    q1, q2, q3 = st.quantiles(x, n=4, method="inclusive") if n > 1 else (x[0],) * 3
    lo, hi = min(x), max(x)
    return {
        "n": n, "mean": mean, "median": st.median(x), "sd": sd, "variance": var,
        "cv_pct": _div(sd, abs(mean)) * 100 if _finite(sd) else math.nan,
        "se_mean": sd / math.sqrt(n) if _finite(sd) else math.nan,
        "min": lo, "max": hi, "range": hi - lo, "q1": q1, "q3": q3, "iqr": q3 - q1,
    }


# -- control-chart tests ---------------------------------------------------

def special_cause_tests(x: list[float], center: float, sigma: float,
                        tests=ALL_TESTS) -> dict[int, list[int]]:
    """Apply the 8 tests for special causes to an individuals series.

    Returns {point index: [test numbers]}. A point is flagged when it completes the
    pattern (as Minitab does); for tests 2 and 3 the flagged point must itself be
    one of the points beyond the zone. Zones use the baseline σ.
    """
    tests = set(tests)
    hits: dict[int, list[int]] = {}
    zone_ok = sigma > 0 and math.isfinite(sigma)
    z = [(v - center) / sigma for v in x] if zone_ok else [math.nan] * len(x)

    def add(i: int, t: int):
        hits.setdefault(i, []).append(t)

    for i in range(len(x)):
        if zone_ok:
            if 1 in tests and abs(z[i]) > 3:
                add(i, 1)
            if 2 in tests and i >= 2:
                w = z[i - 2 : i + 1]
                if (z[i] > 2 and sum(v > 2 for v in w) >= 2) or (z[i] < -2 and sum(v < -2 for v in w) >= 2):
                    add(i, 2)
            if 3 in tests and i >= 4:
                w = z[i - 4 : i + 1]
                if (z[i] > 1 and sum(v > 1 for v in w) >= 4) or (z[i] < -1 and sum(v < -1 for v in w) >= 4):
                    add(i, 3)
        if 4 in tests and i >= 7:
            w = x[i - 7 : i + 1]
            if all(v > center for v in w) or all(v < center for v in w):
                add(i, 4)
        if 5 in tests and i >= 5:
            w = x[i - 5 : i + 1]
            d = [b - a for a, b in zip(w, w[1:])]
            if all(v > 0 for v in d) or all(v < 0 for v in d):
                add(i, 5)
        if zone_ok:
            if 6 in tests and i >= 14 and all(abs(v) < 1 for v in z[i - 14 : i + 1]):
                add(i, 6)
            if 7 in tests and i >= 7:
                w = z[i - 7 : i + 1]
                if all(abs(v) > 1 for v in w) and any(v > 0 for v in w) and any(v < 0 for v in w):
                    add(i, 7)
        if 8 in tests and i >= 13:
            w = x[i - 13 : i + 1]
            d = [b - a for a, b in zip(w, w[1:])]
            if all(v != 0 for v in d) and all((d[k] > 0) != (d[k + 1] > 0) for k in range(len(d) - 1)):
                add(i, 8)
    return hits


def moving_ranges(x: list[float]) -> list[float | None]:
    """MR_i = |x_i − x_{i−1}|; the first point has no moving range."""
    return [None] + [abs(b - a) for a, b in zip(x, x[1:])]


# -- capability ------------------------------------------------------------

def capability(mean: float, sigma_within: float, sigma_overall: float, lsl: float | None,
               usl: float | None) -> dict:
    """Cp/Cpk use within (short-term, MR̄/d2) σ; Pp/Ppk use overall sample SD.

    With only one spec limit, Cp and Pp are undefined and Cpk/Ppk equal the
    one-sided index.
    """
    def idx(s):
        lo = _div(mean - lsl, 3 * s) if lsl is not None else math.nan
        hi = _div(usl - mean, 3 * s) if usl is not None else math.nan
        two = _div(usl - lsl, 6 * s) if lsl is not None and usl is not None else math.nan
        k = min(v for v in (lo, hi) if not math.isnan(v)) if not (math.isnan(lo) and math.isnan(hi)) else math.nan
        return two, k, lo, hi
    cp, cpk, cpl, cpu = idx(sigma_within)
    pp, ppk, ppl, ppu = idx(sigma_overall)
    return {"Cp": cp, "Cpk": cpk, "Cpl": cpl, "Cpu": cpu, "Pp": pp, "Ppk": ppk, "Ppl": ppl, "Ppu": ppu}


# -- full stream analysis ---------------------------------------------------

@dataclass
class Signal:
    index: int
    tests: list          # test numbers (1-8) and/or "MR"
    reasons: list[str]


@dataclass
class Analysis:
    """Result of analyze_stream. `records` are the rows that have the metric recorded;
    `idx[i]` maps position i back to the row's position in the full machine stream."""
    records: list[dict]
    metric: str
    x: list[float]
    baseline: int
    center: float
    mr_bar: float
    sigma: float
    lcl: float
    ucl: float
    flags: list[Signal]
    avg: float
    overall_sd: float
    lsl: float
    target: float
    usl: float | None = None
    tests: tuple = ALL_TESTS
    mr: list = field(default_factory=list)
    mr_ucl: float = math.nan
    cap: dict = field(default_factory=dict)
    desc: dict = field(default_factory=dict)
    fails: list[dict] = field(default_factory=list)
    idx: list[int] = field(default_factory=list)
    n_missing: int = 0

    @property
    def n(self) -> int:
        return len(self.x)

    @property
    def cpl(self) -> float:
        return self.cap.get("Cpl", math.nan)

    @property
    def ppl(self) -> float:
        return self.cap.get("Ppl", math.nan)

    @property
    def cpk(self) -> float:
        return self.cap.get("Cpk", math.nan)

    @property
    def post(self) -> list[Signal]:
        return [f for f in self.flags if f.index >= self.baseline]

    @property
    def baseflags(self) -> list[Signal]:
        return [f for f in self.flags if f.index < self.baseline]

    @property
    def stable(self) -> bool:
        return not self.flags

    @property
    def flagged(self) -> dict[int, list[str]]:
        return {f.index: f.reasons for f in self.flags}

    @property
    def passes(self) -> int:
        return self.n - len(self.fails)

    def is_fail(self, r: dict) -> bool:
        s = float(r["strength"])
        return s < self.lsl or (self.usl is not None and s > self.usl)

    def test_counts(self) -> dict:
        counts = {t: 0 for t in (*self.tests, "MR")}
        for f in self.flags:
            for t in f.tests:
                counts[t] = counts.get(t, 0) + 1
        return counts


def _reason(t) -> str:
    return MR_RULE_TEXT if t == "MR" else f"Test {t}: {SPECIAL_TESTS[t][0]}"


def analyze_stream(records: list[dict], metric: str = "strength", lsl: float = 900, baseline: int = 25,
                   target: float = 1.33, usl: float | None = None, tests=ALL_TESTS,
                   mr_rule: bool = True) -> Analysis:
    """I-MR SPC for one ordered machine stream, plus strength capability and descriptives.

    records  : rows for ONE machine in build order; each needs id and strength, other
               variables are optional (None/blank rows are skipped for that metric only)
    metric   : variable to chart (a key of VARS)
    lsl, usl : strength specification limits in MPa (usl=None → one-sided)
    baseline : number of initial builds that freeze the centre line and limits
               (reduced automatically if the metric has fewer recorded values)
    target   : Cpk target used in the verdict
    tests    : which of the 8 special-cause tests to apply
    mr_rule  : also flag moving ranges above the MR-chart UCL
    """
    if metric not in VARS:
        raise ValueError(f"Unknown metric {metric!r}")
    full = records
    idx = [i for i, r in enumerate(full) if present(r.get(metric))]
    records = [full[i] for i in idx]
    if len(records) < 3:
        raise ValueError(f"{VARS[metric][0]} has fewer than 3 recorded values")
    baseline = min(baseline, len(records) - 1)
    if baseline < 2:
        raise ValueError("Baseline must contain at least 2 builds")
    tests = tuple(sorted(int(t) for t in tests if int(t) in SPECIAL_TESTS))
    x = [float(r[metric]) for r in records]
    b = x[:baseline]
    center = st.fmean(b)
    mr_bar = st.fmean(abs(v - u) for u, v in zip(b, b[1:]))
    sigma = mr_bar / D2
    lcl, ucl = center - 3 * sigma, center + 3 * sigma
    mr = moving_ranges(x)
    mr_ucl = D4 * mr_bar

    hits = special_cause_tests(x, center, sigma, tests)
    if mr_rule:
        for i, m in enumerate(mr):
            if m is not None and m > mr_ucl:
                hits.setdefault(i, []).append("MR")
    flags = [Signal(i, ts, [_reason(t) for t in ts]) for i, ts in sorted(hits.items())]

    avg = st.fmean(x)
    overall = st.stdev(x) if len(x) > 1 else math.nan
    if usl is not None and usl <= lsl:
        usl = None
    s = [float(r["strength"]) for r in full]
    sb = s[:min(baseline, len(s) - 1)] if metric != "strength" else s[:baseline]
    s_center_sigma = sigma if metric == "strength" else st.fmean(abs(v - u) for u, v in zip(sb, sb[1:])) / D2
    cap = capability(st.fmean(s), s_center_sigma, st.stdev(s) if len(s) > 1 else math.nan, lsl, usl)
    a = Analysis(records, metric, x, baseline, center, mr_bar, sigma, lcl, ucl, flags, avg, overall, lsl,
                 target, usl, tests, mr, mr_ucl, cap, describe(x), idx=idx, n_missing=len(full) - len(records))
    a.fails = [r for r in records if a.is_fail(r)]
    return a


def wilson(successes: int, n: int, z: float = 1.96) -> tuple[float, float, float]:
    """Observed proportion and 95% Wilson score interval."""
    p = successes / n
    den = 1 + z * z / n
    mid = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return p, mid - half, mid + half


def pearson(a: list[float], b: list[float]) -> float:
    ma, mb = st.fmean(a), st.fmean(b)
    den = math.sqrt(sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b))
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / den if den else math.nan


def associations(records: list[dict]) -> list[dict]:
    """Pearson correlation of each recorded process variable with strength, strongest first.

    Uses pairwise-complete rows; variables with fewer than MIN_VALUES pairs are skipped.
    Each item: {"v": variable key, "r": correlation, "n": pairs used}.
    """
    out = []
    for v in OPTIONAL_FIELDS:
        pairs = [(float(r["strength"]), float(r[v])) for r in records if present(r.get(v))]
        if len(pairs) >= MIN_VALUES:
            out.append({"v": v, "r": pearson([p[0] for p in pairs], [p[1] for p in pairs]), "n": len(pairs)})
    return sorted(out, key=lambda d: -abs(d["r"]) if math.isfinite(d["r"]) else 0)


def decision_text(a: Analysis) -> str:
    if not a.stable:
        return "Process unstable — capability not demonstrated"
    if not a.cpk >= a.target:
        return "Capability below target — investigate variation"
    return "No SPC signals detected — qualification review required"


def _clean(v):
    """JSON-safe values (NaN/Infinity -> null), recursively."""
    if isinstance(v, float) and not math.isfinite(v):
        return None
    if isinstance(v, dict):
        return {k: _clean(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_clean(x) for x in v]
    return v


def _signals_json(a: Analysis) -> list[dict]:
    return [{"build": a.records[f.index]["id"],
             "phase": "baseline" if f.index < a.baseline else "monitoring",
             "tests": f.tests, "reasons": f.reasons} for f in a.flags]


def report(a: Analysis, *, source: str, machine: str, config: dict, actions: dict, generated_at: str) -> dict:
    """Full dashboard export."""
    return _clean({
        "generated_at": generated_at,
        "source": source,
        "machine": machine,
        "configuration": config,
        "decision": "No selected SPC signals; engineering validation required" if a.stable
        else "Unstable; capability not demonstrated",
        "statistics": {"n": a.n, "mean": a.avg, "baseline_mean": a.center, "baseline_sigma": a.sigma,
                       "overall_sd": a.overall_sd, "Cpl": a.cpl, "Ppl": a.ppl,
                       "failed_strength_tests": len(a.fails)},
        "descriptive": {v: describe([r.get(v) for r in a.records]) for v in available_vars(a.records)},
        "capability": a.cap,
        "control_chart": {"center": a.center, "sigma": a.sigma, "lcl": a.lcl, "ucl": a.ucl,
                          "mr_bar": a.mr_bar, "mr_ucl": a.mr_ucl, "tests_applied": list(a.tests)},
        "signals": _signals_json(a),
        "associations": associations(a.records),
        "corrective_actions": actions,
        "records": a.records,
        "limitations": "Demonstration decision support. No qualification, fatigue reliability or release "
                       "authorization. See Methods for assumptions.",
    })


def analyze(records: list[dict], lsl: float = 900, baseline: int = 25, target: float = 1.33,
            usl: float | None = None, tests=ALL_TESTS, mr_rule: bool = True) -> dict:
    """CLI report. Keeps the original keys and adds Cp/Cpk, descriptives and test numbers."""
    if not 10 <= baseline < len(records):
        raise ValueError("Need at least 10 baseline builds and one monitoring build")
    x = [float(r["strength"]) for r in records]
    if not all(math.isfinite(v) and v > 0 for v in x):
        raise ValueError("Strength must be finite and positive")
    a = analyze_stream(records, "strength", lsl, baseline, target, usl, tests, mr_rule)
    if a.sigma == 0:
        raise ValueError("Zero baseline variation: verify measurement resolution")
    p, lo, hi = wilson(a.passes, a.n)
    return _clean({
        "n": a.n, "mean": a.avg, "baseline_mean": a.center, "baseline_sigma": a.sigma,
        "overall_sd": a.overall_sd, "Cpl": a.cpl, "Ppl": a.ppl, **{k: a.cap[k] for k in ("Cp", "Cpk", "Cpu", "Pp", "Ppk", "Ppu")},
        "lsl": lsl, "usl": a.usl, "descriptive": a.desc,
        "failed_strength_tests": len(a.fails), "pass_rate": p, "wilson_95": [lo, hi],
        "tests_applied": list(a.tests) + (["MR"] if mr_rule else []),
        "signals": _signals_json(a),
        "stable_under_selected_rules": a.stable,
        "capability_screen_passed": a.stable and a.cpk >= target,
        "limitation": "Screening only; does not certify qualification, fatigue reliability or release.",
    })
