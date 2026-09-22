from datetime import datetime, timedelta
from pathlib import Path
from ..contracts import ContractError, read_bars
from .common import entry, settings, bar_key


def run(spec, bars, rec):
    from vnpy.trader.constant import Direction, Exchange, Interval
    from vnpy.trader.object import BarData
    from vnpy_ctastrategy import CtaTemplate
    from vnpy_ctastrategy.backtesting import BacktestingEngine

    cls = entry(spec)
    if not isinstance(cls, type) or not issubclass(cls, CtaTemplate):
        raise ValueError("entrypoint must inherit vnpy_ctastrategy.CtaTemplate")
    cfg, fills, stop_origins = settings(), [], {}

    class Observe(cls):
        def on_bar(self, bar):
            super().on_bar(bar)
            day = bar_key(bar.datetime, spec)
            if day in rec.index:
                rec.decision(self, rec.index[day], "vnpy.CtaTemplate.on_bar")

        def on_order(self, order):
            rec.add(
                "order_status",
                rec.index[bar_key(engine.datetime, spec)],
                "match",
                "vnpy.CtaTemplate.on_order",
                order_id=order.vt_orderid,
                status=order.status.value,
            )
            super().on_order(order)

        def on_stop_order(self, order):
            for native_id in order.vt_orderids:
                stop_origins[native_id] = order.stop_orderid
            rec.add(
                "stop_status",
                rec.index[bar_key(engine.datetime, spec)],
                "match",
                "vnpy.CtaTemplate.on_stop_order",
                order_id=order.stop_orderid,
                native_order_ids=list(order.vt_orderids),
                status=order.status.value,
            )
            super().on_stop_order(order)

        def on_trade(self, trade):
            i = rec.index[bar_key(trade.datetime, spec)]
            q = trade.volume * (1 if trade.direction == Direction.LONG else -1)
            rec.add(
                "fill",
                i,
                "match",
                "vnpy.CtaTemplate.on_trade",
                provenance={"fee": "derived"},
                order_id=stop_origins.get(trade.vt_orderid, trade.vt_orderid),
                native_order_id=trade.vt_orderid,
                qty=float(q),
                price=float(trade.price),
                fee=float(abs(q) * trade.price * engine.size * engine.rate),
                offset=trade.offset.value,
                multiplier=float(engine.size),
                native_timestamp=trade.datetime.isoformat(),
            )
            super().on_trade(trade)

    class Engine(BacktestingEngine):
        def send_order(
            self, strategy, direction, offset, price, volume, stop, lock, net
        ):
            ids = super().send_order(
                strategy, direction, offset, price, volume, stop, lock, net
            )
            for oid in ids:
                rec.add(
                    "order",
                    rec.index[bar_key(self.datetime, spec)],
                    "close",
                    "vnpy.BacktestingEngine.send_order",
                    order_id=oid,
                    qty=float(volume * (1 if direction == Direction.LONG else -1)),
                    price=float(price),
                    order_type="stop" if stop else "limit",
                    status="submitted",
                    offset=offset.value,
                )
            return ids

        def load_bar(self, vt_symbol, days, interval, callback, use_database):
            # Native CtaTemplate feeds these bars to the requested callback while
            # trading is disabled. Never silently substitute empty DB history.
            if interval != native_interval or vt_symbol != instrument:
                raise ContractError(
                    "CTA warmup must use the declared daily instrument", "out_of_scope"
                )
            warmup = Path("fixtures/warmup.csv")
            if not warmup.exists():
                raise ContractError(
                    "CTA on_init.load_bar requires fixtures/warmup.csv before the first evaluation session"
                )
            rows = read_bars(warmup)
            if rows[-1]["date"] >= bars[0]["date"]:
                raise ContractError(
                    "CTA initialization bars must precede the evaluation calendar"
                )
            return [
                BarData(
                    symbol=symbol,
                    exchange=Exchange(exchange),
                    datetime=datetime.fromisoformat(b["date"]),
                    interval=native_interval,
                    volume=b["volume"],
                    open_price=b["open"],
                    high_price=b["high"],
                    low_price=b["low"],
                    close_price=b["close"],
                    gateway_name="FIXTURE",
                )
                for b in rows
                if datetime.fromisoformat(b["date"])
                >= self.start - timedelta(days=days)
            ]

    native_interval = Interval.MINUTE if spec["clock"]["frequency"] == "1m" else Interval.DAILY
    engine = Engine()
    engine.output = lambda message: engine.logs.append(str(message))
    instrument = spec["clock"]["instrument"]
    engine.set_parameters(
        instrument,
        native_interval,
        datetime.fromisoformat(bars[0]["date"]),
        cfg.get("fee_rate", spec["costs"]["fee_rate"]),
        0,
        cfg.get("multiplier", spec["position"]["multiplier"]),
        spec["position"]["price_tick"],
        spec["position"]["initial_cash"],
        datetime.fromisoformat(bars[-1]["date"]),
    )
    symbol, exchange = instrument.split(".")
    engine.history_data = [
        BarData(
            symbol=symbol,
            exchange=Exchange(exchange),
            datetime=datetime.fromisoformat(b["date"]),
            interval=native_interval,
            volume=b["volume"],
            open_price=b["open"],
            high_price=b["high"],
            low_price=b["low"],
            close_price=b["close"],
            gateway_name="FIXTURE",
        )
        for b in bars
    ]
    engine.add_strategy(Observe if rec.enabled else cls, spec.get("parameters", {}))
    engine.run_backtesting()
    if engine.datetime != datetime.fromisoformat(bars[-1]["date"]):
        raise RuntimeError(
            "Native CTA replay stopped early: " + "\n".join(engine.logs[-3:])
        )
    daily = engine.calculate_result()
    equity = float(spec["position"]["initial_cash"])
    for date, row in daily.iterrows():
        equity += float(row.net_pnl)
        rec.add(
            "account",
            max(i for i, b in enumerate(bars) if b["date"][:10] == date.isoformat()),
            "close",
            "vnpy.DailyResult; equity=capital+cumsum(net_pnl)",
            provenance={"equity": "derived", "cash": "unavailable"},
            equity=equity,
            cash=None,
            position=float(row.end_pos),
            commission=float(row.commission),
            net_pnl=float(row.net_pnl),
            holding_pnl=float(row.holding_pnl),
            trading_pnl=float(row.trading_pnl),
        )
    for t in engine.get_all_trades():
        fills.append(
            {
                "session": bar_key(t.datetime, spec),
                "qty": float(t.volume * (1 if t.direction == Direction.LONG else -1)),
                "price": float(t.price),
                "fee": float(t.volume * t.price * engine.size * engine.rate),
            }
        )
    return {
        "equity": equity,
        "cash": None,
        "position": float(engine.strategy.pos),
        "fills": fills,
        "open_orders": len(engine.active_limit_orders) + len(engine.active_stop_orders),
        "net_pnl": float(daily.net_pnl.sum()),
        "commission": float(daily.commission.sum()),
    }
