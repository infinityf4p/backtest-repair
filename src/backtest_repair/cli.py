from __future__ import annotations
import argparse
import ast
import getpass
import json
import os
from pathlib import Path
import sys
from .contracts import (
    load_json,
    validate_spec,
    read_bars,
    capabilities,
    ContractError,
)


def detect(project):
    findings = []
    for path in Path(project).rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        except (SyntaxError, UnicodeError):
            continue
        imports = {}
        for n in tree.body:
            if isinstance(n, ast.Import):
                for a in n.names:
                    imports[a.asname or a.name] = a.name
            if isinstance(n, ast.ImportFrom):
                for a in n.names:
                    imports[a.asname or a.name] = (n.module or "") + "." + a.name
        for n in tree.body:
            if isinstance(n, ast.ClassDef):
                for base in n.bases:
                    parts = ast.unparse(base).split(".")
                    resolved = (
                        imports.get(parts[0], parts[0]) + "." + ".".join(parts[1:])
                        if len(parts) > 1
                        else imports.get(parts[0], parts[0])
                    )
                    engine = next(
                        (
                            e
                            for key, e in [
                                ("backtrader.Strategy", "backtrader"),
                                ("backtrader.SignalStrategy", "backtrader"),
                                ("backtesting.Strategy", "backtesting_py"),
                                ("backtesting.lib.SignalStrategy", "backtesting_py"),
                                ("backtesting.lib.TrailingStrategy", "backtesting_py"),
                                ("vnpy_ctastrategy.CtaTemplate", "vnpy_cta"),
                                ("freqtrade.strategy.IStrategy", "freqtrade"),
                            ]
                            if key == resolved
                        ),
                        None,
                    )
                    if engine:
                        findings.append(
                            {
                                "file": path.relative_to(project).as_posix(),
                                "engine": engine,
                                "class": n.name,
                            }
                        )
        hooks = {
            n.name
            for n in tree.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        if {"init", "handle_bar"} <= hooks:
            findings.append(
                {
                    "file": path.relative_to(project).as_posix(),
                    "engine": "rqalpha",
                    "module": path.stem,
                }
            )
    return {
        "candidates": list({(item["file"],item["engine"],item.get("class")):item for item in findings}.values()),
        "note": "Structural detection only. Public financial specification and pinned native validation are still required.",
    }


def credential_prompt(runtime, mode):
    if mode != "ssh_docker":
        return
    config = load_json(runtime)
    remote = config.get("remote", {})
    env_name = remote.get("password_env", "BTR_SSH_PASSWORD")
    if (
        remote.get("transport") == "paramiko"
        and not remote.get("identity")
        and not os.environ.get(env_name)
    ):
        os.environ[env_name] = getpass.getpass("SSH password (memory only): ")


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="btr",
        description="Native structured-strategy counterexample and repair harness",
    )
    sub = p.add_subparsers(dest="command", required=True)
    for name in ("validate", "inspect", "detect"):
        item = sub.add_parser(name)
        item.add_argument("project", type=Path)
    for name in ("run", "repair"):
        item = sub.add_parser(name)
        item.add_argument("project", type=Path)
        item.add_argument("--runtime", required=True, type=Path)
        item.add_argument("--output", required=True, type=Path)
        item.add_argument(
            "--mode", choices=["local", "docker", "ssh_docker"], default="docker"
        )
        item.add_argument("--seed", type=int, default=0)
        if name == "repair":
            item.add_argument("--method", choices=["B3"], default="B3")
            item.add_argument("--model", default="gpt-6-astra")
            item.add_argument("--effort", default="max")
            item.add_argument(
                "--limits",
                type=Path,
                help="JSON with a limits object, or a plain limits mapping",
            )
    suite = sub.add_parser("suite")
    suite.add_argument("root", type=Path)
    suite.add_argument("--runtime", required=True, type=Path)
    suite.add_argument("--output", required=True, type=Path)
    suite.add_argument(
        "--action", choices=["baseline", "agents", "holdout", "all"], default="all"
    )
    suite.add_argument("--case", action="append")
    suite.add_argument("--jobs", type=int, default=1)
    suite.add_argument(
        "--mode", choices=["local", "docker", "ssh_docker"], default="docker"
    )
    report = sub.add_parser("report")
    report.add_argument("path", type=Path, help="Episode directory or aggregate.json")
    report.add_argument("--output", type=Path)
    a = p.parse_args(argv)
    try:
        if a.command == "suite":
            from .suite import run

            credential_prompt(a.runtime, a.mode)
            result = run(
                a.root, load_json(a.runtime), a.output, a.action, a.case, a.jobs, a.mode
            )
        elif a.command == "detect":
            result = detect(a.project.resolve())
        elif a.command in {"validate", "inspect"}:
            spec = validate_spec(load_json(a.project / "task.json"))
            bars = read_bars(a.project / "fixtures/bars.csv")
            result = {
                "status": "valid",
                "spec": spec,
                "bars": len(bars),
                "capabilities": capabilities(spec),
            }
        elif a.command == "run":
            from .workflow import baseline

            credential_prompt(a.runtime, a.mode)
            result = baseline(a.project, load_json(a.runtime), a.output, mode=a.mode)[
                "report"
            ]
        elif a.command == "repair":
            from .agent import run_episode

            credential_prompt(a.runtime, a.mode)
            limits = load_json(a.limits) if a.limits else {}
            result = run_episode(
                a.project,
                a.runtime,
                a.output,
                a.method,
                a.seed,
                a.mode,
                a.model,
                a.effort,
                limits.get("limits", limits),
            )

        else:
            from .reporting import workflow_report

            target = workflow_report(a.path, a.output)
            result = {"report": str(target)}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if a.command in {"run", "repair"} and result.get("status") not in {
            "ok",
            "submitted",
            "pass",
            "repaired",
            "observed_no_violation",
        }:
            return 2 if result.get("status") in {"needs_spec", "out_of_scope"} else 1
        return 0
    except ContractError as exc:
        print(json.dumps({"status": exc.status, "error": str(exc)}, ensure_ascii=False))
        return 2
    except (OSError, ValueError, RuntimeError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    sys.exit(main())
