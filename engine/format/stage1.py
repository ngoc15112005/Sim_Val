"""
engine/format/stage1.py — VCT Stage 1 Interactive Engine (Regular Season + Playoffs)

Official VCT 2025 Format:
- 12 teams per region (Pacific, Americas, EMEA, China) from Kickoff
- Group Partition: Group Alpha (6 teams) and Group Omega (6 teams)
- Regular Season (Vòng Bảng):
  * Cross-group play: Alpha vs Omega (36 matches BO3, 6 Weeks × 6 matches/week)
  * 1 Championship Point per match win!
  * Top 3 teams from Group Alpha + Top 3 teams from Group Omega advance to Playoffs (6 teams total)
  * Ranks 4-6 from each group are eliminated (Ranks 7-12)
- Playoffs (6-team Double Elimination, 8 matches):
  * Knockout Round 1:
    - KO 1: Alpha #2 vs Omega #3 (BO3) -> Loser 5th-6th (0 CP)
    - KO 2: Omega #2 vs Alpha #3 (BO3) -> Loser 5th-6th (0 CP)
  * Upper Semifinals (Alpha #1 & Omega #1 have BYES):
    - USF 1: Alpha #1 vs Winner KO 2 (BO3)
    - USF 2: Omega #1 vs Winner KO 1 (BO3)
  * Upper Final: Winner USF 1 vs Winner USF 2 (BO3)
  * Lower Semifinal: Loser USF 1 vs Loser USF 2 (BO3) -> Loser 4th (+1 CP, qualifies to EWC)
  * Lower Final: Loser Upper Final vs Winner Lower Semifinal (BO5) -> Loser 3rd (+2 CP, qualifies to Masters Toronto #3 & EWC)
  * Grand Final: Winner Upper Final vs Winner Lower Final (BO5)
    - Winner: Champion (+5 CP, qualifies to Masters Toronto #1 & EWC)
    - Loser: Runner-up (+3 CP, qualifies to Masters Toronto #2 & EWC)
- Qualifiers:
  * Top 3 to Masters Toronto (Seed 1, 2, 3)
  * Top 4 to EWC (Pool 1, 2, 3, 4)
"""

import copy
import random
from typing import Any, Dict, List, Optional, Tuple


def stage1_config() -> Dict[str, Any]:
    return {
        'teams_per_region': 12,
        'group_alpha_teams': 6,
        'group_omega_teams': 6,
        'regular_season_weeks': 6,
        'regular_season_matches': 36,
        'playoff_teams': 6,
        'playoff_matches': 8,
        'total_matches': 44,
        'regular_win_cp': 1,
        'playoff_cp': {1: 5, 2: 3, 3: 2, 4: 1},
        'masters_qualifiers_count': 3,
        'ewc_qualifiers_count': 4,
    }


def partition_stage1_groups(participants: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Partition 12 teams into Group Alpha (6) and Group Omega (6) using serpentine seeding."""
    sorted_teams = sorted(
        participants,
        key=lambda t: (t.get('kickoff_rank') or 999, -t.get('story_rating', 80), t.get('name', ''))
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
            group_alpha.append(t_copy)
        else:
            t_copy['group'] = 'Omega'
            group_omega.append(t_copy)

    return group_alpha, group_omega


def _gen_map_score_stage1(winner_rating: int, loser_rating: int) -> Tuple[int, int]:
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


def simulate_stage1_match(team_a: Dict[str, Any], team_b: Dict[str, Any], bo: int = 3,
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
            wins_a = sum(1 for m in custom_maps if m['team_a_score'] > m['team_b_score'])
            wins_b = sum(1 for m in custom_maps if m['team_b_score'] > m['team_a_score'])
            return {
                'team_a': team_a, 'team_b': team_b,
                'team_a_id': id_a, 'team_b_id': id_b,
                'team_a_score': wins_a, 'team_b_score': wins_b,
                'winner': winner, 'loser': loser,
                'winner_id': winner_id, 'loser_id': loser.get('id') or loser.get('club_id'),
                'maps': custom_maps,
                'bo': bo,
                'is_manual': True,
            }
        else:
            wins_a = target_wins if winner == team_a else 1
            wins_b = target_wins if winner == team_b else 1
            maps = []
            for i in range(target_wins):
                sc_w, sc_l = _gen_map_score_stage1(eff_a if winner == team_a else eff_b, eff_b if winner == team_a else eff_a)
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
            sc_win, sc_lose = _gen_map_score_stage1(eff_a, eff_b)
            wins_a += 1
            maps.append({
                'map_number': map_idx + 1,
                'team_a_score': sc_win,
                'team_b_score': sc_lose,
                'winner_id': id_a,
            })
        else:
            sc_win, sc_lose = _gen_map_score_stage1(eff_b, eff_a)
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


def compute_stage1_group_standings(group_teams: List[Dict[str, Any]],
                                   completed_matches: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    stats = {}
    for t in group_teams:
        t_id = t.get('id') or t.get('club_id')
        stats[t_id] = {
            'team': t,
            'club_id': t_id,
            'name': t.get('name'),
            'short_code': t.get('short_code'),
            'logo_url': t.get('logo_url'),
            'group': t.get('group'),
            'story_rating': t.get('story_rating', 80),
            'wins': 0,
            'losses': 0,
            'map_won': 0,
            'map_lost': 0,
            'map_diff': 0,
            'round_won': 0,
            'round_lost': 0,
            'round_diff': 0,
            'cp_earned': 0,
        }

    for m in completed_matches:
        if m.get('status') != 'completed':
            continue
        a_id = m.get('team_a_id')
        b_id = m.get('team_b_id')
        sc_a = m.get('team_a_score', 0)
        sc_b = m.get('team_b_score', 0)
        maps = m.get('maps', [])

        rd_a = sum(map_info.get('team_a_score', 0) for map_info in maps)
        rd_b = sum(map_info.get('team_b_score', 0) for map_info in maps)

        if a_id in stats:
            if sc_a > sc_b:
                stats[a_id]['wins'] += 1
                stats[a_id]['cp_earned'] += 1
            else:
                stats[a_id]['losses'] += 1
            stats[a_id]['map_won'] += sc_a
            stats[a_id]['map_lost'] += sc_b
            stats[a_id]['map_diff'] = stats[a_id]['map_won'] - stats[a_id]['map_lost']
            stats[a_id]['round_won'] += rd_a
            stats[a_id]['round_lost'] += rd_b
            stats[a_id]['round_diff'] = stats[a_id]['round_won'] - stats[a_id]['round_lost']

        if b_id in stats:
            if sc_b > sc_a:
                stats[b_id]['wins'] += 1
                stats[b_id]['cp_earned'] += 1
            else:
                stats[b_id]['losses'] += 1
            stats[b_id]['map_won'] += sc_b
            stats[b_id]['map_lost'] += sc_a
            stats[b_id]['map_diff'] = stats[b_id]['map_won'] - stats[b_id]['map_lost']
            stats[b_id]['round_won'] += rd_b
            stats[b_id]['round_lost'] += rd_a
            stats[b_id]['round_diff'] = stats[b_id]['round_won'] - stats[b_id]['round_lost']

    standings = list(stats.values())
    standings.sort(key=lambda s: (-s['wins'], s['losses'], -s['map_diff'], -s['round_diff'], -s['story_rating']))

    for i, s in enumerate(standings):
        s['rank'] = i + 1
        s['advanced'] = (i < 3)

    return standings


def init_stage1_region_state(region_slug: str, participants: List[Dict[str, Any]]) -> Dict[str, Any]:
    if len(participants) != 12:
        raise ValueError(f"Stage 1 requires exactly 12 teams, got {len(participants)}")

    group_alpha, group_omega = partition_stage1_groups(participants)

    regular_matches = []
    # 6 Weeks cross-group: each week 6 matches
    for w in range(1, 7):
        for i in range(6):
            t_a = group_alpha[i]
            t_b = group_omega[(i + w - 1) % 6]
            m_id = f"reg_w{w}_m{i+1}"
            regular_matches.append({
                'match_id': m_id,
                'round_type': 'regular',
                'week': w,
                'match_index': i + 1,
                'label': f"Tuần {w} - Trận {i+1}",
                'team_a': t_a,
                'team_b': t_b,
                'team_a_id': t_a.get('id') or t_a.get('club_id'),
                'team_b_id': t_b.get('id') or t_b.get('club_id'),
                'bo': 3,
                'status': 'pending',
                'winner': None,
                'loser': None,
                'winner_id': None,
                'loser_id': None,
                'team_a_score': 0,
                'team_b_score': 0,
                'maps': [],
            })

    alpha_standings = compute_stage1_group_standings(group_alpha, [])
    omega_standings = compute_stage1_group_standings(group_omega, [])

    playoff_templates = [
        # Knockout Round 1 (Upper QF)
        {
            'match_id': 'ko_1',
            'round_type': 'ko',
            'round_name': 'ko_1',
            'label': 'Knockout Vòng 1 - Trận 1',
            'team_a_source': {'type': 'group_seed', 'group': 'Alpha', 'seed': 2},
            'team_b_source': {'type': 'group_seed', 'group': 'Omega', 'seed': 3},
            'bo': 3,
            'loser_standing_rank': 5,
        },
        {
            'match_id': 'ko_2',
            'round_type': 'ko',
            'round_name': 'ko_2',
            'label': 'Knockout Vòng 1 - Trận 2',
            'team_a_source': {'type': 'group_seed', 'group': 'Omega', 'seed': 2},
            'team_b_source': {'type': 'group_seed', 'group': 'Alpha', 'seed': 3},
            'bo': 3,
            'loser_standing_rank': 6,
        },
        # Upper Semifinals
        {
            'match_id': 'upper_sf_1',
            'round_type': 'upper_sf',
            'round_name': 'upper_sf_1',
            'label': 'Bán kết Nhánh thắng 1',
            'team_a_source': {'type': 'group_seed', 'group': 'Alpha', 'seed': 1},
            'team_b_source': {'type': 'winner_of', 'value': 'ko_2'},
            'bo': 3,
        },
        {
            'match_id': 'upper_sf_2',
            'round_type': 'upper_sf',
            'round_name': 'upper_sf_2',
            'label': 'Bán kết Nhánh thắng 2',
            'team_a_source': {'type': 'group_seed', 'group': 'Omega', 'seed': 1},
            'team_b_source': {'type': 'winner_of', 'value': 'ko_1'},
            'bo': 3,
        },
        # Upper Final
        {
            'match_id': 'upper_final',
            'round_type': 'upper_final',
            'round_name': 'upper_final',
            'label': 'Chung kết Nhánh thắng (Tranh vé Chung kết & Masters)',
            'team_a_source': {'type': 'winner_of', 'value': 'upper_sf_1'},
            'team_b_source': {'type': 'winner_of', 'value': 'upper_sf_2'},
            'bo': 3,
            'is_major_decider': 1,
        },
        # Lower Semifinal
        {
            'match_id': 'lower_semifinal',
            'round_type': 'lower_sf',
            'round_name': 'lower_semifinal',
            'label': 'Bán kết Nhánh thua (Tranh vé EWC #4)',
            'team_a_source': {'type': 'loser_of', 'value': 'upper_sf_1'},
            'team_b_source': {'type': 'loser_of', 'value': 'upper_sf_2'},
            'bo': 3,
            'loser_standing_rank': 4,
        },
        # Lower Final
        {
            'match_id': 'lower_final',
            'round_type': 'lower_final',
            'round_name': 'lower_final',
            'label': 'Chung kết Nhánh thua (Tranh vé Masters #2)',
            'team_a_source': {'type': 'loser_of', 'value': 'upper_final'},
            'team_b_source': {'type': 'winner_of', 'value': 'lower_semifinal'},
            'bo': 5,
            'loser_standing_rank': 3,
            'is_major_decider': 1,
        },
        # Grand Final
        {
            'match_id': 'grand_final',
            'round_type': 'grand_final',
            'round_name': 'grand_final',
            'label': 'Chung kết Tổng VCT Stage 1',
            'team_a_source': {'type': 'winner_of', 'value': 'upper_final'},
            'team_b_source': {'type': 'winner_of', 'value': 'lower_final'},
            'bo': 5,
            'winner_standing_rank': 1,
            'loser_standing_rank': 2,
        },
    ]

    playoff_matches = []
    for tmpl in playoff_templates:
        playoff_matches.append({
            'match_id': tmpl['match_id'],
            'round_type': tmpl['round_type'],
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
            'team_a_source_label': '',
            'team_b_source_label': '',
            'winner': None,
            'loser': None,
            'winner_id': None,
            'loser_id': None,
            'team_a_score': 0,
            'team_b_score': 0,
            'maps': [],
            'loser_standing_rank': tmpl.get('loser_standing_rank'),
            'winner_standing_rank': tmpl.get('winner_standing_rank'),
            'is_major_decider': tmpl.get('is_major_decider', 0),
        })

    state = {
        'region': region_slug,
        'status': 'in_progress',
        'current_phase': 'regular_season',  # 'regular_season', 'playoffs', 'completed'
        'participants': participants,
        'group_alpha': group_alpha,
        'group_omega': group_omega,
        'regular_matches': regular_matches,
        'alpha_standings': alpha_standings,
        'omega_standings': omega_standings,
        'playoff_matches': playoff_matches,
        'champion': None,
        'runner_up': None,
        'third_place': None,
        'fourth_place': None,
        'masters_qualifiers': [],
        'ewc_qualifiers': [],
        'standings': [],
        'rewards_awarded': False,
    }

    _resolve_stage1_playoff_slots(state)
    return state


def _resolve_stage1_playoff_slots(state: Dict[str, Any]):
    alpha_standings = state.get('alpha_standings', [])
    omega_standings = state.get('omega_standings', [])
    playoff_matches = state.get('playoff_matches', [])
    completed_playoffs = {m['match_id']: m for m in playoff_matches if m.get('status') == 'completed'}

    reg_completed = all(m.get('status') == 'completed' for m in state.get('regular_matches', []))

    def resolve_source(src: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], str]:
        stype = src.get('type')
        if stype == 'group_seed':
            grp = src.get('group')
            seed = src.get('seed')
            st_list = alpha_standings if grp == 'Alpha' else omega_standings
            label = f"{grp} #{seed}"
            if reg_completed and len(st_list) >= seed:
                return st_list[seed - 1]['team'], label
            return None, label

        elif stype == 'winner_of':
            ref_id = src.get('value')
            label = f"Thắng {ref_id}"
            if ref_id in completed_playoffs:
                return completed_playoffs[ref_id].get('winner'), label
            return None, label

        elif stype == 'loser_of':
            ref_id = src.get('value')
            label = f"Thua {ref_id}"
            if ref_id in completed_playoffs:
                return completed_playoffs[ref_id].get('loser'), label
            return None, label

        return None, 'TBD'

    for pm in playoff_matches:
        if pm.get('status') == 'completed':
            continue

        team_a, label_a = resolve_source(pm['team_a_source'])
        team_b, label_b = resolve_source(pm['team_b_source'])

        pm['team_a'] = team_a
        pm['team_b'] = team_b
        pm['team_a_id'] = (team_a.get('id') or team_a.get('club_id')) if team_a else None
        pm['team_b_id'] = (team_b.get('id') or team_b.get('club_id')) if team_b else None
        pm['team_a_source_label'] = label_a
        pm['team_b_source_label'] = label_b
        pm['ready'] = (team_a is not None and team_b is not None)


def advance_stage1_region(state: Dict[str, Any]) -> bool:
    reg_matches = state.get('regular_matches', [])
    reg_done = all(m.get('status') == 'completed' for m in reg_matches)

    state['alpha_standings'] = compute_stage1_group_standings(state['group_alpha'], reg_matches)
    state['omega_standings'] = compute_stage1_group_standings(state['group_omega'], reg_matches)

    if reg_done and state['current_phase'] == 'regular_season':
        state['current_phase'] = 'playoffs'

    _resolve_stage1_playoff_slots(state)

    playoff_matches = state.get('playoff_matches', [])
    playoffs_done = all(m.get('status') == 'completed' for m in playoff_matches)

    if playoffs_done and state['current_phase'] == 'playoffs':
        state['current_phase'] = 'completed'
        state['status'] = 'completed'

        completed_map = {m['match_id']: m for m in playoff_matches}
        gf = completed_map.get('grand_final')
        lf = completed_map.get('lower_final')
        lsf = completed_map.get('lower_semifinal')
        ko1 = completed_map.get('ko_1')
        ko2 = completed_map.get('ko_2')

        champ = gf.get('winner') if gf else None
        runner = gf.get('loser') if gf else None
        third = lf.get('loser') if lf else None
        fourth = lsf.get('loser') if lsf else None
        fifth_a = ko1.get('loser') if ko1 else None
        fifth_b = ko2.get('loser') if ko2 else None

        state['champion'] = champ
        state['runner_up'] = runner
        state['third_place'] = third
        state['fourth_place'] = fourth

        # Masters Toronto: Top 3
        state['masters_qualifiers'] = [
            {'team': champ, 'regional_seed': 1, 'title': f"{state['region'].upper()} Stage 1 Champion"},
            {'team': runner, 'regional_seed': 2, 'title': f"{state['region'].upper()} Stage 1 Runner-up"},
            {'team': third, 'regional_seed': 3, 'title': f"{state['region'].upper()} Stage 1 3rd Place"},
        ]

        # EWC: Top 4
        state['ewc_qualifiers'] = [
            {'team': champ, 'pool': 1, 'title': f"{state['region'].upper()} Champion"},
            {'team': runner, 'pool': 2, 'title': f"{state['region'].upper()} Runner-up"},
            {'team': third, 'pool': 3, 'title': f"{state['region'].upper()} 3rd Place"},
            {'team': fourth, 'pool': 4, 'title': f"{state['region'].upper()} 4th Place"},
        ]

        # Full 12 team standings
        standings = []
        if champ:
            standings.append({'rank': 1, 'team': champ, 'club_id': champ.get('id') or champ.get('club_id'), 'cp': 5, 'desc': 'Vô địch Stage 1 (Vé Masters & EWC)'})
        if runner:
            standings.append({'rank': 2, 'team': runner, 'club_id': runner.get('id') or runner.get('club_id'), 'cp': 3, 'desc': 'Á quân Stage 1 (Vé Masters & EWC)'})
        if third:
            standings.append({'rank': 3, 'team': third, 'club_id': third.get('id') or third.get('club_id'), 'cp': 2, 'desc': 'Hạng 3 Stage 1 (Vé Masters & EWC)'})
        if fourth:
            standings.append({'rank': 4, 'team': fourth, 'club_id': fourth.get('id') or fourth.get('club_id'), 'cp': 1, 'desc': 'Hạng 4 Stage 1 (Vé EWC)'})
        if fifth_a:
            standings.append({'rank': 5, 'team': fifth_a, 'club_id': fifth_a.get('id') or fifth_a.get('club_id'), 'cp': 0, 'desc': 'Top 5-6 (Knockout)'})
        if fifth_b:
            standings.append({'rank': 6, 'team': fifth_b, 'club_id': fifth_b.get('id') or fifth_b.get('club_id'), 'cp': 0, 'desc': 'Top 5-6 (Knockout)'})

        # Eliminated from group stage: Ranks 7-12
        eliminated_groups = []
        for s in state['alpha_standings'][3:]:
            eliminated_groups.append(s)
        for s in state['omega_standings'][3:]:
            eliminated_groups.append(s)
        eliminated_groups.sort(key=lambda s: (-s['wins'], s['losses'], -s['map_diff'], -s['round_diff']))

        for idx, el in enumerate(eliminated_groups):
            t = el['team']
            standings.append({
                'rank': 7 + idx,
                'team': t,
                'club_id': t.get('id') or t.get('club_id'),
                'cp': 0,
                'desc': f"Hạng {el['rank']} Bảng {el['group']}",
            })

        state['standings'] = standings
        return True

    return False


def resolve_stage1_match(state: Dict[str, Any], match_id: str,
                         winner_id: Optional[int] = None,
                         maps: Optional[List[Dict[str, Any]]] = None,
                         rating_lookup: Optional[Dict[int, int]] = None,
                         form_lookup: Optional[Dict[int, int]] = None) -> Dict[str, Any]:
    # Check if match is in regular matches
    reg_matches = state.get('regular_matches', [])
    target_match = None
    is_regular = False

    for m in reg_matches:
        if m['match_id'] == match_id:
            target_match = m
            is_regular = True
            break

    if not target_match:
        for m in state.get('playoff_matches', []):
            if m['match_id'] == match_id:
                target_match = m
                is_regular = False
                break

    if not target_match:
        raise ValueError(f"Match {match_id} not found in Stage 1")

    # Safeguards:
    # 1. If modifying a regular season match, ensure playoffs haven't started!
    if is_regular:
        playoffs_started = any(m.get('status') == 'completed' for m in state.get('playoff_matches', []))
        if playoffs_started and target_match.get('status') == 'completed':
            raise ValueError("Không thể sửa trận vòng bảng khi vòng Playoffs đã bắt đầu thi đấu. Hãy hoàn tất giải đấu.")
    else:
        # 2. If modifying a playoff match, check downstream matches!
        downstream_map = {
            'ko_1': ['upper_sf_2'],
            'ko_2': ['upper_sf_1'],
            'upper_sf_1': ['upper_final', 'lower_semifinal'],
            'upper_sf_2': ['upper_final', 'lower_semifinal'],
            'upper_final': ['grand_final', 'lower_final'],
            'lower_semifinal': ['lower_final'],
            'lower_final': ['grand_final'],
            'grand_final': [],
        }
        for ds_id in downstream_map.get(match_id, []):
            ds_match = next((m for m in state['playoff_matches'] if m['match_id'] == ds_id), None)
            if ds_match and ds_match.get('status') == 'completed':
                raise ValueError(f"Không thể sửa trận {match_id} vì trận đấu sau ({ds_match.get('label')}) đã hoàn thành. Hãy sửa từ trận mới nhất.")

    if not target_match.get('team_a') or not target_match.get('team_b'):
        raise ValueError(f"Trận {match_id} chưa đủ 2 đội tham gia thi đấu.")

    manual_override = None
    if winner_id is not None:
        manual_override = {'winner_id': winner_id, 'maps': maps or []}

    sim_res = simulate_stage1_match(
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

    advance_stage1_region(state)
    return target_match


def sim_stage1_round(state: Dict[str, Any],
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
            resolve_stage1_match(state, m['match_id'], rating_lookup=rating_lookup, form_lookup=form_lookup)
            count += 1
        return count

    # 2. Regular Season complete, advance playoffs wave
    playoff_matches = state.get('playoff_matches', [])
    _resolve_stage1_playoff_slots(state)
    ready_playoffs = [m for m in playoff_matches if m.get('status') != 'completed' and m.get('ready')]
    if not ready_playoffs:
        return 0

    count = 0
    # Process only currently ready matches in snapshot
    for m in list(ready_playoffs):
        resolve_stage1_match(state, m['match_id'], rating_lookup=rating_lookup, form_lookup=form_lookup)
        count += 1

    return count


def sim_stage1_remaining(state: Dict[str, Any],
                         rating_lookup: Optional[Dict[int, int]] = None,
                         form_lookup: Optional[Dict[int, int]] = None) -> int:
    """Simulate all remaining matches in Stage 1 until complete."""
    total_simmed = 0
    while state.get('status') != 'completed':
        count = sim_stage1_round(state, rating_lookup=rating_lookup, form_lookup=form_lookup)
        if count == 0:
            break
        total_simmed += count
    return total_simmed
