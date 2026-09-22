"""Deterministic, budgeted deletion with a fixed financial failure predicate."""

from .contracts import validate_bars
from .runner import BudgetExhausted
import csv
import io
import math


def minimize(bars, predicate, warmup_bars, max_attempts=20):
    current = list(bars)
    attempts = 0
    history = []
    minimal = False

    def test(candidate):
        nonlocal attempts
        if attempts >= max_attempts:
            raise BudgetExhausted("Shrinker attempt budget exhausted")
        validate_bars(candidate)
        attempts += 1
        return predicate(candidate)

    try:
        if not test(current):
            return {
                "status": "not_reproduced",
                "bars": current,
                "attempts": attempts,
                "locally_minimal": False,
                "history": [],
            }
        # Keep the initial warmup prefix unchanged. Row deletion preserves declared
        # session dates, their ordering, valid OHLC and the actual failed check type.
        chunk = max(1, (len(current) - warmup_bars) // 2)
        while chunk >= 1:
            changed = False
            for start in range(warmup_bars, len(current), chunk):
                trial = current[:start] + current[start + chunk :]
                if len(trial) < warmup_bars + 2:
                    continue
                if test(trial):
                    history.append(
                        {
                            "before": len(current),
                            "after": len(trial),
                            "deleted_start": start,
                            "deleted_count": chunk,
                        }
                    )
                    current, changed = trial, True
                    break
            if not changed:
                if chunk == 1:
                    minimal = True
                chunk //= 2
        # Only row-deletion local minimality is claimed; not global numeric minimality.
        return {
            "status": "reproduced",
            "bars": current,
            "attempts": attempts,
            "locally_minimal": minimal,
            "minimality_scope": "single-row deletion after protected warmup",
            "history": history,
        }
    except BudgetExhausted:
        return {
            "status": "budget_exhausted",
            "bars": current,
            "attempts": attempts,
            "locally_minimal": False,
            "history": history,
        }


def minimize_fixture(
    bars, releases, predicate, warmup_bars, max_attempts=20, price_tick=0.01
):
    """Shrink rows, event rows and OHLCV magnitude under one execution allowance.

    predicate receives (bars, release_csv). Every accepted mutation reproduces
    the same caller-selected failure. Numeric candidates preserve tick sizes,
    positive OHLC ordering and the protected warmup prefix.
    """
    used = 0
    current, event_text = list(bars), releases
    history = []
    reproduced = False

    def test(rows, text):
        nonlocal used
        if used >= max_attempts:
            raise BudgetExhausted("Shrinker attempt budget exhausted")
        validate_bars(rows)
        used += 1
        return predicate(rows, text)

    def serialize(rows):
        buf = io.StringIO()
        writer = csv.DictWriter(
            buf, fieldnames=["event_time", "available_at", "value"], lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)
        return buf.getvalue()

    try:
        reproduced = test(current, event_text)
        if not reproduced:
            return {
                "status": "not_reproduced",
                "bars": current,
                "releases": event_text,
                "attempts": used,
                "reproduced": False,
                "history": [],
            }
        row_limit = max(1, (max_attempts - used) // 2)
        reduced = minimize(
            current, lambda rows: test(rows, event_text), warmup_bars, row_limit
        )
        current = reduced["bars"]
        history.extend({"kind": "bar_deletion", **h} for h in reduced["history"])
        event_rows = list(csv.DictReader(io.StringIO(event_text)))
        i = 0
        while i < len(event_rows):
            candidate = event_rows[:i] + event_rows[i + 1 :]
            text = serialize(candidate)
            if test(current, text):
                history.append({"kind": "event_deletion", "deleted_index": i})
                event_rows, event_text = candidate, text
            else:
                i += 1
        for factor in (100, 10, 1):
            trial = [dict(row) for row in current]
            tick = price_tick * factor
            for row in trial[warmup_bars:]:
                for name in ("open", "close"):
                    row[name] = max(price_tick, round(row[name] / tick) * tick)
                row["low"] = max(
                    price_tick,
                    min(
                        row["open"], row["close"], math.floor(row["low"] / tick) * tick
                    ),
                )
                row["high"] = max(
                    row["open"], row["close"], math.ceil(row["high"] / tick) * tick
                )
                row["volume"] = round(row["volume"])
            if trial != current and test(trial, event_text):
                current = trial
                history.append(
                    {
                        "kind": "numeric_simplification",
                        "price_grid": tick,
                        "volume_grid": 1,
                    }
                )
        status = "reproduced"
    except BudgetExhausted:
        status = "budget_exhausted"
    # Later event/numeric changes can enable more row deletions. Do not claim
    # joint local minimality without a full final fixed-point pass.
    return {
        "status": status,
        "bars": current,
        "releases": event_text,
        "attempts": used,
        "reproduced": reproduced,
        "locally_minimal": False,
        "minimality_scope": "budgeted bar/event deletion and numeric simplification; joint minimality unproven",
        "history": history,
    }
