from copy import deepcopy
from datetime import date, timedelta
import random
from .contracts import validate_bars


def future_perturbation(bars, cutoff_index, seed=0):
    if not 0 <= cutoff_index < len(bars) - 1:
        raise ValueError("Cutoff must leave at least one future bar")
    rng = random.Random(seed)
    result = deepcopy(bars)
    for b in result[cutoff_index + 1 :]:
        # Keep price changes bounded: huge independent jumps can invalidate a
        # perfectly normal ATR stop and make the diagnostic itself unexecutable.
        scale = rng.uniform(0.96, 1.04)
        for k in ("open", "high", "low", "close"):
            b[k] = round(b[k] * scale, 6)
        b["volume"] *= rng.choice([0.5, 3])
    validate_bars(result)
    return result


def synthetic_bars(count=30, seed=0, kind="mixed", continuous=False):
    rng = random.Random(seed)
    rows, day, price = [], date(2025, 1, 6), 100.0
    for i in range(count):
        while not continuous and day.weekday() > 4:
            day += timedelta(days=1)
        if kind == "flat":
            opening = closing = 100.0
        elif kind == "gap":
            closing = [100, 100, 100, 100, 110, 130, 105, 120, 95, 100][i % 10]
            opening = closing + (20 if i % 3 == 2 else -10 if i % 3 == 1 else 0)
        else:
            opening = max(10, price + rng.choice([-8, -3, 0, 4, 10]))
            closing = max(10, opening + rng.choice([-12, -7, -2, 0, 3, 6, 14]))
        rows.append(
            {
                "date": day.isoformat(),
                "open": float(opening),
                "high": float(max(opening, closing) + 2),
                "low": float(min(opening, closing) - 2),
                "close": float(closing),
                "volume": float(rng.choice([100000, 200000, 500000, 1000000])),
            }
        )
        price, day = closing, day + timedelta(days=1)
    validate_bars(rows)
    return rows


def shift_releases(text, days):
    import csv
    import io
    from datetime import datetime

    rows = list(csv.DictReader(io.StringIO(text)))
    for r in rows:
        r["available_at"] = (
            datetime.fromisoformat(r["available_at"]) + timedelta(days=days)
        ).isoformat()
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=["event_time", "available_at", "value"])
    w.writeheader()
    w.writerows(rows)
    return out.getvalue()
