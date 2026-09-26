import unittest
from spicecore.policy import recommend


class PolicyTests(unittest.TestCase):
    def test_untested_arms_have_equal_probability(self):
        stats = [{'persona_id': str(i), 'name': str(i), 'published': 0, 'net_cents': 0} for i in range(5)]
        result = recommend(stats, seed=4)
        self.assertEqual(result['method'], 'untested_rotation')
        self.assertEqual(result['selection_probability'], 0.2)
        self.assertEqual(result, recommend(stats, seed=4))

    def test_profitable_arm_gets_more_probability_after_all_tested(self):
        stats = [{'persona_id': str(i), 'name': str(i), 'published': 2,
                  'net_cents': 1000 if i == 2 else -100} for i in range(5)]
        result = recommend(stats, seed=5)
        self.assertEqual(result['method'], 'epsilon_greedy')
        self.assertAlmostEqual(result['all_arms'][2]['selection_probability'], 0.76)
        self.assertAlmostEqual(sum(x['selection_probability'] for x in result['all_arms']), 1)


if __name__ == '__main__':
    unittest.main()
