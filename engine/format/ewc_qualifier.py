"""EWC Regional Qualifier Engine (Open Regional Qualifier).

Format specification:
Phase 1 - Open Preliminary:
- 16 teams Single Elimination BO3 (14 matches):
  - 4 teams from Stage 1 (ranks 9-12, Seeds 1-4)
  - 12 non-Stage 1 challenger teams (Seeds 5-16)
  - Round of 16 (8 matches) -> Quarterfinals (4 matches) -> Semifinals (2 matches)
  - The 2 Semifinal winners advance to Phase 2 (P1 Qualifier 1 and P1 Qualifier 2).

Phase 2 - Regional Qualifier Final:
- 8 teams Double Elimination (14 matches):
  - 6 teams from Stage 1 (ranks 3-8, Seeds 1-6)
  - 2 winners from Phase 1 (Seeds 7 & 8)
  - Upper Bracket: Quarterfinals (4), Semifinals (2), Upper Final (1)
  - Lower Bracket: Lower R1 (2), Lower QF (2), Lower SF (1), Lower Final (1)
  - Grand Final (1)
  - The 2 Grand Finalists earn the region's remaining 2 slots for EWC:
    - Grand Final Winner: EWC Pool 3
    - Grand Final Runner-up: EWC Pool 4

Total matches per region: 14 (Phase 1) + 14 (Phase 2) = 28 matches.
Supports: Roll, Manual Score, Edit Completed Matches (with cascade reset), Sim Round, Sim Region.
"""

import random
from typing import Any, Dict, List, Optional, Tuple


def get_phase1_bracket_templates() -> List[Dict[str, Any]]:
    """Return the 14 match templates for Phase 1 (Single Elimination BO3)."""
    return [
        # Round of 16 (8 matches)
        {
            'match_code': 'P1_M1',
            'phase': 'phase1',
            'round_name': 'p1_r16_m1',
            'round_type': 'r16',
            'label': 'Vòng 1/8 - Trận 1',
            'team_a_source': {'type': 'seed', 'value': 1},
            'team_b_source': {'type': 'seed', 'value': 16},
            'bo': 3,
        },
        {
            'match_code': 'P1_M2',
            'phase': 'phase1',
            'round_name': 'p1_r16_m2',
            'round_type': 'r16',
            'label': 'Vòng 1/8 - Trận 2',
            'team_a_source': {'type': 'seed', 'value': 8},
            'team_b_source': {'type': 'seed', 'value': 9},
            'bo': 3,
        },
        {
            'match_code': 'P1_M3',
            'phase': 'phase1',
            'round_name': 'p1_r16_m3',
            'round_type': 'r16',
            'label': 'Vòng 1/8 - Trận 3',
            'team_a_source': {'type': 'seed', 'value': 4},
            'team_b_source': {'type': 'seed', 'value': 13},
            'bo': 3,
        },
        {
            'match_code': 'P1_M4',
            'phase': 'phase1',
            'round_name': 'p1_r16_m4',
            'round_type': 'r16',
            'label': 'Vòng 1/8 - Trận 4',
            'team_a_source': {'type': 'seed', 'value': 5},
            'team_b_source': {'type': 'seed', 'value': 12},
            'bo': 3,
        },
        {
            'match_code': 'P1_M5',
            'phase': 'phase1',
            'round_name': 'p1_r16_m5',
            'round_type': 'r16',
            'label': 'Vòng 1/8 - Trận 5',
            'team_a_source': {'type': 'seed', 'value': 2},
            'team_b_source': {'type': 'seed', 'value': 15},
            'bo': 3,
        },
        {
            'match_code': 'P1_M6',
            'phase': 'phase1',
            'round_name': 'p1_r16_m6',
            'round_type': 'r16',
            'label': 'Vòng 1/8 - Trận 6',
            'team_a_source': {'type': 'seed', 'value': 7},
            'team_b_source': {'type': 'seed', 'value': 10},
            'bo': 3,
        },
        {
            'match_code': 'P1_M7',
            'phase': 'phase1',
            'round_name': 'p1_r16_m7',
            'round_type': 'r16',
            'label': 'Vòng 1/8 - Trận 7',
            'team_a_source': {'type': 'seed', 'value': 3},
            'team_b_source': {'type': 'seed', 'value': 14},
            'bo': 3,
        },
        {
            'match_code': 'P1_M8',
            'phase': 'phase1',
            'round_name': 'p1_r16_m8',
            'round_type': 'r16',
            'label': 'Vòng 1/8 - Trận 8',
            'team_a_source': {'type': 'seed', 'value': 6},
            'team_b_source': {'type': 'seed', 'value': 11},
            'bo': 3,
        },
        # Quarterfinals (4 matches)
        {
            'match_code': 'P1_QF1',
            'phase': 'phase1',
            'round_name': 'p1_qf1',
            'round_type': 'qf',
            'label': 'Tứ kết 1',
            'team_a_source': {'type': 'match_winner', 'value': 'p1_r16_m1'},
            'team_b_source': {'type': 'match_winner', 'value': 'p1_r16_m2'},
            'bo': 3,
        },
        {
            'match_code': 'P1_QF2',
            'phase': 'phase1',
            'round_name': 'p1_qf2',
            'round_type': 'qf',
            'label': 'Tứ kết 2',
            'team_a_source': {'type': 'match_winner', 'value': 'p1_r16_m3'},
            'team_b_source': {'type': 'match_winner', 'value': 'p1_r16_m4'},
            'bo': 3,
        },
        {
            'match_code': 'P1_QF3',
            'phase': 'phase1',
            'round_name': 'p1_qf3',
            'round_type': 'qf',
            'label': 'Tứ kết 3',
            'team_a_source': {'type': 'match_winner', 'value': 'p1_r16_m5'},
            'team_b_source': {'type': 'match_winner', 'value': 'p1_r16_m6'},
            'bo': 3,
        },
        {
            'match_code': 'P1_QF4',
            'phase': 'phase1',
            'round_name': 'p1_qf4',
            'round_type': 'qf',
            'label': 'Tứ kết 4',
            'team_a_source': {'type': 'match_winner', 'value': 'p1_r16_m7'},
            'team_b_source': {'type': 'match_winner', 'value': 'p1_r16_m8'},
            'bo': 3,
        },
        # Semifinals (2 matches) -> Winners advance to Phase 2
        {
            'match_code': 'P1_SF1',
            'phase': 'phase1',
            'round_name': 'p1_sf1',
            'round_type': 'sf',
            'label': 'Bán kết 1 (Tranh vé Phase 2)',
            'team_a_source': {'type': 'match_winner', 'value': 'p1_qf1'},
            'team_b_source': {'type': 'match_winner', 'value': 'p1_qf2'},
            'bo': 3,
            'is_decider': True,
        },
        {
            'match_code': 'P1_SF2',
            'phase': 'phase1',
            'round_name': 'p1_sf2',
            'round_type': 'sf',
            'label': 'Bán kết 2 (Tranh vé Phase 2)',
            'team_a_source': {'type': 'match_winner', 'value': 'p1_qf3'},
            'team_b_source': {'type': 'match_winner', 'value': 'p1_qf4'},
            'bo': 3,
            'is_decider': True,
        },
    ]


def get_phase2_bracket_templates() -> List[Dict[str, Any]]:
    """Return the 14 match templates for Phase 2 (8-team Double Elimination)."""
    return [
        # Upper Quarterfinals (4 matches)
        {
            'match_code': 'P2_UB_QF1',
            'phase': 'phase2',
            'round_type': 'upper',
            'round_name': 'p2_ub_qf1',
            'label': 'Nhánh thắng - Tứ kết 1',
            'team_a_source': {'type': 'seed', 'value': 1},
            'team_b_source': {'type': 'seed', 'value': 8},
            'bo': 3,
        },
        {
            'match_code': 'P2_UB_QF2',
            'phase': 'phase2',
            'round_type': 'upper',
            'round_name': 'p2_ub_qf2',
            'label': 'Nhánh thắng - Tứ kết 2',
            'team_a_source': {'type': 'seed', 'value': 4},
            'team_b_source': {'type': 'seed', 'value': 5},
            'bo': 3,
        },
        {
            'match_code': 'P2_UB_QF3',
            'phase': 'phase2',
            'round_type': 'upper',
            'round_name': 'p2_ub_qf3',
            'label': 'Nhánh thắng - Tứ kết 3',
            'team_a_source': {'type': 'seed', 'value': 2},
            'team_b_source': {'type': 'seed', 'value': 7},
            'bo': 3,
        },
        {
            'match_code': 'P2_UB_QF4',
            'phase': 'phase2',
            'round_type': 'upper',
            'round_name': 'p2_ub_qf4',
            'label': 'Nhánh thắng - Tứ kết 4',
            'team_a_source': {'type': 'seed', 'value': 3},
            'team_b_source': {'type': 'seed', 'value': 6},
            'bo': 3,
        },
        # Upper Semifinals (2 matches)
        {
            'match_code': 'P2_UB_SF1',
            'phase': 'phase2',
            'round_type': 'upper',
            'round_name': 'p2_ub_sf1',
            'label': 'Nhánh thắng - Bán kết 1',
            'team_a_source': {'type': 'match_winner', 'value': 'p2_ub_qf1'},
            'team_b_source': {'type': 'match_winner', 'value': 'p2_ub_qf2'},
            'bo': 3,
        },
        {
            'match_code': 'P2_UB_SF2',
            'phase': 'phase2',
            'round_type': 'upper',
            'round_name': 'p2_ub_sf2',
            'label': 'Nhánh thắng - Bán kết 2',
            'team_a_source': {'type': 'match_winner', 'value': 'p2_ub_qf3'},
            'team_b_source': {'type': 'match_winner', 'value': 'p2_ub_qf4'},
            'bo': 3,
        },
        # Lower Round 1 (2 matches)
        {
            'match_code': 'P2_LB_R1_M1',
            'phase': 'phase2',
            'round_type': 'lower',
            'round_name': 'p2_lb_r1_m1',
            'label': 'Nhánh thua - Vòng 1 Trận 1',
            'team_a_source': {'type': 'match_loser', 'value': 'p2_ub_qf1'},
            'team_b_source': {'type': 'match_loser', 'value': 'p2_ub_qf2'},
            'bo': 3,
        },
        {
            'match_code': 'P2_LB_R1_M2',
            'phase': 'phase2',
            'round_type': 'lower',
            'round_name': 'p2_lb_r1_m2',
            'label': 'Nhánh thua - Vòng 1 Trận 2',
            'team_a_source': {'type': 'match_loser', 'value': 'p2_ub_qf3'},
            'team_b_source': {'type': 'match_loser', 'value': 'p2_ub_qf4'},
            'bo': 3,
        },
        # Lower Quarterfinals (2 matches)
        {
            'match_code': 'P2_LB_QF1',
            'phase': 'phase2',
            'round_type': 'lower',
            'round_name': 'p2_lb_qf1',
            'label': 'Nhánh thua - Tứ kết 1',
            'team_a_source': {'type': 'match_loser', 'value': 'p2_ub_sf2'},
            'team_b_source': {'type': 'match_winner', 'value': 'p2_lb_r1_m1'},
            'bo': 3,
        },
        {
            'match_code': 'P2_LB_QF2',
            'phase': 'phase2',
            'round_type': 'lower',
            'round_name': 'p2_lb_qf2',
            'label': 'Nhánh thua - Tứ kết 2',
            'team_a_source': {'type': 'match_loser', 'value': 'p2_ub_sf1'},
            'team_b_source': {'type': 'match_winner', 'value': 'p2_lb_r1_m2'},
            'bo': 3,
        },
        # Upper Final (1 match) -> Winner enters Grand Final and earns EWC spot!
        {
            'match_code': 'P2_UB_F',
            'phase': 'phase2',
            'round_type': 'upper',
            'round_name': 'p2_ub_f',
            'label': 'Chung kết nhánh thắng (Tranh vé EWC)',
            'team_a_source': {'type': 'match_winner', 'value': 'p2_ub_sf1'},
            'team_b_source': {'type': 'match_winner', 'value': 'p2_ub_sf2'},
            'bo': 3,
            'is_decider': True,
        },
        # Lower Semifinals (1 match)
        {
            'match_code': 'P2_LB_SF',
            'phase': 'phase2',
            'round_type': 'lower',
            'round_name': 'p2_lb_sf',
            'label': 'Nhánh thua - Bán kết',
            'team_a_source': {'type': 'match_winner', 'value': 'p2_lb_qf1'},
            'team_b_source': {'type': 'match_winner', 'value': 'p2_lb_qf2'},
            'bo': 3,
        },
        # Lower Final (1 match) -> Winner enters Grand Final and earns EWC spot!
        {
            'match_code': 'P2_LB_F',
            'phase': 'phase2',
            'round_type': 'lower',
            'round_name': 'p2_lb_f',
            'label': 'Chung kết nhánh thua (Tranh vé EWC)',
            'team_a_source': {'type': 'match_loser', 'value': 'p2_ub_f'},
            'team_b_source': {'type': 'match_winner', 'value': 'p2_lb_sf'},
            'bo': 3,
            'is_decider': True,
        },
        # Grand Final (1 match) -> Winner is EWC Pool 3, Loser is EWC Pool 4
        {
            'match_code': 'P2_GF',
            'phase': 'phase2',
            'round_type': 'final',
            'round_name': 'p2_gf',
            'label': 'Tổng Chung kết EWC Qualifier',
            'team_a_source': {'type': 'match_winner', 'value': 'p2_ub_f'},
            'team_b_source': {'type': 'match_winner', 'value': 'p2_lb_f'},
            'bo': 3,
            'is_decider': True,
        },
    ]


def _gen_map_score_internal(winner_rating: int, loser_rating: int) -> Tuple[int, int]:
    diff = winner_rating - loser_rating
    if diff >= 25:
        score_pool = [(13, 2), (13, 3), (13, 4), (13, 5), (13, 6)]
    elif diff >= 15:
        score_pool = [(13, 4), (13, 5), (13, 6), (13, 7), (13, 8)]
    elif diff >= 8:
        score_pool = [(13, 6), (13, 7), (13, 8), (13, 9), (13, 10)]
    elif diff >= 2:
        score_pool = [(13, 8), (13, 9), (13, 10), (13, 11)]
    elif diff >= -5:
        score_pool = [(13, 9), (13, 10), (13, 11), (14, 12), (15, 13)]
    elif diff >= -15:
        score_pool = [(13, 10), (13, 11), (14, 12), (15, 13)]
    else:
        score_pool = [(13, 11), (14, 12), (15, 13), (16, 14), (17, 15)]
    return random.choice(score_pool)


def simulate_single_match(team_a: Dict[str, Any], team_b: Dict[str, Any], bo: int = 3,
                          rating_lookup: Optional[Dict[int, int]] = None,
                          form_lookup: Optional[Dict[int, int]] = None) -> Dict[str, Any]:
    id_a = team_a['id']
    id_b = team_b['id']

    r_a = (rating_lookup.get(id_a) if rating_lookup else None) or team_a.get('story_rating') or team_a.get('current_rating') or team_a.get('rating') or 80
    r_b = (rating_lookup.get(id_b) if rating_lookup else None) or team_b.get('story_rating') or team_b.get('current_rating') or team_b.get('rating') or 80

    f_a = (form_lookup.get(id_a) if form_lookup else None) or team_a.get('form_modifier') or 0
    f_b = (form_lookup.get(id_b) if form_lookup else None) or team_b.get('form_modifier') or 0

    eff_a = r_a + f_a
    eff_b = r_b + f_b

    diff = eff_a - eff_b
    prob_a = max(0.15, min(0.85, 0.50 + diff * 0.0125))

    target_wins = (bo // 2) + 1
    max_maps = bo

    wins_a = 0
    wins_b = 0
    maps = []

    for map_idx in range(max_maps):
        roll = random.random()
        if roll < prob_a:
            wins_a += 1
            w_score, l_score = _gen_map_score_internal(eff_a, eff_b)
            maps.append({
                'map_number': map_idx + 1,
                'team_a_score': w_score,
                'team_b_score': l_score,
                'winner': team_a['short_code'],
            })
        else:
            wins_b += 1
            w_score, l_score = _gen_map_score_internal(eff_b, eff_a)
            maps.append({
                'map_number': map_idx + 1,
                'team_a_score': l_score,
                'team_b_score': w_score,
                'winner': team_b['short_code'],
            })

        if wins_a == target_wins or wins_b == target_wins:
            break

    winner = team_a if wins_a > wins_b else team_b
    loser = team_b if wins_a > wins_b else team_a

    return {
        'team_a_score': wins_a,
        'team_b_score': wins_b,
        'winner_id': winner['id'],
        'loser_id': loser['id'],
        'winner': winner,
        'loser': loser,
        'maps': maps,
        'is_manual': False,
    }


def init_ewc_qualifier_region_state(region_slug: str,
                                    phase1_teams: List[Dict[str, Any]],
                                    phase2_direct_teams: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Initialize state for EWC Regional Qualifier:
    - 16 teams in Phase 1 (Seeds 1-4: S1 ranks 9-12; Seeds 5-16: challengers)
    - 6 teams directly in Phase 2 (Seeds 1-6: S1 ranks 3-8)
    - Phase 1 bracket with 14 matches (Round 1 initialized with seeds)
    - Phase 2 bracket with 14 matches (pending until Phase 1 qualifiers advance)
    """
    if len(phase1_teams) != 16:
        raise ValueError(f"EWC Qualifier Phase 1 requires 16 teams, received {len(phase1_teams)}")
    if len(phase2_direct_teams) != 6:
        raise ValueError(f"EWC Qualifier Phase 2 requires 6 direct teams, received {len(phase2_direct_teams)}")

    # Normalize teams
    norm_p1 = []
    for idx, t in enumerate(phase1_teams):
        item = dict(t)
        item['id'] = item.get('id') or item.get('club_id')
        item['seed'] = idx + 1
        norm_p1.append(item)

    norm_p2_direct = []
    for idx, t in enumerate(phase2_direct_teams):
        item = dict(t)
        item['id'] = item.get('id') or item.get('club_id')
        item['seed'] = idx + 1
        norm_p2_direct.append(item)

    p1_seed_map = {t['seed']: t for t in norm_p1}

    # Initialize Phase 1 matches
    p1_templates = get_phase1_bracket_templates()
    p1_matches = []
    for idx, tpl in enumerate(p1_templates):
        m_id = f"ewcq_{region_slug}_{tpl['round_name']}"
        team_a = None
        team_b = None
        if tpl['team_a_source']['type'] == 'seed':
            team_a = p1_seed_map.get(tpl['team_a_source']['value'])
        if tpl['team_b_source']['type'] == 'seed':
            team_b = p1_seed_map.get(tpl['team_b_source']['value'])

        p1_matches.append({
            'id': m_id,
            'match_code': tpl['match_code'],
            'phase': 'phase1',
            'round_name': tpl['round_name'],
            'round_type': tpl['round_type'],
            'label': tpl['label'],
            'match_order': idx + 1,
            'bo': tpl['bo'],
            'status': 'pending',
            'team_a_source': tpl['team_a_source'],
            'team_b_source': tpl['team_b_source'],
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
            'is_decider': tpl.get('is_decider', False),
        })

    # Initialize Phase 2 matches
    p2_templates = get_phase2_bracket_templates()
    p2_matches = []
    for idx, tpl in enumerate(p2_templates):
        m_id = f"ewcq_{region_slug}_{tpl['round_name']}"
        p2_matches.append({
            'id': m_id,
            'match_code': tpl['match_code'],
            'phase': 'phase2',
            'round_name': tpl['round_name'],
            'round_type': tpl['round_type'],
            'label': tpl['label'],
            'match_order': idx + 15,
            'bo': tpl['bo'],
            'status': 'pending',
            'team_a_source': tpl['team_a_source'],
            'team_b_source': tpl['team_b_source'],
            'team_a': None,
            'team_b': None,
            'team_a_id': None,
            'team_b_id': None,
            'team_a_score': 0,
            'team_b_score': 0,
            'winner_id': None,
            'loser_id': None,
            'winner': None,
            'loser': None,
            'maps': [],
            'is_manual': False,
            'is_decider': tpl.get('is_decider', False),
        })

    state = {
        'region_slug': region_slug,
        'status': 'in_progress',          # 'in_progress' or 'completed'
        'current_phase': 'phase1',        # 'phase1' -> 'phase2'
        'phase1_teams': norm_p1,
        'phase2_direct_teams': norm_p2_direct,
        'phase1_matches': p1_matches,
        'phase1_qualifiers': [],          # [Winner SF1, Winner SF2]
        'phase2_teams': [],               # 8 teams once Phase 1 concludes
        'phase2_matches': p2_matches,
        'champion': None,                 # EWC Pool 3
        'runner_up': None,                # EWC Pool 4
        'ewc_qualifiers': [],             # [champion, runner_up]
        'standings': [],
    }

    _resolve_bracket_slots(state)
    return state


def _resolve_bracket_slots(region_data: Dict[str, Any]):
    """Dynamically resolve team sources for Phase 1 and Phase 2.
    Cascades reset if an upstream winner/loser changes.
    """
    p1_seed_map = {t['seed']: t for t in region_data.get('phase1_teams', [])}
    p1_matches = region_data.get('phase1_matches', [])
    p1_match_map = {m['round_name']: m for m in p1_matches}

    # Helper to resolve source
    def resolve_team(src, seed_map, match_map):
        if not src:
            return None
        stype = src.get('type')
        sval = src.get('value')
        if stype == 'seed':
            return seed_map.get(sval)
        elif stype == 'match_winner':
            target = match_map.get(sval)
            if target and target.get('status') == 'completed' and target.get('winner'):
                return target['winner']
        elif stype == 'match_loser':
            target = match_map.get(sval)
            if target and target.get('status') == 'completed' and target.get('loser'):
                return target['loser']
        return None

    # 1. Update Phase 1 matches
    for m in p1_matches:
        expected_a = resolve_team(m.get('team_a_source'), p1_seed_map, p1_match_map)
        expected_b = resolve_team(m.get('team_b_source'), p1_seed_map, p1_match_map)

        cur_a_id = m.get('team_a_id')
        cur_b_id = m.get('team_b_id')
        exp_a_id = expected_a['id'] if expected_a else None
        exp_b_id = expected_b['id'] if expected_b else None

        if cur_a_id != exp_a_id or cur_b_id != exp_b_id:
            m['team_a'] = expected_a
            m['team_b'] = expected_b
            m['team_a_id'] = exp_a_id
            m['team_b_id'] = exp_b_id
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

    # Check Phase 1 qualifiers
    sf1 = p1_match_map.get('p1_sf1')
    sf2 = p1_match_map.get('p1_sf2')
    p1_done = (sf1 and sf1.get('status') == 'completed') and (sf2 and sf2.get('status') == 'completed')

    if p1_done:
        q1 = sf1['winner']
        q2 = sf2['winner']
        region_data['phase1_qualifiers'] = [q1, q2]

        # Assemble 8 teams for Phase 2: Seeds 1-6 from direct teams, Seeds 7 & 8 from P1 qualifiers
        p2_teams = []
        for t in region_data.get('phase2_direct_teams', []):
            p2_teams.append(dict(t))
        q1_t = dict(q1)
        q1_t['seed'] = 7
        q2_t = dict(q2)
        q2_t['seed'] = 8
        p2_teams.extend([q1_t, q2_t])
        region_data['phase2_teams'] = p2_teams
        if region_data.get('current_phase') == 'phase1':
            region_data['current_phase'] = 'phase2'
    else:
        region_data['phase1_qualifiers'] = []
        region_data['phase2_teams'] = []
        region_data['current_phase'] = 'phase1'

    # 2. Update Phase 2 matches
    p2_seed_map = {t['seed']: t for t in region_data.get('phase2_teams', [])}
    p2_matches = region_data.get('phase2_matches', [])
    p2_match_map = {m['round_name']: m for m in p2_matches}

    for m in p2_matches:
        expected_a = resolve_team(m.get('team_a_source'), p2_seed_map, p2_match_map)
        expected_b = resolve_team(m.get('team_b_source'), p2_seed_map, p2_match_map)

        cur_a_id = m.get('team_a_id')
        cur_b_id = m.get('team_b_id')
        exp_a_id = expected_a['id'] if expected_a else None
        exp_b_id = expected_b['id'] if expected_b else None

        if cur_a_id != exp_a_id or cur_b_id != exp_b_id:
            m['team_a'] = expected_a
            m['team_b'] = expected_b
            m['team_a_id'] = exp_a_id
            m['team_b_id'] = exp_b_id
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

    # Check Grand Final completion
    gf = p2_match_map.get('p2_gf')
    if gf and gf.get('status') == 'completed' and gf.get('winner'):
        champ = dict(gf['winner'])
        runner = dict(gf['loser'])
        champ['ewc_slot'] = 'Pool 3 (EWC Qualifier Champion)'
        runner['ewc_slot'] = 'Pool 4 (EWC Qualifier Runner-up)'
        region_data['champion'] = champ
        region_data['runner_up'] = runner
        region_data['ewc_qualifiers'] = [champ, runner]
        region_data['matches_completed'] = True
        region_data['status'] = 'completed'
    else:
        region_data['champion'] = None
        region_data['runner_up'] = None
        region_data['ewc_qualifiers'] = []
        region_data['status'] = 'in_progress'


def resolve_ewc_qualifier_match(region_data: Dict[str, Any], match_id: str,
                                winner_id: Optional[int] = None,
                                maps: Optional[List[Dict[str, Any]]] = None,
                                rating_lookup: Optional[Dict[int, int]] = None,
                                form_lookup: Optional[Dict[int, int]] = None) -> Dict[str, Any]:
    """Resolve a single match in EWC Qualifier (Phase 1 or Phase 2).
    Supports simulation (winner_id is None) and manual score input (winner_id provided).
    """
    target = None
    for m in region_data.get('phase1_matches', []) + region_data.get('phase2_matches', []):
        if m['id'] == match_id:
            target = m
            break

    if not target:
        raise ValueError(f"Match {match_id} not found in region {region_data.get('region_slug')}")

    if region_data.get('is_confirmed'):
        raise ValueError(f"Không thể chỉnh sửa trận đấu vì kết quả EWC Qualifier của khu vực {region_data.get('region_slug')} đã được xác nhận và khóa chính thức!")

    if not target.get('team_a') or not target.get('team_b'):
        raise ValueError(f"Match {match_id} cannot be played yet; participants not fully determined.")

    team_a = target['team_a']
    team_b = target['team_b']
    bo = target.get('bo', 3)

    if winner_id is not None:
        # Manual score override
        if winner_id not in (team_a['id'], team_b['id']):
            raise ValueError(f"winner_id {winner_id} is neither team A ({team_a['id']}) nor team B ({team_b['id']})")
        winner = team_a if winner_id == team_a['id'] else team_b
        loser = team_b if winner_id == team_a['id'] else team_a

        target_wins = (bo // 2) + 1
        if maps and len(maps) > 0:
            wins_a = sum(1 for mp in maps if mp.get('winner') == team_a.get('short_code'))
            wins_b = sum(1 for mp in maps if mp.get('winner') == team_b.get('short_code'))
        else:
            wins_a = target_wins if winner_id == team_a['id'] else max(0, target_wins - 1)
            wins_b = target_wins if winner_id == team_b['id'] else max(0, target_wins - 1)
            maps = []
            for m_i in range(wins_a + wins_b):
                if m_i < min(wins_a, wins_b) * 2:
                    sub_win = team_a if (m_i % 2 == 0) else team_b
                else:
                    sub_win = winner
                maps.append({
                    'map_number': m_i + 1,
                    'team_a_score': 13 if sub_win['id'] == team_a['id'] else 9,
                    'team_b_score': 13 if sub_win['id'] == team_b['id'] else 9,
                    'winner': sub_win['short_code'],
                })

        target['winner_id'] = winner['id']
        target['loser_id'] = loser['id']
        target['winner'] = winner
        target['loser'] = loser
        target['team_a_score'] = wins_a
        target['team_b_score'] = wins_b
        target['maps'] = maps
        target['status'] = 'completed'
        target['is_manual'] = True
    else:
        # Simulated roll
        sim_res = simulate_single_match(team_a, team_b, bo=bo,
                                        rating_lookup=rating_lookup,
                                        form_lookup=form_lookup)
        target['winner_id'] = sim_res['winner_id']
        target['loser_id'] = sim_res['loser_id']
        target['winner'] = sim_res['winner']
        target['loser'] = sim_res['loser']
        target['team_a_score'] = sim_res['team_a_score']
        target['team_b_score'] = sim_res['team_b_score']
        target['maps'] = sim_res['maps']
        target['status'] = 'completed'
        target['is_manual'] = False

    # Recalculate bracket slots and cascade
    _resolve_bracket_slots(region_data)
    return target


def sim_ewc_qualifier_round(region_data: Dict[str, Any],
                            rating_lookup: Optional[Dict[int, int]] = None,
                            form_lookup: Optional[Dict[int, int]] = None) -> List[Dict[str, Any]]:
    """Simulate all currently playable pending matches in the active phase."""
    _resolve_bracket_slots(region_data)
    active_matches = (
        region_data.get('phase1_matches', [])
        if region_data.get('current_phase') == 'phase1'
        else region_data.get('phase2_matches', [])
    )

    playable = [
        m for m in active_matches
        if m.get('status') == 'pending' and m.get('team_a') and m.get('team_b')
    ]

    resolved_list = []
    for m in playable:
        res = resolve_ewc_qualifier_match(
            region_data, m['id'],
            rating_lookup=rating_lookup,
            form_lookup=form_lookup,
        )
        resolved_list.append(res)

    return resolved_list


def sim_ewc_qualifier_remaining(region_data: Dict[str, Any],
                                rating_lookup: Optional[Dict[int, int]] = None,
                                form_lookup: Optional[Dict[int, int]] = None) -> int:
    """Simulate all remaining matches until the regional qualifier is completed."""
    max_loops = 50
    loops = 0
    total_played = 0
    while region_data.get('status') != 'completed' and loops < max_loops:
        loops += 1
        resolved = sim_ewc_qualifier_round(region_data, rating_lookup, form_lookup)
        if not resolved:
            break
        total_played += len(resolved)

    return total_played


def simulate_ewc_qualifier(region_slug: str,
                           phase1_teams: List[Dict[str, Any]],
                           phase2_direct_teams: List[Dict[str, Any]],
                           rating_lookup: Optional[Dict[int, int]] = None,
                           form_lookup: Optional[Dict[int, int]] = None) -> Dict[str, Any]:
    """Execute a complete simulated run of the EWC Regional Qualifier."""
    state = init_ewc_qualifier_region_state(region_slug, phase1_teams, phase2_direct_teams)
    sim_ewc_qualifier_remaining(state, rating_lookup, form_lookup)
    return state
