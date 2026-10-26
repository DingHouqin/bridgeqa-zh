import unittest
from retrieval import edge_windows, query_and_proof_card


class RetrievalTests(unittest.TestCase):
    def data(self):
        return ([{'context_id':'T','text':'乙是丙的父亲。院内有人。丙的父亲叫乙。梦中说乙不是丙的父亲。'}],
                [{'id':'F1','parent':'乙','child':'丙','parent_role':'father','scope':'现实'}],
                [{'id':'丙','name':'丙','aliases':['小丙']}])

    def test_all_separate_occurrences_are_retrieved(self):
        c,e,n=self.data();windows=edge_windows(c,e,n,radius=0)[0]['windows']
        self.assertEqual(len(windows),3)

    def test_negation_and_dream_are_not_filtered_or_labeled_true(self):
        c,e,n=self.data();rows=edge_windows(c,e,n,radius=0)[0]
        self.assertTrue(any('梦中' in r['text'] for r in rows['windows']))
        self.assertTrue(rows['not_a_truth_or_independence_verdict'])
        self.assertEqual({r['status'] for r in rows['windows']},{'unverified_retrieval_window'})

    def test_offsets_reconstruct_actual_context_exactly(self):
        c,e,n=self.data()
        for w in edge_windows(c,e,n)[0]['windows']:
            self.assertEqual(c[0]['text'][w['start']:w['end']],w['text'])

    def test_child_absent_does_not_invent_a_fact(self):
        c,e,n=self.data();e[0]['child']='丁'
        self.assertEqual(edge_windows(c,e,n)[0]['windows'],[])

    def test_duplicate_contexts_and_negative_radius_refused(self):
        c,e,n=self.data()
        with self.assertRaises(ValueError):edge_windows(c+c,e,n)
        with self.assertRaises(ValueError):edge_windows(c,e,n,radius=-1)

    def test_alias_occurrence_is_locatable(self):
        c,e,n=self.data();c[0]['text']='小丙坐在门前。'
        self.assertEqual(edge_windows(c,e,n)[0]['windows'][0]['matched_surface'],'小丙')

    def test_card_preserves_a_wrong_submitted_fact_order(self):
        p={'query':{'start':'丙','steps':['father','mother']},'candidate':{'status':'answerable',
           'answer_ids':['甲'],'proofs':[{'entities':['丙','乙','甲'],'facts':['SECOND','FIRST']}],
           'facts':[{'id':'FIRST','parent':'乙','child':'丙','parent_role':'father','scope':'现实'},
                    {'id':'SECOND','parent':'甲','child':'乙','parent_role':'mother','scope':'现实'}]}}
        card=query_and_proof_card(p)
        self.assertLess(card.index('fact_id=SECOND'),card.index('fact_id=FIRST'))
        self.assertIn('第0步得到的人的母亲',card)


if __name__=='__main__':
    unittest.main()
