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
                    if k_js in ("cpl", "ppl") and case["v"] != "strength":
                        continue  # capability is only defined for strength (the spec'd characteristic)
                    self.assertTrue(close(case[k_js], val), (k_js, case[k_js], val))
                self.assertEqual(case["fails"], len(a.fails))
                # Signals intentionally differ: the original used 3 rules, this version uses the 8 tests.
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


class EightTests(unittest.TestCase):
    """Each rule on a hand-built series with centre 0 and sigma 1."""

    def hits(self, x, test):
        return sorted(i for i, ts in engine.special_cause_tests(x, 0.0, 1.0, [test]).items() if test in ts)

    def test1_beyond_zone_a(self):
        self.assertEqual(self.hits([0.1, -0.2, 3.5, 0.3, -3.1], 1), [2, 4])

    def test2_two_of_three_beyond_b(self):
        self.assertEqual(self.hits([0.1, 2.5, 0.2, 2.2], 2), [3])
        self.assertEqual(self.hits([2.5, -2.5, 0.0], 2), [])          # opposite sides do not count

    def test3_four_of_five_beyond_c(self):
        self.assertEqual(self.hits([1.5, 1.2, 0.2, 1.1, 1.3], 3), [4])
        self.assertEqual(self.hits([1.5, 1.2, 0.2, 1.1, 0.3], 3), [])

    def test4_eight_same_side(self):
        self.assertEqual(self.hits([0.1] * 7 + [-0.1], 4), [])
        self.assertEqual(self.hits([0.1] * 9, 4), [7, 8])

    def test5_six_trending(self):
        self.assertEqual(self.hits([0, 0.1, 0.2, 0.3, 0.4, 0.5], 5), [5])
        self.assertEqual(self.hits([0, 0.1, 0.2, 0.2, 0.4, 0.5], 5), [])   # a tie breaks the run

    def test6_fifteen_in_zone_c(self):
        x = [0.5, -0.5] * 7 + [0.2]
        self.assertEqual(self.hits(x, 6), [14])
        self.assertEqual(self.hits(x[:-1] + [1.5], 6), [])

    def test7_eight_outside_zone_c_both_sides(self):
        self.assertEqual(self.hits([1.5, -1.5] * 4, 7), [7])
        self.assertEqual(self.hits([1.5] * 8, 7), [])                   # one side only is Test 4, not 7

    def test8_fourteen_alternating(self):
        x = [0.2, -0.2] * 7
        self.assertEqual(self.hits(x, 8), [13])
        self.assertEqual(self.hits(x[:13] + [x[12]], 8), [])

    def test_mr_rule_and_test_selection(self):
        recs = [{"id": str(i), "strength": 950.0 + (i % 2)} for i in range(30)] + [{"id": "j", "strength": 990.0}]
        a = engine.analyze_stream(recs, tests=[], mr_rule=True)
        self.assertEqual([f.tests for f in a.flags], [["MR"]])
        a = engine.analyze_stream(recs, tests=[], mr_rule=False)
        self.assertTrue(a.stable)


class DescriptiveAndCapability(unittest.TestCase):
    def test_describe(self):
        d = engine.describe([2, 4, 4, 4, 5, 5, 7, 9])
        self.assertEqual(d["mean"], 5)
        self.assertEqual(d["median"], 4.5)
        self.assertAlmostEqual(d["variance"], 32 / 7)
        self.assertAlmostEqual(d["sd"], math.sqrt(32 / 7))
        self.assertAlmostEqual(d["cv_pct"], math.sqrt(32 / 7) / 5 * 100)
        self.assertAlmostEqual(d["se_mean"], math.sqrt(32 / 7) / math.sqrt(8))
        self.assertEqual((d["min"], d["max"], d["range"]), (2, 9, 7))
        self.assertEqual((d["q1"], d["q3"], d["iqr"]), (4, 5.5, 1.5))     # Excel QUARTILE.INC

    def test_capability_two_sided(self):
        c = engine.capability(mean=1000, sigma_within=10, sigma_overall=20, lsl=940, usl=1090)
        self.assertAlmostEqual(c["Cp"], 150 / 60)
        self.assertAlmostEqual(c["Cpl"], 2.0)
        self.assertAlmostEqual(c["Cpu"], 3.0)
        self.assertAlmostEqual(c["Cpk"], 2.0)
        self.assertAlmostEqual(c["Pp"], 150 / 120)
        self.assertAlmostEqual(c["Ppk"], 1.0)

    def test_capability_one_sided(self):
        c = engine.capability(mean=1000, sigma_within=10, sigma_overall=20, lsl=940, usl=None)
        self.assertTrue(math.isnan(c["Cp"]))
        self.assertAlmostEqual(c["Cpk"], c["Cpl"])

    def test_usl_failures(self):
        recs = [r for r in data.seed_rows() if r["machine"] == "LPBF-02"]
        a = engine.analyze_stream(recs, usl=970)
        self.assertTrue(all(r["strength"] > 970 or r["strength"] < 900 for r in a.fails))
        self.assertGreater(len(a.fails), 0)


class CSVImport(unittest.TestCase):
    def test_roundtrip(self):
        rows = data.seed_rows()
        self.assertEqual(data.parse_csv(data.to_csv(rows).encode()), rows)

    def test_rejections(self):
        good = data.to_csv(data.seed_rows())
        bad = {
            "missing required header": good.replace('"strength"', '"strenght"', 1),
            "blank strength": data.to_csv([dict(r, strength=None) if i == 3 else r
                                           for i, r in enumerate(data.seed_rows())]),
            "non-numeric": good.replace('"965', '"abc', 1),
            "too few rows": "\n".join(good.splitlines()[:20]),
            "duplicate id": good.replace('"B1-002"', '"B1-001"', 1),
        }
        for name, text in bad.items():
            with self.subTest(name), self.assertRaises(data.ImportError_):
                data.parse_csv(text.encode())


class OptionalColumns(unittest.TestCase):
    def test_strength_only_csv(self):
        text = "id,machine,strength\n" + "\n".join(f"B{i},M1,{950 + (i * 7) % 23}" for i in range(40))
        rows = data.parse_csv(text.encode())
        self.assertIsNone(rows[0]["oxygen"])
        self.assertEqual(engine.available_vars(rows), ["strength"])
        self.assertEqual(engine.associations(rows), [])
        a = engine.analyze_stream(rows, usl=1100)
        self.assertEqual(a.n, 40)

    def test_blank_cells_are_skipped_per_variable(self):
        rows = [r for r in data.seed_rows() if r["machine"] == "LPBF-01"]
        rows = [dict(r, oxygen=None) if i % 5 == 0 else dict(r) for i, r in enumerate(rows)]
        rows = data.parse_csv(data.to_csv(rows).encode())
        am = engine.analyze_stream(rows, "oxygen")
        self.assertEqual(am.n, 48)
        self.assertEqual(am.n_missing, 12)
        self.assertEqual(am.idx[:3], [1, 2, 3])                  # positions map back to the full stream
        assoc = {d["v"]: d for d in engine.associations(rows)}
        self.assertEqual(assoc["oxygen"]["n"], 48)
        self.assertEqual(assoc["humidity"]["n"], 60)

    def test_pages_render_with_strength_only(self):
        from forge_sentinel import views
        text = "id,machine,strength\n" + "\n".join(f"B{i},M1,{950 + (i * 7) % 23}" for i in range(40))
        rows = data.parse_csv(text.encode())
        a = engine.analyze_stream(rows)
        desc = {v: engine.describe([r.get(v) for r in rows]) for v in engine.available_vars(rows)}
        for p in views.PAGES:
            html = views.render_page(p, a, a, dict(engine.DEFAULT_CONFIG), {}, desc)
            self.assertTrue(html, p)
        self.assertIn("Only strength was provided", views.render_page("Parameter analysis", a, a, dict(engine.DEFAULT_CONFIG), {}))


class Charts(unittest.TestCase):
    def test_svgs_render(self):
        recs = [r for r in data.seed_rows() if r["machine"] == "LPBF-01"]
        a = engine.analyze_stream(recs)
        for svg in (charts.control_chart(a, 900, 1100), charts.histogram(a.x, "Strength", 900, 1100),
                    charts.histogram(a.x, "Strength", bins=14), charts.mr_chart(a),
                    charts.boxplot(a.x, a.desc, "Strength"), charts.scatter(a, 900)):
            self.assertIn("<svg", svg)
            self.assertNotIn("nan", svg.lower())


class Views(unittest.TestCase):
    def test_every_page_renders(self):
        from forge_sentinel import views
        recs = [r for r in data.seed_rows() if r["machine"] == "LPBF-01"]
        cfg = dict(engine.DEFAULT_CONFIG)
        all_desc = {v: engine.describe([r[v] for r in recs]) for v in engine.FIELDS}
        for usl in (1100.0, None):
            a = engine.analyze_stream(recs, "strength", 900, 25, 1.33, usl)
            am = engine.analyze_stream(recs, "oxygen", 900, 25, 1.33, usl, tests=[1, 2, 4], mr_rule=False)
            for p in views.PAGES:
                html = views.render_page(p, a, am, cfg, {}, all_desc)
                self.assertNotIn("nan", html.lower().replace("nancy", ""), p)
                self.assertTrue(html)


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
