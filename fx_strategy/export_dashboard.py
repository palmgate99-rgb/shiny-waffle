"""Write dashboard_data.json: real candles and strategy readings for the dashboard.

    python -m fx_strategy.export_dashboard --out dashboard_data.json

For every market and each of the 15 minute, 1 hour and 4 hour timeframes it applies
the same rules as the backtest (strategy.add_indicators and strategy.risk_adjustment)
to finished candles from Yahoo Finance. Interest rates and valuations for the carry
and value layers come from FRED and are refreshed once a day.
"""

from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

import pandas as pd

from . import yahoo
from .data import first_friday_events
from .strategy import Config, add_indicators, risk_adjustment

TIMEFRAMES = ["15m", "1h", "4h"]
CANDLES_SHOWN = 80
SIGNAL_FRESH_BARS = 3  # a trigger stays on the dashboard for this many finished bars

# symbol shown on the dashboard -> (Yahoo ticker, label, category)
MARKETS = {
    "EUR/USD": ("EURUSD=X", "Euro Dollar", "currencies"),
    "GBP/USD": ("GBPUSD=X", "British Pound Dollar", "currencies"),
    "USD/JPY": ("USDJPY=X", "Dollar Yen", "currencies"),
    "USD/CAD": ("USDCAD=X", "Dollar CAD", "currencies"),
    "AUD/USD": ("AUDUSD=X", "Aussie Dollar", "currencies"),
    "NZD/USD": ("NZDUSD=X", "Kiwi Dollar", "currencies"),
    "EUR/JPY": ("EURJPY=X", "Euro Yen", "currencies"),
    "GBP/JPY": ("GBPJPY=X", "Pound Yen", "currencies"),
    "NAS100": ("^NDX", "Nasdaq 100", "indices"),
    "US30": ("^DJI", "Dow Jones", "indices"),
    "SPX500": ("^GSPC", "S&P 500", "indices"),
    "GER40": ("^GDAXI", "DAX Index", "indices"),
    "UK100": ("^FTSE", "FTSE 100", "indices"),
    "JPN225": ("^N225", "Nikkei 225", "indices"),
    "GOLD": ("GC=F", "Gold Futures (COMEX)", "gold"),
    "SILVER": ("SI=F", "Silver Futures (COMEX)", "gold"),
    "AAPL": ("AAPL", "Apple Inc.", "stocks"),
    "NVDA": ("NVDA", "NVIDIA", "stocks"),
    "TSLA": ("TSLA", "Tesla", "stocks"),
    "MSFT": ("MSFT", "Microsoft", "stocks"),
    "AMZN": ("AMZN", "Amazon", "stocks"),
    "META": ("META", "Meta Platforms", "stocks"),
}


def clean(value, digits=6):
    """Round to significant digits and turn NaN into null for JSON."""
    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        return None
    value = float(value)
    return 0.0 if value == 0 else round(value, digits - 1 - int(math.floor(math.log10(abs(value)))))


def macro_tables(previous: dict | None, now: pd.Timestamp) -> dict:
    """Latest interest rates and valuations from FRED, reused for a day between refreshes."""
    if previous and previous.get("fetched") and now - pd.Timestamp(previous["fetched"]) < pd.Timedelta(hours=24):
        return previous
    try:
        from .download_data import (RATE_LAG_DAYS, RATE_SERIES, REER_SERIES, VALUATION_LAG_DAYS,
                                    fetch, fetch_table, valuation_from_reer)
        rates = fetch_table(RATE_SERIES, RATE_LAG_DAYS).loc[:now].ffill().iloc[-1]
        reer = pd.concat({c: fetch(s) for c, s in REER_SERIES.items()}, axis=1, sort=True)
        valuation = valuation_from_reer(reer)
        valuation.index = valuation.index + pd.Timedelta(days=VALUATION_LAG_DAYS)
        valuation = valuation.loc[:now].ffill().iloc[-1]
        return {"fetched": now.isoformat(), "rates": {c: clean(v) for c, v in rates.items()},
                "valuation": {c: clean(v) for c, v in valuation.items()}}
    except Exception as exc:
        print(f"FRED unavailable, keeping previous macro data: {exc}")
        return previous or {"fetched": None, "rates": {}, "valuation": {}}


def side(cfg, symbol, direction, macro, vol_ratio):
    """Risk multiplier and reasons for one direction of one market."""
    nan = float("nan")
    carry = valuation = nan
    if "/" in symbol:
        base, quote = symbol.split("/")
        rates, values = macro["rates"], macro["valuation"]
        if rates.get(base) is not None and rates.get(quote) is not None:
            carry = direction * (rates[base] - rates[quote]) - cfg.swap_markup_pct
        bought = values.get(base if direction == 1 else quote)
        valuation = nan if bought is None else bought
    mult, notes = risk_adjustment(cfg, carry, valuation, vol_ratio)
    return {"mult": mult, "notes": notes}


def reading(cfg, symbol, df, macro):
    """Strategy state on the latest finished candle of one timeframe."""
    ind = add_indicators(df, cfg)
    last = ind.iloc[-1]
    recent = ind["signal"].iloc[-SIGNAL_FRESH_BARS:]
    fired = recent[recent != 0]
    signal, age, signal_price = 0, None, None
    if len(fired) and int(fired.iloc[-1]) == int(last["trend"]):  # ignore a trigger the trend has since left
        signal = int(fired.iloc[-1])
        age = len(ind) - 1 - ind.index.get_loc(fired.index[-1])
        signal_price = clean(ind.at[fired.index[-1], "close"])
    tail = ind.iloc[-CANDLES_SHOWN:]
    return {
        "bar_time": ind.index[-1].isoformat() + "Z",
        "bars": len(ind),
        "close": clean(last["close"]), "sma": clean(last["sma"]), "mom": clean(last["mom"], 4),
        "rsi": clean(last["rsi"], 4), "atr": clean(last["atr"]), "vol_ratio": clean(last["vol_ratio"], 3),
        "trend": int(last["trend"]), "signal": signal, "signal_age": age, "signal_price": signal_price,
        "long": side(cfg, symbol, 1, macro, last["vol_ratio"]),
        "short": side(cfg, symbol, -1, macro, last["vol_ratio"]),
        "candles": [[int(t.timestamp()), clean(r.open), clean(r.high), clean(r.low), clean(r.close), clean(r.sma)]
                    for t, r in tail.iterrows()],
    }


def build(previous: dict | None = None, pause: float = 0.4) -> dict:
    cfg = Config()
    now = pd.Timestamp.now(tz="UTC").tz_localize(None)
    macro = macro_tables((previous or {}).get("macro"), now)
    markets, failed, last_price = {}, [], {}
    for symbol, (ticker, label, category) in MARKETS.items():
        try:
            frames, meta = yahoo.candles(ticker, now)
            tfs = {tf: reading(cfg, symbol, frames[tf], macro) for tf in TIMEFRAMES if len(frames[tf]) > cfg.sma_days}
            if not tfs:
                raise RuntimeError("not enough history")
            hourly = frames["1h"]["close"]
            earlier = hourly[hourly.index.normalize() < hourly.index[-1].normalize()]
            price = frames["15m"]["close"].iloc[-1]
            last_price[symbol] = price
            markets[symbol] = {
                "label": label, "category": category, "ticker": ticker,
                "currency": meta.get("currency", "USD"),
                "layers": "all" if category == "currencies" else "technical",
                "price": clean(price),
                "price_time": frames["15m"].index[-1].isoformat() + "Z",
                "change_pct": clean((price / earlier.iloc[-1] - 1) * 100, 3) if len(earlier) else None,
                "tf": tfs,
            }
        except Exception as exc:
            print(f"{symbol}: {exc}")
            failed.append(symbol)
            if previous and symbol in previous.get("markets", {}):
                markets[symbol] = dict(previous["markets"][symbol], stale=True)
        time.sleep(pause)

    # value in USD of one unit of each quote currency, for position sizing on the dashboard
    to_usd = {"USD": 1.0}
    for ccy, pair, invert in [("JPY", "USD/JPY", True), ("CAD", "USD/CAD", True),
                              ("EUR", "EUR/USD", False), ("GBP", "GBP/USD", False)]:
        if pair in last_price:
            to_usd[ccy] = clean(1 / last_price[pair] if invert else last_price[pair])
    today = now.normalize()
    news = first_friday_events(today, today)
    return {
        "generated": now.isoformat(timespec="seconds") + "Z",
        "source": "Yahoo Finance candles (unofficial feed); interest rates and valuations from FRED",
        "timeframes": TIMEFRAMES,
        "rules": {"sma": cfg.sma_days, "momentum": cfg.momentum_days, "rsi": cfg.rsi_days,
                  "rsi_long": cfg.rsi_long_level, "rsi_short": cfg.rsi_short_level,
                  "stop_atr": cfg.stop_atr, "trail_atr": cfg.trail_atr,
                  "overvalued": cfg.overvalued_limit, "vol_spike": cfg.vol_spike_ratio},
        "news_today": sorted(set(news["currency"])),
        "to_usd": to_usd, "macro": macro, "failed": failed, "markets": markets,
    }


def main():
    parser = argparse.ArgumentParser(description="Export real market data for the dashboard")
    parser.add_argument("--out", default="dashboard_data.json")
    args = parser.parse_args()
    out = Path(args.out)
    previous = json.loads(out.read_text()) if out.exists() else None
    data = build(previous)
    if not data["markets"]:
        raise SystemExit("no market data could be fetched; keeping the existing file")
    out.write_text(json.dumps(data, separators=(",", ":")))
    print(f"wrote {out} with {len(data['markets'])} markets, {len(data['failed'])} failed")


if __name__ == "__main__":
    main()
