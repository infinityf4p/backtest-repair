"""Content identities for public inputs, pinned runtimes, policy and checker code."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

from .contracts import digest, load_json, safe_path, validate_spec


def stable_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def public_manifest(project):
    project = Path(project)
    spec = validate_spec(load_json(project / "task.json"))
    names = {"task.json", "fixtures/bars.csv", "fixtures/warmup.csv", "fixtures/releases.csv", *spec["modifiable_files"], *spec.get("public_files", [])}
    return {name: digest(safe_path(project, name)) if safe_path(project, name).is_file() else None for name in sorted(names)}


def checker_identity(extra_files=()):
    package = Path(__file__).resolve().parent
    files = {p.relative_to(package).as_posix(): digest(p) for p in sorted(package.rglob("*.py"))}
    files.update({"external/" + Path(p).name: digest(p) for p in extra_files if Path(p).is_file()})
    return stable_hash(files)


def execution_identity(project, runtime, policy=None, extra_files=()):
    spec = load_json(Path(project) / "task.json")
    values = {"inputs": public_manifest(project), "runtime": runtime.get(spec["engine"], {}), "worker_timeout": runtime.get("worker_timeout"), "policy": policy or {}, "checker": checker_identity(extra_files)}
    # A runtime entry must contain only a pinned image/local interpreter path, never credentials.
    values["runtime"] = {k: v for k, v in values["runtime"].items() if k in {"image", "python"}}
    return {"key": stable_hash(values), **values}


def reuse_completed(path, identity, candidate=None):
    path = Path(path)
    if not path.exists():
        return None
    result = load_json(path)
    if result.get("execution_identity", {}).get("key") != identity["key"]:
        raise ValueError("Cached input identity changed; preserve this result and use a new execution directory")
    if candidate is not None and result.get("submitted_sha256") != digest(candidate):
        raise ValueError("Previously submitted candidate changed after validation")
    return result
