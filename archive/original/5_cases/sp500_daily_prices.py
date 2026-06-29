#!/usr/bin/env python3
import asyncio
import aiohttp
import os
import pandas as pd
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()
API_KEY = os.getenv("FMP_API_KEY")

BASE_URL = "https://financialmodelingprep.com/stable"
OUT = Path("sp500_daily_prices.csv")
OUT.parent.mkdir(exist_ok=True)

TICKER_FILE = "sp500_jan_apr_2025_1.17.26.csv"
START_DATE = "2025-01-01"
END_DATE = "2025-12-31"

# much slower on purpose
REQUEST_DELAY_SECONDS = 0.35   # ~171 requests/minute max before retries
MAX_RETRIES = 6


def load_tickers_from_csv(path: str) -> list[str]:
    df = pd.read_csv(path, index_col=0)
    tickers = (
        pd.Index(df.index)
        .astype(str)
        .str.strip()
        .str.upper()
        .str.replace(".", "-", regex=False)
        .tolist()
    )
    return list(dict.fromkeys(tickers))


def load_completed_symbols(output_path: Path) -> set[str]:
    if output_path.exists():
        old = pd.read_csv(output_path)
        if "symbol" in old.columns:
            return set(old["symbol"].dropna().unique())
    return set()


async def fetch_prices(symbol: str, session: aiohttp.ClientSession):
    url = f"{BASE_URL}/historical-price-eod/dividend-adjusted"
    params = {
        "symbol": symbol,
        "from": START_DATE,
        "to": END_DATE,
        "apikey": API_KEY,
    }

    backoff = 5

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=60)) as r:
                text = await r.text()

                if r.status == 429:
                    print(f"⏳ {symbol}: hit 429, sleeping {backoff}s (attempt {attempt}/{MAX_RETRIES})")
                    await asyncio.sleep(backoff)
                    backoff *= 2
                    continue

                if r.status != 200:
                    print(f"❌ {symbol}: HTTP {r.status} | {text[:200]}")
                    return None

                try:
                    data = await r.json()
                except Exception:
                    print(f"❌ {symbol}: non-JSON response | {text[:200]}")
                    return None

                if isinstance(data, list):
                    records = data
                elif isinstance(data, dict):
                    if "historical" in data and isinstance(data["historical"], list):
                        records = data["historical"]
                    elif "data" in data and isinstance(data["data"], list):
                        records = data["data"]
                    else:
                        print(f"⚠️ {symbol}: unexpected JSON shape: {str(data)[:200]}")
                        return None
                else:
                    print(f"⚠️ {symbol}: unexpected response type")
                    return None

                if not records:
                    print(f"⚠️ {symbol}: no records returned")
                    return None

                df = pd.DataFrame(records)

                close_col = None
                for candidate in ["adjClose", "adjustedClose", "close"]:
                    if candidate in df.columns:
                        close_col = candidate
                        break

                if "date" not in df.columns or close_col is None:
                    print(f"⚠️ {symbol}: missing expected columns. Got {list(df.columns)}")
                    return None

                out = df[["date", close_col]].copy()
                out.rename(columns={close_col: "adjClose"}, inplace=True)
                out["symbol"] = symbol
                return out[["symbol", "date", "adjClose"]]

        except asyncio.TimeoutError:
            print(f"⏳ {symbol}: timeout, sleeping {backoff}s")
            await asyncio.sleep(backoff)
            backoff *= 2
        except Exception as e:
            print(f"❌ {symbol}: {e}")
            return None

    print(f"❌ {symbol}: failed after {MAX_RETRIES} retries")
    return None


async def main():
    if not API_KEY:
        raise RuntimeError("FMP_API_KEY is missing from your environment.")

    tickers = load_tickers_from_csv(TICKER_FILE)
    completed = load_completed_symbols(OUT)

    if completed:
        tickers = [t for t in tickers if t not in completed]
        print(f"Resuming: {len(completed)} symbols already saved, {len(tickers)} left")
    else:
        print(f"Starting fresh with {len(tickers)} symbols")

    headers = {
        "Accept": "application/json",
        "User-Agent": "python-aiohttp-sp500-fetcher/1.0",
    }

    all_rows = []
    if OUT.exists():
        existing = pd.read_csv(OUT)
        all_rows.append(existing)

    async with aiohttp.ClientSession(headers=headers) as session:
        for i, symbol in enumerate(tickers, start=1):
            print(f"{i}/{len(tickers)} {symbol}")

            df = await fetch_prices(symbol, session)
            if df is not None and not df.empty:
                all_rows.append(df)

                combined = pd.concat(all_rows, ignore_index=True)
                combined["date"] = pd.to_datetime(combined["date"], errors="coerce")
                combined = combined.dropna(subset=["date", "adjClose"])
                combined = combined.sort_values(["symbol", "date"]).reset_index(drop=True)
                combined.to_csv(OUT, index=False)

                print(f"✅ saved {symbol}")

            await asyncio.sleep(REQUEST_DELAY_SECONDS)

    final_df = pd.concat(all_rows, ignore_index=True)
    final_df["date"] = pd.to_datetime(final_df["date"], errors="coerce")
    final_df = final_df.dropna(subset=["date", "adjClose"])
    final_df = final_df.sort_values(["symbol", "date"]).reset_index(drop=True)
    final_df.to_csv(OUT, index=False)

    print(f"✅ Finished. Saved {OUT} with {len(final_df):,} rows")


if __name__ == "__main__":
    asyncio.run(main())
