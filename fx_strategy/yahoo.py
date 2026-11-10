"""Intraday candles from Yahoo Finance's public chart endpoint.

Yahoo does not document or guarantee this endpoint. It can change, throttle or
return gaps without notice, so treat the data as indicative, not as a broker feed.
"""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request

import pandas as pd

HOSTS = ["query1.finance.yahoo.com", "query2.finance.yahoo.com"]
BAR = {"15m": pd.Timedelta(minutes=15), "1h": pd.Timedelta(hours=1), "4h": pd.Timedelta(hours=4)}
MAX_RANGE = {"15m": "60d", "1h": "730d"}


def fetch(ticker: str, interval: str, range_: str | None = None, retries: int = 3):
    """Return (candles, meta). Candles are indexed by bar start time in UTC, without a timezone."""
    range_ = range_ or MAX_RANGE[interval]
    error = None
    for attempt in range(retries):
        host = HOSTS[attempt % len(HOSTS)]
        url = (f"https://{host}/v8/finance/chart/{urllib.parse.quote(ticker)}"
               f"?interval={interval}&range={range_}")
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(request, timeout=30) as response:
                result = json.load(response)["chart"]["result"][0]
            quote = result["indicators"]["quote"][0]
            df = pd.DataFrame(
                {k: quote[k] for k in ("open", "high", "low", "close")},
                index=pd.to_datetime(result["timestamp"], unit="s"),
            ).dropna()
            return df[~df.index.duplicated(keep="last")].sort_index(), result["meta"]
        except Exception as exc:  # network errors, throttling, missing fields
            error = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"Yahoo request failed for {ticker} {interval}: {error}")


def closed_bars(df: pd.DataFrame, timeframe: str, now: pd.Timestamp | None = None) -> pd.DataFrame:
    """Drop the bar that is still forming, so signals only use finished candles."""
    now = now or pd.Timestamp.now(tz="UTC").tz_localize(None)
    return df[df.index + BAR[timeframe] <= now]


def to_4h(hourly: pd.DataFrame) -> pd.DataFrame:
    """Build four hour candles from one hour candles, in blocks that start at midnight UTC."""
    return hourly.resample("4h").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()


def candles(ticker: str, now: pd.Timestamp | None = None) -> tuple[dict, dict]:
    """Closed 15 minute, 1 hour and 4 hour candles for one ticker, from two requests."""
    m15, meta = fetch(ticker, "15m")
    h1, _ = fetch(ticker, "1h")
    h1 = closed_bars(h1, "1h", now)
    return {"15m": closed_bars(m15, "15m", now), "1h": h1, "4h": closed_bars(to_4h(h1), "4h", now)}, meta
