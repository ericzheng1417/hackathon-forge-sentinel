"""Parity and fixture tests. Run: python -m unittest discover tests"""
import json
import math
import pathlib
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from forge_sentinel import charts, data, engine  # noqa: E402

REF = json.loads((ROOT / "tests" / "js_reference.json").read_text())


def close(a, b, tol=1e-9):
    if a is None or b is None:
        return a is None and b is None
    return math.isclose(a, b, rel_tol=tol, abs_tol=tol)


class ParityWithOriginalJS(unittest.TestCase):
    """Reference numbers were produced by running the original dist/app.js in Node."""

    def test_seed_matches(self):
        self.assertEqual(data.seed_rows(), REF["rows"])

    def test_all_metrics_and_configs(self):
        rows = data.seed_rows()
        for case in REF["out"]:
            with self.subTest(m=case["m"], v=case["v"], lsl=case["lsl"], bl=case["bl"]):
                recs = [r for r in rows if r["machine"] == case["m"]]
                a = engine.analyze_stream(recs, case["v"], case["lsl"], case["bl"])
                for k_js, val in [("mu", a.center), ("sig", a.sigma), ("lcl", a.lcl), ("ucl", a.ucl),
                                  ("avg", a.avg), ("s", a.overall_sd), ("cpl", a.cpl), ("ppl", a.ppl)]:
                    self.assertTrue(close(case[k_js], val), (k_js, case[k_js], val))
                self.assertEqual(case["fails"], len(a.fails))
                self.assertEqual(case["flags"], [[f.index, f.reasons] for f in a.flags])
                if case["v"] == "strength":
                    got = engine.associations(recs)
                    self.assertEqual([d["v"] for d in case["ranks"]], [d["v"] for d in got])
                    for x, y in zip(case["ranks"], got):
                        self.assertTrue(close(x["r"], y["r"]))


class Fixtures(unittest.TestCase):
    def test_stable_stream_has_no_signals(self):
        recs = [r for r in data.seed_rows() if r["machine"] == "LPBF-02"]
        out = engine.analyze(recs)
        self.assertTrue(out["stable_under_selected_rules"])

    def test_drifting_stream_flags_monitoring(self):
        recs = [r for r in data.seed_rows() if r["machine"] == "LPBF-01"]
        out = engine.analyze(recs)
        self.assertFalse(out["stable_under_selected_rules"])
        self.assertTrue(all(s["phase"] == "monitoring" for s in out["signals"]))
        self.assertGreater(out["failed_strength_tests"], 0)

    def test_wilson(self):
        p, lo, hi = engine.wilson(50, 60)
        self.assertAlmostEqual(p, 50 / 60)
        self.assertAlmostEqual(lo, 0.7197, places=3)
        self.assertAlmostEqual(hi, 0.9069, places=3)
        _, lo, hi = engine.wilson(60, 60)
        self.assertLess(lo, 1)
        self.assertAlmostEqual(hi, 1.0)

    def test_zero_sigma_rejected(self):
        recs = [{"id": str(i), "strength": 950.0} for i in range(30)]
        with self.assertRaises(ValueError):
            engine.analyze(recs)


class CSVImport(unittest.TestCase):
    def test_roundtrip(self):
        rows = data.seed_rows()
        self.assertEqual(data.parse_csv(data.to_csv(rows).encode()), rows)

    def test_rejections(self):
        good = data.to_csv(data.seed_rows())
        bad = {
            "missing header": good.replace('"stress"', '"stres"', 1),
            "non-numeric": good.replace('"965', '"abc', 1),
            "too few rows": "\n".join(good.splitlines()[:20]),
            "duplicate id": good.replace('"B1-002"', '"B1-001"', 1),
        }
        for name, text in bad.items():
            with self.subTest(name), self.assertRaises(data.ImportError_):
                data.parse_csv(text.encode())


class Charts(unittest.TestCase):
    def test_svgs_render(self):
        recs = [r for r in data.seed_rows() if r["machine"] == "LPBF-01"]
        a = engine.analyze_stream(recs)
        for svg in (charts.control_chart(a, 900), charts.histogram(a, 900), charts.scatter(a, 900)):
            self.assertIn("<svg", svg)
            self.assertNotIn("nan", svg.lower())


class CLI(unittest.TestCase):
    def test_cli(self):
        csv_path = ROOT / "tests" / "_tmp.csv"
        csv_path.write_text(data.to_csv(data.seed_rows()))
        try:
            out = subprocess.run([sys.executable, str(ROOT / "python" / "analyze.py"), str(csv_path),
                                  "--machine", "LPBF-01"], capture_output=True, text=True, check=True).stdout
        finally:
            csv_path.unlink()
        rep = json.loads(out)
        self.assertEqual(rep["n"], 60)
        self.assertFalse(rep["capability_screen_passed"])


if __name__ == "__main__":
    unittest.main()
