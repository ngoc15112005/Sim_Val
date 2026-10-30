"""
engine/points.py — Official VCT 2025 Championship Points (CP) Engine

Standard:
- Ruleset VCT 2025 (Riot Games Official)
- Masters Bangkok = VCT Major
- Masters Toronto = VCT Masters

Points Table:
- Kickoff (Regional):
  * 1st: 3 CP (also qualifies to Major)
  * 2nd: 2 CP (also qualifies to Major)
  * 3rd: 1 CP
  * 4th: 1 CP
- Masters Bangkok (VCT Major, 8 teams):
  * 1st: 5 CP
  * 2nd: 3 CP
  * 3rd: 2 CP
  * 4th: 1 CP
- Stage 1 Regular Season: 1 CP per match win
- Stage 1 Playoffs (Regional):
  * 1st: 5 CP
  * 2nd: 3 CP
  * 3rd: 2 CP
  * 4th: 1 CP
- Masters Toronto (VCT Masters, 12 teams):
  * 1st: 7 CP
  * 2nd: 5 CP
  * 3rd: 4 CP
  * 4th: 3 CP
  * 5th-6th: 2 CP
- Stage 2 Regular Season: 1 CP per match win
- Stage 2 Playoffs (Regional):
  * 1st: 7 CP (Direct Seed 1 to Champions)
  * 2nd: 5 CP (Direct Seed 2 to Champions)
  * 3rd: 4 CP
  * 4th: 3 CP

Champions Paris Qualification (4 teams per region = 16 teams worldwide):
- Slot 1: Vô địch Stage 2 Playoffs (Direct)
- Slot 2: Á quân Stage 2 Playoffs (Direct)
- Slot 3: Đội có CP cao nhất chưa có vé (Championship Points #1)
- Slot 4: Đội có CP cao thứ nhì chưa có vé (Championship Points #2)

Tiebreaker Priority (Khi bằng điểm Championship Points):
1. Thứ hạng Stage 2 (Stage 2 Rank)
2. Thứ hạng Masters Toronto (Master Rank)
3. Thứ hạng Stage 1 (Stage 1 Rank)
4. Thứ hạng Masters Bangkok (Major Rank)
5. Thứ hạng Kickoff (Kickoff Rank)
6. Tổng số trận thắng trong mùa giải (Regular Season wins: Stage 1 + Stage 2)
7. Hiệu số bản đồ (Map Differential)
8. Hiệu số round (Round Differential)
9. Thành tích đối đầu (Head-to-Head match)
10. Hiệu số bản đồ đối đầu
11. Hiệu số round đối đầu
(Lưu ý: Tiêu chí 9-11 chỉ áp dụng khi bằng điểm giữa đúng 2 đội).
"""

from typing import List, Dict, Any, Optional, Tuple


def get_stage_points(stage_key: str, rank: Optional[int] = None, regular_wins: int = 0) -> int:
    """Calculate Championship Points awarded for a specific event/finish.
    
    stage_key options:
    - 'kickoff'
    - 'major' (Masters Bangkok)
    - 'stage1_regular'
    - 'stage1_playoffs'
    - 'master' (Masters Toronto)
    - 'stage2_regular'
    - 'stage2_playoffs'
    """
    if stage_key in ('stage1_regular', 'stage2_regular'):
        return max(0, int(regular_wins))

    if rank is None or rank <= 0:
        return 0

    if stage_key == 'kickoff':
        if rank == 1:
            return 3
        elif rank == 2:
            return 2
        elif rank in (3, 4):
            return 1
        return 0

    elif stage_key == 'major':  # Masters Bangkok
        if rank == 1:
            return 5
        elif rank == 2:
            return 3
        elif rank == 3:
            return 2
        elif rank == 4:
            return 1
        return 0

    elif stage_key == 'stage1_playoffs':
        if rank == 1:
            return 5
        elif rank == 2:
            return 3
        elif rank == 3:
            return 2
        elif rank == 4:
            return 1
        return 0

    elif stage_key == 'master':  # Masters Toronto
        if rank == 1:
            return 7
        elif rank == 2:
            return 5
        elif rank == 3:
            return 4
        elif rank == 4:
            return 3
        elif rank in (5, 6):
            return 2
        return 0

    elif stage_key == 'stage2_playoffs':
        if rank == 1:
            return 7
        elif rank == 2:
            return 5
        elif rank == 3:
            return 4
        elif rank == 4:
            return 3
        return 0

    return 0


def compare_teams_cp(team_a: Dict[str, Any], team_b: Dict[str, Any]) -> int:
    """Compare two teams for Championship Points leaderboard ranking.
    
    Returns:
      -1 if team_a is better than team_b
      1 if team_b is better than team_a
      0 if completely tied
    """
    cp_a = team_a.get('championship_points', 0)
    cp_b = team_b.get('championship_points', 0)
    if cp_a != cp_b:
        return -1 if cp_a > cp_b else 1

    # Tiebreaker 1: Thứ hạng Stage 2 (Lower rank is better, 0/None means didn't play or unranked)
    r_s2_a = team_a.get('stage2_rank') or 999
    r_s2_b = team_b.get('stage2_rank') or 999
    if r_s2_a != r_s2_b:
        return -1 if r_s2_a < r_s2_b else 1

    # Tiebreaker 2: Thứ hạng Masters Toronto (Master)
    r_mt_a = team_a.get('master_rank') or 999
    r_mt_b = team_b.get('master_rank') or 999
    if r_mt_a != r_mt_b:
        return -1 if r_mt_a < r_mt_b else 1

    # Tiebreaker 3: Thứ hạng Stage 1
    r_s1_a = team_a.get('stage1_rank') or 999
    r_s1_b = team_b.get('stage1_rank') or 999
    if r_s1_a != r_s1_b:
        return -1 if r_s1_a < r_s1_b else 1

    # Tiebreaker 4: Thứ hạng Masters Bangkok (Major)
    r_mb_a = team_a.get('major_rank') or 999
    r_mb_b = team_b.get('major_rank') or 999
    if r_mb_a != r_mb_b:
        return -1 if r_mb_a < r_mb_b else 1

    # Tiebreaker 5: Thứ hạng Kickoff
    r_ko_a = team_a.get('kickoff_rank') or 999
    r_ko_b = team_b.get('kickoff_rank') or 999
    if r_ko_a != r_ko_b:
        return -1 if r_ko_a < r_ko_b else 1

    # Tiebreaker 6: Tổng số trận thắng trong mùa giải (Regular season: Stage 1 + Stage 2)
    w_a = team_a.get('regular_season_wins', 0)
    w_b = team_b.get('regular_season_wins', 0)
    if w_a != w_b:
        return -1 if w_a > w_b else 1

    # Tiebreaker 7: Hiệu số bản đồ (Map Differential)
    md_a = team_a.get('map_differential', 0)
    md_b = team_b.get('map_differential', 0)
    if md_a != md_b:
        return -1 if md_a > md_b else 1

    # Tiebreaker 8: Hiệu số round (Round Differential)
    rd_a = team_a.get('round_differential', 0)
    rd_b = team_b.get('round_differential', 0)
    if rd_a != rd_b:
        return -1 if rd_a > rd_b else 1

    # Tiebreaker 9: Head-to-Head match wins
    h2h_a = team_a.get('h2h_wins', {}).get(team_b.get('club_id'), 0)
    h2h_b = team_b.get('h2h_wins', {}).get(team_a.get('club_id'), 0)
    if h2h_a != h2h_b:
        return -1 if h2h_a > h2h_b else 1

    return 0


def sort_championship_points_leaderboard(teams: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Sort teams according to VCT 2025 Championship Points and tiebreaker rules."""
    import functools
    sorted_teams = list(teams)
    sorted_teams.sort(key=functools.cmp_to_key(compare_teams_cp))

    for idx, t in enumerate(sorted_teams, 1):
        t['cp_rank'] = idx

    return sorted_teams


def determine_champions_slots(region_teams: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Determine the 4 Champions qualifiers for a region.
    
    Rule:
    - Slot 1: Vô địch Stage 2 Playoffs (Seed 1)
    - Slot 2: Á quân Stage 2 Playoffs (Seed 2)
    - Slot 3: Đội có CP cao nhất trong các đội còn lại (Championship Points #1)
    - Slot 4: Đội có CP cao thứ nhì trong các đội còn lại (Championship Points #2)
    
    Returns:
    {
        'qualifiers': [
            {'team': ..., 'slot_type': 'stage2_champion', 'seed': 1},
            {'team': ..., 'slot_type': 'stage2_runner_up', 'seed': 2},
            {'team': ..., 'slot_type': 'points_slot_1', 'seed': 3},
            {'team': ..., 'slot_type': 'points_slot_2', 'seed': 4},
        ],
        'leaderboard': sorted_teams_list
    }
    """
    sorted_leaderboard = sort_championship_points_leaderboard(region_teams)

    # Find Stage 2 champion and runner-up
    stage2_champ = None
    stage2_runner = None
    for t in sorted_leaderboard:
        if t.get('stage2_rank') == 1 and not stage2_champ:
            stage2_champ = t
        elif t.get('stage2_rank') == 2 and not stage2_runner:
            stage2_runner = t

    qualifiers = []
    already_qualified_ids = set()

    if stage2_champ:
        qualifiers.append({
            'team': stage2_champ,
            'slot_type': 'Vô địch Stage 2 Playoffs',
            'champions_seed': 1,
        })
        already_qualified_ids.add(stage2_champ.get('club_id'))

    if stage2_runner and stage2_runner.get('club_id') not in already_qualified_ids:
        qualifiers.append({
            'team': stage2_runner,
            'slot_type': 'Á quân Stage 2 Playoffs',
            'champions_seed': 2,
        })
        already_qualified_ids.add(stage2_runner.get('club_id'))

    # Remaining 2 slots from Championship Points leaderboard
    points_qualifiers = []
    for t in sorted_leaderboard:
        c_id = t.get('club_id')
        if c_id not in already_qualified_ids:
            points_qualifiers.append(t)
            already_qualified_ids.add(c_id)
            if len(points_qualifiers) == 2:
                break

    if len(points_qualifiers) > 0:
        qualifiers.append({
            'team': points_qualifiers[0],
            'slot_type': 'Điểm Championship Points #1',
            'champions_seed': 3,
        })

    if len(points_qualifiers) > 1:
        qualifiers.append({
            'team': points_qualifiers[1],
            'slot_type': 'Điểm Championship Points #2',
            'champions_seed': 4,
        })

    return {
        'qualifiers': qualifiers,
        'leaderboard': sorted_leaderboard,
    }
