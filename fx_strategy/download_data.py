"""Download free daily data from FRED into the folder layout the backtest reads.

Run this on a machine with normal internet access:

    python -m fx_strategy.download_data --out data

Sources (all from fred.stlouisfed.org, no API key needed)
  prices     Federal Reserve H.10 daily noon rates. Close only, so the backtest
             approximates the open, high and low. See data.fill_ohlc.
  rates      OECD three month interbank rates, monthly.
  valuation  BIS real broad effective exchange rates, monthly. Valuation is the
             deviation of each index from its own trailing ten year average. This
             is a stand in for a purchasing power parity gap that can be computed
             without hindsight.

Monthly series are shifted forward by a publication lag so the backtest only sees
numbers that had been published by each date.
"""

from __future__ import annotations

import argparse
import io
import urllib.request
from pathlib import Path

import pandas as pd

FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={}"

# Each FRED series is already quoted the same way round as its pair.
PRICE_SERIES = {
    "EURUSD": "DEXUSEU", "GBPUSD": "DEXUSUK", "USDJPY": "DEXJPUS",
    "AUDUSD": "DEXUSAL", "USDCAD": "DEXCAUS", "NZDUSD": "DEXUSNZ",
}
RATE_SERIES = {
    "USD": "IR3TIB01USM156N", "EUR": "IR3TIB01EZM156N", "GBP": "IR3TIB01GBM156N",
    "JPY": "IR3TIB01JPM156N", "AUD": "IR3TIB01AUM156N", "CAD": "IR3TIB01CAM156N",
    "NZD": "IR3TIB01NZM156N",
}
REER_SERIES = {
    "USD": "RBUSBIS", "EUR": "RBXMBIS", "GBP": "RBGBBIS", "JPY": "RBJPBIS",
    "AUD": "RBAUBIS", "CAD": "RBCABIS", "NZD": "RBNZBIS",
}
RATE_LAG_DAYS = 35       # a monthly average is known shortly after the month ends
VALUATION_LAG_DAYS = 50  # BIS publishes around the middle of the following month


def fetch(series_id: str) -> pd.Series:
    request = urllib.request.Request(FRED.format(series_id), headers={"User-Agent": "python-urllib"})
    with urllib.request.urlopen(request, timeout=60) as response:
        df = pd.read_csv(io.BytesIO(response.read()))
    df.columns = ["date", "value"]
    df["date"] = pd.to_datetime(df["date"])
    return pd.to_numeric(df.set_index("date")["value"], errors="coerce").dropna().rename(series_id)


def fetch_table(series: dict, lag_days: int) -> pd.DataFrame:
    table = pd.concat({ccy: fetch(sid) for ccy, sid in series.items()}, axis=1, sort=True)
    table.index = table.index + pd.Timedelta(days=lag_days)
    return table.rename_axis("date")


def valuation_from_reer(reer: pd.DataFrame, window_months: int = 120) -> pd.DataFrame:
    return (reer / reer.rolling(window_months, min_periods=60).mean() - 1).dropna(how="all")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--out", default="data")
    args = parser.parse_args()
    out = Path(args.out)
    (out / "prices").mkdir(parents=True, exist_ok=True)
    for pair, sid in PRICE_SERIES.items():
        series = fetch(sid).rename("close").rename_axis("date")
        series.to_csv(out / "prices" / f"{pair}.csv")
        print(f"{pair}: {len(series)} days from {series.index[0].date()} to {series.index[-1].date()}")
    fetch_table(RATE_SERIES, RATE_LAG_DAYS).to_csv(out / "rates.csv")
    reer = pd.concat({ccy: fetch(sid) for ccy, sid in REER_SERIES.items()}, axis=1, sort=True)
    valuation = valuation_from_reer(reer)
    valuation.index = valuation.index + pd.Timedelta(days=VALUATION_LAG_DAYS)
    valuation.rename_axis("date").to_csv(out / "valuation.csv")
    print(f"saved rates.csv and valuation.csv to {out}")


if __name__ == "__main__":
    main()
