"""
test_devious_rulebook_lawyer.py — Devious QA Testing: Persona 2 (The Rulebook Lawyer)

Edge Cases Covered:
- Case 5: The Rock-Paper-Scissors 3-Way Tiebreaker (Deterministic tiebreak when 3 teams have 3-2, identical map/round diff)
- Case 6: The Swiss Graph Deadlock (Exhaustion of random pairings when all teams in a record pool have played each other)
- Case 7: The Double Qualification Cascade (Champions Paris roll-down when Stage 2 Champion/Runner-up already lead CP)
- Case 8: The Ghost Participant Match (Preventing simulation of a match whose participants are None or unresolved)
"""

import unittest
from engine.points import determine_champions_slots
from engine.format.stage1 import (
    compute_stage1_group_standings,
    init_stage1_region_state,
    resolve_stage1_match,
)
from engine.format.open_qualifier import (
    _pair_bracket_group,
    generate_swiss_round_pairings,
)


class TestDeviousRulebookLawyer(unittest.TestCase):
    def setUp(self):
        self.teams = [
            {'id': i, 'club_id': i, 'name': f"Team {i}", 'short_code': f"T{i}", 'story_rating': 80 + i, 'group': 'Alpha'}
            for i in range(1, 7)
        ]

    def test_case_5_rock_paper_scissors_3way_tiebreaker(self):
        """Case 5: Team 1 beats Team 2 (2-0, 13-5, 13-5),
        Team 2 beats Team 3 (2-0, 13-5, 13-5),
        Team 3 beats Team 1 (2-0, 13-5, 13-5).
        All 3 teams finish 3-2 with identical map diff (+2) and identical round diff (+16).
        Standings must break ties deterministically (by rating/seed) and NEVER produce duplicate ranks
        or non-deterministic sorting across repeated calls."""
        completed_matches = [
            # T1 beats T2 2-0 (13-5, 13-5)
            {'team_a_id': 1, 'team_b_id': 2, 'team_a_score': 2, 'team_b_score': 0, 'status': 'completed',
             'maps': [{'team_a_score': 13, 'team_b_score': 5}, {'team_a_score': 13, 'team_b_score': 5}]},
            # T2 beats T3 2-0 (13-5, 13-5)
            {'team_a_id': 2, 'team_b_id': 3, 'team_a_score': 2, 'team_b_score': 0, 'status': 'completed',
             'maps': [{'team_a_score': 13, 'team_b_score': 5}, {'team_a_score': 13, 'team_b_score': 5}]},
            # T3 beats T1 2-0 (13-5, 13-5)
            {'team_a_id': 3, 'team_b_id': 1, 'team_a_score': 2, 'team_b_score': 0, 'status': 'completed',
             'maps': [{'team_a_score': 13, 'team_b_score': 5}, {'team_a_score': 13, 'team_b_score': 5}]},
            # T1, T2, T3 each beat T4, T5, T6
            {'team_a_id': 1, 'team_b_id': 4, 'team_a_score': 2, 'team_b_score': 0, 'status': 'completed',
             'maps': [{'team_a_score': 13, 'team_b_score': 5}, {'team_a_score': 13, 'team_b_score': 5}]},
            {'team_a_id': 2, 'team_b_id': 5, 'team_a_score': 2, 'team_b_score': 0, 'status': 'completed',
             'maps': [{'team_a_score': 13, 'team_b_score': 5}, {'team_a_score': 13, 'team_b_score': 5}]},
            {'team_a_id': 3, 'team_b_id': 6, 'team_a_score': 2, 'team_b_score': 0, 'status': 'completed',
             'maps': [{'team_a_score': 13, 'team_b_score': 5}, {'team_a_score': 13, 'team_b_score': 5}]},
            # T1, T2, T3 lose one more match to finish 3-2
            {'team_a_id': 4, 'team_b_id': 1, 'team_a_score': 2, 'team_b_score': 0, 'status': 'completed',
             'maps': [{'team_a_score': 13, 'team_b_score': 5}, {'team_a_score': 13, 'team_b_score': 5}]},
            {'team_a_id': 5, 'team_b_id': 2, 'team_a_score': 2, 'team_b_score': 0, 'status': 'completed',
             'maps': [{'team_a_score': 13, 'team_b_score': 5}, {'team_a_score': 13, 'team_b_score': 5}]},
            {'team_a_id': 6, 'team_b_id': 3, 'team_a_score': 2, 'team_b_score': 0, 'status': 'completed',
             'maps': [{'team_a_score': 13, 'team_b_score': 5}, {'team_a_score': 13, 'team_b_score': 5}]},
        ]

        # Call compute 10 times to ensure 100% deterministic ranking
        first_ranks = None
        for _ in range(10):
            standings = compute_stage1_group_standings(self.teams, completed_matches)
            current_ranks = [s['team']['id'] for s in standings]
            if first_ranks is None:
                first_ranks = current_ranks
            self.assertEqual(current_ranks, first_ranks, "Standings sorting must be strictly deterministic!")

        # Exactly 4 teams advance in VCT 2026 (rank 1, 2, 3, 4)
        advancing = [s for s in standings if s['advanced']]
        self.assertEqual(len(advancing), 4)
        self.assertEqual([s['rank'] for s in standings], [1, 2, 3, 4, 5, 6], "Ranks must be strictly 1 to 6 without duplicates")

    def test_case_6_swiss_graph_deadlock_graceful_fallback(self):
        """Case 6: In a 6-team Swiss pool, teams are deliberately constructed such that
        every team has played almost everyone else in past rounds, making valid disjoint
        pairing impossible under zero-rematch constraint.
        The algorithm must NOT return None or raise uncaught exceptions; it must gracefully fallback."""
        pool = [{'id': i, 'name': f"Team {i}"} for i in range(1, 7)]
        # Complete graph of rematches except 1 pair:
        # Everyone has played everyone else!
        past_opponents = {
            1: {2, 3, 4, 5, 6},
            2: {1, 3, 4, 5, 6},
            3: {1, 2, 4, 5, 6},
            4: {1, 2, 3, 5, 6},
            5: {1, 2, 3, 4, 6},
            6: {1, 2, 3, 4, 5},
        }

        # _pair_bracket_group should NOT crash and should return pairs (or fallback pairings)
        pairs = _pair_bracket_group(pool, past_opponents, max_retries=10)
        # In a deadlock, if fallback is implemented, it should return 3 pairs:
        self.assertIsNotNone(pairs, "Deadlock fallback must return paired teams rather than None causing crash")
        self.assertEqual(len(pairs), 3)

    def test_case_7_double_qualification_cascade(self):
        """Case 7: Team 1 wins Stage 2 AND has the #1 CP.
        Team 2 is Stage 2 runner-up AND has the #2 CP.
        The CP qualification slots (Slot 3 and Slot 4) must cleanly cascade/roll-down
        to Team 3 and Team 4 without duplicate entries for Team 1 or Team 2."""
        region_teams = [
            {'club_id': 1, 'name': 'Sentinels', 'stage2_rank': 1, 'championship_points': 25},
            {'club_id': 2, 'name': 'Leviatan', 'stage2_rank': 2, 'championship_points': 22},
            {'club_id': 3, 'name': 'NRG', 'stage2_rank': 3, 'championship_points': 18},
            {'club_id': 4, 'name': 'Cloud9', 'stage2_rank': 4, 'championship_points': 15},
            {'club_id': 5, 'name': 'LOUD', 'stage2_rank': 5, 'championship_points': 12},
        ]

        res = determine_champions_slots(region_teams)
        qualifiers = res['qualifiers']
        self.assertEqual(len(qualifiers), 4, "Must have exactly 4 distinct qualifiers")

        qualified_ids = [q['team']['club_id'] for q in qualifiers]
        self.assertEqual(len(set(qualified_ids)), 4, "All 4 qualified club IDs must be unique!")
        self.assertEqual(qualified_ids, [1, 2, 3, 4], "Must cascade to Team 3 and Team 4!")

    def test_case_8_ghost_participant_match(self):
        """Case 8: User or buggy caller tries to resolve a match where team_a or team_b is None.
        System must raise ValueError instead of throwing AttributeError or KeyError."""
        state = init_stage1_region_state('pacific', self.teams + [{'id': i, 'club_id': i, 'name': f'Team {i}', 'story_rating': 80} for i in range(7, 13)])
        # A pending playoff match that hasn't had teams resolved
        unready_match = next(m for m in state['playoff_matches'] if m['team_a'] is None)

        with self.assertRaises(ValueError) as ctx:
            resolve_stage1_match(state, unready_match['match_id'])
        self.assertIn("chưa đủ 2 đội", str(ctx.exception).lower())


if __name__ == '__main__':
    unittest.main()
