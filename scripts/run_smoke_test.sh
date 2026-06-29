#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "A private .env file was created. Add your FMP key, then run this command again:"
  echo "bash scripts/run_smoke_test.sh"
  exit 2
fi

if grep -Eq "replace_with_(your|new)_fmp_api_key" .env; then
  echo "The FMP key is still a placeholder in .env. Replace it with your key and run again."
  exit 2
fi

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi

source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
make test

rm -f local_check/sp500_metrics.csv \
  local_check/sp500_analysis_data.csv \
  local_check/sp500_daily_prices.csv \
  local_check/event_returns.csv
mkdir -p local_check

python src/stage1/sp500_metrics.py \
  --tickers AAPL,MSFT,XOM \
  --out local_check/sp500_metrics.csv \
  --start-date 2025-01-01 \
  --end-date 2025-04-30 \
  --qps 2 \
  --concurrency 2 \
  --limit 40

python src/stage1/enrich_for_analysis.py \
  --in local_check/sp500_metrics.csv \
  --out local_check/sp500_analysis_data.csv \
  --qps 2 \
  --concurrency 2

python src/stage2/sp500_daily_prices.py \
  --tickers-file local_check/sp500_analysis_data.csv \
  --out local_check/sp500_daily_prices.csv \
  --start-date 2025-01-01 \
  --end-date 2025-12-31 \
  --request-delay 1.0

python src/stage2/make_event_returns.py \
  --in local_check/sp500_daily_prices.csv \
  --out local_check/event_returns.csv

python - <<'PY'
from pathlib import Path
import pandas as pd

root = Path("local_check")
analysis = pd.read_csv(root / "sp500_analysis_data.csv")
events = pd.read_csv(root / "event_returns.csv")
expected = {
    "S1_Decline", "S2_Escalation_Collapse", "S3_Policy_Shock_Jump",
    "S4_Uncertainty_Decline", "S5_Long_Term_Adjustment",
}
assert len(analysis) == 3, f"Expected 3 companies, found {len(analysis)}"
assert expected.issubset(events.columns), "One or more event-window columns are missing"
print("\nSUCCESS: the Python data pipeline worked on three test companies.")
print("Files are in the local_check folder; GitHub will ignore that folder.")
PY
