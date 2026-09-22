"""Read a bounded public task tar on stdin; emit native result on stdout.

Used with `ssh HOST docker run -i --network=none ...`. Nothing is bind-mounted
from the remote host, and private evaluator resources are never transferred.
"""

import base64
import gzip
import contextlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import sys
import tarfile
import tempfile


def main():
    payload = sys.stdin.buffer.read(16 * 1024 * 1024 + 1)
    if len(payload) > 16 * 1024 * 1024:
        raise ValueError("Public task archive exceeds 16 MiB")
    root = Path(tempfile.mkdtemp(prefix="btr-"))
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:") as archive:
        total = 0
        for item in archive:
            name = PurePosixPath(item.name)
            if (
                name.is_absolute()
                or ".." in name.parts
                or "\\" in item.name
                or item.issym()
                or item.islnk()
                or not item.isfile()
            ):
                raise ValueError("Archive must contain regular relative files only")
            if name.parts[0] not in {"candidate", "request.json"}:
                raise ValueError("Unexpected task archive member")
            total += item.size
            if item.size > 2 * 1024 * 1024 or total > 12 * 1024 * 1024:
                raise ValueError("Expanded task archive exceeds limit")
            target = root.joinpath(*name.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.extractfile(item).read())
    candidate = root / "candidate"
    (candidate / ".vntrader").mkdir(exist_ok=True)
    (candidate / "tmp").mkdir(exist_ok=True)
    os.chdir(candidate)
    output = root / "result.json"
    sys.argv = ["worker", str(root / "request.json"), str(output)]
    from .worker import main as worker

    with (
        (root / "native_stdout.log").open("w") as out,
        (root / "native_stderr.log").open("w") as err,
    ):
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            worker()
    result = json.loads(output.read_text(encoding="utf-8"))
    result["native_stdout"] = (root / "native_stdout.log").read_text(errors="replace")[
        -20000:
    ]
    result["native_stderr"] = (root / "native_stderr.log").read_text(errors="replace")[
        -20000:
    ]
    data = base64.b64encode(gzip.compress(
        json.dumps(result, ensure_ascii=False, allow_nan=False).encode(), mtime=0
    )).decode()
    print("BTR_GZIP:" + data, flush=True)


if __name__ == "__main__":
    main()
