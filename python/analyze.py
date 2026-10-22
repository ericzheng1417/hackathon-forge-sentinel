"""Forge Sentinel offline analysis. Python 3.10+, standard library only.
Usage: python python/analyze.py builds.csv --machine LPBF-01 --lsl 900 --usl 1100 > report.json
       python python/analyze.py builds.csv --machine LPBF-01 --tests 1,2,3,4 --no-mr
Uses the same engine as the Shiny dashboard (forge_sentinel/engine.py).
"""
import argparse
import csv
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from forge_sentinel.engine import analyze  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path")
    parser.add_argument("--machine", required=True)
    parser.add_argument("--lsl", type=float, default=900)
    parser.add_argument("--usl", type=float, default=None, help="upper spec limit (omit for one-sided)")
    parser.add_argument("--baseline", type=int, default=25)
    parser.add_argument("--tests", default="1,2,3,4,5,6,7,8", help="comma-separated special-cause tests to apply")
    parser.add_argument("--no-mr", action="store_true", help="do not flag moving ranges above the MR UCL")
    parser.add_argument("--target", type=float, default=1.33)
    args = parser.parse_args()
    with open(args.csv_path, newline="", encoding="utf-8-sig") as handle:
        rows = [r for r in csv.DictReader(handle) if r["machine"] == args.machine]
    tests = [int(t) for t in args.tests.split(",") if t.strip()]
    print(json.dumps(analyze(rows, args.lsl, args.baseline, args.target, args.usl, tests, not args.no_mr),
                     indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
