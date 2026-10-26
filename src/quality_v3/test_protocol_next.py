import unittest
import jsonschema

from protocol_next import next_review_request, NEXT_REVIEW_SCHEMA
from test_review import family, pass_review


class NextContractTests(unittest.TestCase):
    def test_zero_based_complete_proof_remains_schema_valid(self):
        jsonschema.validate(pass_review(), NEXT_REVIEW_SCHEMA)

    def test_ambiguous_one_based_numbering_is_rejected_by_schema(self):
        response = pass_review()
        for step in response['step_reviews']:
            step['step'] += 1
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(response, NEXT_REVIEW_SCHEMA)

    def test_next_request_still_projects_only_one_member(self):
        request = next_review_request(family(), 0)
        self.assertEqual([c['context_id'] for c in request['input']['contexts']], ['T'])
        self.assertFalse(request['automatic_release_eligible'])
        self.assertEqual(request['selected_skill_files'], {})

    def test_caller_cannot_mutate_future_schema_by_editing_one_request(self):
        a = next_review_request(family(), 0)
        a['output_schema']['properties']['step_reviews']['items']['properties']['step']['enum'].append(2)
        b = next_review_request(family(), 0)
        self.assertEqual(b['output_schema']['properties']['step_reviews']['items']['properties']['step']['enum'], [0, 1])

    def test_out_of_scope_query_is_explicitly_refused(self):
        item = family()
        item['query']['steps'].append('father')
        with self.assertRaises(ValueError):
            next_review_request(item, 0)


if __name__ == '__main__':
    unittest.main()
