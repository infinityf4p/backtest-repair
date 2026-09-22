from functools import partial
from .common import entry, frame, settings


def run(spec, bars, rec):
    import backtesting.backtesting as native

    cls = entry(spec)
    if not isinstance(cls, type) or not issubclass(cls, native.Strategy):
        raise ValueError("entrypoint must inherit backtesting.Strategy")
    cfg = settings()
    fills, seen = [], {}

    def order_id(order):
        if id(order) not in seen:
            # Keep references alive; Python must not reuse object identities.
            seen[id(order)] = (str(len(seen) + 1), order)
        return seen[id(order)][0]

    class Broker(native._Broker):
        def _open_trade(self, price, size, sl, tp, time_index, tag):
            cash = self._cash
            super()._open_trade(price, size, sl, tp, time_index, tag)
            item = {
                "session": bars[time_index]["date"],
                "qty": float(size),
                "price": float(price),
                "fee": float(cash - self._cash),
            }
            fills.append(item)
            rec.add(
                "fill",
                time_index,
                "close" if self._trade_on_close else "open",
                "backtesting._Broker._open_trade",
                **{k: v for k, v in item.items() if k != "session"},
            )

        def _close_trade(self, trade, price, time_index):
            cash, size, pl = (
                self._cash,
                trade.size,
                trade.size * (price - trade.entry_price),
            )
            super()._close_trade(trade, price, time_index)
            item = {
                "session": bars[time_index]["date"],
                "qty": float(-size),
                "price": float(price),
                "fee": float(cash + pl - self._cash),
            }
            fills.append(item)
            # Trade.close() is a contingent order; it always executes on the next open.
            rec.add(
                "fill",
                time_index,
                "open",
                "backtesting._Broker._close_trade",
                **{k: v for k, v in item.items() if k != "session"},
            )

    class Observe(cls):
        def next(self):
            super().next()
            i = len(self.data) - 1
            rec.decision(self, i, "backtesting.Strategy.next")
            for order in self._broker.orders:
                if id(order) not in seen:
                    oid = order_id(order)
                    rec.add(
                        "order",
                        i,
                        "close",
                        "backtesting._Broker.orders",
                        order_id=oid,
                        qty=float(order.size),
                        order_type="stop_limit" if order.limit and order.stop else "limit" if order.limit else "stop" if order.stop else "market",
                        price=float(order.limit) if order.limit else None,
                        stop_price=float(order.stop) if order.stop else None,
                        status="submitted",
                    )
            broker = self._broker
            spot_cash = broker._cash - sum(
                t.size * t.entry_price for t in broker.trades
            )
            rec.add(
                "account",
                i,
                "close",
                "backtesting._Broker; cash=_cash-sum(open cost)",
                provenance={"cash": "derived"},
                cash=float(spot_cash),
                position=float(self.position.size),
                equity=float(broker.equity),
                native_cash=float(broker._cash),
            )

    engine = native.Backtest(
        frame(bars, upper=True),
        Observe if rec.enabled else cls,
        cash=spec["position"]["initial_cash"],
        commission=cfg.get("fee_rate", spec["costs"]["fee_rate"]),
        trade_on_close=cfg.get("trade_on_close", False),
        finalize_trades=cfg.get("finalize_trades", False),
    )
    # Broker subclass adds observations after original native operations.
    engine._broker = partial(Broker, **engine._broker.keywords)
    result = engine.run(**spec.get("parameters", {}))
    strategy = result["_strategy"]
    broker = strategy._broker
    return {
        "equity": float(result["Equity Final [$]"]),
        "position": float(strategy.position.size),
        "cash": float(
            broker._cash - sum(t.size * t.entry_price for t in broker.trades)
        ),
        "native_cash": float(broker._cash),
        "fills": fills,
        "open_orders": len(broker.orders),
        "closed_trade_count": len(broker.closed_trades),
    }
