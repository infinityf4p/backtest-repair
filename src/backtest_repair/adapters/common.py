import importlib
import json
from pathlib import Path


def entry(spec):
    module, _, name = spec["entrypoint"].partition(":")
    loaded = importlib.import_module(module)
    return getattr(loaded, name) if name else loaded


def settings():
    path = Path("run_settings.json")
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def bar_key(value, spec):
    if spec["clock"]["frequency"] == "1d":
        return value.date().isoformat()
    return value.replace(tzinfo=None).isoformat()


def frame(bars, upper=False, utc=False):
    import pandas as pd

    data = pd.DataFrame(bars)
    data.index = pd.to_datetime(data.pop("date"), utc=utc)
    if upper:
        data.columns = [c.title() for c in data.columns]
    return data
