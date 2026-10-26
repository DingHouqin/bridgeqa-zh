"""Boot the fixed builder/solver profiles without creating any model turn.

No API credential is read. Config snapshots prove tool masking; the separate
real tool execution audit proves builder registration. See README.md.
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import yaml
from deepseek_harness import DeepSeekHarness
from install_plugin import install
from runner import ROOT, CODE, load


class ConfigLoader(yaml.SafeLoader):
    pass


ConfigLoader.add_constructor('tag:yaml.org,2002:js', lambda loader, node: loader.construct_scalar(node))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-id', default='milestone-007')
    args = parser.parse_args()
    out = ROOT / 'workspace/harness-prototype/runs' / args.run_id
    results = []
    for role in ('builder', 'solver'):
        home = out / ('proof-audit-home' if role == 'builder' else 'solver-installed-smoke-home')
        manifest_path = home / 'profiles/sdk-minimal/package.json'
        manifest = load(manifest_path) if manifest_path.exists() else {}
        if 'bridgeqa-harness-tools' not in manifest.get('dsh', {}).get('profile', {}).get('bundles', []):
            manifest = install(home)
        patches = [str(CODE / 'harness.patch.yml')]
        if role == 'solver':
            patches.append(str(CODE / 'solver.patch.yml'))
        cli = Path(sys.executable).with_name('dsh.exe' if os.name == 'nt' else 'dsh')
        args_cli = [str(cli), '--profile', 'sdk-minimal']
        for patch in patches:
            args_cli.extend(['--patch', patch])
        args_cli.append('--dump-config')
        env = dict(os.environ, DSH_HOME=str(home), DEEPSEEK_API_KEY='')
        dump = subprocess.run(args_cli, env=env, capture_output=True, text=True, encoding='utf-8', check=True)
        (out / (role + '.installed.config.yml')).write_text(dump.stdout, encoding='utf-8')
        rows = {r['id']: r for r in yaml.load(dump.stdout, Loader=ConfigLoader)}
        for tool in ('tool-fs', 'tool-working-directory', 'persistent-bash', 'persistent-pwsh'):
            assert rows[tool]['disabled'] is True
        assert rows['session-log-deepseek']['disabled'] is True
        assert rows['plugin-package-inventory-deepseek']['disabled'] is True
        assert rows['bridgeqa-tools'].get('disabled', False) == (role == 'solver')
        cwd = out / ('runtime-workspaces/' + role)
        with DeepSeekHarness(cwd=str(cwd), runtime_cwd=str(cwd), dsh_home=str(home), profile='sdk-minimal',
              patches=tuple(patches), provider='deepseek-official', model='deepseek-flash', reasoning_effort='off',
              api_key='', base_url='https://api.deepseek.com/anthropic', initialize_timeout_seconds=60) as harness:
            diagnostics = harness.client._runtime_diagnostics()
            assert 'did not activate' not in diagnostics and 'failed to import' not in diagnostics
        results.append({'role': role, 'startup': 'passed', 'installed_bundles': manifest['dsh']['profile']['bundles'],
                        'shell_file_and_directory_tools_disabled': True, 'graph_tool_disabled': role == 'solver',
                        'automatic_log_and_package_upload_disabled': True, 'model_turns': 0})
    (out / 'fixed-profile-smoke.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(results, ensure_ascii=False))


if __name__ == '__main__':
    main()
