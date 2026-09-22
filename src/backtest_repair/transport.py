"""Strict bounded result framing. Framing is not a trust boundary against Python code."""

import base64
import json
import zlib

MAX_RESULT = 64 * 1024 * 1024


def decode_frame(stdout, request_id):
    if len(stdout) > MAX_RESULT:
        raise ValueError("Worker wire output exceeds limit")
    lines = stdout.decode("utf-8", errors="strict").splitlines()
    frames = [line for line in lines if line.startswith(("BTR_GZIP:", "BTR_RESULT:"))]
    if len(frames) != 1 or not frames[0].startswith("BTR_GZIP:"):
        raise ValueError("Expected exactly one compressed result frame")
    inflater = zlib.decompressobj(16 + zlib.MAX_WBITS)
    decoded = inflater.decompress(
        base64.b64decode(frames[0][9:], validate=True), MAX_RESULT + 1
    )
    if len(decoded) > MAX_RESULT or not inflater.eof or inflater.unused_data:
        raise ValueError(
            "Native result exceeds limit, has trailing bytes or is truncated"
        )
    result = json.loads(decoded)
    if result.get("request_id") != request_id:
        raise ValueError("Result request identity mismatch")
    if result.get("status") == "ok" and (
        not isinstance(result.get("native"), dict)
        or not isinstance(result.get("events"), list)
    ):
        raise ValueError("Native result schema invalid")
    return result
