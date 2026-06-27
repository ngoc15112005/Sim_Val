"""
engine/format/master.py — Master (8-team Swiss 2-wins-advance, 8-team Double Elim)

PURE FUNCTIONS. No DB, no Flask, no random for match outcomes.
"""

import random


def swiss_config():
    return {
        'win_target': 2,
        'loss_target': 2,
        'advance_count': 4,
        'swiss_team_count': 8,
        'direct_count': 4,
        'bo': 3,
    }


# ────────────────────────────────────────────────
# Swiss Stage pairing (seed2 vs seed3, cross-region)
# ────────────────────────────────────────────────

def generate_master_swiss_r1(teams):
    """Round 1: seed2 vs seed3, MUST be different regions.

    Uses while-True shuffle-retry until all 4 pairs are valid.
    teams: list of dicts with {id, region, regional_seed}
           Only includes Swiss teams (regional_seed 2 and 3).
    """
    seed2 = [t for t in teams if t.get('regional_seed') == 2]
    seed3 = [t for t in teams if t.get('regional_seed') == 3]

    assert len(seed2) == 4 and len(seed3) == 4, \
        f"Need 4 seed2 + 4 seed3, got {len(seed2)} + {len(seed3)}"

    for _ in range(500):
        s2_shuffled = list(seed2)
        random.shuffle(s2_shuffled)

        available = list(seed3)
        random.shuffle(available)

        pairs = []
        ok = True
        for s2 in s2_shuffled:
            found = None
            for s3 in available:
                if s3['region'] != s2['region']:
                    found = s3
                    break
            if found is None:
                ok = False
                break
            available.remove(found)
            pairs.append((s2, found))

        if ok and len(pairs) == 4:
            return pairs

    # Absolute fallback (should never reach)
    all_t = list(teams)
    random.shuffle(all_t)
    return [(all_t[i], all_t[i + 1]) for i in range(0, len(all_t), 2)]


# Reuse same-record pairing from major for R2-R3
def generate_swiss_pairings(teams, current_round, completed_matches):
    """R2-R3: same-record pairing with rematch blocking."""
    if current_round == 1:
        return generate_master_swiss_r1(teams)

    from engine.format.major import _swiss_same_record_pairing
    return _swiss_same_record_pairing(teams, completed_matches, current_round)


def get_swiss_standings(teams, completed_matches):
    from engine.format.major import _compute_swiss_records
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
# Playoffs: 8-team Double Elimination (with cross-mapping)
# ────────────────────────────────────────────────

def generate_master_playoffs(pool_high, pool_low):
    """Generate 8-team Double Elim bracket.

    Args:
        pool_high: 4 direct qualifiers (regional_seed=1)
        pool_low: 4 Swiss qualifiers

    Upper quarters: pool_high vs pool_low, random draw order.
    Cross-mapping: loser US1 → LR1_2 side, loser US2 → LR1_1 side.

    Returns: list of match templates.
    """
    # Draw: shuffle pool_high, pair with pool_low
    high_shuffled = list(pool_high)
    random.shuffle(high_shuffled)

    available_low = list(pool_low)
    random.shuffle(available_low)

    quarters = []
    for i, h in enumerate(high_shuffled):
        l = available_low[i]
        quarters.append({
            'round_type': 'upper',
            'round_name': f'upper_quarterfinal_{i+1}',
            'sources': {
                'team_a': {'type': 'seed', 'value': h.get('bracket_seed', i+1)},
                'team_b': {'type': 'seed', 'value': l.get('bracket_seed', i+5)},
            },
            'high_team': h,
            'low_team': l,
        })

    return [
        quarters[0],
        quarters[1],
        quarters[2],
        quarters[3],
        {'round_type': 'upper', 'round_name': 'upper_semifinal_1',
         'sources': {'team_a': {'type': 'winner_of', 'value': 'upper_quarterfinal_1'},
                     'team_b': {'type': 'winner_of', 'value': 'upper_quarterfinal_4'}}},
        {'round_type': 'upper', 'round_name': 'upper_semifinal_2',
         'sources': {'team_a': {'type': 'winner_of', 'value': 'upper_quarterfinal_2'},
                     'team_b': {'type': 'winner_of', 'value': 'upper_quarterfinal_3'}}},
        {'round_type': 'upper', 'round_name': 'upper_final',
         'sources': {'team_a': {'type': 'winner_of', 'value': 'upper_semifinal_1'},
                     'team_b': {'type': 'winner_of', 'value': 'upper_semifinal_2'}}},

        {'round_type': 'lower', 'round_name': 'lower_round1_1',
         'sources': {'team_a': {'type': 'loser_of', 'value': 'upper_quarterfinal_1'},
                     'team_b': {'type': 'loser_of', 'value': 'upper_quarterfinal_4'}}},
        {'round_type': 'lower', 'round_name': 'lower_round1_2',
         'sources': {'team_a': {'type': 'loser_of', 'value': 'upper_quarterfinal_2'},
                     'team_b': {'type': 'loser_of', 'value': 'upper_quarterfinal_3'}}},

        # CROSS-MAPPING: loser US1 goes to face winner LR1_2, loser US2 goes to face winner LR1_1
        {'round_type': 'lower', 'round_name': 'lower_quarterfinal_1',
         'sources': {'team_a': {'type': 'winner_of', 'value': 'lower_round1_1'},
                     'team_b': {'type': 'loser_of', 'value': 'upper_semifinal_2'}}},
        {'round_type': 'lower', 'round_name': 'lower_quarterfinal_2',
         'sources': {'team_a': {'type': 'winner_of', 'value': 'lower_round1_2'},
                     'team_b': {'type': 'loser_of', 'value': 'upper_semifinal_1'}}},

        {'round_type': 'lower', 'round_name': 'lower_semifinal',
         'sources': {'team_a': {'type': 'winner_of', 'value': 'lower_quarterfinal_1'},
                     'team_b': {'type': 'winner_of', 'value': 'lower_quarterfinal_2'}}},
        {'round_type': 'lower', 'round_name': 'lower_final',
         'sources': {'team_a': {'type': 'winner_of', 'value': 'lower_semifinal'},
                     'team_b': {'type': 'loser_of', 'value': 'upper_final'}}},
        {'round_type': 'grand', 'round_name': 'grand_final',
         'sources': {'team_a': {'type': 'winner_of', 'value': 'upper_final'},
                     'team_b': {'type': 'winner_of', 'value': 'lower_final'}}},
    ]


def resolve_slot(match_template, completed_matches):
    """Resolve TBD slot to (team_a_id, team_b_id)."""
    def _find(m_list, name):
        for m in m_list:
            if m.get('round_name') == name:
                return m
        return None

    def _resolve(src, matches):
        t, v = src['type'], src['value']
        m = _find(matches, v)
        if m is None:
            return None
        if t == 'winner_of':
            return m.get('winner_id')
        if t == 'loser_of':
            return m.get('loser_id')
        return None

    a = _resolve(match_template['sources']['team_a'], completed_matches)
    b = _resolve(match_template['sources']['team_b'], completed_matches)
    return (a, b)


# ────────────────────────────────────────────────
# Test
# ────────────────────────────────────────────────

if __name__ == '__main__':
    teams = [
        {'id': 101, 'region': 'pacific', 'regional_seed': 2, 'name': 'NS', 'short_code': 'NS', 'rating': 83},
        {'id': 102, 'region': 'pacific', 'regional_seed': 3, 'name': 'GEN', 'short_code': 'GEN', 'rating': 83},
        {'id': 201, 'region': 'americas', 'regional_seed': 2, 'name': 'NRG', 'short_code': 'NRG', 'rating': 85},
        {'id': 202, 'region': 'americas', 'regional_seed': 3, 'name': 'SEN', 'short_code': 'SEN', 'rating': 82},
        {'id': 301, 'region': 'emea', 'regional_seed': 2, 'name': 'TL', 'short_code': 'TL', 'rating': 86},
        {'id': 302, 'region': 'emea', 'regional_seed': 3, 'name': 'BBL', 'short_code': 'BBL', 'rating': 84},
        {'id': 401, 'region': 'china', 'regional_seed': 2, 'name': 'BLG', 'short_code': 'BLG', 'rating': 85},
        {'id': 402, 'region': 'china', 'regional_seed': 3, 'name': 'XLG', 'short_code': 'XLG', 'rating': 82},
    ]

    pairs = generate_master_swiss_r1(teams)
    print('=== Master Swiss R1 (seed2 vs seed3, cross-region) ===')
    for a, b in pairs:
        print(f'  [{a["region"]}] S{a["regional_seed"]} {a["short_code"]} vs [{b["region"]}] S{b["regional_seed"]} {b["short_code"]} (same? {a["region"] == b["region"]})')

    # Test playoffs template
    pool_high = [
        {'id': 1, 'region': 'pacific', 'rating': 93, 'short_code': 'PRX', 'bracket_seed': 1},
        {'id': 2, 'region': 'americas', 'rating': 90, 'short_code': 'G2', 'bracket_seed': 2},
        {'id': 3, 'region': 'emea', 'rating': 88, 'short_code': 'FNC', 'bracket_seed': 3},
        {'id': 4, 'region': 'china', 'rating': 87, 'short_code': 'EDG', 'bracket_seed': 4},
    ]
    pool_low = [
        {'id': 5, 'region': 'pacific', 'rating': 83, 'short_code': 'NS', 'bracket_seed': 5},
        {'id': 6, 'region': 'emea', 'rating': 86, 'short_code': 'TL', 'bracket_seed': 6},
        {'id': 7, 'region': 'pacific', 'rating': 83, 'short_code': 'GEN', 'bracket_seed': 7},
        {'id': 8, 'region': 'americas', 'rating': 82, 'short_code': 'SEN', 'bracket_seed': 8},
    ]

    print('\n=== Playoffs Template (8-team DE) ===')
    bracket = generate_master_playoffs(pool_high, pool_low)
    for m in bracket:
        sa = m['sources']['team_a']
        sb = m['sources']['team_b']
        print(f'  {m["round_type"]:6s} {m["round_name"]:25s} a={sa["type"]}:{sa["value"]}  b={sb["type"]}:{sb["value"]}')
