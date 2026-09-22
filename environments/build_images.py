"""Build runtime images locally or over SSH without sending evaluator resources."""

import argparse
import io
from pathlib import Path
import shlex
import subprocess
import tarfile
from backtest_repair.contracts import load_json, dump_json, VERSIONS

ROOT = Path(__file__).resolve().parents[1]


def build(runtime, engines=None, remote=False):
    config = load_json(runtime)
    for engine in engines or VERSIONS:
        buffer = io.BytesIO()
        with tarfile.open(
            fileobj=buffer, mode="w", format=tarfile.GNU_FORMAT
        ) as archive:
            archive.add(ROOT / "environments/Dockerfile", arcname="Dockerfile")
            archive.add(
                ROOT / f"environments/{engine}/linux-py311.lock",
                arcname="requirements.lock",
            )
            archive.add(ROOT / f"environments/{engine}/extras.lock", arcname="extras.lock")
            package = ROOT / "src/backtest_repair"
            for name in [
                "__init__.py",
                "contracts.py",
                "trace.py",
                "fixture_api.py",
                "worker.py",
                "stream_worker.py",
            ]:
                archive.add(package / name, arcname="backtest_repair/" + name)
            for file in (package / "adapters").glob("*.py"):
                archive.add(file, arcname="backtest_repair/adapters/" + file.name)
        docker = ["docker", "build", "-t", config[engine]["image"], "-"]
        build_payload = buffer.getvalue()
        if remote:
            r = config["remote"]
            if r.get("transport") == "paramiko":
                from backtest_repair.remote import execute

                log_dir = ROOT / "validation/image-builds"
                log_dir.mkdir(parents=True, exist_ok=True)
                print("Building remote " + engine, flush=True)
                with (log_dir / (engine + ".log")).open("w", encoding="utf-8") as log:
                    code, _, _ = execute(
                        r, shlex.join(docker), build_payload, timeout=1200, log=log
                    )
                if code:
                    raise RuntimeError("Remote Docker build failed for " + engine)
                print("Built " + engine, flush=True)
                continue
            command = [
                r.get("ssh", "ssh"),
                "-o",
                "BatchMode=yes",
                "-o",
                "StrictHostKeyChecking=yes",
            ]
            if r.get("known_hosts"):
                command += ["-o", "UserKnownHostsFile=" + r["known_hosts"]]
            if r.get("identity"):
                command += ["-i", r["identity"], "-o", "IdentitiesOnly=yes"]
            if r.get("port"):
                command += ["-p", str(r["port"])]
            command += [r["host"], shlex.join(docker)]
        else:
            command = docker
        print("Building " + engine, flush=True)
        subprocess.run(command, input=build_payload, check=True)
    inspect = [
        "docker",
        "image",
        "inspect",
        *[config[e]["image"] for e in engines or VERSIONS],
    ]
    if remote and config["remote"].get("transport") == "paramiko":
        from backtest_repair.remote import execute
        import json

        code, out, _ = execute(config["remote"], shlex.join(inspect), timeout=30)
        if code:
            raise RuntimeError("Cannot record built image identities")
        images = json.loads(out)
    else:
        import json

        inspect_command = command[:-1] + [shlex.join(inspect)] if remote else inspect
        images = json.loads(subprocess.check_output(inspect_command, text=True))
    image_path = ROOT / "validation/linux-images.json"
    existing = load_json(image_path) if image_path.exists() else []
    replaced_tags = {tag for image in images for tag in image.get("RepoTags", [])}
    retained = [
        image
        for image in existing
        if not replaced_tags.intersection(image.get("RepoTags", []))
    ]
    dump_json(image_path, retained + images)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--runtime", required=True)
    p.add_argument("--remote", action="store_true")
    p.add_argument("--engine", action="append", choices=list(VERSIONS))
    a = p.parse_args()
    if a.remote:
        from backtest_repair.cli import credential_prompt

        credential_prompt(Path(a.runtime), "ssh_docker")
    build(a.runtime, a.engine, a.remote)
