"""Independent financial checks using public specifications, never candidate helpers."""

from __future__ import annotations
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
import math


def close(a, b, atol=1e-6):
    return (
        a is not None
        and b is not None
        and math.isclose(float(a), float(b), rel_tol=1e-9, abs_tol=atol)
    )


def fee(spec, qty, price):
    cost = spec["costs"]
    notional = abs(qty) * price * spec["position"]["multiplier"]
    return max(cost["minimum_fee"], notional * cost["fee_rate"]) + (
        notional * cost["sell_tax"] if qty < 0 else 0
    )


def ledger(spec, bars, fills):
    """Daily cash/position or futures marked PnL from signed actual fills."""
    by_day = defaultdict(list)
    for fill in fills:
        by_day[fill["session"]].append(fill)
    position = 0.0
    equity = cash = float(spec["position"]["initial_cash"])
    multiplier = spec["position"]["multiplier"]
    previous_close = bars[0]["close"]
    results = []
    for bar in bars:
        trades = by_day[bar["date"]]
        costs = sum(fee(spec, t["qty"], t["price"]) for t in trades)
        turnover = sum(abs(t["qty"]) * t["price"] * multiplier for t in trades)
        if spec["accounting_profile"] == "linear_futures_pnl":
            holding = position * (bar["close"] - previous_close) * multiplier
            trading = sum(
                t["qty"] * (bar["close"] - t["price"]) * multiplier for t in trades
            )
            equity += holding + trading - costs
            cash_value = None
        else:
            cash -= sum(t["qty"] * t["price"] for t in trades) + costs
            cash_value = cash
        position += sum(t["qty"] for t in trades)
        if spec["accounting_profile"] == "cash_equity":
            equity = cash + position * bar["close"]
        results.append(
            {
                "session": bar["date"],
                "cash": cash_value,
                "position": position,
                "equity": equity,
                "fee": costs,
                "turnover": turnover,
            }
        )
        previous_close = bar["close"]
    return results


def check(name, status, evidence=None, message=""):
    return {
        "check": name,
        "status": status,
        "message": message,
        "evidence": evidence or [],
    }


def spot_exit_price(spec, bar, fill):
    """Independent long-only, fixed-stop / ROI-table price check for Freqtrade."""
    reason = fill.get("exit_reason")
    rules = spec.get("native_exit_rules")

    def precision(value):
        tick = Decimal(str(spec["position"]["price_tick"]))
        return float(
            (Decimal(str(value)) / tick).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
            * tick
        )

    if reason not in {"roi", "stop_loss"}:
        return bar["open"]
    if rules is None or not fill.get("open_date") or not fill.get("open_rate"):
        return None
    opening = fill["open_rate"]
    if reason == "stop_loss":
        stop = opening * (1 + rules["stoploss"])
        return precision(bar["open"] if stop > bar["high"] else stop)
    elapsed = (
        datetime.fromisoformat(bar["date"])
        - datetime.fromisoformat(fill["open_date"]).replace(tzinfo=None)
    ).total_seconds() / 60
    table = sorted(
        (int(k), float(v)) for k, v in rules["minimal_roi"].items() if int(k) <= elapsed
    )
    if not table:
        return None
    minute, roi = table[-1]
    if roi == -1 and minute % 1440 == 0:
        return bar["open"]
    rate = spec["costs"]["fee_rate"]
    target = opening * (1 + rate) * (1 + roi) / (1 - rate)
    if (
        elapsed > 0
        and elapsed == minute
        and minute % 1440 == 0
        and bar["open"] > target
    ):
        return bar["open"]
    return precision(min(max(target, bar["low"]), bar["high"]))


def validate_trace(spec, bars, result):
    if result["status"] != "ok":
        return [
            check(
                "execution",
                "inconclusive",
                message=result.get("error", result["status"]),
            )
        ]
    events = result["events"]
    fills = [e for e in events if e["kind"] == "fill"]
    accounts = {e["session"]: e for e in events if e["kind"] == "account"}
    signals = [e for e in events if e["kind"] == "signal"]
    checks = []
    errors = []
    for f in fills:
        expected = fee(spec, f["qty"], f["price"])
        if f.get("fee") is None:
            continue
        if not close(f["fee"], expected):
            errors.append(
                {
                    "seq": f["seq"],
                    "session": f["session"],
                    "expected_fee": expected,
                    "observed_fee": f["fee"],
                }
            )
    observed_costs = bool(fills) and all(f.get("fee") is not None for f in fills)
    checks.append(
        check(
            "costs",
            "fail" if errors else "pass" if observed_costs else "inconclusive",
            errors,
            "Independent cost function; no fills means costs were not exercised",
        )
    )
    expected = ledger(spec, bars, fills)
    errors = []
    for row in expected:
        observed = accounts.get(row["session"])
        if observed:
            for field in ("position", "cash", "equity"):
                if row[field] is None:
                    continue
                if observed.get(field) is None:
                    errors.append(
                        {"session": row["session"], "field": field, "missing": True}
                    )
                elif not close(row[field], observed[field]):
                    errors.append(
                        {
                            "seq": observed["seq"],
                            "session": row["session"],
                            "field": field,
                            "expected": row[field],
                            "observed": observed[field],
                        }
                    )
    native = result.get("native", {})
    for field in ("cash", "equity", "position"):
        if (
            expected[-1][field] is not None
            and native.get(field) is not None
            and not close(expected[-1][field], native[field])
        ):
            errors.append(
                {
                    "source": "native.final",
                    "field": field,
                    "expected": expected[-1][field],
                    "observed": native[field],
                }
            )
    checks.append(
        check(
            "accounting",
            "fail" if errors else "pass" if accounts else "inconclusive",
            errors,
        )
    )
    checks.append(
        check(
            "signal_observation",
            "pass" if signals else "inconclusive",
            message="Explicit observed signals required for signal-level conclusions",
        )
    )
    native_fills = result.get("native", {}).get("fills", [])
    reconciled = len(fills) == len(native_fills) and all(
        a["session"] == b["session"]
        and all(close(a[k], b[k]) for k in ("qty", "price", "fee"))
        for a, b in zip(fills, native_fills)
    )
    checks.append(
        check(
            "native_trace_reconciliation",
            "pass" if reconciled else "fail",
            message="Recorded fills must reconcile with native results",
        )
    )
    timing = []
    orders = [e for e in events if e["kind"] == "order"]
    consumed = set()
    engine = spec["engine"]
    for fill in fills:
        i = fill["bar_index"]
        if engine == "rqalpha":
            expected_price = bars[i]["close"]
            valid = fill["phase"] == "close" and close(fill["price"], expected_price)
        elif engine == "freqtrade":
            expected_price = spot_exit_price(spec, bars[i], fill)
            valid = close(fill["price"], expected_price)
        else:
            matches = [
                o
                for o in orders
                if o["seq"] not in consumed
                and o["qty"] * fill["qty"] > 0
                and (not fill.get("order_id") or o.get("order_id") == fill["order_id"])
            ]
            order = matches[0] if matches else None
            if order:
                consumed.add(order["seq"])
            if engine == "vnpy_cta" and order:
                price = order["price"]
                buy = fill["qty"] > 0
                stop = order["order_type"] == "stop"
                expected_price = (
                    (
                        max(price, bars[i]["open"])
                        if buy
                        else min(price, bars[i]["open"])
                    )
                    if stop
                    else (
                        min(price, bars[i]["open"])
                        if buy
                        else max(price, bars[i]["open"])
                    )
                )
                eligible = (
                    bars[i]["high"] >= price
                    if buy and stop
                    else bars[i]["low"] <= price
                    if buy
                    else bars[i]["low"] <= price
                    if stop
                    else bars[i]["high"] >= price
                )
                valid = (
                    i > order["bar_index"]
                    and eligible
                    and close(fill["price"], expected_price)
                )
            else:
                expected_price = bars[i]["open"]
                valid = (
                    order is not None
                    and i == order["bar_index"] + 1
                    and fill["phase"] == "open"
                    and close(fill["price"], expected_price)
                )
        if not valid:
            timing.append(
                {
                    "seq": fill["seq"],
                    "session": fill["session"],
                    "price": fill["price"],
                    "expected_price": expected_price,
                    "phase": fill["phase"],
                }
            )
    checks.append(
        check(
            "fill_timing",
            "fail" if timing else "pass" if fills else "inconclusive",
            timing,
        )
    )
    releases = [e for e in events if e["kind"] == "data_access"]
    violations = [
        e
        for e in releases
        if datetime.fromisoformat(e["available_at"])
        > datetime.fromisoformat(e["timestamp"])
    ]
    checks.append(
        check(
            "release_visibility",
            "fail" if violations else "pass" if releases else "inconclusive",
            [
                {
                    "seq": e["seq"],
                    "available_at": e["available_at"],
                    "decision_time": e["timestamp"],
                }
                for e in violations
            ],
            "Covers instrumented release accesses only; arbitrary Python reads are not observed",
        )
    )
    positions = [e for e in accounts.values() if e.get("position") is not None]
    limit = spec["position"]["unit"]
    bad = [
        e
        for e in positions
        if e["position"] < (-limit - 1e-8 if engine == "vnpy_cta" else -1e-8)
        or (engine != "freqtrade" and e["position"] > limit + 1e-8)
    ]
    checks.append(
        check(
            "position_bounds",
            "fail" if bad else "pass" if positions else "inconclusive",
            [{"seq": e["seq"], "position": e["position"]} for e in bad],
        )
    )
    if engine == "freqtrade":
        expected_rules = spec.get("native_exit_rules")
        actual_rules = native.get("exit_rules")
        checks.append(
            check(
                "native_exit_rules",
                "inconclusive"
                if expected_rules is None or actual_rules is None
                else "pass"
                if expected_rules == actual_rules
                else "fail",
                []
                if expected_rules == actual_rules
                else [{"expected": expected_rules, "observed": actual_rules}],
            )
        )
    if engine == "rqalpha":
        bad = []
        opening_position = 0
        for bar in bars:
            day_fills = [f for f in fills if f["session"] == bar["date"]]
            buys = sum(f["qty"] for f in day_fills if f["qty"] > 0)
            sold = -sum(f["qty"] for f in day_fills if f["qty"] < 0)
            if sold > opening_position + 1e-8 or any(
                not close(f["qty"] / 100, round(f["qty"] / 100)) for f in day_fills
            ):
                bad.append(
                    {
                        "session": bar["date"],
                        "sellable_at_open": opening_position,
                        "sold": sold,
                        "buys": buys,
                    }
                )
            observed = accounts.get(bar["date"])
            if (
                observed
                and observed.get("sellable") is not None
                and not close(observed["sellable"], max(0, opening_position - sold))
            ):
                bad.append(
                    {
                        "session": bar["date"],
                        "expected_sellable": max(0, opening_position - sold),
                        "observed_sellable": observed["sellable"],
                    }
                )
            opening_position += buys - sold
        checks.append(
            check(
                "stock_lot_and_tplus1",
                "fail" if bad else "pass" if accounts else "inconclusive",
                bad,
            )
        )
    return checks


def compare_prefix(left, right, cutoff):
    if left["status"] != "ok" or right["status"] != "ok":
        return check(
            "causality", "inconclusive", message="One of the two native runs failed"
        )

    def decisions(result):
        rows = []
        for e in result["events"]:
            if e["kind"] == "signal" and e["session"] <= cutoff:
                rows.append(
                    {k: e[k] for k in ("session", "signal", "exit_signal") if k in e}
                )
        return rows

    a, b = decisions(left), decisions(right)
    if not a or not b:
        return check(
            "causality",
            "inconclusive",
            message="No explicit signal observations before cutoff",
        )
    if a != b:
        for i in range(max(len(a), len(b))):
            x, y = a[i] if i < len(a) else None, b[i] if i < len(b) else None
            if x != y:
                return check(
                    "causality",
                    "fail",
                    [{"left": x, "right": y, "cutoff": cutoff}],
                    "Changing unavailable data changed an earlier signal",
                )
    return check(
        "causality",
        "pass",
        message="Signals match through cutoff; this probe alone cannot prove absence of all leakage",
    )
