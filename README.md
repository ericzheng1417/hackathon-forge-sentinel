# Forge Sentinel

Forge Sentinel is a web dashboard that helps a quality engineer answer one question:

> **Is our 3D-metal-printing process producing parts that are consistently strong enough, and if not, what changed?**

It was built for a specific case: titanium brackets made by an aerospace supplier. You give it a
spreadsheet (CSV) of past builds, one row per build. Each row has the part's measured strength and
the printer conditions during that build, such as oxygen level, humidity and laser power. The
dashboard then:

- plots strength over time and flags builds where the process seems to have changed,
- says whether the process is *capable*: likely to keep meeting the minimum strength requirement,
- shows which printer conditions move together with strength, so you know where to look first,
- gives you a simple list for tracking investigations and fixes.

The app comes loaded with made-up demo data, so you can try it right away without your own data.

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
| **LSL** (lower specification limit) | The minimum acceptable strength. Default **900 MPa**. A build below it fails. |
| **SPC** (statistical process control) | A standard way to tell normal build-to-build variation apart from a real change in the process. |
| **Baseline** | The first N builds (default 25). They define what "normal" looks like, and later builds are compared against them. |
| **Control limits (UCL / LCL)** | The band of normal variation, worked out from the baseline. A point outside it is a warning sign. |
| **Signal** | A build the SPC rules flag as unusual. It means "investigate", not "this caused the failure". |
| **Cpl** | A capability score: how far average strength sits above the minimum, compared with normal variation. Higher is better. The default target is **1.33**, a common industry rule of thumb (adjustable). |
| **Ppl** | Like Cpl, but uses the total spread of all builds rather than only the baseline variation. |
| **Wilson interval** | A range that shows how sure we can be about the pass rate, given how many builds were tested. |
| **Correlation (r)** | How closely a printer condition moves with strength, from −1 to +1. It suggests where to look; it does not prove cause. |

---

## What's on each page

| Page | What you'll find |
|---|---|
| **Overview** | One-screen summary: pass rate, capability score, average strength, number of warnings, the strength trend chart, and the most recent builds. |
| **Process control** | The detailed trend chart for any measurement (strength, oxygen, humidity…) and a log of every flagged build with the reason. |
| **Capability** | Whether the process meets the strength target, with a checklist of what is and isn't proven. |
| **Parameter analysis** | Which printer conditions are most associated with strength, plus counts of builds with high oxygen or humidity. |
| **Build records** | Every build for the selected machine, newest first. Click ↗ for full details. Download as CSV. |
| **Corrective actions** | Four suggested investigation steps. Set each one's status and add notes. |
| **Methods** | The exact formulas and assumptions, with links to the NIST statistics handbook. |

Other controls:

- **Machine** dropdown (top): switch between printers. Each machine is analysed separately.
- **Configure**: change the minimum strength, capability target, baseline size and alarm thresholds.
- **Import data**: upload your own CSV (format below).
- **Export report**: download all results as a JSON file to keep a record.
- **Click any point on a chart** to see that build's details.

---

## Running it on your own computer

**You need:** Python 3.10 or newer. Check by running `python --version` in a terminal. On Windows,
try `py --version` if `python` isn't recognised.

1. Download or clone this folder and open a terminal inside it.
2. Install the one dependency, [Shiny for Python](https://shiny.posit.co/py/):
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
- *Python version error*: `manifest.json` asks for Python 3.11. If your server doesn't have it,
  change `"version"` under `"python"` to one the server lists (3.10 or newer).
- *Added or renamed files?* Regenerate the manifest with
  `rsconnect write-manifest shiny . --overwrite`.

---

## Using your own data

Click **Import data** and upload a CSV with these exact column headers:

| Column | Meaning | Unit |
|---|---|---|
| `id` | Build ID (unique within each machine) | text |
| `machine` | Printer name, e.g. `LPBF-01` | text |
| `strength` | Measured tensile strength | MPa |
| `oxygen` | Oxygen in the build chamber | ppm |
| `humidity` | Relative humidity | % |
| `temperature` | Build plate temperature | °C |
| `power` | Laser power | W |
| `speed` | Laser scan speed | mm/s |
| `stress` | Residual stress | MPa |

Rules:

- **Rows must be in the order the builds happened**, oldest first. The app uses row order as time order.
- **At least 30 rows per machine.** Every cell must be filled in. Maximum file size is 2 MB.
- **One row per build.** Several test samples from the same build are not independent results.
- Keep each machine's data to one part type, material and process route, so you compare like with like.

Click **Download example** in the Import window for a correctly formatted file.

**Where your data goes:** an uploaded file is held in the server's memory only for your browser
session. It is never saved to disk, and it's gone when you close the tab. Corrective-action notes are
the exception: they are saved to `data/actions.json` on the server and shared by everyone using that
copy of the app. Set the `FORGE_ACTIONS_FILE` environment variable to store them somewhere else.

---

## Offline analysis (no dashboard)

`python/analyze.py` runs the same calculations from the command line and prints a JSON report. It
uses only the Python standard library, so it doesn't need Shiny:

```
python python/analyze.py my-builds.csv --machine LPBF-01 --lsl 900 > report.json
```

Options: `--lsl` (minimum strength, default 900), `--baseline` (number of baseline builds, default 25),
`--target` (Cpl target, default 1.33).

---

## Project layout

```
app.py                     The Shiny app: page layout, buttons, uploads, downloads
forge_sentinel/
  engine.py                All the statistics (control limits, signals, Cpl/Ppl, Wilson, correlations)
  data.py                  Demo data, CSV checking, CSV export
  charts.py                Draws the charts (as SVG images)
  views.py                 Builds the HTML for each page
www/style.css              Visual styling
python/analyze.py          Command-line version of the analysis
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
JavaScript version of this tool. They also cover CSV validation and the command-line tool.

---

## Limitations

- **Demo data is fake.** The two demo machines are synthetic: LPBF-01 deliberately gets worse near
  the end, and LPBF-02 stays stable. Neither represents real Ti-6Al-4V material properties.
- **Default limits are examples**, not aerospace requirements. Use the values your customer or
  specification requires.
- **Not validated** for part qualification, release, fatigue life or structural reliability. The pass-rate
  interval covers tensile-test pass/fail only.
- **No live data feed.** Data comes only from CSV upload.
- **Not an audited quality system.** The corrective-action list has no user accounts, sign-offs or audit trail.

## References

- NIST/SEMATECH e-Handbook: [Individuals control charts](https://www.itl.nist.gov/div898/handbook/pmc/section3/pmc322.htm)
- NIST/SEMATECH e-Handbook: [Process capability](https://www.itl.nist.gov/div898/handbook/pmc/section1/pmc16.htm)
