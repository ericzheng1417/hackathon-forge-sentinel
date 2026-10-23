"""Demonstration data, CSV / Excel import validation, and CSV / Excel export.

CSV handling uses only the standard library. Excel (.xlsx) support uses the
`openpyxl` package, imported only when an Excel file is actually read or written,
so the engine and command-line tool still run without it for CSV files.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import math
import statistics as st

from .engine import COLUMNS, FIELDS, REQUIRED_COLUMNS, VARS, present

MAX_BYTES = 2_000_000          # CSV upload limit
MAX_EXCEL_BYTES = 5_000_000    # .xlsx files are larger for the same data
MIN_ROWS_PER_MACHINE = 30      # builds per machine, one result per build (I-MR chart)
MIN_SUBGROUPS_PER_MACHINE = 20 # builds per machine when several coupons per build are recorded (X̄-S)
EXCEL_EXTENSIONS = (".xlsx", ".xlsm")

# Test datasets shipped in datasets/ (see datasets/README.md): key -> (file name, display name)
SAMPLE_DATASETS = {
    "stable": ("01_stable_capable.csv", "Stable & capable"),
    "drift": ("02_oxygen_drift.csv", "Oxygen drift"),
    "minimal": ("03_strength_only.csv", "Strength only (minimal inputs)"),
    "coupons": ("04_coupon_spread.csv", "4 coupons per build (X̄-S)"),
}


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
    """Raised with a user-facing message when an uploaded file fails validation."""


def read_upload(raw: bytes, filename: str) -> list[dict]:
    """Parse an uploaded file by extension: .xlsx/.xlsm → parse_excel, anything else → parse_csv."""
    name = (filename or "").lower()
    if name.endswith(EXCEL_EXTENSIONS):
        return parse_excel(raw)
    if name.endswith(".xls"):
        raise ImportError_("Old .xls files aren't supported. In Excel, use File → Save As → Excel Workbook (.xlsx) "
                           "or CSV UTF-8.")
    return parse_csv(raw)


def parse_csv(raw: bytes | str) -> list[dict]:
    """Validate an uploaded CSV and return rows as dicts.

    Required columns: id, machine, strength. Optional columns: oxygen, humidity,
    temperature, power, speed, stress — they may be left out entirely, or have
    blank cells; missing values become None. Extra columns are ignored. Raises
    ImportError_ with a user-facing message on the first problem found.
    """
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
    return validate_table(lines)


def _excel_cell(v) -> str:
    """Convert an Excel cell value to the text form the validator expects."""
    if v is None:
        return ""
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    if isinstance(v, (dt.datetime, dt.date)):
        return v.isoformat()
    return str(v)


def parse_excel(raw: bytes) -> list[dict]:
    """Validate an uploaded Excel workbook (.xlsx) and return rows as dicts.

    Uses the first worksheet whose first non-empty row contains the required
    headers (id, machine, strength); otherwise the first worksheet. Cell values
    are read as stored (formula cells use the result Excel last saved). The same
    rules as parse_csv then apply.
    """
    if len(raw) > MAX_EXCEL_BYTES:
        raise ImportError_("Maximum Excel file size is 5 MB.")
    try:
        import openpyxl
    except ImportError:  # pragma: no cover - depends on the environment
        raise ImportError_("Excel import needs the openpyxl package (pip install openpyxl). "
                           "Or save the sheet as CSV UTF-8.") from None
    try:
        wb = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    except Exception:
        raise ImportError_("Could not open the file as an Excel workbook (.xlsx).") from None
    try:
        sheets = []
        for ws in wb.worksheets:
            rows = [[_excel_cell(c) for c in row] for row in ws.iter_rows(values_only=True)]
            rows = [r for r in rows if any(c.strip() for c in r)]
            sheets.append(rows)
            if rows and all(h in [c.strip().lower() for c in rows[0]] for h in REQUIRED_COLUMNS):
                break
        else:
            rows = sheets[0] if sheets else []
    finally:
        wb.close()
    if rows:
        width = len(rows[0])
        while width and not rows[0][width - 1].strip():   # drop trailing blank header cells
            width -= 1
        rows = [(r + [""] * width)[:width] for r in rows]
    return validate_table(rows)


def validate_table(lines: list[list[str]]) -> list[dict]:
    """Shared validation for CSV and Excel: header row first, then one row per build (all text)."""
    if not lines:
        raise ImportError_("The file is empty.")
    lines = list(lines)
    head = [h.strip().lower() for h in lines.pop(0)]
    missing = [h for h in REQUIRED_COLUMNS if h not in head]
    if missing:
        raise ImportError_(f"Missing required column(s): {', '.join(missing)}. Only id, machine and strength are required.")
    if len(set(head)) != len(head):
        raise ImportError_("Duplicated column headers. Download the example for the exact format.")
    idx = {h: head.index(h) for h in COLUMNS if h in head}
    seen, parsed = set(), []
    for n, line in enumerate(lines, start=2):
        if len(line) != len(head):
            raise ImportError_(f"Row {n}: wrong number of columns.")
        r: dict = {k: None for k in COLUMNS if k != "coupon" or "coupon" in idx}
        for k in idx:
            val = line[idx[k]].strip()
            if not val:
                if k in REQUIRED_COLUMNS:
                    raise ImportError_(f"Row {n}: {k} is missing.")
                continue  # optional measurement not recorded for this build
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
        bad = [k for k, ok in (("strength", lambda v: v > 0), ("oxygen", lambda v: v >= 0),
                               ("humidity", lambda v: 0 <= v <= 100), ("power", lambda v: v > 0),
                               ("speed", lambda v: v > 0)) if present(r[k]) and not ok(r[k])]
        if bad:
            raise ImportError_(f"Row {n}: {', '.join(bad)} outside physical range.")
        key = (r["machine"], r["id"], r.get("coupon"))
        if key in seen:
            if "coupon" in idx:
                raise ImportError_(f"Row {n}: duplicate coupon {r['coupon']!r} for build {r['id']!r}.")
            raise ImportError_(f"Row {n}: duplicate build ID. If you test several coupons per build, add a "
                               "'coupon' column (e.g. 1, 2, 3) so each row is one coupon.")
        seen.add(key)
        parsed.append(r)
    machines = machine_list(parsed)
    if not machines:
        raise ImportError_("The file has no data rows.")
    for m in machines:
        builds = {r["id"] for r in parsed if r["machine"] == m}
        n_rows = sum(r["machine"] == m for r in parsed)
        need = MIN_SUBGROUPS_PER_MACHINE if n_rows > len(builds) else MIN_ROWS_PER_MACHINE
        if len(builds) < need:
            raise ImportError_(f"Machine {m!r} has {len(builds)} builds; at least {need} are needed"
                               + (" when several coupons per build are recorded." if need == MIN_SUBGROUPS_PER_MACHINE
                                  else " (one row per build)."))
    for m in machines:
        base = [r["strength"] for r in parsed if r["machine"] == m][:25]
        if st.stdev(base) == 0:
            raise ImportError_("Strength baseline has zero variation; check measurement resolution.")
    return parsed


def machine_list(rows: list[dict]) -> list[str]:
    return list(dict.fromkeys(r["machine"] for r in rows))


def to_csv(rows: list[dict]) -> str:
    """CSV with the required columns plus every optional column that has any value."""
    cols = list(REQUIRED_COLUMNS[:2]) + (["coupon"] if any(present(r.get("coupon")) for r in rows) else []) + [c for c in FIELDS
                                         if c == "strength" or any(present(r.get(c)) for r in rows)]
    buf = io.StringIO()
    w = csv.writer(buf, quoting=csv.QUOTE_ALL, lineterminator="\n")
    w.writerow(cols)
    for r in rows:
        w.writerow([_fmt_cell(r.get(c)) for c in cols])
    return buf.getvalue()


def to_xlsx(rows: list[dict], sheet: str = "builds") -> bytes:
    """Excel workbook with the same columns as to_csv (needs openpyxl)."""
    import openpyxl
    from openpyxl.styles import Font

    cols = list(REQUIRED_COLUMNS[:2]) + (["coupon"] if any(present(r.get("coupon")) for r in rows) else []) + [c for c in FIELDS
                                         if c == "strength" or any(present(r.get(c)) for r in rows)]
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet
    ws.append(cols)
    for c in ws[1]:
        c.font = Font(bold=True)
    for r in rows:
        ws.append([r.get(c) for c in cols])
    for i, c in enumerate(cols, start=1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = 12 if c in VARS or c == "machine" else 10
    ws.freeze_panes = "A2"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _fmt_cell(v):
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)
