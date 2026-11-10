"""Loading price, rate, valuation and news data, plus a synthetic generator for testing."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

PAIRS = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "NZDUSD"]
CURRENCIES = ["USD", "EUR", "GBP", "JPY", "AUD", "CAD", "NZD"]


def fill_ohlc(df: pd.DataFrame, wick_days: int = 14) -> pd.DataFrame:
    """Accept close only data by estimating the open, high and low.

    The open is the previous close, which is fair for a market that trades around
    the clock. The high and low are pushed beyond the open and close by half the
    recent average absolute daily change. For a random walk that is the expected
    size of the wicks, and it makes the average true range come out at about twice
    the average close to close change, as it does in real bars. Without this the
    ATR would be roughly half its true size, so stops would sit too close, positions
    would be too large and intraday stop hits would be missed. It is still an
    estimate: real bars from a broker are better.
    """
    df = df.dropna(subset=["close"]).copy()
    if "open" not in df:
        df["open"] = df["close"].shift().fillna(df["close"])
    if "high" not in df or "low" not in df:
        wick = 0.5 * df["close"].diff().abs().rolling(wick_days, min_periods=1).mean().fillna(0)
        df["high"] = df[["open", "close"]].max(axis=1) + wick
        df["low"] = df[["open", "close"]].min(axis=1) - wick
    return df[["open", "high", "low", "close"]]


def _read(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["date"]).set_index("date").sort_index()
    df.columns = [c.strip() for c in df.columns]
    return df


def load_folder(folder: str | Path):
    """Read a data folder laid out as described in the README.

    Returns prices, rates, valuation, events. The last three are None when the
    file is missing, and the matching rule is then simply not applied.
    """
    folder = Path(folder)
    prices = {}
    for path in sorted((folder / "prices").glob("*.csv")):
        df = _read(path)
        df.columns = [c.lower() for c in df.columns]
        prices[path.stem.upper()] = fill_ohlc(df)
    if not prices:
        raise FileNotFoundError(f"no price files found in {folder / 'prices'}")
    rates = _read(folder / "rates.csv") if (folder / "rates.csv").exists() else None
    valuation = _read(folder / "valuation.csv") if (folder / "valuation.csv").exists() else None
    events = None
    if (folder / "events.csv").exists():
        events = pd.read_csv(folder / "events.csv", parse_dates=["date"])
    return prices, rates, valuation, events


def first_friday_events(start, end, currency: str = "USD") -> pd.DataFrame:
    """Approximate US payrolls dates as the first Friday of each month.

    The real release occasionally moves to the second Friday, and this covers no
    inflation prints or central bank meetings. Supply events.csv for a real calendar.
    """
    days = pd.date_range(start, end, freq="D")
    fridays = days[(days.weekday == 4) & (days.day <= 7)]
    return pd.DataFrame({"date": fridays, "currency": currency})


def synthetic(years: int = 20, seed: int = 7):
    """Random data with trending regimes, for checking that the code runs.

    Results on this data say nothing about how the strategy performs in real markets.
    """
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2004-01-01", periods=years * 260)
    n = len(dates)
    start = {"EURUSD": 1.20, "GBPUSD": 1.60, "USDJPY": 105.0, "AUDUSD": 0.75, "USDCAD": 1.30, "NZDUSD": 0.65}
    prices = {}
    for pair in PAIRS:
        drift = np.repeat(rng.normal(0, 0.0004, n // 120 + 1), 120)[:n]  # regimes of about six months
        vol = 0.006 * np.exp(np.cumsum(rng.normal(0, 0.03, n)) * 0.2).clip(0.5, 2.5)
        close = start[pair] * np.exp(np.cumsum(drift + rng.normal(0, 1, n) * vol))
        open_ = np.r_[close[0], close[:-1]]
        spread = np.abs(rng.normal(0, 1, n)) * vol * close * 0.6
        prices[pair] = pd.DataFrame({
            "open": open_, "high": np.maximum(open_, close) + spread,
            "low": np.minimum(open_, close) - spread, "close": close}, index=dates)
    months = pd.date_range(dates[0], dates[-1], freq="MS")
    rates = pd.DataFrame(
        {c: (2.5 + np.cumsum(rng.normal(0, 0.15, len(months)))).clip(0, 8) for c in CURRENCIES}, index=months)
    valuation = pd.DataFrame(
        {c: np.cumsum(rng.normal(0, 0.02, len(months))).clip(-0.4, 0.4) for c in CURRENCIES}, index=months)
    return prices, rates, valuation, first_friday_events(dates[0], dates[-1])
