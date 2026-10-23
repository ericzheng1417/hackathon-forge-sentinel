# Test datasets

Four synthetic datasets for trying out and checking Forge Sentinel. Each one represents a different
situation a titanium-bracket contractor could face, and each produces a known result that the
automated tests in `tests/test_datasets.py` check.

| File | Machines | Rows | Columns | Scenario | What the tool should conclude |
|---|---|---|---|---|---|
| [`01_stable_capable.csv`](01_stable_capable.csv) | LPBF-A, LPBF-B | 50 + 50 | all | Healthy process | Stable on both machines, Cpk ≈ 1.9 (≥ 1.33), no failures |
| [`02_oxygen_drift.csv`](02_oxygen_drift.csv) | LPBF-C | 70 | all | Chamber leak, then repair | Oxygen flagged at build 44, strength at build 49; 3 failures; oxygen is the top suspect (r = −0.84) |
| [`03_strength_only.csv`](03_strength_only.csv) | LPBF-D | 60 | id, machine, strength | Powder-lot change, minimal data | Shift caught at build 36, before any part fails; Ppk 0.64 |
| [`04_coupon_spread.csv`](04_coupon_spread.csv) | LPBF-E | 40 builds × 4 coupons = 160 | all + `coupon` | Uneven gas flow across the plate | **X̄-S chart**: S chart flags at build 30, X̄ only at 34; 2 builds have a failing coupon; data not normal |
| [`02_oxygen_drift.xlsx`](02_oxygen_drift.xlsx) | LPBF-C | 70 | all | Excel copy of file 02 | Identical results; demonstrates Excel import |

Every variable is defined in **[CODEBOOK.md](CODEBOOK.md)**.

## How to use them

- **In the app:** click **Import data**, then one of the **Try a test dataset** buttons. The badge at the top
  shows which dataset is loaded. You can also upload the CSV files, or `02_oxygen_drift.xlsx`, directly.
- **From the command line:**
  ```
  python python/analyze.py datasets/02_oxygen_drift.csv --machine LPBF-C --usl 1100
  ```
- **Walkthrough:** [DEMO.md](../DEMO.md) goes through all three with screenshots.

All results below use the app's default settings: LSL 900 MPa, USL 1100 MPa, Cpk target 1.33,
baseline = first 25 builds, all 8 tests plus the moving-range rule.

---

## 01 — Stable and capable (`01_stable_capable.csv`)

**Story.** Two printers running the same qualified bracket process. Builds vary only by normal,
random (common-cause) variation. LPBF-B runs about 6 MPa weaker than LPBF-A on average, which is
normal machine-to-machine variation, but both are well inside specification.

**Expected results**

| | LPBF-A | LPBF-B |
|---|---|---|
| Mean strength (MPa) | 968.5 | 958.8 |
| Standard deviation (MPa) | 10.9 | 10.8 |
| Strength signals | none | none |
| Cp / Cpk | 2.77 / 1.89 | 3.13 / 1.84 |
| Pp / Ppk | 3.07 / 2.10 | 3.10 / 1.82 |
| Failures | 0 | 0 |
| Verdict | No SPC signals — qualification review required | same |

**Teaching point.** A few secondary variables still show isolated signals on LPBF-A (one power moving
range, two residual-stress points). With 7 variables × 8 tests there are many chances for a false
alarm, so isolated signals on a stable process are expected. Strength is the variable that decides
capability.

## 02 — Oxygen drift (`02_oxygen_drift.csv`)

**Story.** One printer. From build 41 a chamber door seal starts leaking: oxygen rises by about
4.5 ppm per build and humidity creeps up with it. Above about 70 ppm, oxide films and lack-of-fusion
porosity start to reduce tensile strength. The seal is replaced after build 60, and builds 61–70 are
back to normal.

**Expected results**

- **Oxygen** is flagged first, at **build 44** (Tests 1, 2 and 5). That is **5 builds before** strength.
- **Strength** is first flagged at **build 49**. Signals continue through the leak period.
- **Failures:** C-056, C-057 and C-060 fall below 900 MPa.
- **Cpk 2.04 but Ppk 0.95.** Cpk uses the short-term spread of the clean baseline, while Ppk uses the
  overall spread including the drift, which reveals the problem. The verdict is *Process unstable —
  capability not demonstrated*.
- **Parameter analysis** ranks **oxygen** as the strongest association (r = −0.84), pointing the
  engineer at the chamber atmosphere. The *Investigate chamber atmosphere* corrective action matches.
- No strength signals before the leak or after the repair, so you can see the fix working.

**Physics note.** Oxygen *dissolved* in titanium actually raises strength (and lowers ductility).
This scenario models the other effect of a poor build atmosphere: oxidised spatter and
lack-of-fusion porosity, which lower tensile strength. The size of the effect is illustrative.

## 03 — Strength only (`03_strength_only.csv`)

**Story.** A contractor that only records what the client requires: build ID, machine and tensile
strength. After build 35 a new powder lot is introduced, and mean strength drops from about 968 to
922 MPa.

**Expected results**

- The step is caught at **build 36**, the first build made with the new lot (Test 1 plus the
  moving-range rule). Tests 2, 3 and 4 confirm it over the following builds.
- **No part has failed yet.** The tool flags the problem before the client's strength tests would.
- **Ppk 0.64:** at the new level, failures are expected soon.
- Pages that need process variables (Parameter analysis, the variable selectors) say that only strength
  was provided instead of failing.

This dataset shows the **minimum input** the tool needs.

## 04 — Four coupons per build (`04_coupon_spread.csv`)

**Story.** The contractor pulls **four tensile coupons from every build**, at plate positions P1–P4, and records
each one (one row per coupon, with a `coupon` column). From build 26 the argon flow across the plate starts to
degrade, for example from a partly blocked nozzle. Coupons far from the gas inlet (P4, and P3 to a lesser extent)
lose strength build after build. Coupons near the inlet (P1, P2) are unaffected. The build *average* falls
slowly, but the spread *within* each build grows quickly.

**Expected results**

- The tool switches to an **X̄-S chart** automatically (one subgroup = one build's 4 coupons).
  Within-build σ̂ = s̄ / c₄(4) = **7.95 MPa**; X̄ limits 955.9–979.7 MPa; S chart UCL **16.60 MPa**.
- The **S chart flags first, at build 30**. The X̄ chart doesn't flag until **build 34**, and neither would an
  I-MR chart of the build averages. Watching spread gives 4 builds' extra warning.
- **Failures:** builds E-037 and E-040 each have a P4 coupon below 900 MPa, even though their *averages* pass.
  A build counts as failed if any coupon is out of spec.
- **Distribution:** the 160 coupon strengths are **not normal** (Anderson-Darling p < 0.005; long lower tail). A
  normal fit predicts only about 19 ppm out of spec, but the observed rate is 2 of 160 coupons (12,500 ppm). This
  shows why the normality check matters before trusting capability figures.
- Capability: Cp 4.19, Cpk 2.66, Pp 2.16, Ppk 1.37. Cpk looks excellent because within-build σ̂ is estimated from
  the clean baseline; the unstable verdict and the failures tell the real story.

**Physics note.** Uneven shielding-gas flow across a large build plate is a known cause of position-dependent
properties in LPBF. Spatter and fumes aren't cleared evenly, so some regions get more defects. The effect size
here is illustrative.

---

## How the data was generated

All three files are **synthetic**. They were produced by [`generate_datasets.py`](generate_datasets.py),
which uses only the Python standard library:

```
python datasets/generate_datasets.py
```

- Each build's variables are drawn from normal distributions around the nominal values listed in the
  script (`NOMINAL`), then the scenario's effect is added (seal leak, powder lot change).
- Each scenario uses a **fixed random seed**, so the files are identical on every run.
  `tests/test_datasets.py` regenerates them and checks they match byte for byte.
- **Seed choice.** Random data sometimes produces chance signals. The seeds were chosen by scanning
  candidates so that each file tells a clean story: no strength false alarms in the stable file, and
  no signals before the leak or after the repair in the drift file. This keeps the demonstration easy
  to follow. Real data will contain occasional false alarms.
- Values are rounded to one decimal place, like typical machine logs and test reports.
- File 04 adds within-build structure: each build has a small common effect (SD 1.5 MPa) shared by its four
  coupons, plus independent coupon noise (SD 7 MPa), and the position-dependent loss from build 26.
- If `openpyxl` is installed, the script also writes `02_oxygen_drift.xlsx`, an Excel copy of file 02 with the
  same cell values. Excel files store a save timestamp, so its bytes differ between runs, but its contents
  don't. `tests/test_exports.py` checks that it imports identically to the CSV.

**These values are illustrative.** They are plausible for a hot-isostatically-pressed or
stress-relieved Ti-6Al-4V LPBF process, but they are not material allowables, and the effect sizes
are not measured relationships.

## Using your own data

Follow the same column names and units (see [CODEBOOK.md](CODEBOOK.md)). Only `id`, `machine` and
`strength` are required. Keep rows in build order, use one row per build, and include at least
30 builds per machine.
