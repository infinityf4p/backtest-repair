"""Frozen corpus execution: one episode per source, later data never in prompts."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from .contracts import load_json, digest
from .store import atomic_json
from . import workflow


def verify_catalog(root):
    root = Path(root)
    sources = load_json(root / "sources.json")
    seen = set()
    for source in sources:
        if source["id"] in seen:
            raise ValueError("Duplicate strategy id")
        seen.add(source["id"])
        case = root / "cases" / source["id"]
        if digest(case / "strategy.py") != source["candidate_sha256"]:
            raise ValueError("Frozen upstream candidate changed: " + source["id"])
    manifest = root / "evaluation" / "inputs.json"
    if manifest.exists():
        for name, sha in load_json(manifest).items():
            from .contracts import safe_path

            if digest(safe_path(root, name)) != sha:
                raise ValueError("Frozen evaluation input changed: " + name)
    return sources


def run(root, runtime, output, action="all", selected=None, jobs=1, mode="docker"):
    root = Path(root).resolve()
    output = Path(output).resolve()
    sources = verify_catalog(root)
    if selected:
        if set(selected) - {s["id"] for s in sources}:
            raise ValueError("Unknown case")
        sources = [s for s in sources if s["id"] in selected]
    options = load_json(root / "protocol.json")

    def one(source):
        ident = source["id"]
        project = root / "cases" / ident
        settings = {**options, "conformance": source.get("conformance", False)}
        result = {"case": ident}
        if action in {"baseline", "all"}:
            result["baseline"] = workflow.baseline(
                project, runtime, output, settings, mode
            )["report"]
        if action in {"agents", "repair", "all"}:
            result["episode"] = workflow.repair(
                project, runtime, output, settings, mode
            )
        if action in {"holdout", "all"}:
            result["holdout"] = workflow.holdout(
                project, root / "holdout" / ident, runtime, output, settings, mode
            )
        print(
            __import__("json").dumps(
                {"case": ident, "action": action, "completed": True}
            ),
            flush=True,
        )
        return result

    with ThreadPoolExecutor(max_workers=max(1, min(3, jobs))) as pool:
        results = list(pool.map(one, sources))
    # A selected subset has its own index and cannot overwrite a full-suite report.
    from .identity import stable_hash

    index = (
        output
        / "indexes"
        / (action + "-" + stable_hash([s["id"] for s in sources])[:12] + ".json")
    )
    atomic_json(index, results)
    return results
