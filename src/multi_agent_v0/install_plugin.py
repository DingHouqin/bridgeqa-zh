"""Install the local bundle through the official dsh plugin command.

All pnpm tooling, stores and profile state stay in the approved workspace.
See README.md for the distinction between installation and model inference.
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CODE = Path(__file__).resolve().parent
WORK = ROOT / 'workspace/harness-prototype'


def install(home):
    home = Path(home).resolve()
    if not home.is_relative_to(WORK.resolve()):
        raise ValueError('Harness home must stay inside this prototype workspace')
    home.mkdir(parents=True, exist_ok=True)
    cli = Path(sys.executable).with_name('dsh.exe' if os.name == 'nt' else 'dsh')
    pnpm_bin = WORK / 'runtime/pnpm-tool/node_modules/.bin'
    env = dict(os.environ, DSH_HOME=str(home), PATH=str(pnpm_bin) + os.pathsep + os.environ.get('PATH', ''))
    env.pop('DEEPSEEK_API_KEY', None)
    package_uri = 'file:' + str(CODE / 'plugin').replace('\\', '/')
    for args in [[str(cli), '--profile', 'sdk-minimal', '--dump-default-config'],
                 [str(cli), 'plugin', '--profile', 'sdk-minimal', 'add', package_uri,
                  '--ignore-scripts', '--config.auto-install-peers=false', '--store-dir', str(WORK / 'runtime/pnpm-store')]]:
        result = subprocess.run(args, env=env, capture_output=True, text=True, encoding='utf-8', timeout=180)
        (home / 'bridgeqa-install.stdout.txt').write_text(result.stdout, encoding='utf-8')
        (home / 'bridgeqa-install.stderr.txt').write_text(result.stderr, encoding='utf-8')
        if result.returncode:
            raise RuntimeError('Plugin installation failed; inspect the local install logs: ' + result.stderr[-1500:])
    manifest = json.loads((home / 'profiles/sdk-minimal/package.json').read_text(encoding='utf-8'))
    if 'bridgeqa-harness-tools' not in manifest['dsh']['profile']['bundles']:
        raise RuntimeError('Installed dependency did not activate a bundle')
    return manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--home', required=True)
    args = parser.parse_args()
    manifest = install(args.home)
    print(json.dumps({'installed_bundle': 'bridgeqa-harness-tools', 'bundles': manifest['dsh']['profile']['bundles']}))


if __name__ == '__main__':
    main()
