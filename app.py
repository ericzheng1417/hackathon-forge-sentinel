"""Forge Sentinel — Shiny for Python dashboard.

Run:  shiny run app.py            (add --reload while developing)
Then open http://127.0.0.1:8000
"""
from __future__ import annotations

import io
import json
import math
import os
import pathlib
import statistics as st
import threading
import zipfile
from datetime import datetime, timezone

from shiny import App, reactive, render, ui

from forge_sentinel import data, engine, views

ROOT = pathlib.Path(__file__).resolve().parent
WWW = ROOT / "www"
ACTIONS_FILE = pathlib.Path(os.environ.get("FORGE_ACTIONS_FILE", ROOT / "data" / "actions.json"))


# -- corrective-action register (shared, file-backed) ---------------------

class ActionStore:
    def __init__(self, path: pathlib.Path):
        self.path = path
        self.lock = threading.Lock()

    def load(self) -> dict:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def save(self, task_id: str, key: str, value: str) -> dict:
        with self.lock:
            acts = self.load()
            entry = acts.get(task_id, {})
            entry[key] = value
            entry["updated"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            acts[task_id] = entry
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(acts, indent=2), encoding="utf-8")
            tmp.replace(self.path)
            return acts


STORE = ActionStore(ACTIONS_FILE)
TASK_IDS = {t[0] for t in views.TASKS}

# -- UI -------------------------------------------------------------------

# All clickable chrome is server-rendered HTML; these helpers forward clicks to
# a single Shiny event input (`fs_evt`) so repeat clicks always register.
JS = """
function fsEvt(type, value){
  if (window.Shiny && Shiny.setInputValue)
    Shiny.setInputValue('fs_evt', {type: type, value: value === undefined ? null : value}, {priority: 'event'});
}
function fsGo(p){ fsEvt('nav', p); window.scrollTo(0, 0); }
function fsBuild(i){ fsEvt('build', i); }
function fsMachine(m){ fsEvt('machine', m); }
function fsMetric(m){ fsEvt('metric', m); }
function fsOpen(w){ fsEvt('open', w); }
function fsAction(id, key, value){ fsEvt('action', {id: id, key: key, value: value}); }
"""

app_ui = ui.page_bootstrap(
    ui.head_content(
        ui.tags.meta(name="viewport", content="width=device-width,initial-scale=1"),
        ui.tags.link(rel="stylesheet", href="style.css"),
        ui.tags.script(ui.HTML(JS)),
    ),
    ui.div(
        ui.tags.aside(
            ui.HTML('<div class="brand"><span class="logo">F</span> FORGE<span class="thin">SENTINEL</span></div>'
                    '<div class="workspace"><small>WORKSPACE</small><strong>Aerospace manufacturing</strong>'
                    '<span>Ti-6Al-4V · Laser powder bed fusion</span></div>'),
            ui.tags.nav(ui.output_ui("nav")),
            ui.HTML('<div class="sidebottom"><span class="statusdot"></span> Shiny analysis engine<br>'
                    '<small>Python server · session-scoped data</small><div class="avatar">QE</div>'
                    '<strong>Quality engineering</strong><small>Process assurance workspace</small></div>'),
        ),
        ui.div(
            ui.tags.header(ui.output_ui("header_bits")),
            ui.tags.main(ui.output_ui("main")),
            ui.HTML('<footer>FORGE SENTINEL <span>Engineering decision support · Not a part-release or certification '
                    'system</span><button onclick="fsGo(\'Methods\')">Methods &amp; assumptions ↗</button></footer>'),
            class_="shell",
        ),
        id="fs",
    ),
    title="Forge Sentinel — Process Intelligence",
    lang="en",
)


# -- server ---------------------------------------------------------------

CFG_FIELDS = [  # key, label, min, max, step
    ("lsl", "Minimum strength (MPa)", 1, 2000, 0.1),
    ("target", "Cpl target", 0.1, 5, 0.01),
    ("baseline", "Baseline builds", 10, None, 1),
    ("oxygen", "Oxygen alert (ppm)", 1, 10000, 1),
    ("humidity", "Humidity alert (%)", 1, 100, 1),
]


def close_button():
    return ui.tags.button("✕", type="button", class_="close", **{"data-bs-dismiss": "modal", "aria-label": "Close dialog"})


def server(input, output, session):
    rows = reactive.value(data.seed_rows())
    source = reactive.value("demo")
    page = reactive.value("Overview")
    machine = reactive.value("LPBF-01")
    metric = reactive.value("strength")
    cfg = reactive.value(dict(engine.DEFAULT_CONFIG))
    import_err = reactive.value("")
    cfg_err = reactive.value("")

    @reactive.calc
    def stream() -> list[dict]:
        return [r for r in rows() if r["machine"] == machine()]

    def _analysis(v: str) -> engine.Analysis:
        c, s = cfg(), stream()
        baseline = max(2, min(int(c["baseline"]), len(s) - 1))
        return engine.analyze_stream(s, v, c["lsl"], baseline, c["target"])

    @reactive.calc
    def a() -> engine.Analysis:
        return _analysis("strength")

    @reactive.calc
    def am() -> engine.Analysis:
        return _analysis(metric())

    # ---- rendering ----
    @render.ui
    def nav():
        return ui.HTML(views.nav(page()))

    @render.ui
    def header_bits():
        badge = "◉ &nbsp; DEMONSTRATION DATA" if source() == "demo" else "◉ &nbsp; IMPORTED CSV · SESSION"
        return ui.HTML(f'<span>Manufacturing intelligence <b>/</b> <span id="crumb">{page()}</span></span>'
                       f'<span class="demo">{badge}</span>')

    @render.ui
    def main():
        p, an = page(), a()
        body = views.render_page(p, an, am() if p == "Process control" else an, cfg(), STORE.load())
        machines = data.machine_list(rows())
        return ui.HTML(views.heading(p) + views.filters(machines, machine(), an) + body)

    # ---- event dispatch ----
    @reactive.effect
    @reactive.event(input.fs_evt)
    def _dispatch():
        evt = input.fs_evt() or {}
        kind, value = evt.get("type"), evt.get("value")
        if kind == "nav" and value in views.PAGES:
            page.set(value)
        elif kind == "machine" and value in data.machine_list(rows()):
            machine.set(value)
        elif kind == "metric" and value in engine.VARS:
            metric.set(value)
        elif kind == "build":
            show_build(int(value))
        elif kind == "open" and value == "import":
            show_import()
        elif kind == "open" and value == "config":
            show_config()
        elif kind == "apply_config":
            apply_config()
        elif kind == "restore_demo":
            rows.set(data.seed_rows())
            machine.set("LPBF-01")
            cfg.set({**cfg(), "baseline": 25})
            source.set("demo")
            ui.modal_remove()
        elif kind == "action" and isinstance(value, dict):
            tid, key = value.get("id"), value.get("key")
            if tid in TASK_IDS and key in ("status", "note"):
                STORE.save(tid, key, str(value.get("value", ""))[:4000])

    # ---- modals ----
    def show_build(i: int):
        an = a()
        if 0 <= i < an.n:
            ui.modal_show(ui.modal(close_button(), ui.HTML(views.build_detail(an, i)), easy_close=True, footer=None))

    def show_import():
        import_err.set("")
        ui.modal_show(ui.modal(
            close_button(),
            ui.HTML('<h2>Import build data</h2><p>CSV format: one row per independent build/test result, oldest first. '
                    'Use one consistent part family, material, orientation and heat-treatment route. At least 30 rows per '
                    'machine; all fields required.</p><p><b>Columns:</b> id, machine, strength, oxygen, humidity, '
                    'temperature, power, speed, stress</p><p>Units: MPa, ppm, %, °C, W, mm/s, MPa. IDs must be unique '
                    'within a machine. Import replaces the current dataset for this browser session.</p>'
                    '<div class="actions" style="margin:14px 0"><a id="download_example" class="shiny-download-link" '
                    'href="" target="_blank" download>Download example</a></div>'),
            ui.input_file("upload", "Choose CSV", accept=[".csv", "text/csv"], multiple=False,
                          button_label="Browse…", placeholder="No file selected"),
            ui.output_ui("import_error"),
            ui.HTML('<button class="link" style="border:0;background:none;color:var(--green);font-size:11px;padding:0" '
                    'onclick="fsEvt(\'restore_demo\')">Restore demonstration data</button>'),
            easy_close=True, footer=None,
        ))

    def show_config():
        cfg_err.set("")
        c, n = cfg(), len(stream())
        fields = [ui.input_numeric(f"cfg_{k}", label, c[k], min=lo, max=(n - 1 if hi is None else hi), step=step)
                  for k, label, lo, hi, step in CFG_FIELDS]
        ui.modal_show(ui.modal(
            close_button(),
            ui.HTML('<h2>Analysis configuration</h2><p>Use approved client requirements. Defaults are illustrative, '
                    'not aerospace acceptance criteria.</p>'),
            ui.div(*fields, class_="formgrid"),
            ui.output_ui("cfg_error"),
            ui.HTML('<button class="primary" style="background:var(--green);color:#fff;border:1px solid var(--green);'
                    'border-radius:6px;padding:10px 15px;margin-top:12px" onclick="fsEvt(\'apply_config\')">'
                    'Apply &amp; recalculate</button>'),
            easy_close=True, footer=None,
        ))

    def apply_config():
        n = len(stream())
        nxt = dict(cfg())
        for k, label, lo, hi, _step in CFG_FIELDS:
            val = input[f"cfg_{k}"]()
            hi = n - 1 if hi is None else hi
            if val is None or not isinstance(val, (int, float)) or not math.isfinite(val) or not lo <= val <= hi:
                cfg_err.set(f"{label} must be between {lo} and {hi}.")
                return
            nxt[k] = int(val) if k == "baseline" else float(val)
        if nxt["baseline"] != float(input["cfg_baseline"]()):
            cfg_err.set("Baseline builds must be a whole number.")
            return
        if st.stdev([r["strength"] for r in stream()[: nxt["baseline"]]]) == 0:
            cfg_err.set("Baseline has zero strength variation; choose a different baseline or verify measurement resolution.")
            return
        cfg.set(nxt)
        ui.modal_remove()

    @render.ui
    def import_error():
        return ui.p(import_err(), class_="error") if import_err() else None

    @render.ui
    def cfg_error():
        return ui.p(cfg_err(), class_="error") if cfg_err() else None

    @reactive.effect
    @reactive.event(input.upload)
    def _upload():
        files = input.upload()
        if not files:
            return
        try:
            raw = pathlib.Path(files[0]["datapath"]).read_bytes()
            parsed = data.parse_csv(raw)
        except data.ImportError_ as e:
            import_err.set(str(e))
            return
        rows.set(parsed)
        machine.set(data.machine_list(parsed)[0])
        cfg.set({**cfg(), "baseline": 25})
        source.set("csv")
        ui.modal_remove()
        ui.notification_show(f"Imported {len(parsed)} rows from {files[0]['name']}.", type="message", duration=4)

    # ---- downloads ----
    @render.download(filename="forge-process-report.json")
    def export_report():
        rep = engine.report(a(), source=source(), machine=machine(), config=cfg(), actions=STORE.load(),
                            generated_at=datetime.now(timezone.utc).isoformat())
        yield json.dumps(rep, indent=2, ensure_ascii=False)

    @render.download(filename="forge-builds.csv")
    def download_csv():
        yield data.to_csv(stream())

    @render.download(filename="forge-builds.csv")
    def download_example():
        yield data.to_csv(rows())

    @render.download(filename="forge-sentinel-shiny-source.zip")
    def download_source():
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for p in sorted(ROOT.rglob("*")):
                rel = p.relative_to(ROOT)
                if p.is_file() and not ({"__pycache__", "data", ".git", ".venv"} & set(rel.parts)):
                    z.write(p, pathlib.Path("forge-sentinel-shiny") / rel)
        yield buf.getvalue()


app = App(app_ui, server, static_assets=WWW)
