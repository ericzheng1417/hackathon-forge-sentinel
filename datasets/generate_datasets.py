"""Generate the Forge Sentinel test datasets (synthetic, fully reproducible).

Usage (from the repository root):
    python datasets/generate_datasets.py

Writes three CSV files next to this script. Python standard library only; each
scenario uses a fixed random seed, so the CSV files are byte-for-byte identical on
every run. If the openpyxl package is installed it also writes an Excel copy of the
oxygen-drift dataset (02_oxygen_drift.xlsx) to demonstrate Excel import; its cell
values are identical to the CSV (Excel files embed a save timestamp, so their bytes differ). See datasets/README.md for the scenarios and datasets/CODEBOOK.md for
every variable.
"""
from __future__ import annotations

import csv
import datetime as dt
import pathlib
import random

OUT = pathlib.Path(__file__).resolve().parent
FULL_COLUMNS = ["id", "machine", "build_date", "strength", "oxygen", "humidity", "temperature", "power",
                "speed", "stress"]

# Nominal process for HIP'd / stress-relieved Ti-6Al-4V LPBF brackets (illustrative values)
NOMINAL = {
    "strength": (968.0, 11.0),    # ultimate tensile strength, MPa (mean, SD)
    "oxygen": (60.0, 6.0),        # build-chamber oxygen, ppm
    "humidity": (35.0, 2.5),      # build-room relative humidity, %
    "temperature": (200.0, 2.0),  # build-plate temperature, °C
    "power": (280.0, 2.5),        # laser power, W
    "speed": (1200.0, 15.0),      # scan speed, mm/s
    "stress": (135.0, 12.0),      # residual stress, MPa
}
# Seeds were chosen (by scanning candidate seeds) so each scenario tells a clean story:
# no strength false alarms in the stable file, and no signals before the leak or after the repair
# in the drift file; in the coupon file the S chart flags before the X̄ chart. See datasets/README.md.
SEEDS = {"stable": 231, "drift": 2570, "minimal": 20263, "coupons": 1367}
COUPON_COLUMNS = ["id", "machine", "coupon", "build_date", "strength", "oxygen", "humidity", "temperature", "power",
                  "speed", "stress"]


def r1(v: float) -> float:
    return round(v, 1)


def nominal_build(rng: random.Random) -> dict:
    return {k: rng.gauss(m, s) for k, (m, s) in NOMINAL.items()}


def dates(n: int, start: dt.date, every_days: int = 1) -> list[str]:
    return [(start + dt.timedelta(days=i * every_days)).isoformat() for i in range(n)]


def write(name: str, rows: list[dict], columns: list[str]) -> pathlib.Path:
    path = OUT / name
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=columns, lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({c: (r1(r[c]) if isinstance(r[c], float) else r[c]) for c in columns})
    return path


def stable_capable() -> list[dict]:
    """Two machines in statistical control, comfortably inside a 900–1100 MPa spec."""
    rng = random.Random(SEEDS["stable"])
    rows = []
    for machine, shift, n in (("LPBF-A", 0.0, 50), ("LPBF-B", -6.0, 50)):
        for i, day in enumerate(dates(n, dt.date(2026, 6, 1))):
            b = nominal_build(rng)
            b["strength"] += shift - 0.15 * (b["oxygen"] - 60)      # mild, realistic dependence
            rows.append({"id": f"{machine[-1]}-{i + 1:03d}", "machine": machine, "build_date": day, **b})
    return rows


def oxygen_drift() -> list[dict]:
    """One machine: a chamber seal starts leaking at build 41, oxygen climbs, strength falls;
    the seal is replaced after build 60 and the process recovers for builds 61–70."""
    rng = random.Random(SEEDS["drift"])
    rows = []
    for i, day in enumerate(dates(70, dt.date(2026, 7, 1))):
        n = i + 1
        b = nominal_build(rng)
        leak = 4.5 * (n - 40) if 41 <= n <= 60 else 0.0          # ppm added by the leak
        b["oxygen"] += leak
        b["humidity"] += 0.12 * leak / 4.5                        # moist room air enters with it
        # oxide films / lack-of-fusion porosity above ~70 ppm reduce tensile strength
        b["strength"] -= 0.70 * max(0.0, b["oxygen"] - 70)
        b["stress"] += 0.08 * leak
        rows.append({"id": f"C-{n:03d}", "machine": "LPBF-C", "build_date": day, **b})
    return rows


def strength_only() -> list[dict]:
    """Minimal inputs (id, machine, strength). A new powder lot from build 36 lowers mean strength."""
    rng = random.Random(SEEDS["minimal"])
    rows = []
    for i in range(60):
        n = i + 1
        mean = 968.0 if n <= 35 else 922.0
        rows.append({"id": f"D-{n:03d}", "machine": "LPBF-D", "strength": rng.gauss(mean, 10.0)})
    return rows


def write_xlsx(name: str, csv_path: pathlib.Path) -> pathlib.Path | None:
    """Excel copy of a CSV (same header and values, numbers stored as numbers)."""
    try:
        import openpyxl
        from openpyxl.styles import Font
    except ImportError:
        print("openpyxl not installed: skipping the Excel copy")
        return None
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "builds"
    with csv_path.open(newline="", encoding="utf-8") as fh:
        for i, row in enumerate(csv.reader(fh)):
            if i == 0:
                ws.append(row)
                continue
            out = []
            for c in row:
                try:
                    out.append(float(c))
                except ValueError:
                    out.append(c)
            ws.append(out)
    for c in ws[1]:
        c.font = Font(bold=True)
    ws.freeze_panes = "A2"
    path = OUT / name
    wb.save(path)
    return path


def coupon_spread() -> list[dict]:
    """Four tensile coupons per build at plate positions P1–P4 (one row per coupon).

    From build 26 the argon gas flow across the plate degrades (e.g. a partly blocked
    nozzle): coupons far from the inlet (P4, and P3 less so) lose strength each build,
    so the spread within a build grows much faster than the build mean falls."""
    rng = random.Random(SEEDS["coupons"])
    rows = []
    for i, day in enumerate(dates(40, dt.date(2026, 8, 1))):
        n = i + 1
        b = nominal_build(rng)                       # build-level conditions, shared by the 4 coupons
        build_effect = rng.gauss(0, 1.5)             # small build-to-build variation of the mean
        k = max(0, n - 25)
        for pos, drop in (("P1", 0.0), ("P2", 0.0), ("P3", 1.5 * k), ("P4", 4.5 * k)):
            strength = 968 + build_effect + rng.gauss(0, 7) - drop
            rows.append({"id": f"E-{n:03d}", "machine": "LPBF-E", "coupon": pos, "build_date": day,
                         **{v: b[v] for v in NOMINAL if v != "strength"}, "strength": strength})
    return rows


def main():
    written = [
        write("01_stable_capable.csv", stable_capable(), FULL_COLUMNS),
        write("02_oxygen_drift.csv", oxygen_drift(), FULL_COLUMNS),
        write("03_strength_only.csv", strength_only(), ["id", "machine", "strength"]),
        write("04_coupon_spread.csv", coupon_spread(), COUPON_COLUMNS),
    ]
    xlsx = write_xlsx("02_oxygen_drift.xlsx", OUT / "02_oxygen_drift.csv")
    if xlsx:
        written.append(xlsx)
    for p in written:
        print(f"wrote {p.relative_to(OUT.parent)}")


if __name__ == "__main__":
    main()
