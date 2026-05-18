"""
Data loading utilities for STORM.

Demand CSVs are stored as kW readings at 15-minute resolution. Scenario
generation converts them to interval energy (kWh) so the MILP uses one
consistent energy unit throughout.
"""

import os
from typing import Dict

import numpy as np

import config as cfg


def load_demand_profile(case: str = None, length: int = None, start_interval: int = None) -> np.ndarray:
    """
    Load a demand profile in kW.

    Parameters
    ----------
    case:
        Case id, e.g. "case_3" or "case_10".
    length:
        Optional number of intervals to return. The series is truncated or
        edge-padded to this length.
    start_interval:
        Optional model-interval offset into the annual profile.
    """
    case = case or cfg.ACTIVE_CASE
    length = length or cfg.T
    start_interval = cfg.START_INTERVAL if start_interval is None else start_interval
    csv_path = os.path.join(cfg.DATA_DIR, f"demand_{case}.csv")

    if not os.path.exists(csv_path):
        print(f"Warning: {csv_path} not found. Using synthetic demand.")
        demand_kw = _synthetic_demand_kw(case, start_interval + length)
        return _fit_window(demand_kw, start_interval, length)
    else:
        import pandas as pd
        df = pd.read_csv(csv_path)
        demand_kw = df["demand_kw"].to_numpy(dtype=np.float64)

    return _resample_power_from_data_interval(demand_kw, length, start_interval)


def load_case_metadata(case: str = None) -> Dict:
    """Return metadata for a configured UCEMA case."""
    case = case or cfg.ACTIVE_CASE
    meta = dict(cfg.CASE_METADATA.get(case, {}))
    meta.setdefault("name", case)
    meta.setdefault("location", "unknown")
    meta.setdefault("contracted_power_kw", float(np.max(load_demand_profile(case, 96, start_interval=0))))
    return meta


def load_dte_prices(length: int = None, start_interval: int = None) -> np.ndarray:
    """
    Load a DTE-derived energy price series in USD/MWh.

    If a parsed DTE CSV is not available, generate a synthetic average-cost
    transition price series centered on UCEMA examples.
    """
    length = length or cfg.T
    start_interval = cfg.START_INTERVAL if start_interval is None else start_interval
    price_csv = os.path.join(cfg.DATA_DIR, "dte_prices_15min.csv")
    if os.path.exists(price_csv):
        import pandas as pd
        df = pd.read_csv(price_csv)
        col = "price_usd_per_mwh"
        return _resample_rate(df[col].to_numpy(dtype=np.float64), cfg.DATA_DELTA_T, length, start_interval)

    hourly_csv = os.path.join(cfg.DATA_DIR, "dte_prices_hourly.csv")
    if os.path.exists(hourly_csv):
        import pandas as pd
        df = pd.read_csv(hourly_csv)
        hourly = df["price_usd_per_mwh"].to_numpy(dtype=np.float64)
        return _resample_rate(hourly, 1.0, length, start_interval)

    return _fit_window(_synthetic_spot_prices(start_interval + length), start_interval, length)


def load_grid_adders(case: str = None, length: int = None, start_interval: int = None) -> np.ndarray:
    """
    Return non-energy grid adders in USD/MWh.

    These include services, transport, FNEE, and a distribution peaje proxy.
    They are separate from spot/MATE/MATER energy prices.
    """
    case = case or cfg.ACTIVE_CASE
    length = length or cfg.T
    peaje = cfg.DISTRIBUTION_PEAJE_USD_PER_MWH.get(
        case,
        np.mean(list(cfg.DISTRIBUTION_PEAJE_USD_PER_MWH.values())),
    )
    value = cfg.SERVICES_USD_PER_MWH + cfg.TRANSPORT_USD_PER_MWH + cfg.FNEE_USD_PER_MWH + peaje
    return np.full(length, value, dtype=np.float64)


def load_solar_yield(case: str = None, length: int = None, start_interval: int = None) -> np.ndarray:
    """
    Load or synthesize interval PV yield in kWh/kWp.

    The shipped CSV is a 15-minute power factor (kW/kWp). We convert it to
    interval energy by multiplying by DELTA_T. Location differences between
    Buenos Aires and La Plata are represented by small scaling factors until
    exact irradiance data is added.
    """
    case = case or cfg.ACTIVE_CASE
    length = length or cfg.T
    start_interval = cfg.START_INTERVAL if start_interval is None else start_interval
    solar_csv = os.path.join(cfg.DATA_DIR, "solar_irradiance_cordoba.csv")

    if os.path.exists(solar_csv):
        import pandas as pd
        df = pd.read_csv(solar_csv)
        factor_kw_per_kwp = df["solar_factor"].to_numpy(dtype=np.float64)
        factor_kw_per_kwp = _resample_power(factor_kw_per_kwp, cfg.DATA_DELTA_T, length, start_interval)
    else:
        factor_kw_per_kwp = _fit_window(_synthetic_solar_factor(start_interval + length), start_interval, length)

    scale = _solar_location_scale(case)
    yield_kwh_per_kwp = factor_kw_per_kwp * cfg.DELTA_T * scale
    return _fit_length(yield_kwh_per_kwp, length)


def demand_stats(case: str = None) -> Dict[str, float]:
    """Return basic demand statistics for reporting."""
    demand_kw = load_demand_profile(case)
    return {
        "points": int(len(demand_kw)),
        "energy_kwh": float(np.sum(demand_kw) * cfg.DELTA_T),
        "peak_kw": float(np.max(demand_kw)),
        "avg_kw": float(np.mean(demand_kw)),
        "min_kw": float(np.min(demand_kw)),
    }


def _fit_length(values: np.ndarray, length: int) -> np.ndarray:
    values = np.asarray(values, dtype=np.float64)
    if len(values) == length:
        return values
    if len(values) > length:
        return values[:length]
    if len(values) == 0:
        return np.zeros(length, dtype=np.float64)
    return np.pad(values, (0, length - len(values)), mode="edge")


def _fit_window(values: np.ndarray, start: int, length: int) -> np.ndarray:
    start = max(int(start), 0)
    fitted = _fit_length(values, start + length)
    return fitted[start:start + length]


def _resample_power_from_data_interval(values: np.ndarray, length: int, start: int) -> np.ndarray:
    """Convert shipped 15-minute power readings to model-interval power."""
    return _resample_power(values, cfg.DATA_DELTA_T, length, start)


def _resample_rate(values: np.ndarray, source_delta_t: float, length: int, start: int) -> np.ndarray:
    """Convert price/additive rates to model intervals by time averaging."""
    return _resample_power(values, source_delta_t, length, start)


def _resample_power(values: np.ndarray, source_delta_t: float, length: int, start: int = 0) -> np.ndarray:
    """
    Convert a source-interval power/rate series to model intervals.

    Power-like quantities are averaged when the model interval is coarser and
    repeated when it is finer. This keeps kW and USD/MWh semantics intact
    before scenario generation multiplies by the model interval length.
    """
    values = np.asarray(values, dtype=np.float64)
    if abs(cfg.DELTA_T - source_delta_t) < 1e-12:
        return _fit_window(values, start, length)

    ratio = cfg.DELTA_T / source_delta_t
    if ratio > 1.0 and abs(ratio - round(ratio)) < 1e-9:
        group = int(round(ratio))
        fitted = _fit_length(values, (start + length) * group)
        resampled = fitted.reshape(start + length, group).mean(axis=1)
        return resampled[start:start + length]

    inv_ratio = source_delta_t / cfg.DELTA_T
    if inv_ratio > 1.0 and abs(inv_ratio - round(inv_ratio)) < 1e-9:
        repeat = int(round(inv_ratio))
        return _fit_window(np.repeat(values, repeat), start, length)

    source_time = np.arange(len(values)) * source_delta_t
    if len(values) == 0:
        return np.zeros(length, dtype=np.float64)
    target_time = (start + np.arange(length)) * cfg.DELTA_T
    return np.interp(target_time, source_time, values, left=values[0], right=values[-1])


def _synthetic_demand_kw(case: str, length: int) -> np.ndarray:
    rng = np.random.default_rng(42)

    if case == "case_3":
        base_load, peak = 628.0, 1247.0
    elif case == "case_10":
        base_load, peak = 69.0, 171.0
    else:
        base_load, peak = 500.0, 1000.0

    t = np.arange(length)
    hour = (t // int(round(1.0 / cfg.DELTA_T))) % 24
    day = (t // int(round(24.0 / cfg.DELTA_T))) % 7

    weekly = 1.0 + 0.10 * np.sin(2 * np.pi * day / 7)
    hourly = 0.85 + 0.20 * np.sin(np.pi * (hour - 7) / 12)
    noise = 1.0 + 0.04 * rng.standard_normal(length)
    demand = base_load * weekly * hourly * noise
    return np.clip(demand, 0, peak).astype(np.float64)


def _synthetic_spot_prices(length: int) -> np.ndarray:
    rng = np.random.default_rng(42)
    intervals_per_day = int(round(24.0 / cfg.DELTA_T))
    intervals_per_hour = int(round(1.0 / cfg.DELTA_T))
    t = np.arange(length)
    hour = (t // intervals_per_hour) % 24
    day = t // intervals_per_day

    seasonal = cfg.SPOT_ENERGY_MEAN_USD_PER_MWH + 10.0 * np.sin(2 * np.pi * (day - 30) / 365)
    band = np.where((hour >= 18) & (hour <= 22), 1.18, np.where(hour <= 5, 0.88, 1.0))
    noise = rng.normal(0.0, cfg.SPOT_ENERGY_STD_USD_PER_MWH * 0.20, size=length)
    prices = seasonal * band + noise
    return np.maximum(prices, cfg.SPOT_ENERGY_FLOOR_USD_PER_MWH).astype(np.float64)


def _synthetic_solar_factor(length: int) -> np.ndarray:
    rng = np.random.default_rng(42)
    intervals_per_day = int(round(24.0 / cfg.DELTA_T))
    intervals_per_hour = int(round(1.0 / cfg.DELTA_T))
    t = np.arange(length)
    hour = (t // intervals_per_hour) % 24
    day = t // intervals_per_day

    day_angle = 2 * np.pi * (day - 80) / 365
    declination = 23.45 * np.cos(day_angle) * np.pi / 180
    latitude = -34.6 * np.pi / 180
    hour_angle = 15 * (hour - 12) * np.pi / 180
    sin_elev = (
        np.sin(latitude) * np.sin(declination)
        + np.cos(latitude) * np.cos(declination) * np.cos(hour_angle)
    )
    clear = np.maximum(sin_elev, 0)
    clear = clear / max(np.max(clear), 1e-9)
    cloud = rng.beta(2, 5, length)
    return (clear * (1 - 0.25 * cloud)).astype(np.float64)


def _solar_location_scale(case: str) -> float:
    # The existing CSV is Cordoba-like. Buenos Aires/La Plata generally have
    # lower annual PV yield, so use conservative factors until a local file is
    # added.
    if case == "case_3":
        return 0.90
    if case == "case_10":
        return 0.88
    return 0.90
