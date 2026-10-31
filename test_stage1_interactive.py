import unittest
from engine.format.stage1 import (
    init_stage1_region_state,
    resolve_stage1_match,
    sim_stage1_round,
    sim_stage1_remaining,
    stage1_config,
)


class TestStage1Interactive(unittest.TestCase):
    def setUp(self):
        # 12 simulated teams from Kickoff
        self.participants = [
            {'id': 101, 'name': 'DRX', 'short_code': 'DRX', 'story_rating': 88, 'kickoff_rank': 1},
            {'id': 102, 'name': 'T1', 'short_code': 'T1', 'story_rating': 86, 'kickoff_rank': 2},
            {'id': 103, 'name': 'Gen.G Esports', 'short_code': 'GEN', 'story_rating': 87, 'kickoff_rank': 3},
            {'id': 104, 'name': 'TALON', 'short_code': 'TLN', 'story_rating': 82, 'kickoff_rank': 4},
            {'id': 105, 'name': 'Nongshim RedForce', 'short_code': 'NS', 'story_rating': 81, 'kickoff_rank': 5},
            {'id': 106, 'name': 'DetonatioN FocusMe', 'short_code': 'DFM', 'story_rating': 80, 'kickoff_rank': 6},
            {'id': 107, 'name': 'Rex Regum Qeon', 'short_code': 'RRQ', 'story_rating': 82, 'kickoff_rank': 7},
            {'id': 108, 'name': 'Paper Rex', 'short_code': 'PRX', 'story_rating': 89, 'kickoff_rank': 8},
            {'id': 109, 'name': 'BOOM Esports', 'short_code': 'BME', 'story_rating': 79, 'kickoff_rank': 9},
            {'id': 110, 'name': 'Team Secret', 'short_code': 'TS', 'story_rating': 80, 'kickoff_rank': 10},
            {'id': 111, 'name': 'Global Esports', 'short_code': 'GE', 'story_rating': 78, 'kickoff_rank': 11},
            {'id': 112, 'name': 'ZETA DIVISION', 'short_code': 'ZETA', 'story_rating': 81, 'kickoff_rank': 12},
        ]
        self.state = init_stage1_region_state('pacific', self.participants)

    def test_init_groups_and_schedule(self):
        """Verify groups are 6 each and regular schedule has 36 cross-group matches."""
        self.assertEqual(len(self.state['group_alpha']), 6)
        self.assertEqual(len(self.state['group_omega']), 6)
        self.assertEqual(len(self.state['regular_matches']), 36)

        # Verify every Alpha plays every Omega
        alpha_ids = {t['id'] for t in self.state['group_alpha']}
        omega_ids = {t['id'] for t in self.state['group_omega']}

        pairs = set()
        for m in self.state['regular_matches']:
            a = m['team_a']['id']
            b = m['team_b']['id']
            self.assertIn(a, alpha_ids)
            self.assertIn(b, omega_ids)
            pairs.add((a, b))

        self.assertEqual(len(pairs), 36)

    def test_manual_score_override(self):
        """Verify manual score override works for regular season match."""
        m1 = self.state['regular_matches'][0]
        match_id = m1['match_id']
        team_a_id = m1['team_a_id']
        team_b_id = m1['team_b_id']

        resolved = resolve_stage1_match(
            self.state, match_id,
            winner_id=team_a_id,
            maps=[
                {'map_number': 1, 'team_a_score': 13, 'team_b_score': 8},
                {'map_number': 2, 'team_a_score': 13, 'team_b_score': 11},
            ]
        )
        self.assertEqual(resolved['status'], 'completed')
        self.assertEqual(resolved['winner_id'], team_a_id)
        self.assertEqual(resolved['team_a_score'], 2)
        self.assertEqual(resolved['team_b_score'], 0)
        self.assertTrue(resolved['is_manual'])

    def test_round_by_round_simulation(self):
        """Simulate weeks 1 to 6 one by one."""
        for week in range(1, 7):
            count = sim_stage1_round(self.state)
            self.assertEqual(count, 6, f"Week {week} should simulate 6 matches")

        # Now regular season should be complete
        self.assertEqual(self.state['current_phase'], 'playoffs')
        self.assertTrue(all(m['status'] == 'completed' for m in self.state['regular_matches']))

        # Check standings
        self.assertEqual(len(self.state['alpha_standings']), 6)
        self.assertEqual(len(self.state['omega_standings']), 6)
        top3_alpha = [s for s in self.state['alpha_standings'] if s['advanced']]
        self.assertEqual(len(top3_alpha), 3)

        # Check playoff knockout round is ready
        ko1 = next(m for m in self.state['playoff_matches'] if m['match_id'] == 'ko_1')
        ko2 = next(m for m in self.state['playoff_matches'] if m['match_id'] == 'ko_2')
        self.assertTrue(ko1['ready'])
        self.assertTrue(ko2['ready'])
        self.assertIsNotNone(ko1['team_a'])
        self.assertIsNotNone(ko1['team_b'])

    def test_playoffs_and_full_completion(self):
        """Simulate remaining until complete and verify final standings and qualifiers."""
        total = sim_stage1_remaining(self.state)
        self.assertEqual(total, 44)  # 36 regular + 8 playoffs
        self.assertEqual(self.state['status'], 'completed')
        self.assertIsNotNone(self.state['champion'])
        self.assertIsNotNone(self.state['runner_up'])
        self.assertIsNotNone(self.state['third_place'])
        self.assertIsNotNone(self.state['fourth_place'])

        # Check qualifiers
        self.assertEqual(len(self.state['masters_qualifiers']), 3)
        self.assertEqual(len(self.state['ewc_qualifiers']), 2)  # Top 2 direct to EWC
        self.assertEqual(len(self.state['ewc_phase2_teams']), 6)  # Ranks 3-8 to EWC Qualifier Phase 2
        self.assertEqual(len(self.state['ewc_phase1_teams']), 4)  # Ranks 9-12 to EWC Qualifier Phase 1
        self.assertEqual(self.state['masters_qualifiers'][0]['regional_seed'], 1)
        self.assertEqual(self.state['masters_qualifiers'][1]['regional_seed'], 2)
        self.assertEqual(self.state['masters_qualifiers'][2]['regional_seed'], 3)

        # Check CP standings
        standings = self.state['standings']
        self.assertEqual(len(standings), 12)
        self.assertEqual(standings[0]['rank'], 1)
        self.assertEqual(standings[0]['cp'], 5)
        self.assertEqual(standings[1]['rank'], 2)
        self.assertEqual(standings[1]['cp'], 3)
        self.assertEqual(standings[2]['rank'], 3)
        self.assertEqual(standings[2]['cp'], 2)
        self.assertEqual(standings[3]['rank'], 4)
        self.assertEqual(standings[3]['cp'], 1)
        self.assertEqual(standings[4]['rank'], 5)
        self.assertEqual(standings[4]['cp'], 0)

    def test_edit_safeguards(self):
        """Verify safeguards against downstream corruption."""
        # 1. Complete regular season
        for _ in range(6):
            sim_stage1_round(self.state)

        # Play KO 1
        ko1 = next(m for m in self.state['playoff_matches'] if m['match_id'] == 'ko_1')
        resolve_stage1_match(self.state, 'ko_1')

        # Now attempting to edit a regular season match should raise ValueError
        m_reg = self.state['regular_matches'][0]
        with self.assertRaises(ValueError) as ctx:
            resolve_stage1_match(self.state, m_reg['match_id'], winner_id=m_reg['team_a_id'])
        self.assertIn("Playoffs", str(ctx.exception))

        # Play Upper SF 2 (which depends on KO 1)
        resolve_stage1_match(self.state, 'upper_sf_2')

        # Now attempting to edit KO 1 should raise ValueError because Upper SF 2 is completed!
        with self.assertRaises(ValueError) as ctx2:
            resolve_stage1_match(self.state, 'ko_1', winner_id=ko1['team_a_id'])
        self.assertIn("đã hoàn thành", str(ctx2.exception))


if __name__ == '__main__':
    unittest.main()
