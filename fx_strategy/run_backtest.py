"""Run the backtest and write the results.

    python -m fx_strategy.run_backtest --demo            synthetic data, checks the code only
    python -m fx_strategy.run_backtest --data data       real data from a folder
    python -m fx_strategy.run_backtest --yahoo 1h --macro data    intraday candles from Yahoo
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from .data import first_friday_events, load_folder, synthetic
from .strategy import Backtest, Config, performance


def main():
    parser = argparse.ArgumentParser(description="Backtest the combined FX strategy")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--data", help="folder with prices/, rates.csv, valuation.csv, events.csv")
    source.add_argument("--demo", action="store_true", help="use synthetic data")
    source.add_argument("--yahoo", choices=["15m", "1h", "4h"],
                        help="intraday Yahoo candles for the six USD majors (about 60 days of 15m, 2 years of 1h and 4h)")
    parser.add_argument("--macro", help="folder holding rates.csv and valuation.csv, used with --yahoo")
    parser.add_argument("--out", default="results")
    parser.add_argument("--equity", type=float, default=10_000)
    parser.add_argument("--start", help="first date to trade, for example 2005-01-01")
    args = parser.parse_args()

    if args.demo:
        prices, rates, valuation, events = synthetic()
        print("SYNTHETIC DATA: these numbers only show that the code runs.\n")
    elif args.yahoo:
        from . import yahoo
        from .data import PAIRS, _read
        prices = {p: yahoo.candles(p + "=X")[0][args.yahoo] for p in PAIRS}
        folder = Path(args.macro) if args.macro else None
        rates = _read(folder / "rates.csv") if folder else None
        valuation = _read(folder / "valuation.csv") if folder else None
        events = first_friday_events(min(d.index[0] for d in prices.values()),
                                     max(d.index[-1] for d in prices.values()))
    else:
        prices, rates, valuation, events = load_folder(args.data)
        if events is None:
            first = min(df.index[0] for df in prices.values())
            last = max(df.index[-1] for df in prices.values())
            events = first_friday_events(first, last)
            print("No events.csv found: using first Friday of each month as US payrolls dates.\n")
    if args.start:
        prices = {p: df.loc[args.start:] for p, df in prices.items()}

    bt = Backtest(prices, rates, valuation, events, Config(start_equity=args.equity)).run()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    bt.equity.to_csv(out / "equity.csv")
    bt.trade_log.to_csv(out / "trades.csv", index=False)

    for key, value in performance(bt.equity["equity"], bt.trade_log).items():
        print(f"{key:>18}: {value}")
    print("\nSignals not taken:")
    for key, value in bt.skipped.items():
        print(f"{key:>18}: {value}")
    if len(bt.trade_log):
        by_pair = bt.trade_log.groupby("pair")["pnl_usd"].agg(["count", "sum"]).round(2)
        print("\nProfit and loss by pair (USD):\n" + by_pair.to_string())
        yearly = bt.equity["equity"].groupby(bt.equity.index.year).last().pct_change().mul(100).round(1)
        print("\nReturn by calendar year (%):\n" + yearly.dropna().to_string())
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        ax = bt.equity["equity"].plot(figsize=(10, 4), title="Account equity (USD)")
        ax.figure.savefig(out / "equity.png", dpi=150, bbox_inches="tight")
        plt.close(ax.figure)
    except ImportError:
        pass
    print(f"\nSaved equity.csv and trades.csv to {out}/")


if __name__ == "__main__":
    main()
