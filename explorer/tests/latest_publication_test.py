"""Public v18 completeness and conservative scoring checks.

See [the snapshot](../publication_v18/README.md). Tests read only the checked-in
public files, so CI does not need private model events or local run folders.
"""
import collections
import copy
import csv
import importlib.util
import json
from pathlib import Path
import unittest
from unittest import mock

EXPLORER = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('latest_publication', EXPLORER / 'build_latest_publication.py')
P = importlib.util.module_from_spec(spec)
spec.loader.exec_module(P)


class LatestPublicationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        folder = EXPLORER / 'publication_v18'
        cls.questions, cls.results, cls.summary = [
            json.loads((folder / name).read_text(encoding='utf-8'))
            for name in ('questions.public.json', 'results.json', 'summary.json')]

    def test_complete_two_model_grid_and_exact_main_counts(self):
        qs, rs = self.questions['cases'], self.results['records']
        self.assertEqual(len(qs), 252)
        self.assertEqual(len(rs), 504)
        self.assertEqual(collections.Counter(r['model'] for r in rs), {'gpt-6-luna': 252, 'gpt-6.1-sol': 252})
        current = [q for q in qs if q['phase'] == 'current_r2']
        self.assertEqual(collections.Counter(q['partition'] for q in current), {'primary': 142, 'node': 48, 'control': 12})
        expected = {
            'gpt-6-luna': {'answer': (85, 53, 4), 'logical_proof': (62, 78, 2), 'output_contract': (40, 91, 11)},
            'gpt-6.1-sol': {'answer': (138, 0, 4), 'logical_proof': (138, 0, 4), 'output_contract': (111, 5, 26)}}
        for model, dims in expected.items():
            rows = [r for r in rs if r['phase'] == 'current_r2' and r['partition'] == 'primary' and r['model'] == model]
            for dim, counts in dims.items():
                counter = collections.Counter(r['labels'][dim] for r in rows)
                self.assertEqual(tuple(counter[k] for k in ('P', 'F', 'U')), counts)
        self.assertEqual(P.verify_snapshot(self.questions, self.results, self.summary)['status'], 'pass')

    def test_raw_text_invalid_json_is_retained_not_repaired(self):
        invalid = [r for r in self.results['records'] if not r['json_valid']]
        self.assertEqual(len(invalid), 20)
        for row in invalid:
            self.assertEqual(row['model'], 'gpt-6-luna')
            with self.assertRaises(json.JSONDecodeError):
                json.loads(row['raw_response'])
        broken = copy.deepcopy(self.results)
        broken['records'][0]['raw_response'] += '\nchanged'
        with self.assertRaisesRegex(ValueError, 'Raw text changed'):
            P.verify_snapshot(self.questions, broken, self.summary)

    def test_duplicate_model_slot_does_not_stand_in_for_second_model(self):
        broken = copy.deepcopy(self.results)
        broken['records'][1] = copy.deepcopy(broken['records'][0])
        with self.assertRaisesRegex(ValueError, 'duplicate model slot'):
            P.verify_snapshot(self.questions, broken, self.summary)

    def test_gold_is_not_mixed_into_public_model_input(self):
        broken = copy.deepcopy(self.questions)
        broken['cases'][0]['input']['gold_answers'] = ['not public']
        with self.assertRaisesRegex(ValueError, 'Independent standard reference'):
            P.verify_snapshot(broken, self.results, self.summary)

    def test_clean_jsonl_is_exactly_252_actual_single_question_inputs(self):
        rows = [json.loads(line) for line in (EXPLORER / 'publication_v18/inputs.jsonl').read_text(encoding='utf-8').splitlines()]
        self.assertEqual(len(rows), 252)
        self.assertEqual(rows, [q['input'] for q in self.questions['cases']])
        for row in rows:
            self.assertEqual(set(row), {'id', 'instruction', 'question', 'contexts', 'output_contract'})
            self.assertNotIn('qualification', row)
            self.assertNotIn('metadata', row)
            self.assertNotIn('gold_answers', row)

    def test_csv_formula_projection_preserves_json_originals_and_hash_meaning(self):
        for value in ('=1+1', '+1', '-2', '@lookup', ' \t=2+2'):
            self.assertEqual(P.spreadsheet_safe(value), "'" + value)
        self.assertEqual(P.spreadsheet_safe('{"answer": 1}'), '{"answer": 1}')
        with (EXPLORER / 'publication_v18/results.csv').open(encoding='utf-8-sig', newline='') as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual(len(rows), 504)
        for original, row in zip(self.results['records'], rows):
            self.assertEqual(row['raw_response_spreadsheet_safe'], P.spreadsheet_safe(original['raw_response']))
            self.assertEqual(row['raw_text_sha256'], P.sha_bytes(original['raw_response'].encode('utf-8')))
            self.assertEqual(row['raw_response_csv_prefix_applied'], str(row['raw_response_spreadsheet_safe'] != original['raw_response']))
            for dim in ('answer', 'logical_proof', 'output_contract'):
                self.assertEqual(row[dim], original['labels'][dim])

    def test_ambiguous_historical_gold_remains_review_and_two_model_u(self):
        ambiguous = [q for q in self.questions['cases'] if q['qualification']['target_ambiguity']]
        self.assertEqual(len(ambiguous), 4)
        for q in ambiguous:
            self.assertEqual(q['qualification']['gold_status'], 'requires_review')
            self.assertIn('reason', q['qualification'])
        broken = copy.deepcopy(self.questions)
        q = next(q for q in broken['cases'] if q['qualification']['target_ambiguity'])
        q['qualification']['gold_status'] = 'accepted'
        with self.assertRaisesRegex(ValueError, 'unique accepted truth'):
            P.verify_snapshot(broken, self.results, self.summary)

    def test_u_is_in_fixed_denominator_and_five_trial_values_empty(self):
        out = P.metric(['P', 'U', 'F', 'P'])
        self.assertEqual(out['planned_slots'], 4)
        self.assertIsNone(out['pass@1']['point_estimate'])
        self.assertEqual(out['pass@1']['identification_bounds'], {'lower': .5, 'upper': .75})
        self.assertFalse(out['pass@1']['bounds_are_confidence_intervals'])
        for row in self.results['records']:
            self.assertEqual(row['n'], 1)
            self.assertIsNone(row['pass@5'])
            self.assertIsNone(row['pass^5'])

    def test_secret_and_absolute_user_path_fail_closed(self):
        for secret in ('sk-' + 'a' * 20, 'Bearer ' + 'b' * 30, 'C:\\Users\\private\\file.json',
                       'github_pat_' + 'a' * 30):
            with self.assertRaises(ValueError):
                P.scan_public_text(secret)
        P.scan_public_text('workspace/luna-sol-v16/file.json sha256 0123456789abcdef')

    def test_manifest_hashes_and_public_files_standalone(self):
        original_read = P.read
        def public_only_read(path):
            self.assertNotIn('references', Path(path).name)
            self.assertFalse(Path(path).name.endswith('.private.json'))
            return original_read(path)
        with mock.patch.object(P, 'read', side_effect=public_only_read):
            self.assertEqual(P.verify_existing()['paired_questions'], 252)
        manifest = original_read(EXPLORER / 'publication_v18/manifest.json')
        self.assertEqual(set(manifest['files']), P.PUBLIC_FILES)
        self.assertFalse(any('reference' in name or 'private' in name for name in manifest['files']))

    def test_public_structure_rejects_answer_packages_even_if_renamed(self):
        for forbidden in ('gold_answers', 'gold_paths', 'historical_reference', 'reference_answers',
                          'reference_proof', 'standard_answer', 'standard_proof', 'reading_1', 'reading_2'):
            broken = copy.deepcopy(self.questions)
            broken['cases'][0]['qualification'][forbidden] = ['must remain private']
            with self.assertRaisesRegex(ValueError, 'Independent standard reference'):
                P.verify_snapshot(broken, self.results, self.summary)
        P.reject_private_reference_fields([self.questions, self.results, self.summary])


if __name__ == '__main__':
    unittest.main()
