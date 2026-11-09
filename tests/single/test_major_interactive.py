import unittest
from engine.format.major_sim import (
    init_major_state,
    resolve_major_match,
    advance_major_state,
    sim_major_round,
    sim_major_remaining,
)


class TestMajorInteractive(unittest.TestCase):

    def setUp(self):
        # 8 elite teams (Top 2 from 4 regions)
        self.teams = [
            {'id': 1, 'name': 'Team_Pac_1', 'short_code': 'P01', 'region': 'pacific', 'regional_seed': 1, 'story_rating': 90},
            {'id': 2, 'name': 'Team_Pac_2', 'short_code': 'P02', 'region': 'pacific', 'regional_seed': 2, 'story_rating': 86},
            {'id': 3, 'name': 'Team_Ame_1', 'short_code': 'A01', 'region': 'americas', 'regional_seed': 1, 'story_rating': 92},
            {'id': 4, 'name': 'Team_Ame_2', 'short_code': 'A02', 'region': 'americas', 'regional_seed': 2, 'story_rating': 87},
            {'id': 5, 'name': 'Team_Eme_1', 'short_code': 'E01', 'region': 'emea', 'regional_seed': 1, 'story_rating': 91},
            {'id': 6, 'name': 'Team_Eme_2', 'short_code': 'E02', 'region': 'emea', 'regional_seed': 2, 'story_rating': 85},
            {'id': 7, 'name': 'Team_Chi_1', 'short_code': 'C01', 'region': 'china', 'regional_seed': 1, 'story_rating': 89},
            {'id': 8, 'name': 'Team_Chi_2', 'short_code': 'C02', 'region': 'china', 'regional_seed': 2, 'story_rating': 84},
        ]
        self.state = init_major_state(self.teams)

    def test_init_state(self):
        self.assertEqual(self.state['status'], 'in_progress')
        self.assertEqual(self.state['current_stage'], 'swiss')
        self.assertEqual(self.state['current_swiss_round'], 1)
        self.assertEqual(len(self.state['swiss_matches']), 4)
        self.assertTrue(all(m['status'] == 'pending' for m in self.state['swiss_matches']))
        self.assertEqual(len(self.state['swiss_standings']), 8)

    def test_single_match_roll_and_manual(self):
        m1 = self.state['swiss_matches'][0]
        # Roll simulation
        res = resolve_major_match(self.state, m1['id'], winner_id=None)
        self.assertEqual(res['status'], 'completed')
        self.assertFalse(res['is_manual'])
        self.assertIn(res['winner_id'], [m1['team_a_id'], m1['team_b_id']])

        # Manual edit
        new_winner_id = m1['team_b_id'] if res['winner_id'] == m1['team_a_id'] else m1['team_a_id']
        resolve_major_match(self.state, m1['id'], winner_id=new_winner_id)
        self.assertEqual(m1['winner_id'], new_winner_id)
        self.assertTrue(m1['is_manual'])

    def test_round1_to_round2_auto_progression(self):
        # Complete all 4 matches of Round 1
        r1_matches = [m for m in self.state['swiss_matches'] if m['round'] == 1]
        for m in r1_matches:
            resolve_major_match(self.state, m['id'], winner_id=m['team_a_id'])

        self.assertEqual(self.state['current_swiss_round'], 2)
        self.assertEqual(len(self.state['swiss_matches']), 8)
        r2_matches = [m for m in self.state['swiss_matches'] if m['round'] == 2]
        self.assertEqual(len(r2_matches), 4)
        self.assertTrue(all(m['status'] == 'pending' for m in r2_matches))

    def test_safeguards_in_swiss_and_playoffs(self):
        # Complete Swiss Round 1
        r1_matches = [m for m in self.state['swiss_matches'] if m['round'] == 1]
        for m in r1_matches:
            resolve_major_match(self.state, m['id'], winner_id=m['team_a_id'])

        m1 = r1_matches[0]
        # Edit Round 1 match when Round 2 has only pending matches: resets Round 2 cleanly
        resolve_major_match(self.state, m1['id'], winner_id=m1['team_b_id'])
        self.assertEqual(len(self.state['swiss_matches']), 8)

        # Now start Round 2: play 1 match
        r2_m1 = next(m for m in self.state['swiss_matches'] if m['round'] == 2)
        resolve_major_match(self.state, r2_m1['id'], winner_id=r2_m1['team_a_id'])

        # Now editing Round 1 MUST be blocked!
        with self.assertRaises(ValueError) as ctx:
            resolve_major_match(self.state, m1['id'], winner_id=m1['team_a_id'])
        self.assertIn("các vòng sau đã diễn ra", str(ctx.exception))

    def test_full_major_simulation_and_championship_points(self):
        total = sim_major_remaining(self.state)
        self.assertEqual(total, 16)  # 10 Swiss + 6 Playoffs
        self.assertEqual(self.state['status'], 'completed')
        self.assertIsNotNone(self.state['champion'])
        self.assertIsNotNone(self.state['runner_up'])

        st = self.state['standings']
        self.assertEqual(len(st), 8)
        self.assertEqual(st[0]['rank'], 1)
        self.assertEqual(st[0]['championship_points'], 5)  # Major Champion: 5 CP
        self.assertEqual(st[1]['rank'], 2)
        self.assertEqual(st[1]['championship_points'], 3)  # Major Runner-up: 3 CP
        self.assertEqual(st[2]['rank'], 3)
        self.assertEqual(st[2]['championship_points'], 2)  # 3rd place: 2 CP
        self.assertEqual(st[3]['rank'], 4)
        self.assertEqual(st[3]['championship_points'], 1)  # 4th place: 1 CP
        for s in st[4:]:
            self.assertEqual(s['rank'], 5)
            self.assertEqual(s['championship_points'], 0)  # Eliminated: 0 CP

        # Verify BO5 for both Lower Final and Grand Final
        lf = next(m for m in self.state['playoff_matches'] if m['round_name'] == 'lower_final')
        gf = next(m for m in self.state['playoff_matches'] if m['round_name'] == 'grand_final')
        self.assertEqual(lf['bo'], 5)
        self.assertEqual(gf['bo'], 5)
        self.assertEqual(max(lf['team_a_score'], lf['team_b_score']), 3)
        self.assertEqual(max(gf['team_a_score'], gf['team_b_score']), 3)


if __name__ == '__main__':
    unittest.main()
