"""Rules and backtest engine for the combined FX strategy.

Every decision uses information available at the close of day t and is
executed at the open of day t+1, so the backtest cannot see the future.

Layers
------
1. Trend      direction: close vs 200 day average and sign of the 12 month return
2. Carry      size: halve the risk when the trade pays overnight swap
3. Value      size: halve the risk when the currency bought is over 20% overvalued
4. News       timing: no new entry on the day of a major scheduled release
5. RSI        trigger: pullback inside the trend (RSI 14 recrossing 40 or 60)
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

# Typical retail spreads in pips. These are assumptions, not quotes from any broker.
DEFAULT_SPREADS = {
    "EURUSD": 1.0, "GBPUSD": 1.5, "USDJPY": 1.2,
    "AUDUSD": 1.2, "USDCAD": 1.8, "NZDUSD": 2.0,
}


@dataclass
class Config:
    start_equity: float = 10_000.0
    # Layer 1: trend
    sma_days: int = 200
    momentum_days: int = 252
    # Layer 5: RSI pullback trigger
    rsi_days: int = 14
    rsi_long_level: float = 40.0
    rsi_short_level: float = 60.0
    # Risk and stops
    risk_per_trade: float = 0.01
    atr_days: int = 14
    stop_atr: float = 2.0
    trail_atr: float = 3.0
    # Sizing filters
    overvalued_limit: float = 0.20
    vol_fast_days: int = 20
    vol_slow_days: int = 252
    vol_spike_ratio: float = 1.5
    # Portfolio limits
    max_open_risk: float = 0.04
    max_same_usd_direction: int = 2
    monthly_loss_stop: float = 0.06
    # Costs
    spreads_pips: dict = field(default_factory=lambda: dict(DEFAULT_SPREADS))
    swap_markup_pct: float = 0.5  # annual broker markup charged on both long and short swaps


def pip_size(pair: str) -> float:
    return 0.01 if pair.endswith("JPY") else 0.0001


def rsi(close: pd.Series, days: int = 14) -> pd.Series:
    """Wilder's RSI."""
    change = close.diff()
    gain = change.clip(lower=0).ewm(alpha=1 / days, adjust=False, min_periods=days).mean()
    loss = (-change.clip(upper=0)).ewm(alpha=1 / days, adjust=False, min_periods=days).mean()
    out = 100 - 100 / (1 + gain / loss)
    return out.where(loss > 0, 100.0).where(gain.notna())


def true_range(df: pd.DataFrame) -> pd.Series:
    prev = df["close"].shift()
    return pd.concat(
        [df["high"] - df["low"], (df["high"] - prev).abs(), (df["low"] - prev).abs()], axis=1
    ).max(axis=1)


def add_indicators(df: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """Add trend, RSI, ATR and volatility columns to one pair's OHLC frame."""
    out = df.copy()
    tr = true_range(out)
    out["sma"] = out["close"].rolling(cfg.sma_days).mean()
    out["mom"] = out["close"].pct_change(cfg.momentum_days)
    out["rsi"] = rsi(out["close"], cfg.rsi_days)
    out["atr"] = tr.ewm(alpha=1 / cfg.atr_days, adjust=False, min_periods=cfg.atr_days).mean()
    fast = tr.rolling(cfg.vol_fast_days).mean()
    out["vol_ratio"] = fast / fast.rolling(cfg.vol_slow_days).mean()
    up = (out["close"] > out["sma"]) & (out["mom"] > 0)
    down = (out["close"] < out["sma"]) & (out["mom"] < 0)
    out["trend"] = np.where(up, 1, np.where(down, -1, 0))
    prev_rsi = out["rsi"].shift()
    long_trigger = (prev_rsi < cfg.rsi_long_level) & (out["rsi"] >= cfg.rsi_long_level)
    short_trigger = (prev_rsi > cfg.rsi_short_level) & (out["rsi"] <= cfg.rsi_short_level)
    out["signal"] = np.where(up & long_trigger, 1, np.where(down & short_trigger, -1, 0))
    return out


def risk_adjustment(cfg: Config, carry: float, bought_valuation: float, vol_ratio: float):
    """Layers 2 and 3 plus the volatility filter, shared by the backtest and the dashboard.

    carry is the annual percent the trade earns after the broker markup. Any input
    may be NaN, which means the data is missing and that adjustment is skipped.
    """
    mult, notes = 1.0, []
    if carry < 0:
        mult *= 0.5
        notes.append("pays swap")
    if bought_valuation > cfg.overvalued_limit:
        mult *= 0.5
        notes.append("overvalued")
    if vol_ratio > cfg.vol_spike_ratio:
        mult *= 0.5
        notes.append("vol spike")
    return mult, notes


@dataclass
class Position:
    pair: str
    direction: int
    units: float          # units of the base currency
    entry_date: pd.Timestamp
    entry_price: float
    stop: float
    risk_usd: float
    risk_frac: float
    best_close: float
    swap_usd: float = 0.0
    exit_at_open: bool = False
    notes: str = ""


class Backtest:
    """Bar by bar portfolio backtest with a USD account. Works on daily or intraday bars.

    prices     dict of pair -> DataFrame indexed by date with open, high, low, close
    rates      DataFrame of annual interest rates in percent, one column per currency
    valuation  DataFrame of over or undervaluation as a fraction (0.25 = 25% overvalued)
    events     DataFrame with columns date and currency for major scheduled releases
    """

    def __init__(self, prices, rates=None, valuation=None, events=None, cfg: Config | None = None):
        self.cfg = cfg or Config()
        self.pairs = sorted(prices)
        for pair in self.pairs:
            if "USD" not in (pair[:3], pair[3:]):
                raise ValueError(f"{pair}: only pairs that include USD are supported")
        self.ind = {p: add_indicators(prices[p].sort_index(), self.cfg) for p in self.pairs}
        self.dates = sorted(set().union(*[df.index for df in self.ind.values()]))
        idx = pd.DatetimeIndex(self.dates)
        self.rates = None if rates is None else rates.sort_index().reindex(idx, method="ffill")
        self.valuation = None if valuation is None else valuation.sort_index().reindex(idx, method="ffill")
        self.events = set()
        if events is not None:
            self.events = {(pd.Timestamp(d).normalize(), c) for d, c in zip(events["date"], events["currency"])}

    # ----- helpers -------------------------------------------------------
    def _usd_value(self, pair, units, price_move, price):
        """Convert a price move on `units` of base currency into USD."""
        return units * price_move if pair.endswith("USD") else units * price_move / price

    def _lookup(self, table, date, currency):
        if table is None or currency not in table.columns:
            return np.nan
        return table.at[date, currency]

    def _carry(self, pair, direction, date):
        """Annual percent earned (positive) or paid (negative) for holding the trade."""
        base = self._lookup(self.rates, date, pair[:3])
        quote = self._lookup(self.rates, date, pair[3:])
        if np.isnan(base) or np.isnan(quote):
            return np.nan
        return direction * (base - quote) - self.cfg.swap_markup_pct

    def _is_event_day(self, pair, date):
        day = date.normalize()
        return (day, pair[:3]) in self.events or (day, pair[3:]) in self.events

    def risk_multiplier(self, pair, direction, date, vol_ratio):
        """Layers 2 and 3 plus the volatility filter. Missing data means no adjustment."""
        bought = pair[:3] if direction == 1 else pair[3:]
        return risk_adjustment(self.cfg, self._carry(pair, direction, date),
                               self._lookup(self.valuation, date, bought), vol_ratio)

    def _close(self, pos, date, raw_price, reason):
        half_spread = self.cfg.spreads_pips.get(pos.pair, 2.0) * pip_size(pos.pair) / 2
        price = raw_price - pos.direction * half_spread
        pnl = self._usd_value(pos.pair, pos.units, pos.direction * (price - pos.entry_price), price)
        pnl += pos.swap_usd
        self.balance += pnl
        self.trades.append({
            "pair": pos.pair, "direction": "long" if pos.direction == 1 else "short",
            "entry_date": pos.entry_date, "exit_date": date,
            "entry_price": pos.entry_price, "exit_price": price, "units": pos.units,
            "risk_usd": pos.risk_usd, "swap_usd": pos.swap_usd, "pnl_usd": pnl,
            "r_multiple": pnl / pos.risk_usd, "exit_reason": reason, "size_notes": pos.notes,
        })
        del self.open[pos.pair]

    # ----- main loop -----------------------------------------------------
    def run(self):
        cfg = self.cfg
        self.balance = cfg.start_equity
        self.open: dict[str, Position] = {}
        self.trades: list[dict] = []
        self.skipped = {"open risk limit": 0, "USD direction limit": 0, "monthly loss stop": 0,
                        "deferred for news": 0, "dropped after news": 0}
        pending: dict[str, int] = {}
        last_close: dict[str, float] = {}
        equity = cfg.start_equity
        month, month_start_equity, month_blocked = None, equity, False
        prev_date, prev_bar = None, {}
        curve = []

        for date in self.dates:
            if (date.year, date.month) != month:
                month, month_start_equity, month_blocked = (date.year, date.month), equity, False
            bars = {p: self.ind[p].loc[date] for p in self.pairs if date in self.ind[p].index}
            days = 0 if prev_date is None else (date - prev_date).total_seconds() / 86400

            # 1. Exits flagged at the previous close are filled at today's open.
            for pair, pos in list(self.open.items()):
                if pair in bars and pos.exit_at_open:
                    self._close(pos, date, bars[pair]["open"], "trend exit")

            # 2. Entries queued at the previous close.
            for pair, direction in list(pending.items()):
                if pair not in bars:
                    continue
                if self._is_event_day(pair, date):
                    self.skipped["deferred for news"] += 1
                    continue  # re-checked at tonight's close
                del pending[pair]
                signal_bar = prev_bar[pair]
                if month_blocked:
                    self.skipped["monthly loss stop"] += 1
                    continue
                usd_dir = direction if pair.startswith("USD") else -direction
                same = sum(1 for p in self.open.values()
                           if (p.direction if p.pair.startswith("USD") else -p.direction) == usd_dir)
                if same >= cfg.max_same_usd_direction:
                    self.skipped["USD direction limit"] += 1
                    continue
                mult, notes = self.risk_multiplier(pair, direction, prev_date, signal_bar["vol_ratio"])
                risk_frac = cfg.risk_per_trade * mult
                if sum(p.risk_frac for p in self.open.values()) + risk_frac > cfg.max_open_risk + 1e-12:
                    self.skipped["open risk limit"] += 1
                    continue
                half_spread = cfg.spreads_pips.get(pair, 2.0) * pip_size(pair) / 2
                entry = bars[pair]["open"] + direction * half_spread
                stop_dist = cfg.stop_atr * signal_bar["atr"]
                risk_usd = equity * risk_frac
                units = risk_usd / stop_dist if pair.endswith("USD") else risk_usd * entry / stop_dist
                pos = Position(pair, direction, units, date, entry, entry - direction * stop_dist,
                               risk_usd, risk_frac, best_close=entry, notes=", ".join(notes))
                self.open[pair] = pos

            # 3. Stops, checked against today's range. Gaps are filled at the open.
            for pair, pos in list(self.open.items()):
                if pair not in bars:
                    continue
                bar = bars[pair]
                if pos.direction == 1 and bar["low"] <= pos.stop:
                    self._close(pos, date, min(bar["open"], pos.stop), "stop")
                elif pos.direction == -1 and bar["high"] >= pos.stop:
                    self._close(pos, date, max(bar["open"], pos.stop), "stop")

            # 4. Overnight swap for the calendar days since the previous bar.
            for pair, pos in self.open.items():
                carry = self._carry(pair, pos.direction, date)
                if days and not np.isnan(carry) and pos.entry_date < date:
                    notional = pos.units * last_close.get(pair, pos.entry_price) if pair.endswith("USD") else pos.units
                    pos.swap_usd += notional * carry / 100 * days / 360

            # 5. End of day: trail stops, flag trend exits, read new signals.
            for pair, bar in bars.items():
                last_close[pair] = bar["close"]
                pos = self.open.get(pair)
                if pos:
                    if pos.direction == 1:
                        pos.best_close = max(pos.best_close, bar["close"])
                        pos.stop = max(pos.stop, pos.best_close - cfg.trail_atr * bar["atr"])
                        pos.exit_at_open = bar["close"] < bar["sma"]
                    else:
                        pos.best_close = min(pos.best_close, bar["close"])
                        pos.stop = min(pos.stop, pos.best_close + cfg.trail_atr * bar["atr"])
                        pos.exit_at_open = bar["close"] > bar["sma"]
                elif pair in pending:
                    if bar["trend"] != pending[pair]:  # setup no longer holds after the release
                        del pending[pair]
                        self.skipped["dropped after news"] += 1
                elif bar["signal"] != 0:
                    pending[pair] = int(bar["signal"])
                prev_bar[pair] = bar

            unrealised = sum(
                self._usd_value(p.pair, p.units, p.direction * (last_close[p.pair] - p.entry_price),
                                last_close[p.pair]) + p.swap_usd
                for p in self.open.values() if p.pair in last_close)
            equity = self.balance + unrealised
            if equity / month_start_equity - 1 <= -cfg.monthly_loss_stop:
                month_blocked = True
            curve.append((date, equity, len(self.open)))
            prev_date = date

        self.equity = pd.DataFrame(curve, columns=["date", "equity", "open_positions"]).set_index("date")
        self.trade_log = pd.DataFrame(self.trades)
        return self


def performance(equity: pd.Series, trades: pd.DataFrame) -> dict:
    """Summary statistics. Sharpe uses daily returns with a zero risk free rate."""
    equity = equity.resample("1D").last().dropna()  # intraday curves are measured once a day
    daily = equity.pct_change().dropna()
    years = max((equity.index[-1] - equity.index[0]).days / 365.25, 1e-9)
    drawdown = equity / equity.cummax() - 1
    out = {
        "start": equity.index[0].date(), "end": equity.index[-1].date(),
        "final_equity": round(float(equity.iloc[-1]), 2),
        "cagr_pct": round(((equity.iloc[-1] / equity.iloc[0]) ** (1 / years) - 1) * 100, 2),
        "annual_vol_pct": round(daily.std() * np.sqrt(252) * 100, 2),
        "sharpe": round(daily.mean() / daily.std() * np.sqrt(252), 2) if daily.std() > 0 else 0.0,
        "max_drawdown_pct": round(drawdown.min() * 100, 2),
        "trades": len(trades),
    }
    if len(trades):
        wins = trades.loc[trades["pnl_usd"] > 0, "pnl_usd"]
        losses = trades.loc[trades["pnl_usd"] <= 0, "pnl_usd"]
        out.update({
            "win_rate_pct": round(len(wins) / len(trades) * 100, 1),
            "avg_r": round(trades["r_multiple"].mean(), 3),
            "profit_factor": round(wins.sum() / -losses.sum(), 2) if losses.sum() < 0 else float("inf"),
            "swap_usd": round(trades["swap_usd"].sum(), 2),
        })
    return out
