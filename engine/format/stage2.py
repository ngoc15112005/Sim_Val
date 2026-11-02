"""
engine/format/stage2.py — VCT Stage 2 Interactive Engine (Regular Season + Modified Double Elimination Playoffs)

Official VCT 2026 Unified Format for All 4 Regions (Americas, EMEA, Pacific, China):
- 12 teams per region (8 retained from Stage 1 + 4 qualified from Open Qualifier Stage 2)
- Single unified format across all four regions (No China Cross Play Decider / Seed Decider)
- Regular Season (Vòng Bảng):
  * Group Partition: Group Alpha (6 teams) and Group Omega (6 teams)
  * Single Round Robin intra-group only (each team plays 5 other teams in their group)
  * Exactly 15 Bo3 matches per group = 30 matches total per region (5 matches per team)
  * No cross-group matches between Alpha and Omega in regular season
  * 1 Championship Point per regular season match win (max 5 CP)
  * Top 4 teams from each group advance to Playoffs (8 teams total)
  * Bottom 2 teams from each group (ranks 5 and 6) are eliminated
- Playoffs: 8-Team Modified Double Elimination (12 matches total):
  * Upper Round 1 (Bo3):
    - UBR1-M1: Omega #2 vs Alpha #3
    - UBR1-M2: Alpha #2 vs Omega #3
  * Upper Semifinals (Bo3, Alpha #1 & Omega #1 have BYES):
    - UBSF-M1: Alpha #1 vs Winner(UBR1-M1)
    - UBSF-M2: Omega #1 vs Winner(UBR1-M2)
  * Lower Round 1 (Bo3, Alpha #4 & Omega #4 start here):
    - LBR1-M1: Omega #4 vs Loser(UBR1-M1)
    - LBR1-M2: Alpha #4 vs Loser(UBR1-M2)
  * Lower Round 2 (Bo3, Cross-pairing):
    - LBR2-M1: Winner(LBR1-M2) vs Loser(UBSF-M1)
    - LBR2-M2: Winner(LBR1-M1) vs Loser(UBSF-M2)
  * Upper Final (Bo3):
    - UBF: Winner(UBSF-M1) vs Winner(UBSF-M2)
  * Lower Round 3 (Bo3):
    - LBR3: Winner(LBR2-M1) vs Winner(LBR2-M2)
  * Lower Final (Bo5):
    - LBF: Loser(UBF) vs Winner(LBR3)
  * Grand Final (Bo5, No Bracket Reset):
    - GF: Winner(UBF) vs Winner(LBF)
- Final Placements & Championship Points:
  * 1st: Winner(GF) (+7 CP, direct Seed 1 to Champions)
  * 2nd: Loser(GF) (+5 CP, direct Seed 2 to Champions)
  * 3rd: Loser(LBF) (+4 CP)
  * 4th: Loser(LBR3) (+3 CP)
  * 5th-6th: Losers(LBR2) (+0 CP)
  * 7th-8th: Losers(LBR1) (+0 CP)
  * 9th-12th: Regular season eliminated teams (+0 CP)
  * Total CP = regularSeasonMatchWins + playoffPlacementBonus
"""

import copy
import random
from typing import Any, Dict, List, Optional, Tuple

from engine.match import validate_and_normalize_manual_maps
from engine.tiebreaker import compute_vct_group_standings


def stage2_config() -> Dict[str, Any]:
    return {
        'regions': ["americas", "emea", "pacific", "china"],
        'teams_per_region': 12,
        'group_alpha_teams': 6,
        'group_omega_teams': 6,
        'group_format': "SINGLE_ROUND_ROBIN",
        'group_match_best_of': 3,
        'regular_season_weeks': 5,
        'regular_season_matches': 30,
        'qualified_per_group': 4,
        'eliminated_per_group': 2,
        'playoff_format': "MODIFIED_DOUBLE_ELIMINATION",
        'playoff_teams': 8,
        'playoff_matches': 12,
        'default_playoff_best_of': 3,
        'lower_final_best_of': 5,
        'grand_final_best_of': 5,
        'grand_final_reset': False,
        'total_matches': 42,
        'regular_win_cp': 1,
        'playoff_cp': {1: 7, 2: 5, 3: 4, 4: 3, 5: 0, 6: 0, 7: 0, 8: 0},
        'champions_qualifiers_count': 4,
        'china_seed_decider_enabled': False,
    }


def partition_stage2_groups(participants: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Partition 12 teams into Group Alpha (6) and Group Omega (6) using serpentine seeding based on Stage 1 / OQ results."""
    sorted_teams = sorted(
        participants,
        key=lambda t: (t.get('seed') or t.get('stage1_rank') or 999, -t.get('story_rating', 80), t.get('name', ''))
    )
    # Serpentine distribution:
    # 1 -> Alpha, 2 -> Omega, 3 -> Omega, 4 -> Alpha
    # 5 -> Alpha, 6 -> Omega, 7 -> Omega, 8 -> Alpha
    # 9 -> Alpha, 10 -> Omega, 11 -> Omega, 12 -> Alpha
    alpha_indices = {0, 3, 4, 7, 8, 11}
    group_alpha = []
    group_omega = []
    for idx, t in enumerate(sorted_teams):
        t_copy = copy.deepcopy(t)
        if idx in alpha_indices:
            t_copy['group'] = 'Alpha'
            t_copy['groupId'] = 'ALPHA'
            group_alpha.append(t_copy)
        else:
            t_copy['group'] = 'Omega'
            t_copy['groupId'] = 'OMEGA'
            group_omega.append(t_copy)

    return group_alpha, group_omega


def _gen_map_score_stage2(winner_rating: int, loser_rating: int) -> Tuple[int, int]:
    diff = winner_rating - loser_rating
    roll = random.random()
    if diff >= 10:
        if roll < 0.35:
            return 13, random.randint(3, 7)
        elif roll < 0.80:
            return 13, random.randint(8, 10)
        else:
            return random.choice([(13, 11), (14, 12), (15, 13)])
    elif diff >= 4:
        if roll < 0.20:
            return 13, random.randint(5, 7)
        elif roll < 0.70:
            return 13, random.randint(8, 10)
        else:
            return random.choice([(13, 11), (14, 12), (15, 13)])
    else:
        if roll < 0.50:
            return 13, random.randint(8, 10)
        else:
            return random.choice([(13, 11), (14, 12), (15, 13)])


def simulate_stage2_match(team_a: Dict[str, Any], team_b: Dict[str, Any], bo: int = 3,
                          rating_lookup: Optional[Dict[int, int]] = None,
                          form_lookup: Optional[Dict[int, int]] = None,
                          manual_override: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    id_a = team_a.get('id') if 'id' in team_a else team_a.get('club_id')
    id_b = team_b.get('id') if 'id' in team_b else team_b.get('club_id')

    r_a = (rating_lookup.get(id_a) if rating_lookup else None) or team_a.get('story_rating') or team_a.get('current_rating') or 80
    r_b = (rating_lookup.get(id_b) if rating_lookup else None) or team_b.get('story_rating') or team_b.get('current_rating') or 80
    f_a = (form_lookup.get(id_a) if form_lookup else None) or team_a.get('form_modifier') or 0
    f_b = (form_lookup.get(id_b) if form_lookup else None) or team_b.get('form_modifier') or 0

    eff_a = r_a + f_a
    eff_b = r_b + f_b

    target_wins = 3 if bo == 5 else 2
    max_maps = bo

    if manual_override and manual_override.get('winner_id') in (id_a, id_b):
        winner_id = manual_override['winner_id']
        winner = team_a if winner_id == id_a else team_b
        loser = team_b if winner == team_a else team_a

        custom_maps = manual_override.get('maps', [])
        if custom_maps:
            wins_a, wins_b, real_w_id, real_l_id, sanitized_maps = validate_and_normalize_manual_maps(
                custom_maps, bo=bo, id_a=id_a, id_b=id_b, forced_winner_id=winner_id
            )
            real_winner = team_a if real_w_id == id_a else team_b
            real_loser = team_b if real_w_id == id_a else team_a
            return {
                'team_a': team_a, 'team_b': team_b,
                'team_a_id': id_a, 'team_b_id': id_b,
                'team_a_score': wins_a, 'team_b_score': wins_b,
                'winner': real_winner, 'loser': real_loser,
                'winner_id': real_w_id, 'loser_id': real_l_id,
                'maps': sanitized_maps,
                'bo': bo,
                'is_manual': True,
            }
        else:
            wins_a = target_wins if winner == team_a else 1
            wins_b = target_wins if winner == team_b else 1
            maps = []
            for i in range(target_wins):
                sc_w, sc_l = _gen_map_score_stage2(eff_a if winner == team_a else eff_b, eff_b if winner == team_a else eff_a)
                maps.append({
                    'map_number': i + 1,
                    'team_a_score': sc_w if winner == team_a else sc_l,
                    'team_b_score': sc_l if winner == team_a else sc_w,
                    'winner_id': winner_id,
                })
            return {
                'team_a': team_a, 'team_b': team_b,
                'team_a_id': id_a, 'team_b_id': id_b,
                'team_a_score': wins_a, 'team_b_score': wins_b,
                'winner': winner, 'loser': loser,
                'winner_id': winner_id, 'loser_id': loser.get('id') or loser.get('club_id'),
                'maps': maps,
                'bo': bo,
                'is_manual': True,
            }

    diff = eff_a - eff_b
    prob_a = max(0.15, min(0.85, 0.50 + diff * 0.0125))

    wins_a = 0
    wins_b = 0
    maps = []

    for map_idx in range(max_maps):
        roll = random.random()
        if roll < prob_a:
            sc_win, sc_lose = _gen_map_score_stage2(eff_a, eff_b)
            wins_a += 1
            maps.append({
                'map_number': map_idx + 1,
                'team_a_score': sc_win,
                'team_b_score': sc_lose,
                'winner_id': id_a,
            })
        else:
            sc_win, sc_lose = _gen_map_score_stage2(eff_b, eff_a)
            wins_b += 1
            maps.append({
                'map_number': map_idx + 1,
                'team_a_score': sc_lose,
                'team_b_score': sc_win,
                'winner_id': id_b,
            })

        if wins_a == target_wins or wins_b == target_wins:
            break

    winner = team_a if wins_a > wins_b else team_b
    loser = team_b if wins_a > wins_b else team_a

    return {
        'team_a': team_a, 'team_b': team_b,
        'team_a_id': id_a, 'team_b_id': id_b,
        'team_a_score': wins_a, 'team_b_score': wins_b,
        'winner': winner, 'loser': loser,
        'winner_id': winner.get('id') or winner.get('club_id'),
        'loser_id': loser.get('id') or loser.get('club_id'),
        'maps': maps,
        'bo': bo,
        'is_manual': False,
    }


def compute_stage2_group_standings(group_teams: List[Dict[str, Any]],
                                   completed_matches: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Compute Group Standings using the official VCT 2026 5-tier mini-table tiebreaker."""
    return compute_vct_group_standings(group_teams, completed_matches, qualify_count=4)


def generate_round_robin_schedule(teams: List[Dict[str, Any]]) -> List[List[Tuple[Dict[str, Any], Dict[str, Any]]]]:
    if len(teams) != 6:
        raise ValueError(f"Expected 6 teams for group round-robin, got {len(teams)}")

    rounds_indices = [
        [(0, 5), (1, 4), (2, 3)],
        [(0, 4), (5, 3), (1, 2)],
        [(0, 3), (4, 2), (5, 1)],
        [(0, 2), (3, 1), (4, 5)],
        [(0, 1), (2, 5), (3, 4)],
    ]

    schedule = []
    for r in rounds_indices:
        round_pairs = []
        for i, j in r:
            round_pairs.append((teams[i], teams[j]))
        schedule.append(round_pairs)
    return schedule


def _matches_target_id(match_obj: Dict[str, Any], target_id: str) -> bool:
    if not match_obj:
        return False
    mid = match_obj.get('match_id', '')
    if mid == target_id or mid.lower() == target_id.lower():
        return True
    aliases = match_obj.get('aliases', [])
    for a in aliases:
        if a == target_id or a.lower() == target_id.lower():
            return True
    return False


def init_stage2_region_state(region_slug: str, participants: List[Dict[str, Any]]) -> Dict[str, Any]:
    if len(participants) != 12:
        raise ValueError(f"Stage 2 requires exactly 12 teams, got {len(participants)}")

    group_alpha, group_omega = partition_stage2_groups(participants)
    alpha_schedule = generate_round_robin_schedule(group_alpha)
    omega_schedule = generate_round_robin_schedule(group_omega)

    regular_matches = []
    for w in range(1, 6):
        # Alpha matches (1-3)
        for idx, (t_a, t_b) in enumerate(alpha_schedule[w - 1]):
            m_idx = idx + 1
            m_id = f"reg_w{w}_m{m_idx}"
            regular_matches.append({
                'match_id': m_id,
                'phase': 'regular_season',
                'round_type': 'regular',
                'week': w,
                'match_number': m_idx,
                'group': 'Alpha',
                'groupId': 'ALPHA',
                'label': f"Tuần {w} — Alpha Trận {idx + 1}",
                'bo': 3,
                'team_a': t_a,
                'team_b': t_b,
                'team_a_id': t_a.get('id') or t_a.get('club_id'),
                'team_b_id': t_b.get('id') or t_b.get('club_id'),
                'team_a_score': 0,
                'team_b_score': 0,
                'winner': None,
                'loser': None,
                'winner_id': None,
                'loser_id': None,
                'status': 'pending',
                'ready': True,
                'maps': [],
                'is_manual': False,
            })

        # Omega matches (4-6)
        for idx, (t_a, t_b) in enumerate(omega_schedule[w - 1]):
            m_idx = idx + 4
            m_id = f"reg_w{w}_m{m_idx}"
            regular_matches.append({
                'match_id': m_id,
                'phase': 'regular_season',
                'round_type': 'regular',
                'week': w,
                'match_number': m_idx,
                'group': 'Omega',
                'groupId': 'OMEGA',
                'label': f"Tuần {w} — Omega Trận {idx + 1}",
                'bo': 3,
                'team_a': t_a,
                'team_b': t_b,
                'team_a_id': t_a.get('id') or t_a.get('club_id'),
                'team_b_id': t_b.get('id') or t_b.get('club_id'),
                'team_a_score': 0,
                'team_b_score': 0,
                'winner': None,
                'loser': None,
                'winner_id': None,
                'loser_id': None,
                'status': 'pending',
                'ready': True,
                'maps': [],
                'is_manual': False,
            })

    # 12-Team Modified Double Elimination Playoffs
    playoff_templates = [
        # Upper Round 1
        {
            'match_id': 'UBR1-M1',
            'aliases': ['ubr1_m1', 'ko_1'],
            'round_type': 'ub_r1',
            'bracket': 'upper',
            'round_name': 'UBR1-M1',
            'label': 'Upper Round 1 - Trận 1 (Omega #2 vs Alpha #3)',
            'team_a_source': {'type': 'group_seed', 'group': 'Omega', 'seed': 2},
            'team_b_source': {'type': 'group_seed', 'group': 'Alpha', 'seed': 3},
            'bo': 3,
        },
        {
            'match_id': 'UBR1-M2',
            'aliases': ['ubr1_m2', 'ko_2'],
            'round_type': 'ub_r1',
            'bracket': 'upper',
            'round_name': 'UBR1-M2',
            'label': 'Upper Round 1 - Trận 2 (Alpha #2 vs Omega #3)',
            'team_a_source': {'type': 'group_seed', 'group': 'Alpha', 'seed': 2},
            'team_b_source': {'type': 'group_seed', 'group': 'Omega', 'seed': 3},
            'bo': 3,
        },
        # Upper Semifinals
        {
            'match_id': 'UBSF-M1',
            'aliases': ['ubsf_m1', 'upper_sf_1'],
            'round_type': 'upper_sf',
            'bracket': 'upper',
            'round_name': 'UBSF-M1',
            'label': 'Bán Kết Nhánh Thắng 1 (Alpha #1 vs Thắng UBR1-M1)',
            'team_a_source': {'type': 'group_seed', 'group': 'Alpha', 'seed': 1},
            'team_b_source': {'type': 'winner_of', 'value': 'UBR1-M1'},
            'bo': 3,
        },
        {
            'match_id': 'UBSF-M2',
            'aliases': ['ubsf_m2', 'upper_sf_2'],
            'round_type': 'upper_sf',
            'bracket': 'upper',
            'round_name': 'UBSF-M2',
            'label': 'Bán Kết Nhánh Thắng 2 (Omega #1 vs Thắng UBR1-M2)',
            'team_a_source': {'type': 'group_seed', 'group': 'Omega', 'seed': 1},
            'team_b_source': {'type': 'winner_of', 'value': 'UBR1-M2'},
            'bo': 3,
        },
        # Lower Round 1
        {
            'match_id': 'LBR1-M1',
            'aliases': ['lbr1_m1'],
            'round_type': 'lb_r1',
            'bracket': 'lower',
            'round_name': 'LBR1-M1',
            'label': 'Vòng 1 Nhánh Thua 1 (Omega #4 vs Thua UBR1-M1)',
            'team_a_source': {'type': 'group_seed', 'group': 'Omega', 'seed': 4},
            'team_b_source': {'type': 'loser_of', 'value': 'UBR1-M1'},
            'bo': 3,
            'loser_standing_rank': 7,
        },
        {
            'match_id': 'LBR1-M2',
            'aliases': ['lbr1_m2'],
            'round_type': 'lb_r1',
            'bracket': 'lower',
            'round_name': 'LBR1-M2',
            'label': 'Vòng 1 Nhánh Thua 2 (Alpha #4 vs Thua UBR1-M2)',
            'team_a_source': {'type': 'group_seed', 'group': 'Alpha', 'seed': 4},
            'team_b_source': {'type': 'loser_of', 'value': 'UBR1-M2'},
            'bo': 3,
            'loser_standing_rank': 8,
        },
        # Lower Round 2 (Cross-over)
        {
            'match_id': 'LBR2-M1',
            'aliases': ['lbr2_m1'],
            'round_type': 'lb_r2',
            'bracket': 'lower',
            'round_name': 'LBR2-M1',
            'label': 'Vòng 2 Nhánh Thua 1 (Thắng LBR1-M2 vs Thua UBSF-M1)',
            'team_a_source': {'type': 'winner_of', 'value': 'LBR1-M2'},
            'team_b_source': {'type': 'loser_of', 'value': 'UBSF-M1'},
            'bo': 3,
            'loser_standing_rank': 5,
        },
        {
            'match_id': 'LBR2-M2',
            'aliases': ['lbr2_m2'],
            'round_type': 'lb_r2',
            'bracket': 'lower',
            'round_name': 'LBR2-M2',
            'label': 'Vòng 2 Nhánh Thua 2 (Thắng LBR1-M1 vs Thua UBSF-M2)',
            'team_a_source': {'type': 'winner_of', 'value': 'LBR1-M1'},
            'team_b_source': {'type': 'loser_of', 'value': 'UBSF-M2'},
            'bo': 3,
            'loser_standing_rank': 6,
        },
        # Upper Final
        {
            'match_id': 'UBF',
            'aliases': ['upper_final', 'ubf'],
            'round_type': 'upper_final',
            'bracket': 'upper',
            'round_name': 'UBF',
            'label': 'Chung Kết Nhánh Thắng (Thắng UBSF-M1 vs Thắng UBSF-M2)',
            'team_a_source': {'type': 'winner_of', 'value': 'UBSF-M1'},
            'team_b_source': {'type': 'winner_of', 'value': 'UBSF-M2'},
            'bo': 3,
        },
        # Lower Round 3
        {
            'match_id': 'LBR3',
            'aliases': ['lbr3', 'lower_semifinal'],
            'round_type': 'lb_r3',
            'bracket': 'lower',
            'round_name': 'LBR3',
            'label': 'Vòng 3 Nhánh Thua (Thắng LBR2-M1 vs Thắng LBR2-M2)',
            'team_a_source': {'type': 'winner_of', 'value': 'LBR2-M1'},
            'team_b_source': {'type': 'winner_of', 'value': 'LBR2-M2'},
            'bo': 3,
            'loser_standing_rank': 4,
        },
        # Lower Final
        {
            'match_id': 'LBF',
            'aliases': ['lower_final', 'lbf'],
            'round_type': 'lower_final',
            'bracket': 'lower',
            'round_name': 'LBF',
            'label': 'Chung Kết Nhánh Thua (Thua UBF vs Thắng LBR3)',
            'team_a_source': {'type': 'loser_of', 'value': 'UBF'},
            'team_b_source': {'type': 'winner_of', 'value': 'LBR3'},
            'bo': 5,
            'loser_standing_rank': 3,
        },
        # Grand Final
        {
            'match_id': 'GF',
            'aliases': ['grand_final', 'gf'],
            'round_type': 'grand_final',
            'bracket': 'grand_final',
            'round_name': 'GF',
            'label': 'Chung Kết Tổng VCT Stage 2 (Thắng UBF vs Thắng LBF)',
            'team_a_source': {'type': 'winner_of', 'value': 'UBF'},
            'team_b_source': {'type': 'winner_of', 'value': 'LBF'},
            'bo': 5,
            'winner_standing_rank': 1,
            'loser_standing_rank': 2,
        },
    ]

    playoff_matches = []
    for tmpl in playoff_templates:
        playoff_matches.append({
            'match_id': tmpl['match_id'],
            'aliases': tmpl.get('aliases', []),
            'phase': 'playoffs',
            'round_type': tmpl['round_type'],
            'bracket': tmpl['bracket'],
            'round_name': tmpl['round_name'],
            'label': tmpl['label'],
            'team_a_source': tmpl['team_a_source'],
            'team_b_source': tmpl['team_b_source'],
            'bo': tmpl['bo'],
            'status': 'pending',
            'ready': False,
            'team_a': None,
            'team_b': None,
            'team_a_id': None,
            'team_b_id': None,
            'team_a_score': 0,
            'team_b_score': 0,
            'team_a_source_label': '',
            'team_b_source_label': '',
            'winner': None,
            'loser': None,
            'winner_id': None,
            'loser_id': None,
            'maps': [],
            'is_manual': False,
            'loser_standing_rank': tmpl.get('loser_standing_rank'),
            'winner_standing_rank': tmpl.get('winner_standing_rank'),
        })

    state = {
        'region': region_slug,
        'regionId': region_slug.upper(),
        'participants': participants,
        'current_phase': 'regular_season',  # 'regular_season' -> 'playoffs' -> 'completed'
        'status': 'in_progress',
        'group_alpha': group_alpha,
        'group_omega': group_omega,
        'alpha_standings': compute_stage2_group_standings(group_alpha, []),
        'omega_standings': compute_stage2_group_standings(group_omega, []),
        'regular_matches': regular_matches,
        'playoff_matches': playoff_matches,
        'champion': None,
        'runner_up': None,
        'third_place': None,
        'fourth_place': None,
        'champions_qualifiers': [],
        'standings': [],
        'rewards_awarded': False,
    }

    _resolve_stage2_playoff_slots(state)
    return state


def _resolve_stage2_playoff_slots(state: Dict[str, Any]):
    alpha_standings = state.get('alpha_standings', [])
    omega_standings = state.get('omega_standings', [])
    playoff_matches = state.get('playoff_matches', [])

    completed_playoffs: Dict[str, Dict[str, Any]] = {}
    for m in playoff_matches:
        if m.get('status') == 'completed':
            completed_playoffs[m['match_id']] = m
            completed_playoffs[m['match_id'].lower()] = m
            for a in m.get('aliases', []):
                completed_playoffs[a] = m
                completed_playoffs[a.lower()] = m

    reg_completed = all(m.get('status') == 'completed' for m in state.get('regular_matches', []))

    def resolve_source(src: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], str]:
        stype = src.get('type')
        if stype == 'group_seed':
            grp = src.get('group')
            seed = src.get('seed')
            st_list = alpha_standings if grp in ('Alpha', 'ALPHA') else omega_standings
            label = f"{grp} #{seed}"
            if reg_completed and len(st_list) >= seed:
                return st_list[seed - 1]['team'], label
            return None, label

        elif stype == 'winner_of':
            ref_id = src.get('value')
            label = f"Thắng {ref_id}"
            if ref_id in completed_playoffs or (isinstance(ref_id, str) and ref_id.lower() in completed_playoffs):
                target = completed_playoffs.get(ref_id) or completed_playoffs.get(ref_id.lower())
                return target.get('winner'), label
            return None, label

        elif stype == 'loser_of':
            ref_id = src.get('value')
            label = f"Thua {ref_id}"
            if ref_id in completed_playoffs or (isinstance(ref_id, str) and ref_id.lower() in completed_playoffs):
                target = completed_playoffs.get(ref_id) or completed_playoffs.get(ref_id.lower())
                return target.get('loser'), label
            return None, label

        return None, 'TBD'

    for pm in playoff_matches:
        if pm.get('status') == 'completed':
            continue

        team_a, label_a = resolve_source(pm['team_a_source'])
        team_b, label_b = resolve_source(pm['team_b_source'])

        pm['team_a'] = team_a
        pm['team_b'] = team_b
        pm['team_a_id'] = (team_a.get('id') if 'id' in team_a else team_a.get('club_id')) if team_a else None
        pm['team_b_id'] = (team_b.get('id') if 'id' in team_b else team_b.get('club_id')) if team_b else None
        pm['team_a_source_label'] = label_a
        pm['team_b_source_label'] = label_b
        pm['ready'] = (team_a is not None and team_b is not None)


def advance_stage2_region(state: Dict[str, Any]) -> bool:
    reg_matches = state.get('regular_matches', [])
    reg_done = all(m.get('status') == 'completed' for m in reg_matches)

    state['alpha_standings'] = compute_stage2_group_standings(state['group_alpha'], reg_matches)
    state['omega_standings'] = compute_stage2_group_standings(state['group_omega'], reg_matches)

    if reg_done and state['current_phase'] == 'regular_season':
        state['current_phase'] = 'playoffs'

    _resolve_stage2_playoff_slots(state)

    playoff_matches = state.get('playoff_matches', [])
    playoffs_done = all(m.get('status') == 'completed' for m in playoff_matches)

    if playoffs_done and state['current_phase'] == 'playoffs':
        state['current_phase'] = 'completed'
        state['status'] = 'completed'

        completed_map: Dict[str, Dict[str, Any]] = {}
        for m in playoff_matches:
            completed_map[m['match_id']] = m
            completed_map[m['match_id'].lower()] = m
            for a in m.get('aliases', []):
                completed_map[a] = m
                completed_map[a.lower()] = m

        gf = completed_map.get('GF') or completed_map.get('grand_final')
        lbf = completed_map.get('LBF') or completed_map.get('lower_final')
        lbr3 = completed_map.get('LBR3') or completed_map.get('lower_semifinal')
        lbr2_1 = completed_map.get('LBR2-M1')
        lbr2_2 = completed_map.get('LBR2-M2')
        lbr1_1 = completed_map.get('LBR1-M1')
        lbr1_2 = completed_map.get('LBR1-M2')

        champ = gf.get('winner') if gf else None
        runner = gf.get('loser') if gf else None
        third = lbf.get('loser') if lbf else None
        fourth = lbr3.get('loser') if lbr3 else None
        fifth_a = lbr2_1.get('loser') if lbr2_1 else None
        fifth_b = lbr2_2.get('loser') if lbr2_2 else None
        seventh_a = lbr1_1.get('loser') if lbr1_1 else None
        seventh_b = lbr1_2.get('loser') if lbr1_2 else None

        state['champion'] = champ
        state['runner_up'] = runner
        state['third_place'] = third
        state['fourth_place'] = fourth

        # Eliminated from group stage: Ranks 9-12 (Alpha 5-6, Omega 5-6)
        eliminated_groups = []
        for s in state['alpha_standings'][4:]:
            eliminated_groups.append(s)
        for s in state['omega_standings'][4:]:
            eliminated_groups.append(s)
        eliminated_groups.sort(key=lambda s: (-s['wins'], s['losses'], -s['map_diff'], -s['round_diff']))

        # Full 12 team standings
        standings = []
        if champ:
            standings.append({'rank': 1, 'team': champ, 'club_id': champ.get('id') or champ.get('club_id'), 'cp': 7, 'desc': 'Vô địch Stage 2 (Vé Champions #1)'})
        if runner:
            standings.append({'rank': 2, 'team': runner, 'club_id': runner.get('id') or runner.get('club_id'), 'cp': 5, 'desc': 'Á quân Stage 2 (Vé Champions #2)'})
        if third:
            standings.append({'rank': 3, 'team': third, 'club_id': third.get('id') or third.get('club_id'), 'cp': 4, 'desc': 'Hạng 3 Stage 2 (+4 CP)'})
        if fourth:
            standings.append({'rank': 4, 'team': fourth, 'club_id': fourth.get('id') or fourth.get('club_id'), 'cp': 3, 'desc': 'Hạng 4 Stage 2 (+3 CP)'})
        if fifth_a:
            standings.append({'rank': 5, 'team': fifth_a, 'club_id': fifth_a.get('id') or fifth_a.get('club_id'), 'cp': 0, 'desc': 'Top 5-6 Stage 2'})
        if fifth_b:
            standings.append({'rank': 6, 'team': fifth_b, 'club_id': fifth_b.get('id') or fifth_b.get('club_id'), 'cp': 0, 'desc': 'Top 5-6 Stage 2'})
        if seventh_a:
            standings.append({'rank': 7, 'team': seventh_a, 'club_id': seventh_a.get('id') or seventh_a.get('club_id'), 'cp': 0, 'desc': 'Top 7-8 Stage 2'})
        if seventh_b:
            standings.append({'rank': 8, 'team': seventh_b, 'club_id': seventh_b.get('id') or seventh_b.get('club_id'), 'cp': 0, 'desc': 'Top 7-8 Stage 2'})

        for idx, el in enumerate(eliminated_groups):
            t = el['team']
            standings.append({
                'rank': 9 + idx,
                'team': t,
                'club_id': t.get('id') or t.get('club_id'),
                'cp': 0,
                'desc': f"Hạng {el['rank']} Bảng {el['group']} (Bị loại vòng bảng)",
            })

        state['standings'] = standings

        # Direct Champions Qualifiers from Stage 2 Playoffs:
        state['champions_playoff_qualifiers'] = [
            {'team': champ, 'regional_seed': 1, 'slot_type': 'stage2_champion', 'title': f"{state['region'].upper()} Stage 2 Champion"},
            {'team': runner, 'regional_seed': 2, 'slot_type': 'stage2_runner_up', 'title': f"{state['region'].upper()} Stage 2 Runner-up"},
        ]

        return True

    return False


def resolve_stage2_match(state: Dict[str, Any], match_id: str,
                         winner_id: Optional[int] = None,
                         maps: Optional[List[Dict[str, Any]]] = None,
                         rating_lookup: Optional[Dict[int, int]] = None,
                         form_lookup: Optional[Dict[int, int]] = None) -> Dict[str, Any]:
    target_match = None
    is_regular = False

    for m in state.get('regular_matches', []):
        if _matches_target_id(m, match_id):
            target_match = m
            is_regular = True
            break

    if not target_match:
        for m in state.get('playoff_matches', []):
            if _matches_target_id(m, match_id):
                target_match = m
                is_regular = False
                break

    if not target_match:
        raise ValueError(f"Match {match_id} not found in Stage 2")

    # Safeguards:
    # 1. If modifying a regular season match, ensure playoffs haven't started!
    if is_regular:
        playoffs_started = any(m.get('status') == 'completed' for m in state.get('playoff_matches', []))
        if playoffs_started and target_match.get('status') == 'completed':
            raise ValueError("Không thể sửa trận vòng bảng khi vòng Playoffs đã bắt đầu thi đấu. Hãy hoàn tất giải đấu.")
    else:
        # 2. If modifying a playoff match, check downstream matches!
        downstream_map = {
            'UBR1-M1': ['UBSF-M1', 'LBR1-M1'],
            'UBR1-M2': ['UBSF-M2', 'LBR1-M2'],
            'UBSF-M1': ['UBF', 'LBR2-M1'],
            'UBSF-M2': ['UBF', 'LBR2-M2'],
            'LBR1-M1': ['LBR2-M2'],
            'LBR1-M2': ['LBR2-M1'],
            'LBR2-M1': ['LBR3'],
            'LBR2-M2': ['LBR3'],
            'UBF': ['GF', 'LBF'],
            'LBR3': ['LBF'],
            'LBF': ['GF'],
            'GF': [],
        }

        cur_mid = target_match['match_id']
        ds_targets = downstream_map.get(cur_mid, [])
        if not ds_targets:
            for k, v in downstream_map.items():
                if _matches_target_id(target_match, k):
                    ds_targets = v
                    break

        for ds_id in ds_targets:
            ds_match = next((m for m in state['playoff_matches'] if _matches_target_id(m, ds_id)), None)
            if ds_match and ds_match.get('status') == 'completed':
                raise ValueError(f"Không thể sửa trận {match_id} vì trận đấu sau ({ds_match.get('label')}) đã hoàn thành. Hãy sửa từ trận mới nhất.")

    if not target_match.get('team_a') or not target_match.get('team_b'):
        raise ValueError(f"Trận {match_id} chưa đủ 2 đội tham gia thi đấu.")

    manual_override = None
    if winner_id is not None:
        manual_override = {'winner_id': winner_id, 'maps': maps or []}

    sim_res = simulate_stage2_match(
        target_match['team_a'], target_match['team_b'],
        bo=target_match['bo'],
        rating_lookup=rating_lookup,
        form_lookup=form_lookup,
        manual_override=manual_override,
    )

    target_match['status'] = 'completed'
    target_match['winner'] = sim_res['winner']
    target_match['loser'] = sim_res['loser']
    target_match['winner_id'] = sim_res['winner_id']
    target_match['loser_id'] = sim_res['loser_id']
    target_match['team_a_score'] = sim_res['team_a_score']
    target_match['team_b_score'] = sim_res['team_b_score']
    target_match['maps'] = sim_res['maps']
    target_match['is_manual'] = sim_res['is_manual']

    advance_stage2_region(state)
    return target_match


def sim_stage2_round(state: Dict[str, Any],
                     rating_lookup: Optional[Dict[int, int]] = None,
                     form_lookup: Optional[Dict[int, int]] = None) -> int:
    """Simulate the active week in regular season or the active playable playoff wave."""
    if state.get('status') == 'completed':
        return 0

    # 1. Check if Regular Season has pending matches
    reg_matches = state.get('regular_matches', [])
    pending_reg = [m for m in reg_matches if m.get('status') != 'completed']
    if pending_reg:
        # Find lowest week with pending matches
        active_week = min(m['week'] for m in pending_reg)
        week_matches = [m for m in pending_reg if m['week'] == active_week]
        count = 0
        for m in week_matches:
            resolve_stage2_match(state, m['match_id'], rating_lookup=rating_lookup, form_lookup=form_lookup)
            count += 1
        return count

    # 2. Regular Season complete, advance playoffs wave
    playoff_matches = state.get('playoff_matches', [])
    _resolve_stage2_playoff_slots(state)
    ready_playoffs = [m for m in playoff_matches if m.get('status') != 'completed' and m.get('ready')]
    if not ready_playoffs:
        return 0

    count = 0
    # Process only currently ready matches in snapshot
    for m in list(ready_playoffs):
        resolve_stage2_match(state, m['match_id'], rating_lookup=rating_lookup, form_lookup=form_lookup)
        count += 1

    return count


def sim_stage2_remaining(state: Dict[str, Any],
                         rating_lookup: Optional[Dict[int, int]] = None,
                         form_lookup: Optional[Dict[int, int]] = None) -> int:
    """Simulate all remaining matches in Stage 2 until complete."""
    total_simmed = 0
    while state.get('status') != 'completed':
        count = sim_stage2_round(state, rating_lookup=rating_lookup, form_lookup=form_lookup)
        if count == 0:
            break
        total_simmed += count
    return total_simmed
