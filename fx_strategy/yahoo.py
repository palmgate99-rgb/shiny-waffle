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
    """Keep only finished candles, so signals never use a bar that is still forming.

    Yahoo ends every response with one extra flat row that repeats the latest price.
    While the market is open that row is stamped with the current time and the row
    before it is the forming bar, so both fail the time test below. After the close
    the flat row is stamped at the closing time and would pass as a finished candle,
    so a flat final row is always removed. If a genuine final bar happens to be flat
    it is only held back until the next bar arrives.
    """
    now = now or pd.Timestamp.now(tz="UTC").tz_localize(None)
    if len(df) and df["high"].iloc[-1] == df["low"].iloc[-1]:
        df = df.iloc[:-1]
    return df[df.index + BAR[timeframe] <= now]


def to_4h(hourly: pd.DataFrame, now: pd.Timestamp | None = None) -> pd.DataFrame:
    """Build finished four hour candles from finished one hour candles.

    Markets that trade around the clock use blocks that start at midnight UTC.
    Markets with a daily session (stocks, cash indices) are grouped four hours at a
    time from the session open, so the last candle of a day can be shorter. That is
    how charting platforms draw four hour candles for those markets.
    """
    now = now or pd.Timestamp.now(tz="UTC").tz_localize(None)
    if hourly.empty:
        return hourly
    day = hourly.index.normalize()
    around_the_clock = hourly.groupby(day).size().median() >= 20
    if around_the_clock:
        key = hourly.index.floor("4h")
    else:
        block = hourly.groupby(day).cumcount() // 4
        key = hourly.index.to_series().groupby([day, block.values]).transform("first").values
    grouped = hourly.groupby(key)
    out = grouped.agg({"open": "first", "high": "max", "low": "min", "close": "last"})
    out.index = pd.DatetimeIndex(out.index)
    if now < out.index[-1] + BAR["4h"] and (around_the_clock or grouped.size().iloc[-1] < 4):
        out = out.iloc[:-1]  # the latest block is still forming
    return out


def candles(ticker: str, now: pd.Timestamp | None = None) -> tuple[dict, dict]:
    """Finished 15 minute, 1 hour and 4 hour candles for one ticker, from two requests."""
    now = now or pd.Timestamp.now(tz="UTC").tz_localize(None)
    m15, meta = fetch(ticker, "15m")
    h1, _ = fetch(ticker, "1h")
    h1 = closed_bars(h1, "1h", now)
    return {"15m": closed_bars(m15, "15m", now), "1h": h1, "4h": to_4h(h1, now)}, meta
