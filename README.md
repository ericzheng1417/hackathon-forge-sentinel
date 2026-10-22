# Forge Sentinel (Shiny for Python)

A dashboard for Ti-6Al-4V bracket process assurance (LPBF), rebuilt from the original static
HTML/JS app as a **Shiny for Python** application. The dashboard and the offline CLI now share
one analysis engine, so they always produce the same numbers.

## Run

Requires Python 3.10+.

    pip install -r requirements.txt
    shiny run app.py            # add --reload while developing

Open http://127.0.0.1:8000. In Positron/VS Code with the Shiny extension, open `app.py` and press ▶ Run Shiny App.

## Project layout

    app.py                     Shiny UI + server (state, events, modals, uploads, downloads)
    forge_sentinel/engine.py   SPC, Cpl/Ppl, Wilson interval, correlations, report (stdlib only)
    forge_sentinel/data.py     Demo data, CSV import validation, CSV export
    forge_sentinel/charts.py   Server-rendered SVG control chart, histogram, scatter
    forge_sentinel/views.py    HTML for each page (pure functions, unit-testable)
    www/style.css              Original design, scoped under #fs so Bootstrap doesn't override it
    python/analyze.py          Offline CLI (same output schema as before)
    tests/                     Parity tests against the original JavaScript + fixtures

## What changed from the static version

- **Calculations run on the server in Python.** The JS `calc()` logic was ported to `engine.py`
  and checked against the original JS output for every metric, both machines and several
  LSL/baseline settings (`tests/js_reference.json`).
- **CSV import** goes through Shiny's file upload and the same validation rules. Imported data
  is held in that browser session's server memory only.
- **Corrective-action status and notes** are saved to `data/actions.json` on the server
  (override with `FORGE_ACTIONS_FILE`), so they're shared by everyone using the same app instance
  instead of living in one browser's localStorage.
- **Exports** (JSON report, machine CSV, example CSV, source zip) are Shiny downloads.

## Offline CLI

    python python/analyze.py forge-builds.csv --machine LPBF-01 --lsl 900 > report.json

Standard library only; it doesn't need Shiny installed.

## Tests

    python -m unittest discover tests

## Limitations

Same as the original: demonstration decision support only. One independent build/test result
per row, file order = acquisition order, one material/part family/process route per machine
stream. Not a validated aerospace qualification, fatigue reliability, MES or QMS system. See the
Methods page for equations and NIST references.
