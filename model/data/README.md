# model/data/ — Self-contained Data for the STORM Model

This folder makes the model fully standalone. All data files are extracted
from the original course materials (`material-ucema/`) and stored as standard
CSV files that the model reads directly.

## Contents

| File | Source | Description |
|------|--------|-------------|
| `demand_case_3.csv` | Original: `Caso 3` sheet | 15-min demand profile, 35,040 rows, 5.50 GWh/year, 1.25 MW peak. |
| `demand_case_10.csv` | Original: `Caso 10` sheet | 15-min demand profile, 35,040 rows, 0.61 GWh/year, 171 kW peak. |
| `solar_irradiance_cordoba.csv` | Legacy computed profile | PV power factor (kW/kWp) at 15-min resolution. The loader converts it to interval kWh/kWp and scales it for Buenos Aires/La Plata. |
| `monthly_billing/caso_{1,2,6,7,9}.csv` | Original: monthly billing sheets | Monthly energy and power data for additional case studies. |

## Format

All CSV files are plain text with a single header row:

- `demand_case_*.csv`: `demand_kw`
- `solar_irradiance_cordoba.csv`: `solar_factor`
- `monthly_billing/*.csv`: original columns from the course Excel

## How data is loaded

`data_loader.py` reads from `model/data/` by default, with a fallback to
synthetic generation if a file is missing (for development/testing). The
source demand and PV files are 15-minute power-like series. If a runner changes
`DELTA_T` (for example to 1 hour on the server), the loader averages power/rate
values to the model interval before scenario generation converts demand and PV
to interval energy. Runners can also set `START_INTERVAL` to extract a seasonal
slice instead of always starting on January 1.

## Regeneration

To regenerate this folder from the course materials, run:
```bash
python3 model/data/extract_from_course.py
```

## Notes

- DTE spot prices are shipped separately due to size (~150 MB of zip files).
  The model falls back to synthetic prices when `dte_prices_15min.csv` or
  `dte_prices_hourly.csv` is absent.
- `solar_irradiance_cordoba.csv` is retained as a standalone proxy, not as a
  claim that the UCEMA cases are physically located in Cordoba.
- The model folder is designed to work without any external dependencies
  beyond Python and Gurobi — everything needed for numerical execution is here.
