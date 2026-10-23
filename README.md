# Forge Sentinel

Forge Sentinel is a web dashboard that helps a quality engineer answer one question:

> **Is our 3D-metal-printing process producing parts that are consistently strong enough, and if not, what changed?**

**Who it's for:** the quality or process engineer at an aerospace contractor that 3D-prints
titanium (Ti-6Al-4V) brackets by laser powder bed fusion and is failing the client's tensile-strength
acceptance tests.

**What you give it:** a spreadsheet (CSV or Excel .xlsx) of past builds, one row per build. Only three columns are
required, and the contractor already has all of them: build ID, machine, and the tensile strength from
the client test. Printer conditions you happen to log (chamber oxygen, humidity, plate temperature,
laser power, scan speed, residual stress) are optional; each one you add unlocks root-cause analysis.

**What the dashboard does:**

- summarises every measurement with standard Lean Six Sigma statistics (mean, median, standard
  deviation, variance, CV, standard error, range, quartiles),
- draws individuals and moving-range (I-MR) control charts and checks them with the
  **8 standard tests for special causes**, flagging builds where the process seems to have changed,
- says whether the process is *capable* (Cp, Cpk, Pp, Ppk): likely to keep meeting the strength specification,
- shows which printer conditions move together with strength, so you know where to look first,
- gives you a simple list for tracking investigations and fixes.

The app opens with built-in demo data. **Three test datasets** (stable process, oxygen-leak failure,
strength-only data) can be loaded with one click from **Import data**.

### Documentation

| Document | What's in it |
|---|---|
| [DEMO.md](DEMO.md) | Step-by-step demonstration on the three test datasets, with screenshots |
| [datasets/README.md](datasets/README.md) | The test datasets: scenario, expected results, how they were generated |
| [datasets/CODEBOOK.md](datasets/CODEBOOK.md) | Every variable: meaning, unit, how it's measured, required or optional |
| [docs/REFERENCE.md](docs/REFERENCE.md) | Function reference: inputs, parameters, outputs and formulas |
| This README | What the tool is, how to run it, deploy it and use your own data |

> ⚠️ **This is a decision-support prototype.** It does not certify parts, approve them for flight,
> or replace a validated quality system. Treat its results as prompts to investigate, not verdicts.

---

## Key terms (plain English)

You don't need these to run the app, but they help you read it.

| Term | What it means here |
|---|---|
| **LPBF** (laser powder bed fusion) | A metal 3D-printing method: a laser melts thin layers of metal powder, one on top of another. |
| **Ti-6Al-4V** | The most common titanium alloy in aerospace (titanium with 6% aluminium and 4% vanadium). |
| **Build** | One print job on one machine. The app assumes one strength test result per build. |
| **Tensile strength** | How much pulling force a test sample takes before it breaks, measured in MPa (megapascals). Higher is stronger. |
| **LSL / USL** (lower / upper specification limit) | The acceptable strength range. Defaults **900** and **1100 MPa** (examples only). A build outside it fails. Set USL to 0 for a minimum-only spec. |
| **SPC** (statistical process control) | A standard way to tell normal build-to-build variation apart from a real change in the process. |
| **Baseline** | The first N builds (default 25). They define what "normal" looks like, and later builds are compared against them. |
| **Control limits (UCL / LCL)** | The band of normal variation (mean ± 3σ), worked out from the baseline. A point outside it is a warning sign. |
| **Zones A, B, C** | Bands on the control chart: C is within 1σ of the centre line, B is 1–2σ away, A is 2–3σ away. The 8 tests look for patterns across these zones. |
| **Moving range (MR)** | The absolute difference between one build and the previous one. The MR chart shows short-term jumps. |
| **8 tests for special causes** | Pattern checks (Western Electric / Nelson rules), such as one point beyond zone A, 8 points in a row on one side, or 6 points steadily rising. Listed in full on the Process control page. |
| **Signal** | A build the SPC rules flag as unusual. It means "investigate", not "this caused the failure". |
| **Cp** | Potential capability: how many times the process spread fits inside the specification range. Ignores centring. |
| **Cpk** | Actual capability: like Cp, but measured to the *nearer* spec limit, so an off-centre process scores lower. Default target **1.33**, a common rule of thumb (adjustable). |
| **Cpl / Cpu** | One-sided versions: distance from the mean to the lower / upper limit, divided by 3σ. Cpk is the smaller of the two. |
| **Pp / Ppk** | Same as Cp / Cpk but using the overall spread of all builds instead of short-term (baseline) variation. |
| **Standard deviation (s) / variance (s²)** | How spread out the values are. Variance is the standard deviation squared. |
| **CV** (coefficient of variation) | Standard deviation as a percentage of the mean, so variables with different units can be compared. |
| **SE** (standard error of the mean) | How precisely the average is known: s ÷ √n. Shrinks as you test more builds. |
| **Range / IQR** | Max − min, and the spread of the middle 50% of values (Q3 − Q1). |
| **Wilson interval** | A range that shows how sure we can be about the pass rate, given how many builds were tested. |
| **Correlation (r)** | How closely a printer condition moves with strength, from −1 to +1. It suggests where to look; it does not prove cause. |

---

## What's on each page

| Page | What you'll find |
|---|---|
| **Overview** | One-screen summary: pass rate, capability score, average strength, number of warnings, the strength trend chart, and the most recent builds. |
| **Process control** | I chart with zones A/B/C and an MR chart for any measurement (strength, oxygen, humidity…), the 8 tests with how many points each flagged, and a log of every flagged build with the tests it failed. |
| **Statistics** | Descriptive statistics for any variable (mean, median, SD, variance, CV, SE, range, quartiles, IQR), a box plot and histogram, and a table comparing all variables. |
| **Capability** | Cp, Cpk, Pp, Ppk, Cpl, Cpu and centring, the observed pass rate with its uncertainty, and a checklist of what is and isn't proven. |
| **Parameter analysis** | Which printer conditions are most associated with strength, plus counts of builds with high oxygen or humidity. |
| **Build records** | Every build for the selected machine, newest first. Click ↗ for full details. Download as CSV. |
| **Corrective actions** | Four suggested investigation steps. Set each one's status and add notes. |
| **Methods** | The exact formulas and assumptions, with links to the NIST statistics handbook. |

Other controls:

- **Machine** dropdown (top): switch between printers. Each machine is analysed separately.
- **Configure**: change the spec limits (LSL/USL), Cpk target, baseline size and alarm thresholds, and
  choose which of the 8 tests (and the moving-range rule) to apply.
- **Import data**: upload your own CSV or Excel file (format below), or load one of the three test datasets.
- **Export report**: opens a dialog where you choose the format, for the selected machine and current settings:
  - **PDF report**: a printable 5-page summary covering the verdict, key numbers, I-MR charts, the 8 tests,
    capability, likely causes, statistics and corrective-action status. It opens in a new tab with your browser's
    print dialog; choose **Save as PDF**. If your browser blocks the new tab, the report downloads as an HTML file
    instead, which you open and print the same way.
  - **Excel workbook**: a Summary sheet with a native control chart, the full data with control limits and
    pass/fail, statistics, capability, signals, associations and corrective actions.
  - **JSON data**: the same results in machine-readable form, for archiving or other software.
- **Click any point on a chart** to see that build's details.

---

## Running it on your own computer

**You need:** Python 3.10 or newer. Check by running `python --version` in a terminal. On Windows,
try `py --version` if `python` isn't recognised.

1. Download or clone this folder and open a terminal inside it.
2. Install the two dependencies, [Shiny for Python](https://shiny.posit.co/py/) and
   [openpyxl](https://openpyxl.readthedocs.io/) (for Excel import and export):
   ```
   pip install -r requirements.txt
   ```
3. Start the app:
   ```
   shiny run app.py
   ```
4. Open **http://127.0.0.1:8000** in your browser.
5. To stop it, go back to the terminal and press **Ctrl+C**.

**Using Positron or VS Code?** Open this folder, open `app.py`, and click **▶ Run Shiny App** at the
top right of the editor.

---

## Publishing it on Posit Connect

[Posit Connect](https://posit.co/products/enterprise/connect/) is a server many organisations use to
host Shiny apps at a shareable link. This repo already includes the `manifest.json` file Connect
needs.

**Option 1: from a Git repository**

1. Push this folder to your Git host (GitHub, GitLab, etc.).
2. In Connect, choose **Publish → Import from Git**, enter the repository URL, pick the branch, and
   select the folder that contains `manifest.json`.
3. Click **Deploy**. Connect installs the dependencies and starts the app.

**Option 2: from Positron or VS Code**

1. In Connect, create an API key: click your name, then **API Keys**, then **New API Key**.
2. In the editor, open `app.py` and click the **Publish** icon. Add your Connect server URL and API key.
3. Click **Deploy**.

**Option 3: from the terminal**

```
pip install rsconnect-python
rsconnect add --server https://YOUR-CONNECT-SERVER --name myserver --api-key YOUR_KEY
rsconnect deploy shiny . --name myserver --title "Forge Sentinel"
```

After deploying, open the app in Connect and use the **Access** tab to choose who can view it.

**Troubleshooting**

- *"No deployable content was found"*: the folder you picked has no `manifest.json`. Pick the
  folder that contains it.
- *Python version error*: `manifest.json` asks for Python 3.12.4. If your server doesn't have it,
  change `"version"` under `"python"` to one the server lists (3.10 or newer).
- *Added or renamed files?* Regenerate the manifest with
  `rsconnect write-manifest shiny . --overwrite`.

---

## Using your own data

Click **Import data** and upload a **CSV** or **Excel (.xlsx)** file with these column headers. In Excel, the
first sheet whose first row contains `id`, `machine` and `strength` is used, so a cover sheet in front is
fine. Headers are not case-sensitive. Old `.xls` files must be re-saved as `.xlsx` or CSV.

| Column | Required? | Meaning | Unit |
|---|---|---|---|
| `id` | **required** | Build ID (unique within each machine) | text |
| `machine` | **required** | Printer name, e.g. `LPBF-01` | text |
| `strength` | **required** | Measured tensile strength | MPa |
| `oxygen` | optional | Oxygen in the build chamber | ppm |
| `humidity` | optional | Relative humidity | % |
| `temperature` | optional | Build plate temperature | °C |
| `power` | optional | Laser power | W |
| `speed` | optional | Laser scan speed | mm/s |
| `stress` | optional | Residual stress | MPa |

Full definitions and how each is measured are in [datasets/CODEBOOK.md](datasets/CODEBOOK.md).

Rules:

- **Rows must be in the order the builds happened**, oldest first. The app uses row order as time order.
- **At least 30 rows per machine.** Optional columns can be left out entirely, or blank for some builds.
  Other columns (such as a build date) are ignored. Maximum file size is 2 MB.
- **One row per build.** Several test samples from the same build are not independent results.
- Keep each machine's data to one part type, material and process route, so you compare like with like.

Click **Example (CSV)** or **Example (Excel)** in the Import window for a correctly formatted file.

**Where your data goes:** an uploaded file is held in the server's memory only for your browser
session. It is never saved to disk, and it's gone when you close the tab. Corrective-action notes are
the exception: they are saved to `data/actions.json` on the server and shared by everyone using that
copy of the app. Set the `FORGE_ACTIONS_FILE` environment variable to store them somewhere else.

---

## Offline analysis (no dashboard)

`python/analyze.py` runs the same calculations from the command line and prints a JSON report. It
uses only the Python standard library for CSV files (Excel files need `openpyxl`), so it doesn't need Shiny:

```
python python/analyze.py my-builds.csv --machine LPBF-01 --lsl 900 > report.json
python python/analyze.py my-builds.xlsx --machine LPBF-01 --usl 1100
```

Options: `--lsl` (lower spec, default 900), `--usl` (upper spec; omit for minimum-only),
`--baseline` (number of baseline builds, default 25), `--target` (Cpk target, default 1.33),
`--tests` (which special-cause tests to apply, default `1,2,3,4,5,6,7,8`), `--no-mr` (skip the moving-range rule).

The report includes Cp/Cpk/Pp/Ppk, descriptive statistics, and every flagged build with its test numbers.

---

## Project layout

```
app.py                     The Shiny app: page layout, buttons, uploads, downloads
forge_sentinel/
  engine.py                All the statistics (descriptives, I-MR limits, 8 tests, Cp/Cpk/Pp/Ppk, Wilson, correlations)
  data.py                  Demo data, CSV / Excel import and checking, CSV / Excel export
  exports.py               Printable HTML report, Excel workbook and JSON report
  charts.py                Draws the charts (as SVG images)
  views.py                 Builds the HTML for each page
www/style.css              Visual styling
python/analyze.py          Command-line version of the analysis
datasets/                  3 test datasets, their generator, README and codebook
demo/                      run_demo.py (text demonstration) and its saved output
docs/                      Function reference and demo screenshots
DEMO.md                    Demonstration walkthrough
tests/                     Automated checks
manifest.json              Deployment file for Posit Connect
requirements.txt           Python packages to install
```

The dashboard and the command-line tool share `engine.py`, so they always give the same numbers.

## Running the tests

```
python -m unittest discover tests
```

The tests check the statistics against known results, including reference output from the original
JavaScript version of this tool, each of the 8 special-cause tests on hand-built patterns, the
descriptive statistics and Cp/Cpk formulas. They also cover CSV validation, optional columns, page
rendering and the command-line tool. `tests/test_datasets.py` regenerates the test datasets, checks
they match the committed files byte for byte, and checks every result quoted in [DEMO.md](DEMO.md). `tests/test_exports.py` covers Excel import (including awkward workbooks) and the HTML, Excel and JSON
reports.

## Reproducing the results

Everything in this repository can be regenerated from the code:

```
pip install -r requirements.txt          # Shiny (dashboard) + openpyxl (Excel)
python datasets/generate_datasets.py     # recreates the 3 test CSVs (fixed seeds)
python demo/run_demo.py                  # recomputes every number in DEMO.md
python -m unittest discover tests        # 47 automated checks
shiny run app.py                         # the dashboard
```

The analysis engine, dataset generator, demo script and command-line tool use only the Python standard
library for CSV data (Python 3.10+). The dashboard needs `shiny`; Excel import and the Excel export need
`openpyxl` (if it's missing, the Excel tests are skipped and everything else still runs). The Posit Connect
deployment uses Python 3.12.4 (see `manifest.json`).

---

## Limitations

- **Demo and test data are synthetic.** They're designed to be plausible and to show specific
  scenarios, but they are not real Ti-6Al-4V measurements and their effect sizes are illustrative.
- **Default limits are examples**, not aerospace requirements. Use the values your customer or
  specification requires.
- **Not validated** for part qualification, release, fatigue life or structural reliability. The pass-rate
  interval covers tensile-test pass/fail only.
- **No live data feed.** Data comes only from CSV upload.
- **Not an audited quality system.** The corrective-action list has no user accounts, sign-offs or audit trail.

## References

- NIST/SEMATECH e-Handbook: [Individuals control charts](https://www.itl.nist.gov/div898/handbook/pmc/section3/pmc322.htm)
- NIST/SEMATECH e-Handbook: [Process capability](https://www.itl.nist.gov/div898/handbook/pmc/section1/pmc16.htm)
- NIST/SEMATECH e-Handbook: [What are control charts? (run rules)](https://www.itl.nist.gov/div898/handbook/pmc/section3/pmc32.htm)
