"""Inspect the pinned Harness profile without making a model request.

Usage and outputs: README.md in this directory.
"""
import importlib.metadata
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CODE = Path(__file__).resolve().parent
WORK = ROOT / 'workspace/harness-prototype'


def main():
    WORK.mkdir(exist_ok=True)
    for role in ('builder', 'solver'):
        home = WORK / 'homes' / role
        home.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ, DSH_HOME=str(home))
        env.pop('DEEPSEEK_API_KEY', None)
        cli = Path(sys.executable).with_name('dsh.exe' if os.name == 'nt' else 'dsh')
        # The config-only smoke inserts the local row, but does not claim import
        # activation. Actual startup uses an installed bundle and checks stderr.
        local_overlay = WORK / 'config-only.patch.yml'
        local_overlay.write_text((CODE / 'harness.patch.yml').read_text(encoding='utf-8') + "\n- insert:\n    - id: bridgeqa-tools\n      name: '" + (CODE / 'plugin/index.js').as_posix() + "'\n", encoding='utf-8')
        args = [str(cli), '--profile', 'sdk-minimal', '--patch', str(local_overlay)]
        if role == 'solver':
            args.extend(['--patch', str(CODE / 'solver.patch.yml')])
        args.append('--dump-config')
        result = subprocess.run(args, env=env, capture_output=True, text=True, encoding='utf-8', timeout=90)
        (WORK / (role + '.config.yml')).write_text(result.stdout, encoding='utf-8')
        (WORK / (role + '.bootstrap.stderr.txt')).write_text(result.stderr, encoding='utf-8')
        if result.returncode:
            raise RuntimeError(f'{role} profile dump failed: {result.returncode}; inspect bootstrap stderr')
    versions = {name: importlib.metadata.version(name) for name in ('deepseek-harness-sdk', 'deepseek-harness-runtime-bin', 'jsonschema', 'pyyaml')}
    (WORK / 'runtime_versions.json').write_text(json.dumps(versions, indent=2), encoding='utf-8')
    print(json.dumps({'profile_dumps': 'passed', 'versions': versions}))


if __name__ == '__main__':
    main()
