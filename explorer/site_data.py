"""Static-site data preparation. [Publishing](README.md), [specification](specs/04_技术与运行.md)."""
import hashlib
import json
import re
import threading
from collections import Counter
from pathlib import Path

APP = Path(__file__).resolve().parent
PROJECT = APP.parent
REGISTRY = {
    "pilot_literature_history_v0": {
        "title": "文学与历史 · 首轮对抗候选集",
        "topic": "以文学叙事与史书记载为取材，观察证据链如何受到角色、关系、时间与背景知识干扰。",
        "directory": PROJECT / "data" / "pilot_literature_history_v0",
    }
}
_cache = {}
_lock = threading.Lock()

def review_fingerprint(records):
    """Content identity shared by Windows authoring and Linux publication."""
    canonical = json.dumps(records, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()

def file_url(path):
    return "/files/" + path.relative_to(PROJECT).as_posix()

def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))

def load_bundle(dataset_id):
    if dataset_id not in REGISTRY:
        raise KeyError("数据集未登记")
    entry = REGISTRY[dataset_id]
    directory = entry["directory"]
    paths = [directory / n for n in ("benchmark.jsonl", "sources.json", "combinations.json", "oracle_inputs.jsonl")]
    catalog = PROJECT / "docs" / "benchmark-survey" / "07_场景总表与中文构题配方.md"
    paths.append(catalog)
    signature = tuple((p.stat().st_mtime_ns, p.stat().st_size) for p in paths)
    with _lock:
        if dataset_id in _cache and _cache[dataset_id][0] == signature:
            return _cache[dataset_id][1]
        records = [json.loads(line) for line in paths[0].read_text(encoding="utf-8").splitlines() if line.strip()]
        if len({r["id"] for r in records}) != len(records):
            raise ValueError("重复题号")
        sources = read_json(paths[1])["sources"]
        combinations = read_json(paths[2])["combinations"]
        scenarios = [{"id": m.group(1), "title": m.group(2).strip()}
                     for m in re.finditer(r"^\| (S\d{2}) ([^|]+)\|", catalog.read_text(encoding="utf-8"), re.M)]
        ids = {r["id"] for r in records}
        quote_ids = {q["quote_id"] for s in sources for q in s["quotes"]}
        for r in records:
            if not ({r["control_id"], r["challenge_id"]} <= ids):
                raise ValueError("配对引用缺失")
            if not set(r["scenario_ids"]) <= {s["id"] for s in scenarios}:
                raise ValueError("场景未登记")
            for f in r["facts"]:
                if not set(f["quote_ids"] + f.get("parent_quote_ids", [])) <= quote_ids:
                    raise ValueError("引文缺失")
        summary = {
            "records": len(records), "families": len({r["family_id"] for r in records}),
            "scenarios": len({s for r in records for s in r["scenario_ids"]}),
            "catalog_scenarios": len(scenarios), "sources": len(sources), "combinations": len(combinations),
            "oracle_tasks": sum(bool(line.strip()) for line in paths[3].read_text(encoding="utf-8").splitlines()),
            "domains": dict(Counter(r["domain"] for r in records)),
            "statuses": dict(Counter(r["gold"]["status"] for r in records)),
            "human_reviewed": sum(r["review"]["independent_human_review"] for r in records),
            "model_run": sum(r["review"]["model_run"] for r in records),
        }
        bundle = {"id": dataset_id, "title": entry["title"], "topic": entry["topic"],
                  "summary": summary, "records": records, "sources": sources,
                  "combinations": combinations, "scenarios": scenarios,
                  "version": records[0]["version"] if records else "unknown",
                  "fingerprint": hashlib.sha256(paths[0].read_bytes()).hexdigest(),
                  "review_fingerprint": review_fingerprint(records),
                  "links": {"readme": file_url(directory / "README.md"),
                            "records": file_url(directory / "benchmark.jsonl"),
                            "sources": file_url(paths[1]), "combinations": file_url(paths[2]),
                            "catalog": file_url(catalog),
                            "protocol": file_url(PROJECT / "docs/benchmark-survey/09_多步骤评判与核心创新点回收.md")}}
        _cache[dataset_id] = (signature, bundle)
        return bundle
