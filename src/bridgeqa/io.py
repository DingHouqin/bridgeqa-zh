"""UTF-8 JSONL helpers."""

import json
from pathlib import Path


def read_jsonl(path):
    rows = []
    for number, line in enumerate(Path(path).read_text(encoding="utf-8-sig").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{number}: invalid JSON: {exc.msg}") from exc
        if not isinstance(row, dict):
            raise ValueError(f"{path}:{number}: expected an object")
        rows.append(row)
    return rows
