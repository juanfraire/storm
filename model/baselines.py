"""Baseline strategy suite for the STORM paper campaign.

The baselines are evaluated on the same stochastic scenarios used by STORM so
expected cost and CVaR are comparable across strategies.
"""

from contextlib import contextmanager
from typing import Dict, Iterable, List, Optional

import numpy as np

import config as cfg
from model_milp import StochasticProcurementMILP


BASELINE_STRATEGIES = (
    "gudi_full_service",
    "deterministic_ev",
    "stochastic_risk_neutral",
    "stochastic_cvar",
    "contracts_only",
    "der_only",
    "stochastic_no_degradation",
)


def run_baseline_suite(
    scenarios: Dict[str, np.ndarray],
    include_extended: bool = True,
    cvar_beta: Optional[float] = None,
) -> List[Dict]:
    """Run all baseline strategies on one shared scenario set."""
    beta = cfg.CVAR_BETA if cvar_beta is None else cvar_beta
    rows: List[Dict] = []

    rows.append(compute_gudi_baseline(scenarios))

    deterministic_solution = solve_deterministic_expected_value(scenarios)
    rows.append(evaluate_fixed_strategy(
        scenarios,
        deterministic_solution,
        strategy="deterministic_ev",
        label="Deterministic EV",
    ))

    rows.append(solve_storm_strategy(
        scenarios,
        strategy="stochastic_risk_neutral",
        label="Stochastic beta=0",
        cvar_beta=0.0,
    ))
    rows.append(solve_storm_strategy(
        scenarios,
        strategy="stochastic_cvar",
        label=f"Stochastic CVaR beta={beta:g}",
        cvar_beta=beta,
    ))

    if include_extended:
        rows.append(solve_storm_strategy(
            scenarios,
            strategy="contracts_only",
            label="Contracts only",
            cvar_beta=beta,
            disabled_assets={"der"},
        ))
        rows.append(solve_storm_strategy(
            scenarios,
            strategy="der_only",
            label="DER only",
            cvar_beta=beta,
            disabled_assets={"contracts"},
        ))
        with temporary_config(C_DEG=0.0):
            rows.append(solve_storm_strategy(
                scenarios,
                strategy="stochastic_no_degradation",
                label="No degradation cost",
                cvar_beta=beta,
            ))

    return [_normalize_row(row) for row in rows]


def compute_gudi_baseline(scenarios: Dict[str, np.ndarray]) -> Dict:
    """Compute the full-service distributor/GUDI baseline as a tariff bill."""
    demand = np.asarray(scenarios["demand"], dtype=np.float64)
    case = scenarios.get("case", cfg.ACTIVE_CASE)
    horizon_hours = max(demand.shape[1] * cfg.DELTA_T, 1e-9)
    scale = cfg.YEAR_HOURS / horizon_hours if cfg.SCALE_OPEX_TO_YEAR else 1.0
    price = cfg.GUDI_BASELINE_USD_PER_MWH.get(
        case,
        float(np.mean(list(cfg.GUDI_BASELINE_USD_PER_MWH.values()))),
    )
    opex_values = np.sum(demand, axis=1) / 1000.0 * price * scale
    expected_opex = float(np.mean(opex_values))
    cvar_opex = empirical_cvar(opex_values, cfg.CVAR_ALPHA)
    var_opex = empirical_var(opex_values, cfg.CVAR_ALPHA)

    return {
        "name": "baseline_gudi_full_service",
        "strategy": "gudi_full_service",
        "strategy_label": "GUDI/full service",
        "active_case": case,
        "case": case,
        "status": "computed",
        "objective": expected_opex,
        "mip_gap": None,
        "best_bound": None,
        "solve_time_sec": 0.0,
        "num_vars": 0,
        "num_constrs": 0,
        "annualized_capex": 0.0,
        "expected_opex": expected_opex,
        "expected_total_cost": expected_opex,
        "var_opex": var_opex,
        "cvar_opex": cvar_opex,
        "var_total_cost": var_opex,
        "cvar_total_cost": cvar_opex,
        "opex_scenario_values": [float(v) for v in opex_values],
        "C_PV": 0.0,
        "C_BESS": 0.0,
        "P_BESS": 0.0,
        "contract_MATER_mwh": 0.0,
        "contract_MATE_mwh": 0.0,
        "contract_MATP_kw_avg": 0.0,
        "contract_MATER_kwh": 0.0,
        "contract_MATE_kwh": 0.0,
        "spot_mwh_y": 0.0,
        "grid_import_mwh_y": float(np.mean(np.sum(demand, axis=1)) * scale / 1000.0),
        "pv_self_consumption_mwh_y": 0.0,
        "bess_discharge_mwh_y": 0.0,
        "bess_charge_mwh_y": 0.0,
        "demand_reduction_mwh_y": 0.0,
        "contract_MATER_alloc_mwh_y": 0.0,
        "contract_MATE_alloc_mwh_y": 0.0,
        "peak_import_kw": float(np.mean(np.max(demand / cfg.DELTA_T, axis=1))),
        "residual_ppad_kw": 0.0,
        "gudi_price_usd_per_mwh": price,
    }


def solve_deterministic_expected_value(scenarios: Dict[str, np.ndarray]) -> Dict:
    """Solve the expected-value deterministic MILP and return its decisions."""
    expected = make_expected_value_scenario(scenarios)
    return solve_storm_strategy(
        expected,
        strategy="deterministic_ev_design",
        label="Deterministic EV design",
        cvar_beta=0.0,
        model_name="STORM_deterministic_ev",
        include_opex_values=False,
    )


def evaluate_fixed_strategy(
    scenarios: Dict[str, np.ndarray],
    first_stage_solution: Dict,
    strategy: str,
    label: str,
) -> Dict:
    """Evaluate fixed here-and-now decisions on the stochastic scenarios."""
    fixed = first_stage_from_result(first_stage_solution)
    result = solve_storm_strategy(
        scenarios,
        strategy=strategy,
        label=label,
        cvar_beta=0.0,
        fixed_first_stage=fixed,
        model_name=f"STORM_eval_{strategy}",
    )
    result["deterministic_design_objective"] = first_stage_solution.get("objective")
    return result


def solve_storm_strategy(
    scenarios: Dict[str, np.ndarray],
    strategy: str,
    label: str,
    cvar_beta: float,
    fixed_first_stage: Optional[Dict] = None,
    disabled_assets: Optional[Iterable[str]] = None,
    model_name: Optional[str] = None,
    include_opex_values: bool = True,
) -> Dict:
    """Solve one STORM strategy under temporary objective settings."""
    with temporary_config(CVAR_BETA=cvar_beta):
        milp = StochasticProcurementMILP(
            scenarios=scenarios,
            fixed_first_stage=fixed_first_stage,
            disabled_assets=disabled_assets,
            model_name=model_name or f"STORM_{strategy}",
        )
        result = milp.solve()

    result["name"] = f"baseline_{strategy}"
    result["strategy"] = strategy
    result["strategy_label"] = label
    result["active_case"] = result.get("case", scenarios.get("case", cfg.ACTIVE_CASE))
    result["cvar_beta"] = cvar_beta
    result["disabled_assets"] = ",".join(sorted(str(a) for a in (disabled_assets or [])))
    if not include_opex_values:
        result.pop("opex_scenario_values", None)
    return result


def make_expected_value_scenario(scenarios: Dict[str, np.ndarray]) -> Dict[str, np.ndarray]:
    """Collapse a stochastic scenario set to one mean scenario."""
    expected = {}
    for key, value in scenarios.items():
        if isinstance(value, np.ndarray) and value.ndim == 2:
            expected[key] = np.mean(value, axis=0, keepdims=True)
        else:
            expected[key] = value
    return expected


def first_stage_from_result(result: Dict) -> Dict:
    """Extract first-stage variables in the format accepted by the MILP."""
    return {
        "C_PV": result.get("C_PV", 0.0),
        "C_BESS": result.get("C_BESS", 0.0),
        "P_BESS": result.get("P_BESS", 0.0),
        "Q_energy": {
            "MATER": result.get("Q_MATER_monthly_kwh", []),
            "MATE": result.get("Q_MATE_monthly_kwh", []),
        },
        "R_MATP": result.get("R_MATP_monthly_kw", []),
    }


@contextmanager
def temporary_config(**updates):
    """Temporarily patch values in ``config``."""
    old = {key: getattr(cfg, key) for key in updates}
    try:
        for key, value in updates.items():
            setattr(cfg, key, value)
        yield
    finally:
        for key, value in old.items():
            setattr(cfg, key, value)


def empirical_var(values, alpha: float) -> float:
    arr = np.sort(np.asarray(values, dtype=np.float64))
    if len(arr) == 0:
        return 0.0
    idx = int(np.ceil(alpha * len(arr))) - 1
    idx = min(max(idx, 0), len(arr) - 1)
    return float(arr[idx])


def empirical_cvar(values, alpha: float) -> float:
    arr = np.sort(np.asarray(values, dtype=np.float64))
    if len(arr) == 0:
        return 0.0
    tail_count = max(1, int(np.ceil((1.0 - alpha) * len(arr))))
    return float(np.mean(arr[-tail_count:]))


def _normalize_row(row: Dict) -> Dict:
    """Keep baseline outputs compact and CSV-friendly."""
    normalized = dict(row)
    normalized.setdefault("objective", normalized.get("expected_total_cost"))
    normalized.setdefault("expected_total_cost", normalized.get("objective"))
    normalized.setdefault("cvar_total_cost", normalized.get("expected_total_cost"))
    normalized.setdefault("annualized_capex", 0.0)
    normalized.setdefault("expected_opex", normalized.get("expected_total_cost", 0.0))
    normalized.setdefault("C_PV", 0.0)
    normalized.setdefault("C_BESS", 0.0)
    normalized.setdefault("P_BESS", 0.0)
    normalized.setdefault("contract_MATER_mwh", 0.0)
    normalized.setdefault("contract_MATE_mwh", 0.0)
    normalized.setdefault("contract_MATP_kw_avg", 0.0)
    normalized.setdefault("solve_time_sec", normalized.get("solve_time", 0.0))
    normalized["num_scenarios"] = int(np.asarray(row.get("opex_scenario_values", [])).shape[0])
    for key, value in list(normalized.items()):
        if isinstance(value, float):
            normalized[key] = round(value, 6)
    return normalized
