import unittest
from engine.format.master_sim import (
    init_master_state,
    resolve_master_match,
    sim_master_round,
    sim_master_remaining,
    simulate_master_tournament,
)


class TestMasterEngine(unittest.TestCase):
    def setUp(self):
        # 12 teams for Masters Toronto:
        # 4 regional champions (Seed 1)
        # 4 runners-up (Seed 2)
        # 4 3rd place (Seed 3)
        self.teams = [
            {'id': 1, 'name': 'PRX', 'short_code': 'PRX', 'region': 'pacific', 'regional_seed': 1, 'story_rating': 89},
            {'id': 2, 'name': 'LEV', 'short_code': 'LEV', 'region': 'americas', 'regional_seed': 1, 'story_rating': 88},
            {'id': 3, 'name': 'FNC', 'short_code': 'FNC', 'region': 'emea', 'regional_seed': 1, 'story_rating': 90},
            {'id': 4, 'name': 'EDG', 'short_code': 'EDG', 'region': 'china', 'regional_seed': 1, 'story_rating': 87},

            {'id': 5, 'name': 'GEN', 'short_code': 'GEN', 'region': 'pacific', 'regional_seed': 2, 'story_rating': 86},
            {'id': 6, 'name': 'G2', 'short_code': 'G2', 'region': 'americas', 'regional_seed': 2, 'story_rating': 85},
            {'id': 7, 'name': 'TH', 'short_code': 'TH', 'region': 'emea', 'regional_seed': 2, 'story_rating': 86},
            {'id': 8, 'name': 'FPX', 'short_code': 'FPX', 'region': 'china', 'regional_seed': 2, 'story_rating': 84},

            {'id': 9, 'name': 'T1', 'short_code': 'T1', 'region': 'pacific', 'regional_seed': 3, 'story_rating': 83},
            {'id': 10, 'name': 'SEN', 'short_code': 'SEN', 'region': 'americas', 'regional_seed': 3, 'story_rating': 84},
            {'id': 11, 'name': 'KC', 'short_code': 'KC', 'region': 'emea', 'regional_seed': 3, 'story_rating': 83},
            {'id': 12, 'name': 'TE', 'short_code': 'TE', 'region': 'china', 'regional_seed': 3, 'story_rating': 82},
        ]

    def test_init_state(self):
        state = init_master_state(self.teams)
        self.assertEqual(state['status'], 'in_progress')
        self.assertEqual(state['current_stage'], 'swiss')
        self.assertEqual(state['current_swiss_round'], 1)
        self.assertEqual(len(state['direct_teams']), 4)
        self.assertEqual(len(state['swiss_teams']), 8)
        self.assertEqual(len(state['swiss_matches']), 4)

        # Cross-region check in Round 1
        for m in state['swiss_matches']:
            self.assertNotEqual(m['team_a']['region'], m['team_b']['region'])

    def test_full_simulation(self):
        state = init_master_state(self.teams)
        total = sim_master_remaining(state)
        self.assertEqual(total, 24)  # 10 Swiss + 14 Playoffs
        self.assertEqual(state['status'], 'completed')
        self.assertEqual(len(state['swiss_qualifiers']), 4)
        self.assertEqual(len(state['swiss_eliminated']), 4)
        self.assertEqual(len(state['playoff_matches']), 14)
        self.assertIsNotNone(state['champion'])
        self.assertIsNotNone(state['runner_up'])

        # Check Championship Points distribution
        standings = state['standings']
        self.assertEqual(len(standings), 12)
        self.assertEqual(standings[0]['rank'], 1)
        self.assertEqual(standings[0]['cp'], 7)  # 1st: 7 CP
        self.assertEqual(standings[1]['rank'], 2)
        self.assertEqual(standings[1]['cp'], 5)  # 2nd: 5 CP
        self.assertEqual(standings[2]['rank'], 3)
        self.assertEqual(standings[2]['cp'], 4)  # 3rd: 4 CP
        self.assertEqual(standings[3]['rank'], 4)
        self.assertEqual(standings[3]['cp'], 3)  # 4th: 3 CP
        self.assertEqual(standings[4]['rank'], 5)
        self.assertEqual(standings[4]['cp'], 2)  # 5th: 2 CP
        self.assertEqual(standings[5]['rank'], 6)
        self.assertEqual(standings[5]['cp'], 2)  # 6th: 2 CP
        self.assertEqual(standings[6]['cp'], 0)  # 7th: 0 CP

    def test_manual_score_override(self):
        state = init_master_state(self.teams)
        m1 = state['swiss_matches'][0]
        team_a_id = m1['team_a']['id']
        team_b_id = m1['team_b']['id']

        # Force team A win
        resolve_master_match(state, m1['id'], winner_id=team_a_id)
        self.assertEqual(m1['winner_id'], team_a_id)
        self.assertTrue(m1['is_manual'])


if __name__ == '__main__':
    unittest.main()
