"""[API/acceptance spec](../specs/05_验收与测试.md). Run against local read-only service."""
import hashlib
import json
import sys
import unittest
import urllib.error
import urllib.request
from pathlib import Path

BASE = sys.argv.pop(1) if len(sys.argv)>1 and sys.argv[1].startswith("http") else "http://127.0.0.1:8765"
DATA = Path(__file__).resolve().parents[2] / "data" / "pilot_literature_history_v0"

class APITest(unittest.TestCase):
    def request(self,path,method="GET"):
        try:
            with urllib.request.urlopen(urllib.request.Request(BASE+path,method=method)) as r:
                return r.status,r.headers,r.read()
        except urllib.error.HTTPError as e:
            return e.code,e.headers,e.read()

    def test_live_data_and_source_readonly(self):
        before = {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in DATA.iterdir() if p.is_file()}
        status,headers,body=self.request("/api/datasets/pilot_literature_history_v0/bundle")
        bundle=json.loads(body)
        self.assertEqual(status,200)
        self.assertEqual(bundle["summary"]["records"],128)
        self.assertEqual(bundle["summary"]["families"],20)
        self.assertEqual(bundle["summary"]["scenarios"],27)
        self.assertEqual(bundle["summary"]["oracle_tasks"],58)
        self.assertEqual(len(bundle["scenarios"]),32)
        self.assertIn("charset=utf-8",headers["Content-Type"])
        disk=[json.loads(s) for s in (DATA/"benchmark.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(bundle["records"],disk)
        quoteids={q["quote_id"] for src in bundle["sources"] for q in src["quotes"]}
        for row in disk:
            docids={d["id"] for d in row["input"]["documents"]}
            for fact in row["facts"]:
                self.assertTrue(set(fact["quote_ids"]+fact.get("parent_quote_ids",[]))<=quoteids)
                self.assertIn(row["fact_to_evidence"][fact["fact_id"]],docids)
            for proof in row["gold"]["proofs"]:
                for n in proof:self.assertTrue(set(n["support_evidence_ids"])<=docids)
        after={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in DATA.iterdir() if p.is_file()}
        self.assertEqual(before,after)

    def test_paths_and_write_rejected(self):
        for path in ["/api/datasets/unknown/bundle","/files/../AGENTS.md",
                     "/files/%2e%2e/.git/config","/files/data/pilot_literature_history_v0/../../AGENTS.md",
                     "/server.py","/files/.git/config","/api/datasets/../bundle"]:
            self.assertEqual(self.request(path)[0],404,path)
        self.assertEqual(self.request("/api/datasets","POST")[0],405)
        self.assertEqual(self.request("/files/data/pilot_literature_history_v0/README.md")[0],200)
        for path in ["/testing-guide.html", "/files/README.md", "/files/docs/README.md",
                     "/files/src/pilot_literature_history_v0/README.md"]:
            self.assertEqual(self.request(path)[0],200,path)
        self.assertEqual(self.request("/files/AGENTS.md")[0],200)
        self.assertEqual(self.request("/specs/01_%E4%BA%A7%E5%93%81%E4%B8%8E%E4%BF%A1%E6%81%AF%E6%9E%B6%E6%9E%84.md")[0],200)
        self.assertIn("Content-Security-Policy",self.request("/")[1])

if __name__=="__main__":
    unittest.main()

