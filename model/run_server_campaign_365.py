"""Full-year server campaign for STORM paper figures.

This runner mirrors ``run_server_campaign.py`` but makes the main paper
phases true 365-day, 15-minute runs. Outputs are written to
``output/campaign_365`` so they do not overwrite the existing 42-day paper
campaign.
"""

import argparse
import json
import os
import sys
from dataclasses import asdict
from typing import Callable, Dict, List

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config as cfg
import run_server_campaign as base


OUT = os.path.join(cfg.OUTPUT_DIR, "campaign_365")

FULL_YEAR_DAYS = 365
FULL_YEAR_SCENARIOS = 12
FULL_YEAR_DELTA_T = 0.25
FULL_YEAR_TIMEOUT = 14400
FULL_YEAR_MIP_GAP = 0.02

# The case/seasonal figure still needs seasonal comparisons. These quarter
# windows are longer than the original 21-day representative windows while
# preserving the same seasonal interpretation.
SEASONAL_WINDOWS = (
    ("summer_91d", 0, 91, 0),
    ("fall_91d", 91, 91, 3),
    ("winter_91d", 182, 91, 6),
    ("spring_92d", 273, 92, 9),
)


_SEED_OVERRIDE: int = None


def set_seed_override(seed: int = None) -> None:
    """Stamp ``seed`` onto every subsequent RunConfig produced here."""
    global _SEED_OVERRIDE
    _SEED_OVERRIDE = seed


def full_year_config(**overrides) -> base.RunConfig:
    values = asdict(
        base.RunConfig(
            name="base_365d_12s",
            num_days=FULL_YEAR_DAYS,
            num_scenarios=FULL_YEAR_SCENARIOS,
            delta_t=FULL_YEAR_DELTA_T,
            solver_timeout=FULL_YEAR_TIMEOUT,
            mip_gap=FULL_YEAR_MIP_GAP,
        )
    )
    if _SEED_OVERRIDE is not None and "random_seed" not in overrides:
        values["random_seed"] = _SEED_OVERRIDE
    values.update(overrides)
    return base.RunConfig(**values)


def phase_base() -> List[Dict]:
    return base.run_configs([full_year_config()])


def phase_cvar() -> List[Dict]:
    return base.run_configs(
        full_year_config(name=f"cvar_beta_{beta}", cvar_beta=beta)
        for beta in [0.0, 0.25, 0.5, 1.0, 2.0]
    )


def phase_bess() -> List[Dict]:
    return base.run_configs(
        full_year_config(name=f"bess_cost_{cost}", gamma_bess=cost)
        for cost in [200, 300, 450, 600, 800, 1000]
    )


def phase_pv() -> List[Dict]:
    return base.run_configs(
        full_year_config(name=f"pv_cost_{cost}", gamma_pv=cost)
        for cost in [400, 550, 700, 900]
    )


def phase_mater() -> List[Dict]:
    return base.run_configs(
        full_year_config(name=f"mater_price_{price}", contract_mater_price=price)
        for price in [45, 50, 59, 70, 90]
    )


def phase_mate() -> List[Dict]:
    return base.run_configs(
        full_year_config(name=f"mate_price_{price}", contract_mate_price=price)
        for price in [45, 50, 56, 65, 75]
    )


def phase_ppad() -> List[Dict]:
    return base.run_configs(
        full_year_config(name=f"ppad_spot_{price}", ppad_spot_price=price)
        for price in [8, 12, 16, 20, 24]
    )


def phase_fsa() -> List[Dict]:
    """P2 FSA>0 sensitivity. Sweeps the mean spot energy price upward to mimic
    the post-2027 transition when FSA stops being zero. The MATER/MATE prices
    and the PPAD reference are kept at their base values."""
    return base.run_configs(
        full_year_config(
            name=f"fsa_spot_{mean:g}",
            spot_energy_mean_usd_per_mwh=mean,
        )
        for mean in [60, 80, 100, 120]
    )


def phase_top() -> List[Dict]:
    """Take-or-pay penalty sensitivity. Sweeps c^TOP applied uniformly to MATER
    and MATE. At the baseline TOP=10 USD/MWh the penalty is dormant for the
    Case-3 365-day scenario set; this sweep demonstrates the threshold at
    which the penalty starts shrinking the commitment Q."""
    return base.run_configs(
        full_year_config(
            name=f"top_{penalty:g}",
            contract_top_penalty_usd_per_mwh=penalty,
        )
        for penalty in [0, 10, 30, 50, 100, 200]
    )


def phase_cases() -> List[Dict]:
    return base.run_configs(
        [
            full_year_config(name="case_3_base", active_case="case_3"),
            full_year_config(name="case_10_base", active_case="case_10"),
        ]
    )


def phase_baselines() -> List[Dict]:
    rc = full_year_config(name="baselines_365d_12s")
    base.patch_config(rc)

    import importlib

    import baselines
    import data_loader
    import model_milp
    import scenario_gen

    importlib.reload(data_loader)
    importlib.reload(scenario_gen)
    importlib.reload(model_milp)
    importlib.reload(baselines)

    print(
        f"  baselines_365d_12s      case={rc.active_case} "
        f"horizon={rc.num_days}d dt={rc.delta_t}h scenarios={rc.num_scenarios}"
    )
    scenarios = scenario_gen.generate_scenarios()
    rows = baselines.run_baseline_suite(
        scenarios,
        include_extended=True,
        cvar_beta=rc.cvar_beta,
    )
    for row in rows:
        row["active_case"] = rc.active_case
        row["num_days"] = rc.num_days
        row["num_scenarios"] = rc.num_scenarios
        row["start_day"] = rc.start_day
        row["month_offset"] = rc.month_offset
        row["delta_t"] = rc.delta_t
        row["cvar_beta"] = row.get("cvar_beta", rc.cvar_beta)
        row["gamma_bess"] = rc.gamma_bess
        row["gamma_pv"] = rc.gamma_pv
        row["contract_mater_price"] = rc.contract_mater_price
        row["contract_mate_price"] = rc.contract_mate_price
        row["contract_matp_price"] = rc.contract_matp_price
        row["ppad_spot_price"] = rc.ppad_spot_price
        row["solver_timeout"] = rc.solver_timeout
        row["target_mip_gap"] = rc.mip_gap
        row["name"] = f"baseline_{row.get('strategy', 'unknown')}"
        print(
            f"    {row.get('strategy', row['name']):28s} "
            f"E[cost]={row.get('expected_total_cost')} "
            f"CVaR={row.get('cvar_total_cost')} "
            f"PV={row.get('C_PV')} BESS={row.get('C_BESS')}"
        )
    return rows


def phase_seasonal() -> List[Dict]:
    return base.run_configs(
        full_year_config(
            name=name,
            num_days=num_days,
            start_day=start_day,
            month_offset=month_offset,
        )
        for name, start_day, num_days, month_offset in SEASONAL_WINDOWS
    )


def phase_smoke() -> List[Dict]:
    return base.run_configs([base.lite_config(name="smoke_1d_2s_hourly")])


def phase_lite() -> List[Dict]:
    return base.phase_lite()


PHASES: Dict[str, tuple[str, Callable[[], List[Dict]]]] = {
    "base": ("00_base", phase_base),
    "cvar": ("01_cvar_beta", phase_cvar),
    "bess": ("02_bess_cost", phase_bess),
    "pv": ("03_pv_cost", phase_pv),
    "mater": ("04_mater_price", phase_mater),
    "mate": ("05_mate_price", phase_mate),
    "ppad": ("06_ppad_spot", phase_ppad),
    "cases": ("07_case_comparison", phase_cases),
    "seasonal": ("08_seasonal_windows", phase_seasonal),
    "baselines": ("09_baselines", phase_baselines),
    "fsa": ("10_fsa_spot", phase_fsa),
    "top": ("11_top_penalty", phase_top),
    "smoke": ("99_smoke", phase_smoke),
    "lite": ("98_lite", phase_lite),
}

PAPER_PHASES = [
    "base",
    "baselines",
    "cvar",
    "bess",
    "pv",
    "mater",
    "mate",
    "ppad",
    "cases",
    "seasonal",
]

PAPER_PHASES_EXTENDED = PAPER_PHASES + ["fsa", "top"]


def expand_phases(requested: List[str]) -> List[str]:
    expanded: List[str] = []
    for phase in requested:
        if phase == "paper":
            expanded.extend(PAPER_PHASES)
        elif phase == "all":
            expanded.extend(PAPER_PHASES_EXTENDED)
        else:
            expanded.append(phase)

    seen = set()
    ordered = []
    for phase in expanded:
        if phase not in PHASES:
            valid = ", ".join(sorted(PHASES))
            raise SystemExit(f"Unknown phase '{phase}'. Valid phases: {valid}, paper, all")
        if phase not in seen:
            ordered.append(phase)
            seen.add(phase)
    return ordered


def merge_results() -> None:
    all_results: List[Dict] = []
    for output_name, _ in PHASES.values():
        if output_name in {"99_smoke", "98_lite"}:
            continue
        path = os.path.join(OUT, f"{output_name}.json")
        if os.path.exists(path):
            with open(path) as f:
                data = json.load(f)
            all_results.extend(data if isinstance(data, list) else [data])
    if all_results:
        base.save_sweep("all_results", all_results)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the STORM full-year server campaign.")
    parser.add_argument(
        "phases",
        nargs="*",
        default=["paper"],
        help=(
            "Phases to run: smoke, lite, paper, all, base, baselines, cvar, "
            "bess, pv, mater, mate, ppad, cases, seasonal, fsa."
        ),
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip a phase if its JSON output already exists.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help=(
            "Override the scenario-generator seed for this run. When set, "
            "outputs are written to a per-seed subdirectory of the campaign "
            "folder so seeds do not overwrite each other."
        ),
    )
    parser.add_argument(
        "--seeds",
        type=int,
        nargs="+",
        default=None,
        help=(
            "Run the selected phases once per seed. Each seed produces a "
            "subdirectory <out>/seed_<seed>/ with its phase outputs."
        ),
    )
    return parser.parse_args()


def _run_phases_once(phases: List[str], skip_existing: bool, output_dir: str) -> None:
    os.makedirs(output_dir, exist_ok=True)
    base.OUT = output_dir
    for phase in phases:
        output_name, runner = PHASES[phase]
        output_path = os.path.join(output_dir, f"{output_name}.json")
        if skip_existing and os.path.exists(output_path):
            print(f"\n--- Skipping {phase}: {output_path} exists ---")
            continue
        print(f"\n--- Campaign: {output_name} ({phase}) ---")
        results = runner()
        base.save_sweep(output_name, results)


def _merge_in(output_dir: str) -> None:
    global OUT
    saved = OUT
    OUT = output_dir
    base.OUT = output_dir
    try:
        merge_results()
    finally:
        OUT = saved
        base.OUT = saved


def run_campaign(phases: List[str], seed: int = None, seeds: List[int] = None,
                 skip_existing: bool = False, output_dir: str = None) -> None:
    """Run one or more campaign phases.

    Importable entry point used by ``storm.py``. Parameters:

    phases
        Phase names. ``"paper"`` expands to all sensitivity phases used in the
        manuscript; ``"all"`` adds the FSA and TOP-penalty extensions.
    seed
        Optional single seed override; the phase outputs land in a
        ``seed_<seed>/`` subdirectory.
    seeds
        Optional list of seeds; one subdirectory per seed. Mutually exclusive
        with ``seed``.
    skip_existing
        If True, phases that already have a saved JSON output are skipped.
    output_dir
        Override the campaign output directory (default ``output/campaign_365``).
    """
    expanded = expand_phases(phases)

    if seeds and seed is not None:
        raise SystemExit("Use seed= for a single override or seeds= for a sweep, not both.")
    if seeds:
        seed_list = list(seeds)
    elif seed is not None:
        seed_list = [seed]
    else:
        seed_list = [None]

    out = output_dir or OUT
    print("=" * 72)
    print("STORM Full-Year Server Campaign")
    print(f"Host: {os.uname().nodename}")
    print(f"Output: {out}")
    print(f"Phases: {', '.join(expanded)}")
    print(f"Main horizon: {FULL_YEAR_DAYS}d, dt={FULL_YEAR_DELTA_T}h, scenarios={FULL_YEAR_SCENARIOS}")
    if seed_list == [None]:
        print(f"Seed: default ({cfg.RANDOM_SEED})")
    else:
        print(f"Seeds: {seed_list}")
    print("=" * 72)

    for s in seed_list:
        set_seed_override(s)
        phase_dir = out if s is None else os.path.join(out, f"seed_{s}")
        print(f"\n=== Seed {s if s is not None else cfg.RANDOM_SEED} -> {phase_dir} ===")
        _run_phases_once(expanded, skip_existing, phase_dir)
        if any(phase != "smoke" for phase in expanded):
            print("\n--- Merging completed campaign results ---")
            _merge_in(phase_dir)

    print("\nDone.")


def main() -> None:
    args = parse_args()
    run_campaign(
        phases=args.phases,
        seed=args.seed,
        seeds=args.seeds,
        skip_existing=args.skip_existing,
    )


if __name__ == "__main__":
    main()
