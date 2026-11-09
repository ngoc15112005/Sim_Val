import unittest
from engine.format.open_qualifier import (
    open_qualifier_config,
    generate_swiss_round_pairings,
    compute_swiss_standings,
    compute_swiss_records,
    get_playoff_bracket_templates,
    resolve_playoff_sources,
    simulate_single_match,
    simulate_open_qualifier,
)


class TestOpenQualifier(unittest.TestCase):

    def setUp(self):
        # 16 mock non-partner teams
        self.teams = [
            {'id': 100 + i, 'name': f'Team_{i+1}', 'short_code': f'T{i+1:02d}', 'current_rating': 70 + i}
            for i in range(16)
        ]

    def test_config(self):
        cfg = open_qualifier_config()
        self.assertEqual(cfg['team_count'], 16)
        self.assertEqual(cfg['advance_count'], 4)
        self.assertEqual(cfg['swiss_matches_total'], 33)
        self.assertEqual(cfg['playoff_matches_total'], 10)
        self.assertEqual(cfg['total_matches'], 43)

    def test_single_match_simulation(self):
        team_a = self.teams[0]
        team_b = self.teams[1]
        
        # Test BO1
        res_bo1 = simulate_single_match(team_a, team_b, bo=1)
        self.assertEqual(res_bo1['bo'], 1)
        self.assertIn(res_bo1['winner_id'], [team_a['id'], team_b['id']])
        self.assertEqual(len(res_bo1['maps']), 1)
        self.assertIn((res_bo1['team_a_score'], res_bo1['team_b_score']), [(1, 0), (0, 1)])

        # Test BO3
        res_bo3 = simulate_single_match(team_a, team_b, bo=3)
        self.assertEqual(res_bo3['bo'], 3)
        self.assertIn(res_bo3['winner_id'], [team_a['id'], team_b['id']])
        self.assertIn(len(res_bo3['maps']), [2, 3])
        self.assertIn((res_bo3['team_a_score'], res_bo3['team_b_score']), [(2, 0), (2, 1), (0, 2), (1, 2)])

    def test_swiss_simulation_breakdown(self):
        """Simulate Swiss step by step and verify rounds, BO types, and no rematches."""
        completed_matches = []

        # Round 1: 8 BO1
        r1_pairs = generate_swiss_round_pairings(self.teams, 1, completed_matches)
        self.assertEqual(len(r1_pairs), 8)
        for p in r1_pairs:
            self.assertEqual(p['bo'], 1)
            self.assertFalse(p['is_decider'])
            sim = simulate_single_match(p['team_a'], p['team_b'], bo=p['bo'])
            sim['round'] = 1
            completed_matches.append(sim)

        # Round 2: 8 BO1
        r2_pairs = generate_swiss_round_pairings(self.teams, 2, completed_matches)
        self.assertEqual(len(r2_pairs), 8)
        for p in r2_pairs:
            self.assertEqual(p['bo'], 1)
            self.assertFalse(p['is_decider'])
            sim = simulate_single_match(p['team_a'], p['team_b'], bo=p['bo'])
            sim['round'] = 2
            completed_matches.append(sim)

        # Round 3: 4 BO3 + 4 BO1 = 8 matches
        r3_pairs = generate_swiss_round_pairings(self.teams, 3, completed_matches)
        self.assertEqual(len(r3_pairs), 8)
        bo3_count_r3 = sum(1 for p in r3_pairs if p['bo'] == 3)
        bo1_count_r3 = sum(1 for p in r3_pairs if p['bo'] == 1)
        self.assertEqual(bo3_count_r3, 4)
        self.assertEqual(bo1_count_r3, 4)
        for p in r3_pairs:
            sim = simulate_single_match(p['team_a'], p['team_b'], bo=p['bo'])
            sim['round'] = 3
            completed_matches.append(sim)

        # Round 4: 6 BO3
        r4_pairs = generate_swiss_round_pairings(self.teams, 4, completed_matches)
        self.assertEqual(len(r4_pairs), 6)
        for p in r4_pairs:
            self.assertEqual(p['bo'], 3)
            self.assertTrue(p['is_decider'])
            sim = simulate_single_match(p['team_a'], p['team_b'], bo=p['bo'])
            sim['round'] = 4
            completed_matches.append(sim)

        # Round 5: 3 BO3
        r5_pairs = generate_swiss_round_pairings(self.teams, 5, completed_matches)
        self.assertEqual(len(r5_pairs), 3)
        for p in r5_pairs:
            self.assertEqual(p['bo'], 3)
            self.assertTrue(p['is_decider'])
            sim = simulate_single_match(p['team_a'], p['team_b'], bo=p['bo'])
            sim['round'] = 5
            completed_matches.append(sim)

        # Verify Total Swiss Matches = 33
        self.assertEqual(len(completed_matches), 33)

        # Verify Standings
        standings = compute_swiss_standings(self.teams, completed_matches)
        self.assertEqual(len(standings), 16)

        advancing = [s for s in standings if s['advanced']]
        eliminated = [s for s in standings if s['eliminated']]

        self.assertEqual(len(advancing), 8)
        self.assertEqual(len(eliminated), 8)

        # Check records
        wins_counts = [s['wins'] for s in advancing]
        losses_counts = [s['losses'] for s in eliminated]
        self.assertEqual(wins_counts.count(3), 8)
        self.assertEqual(losses_counts.count(3), 8)

        # Check records distribution: 2x 3-0, 3x 3-1, 3x 3-2
        adv_records = [(s['wins'], s['losses']) for s in advancing]
        self.assertEqual(adv_records.count((3, 0)), 2)
        self.assertEqual(adv_records.count((3, 1)), 3)
        self.assertEqual(adv_records.count((3, 2)), 3)

        # Check elimination records distribution: 2x 0-3, 3x 1-3, 3x 2-3
        elim_records = [(s['wins'], s['losses']) for s in eliminated]
        self.assertEqual(elim_records.count((0, 3)), 2)
        self.assertEqual(elim_records.count((1, 3)), 3)
        self.assertEqual(elim_records.count((2, 3)), 3)

        # Verify No Rematches in Swiss
        records = compute_swiss_records(self.teams, completed_matches)
        for t_id, r in records.items():
            opps = r['opponents']
            self.assertEqual(len(opps), len(set(opps)), f"Team {t_id} played a duplicate opponent!")

    def test_full_open_qualifier_simulation_multiple_times(self):
        """Run 50 complete simulations to ensure zero deadlocks and strict adherence to counts."""
        for run_idx in range(50):
            res = simulate_open_qualifier('pacific', self.teams)
            
            # Exactly 33 Swiss matches
            self.assertEqual(len(res['swiss_matches']), 33)
            # Exactly 10 Playoff matches
            self.assertEqual(len(res['playoff_matches']), 10)
            # Exactly 43 total matches
            self.assertEqual(res['total_matches_count'], 43)

            # Exactly 8 Swiss qualifiers
            self.assertEqual(len(res['swiss_qualifiers']), 8)
            # Exactly 8 Swiss eliminated
            self.assertEqual(len(res['swiss_eliminated']), 8)

            # Exactly 4 qualified teams for Kickoff
            self.assertEqual(len(res['qualified_teams']), 4)
            # All 4 qualified teams are unique
            qual_ids = [t['id'] for t in res['qualified_teams']]
            self.assertEqual(len(set(qual_ids)), 4)

            # All playoff matches must be BO3
            for m in res['playoff_matches']:
                self.assertEqual(m['bo'], 3)
                self.assertIn(len(m['maps']), [2, 3])

    def test_playoff_bracket_template_and_resolution(self):
        templates = get_playoff_bracket_templates()
        self.assertEqual(len(templates), 10)

        # Verify M1..M10 codes
        codes = [t['match_code'] for t in templates]
        self.assertEqual(codes, ['M1', 'M2', 'M3', 'M4', 'M5', 'M6', 'M7', 'M8', 'M9', 'M10'])

        # Verify qualifiers are M5, M6, M9, M10
        qual_matches = [t['match_code'] for t in templates if 'qualifier_slot' in t]
        self.assertEqual(qual_matches, ['M5', 'M6', 'M9', 'M10'])


if __name__ == '__main__':
    unittest.main()
