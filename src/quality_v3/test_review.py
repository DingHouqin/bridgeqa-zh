"""Behavioral boundaries for isolated review; entirely fictional and offline."""
import copy
import json
import unittest

import jsonschema

from review import (project_member, validate_member_projection, ordered_proof_check,
                    literal_shortcut_scan, review_gate, REVIEW_SCHEMA)


def family():
    text='乙是丙的父亲。甲是乙的父亲。丙在读书。'
    facts=[{'id':'f1','parent':'乙','child':'丙','parent_role':'father','scope':'现实',
            'evidence_sets':[[{'unit_id':'T','quote':'乙是丙的父亲。'}]]},
           {'id':'f2','parent':'甲','child':'乙','parent_role':'father','scope':'现实',
            'evidence_sets':[[{'unit_id':'T','quote':'甲是乙的父亲。'}]]},
           {'id':'noise','parent':'丁','child':'戊','parent_role':'father','scope':'现实',
            'evidence_sets':[[{'unit_id':'OTHER','quote':'丁是戊的父亲。'}]]}]
    return {'question':'丙的父亲的父亲是谁？','query':{'start':'丙','steps':['father','father'],'scope':'现实'},
        'origin':{'facts':facts,'entities':[]},
        'external_relation_hints':{'secret':'LIBRARY_SECRET'},'reference':{'secret':'REFERENCE_SECRET'},
        'variants':[{'condition':'base','materials':[{'unit_id':'T','text':text,'original_text':'ORIGINAL_SECRET'}],
            'gold':{'status':'answerable','answer_ids':['甲'],'proofs':[{'entities':['丙','乙','甲'],'facts':['f1','f2']}]},
            'deletion_log':[{'quote':'DELETION_SECRET'}]},
            {'condition':'necessary_support_deleted_name_retained','materials':[{'unit_id':'T','text':'甲是乙的父亲。丙在读书。'}],
            'gold':{'status':'insufficient_evidence','answer_ids':[],'proofs':[]}},
            {'condition':'main_distractor','materials':[{'unit_id':'OTHER','text':'OTHER_MEMBER_SECRET'}],
            'gold':{'status':'insufficient_evidence','answer_ids':[],'proofs':[]}}]}


def payload():return project_member(family(),0)


def pass_review():
    return {'verdict':'pass','candidate_status_supported':True,'answer_supported':True,'proof_supported':True,
        'two_hop':{'verdict':'necessary','evidence':[],'reason':'分别需要两条关系。'},
        'step_reviews':[{'step':0,'supported':True,'evidence':[{'context_id':'T','quote':'乙是丙的父亲。'}],'reason':'第一跳'},
                        {'step':1,'supported':True,'evidence':[{'context_id':'T','quote':'甲是乙的父亲。'}],'reason':'第二跳'}],
        'findings':[],'reason':'当前材料完整支持。'}


class ProjectionTests(unittest.TestCase):
    def test_requires_explicit_member(self):
        with self.assertRaises(ValueError):project_member(family())

    def test_negative_index_not_accepted(self):
        with self.assertRaises(ValueError):project_member(family(),-1)

    def test_other_member_cannot_supply_evidence(self):
        p=payload();self.assertNotIn('OTHER_MEMBER_SECRET',json.dumps(p))
        self.assertEqual([x['context_id'] for x in p['contexts']],['T'])

    def test_raw_source_library_reference_and_logs_are_not_forwarded(self):
        p=json.dumps(payload())
        for secret in ['LIBRARY_SECRET','REFERENCE_SECRET','ORIGINAL_SECRET','DELETION_SECRET']:
            self.assertNotIn(secret,p)

    def test_condition_label_not_forwarded(self):
        p=json.dumps(project_member(family(),1))
        self.assertNotIn('necessary_support_deleted_name_retained',p)

    def test_deleted_support_not_forwarded(self):
        p=json.dumps(project_member(family(),1),ensure_ascii=False)
        self.assertNotIn('乙是丙的父亲。',p)
        self.assertEqual(project_member(family(),1)['candidate']['facts'],[])

    def test_joint_bundle_not_downgraded_to_partial_support(self):
        f=family();f['origin']['facts'][0]['evidence_sets'][0].append({'unit_id':'OTHER','quote':'NONLOCAL'})
        self.assertEqual(project_member(f,0)['candidate']['facts'][0]['evidence_sets'],[])

    def test_duplicate_context_ids_rejected(self):
        f=family();f['variants'][0]['materials']*=2
        with self.assertRaises(ValueError):project_member(f,0)

    def test_unknown_proof_quote_is_removed_single_item(self):
        c={'question':'丙的父亲的父亲是谁？','materials':[{'unit_id':'T','text':'丙在读书。'}],
           'proposed_status':'answerable','proposed_answer':['甲'],
           'proof':[{'from':'丙','to':'乙','relation':'father','quote':'DELETED_SECRET'}],'facts':[]}
        p=project_member(c)
        self.assertNotIn('DELETED_SECRET',json.dumps(p))
        self.assertEqual(p['candidate']['proofs'][0]['evidence'],[])

    def test_unambiguous_legacy_quote_located_without_source_id(self):
        c={'question':'丙的父亲的父亲是谁？','materials':[{'unit_id':'T','text':'乙是丙的父亲。'}],
           'proposed_status':'answerable','proposed_answer':['甲'],
           'proof':[{'from':'丙','to':'乙','relation':'father','quote':'乙是丙的父亲。'}],'facts':[]}
        p=project_member(c)
        self.assertEqual(p['candidate']['proofs'][0]['evidence'][0]['context_id'],'T')

    def test_input_not_mutated(self):
        f=family();before=copy.deepcopy(f);project_member(f,0);self.assertEqual(f,before)

    def test_projection_whitelist_rejects_extra_field(self):
        p=payload();p['gold_reference']='SECRET'
        with self.assertRaises(ValueError):validate_member_projection(p)


class OrderedProofTests(unittest.TestCase):
    def test_correct_chain_is_structurally_valid_but_not_semantically_certified(self):
        c=ordered_proof_check(payload());self.assertTrue(c['structural_valid']);self.assertFalse(c['semantic_validity_established'])

    def test_reversed_fact_array_rejected(self):
        p=payload();p['candidate']['proofs'][0]['facts'].reverse()
        self.assertFalse(ordered_proof_check(p)['structural_valid'])

    def test_wrong_start_rejected(self):
        p=payload();p['query']['start']='丁'
        self.assertIn('proof_start',[x['code'] for x in ordered_proof_check(p)['defects']])

    def test_wrong_final_answer_not_rescued_by_valid_path(self):
        p=payload();p['candidate']['answer_ids']=['乙']
        self.assertIn('proof_answer',[x['code'] for x in ordered_proof_check(p)['defects']])

    def test_mother_father_role_mismatch(self):
        p=payload();p['candidate']['facts'][0]['parent_role']='mother'
        self.assertIn('proof_role',[x['code'] for x in ordered_proof_check(p)['defects']])

    def test_cross_scope_rejected(self):
        p=payload();p['candidate']['facts'][1]['scope']='梦境'
        self.assertIn('proof_scope',[x['code'] for x in ordered_proof_check(p)['defects']])

    def test_explicit_per_step_scope_composition_is_permitted(self):
        p=payload();p['candidate']['facts'][1]['scope']='另一明确记载'
        p['query']['scope_by_step']=['现实','另一明确记载']
        self.assertTrue(ordered_proof_check(p)['structural_valid'])

    def test_missing_fact_rejected(self):
        p=payload();p['candidate']['facts']=p['candidate']['facts'][1:]
        self.assertIn('unknown_proof_fact',[x['code'] for x in ordered_proof_check(p)['defects']])

    def test_insufficient_claim_cannot_carry_answer(self):
        p=project_member(family(),1);p['candidate']['answer_ids']=['甲']
        self.assertFalse(ordered_proof_check(p)['structural_valid'])

    def test_absent_query_not_inferred_from_suspect_proof(self):
        p=payload();p['query']={}
        self.assertTrue(ordered_proof_check(p)['review_required'])

    def test_single_step_proof_disconnection_detected(self):
        p=payload();p['candidate']['proofs']=[{'from':'丙','to':'乙','relation':'father'},
            {'from':'丁','to':'甲','relation':'father'}]
        self.assertIn('disconnected_proof',[x['code'] for x in ordered_proof_check(p)['defects']])

    def test_parent_query_accepts_father_fact(self):
        p=payload();p['query']['steps']=['parent','father']
        self.assertTrue(ordered_proof_check(p)['structural_valid'])


class NecessityAndGateTests(unittest.TestCase):
    def test_same_paragraph_two_hop_not_literal_shortcut(self):
        self.assertFalse(literal_shortcut_scan(payload())['review_required'])

    def test_direct_ancestor_expression_located(self):
        p=payload();p['contexts'][0]['text']+='丙的祖父是甲。'
        s=literal_shortcut_scan(p);self.assertTrue(s['review_required']);self.assertFalse(s['automatic_defect'])
        self.assertIn('丙的祖父是甲。',[x['quote'] for x in s['candidates']])

    def test_negated_ancestor_is_only_review_candidate(self):
        p=payload();p['contexts'][0]['text']+='丙的祖父不是丁。'
        self.assertFalse(literal_shortcut_scan(p)['automatic_defect'])

    def test_dream_ancestor_is_only_review_candidate(self):
        p=payload();p['contexts'][0]['text']+='梦中说丙的祖父是丁。'
        self.assertFalse(literal_shortcut_scan(p)['automatic_defect'])

    def test_schema_accepts_valid_audit(self):
        jsonschema.validate(pass_review(),REVIEW_SCHEMA)

    def test_valid_audit_passes_local_gate_but_never_releases(self):
        g=review_gate(pass_review(),payload());self.assertTrue(g['protocol_valid'])
        self.assertEqual(g['program_disposition'],'pass');self.assertFalse(g['automatic_release_eligible'])

    def test_support_false_with_pass_is_protocol_failure(self):
        a=pass_review();a['proof_supported']=False
        self.assertEqual(review_gate(a,payload())['local_decision'],'protocol_failure')

    def test_major_finding_with_pass_is_protocol_failure(self):
        a=pass_review();a['findings']=[{'code':'wrong_proof','severity':'major','explanation':'有错','evidence':[]}]
        self.assertFalse(review_gate(a,payload())['protocol_valid'])

    def test_unknown_context_quote_cannot_pass(self):
        a=pass_review();a['step_reviews'][0]['evidence'][0]['context_id']='OTHER'
        self.assertIn('review_evidence_not_in_current_member',review_gate(a,payload())['protocol_errors'])

    def test_shortcut_acknowledgment_cannot_still_pass(self):
        a=pass_review();a['two_hop']={'verdict':'shortcut','evidence':[{'context_id':'T','quote':'甲是乙的父亲。'}],'reason':'直接结论'}
        self.assertFalse(review_gate(a,payload())['protocol_valid'])

    def test_undetermined_cannot_still_pass(self):
        a=pass_review();a['two_hop']['verdict']='undetermined'
        self.assertFalse(review_gate(a,payload())['protocol_valid'])

    def test_missing_one_step_is_not_a_complete_review(self):
        a=pass_review();a['step_reviews']=a['step_reviews'][:1]
        self.assertIn('step_review_coverage',review_gate(a,payload())['protocol_errors'])

    def test_structure_reject_separate_from_raw_model_pass(self):
        p=payload();p['candidate']['proofs'][0]['facts'].reverse()
        a=pass_review();original=copy.deepcopy(a);g=review_gate(a,p)
        self.assertEqual(g['raw_verdict'],'pass');self.assertEqual(g['program_disposition'],'needs_revision_structural')
        self.assertEqual(a,original)

    def test_valid_insufficiency_is_not_forced_to_have_two_steps(self):
        p=project_member(family(),1);a=pass_review();a['two_hop']['verdict']='not_applicable';a['step_reviews']=[]
        self.assertEqual(review_gate(a,p)['program_disposition'],'pass')

    def test_insufficiency_claim_requires_not_applicable_necessity(self):
        p=project_member(family(),1);a=pass_review();a['step_reviews']=[]
        self.assertFalse(review_gate(a,p)['protocol_valid'])

    def test_unlocated_finding_is_protocol_failure_even_for_revise(self):
        a=pass_review();a['verdict']='revise';a['findings']=[{'code':'x','severity':'major','explanation':'x',
            'evidence':[{'context_id':'T','quote':'UNSEEN'}]}]
        self.assertFalse(review_gate(a,payload())['protocol_valid'])




class GeneralParentContractTests(unittest.TestCase):
    def make_steps(self, relation='father'):
        p=payload();p['query']['steps']=['parent','parent']
        p['candidate']['proofs']=[{'from':'丙','to':'乙','relation':relation},
                                  {'from':'乙','to':'甲','relation':'mother'}]
        return p

    def test_parent_query_accepts_father_and_mother_step_roles(self):
        self.assertTrue(ordered_proof_check(self.make_steps())['structural_valid'])

    def test_parent_query_does_not_accept_friend_as_a_parent(self):
        self.assertFalse(ordered_proof_check(self.make_steps('friend'))['structural_valid'])

    def test_parent_query_does_not_accept_friend_in_graph_facts(self):
        p=payload();p['query']['steps']=['parent','parent']
        p['candidate']['facts'][0]['parent_role']='friend'
        self.assertFalse(ordered_proof_check(p)['structural_valid'])

    def test_single_item_cycle_is_not_a_two_step_parent_path(self):
        p=self.make_steps();p['candidate']['answer_ids']=['丙'];p['candidate']['proofs'][1]['to']='丙'
        self.assertFalse(ordered_proof_check(p)['structural_valid'])


if __name__=='__main__':unittest.main()
