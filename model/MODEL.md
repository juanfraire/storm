# STORM Model Implementation

STORM is a two-stage stochastic MILP for UCEMA large-user electricity
procurement under the revised paper formulation. The implementation separates
energy procurement (MATER/MATE), power-adequacy coverage (MATP/PPAD), residual
spot exposure, behind-the-meter PV/BESS, and optional demand response.

## Scope

The model is designed for the UCEMA cases used in the paper:

| Case | User Type | Data | Location Proxy |
|------|-----------|------|----------------|
| `case_3` | Large logistics/commercial user | 15-min demand, 5.50 GWh/year, 1.25 MW peak | EDESUR / Buenos Aires |
| `case_10` | Smaller industrial user | 15-min demand, 0.61 GWh/year, 171 kW peak | EDELAP / La Plata |

The code can run the full 35,040-interval year or reduced horizons for smoke
tests and campaign sweeps. When a reduced horizon is used, OPEX is scaled back
to an annual value so it remains comparable with annualized CAPEX.
Reduced horizons can also set `START_INTERVAL` to take a seasonal slice of the
annual demand/PV/price series.

## Units

| Quantity | Unit |
|----------|------|
| Demand profile input | kW |
| Scenario demand | interval kWh |
| PV yield | interval kWh/kWp |
| Spot and grid energy adders | USD/MWh |
| MATER/MATE prices | USD/MWh |
| MATP/PPAD power prices | USD/MWhrp |
| BESS energy | kWh |
| BESS power | kW |

The shipped demand and solar files are 15-minute series. `data_loader.py`
resamples power-like series when a runner changes `DELTA_T`, preserving kW and
USD/MWh semantics before interval energy is formed.

## Data Flow

1. `data_loader.py` reads UCEMA demand CSVs, optional DTE price CSVs, grid
   adders, and PV yield.
2. `scenario_gen.py` converts demand to kWh and builds stochastic scenarios for
   demand, spot price, grid adders, and PV yield.
3. `model_milp.py` builds the two-stage MILP and returns normalized result keys
   used by the runners and plots.

If parsed DTE prices are absent, the model uses a synthetic MEM transition price
series centered on the UCEMA examples. The PV file is still the legacy
Cordoba-like profile, scaled conservatively for Buenos Aires/La Plata until a
local irradiance source is added.

## First-Stage Decisions

| Variable | Meaning |
|----------|---------|
| `C_PV` | Installed PV capacity (kWp) |
| `C_BESS` | Installed BESS energy capacity (kWh) |
| `P_BESS` | Installed BESS power rating (kW) |
| `Q_MATER_m` | Monthly MATER contracted energy (kWh) |
| `Q_MATE_m` | Monthly MATE contracted energy (kWh) |
| `R_MATP_m` | Monthly MATP/PPAD power coverage (kW) |

Legacy aliases are retained for older scripts: `MAT` maps to `MATE`, and
aggregate contract outputs are still exposed as `contract_*`.

## Second-Stage Decisions

For each scenario and interval, the model chooses:

- spot energy purchase;
- MATER/MATE contract allocation;
- total grid import;
- PV self-consumption;
- BESS charge, discharge, and stored energy;
- optional demand reduction;
- PPAD peak requirement and residual spot PPAD exposure.

BESS state is modeled in kWh rather than normalized SOC. SOC limits are imposed
as linear bounds on installed capacity:

`SOC_MIN * C_BESS <= E_bess[t,s] <= SOC_MAX * C_BESS`.

The installed power rating is tied to energy capacity through
`P_BESS <= BESS_MAX_C_RATE * C_BESS`, preventing a zero-energy BESS from
carrying free power capacity when the UCEMA power-cost input is zero.

Charge/discharge exclusivity can be enforced with binary variables via
`USE_BESS_BINARY`.

## Objective

The objective minimizes:

`annualized CAPEX + expected annual OPEX + CVaR_BETA * CVaR_alpha(OPEX)`.

CAPEX is annualized from overnight UCEMA inputs using capital recovery factors.
OPEX includes:

- MATER and MATE take-or-pay monthly energy costs;
- MATP contracted PPAD coverage;
- residual spot PPAD exposure;
- residual spot energy;
- services, transport, FNEE, and distribution peaje adders;
- BESS degradation proxy;
- demand-response compensation.

CVaR is applied to scenario OPEX only. CAPEX is deterministic, so excluding it
from the risk term does not change scenario ordering and avoids double-counting
investment cost in the risk premium.

## Main Constraints

Energy balance:

`e_grid + e_pv + e_dis + d_red = demand + e_ch`

Grid definition:

`e_grid = e_spot + e_MATER + e_MATE`

PV limit:

`e_pv <= ETA_PV * solar_yield * C_PV`

BESS dynamics:

`E_bess[t] = E_bess[t-1] + ETA_CH * e_ch[t] - e_dis[t] / ETA_DIS`

Monthly energy contract coverage:

`sum_t e_contract[k,t] <= Q_k,m`

PPAD peak requirement:

`r_ppad[m,s] >= e_grid[t,s] / DELTA_T` for configured peak-hour intervals.

Residual PPAD spot exposure:

`r_spotP[m,s] >= r_ppad[m,s] - R_MATP[m]`.

## Current Approximations

- MATER and MATE are represented as monthly take-or-pay energy blocks. The code
  does not yet model hourly delivery profiles or renewable matching rules.
- PPAD peak hours use a transparent configurable approximation
  (`PPAD_PEAK_HOURS`) until exact DTE/tariff hour sets are parsed.
- BESS degradation is a linear throughput proxy. The paper can discuss this as
  a tractable surrogate for richer kMC-informed degradation calibration.
- DTE parsing hooks are present, but the standalone repository can run without
  the large DTE archives.

## Main Entry Points

| File | Purpose |
|------|---------|
| `config.py` | Case metadata, costs, tariffs, solver settings |
| `data_loader.py` | Demand, price, grid-adder, and PV loading/resampling |
| `scenario_gen.py` | Scenario generation in model units |
| `model_milp.py` | Gurobi MILP formulation and result extraction |
| `solve.py` | Base solve and compact CVaR sensitivity |
| `storm.py` | Unified CLI: solve / campaign / plot / info |
| `run_server_campaign.py` | Hourly server campaign runner |
| `plot_campaign.py` | Campaign plotting from saved JSON |
