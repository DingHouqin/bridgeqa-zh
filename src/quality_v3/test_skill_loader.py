import unittest

from skill_loader import load_skills, snapshot


class SkillLoadingTests(unittest.TestCase):
    def test_review_does_not_load_grader_or_source_inventory(self):
        bundle = load_skills('review')
        self.assertEqual({p.split('/')[0] for p in bundle['files']},
                         {'two-hop-necessity', 'member-evidence-audit'})

    def test_scoring_does_not_receive_review_roles(self):
        bundle = load_skills('scoring')
        self.assertEqual({p.split('/')[0] for p in bundle['files']},
                         {'semantic-score-review'})

    def test_snapshot_exact_match_reusable(self):
        for role, files in snapshot().items():
            self.assertEqual(load_skills(role, files)['files'], files)

    def test_changed_or_extra_frozen_file_is_refused(self):
        for changed in ({'different': 'digest'}, {}, {'../other': 'digest'}):
            with self.assertRaisesRegex(ValueError, 'snapshot changed'):
                load_skills('review', changed)

    def test_unknown_role_cannot_traverse(self):
        with self.assertRaises(ValueError):
            load_skills('../scoring')


if __name__ == '__main__':
    unittest.main()
