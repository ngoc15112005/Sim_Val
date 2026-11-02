"""engine/format/master_sim.py — VCT Masters (Masters Toronto) Pure Simulation Engine

Specifications:
- 12 World Elite Teams:
  * 4 Direct Qualifiers (Stage 1 Champions of Pacific, Americas, EMEA, China - Seed 1)
  * 8 Swiss Qualifiers (Stage 1 Runners-up & 3rd Place of each region - Seed 2 & 3)
- Stage 1: Swiss Stage (8 teams, 2 wins advance / 2 losses eliminated, max 3 rounds, 10 matches)
  * Round 1: 4 matches (BO3) — Cross-region pairing (Seed 2 vs Seed 3 across different regions)
  * Round 2: 4 matches (BO3) — 1-0 vs 1-0 (2 matches), 0-1 vs 0-1 (2 matches)
  * Round 3: 2 matches (BO3) — 1-1 vs 1-1 (2 matches)
  * Advancing: 4 teams (2 at 2-0, 2 at 2-1)
  * Eliminated: 4 teams (2 at 0-2, 2 at 1-2)
- Stage 2: Playoffs (8 teams Double Elimination, 14 matches)
  * 4 Direct Qualifiers + 4 Swiss Qualifiers
  * Upper Quarterfinals: 4 matches (Direct vs Swiss)
  * Upper Semifinals: 2 matches
  * Upper Final: 1 match
  * Lower Round 1: 2 matches
  * Lower Quarterfinals: 2 matches (Cross-mapping: loser US2 to LR1_1, loser US1 to LR1_2)
  * Lower Semifinal: 1 match
  * Lower Final: 1 match (BO5)
  * Grand Final: 1 match (BO5)
- Championship Points:
  * 1st: 7 CP (Masters Toronto Champion)
  * 2nd: 5 CP (Masters Toronto Runner-up)
  * 3rd: 4 CP
  * 4th: 3 CP
  * 5th-6th: 2 CP each
  * 7th-8th: 0 CP
  * 9th-12th: 0 CP
"""

import random
from typing import List, Dict, Optional, Any, Tuple
from engine.format.master import (
    generate_master_swiss_r1,
    generate_swiss_pairings,
    get_swiss_standings,
    generate_master_playoffs,
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
    - Base probability 0.50 (Rating is NOT added to win probability).
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
        tour_type='master',
        is_grand_final=is_grand_final,
        is_playoff=is_playoff,
        seed_a=seed_a,
        seed_b=seed_b,
        prior_a=prior_a,
        prior_b=prior_b,
        streak_a=streak_a,
        streak_b=streak_b,
    )


def simulate_master_single_match(team_a: Dict[str, Any], team_b: Dict[str, Any], bo: int = 3,
                                 is_grand_final: bool = False,
                                 is_playoff: bool = False,
                                 prior_a: int = 0, prior_b: int = 0,
                                 streak_a: int = 0, streak_b: int = 0,
                                 manual_override: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Simulate a single Masters Toronto match or apply manual override."""
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


def _get_playoff_label(round_name: str) -> str:
    labels = {
        'upper_quarterfinal_1': 'Tứ kết Nhánh thắng 1',
        'upper_quarterfinal_2': 'Tứ kết Nhánh thắng 2',
        'upper_quarterfinal_3': 'Tứ kết Nhánh thắng 3',
        'upper_quarterfinal_4': 'Tứ kết Nhánh thắng 4',
        'upper_semifinal_1': 'Bán kết Nhánh thắng 1',
        'upper_semifinal_2': 'Bán kết Nhánh thắng 2',
        'upper_final': 'Chung kết Nhánh thắng',
        'lower_round1_1': 'Vòng 1 Nhánh thua - Trận 1',
        'lower_round1_2': 'Vòng 1 Nhánh thua - Trận 2',
        'lower_quarterfinal_1': 'Tứ kết Nhánh thua 1',
        'lower_quarterfinal_2': 'Tứ kết Nhánh thua 2',
        'lower_semifinal': 'Bán kết Nhánh thua',
        'lower_final': 'Chung kết Nhánh thua (BO5)',
        'grand_final': 'Tổng Chung kết Masters Toronto (BO5)',
    }
    return labels.get(round_name, round_name.replace('_', ' ').title())


def init_master_state(teams: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Initialize interactive state for VCT Masters (Masters Toronto) 12 teams."""
    if len(teams) != 12:
        raise ValueError(f"Masters Toronto requires exactly 12 teams, received {len(teams)}")

    normalized_teams = []
    for t in teams:
        norm_t = dict(t)
        norm_t['id'] = norm_t.get('id') or norm_t.get('club_id')
        norm_t['club_id'] = norm_t['id']
        if 'region' not in norm_t and 'region_slug' in norm_t:
            norm_t['region'] = norm_t['region_slug']
        norm_t.setdefault('regional_seed', 1)
        normalized_teams.append(norm_t)

    # 4 Direct seeds: regional_seed == 1
    pool_high = [t for t in normalized_teams if t.get('regional_seed') == 1]
    # 8 Swiss teams: regional_seed in (2, 3)
    pool_swiss = [t for t in normalized_teams if t.get('regional_seed') in (2, 3)]

    if len(pool_high) != 4 or len(pool_swiss) != 8:
        # Fallback if regional seeds are not strictly 1 vs 2/3
        pool_high = normalized_teams[:4]
        pool_swiss = normalized_teams[4:]

    # Swiss Round 1 Pairings (seed 2 vs seed 3, cross-region)
    r1_pairs = generate_master_swiss_r1(pool_swiss)
    swiss_matches = []
    for idx, (t_a, t_b) in enumerate(r1_pairs):
        r_name = f'swiss_r1_m{idx + 1}'
        swiss_matches.append({
            'id': f"master_{r_name}",
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

    standings = get_swiss_standings(pool_swiss, [])

    return {
        'tournament_name': 'VCT Masters (Masters Toronto)',
        'status': 'in_progress',          # 'in_progress' or 'completed'
        'current_stage': 'swiss',          # 'swiss' or 'playoffs'
        'current_swiss_round': 1,         # 1..3
        'teams': normalized_teams,
        'direct_teams': pool_high,
        'swiss_teams': pool_swiss,
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


def _init_master_playoffs(master_data: Dict[str, Any]):
    """Initialize the 8-team Double Elimination playoff bracket after Swiss finishes."""
    pool_high = master_data.get('direct_teams', [])
    swiss_qualifiers = master_data.get('swiss_qualifiers', [])

    if len(pool_high) != 4 or len(swiss_qualifiers) != 4:
        raise ValueError("Playoffs require 4 direct teams and 4 Swiss qualifiers.")

    # Assign bracket seeds: 1-4 for direct teams, 5-8 for swiss qualifiers
    for idx, t in enumerate(pool_high):
        t['bracket_seed'] = idx + 1
    for idx, t in enumerate(swiss_qualifiers):
        t['bracket_seed'] = idx + 5

    templates = generate_master_playoffs(pool_high, swiss_qualifiers)
    playoff_matches = []

    for tpl in templates:
        r_name = tpl['round_name']
        bo = 5 if r_name in ('lower_final', 'grand_final') else 3
        team_a = tpl.get('high_team')
        team_b = tpl.get('low_team')

        playoff_matches.append({
            'id': f"master_{r_name}",
            'round_name': r_name,
            'round_type': tpl.get('round_type', 'upper'),
            'label': _get_playoff_label(r_name),
            'bo': bo,
            'status': 'pending',
            'sources': tpl.get('sources', {}),
            'team_a': team_a,
            'team_b': team_b,
            'team_a_id': team_a['id'] if team_a else None,
            'team_b_id': team_b['id'] if team_b else None,
            'team_a_score': 0,
            'team_b_score': 0,
            'winner_id': None,
            'loser_id': None,
            'winner': None,
            'loser': None,
            'maps': [],
            'is_manual': False,
        })

    master_data['playoff_matches'] = playoff_matches
    master_data['current_stage'] = 'playoffs'
    _resolve_master_playoff_slots(master_data)


def _resolve_master_playoff_slots(master_data: Dict[str, Any]):
    """Resolve dynamic team sources for all playoff matches."""
    team_lookup = {t['id']: t for t in master_data.get('teams', [])}
    completed_matches = master_data.get('completed_playoffs', {})

    def resolve_source(src):
        if not src:
            return None
        stype = src.get('type')
        sval = src.get('value')
        if stype == 'winner_of':
            target = completed_matches.get(sval)
            if target and target.get('status') == 'completed':
                return team_lookup.get(target.get('winner_id'))
        elif stype == 'loser_of':
            target = completed_matches.get(sval)
            if target and target.get('status') == 'completed':
                return team_lookup.get(target.get('loser_id'))
        return None

    def get_source_label(src):
        if not src:
            return 'TBD'
        stype = src.get('type')
        sval = src.get('value')
        if stype == 'winner_of':
            return f"Thắng {_get_playoff_label(sval)}"
        elif stype == 'loser_of':
            return f"Thua {_get_playoff_label(sval)}"
        return 'TBD'

    for m in master_data.get('playoff_matches', []):
        if m.get('round_name', '').startswith('upper_quarterfinal_'):
            continue

        src_a = m.get('sources', {}).get('team_a')
        src_b = m.get('sources', {}).get('team_b')

        exp_a = resolve_source(src_a)
        exp_b = resolve_source(src_b)

        cur_a_id = m.get('team_a_id')
        cur_b_id = m.get('team_b_id')
        exp_a_id = exp_a['id'] if exp_a else None
        exp_b_id = exp_b['id'] if exp_b else None

        if cur_a_id != exp_a_id or cur_b_id != exp_b_id:
            m['team_a'] = exp_a
            m['team_b'] = exp_b
            m['team_a_id'] = exp_a_id
            m['team_b_id'] = exp_b_id
            m['team_a_source_label'] = get_source_label(src_a)
            m['team_b_source_label'] = get_source_label(src_b)

            if m.get('status') == 'completed':
                m['status'] = 'pending'
                m['winner_id'] = None
                m['loser_id'] = None
                m['winner'] = None
                m['loser'] = None
                m['team_a_score'] = 0
                m['team_b_score'] = 0
                m['maps'] = []
                m['is_manual'] = False
                completed_matches.pop(m['round_name'], None)


def advance_master_state(master_data: Dict[str, Any]) -> bool:
    """Advance Masters Toronto state after a match completes."""
    team_lookup = {t['id']: t for t in master_data.get('teams', [])}

    # 1. In Swiss stage
    if master_data.get('current_stage') == 'swiss':
        swiss_matches = master_data.get('swiss_matches', [])
        completed_swiss = [m for m in swiss_matches if m.get('status') == 'completed']

        # Update standings
        standings = get_swiss_standings(master_data['swiss_teams'], completed_swiss)
        master_data['swiss_standings'] = standings

        qualifiers = [s['team'] for s in standings if s.get('advanced') or s.get('qualified')]
        eliminated = [s['team'] for s in standings if s.get('eliminated')]
        master_data['swiss_qualifiers'] = qualifiers
        master_data['swiss_eliminated'] = eliminated

        cur_round = master_data.get('current_swiss_round', 1)
        cur_round_matches = [m for m in swiss_matches if m.get('round') == cur_round]

        if cur_round_matches and all(m.get('status') == 'completed' for m in cur_round_matches):
            if len(qualifiers) == 4 and len(eliminated) == 4:
                # Swiss complete -> initialize Playoffs
                _init_master_playoffs(master_data)
                return True
            elif cur_round < 3:
                next_round = cur_round + 1
                master_data['current_swiss_round'] = next_round
                next_pairs = generate_swiss_pairings(master_data['swiss_teams'], next_round, completed_swiss)

                for idx, (t_a, t_b) in enumerate(next_pairs):
                    r_name = f'swiss_r{next_round}_m{idx + 1}'
                    swiss_matches.append({
                        'id': f"master_{r_name}",
                        'round': next_round,
                        'round_name': r_name,
                        'label': f'Swiss Vòng {next_round} - Trận {idx + 1}',
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
                return True
        return False

    # 2. In Playoffs stage
    if master_data.get('current_stage') == 'playoffs':
        _resolve_master_playoff_slots(master_data)
        completed_matches = master_data.get('completed_playoffs', {})
        gf = completed_matches.get('grand_final')

        if gf and gf.get('status') == 'completed':
            champ = team_lookup.get(gf['winner_id'])
            runner = team_lookup.get(gf['loser_id'])
            lf = completed_matches.get('lower_final')
            third = team_lookup.get(lf['loser_id']) if lf else None
            lsf = completed_matches.get('lower_semifinal')
            fourth = team_lookup.get(lsf['loser_id']) if lsf else None
            lqf1 = completed_matches.get('lower_quarterfinal_1')
            lqf2 = completed_matches.get('lower_quarterfinal_2')
            fifth_a = team_lookup.get(lqf1['loser_id']) if lqf1 else None
            fifth_b = team_lookup.get(lqf2['loser_id']) if lqf2 else None
            lr1_1 = completed_matches.get('lower_round1_1')
            lr1_2 = completed_matches.get('lower_round1_2')
            seventh_a = team_lookup.get(lr1_1['loser_id']) if lr1_1 else None
            seventh_b = team_lookup.get(lr1_2['loser_id']) if lr1_2 else None

            master_data['champion'] = champ
            master_data['runner_up'] = runner

            final_standings = [
                {'rank': 1, 'team': champ, 'club_id': champ.get('id') if champ else None, 'cp': get_stage_points('master', rank=1), 'championship_points': get_stage_points('master', rank=1), 'desc': 'Quán quân VCT Masters Toronto (Cúp Vô Địch)'},
                {'rank': 2, 'team': runner, 'club_id': runner.get('id') if runner else None, 'cp': get_stage_points('master', rank=2), 'championship_points': get_stage_points('master', rank=2), 'desc': 'Á quân VCT Masters Toronto'},
                {'rank': 3, 'team': third, 'club_id': third.get('id') if third else None, 'cp': get_stage_points('master', rank=3), 'championship_points': get_stage_points('master', rank=3), 'desc': 'Hạng 3 VCT Masters Toronto'},
                {'rank': 4, 'team': fourth, 'club_id': fourth.get('id') if fourth else None, 'cp': get_stage_points('master', rank=4), 'championship_points': get_stage_points('master', rank=4), 'desc': 'Hạng 4 VCT Masters Toronto'},
                {'rank': 5, 'team': fifth_a, 'club_id': fifth_a.get('id') if fifth_a else None, 'cp': get_stage_points('master', rank=5), 'championship_points': get_stage_points('master', rank=5), 'desc': 'Hạng 5-6 VCT Masters Toronto'},
                {'rank': 6, 'team': fifth_b, 'club_id': fifth_b.get('id') if fifth_b else None, 'cp': get_stage_points('master', rank=6), 'championship_points': get_stage_points('master', rank=6), 'desc': 'Hạng 5-6 VCT Masters Toronto'},
                {'rank': 7, 'team': seventh_a, 'club_id': seventh_a.get('id') if seventh_a else None, 'cp': 0, 'championship_points': 0, 'desc': 'Hạng 7-8 VCT Masters Toronto'},
                {'rank': 8, 'team': seventh_b, 'club_id': seventh_b.get('id') if seventh_b else None, 'cp': 0, 'championship_points': 0, 'desc': 'Hạng 7-8 VCT Masters Toronto'},
            ]

            for idx, el in enumerate(master_data.get('swiss_eliminated', [])):
                final_standings.append({
                    'rank': 9 + idx,
                    'team': el,
                    'club_id': el.get('id') if el else None,
                    'cp': 0,
                    'championship_points': 0,
                    'desc': 'Bị loại ở Vòng Thụy Sĩ',
                })

            master_data['matches_completed'] = True
            master_data['standings'] = final_standings
            master_data['status'] = 'completed'
            return True

    return False


def resolve_master_match(master_data: Dict[str, Any], match_id_or_round_name: str,
                         winner_id: Optional[int] = None,
                         maps: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Resolve a match in Masters Toronto (Roll or Manual Score)."""
    target = None
    all_matches = master_data.get('swiss_matches', []) + master_data.get('playoff_matches', [])
    for m in all_matches:
        if m.get('id') == match_id_or_round_name or m.get('round_name') == match_id_or_round_name:
            target = m
            break

    if not target:
        raise ValueError(f"Match {match_id_or_round_name} not found in Masters Toronto")

    if master_data.get('is_confirmed'):
        raise ValueError("Không thể chỉnh sửa trận đấu vì giải đấu Masters Toronto đã được xác nhận và khóa chính thức!")

    if not target.get('team_a') or not target.get('team_b'):
        raise ValueError("Match participants are not fully determined yet.")

    override = None
    if winner_id is not None:
        override = {'winner_id': winner_id, 'maps': maps or []}

    is_gf = (target.get('round_name') == 'grand_final')
    is_playoff = ('sources' in target or master_data.get('current_stage') == 'playoffs')
    bo = target.get('bo', 3)

    all_completed = [m for m in all_matches if m.get('status') == 'completed' and m.get('id') != target.get('id')]
    id_a = target['team_a']['id'] if 'id' in target['team_a'] else target['team_a'].get('club_id')
    id_b = target['team_b']['id'] if 'id' in target['team_b'] else target['team_b'].get('club_id')
    prior_a = sum(1 for m in all_completed if m.get('team_a_id') == id_a or m.get('team_b_id') == id_a)
    prior_b = sum(1 for m in all_completed if m.get('team_a_id') == id_b or m.get('team_b_id') == id_b)

    res = simulate_master_single_match(
        target['team_a'], target['team_b'],
        bo=bo,
        is_grand_final=is_gf,
        is_playoff=is_playoff,
        prior_a=prior_a,
        prior_b=prior_b,
        manual_override=override
    )

    target['status'] = 'completed'
    target['team_a_score'] = res['team_a_score']
    target['team_b_score'] = res['team_b_score']
    target['winner_id'] = res['winner_id']
    target['loser_id'] = res['loser_id']
    target['winner'] = res['winner']
    target['loser'] = res['loser']
    target['maps'] = res['maps']
    target['is_manual'] = res['is_manual']

    if 'sources' in target:
        master_data.setdefault('completed_playoffs', {})[target['round_name']] = target

    master_data['total_matches_count'] = master_data.get('total_matches_count', 0) + 1
    advance_master_state(master_data)
    return target


def sim_master_round(master_data: Dict[str, Any]) -> int:
    """Simulate current active round/wave in Masters Toronto."""
    if master_data.get('status') == 'completed':
        return 0

    stage = master_data.get('current_stage')
    simmed = 0

    if stage == 'swiss':
        cur_round = master_data.get('current_swiss_round', 1)
        pending = [
            m for m in master_data.get('swiss_matches', [])
            if m.get('round') == cur_round and m.get('status') == 'pending'
        ]
        for m in pending:
            resolve_master_match(master_data, m['id'])
            simmed += 1
        return simmed

    elif stage == 'playoffs':
        _resolve_master_playoff_slots(master_data)
        playable = [
            m for m in master_data.get('playoff_matches', [])
            if m.get('status') == 'pending' and m.get('team_a') and m.get('team_b')
        ]
        for m in playable:
            resolve_master_match(master_data, m['id'])
            simmed += 1
        return simmed

    return 0


def sim_master_remaining(master_data: Dict[str, Any]) -> int:
    """Simulate all remaining matches in Masters Toronto until complete."""
    total = 0
    max_loops = 50
    loops = 0
    while master_data.get('status') != 'completed' and loops < max_loops:
        loops += 1
        count = sim_master_round(master_data)
        if count == 0:
            break
        total += count
    return total


def simulate_master_tournament(teams: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Execute complete automated simulation of Masters Toronto."""
    state = init_master_state(teams)
    sim_master_remaining(state)
    return state
