import base64
import gzip
import json
from pathlib import Path
import pytest

from backtest_repair.store import locked, recorded_call, UncertainCall
from backtest_repair.transport import decode_frame
from backtest_repair.workflow import replace_transaction
from backtest_repair.validation import indicator_preservation
from backtest_repair.rules import check_contract
from backtest_repair.suite import verify_catalog
from backtest_repair.preservation import check_preservation


def test_unknown_model_usage_is_never_automatically_rebilled(tmp_path):
    calls = []

    def disconnected():
        calls.append(1)
        raise TimeoutError("connection lost after sending request")

    with pytest.raises(UncertainCall):
        recorded_call(tmp_path, {"prompt": "test"}, disconnected)
    with pytest.raises(UncertainCall):
        recorded_call(tmp_path, {"prompt": "test"}, disconnected)
    assert len(calls) == 1
    assert json.loads((tmp_path / "failure.json").read_text())["usage_known"] is False


def test_durable_response_is_reused_and_cannot_be_attached_to_another_prompt(tmp_path):
    calls = []

    def invoke():
        calls.append(1)
        return {"usage": {"input_tokens": 4, "output_tokens": 2}}

    first = recorded_call(tmp_path, {"prompt": "one"}, invoke)
    assert recorded_call(tmp_path, {"prompt": "one"}, invoke) == first
    with pytest.raises(ValueError):
        recorded_call(tmp_path, {"prompt": "two"}, invoke)
    assert len(calls) == 1


def test_process_lock_prevents_concurrent_execution(tmp_path):
    with locked(tmp_path):
        with pytest.raises(RuntimeError):
            with locked(tmp_path):
                pass
    with locked(tmp_path):
        pass


def test_edit_recovery_does_not_apply_nonidempotent_replacement_twice(tmp_path):
    path = tmp_path / "strategy.py"
    original = tmp_path / "original.py"
    path.write_text("x = 1\n", encoding="utf-8")
    original.write_text("x = 1\n", encoding="utf-8")
    action = {"tool": "replace", "old": "1", "new": "11"}
    first = replace_transaction(path, original, action, tmp_path / "edit.json")
    assert replace_transaction(path, original, action, tmp_path / "edit.json") == first
    assert path.read_text() == "x = 11\n"


def frame(value):
    return (
        b"BTR_GZIP:"
        + base64.b64encode(gzip.compress(json.dumps(value).encode()))
        + b"\n"
    )


def test_forged_or_ambiguous_worker_frames_are_rejected():
    packet = frame({"status": "ok", "request_id": "real", "native": {}, "events": []})
    assert decode_frame(packet, "real")["status"] == "ok"
    for invalid in [
        packet + packet,
        packet + b"BTR_RESULT:e30=\n",
        packet.replace(b"BTR_GZIP:", b"junk:"),
    ]:
        with pytest.raises(ValueError):
            decode_frame(invalid, "real")
    with pytest.raises(ValueError):
        decode_frame(packet, "another-request")


def test_candidate_cannot_redefine_its_own_indicator_oracle():
    original = {
        "events": [],
        "native": {
            "indicators": [
                {"session": "2024-01-01", "values": {"adx": 30, "mean-volume": 20}}
            ]
        },
    }
    candidate = {
        "events": [],
        "native": {
            "indicators": [
                {"session": "2024-01-01", "values": {"adx": 0, "mean-volume": 15}}
            ]
        },
    }
    check = indicator_preservation(
        {"repair_policy": {"mutable_indicators": ["mean-volume"]}}, original, candidate
    )
    assert check["status"] == "fail" and check["difference_count"] == 1


def test_no_trade_coverage_is_not_a_pass():
    bars = [{"date": "2024-01-01"}]
    result = {
        "status": "ok",
        "native": {"fills": []},
        "events": [
            {"kind": "decision", "seq": 0, "bar_index": 0, "session": "2024-01-01"}
        ],
    }
    assert (
        check_contract({"engine": "backtrader"}, bars, result)["status"]
        == "inconclusive"
    )


def test_broken_trace_is_rejected_even_when_trades_exist():
    result = {
        "status": "ok",
        "native": {"fills": [{}]},
        "events": [
            {"kind": "decision", "seq": 0, "bar_index": 9, "session": "2024-01-01"}
        ],
    }
    assert (
        check_contract({"engine": "backtrader"}, [{"date": "2024-01-01"}], result)[
            "status"
        ]
        == "fail"
    )


def test_protected_indicator_calculation_and_new_unsafe_code(tmp_path):
    original = tmp_path / "original.py"
    candidate = tmp_path / "candidate.py"
    original.write_text(
        "def calculate(x):\n    y = x * 2\n    return y\n", encoding="utf-8"
    )
    candidate.write_text(
        "def calculate(x):\n    y = x * 0\n    return y\n", encoding="utf-8"
    )
    policy = {"editable_methods": ["calculate"], "protected_fragments": ["y = x * 2"]}
    assert check_preservation(original, candidate, policy)["status"] == "fail"
    candidate.write_text(
        "def calculate(x):\n    y = x * 2\n    exec(x)\n    return y\n",
        encoding="utf-8",
    )
    assert check_preservation(original, candidate, policy)["status"] == "fail"


def test_twenty_published_distinct_sources_are_frozen_with_later_holdouts():
    root = Path(__file__).resolve().parents[1]
    sources = verify_catalog(root)
    assert len(sources) == 20
    assert len({s["candidate_sha256"] for s in sources}) == 20
    assert {s["engine"] for s in sources} == {
        "backtrader",
        "backtesting_py",
        "vnpy_cta",
        "rqalpha",
        "freqtrade",
    }
    from backtest_repair.contracts import read_bars

    for source in sources:
        visible = read_bars(root / "cases" / source["id"] / "fixtures/bars.csv")
        later = read_bars(root / "holdout" / source["id"] / "bars.csv")
        assert later[0]["date"] > visible[-1]["date"]
        assert (root / "provenance" / source["id"] / "LICENSE").exists()
