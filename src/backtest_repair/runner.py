from __future__ import annotations
from dataclasses import dataclass
import hashlib
import base64
import zlib
import io
import json
import os
from pathlib import Path
import shutil
import shlex
import subprocess
import time
import tarfile
import uuid

from .contracts import (
    dump_json,
    load_json,
    read_bars,
    safe_path,
    validate_spec,
    write_bars,
)


class BudgetExhausted(RuntimeError):
    pass


@dataclass
class Budget:
    max_runs: int = 60
    max_seconds: float = 900
    runs: int = 0
    started: float = 0

    def __post_init__(self):
        if not self.started:
            self.started = time.monotonic()

    def consume(self):
        if (
            self.runs >= self.max_runs
            or time.monotonic() - self.started >= self.max_seconds
        ):
            raise BudgetExhausted("Native execution or wall-clock budget exhausted")
        self.runs += 1

    def remaining_seconds(self):
        return max(0.1, self.max_seconds - (time.monotonic() - self.started))


def project_hash(project):
    h = hashlib.sha256()
    for p in sorted(Path(project).rglob("*")):
        if (
            p.is_file()
            and "__pycache__" not in p.parts
            and p.suffix in {".py", ".json", ".csv", ".md"}
        ):
            h.update(p.relative_to(project).as_posix().encode())
            h.update(p.read_bytes())
    return h.hexdigest()


def task_archive(request, candidate):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w", format=tarfile.GNU_FORMAT) as archive:
        archive.add(request, arcname="request.json")
        for file in candidate.rglob("*"):
            if file.is_file():
                archive.add(
                    file, arcname="candidate/" + file.relative_to(candidate).as_posix()
                )
    return buffer.getvalue()


def copy_public_project(project, target, spec=None):
    """Copy only declared source/config and documented fixture inputs."""
    project, target = Path(project).resolve(), Path(target).resolve()
    spec = spec or validate_spec(load_json(project / "task.json"))
    names = {
        "task.json",
        "fixtures/bars.csv",
        "fixtures/releases.csv",
        "fixtures/warmup.csv",
        *spec["modifiable_files"],
        *spec.get("public_files", []),
    }
    target.mkdir(parents=True, exist_ok=True)
    for name in sorted(names):
        source = safe_path(project, name)
        if source.suffix not in {".py", ".json", ".csv", ".md"}:
            raise ValueError("Unsupported public project file type")
        if source.exists():
            if not source.is_file():
                raise ValueError("Public project member is not a regular file")
            destination = safe_path(target, name)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)


class Runner:
    def __init__(self, runtime, output, budget=None, mode="local"):
        self.runtime = (
            load_json(runtime) if isinstance(runtime, (str, Path)) else runtime
        )
        self.output = Path(output).resolve()
        self.output.mkdir(parents=True, exist_ok=True)
        self.budget = budget or Budget()
        self.mode = mode

    def run(
        self,
        project,
        bars=None,
        seed=0,
        instrument=True,
        releases=None,
        operation="backtest",
    ):
        project = Path(project).resolve()
        spec = validate_spec(load_json(project / "task.json"))
        self.budget.consume()  # Every attempted native execution, including failures and shrink, counts.
        run_id = uuid.uuid4().hex[:12]
        folder = self.output / run_id
        candidate = folder / "candidate"
        copy_public_project(project, candidate, spec)
        if bars is not None:
            write_bars(candidate / "fixtures/bars.csv", bars)
        if releases is not None:
            (candidate / "fixtures/releases.csv").write_text(releases, encoding="utf-8")
        read_bars(candidate / "fixtures/bars.csv")
        (candidate / ".vntrader").mkdir(exist_ok=True)
        (candidate / "tmp").mkdir(exist_ok=True)
        dump_json(
            folder / "request.json",
            {
                "spec": spec,
                "seed": seed,
                "instrument": instrument,
                "operation": operation,
            },
        )
        env = {
            k: v
            for k, v in os.environ.items()
            if k.upper()
            in {
                "SYSTEMROOT",
                "WINDIR",
                "PATH",
                "COMSPEC",
                "PATHEXT",
                "PROCESSOR_ARCHITECTURE",
                "NUMBER_OF_PROCESSORS",
                "USERPROFILE",
            }
        }
        env.update(
            PYTHONIOENCODING="utf-8",
            PYTHONDONTWRITEBYTECODE="1",
            PYTHONHASHSEED=str(seed),
            QT_QPA_PLATFORM="offscreen",
            MPLCONFIGDIR=str(candidate / "tmp"),
            TEMP=str(candidate / "tmp"),
            TMP=str(candidate / "tmp"),
        )
        source_root = Path(__file__).resolve().parent.parent
        result_path = folder / "result.json"
        payload = None
        remote_command = None
        container_name = "btr-" + run_id
        if self.mode == "ssh_docker":
            remote = self.runtime["remote"]
            host = remote["host"]
            if host.startswith("-") or any(c.isspace() for c in host):
                raise ValueError("Invalid SSH host")
            command = [
                remote.get("ssh", "ssh"),
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=15",
                "-o",
                "StrictHostKeyChecking=yes",
            ]
            if remote.get("known_hosts"):
                command += ["-o", "UserKnownHostsFile=" + remote["known_hosts"]]
            if remote.get("identity"):
                command += ["-o", "IdentitiesOnly=yes", "-i", remote["identity"]]
            if remote.get("port"):
                command += ["-p", str(remote["port"])]
            docker = [
                "docker",
                "run",
                "--rm",
                "--init",
                "--name",
                container_name,
                "-i",
                "--network=none",
                "--read-only",
                "--cap-drop=ALL",
                "--security-opt=no-new-privileges",
                "--pids-limit=128",
                "--memory=2g",
                "--cpus=1",
                "--tmpfs",
                "/tmp:rw,noexec,nosuid,size=256m",
                "-e",
                "PYTHONHASHSEED=" + str(seed),
                "-e",
                "OPENBLAS_NUM_THREADS=1",
                self.runtime[spec["engine"]]["image"],
                "python",
                "-m",
                "backtest_repair.stream_worker",
            ]
            command += [host, shlex.join(docker)]
            if remote.get("transport") == "paramiko":
                remote_command = shlex.join(docker)
            payload = task_archive(folder / "request.json", candidate)
            isolation = "remote_container_public_stdin_only"
        elif self.mode == "docker":
            command = [
                "docker",
                "run",
                "--rm",
                "--init",
                "--name",
                container_name,
                "-i",
                "--network=none",
                "--read-only",
                "--cap-drop=ALL",
                "--security-opt=no-new-privileges",
                "--pids-limit=128",
                "--memory=2g",
                "--cpus=1",
                "--tmpfs",
                "/tmp:rw,noexec,nosuid,size=256m",
                "-e",
                "PYTHONHASHSEED=" + str(seed),
                "-e",
                "OPENBLAS_NUM_THREADS=1",
                self.runtime[spec["engine"]]["image"],
                "python",
                "-m",
                "backtest_repair.stream_worker",
            ]
            payload = task_archive(folder / "request.json", candidate)
            isolation = "container_public_stdin_only"
        elif self.mode == "local":
            env["PYTHONPATH"] = str(source_root)
            command = [
                self.runtime[spec["engine"]]["python"],
                "-X",
                "utf8",
                "-m",
                "backtest_repair.worker",
                str(folder / "request.json"),
                str(result_path),
            ]
            isolation = "process_only_trusted_development"
        else:
            raise ValueError("Runner mode must be local, docker or ssh_docker")
        start = time.monotonic()
        try:
            with (
                (folder / "stdout.log").open("w", encoding="utf-8") as out,
                (folder / "stderr.log").open("w", encoding="utf-8") as err,
            ):
                if payload is not None:
                    if remote_command:
                        from .remote import execute
                        from types import SimpleNamespace

                        code, raw_out, raw_err = execute(
                            self.runtime["remote"],
                            remote_command,
                            payload,
                            timeout=min(
                                self.runtime.get("worker_timeout", 120),
                                self.budget.remaining_seconds(),
                            ),
                        )
                        err.write(raw_err.decode("utf-8", "replace"))
                        proc = SimpleNamespace(returncode=code, stdout=raw_out)
                    else:
                        proc = subprocess.run(
                            command,
                            cwd=candidate,
                            env=env,
                            input=payload,
                            stdout=subprocess.PIPE,
                            stderr=err,
                            timeout=min(
                                self.runtime.get("worker_timeout", 120),
                                self.budget.remaining_seconds(),
                            ),
                        )
                    stdout = proc.stdout.decode("utf-8", "replace")
                    compressed = next((line[len("BTR_GZIP:"):] for line in reversed(stdout.splitlines()) if line.startswith("BTR_GZIP:")), None)
                    if compressed:
                        inflater = zlib.decompressobj(16 + zlib.MAX_WBITS)
                        decoded_bytes = inflater.decompress(base64.b64decode(compressed, validate=True), 64 * 1024 * 1024 + 1)
                        if len(decoded_bytes) > 64 * 1024 * 1024 or not inflater.eof:
                            raise ValueError("Native result exceeds limit or is truncated")
                        decoded = json.loads(decoded_bytes)
                        out.write(decoded.pop("native_stdout", ""))
                        err.write(decoded.pop("native_stderr", ""))
                        dump_json(result_path, decoded)
                    marker = next(
                        (
                            line[len("BTR_RESULT:") :]
                            for line in reversed(stdout.splitlines())
                            if line.startswith("BTR_RESULT:")
                        ),
                        None,
                    )
                    if marker:
                        decoded = json.loads(base64.b64decode(marker))
                        out.write(decoded.pop("native_stdout", ""))
                        err.write(decoded.pop("native_stderr", ""))
                        dump_json(result_path, decoded)
                    elif not compressed:
                        out.write(stdout[-20000:])
                else:
                    proc = subprocess.run(
                        command,
                        cwd=candidate,
                        env=env,
                        stdout=out,
                        stderr=err,
                        timeout=min(
                            self.runtime.get("worker_timeout", 120),
                            self.budget.remaining_seconds(),
                        ),
                    )
            result = (
                load_json(result_path)
                if result_path.exists()
                else {
                    "status": "infra_error",
                    "events": [],
                    "error": "Worker returned no JSON result",
                    "returncode": proc.returncode,
                }
            )
        except (subprocess.TimeoutExpired, TimeoutError):
            result = {
                "status": "timeout",
                "events": [],
                "error": "Worker wall-clock timeout",
            }
            if self.mode in {"docker", "ssh_docker"}:
                try:
                    cleanup = ["docker", "rm", "--force", container_name]
                    if remote_command:
                        execute(self.runtime["remote"], shlex.join(cleanup), timeout=20)
                    elif self.mode == "ssh_docker":
                        subprocess.run(
                            command[:-1] + [shlex.join(cleanup)],
                            env=env,
                            capture_output=True,
                            timeout=20,
                        )
                    else:
                        subprocess.run(cleanup, capture_output=True, timeout=20)
                except Exception as exc:
                    result["cleanup_error"] = type(exc).__name__
        except Exception as exc:
            result = {"status": "infra_error", "events": [], "error": str(exc)}
        result.update(
            run_id=run_id,
            operation=operation,
            runtime_image=self.runtime[spec["engine"]].get("image")
            if self.mode != "local"
            else None,
            code_hash=project_hash(project),
            fixture_hash=hashlib.sha256(
                (candidate / "fixtures/bars.csv").read_bytes()
            ).hexdigest(),
            seed=seed,
            elapsed_seconds=time.monotonic() - start,
            isolation=isolation,
            artifact_dir=str(folder),
        )
        dump_json(result_path, result)
        with (folder / "trace.jsonl").open("w", encoding="utf-8") as f:
            for event in result["events"]:
                f.write(json.dumps(event, ensure_ascii=False, allow_nan=False) + "\n")
        return result
