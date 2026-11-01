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
from engine.match import _calc_region_bonus, _gen_map_score, calc_pure_international_win_rate
from engine.points import get_stage_points


def _calc_international_win_rate(team_a: Dict[str, Any], team_b: Dict[str, Any],
                                 is_grand_final: bool = False,
                                 is_playoff: bool = False,
                                 streak_a: int = 0, streak_b: int = 0,
                                 prior_a: int = 0, prior_b: int = 0) -> float:
    """Calculate win probability for an international match.
    
    Philosophy ('Cỏ lúa bằng nhau'):
    - Base probability is 0.50 (Rating is NOT added to win probability).
    - Regional Meta DNA applies across different regions.
    - Seed 1 Curse: -4% cold start for direct playoff seeds.
    - Warm-up / Match Rhythm: +3% for battle-tested teams.
    - Momentum streak bonus.
    """
    reg_a = team_a.get('region_slug') or team_a.get('region')
    reg_b = team_b.get('region_slug') or team_b.get('region')
    seed_a = team_a.get('regional_seed') or team_a.get('seed') or 2
    seed_b = team_b.get('regional_seed') or team_b.get('seed') or 2

    return calc_pure_international_win_rate(
        region_a=reg_a,
        region_b=reg_b,
        tour_type='major',
        is_grand_final=is_grand_final,
        is_playoff=is_playoff,
        seed_a=seed_a,
        seed_b=seed_b,
        prior_a=prior_a,
        prior_b=prior_b,
        streak_a=streak_a,
        streak_b=streak_b,
    )


def simulate_major_single_match(team_a: Dict[str, Any], team_b: Dict[str, Any], bo: int = 3,
                                is_grand_final: bool = False,
                                is_playoff: bool = False,
                                prior_a: int = 0, prior_b: int = 0,
                                streak_a: int = 0, streak_b: int = 0,
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

    prob_a = _calc_international_win_rate(
        team_a, team_b,
        is_grand_final=is_grand_final,
        is_playoff=is_playoff,
        streak_a=streak_a,
        streak_b=streak_b,
        prior_a=prior_a,
        prior_b=prior_b,
    )

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


def init_major_state(teams: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Initialize interactive state for VCT Major (Masters Bangkok) 8 teams."""
    if len(teams) != 8:
        raise ValueError(f"Major requires exactly 8 teams, received {len(teams)}")

    normalized_teams = []
    for t in teams:
        norm_t = dict(t)
        norm_t['id'] = norm_t.get('id') or norm_t.get('club_id')
        norm_t['club_id'] = norm_t['id']
        if 'region' not in norm_t and 'region_slug' in norm_t:
            norm_t['region'] = norm_t['region_slug']
        norm_t.setdefault('regional_seed', 1)
        normalized_teams.append(norm_t)

    r1_pairs = generate_swiss_pairings(normalized_teams, 1, [])
    swiss_matches = []
    for idx, (t_a, t_b) in enumerate(r1_pairs):
        r_name = f'swiss_r1_m{idx + 1}'
        swiss_matches.append({
            'id': f"major_{r_name}",
            'round': 1,
            'round_name': r_name,
            'label': f'Swiss Vòng 1 - Trận {idx + 1}',
            'bo': 3,
            'status': 'pending',
            'team_a': t_a,
            'team_b': t_b,
            'team_a_id': t_a['id'],
            'team_b_id': t_b['id'],
            'team_a_score': 0,
            'team_b_score': 0,
            'winner_id': None,
            'loser_id': None,
            'winner': None,
            'loser': None,
            'maps': [],
            'is_manual': False,
        })

    standings = get_swiss_standings(normalized_teams, [])

    return {
        'tournament_name': 'VCT Major (Masters Bangkok)',
        'status': 'in_progress',          # 'in_progress' or 'completed'
        'current_stage': 'swiss',          # 'swiss' or 'playoffs'
        'current_swiss_round': 1,         # 1..3
        'teams': normalized_teams,
        'swiss_matches': swiss_matches,
        'swiss_standings': standings,
        'swiss_qualifiers': [],
        'swiss_eliminated': [],
        'playoff_matches': [],
        'completed_playoffs': {},
        'champion': None,
        'runner_up': None,
        'standings': [],
        'total_matches_count': 0,
    }


def _init_major_playoffs(major_data: Dict[str, Any]):
    advancing = major_data['swiss_qualifiers']
    for idx, t in enumerate(advancing):
        t['bracket_seed'] = idx + 1

    templates = generate_playoffs_4_teams(advancing)
    playoff_matches = []
    for idx, tpl in enumerate(templates):
        r_name = tpl['round_name']
        bo = 5 if r_name == 'grand_final' else 3
        playoff_matches.append({
            'id': f"major_{r_name}",
            'round_name': r_name,
            'round_type': tpl['round_type'],
            'label': _get_playoff_label(r_name),
            'bo': bo,
            'status': 'pending',
            'sources': tpl['sources'],
            'team_a': None,
            'team_b': None,
            'team_a_id': None,
            'team_b_id': None,
            'placeholder_a': None,
            'placeholder_b': None,
            'team_a_score': 0,
            'team_b_score': 0,
            'winner_id': None,
            'loser_id': None,
            'winner': None,
            'loser': None,
            'maps': [],
            'is_manual': False,
        })

    major_data['playoff_matches'] = playoff_matches
    _resolve_major_playoff_slots(major_data)


def _resolve_major_playoff_slots(major_data: Dict[str, Any]):
    advancing = major_data.get('swiss_qualifiers', [])
    seed_map = {t['bracket_seed']: t for t in advancing}
    completed_playoffs = {m['round_name']: m for m in major_data.get('playoff_matches', []) if m['status'] == 'completed'}
    major_data['completed_playoffs'] = completed_playoffs

    def resolve_source(src):
        stype = src.get('type')
        sval = src.get('value')
        if stype == 'seed':
            return seed_map.get(sval)
        if stype == 'winner_of':
            feeder = completed_playoffs.get(sval)
            return feeder['winner'] if feeder else None
        if stype == 'loser_of':
            feeder = completed_playoffs.get(sval)
            return feeder['loser'] if feeder else None
        return None

    def get_source_label(src):
        stype = src.get('type')
        sval = src.get('value')
        if stype == 'seed':
            return f"Seed #{sval}"
        labels = {
            'upper_semifinal_1': 'Bán kết 1',
            'upper_semifinal_2': 'Bán kết 2',
            'upper_final': 'Chung kết Nhánh thắng',
            'lower_round1': 'Vòng 1 Nhánh thua',
            'lower_final': 'Chung kết Nhánh thua',
        }
        name = labels.get(sval, sval)
        if stype == 'winner_of':
            return f"Thắng {name}"
        if stype == 'loser_of':
            return f"Thua {name}"
        return "TBD"

    for m in major_data.get('playoff_matches', []):
        if m['status'] == 'pending':
            src_a = m['sources']['team_a']
            src_b = m['sources']['team_b']
            t_a = resolve_source(src_a)
            t_b = resolve_source(src_b)

            if t_a:
                m['team_a'] = t_a
                m['team_a_id'] = t_a['id']
                m['placeholder_a'] = None
            else:
                m['team_a'] = None
                m['team_a_id'] = None
                m['placeholder_a'] = get_source_label(src_a)

            if t_b:
                m['team_b'] = t_b
                m['team_b_id'] = t_b['id']
                m['placeholder_b'] = None
            else:
                m['team_b'] = None
                m['team_b_id'] = None
                m['placeholder_b'] = get_source_label(src_b)


def advance_major_state(major_data: Dict[str, Any]) -> bool:
    """Advance the tournament state for VCT Major."""
    teams = major_data['teams']
    swiss_matches = major_data.get('swiss_matches', [])
    completed_swiss = [m for m in swiss_matches if m['status'] == 'completed']

    # Update Swiss standings
    major_data['swiss_standings'] = get_swiss_standings(teams, completed_swiss)

    if major_data['current_stage'] == 'swiss':
        current_r = major_data['current_swiss_round']
        current_r_matches = [m for m in swiss_matches if m['round'] == current_r]

        if current_r_matches and all(m['status'] == 'completed' for m in current_r_matches):
            advancing = [s['team'] for s in major_data['swiss_standings'] if s['advanced']]
            eliminated = [s['team'] for s in major_data['swiss_standings'] if s['eliminated']]

            if len(advancing) == 4 and len(eliminated) == 4:
                major_data['current_stage'] = 'playoffs'
                major_data['swiss_qualifiers'] = advancing
                major_data['swiss_eliminated'] = eliminated
                _init_major_playoffs(major_data)
            elif current_r < 3:
                next_r = current_r + 1
                existing_next = [m for m in swiss_matches if m['round'] == next_r]
                if not existing_next:
                    pairs = generate_swiss_pairings(teams, next_r, completed_swiss)
                    for idx, (t_a, t_b) in enumerate(pairs):
                        r_name = f'swiss_r{next_r}_m{idx + 1}'
                        swiss_matches.append({
                            'id': f"major_{r_name}",
                            'round': next_r,
                            'round_name': r_name,
                            'label': f'Swiss Vòng {next_r} - Trận {idx + 1}',
                            'bo': 3,
                            'status': 'pending',
                            'team_a': t_a,
                            'team_b': t_b,
                            'team_a_id': t_a['id'],
                            'team_b_id': t_b['id'],
                            'team_a_score': 0,
                            'team_b_score': 0,
                            'winner_id': None,
                            'loser_id': None,
                            'winner': None,
                            'loser': None,
                            'maps': [],
                            'is_manual': False,
                        })
                    major_data['current_swiss_round'] = next_r

    elif major_data['current_stage'] == 'playoffs':
        _resolve_major_playoff_slots(major_data)

    playoffs = major_data.get('playoff_matches', [])
    if playoffs and all(m['status'] == 'completed' for m in playoffs):
        completed_playoffs = {m['round_name']: m for m in playoffs}
        major_data['completed_playoffs'] = completed_playoffs
        gf = completed_playoffs['grand_final']
        lb_final = completed_playoffs['lower_final']
        lb_r1 = completed_playoffs['lower_round1']

        champion = gf['winner']
        runner_up = gf['loser']
        third_place = lb_final['loser']
        fourth_place = lb_r1['loser']
        eliminated = major_data.get('swiss_eliminated', [])

        standings = [
            {
                'rank': 1, 'team': champion, 'club_id': champion['id'],
                'title': 'Vô địch VCT Major (Masters Bangkok)',
                'championship_points': get_stage_points('major', rank=1),  # 5 CP
            },
            {
                'rank': 2, 'team': runner_up, 'club_id': runner_up['id'],
                'title': 'Á quân VCT Major',
                'championship_points': get_stage_points('major', rank=2),  # 3 CP
            },
            {
                'rank': 3, 'team': third_place, 'club_id': third_place['id'],
                'title': 'Hạng 3 (Thua Chung kết Nhánh thua)',
                'championship_points': get_stage_points('major', rank=3),  # 2 CP
            },
            {
                'rank': 4, 'team': fourth_place, 'club_id': fourth_place['id'],
                'title': 'Hạng 4 (Thua Vòng 1 Nhánh thua)',
                'championship_points': get_stage_points('major', rank=4),  # 1 CP
            },
        ]

        for elim_team in eliminated:
            standings.append({
                'rank': 5, 'team': elim_team, 'club_id': elim_team['id'],
                'title': 'Bị loại ở Vòng Thụy Sĩ (Swiss Stage)',
                'championship_points': 0,
            })

        major_data['champion'] = champion
        major_data['runner_up'] = runner_up
        major_data['standings'] = standings
        major_data['status'] = 'completed'
        major_data['total_matches_count'] = len(swiss_matches) + len(playoffs)
        return True

    return False


def resolve_major_match(major_data: Dict[str, Any], match_id_or_round_name: str,
                        winner_id: Optional[int] = None,
                        maps: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Resolve an interactive Major match with manual input or single simulation roll."""
    all_matches = major_data.get('swiss_matches', []) + major_data.get('playoff_matches', [])
    match_obj = None
    for m in all_matches:
        if m['id'] == match_id_or_round_name or m['round_name'] == match_id_or_round_name:
            match_obj = m
            break

    if not match_obj:
        raise ValueError(f"Match {match_id_or_round_name} not found in Major")

    if not match_obj.get('team_a') or not match_obj.get('team_b'):
        raise ValueError(f"Match {match_obj['round_name']} does not have both teams determined yet")

    if major_data.get('status') == 'completed':
        raise ValueError("Không thể chỉnh sửa trận đấu vì giải đấu Major đã hoàn thành!")

    # Safeguard against invalid mid-tournament edits:
    if match_obj.get('status') == 'completed':
        if 'round' in match_obj:  # Swiss stage
            if major_data.get('current_stage') == 'playoffs':
                if any(m.get('status') == 'completed' for m in major_data.get('playoff_matches', [])):
                    raise ValueError("Không thể sửa trận Swiss này vì giai đoạn Playoffs đã có trận hoàn thành!")
                major_data['current_stage'] = 'swiss'
                major_data['playoff_matches'] = []
                major_data['swiss_qualifiers'] = []
                major_data['swiss_eliminated'] = []

            current_r = match_obj['round']
            later_matches = [m for m in major_data.get('swiss_matches', []) if m.get('round', 1) > current_r]
            if any(m.get('status') == 'completed' for m in later_matches):
                raise ValueError(f"Không thể sửa trận Swiss Vòng {current_r} vì các vòng sau đã diễn ra!")
            if later_matches:
                major_data['swiss_matches'] = [m for m in major_data['swiss_matches'] if m.get('round', 1) <= current_r]
                major_data['current_swiss_round'] = current_r

        else:  # Playoff stage
            r_name = match_obj['round_name']
            playoffs = major_data.get('playoff_matches', [])
            downstream = [
                m for m in playoffs
                if (m.get('sources', {}).get('team_a', {}).get('value') == r_name or
                    m.get('sources', {}).get('team_b', {}).get('value') == r_name)
            ]
            if any(m.get('status') == 'completed' for m in downstream):
                raise ValueError("Không thể sửa trận đấu này vì trận đấu nhánh tiếp theo đã hoàn thành!")

    t_a = match_obj['team_a']
    t_b = match_obj['team_b']
    id_a = t_a['id']
    id_b = t_b['id']
    bo = match_obj.get('bo', 3)
    target_wins = 3 if bo == 5 else 2

    r_a = t_a.get('story_rating') or t_a.get('current_rating') or t_a.get('rating') or 80
    r_b = t_b.get('story_rating') or t_b.get('current_rating') or t_b.get('rating') or 80

    if winner_id is not None:
        if winner_id not in (id_a, id_b):
            raise ValueError(f"winner_id {winner_id} is neither team A ({id_a}) nor team B ({id_b})")

        winner = t_a if winner_id == id_a else t_b
        loser = t_b if winner == t_a else t_a

        if maps:
            wins_a = sum(1 for m_item in maps if m_item['team_a_score'] > m_item['team_b_score'])
            wins_b = sum(1 for m_item in maps if m_item['team_b_score'] > m_item['team_a_score'])
            resolved_maps = maps
        else:
            wins_a = target_wins if winner == t_a else 1
            wins_b = target_wins if winner == t_b else 1
            resolved_maps = []
            for i in range(target_wins):
                sc_w, sc_l = _gen_map_score(r_a if winner == t_a else r_b, r_b if winner == t_a else r_a, is_bo5=(bo == 5))
                resolved_maps.append({
                    'map_number': i + 1,
                    'team_a_score': sc_w if winner == t_a else sc_l,
                    'team_b_score': sc_l if winner == t_a else sc_w,
                    'winner_id': winner_id,
                })

        match_obj.update({
            'status': 'completed',
            'team_a_score': wins_a,
            'team_b_score': wins_b,
            'winner_id': winner_id,
            'loser_id': loser['id'],
            'winner': winner,
            'loser': loser,
            'maps': resolved_maps,
            'is_manual': True,
        })
    else:
        is_gf = (match_obj.get('round_name') == 'grand_final')
        is_playoff = (major_data.get('current_stage') == 'playoffs' or 'round' not in match_obj)
        all_completed = [m for m in all_matches if m.get('status') == 'completed' and m.get('id') != match_obj.get('id')]
        prior_a = sum(1 for m in all_completed if m.get('team_a_id') == id_a or m.get('team_b_id') == id_a)
        prior_b = sum(1 for m in all_completed if m.get('team_a_id') == id_b or m.get('team_b_id') == id_b)

        sim = simulate_major_single_match(
            t_a, t_b,
            bo=bo,
            is_grand_final=is_gf,
            is_playoff=is_playoff,
            prior_a=prior_a,
            prior_b=prior_b,
        )
        match_obj.update({
            'status': 'completed',
            'team_a_score': sim['team_a_score'],
            'team_b_score': sim['team_b_score'],
            'winner_id': sim['winner_id'],
            'loser_id': sim['loser_id'],
            'winner': sim['winner'],
            'loser': sim['loser'],
            'maps': sim['maps'],
            'is_manual': False,
        })

    advance_major_state(major_data)
    return match_obj


def sim_major_round(major_data: Dict[str, Any]) -> int:
    """Simulate all currently playable pending matches in the active round/wave."""
    playable = []
    if major_data['current_stage'] == 'swiss':
        current_r = major_data['current_swiss_round']
        playable = [m for m in major_data['swiss_matches'] if m['round'] == current_r and m['status'] == 'pending']
    elif major_data['current_stage'] == 'playoffs':
        playable = [m for m in major_data['playoff_matches'] if m['status'] == 'pending' and m.get('team_a') and m.get('team_b')]

    count = 0
    for m in playable:
        resolve_major_match(major_data, m['round_name'], winner_id=None)
        count += 1

    return count


def sim_major_remaining(major_data: Dict[str, Any]) -> int:
    """Simulate all remaining matches until Grand Final finishes."""
    total = 0
    max_loops = 50
    loop_idx = 0
    while major_data.get('status') != 'completed' and loop_idx < max_loops:
        c = sim_major_round(major_data)
        if c == 0:
            break
        total += c
        loop_idx += 1
    return total


def simulate_major_tournament(teams: List[Dict[str, Any]],
                              manual_overrides: Optional[Dict[str, Any]] = None,
                              previous_result: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Execute complete VCT Major (Masters Bangkok) tournament."""
    state = init_major_state(teams)
    overrides = manual_overrides or {}

    has_swiss_override = any(k.startswith('swiss_') for k in overrides.keys())
    if previous_result and not has_swiss_override and previous_result.get('swiss_matches'):
        state['swiss_matches'] = [dict(m) for m in previous_result['swiss_matches']]
        state['current_swiss_round'] = 3
        advance_major_state(state)

    prev_playoffs = previous_result.get('completed_playoffs', {}) if previous_result else {}

    max_loops = 50
    loop_idx = 0
    while state.get('status') != 'completed' and loop_idx < max_loops:
        playable = []
        if state['current_stage'] == 'swiss':
            current_r = state['current_swiss_round']
            playable = [m for m in state['swiss_matches'] if m['round'] == current_r and m['status'] == 'pending']
        elif state['current_stage'] == 'playoffs':
            playable = [m for m in state['playoff_matches'] if m['status'] == 'pending' and m.get('team_a') and m.get('team_b')]

        if not playable:
            break

        for m in playable:
            r_name = m['round_name']
            if r_name in overrides:
                ov = overrides[r_name]
                resolve_major_match(state, r_name, winner_id=ov.get('winner_id'), maps=ov.get('maps'))
            elif r_name in prev_playoffs and prev_playoffs[r_name].get('winner_id') in (m['team_a_id'], m['team_b_id']):
                prev_w = prev_playoffs[r_name]['winner_id']
                prev_maps = prev_playoffs[r_name].get('maps')
                resolve_major_match(state, r_name, winner_id=prev_w, maps=prev_maps)
            else:
                resolve_major_match(state, r_name, winner_id=None)
        loop_idx += 1

    return state
