import unittest
from engine.format.ewc_qualifier import (
    get_phase1_bracket_templates,
    get_phase2_bracket_templates,
    init_ewc_qualifier_region_state,
    resolve_ewc_qualifier_match,
    sim_ewc_qualifier_round,
    sim_ewc_qualifier_remaining,
    simulate_ewc_qualifier,
)


class TestEWCQualifierEngine(unittest.TestCase):
    def setUp(self):
        # 16 teams for Phase 1
        self.phase1_teams = [
            {'id': i, 'name': f'P1_Team_{i}', 'short_code': f'P1_{i}', 'story_rating': 75 + i}
            for i in range(1, 17)
        ]
        # 6 teams for Phase 2
        self.phase2_direct = [
            {'id': 100 + i, 'name': f'P2_Team_{i}', 'short_code': f'P2_{i}', 'story_rating': 85 + i}
            for i in range(1, 7)
        ]

    def test_templates_count(self):
        p1 = get_phase1_bracket_templates()
        p2 = get_phase2_bracket_templates()
        self.assertEqual(len(p1), 14)
        self.assertEqual(len(p2), 14)

    def test_init_state(self):
        state = init_ewc_qualifier_region_state('pacific', self.phase1_teams, self.phase2_direct)
        self.assertEqual(state['status'], 'in_progress')
        self.assertEqual(state['current_phase'], 'phase1')
        self.assertEqual(len(state['phase1_matches']), 14)
        self.assertEqual(len(state['phase2_matches']), 14)

        # Check R16 matchups
        r16_m1 = state['phase1_matches'][0]
        self.assertEqual(r16_m1['team_a']['id'], 1)   # Seed 1
        self.assertEqual(r16_m1['team_b']['id'], 16)  # Seed 16

        # Phase 2 matches initially have no teams
        p2_m1 = state['phase2_matches'][0]
        self.assertIsNone(p2_m1['team_a'])

    def test_full_simulation(self):
        state = init_ewc_qualifier_region_state('americas', self.phase1_teams, self.phase2_direct)
        total_played = sim_ewc_qualifier_remaining(state)
        self.assertEqual(total_played, 28)
        self.assertEqual(state['status'], 'completed')
        self.assertEqual(len(state['phase1_qualifiers']), 2)
        self.assertEqual(len(state['phase2_teams']), 8)
        self.assertIsNotNone(state['champion'])
        self.assertIsNotNone(state['runner_up'])
        self.assertEqual(len(state['ewc_qualifiers']), 2)

    def test_manual_override_and_cascade(self):
        state = init_ewc_qualifier_region_state('emea', self.phase1_teams, self.phase2_direct)
        # Play R16 match 1 manually
        m1 = state['phase1_matches'][0]
        resolve_ewc_qualifier_match(state, m1['id'], winner_id=16)  # Seed 16 upsets Seed 1
        self.assertEqual(m1['winner_id'], 16)
        self.assertTrue(m1['is_manual'])

        # Check QF1 team_a is now team 16
        qf1 = state['phase1_matches'][8]
        self.assertIsNotNone(qf1['team_a'])
        self.assertEqual(qf1['team_a']['id'], 16)

        # Edit M1: change winner to team 1
        resolve_ewc_qualifier_match(state, m1['id'], winner_id=1)
        self.assertEqual(m1['winner_id'], 1)
        self.assertEqual(qf1['team_a']['id'], 1)


if __name__ == '__main__':
    unittest.main()
