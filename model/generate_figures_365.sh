#!/usr/bin/env bash
# Generate paper-style figures from downloaded full-year campaign results.
# Usage: bash model/generate_figures_365.sh [input_dir] [output_dir]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "${SCRIPT_DIR}"

INPUT_DIR="${1:-output/campaign_server_365/campaign_365}"
OUTPUT_DIR="${2:-output/figures_server_365}"
WIDTH="${WIDTH:-single}"
FORMATS="${FORMATS:-pdf,png}"
ENVELOPE_DAYS="${ENVELOPE_DAYS:-365}"
ENVELOPE_SCENARIOS="${ENVELOPE_SCENARIOS:-80}"
ENVELOPE_START_DAY="${ENVELOPE_START_DAY:-0}"
MPLCONFIGDIR="${MPLCONFIGDIR:-${SCRIPT_DIR}/output/.matplotlib}"
export MPLCONFIGDIR

mkdir -p "${MPLCONFIGDIR}"

python3 plot_campaign.py \
  --input "${INPUT_DIR}" \
  --output "${OUTPUT_DIR}" \
  --width "${WIDTH}" \
  --formats "${FORMATS}" \
  --envelope-days "${ENVELOPE_DAYS}" \
  --envelope-scenarios "${ENVELOPE_SCENARIOS}" \
  --envelope-start-day "${ENVELOPE_START_DAY}"

echo "Figures written to ${SCRIPT_DIR}/${OUTPUT_DIR}"
