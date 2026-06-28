"""
services/bracket_service.py — Bridge between format modules and DB models.

Converts DB objects to format-compatible dicts, calls format functions,
and returns results that routes can pass to Jinja2.
"""

from collections import OrderedDict
from engine.format import major, master, champion
from models import Match, TournamentParticipant


def _team_to_dict(p):
    """Convert TournamentParticipant to format-compatible team dict."""
    return {
        'id': p.club_id,
        'region': p.region or '?',
        'regional_seed': p.regional_seed or 0,
        'name': p.club.name,
        'short_code': p.club.short_code,
        'rating': p.club.current_rating,
        'logo_url': p.club.logo_url,
        'bracket_seed': p.seed,
        'group': getattr(p, 'group_label', None),
    }


def _match_to_dict(m):
    """Convert Match model to format-compatible result dict."""
    return {
        'team_a_id': m.team_a_id,
        'team_b_id': m.team_b_id,
        'winner_id': m.winner_id,
        'loser_id': m.loser_id,
        'round_name': m.round_name,
        'round_type': m.round_type,
        'status': m.status,
    }


def generate_swiss_matches(tournament, current_round):
    """Generate next Swiss round matches for a tournament.

    Returns list of (team_a_id, team_b_id) pairs.
    """
    ttype = tournament.type
    participants = TournamentParticipant.query.filter_by(
        tournament_id=tournament.id,
    ).order_by(TournamentParticipant.seed).all()

    if ttype == 'master':
        swiss_teams = [p for p in participants if p.regional_seed and p.regional_seed >= 2]
    else:
        swiss_teams = list(participants)

    team_dicts = [_team_to_dict(p) for p in swiss_teams]

    # Direct query to avoid relationship caching
    matches = Match.query.filter_by(
        tournament_id=tournament.id, round_type='swiss',
    ).all()
    completed = [_match_to_dict(m) for m in matches if m.status == 'completed']

    if ttype == 'master':
        pairs = master.generate_swiss_pairings(team_dicts, current_round, completed)
    else:
        pairs = major.generate_swiss_pairings(team_dicts, current_round, completed)

    return [(a['id'], b['id']) for a, b in pairs]


def generate_playoff_matches(tournament, advancing_participants):
    """Generate playoff bracket match templates for a tournament."""
    ttype = tournament.type
    n = len(advancing_participants)

    if n == 4:
        templates = major.generate_playoffs_4_teams(
            [_team_to_dict(p) for p in advancing_participants]
        )
    elif n == 8:
        if ttype == 'master':
            pool_high = [p for p in advancing_participants if p.regional_seed == 1]
            pool_low = [p for p in advancing_participants if p.regional_seed and p.regional_seed >= 2]
            templates = master.generate_master_playoffs(
                [_team_to_dict(p) for p in pool_high],
                [_team_to_dict(p) for p in pool_low],
            )
        elif ttype == 'champion':
            winners = [p for p in advancing_participants if p.seed <= 4]
            runners = [p for p in advancing_participants if p.seed >= 5]
            templates = champion.generate_champion_playoffs_draw(
                [_team_to_dict(p) for p in winners],
                [_team_to_dict(p) for p in runners],
            )
        else:
            # Generic 8-team
            templates = major.generate_playoffs_4_teams(
                [_team_to_dict(p) for p in advancing_participants[:4]]
            )
            return templates
    else:
        return []

    return templates


def resolve_playoff_slot(match_template, tournament):
    """Resolve TBD bracket slot to actual team IDs using completed matches."""
    ttype = tournament.type
    matches = Match.query.filter_by(
        tournament_id=tournament.id,
    ).filter(Match.round_type.in_(['upper', 'lower', 'grand'])).all()
    completed = [_match_to_dict(m) for m in matches if m.status == 'completed']

    if ttype == 'major':
        return major.resolve_slot(match_template, completed)
    elif ttype == 'master':
        return master.resolve_slot(match_template, completed)
    elif ttype == 'champion':
        return champion.resolve_slot(match_template, completed)
    return (None, None)


def get_swiss_standings(tournament):
    """Compute Swiss Stage standings for display.

    Returns list of dicts compatible with Jinja2 template:
      {club, wins, losses, results: ['W','L',...], advanced, rating}
    """
    ttype = tournament.type
    participants = TournamentParticipant.query.filter_by(
        tournament_id=tournament.id,
    ).order_by(TournamentParticipant.seed).all()

    if ttype == 'master':
        swiss_teams = [p for p in participants if p.regional_seed and p.regional_seed >= 2]
    else:
        swiss_teams = list(participants)

    team_dicts = [_team_to_dict(p) for p in swiss_teams]
    matches = Match.query.filter_by(
        tournament_id=tournament.id, round_type='swiss',
    ).all()
    completed = [_match_to_dict(m) for m in matches if m.status == 'completed']

    if ttype == 'master':
        base = master.get_swiss_standings(team_dicts, completed)
    else:
        base = major.get_swiss_standings(team_dicts, completed)

    # Enrich with per-round results and DB club object
    result = []
    for s in base:
        p = next((pp for pp in swiss_teams if pp.club_id == s['team']['id']), None)
        per_round = _get_per_round_results(tournament, s['team']['id'])
        result.append({
            'club': p.club if p else s['team'],
            'wins': s['wins'],
            'losses': s['losses'],
            'results': per_round,
            'advanced': s['advanced'],
            'rating': s['team'].get('rating', 0),
        })
    return result


def _get_per_round_results(tournament, club_id):
    """Get per-round W/L results for a club_id, in chronological order."""
    results = []
    swiss_matches = Match.query.filter_by(
        tournament_id=tournament.id, round_type='swiss',
    ).order_by(Match.match_order).all()
    for m in swiss_matches:
        if m.status != 'completed':
            continue
        if m.team_a_id == club_id or m.team_b_id == club_id:
            results.append('W' if m.winner_id == club_id else 'L')
    return results


def get_swiss_data(tournament):
    """Build Swiss Stage data for Major/Master.

    Returns dict:
      {
        'standings': [...],   # full-width standings table data
        'rounds': {            # matches grouped by round, ordered
          'swiss_round1': {'label': 'Round 1', 'matches': [match_display, ...]},
          ...
        },
        'direct_qualifiers': [...],  # Master only: 4 teams that skip Swiss
      }
    """
    ttype = tournament.type
    if ttype not in ('major', 'master'):
        return None

    # Identify Swiss participants
    all_participants = TournamentParticipant.query.filter_by(
        tournament_id=tournament.id,
    ).order_by(TournamentParticipant.seed).all()

    if ttype == 'master':
        swiss_participants = [p for p in all_participants
                              if p.regional_seed and p.regional_seed >= 2]
        direct_participants = [p for p in all_participants
                               if p.regional_seed == 1]
    else:
        swiss_participants = list(all_participants)
        direct_participants = []

    # Standings (reuse existing function)
    standings = get_swiss_standings(tournament)

    # Group matches by round
    swiss_matches = Match.query.filter_by(
        tournament_id=tournament.id, round_type='swiss',
    ).order_by(Match.match_order).all()

    rounds = OrderedDict()
    for m in swiss_matches:
        rn = m.round_name
        if rn not in rounds:
            # Extract round number from "swiss_round1" / "swiss_round2" etc
            num = ''.join(c for c in rn if c.isdigit())
            rounds[rn] = {
                'round_name': rn,
                'label': f'Vòng {num}' if num else rn,
                'matches': [],
            }
        rounds[rn]['matches'].append(resolve_match_display(m))

    # Direct qualifiers display (Master only)
    direct_qualifiers = []
    if ttype == 'master':
        for p in direct_participants:
            direct_qualifiers.append({
                'club': p.club,
                'regional_seed': p.regional_seed,
                'rating': p.club.current_rating,
            })
        # Sort by regional_seed
        direct_qualifiers.sort(key=lambda d: d['regional_seed'])

    return {
        'standings': standings,
        'rounds': rounds,
        'direct_qualifiers': direct_qualifiers,
    }


def group_playoff_rounds(tournament):
    """Group playoff matches into ordered rounds for bracket display."""
    from collections import OrderedDict

    all_matches = Match.query.filter_by(
        tournament_id=tournament.id,
    ).filter(Match.round_type.in_(['upper', 'lower', 'grand'])).order_by(Match.match_order).all()

    rounds = OrderedDict()
    for m in all_matches:
        label = _match_label(m)
        rounds.setdefault(label, []).append(m)
    return rounds


def _match_label(m):
    """Human-readable round label for bracket display (Vietnamese)."""
    name = m.round_name
    if m.round_type == 'upper':
        if 'quarterfinal' in name:
            return 'Tứ kết'
        elif 'semifinal' in name:
            return 'Bán kết'
        elif 'final' in name:
            return 'CK Thắng'
    elif m.round_type == 'lower':
        if 'round1' in name:
            return 'NR Vòng 1'
        elif 'quarterfinal' in name:
            return 'NR Vòng 2'
        elif 'semifinal' in name:
            return 'NR Vòng 3'
        elif 'final' in name:
            return 'CK Thua'
    elif m.round_type == 'grand':
        return 'CK Tổng'
    return name


def resolve_match_display(m):
    """Convert a Match to display dict for Jinja2."""
    if m is None:
        return None
    return {
        'id': m.id,
        'round_type': m.round_type,
        'round_name': m.round_name,
        'match_order': m.match_order,
        'team_a': m.team_a.short_code if m.team_a else 'TBD',
        'team_b': m.team_b.short_code if m.team_b else 'TBD',
        'logo_a': m.team_a.logo_url if m.team_a else '',
        'logo_b': m.team_b.logo_url if m.team_b else '',
        'score_a': m.team_a_score if m.team_a_score is not None else '—',
        'score_b': m.team_b_score if m.team_b_score is not None else '—',
        'win_a': m.winner_id == m.team_a_id if m.winner_id and m.team_a else False,
        'win_b': m.winner_id == m.team_b_id if m.winner_id and m.team_b else False,
        'winner_id': m.winner_id,
        'status': m.status,
        'is_manual': m.is_manual,
        'maps': [f'{mp.team_a_score}-{mp.team_b_score}' for mp in (m.maps or [])],
    }


def get_groups_data(tournament):
    """Build GSL Group Stage data for Champion tournament.

    Returns dict:
      {
        'A': {
          'standings': [{rank, club, wins, losses, round_diff, status}, ...],
          'matches': {
            'opening': [match_display_dict, ...],
            'winners': [...],
            'elimination': [...],
            'decider': [...],
          }
        },
        'B': {...}, 'C': {...}, 'D': {...}
      }
    """
    # Get all group matches grouped by group_label
    group_matches = Match.query.filter_by(
        tournament_id=tournament.id, round_type='group',
    ).order_by(Match.match_order).all()

    # Group by group_label
    by_group = {}
    for m in group_matches:
        # round_name format: 'groupA_opening1', 'groupB_winners_match', etc.
        parts = m.round_name.split('_')
        if len(parts) < 2:
            continue
        grp = parts[0].replace('group', '')
        if grp not in ('A', 'B', 'C', 'D'):
            continue
        # Stage: opening1, opening2, winners_match, elimination_match, decider_match
        stage = '_'.join(parts[1:])

        if grp not in by_group:
            by_group[grp] = {'standings': [], 'matches': {}}
        if stage not in by_group[grp]['matches']:
            by_group[grp]['matches'][stage] = []
        by_group[grp]['matches'][stage].append(m)

    # For each group, compute standings and build display dicts
    result = {}
    for grp, data in by_group.items():
        standings = _compute_group_standings(tournament, grp)
        data['standings'] = standings

        # Build display dicts for matches
        display_matches = {}
        for stage, matches in data['matches'].items():
            display_matches[stage] = [resolve_match_display(m) for m in matches]
        data['matches'] = display_matches

        result[grp] = data

    # Ensure all 4 groups are in result (in case some haven't started)
    for grp in ('A', 'B', 'C', 'D'):
        if grp not in result:
            result[grp] = {'standings': [], 'matches': {}}

    return result


def _compute_group_standings(tournament, group_label):
    """Compute standings for one group: rank, club, wins, losses, round_diff, status.

    status: 'qualified' (top 2), 'eliminated' (bottom 2), 'pending' (no matches)
    """
    # Get all matches for this group
    grp_matches = Match.query.filter_by(
        tournament_id=tournament.id, round_type='group',
    ).all()
    grp_matches = [m for m in grp_matches
                   if m.round_name.split('_')[0] == f'group{group_label}']

    # Get participants in this group
    participants = TournamentParticipant.query.filter_by(
        tournament_id=tournament.id, group_label=group_label,
    ).order_by(TournamentParticipant.id).all()

    # Compute W-L and round diff for each
    records = {}
    for p in participants:
        if p.club_id is None:
            continue
        rec = {'wins': 0, 'losses': 0, 'round_for': 0, 'round_against': 0}
        records[p.club_id] = rec

    for m in grp_matches:
        if m.status != 'completed' or m.team_a_score is None:
            continue
        if m.team_a_id in records:
            records[m.team_a_id]['round_for'] += m.team_a_score
            records[m.team_a_id]['round_against'] += m.team_b_score
            if m.winner_id == m.team_a_id:
                records[m.team_a_id]['wins'] += 1
            else:
                records[m.team_a_id]['losses'] += 1
        if m.team_b_id in records:
            records[m.team_b_id]['round_for'] += m.team_b_score
            records[m.team_b_id]['round_against'] += m.team_a_score
            if m.winner_id == m.team_b_id:
                records[m.team_b_id]['wins'] += 1
            else:
                records[m.team_b_id]['losses'] += 1

    # Build standings list
    standings = []
    for p in participants:
        rec = records.get(p.club_id)
        if rec is None:
            continue
        # Determine status based on which matches have been played
        all_done = all(m.status == 'completed' for m in grp_matches)
        decider_done = any(
            m.status == 'completed' and 'decider' in m.round_name
            for m in grp_matches
        )

        # If group is fully done, top 2 qualified, rest eliminated
        if decider_done:
            sorted_records = sorted(records.items(), key=lambda x: (-x[1]['wins'], x[1]['losses']))
            team_rank = next(
                (idx + 1 for idx, (cid, _) in enumerate(sorted_records) if cid == p.club_id),
                99
            )
            status = 'qualified' if team_rank <= 2 else 'eliminated'
        else:
            # No matches played yet or only opening done
            status = 'pending'

        standings.append({
            'rank': 0,  # filled in after sort
            'club': p.club,
            'wins': rec['wins'],
            'losses': rec['losses'],
            'round_for': rec['round_for'],
            'round_against': rec['round_against'],
            'round_diff': rec['round_for'] - rec['round_against'],
            'round_record': f"{rec['round_for']}-{rec['round_against']}",
            'status': status,
        })

    # Sort: wins desc, losses asc, round_diff desc
    standings.sort(key=lambda s: (-s['wins'], s['losses'], -s['round_diff']))
    for i, s in enumerate(standings):
        s['rank'] = i + 1
        # Update status based on final rank
        if s['status'] == 'qualified' or s['status'] == 'eliminated':
            pass  # keep
        elif s['rank'] <= 2:
            s['status'] = 'qualified'  # projected
        else:
            s['status'] = 'eliminated'  # projected

    return standings


def get_group_matches(tournament):
    """Return GSL group match templates for Champion."""
    return champion.get_gsl_matches(None, 'A')  # Just for template reference
