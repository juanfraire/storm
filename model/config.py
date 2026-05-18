"""
Configuration for STORM.

Units:
- Money: USD
- Power: kW
- Energy: kWh
- Energy prices: USD/MWh unless explicitly stated otherwise

The implementation follows the revised paper formulation:
energy contracts (MATER/MATE), power-adequacy coverage (MATP/PPAD),
residual spot exposure, PV, BESS, and demand-side flexibility.
"""

import os
from math import pow

# --- Model name ---
MODEL_NAME = "STORM"

# --- Paths ---
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# --- Time parameters ---
# The UCEMA demand and shipped PV profile are stored at 15-minute resolution.
DATA_DELTA_T = 0.25
DELTA_T = 0.25
MONTH_DAYS = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)


def month_boundaries_for_delta_t(delta_t: float = None):
    """Return calendar month boundaries in model intervals."""
    delta_t = DELTA_T if delta_t is None else delta_t
    intervals_per_day = int(round(24.0 / delta_t))
    boundaries = [0]
    total = 0
    for days in MONTH_DAYS:
        total += days * intervals_per_day
        boundaries.append(total)
    return boundaries


T = 35040
MONTH_BOUNDARIES = month_boundaries_for_delta_t(DELTA_T)

# Approximation of CAMMESA peak-power hours used for PPAD exposure.
# The actual program defines HMD/HRP by month; this keeps the model linear
# and transparent until the DTE/tariff parser supplies exact monthly sets.
PPAD_PEAK_HOURS = tuple(range(18, 23))
PPAD_KP_SUMMER_WINTER = 1.10
PPAD_KP_SHOULDER = 0.90

# --- Scenario parameters ---
YEAR_HOURS = 8760.0
SCALE_OPEX_TO_YEAR = True
NUM_SCENARIOS = 100
CVAR_ALPHA = 0.95
CVAR_BETA = 0.5
RANDOM_SEED = 2026

# --- Case selection ---
ACTIVE_CASE = "case_3"
START_INTERVAL = 0
MONTH_OFFSET = 0

CASE_METADATA = {
    "case_3": {
        "name": "UCEMA Case 3",
        "location": "edesur_ba",
        "contracted_power_kw": 1500.0,
        "description": "Logistics center in EDESUR area.",
    },
    "case_10": {
        "name": "UCEMA Case 10",
        "location": "edelap_la_plata",
        "contracted_power_kw": 120.0,
        "description": "Small factory near La Plata.",
    },
}

# --- Capital costs from UCEMA case statements (overnight inputs) ---
GAMMA_PV = 550.0
GAMMA_BESS = 600.0
GAMMA_P_BESS = 0.0

# Annualization. The MILP objective is annual cost, so overnight CAPEX is
# converted to an annual charge using a capital recovery factor.
DISCOUNT_RATE = 0.10
PV_LIFE_YEARS = 20
BESS_LIFE_YEARS = 10


def capital_recovery_factor(rate: float, years: int) -> float:
    if years <= 0:
        return 1.0
    if abs(rate) < 1e-12:
        return 1.0 / years
    growth = pow(1.0 + rate, years)
    return rate * growth / (growth - 1.0)


PV_CRF = capital_recovery_factor(DISCOUNT_RATE, PV_LIFE_YEARS)
BESS_CRF = capital_recovery_factor(DISCOUNT_RATE, BESS_LIFE_YEARS)

# --- Investment bounds for numerically stable big-M constraints ---
MAX_PV_KWP = 5000.0
MAX_BESS_KWH = 20000.0
MAX_BESS_KW = 10000.0

# --- BESS parameters ---
ETA_CH = 0.95
ETA_DIS = 0.95
BESS_MAX_C_RATE = 1.0
SOC_MIN = 0.10
SOC_MAX = 0.90
SOC_INIT = 0.50
C_DEG = 0.012

# --- PV parameters ---
ETA_PV = 0.85

# --- Contract parameters ---
ENERGY_CONTRACT_TYPES = ("MATER", "MATE")
POWER_CONTRACT_TYPES = ("MATP",)

# Backward-compatible name for legacy scripts.
CONTRACT_TYPES = ["MATER", "MATE", "MATP"]

CONTRACT_PRICES = {
    "MATER": 59.0,  # USD/MWh
    "MATE": 56.0,   # USD/MWh
    "MAT": 56.0,    # legacy alias for MATE
    "MATP": 15.0,   # USD/MWhrp
}

# Take-or-pay deviation penalty in USD/MWh, charged per scenario on the gap
# between the first-stage monthly commitment Q^E_{k,m} and the actually allocated
# energy. This is on top of the commitment cost c^E_{k,m} * Q^E_{k,m}, so the
# total cost of carrying an over-sized commitment in a low-demand scenario is
# c^E * Q + c^TOP * (Q - allocated). Setting this to 0 recovers the previous
# behavior where the commitment cost is sunk regardless of allocation.
CONTRACT_TOP_PENALTY_USD_PER_MWH = {
    "MATER": 10.0,
    "MATE": 10.0,
    "MAT": 10.0,
}

# Tiny secondary cost on the take-or-pay slack used as an LP symmetry breaker.
# Without it, the dev_under variables create a flat region in the relaxation
# when the configured TOP penalty is zero (or trivially small), which caused
# Gurobi to time out on cvar_beta_0.25 in the 365-day campaign. 0.01 USD/MWh
# is well below any economic effect (less than $1/year of dispatch cost in
# practice) but is enough to make the optimizer prefer allocation = Q.
CONTRACT_DEV_SYMMETRY_BREAK_USD_PER_MWH = 0.01

# Maximum delivery/coverage. Energy bounds are converted to kWh per month
# inside the model using the number of hours in each modeled month.
CONTRACT_MAX_KW = {
    "MATER": 5000.0,
    "MATE": 10000.0,
    "MAT": 10000.0,
}
MATP_MAX_KW = 10000.0

# --- MEM/grid cost components ---
# Demand-side spot energy remains close to average cost during the FSA=0
# transition. Synthetic scenarios are centered on these values until parsed
# DTE data is available.
SPOT_ENERGY_MEAN_USD_PER_MWH = 60.0
SPOT_ENERGY_STD_USD_PER_MWH = 12.0
SPOT_ENERGY_FLOOR_USD_PER_MWH = 20.0

SERVICES_USD_PER_MWH = 3.5
TRANSPORT_USD_PER_MWH = 7.0
FNEE_USD_PER_MWH = 1.5

# Distribution/local terms are intentionally explicit: they are not MEM spot.
DISTRIBUTION_PEAJE_USD_PER_MWH = {
    "case_3": 45.0,
    "case_10": 45.0,
}

GUDI_BASELINE_USD_PER_MWH = {
    "case_3": 141.70,
    "case_10": 141.70,
}

# PPAD/MATP charge in USD/MWhrp. Converted to USD/kW-month by multiplying
# by modeled peak-power hours and KP, then dividing by 1000.
PPAD_SPOT_USD_PER_MWHRP = 16.0

# Legacy aliases used by old campaign code. They no longer drive the model
# directly except through mapping to PPAD prices.
PEAK_CHARGE = 15.0
SMEC_CHARGE = 0.0
WHEELING_CHARGE = 0.0

# --- Demand response ---
DR_COST = 0.10
DR_MAX_FRACTION = 0.10
USE_DR_EVENT_BINARY = False
DR_MAX_HOURS_PER_YEAR = 14 * 5
DR_MAX_POWER_KW = 10000.0

# --- Binary charge/discharge exclusivity ---
USE_BESS_BINARY = True

# --- Solver ---
SOLVER_TIMEOUT = 3600
MIP_GAP = 0.01
THREADS = 4
SOLVER_OUTPUT = False
