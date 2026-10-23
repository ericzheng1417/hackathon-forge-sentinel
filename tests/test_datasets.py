"""Checks that the shipped test datasets are reproducible and produce the results documented
in datasets/README.md and DEMO.md. Run: python -m unittest discover tests"""
import importlib.util
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from forge_sentinel import data, engine  # noqa: E402

DS = ROOT / "datasets"


def load(name):
    return data.parse_csv((DS / name).read_bytes())


def stream(rows, machine):
    return [r for r in rows if r["machine"] == machine]


def first_signal_build(a):
    return a.flags[0].index + 1 if a.flags else None


class Reproducible(unittest.TestCase):
    def test_generator_recreates_identical_files(self):
        spec = importlib.util.spec_from_file_location("gen", DS / "generate_datasets.py")
        gen = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gen)
        with tempfile.TemporaryDirectory() as tmp:
            gen.OUT = pathlib.Path(tmp)
            gen.main.__globals__["OUT"] = gen.OUT
            import contextlib, io
            with contextlib.redirect_stdout(io.StringIO()):
                gen.main()
            for name in ("01_stable_capable.csv", "02_oxygen_drift.csv", "03_strength_only.csv", "04_coupon_spread.csv"):
                self.assertEqual((DS / name).read_bytes(), (pathlib.Path(tmp) / name).read_bytes(), name)


class StableCapable(unittest.TestCase):
    rows = load("01_stable_capable.csv")

    def test_shape(self):
        self.assertEqual(len(self.rows), 100)
        self.assertEqual(data.machine_list(self.rows), ["LPBF-A", "LPBF-B"])

    def test_both_machines_stable_and_capable(self):
        for m in ("LPBF-A", "LPBF-B"):
            a = engine.analyze_stream(stream(self.rows, m), usl=1100)
            self.assertTrue(a.stable, m)
            self.assertEqual(len(a.fails), 0, m)
            self.assertGreater(a.cpk, 1.33, m)
            self.assertGreater(a.cap["Ppk"], 1.33, m)
            self.assertEqual(engine.decision_text(a), "No SPC signals detected — qualification review required")


class OxygenDrift(unittest.TestCase):
    rows = load("02_oxygen_drift.csv")

    def test_oxygen_flags_before_strength(self):
        a = engine.analyze_stream(self.rows, usl=1100)
        ox = engine.analyze_stream(self.rows, "oxygen")
        self.assertEqual(first_signal_build(ox), 44)
        self.assertEqual(first_signal_build(a), 49)

    def test_failures_and_verdict(self):
        a = engine.analyze_stream(self.rows, usl=1100)
        self.assertEqual([r["id"] for r in a.fails], ["C-056", "C-057", "C-060"])
        self.assertFalse(a.stable)
        self.assertLess(a.cap["Ppk"], 1.0)

    def test_no_signals_before_leak_or_after_repair(self):
        a = engine.analyze_stream(self.rows, usl=1100)
        builds = [f.index + 1 for f in a.flags]
        self.assertTrue(all(45 <= b <= 63 for b in builds), builds)

    def test_oxygen_is_top_suspect(self):
        top = engine.associations(self.rows)[0]
        self.assertEqual(top["v"], "oxygen")
        self.assertLess(top["r"], -0.8)


class StrengthOnly(unittest.TestCase):
    rows = load("03_strength_only.csv")

    def test_minimal_columns(self):
        self.assertEqual(engine.available_vars(self.rows), ["strength"])

    def test_shift_caught_before_any_failure(self):
        a = engine.analyze_stream(self.rows, usl=1100)
        self.assertEqual(first_signal_build(a), 36)
        self.assertEqual(len(a.fails), 0)
        self.assertLess(a.cap["Ppk"], 1.0)


if __name__ == "__main__":
    unittest.main()
