"""
engine/format/champion_sim.py — VALORANT Champions Paris Simulation Engine for Campaign Mode

Specifications:
- 16 World Elite Teams (4 Pacific, 4 Americas, 4 EMEA, 4 China):
  * Pool 1 (Seed 1): 4 Stage 2 Champions
  * Pool 2 (Seed 2): 4 Stage 2 Runners-up
  * Pool 3 (Seed 3): 4 Championship Points #1
  * Pool 4 (Seed 4): 4 Championship Points #2
- Stage 1: Group Stage (4 Groups of 4 teams, GSL Format, 5 BO3 matches per group = 20 matches)
  * Opening 1: Pool 1 vs Pool 4
  * Opening 2: Pool 2 vs Pool 3
  * Winners Match: Winner O1 vs Winner O2 -> Winner qualifies as #1 seed
  * Elimination Match: Loser O1 vs Loser O2 -> Loser eliminated
  * Decider Match: Loser Winners vs Winner Elimination -> Winner qualifies as #2 seed, Loser eliminated
- Stage 2: Playoffs (8 teams Double Elimination, 14 matches)
  * 4 Upper Quarterfinals (BO3): #1 seed vs #2 seed (constraint: cannot face team from same group, opposite halves)
  * 2 Upper Semifinals (BO3)
  * 1 Upper Final (BO3)
  * 2 Lower Round 1 (BO3)
  * 2 Lower Quarterfinals (BO3)
  * 1 Lower Semifinal (BO3)
  * 1 Lower Final (BO5)
  * 1 Grand Final (BO5)
- Total Champions matches: 20 (Groups) + 14 (Playoffs) = 34 matches.
- Story Rewards: World Champion (+10 story rating), Runner-up (+6), 3rd (+4), 4th (+3).
"""

import copy
import random
from typing import List, Dict, Optional, Any, Tuple
from engine.format.champion import (
    generate_gsl_groups,
    get_gsl_matches,
    generate_champion_playoffs_draw,
    resolve_slot,
)
from engine.match import _calc_region_bonus, _gen_map_score, calc_pure_international_win_rate


def _calc_champion_win_rate(team_a: Dict[str, Any], team_b: Dict[str, Any],
                            is_grand_final: bool = False,
                            is_playoff: bool = False,
                            streak_a: int = 0, streak_b: int = 0,
                            prior_a: int = 0, prior_b: int = 0) -> float:
    """Calculate win probability for an international match in VALORANT Champions.
    
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
        tour_type='champion',
        is_grand_final=is_grand_final,
        is_playoff=is_playoff,
        seed_a=seed_a,
        seed_b=seed_b,
        prior_a=prior_a,
        prior_b=prior_b,
        streak_a=streak_a,
        streak_b=streak_b,
    )


def simulate_champion_single_match(team_a: Dict[str, Any], team_b: Dict[str, Any], bo: int = 3,
                                   is_grand_final: bool = False,
                                   is_playoff: bool = False,
                                   prior_a: int = 0, prior_b: int = 0,
                                   streak_a: int = 0, streak_b: int = 0,
                                   manual_override: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Simulate a single Champions match or apply manual override."""
    id_a = team_a['id'] if 'id' in team_a else team_a.get('club_id')
    id_b = team_b['id'] if 'id' in team_b else team_b.get('club_id')

    r_a = team_a.get('story_rating') or team_a.get('effective_rating') or 80
    r_b = team_b.get('story_rating') or team_b.get('effective_rating') or 80

    target_wins = 3 if bo == 5 else (bo // 2) + 1

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
    prob_a = _calc_champion_win_rate(
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
        'upper_quarterfinal_1': 'Tứ kết Nhánh Thắng 1 (UQ 1)',
        'upper_quarterfinal_2': 'Tứ kết Nhánh Thắng 2 (UQ 2)',
        'upper_quarterfinal_3': 'Tứ kết Nhánh Thắng 3 (UQ 3)',
        'upper_quarterfinal_4': 'Tứ kết Nhánh Thắng 4 (UQ 4)',
        'upper_semifinal_1': 'Bán kết Nhánh Thắng 1 (USF 1)',
        'upper_semifinal_2': 'Bán kết Nhánh Thắng 2 (USF 2)',
        'upper_final': 'Chung kết Nhánh Thắng (Upper Final)',
        'lower_round1_1': 'Vòng Loại Nhánh Thua 1 (LR1 1)',
        'lower_round1_2': 'Vòng Loại Nhánh Thua 2 (LR1 2)',
        'lower_quarterfinal_1': 'Tứ kết Nhánh Thua 1 (LQF 1)',
        'lower_quarterfinal_2': 'Tứ kết Nhánh Thua 2 (LQF 2)',
        'lower_semifinal': 'Bán kết Nhánh Thua (Lower Semifinal)',
        'lower_final': 'Chung kết Nhánh Thua (Lower Final - BO5)',
        'grand_final': 'Chung kết Thế Giới Champions Paris (Grand Final - BO5)',
    }
    return labels.get(round_name, round_name.replace('_', ' ').title())


def init_champion_state(teams: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Initialize interactive VALORANT Champions Paris state with 16 qualified teams."""
    if len(teams) != 16:
        raise ValueError(f"VALORANT Champions requires exactly 16 teams, got {len(teams)}")

    normalized_teams = []
    for t in teams:
        norm_t = dict(t)
        norm_t['id'] = norm_t.get('id') or norm_t.get('club_id')
        norm_t['club_id'] = norm_t['id']
        if 'region' not in norm_t and 'region_slug' in norm_t:
            norm_t['region'] = norm_t['region_slug']
        pool_num = norm_t.get('pool') or norm_t.get('champions_seed') or norm_t.get('regional_seed') or 1
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

        for tmpl in match_templates:
            m_name = tmpl['round_name']
            m_label = m_name.replace(f'group{label}_', '').replace('_', ' ').title()

            is_opening1 = m_name.endswith('opening1')
            is_opening2 = m_name.endswith('opening2')

            team_a = t1 if is_opening1 else (t2 if is_opening2 else None)
            team_b = t4 if is_opening1 else (t3 if is_opening2 else None)
            ready = is_opening1 or is_opening2

            matches[m_name] = {
                'id': m_name,
                'round_name': m_name,
                'label': f"Bảng {label} — {m_label}",
                'group': label,
                'phase': 'group',
                'bo': 3,
                'team_a': team_a,
                'team_b': team_b,
                'team_a_score': 0,
                'team_b_score': 0,
                'winner': None,
                'loser': None,
                'winner_id': None,
                'loser_id': None,
                'status': 'pending',
                'ready': ready,
                'maps': [],
                'is_manual': False,
                'template': tmpl,
            }

        grp_obj = {
            'label': label,
            'teams': grp_teams,
            'matches': matches,
            'winner_seed1': None,
            'winner_seed2': None,
            'status': 'in_progress',
        }
        update_champion_group_standings(grp_obj)
        groups_data[label] = grp_obj

    return {
        'status': 'in_progress',
        'current_stage': 'groups',  # 'groups' -> 'playoffs' -> 'completed'
        'groups': groups_data,
        'playoff_matches': [],
        'champion': None,
        'runner_up': None,
        'third_place': None,
        'fourth_place': None,
        'standings': [],
        'rewards_awarded': False,
    }


def update_champion_group_standings(grp: Dict[str, Any]):
    """Calculate Liquipedia-style group standings (W-L, Map Diff, Qualification status) for a Champions GSL group."""
    teams = grp.get('teams', [])
    matches = grp.get('matches', {})
    stats = {}
    for t in teams:
        if isinstance(t, dict) and t.get('id'):
            stats[t['id']] = {
                'team': t,
                'club_id': t['id'],
                'wins': 0,
                'losses': 0,
                'map_w': 0,
                'map_l': 0,
                'status': 'pending',
                'is_seed1': False,
                'is_seed2': False,
            }

    # Inspect all completed matches in group
    for m in matches.values():
        if isinstance(m, dict) and m.get('status') == 'completed':
            w_id = m.get('winner_id')
            ta = m.get('team_a') or {}
            tb = m.get('team_b') or {}
            ta_id = ta.get('id') if isinstance(ta, dict) else None
            tb_id = tb.get('id') if isinstance(tb, dict) else None
            l_id = tb_id if w_id == ta_id else ta_id

            if w_id and w_id in stats:
                stats[w_id]['wins'] += 1
            if l_id and l_id in stats:
                stats[l_id]['losses'] += 1

            sa = m.get('team_a_score', 0)
            sb = m.get('team_b_score', 0)
            if ta_id and ta_id in stats:
                stats[ta_id]['map_w'] += sa
                stats[ta_id]['map_l'] += sb
            if tb_id and tb_id in stats:
                stats[tb_id]['map_w'] += sb
                stats[tb_id]['map_l'] += sa

    # Check qualification & elimination status
    w_seed1 = grp.get('winner_seed1')
    if w_seed1 and isinstance(w_seed1, dict) and w_seed1.get('id') in stats:
        stats[w_seed1['id']]['status'] = 'qualified'
        stats[w_seed1['id']]['is_seed1'] = True

    w_seed2 = grp.get('winner_seed2')
    if w_seed2 and isinstance(w_seed2, dict) and w_seed2.get('id') in stats:
        stats[w_seed2['id']]['status'] = 'qualified'
        stats[w_seed2['id']]['is_seed2'] = True

    label = grp.get('label', '')
    em = matches.get(f'group{label}_elimination_match')
    if em and em.get('status') == 'completed' and em.get('loser'):
        l4 = em['loser']
        l4_id = l4.get('id') if isinstance(l4, dict) else None
        if l4_id in stats and stats[l4_id]['status'] != 'qualified':
            stats[l4_id]['status'] = 'eliminated'

    dm = matches.get(f'group{label}_decider_match')
    if dm and dm.get('status') == 'completed' and dm.get('loser'):
        l3 = dm['loser']
        l3_id = l3.get('id') if isinstance(l3, dict) else None
        if l3_id in stats and stats[l3_id]['status'] != 'qualified':
            stats[l3_id]['status'] = 'eliminated'

    standings = []
    for s in stats.values():
        s['map_diff'] = s['map_w'] - s['map_l']
        standings.append(s)

    def _rank_key(item):
        if item['is_seed1']:
            return (0, 0)
        elif item['is_seed2']:
            return (1, 0)
        elif item['status'] == 'pending':
            return (2, -item['wins'], item['losses'], -item['map_diff'])
        else:
            return (3, -item['wins'], item['losses'], -item['map_diff'])

    standings.sort(key=_rank_key)
    for idx, s in enumerate(standings, start=1):
        s['rank'] = idx

    grp['standings'] = standings


def advance_champion_state(data: Dict[str, Any]) -> bool:
    """Advance Champions GSL groups and 8-team Double Elimination playoffs."""
    if data.get('status') == 'completed':
        return False

    groups_data = data.get('groups', {})
    all_groups_done = True
    advancing_winners = []
    advancing_runners = []

    # 1. Update GSL Group Stages
    for label in ['A', 'B', 'C', 'D']:
        grp = groups_data.get(label)
        if not grp:
            continue
        matches = grp['matches']

        op1 = matches.get(f'group{label}_opening1')
        op2 = matches.get(f'group{label}_opening2')
        wm = matches.get(f'group{label}_winners_match')
        em = matches.get(f'group{label}_elimination_match')
        dm = matches.get(f'group{label}_decider_match')

        # Winners Match slot resolution
        if wm and wm['status'] == 'pending':
            if op1 and op1['status'] == 'completed' and op2 and op2['status'] == 'completed':
                wm['team_a'] = op1['winner']
                wm['team_b'] = op2['winner']
                wm['ready'] = True

        # Elimination Match slot resolution
        if em and em['status'] == 'pending':
            if op1 and op1['status'] == 'completed' and op2 and op2['status'] == 'completed':
                em['team_a'] = op1['loser']
                em['team_b'] = op2['loser']
                em['ready'] = True

        # Decider Match slot resolution
        if dm and dm['status'] == 'pending':
            if wm and wm['status'] == 'completed' and em and em['status'] == 'completed':
                dm['team_a'] = wm['loser']
                dm['team_b'] = em['winner']
                dm['ready'] = True

        # Group completed check
        if wm and wm['status'] == 'completed':
            grp['winner_seed1'] = wm['winner']
        if dm and dm['status'] == 'completed':
            grp['winner_seed2'] = dm['winner']

        if grp['winner_seed1'] and grp['winner_seed2']:
            grp['status'] = 'completed'
            advancing_winners.append(grp['winner_seed1'])
            advancing_runners.append(grp['winner_seed2'])
        else:
            all_groups_done = False

        update_champion_group_standings(grp)

    # 2. Transition to Playoffs when groups finish
    if all_groups_done and data['current_stage'] == 'groups':
        data['current_stage'] = 'playoffs'
        playoff_draw = generate_champion_playoffs_draw(advancing_winners, advancing_runners)
        playoff_matches = []

        for item in playoff_draw:
            r_name = item['round_name']
            r_type = item.get('round_type')
            is_bo5 = r_name in ('lower_final', 'grand_final')

            team_a = item.get('high_team')
            team_b = item.get('low_team')
            ready = (team_a is not None and team_b is not None)

            playoff_matches.append({
                'id': r_name,
                'round_name': r_name,
                'round_type': r_type,
                'bracket': 'upper' if r_type == 'upper' else ('lower' if r_type == 'lower' else 'grand'),
                'label': _get_playoff_label(r_name),
                'bo': 5 if is_bo5 else 3,
                'team_a': team_a,
                'team_b': team_b,
                'team_a_score': 0,
                'team_b_score': 0,
                'winner': None,
                'loser': None,
                'winner_id': None,
                'loser_id': None,
                'status': 'pending',
                'ready': ready,
                'maps': [],
                'is_manual': False,
                'template': item,
            })

        data['playoff_matches'] = playoff_matches

    # 3. Update Playoff Slots (Double Elimination)
    if data['current_stage'] == 'playoffs':
        p_matches = data.get('playoff_matches', [])
        completed_p = {m['id']: m for m in p_matches if m['status'] == 'completed'}

        def _get_team(tmpl_source: Dict[str, Any]) -> Optional[Dict[str, Any]]:
            stype = tmpl_source.get('type')
            sval = tmpl_source.get('value')
            if sval in completed_p:
                if stype == 'winner_of':
                    return completed_p[sval]['winner']
                elif stype == 'loser_of':
                    return completed_p[sval]['loser']
            return None

        for pm in p_matches:
            if pm['status'] == 'completed':
                continue
            tmpl = pm.get('template', {})
            sources = tmpl.get('sources', {})

            if 'team_a' in sources:
                t_a = _get_team(sources['team_a'])
                if t_a:
                    pm['team_a'] = t_a
            if 'team_b' in sources:
                t_b = _get_team(sources['team_b'])
                if t_b:
                    pm['team_b'] = t_b

            pm['ready'] = (pm['team_a'] is not None and pm['team_b'] is not None)

        # Check tournament completion
        gf = next((m for m in p_matches if m['id'] == 'grand_final'), None)
        if gf and gf['status'] == 'completed':
            data['matches_completed'] = True
            data['status'] = 'completed'
            data['champion'] = gf['winner']
            data['runner_up'] = gf['loser']

            lf = next((m for m in p_matches if m['id'] == 'lower_final'), None)
            lsf = next((m for m in p_matches if m['id'] == 'lower_semifinal'), None)

            data['third_place'] = lf['loser'] if lf else None
            data['fourth_place'] = lsf['loser'] if lsf else None

            # Generate Final Standings for all 16 teams
            data['standings'] = _compute_champion_standings(data)
            return True

    return False


def _compute_champion_standings(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    standings = []
    p_matches = {m['id']: m for m in data.get('playoff_matches', [])}

    # 1. World Champion
    if data.get('champion'):
        standings.append({'rank': 1, 'team': data['champion'], 'title': 'Nhà Vô Địch Thế Giới (World Champion)', 'desc': 'Nâng cao Cúp Champions Paris danh giá'})
    # 2. Runner-up
    if data.get('runner_up'):
        standings.append({'rank': 2, 'team': data['runner_up'], 'title': 'Á Quân Thế Giới (World Runner-up)', 'desc': 'Thua trận Chung kết Tổng'})
    # 3. Third Place
    if data.get('third_place'):
        standings.append({'rank': 3, 'team': data['third_place'], 'title': 'Hạng 3 Thế Giới (3rd Place)', 'desc': 'Thua trận Chung kết Nhánh Thua'})
    # 4. Fourth Place
    if data.get('fourth_place'):
        standings.append({'rank': 4, 'team': data['fourth_place'], 'title': 'Hạng 4 Thế Giới (4th Place)', 'desc': 'Thua trận Bán kết Nhánh Thua'})

    # 5-6: Losers of Lower Quarterfinals
    lqf1 = p_matches.get('lower_quarterfinal_1')
    lqf2 = p_matches.get('lower_quarterfinal_2')
    if lqf1 and lqf1.get('loser'):
        standings.append({'rank': 5, 'team': lqf1['loser'], 'title': 'Top 5-6 Thế Giới', 'desc': 'Thua Tứ kết Nhánh Thua'})
    if lqf2 and lqf2.get('loser'):
        standings.append({'rank': 6, 'team': lqf2['loser'], 'title': 'Top 5-6 Thế Giới', 'desc': 'Thua Tứ kết Nhánh Thua'})

    # 7-8: Losers of Lower Round 1
    lr1_1 = p_matches.get('lower_round1_1')
    lr1_2 = p_matches.get('lower_round1_2')
    if lr1_1 and lr1_1.get('loser'):
        standings.append({'rank': 7, 'team': lr1_1['loser'], 'title': 'Top 7-8 Thế Giới', 'desc': 'Thua Vòng 1 Nhánh Thua'})
    if lr1_2 and lr1_2.get('loser'):
        standings.append({'rank': 8, 'team': lr1_2['loser'], 'title': 'Top 7-8 Thế Giới', 'desc': 'Thua Vòng 1 Nhánh Thua'})

    # 9-12: Decider losers
    for label in ['A', 'B', 'C', 'D']:
        grp = data.get('groups', {}).get(label, {})
        dm = grp.get('matches', {}).get(f'group{label}_decider_match')
        if dm and dm.get('loser'):
            standings.append({'rank': 9, 'team': dm['loser'], 'title': f'Hạng 3 Bảng {label} (Top 9-12)', 'desc': 'Thua trận Quyết định vòng bảng'})

    # 13-16: Elimination losers
    for label in ['A', 'B', 'C', 'D']:
        grp = data.get('groups', {}).get(label, {})
        em = grp.get('matches', {}).get(f'group{label}_elimination_match')
        if em and em.get('loser'):
            standings.append({'rank': 13, 'team': em['loser'], 'title': f'Hạng 4 Bảng {label} (Top 13-16)', 'desc': 'Bị loại trận Sinh tử vòng bảng'})

    return standings


def resolve_champion_match(data: Dict[str, Any], match_id: str,
                           winner_id: Optional[int] = None,
                           maps: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Resolve a specific match in Champions (by ID) through roll or manual input."""
    target_match = None

    # Search in groups
    for label in ['A', 'B', 'C', 'D']:
        grp = data.get('groups', {}).get(label, {})
        if match_id in grp.get('matches', {}):
            target_match = grp['matches'][match_id]
            break

    # Search in playoffs
    if not target_match:
        for pm in data.get('playoff_matches', []):
            if pm['id'] == match_id:
                target_match = pm
                break

    if not target_match:
        raise ValueError(f"Match {match_id} not found in VALORANT Champions")

    if data.get('is_confirmed'):
        raise ValueError("Không thể chỉnh sửa trận đấu vì giải đấu VALORANT Champions đã được xác nhận và khóa chính thức!")

    if not target_match.get('team_a') or not target_match.get('team_b'):
        raise ValueError(f"Trận {match_id} chưa xác định đủ 2 đội tuyển thi đấu.")

    manual_override = None
    if winner_id is not None:
        manual_override = {'winner_id': winner_id, 'maps': maps or []}

    is_gf = (target_match['id'] == 'grand_final')
    is_playoff = (target_match in data.get('playoff_matches', []))

    all_matches = []
    for grp in data.get('groups', {}).values():
        all_matches.extend(grp.get('matches', {}).values())
    all_matches.extend(data.get('playoff_matches', []))

    all_completed = [m for m in all_matches if m.get('status') == 'completed' and m.get('id') != target_match.get('id')]
    id_a = target_match['team_a']['id'] if 'id' in target_match['team_a'] else target_match['team_a'].get('club_id')
    id_b = target_match['team_b']['id'] if 'id' in target_match['team_b'] else target_match['team_b'].get('club_id')
    prior_a = sum(1 for m in all_completed if m.get('team_a_id') == id_a or m.get('team_b_id') == id_a)
    prior_b = sum(1 for m in all_completed if m.get('team_a_id') == id_b or m.get('team_b_id') == id_b)

    sim_res = simulate_champion_single_match(
        target_match['team_a'], target_match['team_b'],
        bo=target_match['bo'],
        is_grand_final=is_gf,
        is_playoff=is_playoff,
        prior_a=prior_a,
        prior_b=prior_b,
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

    advance_champion_state(data)
    return target_match


def sim_champion_round(data: Dict[str, Any]) -> int:
    """Simulate active wave of playable matches in Champions."""
    if data.get('status') == 'completed':
        return 0

    sim_count = 0

    # 1. Groups phase
    if data['current_stage'] == 'groups':
        ready_matches = []
        for label in ['A', 'B', 'C', 'D']:
            grp = data.get('groups', {}).get(label, {})
            for m in grp.get('matches', {}).values():
                if m['status'] == 'pending' and m['ready']:
                    ready_matches.append(m)

        for m in ready_matches:
            resolve_champion_match(data, m['id'])
            sim_count += 1
        return sim_count

    # 2. Playoffs phase
    if data['current_stage'] == 'playoffs':
        advance_champion_state(data)
        ready_playoffs = [m for m in data.get('playoff_matches', []) if m['status'] == 'pending' and m['ready']]
        for m in ready_playoffs:
            resolve_champion_match(data, m['id'])
            sim_count += 1

    return sim_count


def sim_champion_remaining(data: Dict[str, Any]) -> int:
    """Simulate all remaining matches until Champions Paris completes."""
    total_sim = 0
    while data.get('status') != 'completed':
        count = sim_champion_round(data)
        if count == 0:
            break
        total_sim += count
    return total_sim
