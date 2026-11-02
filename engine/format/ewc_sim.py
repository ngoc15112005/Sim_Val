"""engine/format/ewc_sim.py — Esports World Cup (EWC) Simulation Engine for Campaign Mode

Specifications:
- 16 World Elite Teams (4 Pacific, 4 Americas, 4 EMEA, 4 China):
  * Pool 1: 4 Stage 1 Champions
  * Pool 2: 4 Stage 1 Runners-up
  * Pool 3: 4 EWC Regional Qualifier Champions
  * Pool 4: 4 EWC Regional Qualifier Runners-up
- Stage 1: Group Stage (4 Groups of 4 teams, GSL Format, 5 BO3 matches per group = 20 matches)
  * Opening 1: Pool 1 vs Pool 4
  * Opening 2: Pool 2 vs Pool 3
  * Winners Match: Winner O1 vs Winner O2 -> Winner qualifies as #1 seed
  * Elimination Match: Loser O1 vs Loser O2 -> Loser eliminated
  * Decider Match: Loser Winners vs Winner Elimination -> Winner qualifies as #2 seed, Loser eliminated
- Stage 2: Playoffs (8 teams Single Elimination, 8 matches)
  * 4 Quarterfinals (BO3): #1 seed vs #2 seed (constraint: cannot face team from same group, opposite halves)
  * 2 Semifinals (BO3)
  * 1 Third Place Match (BO3)
  * 1 Grand Final (BO5)
- Total EWC matches: 20 (Groups) + 8 (Playoffs) = 28 matches.
- Championship Points: 0 CP (EWC does not award VCT Championship Points per official Riot 2025 rules).
- Story Rewards: Champion (+5 story rating), Runner-up (+3), 3rd Place (+2), 4th Place (+1).
"""

import random
from typing import List, Dict, Optional, Any, Tuple
from engine.format.ewc import (
    generate_gsl_groups,
    get_gsl_matches,
    generate_ewc_playoffs_draw,
    resolve_gs_slot,
)
from engine.match import _calc_region_bonus, _gen_map_score, calc_pure_international_win_rate


def _calc_ewc_win_rate(team_a: Dict[str, Any], team_b: Dict[str, Any],
                       is_grand_final: bool = False,
                       is_playoff: bool = False,
                       streak_a: int = 0, streak_b: int = 0,
                       prior_a: int = 0, prior_b: int = 0) -> float:
    """Calculate win probability for an international match in EWC.
    
    Philosophy ('Cỏ lúa bằng nhau'):
    - Base probability is 0.50 (Rating is NOT added to win probability).
    - Regional Meta DNA applies across different regions.
    - Seed 1 Curse: -4% cold start for direct playoff seeds.
    - Warm-up / Match Rhythm: +3% for battle-tested teams.
    - Momentum streak bonus.
    """
    reg_a = team_a.get('region_slug') or team_a.get('region')
    reg_b = team_b.get('region_slug') or team_b.get('region')
    seed_a = team_a.get('seed') or team_a.get('regional_seed') or 2
    seed_b = team_b.get('seed') or team_b.get('regional_seed') or 2

    return calc_pure_international_win_rate(
        region_a=reg_a,
        region_b=reg_b,
        tour_type='ewc',
        is_grand_final=is_grand_final,
        is_playoff=is_playoff,
        seed_a=seed_a,
        seed_b=seed_b,
        prior_a=prior_a,
        prior_b=prior_b,
        streak_a=streak_a,
        streak_b=streak_b,
    )


def simulate_ewc_single_match(team_a: Dict[str, Any], team_b: Dict[str, Any], bo: int = 3,
                              is_grand_final: bool = False,
                              is_playoff: bool = False,
                              prior_a: int = 0, prior_b: int = 0,
                              streak_a: int = 0, streak_b: int = 0,
                              manual_override: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Simulate a single EWC match or apply manual override."""
    id_a = team_a['id'] if 'id' in team_a else team_a.get('club_id')
    id_b = team_b['id'] if 'id' in team_b else team_b.get('club_id')

    r_a = team_a.get('story_rating') or team_a.get('current_rating') or team_a.get('rating') or 80
    r_b = team_b.get('story_rating') or team_b.get('current_rating') or team_b.get('rating') or 80

    target_wins = 3 if bo == 5 else 2

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

        wins_a = target_wins if winner == team_a else max(0, target_wins - 2)
        wins_b = target_wins if winner == team_b else max(0, target_wins - 2)
        simulated_maps = []
        map_idx = 1
        for _ in range(wins_a):
            sa, sb = _gen_map_score(r_a, r_b, is_bo5=(bo == 5))
            simulated_maps.append({'map_number': map_idx, 'team_a_score': sa, 'team_b_score': sb, 'winner_id': id_a})
            map_idx += 1
        for _ in range(wins_b):
            sb, sa = _gen_map_score(r_b, r_a, is_bo5=(bo == 5))
            simulated_maps.append({'map_number': map_idx, 'team_a_score': sa, 'team_b_score': sb, 'winner_id': id_b})
            map_idx += 1

        return {
            'team_a': team_a, 'team_b': team_b,
            'team_a_id': id_a, 'team_b_id': id_b,
            'team_a_score': wins_a, 'team_b_score': wins_b,
            'winner': winner, 'loser': loser,
            'winner_id': winner_id, 'loser_id': loser['id'] if 'id' in loser else loser.get('club_id'),
            'maps': simulated_maps,
            'bo': bo,
            'is_manual': True,
        }

    # Simulation roll
    prob_a = _calc_ewc_win_rate(
        team_a, team_b,
        is_grand_final=is_grand_final,
        is_playoff=is_playoff,
        streak_a=streak_a,
        streak_b=streak_b,
        prior_a=prior_a,
        prior_b=prior_b,
    )
    wins_a, wins_b = 0, 0
    maps = []
    map_idx = 1

    while wins_a < target_wins and wins_b < target_wins:
        a_wins_map = (random.random() < prob_a)
        if a_wins_map:
            wins_a += 1
            sa, sb = _gen_map_score(r_a, r_b, is_bo5=(bo == 5))
            w_id = id_a
        else:
            wins_b += 1
            sb, sa = _gen_map_score(r_b, r_a, is_bo5=(bo == 5))
            w_id = id_b

        maps.append({'map_number': map_idx, 'team_a_score': sa, 'team_b_score': sb, 'winner_id': w_id})
        map_idx += 1

    winner = team_a if wins_a > wins_b else team_b
    loser = team_b if winner == team_a else team_a

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
        'quarterfinal_1': 'Tứ kết 1',
        'quarterfinal_2': 'Tứ kết 2',
        'quarterfinal_3': 'Tứ kết 3',
        'quarterfinal_4': 'Tứ kết 4',
        'semifinal_1': 'Bán kết 1',
        'semifinal_2': 'Bán kết 2',
        'third_place_match': 'Tranh Hạng 3 EWC',
        'grand_final': 'Chung kết Tổng EWC (BO5)',
    }
    return labels.get(round_name, round_name.replace('_', ' ').title())


def init_ewc_state(teams: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Initialize interactive Esports World Cup (EWC) state.
    teams: 16 teams.
    - 4 Stage 1 Champions (Pool 1)
    - 4 Stage 1 Runners-up (Pool 2)
    - 4 EWC Qualifier Champions (Pool 3)
    - 4 EWC Qualifier Runners-up (Pool 4)
    """
    if len(teams) != 16:
        raise ValueError(f"EWC requires exactly 16 teams, got {len(teams)}")

    normalized_teams = []
    for t in teams:
        norm_t = dict(t)
        norm_t['id'] = norm_t.get('id') or norm_t.get('club_id')
        norm_t['club_id'] = norm_t['id']
        if 'region' not in norm_t and 'region_slug' in norm_t:
            norm_t['region'] = norm_t['region_slug']
        pool_num = norm_t.get('pool') or norm_t.get('regional_seed') or 1
        norm_t['regional_seed'] = pool_num
        norm_t['pool'] = pool_num
        normalized_teams.append(norm_t)

    # Generate 4 GSL groups (A, B, C, D)
    raw_groups = generate_gsl_groups(normalized_teams)
    groups_data = {}

    for label in ['A', 'B', 'C', 'D']:
        grp_teams = raw_groups.get(label, [])
        for t in grp_teams:
            t['group_label'] = label
            t['group'] = label

        sorted_grp = sorted(grp_teams, key=lambda x: x.get('regional_seed', 1))
        t1 = sorted_grp[0] if len(sorted_grp) > 0 else None
        t2 = sorted_grp[1] if len(sorted_grp) > 1 else None
        t3 = sorted_grp[2] if len(sorted_grp) > 2 else None
        t4 = sorted_grp[3] if len(sorted_grp) > 3 else None

        match_templates = get_gsl_matches(grp_teams, label)
        matches = {}
        for tpl in match_templates:
            r_name = tpl['round_name']
            if 'opening1' in r_name:
                team_a, team_b = t1, t4
            elif 'opening2' in r_name:
                team_a, team_b = t2, t3
            else:
                team_a = tpl.get('high_team')
                team_b = tpl.get('low_team')

            matches[r_name] = {
                'id': f"ewc_{r_name}",
                'group': label,
                'round_name': r_name,
                'label': _get_gsl_label(r_name, label),
                'bo': 3,
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
            }

        standings = [
            {'team': t, 'club_id': t['id'], 'wins': 0, 'losses': 0, 'map_diff': 0, 'status': 'pending'}
            for t in grp_teams
        ]

        groups_data[label] = {
            'label': label,
            'teams': grp_teams,
            'matches': matches,
            'standings': standings,
            'winner': None,
            'runner_up': None,
            'status': 'in_progress',
        }

    return {
        'tournament_name': 'Esports World Cup (EWC)',
        'status': 'in_progress',         # 'in_progress' or 'completed'
        'current_stage': 'groups',        # 'groups' or 'playoffs'
        'teams': normalized_teams,
        'groups': groups_data,
        'playoff_matches': [],
        'completed_playoffs': {},
        'group_qualifiers': {'winners': [], 'runners': []},
        'champion': None,
        'runner_up': None,
        'third_place': None,
        'fourth_place': None,
        'standings': [],
        'total_matches_count': 0,
    }


def _get_gsl_label(round_name: str, group_label: str) -> str:
    if 'opening1' in round_name:
        return f"Bảng {group_label} - Mở màn 1"
    if 'opening2' in round_name:
        return f"Bảng {group_label} - Mở màn 2"
    if 'winners_match' in round_name:
        return f"Bảng {group_label} - Nhánh Thắng (Tranh vé 1)"
    if 'elimination_match' in round_name:
        return f"Bảng {group_label} - Nhánh Thua (Trận sinh tử)"
    if 'decider_match' in round_name:
        return f"Bảng {group_label} - Quyết định (Tranh vé 2)"
    return f"Bảng {group_label} - {round_name}"


def _update_group_state(group_data: Dict[str, Any], team_lookup: Dict[int, Any]):
    """Update GSL match slots and standings for a group."""
    matches = group_data['matches']
    label = group_data['label']

    op1 = matches.get(f"group{label}_opening1")
    op2 = matches.get(f"group{label}_opening2")
    wm = matches.get(f"group{label}_winners_match")
    em = matches.get(f"group{label}_elimination_match")
    dm = matches.get(f"group{label}_decider_match")

    # 1. Resolve Winners Match (Winner OP1 vs Winner OP2)
    if op1 and op1.get('status') == 'completed' and op2 and op2.get('status') == 'completed':
        w_op1 = team_lookup.get(op1['winner_id'])
        w_op2 = team_lookup.get(op2['winner_id'])
        if wm['team_a_id'] != op1['winner_id'] or wm['team_b_id'] != op2['winner_id']:
            wm['team_a'] = w_op1
            wm['team_b'] = w_op2
            wm['team_a_id'] = op1['winner_id']
            wm['team_b_id'] = op2['winner_id']
            if wm.get('status') == 'completed':
                wm['status'] = 'pending'
                wm['winner_id'] = None
                wm['loser_id'] = None
                wm['winner'] = None
                wm['loser'] = None
                wm['team_a_score'] = 0
                wm['team_b_score'] = 0
                wm['maps'] = []
    else:
        wm['team_a'] = None
        wm['team_b'] = None
        wm['team_a_id'] = None
        wm['team_b_id'] = None
        wm['team_a_source_label'] = f"Thắng Mở màn 1"
        wm['team_b_source_label'] = f"Thắng Mở màn 2"

    # 2. Resolve Elimination Match (Loser OP1 vs Loser OP2)
    if op1 and op1.get('status') == 'completed' and op2 and op2.get('status') == 'completed':
        l_op1 = team_lookup.get(op1['loser_id'])
        l_op2 = team_lookup.get(op2['loser_id'])
        if em['team_a_id'] != op1['loser_id'] or em['team_b_id'] != op2['loser_id']:
            em['team_a'] = l_op1
            em['team_b'] = l_op2
            em['team_a_id'] = op1['loser_id']
            em['team_b_id'] = op2['loser_id']
            if em.get('status') == 'completed':
                em['status'] = 'pending'
                em['winner_id'] = None
                em['loser_id'] = None
                em['winner'] = None
                em['loser'] = None
                em['team_a_score'] = 0
                em['team_b_score'] = 0
                em['maps'] = []
    else:
        em['team_a'] = None
        em['team_b'] = None
        em['team_a_id'] = None
        em['team_b_id'] = None
        em['team_a_source_label'] = f"Thua Mở màn 1"
        em['team_b_source_label'] = f"Thua Mở màn 2"

    # 3. Resolve Decider Match (Loser WM vs Winner EM)
    if wm and wm.get('status') == 'completed' and em and em.get('status') == 'completed':
        l_wm = team_lookup.get(wm['loser_id'])
        w_em = team_lookup.get(em['winner_id'])
        if dm['team_a_id'] != wm['loser_id'] or dm['team_b_id'] != em['winner_id']:
            dm['team_a'] = l_wm
            dm['team_b'] = w_em
            dm['team_a_id'] = wm['loser_id']
            dm['team_b_id'] = em['winner_id']
            if dm.get('status') == 'completed':
                dm['status'] = 'pending'
                dm['winner_id'] = None
                dm['loser_id'] = None
                dm['winner'] = None
                dm['loser'] = None
                dm['team_a_score'] = 0
                dm['team_b_score'] = 0
                dm['maps'] = []
    else:
        dm['team_a'] = None
        dm['team_b'] = None
        dm['team_a_id'] = None
        dm['team_b_id'] = None
        dm['team_a_source_label'] = f"Thua Nhánh Thắng"
        dm['team_b_source_label'] = f"Thắng Nhánh Thua"

    # 4. Check Group Completion
    if wm and wm.get('status') == 'completed':
        group_data['winner'] = wm['winner']
    else:
        group_data['winner'] = None

    if dm and dm.get('status') == 'completed':
        group_data['runner_up'] = dm['winner']
        group_data['status'] = 'completed'
    else:
        group_data['runner_up'] = None
        group_data['status'] = 'in_progress'

    # 5. Compute Group Standings
    stats = {t['id']: {'wins': 0, 'losses': 0, 'map_w': 0, 'map_l': 0, 'status': 'pending'} for t in group_data['teams']}
    for m in [op1, op2, wm, em, dm]:
        if m and m.get('status') == 'completed' and m.get('winner_id') and m.get('loser_id'):
            stats[m['winner_id']]['wins'] += 1
            stats[m['loser_id']]['losses'] += 1
            stats[m['team_a_id']]['map_w'] += m.get('team_a_score', 0)
            stats[m['team_a_id']]['map_l'] += m.get('team_b_score', 0)
            stats[m['team_b_id']]['map_w'] += m.get('team_b_score', 0)
            stats[m['team_b_id']]['map_l'] += m.get('team_a_score', 0)

    # Status tags
    if group_data['winner']:
        stats[group_data['winner']['id']]['status'] = 'qualified'
    if group_data['runner_up']:
        stats[group_data['runner_up']['id']]['status'] = 'qualified'
    if em and em.get('status') == 'completed':
        stats[em['loser_id']]['status'] = 'eliminated'
    if dm and dm.get('status') == 'completed':
        stats[dm['loser_id']]['status'] = 'eliminated'

    standings = []
    for t in group_data['teams']:
        tid = t['id']
        st = stats[tid]
        standings.append({
            'team': t,
            'club_id': tid,
            'wins': st['wins'],
            'losses': st['losses'],
            'map_diff': st['map_w'] - st['map_l'],
            'status': st['status'],
        })

    def _rank_key(item):
        if item['status'] == 'qualified':
            return (0, -item['wins'], item['losses'], -item['map_diff'])
        elif item['status'] == 'pending':
            return (1, -item['wins'], item['losses'], -item['map_diff'])
        else:
            return (2, -item['wins'], item['losses'], -item['map_diff'])

    standings.sort(key=_rank_key)
    # Ensure exact 1st and 2nd rank placement
    if group_data['winner'] and len(standings) > 0:
        if standings[0]['club_id'] != group_data['winner']['id']:
            w_idx = next((i for i, s in enumerate(standings) if s['club_id'] == group_data['winner']['id']), 0)
            standings.insert(0, standings.pop(w_idx))
    if group_data['runner_up'] and len(standings) > 1:
        if standings[1]['club_id'] != group_data['runner_up']['id']:
            r_idx = next((i for i, s in enumerate(standings[1:], start=1) if s['club_id'] == group_data['runner_up']['id']), 1)
            standings.insert(1, standings.pop(r_idx))

    group_data['standings'] = standings


def _init_ewc_playoffs(ewc_data: Dict[str, Any]):
    """Initialize the 8-team Single Elimination playoff bracket after all GSL groups finish."""
    winners = []
    runners = []
    for label in ['A', 'B', 'C', 'D']:
        grp = ewc_data['groups'][label]
        if not grp.get('winner') or not grp.get('runner_up'):
            return
        w = dict(grp['winner'])
        w['group'] = label
        w['group_label'] = label
        winners.append(w)
        r = dict(grp['runner_up'])
        r['group'] = label
        r['group_label'] = label
        runners.append(r)

    ewc_data['group_qualifiers'] = {'winners': winners, 'runners': runners}

    templates = generate_ewc_playoffs_draw(winners, runners)
    playoff_matches = []

    for tpl in templates:
        r_name = tpl['round_name']
        bo = 5 if r_name == 'grand_final' else 3
        team_a = tpl.get('high_team')
        team_b = tpl.get('low_team')

        playoff_matches.append({
            'id': f"ewc_{r_name}",
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

    ewc_data['playoff_matches'] = playoff_matches
    ewc_data['current_stage'] = 'playoffs'
    _resolve_ewc_playoff_slots(ewc_data)


def _resolve_ewc_playoff_slots(ewc_data: Dict[str, Any]):
    """Resolve dynamic team sources for all playoff matches."""
    team_lookup = {t['id']: t for t in ewc_data.get('teams', [])}
    completed_matches = ewc_data.get('completed_playoffs', {})

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

    for m in ewc_data.get('playoff_matches', []):
        if m.get('round_name', '').startswith('quarterfinal_'):
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


def advance_ewc_state(ewc_data: Dict[str, Any]) -> bool:
    """Advance EWC state after a match completes."""
    team_lookup = {t['id']: t for t in ewc_data.get('teams', [])}

    # 1. Update Groups
    all_groups_done = True
    for label in ['A', 'B', 'C', 'D']:
        grp = ewc_data['groups'][label]
        _update_group_state(grp, team_lookup)
        if grp.get('status') != 'completed':
            all_groups_done = False

    # 2. Check transition from Groups to Playoffs
    if all_groups_done and not ewc_data.get('playoff_matches'):
        _init_ewc_playoffs(ewc_data)
        return True

    # 3. Update Playoffs
    if ewc_data.get('playoff_matches'):
        _resolve_ewc_playoff_slots(ewc_data)

        completed_matches = ewc_data.get('completed_playoffs', {})
        gf = completed_matches.get('grand_final')
        tp = completed_matches.get('third_place_match')

        if gf and gf.get('status') == 'completed' and tp and tp.get('status') == 'completed':
            champ = team_lookup.get(gf['winner_id'])
            runner = team_lookup.get(gf['loser_id'])
            third = team_lookup.get(tp['winner_id'])
            fourth = team_lookup.get(tp['loser_id'])

            ewc_data['champion'] = champ
            ewc_data['runner_up'] = runner
            ewc_data['third_place'] = third
            ewc_data['fourth_place'] = fourth

            # Quarterfinal losers: ranks 5-8
            qf_losers = []
            for q_name in ['quarterfinal_1', 'quarterfinal_2', 'quarterfinal_3', 'quarterfinal_4']:
                m = completed_matches.get(q_name)
                if m and m.get('loser_id'):
                    qf_losers.append(team_lookup.get(m['loser_id']))

            final_standings = [
                {'rank': 1, 'team': champ, 'club_id': champ.get('id') if champ else None, 'cp': 0, 'desc': 'Quán quân Esports World Cup (Cúp Vô Địch)'},
                {'rank': 2, 'team': runner, 'club_id': runner.get('id') if runner else None, 'cp': 0, 'desc': 'Á quân Esports World Cup'},
                {'rank': 3, 'team': third, 'club_id': third.get('id') if third else None, 'cp': 0, 'desc': 'Hạng 3 Esports World Cup'},
                {'rank': 4, 'team': fourth, 'club_id': fourth.get('id') if fourth else None, 'cp': 0, 'desc': 'Hạng 4 Esports World Cup'},
            ]

            for idx, ql in enumerate(qf_losers):
                final_standings.append({
                    'rank': 5 + idx,
                    'team': ql,
                    'club_id': ql.get('id') if ql else None,
                    'cp': 0,
                    'desc': 'Tứ kết Esports World Cup (Top 5-8)',
                })

            # Group stage eliminated teams: ranks 9-16
            for label in ['A', 'B', 'C', 'D']:
                grp = ewc_data['groups'][label]
                for s in grp.get('standings', [])[2:]:
                    final_standings.append({
                        'rank': len(final_standings) + 1,
                        'team': s['team'],
                        'club_id': s['club_id'],
                        'cp': 0,
                        'desc': f'Bị loại ở Vòng Bảng {label}',
                    })

            ewc_data['matches_completed'] = True
            ewc_data['standings'] = final_standings
            ewc_data['status'] = 'completed'
            return True

    return False


def resolve_ewc_match(ewc_data: Dict[str, Any], match_id_or_round_name: str,
                      winner_id: Optional[int] = None,
                      maps: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Resolve a single match in EWC (Roll or Manual Score)."""
    target = None

    # Search in groups
    for label in ['A', 'B', 'C', 'D']:
        grp = ewc_data['groups'][label]
        for m in grp['matches'].values():
            if m.get('id') == match_id_or_round_name or m.get('round_name') == match_id_or_round_name:
                target = m
                break
        if target:
            break

    # Search in playoffs
    if not target:
        for m in ewc_data.get('playoff_matches', []):
            if m.get('id') == match_id_or_round_name or m.get('round_name') == match_id_or_round_name:
                target = m
                break

    if not target:
        raise ValueError(f"Match {match_id_or_round_name} not found in EWC")

    if ewc_data.get('is_confirmed'):
        raise ValueError("Không thể chỉnh sửa trận đấu vì giải đấu EWC đã được xác nhận và khóa chính thức!")

    if not target.get('team_a') or not target.get('team_b'):
        raise ValueError("Match participants are not fully determined yet.")

    override = None
    if winner_id is not None:
        override = {'winner_id': winner_id, 'maps': maps or []}

    is_gf = (target.get('round_name') == 'grand_final')
    is_playoff = (target in ewc_data.get('playoff_matches', []))
    bo = target.get('bo', 3)

    all_matches = []
    for grp in ewc_data.get('groups', {}).values():
        all_matches.extend(grp.get('matches', {}).values())
    all_matches.extend(ewc_data.get('playoff_matches', []))

    all_completed = [m for m in all_matches if m.get('status') == 'completed' and m.get('id') != target.get('id')]
    id_a = target['team_a']['id'] if 'id' in target['team_a'] else target['team_a'].get('club_id')
    id_b = target['team_b']['id'] if 'id' in target['team_b'] else target['team_b'].get('club_id')
    prior_a = sum(1 for m in all_completed if m.get('team_a_id') == id_a or m.get('team_b_id') == id_a)
    prior_b = sum(1 for m in all_completed if m.get('team_a_id') == id_b or m.get('team_b_id') == id_b)

    res = simulate_ewc_single_match(
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

    if 'sources' in target and not target.get('group'):
        ewc_data.setdefault('completed_playoffs', {})[target['round_name']] = target

    ewc_data['total_matches_count'] = ewc_data.get('total_matches_count', 0) + 1
    advance_ewc_state(ewc_data)
    return target


def sim_ewc_round(ewc_data: Dict[str, Any]) -> int:
    """Simulate current active round/wave in EWC."""
    if ewc_data.get('status') == 'completed':
        return 0

    stage = ewc_data.get('current_stage')
    simmed = 0

    if stage == 'groups':
        advance_ewc_state(ewc_data)
        for label in ['A', 'B', 'C', 'D']:
            grp = ewc_data['groups'][label]
            for m in grp['matches'].values():
                if m.get('status') == 'pending' and m.get('team_a') and m.get('team_b'):
                    resolve_ewc_match(ewc_data, m['id'])
                    simmed += 1
        return simmed

    elif stage == 'playoffs':
        _resolve_ewc_playoff_slots(ewc_data)
        playable = [
            m for m in ewc_data.get('playoff_matches', [])
            if m.get('status') == 'pending' and m.get('team_a') and m.get('team_b')
        ]
        for m in playable:
            resolve_ewc_match(ewc_data, m['id'])
            simmed += 1
        return simmed

    return 0


def sim_ewc_remaining(ewc_data: Dict[str, Any]) -> int:
    """Simulate all remaining matches in EWC until Grand Final completes."""
    total = 0
    max_loops = 50
    loops = 0
    while ewc_data.get('status') != 'completed' and loops < max_loops:
        loops += 1
        count = sim_ewc_round(ewc_data)
        if count == 0:
            break
        total += count
    return total


def simulate_ewc_tournament(teams: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Execute complete automated simulation of EWC."""
    state = init_ewc_state(teams)
    sim_ewc_remaining(state)
    return state
