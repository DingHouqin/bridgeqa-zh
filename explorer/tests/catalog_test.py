"""[Full catalog acceptance](../specs/11_全量题库与最新关系题发布.md)."""
import hashlib
import json
import sys
import unittest
from collections import Counter
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from build_catalog import verify, OUT, PROJECT

class CatalogTest(unittest.TestCase):
    def setUp(self):
        self.c=json.loads((OUT/'catalog.json').read_text(encoding='utf-8'))
        self.r=json.loads((OUT/'luna.json').read_text(encoding='utf-8'))
    def test_counts_and_semantic_uncertainty(self):
        verify(self.c,self.r)
        self.assertEqual(sum(q['kind']=='oracle' for q in self.c['cases']),58)
        self.assertEqual(sum(q['cohort']=='v2' and q['kind']=='diagnostic' for q in self.c['cases']),10)
        expected={'v20':(9,9),'v21':(3,13),'v23':(1,18),'v24':(8,16)}
        for cohort,(mothers,variants) in expected.items():
            kinds=Counter(q['kind'] for q in self.c['cases'] if q['cohort']==cohort)
            self.assertEqual((kinds['mother'],kinds['variant']),(mothers,variants))
    def test_current_inputs_equal_frozen_source_when_available(self):
        for cohort,source in [('v20','data/graph_pilot_v20/final-r1/public_inputs.jsonl'),('v21','data/natural_goal_v21/draft-r3/public_inputs.jsonl'),('v23','data/adversarial_axes_v23/draft-r2/public_all_inputs.jsonl'),('v24','data/nested_relations_v24/final-r2/public_inputs.jsonl')]:
            p=PROJECT/source
            if not p.exists():continue  # Public CI intentionally lacks private experiment archives.
            rows=[json.loads(x) for x in p.read_text(encoding='utf-8').splitlines()]
            self.assertEqual([q['input'] for q in self.c['cases'] if q['cohort']==cohort],rows)
    def test_manifest_and_explicit_public_boundary(self):
        manifest=json.loads((OUT/'manifest.json').read_text(encoding='utf-8'))
        for name,expected in manifest['outputs'].items():
            self.assertEqual(hashlib.sha256((OUT/name).read_bytes()).hexdigest(),expected)
        allowed={'key','case_id','model','status','raw_response','raw_text_sha256','endpoint_success','rationale','progress','contract','proof_diagnostics'}
        for r in self.r['records']:self.assertEqual(set(r),allowed)
        public=json.loads((PROJECT/'explorer/web/documents.json').read_text(encoding='utf-8'))['files']
        for name in public:
            self.assertNotIn('name_maps.private',name)
            self.assertNotIn('references.jsonl',name)
            self.assertFalse(name.startswith(('data/nested_relations_v24/','data/adversarial_axes_v23/','workspace/')))

if __name__=='__main__':unittest.main()
