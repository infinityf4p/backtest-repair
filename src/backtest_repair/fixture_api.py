"""Optional release-table access with observable availability metadata.

Candidate code may use native dataframe APIs instead; those accesses are checked
by perturbation, not falsely claimed to be fully instrumented.
"""

import csv
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from .contracts import ContractError

_recorder = None
_releases = []


def configure(recorder, path):
    global _recorder, _releases
    _recorder = recorder
    if Path(path).exists():
        with Path(path).open(encoding="utf-8") as f:
            _releases = list(csv.DictReader(f))
    else:
        _releases = []


def latest_release(session, use="available_at", default=0.0):
    if use not in {"available_at", "event_time"}:
        raise ValueError("Unknown release timestamp field")
    if _recorder is None or session not in _recorder.index:
        raise ContractError(
            "Release queries must identify a declared evaluation session"
        )
    clock = _recorder.spec["clock"]
    zone = ZoneInfo(clock["timezone"])
    opening = datetime.fromisoformat(session + "T" + clock["session_open"]).replace(
        tzinfo=zone
    )
    decision = datetime.fromisoformat(session + "T" + clock["session_close"]).replace(
        tzinfo=zone
    )
    if decision <= opening:
        decision += timedelta(days=1)

    def timestamp(row):
        value = datetime.fromisoformat(row[use])
        if value.tzinfo is None:
            raise ContractError("Release timestamps must include an explicit timezone")
        return value

    eligible = [r for r in _releases if timestamp(r) <= decision]
    if not eligible:
        return default
    row = max(eligible, key=timestamp)
    if _recorder:
        _recorder.add(
            "data_access",
            _recorder.index[session],
            "close",
            "fixture_api.latest_release",
            event_time=row["event_time"],
            available_at=row["available_at"],
            value=float(row["value"]),
        )
    return float(row["value"])
