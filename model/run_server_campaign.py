"""Remote/local execution campaign for the STORM paper.

The representative paper campaign uses 42 days at 15-minute resolution,
12 stochastic scenarios, annualized OPEX, and a 2% MIP-gap target. This
runner reproduces the sensitivity phases, baseline comparison, and optional
hourly full-year check for validation.
"""

import argparse
import csv
import json
import os
import sys
import time
from dataclasses import asdict, dataclass
from typing import Callable, Dict, Iterable, List

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as cfg


OUT = os.path.join(cfg.OUTPUT_DIR, "campaign")
PAPER_DAYS = 42
PAPER_SCENARIOS = 12
PAPER_DELTA_T = 0.25
PAPER_TIMEOUT = 1800
PAPER_MIP_GAP = 0.02
LITE_DAYS = 1
LITE_SCENARIOS = 2
LITE_DELTA_T = 1.0


@dataclass
class RunConfig:
    name: str
    active_case: str = "case_3"
    num_days: int = PAPER_DAYS
    num_scenarios: int = PAPER_SCENARIOS
    start_day: int = 0
    month_offset: int = 0
    delta_t: float = PAPER_DELTA_T
    cvar_beta: float = 0.5
    gamma_bess: float = 600.0
    gamma_pv: float = 550.0
    contract_mater_price: float = 59.0
    contract_mate_price: float = 56.0
    contract_matp_price: float = 15.0
    ppad_spot_price: float = 16.0
    solver_timeout: int = PAPER_TIMEOUT
    mip_gap: float = PAPER_MIP_GAP
    # P2 FSA sensitivity: mean of the synthetic spot-energy distribution. None
    # leaves the configured default in place.
    spot_energy_mean_usd_per_mwh: float = None
    # P1 take-or-pay penalty (USD/MWh) applied uniformly to MATER and MATE.
    # None preserves whatever the config module already declares.
    contract_top_penalty_usd_per_mwh: float = None
    # P3 multi-seed support. None preserves cfg.RANDOM_SEED.
    random_seed: int = None


def _intervals_per_day(delta_t: float) -> int:
    return int(round(24.0 / delta_t))


def patch_config(rc: RunConfig) -> None:
    """Patch the global config module before reloading model modules."""
    cfg.ACTIVE_CASE = rc.active_case
    cfg.DELTA_T = rc.delta_t
    cfg.T = rc.num_days * _intervals_per_day(rc.delta_t)
    cfg.NUM_SCENARIOS = rc.num_scenarios
    cfg.START_INTERVAL = rc.start_day * _intervals_per_day(rc.delta_t)
    cfg.MONTH_OFFSET = rc.month_offset
    cfg.MONTH_BOUNDARIES = (
        cfg.month_boundaries_for_delta_t(cfg.DELTA_T)
        if rc.num_days == 365 and rc.start_day == 0
        else [0, cfg.T]
    )

    cfg.SCALE_OPEX_TO_YEAR = True
    cfg.SOLVER_TIMEOUT = rc.solver_timeout
    cfg.MIP_GAP = rc.mip_gap
    cfg.CVAR_BETA = rc.cvar_beta
    cfg.GAMMA_BESS = rc.gamma_bess
    cfg.GAMMA_P_BESS = 0.0
    cfg.GAMMA_PV = rc.gamma_pv
    cfg.PPAD_SPOT_USD_PER_MWHRP = rc.ppad_spot_price
    cfg.PEAK_CHARGE = rc.ppad_spot_price
    cfg.CONTRACT_PRICES["MATER"] = rc.contract_mater_price
    cfg.CONTRACT_PRICES["MATE"] = rc.contract_mate_price
    cfg.CONTRACT_PRICES["MAT"] = rc.contract_mate_price
    cfg.CONTRACT_PRICES["MATP"] = rc.contract_matp_price

    if rc.spot_energy_mean_usd_per_mwh is not None:
        cfg.SPOT_ENERGY_MEAN_USD_PER_MWH = rc.spot_energy_mean_usd_per_mwh
    if rc.contract_top_penalty_usd_per_mwh is not None:
        top = float(rc.contract_top_penalty_usd_per_mwh)
        if not hasattr(cfg, "CONTRACT_TOP_PENALTY_USD_PER_MWH"):
            cfg.CONTRACT_TOP_PENALTY_USD_PER_MWH = {}
        for k in ("MATER", "MATE", "MAT"):
            cfg.CONTRACT_TOP_PENALTY_USD_PER_MWH[k] = top
    if rc.random_seed is not None:
        cfg.RANDOM_SEED = int(rc.random_seed)


def run_single(rc: RunConfig) -> Dict:
    """Run one MILP configuration and return a serializable summary."""
    patch_config(rc)

    import importlib

    import data_loader
    import model_milp
    import scenario_gen

    importlib.reload(data_loader)
    importlib.reload(scenario_gen)
    importlib.reload(model_milp)
    from model_milp import StochasticProcurementMILP

    print(
        f"  {rc.name:24s} case={rc.active_case} "
        f"horizon={rc.num_days}d dt={rc.delta_t}h scenarios={rc.num_scenarios}"
    )

    t0 = time.time()
    scenarios = scenario_gen.generate_scenarios()
    scenario_time = time.time() - t0

    t0 = time.time()
    milp = StochasticProcurementMILP(scenarios=scenarios)
    milp.build()
    milp.model.update()
    build_time = time.time() - t0

    t0 = time.time()
    try:
        milp.model.optimize()
    except Exception as exc:
        if exc.__class__.__name__ == "GurobiError" and "Model too large for size-limited license" in str(exc):
            raise SystemExit(
                "Gurobi is running with a size-limited license on this server. "
                "The current phase is too large for that license. Activate an unrestricted "
                "Gurobi license on the server, or run the tiny orchestration check with: "
                "python3 -u run_server_campaign.py lite"
            ) from exc
        raise
    solve_time = time.time() - t0

    status = int(milp.model.Status)
    has_solution = milp.model.SolCount > 0
    solved = milp._extract_results() if has_solution else {}

    result = {
        **asdict(rc),
        "status": status,
        "objective": round(solved.get("objective"), 2) if has_solution else None,
        "mip_gap": round(solved.get("mip_gap"), 6) if has_solution else None,
        "best_bound": round(milp.model.ObjBound, 2) if has_solution else None,
        "scenario_time_sec": round(scenario_time, 2),
        "build_time_sec": round(build_time, 2),
        "solve_time_sec": round(solve_time, 2),
        "num_vars": int(milp.model.NumVars),
        "num_constrs": int(milp.model.NumConstrs),
        "C_PV": round(solved.get("C_PV", 0.0), 2) if has_solution else None,
        "C_BESS": round(solved.get("C_BESS", 0.0), 2) if has_solution else None,
        "P_BESS": round(solved.get("P_BESS", 0.0), 2) if has_solution else None,
        "contract_MATER_mwh": round(solved.get("contract_MATER_mwh", 0.0), 2) if has_solution else None,
        "contract_MATE_mwh": round(solved.get("contract_MATE_mwh", 0.0), 2) if has_solution else None,
        "contract_MATP_kw_avg": round(solved.get("contract_MATP_kw_avg", 0.0), 2) if has_solution else None,
        "annualized_capex": round(solved.get("annualized_capex", 0.0), 2) if has_solution else None,
        "expected_opex": round(solved.get("expected_opex", 0.0), 2) if has_solution else None,
        "expected_total_cost": round(solved.get("expected_total_cost", 0.0), 2) if has_solution else None,
        "cvar_total_cost": round(solved.get("cvar_total_cost", 0.0), 2) if has_solution else None,
        "cvar_opex": round(solved.get("cvar_opex", 0.0), 2) if has_solution else None,
        "cvar_eta": round(solved.get("cvar_eta", 0.0), 2) if has_solution else None,
        "spot_mwh_y": round(solved.get("spot_mwh_y", 0.0), 2) if has_solution else None,
        "grid_import_mwh_y": round(solved.get("grid_import_mwh_y", 0.0), 2) if has_solution else None,
        "pv_self_consumption_mwh_y": round(solved.get("pv_self_consumption_mwh_y", 0.0), 2) if has_solution else None,
        "bess_discharge_mwh_y": round(solved.get("bess_discharge_mwh_y", 0.0), 2) if has_solution else None,
        "peak_import_kw": round(solved.get("peak_import_kw", 0.0), 2) if has_solution else None,
        "residual_ppad_kw": round(solved.get("residual_ppad_kw", 0.0), 2) if has_solution else None,
        "opex_scale_to_year": round(solved.get("opex_scale_to_year", 0.0), 4) if has_solution else None,
        "contract_MATER_alloc_mwh_y": round(solved.get("contract_MATER_alloc_mwh_y", 0.0), 4) if has_solution else None,
        "contract_MATE_alloc_mwh_y": round(solved.get("contract_MATE_alloc_mwh_y", 0.0), 4) if has_solution else None,
        "contract_MATER_dev_under_mwh_y": round(solved.get("contract_MATER_dev_under_mwh_y", 0.0), 4) if has_solution else None,
        "contract_MATE_dev_under_mwh_y": round(solved.get("contract_MATE_dev_under_mwh_y", 0.0), 4) if has_solution else None,
        "contract_MATER_top_penalty_usd_y": round(solved.get("contract_MATER_top_penalty_usd_y", 0.0), 4) if has_solution else None,
        "contract_MATE_top_penalty_usd_y": round(solved.get("contract_MATE_top_penalty_usd_y", 0.0), 4) if has_solution else None,
        "contract_top_penalty_usd_per_mwh_MATER": solved.get("contract_top_penalty_usd_per_mwh_MATER", 0.0) if has_solution else None,
        "contract_top_penalty_usd_per_mwh_MATE": solved.get("contract_top_penalty_usd_per_mwh_MATE", 0.0) if has_solution else None,
    }

    print(
        f"    status={status} obj={result['objective']} gap={result['mip_gap']} "
        f"PV={result['C_PV']} BESS={result['C_BESS']} "
        f"MATP={result['contract_MATP_kw_avg']} solve={result['solve_time_sec']}s"
    )
    return result


def save_sweep(name: str, results: List[Dict]) -> None:
    os.makedirs(OUT, exist_ok=True)
    json_path = os.path.join(OUT, f"{name}.json")
    csv_path = os.path.join(OUT, f"{name}.csv")

    with open(json_path, "w") as f:
        json.dump(results, f, indent=2)

    if results:
        fieldnames: List[str] = []
        for row in results:
            for key in row.keys():
                if key not in fieldnames:
                    fieldnames.append(key)
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(results)

    print(f"  Saved {len(results)} rows to {json_path} and {csv_path}")


def run_configs(configs: Iterable[RunConfig]) -> List[Dict]:
    return [run_single(rc) for rc in configs]


def base_config(**overrides) -> RunConfig:
    values = asdict(RunConfig(name="base_42d_12s"))
    values.update(overrides)
    return RunConfig(**values)


def lite_config(**overrides) -> RunConfig:
    values = asdict(
        RunConfig(
            name="lite_base_1d_2s_hourly",
            num_days=LITE_DAYS,
            num_scenarios=LITE_SCENARIOS,
            delta_t=LITE_DELTA_T,
            solver_timeout=300,
            mip_gap=0.10,
        )
    )
    values.update(overrides)
    return RunConfig(**values)


def phase_base() -> List[Dict]:
    return run_configs([base_config()])


def phase_cvar() -> List[Dict]:
    return run_configs(
        base_config(name=f"cvar_beta_{beta}", cvar_beta=beta)
        for beta in [0.0, 0.25, 0.5, 1.0, 2.0]
    )


def phase_bess() -> List[Dict]:
    return run_configs(
        base_config(name=f"bess_cost_{cost}", gamma_bess=cost)
        for cost in [200, 300, 450, 600, 800, 1000]
    )


def phase_pv() -> List[Dict]:
    return run_configs(
        base_config(name=f"pv_cost_{cost}", gamma_pv=cost)
        for cost in [400, 550, 700, 900]
    )


def phase_mater() -> List[Dict]:
    return run_configs(
        base_config(name=f"mater_price_{price}", contract_mater_price=price)
        for price in [45, 50, 59, 70, 90]
    )


def phase_mate() -> List[Dict]:
    return run_configs(
        base_config(name=f"mate_price_{price}", contract_mate_price=price)
        for price in [45, 50, 56, 65, 75]
    )


def phase_ppad() -> List[Dict]:
    return run_configs(
        base_config(name=f"ppad_spot_{price}", ppad_spot_price=price)
        for price in [8, 12, 16, 20, 24]
    )


def phase_cases() -> List[Dict]:
    return run_configs(
        [
            base_config(name="case_3_base", active_case="case_3"),
            base_config(name="case_10_base", active_case="case_10"),
        ]
    )


def phase_baselines() -> List[Dict]:
    rc = base_config(name="baselines_42d_12s")
    patch_config(rc)

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
        f"  baselines_42d_12s       case={rc.active_case} "
        f"horizon={rc.num_days}d dt={rc.delta_t}h scenarios={rc.num_scenarios}"
    )
    scenarios = scenario_gen.generate_scenarios()
    rows = baselines.run_baseline_suite(scenarios, include_extended=True, cvar_beta=rc.cvar_beta)
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
    seasonal = [
        ("summer_21d", 14, 0),
        ("fall_21d", 104, 3),
        ("winter_21d", 195, 6),
        ("spring_21d", 287, 9),
    ]
    return run_configs(
        base_config(name=name, num_days=21, start_day=start_day, month_offset=month_offset)
        for name, start_day, month_offset in seasonal
    )


def phase_year() -> List[Dict]:
    return run_configs(
        [
            base_config(
                name="full_year_hourly_case_3_10s",
                num_days=365,
                num_scenarios=10,
                delta_t=1.0,
                solver_timeout=7200,
                mip_gap=0.05,
            )
        ]
    )


def phase_smoke() -> List[Dict]:
    return run_configs(
        [
            lite_config(
                name="smoke_1d_2s_hourly",
            )
        ]
    )


def phase_lite() -> List[Dict]:
    """Tiny end-to-end campaign that fits Gurobi's restricted fallback license.

    This phase validates orchestration only. It is not suitable for paper
    claims because it uses a one-day hourly horizon and two scenarios.
    """
    configs = [
        lite_config(name="lite_base"),
        lite_config(name="lite_cvar_beta_0.0", cvar_beta=0.0),
        lite_config(name="lite_cvar_beta_0.5", cvar_beta=0.5),
        lite_config(name="lite_bess_cost_300", gamma_bess=300),
        lite_config(name="lite_bess_cost_800", gamma_bess=800),
        lite_config(name="lite_pv_cost_400", gamma_pv=400),
        lite_config(name="lite_pv_cost_900", gamma_pv=900),
        lite_config(name="lite_mater_price_50", contract_mater_price=50),
        lite_config(name="lite_mate_price_65", contract_mate_price=65),
        lite_config(name="lite_ppad_spot_24", ppad_spot_price=24),
        lite_config(name="lite_case_10", active_case="case_10"),
    ]
    return run_configs(configs)


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
    "year": ("10_full_year", phase_year),
    "smoke": ("99_smoke", phase_smoke),
    "lite": ("98_lite", phase_lite),
}

PAPER_PHASES = ["base", "baselines", "cvar", "bess", "pv", "mater", "mate", "ppad", "cases", "seasonal"]


def expand_phases(requested: List[str]) -> List[str]:
    expanded: List[str] = []
    for phase in requested:
        if phase == "paper":
            expanded.extend(PAPER_PHASES)
        elif phase == "all":
            expanded.extend(PAPER_PHASES + ["year"])
        else:
            expanded.append(phase)

    seen = set()
    ordered = []
    for phase in expanded:
        if phase not in PHASES:
            raise SystemExit(f"Unknown phase '{phase}'. Valid phases: {', '.join(sorted(PHASES))}, paper, all")
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
        save_sweep("all_results", all_results)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the STORM remote execution campaign.")
    parser.add_argument(
        "phases",
        nargs="*",
        default=["paper"],
        help="Phases to run: smoke, lite, paper, all, base, baselines, cvar, bess, pv, mater, mate, ppad, cases, seasonal, year.",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip a phase if its JSON output already exists.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    phases = expand_phases(args.phases)
    os.makedirs(OUT, exist_ok=True)

    print("=" * 72)
    print("STORM Server Campaign")
    print(f"Host: {os.uname().nodename}")
    print(f"Output: {OUT}")
    print(f"Phases: {', '.join(phases)}")
    print("=" * 72)

    for phase in phases:
        output_name, runner = PHASES[phase]
        output_path = os.path.join(OUT, f"{output_name}.json")
        if args.skip_existing and os.path.exists(output_path):
            print(f"\n--- Skipping {phase}: {output_path} exists ---")
            continue
        print(f"\n--- Campaign: {output_name} ({phase}) ---")
        results = runner()
        save_sweep(output_name, results)

    if any(phase != "smoke" for phase in phases):
        print("\n--- Merging completed campaign results ---")
        merge_results()
    print("\nDone.")


if __name__ == "__main__":
    main()
