# Codebook

Definitions for every column Forge Sentinel reads. The same columns are used by the test datasets,
by CSV import in the app, and by `python/analyze.py`.

**One row = one build** (one print job on one machine) **with one representative tensile test
result.** Rows must be in the order the builds were made, oldest first, because the tool uses row
order as time order.

## File formats

- **CSV** (UTF-8, comma-separated, first row = headers), or
- **Excel workbook (.xlsx / .xlsm)**: the first worksheet whose first non-empty row contains `id`, `machine`
  and `strength` is used, so a cover or notes sheet in front is fine. Numbers should be stored as numbers.
  Formula cells use the value Excel last saved. Old `.xls` files must be re-saved as `.xlsx` or CSV.

The column rules below are the same for both formats.

## Summary

| Column | Required? | Type | Unit | Example | Valid values |
|---|---|---|---|---|---|
| `id` | **Required** | text | — | `C-044` | Unique within each machine |
| `machine` | **Required** | text | — | `LPBF-C` | Any label; each machine is analysed separately |
| `strength` | **Required** | number | MPa | `931.4` | > 0 |
| `oxygen` | Optional | number | ppm | `78.2` | ≥ 0 |
| `humidity` | Optional | number | % RH | `35.9` | 0–100 |
| `temperature` | Optional | number | °C | `200.4` | any |
| `power` | Optional | number | W | `281.0` | > 0 |
| `speed` | Optional | number | mm/s | `1203.5` | > 0 |
| `stress` | Optional | number | MPa | `141.7` | any (positive = tensile) |
| `build_date` | Ignored | date | ISO 8601 | `2026-07-14` | Kept for traceability; not used in calculations |

- **Optional** columns can be left out of the file entirely, or left blank for individual builds. Blank
  values are skipped for that variable only. A variable needs at least 10 recorded values before it is
  charted or correlated.
- **Ignored** columns, and any other extra columns, are accepted and not used.
- Column names are not case-sensitive. Use a decimal point, not a comma, for decimals. Don't include
  units or thousands separators in the cells.
- Each machine needs at least 30 rows, and strength must vary within the first 25 builds (zero
  variation usually means the measurement resolution is too coarse).

## Variables in detail

### `id` — build identifier
The build or job number the contractor already uses (traveller, job card or machine job ID). It links
each row back to the physical build and its test coupons. It must be unique within a machine.

### `machine` — printer
The printer the build ran on, e.g. `LPBF-A`. Control limits and capability are calculated **per
machine**, because each printer has its own normal variation. Only combine builds that use the same
part family, material, orientation and heat-treatment route.

### `strength` — ultimate tensile strength (MPa) · *required*
The highest stress a tensile test specimen withstands before breaking.

- **How it's measured:** a tensile test to ASTM E8/E8M on a witness coupon printed in the same build,
  in the same orientation as the bracket, and given the same heat treatment. Record one
  representative value per build: either the coupon designated by the test plan, or the build average
  if several coupons are pulled. Several coupons from one build are **not** independent results.
- **Why it matters:** this is the value the client's acceptance test checks. The default
  specification (900–1100 MPa) is illustrative. For reference, ASTM F2924 (Ti-6Al-4V made by powder
  bed fusion) sets a minimum tensile strength of 895 MPa; use the limits in your contract or drawing.
- **Who has it:** every contractor that is being tested by the client already has this number.

### `oxygen` — build-chamber oxygen (ppm) · optional
Oxygen concentration in the argon atmosphere of the build chamber.

- **How it's measured:** the printer's built-in oxygen sensor, which most LPBF machines log
  continuously. Record the **average over the build** from the machine log or build report (or the
  maximum, as long as you're consistent).
- **Why it matters:** titanium reacts readily with oxygen. A leaking seal, a poor purge or a saturated
  gas filter raises chamber oxygen, which leads to oxidised spatter and lack-of-fusion defects. Default
  alarm threshold: 100 ppm (illustrative; editable in Configure).

### `humidity` — relative humidity (%) · optional
Relative humidity of the build room or powder-handling area at the start of the build.

- **How it's measured:** a room hygrometer or the facility's environmental monitoring system.
- **Why it matters:** moisture absorbed by titanium powder adds oxygen and hydrogen and can cause
  porosity. Default alarm threshold: 40% (illustrative).

### `temperature` — build-plate temperature (°C) · optional
Set point or measured temperature of the heated build plate.

- **How it's measured:** the machine log (plate thermocouple) or the build parameter file.
- **Why it matters:** plate temperature affects cooling rates, residual stress and microstructure.

### `power` — laser power (W) · optional
Laser power used for the bulk (infill) of the part.

- **How it's measured:** the build parameter file, or the machine's laser power log if available.
- **Why it matters:** too little energy causes lack-of-fusion porosity; too much causes keyhole porosity.
  A drop in delivered power, for example from a dirty window or a degrading laser, lowers strength.

### `speed` — scan speed (mm/s) · optional
Laser scan speed for the bulk of the part.

- **How it's measured:** the build parameter file.
- **Why it matters:** together with power, layer thickness and hatch spacing it sets the energy
  density delivered to the powder.

### `stress` — residual stress (MPa) · optional
Residual stress measured on a witness sample, positive = tensile.

- **How it's measured:** X-ray diffraction (ASTM E2860) or hole drilling (ASTM E837) on a witness
  coupon, after the same heat treatment as the parts.
- **Why it matters:** high residual stress can cause distortion and cracking and indicates an
  incomplete stress relief.
- **Note:** this needs specialist equipment, so many contractors only measure it on a sample of builds.
  That's why it's optional and blank cells are allowed.

### `build_date` — build start date · ignored
ISO date (YYYY-MM-DD) when the build started. It's included in the test datasets for traceability but is
not used in any calculation; row order defines time order.

## Minimum dataset

The smallest valid file has just three columns:

```
id,machine,strength
D-001,LPBF-D,976.3
D-002,LPBF-D,971.6
...
```

With this the tool still produces control charts, the 8 tests, descriptive statistics, Cp/Cpk/Pp/Ppk and
the pass rate. Adding process columns unlocks Parameter analysis, which helps find the cause of a problem.
