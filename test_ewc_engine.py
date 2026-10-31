import unittest
from engine.format.ewc_sim import (
    init_ewc_state,
    resolve_ewc_match,
    sim_ewc_round,
    sim_ewc_remaining,
    simulate_ewc_tournament,
)


class TestEWCEngine(unittest.TestCase):
    def setUp(self):
        # 16 teams for EWC (4 regions x 4 pools)
        regions = ['pacific', 'americas', 'emea', 'china']
        self.teams = []
        tid = 1
        for r in regions:
            for pool in range(1, 5):
                self.teams.append({
                    'id': tid,
                    'name': f"{r[:3].upper()} Team {pool}",
                    'short_code': f"{r[:3].upper()}{pool}",
                    'region': r,
                    'regional_seed': pool,
                    'pool': pool,
                    'story_rating': 88 - pool * 2,
                })
                tid += 1

    def test_init_state(self):
        state = init_ewc_state(self.teams)
        self.assertEqual(state['status'], 'in_progress')
        self.assertEqual(state['current_stage'], 'groups')
        self.assertEqual(len(state['groups']), 4)
        for label, grp in state['groups'].items():
            self.assertEqual(len(grp['teams']), 4)
            self.assertEqual(len(grp['matches']), 5)
            # Seeds 1 to 4 present in each group
            seeds = [t['regional_seed'] for t in grp['teams']]
            self.assertEqual(sorted(seeds), [1, 2, 3, 4])
            # Max 1 per region
            grp_regs = [t['region'] for t in grp['teams']]
            self.assertEqual(len(set(grp_regs)), 4)

    def test_full_simulation(self):
        state = init_ewc_state(self.teams)
        total = sim_ewc_remaining(state)
        # 4 groups * 5 matches = 20 matches + 8 playoff matches = 28 matches
        self.assertEqual(total, 28)
        self.assertEqual(state['status'], 'completed')
        self.assertIsNotNone(state['champion'])
        self.assertIsNotNone(state['runner_up'])
        self.assertIsNotNone(state['third_place'])
        self.assertIsNotNone(state['fourth_place'])
        self.assertEqual(len(state['standings']), 16)
        self.assertEqual(state['standings'][0]['rank'], 1)
        self.assertEqual(state['standings'][1]['rank'], 2)
        self.assertEqual(state['standings'][2]['rank'], 3)
        self.assertEqual(state['standings'][3]['rank'], 4)

    def test_manual_score_override(self):
        state = init_ewc_state(self.teams)
        m1 = state['groups']['A']['matches']['groupA_opening1']
        team_a_id = m1['team_a']['id']

        resolve_ewc_match(state, m1['id'], winner_id=team_a_id)
        self.assertEqual(m1['winner_id'], team_a_id)
        self.assertTrue(m1['is_manual'])


if __name__ == '__main__':
    unittest.main()
