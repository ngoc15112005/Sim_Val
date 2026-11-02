"""
engine/tiebreaker.py — Official VCT 2026 Mini-Table & Group Standings Tiebreaker Engine

Implements the official VCT 2026 tiebreaker hierarchy:
1. Head-to-head match score (mini-table)
2. Head-to-head map differential (mini-table)
3. Head-to-head round differential (mini-table)
4. Overall map differential
5. Overall round differential

Recursive Sub-group Rule:
If 3+ teams are tied, and one or more criteria resolve a subset of teams,
the tiebreak process for any remaining tied subgroup RESTARTS from criterion #1.

Unresolved Tie:
If all criteria fail to break the tie, do NOT randomly pick a winner.
Flag as `unresolved_tie = True` and retain deterministic order.
"""

from typing import Any, Dict, List, Optional


def compute_vct_group_standings(
    group_teams: List[Dict[str, Any]],
    completed_matches: List[Dict[str, Any]],
    qualify_count: int = 4
) -> List[Dict[str, Any]]:
    """Compute VCT Group Standings with official 5-tier tiebreaker and recursive restart.
    
    Returns sorted list of standings records with both camelCase and snake_case attributes.
    """
    stats: Dict[Any, Dict[str, Any]] = {}

    for t in group_teams:
        t_id = t.get('id') if 'id' in t else t.get('club_id')
        stats[t_id] = {
            'team': t,
            'club_id': t_id,
            'name': t.get('name'),
            'short_code': t.get('short_code'),
            'logo_url': t.get('logo_url'),
            'group': t.get('group'),
            'story_rating': t.get('story_rating', 80),
            'matchesPlayed': 0,
            'matchWins': 0,
            'matchLosses': 0,
            'wins': 0,
            'losses': 0,
            'mapsWon': 0,
            'mapsLost': 0,
            'mapDifferential': 0,
            'map_won': 0,
            'map_lost': 0,
            'map_diff': 0,
            'roundsWon': 0,
            'roundsLost': 0,
            'roundDifferential': 0,
            'round_won': 0,
            'round_lost': 0,
            'round_diff': 0,
            'championshipPoints': 0,
            'cp_earned': 0,
            'rank': 0,
            'groupPosition': 0,
            'advanced': False,
            'playoffQualified': False,
            'unresolved_tie': False,
        }

    for m in completed_matches:
        if m.get('status') != 'completed':
            continue
        a_id = m.get('team_a_id')
        b_id = m.get('team_b_id')
        sc_a = m.get('team_a_score', 0)
        sc_b = m.get('team_b_score', 0)
        maps = m.get('maps', [])

        rd_a = sum(mp.get('team_a_score', 0) for mp in maps)
        rd_b = sum(mp.get('team_b_score', 0) for mp in maps)

        if a_id in stats:
            stats[a_id]['matchesPlayed'] += 1
            if sc_a > sc_b:
                stats[a_id]['matchWins'] += 1
                stats[a_id]['wins'] += 1
                stats[a_id]['championshipPoints'] += 1
                stats[a_id]['cp_earned'] += 1
            else:
                stats[a_id]['matchLosses'] += 1
                stats[a_id]['losses'] += 1
            stats[a_id]['mapsWon'] += sc_a
            stats[a_id]['mapsLost'] += sc_b
            stats[a_id]['map_won'] += sc_a
            stats[a_id]['map_lost'] += sc_b
            stats[a_id]['roundsWon'] += rd_a
            stats[a_id]['roundsLost'] += rd_b
            stats[a_id]['round_won'] += rd_a
            stats[a_id]['round_lost'] += rd_b

        if b_id in stats:
            stats[b_id]['matchesPlayed'] += 1
            if sc_b > sc_a:
                stats[b_id]['matchWins'] += 1
                stats[b_id]['wins'] += 1
                stats[b_id]['championshipPoints'] += 1
                stats[b_id]['cp_earned'] += 1
            else:
                stats[b_id]['matchLosses'] += 1
                stats[b_id]['losses'] += 1
            stats[b_id]['mapsWon'] += sc_b
            stats[b_id]['mapsLost'] += sc_a
            stats[b_id]['map_won'] += sc_b
            stats[b_id]['map_lost'] += sc_a
            stats[b_id]['roundsWon'] += rd_b
            stats[b_id]['roundsLost'] += rd_a
            stats[b_id]['round_won'] += rd_b
            stats[b_id]['round_lost'] += rd_a

    # Compute differentials
    for s in stats.values():
        s['mapDifferential'] = s['mapsWon'] - s['mapsLost']
        s['map_diff'] = s['mapDifferential']
        s['roundDifferential'] = s['roundsWon'] - s['roundsLost']
        s['round_diff'] = s['roundDifferential']

    # Group teams by matchWins
    clusters_by_wins: Dict[int, List[Dict[str, Any]]] = {}
    for s in stats.values():
        w = s['matchWins']
        clusters_by_wins.setdefault(w, []).append(s)

    # Sort win counts descending
    sorted_standings: List[Dict[str, Any]] = []
    for win_count in sorted(clusters_by_wins.keys(), reverse=True):
        cluster = clusters_by_wins[win_count]
        if len(cluster) == 1:
            sorted_standings.extend(cluster)
        else:
            resolved_cluster = _break_tied_cluster(cluster, completed_matches, stats, crit_start=1)
            sorted_standings.extend(resolved_cluster)

    for idx, s in enumerate(sorted_standings):
        pos = idx + 1
        s['rank'] = pos
        s['groupPosition'] = pos
        s['advanced'] = (pos <= qualify_count)
        s['playoffQualified'] = (pos <= qualify_count)

    return sorted_standings


def _break_tied_cluster(
    cluster: List[Dict[str, Any]],
    completed_matches: List[Dict[str, Any]],
    stats_map: Dict[Any, Dict[str, Any]],
    crit_start: int = 1
) -> List[Dict[str, Any]]:
    """Recursively resolve tied clusters using official VCT criteria:
    1: Head-to-head match score (mini-table)
    2: Head-to-head map differential (mini-table)
    3: Head-to-head round differential (mini-table)
    4: Overall map differential
    5: Overall round differential
    """
    if len(cluster) <= 1:
        return cluster

    cluster_ids = {t['club_id'] for t in cluster}

    for crit in range(crit_start, 6):
        scores: Dict[Any, int] = {}

        if crit in (1, 2, 3):
            # Compute mini-table head-to-head stats among cluster_ids
            h2h_wins: Dict[Any, int] = {cid: 0 for cid in cluster_ids}
            h2h_map_diff: Dict[Any, int] = {cid: 0 for cid in cluster_ids}
            h2h_round_diff: Dict[Any, int] = {cid: 0 for cid in cluster_ids}

            for m in completed_matches:
                if m.get('status') != 'completed':
                    continue
                a_id = m.get('team_a_id')
                b_id = m.get('team_b_id')
                if a_id in cluster_ids and b_id in cluster_ids:
                    sc_a = m.get('team_a_score', 0)
                    sc_b = m.get('team_b_score', 0)
                    maps = m.get('maps', [])
                    rd_a = sum(mp.get('team_a_score', 0) for mp in maps)
                    rd_b = sum(mp.get('team_b_score', 0) for mp in maps)

                    if sc_a > sc_b:
                        h2h_wins[a_id] += 1
                    elif sc_b > sc_a:
                        h2h_wins[b_id] += 1

                    h2h_map_diff[a_id] += (sc_a - sc_b)
                    h2h_map_diff[b_id] += (sc_b - sc_a)
                    h2h_round_diff[a_id] += (rd_a - rd_b)
                    h2h_round_diff[b_id] += (rd_b - rd_a)

            for cid in cluster_ids:
                if crit == 1:
                    scores[cid] = h2h_wins[cid]
                elif crit == 2:
                    scores[cid] = h2h_map_diff[cid]
                elif crit == 3:
                    scores[cid] = h2h_round_diff[cid]

        elif crit == 4:
            for cid in cluster_ids:
                scores[cid] = stats_map[cid]['mapDifferential']

        elif crit == 5:
            for cid in cluster_ids:
                scores[cid] = stats_map[cid]['roundDifferential']

        distinct_scores = set(scores.values())
        if len(distinct_scores) > 1:
            # Group teams by score
            grouped: Dict[int, List[Dict[str, Any]]] = {}
            for t in cluster:
                val = scores[t['club_id']]
                grouped.setdefault(val, []).append(t)

            resolved: List[Dict[str, Any]] = []
            for val in sorted(grouped.keys(), reverse=True):
                subgroup = grouped[val]
                if len(subgroup) == 1:
                    resolved.extend(subgroup)
                else:
                    # RESTART tiebreak from Criterion 1 for the smaller tied subgroup!
                    resolved.extend(_break_tied_cluster(subgroup, completed_matches, stats_map, crit_start=1))
            return resolved

    # If all criteria failed to separate teams, mark as unresolved tie
    for t in cluster:
        t['unresolved_tie'] = True
    # Keep original deterministic ordering without randomizing
    return cluster
