"""
engine/format/ewc.py — Esports World Cup (16-team GSL Groups → 8-team Single Elimination)

PURE FUNCTIONS. No DB, no Flask, no random for match outcomes.
"""

import random
import itertools
from engine.format import champion


def group_config():
    return {
        'group_count': 4,
        'teams_per_group': 4,
        'advance_per_group': 2,
        'total_advance': 8,
        'bo': 3,
    }


# ────────────────────────────────────────────────
# Group Stage: GSL format (identical structure to Champion)
# ────────────────────────────────────────────────

def generate_gsl_groups(teams):
    """Split 16 teams into 4 groups A/B/C/D.
    Each group must contain:
      - Exactly 1 team from Pool 1 (Seed 1 - VCT Stage 1 Champions)
      - Exactly 1 team from Pool 2 (Seed 2 - VCT Stage 1 Runners-up)
      - Exactly 1 team from Pool 3 (Seed 3 - EWC Qualifier Upper Winners)
      - Exactly 1 team from Pool 4 (Seed 4 - EWC Qualifier Lower Winners)
    Max 1 team per region per group (Americas, EMEA, Pacific, China).
    """
    return champion.generate_gsl_groups(teams)


def get_gsl_matches(group_teams, group_label):
    """Generate the 5 GSL match templates for one group."""
    return champion.get_gsl_matches(group_teams, group_label)


def resolve_gs_slot(match_template, completed_matches):
    """Resolve GSL match slots."""
    return champion.resolve_gs_slot(match_template, completed_matches)


def get_group_qualifiers(group_label, completed_matches):
    """Get the 2 advancing teams from a group."""
    return champion.get_group_qualifiers(group_label, completed_matches)


# ────────────────────────────────────────────────
# Playoffs: 8-team Single Elimination with draw constraints
# ────────────────────────────────────────────────

def generate_ewc_playoffs_draw(winners, runners):
    """Generate single elimination playoff draw with constraints.

    Args:
        winners: 4 group winners [{id, group, short_code, ...}, ...]
        runners: 4 group runners-up [{id, group, short_code, ...}, ...]

    Constraints:
      1. Winner vs Runner in Quarterfinals.
      2. No same-group match in Quarterfinals.
      3. Opposite halves: if Winner_A is in Top Half (QF1/QF2), Runner_A must be in Bottom Half (QF3/QF4).
         This ensures two teams from the same group cannot meet until the Grand Final!
    """
    for _ in range(500):
        w_shuffled = list(winners)
        random.shuffle(w_shuffled)

        top_runners = []     # Runners whose winners are in bottom half
        bottom_runners = []  # Runners whose winners are in top half

        ok = True
        for i, w in enumerate(w_shuffled):
            winner_half = 'top' if i < 2 else 'bottom'
            w_grp = w.get('group') or w.get('group_label')
            r = _find_by_group(runners, w_grp)
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

        qf1 = (w_shuffled[0], top_runners[0])
        qf2 = (w_shuffled[1], top_runners[1])
        qf3 = (w_shuffled[2], bottom_runners[0])
        qf4 = (w_shuffled[3], bottom_runners[1])

        if (_same_group(qf1) or _same_group(qf2) or
            _same_group(qf3) or _same_group(qf4)):
            continue

        return [
            {'round_type': 'upper', 'round_name': 'quarterfinal_1',
             'high_team': qf1[0], 'low_team': qf1[1],
             'sources': {'desc': f'{qf1[0]["short_code"]} vs {qf1[1]["short_code"]}'}},
            {'round_type': 'upper', 'round_name': 'quarterfinal_2',
             'high_team': qf2[0], 'low_team': qf2[1],
             'sources': {'desc': f'{qf2[0]["short_code"]} vs {qf2[1]["short_code"]}'}},
            {'round_type': 'upper', 'round_name': 'quarterfinal_3',
             'high_team': qf3[0], 'low_team': qf3[1],
             'sources': {'desc': f'{qf3[0]["short_code"]} vs {qf3[1]["short_code"]}'}},
            {'round_type': 'upper', 'round_name': 'quarterfinal_4',
             'high_team': qf4[0], 'low_team': qf4[1],
             'sources': {'desc': f'{qf4[0]["short_code"]} vs {qf4[1]["short_code"]}'}},
            {'round_type': 'upper', 'round_name': 'semifinal_1',
             'sources': {'team_a': {'type': 'winner_of', 'value': 'quarterfinal_1'},
                         'team_b': {'type': 'winner_of', 'value': 'quarterfinal_2'}}},
            {'round_type': 'upper', 'round_name': 'semifinal_2',
             'sources': {'team_a': {'type': 'winner_of', 'value': 'quarterfinal_3'},
                         'team_b': {'type': 'winner_of', 'value': 'quarterfinal_4'}}},
            {'round_type': 'grand', 'round_name': 'grand_final',
             'sources': {'team_a': {'type': 'winner_of', 'value': 'semifinal_1'},
                         'team_b': {'type': 'winner_of', 'value': 'semifinal_2'}}},
            {'round_type': 'third_place', 'round_name': 'third_place_match',
             'sources': {'team_a': {'type': 'loser_of', 'value': 'semifinal_1'},
                         'team_b': {'type': 'loser_of', 'value': 'semifinal_2'}}},
        ]

    # Fallback if constraint matching fails
    all_w = list(winners)
    all_r = list(runners)
    random.shuffle(all_w)
    random.shuffle(all_r)
    return [
        {'round_type': 'upper', 'round_name': 'quarterfinal_1',
         'high_team': all_w[0], 'low_team': all_r[0],
         'sources': {'desc': 'fallback'}},
        {'round_type': 'upper', 'round_name': 'quarterfinal_2',
         'high_team': all_w[1], 'low_team': all_r[1],
         'sources': {'desc': 'fallback'}},
        {'round_type': 'upper', 'round_name': 'quarterfinal_3',
         'high_team': all_w[2], 'low_team': all_r[2],
         'sources': {'desc': 'fallback'}},
        {'round_type': 'upper', 'round_name': 'quarterfinal_4',
         'high_team': all_w[3], 'low_team': all_r[3],
         'sources': {'desc': 'fallback'}},
        {'round_type': 'upper', 'round_name': 'semifinal_1',
         'sources': {'team_a': {'type': 'winner_of', 'value': 'quarterfinal_1'},
                     'team_b': {'type': 'winner_of', 'value': 'quarterfinal_2'}}},
        {'round_type': 'upper', 'round_name': 'semifinal_2',
         'sources': {'team_a': {'type': 'winner_of', 'value': 'quarterfinal_3'},
                     'team_b': {'type': 'winner_of', 'value': 'quarterfinal_4'}}},
        {'round_type': 'grand', 'round_name': 'grand_final',
         'sources': {'team_a': {'type': 'winner_of', 'value': 'semifinal_1'},
                     'team_b': {'type': 'winner_of', 'value': 'semifinal_2'}}},
        {'round_type': 'third_place', 'round_name': 'third_place_match',
         'sources': {'team_a': {'type': 'loser_of', 'value': 'semifinal_1'},
                     'team_b': {'type': 'loser_of', 'value': 'semifinal_2'}}},
    ]


def resolve_slot(match_template, completed_matches):
    """Resolve TBD slot to (team_a_id, team_b_id)."""
    def _find(m_list, name):
        for m in m_list:
            if m.get('round_name') == name:
                return m
        return None

    def _resolve(src, matches):
        if not src or src.get('desc'):
            return None
        t, v = src.get('type'), src.get('value')
        m = _find(matches, v)
        if not m:
            return None
        if t == 'winner_of':
            return m.get('winner_id')
        if t == 'loser_of':
            return m.get('loser_id')
        return None

    sources = match_template.get('sources', {})
    a = _resolve(sources.get('team_a', {}), completed_matches)
    b = _resolve(sources.get('team_b', {}), completed_matches)
    return (a, b)


def _find_by_group(runners, group_label):
    for r in runners:
        if (r.get('group') or r.get('group_label')) == group_label:
            return r
    return None


def _same_group(pair):
    g0 = pair[0].get('group') or pair[0].get('group_label')
    g1 = pair[1].get('group') or pair[1].get('group_label')
    return g0 == g1
