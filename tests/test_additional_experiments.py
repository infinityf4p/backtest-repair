"""A later/default passing probe must not erase an earlier counterexample."""

import pytest
from backtest_repair.acceptance import validate_submission
from backtest_repair.validation import Evaluation


def passing():
    return {
        "baseline": {"status": "ok"},
        **{
            k: {"status": "pass"}
            for k in ("financial", "invariants", "causality", "preservation")
        },
    }


@pytest.mark.parametrize(
    "status,source", [("fail", "new"), ("inconclusive", "new"), ("pass", "old")]
)
def test_default_success_cannot_override_a_failed_or_stale_extra_probe(status, source):
    report = passing()
    report["causality"]["additional_probes"] = [
        {
            "kind": "future",
            "fraction": 0.75,
            "result": {"status": status, "source_sha256": source},
        }
    ]
    with pytest.raises(ValueError):
        validate_submission("repaired", "old", "new", "new", report)


def test_unchecked_requested_experiment_blocks_submission():
    report = passing()
    required = [{"kind": "prefix", "fraction": 0.75}]
    with pytest.raises(ValueError):
        validate_submission("repaired", "old", "new", "new", report, required)
    report["causality"]["additional_probes"] = [
        {**required[0], "result": {"status": "pass", "source_sha256": "new"}}
    ]
    assert validate_submission("repaired", "old", "new", "new", report, required)[
        "accepted"
    ]


def test_check_replays_the_discovered_cutoff_on_repaired_code(tmp_path, monkeypatch):
    from backtest_repair import validation
    from backtest_repair.contracts import dump_json

    (tmp_path / "strategy.py").write_text("x = 1\n", encoding="utf-8")
    dump_json(tmp_path / "task.json", {})
    monkeypatch.setattr(validation, "read_bars", lambda path: [{"date": "2024-01-01"}])
    monkeypatch.setattr(validation, "financial_check", lambda *args: {"status": "pass"})
    monkeypatch.setattr(validation, "check_contract", lambda *args: {"status": "pass"})
    evaluator = Evaluation(None, tmp_path)
    monkeypatch.setattr(
        evaluator,
        "native",
        lambda *a, **k: {"status": "ok", "run_id": "full", "native": {}},
    )
    calls = []

    def probe(project, full=None, fraction=None, kind="future"):
        calls.append((kind, fraction))
        return {
            "status": "fail" if fraction == 0.75 else "pass",
            "source_sha256": "current",
        }

    monkeypatch.setattr(evaluator, "probe", probe)
    report, _ = evaluator.check(
        tmp_path, extra_probes=[{"kind": "future", "fraction": 0.75}]
    )
    assert calls == [("future", None), ("future", 0.75)]
    assert report["causality"]["status"] == "fail" and report["status"] == "fail"
