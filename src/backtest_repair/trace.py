from __future__ import annotations
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


def bar_times(spec, session):
    clock = spec['clock']
    zone = ZoneInfo(clock['timezone'])
    if 'T' in session:
        opening = datetime.fromisoformat(session).replace(tzinfo=zone)
        unit = clock['frequency'][-1]
        minutes = int(clock['frequency'][:-1]) * {'m': 1, 'h': 60, 'd': 1440}[unit]
        closing = opening + timedelta(minutes=minutes)
    else:
        opening = datetime.fromisoformat(session + 'T' + clock['session_open']).replace(tzinfo=zone)
        closing = datetime.fromisoformat(session + 'T' + clock['session_close']).replace(tzinfo=zone)
        if closing <= opening:
            closing += timedelta(days=1)
    return opening, closing


class Recorder:
    def __init__(self, spec, bars, enabled=True):
        self.spec, self.bars, self.enabled = spec, bars, enabled
        self.events = []
        self.index = {b["date"]: i for i, b in enumerate(bars)}

    def add(self, kind, i, phase, source, provenance=None, **values):
        if not self.enabled:
            return
        i = max(0, min(int(i), len(self.bars) - 1))
        clock = self.spec["clock"]
        day = self.bars[i]["date"]
        opening, closing = bar_times(self.spec, day)
        timestamp = opening if phase in {"open", "match"} else closing
        self.events.append(
            {
                "seq": len(self.events),
                "kind": kind,
                "bar_index": i,
                "session": day,
                "timestamp": timestamp.isoformat(),
                "bar_start": opening.isoformat(),
                "bar_end": closing.isoformat(),
                "phase": phase,
                "instrument": clock["instrument"],
                "source": source,
                "provenance": {
                    k: (provenance or {}).get(k, "observed") for k in values
                },
                **values,
            }
        )

    def decision(self, obj, i, source):
        attribute = self.spec.get("signal_attribute", "signal")
        value = getattr(obj, attribute, None)
        for name in self.spec.get("observable_attributes", []):
            series = getattr(obj, name, None)
            if series is not None:
                try:
                    number = float(series[0 if self.spec["engine"]=="backtrader" else -1])
                except (TypeError, IndexError):
                    number = float(series)
                import math
                self.add("indicator", i, "close", source, name=name, value=number if math.isfinite(number) else None)
        if value is not None:
            self.add("signal", i, "close", source, signal=float(value))
        else:
            self.add(
                "decision",
                i,
                "close",
                source,
                provenance={"signal": "unavailable"},
                signal=None,
            )
