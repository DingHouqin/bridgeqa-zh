"""[Delivery checks and files](README.md). Local paths are resolved without Git access."""
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import unquote

project = Path(__file__).resolve().parents[2]
out = Path(__file__).resolve().parent
readme = out / 'README.md'
text = readme.read_text(encoding='utf-8').replace('以及13组', '以及14组')
if '固定测试指引在未知数据集参数下' not in text:
    text = text.replace('- 原始数据只读一致', '- 固定测试指引在未知数据集参数下直接打开，不请求数据集 bundle；文件链接、刷新、章节跳转和窄屏检查。\n- 原始数据只读一致')
text = text.replace('以上是可重新生成', '- [测试指引 · 桌面](07-testing-guide-desktop.png)\n- [测试指引 · 窄屏](08-testing-guide-mobile.png)\n\n[交付核对脚本](verify_delivery.py) 检查当前文档链接和原始数据散列，更新交付检查记录。\n\n以上是可重新生成') if 'verify_delivery.py' not in text else text
readme.write_text(text, encoding='utf-8')

docs = [project / p for p in ['README.md', 'AGENTS.md', 'docs/README.md',
    'docs/report/README.md', 'docs/benchmark-survey/README.md', 'explorer/README.md']]
docs += sorted((project / 'explorer/specs').glob('*.md'))
docs.append(readme)
broken = []
count = 0
for file in docs:
    for raw in re.findall(r'\[[^\]]*\]\(([^)]+)\)', file.read_text(encoding='utf-8')):
        raw = raw.strip().strip('<>')
        if re.match(r'^[a-zA-Z][\w+.-]*:', raw) or raw.startswith('#'):
            continue
        count += 1
        target = (file.parent / unquote(raw.split('#')[0])).resolve()
        if not target.exists():
            broken.append({'file': str(file.relative_to(project)), 'target': raw})
assert not broken, broken

baseline = json.loads((project / 'workspace/pilot_literature_history_v0/validation.json').read_text(encoding='utf-8'))
data = project / 'data/pilot_literature_history_v0'
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
for name, expected in baseline['output_hashes'].items():
    assert sha(data / name) == expected, name
for name, expected in baseline['input_hashes'].items():
    actual = data / name if name != 'build_pilot.py' else project / 'src/pilot_literature_history_v0' / name
    assert sha(actual) == expected, name

guide = project / 'explorer/web/testing-guide.html'
allowed_mentions = []
for file in project.rglob('*'):
    if file.suffix not in ('.md', '.html', '.js', '.css', '.py', '.cjs', '.mjs') or not file.is_file():
        continue
    # Preserve the archived report as opaque bytes, never read it as research evidence.
    if 'report' in file.parts or file == Path(__file__).resolve():
        continue
    if re.search(r'B\s*组', file.read_text(encoding='utf-8')):
        allowed_mentions.append(file)
assert allowed_mentions == [guide], allowed_mentions
assert not (project / '研究设计参考报告.md').exists()
report = project / 'docs/report/研究设计参考报告.md'
assert report.exists()
browser = json.loads((out / 'browser_checks.json').read_text(encoding='utf-8'))
assert browser['status'] == 'passed' and len(browser['checks']) == 14
delivery = json.loads((out / 'delivery_checks.json').read_text(encoding='utf-8'))
delivery.update(browser_check_groups=14, markdown_files_checked=len(docs), local_links_checked=count,
    broken_local_links=broken, original_dataset_and_source_hashes_unchanged=True,
    fixed_guide_verified=True, reference_report_archive_sha256=sha(report))
files = list((project / 'explorer').rglob('*')) + docs
delivery['files'] = {str(p.relative_to(project)): sha(p) for p in files if p.is_file() and '__pycache__' not in p.parts}
(out / 'delivery_checks.json').write_text(json.dumps(delivery, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'status':'passed','markdown_files':len(docs),'local_links':count,
    'dataset_hashes':'unchanged','fixed_guide':'passed'}, ensure_ascii=False))
