#!/usr/bin/env bash
# deploy_and_run_365.sh - deploy STORM and run the full-year server campaign
# Usage: bash model/deploy_and_run_365.sh <server_user> <server_host> [phase ...]
# Example: bash model/deploy_and_run_365.sh jfraire agoraserv.alias.inria.fr paper
# Phases are handled by run_server_campaign_365.py: smoke, lite, paper, all,
# base, baselines, cvar, bess, pv, mater, mate, ppad, cases, seasonal.

set -euo pipefail

USER="${1:?Usage: $0 <server_user> <server_host> [phase ...]}"
HOST="${2:?Usage: $0 <server_user> <server_host> [phase ...]}"
PHASES=("${@:3}")
if [ "${#PHASES[@]}" -eq 0 ]; then
  PHASES=(paper)
fi
DEST="/home/${USER}/storm"

echo "=== Step 1: Create full-year deployment tarball ==="
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TARBALL="/tmp/storm-model-365.tar.gz"
STAGE="$(mktemp -d /tmp/storm-package-365.XXXXXX)"
trap 'rm -rf "${STAGE}"' EXIT
cd "${PROJECT_DIR}"

mkdir -p "${STAGE}/data"
cp \
  model/config.py \
  model/data_loader.py \
  model/scenario_gen.py \
  model/model_milp.py \
  model/baselines.py \
  model/solve.py \
  model/storm.py \
  model/run_server_campaign.py \
  model/run_server_campaign_365.py \
  model/plot_campaign.py \
  model/requirements.txt \
  model/README.md \
  model/MODEL.md \
  model/SERVER.md \
  "${STAGE}/"
cp \
  model/data/demand_case_3.csv \
  model/data/demand_case_10.csv \
  model/data/solar_irradiance_cordoba.csv \
  "${STAGE}/data/"
if command -v xattr >/dev/null 2>&1; then
  xattr -cr "${STAGE}" || true
fi

# Sanity-check the staged files. If a Google Drive sync was mid-flight or a
# rename/move desynced the working tree, the tarball can silently miss recent
# edits. Fail loudly here rather than land a partial deploy on the server.
echo "--- Sanity-checking staged sources ---"
for marker_file_marker in \
    "config.py:CONTRACT_TOP_PENALTY_USD_PER_MWH" \
    "config.py:CONTRACT_DEV_SYMMETRY_BREAK_USD_PER_MWH" \
    "model_milp.py:dev_under" \
    "model_milp.py:symmetry_break_usd_per_mwh" \
    "run_server_campaign_365.py:phase_fsa" \
    "run_server_campaign_365.py:phase_top" \
    "run_server_campaign.py:random_seed" \
    "run_server_campaign.py:contract_MATE_alloc_mwh_y"; do
  marker_file="${marker_file_marker%%:*}"
  marker="${marker_file_marker##*:}"
  if ! grep -q -F -- "${marker}" "${STAGE}/${marker_file}"; then
    echo "ERROR: '${marker}' not found in staged ${marker_file}."
    echo "       The local source likely failed to sync (Google Drive lag?) before tar."
    echo "       Refusing to deploy a partial code state. Resync and re-run."
    exit 2
  fi
done
echo "    OK: P1/P2/P3 markers present in staged sources."

COPYFILE_DISABLE=1 tar czf "${TARBALL}" -C "${STAGE}" .

echo "=== Step 2: Copy tarball to server ==="
scp "${TARBALL}" "${USER}@${HOST}:/tmp/"

echo "=== Step 3: SSH and set up ==="
ssh "${USER}@${HOST}" bash -s << 'REMOTE'
set -euo pipefail
DEST=~/storm
mkdir -p "${DEST}"
cd "${DEST}"
# Wipe Python bytecode cache before extracting, so an old .pyc cannot shadow a
# fresh .py if mtimes line up unfortunately.
rm -rf "${DEST}/__pycache__"
tar xzf /tmp/storm-model-365.tar.gz

echo "--- Checking server tools ---"
if ! command -v python3 >/dev/null 2>&1; then
    echo "ERROR: python3 is not available on this server. Ask the server admin to install Python 3.10+."
    exit 1
fi

echo "--- Installing Python packages ---"
if ! python3 -m venv venv; then
    echo "ERROR: python3 -m venv failed. Ask the server admin to install python3-venv, or create ~/storm/venv manually."
    exit 1
fi
source venv/bin/activate
pip install -q --upgrade pip
# Install from the shipped requirements.txt if present; otherwise install the
# legacy explicit list. This keeps older server snapshots working.
if [ -f "${DEST}/requirements.txt" ]; then
    pip install -q -r "${DEST}/requirements.txt"
else
    pip install -q numpy pandas scipy matplotlib gurobipy
fi

echo "--- Checking Gurobi ---"
if command -v gurobi_cl >/dev/null 2>&1; then
    gurobi_cl --version || true
else
    echo "gurobi_cl is not on PATH. That is OK for this campaign if gurobipy has access to a valid license."
fi

echo "--- Test import ---"
python3 -c 'import gurobipy; print("Gurobi", gurobipy.gurobi.version())'

echo "--- Setup complete ---"
REMOTE

echo ""
echo "=== Step 4: Launch full-year campaign ==="
ssh "${USER}@${HOST}" bash -s -- "${PHASES[@]}" << 'REMOTE'
PHASES=("$@")
PHASE_CMD="${PHASES[*]}"
DEST=~/storm
cd "${DEST}"
source venv/bin/activate
LOG="${DEST}/campaign_365.log"
SCREEN_LOG="${DEST}/campaign_365.screen.log"

touch "${LOG}"
echo "[$(date)] STORM 365-day launch requested on $(hostname): ${PHASE_CMD}" | tee -a "${LOG}"

RUN_CMD="
  set -o pipefail
  cd ~/storm
  source venv/bin/activate
  echo \"[\$(date)] STORM 365-day campaign starting on \$(hostname): ${PHASE_CMD}\" | tee -a campaign_365.log
  python3 -u run_server_campaign_365.py ${PHASE_CMD} 2>&1 | tee -a campaign_365.log
  echo \"[\$(date)] STORM 365-day campaign finished\" | tee -a campaign_365.log
"

if command -v screen >/dev/null 2>&1; then
    screen -X -S storm365 quit 2>/dev/null || true
    screen -L -Logfile "${SCREEN_LOG}" -dmS storm365 bash -lc "${RUN_CMD}"
    echo "Campaign launched in screen session 'storm365' with phases: ${PHASE_CMD}"
    echo "Attach:  screen -r storm365"
    echo "Detach:  Ctrl+A, D"
    sleep 1
    screen -ls || true
else
    echo "screen is not installed; launching with nohup instead."
    nohup bash -lc "${RUN_CMD}" > storm_365.nohup.out 2>&1 &
    echo "Campaign launched with nohup, PID $!, phases: ${PHASE_CMD}"
fi
echo "Logs:    tail -f ${LOG}"
echo "Results: ~/storm/output/campaign_365/"
REMOTE

echo ""
echo "=== Deployment complete ==="
echo ""
echo "Quick commands:"
echo "  Attach to screen session, if used: ssh ${USER}@${HOST} screen -r storm365"
echo "  Check progress:   ssh ${USER}@${HOST} tail -f ~/storm/campaign_365.log"
echo "  Download results: scp -r ${USER}@${HOST}:~/storm/output/campaign_365/ ./model/output/campaign_server_365/"
echo "  Fetch and plot:   bash model/fetch_and_plot_365.sh ${USER} ${HOST}"
