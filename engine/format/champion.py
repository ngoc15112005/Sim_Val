"""
engine/format/champion.py — Champion (16-team GSL Groups → 8-team Double Elim)

PURE FUNCTIONS. No DB, no Flask, no random for match outcomes.
"""

import random


def group_config():
    return {
        'group_count': 4,
        'teams_per_group': 4,
        'advance_per_group': 2,
        'total_advance': 8,
        'bo': 3,
    }


# ────────────────────────────────────────────────
# Group Stage: GSL format
# ────────────────────────────────────────────────

def generate_gsl_groups(teams):
    """Split 16 teams into 4 groups A/B/C/D.
    Max 1 team per region per group. Shuffle retry.

    Returns: dict {group_label: [team, ...]}
             group_label is 'A','B','C','D'
    """
    for _ in range(500):
        shuffled = list(teams)
        random.shuffle(shuffled)

        groups = {'A': [], 'B': [], 'C': [], 'D': []}
        region_used = {'A': set(), 'B': set(), 'C': set(), 'D': set()}

        ok = True
        for t in shuffled:
            placed = False
            for grp in ['A', 'B', 'C', 'D']:
                if len(groups[grp]) < 4 and t['region'] not in region_used[grp]:
                    groups[grp].append(t)
                    region_used[grp].add(t['region'])
                    placed = True
                    break
            if not placed:
                ok = False
                break

        if ok and all(len(g) == 4 for g in groups.values()):
            return groups

    # Fallback
    all_t = list(teams)
    random.shuffle(all_t)
    return {
        'A': all_t[0:4], 'B': all_t[4:8],
        'C': all_t[8:12], 'D': all_t[12:16],
    }


def get_gsl_matches(group_teams, group_label):
    """Generate the 5 GSL match templates for one group.

    Returns: list of match templates.
    """
    prefix = f'group{group_label}'
    return [
        {'round_type': 'group', 'round_name': f'{prefix}_opening1',
         'sources': {'desc': 'opening1'}},
        {'round_type': 'group', 'round_name': f'{prefix}_opening2',
         'sources': {'desc': 'opening2'}},
        {'round_type': 'group', 'round_name': f'{prefix}_winners_match',
         'sources': {
             'team_a': {'type': 'winner_of', 'value': f'{prefix}_opening1'},
             'team_b': {'type': 'winner_of', 'value': f'{prefix}_opening2'},
         }},
        {'round_type': 'group', 'round_name': f'{prefix}_elimination_match',
         'sources': {
             'team_a': {'type': 'loser_of', 'value': f'{prefix}_opening1'},
             'team_b': {'type': 'loser_of', 'value': f'{prefix}_opening2'},
         }},
        {'round_type': 'group', 'round_name': f'{prefix}_decider_match',
         'sources': {
             'team_a': {'type': 'loser_of', 'value': f'{prefix}_winners_match'},
             'team_b': {'type': 'winner_of', 'value': f'{prefix}_elimination_match'},
         }},
    ]


def resolve_gs_slot(match_template, completed_matches):
    """Resolve GSL match slots."""
    def _find(m_list, name):
        for m in m_list:
            if m.get('round_name') == name:
                return m
        return None

    def _resolve(src, matches):
        if src.get('desc'):
            return None
        t, v = src['type'], src['value']
        m = _find(matches, v)
        if not m:
            return None
        if t == 'winner_of':
            return m.get('winner_id')
        if t == 'loser_of':
            return m.get('loser_id')
        return None

    a = _resolve(match_template['sources'].get('team_a', {}), completed_matches)
    b = _resolve(match_template['sources'].get('team_b', {}), completed_matches)
    return (a, b)


def get_group_qualifiers(group_label, completed_matches):
    """Get the 2 advancing teams from a group.

    Returns: (winner_seed1, winner_seed2) as team dicts
    """
    prefix = f'group{group_label}'
    wm = _find_match(completed_matches, f'{prefix}_winners_match')
    dm = _find_match(completed_matches, f'{prefix}_decider_match')

    wm_winner = wm.get('winner_id') if wm else None
    dm_winner = dm.get('winner_id') if dm else None

    return wm_winner, dm_winner


def _find_match(matches, name):
    for m in matches:
        if m.get('round_name') == name:
            return m
    return None


# ────────────────────────────────────────────────
# Playoffs: 8-team Double Elim with draw constraints
# ────────────────────────────────────────────────

def generate_champion_playoffs_draw(winners, runners):
    """Generate quarterfinal draw with constraints.

    Args:
        winners: 4 group winners [{id, group, ...}, ...]
        runners: 4 group runners-up

    Constraints:
      1. Winner vs Runner
      2. No same-group match
      3. Opposite halves: if Winner_A in UQ1/UQ2, Runner_A must be in UQ3/UQ4

    Uses while-True shuffle retry.
    """
    for _ in range(500):
        w_shuffled = list(winners)
        random.shuffle(w_shuffled)

        top_runners = []   # Runners whose winners are in bottom half
        bottom_runners = []  # Runners whose winners are in top half

        ok = True
        for i, w in enumerate(w_shuffled):
            winner_half = 'top' if i < 2 else 'bottom'
            r = _find_by_group(runners, w['group'])
            if r is None:
                ok = False
                break
            if winner_half == 'top':
                bottom_runners.append(r)
            else:
                top_runners.append(r)

        if not ok or len(top_runners) != 2 or len(bottom_runners) != 2:
            continue

        random.shuffle(top_runners)
        random.shuffle(bottom_runners)

        # Verify: no runner faces its own group's winner in QF
        uq1 = (w_shuffled[0], top_runners[0])
        uq2 = (w_shuffled[1], top_runners[1])
        uq3 = (w_shuffled[2], bottom_runners[0])
        uq4 = (w_shuffled[3], bottom_runners[1])

        if (_same_group(uq1) or _same_group(uq2) or
            _same_group(uq3) or _same_group(uq4)):
            continue

        # All constraints satisfied
        return [
            {'round_type': 'upper', 'round_name': 'upper_quarterfinal_1',
             'high_team': uq1[0], 'low_team': uq1[1],
             'sources': {'desc': f'{uq1[0]["short_code"]} vs {uq1[1]["short_code"]}'}},
            {'round_type': 'upper', 'round_name': 'upper_quarterfinal_2',
             'high_team': uq2[0], 'low_team': uq2[1],
             'sources': {'desc': f'{uq2[0]["short_code"]} vs {uq2[1]["short_code"]}'}},
            {'round_type': 'upper', 'round_name': 'upper_quarterfinal_3',
             'high_team': uq3[0], 'low_team': uq3[1],
             'sources': {'desc': f'{uq3[0]["short_code"]} vs {uq3[1]["short_code"]}'}},
            {'round_type': 'upper', 'round_name': 'upper_quarterfinal_4',
             'high_team': uq4[0], 'low_team': uq4[1],
             'sources': {'desc': f'{uq4[0]["short_code"]} vs {uq4[1]["short_code"]}'}},
        ] + _playoffs_8team_rest()

    # Fallback
    all_q = winners + runners
    random.shuffle(all_q)
    return [
        {'round_type': 'upper', 'round_name': 'upper_quarterfinal_1',
         'high_team': all_q[0], 'low_team': all_q[5],
         'sources': {'desc': 'fallback'}},
        {'round_type': 'upper', 'round_name': 'upper_quarterfinal_2',
         'high_team': all_q[1], 'low_team': all_q[6],
         'sources': {'desc': 'fallback'}},
        {'round_type': 'upper', 'round_name': 'upper_quarterfinal_3',
         'high_team': all_q[2], 'low_team': all_q[7],
         'sources': {'desc': 'fallback'}},
        {'round_type': 'upper', 'round_name': 'upper_quarterfinal_4',
         'high_team': all_q[3], 'low_team': all_q[4],
         'sources': {'desc': 'fallback'}},
    ] + _playoffs_8team_rest()


def _playoffs_8team_rest():
    """Standard 8-team DE bracket after quarterfinals (with cross-mapping)."""
    return [
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
        # CROSS-MAPPING
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
        if src.get('desc'):
            return None
        t, v = src['type'], src['value']
        m = _find(matches, v)
        if not m:
            return None
        if t == 'winner_of':
            return m.get('winner_id')
        if t == 'loser_of':
            return m.get('loser_id')
        return None

    a = _resolve(match_template['sources'].get('team_a', {}), completed_matches)
    b = _resolve(match_template['sources'].get('team_b', {}), completed_matches)
    return (a, b)


def _find_by_group(runners, group_label):
    for r in runners:
        if r.get('group') == group_label:
            return r
    return None


def _same_group(pair):
    return pair[0].get('group') == pair[1].get('group')


# ────────────────────────────────────────────────
# Test
# ────────────────────────────────────────────────

if __name__ == '__main__':
    # Test GSL groups
    teams = []
    regions = ['pacific', 'americas', 'emea', 'china']
    tid = 1
    for region in regions:
        for s in range(4):
            teams.append({
                'id': tid, 'region': region,
                'regional_seed': s+1, 'short_code': f'{region[:3].upper()}{s+1}',
                'rating': 90 - s*5 - tid,
            })
            tid += 1

    groups = generate_gsl_groups(teams)
    print('=== GSL Groups ===')
    for grp, ts in groups.items():
        regions_in_grp = [t['region'] for t in ts]
        codes = [t['short_code'] for t in ts]
        has_dup = len(regions_in_grp) != len(set(regions_in_grp))
        print(f'  Group {grp}: {codes}  regions={regions_in_grp}  dup={has_dup}')

    # Test champion draw
    winners = [
        {'id': 1, 'group': 'A', 'short_code': 'PRX', 'region': 'pacific'},
        {'id': 2, 'group': 'B', 'short_code': 'G2', 'region': 'americas'},
        {'id': 3, 'group': 'C', 'short_code': 'FNC', 'region': 'emea'},
        {'id': 4, 'group': 'D', 'short_code': 'EDG', 'region': 'china'},
    ]
    runners = [
        {'id': 5, 'group': 'A', 'short_code': 'NS', 'region': 'pacific'},
        {'id': 6, 'group': 'B', 'short_code': 'SEN', 'region': 'americas'},
        {'id': 7, 'group': 'C', 'short_code': 'TL', 'region': 'emea'},
        {'id': 8, 'group': 'D', 'short_code': 'BLG', 'region': 'china'},
    ]

    print('\n=== Champion QF Draw ===')
    bracket = generate_champion_playoffs_draw(winners, runners)
    for m in bracket[:4]:
        w = m.get('high_team', {})
        r = m.get('low_team', {})
        print(f'  {m["round_name"]}: [{w.get("group")}]{w.get("short_code")} vs [{r.get("group")}]{r.get("short_code")}  (same? {_same_group((w, r))})')
