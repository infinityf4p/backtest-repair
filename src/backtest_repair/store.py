"""Atomic receipts and process locks for resumable, content-addressed work."""

from __future__ import annotations
from contextlib import contextmanager
import json
import os
from pathlib import Path
import uuid


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def locked(folder):
    """OS releases the lock after a crash; a persistent file is not a stale lock."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / ".lock").open("a+b") as stream:
        stream.seek(0, 2)
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError("Another process owns this execution directory") from exc
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


class UncertainCall(RuntimeError):
    """A request may have been billed; never silently send it again."""


def recorded_call(folder, request, invoke):
    from .contracts import load_json
    from .identity import stable_hash

    folder = Path(folder)
    key = stable_hash(request)
    if (folder / "response.json").exists():
        receipt = load_json(folder / "response.json")
        if receipt["request_hash"] != key:
            raise ValueError("Recorded model response belongs to different input")
        return receipt["response"]
    if (folder / "dispatched.json").exists():
        raise UncertainCall(
            "Model request was dispatched without a durable response; usage is unknown. Automatic retry disabled."
        )
    atomic_json(folder / "request.json", request)
    # Mark before network I/O: a crash before send is conservatively uncertain.
    atomic_json(folder / "dispatched.json", {"request_hash": key, "usage_known": False})
    try:
        response = invoke()
    except Exception as exc:
        atomic_json(
            folder / "failure.json",
            {"error_type": type(exc).__name__, "error": str(exc), "usage_known": False},
        )
        raise UncertainCall(str(exc)) from exc
    atomic_json(folder / "response.json", {"request_hash": key, "response": response})
    return response
