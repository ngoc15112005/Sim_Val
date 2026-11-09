import unittest
from engine.format.kickoff import (
    init_kickoff_region_state,
    resolve_kickoff_match,
    advance_kickoff_region,
    sim_kickoff_round,
    sim_kickoff_remaining,
)


class TestKickoffInteractive(unittest.TestCase):

    def setUp(self):
        # 12 mock participants: 8 partners + 4 open qualifiers
        self.participants = [
            {'id': 1, 'name': 'Partner_1', 'short_code': 'P01', 'is_partner': True, 'story_rating': 92},
            {'id': 2, 'name': 'Partner_2', 'short_code': 'P02', 'is_partner': True, 'story_rating': 90},
            {'id': 3, 'name': 'Partner_3', 'short_code': 'P03', 'is_partner': True, 'story_rating': 88},
            {'id': 4, 'name': 'Partner_4', 'short_code': 'P04', 'is_partner': True, 'story_rating': 86},
            {'id': 5, 'name': 'Partner_5', 'short_code': 'P05', 'is_partner': True, 'story_rating': 84},
            {'id': 6, 'name': 'Partner_6', 'short_code': 'P06', 'is_partner': True, 'story_rating': 82},
            {'id': 7, 'name': 'Partner_7', 'short_code': 'P07', 'is_partner': True, 'story_rating': 80},
            {'id': 8, 'name': 'Partner_8', 'short_code': 'P08', 'is_partner': True, 'story_rating': 78},
            {'id': 9, 'name': 'OpenQual_1', 'short_code': 'OQ1', 'is_partner': False, 'story_rating': 76, 'oq_seed': 1},
            {'id': 10, 'name': 'OpenQual_2', 'short_code': 'OQ2', 'is_partner': False, 'story_rating': 75, 'oq_seed': 2},
            {'id': 11, 'name': 'OpenQual_3', 'short_code': 'OQ3', 'is_partner': False, 'story_rating': 74, 'oq_seed': 3},
            {'id': 12, 'name': 'OpenQual_4', 'short_code': 'OQ4', 'is_partner': False, 'story_rating': 73, 'oq_seed': 4},
        ]
        self.state = init_kickoff_region_state('pacific', self.participants)

    def test_init_state(self):
        self.assertEqual(self.state['region_slug'], 'pacific')
        self.assertEqual(self.state['status'], 'in_progress')
        self.assertEqual(len(self.state['matches']), 22)
        self.assertTrue(all(m['status'] == 'pending' for m in self.state['matches']))

        # Upper R1 matches (4 matches) must have both teams ready
        r1_matches = [m for m in self.state['matches'] if 'r1' in m['round_name'] and m['round_type'] == 'upper']
        self.assertEqual(len(r1_matches), 4)
        for m in r1_matches:
            self.assertIsNotNone(m['team_a'])
            self.assertIsNotNone(m['team_b'])
            self.assertIsNone(m['placeholder_a'])
            self.assertIsNone(m['placeholder_b'])

        # Upper QF matches must have Bye team in team_a, and placeholder in team_b
        qf_matches = [m for m in self.state['matches'] if 'qf' in m['round_name'] and m['round_type'] == 'upper']
        self.assertEqual(len(qf_matches), 4)
        for m in qf_matches:
            self.assertIsNotNone(m['team_a'])
            self.assertIsNone(m['team_b'])
            self.assertIsNotNone(m['placeholder_b'])

    def test_single_match_roll_and_manual_entry(self):
        m1 = next(m for m in self.state['matches'] if m['round_name'] == 'upper_r1_m1')
        qf1 = next(m for m in self.state['matches'] if m['round_name'] == 'upper_qf_m1')
        lb1 = next(m for m in self.state['matches'] if m['round_name'] == 'lower_r1_m1')

        # Simulate roll
        res = resolve_kickoff_match(self.state, m1['round_name'], winner_id=None)
        self.assertEqual(res['status'], 'completed')
        self.assertFalse(res['is_manual'])
        self.assertIn(res['winner_id'], [m1['team_a_id'], m1['team_b_id']])

        # Winner feeds to Upper QF 1
        self.assertEqual(qf1['team_b']['id'], res['winner_id'])
        # Loser feeds to Lower R1 1
        self.assertEqual(lb1['team_a']['id'], res['loser_id'])

        # Manual edit before downstream matches are played
        new_winner_id = res['loser_id']
        resolve_kickoff_match(self.state, m1['round_name'], winner_id=new_winner_id)
        self.assertEqual(m1['winner_id'], new_winner_id)
        self.assertTrue(m1['is_manual'])
        # Downstream feeder slots automatically updated
        self.assertEqual(qf1['team_b']['id'], new_winner_id)

    def test_downstream_safeguard(self):
        m1 = next(m for m in self.state['matches'] if m['round_name'] == 'upper_r1_m1')
        qf1 = next(m for m in self.state['matches'] if m['round_name'] == 'upper_qf_m1')

        # Resolve m1
        resolve_kickoff_match(self.state, m1['round_name'], winner_id=m1['team_a_id'])
        # Now qf1 has both teams
        self.assertIsNotNone(qf1['team_a'])
        self.assertIsNotNone(qf1['team_b'])

        # Resolve qf1
        resolve_kickoff_match(self.state, qf1['round_name'], winner_id=qf1['team_a_id'])
        self.assertEqual(qf1['status'], 'completed')

        # Attempt to edit m1 now must fail because qf1 is completed!
        with self.assertRaises(ValueError) as ctx:
            resolve_kickoff_match(self.state, m1['round_name'], winner_id=m1['team_b_id'])
        self.assertIn("trận đấu nhánh tiếp theo đã hoàn thành", str(ctx.exception))

    def test_sim_round_progression(self):
        # Wave 1 (Upper R1: 4 matches)
        c1 = sim_kickoff_round(self.state)
        self.assertEqual(c1, 4)

        # Wave 2 (Upper QF: 4 matches, Bye teams vs Upper R1 winners)
        c2 = sim_kickoff_round(self.state)
        self.assertEqual(c2, 4)

        # Wave 3 (Upper SF: 2 matches + Lower R1: 4 matches [Losers of Upper R1 vs Losers of Upper QF] = 6 matches)
        c3 = sim_kickoff_round(self.state)
        self.assertEqual(c3, 6)

    def test_full_kickoff_simulation_and_standings(self):
        total = sim_kickoff_remaining(self.state)
        self.assertEqual(total, 22)
        self.assertEqual(self.state['status'], 'completed')
        self.assertEqual(len(self.state['standings']), 12)
        self.assertEqual(len(self.state['major_qualifiers']), 2)

        st = self.state['standings']
        # Check Championship Points allocation
        self.assertEqual(st[0]['rank'], 1)
        self.assertEqual(st[0]['championship_points'], 3)
        self.assertEqual(st[1]['rank'], 2)
        self.assertEqual(st[1]['championship_points'], 2)
        self.assertEqual(st[2]['rank'], 3)
        self.assertEqual(st[2]['championship_points'], 1)
        self.assertEqual(st[3]['rank'], 4)
        self.assertEqual(st[3]['championship_points'], 1)
        self.assertEqual(st[4]['rank'], 5)
        self.assertEqual(st[4]['championship_points'], 0)


if __name__ == '__main__':
    unittest.main()
