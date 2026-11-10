import unittest

import numpy as np
import pandas as pd

from fx_strategy.data import fill_ohlc, first_friday_events, synthetic
from fx_strategy.strategy import Backtest, Config, add_indicators, rsi


def frame(closes, start="2020-01-01"):
    idx = pd.bdate_range(start, periods=len(closes))
    return fill_ohlc(pd.DataFrame({"close": np.asarray(closes, dtype=float)}, index=idx))


def uptrend_with_dip(n=400, dip_at=350):
    """Steady rise, then a sharp three day dip and recovery that fires a long signal."""
    closes = list(1.0 + 0.001 * np.arange(n))
    for k, drop in enumerate([0.012, 0.024, 0.034]):
        closes[dip_at + k] -= drop
    return closes


class Indicators(unittest.TestCase):
    def test_rsi_bounds_and_extremes(self):
        up = pd.Series(np.arange(1, 60, dtype=float))
        self.assertEqual(rsi(up).iloc[-1], 100.0)
        noisy = pd.Series(np.cumsum(np.random.default_rng(1).normal(0, 1, 500)) + 100)
        values = rsi(noisy).dropna()
        self.assertTrue(((values >= 0) & (values <= 100)).all())

    def test_no_direction_when_trend_filters_disagree(self):
        closes = list(np.linspace(2.0, 1.0, 300)) + list(np.linspace(1.0, 1.3, 60))
        ind = add_indicators(frame(closes), Config())
        last = ind.iloc[-1]
        self.assertGreater(last["close"], last["sma"])  # above the average
        self.assertLess(last["mom"], 0)                 # but down over twelve months
        self.assertEqual(last["trend"], 0)

    def test_long_signal_only_on_rsi_recross_in_uptrend(self):
        ind = add_indicators(frame(uptrend_with_dip()), Config())
        signals = ind.index[ind["signal"] == 1]
        self.assertEqual(len(signals), 1)
        day = ind.index.get_loc(signals[0])
        self.assertLess(ind["rsi"].iloc[day - 1], 40)
        self.assertGreaterEqual(ind["rsi"].iloc[day], 40)


def quiet(**kwargs):
    """Config with the volatility filter off, because the test dip is itself a volatility spike."""
    return Config(vol_spike_ratio=float("inf"), **kwargs)


class Engine(unittest.TestCase):
    def run_one(self, pair="EURUSD", **kwargs):
        cfg = kwargs.pop("cfg", quiet(spreads_pips={}))
        return Backtest({pair: frame(uptrend_with_dip())}, cfg=cfg, **kwargs).run()

    def test_entry_is_at_the_open_after_the_signal(self):
        bt = self.run_one()
        ind = bt.ind["EURUSD"]
        signal_day = ind.index[ind["signal"] == 1][0]
        trade = bt.trade_log.iloc[0] if len(bt.trade_log) else None
        pos = bt.open.get("EURUSD")
        entry_date = pos.entry_date if pos else trade["entry_date"]
        self.assertEqual(entry_date, ind.index[ind.index.get_loc(signal_day) + 1])

    def test_position_size_risks_one_percent_at_the_stop(self):
        cfg = quiet(spreads_pips={"EURUSD": 0.0})
        bt = self.run_one(cfg=cfg)
        pos = bt.open["EURUSD"]
        self.assertAlmostEqual(pos.risk_usd, 100.0, places=6)
        initial_stop = pos.entry_price - cfg.stop_atr * bt.ind["EURUSD"]["atr"].loc[:pos.entry_date].iloc[-2]
        self.assertAlmostEqual(pos.units * (pos.entry_price - initial_stop), 100.0, places=6)

    def test_negative_carry_and_overvaluation_each_halve_risk(self):
        idx = pd.DatetimeIndex(["2019-01-01"])
        rates = pd.DataFrame({"EUR": [0.0], "USD": [5.0]}, index=idx)
        valuation = pd.DataFrame({"EUR": [0.30], "USD": [0.0]}, index=idx)
        self.assertAlmostEqual(self.run_one(rates=rates).open["EURUSD"].risk_frac, 0.005)
        both = self.run_one(rates=rates, valuation=valuation).open["EURUSD"]
        self.assertAlmostEqual(both.risk_frac, 0.0025)
        self.assertEqual(both.notes, "pays swap, overvalued")

    def test_volatility_spike_halves_risk(self):
        pos = self.run_one(cfg=Config(spreads_pips={})).open["EURUSD"]
        self.assertAlmostEqual(pos.risk_frac, 0.005)
        self.assertEqual(pos.notes, "vol spike")

    def test_entry_waits_for_the_news_day_to_pass(self):
        plain = self.run_one()
        entry = plain.open["EURUSD"].entry_date
        events = pd.DataFrame({"date": [entry], "currency": ["USD"]})
        delayed = self.run_one(events=events)
        self.assertEqual(delayed.skipped["deferred for news"], 1)
        self.assertEqual(delayed.open["EURUSD"].entry_date, entry + pd.offsets.BDay(1))

    def test_stop_closes_the_trade_for_about_minus_one_r(self):
        closes = uptrend_with_dip()
        closes[356:] = [closes[355] - 0.03 * (k + 1) for k in range(len(closes) - 356)]
        bt = Backtest({"EURUSD": frame(closes)}, cfg=Config(spreads_pips={"EURUSD": 0.0})).run()
        first = bt.trade_log.iloc[0]
        self.assertEqual(first["exit_reason"], "stop")
        self.assertLess(first["r_multiple"], 0)
        self.assertAlmostEqual(bt.equity["equity"].iloc[-1], 10_000 + bt.trade_log["pnl_usd"].sum(), places=6)

    def test_usd_direction_limit(self):
        closes = uptrend_with_dip()
        prices = {p: frame(closes) for p in ["EURUSD", "GBPUSD", "AUDUSD"]}
        bt = Backtest(prices, cfg=Config()).run()
        self.assertEqual(len(bt.open), 2)
        self.assertEqual(bt.skipped["USD direction limit"], 1)

    def test_usd_base_pair_sizing(self):
        closes = [100 * c for c in uptrend_with_dip()]
        bt = Backtest({"USDJPY": frame(closes)}, cfg=quiet(spreads_pips={"USDJPY": 0.0})).run()
        pos = bt.open["USDJPY"]
        stop_dist = 2 * bt.ind["USDJPY"]["atr"].loc[:pos.entry_date].iloc[-2]
        self.assertAlmostEqual(pos.units * stop_dist / pos.entry_price, 100.0, places=6)

    def test_synthetic_run_is_consistent(self):
        prices, rates, valuation, events = synthetic(years=6)
        bt = Backtest(prices, rates, valuation, events).run()
        self.assertGreater(len(bt.trade_log), 10)
        self.assertTrue((bt.equity["open_positions"] <= 4).all())
        self.assertTrue((bt.trade_log["entry_date"] < bt.trade_log["exit_date"]).mean() > 0.9)


class Intraday(unittest.TestCase):
    def hourly(self, n=600):
        idx = pd.date_range("2026-03-02", periods=n, freq="h")
        closes = uptrend_with_dip(n=n, dip_at=500)
        return fill_ohlc(pd.DataFrame({"close": closes}, index=idx))

    def test_unfinished_bar_is_dropped(self):
        from fx_strategy import yahoo
        df = self.hourly().iloc[:5]
        now = df.index[-1] + pd.Timedelta(minutes=20)
        self.assertEqual(len(yahoo.closed_bars(df, "1h", now)), 4)
        self.assertEqual(len(yahoo.to_4h(df)), 2)

    def test_engine_runs_on_hourly_bars(self):
        bt = Backtest({"EURUSD": self.hourly()}, cfg=quiet(spreads_pips={})).run()
        ind = bt.ind["EURUSD"]
        signal_at = ind.index[ind["signal"] == 1][0]
        self.assertEqual(bt.open["EURUSD"].entry_date, signal_at + pd.Timedelta(hours=1))

    def test_dashboard_reading_matches_the_rules(self):
        from fx_strategy.export_dashboard import reading
        df = self.hourly()
        signal_at = add_indicators(df, Config()).query("signal == 1").index[0]
        macro = {"rates": {"EUR": 1.0, "USD": 4.0}, "valuation": {"EUR": 0.3, "USD": 0.0}}
        r = reading(Config(), "EUR/USD", df.loc[:signal_at], macro)
        self.assertEqual((r["trend"], r["signal"], r["signal_age"]), (1, 1, 0))
        self.assertEqual(r["long"]["notes"], ["pays swap", "overvalued", "vol spike"])
        self.assertEqual(r["long"]["mult"], 0.125)
        self.assertEqual(len(r["candles"]), 80)
        stock = reading(Config(), "AAPL", df.loc[:signal_at], macro)
        self.assertEqual(stock["long"]["notes"], ["vol spike"])


class Calendar(unittest.TestCase):
    def test_first_fridays(self):
        events = first_friday_events("2024-01-01", "2024-03-31")
        self.assertEqual([d.strftime("%Y-%m-%d") for d in events["date"]],
                         ["2024-01-05", "2024-02-02", "2024-03-01"])


if __name__ == "__main__":
    unittest.main()
