#!/usr/bin/env python3
from __future__ import annotations
import os, sys, csv, json, time, asyncio, math
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

import aiohttp
import numpy as np
import pandas as pd
from dotenv import load_dotenv

## run
# python enrich_for_analysis.py \
#   --in sp500_jan_apr_2025.csv \
#   --out sp500_jan_apr_2025_ANALYSIS_READY.csv \
#   --qps 8 --concurrency 12


# ── Config ────────────────────────────────────────────────────────────────
load_dotenv()
API_KEY = os.getenv("FMP_API_KEY")
if not API_KEY:
    sys.exit("❌ FMP_API_KEY missing. Put it in .env (FMP_API_KEY=...)")

BASE = "https://financialmodelingprep.com/api/v3"
CACHE = Path(".cache_enrich"); CACHE.mkdir(exist_ok=True)

SECTORS = [
    "Basic Materials","Communication Services","Consumer Cyclical","Consumer Defensive",
    "Energy","Financial Services","Healthcare","Industrials","Real Estate",
    "Technology","Utilities"
]

MARKET_COLS = [
    "marketCap","priceAvg200","avgVolume","sharesOutstanding","beta",
    "stockLiquidity","price50over200","PE ratio"
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
                r.raise_for_status()
        except (aiohttp.ClientError, asyncio.TimeoutError):
            if attempt == retries - 1: raise
            await asyncio.sleep(backoff); backoff = min(30.0, backoff*2)
    raise RuntimeError("unreachable")

def last_trading_close(df: pd.DataFrame, year: int, month: int) -> Optional[float]:
    df = df.copy(); df["date"] = pd.to_datetime(df["date"], errors="coerce")
    sel = df[(df["date"].dt.year==year)&(df["date"].dt.month==month)].sort_values("date")
    if sel.empty: return None
    price_col = "adjClose" if "adjClose" in sel.columns else "close"
    return float(sel.iloc[-1][price_col])

def moving_average(df: pd.DataFrame, window: int, asof: Tuple[int,int,int]) -> Optional[float]:
    ref = pd.Timestamp(*asof); df = df.copy(); df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df[df["date"]<=ref].sort_values("date"); price_col = "adjClose" if "adjClose" in df.columns else "close"
    tail = df.iloc[-window:]; 
    if price_col not in df.columns or len(tail)==0: return None
    return float(tail[price_col].mean())

def avg_volume(df: pd.DataFrame, days: int, asof: Tuple[int,int,int]) -> Optional[float]:
    ref = pd.Timestamp(*asof); df = df.copy(); df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df[df["date"]<=ref].sort_values("date").iloc[-days:]
    if "volume" not in df.columns or len(df)==0: return None
    return float(df["volume"].mean())

def stock_liquidity(df: pd.DataFrame, days: int, asof: Tuple[int,int,int]) -> Optional[float]:
    ref = pd.Timestamp(*asof); df = df.copy(); df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df[df["date"]<=ref].sort_values("date").iloc[-days:]
    price_col = "adjClose" if "adjClose" in df.columns else "close"
    if "volume" not in df.columns or price_col not in df.columns or len(df)==0: return None
    return float((df["volume"]*df[price_col]).mean())

def pct_return(a, b): 
    if a is None or b is None or b==0: return None
    return (a-b)/abs(b)

# ── Fetch per ticker ──────────────────────────────────────────────────────
async def fetch_profile_quote_prices(session, rl, refresh, symbol: str) -> Dict[str,Any]:
    out = {"symbol": symbol}
    # Profile
    prof = await fetch_json(session,f"{BASE}/profile/{symbol}",{"apikey":API_KEY},
                            CACHE/f"profile_{symbol}.json",rl,refresh)
    if isinstance(prof,list) and prof:
        p0=prof[0]; out["sector"]=p0.get("sector"); out["sharesOutstanding"]=p0.get("sharesOutstanding"); out["beta"]=p0.get("beta")
    # Quote
    quote = await fetch_json(session,f"{BASE}/quote/{symbol}",{"apikey":API_KEY},
                             CACHE/f"quote_{symbol}.json",rl,refresh)
    if isinstance(quote,list) and quote:
        q0=quote[0]; out["marketCap"]=q0.get("marketCap"); out["avgVolume"]=q0.get("avgVolume"); out["PE ratio"]=q0.get("pe") or q0.get("peRatio")
    # Prices
    hist = await fetch_json(session,f"{BASE}/historical-price-full/{symbol}",
                            {"serietype":"line","timeseries":400,"apikey":API_KEY},
                            CACHE/f"prices_{symbol}.json",rl,refresh)
    prices = hist.get("historical") if isinstance(hist,dict) else None
    if prices:
        hdf=pd.DataFrame(prices)
        # Added Dec (for Jan return baseline); kept Mar/Apr for Apr return
        dec=last_trading_close(hdf,2024,12)
        jan=last_trading_close(hdf,2025,1)
        mar=last_trading_close(hdf,2025,3)
        apr=last_trading_close(hdf,2025,4)

        # Switched to January–April instead of February–April
        out["ReturnApr_monthly"]=pct_return(apr,mar)
        out["ReturnApr"]=pct_return(apr,jan)

        out["priceAvg200"]=moving_average(hdf,200,(2025,4,30))
        ma50=moving_average(hdf,50,(2025,4,30)); ma200=out["priceAvg200"]
        out["price50over200"]=int(ma50 is not None and ma200 is not None and ma50>ma200)
        out["avgVolume"]=avg_volume(hdf,60,(2025,4,30)) or out.get("avgVolume")
        out["stockLiquidity"]=stock_liquidity(hdf,60,(2025,4,30))
    return out

def add_sector_dummies(df: pd.DataFrame)->pd.DataFrame:
    for s in SECTORS:
        df[s]=((df["sector"]==s).astype(int) if "sector" in df.columns else 0)
    return df

# ── Main ──────────────────────────────────────────────────────────────────
async def enrich(input_csv, output_csv, refresh=False, qps=8.0, concurrency=12):
    base=pd.read_csv(input_csv)
    if "symbol" not in base.columns and "Ticker" in base.columns:
        base=base.rename(columns={"Ticker":"symbol"})
    if "symbol" not in base.columns: sys.exit("❌ Need 'symbol' or 'Ticker' col")
    symbols=base["symbol"].astype(str).str.upper().tolist()

    rl=RateLimiter(qps); sem=asyncio.Semaphore(concurrency)
    async with aiohttp.ClientSession(raise_for_status=True,timeout=aiohttp.ClientTimeout(total=None)) as session:
        tasks=[fetch_profile_quote_prices(session,rl,refresh,s) for s in symbols]
        rows=[await fut for fut in asyncio.as_completed(tasks)]
    enrich_df=pd.DataFrame(rows); enrich_df=add_sector_dummies(enrich_df)

    # Column order: symbol → ReturnApr_monthly → ReturnApr → sectors → market cols
    front=["symbol","ReturnApr_monthly","ReturnApr"]+SECTORS+MARKET_COLS
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
