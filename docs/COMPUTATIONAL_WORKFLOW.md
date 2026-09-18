# Computational workflow

Run all commands from the repository root. The pipeline uses FMP's current `stable` API routes and authenticates through request headers. A full run makes live requests for 503 firms and can take a while; caches allow interrupted runs to resume without repeating every successful request.

## 1. Prepare the environment

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cp .env.example .env
```

Put the real key in `.env`, then confirm only that it loads; do not print the key:

```bash
python -c 'from dotenv import load_dotenv; import os; load_dotenv(); assert os.getenv("FMP_API_KEY"); print("FMP key loaded")'
```

Install the two R packages only if the local check reports they are absent. The following is a Terminal command; `Rscript -e` sends the quoted expression to R:

```bash
Rscript -e 'install.packages(c("glmnet", "dplyr"), repos="https://cloud.r-project.org")'
```

Do not paste bare `install.packages(...)` at a `%` or `$` shell prompt. That form works only after starting an interactive R session and seeing R's `>` prompt.

```bash
make test
```

Success means Python compilation, R dependency checks, and the offline event-window test all pass.

## 2. Stage 1: financial metrics

Use the frozen 503-symbol universe so a later run does not silently substitute the current S&P 500 membership.

```bash
python src/stage1/sp500_metrics.py \
  --tickers-file data/reference/sp500_2025_symbols.txt \
  --out data/interim/sp500_metrics.csv \
  --start-date 2025-01-01 \
  --end-date 2025-04-30 \
  --qps 2 \
  --concurrency 3 \
  --limit 40
```

Expected final message: `Wrote ... with 503 companies × ... metrics.` A smaller count means some symbols failed or the universe file changed. `--limit 40` retains enough quarterly history for both 3-year CAGR and 5-year average variables.

Add sector classifications. The working analysis does not download unused live quote or liquidity variables, which would vary with the date of a later run.

```bash
python src/stage1/enrich_for_analysis.py \
  --in data/interim/sp500_metrics.csv \
  --out data/processed/sp500_analysis_data.csv \
  --qps 2 \
  --concurrency 3
```

## 3. Stage 2: daily prices and event returns

```bash
python src/stage2/sp500_daily_prices.py \
  --tickers-file data/processed/sp500_analysis_data.csv \
  --out data/derived/sp500_daily_prices.csv \
  --start-date 2025-01-01 \
  --end-date 2025-12-31 \
  --request-delay 1.0
```

This script writes after each successful ticker and resumes from an existing output file. The conservative defaults are intentional. HTTP 429 means the plan's rate limit was reached; increase `--request-delay` and rerun.

```bash
python src/stage2/make_event_returns.py \
  --in data/derived/sp500_daily_prices.csv \
  --out data/derived/event_returns.csv
```

The output must contain `symbol` and the five `S1_...` through `S5_...` columns described in [VARIABLES.md](VARIABLES.md).

## 4. Run the mediation analysis

Run one scenario at a time. The third argument selects the outcome column.

```bash
Rscript analysis/run_mediation_analysis.R \
  data/processed/sp500_analysis_data.csv \
  data/derived/event_returns.csv \
  S1_Decline
```

Valid scenario arguments are:

- `S1_Decline`
- `S2_Escalation_Collapse`
- `S3_Policy_Shock_Jump`
- `S4_Uncertainty_Decline`
- `S5_Long_Term_Adjustment`

Each run creates a timestamped folder under `results/` containing direct/indirect-effect and mediator-effect CSV tables.

### Joint tests across all five scenarios

Run the companion script once to test the complete direct- and indirect-effect
vectors for every event window:

```bash
Rscript analysis/run_joint_hypothesis_tests.R \
  data/processed/sp500_analysis_data.csv \
  data/derived/event_returns.csv \
  results/joint_hypothesis_tests_S1-S5.csv
```

The output reports the repository's joint Wald statistic for
`H0: beta = 0` and its direct-effect F-type statistic for
`H0: alpha1 = 0`. Their primary p-values use the asymptotic chi-square
reference distribution with `q = 11` degrees of freedom, corresponding to the
intercept plus the ten non-baseline sector indicators in `X`. The additional
`Tn2` LRT-style and classical-F columns are labelled as sensitivity or
descriptive calibrations; they are not substitutes for the primary tests.

In the summary CSV, `Sample_Size_N` is the number of companies used in the
analysis (503 in the supplied study data). `Joint_Test_DF_Q` is the dimension
of each effect vector and therefore the degrees of freedom for the primary
joint tests. Here `Q = 11`: one intercept representing the Utilities baseline
plus ten indicators for the other sectors. The
`Joint_Test_Coefficients` column records this composition directly in every
row so that exported tables remain interpretable without consulting the code.

## 5. Validation record

Record these checks in the paper's computational appendix:

1. Git commit hash and run date.
2. Python and R versions.
3. FMP plan and endpoint-access status, but never the key.
4. Row counts at each stage: expected universe 503; document any failed or delisted symbols.
5. Missingness rates for every selected mediator.
6. Exact event-window boundaries, boundary-date convention, and whether boundary dates were trading days. The working event-return code uses close-to-close windows: `start_date < return date <= end_date`.
7. A comparison of regenerated tables with the archived paper tables, allowing only explained data-revision or numerical-tolerance differences.

For the long-term window, also inspect firms whose price histories end before 2025-12-31. The pipeline reports the available cumulative return; acquisition, delisting, or symbol-history treatment must be stated in the paper rather than silently inferred by the code.

## Troubleshooting

- `FMP_API_KEY missing`: `.env` is absent, misspelled, or not in the repository root.
- HTTP 401/403: the key or plan does not permit that endpoint.
- HTTP 429: lower `--qps`/`--concurrency`, or increase the daily-price request delay.
- Empty financial metrics: inspect `.cache/` responses and confirm the requested historical statements exist.
- R `system is computationally singular`: inspect zero-variance columns, missingness, duplicate sector indicators, and the chosen baseline before changing the method.
