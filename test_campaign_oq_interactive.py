import unittest
from engine.format.open_qualifier import (
    init_open_qualifier_region_state,
    resolve_open_qualifier_match,
    advance_open_qualifier_region,
    sim_open_qualifier_round,
    sim_open_qualifier_remaining,
)


class TestCampaignOQInteractive(unittest.TestCase):

    def setUp(self):
        # 16 mock teams
        self.teams = [
            {'id': 100 + i, 'name': f'Team_{i+1}', 'short_code': f'T{i+1:02d}', 'current_rating': 70 + i}
            for i in range(16)
        ]
        self.state = init_open_qualifier_region_state('pacific', self.teams)

    def test_init_state(self):
        self.assertEqual(self.state['region_slug'], 'pacific')
        self.assertEqual(self.state['status'], 'in_progress')
        self.assertEqual(self.state['current_stage'], 'swiss')
        self.assertEqual(self.state['current_swiss_round'], 1)
        self.assertEqual(len(self.state['teams']), 16)
        self.assertEqual(len(self.state['swiss_matches']), 8)
        self.assertTrue(all(m['status'] == 'pending' for m in self.state['swiss_matches']))
        self.assertEqual(len(self.state['swiss_standings']), 16)
        self.assertTrue(all(s['wins'] == 0 and s['losses'] == 0 for s in self.state['swiss_standings']))

    def test_single_match_sim_roll(self):
        m1 = self.state['swiss_matches'][0]
        m1_id = m1['id']
        res = resolve_open_qualifier_match(self.state, m1_id, winner_id=None)
        self.assertEqual(res['status'], 'completed')
        self.assertFalse(res['is_manual'])
        self.assertIn(res['winner_id'], [m1['team_a_id'], m1['team_b_id']])
        self.assertEqual(len(res['maps']), 1)  # BO1
        self.assertIn(res['maps'][0]['team_a_score'], range(0, 30))

        # Check standings updated
        winner_st = next(s for s in self.state['swiss_standings'] if s['club_id'] == res['winner_id'])
        loser_st = next(s for s in self.state['swiss_standings'] if s['club_id'] == res['loser_id'])
        self.assertEqual(winner_st['wins'], 1)
        self.assertEqual(loser_st['losses'], 1)

    def test_single_match_manual_score(self):
        m1 = self.state['swiss_matches'][0]
        m1_id = m1['id']
        winner_id = m1['team_a_id']
        maps_data = [{
            'map_number': 1,
            'team_a_score': 13,
            'team_b_score': 11,
            'winner_id': winner_id,
        }]

        res = resolve_open_qualifier_match(self.state, m1_id, winner_id=winner_id, maps=maps_data)
        self.assertEqual(res['status'], 'completed')
        self.assertTrue(res['is_manual'])
        self.assertEqual(res['winner_id'], winner_id)
        self.assertEqual(res['team_a_score'], 1)
        self.assertEqual(res['team_b_score'], 0)
        self.assertEqual(res['maps'][0]['team_a_score'], 13)
        self.assertEqual(res['maps'][0]['team_b_score'], 11)

    def test_round1_to_round2_auto_progression(self):
        # Resolve 7 matches
        for m in self.state['swiss_matches'][:7]:
            resolve_open_qualifier_match(self.state, m['id'], winner_id=m['team_a_id'])
        self.assertEqual(len(self.state['swiss_matches']), 8)
        self.assertEqual(self.state['current_swiss_round'], 1)

        # Resolve the 8th match -> Round 2 should be generated immediately!
        m8 = self.state['swiss_matches'][7]
        resolve_open_qualifier_match(self.state, m8['id'], winner_id=m8['team_a_id'])

        self.assertEqual(len(self.state['swiss_matches']), 16)
        self.assertEqual(self.state['current_swiss_round'], 2)
        r2_matches = [m for m in self.state['swiss_matches'] if m['round'] == 2]
        self.assertEqual(len(r2_matches), 8)
        self.assertTrue(all(m['status'] == 'pending' for m in r2_matches))

    def test_edit_safeguards_in_swiss(self):
        # Complete Round 1 only
        r1_matches = [m for m in self.state['swiss_matches'] if m['round'] == 1]
        for m in r1_matches:
            resolve_open_qualifier_match(self.state, m['id'], winner_id=m['team_a_id'])
        self.assertEqual(len(self.state['swiss_matches']), 16)
        self.assertEqual(self.state['current_swiss_round'], 2)

        # Edit Round 1 Match 1 while Round 2 matches are all pending:
        # Should reset Round 2, apply edit, and re-generate Round 2 cleanly!
        m1 = self.state['swiss_matches'][0]
        new_winner_id = m1['team_b_id']
        resolve_open_qualifier_match(self.state, m1['id'], winner_id=new_winner_id)
        self.assertEqual(m1['winner_id'], new_winner_id)
        self.assertEqual(len(self.state['swiss_matches']), 16)

        # Now start Round 2: complete 1 match in Round 2
        r2_m1 = next(m for m in self.state['swiss_matches'] if m['round'] == 2)
        resolve_open_qualifier_match(self.state, r2_m1['id'], winner_id=r2_m1['team_a_id'])

        # Now attempt to edit Round 1 Match 1 -> MUST BE BLOCKED!
        with self.assertRaises(ValueError) as ctx:
            resolve_open_qualifier_match(self.state, m1['id'], winner_id=m1['team_a_id'])
        self.assertIn("các vòng sau đã diễn ra", str(ctx.exception))

    def test_playoff_edit_safeguards_and_cascading(self):
        # Progress through Swiss
        while self.state['current_stage'] == 'swiss':
            sim_open_qualifier_round(self.state)

        self.assertEqual(self.state['current_stage'], 'playoffs')
        self.assertEqual(len(self.state['playoff_matches']), 10)

        # M1 (upper_r1_m1)
        m1 = next(m for m in self.state['playoff_matches'] if m['round_name'] == 'upper_r1_m1')
        m2 = next(m for m in self.state['playoff_matches'] if m['round_name'] == 'upper_r1_m2')
        m5 = next(m for m in self.state['playoff_matches'] if m['round_name'] == 'upper_r2_m5')

        # Resolve M1 with Team A winning
        orig_winner_id = m1['team_a']['id']
        orig_loser_id = m1['team_b']['id']
        resolve_open_qualifier_match(self.state, m1['id'], winner_id=orig_winner_id)

        # M5 should now have team_a = orig_winner_id
        self.assertEqual(m5['team_a']['id'], orig_winner_id)

        # Now edit M1: make Team B win!
        resolve_open_qualifier_match(self.state, m1['id'], winner_id=orig_loser_id)
        # M5 should cascade and now have team_a = orig_loser_id!
        self.assertEqual(m5['team_a']['id'], orig_loser_id)

        # Now resolve M2 so M5 has both teams
        resolve_open_qualifier_match(self.state, m2['id'], winner_id=m2['team_a']['id'])
        self.assertIsNotNone(m5['team_b'])

        # Now play M5
        resolve_open_qualifier_match(self.state, m5['id'], winner_id=m5['team_a']['id'])
        self.assertEqual(m5['status'], 'completed')

        # Now attempting to edit M1 or M2 MUST be blocked because M5 is completed!
        with self.assertRaises(ValueError) as ctx:
            resolve_open_qualifier_match(self.state, m1['id'], winner_id=orig_winner_id)
        self.assertIn("trận đấu kế tiếp của nhánh đã hoàn thành", str(ctx.exception))

    def test_sim_round_progression(self):
        # Sim Swiss Round 1 (8 matches)
        count_r1 = sim_open_qualifier_round(self.state)
        self.assertEqual(count_r1, 8)
        self.assertEqual(self.state['current_swiss_round'], 2)
        self.assertEqual(len(self.state['swiss_matches']), 16)

        # Sim Swiss Round 2 (8 matches)
        count_r2 = sim_open_qualifier_round(self.state)
        self.assertEqual(count_r2, 8)
        self.assertEqual(self.state['current_swiss_round'], 3)
        self.assertEqual(len(self.state['swiss_matches']), 24)

    def test_full_region_simulation_and_playoff_safeguards(self):
        # Simulate until stage completes
        sim_open_qualifier_remaining(self.state)
        self.assertEqual(self.state['status'], 'completed')
        self.assertEqual(self.state['current_stage'], 'playoffs')
        self.assertEqual(len(self.state['swiss_matches']), 33)
        self.assertEqual(len(self.state['playoff_matches']), 10)
        self.assertEqual(len(self.state['qualified_teams']), 4)
        self.assertEqual(len(set(t['id'] for t in self.state['qualified_teams'])), 4)

        # Editing any match now should be blocked because stage is completed!
        m1 = self.state['swiss_matches'][0]
        with self.assertRaises(ValueError) as ctx:
            resolve_open_qualifier_match(self.state, m1['id'], winner_id=m1['team_a_id'])
        self.assertIn("đã hoàn thành", str(ctx.exception))


if __name__ == '__main__':
    unittest.main()
