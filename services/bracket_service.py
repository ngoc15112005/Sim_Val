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


def get_group_matches(tournament):
    """Return GSL group match templates for Champion."""
    return champion.get_gsl_matches(None, 'A')  # Just for template reference
