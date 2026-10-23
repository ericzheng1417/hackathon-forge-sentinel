"""Forge Sentinel analysis engine. Python 3.10+, standard library only.

Shared by the Shiny dashboard (app.py) and the offline CLI (python/analyze.py),
so both always produce the same numbers.

Contents
- Descriptive statistics (mean, median, SD, variance, CV, SE, range, quartiles, IQR)
- Individuals (I) and moving-range (MR) control charts with baseline-frozen limits
- The 8 standard tests for special causes (Western Electric / Nelson rules)
- X̄ and S charts when several test coupons are recorded per build (subgroups)
- Capability and performance indices: Cp, Cpk, Cpl, Cpu, Pp, Ppk, Ppl, Ppu
- Distribution checks: Anderson-Darling normality test, normal Q-Q points, expected ppm out of spec
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
COLUMNS = ("id", "machine", "coupon", *FIELDS)   # coupon: optional, one row per tensile coupon
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


# -- distribution / normality ----------------------------------------------

def anderson_darling(values: list) -> dict:
    """Anderson-Darling test for normality (mean and SD estimated from the data).

    A² = −n − (1/n) Σ (2i − 1) [ln F(x₍ᵢ₎) + ln(1 − F(x₍ₙ₊₁₋ᵢ₎))], with F the fitted normal CDF;
    A²* = A² (1 + 0.75/n + 2.25/n²); p-value from D'Agostino & Stephens (1986). Returns
    {"n", "ad", "ad_adj", "p", "normal"} where normal = p ≥ 0.05 (NaN/None if n < 8 or SD = 0).
    """
    x = sorted(float(v) for v in values if present(v))
    n = len(x)
    empty = {"n": n, "ad": math.nan, "ad_adj": math.nan, "p": math.nan, "normal": None}
    if n < 8:
        return empty
    m, sd = st.fmean(x), st.stdev(x)
    if sd == 0:
        return empty
    nd = st.NormalDist(m, sd)
    f = [min(max(nd.cdf(v), 1e-15), 1 - 1e-15) for v in x]
    a2 = -n - sum((2 * i - 1) * (math.log(f[i - 1]) + math.log(1 - f[n - i])) for i in range(1, n + 1)) / n
    a = a2 * (1 + 0.75 / n + 2.25 / n ** 2)
    if a >= 0.6:
        p = math.exp(1.2937 - 5.709 * a + 0.0186 * a * a)
    elif a >= 0.34:
        p = math.exp(0.9177 - 4.279 * a - 1.38 * a * a)
    elif a >= 0.2:
        p = 1 - math.exp(-8.318 + 42.796 * a - 59.938 * a * a)
    else:
        p = 1 - math.exp(-13.436 + 101.14 * a - 223.73 * a * a)
    p = min(max(p, 0.0), 1.0)
    return {"n": n, "ad": a2, "ad_adj": a, "p": p, "normal": p >= 0.05}


def normal_quantiles(n: int) -> list[float]:
    """Theoretical standard-normal quantiles for a Q-Q plot (Blom: (i − 0.375) / (n + 0.25))."""
    z = st.NormalDist()
    return [z.inv_cdf((i - 0.375) / (n + 0.25)) for i in range(1, n + 1)]


def expected_out_of_spec(mean: float, sigma: float, lsl: float | None, usl: float | None) -> dict:
    """Fraction of parts a normal distribution N(mean, sigma) puts outside the limits, in ppm."""
    if not (_finite(mean) and _finite(sigma) and sigma > 0):
        return {"below_ppm": math.nan, "above_ppm": math.nan, "total_ppm": math.nan}
    nd = st.NormalDist(mean, sigma)
    below = nd.cdf(lsl) * 1e6 if lsl is not None else 0.0
    above = (1 - nd.cdf(usl)) * 1e6 if usl is not None else 0.0
    return {"below_ppm": below, "above_ppm": above, "total_ppm": below + above}


# -- subgroups (several coupons per build) ----------------------------------

def has_coupons(records: list[dict]) -> bool:
    """True if any row carries a coupon label (coupon-level data)."""
    return any(present(r.get("coupon")) for r in records)


def build_level(records: list[dict]) -> list[dict]:
    """One row per build. Without a coupon column the rows are returned unchanged.

    With coupons, rows sharing (machine, id) are combined in first-seen order:
    strength = mean of the coupons; each process variable = mean of its recorded values;
    plus "coupons" [(label, strength)], "n_coupons", "strength_sd", "strength_min", "strength_max".
    """
    if not has_coupons(records):
        return records
    groups: dict = {}
    for r in records:
        groups.setdefault((r["machine"], r["id"]), []).append(r)
    out = []
    for (machine, bid), rows in groups.items():
        vals = [float(r["strength"]) for r in rows if present(r.get("strength"))]
        b = {"id": bid, "machine": machine, "coupon": None,
             "strength": st.fmean(vals) if vals else None,
             "coupons": [(r.get("coupon"), float(r["strength"])) for r in rows if present(r.get("strength"))],
             "n_coupons": len(vals),
             "strength_sd": st.stdev(vals) if len(vals) > 1 else None,
             "strength_min": min(vals) if vals else None, "strength_max": max(vals) if vals else None}
        for v in OPTIONAL_FIELDS:
            pv = [float(r[v]) for r in rows if present(r.get(v))]
            b[v] = st.fmean(pv) if pv else None
        out.append(b)
    return out


def c4(n: int) -> float:
    """Unbiasing constant for the sample SD: E[s] = c4·σ for subgroups of size n."""
    return math.sqrt(2 / (n - 1)) * math.exp(math.lgamma(n / 2) - math.lgamma((n - 1) / 2))


def xbar_s_constants(n: int) -> dict:
    """Classic table constants (A3, B3, B4, c4) for subgroup size n — for reference and tests."""
    c = c4(n)
    w = 3 * math.sqrt(1 - c * c) / c
    return {"c4": c, "A3": 3 / (c * math.sqrt(n)), "B3": max(0.0, 1 - w), "B4": 1 + w}


@dataclass
class XbarS:
    """X̄ and S chart for one machine (one subgroup = one build's coupons)."""
    ids: list
    n: list[int]                  # coupons per build
    means: list[float]
    sds: list                     # None where n < 2
    baseline: int
    center: float                 # grand mean of the baseline coupons
    sigma: float                  # within-build σ̂ (s̄/c4 for equal n; pooled s / c4(d) otherwise)
    s_bar: float
    x_lcl: list[float]
    x_ucl: list[float]
    s_center: list
    s_lcl: list
    s_ucl: list
    method: str
    x_hits: dict = field(default_factory=dict)   # index -> [test numbers]
    s_hits: dict = field(default_factory=dict)   # index -> "above" / "below"

    @property
    def equal_n(self) -> bool:
        return len(set(self.n)) == 1

    @property
    def typical_n(self) -> int:
        return max(set(self.n), key=self.n.count)


def xbar_s(builds: list[dict], baseline: int, tests=ALL_TESTS) -> XbarS:
    """X̄-S chart from build-level rows (output of build_level) with frozen baseline limits.

    σ̂ within: s̄ / c4(n) when every baseline build has the same number of coupons, otherwise
    the pooled SD / c4(d), d = Σ(nᵢ − 1) + 1. Limits for build i with nᵢ coupons:
      X̄: x̿ ± 3σ̂/√nᵢ   (= x̿ ± A3·s̄ for equal n)
      S: c4(nᵢ)σ̂ ± 3σ̂√(1 − c4(nᵢ)²), lower limit floored at 0   (= B3·s̄, B4·s̄)
    The 8 tests run on standardised means zᵢ = (x̄ᵢ − x̿) / (σ̂/√nᵢ); an S value outside its
    limits is flagged as "S".
    """
    groups = [[v for _, v in b["coupons"]] if b.get("coupons") else [float(b["strength"])] for b in builds]
    sizes = [len(g) for g in groups]
    means = [st.fmean(g) for g in groups]
    sds = [st.stdev(g) if len(g) > 1 else None for g in groups]
    base = groups[:baseline]
    multi = [g for g in base if len(g) > 1]
    if len(multi) < 2:
        raise ValueError("X̄-S charts need at least 2 baseline builds with 2 or more coupons")
    center = sum(sum(g) for g in base) / sum(len(g) for g in base)
    base_sizes = {len(g) for g in base}
    if len(base_sizes) == 1:
        nn = base_sizes.pop()
        s_bar = st.fmean(st.stdev(g) for g in base)
        sigma, method = s_bar / c4(nn), f"s̄ / c4({nn})"
    else:
        dof = sum(len(g) - 1 for g in multi)
        sp = math.sqrt(sum((len(g) - 1) * st.variance(g) for g in multi) / dof)
        s_bar, sigma, method = sp, sp / c4(dof + 1), f"pooled s / c4({dof + 1})"
    x_lcl = [center - 3 * sigma / math.sqrt(k) for k in sizes]
    x_ucl = [center + 3 * sigma / math.sqrt(k) for k in sizes]
    s_center, s_lcl, s_ucl = [], [], []
    for k in sizes:
        if k < 2:
            s_center.append(None), s_lcl.append(None), s_ucl.append(None)
            continue
        c, w = c4(k) * sigma, 3 * sigma * math.sqrt(1 - c4(k) ** 2)
        s_center.append(c), s_lcl.append(max(0.0, c - w)), s_ucl.append(c + w)
    xs = XbarS([b["id"] for b in builds], sizes, means, sds, baseline, center, sigma, s_bar, x_lcl, x_ucl,
               s_center, s_lcl, s_ucl, method)
    if sigma > 0:
        z = [(m - center) / (sigma / math.sqrt(k)) for m, k in zip(means, sizes)]
        xs.x_hits = special_cause_tests(z, 0.0, 1.0, tests)
        for i, sd in enumerate(sds):
            if sd is not None and s_ucl[i] is not None:
                if sd > s_ucl[i]:
                    xs.s_hits[i] = "above"
                elif s_lcl[i] > 0 and sd < s_lcl[i]:
                    xs.s_hits[i] = "below"
    return xs


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
    tests: list          # test numbers (1-8) and/or "MR" (moving range) / "S" (S chart)
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
    values: list = field(default_factory=list)     # individual observations (coupons if subgrouped)
    value_idx: list = field(default_factory=list)  # build position (in `records`) of each value
    normal: dict = field(default_factory=dict)     # anderson_darling(values)
    expected: dict = field(default_factory=dict)   # {"within": ppm dict, "overall": ppm dict} (strength only)
    xs: XbarS | None = None                        # X̄-S chart when strength has coupon subgroups
    cap_basis: str = "MR̄ / 1.128"                  # how within σ was estimated for Cp/Cpk

    @property
    def chart(self) -> str:
        return "Xbar-S" if self.xs else "I-MR"

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
        """A build fails if its strength (or, with coupons, any coupon) is outside the specification."""
        lo = r.get("strength_min", r["strength"])
        hi = r.get("strength_max", r["strength"])
        lo = float(lo if lo is not None else r["strength"])
        hi = float(hi if hi is not None else r["strength"])
        return lo < self.lsl or (self.usl is not None and hi > self.usl)

    def test_counts(self) -> dict:
        counts = {t: 0 for t in (*self.tests, "S" if self.xs else "MR")}
        for f in self.flags:
            for t in f.tests:
                counts[t] = counts.get(t, 0) + 1
        return counts


def _reason(t) -> str:
    return MR_RULE_TEXT if t == "MR" else f"Test {t}: {SPECIAL_TESTS[t][0]}"


def analyze_stream(records: list[dict], metric: str = "strength", lsl: float = 900, baseline: int = 25,
                   target: float = 1.33, usl: float | None = None, tests=ALL_TESTS,
                   mr_rule: bool = True) -> Analysis:
    """SPC for one ordered machine stream, plus strength capability, descriptives and normality.

    records  : rows for ONE machine in build order; each needs id and strength, other
               variables are optional (None/blank rows are skipped for that metric only).
               Coupon-level rows (a coupon column, several rows per build) are combined with
               build_level(); for strength the X̄-S chart then replaces I-MR, and Cp/Cpk use
               the within-build σ̂ from xbar_s().
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
    coupon_rows = records
    records = build_level(records)
    subgrouped = records is not coupon_rows and any(r.get("n_coupons", 1) > 1 for r in records)
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
    a.values = x
    a.value_idx = list(range(len(x)))
    if metric == "strength" and subgrouped:
        _apply_subgroups(a, coupon_rows, tests)
    a.normal = anderson_darling(a.values)
    if metric == "strength":
        a.expected = {"within": expected_out_of_spec(st.fmean(a.values), a.sigma if not a.xs else a.xs.sigma, lsl, usl),
                      "overall": expected_out_of_spec(st.fmean(a.values), st.stdev(a.values), lsl, usl)}
    a.fails = [r for r in records if a.is_fail(r)]
    return a


def _apply_subgroups(a: Analysis, coupon_rows: list[dict], tests) -> None:
    """Switch a strength Analysis to the X̄-S chart and coupon-level capability."""
    xs = xbar_s(a.records, a.baseline, tests)
    a.xs = xs
    hits: dict = {i: list(ts) for i, ts in xs.x_hits.items()}
    for i in xs.s_hits:
        hits.setdefault(i, []).append("S")
    a.flags = [Signal(i, ts, [(f"S chart: within-build SD {'above UCL' if xs.s_hits[i] == 'above' else 'below LCL'}"
                               if t == "S" else _reason(t)) for t in ts]) for i, ts in sorted(hits.items())]
    a.center = xs.center
    a.sigma = xs.sigma
    a.lcl, a.ucl = xs.x_lcl[0], xs.x_ucl[0]
    pos = {(r["machine"], r["id"]): i for i, r in enumerate(a.records)}
    used = [r for r in coupon_rows if present(r.get("strength"))]
    vals = [float(r["strength"]) for r in used]
    a.values = vals
    a.value_idx = [pos[(r["machine"], r["id"])] for r in used]
    a.desc = describe(vals)
    a.avg, a.overall_sd = st.fmean(vals), st.stdev(vals)
    a.cap = capability(a.avg, xs.sigma, a.overall_sd, a.lsl, a.usl)
    a.cap_basis = f"within-build σ̂ = {xs.method}"


def describe_all(stream: list[dict]) -> dict:
    """describe() for every recorded variable of one machine: strength over all individual
    results (every coupon), process variables over builds (one value per build)."""
    builds = build_level(stream)
    out = {}
    for v in available_vars(builds):
        src = stream if v == "strength" else builds
        out[v] = describe([r.get(v) for r in src])
    return out


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
        "descriptive": {v: describe([r.get(v) for r in a.records]) for v in available_vars(a.records)}
        | ({"strength": a.desc} if a.xs else {}),
        "capability": a.cap,
        "capability_basis": a.cap_basis,
        "normality": a.normal,
        "expected_out_of_spec_ppm": a.expected,
        "control_chart": ({"type": "I-MR", "center": a.center, "sigma": a.sigma, "lcl": a.lcl, "ucl": a.ucl,
                           "mr_bar": a.mr_bar, "mr_ucl": a.mr_ucl, "tests_applied": list(a.tests)} if not a.xs else
                          {"type": "Xbar-S", "center": a.xs.center, "sigma_within": a.xs.sigma, "s_bar": a.xs.s_bar,
                           "sigma_method": a.xs.method, "subgroup_sizes": a.xs.n, "xbar_lcl": a.xs.x_lcl,
                           "xbar_ucl": a.xs.x_ucl, "s_lcl": a.xs.s_lcl, "s_ucl": a.xs.s_ucl,
                           "tests_applied": list(a.tests) + ["S"]}),
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
    if not 10 <= baseline < len(build_level(records)):
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
        "lsl": lsl, "usl": a.usl, "descriptive": a.desc, "chart": a.chart,
        "capability_basis": a.cap_basis, "normality": a.normal, "expected_out_of_spec_ppm": a.expected,
        **({"coupons_per_build": a.xs.n, "xbar_center": a.xs.center, "sigma_within": a.xs.sigma} if a.xs else {}),
        "failed_strength_tests": len(a.fails), "pass_rate": p, "wilson_95": [lo, hi],
        "tests_applied": list(a.tests) + (["S"] if a.xs else (["MR"] if mr_rule else [])),
        "signals": _signals_json(a),
        "stable_under_selected_rules": a.stable,
        "capability_screen_passed": a.stable and a.cpk >= target,
        "limitation": "Screening only; does not certify qualification, fatigue reliability or release.",
    })
