"""Versioned narrow contracts; see README.md and schemas.json in this directory."""
import json
from pathlib import Path

VERSION = 'bridgeqa-family-v0.1'


def obj(properties, required=None):
    return {'type': 'object', 'properties': properties, 'required': list(properties) if required is None else required, 'additionalProperties': False}


def arr(items, minimum=0):
    return {'type': 'array', 'items': items, 'minItems': minimum}


S = {'type': 'string', 'minLength': 1}
STRINGS = arr(S)
ROLE = {'enum': ['father', 'mother', 'parent']}
QUOTE = obj({'unit_id': S, 'quote': S})
ENTITY = obj({'id': S, 'name': S, 'aliases': STRINGS})
FACT = obj({'id': S, 'parent': S, 'child': S, 'parent_role': ROLE, 'scope': S,
            'expression': {'enum': ['direct', 'coreference']}, 'evidence_sets': arr(arr(QUOTE, 1), 1)})
QUERY = obj({'operation': {'const': 'parent_chain'}, 'start': S,
             'steps': {'type': 'array', 'items': ROLE, 'minItems': 2, 'maxItems': 2}, 'scope': S})
SCHEMAS = {
    'origin': obj({'entities': arr(ENTITY, 1), 'facts': arr(FACT, 1), 'warnings': STRINGS}),
    'composer': obj({'candidate_id': S, 'question': S, 'base_unit_ids': arr(S, 1), 'query': QUERY,
                     'proposed_answer_ids': arr(S, 1), 'proof_fact_ids': arr(S, 2), 'multi_hop_rationale': S, 'shortcut_risks': STRINGS}),
    'difficult': obj({'mechanism': {'const': 'entity_confusion'}, 'distractor_unit_ids': arr(S, 1),
                      'irrelevant_unit_ids': arr(S, 1), 'deletions': arr(QUOTE, 1),
                      'expected_trap_answer_ids': arr(S, 1), 'wrong_path_explanation': S, 'invariants': arr(S, 1)}),
    'supervisor': obj({'verdict': {'enum': ['pass', 'revise', 'reject']},
                       'checks': arr(obj({'name': S, 'passed': {'type': 'boolean'}, 'evidence': S}), 1),
                       'issues': arr(obj({'code': S, 'severity': {'enum': ['major', 'minor']}, 'message': S})),
                       'required_changes': STRINGS}),
    'blind-solver': obj({'status': {'enum': ['answerable', 'insufficient_evidence', 'ambiguous', 'conflicting']},
                         'answers': STRINGS, 'evidence': arr(obj({'context_id': S, 'quote': S})),
                         'steps': arr(obj({'from': S, 'relation': ROLE, 'to': S,
                                           'evidence': arr(obj({'context_id': S, 'quote': S}), 1)})),
                         'brief_reason': S}),
}


if __name__ == '__main__':
    Path(__file__).with_name('schemas.json').write_text(json.dumps(SCHEMAS, ensure_ascii=False, indent=2), encoding='utf-8')
