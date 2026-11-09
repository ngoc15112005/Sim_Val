"""
test_vct_stage1_2026_spec.py — Complete Automated Test Suite for VCT Stage 1 2026 Specification
Validates all requirements specified in e:\\Download\\VCT_STAGE1_2026_AI_AGENT_SPEC.txt.
"""

import unittest
from engine.format.stage1 import (
    init_stage1_region_state,
    resolve_stage1_match,
    sim_stage1_round,
    sim_stage1_remaining,
    stage1_config,
    compute_stage1_group_standings,
)
from engine.points import get_stage_points
from engine.tiebreaker import compute_vct_group_standings


class TestVCTStage12026Spec(unittest.TestCase):
    def setUp(self):
        # 12 representative teams (A1..A6 and O1..O6)
        self.participants = [
            {'id': 1, 'name': 'Alpha 1', 'short_code': 'A1', 'story_rating': 90, 'kickoff_rank': 1},
            {'id': 2, 'name': 'Omega 1', 'short_code': 'O1', 'story_rating': 89, 'kickoff_rank': 2},
            {'id': 3, 'name': 'Omega 2', 'short_code': 'O2', 'story_rating': 88, 'kickoff_rank': 3},
            {'id': 4, 'name': 'Alpha 2', 'short_code': 'A2', 'story_rating': 87, 'kickoff_rank': 4},
            {'id': 5, 'name': 'Alpha 3', 'short_code': 'A3', 'story_rating': 86, 'kickoff_rank': 5},
            {'id': 6, 'name': 'Omega 3', 'short_code': 'O3', 'story_rating': 85, 'kickoff_rank': 6},
            {'id': 7, 'name': 'Omega 4', 'short_code': 'O4', 'story_rating': 84, 'kickoff_rank': 7},
            {'id': 8, 'name': 'Alpha 4', 'short_code': 'A4', 'story_rating': 83, 'kickoff_rank': 8},
            {'id': 9, 'name': 'Alpha 5', 'short_code': 'A5', 'story_rating': 82, 'kickoff_rank': 9},
            {'id': 10, 'name': 'Omega 5', 'short_code': 'O5', 'story_rating': 81, 'kickoff_rank': 10},
            {'id': 11, 'name': 'Omega 6', 'short_code': 'O6', 'story_rating': 80, 'kickoff_rank': 11},
            {'id': 12, 'name': 'Alpha 6', 'short_code': 'A6', 'story_rating': 79, 'kickoff_rank': 12},
        ]

    # ====================================================
    # 1. REGULAR SEASON VALIDATION
    # ====================================================
    def test_regular_season_structure(self):
        state = init_stage1_region_state('pacific', self.participants)

        # [ ] Mỗi khu vực có 12 đội.
        self.assertEqual(len(state['participants']), 12)

        # [ ] Alpha có chính xác 6 đội.
        self.assertEqual(len(state['group_alpha']), 6)

        # [ ] Omega có chính xác 6 đội.
        self.assertEqual(len(state['group_omega']), 6)

        alpha_ids = {t['id'] for t in state['group_alpha']}
        omega_ids = {t['id'] for t in state['group_omega']}

        # No team overlaps
        self.assertEqual(len(alpha_ids.intersection(omega_ids)), 0)

        # [ ] Mỗi bảng có chính xác 15 series, tổng cộng 30 series Regular Season.
        regular_matches = state['regular_matches']
        self.assertEqual(len(regular_matches), 30)

        alpha_matches = [m for m in regular_matches if m['group'] == 'Alpha']
        omega_matches = [m for m in regular_matches if m['group'] == 'Omega']
        self.assertEqual(len(alpha_matches), 15)
        self.assertEqual(len(omega_matches), 15)

        # [ ] Không có trận Regular Season giữa Alpha và Omega.
        for m in regular_matches:
            t_a = m['team_a']['id']
            t_b = m['team_b']['id']
            if m['group'] == 'Alpha':
                self.assertIn(t_a, alpha_ids)
                self.assertIn(t_b, alpha_ids)
            else:
                self.assertIn(t_a, omega_ids)
                self.assertIn(t_b, omega_ids)

            # [ ] Mọi series Regular Season đều là Bo3.
            self.assertEqual(m['bo'], 3)

        # [ ] Mỗi đội có chính xác 5 đối thủ khác nhau trong bảng.
        for t_id in alpha_ids:
            opponents = set()
            for m in alpha_matches:
                if m['team_a']['id'] == t_id:
                    opponents.add(m['team_b']['id'])
                elif m['team_b']['id'] == t_id:
                    opponents.add(m['team_a']['id'])
            self.assertEqual(len(opponents), 5)

        for t_id in omega_ids:
            opponents = set()
            for m in omega_matches:
                if m['team_a']['id'] == t_id:
                    opponents.add(m['team_b']['id'])
                elif m['team_b']['id'] == t_id:
                    opponents.add(m['team_a']['id'])
            self.assertEqual(len(opponents), 5)

    # ====================================================
    # 2. GROUP STANDINGS & TIEBREAKER VALIDATION
    # ====================================================
    def test_two_team_tiebreaker(self):
        """[ ] Tiebreak hai đội bằng nhau được xử lý chính xác bởi Head-to-Head."""
        teams = [{'id': 101, 'name': 'Team A'}, {'id': 102, 'name': 'Team B'}, {'id': 103, 'name': 'Team C'}]
        # Team A beat Team B in their direct match
        # Team A has 1 win (over B)
        # Team B has 1 win (over C)
        # Team C has 1 win (over A)
        # But if only Team A and Team B have equal match wins (say both 1 win):
        matches = [
            # A beat B 2-0
            {'status': 'completed', 'team_a_id': 101, 'team_b_id': 102, 'team_a_score': 2, 'team_b_score': 0, 'maps': [{'team_a_score': 13, 'team_b_score': 8}, {'team_a_score': 13, 'team_b_score': 9}]},
            # A lost to C 0-2
            {'status': 'completed', 'team_a_id': 101, 'team_b_id': 103, 'team_a_score': 0, 'team_b_score': 2, 'maps': [{'team_a_score': 8, 'team_b_score': 13}, {'team_a_score': 9, 'team_b_score': 13}]},
            # B beat C 2-0
            {'status': 'completed', 'team_a_id': 102, 'team_b_id': 103, 'team_a_score': 2, 'team_b_score': 0, 'maps': [{'team_a_score': 13, 'team_b_score': 8}, {'team_a_score': 13, 'team_b_score': 9}]},
        ]
        # In this cycle:
        # A, B, C all have 1 win, 1 loss.
        # A beat B (2-0, +2)
        # B beat C (2-0, +2)
        # C beat A (2-0, +2)
        # Mini-table: each is 1-1, map diff 0, round diff 0!
        standings = compute_vct_group_standings(teams, matches)
        self.assertEqual(len(standings), 3)

        # Test simple 2-team tiebreak: A beat B (2-1), C lost both (0 wins).
        matches_2team = [
            {'status': 'completed', 'team_a_id': 101, 'team_b_id': 102, 'team_a_score': 2, 'team_b_score': 1, 'maps': [{'team_a_score': 13, 'team_b_score': 8}, {'team_a_score': 9, 'team_b_score': 13}, {'team_a_score': 13, 'team_b_score': 10}]},
            {'status': 'completed', 'team_a_id': 101, 'team_b_id': 103, 'team_a_score': 2, 'team_b_score': 0, 'maps': [{'team_a_score': 13, 'team_b_score': 5}, {'team_a_score': 13, 'team_b_score': 5}]},
            {'status': 'completed', 'team_a_id': 102, 'team_b_id': 103, 'team_a_score': 2, 'team_b_score': 0, 'maps': [{'team_a_score': 13, 'team_b_score': 5}, {'team_a_score': 13, 'team_b_score': 5}]},
        ]
        # A: 2-0, B: 1-1, C: 0-2
        st2 = compute_vct_group_standings(teams, matches_2team)
        self.assertEqual(st2[0]['club_id'], 101)
        self.assertEqual(st2[1]['club_id'], 102)
        self.assertEqual(st2[2]['club_id'], 103)

    def test_three_team_mini_table_and_subgroup_restart(self):
        """[ ] Mini-table cho trường hợp 3 đội bằng nhau và restart từ tiêu chí 1."""
        # Teams 1, 2, 3, 4:
        # Team 1, 2, 3 all finish 2-1. Team 4 finishes 0-3.
        # Between 1, 2, 3:
        # 1 beat 2 (2-0, +2 map diff)
        # 2 beat 3 (2-1, +1 map diff)
        # 3 beat 1 (2-1, +1 map diff)
        # Mini-table map diffs:
        # Team 1: vs 2 (+2), vs 3 (-1) => +1
        # Team 2: vs 1 (-2), vs 3 (+1) => -1
        # Team 3: vs 2 (-1), vs 1 (+1) => 0
        # Criterion 2 separates all three: Team 1 (+1) > Team 3 (0) > Team 2 (-1)!
        teams = [{'id': i, 'name': f"T{i}"} for i in [1, 2, 3, 4]]
        matches = [
            {'status': 'completed', 'team_a_id': 1, 'team_b_id': 2, 'team_a_score': 2, 'team_b_score': 0, 'maps': [{'team_a_score': 13, 'team_b_score': 7}, {'team_a_score': 13, 'team_b_score': 8}]},
            {'status': 'completed', 'team_a_id': 2, 'team_b_id': 3, 'team_a_score': 2, 'team_b_score': 1, 'maps': [{'team_a_score': 13, 'team_b_score': 8}, {'team_a_score': 8, 'team_b_score': 13}, {'team_a_score': 13, 'team_b_score': 11}]},
            {'status': 'completed', 'team_a_id': 3, 'team_b_id': 1, 'team_a_score': 2, 'team_b_score': 1, 'maps': [{'team_a_score': 13, 'team_b_score': 11}, {'team_a_score': 7, 'team_b_score': 13}, {'team_a_score': 13, 'team_b_score': 10}]},
            # Team 4 loses to everyone 0-2
            {'status': 'completed', 'team_a_id': 1, 'team_b_id': 4, 'team_a_score': 2, 'team_b_score': 0, 'maps': [{'team_a_score': 13, 'team_b_score': 5}, {'team_a_score': 13, 'team_b_score': 5}]},
            {'status': 'completed', 'team_a_id': 2, 'team_b_id': 4, 'team_a_score': 2, 'team_b_score': 0, 'maps': [{'team_a_score': 13, 'team_b_score': 5}, {'team_a_score': 13, 'team_b_score': 5}]},
            {'status': 'completed', 'team_a_id': 3, 'team_b_id': 4, 'team_a_score': 2, 'team_b_score': 0, 'maps': [{'team_a_score': 13, 'team_b_score': 5}, {'team_a_score': 13, 'team_b_score': 5}]},
        ]
        st = compute_vct_group_standings(teams, matches)
        self.assertEqual(st[0]['club_id'], 1)
        self.assertEqual(st[1]['club_id'], 3)
        self.assertEqual(st[2]['club_id'], 2)
        self.assertEqual(st[3]['club_id'], 4)

    def test_unresolved_tie_no_randomization(self):
        """[ ] Nếu vẫn hòa sau toàn bộ tiêu chí, hệ thống không random đội đi tiếp và flag unresolved_tie."""
        teams = [{'id': 1, 'name': 'A'}, {'id': 2, 'name': 'B'}]
        # Identical matches (e.g. 0 matches played or perfectly symmetric)
        st = compute_vct_group_standings(teams, [])
        self.assertTrue(st[0]['unresolved_tie'])
        self.assertTrue(st[1]['unresolved_tie'])

    # ====================================================
    # 3. PLAYOFF ENTRY & MATCHUPS (MODIFIED DOUBLE ELIMINATION)
    # ====================================================
    def test_playoff_bracket_matchups_and_progression(self):
        """Validate all 12 playoff matchups, seeds, byes, and cross-pairing in Section 12."""
        state = init_stage1_region_state('americas', self.participants)

        # 1. Complete Regular Season
        for _ in range(5):
            sim_stage1_round(state)
        self.assertEqual(state['current_phase'], 'playoffs')

        # [ ] Chính xác 4 đội mỗi bảng được vào playoff.
        # [ ] Chính xác 2 đội mỗi bảng bị loại.
        top4_alpha = [s for s in state['alpha_standings'] if s['advanced']]
        top4_omega = [s for s in state['omega_standings'] if s['advanced']]
        self.assertEqual(len(top4_alpha), 4)
        self.assertEqual(len(top4_omega), 4)

        # Verify seeds
        a1 = state['alpha_standings'][0]['team']
        a2 = state['alpha_standings'][1]['team']
        a3 = state['alpha_standings'][2]['team']
        a4 = state['alpha_standings'][3]['team']
        o1 = state['omega_standings'][0]['team']
        o2 = state['omega_standings'][1]['team']
        o3 = state['omega_standings'][2]['team']
        o4 = state['omega_standings'][3]['team']

        playoffs = {m['match_id']: m for m in state['playoff_matches']}

        # [ ] Tổng số playoff series mỗi khu vực là 12.
        self.assertEqual(len(state['playoff_matches']), 12)

        # [ ] UBR1-M1 = O2 vs A3.
        self.assertEqual(playoffs['UBR1-M1']['team_a']['id'], o2['id'])
        self.assertEqual(playoffs['UBR1-M1']['team_b']['id'], a3['id'])
        self.assertEqual(playoffs['UBR1-M1']['bo'], 3)
        self.assertTrue(playoffs['UBR1-M1']['ready'])

        # [ ] UBR1-M2 = A2 vs O3.
        self.assertEqual(playoffs['UBR1-M2']['team_a']['id'], a2['id'])
        self.assertEqual(playoffs['UBR1-M2']['team_b']['id'], o3['id'])
        self.assertEqual(playoffs['UBR1-M2']['bo'], 3)
        self.assertTrue(playoffs['UBR1-M2']['ready'])

        # Upper Semis must not be ready until UBR1 completes
        self.assertFalse(playoffs['UBSF-M1']['ready'])
        self.assertFalse(playoffs['UBSF-M2']['ready'])

        # Simulate UBR1-M1: O2 wins over A3
        resolve_stage1_match(state, 'UBR1-M1', winner_id=o2['id'])
        # Simulate UBR1-M2: A2 wins over O3
        resolve_stage1_match(state, 'UBR1-M2', winner_id=a2['id'])

        # [ ] UBSF-M1 = A1 vs Winner(UBR1-M1) (O2).
        self.assertTrue(playoffs['UBSF-M1']['ready'])
        self.assertEqual(playoffs['UBSF-M1']['team_a']['id'], a1['id'])
        self.assertEqual(playoffs['UBSF-M1']['team_b']['id'], o2['id'])
        self.assertEqual(playoffs['UBSF-M1']['bo'], 3)

        # [ ] UBSF-M2 = O1 vs Winner(UBR1-M2) (A2).
        self.assertTrue(playoffs['UBSF-M2']['ready'])
        self.assertEqual(playoffs['UBSF-M2']['team_a']['id'], o1['id'])
        self.assertEqual(playoffs['UBSF-M2']['team_b']['id'], a2['id'])
        self.assertEqual(playoffs['UBSF-M2']['bo'], 3)

        # [ ] LBR1-M1 = O4 vs Loser(UBR1-M1) (A3).
        self.assertTrue(playoffs['LBR1-M1']['ready'])
        self.assertEqual(playoffs['LBR1-M1']['team_a']['id'], o4['id'])
        self.assertEqual(playoffs['LBR1-M1']['team_b']['id'], a3['id'])
        self.assertEqual(playoffs['LBR1-M1']['bo'], 3)

        # [ ] LBR1-M2 = A4 vs Loser(UBR1-M2) (O3).
        self.assertTrue(playoffs['LBR1-M2']['ready'])
        self.assertEqual(playoffs['LBR1-M2']['team_a']['id'], a4['id'])
        self.assertEqual(playoffs['LBR1-M2']['team_b']['id'], o3['id'])
        self.assertEqual(playoffs['LBR1-M2']['bo'], 3)

        # Simulate UBSF matches:
        # UBSF-M1: A1 beats O2
        resolve_stage1_match(state, 'UBSF-M1', winner_id=a1['id'])
        # UBSF-M2: O1 beats A2
        resolve_stage1_match(state, 'UBSF-M2', winner_id=o1['id'])

        # Simulate LBR1 matches:
        # LBR1-M1: O4 beats A3 (A3 eliminated rank 7-8)
        resolve_stage1_match(state, 'LBR1-M1', winner_id=o4['id'])
        # LBR1-M2: A4 beats O3 (O3 eliminated rank 7-8)
        resolve_stage1_match(state, 'LBR1-M2', winner_id=a4['id'])

        # [ ] LBR2-M1 = Winner(LBR1-M2) (A4) vs Loser(UBSF-M1) (O2).
        self.assertTrue(playoffs['LBR2-M1']['ready'])
        self.assertEqual(playoffs['LBR2-M1']['team_a']['id'], a4['id'])
        self.assertEqual(playoffs['LBR2-M1']['team_b']['id'], o2['id'])
        self.assertEqual(playoffs['LBR2-M1']['bo'], 3)

        # [ ] LBR2-M2 = Winner(LBR1-M1) (O4) vs Loser(UBSF-M2) (A2).
        self.assertTrue(playoffs['LBR2-M2']['ready'])
        self.assertEqual(playoffs['LBR2-M2']['team_a']['id'], o4['id'])
        self.assertEqual(playoffs['LBR2-M2']['team_b']['id'], a2['id'])
        self.assertEqual(playoffs['LBR2-M2']['bo'], 3)

        # [ ] UBF = Winner(UBSF-M1) (A1) vs Winner(UBSF-M2) (O1).
        self.assertTrue(playoffs['UBF']['ready'])
        self.assertEqual(playoffs['UBF']['team_a']['id'], a1['id'])
        self.assertEqual(playoffs['UBF']['team_b']['id'], o1['id'])
        self.assertEqual(playoffs['UBF']['bo'], 3)

        # Simulate LBR2 and UBF:
        # LBR2-M1: A4 beats O2 (O2 eliminated rank 5-6)
        resolve_stage1_match(state, 'LBR2-M1', winner_id=a4['id'])
        # LBR2-M2: A2 beats O4 (O4 eliminated rank 5-6)
        resolve_stage1_match(state, 'LBR2-M2', winner_id=a2['id'])
        # UBF: A1 beats O1 (A1 to GF, O1 to LBF)
        resolve_stage1_match(state, 'UBF', winner_id=a1['id'])

        # [ ] LBR3 = Winner(LBR2-M1) (A4) vs Winner(LBR2-M2) (A2).
        self.assertTrue(playoffs['LBR3']['ready'])
        self.assertEqual(playoffs['LBR3']['team_a']['id'], a4['id'])
        self.assertEqual(playoffs['LBR3']['team_b']['id'], a2['id'])
        self.assertEqual(playoffs['LBR3']['bo'], 3)

        # Simulate LBR3: A4 beats A2 (A2 eliminated rank 4)
        resolve_stage1_match(state, 'LBR3', winner_id=a4['id'])

        # [ ] LBF = Loser(UBF) (O1) vs Winner(LBR3) (A4). (BO5)
        self.assertTrue(playoffs['LBF']['ready'])
        self.assertEqual(playoffs['LBF']['team_a']['id'], o1['id'])
        self.assertEqual(playoffs['LBF']['team_b']['id'], a4['id'])
        self.assertEqual(playoffs['LBF']['bo'], 5)

        # Simulate LBF: O1 beats A4 (A4 eliminated rank 3)
        resolve_stage1_match(state, 'LBF', winner_id=o1['id'])

        # [ ] GF = Winner(UBF) (A1) vs Winner(LBF) (O1). (BO5, No reset)
        self.assertTrue(playoffs['GF']['ready'])
        self.assertEqual(playoffs['GF']['team_a']['id'], a1['id'])
        self.assertEqual(playoffs['GF']['team_b']['id'], o1['id'])
        self.assertEqual(playoffs['GF']['bo'], 5)

        # Simulate GF: A1 beats O1
        resolve_stage1_match(state, 'GF', winner_id=a1['id'])

        # Check completed status
        self.assertEqual(state['status'], 'completed')
        self.assertEqual(state['current_phase'], 'completed')

        # [ ] Hạng 1 = đội thắng Grand Final.
        self.assertEqual(state['champion']['id'], a1['id'])
        # [ ] Hạng 2 = đội thua Grand Final.
        self.assertEqual(state['runner_up']['id'], o1['id'])
        # [ ] Hạng 3 = đội thua Lower Final.
        self.assertEqual(state['third_place']['id'], a4['id'])
        # [ ] Hạng 4 = đội thua Lower Round 3.
        self.assertEqual(state['fourth_place']['id'], a2['id'])

        # [ ] Championship Points Bonus: 6 / 4 / 3 / 2 cho hạng 1 / 2 / 3 / 4.
        self.assertEqual(get_stage_points('stage1_playoffs', rank=1), 6)
        self.assertEqual(get_stage_points('stage1_playoffs', rank=2), 4)
        self.assertEqual(get_stage_points('stage1_playoffs', rank=3), 3)
        self.assertEqual(get_stage_points('stage1_playoffs', rank=4), 2)
        self.assertEqual(get_stage_points('stage1_playoffs', rank=5), 0)
        self.assertEqual(get_stage_points('stage1_playoffs', rank=6), 0)
        self.assertEqual(get_stage_points('stage1_playoffs', rank=7), 0)
        self.assertEqual(get_stage_points('stage1_playoffs', rank=8), 0)

        # [ ] Top 3 giành vé Masters.
        qualifiers = state['masters_qualifiers']
        self.assertEqual(len(qualifiers), 3)
        self.assertEqual(qualifiers[0]['team']['id'], a1['id'])
        self.assertEqual(qualifiers[0]['regional_seed'], 1)
        self.assertEqual(qualifiers[1]['team']['id'], o1['id'])
        self.assertEqual(qualifiers[1]['regional_seed'], 2)
        self.assertEqual(qualifiers[2]['team']['id'], a4['id'])
        self.assertEqual(qualifiers[2]['regional_seed'], 3)

    # ====================================================
    # 4. REGIONAL UNIFORMITY (CHINA, AMERICAS, EMEA, PACIFIC)
    # ====================================================
    def test_regional_uniformity(self):
        """[ ] Cả 4 khu vực sử dụng cùng thể thức, China KHÔNG có Cross Play Decider."""
        cfg = stage1_config()
        self.assertFalse(cfg['china_seed_decider_enabled'])
        self.assertEqual(cfg['playoff_matches'], 12)
        self.assertEqual(cfg['playoff_teams'], 8)

        for region in ['americas', 'emea', 'pacific', 'china']:
            st = init_stage1_region_state(region, self.participants)
            self.assertEqual(len(st['regular_matches']), 30, f"{region} must have 30 regular matches")
            self.assertEqual(len(st['playoff_matches']), 12, f"{region} must have 12 playoff matches")
            self.assertEqual(st['playoff_matches'][0]['match_id'], 'UBR1-M1')
            self.assertEqual(st['playoff_matches'][11]['match_id'], 'GF')


if __name__ == '__main__':
    unittest.main()
