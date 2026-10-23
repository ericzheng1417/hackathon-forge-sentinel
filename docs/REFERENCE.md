# Function reference

How each part of Forge Sentinel works: inputs, parameters, outputs and the formulas behind them.
For a user-level introduction see the [README](../README.md); for the data format see
[datasets/CODEBOOK.md](../datasets/CODEBOOK.md).

```
app.py                        Shiny UI + server: state, events, dialogs, uploads, downloads
forge_sentinel/engine.py      Statistics (standard library only) — used by the app AND the CLI
forge_sentinel/data.py        Demo data, CSV / Excel validation and import, CSV / Excel export
forge_sentinel/exports.py     Printable HTML report, Excel workbook, JSON report
forge_sentinel/charts.py      SVG charts (I chart, MR chart, histogram, box plot, scatter)
forge_sentinel/views.py       HTML for each page (pure functions; no Shiny import)
python/analyze.py             Command-line interface
datasets/generate_datasets.py Reproducible test-data generator
demo/run_demo.py              Text demonstration on the three test datasets
```

**Data flow:** CSV or Excel → `data.read_upload` → rows (list of dicts) → filter to one machine →
`engine.analyze_stream` → `Analysis` → `views.render_page` / `charts.*` → HTML shown by `app.py`.
Exports: rows + settings → `exports.build_context` → `html_report` / `excel_report` / `json_report`.

---

## Quick start (Python)

```python
from forge_sentinel import data, engine

rows = data.parse_csv(open("datasets/02_oxygen_drift.csv", "rb").read())
a = engine.analyze_stream(rows, "strength", lsl=900, usl=1100)

engine.decision_text(a)          # 'Process unstable — capability not demonstrated'
a.cpk, a.cap["Ppk"]              # (2.04, 0.95)  (rounded)
a.flags[0].index + 1             # 49   ← first flagged build (1-based)
a.flags[0].tests                 # [1, 'MR']
engine.associations(rows)[0]     # {'v': 'oxygen', 'r': -0.839, 'n': 70}
```

---

## `forge_sentinel/engine.py`

### Constants

| Name | Value / meaning |
|---|---|
| `VARS` | `{key: (label, unit)}` for the 7 measured variables: `strength`, `oxygen`, `humidity`, `temperature`, `power`, `speed`, `stress` |
| `FIELDS` | The 7 variable keys, in order |
| `COLUMNS` | `("id", "machine", *FIELDS)` |
| `REQUIRED_COLUMNS` | `("id", "machine", "strength")`, the only inputs a user must supply |
| `OPTIONAL_FIELDS` | The 6 process variables (all except strength) |
| `MIN_VALUES` | `10`: a variable needs this many recorded values to be charted or correlated |
| `ALL_TESTS` | `(1, 2, 3, 4, 5, 6, 7, 8)` |
| `DEFAULT_CONFIG` | `lsl` 900, `usl` 1100, `target` 1.33, `baseline` 25, `oxygen` 100, `humidity` 40, `tests` 1–8, `mr_rule` True |
| `D2`, `D4` | 1.128 and 3.267, control-chart constants for moving ranges of 2 |
| `SPECIAL_TESTS` | `{n: (short name, pattern, what it usually signals)}` for the 8 tests |

### `present(v) -> bool`
True if a value was recorded (not `None` and not an empty string).

### `available_vars(records) -> list[str]`
| | |
|---|---|
| **records** | list of row dicts for one machine |
| **returns** | variable keys with at least `MIN_VALUES` recorded values; `strength` is always included |

### `describe(values) -> dict`
Descriptive statistics. Blank values are ignored.

| Output key | Formula |
|---|---|
| `n` | number of recorded values |
| `mean` | x̄ = Σx / n |
| `median` | middle ordered value (average of the two middle values when n is even) |
| `sd` | sample standard deviation s = √[Σ(x − x̄)² / (n − 1)] |
| `variance` | s² |
| `cv_pct` | coefficient of variation = s / \|x̄\| × 100 |
| `se_mean` | standard error of the mean = s / √n |
| `min`, `max`, `range` | smallest, largest, max − min |
| `q1`, `q3`, `iqr` | quartiles by the inclusive method (Excel `QUARTILE.INC`), IQR = Q3 − Q1 |

Example: `describe([2, 4, 4, 4, 5, 5, 7, 9])` → mean 5, median 4.5, variance 4.571, q1 4, q3 5.5.

### `special_cause_tests(x, center, sigma, tests=ALL_TESTS) -> dict[int, list[int]]`
Applies the 8 tests for special causes (Western Electric / Nelson rules) to an individuals series.

| Parameter | Meaning |
|---|---|
| **x** | values in time order |
| **center** | centre line (baseline mean) |
| **sigma** | baseline σ; zones are C = within 1σ, B = 1–2σ, A = 2–3σ |
| **tests** | which test numbers to apply |
| **returns** | `{point index: [test numbers]}` for flagged points (0-based index) |

A point is flagged when it **completes** the pattern:

| Test | Flags point *i* when… |
|---|---|
| 1 | \|zᵢ\| > 3 (beyond zone A), where zᵢ = (xᵢ − center) / σ |
| 2 | 2 of the last 3 points are beyond 2σ on the same side, and point *i* is one of them |
| 3 | 4 of the last 5 points are beyond 1σ on the same side, and point *i* is one of them |
| 4 | the last 8 points are all above, or all below, the centre line |
| 5 | the last 6 points are strictly increasing or strictly decreasing |
| 6 | the last 15 points are all within 1σ (zone C) |
| 7 | the last 8 points are all beyond 1σ, with points on both sides of the centre line |
| 8 | the last 14 points alternate up and down |

Tests 1, 2, 3, 6 and 7 need σ > 0; they are skipped if σ is 0.
Example: `special_cause_tests([0.1, 2.5, 0.2, 2.2], 0, 1, [2])` → `{3: [2]}`.

### `moving_ranges(x) -> list`
MRᵢ = |xᵢ − xᵢ₋₁|; the first element is `None`.

### `capability(mean, sigma_within, sigma_overall, lsl, usl) -> dict`

| Output | Formula |
|---|---|
| `Cp` | (USL − LSL) / 6σ_within |
| `Cpl`, `Cpu` | (x̄ − LSL) / 3σ_within, (USL − x̄) / 3σ_within |
| `Cpk` | min(Cpl, Cpu) |
| `Pp`, `Ppl`, `Ppu`, `Ppk` | same formulas using σ_overall (sample SD of all builds) |

If `usl` is `None` (one-sided specification), `Cp`, `Cpu`, `Pp` and `Ppu` are NaN, and `Cpk` = `Cpl`.
Example: `capability(1000, 10, 20, 940, 1090)` → Cp 2.5, Cpk 2.0, Pp 1.25, Ppk 1.0.

### `analyze_stream(records, metric="strength", lsl=900, baseline=25, target=1.33, usl=None, tests=ALL_TESTS, mr_rule=True) -> Analysis`
The main analysis for **one machine**.

| Parameter | Meaning |
|---|---|
| **records** | that machine's rows, in build order |
| **metric** | variable to chart; rows where it is blank are skipped |
| **lsl / usl** | strength specification limits (MPa); `usl=None` means one-sided |
| **baseline** | first N recorded builds used to freeze the centre line and limits; reduced automatically if the metric has fewer values |
| **target** | Cpk target used by `decision_text` |
| **tests** | which of the 8 tests to apply |
| **mr_rule** | also flag moving ranges above the MR-chart UCL |

Steps:
1. Baseline: x̄ = mean of the first N values; MR̄ = mean moving range within the baseline; σ = MR̄ / 1.128.
2. Limits: I chart x̄ ± 3σ; MR chart UCL = 3.267 × MR̄, LCL = 0.
3. Signals: `special_cause_tests` on every point (baseline included), plus the MR rule.
4. Capability: `capability()` on **strength** (always the full stream), using baseline σ and overall SD.
5. Descriptives: `describe()` on the metric.
6. Failures: strength < LSL or > USL.

### `Analysis` (returned object)

| Field / property | Meaning |
|---|---|
| `records`, `x` | rows with the metric recorded, and their values |
| `idx` | `idx[i]` = position of `records[i]` in the full machine stream (used for click-through) |
| `n_missing` | builds skipped because the metric was blank |
| `baseline`, `center`, `sigma`, `lcl`, `ucl` | I-chart parameters |
| `mr`, `mr_bar`, `mr_ucl` | moving ranges and MR-chart parameters |
| `flags` | list of `Signal(index, tests, reasons)` |
| `post` / `baseflags` | signals after / within the baseline |
| `stable` | True if there are no signals at all |
| `cap` | dict from `capability()`; shortcuts `cpk`, `cpl`, `ppl` |
| `desc` | dict from `describe()` |
| `fails`, `passes`, `is_fail(row)` | out-of-spec builds |
| `test_counts()` | `{test number or "MR": points flagged}` |
| `avg`, `overall_sd`, `n` | overall mean, sample SD, count |

### `wilson(successes, n, z=1.96) -> (p, low, high)`
Observed proportion and 95% Wilson score interval:
centre = (p + z²/2n) / (1 + z²/n), half-width = z·√[p(1−p)/n + z²/4n²] / (1 + z²/n).
Example: `wilson(67, 70)` → (0.957, 0.881, 0.985).

### `pearson(a, b) -> float` and `associations(records) -> list[dict]`
`pearson` is the Pearson correlation coefficient (NaN if either series is constant). `associations`
correlates each optional variable with strength, using rows where both are recorded, skips variables
with fewer than `MIN_VALUES` pairs, and sorts by |r| (strongest first).
Each item: `{"v": key, "r": correlation, "n": pairs}`.

### `decision_text(a) -> str`
- Any signal → *Process unstable — capability not demonstrated*
- otherwise Cpk < target → *Capability below target — investigate variation*
- otherwise → *No SPC signals detected — qualification review required*

### `report(a, *, source, machine, config, actions, generated_at) -> dict`
The JSON behind **Export report**: configuration, decision, statistics, descriptive statistics per
variable, capability, control-chart parameters, signals (build, phase, tests, reasons), associations,
corrective actions and the records. NaN/∞ become `null`.

### `analyze(records, lsl=900, baseline=25, target=1.33, usl=None, tests=ALL_TESTS, mr_rule=True) -> dict`
The CLI report for a strength stream: n, mean, baseline mean/σ, overall SD, Cp/Cpk/Cpl/Cpu/Pp/Ppk/Ppl/Ppu,
descriptive statistics, failures, pass rate, Wilson interval, tests applied, signals,
`stable_under_selected_rules` and `capability_screen_passed` (stable **and** Cpk ≥ target).
It raises `ValueError` if the baseline is < 10 or ≥ n, if strength is not positive, or if baseline σ is 0.

---

## `forge_sentinel/data.py`

| Function | Inputs → output | Notes |
|---|---|---|
| `read_upload(raw, filename)` | bytes + file name → rows | Routes `.xlsx`/`.xlsm` to `parse_excel` and everything else to `parse_csv`; rejects old `.xls` with a re-save hint. |
| `parse_excel(raw)` | `.xlsx` bytes → rows | Needs `openpyxl`. Uses the first worksheet whose first non-empty row contains id/machine/strength (otherwise the first sheet); reads stored values (formula cells use the value Excel last saved); converts numbers stored as whole floats to text IDs, dates to ISO text; pads ragged rows. Then applies `validate_table`. 5 MB limit. |
| `validate_table(lines)` | list of text rows (header first) → rows | The shared validation used by both CSV and Excel (the rules listed for `parse_csv`). |
| `parse_csv(raw)` | bytes or str → list of row dicts | Requires `id`, `machine`, `strength`; the 6 optional columns may be absent or blank (stored as `None`); extra columns are ignored; headers are case-insensitive. Rejects files over 2 MB, non-numeric values, out-of-range values (strength ≤ 0, oxygen < 0, humidity outside 0–100, power or speed ≤ 0), duplicate IDs within a machine, fewer than 30 rows per machine, and zero strength variation in the first 25 builds. Raises `ImportError_` with a message naming the row. |
| `to_csv(rows)` | rows → CSV text | Writes the required columns plus any optional column that has values; blanks for `None`. |
| `to_xlsx(rows)` | rows → `.xlsx` bytes | Same columns as `to_csv`, bold header, frozen header row. Needs `openpyxl`. |
| `SAMPLE_DATASETS` | dict | `{key: (file name, display name)}` for the test datasets offered in the Import dialog. |
| `machine_list(rows)` | rows → machine names | In order of first appearance. |
| `seed_rows()` | → rows | Built-in demo data shown when the app opens (LPBF-01 deteriorates after build 39; LPBF-02 is stable). |

## `forge_sentinel/exports.py`

All three exports are built from one context, so they agree with each other and with the dashboard.

| Function | Inputs → output | Notes |
|---|---|---|
| `build_context(stream, cfg, *, machine, source, actions, tasks, generated_at)` | one machine's rows + settings → `ReportContext` | Runs the strength analysis, an analysis for every recorded process variable, `describe()` per variable, `associations()` and the Wilson interval, all with the dashboard's current settings. |
| `html_report(ctx)` | → HTML text | Self-contained printable report: header and settings, verdict, KPI tiles, I and MR charts, the 8-test table and strength signal log, capability (histogram + indices), out-of-spec builds, early warnings on process variables, associations + scatter, descriptive statistics, corrective actions, method and limitations. A4 print stylesheet; about 5 pages; a "Print / Save as PDF" button (hidden when printing). |
| `excel_report(ctx)` | → `.xlsx` bytes | Sheets: **Summary** (settings, key metrics, native line chart of strength with centre/UCL/LCL/LSL), **Data** (every build with process variables, control limits, moving range, PASS/FAIL, phase, signals; failures shaded; filter on), **Statistics**, **Capability** (indices + inputs + Wilson), **Signals** (strength and process variables, plus counts per test), **Associations**, **Corrective actions**. Needs `openpyxl`. |
| `json_report(ctx)` | → JSON text | `engine.report()` plus `process_variable_signals` and `conformance` (pass rate, Wilson interval, failed builds). |
| `key_metrics(ctx)` | → list of (label, value, note) | Used by both the HTML and Excel summaries. |
| `early_warnings(ctx)` | → list of dicts | Process variables with signals: count, first flagged build, reasons, r with strength, and how many builds before the first strength signal. Ranked by \|r\| so the likely cause comes first. |

## `forge_sentinel/charts.py`

All functions return an SVG string. Clicking a point calls `fsBuild(i)` with the build's position in the stream.

| Function | Draws |
|---|---|
| `control_chart(a, lsl, usl=None, zones=True)` | I chart: baseline shading, ±1σ/±2σ zone lines labelled A/B/C, UCL/mean/LCL, spec lines (strength only), flagged points in red |
| `mr_chart(a)` | MR chart with MR̄, UCL and LCL = 0 |
| `histogram(x, label, lsl=None, usl=None, bins=None, width=350)` | histogram; bars outside the spec are shaded red |
| `boxplot(x, desc, label, idx=None)` | box (Q1–Q3), median line, mean diamond, 1.5×IQR whiskers, jittered points (outliers red) |
| `scatter(a, lsl, var="oxygen")` | `var` against strength; failing builds red |
| `fmt(n, d)`, `num(v)` | number formatting (`—` for missing or non-finite values) |

## `forge_sentinel/views.py`

Pure functions that return HTML strings. `render_page(page, a, am, cfg, actions, all_desc)` dispatches to:
`overview`, `control`, `statistics_page`, `capability`, `parameters`, `records`, `tasks`, `methods`.
Here `a` is the strength analysis, `am` the analysis of the selected variable, and `all_desc` maps each
variable to its `describe()` output. `build_detail(a, i)` builds the pop-up for one build.

## `app.py` (Shiny server)

| Piece | Role |
|---|---|
| reactive state | `rows`, `source`, `page`, `machine`, `metric`, `cfg` (one copy per browser session) |
| `stream()`, `a()`, `am()`, `avail()` | the selected machine's rows, the strength analysis, the selected-variable analysis, the recorded variables |
| `input.fs_evt` | a single event channel: `nav`, `machine`, `metric`, `build`, `open`, `apply_config`, `sample`, `restore_demo`, `action` |
| `input.upload` | CSV or Excel upload → `read_upload` → replaces `rows` for this session |
| `SAMPLES` | the three test datasets offered in the Import dialog |
| downloads | `export_report` (printable HTML), `export_excel` (workbook), `export_json`, `download_csv`, `download_example` (CSV), `download_example_xlsx`, `download_source` (zip). Report file names include the machine and date. |
| `ActionStore` | corrective-action status and notes in `data/actions.json`; set the `FORGE_ACTIONS_FILE` environment variable to store them elsewhere |

**Configure dialog parameters**

| Setting | Range | Default |
|---|---|---|
| LSL (MPa) | 1–2000 | 900 |
| USL (MPa), 0 = none | 0–5000, must be > LSL | 1100 |
| Cpk target | 0.1–5 | 1.33 |
| Baseline builds | 10 to n − 1 | 25 |
| Oxygen alarm (ppm) | 1–10000 | 100 |
| Humidity alarm (%) | 1–100 | 40 |
| Tests 1–8 | checkboxes | all on |
| Moving-range rule | checkbox | on |

## `python/analyze.py` (command line)

```
python python/analyze.py CSV --machine NAME [--lsl 900] [--usl 1100] [--baseline 25]
                             [--target 1.33] [--tests 1,2,3,4,5,6,7,8] [--no-mr]
```

| Argument | Meaning |
|---|---|
| `CSV` | path to a build file: `.csv`, or `.xlsx` (needs `openpyxl`); see the codebook |
| `--machine` | machine to analyse (required) |
| `--lsl`, `--usl` | specification limits in MPa; omit `--usl` for a one-sided spec |
| `--baseline` | number of baseline builds (≥ 10 and < n) |
| `--target` | Cpk target for `capability_screen_passed` |
| `--tests` | comma-separated special-cause tests |
| `--no-mr` | don't flag moving ranges |

The output is JSON from `engine.analyze()` on stdout. It uses only the standard library.

## `datasets/generate_datasets.py`
`python datasets/generate_datasets.py` rewrites the three test CSVs. Each scenario function
(`stable_capable`, `oxygen_drift`, `strength_only`) draws from normal distributions around `NOMINAL`
with a fixed seed from `SEEDS` and adds the scenario's effect. See [datasets/README.md](../datasets/README.md).

## `demo/run_demo.py`
`python demo/run_demo.py` prints a text report for every machine in every test dataset (verdict,
descriptive statistics, I-MR parameters, capability, conformance, signals per test, signals on
process variables, top associations), using `DEFAULT_CONFIG`.

## Tests
`python -m unittest discover tests`:
- `test_engine.py` covers parity with the original JavaScript calculations, each of the 8 tests,
  descriptive statistics, Cp/Cpk, CSV validation, optional columns, page rendering and the CLI.
- `test_datasets.py` checks that the datasets regenerate byte for byte and give the documented results.
- `test_exports.py` covers Excel import (round trip, the shipped `.xlsx`, a messy real-world workbook, bad files,
  CLI), the HTML report, the JSON report and the Excel workbook. Excel tests are skipped if `openpyxl` is missing.
