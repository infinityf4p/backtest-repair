"""Host-owned native evidence checks shared by CLI and corpus evaluation."""

from __future__ import annotations
import math
from pathlib import Path
from .contracts import load_json, read_bars, digest
from .semantics import ledger, fee
from .identity import execution_identity
from .preservation import check_preservation
from .rules import check_contract
from .probes import future_perturbation
from .store import atomic_json


def near(a, b):
    if a is None or b is None:
        return a is b
    return math.isclose(float(a), float(b), abs_tol=1e-6, rel_tol=1e-8)


def financial_check(spec, bars, result):
    if result["status"] != "ok":
        return {"status": "inconclusive", "reason": result.get("error")}
    native = result["native"]
    fills = native.get("fills", [])
    expected = ledger(spec, bars, fills)
    observed_fills = [e for e in result["events"] if e["kind"] == "fill"]
    errors = []
    if spec.get("native_exit_rules"):
        configs = [
            e.get("exit_rules")
            for e in result["events"]
            if e["kind"] == "execution_config"
        ]
        if len(configs) != 1 or configs[0] != spec["native_exit_rules"]:
            errors.append(
                {
                    "field": "execution_config",
                    "expected": spec["native_exit_rules"],
                    "actual": configs,
                }
            )
    for field in ["equity", "position"] + (
        ["cash"] if spec["accounting_profile"] == "cash_equity" else []
    ):
        if native.get(field) is None or not math.isfinite(float(native[field])):
            errors.append(
                {
                    "field": field,
                    "reason": "Required native account observation missing or nonfinite",
                }
            )
    for i, f in enumerate(fills):
        if not near(f["fee"], fee(spec, f["qty"], f["price"])):
            errors.append(
                {
                    "fill": i,
                    "field": "fee",
                    "expected": fee(spec, f["qty"], f["price"]),
                    "actual": f["fee"],
                }
            )
    for field in ["cash", "equity", "position"]:
        a, b = expected[-1].get(field), native.get(field)
        if a is not None and b is not None and not near(a, b):
            errors.append({"field": field, "expected": a, "actual": b})
    if len(observed_fills) != len(fills):
        errors.append(
            {
                "field": "fill_trace_count",
                "native": len(fills),
                "trace": len(observed_fills),
            }
        )
    for i, (a, b) in enumerate(zip(observed_fills, fills)):
        if a["session"] != b["session"] or any(
            not near(a[k], b[k]) for k in ["qty", "price", "fee"]
        ):
            errors.append({"field": "fill_trace_reconciliation", "fill": i})
    # Account at every observed bar, including the native daily result for minute CTA data.
    by_session = {r["session"]: r for r in expected}
    accounts = {e["session"]: e for e in result["events"] if e["kind"] == "account"}
    for e in accounts.values():
        for field in ["cash", "equity", "position"]:
            a, b = by_session[e["session"]].get(field), e.get(field)
            if a is not None and b is not None and not near(a, b):
                errors.append(
                    {
                        "field": field,
                        "session": e["session"],
                        "expected": a,
                        "actual": b,
                    }
                )
    return {
        "status": "fail" if errors else "pass" if fills else "inconclusive",
        "fills": len(fills),
        "errors": errors[:8],
        "error_count": len(errors),
        "meaning": "Reconciles native fills, declared fees and cash/PnL ledger; does not prove strategy intent or market realism.",
    }


def observations(result, last_session):
    values = {}
    fills = []
    orders = []
    terminal_ids = {
        e["order_id"]
        for e in result.get("events", [])
        if e["kind"] == "fill"
        and e.get("order_id") is not None
        and (e.get("exit_reason") == "force_exit" or e.get("phase") == "finalize")
    }
    for e in result.get("events", []):
        if e["session"] > last_session:
            continue
        if e["kind"] == "indicator":
            values[e["session"] + "|indicator|" + e["name"]] = e["value"]
        elif e["kind"] == "signal":
            values[e["session"] + "|entry"] = e.get("signal")
            if "exit_signal" in e:
                values[e["session"] + "|exit"] = e["exit_signal"]
        elif (
            e["kind"] == "order"
            and e.get("order_id") not in terminal_ids
            and e.get("phase") != "finalize"
        ):
            orders.append(
                (e["session"], e.get("qty"), e.get("order_type"), e.get("price"))
            )
    for row in result.get("native", {}).get("indicators", []):
        if row["session"] <= last_session:
            for name, value in row["values"].items():
                values[row["session"] + "|indicator|" + name] = value
    terminal_fills = {
        (e["session"], e.get("qty"), e.get("price"), e.get("fee"))
        for e in result.get("events", [])
        if e.get("kind") == "fill"
        and (e.get("exit_reason") == "force_exit" or e.get("phase") == "finalize")
    }
    for f in result.get("native", {}).get("fills", []):
        if (
            f["session"] <= last_session
            and f.get("exit_reason") != "force_exit"
            and not f.get("terminal", False)
            and (f["session"], f["qty"], f["price"], f["fee"]) not in terminal_fills
        ):
            fills.append({k: f[k] for k in ["session", "qty", "price", "fee"]})
    return values, fills, orders


def prefix_check(full, prefix, bars, count):
    if full["status"] != "ok" or prefix["status"] != "ok":
        return {
            "status": "inconclusive",
            "reason": prefix.get("error") or full.get("error"),
            "full_status": full["status"],
            "prefix_status": prefix["status"],
        }
    # Compare indicators/signals through the decision boundary. Only explicitly
    # identified forced terminal fills/orders are excluded by observations().
    last = bars[count - 1]["date"]
    a, af, ao = observations(full, last)
    b, bf, bo = observations(prefix, last)
    if not any(v is not None for v in a.values()) and not af and not ao:
        return {
            "status": "inconclusive",
            "reason": "No meaningful indicator, signal, order or fill observations through the cutoff",
            "difference_count": 0,
        }
    differences = []
    for key in sorted(a.keys() | b.keys()):
        if key not in a or key not in b or not near(a.get(key), b.get(key)):
            differences.append(
                {"observation": key, "full": a.get(key), "prefix": b.get(key)}
            )
    if af != bf:
        differences.append(
            {
                "observation": "native_fill_sequence",
                "full_count": len(af),
                "prefix_count": len(bf),
                "full_first": af[:3],
                "prefix_first": bf[:3],
            }
        )
    if ao != bo:
        differences.append(
            {
                "observation": "order_sequence",
                "full_count": len(ao),
                "prefix_count": len(bo),
            }
        )
    return {
        "status": "fail" if differences else "pass",
        "compared_through": last,
        "prefix_bars": count,
        "observable_values": len(a),
        "fill_count": len(af),
        "order_count": len(ao),
        "difference_count": len(differences),
        "examples": differences[:5],
        "full_run_id": full["run_id"],
        "prefix_run_id": prefix["run_id"],
        "scope": "Selected indicators, entry/exit signals and native order/fill prefixes; hidden internal state is not fully observed.",
    }


def conformance_check(full, plain):
    if full["status"] != "ok" or plain["status"] != "ok":
        return {
            "status": "inconclusive",
            "reason": plain.get("error") or full.get("error"),
        }
    a, b = full["native"], plain["native"]
    ok = all(
        near(a.get(k), b.get(k)) for k in ["cash", "equity", "position"]
    ) and a.get("fills") == b.get("fills")
    return {
        "status": "pass" if ok else "fail",
        "plain_run_id": plain["run_id"],
        "meaning": "Observation toggle preserves native final account and every native fill.",
    }


def short(result):
    native = result.get("native", {})
    return {
        "status": result["status"],
        "error": result.get("error"),
        "run_id": result["run_id"],
        "runtime_image": result.get("runtime_image"),
        "equity": native.get("equity"),
        "position": native.get("position"),
        "fills": len(native.get("fills", [])),
        "trades": native.get("trade_count", native.get("closed_trade_count")),
        "elapsed_seconds": result.get("elapsed_seconds"),
    }


def indicator_preservation(spec, original, candidate):
    """Compare against immutable original observations, not candidate-defined truth."""
    allowed = set(spec.get("repair_policy", {}).get("mutable_indicators", []))
    old = observations(original, "9999")[0]
    new = observations(candidate, "9999")[0]
    keys = {
        key
        for key in old.keys() | new.keys()
        if "|indicator|" in key and key.rsplit("|", 1)[-1] not in allowed
    }
    errors = [
        key
        for key in sorted(keys)
        if key not in old or key not in new or not near(old[key], new[key])
    ]
    return {
        "status": "fail" if errors else "pass",
        "protected_values": len(keys),
        "exceptions": sorted(allowed),
        "difference_count": len(errors),
        "examples": errors[:8],
    }


class Evaluation:
    """One native execution cache and validator for every entry point."""

    def __init__(self, runner, folder, policy=None):
        self.runner = runner
        self.folder = Path(folder)
        self.policy = policy or {}

    def native(self, project, **options):
        identity = execution_identity(
            project, self.runner.runtime, {"mode": self.runner.mode, "options": options}
        )
        path = self.folder / "native" / identity["key"] / "receipt.json"
        if path.exists():
            result = load_json(path)
            if result["execution_identity"] != identity:
                raise ValueError("Native cache identity mismatch")
            return result["result"]
        result = self.runner.run(project, **options)
        # Failures remain receipts too. Retrying requires an explicit new attempt.
        atomic_json(path, {"execution_identity": identity, "result": result})
        return result

    def probe(self, project, full=None, fraction=None, kind="future"):
        bars = read_bars(Path(project) / "fixtures/bars.csv")
        count = max(
            2,
            min(
                len(bars) - 1,
                int(len(bars) * (fraction or self.policy.get("cutoff_fraction", 0.5))),
            ),
        )
        full = full or self.native(project)
        if full["status"] != "ok":
            return {
                "status": "inconclusive",
                "reason": full.get("error"),
                "full_status": full["status"],
            }
        changed = (
            bars[:count]
            if kind == "prefix"
            else future_perturbation(bars, count - 1, seed=0)
        )
        other = self.native(project, bars=changed)
        check = prefix_check(full, other, bars, count)
        check.update(
            source_sha256=digest(Path(project) / "strategy.py"),
            probe=kind,
            fixture_kind="historical_prefix"
            if kind == "prefix"
            else "diagnostic_future_transformation",
            cutoff_index=count - 1,
        )
        return check

    def check(self, project, original=None, original_full=None, extra_probes=()):
        project = Path(project)
        original = Path(original or project)
        spec = load_json(project / "task.json")
        bars = read_bars(project / "fixtures/bars.csv")
        full = self.native(project)
        preservation = check_preservation(
            original / "strategy.py", project / "strategy.py", spec.get("repair_policy")
        )
        if (
            original_full is not None
            and original_full.get("status") == "ok"
            and full["status"] == "ok"
        ):
            preservation["indicators"] = indicator_preservation(
                spec, original_full, full
            )
            if preservation["indicators"]["status"] != "pass":
                preservation["status"] = "fail"
        result = {
            "source_sha256": digest(project / "strategy.py"),
            "baseline": short(full),
            "financial": financial_check(spec, bars, full),
            "invariants": check_contract(spec, bars, full),
            "causality": self.probe(project, full),
            "preservation": preservation,
        }
        additional = [
            {
                **probe,
                "result": self.probe(
                    project, full, fraction=probe["fraction"], kind=probe["kind"]
                ),
            }
            for probe in extra_probes
        ]
        if additional:
            result["causality"]["additional_probes"] = additional
            statuses = [
                result["causality"]["status"],
                *[p["result"]["status"] for p in additional],
            ]
            result["causality"]["status"] = (
                "fail"
                if "fail" in statuses
                else "pass"
                if all(s == "pass" for s in statuses)
                else "inconclusive"
            )
        if self.policy.get("conformance", False):
            result["conformance"] = conformance_check(
                full, self.native(project, instrument=False)
            )
            if result["conformance"]["status"] != "pass":
                result["invariants"]["status"] = "inconclusive"
                result["invariants"]["reason"] = "Observer conformance did not pass"
        statuses = [
            result[name]["status"]
            for name in ("financial", "invariants", "causality", "preservation")
        ]
        result["status"] = (
            "fail"
            if "fail" in statuses
            else "pass"
            if all(s == "pass" for s in statuses)
            else "inconclusive"
        )
        return result, full
