#!/usr/bin/env bash
# deploy_and_run.sh — Deploy STORM model to Ubuntu server, install deps, and run
# Usage: bash deploy_and_run.sh <server_user> <server_host> [phase ...]
# Example: bash deploy_and_run.sh jfraire agoraserv.alias.inria.fr paper
# Phases are handled by run_server_campaign.py: smoke, lite, paper, all, base,
# cvar, bess, pv, mater, mate, ppad, cases, seasonal, year.

set -euo pipefail

USER="${1:?Usage: $0 <server_user> <server_host> [phase ...]}"
HOST="${2:?Usage: $0 <server_user> <server_host> [phase ...]}"
PHASES=("${@:3}")
if [ "${#PHASES[@]}" -eq 0 ]; then
  PHASES=(paper)
fi
DEST="/home/${USER}/storm"

echo "=== Step 1: Create deployment tarball ==="
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TARBALL="/tmp/storm-model.tar.gz"
STAGE="$(mktemp -d /tmp/storm-package.XXXXXX)"
trap 'rm -rf "${STAGE}"' EXIT
cd "${PROJECT_DIR}"

mkdir -p "${STAGE}/data"
cp \
  model/config.py \
  model/data_loader.py \
  model/scenario_gen.py \
  model/model_milp.py \
  model/baselines.py \
  model/run_server_campaign.py \
  model/run_server_campaign_365.py \
  model/plot_campaign.py \
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
COPYFILE_DISABLE=1 tar czf "${TARBALL}" -C "${STAGE}" .

echo "=== Step 2: Copy tarball to server ==="
scp "${TARBALL}" "${USER}@${HOST}:/tmp/"

echo "=== Step 3: SSH and set up ==="
ssh "${USER}@${HOST}" bash -s << 'REMOTE'
set -euo pipefail
DEST=~/storm
mkdir -p "${DEST}"
cd "${DEST}"
tar xzf /tmp/storm-model.tar.gz

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
pip install -q numpy pandas scipy matplotlib seaborn openpyxl gurobipy

echo "--- Checking Gurobi ---"
if command -v gurobi_cl >/dev/null 2>&1; then
    gurobi_cl --version || true
else
    echo "gurobi_cl is not on PATH. That is OK for this campaign if gurobipy has access to a valid license."
fi
# If you need to activate a free academic license, run manually on the server:
#   grbgetkey <YOUR_LICENSE_KEY>

echo "--- Test import ---"
python3 -c 'import gurobipy; print("Gurobi", gurobipy.gurobi.version())'

echo "--- Setup complete ---"
REMOTE

echo ""
echo "=== Step 4: Launch campaign ==="
ssh "${USER}@${HOST}" bash -s -- "${PHASES[@]}" << 'REMOTE'
PHASES=("$@")
PHASE_CMD="${PHASES[*]}"
DEST=~/storm
cd "${DEST}"
source venv/bin/activate

RUN_CMD="
  cd ~/storm
  source venv/bin/activate
  echo \"[\$(date)] STORM campaign starting on \$(hostname): ${PHASE_CMD}\" | tee -a campaign.log
  python3 -u run_server_campaign.py ${PHASE_CMD} 2>&1 | tee -a campaign.log
  echo \"[\$(date)] STORM campaign finished\" | tee -a campaign.log
"

if command -v screen >/dev/null 2>&1; then
    screen -X -S storm quit 2>/dev/null || true
    screen -dmS storm bash -lc "${RUN_CMD}"
    echo "Campaign launched in screen session 'storm' with phases: ${PHASE_CMD}"
    echo "Attach:  screen -r storm"
    echo "Detach:  Ctrl+A, D"
else
    echo "screen is not installed; launching with nohup instead."
    nohup bash -lc "${RUN_CMD}" > storm.nohup.out 2>&1 &
    echo "Campaign launched with nohup, PID $!, phases: ${PHASE_CMD}"
fi
echo "Logs:    tail -f ~/storm/campaign.log"
echo "Results: ~/storm/output/campaign/"
REMOTE

echo ""
echo "=== Deployment complete ==="
echo ""
echo "Quick commands:"
echo "  Attach to screen session, if used: ssh ${USER}@${HOST} screen -r storm"
echo "  Check progress:   ssh ${USER}@${HOST} tail -f ~/storm/campaign.log"
echo "  Download results: scp -r ${USER}@${HOST}:~/storm/output/campaign/ ./model/output/campaign_server/"
