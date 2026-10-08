"""[Shared review content identity](../specs/08_临时人工审查.md)."""
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from site_data import review_fingerprint, load_bundle

class ReviewFingerprintTest(unittest.TestCase):
    def test_file_line_endings_and_json_format_do_not_change_round(self):
        rows = load_bundle('pilot_literature_history_v0')['records']
        lf = '\n'.join(json.dumps(r, ensure_ascii=False) for r in rows)
        crlf = lf.replace('\n', '\r\n')
        parse = lambda text: [json.loads(line) for line in text.splitlines()]
        self.assertNotEqual(lf.encode(), crlf.encode())
        self.assertEqual(review_fingerprint(parse(lf)), review_fingerprint(parse(crlf)))
        reverse_keys = [{k: row[k] for k in reversed(row)} for row in rows]
        self.assertEqual(review_fingerprint(rows), review_fingerprint(reverse_keys))
        self.assertEqual(load_bundle('pilot_literature_history_v0')['review_fingerprint'], review_fingerprint(rows))

    def test_real_material_change_starts_a_new_round(self):
        rows = load_bundle('pilot_literature_history_v0')['records']
        changed = json.loads(json.dumps(rows))
        changed[0]['input']['question'] += '（条件变化）'
        self.assertNotEqual(review_fingerprint(rows), review_fingerprint(changed))

if __name__ == '__main__':
    unittest.main()
