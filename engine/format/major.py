"""
engine/format/major.py — Major (8-team Swiss 2-win-advance, 4-team Double Elim)

PURE FUNCTIONS. No DB, no Flask, no random for match outcomes.
Only bracket generation, pairing logic, and state computation.
"""

import random


def swiss_config():
    return {
        'win_target': 2,
        'loss_target': 2,
        'advance_count': 4,
        'team_count': 8,
        'bo': 3,
    }


# ────────────────────────────────────────────────
# Swiss Stage pairing
# ────────────────────────────────────────────────

def generate_swiss_pairings(teams, current_round, completed_matches):
    """Return list of (team_a, team_b) for the next round.

    Args:
        teams: list of dicts with {id, region, regional_seed}
        current_round: 1, 2, or 3
        completed_matches: list of {team_a_id, team_b_id, winner_id, round_name}

    Returns: list of (team_a, team_b) where team_a/team_b are team dicts
             Returns [] if Swiss is complete.
    """
    if current_round == 1:
        return _swiss_r1_seed_pairing(teams)
    else:
        return _swiss_same_record_pairing(teams, completed_matches, current_round)


def _swiss_r1_seed_pairing(teams):
    """Round 1: pair seed1 vs seed2 across different regions.

    Uses shuffle-retry until all 4 pairs are cross-region.
    """
    seed1 = [t for t in teams if t.get('regional_seed') == 1]
    seed2 = [t for t in teams if t.get('regional_seed') == 2]

    for _ in range(200):
        s1_shuffled = list(seed1)
        random.shuffle(s1_shuffled)

        available = list(seed2)
        random.shuffle(available)

        pairs = []
        ok = True
        for s1 in s1_shuffled:
            found = None
            for s2 in available:
                if s2['region'] != s1['region']:
                    found = s2
                    break
            if found is None:
                ok = False
                break
            available.remove(found)
            pairs.append((s1, found))

        if ok:
            return pairs

    # Fallback: just shuffle and pair
    all_teams = list(teams)
    random.shuffle(all_teams)
    return [(all_teams[i], all_teams[i + 1]) for i in range(0, len(all_teams), 2)]


def _swiss_same_record_pairing(teams, completed_matches, current_round):
    """Round 2-3: pair teams with same (wins, losses), block rematches."""
    team_map = {t['id']: t for t in teams}
    records = _compute_swiss_records(teams, completed_matches)
    past_opponents = _build_past_opponents(completed_matches)

    # Determine who is still active (not eliminated, not advanced)
    cfg = swiss_config()
    active = [
        t for t in teams
        if records[t['id']]['wins'] < cfg['win_target']
        and records[t['id']]['losses'] < cfg['loss_target']
    ]

    if not active:
        return []

    # Group by record
    record_groups = {}
    for t in active:
        key = (records[t['id']]['wins'], records[t['id']]['losses'])
        record_groups.setdefault(key, []).append(t)

    for _ in range(200):
        pairs = []
        ok = True
        for key, group in record_groups.items():
            shuffled = list(group)
            random.shuffle(shuffled)

            for i in range(0, len(shuffled), 2):
                if i + 1 >= len(shuffled):
                    # Odd number: pair with adjacent record group
                    continue
                a, b = shuffled[i], shuffled[i + 1]

                # Block rematch
                if b['id'] in past_opponents.get(a['id'], set()):
                    ok = False
                    break
                pairs.append((a, b))
            if not ok:
                break

        if ok and len(pairs) == len(active) // 2:
            return pairs

    # Fallback: ignore rematch block
    pairs = []
    for key, group in record_groups.items():
        shuffled = list(group)
        random.shuffle(shuffled)
        for i in range(0, len(shuffled), 2):
            if i + 1 < len(shuffled):
                pairs.append((shuffled[i], shuffled[i + 1]))
    return pairs


def _compute_swiss_records(teams, completed_matches):
    records = {t['id']: {'wins': 0, 'losses': 0} for t in teams}
    for m in completed_matches:
        wid = m.get('winner_id')
        if wid is None:
            continue
        records[m['team_a_id']]['wins'] += int(wid == m['team_a_id'])
        records[m['team_a_id']]['losses'] += int(wid != m['team_a_id'])
        records[m['team_b_id']]['wins'] += int(wid == m['team_b_id'])
        records[m['team_b_id']]['losses'] += int(wid != m['team_b_id'])
    return records


def _build_past_opponents(completed_matches):
    opps = {}
    for m in completed_matches:
        a, b = m['team_a_id'], m['team_b_id']
        opps.setdefault(a, set()).add(b)
        opps.setdefault(b, set()).add(a)
    return opps


def get_swiss_standings(teams, completed_matches):
    """Return standings sorted by (wins desc, losses asc, rating desc)."""
    records = _compute_swiss_records(teams, completed_matches)
    cfg = swiss_config()

    standings = []
    for t in teams:
        r = records[t['id']]
        advanced = r['wins'] >= cfg['win_target']
        eliminated = r['losses'] >= cfg['loss_target']
        standings.append({
            'team': t,
            'wins': r['wins'],
            'losses': r['losses'],
            'advanced': advanced,
            'eliminated': eliminated,
        })

    standings.sort(key=lambda s: (-s['wins'], s['losses'], -(t.get('rating', 0))))
    return standings


# ────────────────────────────────────────────────
# Playoffs: 4-team Double Elimination
# ────────────────────────────────────────────────

def generate_playoffs_4_teams(qualified_teams):
    """Return list of match templates for 4-team Double Elim bracket.

    Args:
        qualified_teams: list of 4 team dicts sorted by seed (best first)

    Returns: list of match templates:
        [{round_type, round_name, team_a_seed, team_b_seed}, ...]
    """
    seeds = sorted(qualified_teams, key=lambda t: t.get('bracket_seed', 0))
    return [
        {'round_type': 'upper', 'round_name': 'upper_semifinal_1',
         'sources': {'team_a': {'type': 'seed', 'value': 1},
                     'team_b': {'type': 'seed', 'value': 4}}},
        {'round_type': 'upper', 'round_name': 'upper_semifinal_2',
         'sources': {'team_a': {'type': 'seed', 'value': 2},
                     'team_b': {'type': 'seed', 'value': 3}}},
        {'round_type': 'upper', 'round_name': 'upper_final',
         'sources': {'team_a': {'type': 'winner_of', 'value': 'upper_semifinal_1'},
                     'team_b': {'type': 'winner_of', 'value': 'upper_semifinal_2'}}},
        {'round_type': 'lower', 'round_name': 'lower_round1',
         'sources': {'team_a': {'type': 'loser_of', 'value': 'upper_semifinal_1'},
                     'team_b': {'type': 'loser_of', 'value': 'upper_semifinal_2'}}},
        {'round_type': 'lower', 'round_name': 'lower_final',
         'sources': {'team_a': {'type': 'winner_of', 'value': 'lower_round1'},
                     'team_b': {'type': 'loser_of', 'value': 'upper_final'}}},
        {'round_type': 'grand', 'round_name': 'grand_final',
         'sources': {'team_a': {'type': 'winner_of', 'value': 'upper_final'},
                     'team_b': {'type': 'winner_of', 'value': 'lower_final'}}},
    ]


def resolve_slot(match_template, completed_matches):
    """Resolve a TBD bracket slot to actual team IDs.

    Args:
        match_template: from generate_playoffs_4_teams
        completed_matches: list of {team_a_id, team_b_id, winner_id, loser_id, round_name}

    Returns: (team_a_id, team_b_id) or (None, None) if not ready
    """
    def _find(match_list, round_name):
        for m in match_list:
            if m.get('round_name') == round_name:
                return m
        return None

    def _resolve_source(src, matches):
        src_type = src['type']
        src_val = src['value']
        m = _find(matches, src_val)
        if m is None:
            return None
        if src_type == 'winner_of':
            return m.get('winner_id')
        elif src_type == 'loser_of':
            return m.get('loser_id')
        elif src_type == 'seed':
            return None  # seeds are resolved at creation time
        return None

    a = _resolve_source(match_template['sources']['team_a'], completed_matches)
    b = _resolve_source(match_template['sources']['team_b'], completed_matches)
    return (a, b)


def get_playoff_rounds():
    """Return ordered list of round names for display."""
    return [
        ('upper_semifinal_1', 'Ban ket'),
        ('upper_semifinal_2', 'Ban ket'),
        ('upper_final', 'CK Thang'),
        ('lower_round1', 'NR Vong 1'),
        ('lower_final', 'CK Thua'),
        ('grand_final', 'CK Tong'),
    ]


# ────────────────────────────────────────────────
# Test
# ────────────────────────────────────────────────

if __name__ == '__main__':
    teams = [
        {'id': 1, 'region': 'pacific', 'regional_seed': 1, 'name': 'PRX', 'short_code': 'PRX', 'rating': 93},
        {'id': 2, 'region': 'pacific', 'regional_seed': 2, 'name': 'NS', 'short_code': 'NS', 'rating': 83},
        {'id': 3, 'region': 'americas', 'regional_seed': 1, 'name': 'G2', 'short_code': 'G2', 'rating': 90},
        {'id': 4, 'region': 'americas', 'regional_seed': 2, 'name': 'NRG', 'short_code': 'NRG', 'rating': 85},
        {'id': 5, 'region': 'emea', 'regional_seed': 1, 'name': 'FNC', 'short_code': 'FNC', 'rating': 88},
        {'id': 6, 'region': 'emea', 'regional_seed': 2, 'name': 'TL', 'short_code': 'TL', 'rating': 86},
        {'id': 7, 'region': 'china', 'regional_seed': 1, 'name': 'EDG', 'short_code': 'EDG', 'rating': 87},
        {'id': 8, 'region': 'china', 'regional_seed': 2, 'name': 'BLG', 'short_code': 'BLG', 'rating': 85},
    ]

    # Round 1 pairing
    pairs = generate_swiss_pairings(teams, 1, [])
    print('=== Swiss R1 ===')
    for a, b in pairs:
        print(f'  [{a["region"]}] S{a["regional_seed"]} {a["short_code"]} vs [{b["region"]}] S{b["regional_seed"]} {b["short_code"]}  (same? {a["region"] == b["region"]})')

    # Simulate R1 results
    completed = []
    for i, (a, b) in enumerate(pairs):
        completed.append({
            'team_a_id': a['id'], 'team_b_id': b['id'],
            'winner_id': a['id'], 'loser_id': b['id'],
            'round_name': 'swiss_round1',
        })

    # Round 2 pairing
    pairs2 = generate_swiss_pairings(teams, 2, completed)
    print('\n=== Swiss R2 ===')
    for a, b in pairs2:
        print(f'  [{a["region"]}] {a["short_code"]} vs [{b["region"]}] {b["short_code"]}')

    # Simulate R2 (top half winners, bottom half losers)
    completed2 = list(completed)
    for a, b in pairs2:
        winner = a if a['regional_seed'] == 1 or random.random() < 0.5 else b
        loser = b if winner == a else a
        completed2.append({
            'team_a_id': a['id'], 'team_b_id': b['id'],
            'winner_id': winner['id'], 'loser_id': loser['id'],
            'round_name': 'swiss_round2',
        })

    # Round 3 pairing
    pairs3 = generate_swiss_pairings(teams, 3, completed2)
    print(f'\n=== Swiss R3 ({len(pairs3)} pairs) ===')
    for a, b in pairs3:
        print(f'  [{a["region"]}] {a["short_code"]} vs [{b["region"]}] {b["short_code"]}')

    # Standings
    standings = get_swiss_standings(teams, completed2)
    print('\n=== Standings after R2 ===')
    for s in standings:
        print(f'  {s["team"]["short_code"]:5s} {s["wins"]}-{s["losses"]}  adv={s["advanced"]}')

    # Playoffs template
    print('\n=== Playoffs Template ===')
    for m in generate_playoffs_4_teams(teams[:4]):
        print(f'  {m["round_type"]:6s} {m["round_name"]:25s} a={m["sources"]["team_a"]} b={m["sources"]["team_b"]}')
