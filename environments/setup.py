"""Install pinned native workers without changing the system Python environment."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
ENGINES = ("core", "backtrader", "backtesting_py", "vnpy_cta", "rqalpha", "freqtrade")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT / ".runtime")
    parser.add_argument("--python", default="3.11.13")
    parser.add_argument("--engine", action="append", choices=ENGINES)
    parser.add_argument("--output", type=Path, default=ROOT / "runtime.local.json")
    args = parser.parse_args()
    uv = shutil.which("uv")
    if not uv:
        raise SystemExit(
            "Install uv, then rerun: https://docs.astral.sh/uv/getting-started/installation/"
        )
    args.root = args.root.resolve()
    config = {"worker_timeout": 180}
    for engine in args.engine or ENGINES:
        environment = args.root / engine
        python = environment / (
            "Scripts/python.exe" if os.name == "nt" else "bin/python"
        )
        if not python.exists():
            subprocess.run(
                [uv, "venv", "--python", args.python, str(environment)], check=True
            )
        lock = (
            ROOT
            / "environments"
            / engine
            / ("windows-py311.lock" if os.name == "nt" else "linux-py311.lock")
        )
        command = [uv, "pip", "sync", "--python", str(python), str(lock)]
        if os.name != "nt":
            command += ["--require-hashes"]
        subprocess.run(command, check=True)
        if engine == "core":
            subprocess.run(
                [
                    uv,
                    "pip",
                    "install",
                    "--python",
                    str(python),
                    "--no-build-isolation",
                    "-e",
                    str(ROOT),
                ],
                check=True,
            )
        else:
            config[engine] = {
                "python": str(python),
                "image": "backtest-repair/" + engine + ":0.1.0",
            }
    if args.output.exists():
        config = {**json.loads(args.output.read_text(encoding="utf-8")), **config}
    args.output.write_text(json.dumps(config, indent=2), encoding="utf-8")
    print("Runtime configuration: " + str(args.output))


if __name__ == "__main__":
    main()
