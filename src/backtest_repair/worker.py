"""Single request per process. Only public input and the adapter package are needed."""

import importlib
import importlib.metadata
from pathlib import Path
import random
import sys
import traceback

from .contracts import DISTRIBUTIONS, dump_json, load_json, read_bars, validate_spec, digest, safe_path
from .trace import Recorder
from . import fixture_api


def main():
    import faulthandler

    faulthandler.enable()
    faulthandler.dump_traceback_later(45, repeat=False)
    request = load_json(sys.argv[1])
    output = Path(sys.argv[2])
    try:
        expected=request.get('input_manifest',{})
        before={name:digest(safe_path(Path.cwd(),name)) for name in expected}
        if before!=expected: raise ValueError('Public input hashes do not match request')
        spec = validate_spec(request["spec"])
        version = importlib.metadata.version(DISTRIBUTIONS[spec["engine"]])
        if version != spec["framework_version"]:
            raise RuntimeError(
                f"Framework version mismatch: installed {version}, required {spec['framework_version']}"
            )
        random.seed(request.get("seed", 0))
        import numpy as np

        np.random.seed(request.get("seed", 0))
        sys.path.insert(0, str(Path.cwd()))
        bars = read_bars("fixtures/bars.csv")
        recorder = Recorder(spec, bars, request.get("instrument", True))
        fixture_api.configure(recorder, "fixtures/releases.csv")
        operation = request.get("operation", "backtest")
        if operation not in {"backtest", "freqtrade_lookahead"} or (
            operation == "freqtrade_lookahead" and spec["engine"] != "freqtrade"
        ):
            raise ValueError("Unsupported native operation")
        adapter_name = (
            "freqtrade_analysis"
            if operation == "freqtrade_lookahead"
            else spec["engine"]
        )
        adapter = importlib.import_module("backtest_repair.adapters." + adapter_name)
        native = adapter.run(spec, bars, recorder)
        after={name:digest(safe_path(Path.cwd(),name)) for name in expected}
        if after!=expected: raise ValueError('Strategy modified declared public inputs during execution')
        dump_json(
            output,
            {
                "status": "ok",
                "request_id": request.get('request_id'),
                "input_integrity": {"status":"pass","files":len(expected)},
                "engine": spec["engine"],
                "version": version,
                "events": recorder.events,
                "native": native,
                "packages": {
                    d.metadata["Name"]: d.version
                    for d in importlib.metadata.distributions()
                },
            },
        )
    except Exception as exc:
        dump_json(
            output,
            {
                "status": getattr(exc, "status", "execution_error"),
                "request_id": request.get('request_id'),
                "error": str(exc),
                "traceback": traceback.format_exc(),
                "events": [],
            },
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
