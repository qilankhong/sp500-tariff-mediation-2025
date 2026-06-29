
#!/usr/bin/env python3
from __future__ import annotations

import argparse, os, sys, time, json, math
from typing import Optional, Dict, Any
from pathlib import Path

import requests
import pandas as pd

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

API_KEY = os.getenv("FMP_API_KEY")
BASE = "https://financialmodelingprep.com/api/v3"

def die(msg: str) -> None:
    print(f"❌ {msg}", file=sys.stderr)
    sys.exit(1)

def fetch_prices(symbol: str, timeseries: int = 420, retry: int = 4, backoff: float = 1.2) -> Optional[pd.DataFrame]:
    url = f"{BASE}/historical-price-full/{symbol}"
    params = {"serietype": "line", "timeseries": timeseries, "apikey": API_KEY}
    for i in range(retry):
        try:
            r = requests.get(url, params=params, timeout=30)
            if r.status_code == 429:
                # basic rate-limit backoff
                time.sleep(backoff * (i+1))
                continue
            r.raise_for_status()
            data = r.json()
            hist = data.get("historical")
            if not isinstance(hist, list) or not hist:
                return None
            df = pd.DataFrame(hist)
            # normalize columns
            if "date" not in df.columns:
                return None
            return df
        except requests.RequestException:
            time.sleep(backoff * (i+1))
    return None

def last_trading_close(df: pd.DataFrame, year: int, month: int) -> Optional[float]:
    d = df.copy()
    d["date"] = pd.to_datetime(d["date"], errors="coerce")
    sel = d[(d["date"].dt.year == year) & (d["date"].dt.month == month)].sort_values("date")
    if sel.empty:
        return None
    price_col = "adjClose" if "adjClose" in sel.columns else ("close" if "close" in sel.columns else None)
    if price_col is None or price_col not in sel.columns:
        return None
    try:
        return float(sel.iloc[-1][price_col])
    except Exception:
        return None

def recompute_returnapr_for_symbol(symbol: str, year: int) -> Optional[float]:
    df = fetch_prices(symbol)
    if df is None:
        return None
    jan = last_trading_close(df, year, 1)
    apr = last_trading_close(df, year, 4)
    if jan is None or apr is None or jan == 0:
        return None
    return (apr / jan) - 1.0

def main():
    ap = argparse.ArgumentParser(description="Overwrite ReturnApr to Jan→Apr YTD using FMP prices.")
    ap.add_argument("--in", dest="input_csv", required=True, help="Path to input CSV (must include 'symbol' column).")
    ap.add_argument("--out", dest="output_csv", required=True, help="Path to write updated CSV.")
    ap.add_argument("--year", type=int, default=2025, help="Target year for Jan and Apr (default: 2025).")
    args = ap.parse_args()

    if not API_KEY:
        die("Missing FMP_API_KEY. Put it in a .env file or export it in your shell.")

    inp = Path(args.input_csv)
    if not inp.exists():
        die(f"Input CSV not found: {inp}")

    df = pd.read_csv(inp)
    if "symbol" not in df.columns:
        # graceful fallback if user used 'Ticker'
        if "Ticker" in df.columns:
            df = df.rename(columns={"Ticker": "symbol"})
        else:
            die("Input CSV must have a 'symbol' or 'Ticker' column.")

    # Prepare an output ReturnApr column (keep existing values to start).
    if "ReturnApr" not in df.columns:
        df["ReturnApr"] = pd.NA

    updated = 0
    failed = 0

    for i, sym in enumerate(df["symbol"].astype(str).str.upper().tolist(), 1):
        val = recompute_returnapr_for_symbol(sym, args.year)
        if val is None or (isinstance(val, float) and (math.isnan(val) or math.isinf(val))):
            failed += 1
            # Keep the original value if present; just log.
            print(f"⚠️  {sym}: could not compute Jan→Apr {args.year}; keeping existing ReturnApr", file=sys.stderr)
            continue
        df.loc[df["symbol"].astype(str).str.upper() == sym, "ReturnApr"] = val
        updated += 1
        # gentle throttle to avoid rate limits
        time.sleep(0.12)

    # Write out exactly the same columns, with ReturnApr overwritten
    outp = Path(args.output_csv)
    outp.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(outp, index=False)
    print(f"✅ Done. Overwrote ReturnApr for {updated} tickers; {failed} unchanged.")
    print(f"→ {outp}")

if __name__ == "__main__":
    main()

