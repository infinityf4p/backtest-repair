"""Minimal stateless Responses client. Credentials never enter worker environments."""

from __future__ import annotations

import json
import os
from pathlib import Path
import time
import tomllib
import urllib.error
import urllib.request


def local_credentials():
    root = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
    config = (
        tomllib.loads((root / "config.toml").read_text(encoding="utf-8"))
        if (root / "config.toml").exists()
        else {}
    )
    provider = config.get("model_providers", {}).get(config.get("model_provider"), {})
    base = os.environ.get("BTR_API_BASE") or provider.get("base_url")
    key = os.environ.get("BTR_API_KEY") or os.environ.get(
        provider.get("env_key", "OPENAI_API_KEY")
    )
    if not key and (root / "auth.json").exists():
        # Only use an explicitly stored API key; never extract login session tokens.
        key = json.loads((root / "auth.json").read_text(encoding="utf-8")).get(
            "OPENAI_API_KEY"
        )
    if not base or not key:
        raise RuntimeError(
            "Configure BTR_API_BASE and BTR_API_KEY or a local Codex API-key provider"
        )
    return base.rstrip("/"), key


class ResponsesClient:
    def __init__(
        self, model="gpt-5.6-luna", effort="max", timeout=180, base=None, key=None
    ):
        self.base, self.key = (base, key) if base and key else local_credentials()
        self.model, self.effort, self.timeout = model, effort, timeout
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def complete(self, messages, max_output_tokens=8192):
        body = {
            "model": self.model,
            "reasoning": {"effort": self.effort},
            "input": messages,
            "stream": True,
            "store": False,
            "max_output_tokens": max_output_tokens,
        }
        request = urllib.request.Request(
            self.base + "/responses",
            data=json.dumps(body).encode(),
            headers={
                "Authorization": "Bearer " + self.key,
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
                "User-Agent": "backtest-repair/0.1.0",
            },
        )
        start = time.monotonic()
        pieces, completed = [], None
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                for raw in response:
                    if time.monotonic() - start > self.timeout:
                        raise TimeoutError(
                            "Responses stream exceeded its wall-clock allowance; final usage unavailable"
                        )
                    line = raw.decode("utf-8").strip()
                    if not line.startswith("data:") or line == "data: [DONE]":
                        continue
                    event = json.loads(line[5:].strip())
                    if event.get("type") == "response.output_text.delta":
                        pieces.append(event["delta"])
                    if event.get("type") in {
                        "response.completed",
                        "response.incomplete",
                    }:
                        completed = event["response"]
                    if event.get("type") in {"error", "response.failed"}:
                        raise RuntimeError(
                            "Responses stream failed: "
                            + json.dumps(
                                event.get(
                                    "error", event.get("response", {}).get("error")
                                )
                            )
                        )
        except urllib.error.HTTPError as exc:
            # Provider errors can echo inputs, so redact credentials before reporting.
            detail = (
                exc.read(2000)
                .decode("utf-8", "replace")
                .replace(self.key, "[REDACTED]")
            )
            raise RuntimeError(f"Responses HTTP {exc.code}: {detail}") from None
        if not completed:
            raise RuntimeError(
                "Responses stream ended without a completion event; token usage unknown"
            )
        # Codex-compatible relays may emit several assistant messages (commentary
        # and final) in one response. Concatenating them corrupts structured JSON.
        messages_out = [
            item
            for item in completed.get("output", [])
            if item.get("type") == "message"
        ]
        finals = [item for item in messages_out if item.get("channel") == "final"]
        chosen = finals[-1:] or messages_out[-1:]
        output = "".join(
            c.get("text", "")
            for item in chosen
            for c in item.get("content", [])
            if c.get("type") == "output_text"
        )
        if not output:
            output = "".join(pieces)
        return {
            "text": output,
            "usage": completed.get("usage"),
            "model_requested": self.model,
            "model_returned": completed.get("model"),
            "status": completed.get("status"),
            "response_id": completed.get("id"),
            "elapsed_seconds": time.monotonic() - start,
            "reasoning_effort": self.effort,
            "billed_cost": None,
        }
