from __future__ import annotations
import json
from pathlib import Path
import time
from .contracts import dump_json
from .model import ResponsesClient
from .runner import Runner, Budget, BudgetExhausted, project_hash, copy_public_project
from .tools import ToolBox, TOOL_HELP

METHODS = {
    "B1": "You are a coding agent. Inspect the structured strategy project, use tools as needed, and fix only actual violations of the public specification. Choose your own working approach.",
    "B2": "You are a coding agent following a fixed diagnostic workflow. First inspect the supplied fixed suite results (visible, gap, flat, future). Then diagnose, shrink a reproducible failed check if useful, patch, run visible regression, and submit. Do not add unrelated experiments before reviewing the fixed suite.",
    "B3": "You are a coding agent diagnosing backtest faults by discriminating between candidate causes. Start with reproduction, list brief falsifiable hypotheses, and adaptively choose a probe that distinguishes them. Link conclusions to observed evidence. Shrink a reproducible counterexample when it will clarify the fix; then patch, verify visible regressions, and submit. Stop experiments that add no information.",
}


def enforce_usage(usage, limit):
    """Account for the whole provider response before allowing any actions.

    A relay can add input tokens that cannot be limited with max_output_tokens.
    Such usage is recorded, but an over-budget reply can never submit a repair.
    """
    total = usage["input_tokens"] + usage["output_tokens"]
    if total > limit:
        raise BudgetExhausted(
            f"Provider usage {total} exceeded episode token allowance {limit}"
        )
    return total


def compact_history(messages, keep_recent=4):
    """Keep all assistant hypotheses/patches and bounded old tool observations.

    Full responses remain in JSONL. This deterministic policy is identical for
    B1/B2/B3; the agent can inspect files or rerun any missing observation.
    """
    for message in messages[2:-keep_recent]:
        if message["role"] == "user" and len(message["content"]) > 4000:
            text = message["content"]
            message["content"] = (
                text[:3000]
                + "\n[Older tool observation abbreviated; complete evidence remains in run artifacts.]\n"
                + text[-800:]
            )
    return messages


def parse_actions(text):
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    value = json.loads(text)
    if (
        not isinstance(value, dict)
        or not isinstance(value.get("actions"), list)
        or len(value["actions"]) > 6
    ):
        raise ValueError("Return a JSON object with an actions array (at most six)")
    if any(
        not isinstance(a, dict)
        or not isinstance(a.get("tool"), str)
        or not isinstance(a.get("args", {}), dict)
        for a in value["actions"]
    ):
        raise ValueError("Each action needs a tool string and an args object")
    return value


def run_episode(
    project,
    runtime,
    output,
    method="B3",
    seed=0,
    mode="local",
    model="gpt-5.6-luna",
    effort="max",
    limits=None,
    client=None,
):
    if method not in METHODS:
        raise ValueError("Expected B1, B2 or B3")
    limits = {
        "decisions": 12,
        "runs": 60,
        "seconds": 900,
        "tokens": 120000,
        "output_tokens": 8192,
        **(limits or {}),
    }
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    if (output / "episode.json").exists():
        raise ValueError("An episode already exists; choose a new output directory")
    candidate = output / "candidate"
    if candidate.exists():
        raise ValueError(
            "An unfinished candidate already exists; preserve it and use a new episode directory"
        )
    copy_public_project(project, candidate)
    original_hash = project_hash(candidate)
    runner = Runner(
        runtime, output / "native_runs", Budget(limits["runs"], limits["seconds"]), mode
    )
    box = ToolBox(candidate, runner, output, seed)
    client = client or ResponsesClient(model, effort)
    messages = [
        {
            "role": "system",
            "content": METHODS[method]
            + "\n"
            + TOOL_HELP
            + "\nDo not infer bug labels from task identifiers. Same model and resource limits apply to all methods. Return JSON only.\nEpisode limits: "
            + json.dumps(limits)
            + ". Reserve enough budget to verify and submit. The initial public project message already includes the editable source files. Batch independent actions when their arguments do not depend on an unseen tool result.",
        },
        {
            "role": "user",
            "content": json.dumps(box.inspect_project(), ensure_ascii=False),
        },
    ]
    token_count = 0
    tokens = {}
    usage = {"input_tokens": 0, "output_tokens": 0, "cached_input_tokens": 0}
    events = []
    start = time.monotonic()
    status, error, decisions = "running", None, 0

    def log(event):
        events.append(event)
        with (output / "episode.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False, allow_nan=False) + "\n")

    try:
        if method == "B2":
            fixed = box.run_visible_tests()
            log({"type": "fixed_diagnostics", "result": fixed})
            messages.append(
                {
                    "role": "user",
                    "content": "Fixed diagnostic suite: "
                    + json.dumps(fixed, ensure_ascii=False),
                }
            )
        for step in range(limits["decisions"]):
            decisions = step + 1
            if (
                token_count >= limits["tokens"]
                or runner.budget.remaining_seconds() <= 0.2
            ):
                raise BudgetExhausted("Token or wall-clock budget exhausted")
            compact_history(messages)
            # Admission reserves the last observed full input and output ceiling;
            # the post-response check also catches provider-side prompt growth.
            reserve = (tokens.get("input_tokens", 0) if step else 0) + limits[
                "output_tokens"
            ]
            if step and token_count + reserve > limits["tokens"]:
                raise BudgetExhausted(
                    "Insufficient token allowance for another model response"
                )
            client.timeout = min(180, runner.budget.remaining_seconds())
            response = client.complete(
                messages,
                max_output_tokens=min(
                    limits["output_tokens"], limits["tokens"] - token_count
                ),
            )
            tokens = response.get("usage") or {}
            if not all(
                isinstance(tokens.get(k), int)
                for k in ("input_tokens", "output_tokens")
            ):
                log({"type": "model_usage_unknown", "step": step, **response})
                raise RuntimeError(
                    "Provider did not report complete token usage; cannot enforce experiment budget"
                )
            usage["input_tokens"] += tokens.get("input_tokens", 0)
            usage["output_tokens"] += tokens.get("output_tokens", 0)
            usage["cached_input_tokens"] += tokens.get("input_tokens_details", {}).get(
                "cached_tokens", 0
            )
            token_count = usage["input_tokens"] + usage["output_tokens"]
            log({"type": "model", "step": step, **response})
            enforce_usage(usage, limits["tokens"])
            if response.get("model_returned") != model:
                raise RuntimeError("Provider returned a different model than requested")
            if runner.budget.remaining_seconds() <= 0.2:
                raise BudgetExhausted(
                    "Wall-clock budget exhausted after model response"
                )
            messages.append({"role": "assistant", "content": response["text"]})
            try:
                decision = parse_actions(response["text"])
            except (ValueError, TypeError) as exc:
                messages.append(
                    {"role": "user", "content": "Protocol error: " + str(exc)}
                )
                continue
            returns = []
            for action in decision["actions"]:
                if runner.budget.remaining_seconds() <= 0.2:
                    raise BudgetExhausted(
                        "Wall-clock budget exhausted before tool action"
                    )
                name, args = action.get("tool"), action.get("args", {})
                try:
                    value = box.execute(name, args)
                except BudgetExhausted:
                    raise
                except Exception as exc:
                    value = {"tool_error": type(exc).__name__, "message": str(exc)}
                item = {
                    "tool": name,
                    "args": args,
                    "result": value,
                    "elapsed_seconds": time.monotonic() - start,
                }
                log({"type": "tool", "step": step, **item})
                returns.append(item)
                if box.submission is not None:
                    break
            messages.append(
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "results": returns,
                            "budget_remaining": {
                                "model_decisions": limits["decisions"] - decisions,
                                "native_runs": limits["runs"] - runner.budget.runs,
                                "seconds": round(runner.budget.remaining_seconds(), 1),
                                "total_tokens": max(0, limits["tokens"] - token_count),
                                "next_response_reserved_tokens": tokens.get(
                                    "input_tokens", 0
                                )
                                + limits["output_tokens"],
                            },
                        },
                        ensure_ascii=False,
                    ),
                }
            )
            if box.submission is not None:
                if runner.budget.remaining_seconds() <= 0.2:
                    raise BudgetExhausted(
                        "Wall-clock budget exhausted during tool action"
                    )
                status = "submitted"
                break
        else:
            status = "budget_exhausted"
    except BudgetExhausted as exc:
        status, error = "budget_exhausted", str(exc)
    except Exception as exc:
        status, error = "infra_error", str(exc)
    summary = {
        "status": status,
        "error": error,
        "method": method,
        "seed": seed,
        "model": model,
        "reasoning_effort": effort,
        "decisions": decisions,
        "native_runs": runner.budget.runs,
        "usage": usage,
        "billed_cost": None,
        "elapsed_seconds": time.monotonic() - start,
        "limits": limits,
        "original_hash": original_hash,
        "final_hash": project_hash(candidate),
        "submission": box.submission,
        "token_budget_compliant": token_count <= limits["tokens"],
        "budget_compliant": token_count <= limits["tokens"]
        and time.monotonic() - start <= limits["seconds"],
        "isolation": "container"
        if mode in {"docker", "ssh_docker"}
        else "development_process_only",
    }
    dump_json(output / "episode.json", summary)
    return summary
