"""
Scenario generation for STORM.

The generated arrays use the revised model units:
- demand: interval kWh
- spot_price: USD/MWh
- grid_adder: USD/MWh
- solar_yield: interval kWh/kWp

Legacy keys are also returned for older plotting/running scripts.
"""

from typing import Dict

import numpy as np

import config as cfg
from data_loader import (
    load_demand_profile,
    load_dte_prices,
    load_grid_adders,
    load_solar_yield,
)


def generate_scenarios(
    case: str = None,
    num_scenarios: int = None,
    horizon: int = None,
    start_interval: int = None,
) -> Dict[str, np.ndarray]:
    """Generate demand, price, grid-adder, and solar scenarios."""
    case = case or cfg.ACTIVE_CASE
    S = int(num_scenarios or cfg.NUM_SCENARIOS)
    T = int(horizon or cfg.T)
    start_interval = cfg.START_INTERVAL if start_interval is None else start_interval

    demand_kw_base = load_demand_profile(case=case, length=T, start_interval=start_interval)
    demand_kwh_base = demand_kw_base * cfg.DELTA_T
    price_base = load_dte_prices(length=T, start_interval=start_interval)
    grid_adder_base = load_grid_adders(case=case, length=T, start_interval=start_interval)
    solar_base = load_solar_yield(case=case, length=T, start_interval=start_interval)

    demands = np.zeros((S, T), dtype=np.float64)
    prices = np.zeros((S, T), dtype=np.float64)
    grid_adders = np.zeros((S, T), dtype=np.float64)
    solars = np.zeros((S, T), dtype=np.float64)

    rng = np.random.default_rng(seed=cfg.RANDOM_SEED)

    for s in range(S):
        demand_noise = _ar1_filter(rng.lognormal(mean=0.0, sigma=0.025, size=T), phi=0.85)
        demands[s] = demand_kwh_base * demand_noise

        price_noise = _ar1_filter(rng.normal(0.0, cfg.SPOT_ENERGY_STD_USD_PER_MWH, size=T), phi=0.75)
        prices[s] = np.maximum(price_base + 0.35 * price_noise, cfg.SPOT_ENERGY_FLOOR_USD_PER_MWH)

        adder_noise = _ar1_filter(rng.normal(0.0, 1.0, size=T), phi=0.90)
        grid_adders[s] = np.maximum(grid_adder_base + adder_noise, 0.0)

        cloud = _ar1_filter(rng.beta(7, 2, size=T), phi=0.92)
        solars[s] = solar_base * cloud

    return {
        "case": case,
        "start_interval": start_interval,
        "demand": demands,
        "demand_kwh": demands,
        "spot_price": prices,
        "spot_price_usd_per_mwh": prices,
        "grid_adder": grid_adders,
        "grid_adder_usd_per_mwh": grid_adders,
        "solar_yield": solars,
        "solar_yield_kwh_per_kwp": solars,
        # Legacy name; now represents interval kWh/kWp, not GHI power.
        "solar_ghi": solars,
    }


def _ar1_filter(x: np.ndarray, phi: float = 0.8) -> np.ndarray:
    """Apply an AR(1)-style smoothing filter."""
    y = np.zeros_like(x, dtype=np.float64)
    if len(x) == 0:
        return y
    y[0] = x[0]
    for i in range(1, len(x)):
        y[i] = phi * y[i - 1] + (1.0 - phi) * x[i]
    return y
