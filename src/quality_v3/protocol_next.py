"""Explicit index contract for subsequent requests, never used to rescore run002.

This small successor fixes an ambiguity observed in the locked pilot. Its
behavior is unit-tested; no model-effect claim is made without a new run.
"""
import copy

from review import REVIEW_SCHEMA, GENERIC_REVIEW_PROMPT, project_member
from skill_loader import load_skills

CONTRACT_VERSION = 'quality-review-v0.3.1'
NEXT_REVIEW_SCHEMA = copy.deepcopy(REVIEW_SCHEMA)
NEXT_REVIEW_SCHEMA['properties']['step_reviews']['items']['properties']['step'] = {
    'type': 'integer', 'enum': [0, 1],
    'description': 'Zero-based query-step index: 0 is the first relation; 1 is the second relation.'}
NEXT_REVIEW_PROMPT = (GENERIC_REVIEW_PROMPT +
    '\nstep_reviews.step严格从0编号：第一步为0，第二步为1。不是自然序号1和2。该合同仅覆盖两步查询。')


def next_review_request(candidate, variant_index=None, *, experimental_skills=False):
    payload = project_member(candidate, variant_index)
    if len(payload.get('query', {}).get('steps', [])) != 2:
        raise ValueError('This explicit-index contract supports exactly two query steps')
    prompt = NEXT_REVIEW_PROMPT
    bundle = load_skills('review') if experimental_skills else None
    if bundle:
        prompt += '\n\n' + bundle['text']
    return {'contract_version': CONTRACT_VERSION, 'input': payload,
            'output_schema': copy.deepcopy(NEXT_REVIEW_SCHEMA), 'skill': prompt,
            'experimental_skills': experimental_skills,
            'selected_skill_files': bundle['files'] if bundle else {},
            'automatic_release_eligible': False}
