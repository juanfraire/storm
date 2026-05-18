# STORM

**Stochastic Trading and Optimization under Regulation for the Argentine
Wholesale Electricity Market (MEM).**

A two-stage stochastic mixed-integer linear program for electricity
procurement and behind-the-meter DER sizing for large industrial users under
the post-Resolution SE 400/2025 contracting structure. The model jointly
chooses MATER / MATE energy contracts, MATP power-adequacy coverage, PV
capacity, and BESS capacity (first stage) together with per-scenario
operational dispatch (second stage), under a CVaR risk objective.

The repository ships the formulation, a self-contained scenario generator, a
baseline-strategy suite (full-service GUDI proxy, deterministic
expected-value, STORM-RN, STORM-CVaR, contracts-only / DER-only /
no-degradation ablations), the full paper campaign, and figure generation.

---

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

STORM solves via Gurobi. The campaign requires an **unrestricted** Gurobi
license; the bundled `gurobipy` size-limited license only fits the `smoke`
phase. An academic license is free — see
<https://www.gurobi.com/academia/academic-program-and-licenses/>:

```bash
grbgetkey <YOUR_KEY>
```

## Quickstart

All workflows go through the single CLI entry point `storm.py`:

```bash
# Validate the install (1 day, hourly, 2 scenarios — solves in seconds)
python storm.py solve --days 1 --delta-t 1.0 --scenarios 2

# Default solve: Case 3, 365 days × 15 min × 12 scenarios, STORM-CVaR (β=0.5)
python storm.py solve

# Risk-neutral on Case 10 (smaller user)
python storm.py solve --case case_10 --beta 0

# Save the full result row as JSON
python storm.py solve --output result.json

# Show active configuration and case metadata
python storm.py info

# Run a single phase (e.g. the BESS-cost sweep)
python storm.py campaign bess

# Full STORM campaign (44 runs ≈ 30 h on 4 cores). `all` adds FSA and TOP sweeps.
python storm.py campaign all

# Multi-seed bands on the headline baselines (4 extra seeds, ≈ 16 h)
python storm.py campaign base baselines --seeds 2024 2025 2027 2028

# Generate paper figures from a saved campaign directory
python storm.py plot --input output/campaign_365 --output output/figures
```

Get per-subcommand help with `python storm.py <command> --help`.

## Repository layout

| File | Role |
|------|------|
| `storm.py` | CLI entry point (this is what users run). |
| `config.py` | All tunable parameters: costs, tariffs, horizons, solver. |
| `model_milp.py` | Two-stage stochastic MILP (Gurobi). |
| `data_loader.py` | Demand / PV / price loading + resampling. |
| `scenario_gen.py` | Stochastic scenario generation. |
| `baselines.py` | GUDI / Det-EV / STORM-RN / STORM-CVaR / ablation suite. |
| `solve.py` | Minimal scripted example (single solve + compact CVaR sweep). |
| `run_server_campaign.py` | Campaign orchestration primitives. |
| `run_server_campaign_365.py` | Full-year phase definitions used by the paper. |
| `plot_campaign.py` | Paper figure generation from saved campaign JSON. |
| `deploy_and_run.sh`, `deploy_and_run_365.sh` | Server deployment scripts. |
| `fetch_and_plot_365.sh`, `generate_figures_365.sh` | Local figure refresh from server results. |
| `MODEL.md` | Formulation reference (variables, constraints, objective). |
| `SERVER.md` | Remote campaign protocol (Inria `agoraserv`). |
| `data/` | Case demand profiles, PV factor, monthly billing snapshots. |
| `output/` | Campaign results and figures (gitignored). |

## Model overview

The formulation is documented in detail in [`MODEL.md`](MODEL.md). In brief:

- **First stage** (deterministic, scenario-independent): MATER and MATE
  monthly energy commitments `Q_{k,m}`, MATP power coverage `R_m`, PV
  capacity `C_PV`, BESS energy and power `C_BESS` / `P_BESS`.
- **Second stage** (per scenario × interval): spot energy purchase, contract
  allocation, PV self-consumption, BESS charge/discharge/SOC, demand
  reduction, residual PPAD exposure.
- **Objective**: annualized CAPEX + expected OPEX + `β · CVaR_α(OPEX)`.
  CVaR is applied to scenario-dependent OPEX only.
- **Take-or-pay**: monthly commitment cost paid on `Q` plus an explicit
  per-scenario penalty `c^TOP_k` for under-allocation. `β=0` gives STORM-RN,
  `β>0` gives STORM-CVaR.

Two named operating modes:

- **STORM-RN** (`β=0`): risk-neutral, the expected-cost optimizer.
- **STORM-CVaR** (`β>0`): risk-averse hedge designer.

## Reproducing the paper campaign

Local (one solve at a time):

```bash
python storm.py campaign all                                  # 48-run primary
python storm.py campaign base baselines --seeds 2024 2025 2027 2028   # bands
python storm.py plot --input output/campaign_365 --output output/figures
```

Remote (Inria `agoraserv` or any Linux host with SSH + Gurobi):

```bash
bash deploy_and_run_365.sh <user> <host> all
# Multi-seed sweep:
ssh <user>@<host> 'cd ~/storm && source venv/bin/activate && \
  python3 -u run_server_campaign_365.py base baselines --seeds 2024 2025 2027 2028'
# Pull the results back and replot:
bash fetch_and_plot_365.sh <user> <host>
```

The full deployment protocol (license handling, `screen` monitoring,
troubleshooting) lives in [`SERVER.md`](SERVER.md).

## Configuration overview

`config.py` exposes all economic and solver parameters as module attributes
so they can be overridden either via the CLI (`--gamma-pv 400`, `--beta 1.0`,
`--seed 2027`) or by mutating `cfg.*` in a script before importing
`model_milp`. Notable knobs:

| Parameter | Default | Meaning |
|---|---:|---|
| `ACTIVE_CASE` | `case_3` | UCEMA case identifier. |
| `DELTA_T` | 0.25 | Interval length in hours. |
| `NUM_SCENARIOS` | 100 | Number of stochastic scenarios. |
| `CVAR_ALPHA` | 0.95 | Tail confidence level. |
| `CVAR_BETA` | 0.5 | CVaR weight in the objective. |
| `GAMMA_PV`, `GAMMA_BESS` | 550, 600 | Overnight CAPEX (USD/kWp, USD/kWh). |
| `CONTRACT_PRICES` | dict | MATER, MATE, MATP rates. |
| `CONTRACT_TOP_PENALTY_USD_PER_MWH` | 10 | Per-MWh take-or-pay penalty. |
| `PPAD_SPOT_USD_PER_MWHRP` | 16 | Spot PPAD price. |
| `RANDOM_SEED` | 2026 | Scenario-generator seed. |
| `SOLVER_TIMEOUT` | 3600 | Per-solve time limit (seconds). |
| `MIP_GAP` | 0.01 | Solver gap target. |

## Acknowledgments

Demand profiles, contract-price references, and PPAD/MEM cost assumptions
used in this repository are derived from the UCEMA *Diplomatura en Gestión
y Compra de Energía Eléctrica*:
<https://ucema.edu.ar/educacion-ejecutiva/gestion-compra-energia-electrica>.

## Citation

If you use STORM, please cite the accompanying paper:

```
J. A. Fraire, O. A. Oviedo, and G. Martínez Carreras,
"Stochastic Trading and Optimization under Regulation for the Argentine
 Electricity Market," 2026.
```
