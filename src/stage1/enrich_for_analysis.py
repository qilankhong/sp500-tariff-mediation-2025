#!/usr/bin/env python3
from __future__ import annotations
import os, sys, csv, json, time, asyncio, math
from pathlib import Path
from typing import Dict, Any

import aiohttp
import numpy as np
import pandas as pd
from dotenv import load_dotenv

## run
# python enrich_for_analysis.py \
#   --in data/interim/sp500_metrics.csv \
#   --out data/processed/sp500_analysis_data.csv \
#   --qps 8 --concurrency 12


# ── Config ────────────────────────────────────────────────────────────────
load_dotenv()
API_KEY = os.getenv("FMP_API_KEY")

BASE = "https://financialmodelingprep.com/stable"
CACHE = Path(".cache_enrich"); CACHE.mkdir(exist_ok=True)

SECTORS = [
    "Basic Materials","Communication Services","Consumer Cyclical","Consumer Defensive",
    "Energy","Financial Services","Healthcare","Industrials","Real Estate",
    "Technology","Utilities"
]

# ── Helpers ────────────────────────────────────────────────────────────────
class RateLimiter:
    def __init__(self, qps: float = 8.0):
        self.qps = max(0.5, qps); self.tokens = self.qps; self.ts = time.monotonic()
    async def acquire(self):
        while True:
            now = time.monotonic()
            self.tokens += (now - self.ts) * self.qps
            self.ts = now
            if self.tokens >= 1:
                self.tokens -= 1; return
            await asyncio.sleep((1 - self.tokens) / self.qps)

async def fetch_json(session, url, params, cache_file, rl, refresh, retries=4):
    if cache_file.exists() and not refresh:
        return json.loads(cache_file.read_text())
    backoff = 1.0
    for attempt in range(retries):
        await rl.acquire()
        try:
            async with session.get(url, params=params, timeout=45) as r:
                if r.status == 200:
                    data = await r.json(); cache_file.write_text(json.dumps(data)); return data
                if r.status in (429,503): raise aiohttp.ClientError(f"HTTP {r.status}")
                raise RuntimeError(f"FMP returned HTTP {r.status}")
        except (aiohttp.ClientError, asyncio.TimeoutError):
            if attempt == retries - 1: raise
            await asyncio.sleep(backoff); backoff = min(30.0, backoff*2)
    raise RuntimeError("unreachable")

# ── Fetch per ticker ──────────────────────────────────────────────────────
async def fetch_sector(session, rl, refresh, symbol: str) -> Dict[str,Any]:
    out = {"symbol": symbol}
    prof = await fetch_json(session,f"{BASE}/profile",{"symbol":symbol},
                            CACHE/f"profile_{symbol}.json",rl,refresh)
    if isinstance(prof,list) and prof:
        out["sector"]=prof[0].get("sector")
    return out

def add_sector_dummies(df: pd.DataFrame)->pd.DataFrame:
    for s in SECTORS:
        df[s]=((df["sector"]==s).astype(int) if "sector" in df.columns else 0)
    return df

# ── Main ──────────────────────────────────────────────────────────────────
async def enrich(input_csv, output_csv, refresh=False, qps=8.0, concurrency=12):
    if not API_KEY:
        sys.exit("❌ FMP_API_KEY missing. Put it in .env (FMP_API_KEY=...)")

    base=pd.read_csv(input_csv)
    if "symbol" not in base.columns and "Ticker" in base.columns:
        base=base.rename(columns={"Ticker":"symbol"})
    if "symbol" not in base.columns: sys.exit("❌ Need 'symbol' or 'Ticker' col")
    symbols=base["symbol"].astype(str).str.upper().tolist()

    rl=RateLimiter(qps); sem=asyncio.Semaphore(concurrency)

    async def fetch_one(symbol):
        async with sem:
            return await fetch_sector(session,rl,refresh,symbol)

    async with aiohttp.ClientSession(headers={"apikey":API_KEY},timeout=aiohttp.ClientTimeout(total=None)) as session:
        tasks=[fetch_one(s) for s in symbols]
        rows=[await fut for fut in asyncio.as_completed(tasks)]
    enrich_df=pd.DataFrame(rows); enrich_df=add_sector_dummies(enrich_df)

    # Column order: symbol → sector indicators → statement metrics
    front=["symbol"]+SECTORS
    for c in front:
        if c not in enrich_df.columns: enrich_df[c]=np.nan
    out_df=pd.merge(enrich_df[front],base,on="symbol",how="right")
    rest=[c for c in out_df.columns if c not in front]
    out_df=out_df[front+rest]
    Path(output_csv).parent.mkdir(parents=True,exist_ok=True)
    out_df.to_csv(output_csv,index=False,quoting=csv.QUOTE_NONNUMERIC)
    print(f"✅ Wrote {output_csv} with shape {out_df.shape}")

if __name__=="__main__":
    import argparse
    ap=argparse.ArgumentParser()
    ap.add_argument("--in",dest="input_csv",required=True)
    ap.add_argument("--out",dest="output_csv",required=True)
    ap.add_argument("--refresh",action="store_true")
    ap.add_argument("--qps",type=float,default=8.0)
    ap.add_argument("--concurrency",type=int,default=12)
    args=ap.parse_args()
    asyncio.run(enrich(args.input_csv,args.output_csv,args.refresh,args.qps,args.concurrency))
