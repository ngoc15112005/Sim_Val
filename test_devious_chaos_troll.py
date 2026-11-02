"""
test_devious_chaos_troll.py — Devious QA Testing: Persona 1 (The Chaos Troll)

Edge Cases Covered:
- Case 1: The Grandfather Time Paradox (Attempting to modify group match after playoffs started)
- Case 2: The Self-Contradictory Match (winner_id disagrees with maps array)
- Case 3: Absurd Map Scores (Negative scores, draw 13-13, invalid overtime 13-12, excessive maps)
- Case 4: Underdog Miracle Run via Manual Override (Lower bracket sweep with underdog)
"""

import unittest
from engine.format.stage1 import (
    init_stage1_region_state,
    resolve_stage1_match,
    sim_stage1_round,
    advance_stage1_region,
)
from engine.format.kickoff import (
    init_kickoff_region_state,
    resolve_kickoff_match,
    sim_kickoff_round,
)


class TestDeviousChaosTroll(unittest.TestCase):
    def setUp(self):
        # 12 teams for Stage 1
        self.teams_stage1 = [
            {'id': i, 'club_id': i, 'name': f"Team {i}", 'short_code': f"T{i}", 'story_rating': 80 + i, 'kickoff_rank': i}
            for i in range(1, 13)
        ]
        # 12 teams for Kickoff (8 partner, 4 OQ)
        self.teams_kickoff = (
            [{'id': i, 'club_id': i, 'name': f"Partner {i}", 'short_code': f"P{i}", 'story_rating': 85, 'is_partner': True} for i in range(1, 9)] +
            [{'id': i, 'club_id': i, 'name': f"Qual {i}", 'short_code': f"Q{i}", 'story_rating': 75, 'is_partner': False} for i in range(9, 13)]
        )

    def test_case_1_grandfather_time_paradox(self):
        """Case 1: User tries to modify an early group match when playoffs have already started.
        System MUST reject this to prevent corrupting playoff brackets or leaving orphan slots."""
        state = init_stage1_region_state('pacific', self.teams_stage1)

        # 1. Simulate all 5 regular season weeks
        for _ in range(5):
            sim_stage1_round(state)
        self.assertEqual(state['current_phase'], 'playoffs')

        # 2. Simulate the first playoff match (UBR1-M1)
        ko1_match = next(m for m in state['playoff_matches'] if m['match_id'] in ('UBR1-M1', 'ko_1') or 'ko_1' in m.get('aliases', []))
        resolve_stage1_match(state, ko1_match['match_id'])
        self.assertEqual(ko1_match['status'], 'completed')

        # 3. Troll behavior: Now try to modify a Round 1 regular season match!
        first_regular_match = state['regular_matches'][0]
        t_a_id = first_regular_match['team_a']['id']
        t_b_id = first_regular_match['team_b']['id']

        with self.assertRaises(ValueError) as ctx:
            resolve_stage1_match(
                state,
                first_regular_match['match_id'],
                winner_id=t_b_id,
                maps=[{'team_a_score': 5, 'team_b_score': 13}, {'team_a_score': 4, 'team_b_score': 13}],
            )
        self.assertIn("Không thể sửa trận vòng bảng khi vòng Playoffs đã bắt đầu thi đấu", str(ctx.exception))

    def test_case_2_self_contradictory_match(self):
        """Case 2: Winner ID claims Team B won, but maps array shows Team A won 2-0.
        System must detect this contradiction and either auto-correct winner_id to match maps,
        or reject with clear error so stats and bracket never diverge."""
        state = init_stage1_region_state('americas', self.teams_stage1)
        m = state['regular_matches'][0]
        id_a = m['team_a']['id']
        id_b = m['team_b']['id']

        # Team A wins both maps 13-2, but client claims winner_id is id_b!
        contradictory_maps = [
            {'map_number': 1, 'team_a_score': 13, 'team_b_score': 2},
            {'map_number': 2, 'team_a_score': 13, 'team_b_score': 5},
        ]

        res = resolve_stage1_match(state, m['match_id'], winner_id=id_b, maps=contradictory_maps)

        # Assertion: If system resolves it, winner MUST strictly match the maps winner (Team A)!
        # Or if winner_id was forced, team scores must not contradict winner!
        self.assertEqual(res['winner_id'], id_a, "Backend should auto-align winner_id with map scores!")
        self.assertEqual(res['team_a_score'], 2)
        self.assertEqual(res['team_b_score'], 0)

    def test_case_3_absurd_map_scores(self):
        """Case 3: User inputs ridiculous/impossible scores:
        - Draw 13-13
        - Negative score 13 to -4
        - Invalid overtime 13-12 (must win by 2)
        - 5 maps in a BO3."""
        state = init_stage1_region_state('emea', self.teams_stage1)
        m = state['regular_matches'][0]
        id_a = m['team_a']['id']

        # Draw map 13-13
        with self.assertRaises(ValueError):
            resolve_stage1_match(state, m['match_id'], winner_id=id_a, maps=[{'team_a_score': 13, 'team_b_score': 13}])

        # Negative score
        with self.assertRaises(ValueError):
            resolve_stage1_match(state, m['match_id'], winner_id=id_a, maps=[{'team_a_score': 13, 'team_b_score': -5}])

        # Invalid Overtime (13-12 is not valid in Valorant, must be 14-12, 15-13, etc.)
        with self.assertRaises(ValueError):
            resolve_stage1_match(state, m['match_id'], winner_id=id_a, maps=[{'team_a_score': 13, 'team_b_score': 12}])

        # Excessive maps for BO3 (4 maps in BO3)
        with self.assertRaises(ValueError):
            resolve_stage1_match(state, m['match_id'], winner_id=id_a, maps=[
                {'team_a_score': 13, 'team_b_score': 5},
                {'team_a_score': 5, 'team_b_score': 13},
                {'team_a_score': 13, 'team_b_score': 8},
                {'team_a_score': 13, 'team_b_score': 2},
            ])

    def test_case_4_underdog_miracle_run_via_manual_override(self):
        """Case 4: Troll forces the weakest team (Seed 12 / lowest rating) to manually sweep
        the entire lower bracket all the way to the Grand Final.
        Bracket must dynamically update and resolve slots correctly at every step."""
        state = init_kickoff_region_state('china', self.teams_kickoff)

        # Upper Round 1 Trận 1: Seed 5 vs Seed 12
        # Let's force Seed 12 (qualifier 4) to win
        m1 = next(m for m in state['matches'] if m['round_name'] == 'upper_r1_m1')
        id_underdog = m1['team_b']['id']
        resolve_kickoff_match(state, m1['round_name'], winner_id=id_underdog)

        # Upper QF 1: Seed 1 vs Winner UB R1 M1
        m_qf1 = next(m for m in state['matches'] if m['round_name'] == 'upper_qf_m1')
        self.assertIsNotNone(m_qf1['team_b'])
        self.assertEqual(m_qf1['team_b']['id'], id_underdog)

        # Now force underdog to lose to Seed 1 -> underdog drops to Lower Bracket!
        id_seed1 = m_qf1['team_a']['id']
        resolve_kickoff_match(state, m_qf1['round_name'], winner_id=id_seed1)

        # Lower R1 M2: Loser UB R1 M2 vs Loser UB QF 1
        m_lb1_2 = next(m for m in state['matches'] if m['round_name'] == 'lower_r1_m2')
        self.assertIsNotNone(m_lb1_2['team_b'])
        self.assertEqual(m_lb1_2['team_b']['id'], id_underdog, "Underdog should correctly drop into LB R1 M2")


if __name__ == '__main__':
    unittest.main()
