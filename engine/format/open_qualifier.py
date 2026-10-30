"""
engine/format/open_qualifier.py — Open Qualifier Format Engine

Format Specification:
- 16 Non-partner clubs per region
- Objective: Select exactly 4 teams for Kickoff (joining 8 partner teams)
- Stage 1: Swiss Stage (16 teams, 3-Win advance / 3-Loss eliminate, max 5 rounds, exactly 33 matches)
  * Round 1: 8 BO1 (all 0-0)
  * Round 2: 8 BO1 (4 High 1-0, 4 Low 0-1)
  * Round 3: 4 BO3 + 4 BO1 (2 High 2-0 BO3, 4 Mid 1-1 BO1, 2 Low 0-2 BO3)
  * Round 4: 6 BO3 (3 High 2-1 BO3, 3 Low 1-2 BO3)
  * Round 5: 3 BO3 (3 Decider 2-2 BO3)
  Total Swiss = 8 + 8 + 8 + 6 + 3 = 33 matches.
  Advancing: 8 teams (2 at 3-0, 3 at 3-1, 3 at 3-2)
  Eliminated: 8 teams (2 at 0-3, 3 at 1-3, 3 at 2-3)

- Stage 2: Playoffs (8 teams, Double Elimination to 4 qualifiers, exactly 10 BO3 matches)
  * Upper R1: M1 (1v8), M2 (4v5), M3 (2v7), M4 (3v6)
  * Upper R2: M5 (W1 v W2 -> Winner Qualifies #1), M6 (W3 v W4 -> Winner Qualifies #2)
  * Lower R1: M7 (L1 v L2 -> Loser out), M8 (L3 v L4 -> Loser out)
  * Lower Qual: M9 (W7 v L5 -> Winner Qualifies #3), M10 (W8 v L6 -> Winner Qualifies #4)
  Total Playoffs = 4 + 2 + 2 + 2 = 10 matches.
  Grand Total = 33 + 10 = 43 matches per region.
"""

import random
from typing import List, Dict, Tuple, Optional, Any


def open_qualifier_config() -> Dict[str, Any]:
    return {
        'team_count': 16,
        'advance_count': 4,
        'swiss_win_target': 3,
        'swiss_loss_target': 3,
        'swiss_max_rounds': 5,
        'swiss_advancers': 8,
        'swiss_matches_total': 33,
        'playoff_matches_total': 10,
        'total_matches': 43,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Swiss Stage Helpers & Standings
# ─────────────────────────────────────────────────────────────────────────────

def compute_swiss_records(teams: List[Dict[str, Any]], completed_matches: List[Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
    """Compute W-L records, map scores, and opponents for Swiss stage.
    
    Each match in completed_matches is expected to have:
    - team_a_id, team_b_id, winner_id
    - team_a_score, team_b_score (map scores, e.g. 1-0 for BO1 or 2-0/2-1 for BO3)
    """
    records = {
        t['id']: {
            'wins': 0,
            'losses': 0,
            'maps_won': 0,
            'maps_lost': 0,
            'opponents': [],
        }
        for t in teams
    }

    for m in completed_matches:
        a_id = m.get('team_a_id')
        b_id = m.get('team_b_id')
        w_id = m.get('winner_id')
        if not a_id or not b_id or not w_id:
            continue
        if a_id not in records or b_id not in records:
            continue

        records[a_id]['opponents'].append(b_id)
        records[b_id]['opponents'].append(a_id)

        a_score = m.get('team_a_score', 0) or 0
        b_score = m.get('team_b_score', 0) or 0
        records[a_id]['maps_won'] += a_score
        records[a_id]['maps_lost'] += b_score
        records[b_id]['maps_won'] += b_score
        records[b_id]['maps_lost'] += a_score

        if w_id == a_id:
            records[a_id]['wins'] += 1
            records[b_id]['losses'] += 1
        elif w_id == b_id:
            records[b_id]['wins'] += 1
            records[a_id]['losses'] += 1

    return records


def compute_swiss_standings(teams: List[Dict[str, Any]], completed_matches: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Calculate Swiss standings sorted by:
    1. Wins desc, Losses asc
    2. Buchholz score (sum of opponents' wins) desc
    3. Map difference (maps won - maps lost) desc
    4. Team rating/seed desc
    """
    records = compute_swiss_records(teams, completed_matches)
    team_dict = {t['id']: t for t in teams}

    standings = []
    for t_id, r in records.items():
        team = team_dict[t_id]
        buchholz = sum(records[opp_id]['wins'] for opp_id in r['opponents'] if opp_id in records)
        map_diff = r['maps_won'] - r['maps_lost']
        advanced = r['wins'] >= 3
        eliminated = r['losses'] >= 3

        standings.append({
            'team': team,
            'club_id': t_id,
            'wins': r['wins'],
            'losses': r['losses'],
            'buchholz': buchholz,
            'maps_won': r['maps_won'],
            'maps_lost': r['maps_lost'],
            'map_diff': map_diff,
            'advanced': advanced,
            'eliminated': eliminated,
            'opponents': r['opponents'],
        })

    standings.sort(key=lambda s: (
        -s['wins'],
        s['losses'],
        -s['buchholz'],
        -s['map_diff'],
        -(s['team'].get('current_rating') or s['team'].get('story_rating') or s['team'].get('rating') or 80)
    ))

    for idx, s in enumerate(standings, 1):
        s['rank'] = idx

    return standings


# ─────────────────────────────────────────────────────────────────────────────
# Swiss Pairing Logic
# ─────────────────────────────────────────────────────────────────────────────

def _pair_bracket_group(teams: List[Dict[str, Any]], past_opponents: Dict[int, set], max_retries: int = 500) -> Optional[List[Tuple[Dict[str, Any], Dict[str, Any]]]]:
    """Pair an even number of teams within the same record group without rematches."""
    n = len(teams)
    if n % 2 != 0:
        return None
    if n == 0:
        return []

    for _ in range(max_retries):
        shuffled = list(teams)
        random.shuffle(shuffled)
        pairs = []
        valid = True
        for i in range(0, n, 2):
            t1, t2 = shuffled[i], shuffled[i + 1]
            if t2['id'] in past_opponents.get(t1['id'], set()):
                valid = False
                break
            pairs.append((t1, t2))
        if valid:
            return pairs

    # Backtracking fallback if random shuffle didn't find match
    def backtrack(remaining: List[Dict[str, Any]], current_pairs: List[Tuple[Dict[str, Any], Dict[str, Any]]]):
        if not remaining:
            return current_pairs
        first = remaining[0]
        for idx in range(1, len(remaining)):
            candidate = remaining[idx]
            if candidate['id'] not in past_opponents.get(first['id'], set()):
                next_rem = [t for i, t in enumerate(remaining) if i != 0 and i != idx]
                res = backtrack(next_rem, current_pairs + [(first, candidate)])
                if res is not None:
                    return res
        return None

    return backtrack(list(teams), [])


def generate_swiss_round_pairings(teams: List[Dict[str, Any]], current_round: int, completed_matches: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Generate match pairings for a given Swiss round (1 to 5).
    
    Returns a list of match specifications:
    [{'round': round_num, 'match_name': str, 'bo': 1 or 3, 'team_a': dict, 'team_b': dict, 'is_decider': bool}, ...]
    """
    if current_round < 1 or current_round > 5:
        return []

    records = compute_swiss_records(teams, completed_matches)
    past_opponents = {t['id']: set(records[t['id']]['opponents']) for t in teams}

    # Round 1: 16 teams, all 0-0. 8 BO1 matches.
    if current_round == 1:
        shuffled = list(teams)
        # Sort or randomize: Seed 1-8 vs Seed 9-16 or random
        random.shuffle(shuffled)
        pairings = []
        for i in range(8):
            pairings.append({
                'round': 1,
                'match_name': f'swiss_r1_m{i+1}',
                'bo': 1,
                'team_a': shuffled[i * 2],
                'team_b': shuffled[i * 2 + 1],
                'is_decider': False,
                'record_group': '0-0',
            })
        return pairings

    # Active teams (not 3 wins, not 3 losses)
    active = [t for t in teams if records[t['id']]['wins'] < 3 and records[t['id']]['losses'] < 3]

    # Group by (wins, losses)
    groups: Dict[Tuple[int, int], List[Dict[str, Any]]] = {}
    for t in active:
        key = (records[t['id']]['wins'], records[t['id']]['losses'])
        groups.setdefault(key, []).append(t)

    pairings = []
    match_counter = 1

    if current_round == 2:
        # High (1-0): 8 teams -> 4 BO1
        # Low (0-1): 8 teams -> 4 BO1
        for key in [(1, 0), (0, 1)]:
            grp = groups.get(key, [])
            pairs = _pair_bracket_group(grp, past_opponents)
            if pairs is None:
                # Emergency fallback: pair in order
                pairs = [(grp[i], grp[i + 1]) for i in range(0, len(grp), 2)]
            for t_a, t_b in pairs:
                pairings.append({
                    'round': 2,
                    'match_name': f'swiss_r2_m{match_counter}',
                    'bo': 1,
                    'team_a': t_a,
                    'team_b': t_b,
                    'is_decider': False,
                    'record_group': f'{key[0]}-{key[1]}',
                })
                match_counter += 1

    elif current_round == 3:
        # High (2-0): 4 teams -> 2 BO3 (Decider for Playoffs)
        # Mid (1-1): 8 teams -> 4 BO1 (Non-deciding)
        # Low (0-2): 4 teams -> 2 BO3 (Decider for Elimination)
        for key, bo, is_decider in [((2, 0), 3, True), ((1, 1), 1, False), ((0, 2), 3, True)]:
            grp = groups.get(key, [])
            pairs = _pair_bracket_group(grp, past_opponents)
            if pairs is None:
                pairs = [(grp[i], grp[i + 1]) for i in range(0, len(grp), 2)]
            for t_a, t_b in pairs:
                pairings.append({
                    'round': 3,
                    'match_name': f'swiss_r3_m{match_counter}',
                    'bo': bo,
                    'team_a': t_a,
                    'team_b': t_b,
                    'is_decider': is_decider,
                    'record_group': f'{key[0]}-{key[1]}',
                })
                match_counter += 1

    elif current_round == 4:
        # High (2-1): 6 teams -> 3 BO3 (Decider for Playoffs)
        # Low (1-2): 6 teams -> 3 BO3 (Decider for Elimination)
        for key in [(2, 1), (1, 2)]:
            grp = groups.get(key, [])
            pairs = _pair_bracket_group(grp, past_opponents)
            if pairs is None:
                pairs = [(grp[i], grp[i + 1]) for i in range(0, len(grp), 2)]
            for t_a, t_b in pairs:
                pairings.append({
                    'round': 4,
                    'match_name': f'swiss_r4_m{match_counter}',
                    'bo': 3,
                    'team_a': t_a,
                    'team_b': t_b,
                    'is_decider': True,
                    'record_group': f'{key[0]}-{key[1]}',
                })
                match_counter += 1

    elif current_round == 5:
        # Decider (2-2): 6 teams -> 3 BO3 (Winners to Playoffs, Losers eliminated)
        grp = groups.get((2, 2), [])
        pairs = _pair_bracket_group(grp, past_opponents)
        if pairs is None:
            pairs = [(grp[i], grp[i + 1]) for i in range(0, len(grp), 2)]
        for t_a, t_b in pairs:
            pairings.append({
                'round': 5,
                'match_name': f'swiss_r5_m{match_counter}',
                'bo': 3,
                'team_a': t_a,
                'team_b': t_b,
                'is_decider': True,
                'record_group': '2-2',
            })
            match_counter += 1

    return pairings


# ─────────────────────────────────────────────────────────────────────────────
# Playoffs Double Elimination Stage (8 teams -> 4 qualifiers)
# ─────────────────────────────────────────────────────────────────────────────

def get_playoff_bracket_templates() -> List[Dict[str, Any]]:
    """Return template structure for the 10-match playoff bracket.
    
    Structure:
    - Upper R1: M1 (S1 vs S8), M2 (S4 vs S5), M3 (S2 vs S7), M4 (S3 vs S6)
    - Upper R2: M5 (W1 vs W2 -> Qual 1), M6 (W3 vs W4 -> Qual 2)
    - Lower R1: M7 (L1 vs L2 -> Loser out), M8 (L3 vs L4 -> Loser out)
    - Lower Qual: M9 (W7 vs L5 -> Qual 3), M10 (W8 vs L6 -> Qual 4)
    """
    return [
        {
            'match_code': 'M1',
            'round_type': 'upper',
            'round_name': 'upper_r1_m1',
            'label': 'Upper R1 Match 1',
            'team_a_source': {'type': 'seed', 'value': 1},
            'team_b_source': {'type': 'seed', 'value': 8},
            'bo': 3,
        },
        {
            'match_code': 'M2',
            'round_type': 'upper',
            'round_name': 'upper_r1_m2',
            'label': 'Upper R1 Match 2',
            'team_a_source': {'type': 'seed', 'value': 4},
            'team_b_source': {'type': 'seed', 'value': 5},
            'bo': 3,
        },
        {
            'match_code': 'M3',
            'round_type': 'upper',
            'round_name': 'upper_r1_m3',
            'label': 'Upper R1 Match 3',
            'team_a_source': {'type': 'seed', 'value': 2},
            'team_b_source': {'type': 'seed', 'value': 7},
            'bo': 3,
        },
        {
            'match_code': 'M4',
            'round_type': 'upper',
            'round_name': 'upper_r1_m4',
            'label': 'Upper R1 Match 4',
            'team_a_source': {'type': 'seed', 'value': 3},
            'team_b_source': {'type': 'seed', 'value': 6},
            'bo': 3,
        },
        {
            'match_code': 'M5',
            'round_type': 'upper',
            'round_name': 'upper_r2_m5',
            'label': 'Upper R2 (Qualification 1)',
            'team_a_source': {'type': 'winner_of', 'value': 'upper_r1_m1'},
            'team_b_source': {'type': 'winner_of', 'value': 'upper_r1_m2'},
            'bo': 3,
            'qualifier_slot': 1,  # Winner earns Kickoff Qualifier #1
        },
        {
            'match_code': 'M6',
            'round_type': 'upper',
            'round_name': 'upper_r2_m6',
            'label': 'Upper R2 (Qualification 2)',
            'team_a_source': {'type': 'winner_of', 'value': 'upper_r1_m3'},
            'team_b_source': {'type': 'winner_of', 'value': 'upper_r1_m4'},
            'bo': 3,
            'qualifier_slot': 2,  # Winner earns Kickoff Qualifier #2
        },
        {
            'match_code': 'M7',
            'round_type': 'lower',
            'round_name': 'lower_r1_m7',
            'label': 'Lower R1 Match 1',
            'team_a_source': {'type': 'loser_of', 'value': 'upper_r1_m1'},
            'team_b_source': {'type': 'loser_of', 'value': 'upper_r1_m2'},
            'bo': 3,
        },
        {
            'match_code': 'M8',
            'round_type': 'lower',
            'round_name': 'lower_r1_m8',
            'label': 'Lower R1 Match 2',
            'team_a_source': {'type': 'loser_of', 'value': 'upper_r1_m3'},
            'team_b_source': {'type': 'loser_of', 'value': 'upper_r1_m4'},
            'bo': 3,
        },
        {
            'match_code': 'M9',
            'round_type': 'lower',
            'round_name': 'lower_qual_m9',
            'label': 'Lower Qualification (Slot 3)',
            'team_a_source': {'type': 'winner_of', 'value': 'lower_r1_m7'},
            'team_b_source': {'type': 'loser_of', 'value': 'upper_r2_m5'},
            'bo': 3,
            'qualifier_slot': 3,  # Winner earns Kickoff Qualifier #3
        },
        {
            'match_code': 'M10',
            'round_type': 'lower',
            'round_name': 'lower_qual_m10',
            'label': 'Lower Qualification (Slot 4)',
            'team_a_source': {'type': 'winner_of', 'value': 'lower_r1_m8'},
            'team_b_source': {'type': 'loser_of', 'value': 'upper_r2_m6'},
            'bo': 3,
            'qualifier_slot': 4,  # Winner earns Kickoff Qualifier #4
        },
    ]


def resolve_playoff_sources(template: Dict[str, Any], seeds: Dict[int, Dict[str, Any]], completed_matches: Dict[str, Dict[str, Any]]) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """Resolve team_a and team_b for a playoff match template."""
    def resolve_source(src: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        stype = src.get('type')
        sval = src.get('value')
        if stype == 'seed':
            return seeds.get(sval)
        if stype == 'winner_of':
            m = completed_matches.get(sval)
            return m.get('winner') if m else None
        if stype == 'loser_of':
            m = completed_matches.get(sval)
            return m.get('loser') if m else None
        return None

    team_a = resolve_source(template['team_a_source'])
    team_b = resolve_source(template['team_b_source'])
    return team_a, team_b


# ─────────────────────────────────────────────────────────────────────────────
# Match Simulation & Map Score Logic for Regional Matches
# ─────────────────────────────────────────────────────────────────────────────

def _gen_map_score_internal(winner_rating: int, loser_rating: int) -> Tuple[int, int]:
    """Generate map score based on power rating difference."""
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


def simulate_single_match(team_a: Dict[str, Any], team_b: Dict[str, Any], bo: int = 1,
                          rating_lookup: Optional[Dict[int, int]] = None,
                          form_lookup: Optional[Dict[int, int]] = None) -> Dict[str, Any]:
    """Simulate a match between team_a and team_b using effective rating (story_rating + form).
    
    Regional Match Philosophy:
    - Base win probability is scaled smoothly by effective rating difference:
      prob_a = 0.50 + (effective_a - effective_b) * 0.0125
      clamped to [0.15, 0.85].
    - Map scores reflect rating difference.
    - bo: 1 (BO1, target 1) or 3 (BO3, target 2).
    """
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

    target_wins = 1 if bo == 1 else 2
    max_maps = 1 if bo == 1 else 3

    wins_a = 0
    wins_b = 0
    maps = []

    for map_idx in range(max_maps):
        roll = random.random()
        if roll < prob_a:
            sc_win, sc_lose = _gen_map_score_internal(eff_a, eff_b)
            wins_a += 1
            maps.append({
                'map_number': map_idx + 1,
                'team_a_score': sc_win,
                'team_b_score': sc_lose,
                'winner_id': id_a,
            })
        else:
            sc_win, sc_lose = _gen_map_score_internal(eff_b, eff_a)
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

    return {
        'team_a': team_a,
        'team_b': team_b,
        'team_a_id': id_a,
        'team_b_id': id_b,
        'team_a_score': wins_a,
        'team_b_score': wins_b,
        'winner': winner,
        'loser': loser,
        'winner_id': winner['id'],
        'loser_id': loser['id'],
        'maps': maps,
        'bo': bo,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Master Regional Simulation Function
# ─────────────────────────────────────────────────────────────────────────────

def simulate_open_qualifier(region_slug: str, teams: List[Dict[str, Any]],
                            rating_lookup: Optional[Dict[int, int]] = None,
                            form_lookup: Optional[Dict[int, int]] = None) -> Dict[str, Any]:
    """Execute the full 43-match Open Qualifier tournament for a region.
    
    Args:
        region_slug: e.g. 'pacific', 'americas', 'emea', 'china'
        teams: List of 16 non-partner team dicts
        rating_lookup: Optional dict of {club_id: story_rating}
        form_lookup: Optional dict of {club_id: form_modifier}
        
    Returns:
        {
            'region_slug': str,
            'swiss_matches': list of 33 match dicts,
            'swiss_standings': list of 16 standings dicts (ranked 1-16),
            'swiss_qualifiers': list of 8 advancing teams (seeds 1-8 for playoffs),
            'swiss_eliminated': list of 8 eliminated teams,
            'playoff_matches': list of 10 match dicts,
            'qualified_teams': list of 4 teams qualifying for Kickoff,
            'total_matches_count': 43,
        }
    """
    if len(teams) != 16:
        raise ValueError(f"Open Qualifier requires exactly 16 teams, received {len(teams)}")

    # ──────────────── Stage 1: Swiss (33 matches) ────────────────
    all_swiss_matches: List[Dict[str, Any]] = []

    for round_num in range(1, 6):
        round_pairings = generate_swiss_round_pairings(teams, round_num, all_swiss_matches)
        for p in round_pairings:
            sim = simulate_single_match(
                p['team_a'], p['team_b'], bo=p['bo'],
                rating_lookup=rating_lookup, form_lookup=form_lookup
            )
            sim.update({
                'round': round_num,
                'round_name': p['match_name'],
                'record_group': p['record_group'],
                'is_decider': p['is_decider'],
            })
            all_swiss_matches.append(sim)

    swiss_standings = compute_swiss_standings(teams, all_swiss_matches)
    swiss_qualifiers = [s['team'] for s in swiss_standings if s['advanced']]
    swiss_eliminated = [s['team'] for s in swiss_standings if s['eliminated']]

    if len(swiss_qualifiers) != 8:
        raise RuntimeError(f"Expected 8 Swiss qualifiers, got {len(swiss_qualifiers)}")

    # Map Swiss qualifiers to Seed 1..8
    seeds: Dict[int, Dict[str, Any]] = {i + 1: swiss_qualifiers[i] for i in range(8)}

    # ──────────────── Stage 2: Playoffs (10 matches) ────────────────
    playoff_templates = get_playoff_bracket_templates()
    completed_playoffs: Dict[str, Dict[str, Any]] = {}
    playoff_matches_list: List[Dict[str, Any]] = []
    qualifiers_dict: Dict[int, Dict[str, Any]] = {}

    for tpl in playoff_templates:
        t_a, t_b = resolve_playoff_sources(tpl, seeds, completed_playoffs)
        if not t_a or not t_b:
            raise RuntimeError(f"Playoff match {tpl['round_name']} could not resolve teams")

        sim = simulate_single_match(
            t_a, t_b, bo=tpl['bo'],
            rating_lookup=rating_lookup, form_lookup=form_lookup
        )
        sim.update({
            'round_name': tpl['round_name'],
            'round_type': tpl['round_type'],
            'match_code': tpl['match_code'],
            'label': tpl['label'],
        })

        completed_playoffs[tpl['round_name']] = sim
        playoff_matches_list.append(sim)

        if 'qualifier_slot' in tpl:
            slot = tpl['qualifier_slot']
            qualifiers_dict[slot] = sim['winner']

    # Exactly 4 qualifiers sorted by slot 1, 2, 3, 4
    qualified_teams = [qualifiers_dict[i] for i in [1, 2, 3, 4]]

    return {
        'region_slug': region_slug,
        'swiss_matches': all_swiss_matches,
        'swiss_standings': swiss_standings,
        'swiss_qualifiers': swiss_qualifiers,
        'swiss_eliminated': swiss_eliminated,
        'playoff_matches': playoff_matches_list,
        'qualified_teams': qualified_teams,
        'total_matches_count': len(all_swiss_matches) + len(playoff_matches_list),
    }
