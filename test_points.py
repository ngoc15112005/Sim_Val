import unittest
from engine.points import (
    get_stage_points,
    compare_teams_cp,
    sort_championship_points_leaderboard,
    determine_champions_slots,
)


class TestChampionshipPoints(unittest.TestCase):

    def test_point_values_across_stages(self):
        # 1. Kickoff
        self.assertEqual(get_stage_points('kickoff', rank=1), 3)
        self.assertEqual(get_stage_points('kickoff', rank=2), 2)
        self.assertEqual(get_stage_points('kickoff', rank=3), 1)
        self.assertEqual(get_stage_points('kickoff', rank=4), 1)
        self.assertEqual(get_stage_points('kickoff', rank=5), 0)

        # 2. Masters Bangkok (VCT Major)
        self.assertEqual(get_stage_points('major', rank=1), 5)
        self.assertEqual(get_stage_points('major', rank=2), 3)
        self.assertEqual(get_stage_points('major', rank=3), 2)
        self.assertEqual(get_stage_points('major', rank=4), 1)
        self.assertEqual(get_stage_points('major', rank=5), 0)

        # 3. Stage 1 Regular Season
        self.assertEqual(get_stage_points('stage1_regular', regular_wins=4), 4)

        # 4. Stage 1 Playoffs
        self.assertEqual(get_stage_points('stage1_playoffs', rank=1), 5)
        self.assertEqual(get_stage_points('stage1_playoffs', rank=2), 3)
        self.assertEqual(get_stage_points('stage1_playoffs', rank=3), 2)
        self.assertEqual(get_stage_points('stage1_playoffs', rank=4), 1)

        # 5. Masters Toronto (VCT Masters)
        self.assertEqual(get_stage_points('master', rank=1), 7)
        self.assertEqual(get_stage_points('master', rank=2), 5)
        self.assertEqual(get_stage_points('master', rank=3), 4)
        self.assertEqual(get_stage_points('master', rank=4), 3)
        self.assertEqual(get_stage_points('master', rank=5), 2)
        self.assertEqual(get_stage_points('master', rank=6), 2)
        self.assertEqual(get_stage_points('master', rank=7), 0)

        # 6. Stage 2 Regular Season
        self.assertEqual(get_stage_points('stage2_regular', regular_wins=5), 5)

        # 7. Stage 2 Playoffs
        self.assertEqual(get_stage_points('stage2_playoffs', rank=1), 7)
        self.assertEqual(get_stage_points('stage2_playoffs', rank=2), 5)
        self.assertEqual(get_stage_points('stage2_playoffs', rank=3), 4)
        self.assertEqual(get_stage_points('stage2_playoffs', rank=4), 3)

    def test_tiebreaker_priority(self):
        # Team A and Team B have equal CP (12 points)
        # Priority 1: Stage 2 Rank
        team_a = {'club_id': 1, 'name': 'A', 'championship_points': 12, 'stage2_rank': 3}
        team_b = {'club_id': 2, 'name': 'B', 'championship_points': 12, 'stage2_rank': 4}
        self.assertEqual(compare_teams_cp(team_a, team_b), -1)  # A is better

        # If Stage 2 Rank is tied, Priority 2: Masters Toronto (Master Rank)
        team_a['stage2_rank'] = 3
        team_b['stage2_rank'] = 3
        team_a['master_rank'] = 2
        team_b['master_rank'] = 3
        self.assertEqual(compare_teams_cp(team_a, team_b), -1)  # A is better

        # If Master Rank tied, Priority 3: Stage 1 Rank
        team_a['master_rank'] = 2
        team_b['master_rank'] = 2
        team_a['stage1_rank'] = 4
        team_b['stage1_rank'] = 2
        self.assertEqual(compare_teams_cp(team_a, team_b), 1)   # B is better

        # If all stage ranks tied, Priority 6: Regular Season wins
        team_a['stage1_rank'] = 2
        team_b['stage1_rank'] = 2
        team_a['regular_season_wins'] = 8
        team_b['regular_season_wins'] = 6
        self.assertEqual(compare_teams_cp(team_a, team_b), -1)  # A is better

    def test_champions_paris_slot_allocation(self):
        teams = [
            {'club_id': 1, 'name': 'Team1', 'championship_points': 15, 'stage2_rank': 1}, # Stage 2 Champion -> Slot 1
            {'club_id': 2, 'name': 'Team2', 'championship_points': 18, 'stage2_rank': 3}, # Highest CP not champ/runner -> Slot 3
            {'club_id': 3, 'name': 'Team3', 'championship_points': 10, 'stage2_rank': 2}, # Stage 2 Runner-up -> Slot 2
            {'club_id': 4, 'name': 'Team4', 'championship_points': 14, 'stage2_rank': 4}, # Second highest CP -> Slot 4
            {'club_id': 5, 'name': 'Team5', 'championship_points': 11, 'stage2_rank': 5},
            {'club_id': 6, 'name': 'Team6', 'championship_points': 8,  'stage2_rank': 6},
        ]

        result = determine_champions_slots(teams)
        qualifiers = result['qualifiers']
        self.assertEqual(len(qualifiers), 4)

        # Check slots
        self.assertEqual(qualifiers[0]['team']['club_id'], 1)
        self.assertEqual(qualifiers[0]['champions_seed'], 1)
        self.assertEqual(qualifiers[0]['slot_type'], 'Vô địch Stage 2 Playoffs')

        self.assertEqual(qualifiers[1]['team']['club_id'], 3)
        self.assertEqual(qualifiers[1]['champions_seed'], 2)
        self.assertEqual(qualifiers[1]['slot_type'], 'Á quân Stage 2 Playoffs')

        self.assertEqual(qualifiers[2]['team']['club_id'], 2)
        self.assertEqual(qualifiers[2]['champions_seed'], 3)
        self.assertEqual(qualifiers[2]['slot_type'], 'Điểm Championship Points #1')

        self.assertEqual(qualifiers[3]['team']['club_id'], 4)
        self.assertEqual(qualifiers[3]['champions_seed'], 4)
        self.assertEqual(qualifiers[3]['slot_type'], 'Điểm Championship Points #2')


if __name__ == '__main__':
    unittest.main()
