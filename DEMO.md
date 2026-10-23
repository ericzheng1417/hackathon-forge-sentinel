# Demonstration

This walkthrough uses the three test datasets in [`datasets/`](datasets/README.md) to show what Forge
Sentinel does for a contractor whose titanium brackets are failing client strength tests:

1. **Monitor:** is the printing process stable, and is it capable of meeting the specification?
2. **Flag:** when did it change, and which builds are affected?
3. **Help resolve:** which process condition is the likely cause, and what to do next?

Everything uses the default settings: LSL 900 MPa, USL 1100 MPa, Cpk target 1.33, baseline = first 25
builds, all 8 tests plus the moving-range rule.

## Reproduce it yourself

**In the dashboard** (locally with `shiny run app.py`, or on the deployed Posit Connect app): click
**Import data**, then pick one of the **Try a test dataset** buttons. To try Excel import, upload
`datasets/02_oxygen_drift.xlsx` instead; it gives the same results as the CSV.

**Without the dashboard:** run the same analysis from the command line (standard library only):

```
python demo/run_demo.py
```

The output is saved in [`demo/demo_output.txt`](demo/demo_output.txt). Every number quoted below comes
from it, and `tests/test_datasets.py` checks the key results automatically.

---

## Scenario 1 — A healthy process (`01_stable_capable.csv`)

*Question: if we're doing things right, does the tool say so?*

![Overview for the stable dataset, machine LPBF-A](docs/images/01_stable_overview.png)

**What the tool shows (LPBF-A):**
- **Verdict:** *No SPC signals detected — qualification review required.* No strength build trips any
  of the 8 tests.
- **Capability:** Cpk **1.89** and Ppk **2.10**, both above the 1.33 target. Short-term (within) and
  overall spread agree (σ 12.05 vs s 10.87 MPa), as expected for a stable process.
- **Pass rate:** 50/50. The 95% Wilson interval is 92.9–100%: even with no failures, 50 tests can't
  prove a 100% pass rate.
- Switch the **Machine** selector to **LPBF-B**: also stable, Cpk 1.84, running about 10 MPa weaker on
  average. That's worth knowing, but it's not a problem.

**What it tells the contractor:** the process is stable and capable on both machines. The numbers
support a qualification review, but they don't replace one.

---

## Scenario 2 — Finding the cause of failures (`02_oxygen_drift.csv`)

*Question: parts started failing. When did the process change, and why?*

### Step 1 — The overview raises the alarm

![Overview for the oxygen-drift dataset](docs/images/02_drift_overview.png)

- **Verdict:** *Process unstable — capability not demonstrated.* 13 monitored builds have special-cause
  signals, and 3 builds (C-056, C-057, C-060) are outside the 900–1100 MPa specification.
- The strength chart shows a clear dip in the middle of the run, followed by recovery.
- **Cpk 2.04 vs Ppk 0.95.** Cpk is calculated from the clean baseline (builds 1–25), so it reflects
  what the process *can* do. Ppk uses the overall spread, including the drift, so it shows what the
  process *actually* delivered. The card is labelled *Provisional* because capability means nothing
  for an unstable process.

### Step 2 — Process control pinpoints when

![I chart, MR chart and the 8 tests for strength](docs/images/03_drift_control_strength.png)

- The first strength signal is **build 49** (Test 1: beyond zone A, plus a moving-range jump).
- The **8-tests table** counts what fired: Test 1 = 11 points, Test 2 = 11, Test 3 = 9, Test 4 = 5,
  MR rule = 2. The **signal log** lists each flagged build with its reasons.
- The signals stop after build 61, which shows that whatever changed was fixed.

Now switch the variable selector to **Chamber oxygen**:

![I chart for chamber oxygen](docs/images/04_drift_control_oxygen.png)

- Oxygen is flagged at **build 44** (Tests 1, 2 and 5), **5 builds before strength**. Had the
  contractor been watching oxygen, they could have stopped the machine before any failing parts were made.

### Step 3 — Parameter analysis points to why

![Parameter analysis for the oxygen-drift dataset](docs/images/05_drift_parameters.png)

- **Chamber oxygen** has by far the strongest association with strength (**r = −0.84**). The next is
  humidity at −0.22, which rose with the leak.
- **12 builds** exceeded the 100 ppm oxygen alarm.
- The scatter plot shows strength falling as oxygen rises. All three failing builds (red) are among the
  highest-oxygen builds (above 130 ppm).

### Step 4 — Capability, statistics and next steps

![Capability page for the oxygen-drift dataset](docs/images/06_drift_capability.png)

The **Capability** page sets out every index (Cp 3.31, Cpk 2.04, Pp 1.54, Ppk 0.95). Its evidence
checklist shows the gap: the monitoring period is not free of signals, and Ppk is below target.

![Statistics page for the oxygen-drift dataset](docs/images/07_drift_statistics.png)

The **Statistics** page shows the descriptive picture: mean 961.5 vs median 968.1 MPa (the drift
pulls the mean down), SD 21.60 MPa, CV 2.25%, range 96.2 MPa. Compare that with SD 10.9 and CV 1.12% in the
stable dataset.

Finally, **Corrective actions** lists the response, starting with *Contain affected production* and
*Investigate chamber atmosphere* (check the oxygen sensor, purge logs, seals and gas flow). The engineer
records status and notes there.

### Step 5 — Share the findings

Click **Export report** and choose a format:

![The Export report dialog](docs/images/12_export_dialog.png)

**PDF report** opens the printable report in a new tab with the print dialog. Choose **Save as PDF** to
get a 5-page summary to send to the client or a manager.

![Page 1 of the printable report](docs/images/10_report_page1.png)

Page 1 has the verdict, key numbers and the I-MR charts. Later pages cover the 8 tests and signal log,
capability and out-of-spec builds, and **Where to look**. That section ranks process variables by their
link to strength, so chamber oxygen comes first, flagged 5 builds before strength:

![Page 3 of the printable report: capability and where to look](docs/images/11_report_page3.png)

The report ends with descriptive statistics, corrective-action status and notes, and the method and limitations.

**Excel workbook** downloads the same results as a workbook: a Summary sheet with a native Excel control chart, the full
build data with control limits and PASS/FAIL (failures shaded, filters on), and sheets for statistics,
capability, signals, associations and corrective actions. **JSON data** gives the same results in machine-readable form.

**What actually happened** (from the dataset design): a chamber seal began leaking at build 41 and was
replaced after build 60. The tool found the change, its timing and its cause from the data alone.

> Note: a few secondary variables (laser power, scan speed, residual stress) show isolated early
> signals. With 7 variables × 8 tests, occasional false alarms are expected, so the engineer should
> look for patterns that line up with strength.

---

## Scenario 3 — Minimal data, early warning (`03_strength_only.csv`)

*Question: what if the contractor only records strength?*

![Overview for the strength-only dataset](docs/images/08_minimal_overview.png)

![I chart for the strength-only dataset](docs/images/09_minimal_control.png)

- The file has only `id`, `machine` and `strength`. The tool still produces control charts, the 8 tests,
  descriptive statistics and capability indices.
- A mean shift is caught at **build 36**, the first build after the change (Test 1 plus a moving-range
  jump). Tests 2, 3 and 4 confirm it over the next few builds.
- **No part has failed yet** (60/60 pass), but **Ppk is 0.64**: at the new level, failures are coming.
  The tool gives the warning before the client's acceptance tests would.
- **Parameter analysis** explains that only strength was provided and suggests which process columns to
  record next, so the contractor can find the cause next time.

**What actually happened:** a new powder lot was introduced at build 36 and lowered mean strength by
about 46 MPa.

---

## Command-line demo

The same engine works without the dashboard, for example in a nightly job:

```
$ python python/analyze.py datasets/02_oxygen_drift.csv --machine LPBF-C --usl 1100
{
  "n": 70,
  "mean": 961.54...,
  "Cp": 3.31..., "Cpk": 2.04..., "Pp": 1.54..., "Ppk": 0.95...,
  "failed_strength_tests": 3,
  "tests_applied": [1, 2, 3, 4, 5, 6, 7, 8, "MR"],
  "signals": [{"build": "C-049", "phase": "monitoring", "tests": [1, "MR"], ...}, ...],
  "stable_under_selected_rules": false,
  "capability_screen_passed": false,
  ...
}
```

(Output shortened; the full JSON also includes descriptive statistics, the pass rate and the Wilson interval.)

## About the screenshots

The screenshots were captured from the app's rendered pages at 1440 px wide with the test datasets loaded,
then scaled to 1200 px. Fonts may differ slightly from the live app.
