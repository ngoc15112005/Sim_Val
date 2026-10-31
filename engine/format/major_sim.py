"""
engine/format/major_sim.py — VCT Major (Masters Bangkok) Pure Simulation Engine

Specifications:
- 8 World Elite Teams (Top 2 from Kickoff in Pacific, Americas, EMEA, China)
- Stage 1: Swiss Stage (8 teams, 2 wins advance / 2 losses eliminated, max 3 rounds, 10 matches)
  * Round 1: 4 matches (BO3) — Cross-region pairing (Seed 1 vs Seed 2 across different regions)
  * Round 2: 4 matches (BO3) — 1-0 vs 1-0 (2 matches), 0-1 vs 0-1 (2 matches)
  * Round 3: 2 matches (BO3) — 1-1 vs 1-1 (2 matches)
  * Advancing: 4 teams (2 at 2-0, 2 at 2-1)
  * Eliminated: 4 teams (2 at 0-2, 2 at 1-2)
- Stage 2: Playoffs (4 teams Double Elimination, 6 matches)
  * Upper Semifinal 1: Seed 1 vs Seed 4 (BO3)
  * Upper Semifinal 2: Seed 2 vs Seed 3 (BO3)
  * Upper Final: Winner SF1 vs Winner SF2 (BO3)
  * Lower Round 1: Loser SF1 vs Loser SF2 (BO3)
  * Lower Final: Winner LB R1 vs Loser Upper Final (BO3/BO5)
  * Grand Final: Winner Upper Final vs Winner Lower Final (BO5)
- Championship Points:
  * 1st: 5 CP (Major Champion)
  * 2nd: 3 CP (Major Runner-up)
  * 3rd: 2 CP
  * 4th: 1 CP
  * 5th-8th: 0 CP
"""

import random
from typing import List, Dict, Optional, Any, Tuple
from engine.format.major import (
    generate_swiss_pairings,
    get_swiss_standings,
    generate_playoffs_4_teams,
    resolve_slot,
)
from engine.match import _calc_region_bonus, _gen_map_score
from engine.points import get_stage_points


def _calc_international_win_rate(team_a: Dict[str, Any], team_b: Dict[str, Any],
                                 is_grand_final: bool = False,
                                 streak_a: int = 0, streak_b: int = 0) -> float:
    """Calculate win probability for an international match.
    
    Philosophy ('Cỏ lúa bằng nhau'):
    - Base probability is 0.50.
    - Regional Meta DNA applies across different regions.
    - Momentum streak bonus.
    """
    prob_a = 0.50
    reg_a = team_a.get('region_slug') or team_a.get('region')
    reg_b = team_b.get('region_slug') or team_b.get('region')

    if reg_a and reg_b and reg_a != reg_b:
        bonus_a = _calc_region_bonus(reg_a, tour_type='major', is_grand_final=is_grand_final, is_champions=False, is_masters=True)
        bonus_b = _calc_region_bonus(reg_b, tour_type='major', is_grand_final=is_grand_final, is_champions=False, is_masters=True)
        prob_a += (bonus_a - bonus_b)

    streak_diff = min(streak_a, 3) - min(streak_b, 3)
    prob_a += streak_diff * 0.015

    return max(0.20, min(0.80, prob_a))


def simulate_major_single_match(team_a: Dict[str, Any], team_b: Dict[str, Any], bo: int = 3,
                                is_grand_final: bool = False,
                                manual_override: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Simulate a single Major match or apply manual override."""
    id_a = team_a['id'] if 'id' in team_a else team_a.get('club_id')
    id_b = team_b['id'] if 'id' in team_b else team_b.get('club_id')

    r_a = team_a.get('story_rating') or team_a.get('current_rating') or team_a.get('rating') or 80
    r_b = team_b.get('story_rating') or team_b.get('current_rating') or team_b.get('rating') or 80

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
                'winner_id': winner_id, 'loser_id': loser['id'] if 'id' in loser else loser.get('club_id'),
                'maps': custom_maps,
                'bo': bo,
                'is_manual': True,
            }
        else:
            wins_a = target_wins if winner == team_a else 1
            wins_b = target_wins if winner == team_b else 1
            maps = []
            for i in range(target_wins):
                sc_w, sc_l = _gen_map_score(r_a if winner == team_a else r_b, r_b if winner == team_a else r_a, is_bo5=(bo == 5))
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
                'winner_id': winner_id, 'loser_id': loser['id'] if 'id' in loser else loser.get('club_id'),
                'maps': maps,
                'bo': bo,
                'is_manual': True,
            }

    prob_a = _calc_international_win_rate(team_a, team_b, is_grand_final=is_grand_final)

    wins_a = 0
    wins_b = 0
    maps = []

    for map_idx in range(max_maps):
        roll = random.random()
        if roll < prob_a:
            sc_win, sc_lose = _gen_map_score(r_a, r_b, is_bo5=(bo == 5))
            wins_a += 1
            maps.append({
                'map_number': map_idx + 1,
                'team_a_score': sc_win,
                'team_b_score': sc_lose,
                'winner_id': id_a,
            })
        else:
            sc_win, sc_lose = _gen_map_score(r_b, r_a, is_bo5=(bo == 5))
            wins_b += 1
            maps.append({
                'map_number': map_idx + 1,
                'team_a_score': sc_lose,
                'team_b_score': sc_win,
                'winner_id': id_b,
            })

        if wins_a >= target_wins or wins_b >= target_wins:
            break

    winner = team_a if wins_a >= target_wins else team_b
    loser = team_b if winner == team_a else team_a
    winner_id = id_a if winner == team_a else id_b
    loser_id = id_b if winner == team_a else id_a

    return {
        'team_a': team_a,
        'team_b': team_b,
        'team_a_id': id_a,
        'team_b_id': id_b,
        'team_a_score': wins_a,
        'team_b_score': wins_b,
        'winner': winner,
        'loser': loser,
        'winner_id': winner_id,
        'loser_id': loser_id,
        'maps': maps,
        'bo': bo,
        'is_manual': False,
    }


def simulate_major_tournament(teams: List[Dict[str, Any]],
                              manual_overrides: Optional[Dict[str, Any]] = None,
                              previous_result: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Execute complete VCT Major (Masters Bangkok) tournament.
    
    Args:
        teams: List of 8 team dicts with {id, name, short_code, region, regional_seed}
        manual_overrides: optional dict {round_name: {'winner_id': int, ...}}
        previous_result: optional dict containing previous tournament state to preserve unchanged matches
    
    Returns:
        Structured results including Swiss matches, standings, playoff matches, champion, and CP.
    """
    if len(teams) != 8:
        raise ValueError(f"Major requires exactly 8 teams, received {len(teams)}")

    # Ensure each team has region and regional_seed
    normalized_teams = []
    for t in teams:
        norm_t = dict(t)
        if 'region' not in norm_t and 'region_slug' in norm_t:
            norm_t['region'] = norm_t['region_slug']
        norm_t.setdefault('regional_seed', 1)
        normalized_teams.append(norm_t)

    overrides = manual_overrides or {}
    completed_swiss: List[Dict[str, Any]] = []

    has_swiss_override = any(k.startswith('swiss_') for k in overrides.keys())

    # ──── Stage 1: Swiss (Rounds 1, 2, 3) ────
    if previous_result and not has_swiss_override and previous_result.get('swiss_matches'):
        completed_swiss = list(previous_result['swiss_matches'])
        swiss_standings = previous_result['swiss_standings']
        advancing = [s['team'] for s in swiss_standings if s['advanced']]
        eliminated = [s['team'] for s in swiss_standings if s['eliminated']]
    else:
        for current_round in [1, 2, 3]:
            pairs = generate_swiss_pairings(normalized_teams, current_round, completed_swiss)
            if not pairs:
                break

            for idx, (t_a, t_b) in enumerate(pairs):
                r_name = f'swiss_r{current_round}_m{idx + 1}'
                m_override = overrides.get(r_name)
                sim = simulate_major_single_match(t_a, t_b, bo=3, manual_override=m_override)
                sim.update({
                    'round': current_round,
                    'round_name': r_name,
                    'label': f'Swiss Vòng {current_round} - Trận {idx + 1}',
                })
                completed_swiss.append(sim)

        # Compute Swiss standings & qualifiers
        swiss_standings = get_swiss_standings(normalized_teams, completed_swiss)
        advancing = [s['team'] for s in swiss_standings if s['advanced']]
        eliminated = [s['team'] for s in swiss_standings if s['eliminated']]

    if len(advancing) != 4:
        raise RuntimeError(f"Expected 4 advancing teams from Swiss, got {len(advancing)}")

    # Assign seeds 1..4 for Playoffs
    for idx, t in enumerate(advancing):
        t['bracket_seed'] = idx + 1

    # ──── Stage 2: Playoffs (4 teams Double Elimination) ────
    playoff_templates = generate_playoffs_4_teams(advancing)
    completed_playoffs: Dict[str, Dict[str, Any]] = {}
    playoff_matches_list: List[Dict[str, Any]] = []

    seed_map = {t['bracket_seed']: t for t in advancing}
    prev_playoffs = previous_result.get('completed_playoffs', {}) if previous_result else {}

    for tpl in playoff_templates:
        r_name = tpl['round_name']
        bo = 5 if r_name == 'grand_final' else 3
        is_gf = (r_name == 'grand_final')

        # Resolve teams
        src_a = tpl['sources']['team_a']
        src_b = tpl['sources']['team_b']

        t_a = seed_map.get(src_a['value']) if src_a['type'] == 'seed' else None
        t_b = seed_map.get(src_b['value']) if src_b['type'] == 'seed' else None

        if not t_a and src_a['type'] in ('winner_of', 'loser_of'):
            src_m = completed_playoffs.get(src_a['value'])
            t_a = src_m['winner'] if src_a['type'] == 'winner_of' else src_m['loser']

        if not t_b and src_b['type'] in ('winner_of', 'loser_of'):
            src_m = completed_playoffs.get(src_b['value'])
            t_b = src_m['winner'] if src_b['type'] == 'winner_of' else src_m['loser']

        if not t_a or not t_b:
            raise RuntimeError(f"Could not resolve teams for Playoff match {r_name}")

        id_a = t_a['id'] if 'id' in t_a else t_a.get('club_id')
        id_b = t_b['id'] if 'id' in t_b else t_b.get('club_id')

        m_override = overrides.get(r_name)
        if m_override:
            sim = simulate_major_single_match(t_a, t_b, bo=bo, is_grand_final=is_gf, manual_override=m_override)
        elif r_name in prev_playoffs:
            prev_m = prev_playoffs[r_name]
            if prev_m.get('team_a_id') == id_a and prev_m.get('team_b_id') == id_b:
                sim = dict(prev_m)
            else:
                sim = simulate_major_single_match(t_a, t_b, bo=bo, is_grand_final=is_gf)
        else:
            sim = simulate_major_single_match(t_a, t_b, bo=bo, is_grand_final=is_gf)

        sim.update({
            'round_name': r_name,
            'round_type': tpl['round_type'],
            'bo': bo,
            'label': _get_playoff_label(r_name),
        })

        completed_playoffs[r_name] = sim
        playoff_matches_list.append(sim)

    # Standings & Championship Points:
    gf = completed_playoffs['grand_final']
    lb_final = completed_playoffs['lower_final']
    lb_r1 = completed_playoffs['lower_round1']

    champion = gf['winner']
    runner_up = gf['loser']
    third_place = lb_final['loser']
    fourth_place = lb_r1['loser']

    standings = [
        {
            'rank': 1,
            'team': champion,
            'club_id': champion['id'],
            'title': 'Vô địch VCT Major (Masters Bangkok)',
            'championship_points': get_stage_points('major', rank=1),  # 5 CP
        },
        {
            'rank': 2,
            'team': runner_up,
            'club_id': runner_up['id'],
            'title': 'Á quân VCT Major',
            'championship_points': get_stage_points('major', rank=2),  # 3 CP
        },
        {
            'rank': 3,
            'team': third_place,
            'club_id': third_place['id'],
            'title': 'Hạng 3 (Thua Chung kết Nhánh thua)',
            'championship_points': get_stage_points('major', rank=3),  # 2 CP
        },
        {
            'rank': 4,
            'team': fourth_place,
            'club_id': fourth_place['id'],
            'title': 'Hạng 4 (Thua Vòng 1 Nhánh thua)',
            'championship_points': get_stage_points('major', rank=4),  # 1 CP
        },
    ]

    for elim_team in eliminated:
        standings.append({
            'rank': 5,
            'team': elim_team,
            'club_id': elim_team['id'],
            'title': 'Bị loại ở Vòng Thụy Sĩ (Swiss Stage)',
            'championship_points': 0,
        })

    return {
        'tournament_name': 'VCT Major (Masters Bangkok)',
        'teams': normalized_teams,
        'swiss_matches': completed_swiss,
        'swiss_standings': swiss_standings,
        'swiss_qualifiers': advancing,
        'playoff_matches': playoff_matches_list,
        'completed_playoffs': completed_playoffs,
        'champion': champion,
        'runner_up': runner_up,
        'standings': standings,
        'total_matches_count': len(completed_swiss) + len(playoff_matches_list),
    }


def _get_playoff_label(round_name: str) -> str:
    labels = {
        'upper_semifinal_1': 'Bán kết Nhánh thắng 1',
        'upper_semifinal_2': 'Bán kết Nhánh thắng 2',
        'upper_final': 'Chung kết Nhánh thắng',
        'lower_round1': 'Vòng 1 Nhánh thua',
        'lower_final': 'Chung kết Nhánh thua',
        'grand_final': 'Chung kết Tổng (BO5)',
    }
    return labels.get(round_name, round_name)
