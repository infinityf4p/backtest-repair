"""Run historical-defect cases; reuse completed evidence without paid repetitions."""
import argparse
from datetime import datetime, timezone
import getpass
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT), str(ROOT / 'src')]
from backtest_repair.contracts import load_json, dump_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['build', 'baseline', 'baseline_fixed', 'baseline_covered', 'agents', 'holdout'])
    parser.add_argument('--runtime', required=True, type=Path)
    parser.add_argument('--case', action='append')
    args = parser.parse_args()
    runtime = load_json(args.runtime)
    env = runtime['remote'].get('password_env', 'BTR_SSH_PASSWORD')
    if not os.environ.get(env) and not runtime['remote'].get('identity'):
        os.environ[env] = getpass.getpass('SSH password (memory only): ')
    if args.action == 'build':
        from environments.build_images import build
        engines = sorted({s['engine'] for s in load_json(ROOT / 'sources.json')})
        build(args.runtime, engines=engines, remote=True)
        images = load_json(ROOT / 'validation/linux-images.json')
        for engine in engines:
            runtime[engine]['image'] = next(i['Id'] for i in images if runtime[engine]['image'] in i.get('RepoTags', []))
        dump_json(args.runtime.with_name('runtime.pinned.local.json'), runtime)
    else:
        from external_eval import main as evaluate
        evaluate(args.action, runtime, args.case)
        if args.action == 'holdout':
            from backtest_repair.remote import execute
            code, out, _ = execute(runtime['remote'], "docker ps --filter name=btr- --format '{{json .}}'", timeout=30)
            dump_json(ROOT / 'validation/remote-closeout.json', {'checked_at': datetime.now(timezone.utc).isoformat(), 'exit_code': code, 'active_suite_containers': [json.loads(s) for s in out.decode().splitlines() if s.strip()]})


if __name__ == '__main__':
    main()
