----How to Download S&P 500 Fundamentals (Jan–Apr 2025)-----
Step 1: Running sp500_metrics.py
1) Activate a virtual environment
	python3 -m venv .venv
	source .venv/bin/activate
2) Install required packages
	python -m pip install -U pip
	pip install aiohttp pandas numpy python-dotenv tqdm
3) Add your FMP API Key
	echo "FMP_API_KEY=YOUR_PREMIUM_KEY_HERE" > .env
4) Run this script:
python sp500_metrics.py \
  --universe sp500 \
  --out data/sp500_jan_apr_2025.csv \
  --start-date 2025-12-31 --end-date 2025-04-30 \
  --qps 8 --concurrency 12 --limit 40
Step 2: Running enrich_for_analysis.py
**pre-requisite: you have all steps from step 1 completed & are still in the virtual env**
1) run this script:
python enrich_for_analysis.py \
  --in sp500_jan_apr_2025.csv \
  --out sp500_jan_apr_2025_ANALYSIS_READY.csv \
  --qps 8 --concurrency 12
Step 3: Running update_returnapr_only.py
1) install required packages
	pip install requests python-dotenv pandas
2) Run this script:
python update_returnapr_only.py \
  --in sp500_jan_apr_2025_ANALYSIS_READY.csv \
  --out sp500_jan_apr_2025_RENEWEDAPR_JanApr.csv \
  --year 2025


