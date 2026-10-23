"""Forge Sentinel demonstration: run the analysis on the three test datasets.

Usage (from the repository root):
    python demo/run_demo.py                 # print the report
    python demo/run_demo.py > demo/demo_output.txt

Python standard library only (no Shiny needed). Uses the same engine as the dashboard,
with the dashboard's default settings, so every number here matches what the app shows.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from forge_sentinel import data, engine  # noqa: E402

CFG = engine.DEFAULT_CONFIG
DATASETS = [
    ("01_stable_capable.csv", "Stable and capable process"),
    ("02_oxygen_drift.csv", "Chamber seal leak (oxygen drift), then repair"),
    ("03_strength_only.csv", "Powder-lot change, strength-only data"),
    ("04_coupon_spread.csv", "4 coupons per build, uneven gas flow across the plate (X̄-S chart)"),
]


def f(v, d=2):
    return "—" if v is None or v != v or v in (float("inf"), float("-inf")) else f"{v:.{d}f}"


def pv(p):
    return "< 0.005" if p < 0.005 else f"= {p:.3f}"


def describe_machine(rows: list[dict], machine: str) -> list[str]:
    s = [r for r in rows if r["machine"] == machine]
    a = engine.analyze_stream(s, "strength", CFG["lsl"], CFG["baseline"], CFG["target"], CFG["usl"],
                              CFG["tests"], CFG["mr_rule"])
    d, c = a.desc, a.cap
    p, lo, hi = engine.wilson(a.passes, a.n)
    out = [f"  Machine {machine} · {a.n} builds"
           + (f" × {a.xs.typical_n} coupons ({len(a.values)} results)" if a.xs else "")
           + f" · chart: {a.chart} · variables recorded: {', '.join(engine.available_vars(engine.build_level(s)))}",
           f"    Verdict            : {engine.decision_text(a)}",
           f"    Strength           : mean {f(d['mean'], 1)} · median {f(d['median'], 1)} · SD {f(d['sd'], 2)} · "
           f"variance {f(d['variance'], 1)} · CV {f(d['cv_pct'], 2)}% · SE {f(d['se_mean'], 3)} MPa",
           f"    Spread             : range {f(d['range'], 1)} ({f(d['min'], 1)}–{f(d['max'], 1)}) · "
           f"Q1 {f(d['q1'], 1)} · Q3 {f(d['q3'], 1)} · IQR {f(d['iqr'], 1)} MPa",
           (f"    X̄-S (baseline)    : x̿ {f(a.xs.center, 1)} · σ̂ within {f(a.xs.sigma, 2)} ({a.xs.method}) · "
            f"X̄ LCL {f(a.xs.x_lcl[0], 1)} · UCL {f(a.xs.x_ucl[0], 1)} · S̄ {f(a.xs.s_bar, 2)} · S UCL {f(a.xs.s_ucl[0], 2)}"
            if a.xs else
            f"    I chart (baseline) : centre {f(a.center, 1)} · σ {f(a.sigma, 2)} · LCL {f(a.lcl, 1)} · UCL {f(a.ucl, 1)} · "
            f"MR̄ {f(a.mr_bar, 2)} · MR UCL {f(a.mr_ucl, 1)}"),
           f"    Capability         : Cp {f(c['Cp'])} · Cpk {f(c['Cpk'])} · Pp {f(c['Pp'])} · Ppk {f(c['Ppk'])} "
           f"(target Cpk ≥ {CFG['target']})",
           f"    Conformance        : {a.passes}/{a.n} builds in spec ({f(100 * p, 1)}%, 95% Wilson {f(100 * lo, 1)}–{f(100 * hi, 1)}%)"
           + (f" · failed: {', '.join(r['id'] for r in a.fails)}" if a.fails else ""),
           f"    Distribution       : Anderson-Darling A² {f(a.normal['ad'], 3)}, p {pv(a.normal['p'])} → "
           f"{'consistent with normal' if a.normal['normal'] else 'NOT normal'} · expected out of spec "
           f"{f(a.expected['within']['total_ppm'], 1)} ppm (within σ) / {f(a.expected['overall']['total_ppm'], 1)} ppm (overall s)"
           f" · observed {sum(v < a.lsl or (a.usl is not None and v > a.usl) for v in a.values)} of {len(a.values)} results"]
    if a.flags:
        first = a.flags[0]
        counts = {k: v for k, v in a.test_counts().items() if v}
        out.append(f"    Strength signals   : {len(a.flags)} builds; first at build {first.index + 1} "
                   f"({a.records[first.index]['id']}: {'; '.join(first.reasons)})")
        out.append("    Points per test    : " + ", ".join(f"{k if k in ('MR', 'S') else 'Test ' + str(k)}={v}" for k, v in counts.items()))
        if a.xs:
            fx = min(a.xs.x_hits) + 1 if a.xs.x_hits else None
            fs = min(a.xs.s_hits) + 1 if a.xs.s_hits else None
            out.append(f"    First X̄ / S signal : build {fx} / build {fs}")
    else:
        out.append("    Strength signals   : none")
    for v in engine.available_vars(s)[1:]:
        am = engine.analyze_stream(s, v, CFG["lsl"], CFG["baseline"], CFG["target"], CFG["usl"], CFG["tests"], CFG["mr_rule"])
        if am.flags:
            fs = am.flags[0]
            out.append(f"    {engine.VARS[v][0]:<19}: {len(am.flags)} signal(s); first at build {fs.index + 1} ({'; '.join(fs.reasons)})")
    assoc = engine.associations(engine.build_level(s))
    if assoc:
        out.append("    Top associations   : " + ", ".join(f"{engine.VARS[x['v']][0].lower()} r = {f(x['r'])}" for x in assoc[:3]))
    else:
        out.append("    Top associations   : none (only strength recorded)")
    return out


def main():
    print("FORGE SENTINEL — DEMONSTRATION REPORT")
    print(f"Settings: LSL {CFG['lsl']:g} MPa · USL {CFG['usl']:g} MPa · baseline {CFG['baseline']} builds · "
          f"tests {','.join(map(str, CFG['tests']))} + MR rule · Cpk target {CFG['target']}")
    for name, title in DATASETS:
        rows = data.parse_csv((ROOT / "datasets" / name).read_bytes())
        print("\n" + "=" * 100)
        print(f"{name} — {title}")
        print("=" * 100)
        for m in data.machine_list(rows):
            print("\n".join(describe_machine(rows, m)))


if __name__ == "__main__":
    main()
