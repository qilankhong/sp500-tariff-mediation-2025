#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ ! -f .env ]]; then
  echo "Missing .env. Run the smoke test first and add your FMP key."
  exit 2
fi

if [[ -d .venv ]]; then
  source .venv/bin/activate
fi

python src/stage1/sp500_metrics.py \
  --tickers-file data/reference/sp500_2025_symbols.txt \
  --out data/interim/sp500_metrics.csv \
  --start-date 2025-01-01 \
  --end-date 2025-04-30 \
  --qps 2 \
  --concurrency 3 \
  --limit 40

python src/stage1/enrich_for_analysis.py \
  --in data/interim/sp500_metrics.csv \
  --out data/processed/sp500_analysis_data.csv \
  --qps 2 \
  --concurrency 3

python src/stage2/sp500_daily_prices.py \
  --tickers-file data/processed/sp500_analysis_data.csv \
  --out data/derived/sp500_daily_prices.csv \
  --start-date 2025-01-01 \
  --end-date 2025-12-31 \
  --request-delay 1.0

python src/stage2/make_event_returns.py \
  --in data/derived/sp500_daily_prices.csv \
  --out data/derived/event_returns.csv

for event in \
  S1_Decline \
  S2_Escalation_Collapse \
  S3_Policy_Shock_Jump \
  S4_Uncertainty_Decline \
  S5_Long_Term_Adjustment
do
  Rscript analysis/run_mediation_analysis.R \
    data/processed/sp500_analysis_data.csv \
    data/derived/event_returns.csv \
    "$event"
done
