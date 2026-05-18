# STORM Server Execution Campaign

This file plans the complete remote campaign for the STORM paper and the
current model implementation. The target server is:

```bash
ssh -X jfraire@agoraserv.alias.inria.fr
```

X11 forwarding is optional for the batch run; it is useful only if you want to
inspect plots or GUI tools remotely. The actual campaign should run inside
`screen` so it survives SSH disconnects.

## What Must Be Reproduced

`paper/main.tex` describes a representative STORM campaign with:

- Case 3 as the main user, plus a Case 10 scaling check.
- 42-day 15-minute horizons, 12 stochastic scenarios, CVaR alpha 0.95, and
  annualized OPEX scaling.
- 2% MIP-gap target for the representative paper runs.
- Sensitivities for CVaR beta, BESS cost, PV cost, MATER price, MATE price,
  and residual PPAD price.
- Seasonal 21-day windows for summer, fall, winter, and spring.
- Solve-time, optimality-gap, scenario-count, horizon-length, and
  annualization-factor metadata in every result row.

The current model implements these pieces in:

| File | Role |
|---|---|
| `config.py` | Global parameters, costs, cases, PPAD hours, solver controls |
| `data_loader.py` | Demand/PV/price/grid-adder loading and resampling |
| `scenario_gen.py` | Stochastic demand, spot, grid-adder, and PV scenarios |
| `model_milp.py` | Gurobi MILP with MATER/MATE/MATP, PV, BESS, DR, CVaR |
| `baselines.py` | Baseline strategy suite used by the campaign comparison |
| `run_server_campaign.py` | Remote campaign orchestration and checkpoint output |
| `run_server_campaign_365.py` | Full-year 15-minute campaign orchestration |
| `plot_campaign.py` | Paper figure generation from saved JSON/CSV outputs |

## Campaign Matrix

The executable campaign is split into named phases. Running `paper` executes the
37-run campaign used for the manuscript figures. Running `all` executes `paper`
plus the hourly full-year validation run.

| Phase | Output stem | Runs | Horizon | Scenarios | Purpose |
|---|---:|---:|---:|---:|---|
| `smoke` | `99_smoke` | 1 | 1 day, hourly | 2 | Validate Python/Gurobi/data setup |
| `lite` | `98_lite` | 11 | 1 day, hourly | 2 | Tiny orchestration check for restricted licenses |
| `base` | `00_base` | 1 | 42 days, 15 min | 12 | Main Case 3 reference point |
| `cvar` | `01_cvar_beta` | 5 | 42 days, 15 min | 12 | beta = 0, 0.25, 0.5, 1, 2 |
| `bess` | `02_bess_cost` | 6 | 42 days, 15 min | 12 | BESS cost threshold |
| `pv` | `03_pv_cost` | 4 | 42 days, 15 min | 12 | PV cost sensitivity |
| `mater` | `04_mater_price` | 5 | 42 days, 15 min | 12 | MATER/MATE substitution |
| `mate` | `05_mate_price` | 5 | 42 days, 15 min | 12 | MATE/MATER substitution |
| `ppad` | `06_ppad_spot` | 5 | 42 days, 15 min | 12 | MATP activation under PPAD risk |
| `cases` | `07_case_comparison` | 2 | 42 days, 15 min | 12 | Case 3 vs Case 10 scaling |
| `seasonal` | `08_seasonal_windows` | 4 | 21 days, 15 min | 12 | Seasonal resource/demand windows |
| `year` | `09_full_year` | 1 | 365 days, hourly | 10 | Full-year consistency check |

All phase outputs are written under `~/storm/output/campaign/` as both JSON and
CSV. The runner also merges completed non-smoke phases into
`all_results.{json,csv}`.

## Recommended Execution Order

1. Deploy and verify with the smoke test.
2. Run the 37-run `paper` campaign.
3. Download results and regenerate figures.
4. Run the optional `year` phase if the representative campaign behaves well.
5. Use the output metadata to update the paper tables and discussion.

This order keeps failures cheap: if the server lacks a Gurobi license or a
Python dependency, the smoke phase catches it before launching the full
campaign.

Important: the `paper` and `all` campaigns require an unrestricted Gurobi
license. If Gurobi reports `Model too large for size-limited license`, the
server is using the restricted fallback license from `gurobipy`; activate the
full license before launching the paper campaign. The `lite` phase exists only
to test orchestration under a restricted license and must not be used for paper
claims.

## Automated Deploy

From the local project root:

```bash
bash model/deploy_and_run.sh jfraire agoraserv.alias.inria.fr smoke
```

After the smoke run is healthy, launch the paper campaign:

```bash
bash model/deploy_and_run.sh jfraire agoraserv.alias.inria.fr paper
```

If the server is still on a size-limited Gurobi license, this will fail before
solving the 42-day MILP. To test the phase orchestration without a full license:

```bash
bash model/deploy_and_run.sh jfraire agoraserv.alias.inria.fr lite
```

To include the hourly full-year validation in the same launch:

```bash
bash model/deploy_and_run.sh jfraire agoraserv.alias.inria.fr all
```

The deploy script packages the self-contained model files, copies them to
`~/storm/`, creates a Python virtual environment, installs dependencies, checks
`gurobipy`, and starts the run. If `screen` is available it uses a detached
session named `storm`; otherwise it falls back to `nohup`. It does not require
`sudo`.

If `screen` is used, the deploy helper replaces any existing `screen` session
with the same name, so download or finish old results before launching a new
automated run.

## Manual Setup

Use this path if you prefer to control each server step.

```bash
ssh -X jfraire@agoraserv.alias.inria.fr
mkdir -p ~/storm
cd ~/storm
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install numpy pandas scipy matplotlib seaborn openpyxl gurobipy
```

The campaign can run through the `gurobipy` package as long as a valid Gurobi
license is available. A system-wide `gurobi_cl` installation is useful but not
required.

If `grbgetkey` is not available and you do not have `sudo`, install the Gurobi
command-line tools under your home directory:

```bash
mkdir -p ~/opt
curl -L https://packages.gurobi.com/11.0/gurobi11.0.3_linux64.tar.gz -o /tmp/gurobi.tar.gz
tar xzf /tmp/gurobi.tar.gz -C ~/opt
export GUROBI_HOME="$HOME/opt/gurobi1103/linux64"
export PATH="$GUROBI_HOME/bin:$PATH"
export LD_LIBRARY_PATH="$GUROBI_HOME/lib:${LD_LIBRARY_PATH:-}"
grbgetkey <YOUR_GUROBI_LICENSE_KEY>
```

Persist the path setup for future SSH sessions:

```bash
cat >> ~/.bashrc <<'EOF'
export GUROBI_HOME="$HOME/opt/gurobi1103/linux64"
export PATH="$GUROBI_HOME/bin:$PATH"
export LD_LIBRARY_PATH="$GUROBI_HOME/lib:${LD_LIBRARY_PATH:-}"
EOF
```

If you have admin rights and prefer a system-wide command-line installation:

```bash
curl -L https://packages.gurobi.com/11.0/gurobi11.0.3_linux64.tar.gz -o /tmp/gurobi.tar.gz
sudo tar xzf /tmp/gurobi.tar.gz -C /opt
sudo ln -sf /opt/gurobi1103/linux64/bin/gurobi_cl /usr/local/bin/gurobi_cl
```

Activate the license if needed:

```bash
grbgetkey <YOUR_GUROBI_LICENSE_KEY>
# or
export GRB_LICENSE_FILE=/path/to/gurobi.lic
```

Then verify the license with a run larger than the tiny smoke model:

```bash
cd ~/storm
source venv/bin/activate
python3 -u run_server_campaign.py base
```

Copy the model from the laptop:

```bash
cd /path/to/project
STAGE="$(mktemp -d /tmp/storm-package.XXXXXX)"
mkdir -p "$STAGE/data"
cp \
  model/config.py \
  model/data_loader.py \
  model/scenario_gen.py \
  model/model_milp.py \
  model/run_server_campaign.py \
  model/plot_campaign.py \
  model/MODEL.md \
  model/SERVER.md \
  "$STAGE/"
cp \
  model/data/demand_case_3.csv \
  model/data/demand_case_10.csv \
  model/data/solar_irradiance_cordoba.csv \
  "$STAGE/data/"
if command -v xattr >/dev/null 2>&1; then xattr -cr "$STAGE"; fi
COPYFILE_DISABLE=1 tar czf /tmp/storm-model.tar.gz -C "$STAGE" .

scp /tmp/storm-model.tar.gz jfraire@agoraserv.alias.inria.fr:/tmp/
ssh -X jfraire@agoraserv.alias.inria.fr
cd ~/storm
tar xzf /tmp/storm-model.tar.gz
```

## Launching Runs

Inside the server:

```bash
cd ~/storm
source venv/bin/activate
python3 -u run_server_campaign.py smoke
```

Detached `screen` launch for the full paper campaign:

```bash
cd ~/storm
screen -dmS storm bash -lc '
  cd ~/storm
  source venv/bin/activate
  echo "[$(date)] STORM paper campaign starting on $(hostname)" | tee -a campaign.log
  python3 -u run_server_campaign.py paper 2>&1 | tee -a campaign.log
  echo "[$(date)] STORM paper campaign finished" | tee -a campaign.log
'
```

Optional follow-up full-year validation:

```bash
cd ~/storm
source venv/bin/activate
python3 -u run_server_campaign.py year 2>&1 | tee -a campaign.log
```

Full-year paper campaign with the same base/baseline/sensitivity/case phases
as `paper`, but using 365 days at 15-minute resolution for the main phases:

```bash
bash model/deploy_and_run_365.sh jfraire agoraserv.alias.inria.fr paper
```

The full-year runner writes to `~/storm/output/campaign_365/` and logs to
`~/storm/campaign_365.log`. It includes the `baselines` phase by default.

If a previous phase already completed, keep its JSON and skip it:

```bash
python3 -u run_server_campaign.py paper --skip-existing
```

## Monitoring

| Action | Command |
|---|---|
| Tail log | `ssh jfraire@agoraserv.alias.inria.fr tail -f ~/storm/campaign.log` |
| Attach to screen | `ssh -X jfraire@agoraserv.alias.inria.fr screen -r storm` |
| Detach from screen | `Ctrl+A`, then `D` |
| List sessions | `ssh jfraire@agoraserv.alias.inria.fr screen -ls` |
| Stop campaign | `ssh jfraire@agoraserv.alias.inria.fr screen -X -S storm quit` |
| Check outputs | `ssh jfraire@agoraserv.alias.inria.fr ls -lh ~/storm/output/campaign` |
| Check 365 outputs | `ssh jfraire@agoraserv.alias.inria.fr ls -lh ~/storm/output/campaign_365` |

## Downloading Results

From the local project root:

```bash
mkdir -p model/output/campaign_server
scp -r jfraire@agoraserv.alias.inria.fr:~/storm/output/campaign/ model/output/campaign_server/
```

The copied files will appear under:

```text
model/output/campaign_server/campaign/
```

To regenerate figures locally from the server campaign:

```bash
cd model
python3 plot_campaign.py \
  --input output/campaign_server/campaign \
  --output output/figures_server \
  --width single
```

Then copy the selected PDF figures into `paper/figures/` only after checking
that the result trends match the manuscript claims.

For the full-year campaign, fetch results and generate matching figures:

```bash
bash model/fetch_and_plot_365.sh jfraire agoraserv.alias.inria.fr
```

This copies `~/storm/output/campaign_365/` into
`model/output/campaign_server_365/campaign_365/` and writes figures to
`model/output/figures_server_365/`.

## Expected Outputs

The paper campaign should produce:

```text
00_base.{json,csv}
01_cvar_beta.{json,csv}
02_bess_cost.{json,csv}
03_pv_cost.{json,csv}
04_mater_price.{json,csv}
05_mate_price.{json,csv}
06_ppad_spot.{json,csv}
07_case_comparison.{json,csv}
08_seasonal_windows.{json,csv}
all_results.{json,csv}
```

Every row includes the run controls and solver metadata:

```text
name, status, active_case, num_days, num_scenarios, start_day, month_offset,
delta_t, cvar_beta, gamma_bess, gamma_pv, contract_mater_price,
contract_mate_price, ppad_spot_price, objective, mip_gap, best_bound,
scenario_time_sec, build_time_sec, solve_time_sec, num_vars, num_constrs,
C_PV, C_BESS, P_BESS, contract_MATER_mwh, contract_MATE_mwh,
contract_MATP_kw_avg, annualized_capex, expected_opex, cvar_eta,
opex_scale_to_year
```

## Validation Checklist

Before using the numbers in `paper/main.tex`, check:

- All paper-campaign rows have `status = 2` or otherwise report a usable
  incumbent and gap.
- `mip_gap` is at or below the configured tolerance for final claims.
- `opex_scale_to_year` is approximately 8.6905 for 42-day runs and 17.3810 for
  21-day seasonal runs.
- The CVaR sweep changes first-stage decisions, not only the objective.
- Cheap BESS reduces MATP or peak exposure; expensive BESS drops out.
- MATER and MATE price sweeps show the expected contract substitution.
- PPAD sensitivity activates MATP only when residual PPAD exposure is expensive.
- Case 10 capacities scale down relative to Case 3.
- Seasonal windows change PV/BESS/MATP decisions without hard-coded seasonal
  rules.
- The optional hourly full-year run is directionally consistent with the
  representative campaign.

## Current Limitations

The server campaign reproduces the representative implementation-stage results.
It does not yet solve the pending empirical tasks listed in the paper:

- final CAMMESA DTE and distributor-tariff reconstruction;
- full-service distributor/GUDI baseline;
- deterministic expected-value MILP baseline;
- richer SOC-window-dependent BESS degradation calibration.

Use the current campaign to support model-behavior claims and sensitivity
tendencies, not final savings claims versus distributor service.

## Troubleshooting

| Problem | Likely fix |
|---|---|
| `ModuleNotFoundError: gurobipy` | Activate `~/storm/venv` and run `pip install gurobipy` |
| `Gurobi license not found` | Run `grbgetkey <YOUR_GUROBI_LICENSE_KEY>` or set `GRB_LICENSE_FILE` |
| `Model too large for size-limited license` | Activate an unrestricted Gurobi license; `smoke` and `lite` may run, but `paper` will not |
| `sudo` authentication failed | Re-run the updated deploy script; it no longer requires `sudo` |
| `screen: command not found` | The deploy script falls back to `nohup`; install `screen` only if you have admin rights |
| tar warnings about `LIBARCHIVE.xattr` | Harmless macOS metadata warnings; the updated packager clears xattrs before creating the tarball |
| Model times out | Re-run the same phase; incumbent/gap are still saved if Gurobi found a solution |
| Memory pressure | Run phases separately, or run `year` only after `paper` succeeds |
| Need to resume | `python3 -u run_server_campaign.py paper --skip-existing` |
