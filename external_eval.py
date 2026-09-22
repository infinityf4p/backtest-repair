"""Compatibility facade; all acceptance and native checks live in the package."""
from pathlib import Path
from backtest_repair.validation import financial_check, prefix_check, observations, conformance_check, short, near
from backtest_repair import workflow
from backtest_repair.contracts import load_json
from backtest_repair.suite import run
ROOT=Path(__file__).resolve().parent

def baseline(ident,runtime,tag="baseline"):
    return workflow.baseline(ROOT/"cases"/ident,runtime,ROOT/"results",load_json(ROOT/"protocol.json"),"ssh_docker")

def main(action,runtime,selected=None):
    return run(ROOT,runtime,ROOT/"results", "baseline" if action.startswith("baseline") else action,selected,jobs=2,mode="ssh_docker")
