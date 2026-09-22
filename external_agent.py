"""Compatibility facade for the single package workflow."""
from pathlib import Path
from backtest_repair import workflow
from backtest_repair.contracts import load_json
ROOT=Path(__file__).resolve().parent

def episode(ident,runtime):
    return workflow.repair(ROOT/"cases"/ident,runtime,ROOT/"results",load_json(ROOT/"protocol.json"),"ssh_docker")

def holdout(ident,runtime):
    return workflow.holdout(ROOT/"cases"/ident,ROOT/"holdout"/ident,runtime,ROOT/"results",load_json(ROOT/"protocol.json"),"ssh_docker")
