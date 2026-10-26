"""Family-v0.2 contracts. See the companion family.py and tests in this directory.

v0.1 contracts are not changed; optional diagnostics never masquerade as mandatory.
"""

VERSION = 'bridgeqa-family-v0.2'
MANDATORY = (
    'base', 'main_distractor', 'irrelevant_addition',
    'necessary_support_deleted_name_retained', 'irrelevant_deleted',
)
OPTIONAL = ('name_absent_deleted', 'redundant_support_deleted', 'alternative_proof_preserved')
DELETION_CONDITIONS = MANDATORY[3:] + OPTIONAL

STRING = {'type': 'string', 'minLength': 1}
QUOTE = {'type': 'object', 'properties': {'unit_id': STRING, 'quote': STRING},
         'required': ['unit_id', 'quote'], 'additionalProperties': False}
PACKET_SCHEMA = {
    'type': 'object',
    'required': ['family_id', 'track', 'question', 'origin', 'query', 'base_unit_ids',
                 'additions', 'deletions', 'optional_not_applicable', 'materials'],
    'properties': {
        'family_id': STRING, 'track': {'enum': ['source', 'synthetic']}, 'question': STRING,
        'origin': {'type': 'object'}, 'query': {'type': 'object'},
        'base_unit_ids': {'type': 'array', 'items': STRING, 'minItems': 1, 'uniqueItems': True},
        'materials': {'type': 'array', 'minItems': 1, 'items': {
            'type': 'object', 'required': ['unit_id', 'text'],
            'properties': {'unit_id': STRING, 'text': STRING},
        }},
        'additions': {'type': 'object', 'required': ['main_distractor', 'irrelevant_addition'],
                      'properties': {k: {'type': 'array', 'items': STRING, 'minItems': 1,
                                          'uniqueItems': True} for k in MANDATORY[1:3]},
                      'additionalProperties': False},
        'deletions': {'type': 'object', 'required': list(MANDATORY[3:]),
                      'properties': {k: {'type': 'array', 'items': QUOTE, 'minItems': 1}
                                     for k in DELETION_CONDITIONS},
                      'additionalProperties': False},
        'optional_not_applicable': {'type': 'object',
                                    'properties': {k: STRING for k in OPTIONAL},
                                    'additionalProperties': False},
        'semantic_residual': {'oneOf': [
            {'type': 'boolean'},
            {'type': 'object', 'properties': {k: {'type': 'boolean'} for k in DELETION_CONDITIONS},
             'additionalProperties': False},
        ]},
    },
}

FAMILY_SCHEMA = {
    'type': 'object',
    'required': ['schema_version', 'family_version', 'family_id', 'track', 'question', 'query',
                 'origin', 'variants', 'optional_applicability', 'provenance', 'validation_status',
                 'eligible_for_locked_experiment', 'human_review', 'formal_release'],
    'properties': {
        'schema_version': {'const': VERSION}, 'family_version': {'const': 'family-v0.2'},
        'family_id': STRING, 'track': {'enum': ['source', 'synthetic']}, 'question': STRING,
        'query': {'type': 'object'}, 'origin': {'type': 'object'},
        'variants': {'type': 'array', 'minItems': 5, 'maxItems': 8, 'items': {
            'type': 'object', 'required': ['condition', 'materials', 'gold', 'registered_graph_gold',
                                          'active_fact_ids', 'deletion_log', 'name_positions',
                                          'requires_text_review', 'support_counts'],
            'properties': {'condition': {'enum': list(MANDATORY + OPTIONAL)},
                           'requires_text_review': {'const': True}},
        }},
        'optional_applicability': {'type': 'object', 'required': list(OPTIONAL)},
        'provenance': {'type': 'object'},
        'validation_status': {'enum': ['graph_checked_pending_text_audit', 'pending_semantic_review']},
        'eligible_for_locked_experiment': {'const': False},
        'human_review': {'const': 'not_run'}, 'formal_release': {'const': False},
    },
}
