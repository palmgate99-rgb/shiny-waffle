# Combined FX strategy backtest

A daily bar backtest of one rule set that combines trend following, carry, value, a news filter and an RSI pullback entry on six major currency pairs. This is a research tool. It is not financial advice and it places no orders.

## The rules

| Layer | Job | Rule |
|---|---|---|
| Trend | Direction | Long only when the close is above the 200 day average and the 12 month return is positive. Short only when both are reversed. |
| RSI | Entry | In an uptrend, buy at the next open after RSI(14) closes back above 40 from below. In a downtrend, sell after it closes back below 60 from above. |
| Carry | Size | Halve the risk when the trade pays overnight swap after the broker markup. |
| Value | Size | Halve the risk when the currency being bought is more than 20% overvalued. |
| Volatility | Size | Halve the risk when the 20 day average range is above 1.5 times its one year average. |
| News | Timing | No entry on the day of a major release. The entry moves to the next day if the trend still holds. |

Base risk is 1% of equity per trade. The stop starts 2 ATR(14) from entry and trails 3 ATR behind the best close. A close on the wrong side of the 200 day average exits at the next open. Total open risk is capped at 4%, no more than two positions may bet the same way on the US dollar, and a 6% loss within a calendar month blocks new entries until the next month. All of these numbers live in `Config` in `strategy.py`.

## Running it

It needs Python 3.10 or later with pandas and numpy. matplotlib is optional and adds an equity chart.

    python -m fx_strategy.download_data --out data      # free data from FRED
    python -m fx_strategy.run_backtest --data data --start 2000-01-01
    python -m fx_strategy.run_backtest --demo           # synthetic data, checks the code only
    python -m unittest fx_strategy.tests.test_strategy

The run prints summary statistics and writes `results/equity.csv` and `results/trades.csv`. The trade log records the size adjustments applied to each trade and the reason for each exit.

## Using your own data

Broker data is better than the free download because it has real highs and lows. The data folder is laid out like this.

| File | Contents |
|---|---|
| `prices/EURUSD.csv` | One file per pair with `date, open, high, low, close`. A file with only `date, close` also works. |
| `rates.csv` | `date` plus one column per currency holding an annual interest rate in percent. |
| `valuation.csv` | `date` plus one column per currency holding over or undervaluation as a fraction, so 0.25 means 25% overvalued. |
| `events.csv` | `date, currency` for each major scheduled release. |

Only prices are required. A rule whose data file is missing is not applied. Without `events.csv` the runner treats the first Friday of each month as the US payrolls date, which is an approximation and covers no inflation prints or central bank meetings.

## Result on free FRED data, 2000 to November 2026

| Measure | Value |
|---|---|
| Compound annual return | 1.0% |
| Annual volatility | 4.1% |
| Sharpe ratio, zero risk free rate | 0.27 |
| Worst drawdown | 11.3% |
| Trades | 380 |
| Winning trades | 33% |
| Average result per trade | 0.12 R |
| Profit factor | 1.22 |

A 10,000 dollar account ended at about 13,100 dollars after almost 27 years. The first year is a warm up with no trades. Tripling the spreads and the swap markup cut the return to 0.3% a year. Reversing every signal lost money, which is what a real but small edge should look like. The return was similar in both halves of the period.

## Limits you should know about

The FRED prices are one noon rate per day with no high or low. The loader estimates the daily range from close to close changes, assuming a random walk. The result is very sensitive to that estimate: with the range left out, the same rules showed 7.4% a year, which was an artefact of stops sitting too close and positions being too large. Treat the figures above as a rough guide until you rerun on real bars.

The valuation measure is the BIS real effective exchange rate against its own trailing ten year average, which stands in for a purchasing power parity gap. The interest rates are monthly three month interbank rates, and some of those series stop in early 2026, after which the last value is carried forward. Spreads and the swap markup are assumptions, not quotes from a broker. Slippage beyond the stop price is modelled only for opening gaps.

The thresholds (40 and 60 on RSI, 20% overvaluation, 1.5 times volatility) were chosen in advance from convention and were not tuned on this data. If you start tuning them to improve the result, hold back several years of data that you never optimise on.
