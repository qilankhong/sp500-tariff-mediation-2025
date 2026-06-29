#!/usr/bin/env python3
from __future__ import annotations

import argparse, asyncio, csv, json, os, sys, time
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiohttp
import numpy as np
import pandas as pd
from dotenv import load_dotenv

# ────────────────────────────────────────────────────────────────────────────────
## activate a virtual environment before running:
# python3 -m venv .venv
# source .venv/bin/activate
# python -m pip install -U pip
## install required packages
# pip install aiohttp pandas numpy python-dotenv tqdm
## add API key
# echo "FMP_API_KEY=YOUR_PREMIUM_KEY_HERE" > .env
## run this script
# python sp500_metrics.py \
#   --universe sp500 \
#   --out data/sp500_feb_apr_2025.csv \
#   --start-date 2025-12-31 --end-date 2025-04-30 \
#   --qps 8 --concurrency 12 --limit 40


# ────────────────────────────────────────────────────────────────────────────────
# Env & constants
# ────────────────────────────────────────────────────────────────────────────────
load_dotenv()
API_KEY = os.getenv("FMP_API_KEY")
if not API_KEY:
    sys.exit("❌ FMP_API_KEY missing. Put it in a .env file at project root.")

BASE_URL = "https://financialmodelingprep.com/api/v3"
CACHE_DIR = Path(".cache"); CACHE_DIR.mkdir(exist_ok=True)

STATEMENTS = {
    "is": "income-statement",
    "bs": "balance-sheet-statement",
    "cf": "cash-flow-statement",
}

NON_DATA_COLS = {
    "symbol","cik","period","date","reportedCurrency","fillingDate","acceptedDate",
    "calendarYear","link","finalLink"
}

# Curated fields (safe defaults). Use --auto-fields to compute ALL numeric fields returned by FMP.
CURATED_FIELDS = {
    "is": [
        "revenue","costOfRevenue","grossProfit",
        "researchAndDevelopmentExpenses","generalAndAdministrativeExpenses","sellingAndMarketingExpenses",
        "operatingExpenses","operatingIncome","interestExpense","incomeBeforeTax",
        "incomeTaxExpense","netIncome","ebitda","ebit",
        "weightedAverageShsOut","weightedAverageShsOutDil","eps","epsdiluted"
    ],
    "bs": [
        "cashAndCashEquivalents","shortTermInvestments","netReceivables","inventory","otherCurrentAssets",
        "totalCurrentAssets","propertyPlantEquipmentNet","goodwill","intangibleAssets","totalNonCurrentAssets",
        "totalAssets","accountPayables","shortTermDebt","deferredRevenue","otherCurrentLiabilities",
        "totalCurrentLiabilities","longTermDebt","totalNonCurrentLiabilities","totalLiabilities",
        "commonStock","retainedEarnings","totalStockholdersEquity","workingCapital","commonStockSharesOutstanding"
    ],
    "cf": [
        "netCashProvidedByOperatingActivities","netCashUsedForInvestingActivites",
        "netCashUsedProvidedByFinancingActivities","capitalExpenditure",
        "stockBasedCompensation","freeCashFlow","dividendsPaid"
    ]
}

DERIV_SUFFIXES = {
    "":       lambda s, i: _safe_iloc(s, i),           # anchor value
    "_YoY":   lambda s, i: _pct_change(s, i, 4),       # quarterly YoY (i vs i+4)
    "_QoQ":   lambda s, i: _pct_change(s, i, 1),       # quarter-over-quarter
    "_CAGR3": lambda s, i: _cagr_quarters(s, i, 12),   # 3 years = 12 quarters
    "_Avg5":  lambda s, i: _window_mean(s, i, 20),     # 5-year trailing avg (20 qtrs)
}

# ────────────────────────────────────────────────────────────────────────────────
# Helpers – math & safety
# ────────────────────────────────────────────────────────────────────────────────
def _safe_iloc(s: pd.Series, i: int):
    try:
        return float(s.iloc[i])
    except Exception:
        return np.nan

def _pct_change(s: pd.Series, i: int, lag: int):
    try:
        a = float(s.iloc[i]); b = float(s.iloc[i+lag])
        if b == 0 or np.isnan(b): return np.nan
        return (a - b) / abs(b)
    except Exception:
        return np.nan

def _cagr_quarters(s: pd.Series, i: int, lag_q: int):
    try:
        a = float(s.iloc[i]); b = float(s.iloc[i+lag_q])
        if b <= 0 or a <= 0: return np.nan
        years = lag_q / 4.0
        return (a / b) ** (1.0/years) - 1.0
    except Exception:
        return np.nan

def _window_mean(s: pd.Series, i: int, w: int):
    try:
        window = s.iloc[i:i+w].astype(float)
        return float(window.mean()) if len(window) else np.nan
    except Exception:
        return np.nan

def _numeric_cols(df: pd.DataFrame) -> List[str]:
    cols = []
    for c in df.columns:
        if c in NON_DATA_COLS: continue
        try:
            pd.to_numeric(df[c])
            cols.append(c)
        except Exception:
            pass
    return cols

# ────────────────────────────────────────────────────────────────────────────────
# Rate limiting & HTTP
# ────────────────────────────────────────────────────────────────────────────────
class RateLimiter:
    def __init__(self, qps: float):
        self.qps = max(0.1, float(qps))
        self.tokens = self.qps
        self.ts = time.monotonic()
    async def acquire(self):
        while True:
            now = time.monotonic()
            self.tokens += (now - self.ts) * self.qps
            self.ts = now
            if self.tokens >= 1:
                self.tokens -= 1
                return
            await asyncio.sleep((1 - self.tokens)/self.qps)

async def _fetch_json(session: aiohttp.ClientSession, url: str, params: dict,
                      cache_path: Path, rl: RateLimiter, refresh: bool, retries=4):
    if cache_path.exists() and not refresh:
        return json.loads(cache_path.read_text())

    backoff = 1.0
    for attempt in range(retries):
        await rl.acquire()
        try:
            async with session.get(url, params=params, timeout=45) as r:
                if r.status == 200:
                    data = await r.json()
                    cache_path.write_text(json.dumps(data))
                    return data
                if r.status in (429, 503):
                    raise aiohttp.ClientError(f"HTTP {r.status}")
                r.raise_for_status()
        except (aiohttp.ClientError, asyncio.TimeoutError):
            if attempt == retries - 1:
                raise
            await asyncio.sleep(backoff)
            backoff = min(30.0, backoff * 2.0)
    raise RuntimeError("unreachable")

# ────────────────────────────────────────────────────────────────────────────────
# Data fetching
# ────────────────────────────────────────────────────────────────────────────────
async def get_sp500_tickers() -> List[str]:
    """Fetch S&P 500 constituents from FMP (no scraping; avoids 403)."""
    url = f"{BASE_URL}/sp500_constituent"
    params = {"apikey": API_KEY}
    timeout = aiohttp.ClientTimeout(total=None, sock_connect=45, sock_read=45)
    async with aiohttp.ClientSession(raise_for_status=True, timeout=timeout) as s:
        async with s.get(url, params=params, timeout=45) as r:
            data = await r.json()
    symbols = sorted({str(d.get("symbol","")).replace(".","-") for d in data if d.get("symbol")})
    return symbols

async def fetch_statements(ticker: str, period: str, limit: int,
                           session: aiohttp.ClientSession, rl: RateLimiter, refresh: bool):
    frames: Dict[str, pd.DataFrame] = {}
    for tag, endpoint in STATEMENTS.items():
        url = f"{BASE_URL}/{endpoint}/{ticker}"
        params = {"period": period, "limit": limit, "apikey": API_KEY}
        cache_file = CACHE_DIR / f"{ticker}_{tag}_{period}_{limit}.json"
        data = await _fetch_json(session, url, params, cache_file, rl, refresh)
        df = pd.DataFrame(data)
        if df.empty:
            frames[tag] = pd.DataFrame()
            continue
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df = df.sort_values("date", ascending=False).reset_index(drop=True)
        frames[tag] = df
    return frames

# ────────────────────────────────────────────────────────────────────────────────
# Metric engine (now records anchor dates)
# ────────────────────────────────────────────────────────────────────────────────
def compute_metrics(frames: Dict[str, pd.DataFrame],
                    start_date: Optional[str],
                    end_date: Optional[str],
                    use_auto_fields: bool,
                    min_coverage: float,
                    curated_fields: Dict[str, List[str]]) -> Dict[str, float]:

    def anchor_index(df: pd.DataFrame) -> int:
        """Latest row within [start,end]; else 0 (latest overall)."""
        if df.empty: return 0
        if start_date or end_date:
            mask = pd.Series([True]*len(df))
            if start_date:
                mask &= df["date"] >= pd.to_datetime(start_date)
            if end_date:
                mask &= df["date"] <= pd.to_datetime(end_date)
            candidates = df[mask]
            if not candidates.empty:
                return int(candidates.index[0])
        return 0

    out: Dict[str, float] = {}

    # Decide field sets per statement
    fields_by_stmt: Dict[str, List[str]] = {}
    for tag, df in frames.items():
        if use_auto_fields and not df.empty:
            fields_by_stmt[tag] = _numeric_cols(df)
        else:
            fields_by_stmt[tag] = [f for f in curated_fields.get(tag, []) if f in df.columns]

    # Record per-statement anchor dates + compute metrics
    anchor_dates: Dict[str, Optional[str]] = {"is": None, "bs": None, "cf": None}

    for tag, df in frames.items():
        # default: write NaNs and keep anchor date None if empty
        if df.empty:
            for col in fields_by_stmt.get(tag, []):
                for suff in DERIV_SUFFIXES:
                    out[f"{tag.upper()}:{col}{suff}"] = np.nan
            continue

        i0 = anchor_index(df)
        # store anchor date for this statement
        try:
            anchor_dates[tag] = str(pd.to_datetime(df.loc[i0, "date"]).date())
        except Exception:
            anchor_dates[tag] = None

        for col in fields_by_stmt[tag]:
            s = pd.to_numeric(df[col], errors="coerce")
            for suff, fn in DERIV_SUFFIXES.items():
                out[f"{tag.upper()}:{col}{suff}"] = fn(s, i0)

    # Emit explicit anchor date columns
    out["IS_AnchorDate"] = anchor_dates["is"]
    out["BS_AnchorDate"] = anchor_dates["bs"]
    out["CF_AnchorDate"] = anchor_dates["cf"]

    # Also emit a single overall AnchorDate (prefers IS, then BS, then CF)
    out["AnchorDate"] = anchor_dates["is"] or anchor_dates["bs"] or anchor_dates["cf"]

    return out

# ────────────────────────────────────────────────────────────────────────────────
# Orchestration
# ────────────────────────────────────────────────────────────────────────────────
async def process_ticker(ticker: str, period: str, limit: int, rl: RateLimiter,
                         sem: asyncio.Semaphore, session: aiohttp.ClientSession,
                         start_date: Optional[str], end_date: Optional[str],
                         use_auto_fields: bool, curated_fields: Dict[str, List[str]],
                         refresh: bool) -> Dict[str, Any]:
    async with sem:
        try:
            frames = await fetch_statements(ticker, period, limit, session, rl, refresh)
            metrics = compute_metrics(frames, start_date, end_date, use_auto_fields, 0.0, curated_fields)
            metrics["Ticker"] = ticker
            return metrics
        except Exception as e:
            sys.stderr.write(f"[WARN] {ticker}: {e}\n")
            return {"Ticker": ticker}

async def run(args):
    # Universe
    tickers: List[str] = []
    if args.universe == "sp500":
        tickers = await get_sp500_tickers()
    if args.tickers:
        tickers.extend([t.strip().upper() for t in args.tickers.split(",") if t.strip()])
    if args.tickers_file:
        tickers.extend([t.strip().upper() for t in Path(args.tickers_file).read_text().splitlines() if t.strip()])
    tickers = sorted(set(tickers))
    if not tickers:
        sys.exit("❌ No tickers provided. Use --universe sp500 or --tickers ... or --tickers-file ...")

    # Fields mode
    curated_fields = CURATED_FIELDS if not args.auto_fields else {"is":[], "bs":[], "cf":[]}

    # Clients
    rl = RateLimiter(args.qps)
    sem = asyncio.Semaphore(args.concurrency)
    timeout = aiohttp.ClientTimeout(total=None, sock_connect=45, sock_read=45)
    async with aiohttp.ClientSession(raise_for_status=True, timeout=timeout) as session:
        tasks = [
            process_ticker(t, args.period, args.limit, rl, sem, session,
                           args.start_date, args.end_date, args.auto_fields, curated_fields, args.refresh)
            for t in tickers
        ]
        rows: List[Dict[str, Any]] = []
        completed = 0
        for coro in asyncio.as_completed(tasks):
            rows.append(await coro)
            completed += 1
            if completed % 25 == 0:
                print(f"… {completed}/{len(tickers)} tickers done")

    # Build DataFrame
    df = pd.DataFrame(rows).set_index("Ticker").sort_index()

    # Optional coverage filter (apply after aggregation)
    if args.min_coverage > 0:
        keep = []
        n = len(df)
        for c in df.columns:
            coverage = 1.0 - (df[c].isna().sum() / n)
            if coverage >= args.min_coverage:
                keep.append(c)
        df = df[keep]

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.out, quoting=csv.QUOTE_NONNUMERIC)
    print(f"✅ Wrote {args.out} with {df.shape[0]} companies × {df.shape[1]} metrics.")

def parse_args():
    p = argparse.ArgumentParser(description="FMP Premium S&P 500 metrics ETL (with AnchorDate columns)")
    uni = p.add_mutually_exclusive_group()
    uni.add_argument("--universe", choices=["sp500"], help="Universe selector")
    uni.add_argument("--tickers", help="Comma-separated tickers (e.g., AAPL,MSFT,NVDA)")
    uni.add_argument("--tickers-file", help="Path to file with one ticker per line")

    p.add_argument("--period", choices=["quarter","annual"], default="quarter")
    p.add_argument("--limit", type=int, default=20, help="History depth to fetch")
    p.add_argument("--out", default="data/sp500_metrics.csv", help="Output CSV path")

    p.add_argument("--start-date", help="Anchor window start (YYYY-MM-DD)")
    p.add_argument("--end-date", help="Anchor window end (YYYY-MM-DD)")

    p.add_argument("--qps", type=float, default=20.0, help="Requests per second throttle")
    p.add_argument("--concurrency", type=int, default=40, help="Concurrent in-flight requests")
    p.add_argument("--refresh", action="store_true", help="Ignore cache and re-fetch everything")

    p.add_argument("--auto-fields", action="store_true",
                   help="Use ALL numeric fields returned by FMP (instead of curated list)")
    p.add_argument("--min-coverage", type=float, default=0.0,
                   help="Drop columns with coverage < this fraction (0..1)")

    return p.parse_args()

if __name__ == "__main__":
    asyncio.run(run(parse_args()))

