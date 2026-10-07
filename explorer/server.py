"""Read-only local explorer. [Run/specs](README.md), [API spec](specs/04_技术与运行.md)."""
from __future__ import annotations
import argparse
import hashlib
import json
import mimetypes
import re
import threading
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

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
                  "links": {"readme": file_url(directory / "README.md"),
                            "records": file_url(directory / "benchmark.jsonl"),
                            "sources": file_url(paths[1]), "combinations": file_url(paths[2]),
                            "catalog": file_url(catalog),
                            "protocol": file_url(PROJECT / "docs/benchmark-survey/09_多步骤评判与核心创新点回收.md")}}
        _cache[dataset_id] = (signature, bundle)
        return bundle

def allowed_file(urlpath):
    raw = unquote(urlpath).replace("\\", "/")
    parts = raw.split("/")
    if any(part.startswith(".") for part in parts if part) or "\x00" in raw:
        return None
    if raw.startswith("/files/"):
        candidate = (PROJECT / raw[len("/files/"):]).resolve()
        roots = [e["directory"].resolve() for e in REGISTRY.values()]
        roots.append((PROJECT / "docs/benchmark-survey").resolve())
        document_files = {(PROJECT / p).resolve() for p in (
            "README.md", "data/README.md", "docs/README.md", "explorer/README.md",
            "src/pilot_literature_history_v0/README.md")}
        if candidate not in document_files and not any(candidate.is_relative_to(root) for root in roots):
            return None
        if candidate.suffix.lower() not in (".md", ".json", ".jsonl"):
            return None
        return candidate
    if raw.startswith("/specs/"):
        candidate = (APP / raw.lstrip("/")).resolve()
        if candidate.is_relative_to((APP / "specs").resolve()) and candidate.suffix == ".md":
            return candidate
        return None
    candidate = (APP / "web" / ("index.html" if raw == "/" else raw.lstrip("/"))).resolve()
    if candidate.is_relative_to((APP / "web").resolve()) and candidate.suffix in (".html", ".css", ".js", ".svg"):
        return candidate
    return None

class Handler(BaseHTTPRequestHandler):
    def send_bytes(self, status, data, content_type):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; script-src 'self'; style-src 'self'; "
                         "img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(data)

    def json_response(self, status, value):
        self.send_bytes(status, json.dumps(value, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/api/datasets":
            self.json_response(200, [{"id": key, "title": value["title"], "topic": value["topic"]} for key, value in REGISTRY.items()])
            return
        if path.startswith("/api/datasets/") and path.endswith("/bundle"):
            dataset_id = unquote(path[len("/api/datasets/"):-len("/bundle")])
            try:
                self.json_response(200, load_bundle(dataset_id))
            except KeyError:
                self.json_response(404, {"error": "未登记的数据集，请返回数据集概览。"})
            except (OSError, ValueError, TypeError):
                self.json_response(500, {"error": "数据读取或标注校验失败，请检查已登记的数据文件并重试。"})
            return
        candidate = allowed_file(path)
        if not candidate or not candidate.is_file():
            self.json_response(404, {"error": "资源不存在或不在允许范围内。"})
            return
        kind = {".js": "text/javascript", ".jsonl": "text/plain", ".md": "text/plain"}.get(
            candidate.suffix, mimetypes.guess_type(str(candidate))[0] or "application/octet-stream")
        self.send_bytes(200, candidate.read_bytes(), kind + ("; charset=utf-8" if candidate.suffix != ".svg" else ""))

    def do_POST(self):
        self.json_response(405, {"error": "本系统只读，不提供写入接口。"})

    do_PUT = do_POST
    do_DELETE = do_POST
    do_PATCH = do_POST

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"BridgeQA explorer: http://127.0.0.1:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

if __name__ == "__main__":
    main()

