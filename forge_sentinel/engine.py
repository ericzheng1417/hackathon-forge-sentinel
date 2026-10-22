"""Forge Sentinel analysis engine. Python 3.10+, standard library only.

Shared by the Shiny dashboard (app.py) and the offline CLI (python/analyze.py),
so both always produce the same SPC, capability and Wilson-interval numbers.
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

DEFAULT_CONFIG = {"lsl": 900.0, "target": 1.33, "baseline": 25, "oxygen": 100.0, "humidity": 40.0}

D2 = 1.128      # bias constant for moving range of 2
D4 = 3.267      # MR chart upper-limit factor
RUN_LENGTH = 9  # points on one side of the centre line


def _div(a: float, b: float) -> float:
    if b == 0:
        return math.nan if a == 0 else math.copysign(math.inf, a)
    return a / b


@dataclass
class Signal:
    index: int
    reasons: list[str]


@dataclass
class Analysis:
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
    cpl: float = math.nan
    ppl: float = math.nan
    fails: list[dict] = field(default_factory=list)

    # convenience views -------------------------------------------------
    @property
    def n(self) -> int:
        return len(self.x)

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


def individuals_signals(x: list[float], center: float, lcl: float, ucl: float, mr_bar: float) -> list[Signal]:
    """Apply the three implemented rules to every point (baseline included)."""
    flags = []
    for i, value in enumerate(x):
        why = []
        if value < lcl or value > ucl:
            why.append("Outside 3σ limits")
        if i >= RUN_LENGTH - 1:
            window = x[i - RUN_LENGTH + 1 : i + 1]
            if all(v > center for v in window) or all(v < center for v in window):
                why.append("9 points on one side")
        if i and abs(value - x[i - 1]) > D4 * mr_bar:
            why.append("Moving range exceeds UCL")
        if why:
            flags.append(Signal(i, why))
    return flags


def analyze_stream(records: list[dict], metric: str = "strength", lsl: float = 900, baseline: int = 25,
                   target: float = 1.33) -> Analysis:
    """Individuals/MR SPC for one ordered machine stream plus strength capability."""
    if metric not in VARS:
        raise ValueError(f"Unknown metric {metric!r}")
    if not 2 <= baseline <= len(records):
        raise ValueError("Baseline must contain at least 2 builds and not exceed the record count")
    x = [float(r[metric]) for r in records]
    b = x[:baseline]
    center = st.fmean(b)
    mr = [abs(v - u) for u, v in zip(b, b[1:])]
    mr_bar = st.fmean(mr)
    sigma = mr_bar / D2
    lcl, ucl = center - 3 * sigma, center + 3 * sigma
    flags = individuals_signals(x, center, lcl, ucl, mr_bar)
    avg = st.fmean(x)
    overall = st.stdev(x) if len(x) > 1 else math.nan
    a = Analysis(records, metric, x, baseline, center, mr_bar, sigma, lcl, ucl, flags, avg, overall, lsl, target)
    a.cpl = _div(avg - lsl, 3 * sigma)
    a.ppl = _div(avg - lsl, 3 * overall)
    a.fails = [r for r in records if float(r["strength"]) < lsl]
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
    """Correlation of each process variable with strength, strongest first."""
    s = [float(r["strength"]) for r in records]
    out = [{"v": v, "r": pearson(s, [float(r[v]) for r in records])} for v in FIELDS if v != "strength"]
    return sorted(out, key=lambda d: -abs(d["r"]) if math.isfinite(d["r"]) else 0)


def decision_text(a: Analysis) -> str:
    if not a.stable:
        return "Process unstable — capability not demonstrated"
    if a.cpl < a.target:
        return "Capability below target — investigate variation"
    return "No SPC signals detected — qualification review required"


def _clean(v):
    """JSON-safe floats (no NaN/Infinity)."""
    if isinstance(v, float) and not math.isfinite(v):
        return None
    return v


def report(a: Analysis, *, source: str, machine: str, config: dict, actions: dict, generated_at: str) -> dict:
    """Full dashboard export, same structure as the original web app's report."""
    return {
        "generated_at": generated_at,
        "source": source,
        "machine": machine,
        "configuration": config,
        "decision": "No selected SPC signals; engineering validation required" if a.stable
        else "Unstable; capability not demonstrated",
        "statistics": {k: _clean(v) for k, v in {
            "n": a.n, "mean": a.avg, "baseline_mean": a.center, "baseline_sigma": a.sigma,
            "overall_sd": a.overall_sd, "Cpl": a.cpl, "Ppl": a.ppl,
            "failed_strength_tests": len(a.fails)}.items()},
        "signals": [{"build": a.records[f.index]["id"],
                     "phase": "baseline" if f.index < a.baseline else "monitoring",
                     "reasons": f.reasons} for f in a.flags],
        "associations": [{"v": d["v"], "r": _clean(d["r"])} for d in associations(a.records)],
        "corrective_actions": actions,
        "records": a.records,
        "limitations": "Demonstration decision support. No qualification, fatigue reliability or release "
                       "authorization. See Methods for assumptions.",
    }


def analyze(records: list[dict], lsl: float = 900, baseline: int = 25, target: float = 1.33) -> dict:
    """CLI report (unchanged output schema from the original analyze.py)."""
    if not 10 <= baseline < len(records):
        raise ValueError("Need at least 10 baseline builds and one monitoring build")
    x = [float(r["strength"]) for r in records]
    if not all(math.isfinite(v) and v > 0 for v in x):
        raise ValueError("Strength must be finite and positive")
    a = analyze_stream(records, "strength", lsl, baseline, target)
    if a.sigma == 0:
        raise ValueError("Zero baseline variation: verify measurement resolution")
    p, lo, hi = wilson(a.passes, a.n)
    return {"n": a.n, "mean": a.avg, "baseline_mean": a.center, "baseline_sigma": a.sigma,
            "overall_sd": a.overall_sd, "Cpl": a.cpl, "Ppl": a.ppl,
            "failed_strength_tests": len(a.fails), "pass_rate": p, "wilson_95": [lo, hi],
            "signals": [{"build": records[f.index]["id"],
                         "phase": "baseline" if f.index < baseline else "monitoring",
                         "reasons": f.reasons} for f in a.flags],
            "stable_under_selected_rules": a.stable,
            "capability_screen_passed": a.stable and a.cpl >= target,
            "limitation": "Screening only; does not certify qualification, fatigue reliability or release."}
