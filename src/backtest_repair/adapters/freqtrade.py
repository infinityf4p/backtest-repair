"""IStrategy through the original Backtesting engine, with offline CCXT metadata."""

from pathlib import Path
from .common import entry, frame, settings, bar_key
from ..contracts import ContractError


def offline_environment(spec, cls):
    import ccxt
    from freqtrade.enums import RunMode, TradingMode, CandleType
    from freqtrade.exchange import Exchange

    cfg, pair = settings(), spec["clock"]["instrument"]
    base, quote = pair.split("/")
    config = {
        "strategy": cls.__name__,
        "strategy_path": str(Path.cwd()),
        "user_data_dir": Path.cwd(),
        "datadir": Path("fixtures"),
        "timeframe": spec["clock"]["frequency"],
        "max_open_trades": 1,
        "stake_currency": quote,
        "stake_amount": spec["position"]["stake"],
        "dry_run": True,
        "dry_run_wallet": spec["position"]["initial_cash"],
        "tradable_balance_ratio": 1.0,
        "runmode": RunMode.BACKTEST,
        "trading_mode": TradingMode.SPOT,
        "candle_type_def": CandleType.SPOT,
        "fee": cfg.get("fee_rate", spec["costs"]["fee_rate"]),
        "dataformat_ohlcv": "json",
        "exchange": {
            "name": "binance",
            "key": "",
            "secret": "",
            "pair_whitelist": [pair],
            "pair_blacklist": [],
            "enable_ws": False,
        },
        "pairlists": [{"method": "StaticPairList", "allow_inactive": True}],
        "entry_pricing": {"price_side": "other", "use_order_book": False},
        "exit_pricing": {"price_side": "other", "use_order_book": False},
        "unfilledtimeout": {"entry": 10, "exit": 10, "unit": "minutes"},
        "export": "none",
        "internals": {},
    }
    exchange = Exchange(config, validate=False)
    # Only exchange metadata is replaced; no broker, wallet, sizing or matching code is replaced.
    market = {
        "id": base + quote,
        "symbol": pair,
        "base": base,
        "quote": quote,
        "baseId": base,
        "quoteId": quote,
        "active": True,
        "spot": True,
        "type": "spot",
        "swap": False,
        "future": False,
        "contract": False,
        "precision": {
            "amount": 10 ** -spec["position"]["amount_decimals"],
            "price": spec["position"]["price_tick"],
        },
        "limits": {
            "amount": {"min": 0.000001, "max": 1e12},
            "cost": {"min": 1.0, "max": 1e12},
            "price": {"min": spec["position"]["price_tick"]},
        },
        "maker": spec["costs"]["fee_rate"],
        "taker": spec["costs"]["fee_rate"],
        "info": {},
    }
    exchange._markets = {pair: market}
    for api in [exchange._api, exchange._api_async]:
        api.precisionMode = ccxt.TICK_SIZE
        api.set_markets([market])
    return config, exchange


def run(spec, bars, rec):
    from freqtrade.optimize.backtesting import Backtesting
    from freqtrade.persistence import LocalTrade
    from freqtrade.strategy import IStrategy

    cls = entry(spec)
    if not isinstance(cls, type) or not issubclass(cls, IStrategy):
        raise ContractError(
            "entrypoint must inherit freqtrade.strategy.IStrategy", "out_of_scope"
        )
    for name in (
        "trailing_stop",
        "use_custom_stoploss",
        "position_adjustment_enable",
        "can_short",
    ):
        if getattr(cls, name, False):
            raise ContractError(
                "Freqtrade profile does not support " + name, "out_of_scope"
            )
    for name in (
        "custom_exit",
        "custom_entry_price",
        "custom_exit_price",
        "adjust_trade_position",
        "custom_roi",
    ):
        if getattr(cls, name, None) is not getattr(IStrategy, name, None):
            raise ContractError(
                "Freqtrade profile does not support callback " + name, "out_of_scope"
            )
    config, exchange = offline_environment(spec, cls)
    pair = spec["clock"]["instrument"]
    quote = pair.split("/")[1]
    fills, seen_orders = [], set()

    class Observe(Backtesting):
        def _try_close_open_order(self, order, trade, current_date, row):
            if order is None:
                return super()._try_close_open_order(order, trade, current_date, row)
            i = rec.index[bar_key(current_date, spec)]
            if order.order_id not in seen_orders:
                seen_orders.add(order.order_id)
                rec.add(
                    "order",
                    i,
                    "open",
                    "freqtrade.persistence.Order",
                    order_id=order.order_id,
                    qty=float(
                        order.amount * (1 if order.ft_order_side == "buy" else -1)
                    ),
                    order_type=order.order_type,
                    status=order.status,
                )
            was_open = order.ft_is_open
            result = super()._try_close_open_order(order, trade, current_date, row)
            if was_open and not order.ft_is_open and order.filled:
                q = float(order.filled * (1 if order.ft_order_side == "buy" else -1))
                p = float(order.average or order.price)
                fee = abs(q) * p * (trade.fee_open if q > 0 else trade.fee_close)
                item = {"session": bars[i]["date"], "qty": q, "price": p, "fee": fee}
                fills.append(item)
                reason = trade.exit_reason if q < 0 else "entry"
                phase = "match" if reason in {"roi", "stop_loss"} else "open"
                rec.add(
                    "fill",
                    i,
                    phase,
                    "freqtrade.Backtesting._try_close_open_order",
                    provenance={"fee": "derived"},
                    order_id=order.order_id,
                    exit_reason=reason,
                    open_rate=float(trade.open_rate),
                    open_date=trade.open_date.isoformat(),
                    stop_loss=float(trade.stop_loss),
                    **{k: v for k, v in item.items() if k != "session"},
                )
            return result

        def backtest_loop(self, row, pair, current_time, trade_dir, can_enter):
            result = super().backtest_loop(
                row, pair, current_time, trade_dir, can_enter
            )
            i = rec.index[bar_key(current_time, spec)]
            self.wallets.update()
            qty = float(
                sum(t.amount for t in LocalTrade.bt_trades_open if t.has_open_position)
            )
            # Freqtrade dry wallet reserves stake; its open fee is booked into profit on exit.
            # Record that native basis separately, derive economically equivalent spot cash.
            native_wallet = float(self.wallets.get_total(quote))
            open_fees = sum(
                t.amount * t.open_rate * t.fee_open
                for t in LocalTrade.bt_trades_open
                if t.has_open_position
            )
            cash = native_wallet - open_fees
            rec.add(
                "account",
                i,
                "close",
                "freqtrade.Wallets + fill cash reconciliation",
                provenance={"cash": "derived", "equity": "derived"},
                cash=cash,
                position=qty,
                equity=cash + qty * bars[i]["close"],
                native_wallet=native_wallet,
            )
            return result

    engine = Observe(config, exchange=exchange)
    try:
        engine._set_strategy(engine.strategylist[0])
        strategy = engine.strategy
        exit_rules = {
            "minimal_roi": {str(k): float(v) for k, v in strategy.minimal_roi.items()},
            "stoploss": float(strategy.stoploss),
            "use_exit_signal": bool(strategy.use_exit_signal),
        }
        rec.add(
            "execution_config",
            0,
            "open",
            "freqtrade.StrategyResolver",
            exit_rules=exit_rules,
        )
        original = strategy.ft_advise_signals

        def observe_signals(dataframe, metadata):
            result = original(dataframe, metadata)
            for _, row in result.iterrows():
                i = rec.index[bar_key(row["date"], spec)]
                rec.add(
                    "signal",
                    i,
                    "close",
                    "freqtrade.IStrategy.ft_advise_signals",
                    signal=float(row.get("enter_long", 0)) if row.get("enter_long", 0) == 1 else 0.0,
                    exit_signal=float(row.get("exit_long", 0)) if row.get("exit_long", 0) == 1 else 0.0,
                )
            return result

        strategy.ft_advise_signals = observe_signals
        data = frame(bars, utc=True).reset_index().rename(columns={"index": "date"})
        processed = strategy.advise_all_indicators({pair: data})
        # Observe computed features for causal-prefix testing, including cases where
        # a biased indicator does not change an entry/exit on this market sample.
        import math
        observed_indicators = []
        for _, row in processed[pair].iterrows():
            features = {}
            for name in spec.get("indicator_columns", []):
                val = row.get(name)
                features[name] = float(val) if val is not None and math.isfinite(float(val)) else None
            observed_indicators.append({"session": bar_key(row["date"], spec), "values": features})
        result = engine.backtest(
            processed,
            data.iloc[0]["date"].to_pydatetime(),
            data.iloc[-1]["date"].to_pydatetime(),
        )
        rec.add(
            "account",
            len(bars) - 1,
            "finalize",
            "freqtrade.Backtesting.final_balance",
            cash=float(result["final_balance"]),
            equity=float(result["final_balance"]),
            position=float(
                sum(t.amount for t in LocalTrade.bt_trades_open if t.has_open_position)
            ),
        )
        # Exit fills are handled through _process_exit_order, not necessarily through entry matching hooks.
        native_trades = []
        for t in LocalTrade.bt_trades:
            native_trades.append(
                {
                    "entry": t.open_date.isoformat(),
                    "exit": t.close_date.isoformat() if t.close_date else None,
                    "amount": float(t.amount),
                    "open_rate": float(t.open_rate),
                    "close_rate": float(t.close_rate) if t.close_rate else None,
                    "fee_open": float(t.fee_open),
                    "fee_close": float(t.fee_close),
                    "exit_reason": t.exit_reason,
                }
            )
        return {
            "equity": float(result["final_balance"]),
            "cash": float(result["final_balance"]),
            "position": 0.0,
            "fills": fills,
            "trades": native_trades,
            "trade_count": len(result["results"]),
            "indicators": observed_indicators,
            "exit_rules": exit_rules,
        }
    finally:
        engine.cleanup()
        exchange.close()
