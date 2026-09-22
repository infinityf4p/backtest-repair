"""Offline daily stock datasource + native RQAlpha event bus integration."""

from pathlib import Path
import sys
import types
from .common import entry, settings
from ..contracts import ContractError, read_bars


def run(spec, bars, rec):
    import numpy as np
    import pandas as pd
    from rqalpha import run_func
    from rqalpha.const import TRADING_CALENDAR_TYPE, SIDE
    from rqalpha.core.events import EVENT
    from rqalpha.interface import AbstractDataSource, AbstractMod, ExchangeRate
    from rqalpha.model.instrument import Instrument

    module = entry(spec)
    if not callable(getattr(module, "init", None)) or not callable(
        getattr(module, "handle_bar", None)
    ):
        raise ValueError("RQAlpha strategy module must define init and handle_bar")
    cfg, fills, final = settings(), [], {}
    symbol = spec["clock"]["instrument"]
    warmup_path = Path("fixtures/warmup.csv")
    warmup = read_bars(warmup_path) if warmup_path.exists() else []
    if warmup and warmup[-1]["date"] >= bars[0]["date"]:
        raise ContractError("Historical warmup must precede evaluation")
    history = warmup + bars
    dates = pd.DatetimeIndex([b["date"] for b in history])
    history_index = {b["date"]: i for i, b in enumerate(history)}
    dtype = [
        ("datetime", "u8"),
        *[
            (k, "f8")
            for k in [
                "open",
                "high",
                "low",
                "close",
                "volume",
                "total_turnover",
                "limit_up",
                "limit_down",
                "prev_close",
            ]
        ],
    ]
    records = np.array(
        [
            (
                int(b["date"].replace("-", "") + "000000"),
                b["open"],
                b["high"],
                b["low"],
                b["close"],
                b["volume"],
                b["volume"] * b["close"],
                1e12,
                0.01,
                history[max(i - 1, 0)]["close"],
            )
            for i, b in enumerate(history)
        ],
        dtype=dtype,
    )
    instrument = Instrument(
        {
            "order_book_id": symbol,
            "symbol": "FIXTURE",
            "type": "CS",
            "exchange": symbol.split(".")[1],
            "board_type": "MainBoard",
            "round_lot": 100,
            "market_tplus": 1,
            "listed_date": "2000-01-01",
            "de_listed_date": "2099-01-01",
            "contract_multiplier": 1,
            "status": "Active",
            "tick_size": spec["position"]["price_tick"],
        }
    )

    class FixtureSource(AbstractDataSource):
        def get_instruments(self, id_or_syms=None, types=None):
            return (
                [instrument]
                if (
                    id_or_syms is None
                    or symbol in id_or_syms
                    or "FIXTURE" in id_or_syms
                )
                and (types is None or instrument.type in types)
                else []
            )

        def get_trading_calendars(self):
            return {TRADING_CALENDAR_TYPE.CN_STOCK: dates}

        def available_data_range(self, frequency):
            return dates[0].date(), dates[-1].date()

        def get_bar(self, instrument, dt, frequency):
            day = dt.date().isoformat()
            return records[history_index[day]] if day in history_index else None

        def history_bars(
            self,
            instrument,
            bar_count,
            frequency,
            fields,
            dt,
            skip_suspended=True,
            include_now=False,
            adjust_type="pre",
            adjust_orig=None,
        ):
            if frequency != "1d":
                raise ContractError(
                    "Synthetic RQAlpha source supports daily history only",
                    "out_of_scope",
                )
            end = dates.searchsorted(pd.Timestamp(dt.date()), side="right")
            data = records[max(0, end - bar_count) : end]
            return data[fields] if fields is not None else data

        def get_open_auction_bar(self, instrument, dt):
            return self.get_bar(instrument, dt, "1d")

        def get_open_auction_volume(self, instrument, dt):
            return float(self.get_bar(instrument, dt, "1d")["volume"])

        def get_dividend(self, instrument):
            return None

        def get_split(self, instrument):
            return None

        def get_share_transformation(self, order_book_id):
            return None

        def is_suspended(self, order_book_id, dates):
            return [False] * len(dates)

        def is_st_stock(self, order_book_id, dates):
            return [False] * len(dates)

        def get_exchange_rate(self, trading_date, local, settlement=None):
            return ExchangeRate(1, 1, 1, 1, 1, 1)

        def get_yield_curve(self, start_date, end_date, tenor=None):
            return pd.DataFrame({"0S": 0.0}, index=dates)

    class FixtureMod(AbstractMod):
        def start_up(self, env, mod_config):
            self.env = env
            env.set_data_source(FixtureSource())

            def index():
                return rec.index[env.trading_dt.date().isoformat()]

            def on_order(event):
                if not hasattr(event, "order"):
                    # Validation may reject an intent before an Order exists.
                    rec.add(
                        "order_rejected",
                        index(),
                        "close",
                        "rqalpha.EventBus." + event.event_type.name,
                        order_book_id=getattr(event, "order_book_id", symbol),
                        reason=str(getattr(event, "reason", "")),
                    )
                    return
                o = event.order
                rec.add(
                    "order"
                    if event.event_type == EVENT.ORDER_PENDING_NEW
                    else "order_status",
                    index(),
                    "close",
                    "rqalpha.EventBus." + event.event_type.name,
                    order_id=str(o.order_id),
                    qty=float(o.quantity * (1 if o.side == SIDE.BUY else -1)),
                    status=o.status.name,
                    order_type=o.type.name,
                )

            def on_trade(event):
                t = event.trade
                item = {
                    "session": bars[index()]["date"],
                    "qty": float(t.last_quantity * (1 if t.side == SIDE.BUY else -1)),
                    "price": float(t.last_price),
                    "fee": float(t.commission + t.tax),
                }
                fills.append(item)
                rec.add(
                    "fill",
                    index(),
                    "close",
                    "rqalpha.EventBus.TRADE",
                    order_id=str(t.order_id),
                    commission=float(t.commission),
                    tax=float(t.tax),
                    **{k: v for k, v in item.items() if k != "session"},
                )

            def account(event):
                p = env.portfolio
                pos = p.positions[symbol]
                rec.add(
                    "account",
                    index(),
                    "close",
                    "rqalpha.Portfolio",
                    cash=float(p.cash),
                    equity=float(p.total_value),
                    position=float(pos.quantity),
                    sellable=float(pos.sellable),
                )
                final.update(
                    cash=float(p.cash),
                    equity=float(p.total_value),
                    position=float(pos.quantity),
                )

            for event in [
                EVENT.ORDER_PENDING_NEW,
                EVENT.ORDER_CREATION_PASS,
                EVENT.ORDER_CREATION_REJECT,
                EVENT.ORDER_CANCELLATION_PASS,
                EVENT.ORDER_UNSOLICITED_UPDATE,
            ]:
                env.event_bus.add_listener(event, on_order, user=True)
            env.event_bus.add_listener(EVENT.TRADE, on_trade, user=True)
            env.event_bus.add_listener(EVENT.POST_AFTER_TRADING, account, user=True)

        def tear_down(self, code, exception=None):
            return None

    mod = types.ModuleType("btr_fixture_mod")
    mod.load_mod = FixtureMod
    sys.modules[mod.__name__] = mod

    def handle_bar(context, bar_dict):
        module.handle_bar(context, bar_dict)
        rec.decision(
            context, rec.index[context.now.date().isoformat()], "rqalpha.handle_bar"
        )

    config = {
        "base": {
            "start_date": bars[0]["date"],
            "end_date": bars[-1]["date"],
            "frequency": "1d",
            "accounts": {"stock": spec["position"]["initial_cash"]},
            "data_bundle_path": str(Path("fixtures").resolve()),
            "rqdatac_uri": "disabled",
        },
        "extra": {"log_level": "error", "locale": "en_US"},
        "mod": {
            "fixture": {"enabled": True, "lib": mod.__name__, "priority": 1},
            "sys_analyser": {"enabled": True, "record": True, "plot": False},
            "sys_progress": {"enabled": False},
            "sys_simulation": {
                "enabled": True,
                "matching_type": "current_bar",
                "volume_limit": False,
                "price_limit": False,
                "slippage": 0,
            },
            "sys_transaction_cost": {
                "enabled": True,
                "stock_commission_multiplier": cfg.get(
                    "fee_rate", spec["costs"]["fee_rate"]
                )
                / 0.0008,
                "stock_min_commission": cfg.get(
                    "minimum_fee", spec["costs"]["minimum_fee"]
                ),
                "tax_multiplier": cfg.get("sell_tax", spec["costs"]["sell_tax"])
                / 0.0005,
                "pit_tax": False,
            },
        },
    }
    hooks = {
        name: getattr(module, name)
        for name in ("before_trading", "after_trading")
        if callable(getattr(module, name, None))
    }
    result = run_func(config=config, init=module.init, handle_bar=handle_bar, **hooks)
    if not final:
        raise RuntimeError("RQAlpha produced no native account observations")
    import math
    indicators=[]
    plots=result.get("sys_analyser",{}).get("plots") if result else None
    if plots is not None:
        for timestamp,row in plots.iterrows():
            indicators.append({"session":timestamp.date().isoformat(),"values":{str(name):float(value) if math.isfinite(float(value)) else None for name,value in row.items()}})
    return {**final, "fills": fills, "indicators":indicators}
