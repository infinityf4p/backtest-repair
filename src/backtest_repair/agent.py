"""Compatibility facade for the unified workflow (historical B1/B2 study is archived)."""
from pathlib import Path
from .contracts import load_json
from .workflow import repair


def run_episode(project,runtime,output,method="B3",seed=0,mode="local",model="gpt-6-astra",effort="max",limits=None,client=None):
    if method!="B3" or seed!=0:
        raise ValueError("Current workflow uses one evidence-driven episode and seed 0; historical ablations are archived")
    names={"decisions":"max_model_decisions","runs":"max_native_runs","seconds":"max_seconds","tokens":"max_tokens_per_episode","output_tokens":"max_output_tokens_per_call"}
    options={names.get(k,k):v for k,v in (limits or {}).items()}
    options.update(model=model,reasoning_effort=effort)
    runtime=load_json(runtime) if isinstance(runtime,(str,Path)) else runtime
    return repair(project,runtime,output,options,mode,client)
