"""Exercise the real Harness tool pipeline on the generated query, without LLM I/O.

See README.md; credentials are used only for normal SDK route initialization.
"""
import argparse
import getpass
import json
import os
import time
from pathlib import Path

from deepseek_harness import DeepSeekHarness
from core import active_facts, solve, digest
from runner import ROOT, CODE, load


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-id', required=True)
    args = parser.parse_args()
    out = ROOT / 'workspace/harness-prototype/runs' / args.run_id
    origin_path = out / 'facts.gpt-adjudicated.json'
    origin = load(origin_path if origin_path.exists() else out / 'facts.reviewed.json')
    composer = load(out / 'base.reviewed.json')
    units = [u for u in load(out / 'materials.frozen.json') if u['unit_id'] in composer['base_unit_ids']]
    facts = active_facts(origin, units)
    payload = {'facts': facts, 'query': composer['query']}
    expected = solve(composer['query'], facts)
    key = os.environ.get('DEEPSEEK_API_KEY') or getpass.getpass('DeepSeek runtime credential (hidden): ').strip()
    if not key:
        raise ValueError('Missing runtime credential')
    target = out / 'harness-plugin-execution.json'
    if target.exists():
        raise ValueError('Verification output already exists; inspect it instead of overwriting')
    home = out / 'proof-audit-home'
    cwd = out / 'proof-audit-workspace'
    home.mkdir(exist_ok=True)
    cwd.mkdir(exist_ok=True)
    overlay = out / 'plugin-installed.patch.yml'
    overlay.write_text((CODE / 'harness.patch.yml').read_text(encoding='utf-8').split('- insert:')[0], encoding='utf-8')
    with DeepSeekHarness(provider='deepseek-official', model='deepseek-flash', reasoning_effort='off', max_tokens=1000,
        cwd=str(cwd), runtime_cwd=str(cwd), dsh_home=str(home), profile='sdk-minimal',
        patches=(str(overlay),), api_key=key, base_url='https://api.deepseek.com/anthropic',
        env={'BRIDGEQA_TOOL_AUDIT_INPUT': json.dumps(payload, ensure_ascii=False), 'BRIDGEQA_TOOL_AUDIT_FILE': str(target)},
        initialize_timeout_seconds=90, request_timeout_seconds=30) as harness:
        for _ in range(100):
            if target.exists():
                break
            time.sleep(0.05)
        if not target.exists():
            diagnostics = harness.client._runtime_diagnostics()
            (out / 'plugin-startup-diagnostics.txt').write_text(diagnostics.replace(key, '[REDACTED]'), encoding='utf-8')
            raise RuntimeError('Harness plugin did not produce the execution audit')
    audit = load(target)
    assert audit['visible_tools'] == ['bridgeqa_check_parent_path']
    result = audit['result']
    content = result.get('content')
    if content is None and 'result' in result:
        content = result['result'].get('content')
    assert content is not None, 'No model-facing tool result content'
    texts = [block['text'] for block in content if block.get('type') == 'text']
    actual = json.loads(''.join(texts))
    assert actual == expected
    summary = {'status': 'passed', 'harness_tool_execution': True, 'tool': 'bridgeqa_check_parent_path',
               'model_requests': 0, 'python_and_harness_results_equal': True, 'payload_hash': digest(payload), 'query': composer['query'], 'result': actual}
    (out / 'harness-plugin-verification.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
