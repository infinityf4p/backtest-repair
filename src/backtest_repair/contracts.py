"""Public contracts. Hidden labels and reference implementations never live here."""

from __future__ import annotations
import csv
from datetime import datetime
import hashlib
import json
import math
import re
from pathlib import Path, PurePosixPath

VERSIONS = {
    "backtrader": "1.9.78.123",
    "backtesting_py": "0.6.6",
    "vnpy_cta": "1.4.1",
    "rqalpha": "6.4.0",
    "freqtrade": "2026.8",
}
DISTRIBUTIONS = {
    **{x: x for x in VERSIONS},
    "backtesting_py": "backtesting",
    "vnpy_cta": "vnpy_ctastrategy",
}
PROFILES = {
    "backtrader": "cash_next_open",
    "backtesting_py": "cash_next_open",
    "vnpy_cta": "futures_bar_limit",
    "rqalpha": "stock_current_close",
    "freqtrade": "spot_next_open_force_exit",
}


class ContractError(ValueError):
    def __init__(self, message, status="needs_spec"):
        self.status = status
        super().__init__(message)


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def dump_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8"
    )


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def safe_path(root, relative):
    root = Path(root).resolve()
    raw = root / relative
    # Inspect components before resolve(), which would erase an in-root symlink.
    for part in [raw, *raw.parents]:
        if part == root:
            break
        if part.is_symlink() or (hasattr(part, "is_junction") and part.is_junction()):
            raise ValueError("Symlink/junction paths are not allowed")
    path = raw.resolve()
    if not path.is_relative_to(root) or path == root:
        raise ValueError("Path must name a file inside the public candidate project")
    # Junctions and symlinks must not turn a file operation into an escape.
    for part in [path, *path.parents]:
        if part == root:
            break
        if part.is_symlink() or (hasattr(part, "is_junction") and part.is_junction()):
            raise ValueError("Symlink/junction paths are not allowed")
    return path


def validate_spec(spec):
    spec = dict(spec)
    if "entrypoint" not in spec:
        if spec.get("strategy_module"):
            spec["entrypoint"] = spec["strategy_module"]
        elif spec.get("strategy_class"):
            module, _, name = spec["strategy_class"].rpartition(".")
            spec["entrypoint"] = module + ":" + name
    required = {
        "task_id",
        "engine",
        "framework_version",
        "entrypoint",
        "strategy_rules",
        "execution_profile",
        "accounting_profile",
        "clock",
        "position",
        "costs",
        "warmup_bars",
        "modifiable_files",
    }
    missing = required - spec.keys()
    if missing:
        raise ContractError(
            "Missing specification fields: " + ", ".join(sorted(missing))
        )
    engine = spec["engine"]
    if engine not in VERSIONS:
        raise ContractError("Unsupported native engine", "out_of_scope")
    if spec["framework_version"] != VERSIONS[engine]:
        raise ContractError(
            "Adapter requires pinned framework version " + VERSIONS[engine],
            "out_of_scope",
        )
    if spec["execution_profile"] != PROFILES[engine]:
        raise ContractError(
            "Unsupported execution profile for " + engine, "out_of_scope"
        )
    expected_accounting = (
        "linear_futures_pnl" if engine == "vnpy_cta" else "cash_equity"
    )
    if spec["accounting_profile"] != expected_accounting:
        raise ContractError("Unsupported accounting profile", "out_of_scope")
    for key in (
        "timezone",
        "bar_label",
        "frequency",
        "instrument",
        "session_open",
        "session_close",
    ):
        if key not in spec["clock"]:
            raise ContractError("Missing clock." + key)
    supported = {"1d"}
    if spec.get("external_strategy"):
        supported = {"1d", "1m"} if engine == "vnpy_cta" else {"1d", "5m", "30m", "1h"} if engine == "freqtrade" else supported
    if spec["clock"]["frequency"] not in supported:
        raise ContractError(
            "Only single-instrument daily bars are supported", "out_of_scope"
        )
    for key in (
        "initial_cash",
        "unit",
        "multiplier",
        "price_tick",
        "stake",
        "amount_decimals",
    ):
        if key not in spec["position"]:
            raise ContractError("Missing position." + key)
    for key in ("fee_rate", "minimum_fee", "sell_tax", "slippage"):
        if key not in spec["costs"]:
            raise ContractError("Missing costs." + key)
        if not math.isfinite(spec["costs"][key]) or spec["costs"][key] < 0:
            raise ContractError("Costs must be finite and nonnegative")
    if spec["costs"]["slippage"] != 0:
        raise ContractError(
            "This adapter profile requires zero slippage", "out_of_scope"
        )
    if not isinstance(spec["warmup_bars"], int) or spec["warmup_bars"] < 1:
        raise ContractError("warmup_bars must be a positive integer")
    if spec["position"]["initial_cash"] <= 0 or spec["position"]["unit"] <= 0:
        raise ContractError("Initial cash and order unit must be positive")
    if not spec["strategy_rules"].strip():
        raise ContractError("Natural-language strategy rules are required")
    if not re.fullmatch(
        r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*(?::[A-Za-z_]\w*)?", spec["entrypoint"]
    ):
        raise ContractError("Entrypoint must be a Python module or module:Class")
    if not isinstance(spec["modifiable_files"], list) or not spec["modifiable_files"]:
        raise ContractError("Explicit modifiable_files are required")
    for name in spec["modifiable_files"]:
        path = PurePosixPath(name)
        if (
            path.is_absolute()
            or ".." in path.parts
            or "\\" in name
            or ":" in name
            or path.suffix not in {".py", ".json"}
            or name == "task.json"
            or path.parts[0] == "fixtures"
        ):
            raise ContractError(
                "Only candidate Python and run configuration files may be modified"
            )
    if engine != "rqalpha" and (
        spec["costs"]["minimum_fee"] or spec["costs"]["sell_tax"]
    ):
        raise ContractError(
            "This native fee profile supports proportional fees only", "out_of_scope"
        )
    if engine != "vnpy_cta" and spec["position"]["multiplier"] != 1:
        raise ContractError("Cash/spot profiles require multiplier=1", "out_of_scope")
    if engine == "rqalpha" and spec["position"]["unit"] % 100:
        raise ContractError(
            "The synthetic stock profile requires a whole 100-share lot", "out_of_scope"
        )
    if engine == "freqtrade":
        if not isinstance(spec.get("native_exit_rules"), dict) or not all(
            k in spec["native_exit_rules"]
            for k in ("minimal_roi", "stoploss", "use_exit_signal")
        ):
            raise ContractError(
                "Freqtrade requires native_exit_rules: minimal_roi, stoploss, use_exit_signal"
            )
        if not spec["position"]["stake"] or spec["position"]["stake"] <= 0:
            raise ContractError("Freqtrade fixed quote stake must be positive")
    return spec


def read_bars(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        for name in ("open", "high", "low", "close", "volume"):
            row[name] = float(row[name])
    validate_bars(rows)
    return rows


def validate_bars(rows):
    if len(rows) < 2:
        raise ContractError("At least two daily bars are required")
    previous = ""
    for row in rows:
        date = row["date"]
        parsed = datetime.fromisoformat(date)
        if parsed.tzinfo is not None or ("T" not in date and len(date) != 10):
            raise ContractError("Use a session date or a timezone-naive ISO bar label with the timezone declared in the spec")
        if date <= previous:
            raise ContractError("Daily bars must have unique increasing session dates")
        previous = date
        opening, high, low, closing, volume = (
            row[k] for k in ("open", "high", "low", "close", "volume")
        )
        if (
            not all(math.isfinite(x) for x in [opening, high, low, closing, volume])
            or not (0 < low <= min(opening, closing) <= max(opening, closing) <= high)
            or volume < 0
        ):
            raise ContractError("Invalid OHLCV bar at " + date)


def write_bars(path, rows):
    validate_bars(rows)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f, fieldnames=["date", "open", "high", "low", "close", "volume"]
        )
        w.writeheader()
        w.writerows(rows)


def capabilities(spec):
    validate_spec(spec)
    return {
        "engine": spec["engine"],
        "version": spec["framework_version"],
        "frequency": "1d",
        "profiles": [spec["execution_profile"], spec["accounting_profile"]],
        "observations": {
            "native_orders": True,
            "native_fills": True,
            "account_equity": True,
            "signal": "explicit public observable or native signal columns",
            "all_python_data_reads": False,
            "release_access_via_fixture_api": True,
        },
        "checks": [
            "future_perturbation",
            "prefix",
            "fill_timing",
            "costs",
            "accounting",
            "release_visibility",
        ],
        "unsupported": [
            "tick",
            "multi_asset",
            "live_trading",
            "arbitrary_scripts",
            "margin_liquidation",
        ],
    }
