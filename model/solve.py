"""
Run STORM and export sensitivity results.
"""

import json
import os
from typing import Dict, Optional

import config as cfg
from model_milp import StochasticProcurementMILP
from scenario_gen import generate_scenarios


def solve_model(scenarios=None, beta: Optional[float] = None) -> Dict:
    """Build and solve one STORM instance."""
    old_beta = cfg.CVAR_BETA
    if beta is not None:
        cfg.CVAR_BETA = beta
    try:
        milp = StochasticProcurementMILP(scenarios=scenarios)
        milp.build()
        return milp.solve()
    finally:
        cfg.CVAR_BETA = old_beta


def sensitivity_analysis() -> Dict[str, Dict]:
    """Run a compact CVaR sensitivity sweep."""
    scenarios = generate_scenarios()
    results = {}

    print("=== Base case ===")
    results["base"] = solve_model(scenarios)

    for beta in [0.0, 0.2, 0.5, 1.0, 2.0]:
        print(f"=== CVaR beta = {beta} ===")
        results[f"cvar_beta_{beta}"] = solve_model(scenarios, beta=beta)

    os.makedirs(cfg.OUTPUT_DIR, exist_ok=True)
    with open(os.path.join(cfg.OUTPUT_DIR, "sensitivity_results.json"), "w") as f:
        json.dump(results, f, indent=2, default=str)

    print("Sensitivity results saved.")
    return results


if __name__ == "__main__":
    sensitivity_analysis()
