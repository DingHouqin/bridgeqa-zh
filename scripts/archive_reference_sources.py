"""Copy the four user-provided reference files into the local course repo."""

import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT.parent
REFERENCES = ROOT / "docs" / "references"
FILES = [
    ("PJ要求2026.docx", "course"),
    ("AB对抗组选题说明.docx", "course"),
    ("多跳问答与对抗鲁棒性深度研究.md", "research"),
    ("中文多跳与多跳相关 Benchmark 深度调研报告.md", "research"),
]


def main():
    missing = [name for name, _ in FILES if not (SOURCE_ROOT / name).is_file()]
    if missing:
        raise FileNotFoundError(f"Missing local reference files: {missing}")
    records = []
    for name, subdir in FILES:
        source = SOURCE_ROOT / name
        target = REFERENCES / subdir / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        assert hashlib.sha256(target.read_bytes()).hexdigest() == source_hash
        records.append({"source_relative_to_workspace": name, "archive_relative_to_repo": target.relative_to(ROOT).as_posix(), "sha256": source_hash, "bytes": source.stat().st_size, "external_distribution_permission": "not_assumed"})
    (REFERENCES / "archive-manifest.json").write_text(json.dumps({"archived_on": "2026-09-30", "files": records}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Archived {len(records)} local source files with matching SHA-256.")


if __name__ == "__main__":
    main()
