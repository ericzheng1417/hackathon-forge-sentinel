"""Demonstration data, CSV import validation and CSV export."""
from __future__ import annotations

import csv
import io
import math
import statistics as st

from .engine import COLUMNS, FIELDS

MAX_BYTES = 2_000_000
MIN_ROWS_PER_MACHINE = 30


def _r1(v: float) -> float:
    return float(f"{v:.1f}")


def seed_rows() -> list[dict]:
    """Synthetic streams: LPBF-01 deteriorates after build 39; LPBF-02 is a comparison stream."""
    rows = []
    for m in (1, 2):
        for i in range(60):
            drift = (i - 38) * 3.6 if m == 1 and i >= 39 else 0
            noise = math.sin(i * 2.39) * 15 + math.cos(i * 1.12) * 8
            rows.append({
                "id": f"B{m}-{i + 1:03d}",
                "machine": f"LPBF-0{m}",
                "strength": _r1(965 + noise - drift),
                "oxygen": _r1(52 + math.sin(i * 1.34) * 9 + drift * 1.3),
                "humidity": _r1(29 + math.cos(i * 0.83) * 4 + drift * 0.14),
                "temperature": _r1(201 + math.sin(i * 0.8) * 5),
                "power": _r1(280 + math.sin(i * 1.8) * 5 - drift * 0.11),
                "speed": _r1(1200 + math.sin(i * 1.4) * 28),
                "stress": _r1(135 + math.cos(i * 0.9) * 17 + drift * 0.7),
            })
    return rows


class ImportError_(ValueError):
    """Raised with a user-facing message when a CSV fails validation."""


def parse_csv(raw: bytes | str) -> list[dict]:
    """Validate an uploaded CSV with the same rules as the original web importer."""
    if isinstance(raw, bytes):
        if len(raw) > MAX_BYTES:
            raise ImportError_("Maximum CSV size is 2 MB.")
        try:
            raw = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise ImportError_("File must be UTF-8 encoded text.") from None
    raw = raw.lstrip("﻿")
    try:
        lines = [row for row in csv.reader(io.StringIO(raw, newline=""), strict=True)
                 if any(c.strip() for c in row)]
    except csv.Error as e:
        raise ImportError_(f"Could not parse CSV: {e}.") from None
    if not lines:
        raise ImportError_("The file is empty.")
    head = [h.strip() for h in lines.pop(0)]
    if any(h not in head for h in COLUMNS) or len(set(head)) != len(head):
        raise ImportError_("Missing or duplicated column headers. Download the example for the exact format.")
    idx = {h: head.index(h) for h in COLUMNS}
    seen, parsed = set(), []
    for n, line in enumerate(lines, start=2):
        if len(line) != len(head):
            raise ImportError_(f"Row {n}: wrong number of columns.")
        r: dict = {}
        for k in COLUMNS:
            val = line[idx[k]].strip()
            if not val:
                raise ImportError_(f"Row {n}: {k} is missing.")
            if k in FIELDS:
                try:
                    num = float(val)
                except ValueError:
                    num = math.nan
                if not math.isfinite(num):
                    raise ImportError_(f"Row {n}: {k} must be numeric.")
                r[k] = num
            else:
                r[k] = val
        if (r["strength"] <= 0 or r["oxygen"] < 0 or not 0 <= r["humidity"] <= 100
                or r["power"] <= 0 or r["speed"] <= 0):
            raise ImportError_(f"Row {n}: values outside physical range.")
        key = (r["machine"], r["id"])
        if key in seen:
            raise ImportError_(f"Row {n}: duplicate build ID.")
        seen.add(key)
        parsed.append(r)
    machines = machine_list(parsed)
    if not machines or any(sum(r["machine"] == m for r in parsed) < MIN_ROWS_PER_MACHINE for m in machines):
        raise ImportError_(f"Every machine needs at least {MIN_ROWS_PER_MACHINE} complete rows.")
    for m in machines:
        base = [r["strength"] for r in parsed if r["machine"] == m][:25]
        if st.stdev(base) == 0:
            raise ImportError_("Strength baseline has zero variation; check measurement resolution.")
    return parsed


def machine_list(rows: list[dict]) -> list[str]:
    return list(dict.fromkeys(r["machine"] for r in rows))


def to_csv(rows: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, quoting=csv.QUOTE_ALL, lineterminator="\n")
    w.writerow(COLUMNS)
    for r in rows:
        w.writerow([_fmt_cell(r[c]) for c in COLUMNS])
    return buf.getvalue()


def _fmt_cell(v):
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)
