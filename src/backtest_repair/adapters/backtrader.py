from .common import entry, frame, settings


def run(spec, bars, rec):
    import backtrader as bt

    cls = entry(spec)
    if not isinstance(cls, type) or not issubclass(cls, bt.Strategy):
        raise ValueError("entrypoint must inherit backtrader.Strategy")
    cfg = settings()
    fills, orders = [], {}

    class Observe(bt.Analyzer):
        def notify_order(self, order):
            index = max(0, len(self.strategy.data) - 1)
            created = bt.num2date(order.created.dt).date().isoformat()
            ci = rec.index.get(created, index)
            oid = str(order.ref)
            if oid not in orders:
                orders[oid] = {"session": created, "qty": float(order.created.size)}
                rec.add(
                    "order",
                    ci,
                    "close",
                    "backtrader.Order.created",
                    order_id=oid,
                    qty=float(order.created.size),
                    order_type=order.getordername(),
                    status="submitted",
                )
            rec.add(
                "order_status",
                index,
                "match",
                "backtrader.Analyzer.notify_order",
                order_id=oid,
                status=order.getstatusname(),
            )
            if order.status == order.Completed:
                executed = bt.num2date(order.executed.dt).date().isoformat()
                fi = rec.index[executed]
                item = {
                    "session": executed,
                    "qty": float(order.executed.size),
                    "price": float(order.executed.price),
                    "fee": float(order.executed.comm),
                }
                fills.append(item)
                rec.add(
                    "fill",
                    fi,
                    "close" if cfg.get("trade_on_close", False) else "open",
                    "backtrader.Order.executed",
                    order_id=oid,
                    submitted_session=created,
                    native_timestamp=str(bt.num2date(order.executed.dt)),
                    **{k: v for k, v in item.items() if k != "session"},
                )

        def next(self):
            i = len(self.strategy.data) - 1
            rec.decision(self.strategy, i, "backtrader.Strategy.next")
            rec.add(
                "account",
                i,
                "close",
                "backtrader.BackBroker",
                cash=float(self.strategy.broker.getcash()),
                equity=float(self.strategy.broker.getvalue()),
                position=float(self.strategy.position.size),
            )

    engine = bt.Cerebro(stdstats=False)
    engine.broker.setcash(spec["position"]["initial_cash"])
    engine.broker.setcommission(
        commission=cfg.get("fee_rate", spec["costs"]["fee_rate"]),
        percabs=True,
        stocklike=True,
    )
    engine.broker.set_coc(cfg.get("trade_on_close", False))
    engine.adddata(bt.feeds.PandasData(dataname=frame(bars)))
    engine.addstrategy(cls, **spec.get("parameters", {}))
    engine.addanalyzer(Observe)
    strategy = engine.run(runonce=False)[0]
    # A final-bar submission may never produce a notification. Capture the native order object.
    for order in engine.broker.orders:
        oid = str(order.ref)
        if oid not in orders:
            date = bt.num2date(order.created.dt).date().isoformat()
            rec.add(
                "order",
                rec.index[date],
                "close",
                "backtrader.BackBroker.orders",
                order_id=oid,
                qty=float(order.created.size),
                order_type=order.getordername(),
                status=order.getstatusname(),
            )
    return {
        "cash": float(engine.broker.getcash()),
        "equity": float(engine.broker.getvalue()),
        "position": float(strategy.position.size),
        "fills": fills,
        "open_orders": sum(o.alive() for o in engine.broker.orders),
    }
