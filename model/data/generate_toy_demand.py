"""
Generate parametric "toy" demand profiles for STORM (line 1 of the dashboard
plan, consultora/DASHBOARD_PLAN.md).

These are deterministic, schedule-driven demand profiles meant to build
intuition and sanity-check STORM's response — *not* real metered data. They
emit the same format the model reads: a single `demand_kw` column, one row per
15-minute interval, 35,040 rows = one year (365 * 96).

Two shapes (Oscar's idea, 2026-06-13):

  * "step"  — simple step: `base_kw` overnight, jumps to `level_kw` during the
              working window [on_hour, off_hour).
  * "lunch" — double step: same, but drops to `lunch_level` * level during the
              lunch window [lunch_on, lunch_off) (the "efecto almuerzo").

Files are written as `demand_case_toy_<name>.csv`, so they load through the
normal path with `--case case_toy_<name>` (data_loader resolves
`demand_{case}.csv`).

Usage:
  python3 generate_toy_demand.py                 # canonical step + lunch pair
  python3 generate_toy_demand.py --sweep         # + entry/exit-hour sweep
  python3 generate_toy_demand.py --level 450     # FCQ-sized (~3x) toy
  python3 generate_toy_demand.py --report-only   # band breakdown, no files

The band breakdown reports energy split across the MEM time bands so the
schedule sensitivity is visible without running the MILP. Band definition
mirrors cfg.PPAD_PEAK_HOURS = range(18, 23):
  pico  = hours 18-22   (5 h)   peak — most expensive
  resto = hours 5-17    (13 h)
  valle = hours 23-4    (6 h)   off-peak — cheapest
"""

import argparse
import os

import numpy as np
import pandas as pd

INTERVALS_PER_HOUR = 4          # 15-min resolution
DAY_INTERVALS = 24 * INTERVALS_PER_HOUR   # 96
YEAR_DAYS = 365
YEAR_INTERVALS = YEAR_DAYS * DAY_INTERVALS  # 35,040

# MEM/EPEC time bands by hour-of-day (mirrors cfg.PPAD_PEAK_HOURS = range(18, 23)).
PICO_HOURS = set(range(18, 23))            # 18,19,20,21,22
RESTO_HOURS = set(range(5, 18))            # 5..17
VALLE_HOURS = set(range(0, 5)) | {23}      # 0..4, 23


def build_day_profile(
    level_kw: float = 300.0,
    base_kw: float = 0.0,
    on_hour: float = 6.0,
    off_hour: float = 18.0,
    lunch: bool = False,
    lunch_on: float = 13.0,
    lunch_off: float = 14.0,
    lunch_level: float = 0.5,
    ramp_intervals: int = 0,
) -> np.ndarray:
    """Build one 24 h day as a 96-vector of kW at 15-min resolution.

    Hours may be fractional (e.g. 6.5 -> 06:30). `lunch_level` is a fraction of
    `level_kw` held during the lunch window. `ramp_intervals` linearly smooths
    each transition over N intervals (0 = instantaneous step).
    """
    t = np.arange(DAY_INTERVALS)
    hour = t / INTERVALS_PER_HOUR  # hour-of-day for each interval start

    working = (hour >= on_hour) & (hour < off_hour)
    profile = np.where(working, level_kw, base_kw).astype(np.float64)

    if lunch:
        in_lunch = (hour >= lunch_on) & (hour < lunch_off)
        profile = np.where(in_lunch, lunch_level * level_kw, profile)

    if ramp_intervals > 0:
        kernel = np.ones(ramp_intervals) / ramp_intervals
        # circular smoothing so the day tiles seamlessly
        ext = np.concatenate([profile[-ramp_intervals:], profile, profile[:ramp_intervals]])
        smoothed = np.convolve(ext, kernel, mode="same")
        profile = smoothed[ramp_intervals:ramp_intervals + DAY_INTERVALS]

    return profile


def build_year(day_profile: np.ndarray, weekend_factor: float = 1.0) -> np.ndarray:
    """Tile a day profile across a full year (35,040 intervals).

    `weekend_factor` scales Saturday/Sunday demand (1.0 = identical every day).
    Day 0 is treated as a Monday.
    """
    if weekend_factor == 1.0:
        return np.tile(day_profile, YEAR_DAYS)

    days = []
    for d in range(YEAR_DAYS):
        is_weekend = (d % 7) in (5, 6)  # day 0 = Monday
        days.append(day_profile * weekend_factor if is_weekend else day_profile)
    return np.concatenate(days)


def band_breakdown(year_kw: np.ndarray) -> dict:
    """Split annual energy (MWh) across MEM time bands and report peak kW."""
    t = np.arange(len(year_kw))
    hour = (t // INTERVALS_PER_HOUR) % 24
    energy_mwh = year_kw / INTERVALS_PER_HOUR / 1000.0  # kW * 0.25 h -> kWh -> MWh

    pico_mask = np.isin(hour, list(PICO_HOURS))
    resto_mask = np.isin(hour, list(RESTO_HOURS))
    valle_mask = np.isin(hour, list(VALLE_HOURS))

    total = energy_mwh.sum()
    return {
        "peak_kw": float(year_kw.max()),
        "total_mwh": float(total),
        "pico_mwh": float(energy_mwh[pico_mask].sum()),
        "resto_mwh": float(energy_mwh[resto_mask].sum()),
        "valle_mwh": float(energy_mwh[valle_mask].sum()),
        "pico_pct": float(100 * energy_mwh[pico_mask].sum() / total) if total else 0.0,
    }


def _print_report(name: str, year_kw: np.ndarray) -> None:
    b = band_breakdown(year_kw)
    print(
        f"  {name:<28} peak={b['peak_kw']:7.1f} kW  "
        f"total={b['total_mwh']:8.1f} MWh  "
        f"pico={b['pico_mwh']:7.1f} ({b['pico_pct']:4.1f}%)  "
        f"resto={b['resto_mwh']:7.1f}  valle={b['valle_mwh']:6.1f}"
    )


def write_case(data_dir: str, name: str, year_kw: np.ndarray) -> str:
    """Write a `demand_case_toy_<name>.csv` and return its path."""
    assert len(year_kw) == YEAR_INTERVALS, f"{name}: expected {YEAR_INTERVALS} rows, got {len(year_kw)}"
    path = os.path.join(data_dir, f"demand_case_toy_{name}.csv")
    pd.DataFrame({"demand_kw": year_kw}).to_csv(path, index=False)
    return path


def main():
    parser = argparse.ArgumentParser(description="Generate STORM toy demand profiles.")
    parser.add_argument("--data-dir", default=os.path.dirname(__file__),
                        help="Output directory (default: this folder).")
    parser.add_argument("--level", type=float, default=300.0,
                        help="Working-window demand in kW (default 300; use ~450 for FCQ-sized x3).")
    parser.add_argument("--base", type=float, default=0.0,
                        help="Overnight/idle demand in kW (default 0).")
    parser.add_argument("--ramp", type=int, default=0,
                        help="Smooth transitions over N 15-min intervals (default 0 = hard step).")
    parser.add_argument("--weekend-factor", type=float, default=1.0,
                        help="Scale Sat/Sun demand (default 1.0 = same every day).")
    parser.add_argument("--sweep", action="store_true",
                        help="Also emit entry/exit-hour sweep variants.")
    parser.add_argument("--report-only", action="store_true",
                        help="Print band breakdowns without writing any files.")
    args = parser.parse_args()

    common = dict(level_kw=args.level, base_kw=args.base, ramp_intervals=args.ramp)

    # --- Canonical pair ---------------------------------------------------
    cases = []
    cases.append(("step", build_year(
        build_day_profile(on_hour=6, off_hour=18, **common), args.weekend_factor)))
    cases.append(("lunch", build_year(
        build_day_profile(on_hour=6, off_hour=18, lunch=True,
                          lunch_on=13, lunch_off=14, lunch_level=0.5, **common),
        args.weekend_factor)))

    # --- Schedule sweep ---------------------------------------------------
    if args.sweep:
        # Entry-hour sweep (fixed exit 18:00): 06 / 07 / 08
        for on in (6, 7, 8):
            cases.append((f"step_on{on:02d}", build_year(
                build_day_profile(on_hour=on, off_hour=18, **common), args.weekend_factor)))
        # Exit-hour sweep (fixed entry 06:00): 17 / 18 / 19 — 19 leaks into pico
        for off in (17, 18, 19):
            cases.append((f"step_off{off:02d}", build_year(
                build_day_profile(on_hour=6, off_hour=off, **common), args.weekend_factor)))

    action = "Reporting" if args.report_only else "Writing"
    print(f"{action} {len(cases)} toy case(s)  "
          f"(level={args.level} kW, base={args.base} kW, ramp={args.ramp}, "
          f"weekend_factor={args.weekend_factor}):")
    for name, year_kw in cases:
        if not args.report_only:
            path = write_case(args.data_dir, name, year_kw)
            print(f"-> {os.path.basename(path)}")
        _print_report(f"toy_{name}", year_kw)

    if not args.report_only:
        print("\nLoad in STORM with, e.g.:  python3 storm.py solve --case case_toy_step --days 7")


if __name__ == "__main__":
    main()
