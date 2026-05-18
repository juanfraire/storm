#!/usr/bin/env bash
# Fetch full-year server campaign outputs and regenerate corresponding figures.
# Usage: bash model/fetch_and_plot_365.sh <server_user> <server_host>

set -euo pipefail

USER="${1:?Usage: $0 <server_user> <server_host>}"
HOST="${2:?Usage: $0 <server_user> <server_host>}"

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOCAL_DIR="${PROJECT_DIR}/model/output/campaign_server_365"

mkdir -p "${LOCAL_DIR}"
scp -r "${USER}@${HOST}:~/storm/output/campaign_365/" "${LOCAL_DIR}/"

bash "${PROJECT_DIR}/model/generate_figures_365.sh"
