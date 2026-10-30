import unittest
from engine.format.kickoff import (
    kickoff_config,
    seed_kickoff_participants,
    get_kickoff_bracket_templates,
    simulate_kickoff_match,
    simulate_kickoff_tournament,
)


class TestKickoff(unittest.TestCase):

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

    def test_config(self):
        cfg = kickoff_config()
        self.assertEqual(cfg['team_count'], 12)
        self.assertEqual(cfg['partner_count'], 8)
        self.assertEqual(cfg['open_qualifier_count'], 4)
        self.assertEqual(cfg['byes_count'], 4)
        self.assertEqual(cfg['upper_matches'], 11)
        self.assertEqual(cfg['lower_matches'], 10)
        self.assertEqual(cfg['grand_final_matches'], 1)
        self.assertEqual(cfg['total_matches'], 22)
        self.assertEqual(cfg['major_qualifiers'], 2)

    def test_seeding_and_byes(self):
        seeding = seed_kickoff_participants(self.participants)
        seeds = seeding['seeds']

        # Byes are top 4 partners (Seeds 1..4)
        self.assertEqual(len(seeding['byes']), 4)
        self.assertEqual(seeds[1]['short_code'], 'P01')
        self.assertEqual(seeds[2]['short_code'], 'P02')
        self.assertEqual(seeds[3]['short_code'], 'P03')
        self.assertEqual(seeds[4]['short_code'], 'P04')

        # Upper R1 Partners are Seeds 5..8
        self.assertEqual(len(seeding['upper_partners']), 4)
        self.assertEqual(seeds[5]['short_code'], 'P05')
        self.assertEqual(seeds[6]['short_code'], 'P06')
        self.assertEqual(seeds[7]['short_code'], 'P07')
        self.assertEqual(seeds[8]['short_code'], 'P08')

        # Upper R1 Open Qualifiers are Seeds 9..12
        self.assertEqual(len(seeding['open_qualifiers']), 4)
        self.assertEqual(seeds[9]['short_code'], 'OQ1')
        self.assertEqual(seeds[10]['short_code'], 'OQ2')
        self.assertEqual(seeds[11]['short_code'], 'OQ3')
        self.assertEqual(seeds[12]['short_code'], 'OQ4')

    def test_bracket_template_rules(self):
        templates = get_kickoff_bracket_templates()
        self.assertEqual(len(templates), 22)

        # Check BO formats
        bo5_matches = [t['round_name'] for t in templates if t['bo'] == 5]
        self.assertEqual(set(bo5_matches), {'lower_final', 'grand_final'})

        bo3_matches = [t['round_name'] for t in templates if t['bo'] == 3]
        self.assertEqual(len(bo3_matches), 20)

        # Verify Upper R1 pairings (Partner vs Open Qualifier)
        r1_matches = [t for t in templates if t['round_type'] == 'upper' and 'r1' in t['round_name']]
        self.assertEqual(len(r1_matches), 4)
        for m in r1_matches:
            src_a = m['team_a_source']['value']
            src_b = m['team_b_source']['value']
            self.assertTrue(5 <= src_a <= 8, f"Team A should be Partner seed 5-8, got {src_a}")
            self.assertTrue(9 <= src_b <= 12, f"Team B should be Open Qualifier seed 9-12, got {src_b}")

    def test_full_simulation_run(self):
        res = simulate_kickoff_tournament('pacific', self.participants)
        self.assertEqual(res['total_matches_count'], 22)
        self.assertEqual(len(res['matches']), 22)

        # Check Standings
        standings = res['standings']
        self.assertEqual(len(standings), 12)

        # Champion (Rank 1)
        self.assertEqual(standings[0]['rank'], 1)
        self.assertEqual(standings[0]['championship_points'], 3)
        self.assertTrue(standings[0]['major_qualified'])
        self.assertEqual(standings[0]['major_seed'], 1)

        # Runner-up (Rank 2)
        self.assertEqual(standings[1]['rank'], 2)
        self.assertEqual(standings[1]['championship_points'], 2)
        self.assertTrue(standings[1]['major_qualified'])
        self.assertEqual(standings[1]['major_seed'], 2)

        # 3rd Place
        self.assertEqual(standings[2]['rank'], 3)
        self.assertEqual(standings[2]['championship_points'], 1)
        self.assertFalse(standings[2]['major_qualified'])

        # 4th Place
        self.assertEqual(standings[3]['rank'], 4)
        self.assertEqual(standings[3]['championship_points'], 1)
        self.assertFalse(standings[3]['major_qualified'])

        # 5-12 Place (0 CP)
        for s in standings[4:]:
            self.assertEqual(s['championship_points'], 0)
            self.assertFalse(s['major_qualified'])

        # Major Qualifiers
        self.assertEqual(len(res['major_qualifiers']), 2)
        self.assertEqual(res['major_qualifiers'][0]['id'], standings[0]['club_id'])
        self.assertEqual(res['major_qualifiers'][1]['id'], standings[1]['club_id'])

    def test_manual_override(self):
        """Test forcing an underdog open qualifier to win a match."""
        # Force OQ4 (id 12) to win Upper R1 Match 1 against Partner 5 (id 5)
        overrides = {
            'upper_r1_m1': {
                'winner_id': 12,
                'maps': [
                    {'map_number': 1, 'team_a_score': 8, 'team_b_score': 13, 'winner_id': 12},
                    {'map_number': 2, 'team_a_score': 10, 'team_b_score': 13, 'winner_id': 12},
                ]
            }
        }
        res = simulate_kickoff_tournament('pacific', self.participants, manual_overrides=overrides)
        m1 = res['completed_dict']['upper_r1_m1']
        self.assertEqual(m1['winner_id'], 12)
        self.assertTrue(m1['is_manual'])

        # Verify OQ4 (id 12) advanced into Upper QF Match 1
        qf1 = res['completed_dict']['upper_qf_m1']
        self.assertEqual(qf1['team_b']['id'], 12)

    def test_multiple_iterations_no_deadlocks(self):
        """Run 50 complete simulations to ensure zero deadlocks and 100% stability."""
        for _ in range(50):
            res = simulate_kickoff_tournament('pacific', self.participants)
            self.assertEqual(res['total_matches_count'], 22)
            self.assertEqual(len(res['major_qualifiers']), 2)


if __name__ == '__main__':
    unittest.main()
