"""Host-owned submission decisions. Model labels never override measured checks."""

from __future__ import annotations


REQUIRED_CHECKS = ("financial", "invariants", "causality", "preservation")


def validate_submission(
    diagnosis, original_hash, candidate_hash, checked_hash, report, required_probes=()
):
    if diagnosis not in {
        "observed_no_violation",
        "repaired",
        "inconclusive",
        "needs_spec",
        "infrastructure_blocked",
    }:
        raise ValueError("Unknown diagnosis")
    changed = candidate_hash != original_hash
    if diagnosis in {"needs_spec", "infrastructure_blocked", "inconclusive"}:
        if changed:
            raise ValueError(
                "An unverified modified candidate cannot be a completed submission"
            )
        return {"status": diagnosis, "accepted": False}
    if diagnosis == "repaired" and not changed:
        raise ValueError("Repaired requires an actual source change")
    if diagnosis == "observed_no_violation" and changed:
        raise ValueError("No-violation submission must preserve the original source")
    if checked_hash != candidate_hash:
        raise ValueError("Submission has not been checked at this exact source hash")
    if report.get("baseline", {}).get("status") != "ok":
        raise ValueError("Native execution has not completed successfully")
    failed = [
        name for name in REQUIRED_CHECKS if report.get(name, {}).get("status") != "pass"
    ]
    if failed:
        raise ValueError("Submission requires passing checks: " + ", ".join(failed))
    measured = {}
    for item in report.get("causality", {}).get("additional_probes", []):
        key = (item["kind"], item["fraction"])
        result = item["result"]
        if (
            result.get("status") != "pass"
            or result.get("source_sha256") != candidate_hash
        ):
            raise ValueError(
                "An additional experiment failed, is inconclusive, or belongs to an older candidate"
            )
        measured[key] = result
    if any((p["kind"], p["fraction"]) not in measured for p in required_probes):
        raise ValueError(
            "Check the current candidate against every requested experiment before submitting"
        )
    return {"status": diagnosis, "accepted": True}
