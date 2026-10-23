"""Service for exporting and importing tournaments to and from portable JSON format."""

from datetime import datetime, timezone
from models import db, Region, Club, Tournament, TournamentParticipant, Match, MatchMap, ClubRating


def export_tournament_dict(tour):
    """Serialize a single Tournament into a portable dictionary."""
    participants_data = []
    for p in tour.participants:
        participants_data.append({
            'seed': p.seed,
            'regional_seed': p.regional_seed,
            'region': p.region,
            'group_label': p.group_label,
            'final_rank': p.final_rank,
            'club_code': p.club.short_code if p.club else None,
            'club_name': p.club.name if p.club else None,
        })

    matches_data = []
    # Order matches by match_order
    sorted_matches = sorted(tour.matches, key=lambda m: m.match_order or 0)
    for m in sorted_matches:
        maps_data = []
        sorted_maps = sorted(m.maps, key=lambda mp: mp.map_number or 0)
        for mp in sorted_maps:
            maps_data.append({
                'map_number': mp.map_number,
                'team_a_score': mp.team_a_score,
                'team_b_score': mp.team_b_score,
                'winner_code': mp.winner.short_code if mp.winner else None,
            })

        matches_data.append({
            'round_type': m.round_type,
            'round_name': m.round_name,
            'match_order': m.match_order,
            'team_a_code': m.team_a.short_code if m.team_a else None,
            'team_b_code': m.team_b.short_code if m.team_b else None,
            'team_a_score': m.team_a_score,
            'team_b_score': m.team_b_score,
            'winner_code': m.winner.short_code if m.winner else None,
            'loser_code': m.loser.short_code if m.loser else None,
            'status': m.status,
            'is_manual': bool(m.is_manual),
            'maps': maps_data,
        })

    ratings_data = []
    ratings = ClubRating.query.filter_by(tournament_id=tour.id).all()
    for r in ratings:
        ratings_data.append({
            'club_code': r.club.short_code if r.club else None,
            'rating_before': r.rating_before,
            'rating_after': r.rating_after,
        })

    created_at_str = tour.created_at.isoformat() if tour.created_at else datetime.now(timezone.utc).isoformat()

    return {
        'version': '1.0',
        'id': tour.id,
        'type': tour.type,
        'name': tour.name,
        'status': tour.status,
        'created_at': created_at_str,
        'participants': participants_data,
        'matches': matches_data,
        'ratings': ratings_data,
    }


def export_all_tournaments_dict():
    """Serialize all tournaments into a single backup structure."""
    tournaments = Tournament.query.order_by(Tournament.created_at.desc()).all()
    return {
        'version': '1.0',
        'exported_at': datetime.now(timezone.utc).isoformat(),
        'count': len(tournaments),
        'tournaments': [export_tournament_dict(t) for t in tournaments],
    }


def _find_or_create_club(code, name=None, clubs_by_code=None, clubs_by_name=None, default_region=None):
    """Find a club by short code or name, or create a placeholder if missing."""
    if not code and not name:
        return None

    code_key = (code or '').strip().upper()
    name_key = (name or '').strip().lower()

    if code_key and clubs_by_code and code_key in clubs_by_code:
        return clubs_by_code[code_key]

    if name_key and clubs_by_name and name_key in clubs_by_name:
        return clubs_by_name[name_key]

    # Try querying db directly if not in caches
    if code_key:
        c = Club.query.filter_by(short_code=code_key).first()
        if c:
            if clubs_by_code is not None:
                clubs_by_code[code_key] = c
            return c

    if name_key:
        c = Club.query.filter(Club.name.ilike(name_key)).first()
        if c:
            if clubs_by_name is not None:
                clubs_by_name[name_key] = c
            return c

    # Create placeholder club to avoid failing import
    reg_id = default_region.id if default_region else 1
    new_club = Club(
        name=name or code or 'Unknown Club',
        short_code=code_key or 'UNK',
        region_id=reg_id,
        base_rating=80,
        current_rating=80,
    )
    db.session.add(new_club)
    db.session.flush()

    if clubs_by_code is not None and new_club.short_code:
        clubs_by_code[new_club.short_code.upper()] = new_club
    if clubs_by_name is not None and new_club.name:
        clubs_by_name[new_club.name.lower()] = new_club

    return new_club


def import_tournament_dict(tour_dict):
    """Import a single tournament dictionary into database. Returns the Tournament instance."""
    clubs_by_code = {c.short_code.upper(): c for c in Club.query.all()}
    clubs_by_name = {c.name.lower(): c for c in Club.query.all()}
    default_region = Region.query.first()

    tour_type = tour_dict.get('type', 'major')
    name = tour_dict.get('name', 'Imported Tournament')
    status = tour_dict.get('status', 'setup')

    created_at = None
    created_at_raw = tour_dict.get('created_at')
    if created_at_raw:
        try:
            created_at = datetime.fromisoformat(created_at_raw)
        except Exception:
            created_at = datetime.now(timezone.utc)
    else:
        created_at = datetime.now(timezone.utc)

    new_tour = Tournament(
        type=tour_type,
        name=name,
        status=status,
        created_at=created_at,
    )
    db.session.add(new_tour)
    db.session.flush()

    # 1. Participants
    for p_data in tour_dict.get('participants', []):
        club = _find_or_create_club(
            p_data.get('club_code'),
            p_data.get('club_name'),
            clubs_by_code,
            clubs_by_name,
            default_region,
        )
        if club:
            tp = TournamentParticipant(
                tournament_id=new_tour.id,
                club_id=club.id,
                seed=p_data.get('seed'),
                regional_seed=p_data.get('regional_seed'),
                region=p_data.get('region') or (club.region.slug if club.region else None),
                group_label=p_data.get('group_label'),
                final_rank=p_data.get('final_rank'),
            )
            db.session.add(tp)

    # 2. Matches & Maps
    for m_data in tour_dict.get('matches', []):
        team_a = _find_or_create_club(m_data.get('team_a_code'), None, clubs_by_code, clubs_by_name, default_region) if m_data.get('team_a_code') else None
        team_b = _find_or_create_club(m_data.get('team_b_code'), None, clubs_by_code, clubs_by_name, default_region) if m_data.get('team_b_code') else None
        winner = _find_or_create_club(m_data.get('winner_code'), None, clubs_by_code, clubs_by_name, default_region) if m_data.get('winner_code') else None
        loser = _find_or_create_club(m_data.get('loser_code'), None, clubs_by_code, clubs_by_name, default_region) if m_data.get('loser_code') else None

        match = Match(
            tournament_id=new_tour.id,
            round_type=m_data.get('round_type', 'playoffs'),
            round_name=m_data.get('round_name', ''),
            match_order=m_data.get('match_order', 0),
            team_a_id=team_a.id if team_a else None,
            team_b_id=team_b.id if team_b else None,
            team_a_score=m_data.get('team_a_score'),
            team_b_score=m_data.get('team_b_score'),
            winner_id=winner.id if winner else None,
            loser_id=loser.id if loser else None,
            status=m_data.get('status', 'pending'),
            is_manual=bool(m_data.get('is_manual', False)),
        )
        db.session.add(match)
        db.session.flush()

        for map_data in m_data.get('maps', []):
            map_winner = _find_or_create_club(map_data.get('winner_code'), None, clubs_by_code, clubs_by_name, default_region) if map_data.get('winner_code') else None
            mm = MatchMap(
                match_id=match.id,
                map_number=map_data.get('map_number', 1),
                team_a_score=map_data.get('team_a_score', 0),
                team_b_score=map_data.get('team_b_score', 0),
                winner_id=map_winner.id if map_winner else None,
            )
            db.session.add(mm)

    # 3. Ratings
    for r_data in tour_dict.get('ratings', []):
        club = _find_or_create_club(r_data.get('club_code'), None, clubs_by_code, clubs_by_name, default_region) if r_data.get('club_code') else None
        if club:
            cr = ClubRating(
                tournament_id=new_tour.id,
                club_id=club.id,
                rating_before=r_data.get('rating_before', 80),
                rating_after=r_data.get('rating_after', 80),
            )
            db.session.add(cr)

    return new_tour


def import_payload(payload):
    """Import tournament(s) from a parsed JSON payload.
    Supports:
      - {"tournament": {...}}
      - {"tournaments": [{...}, ...]}
      - [{...}, ...]
      - {...} (direct tournament dict)
    Returns list of imported Tournament objects.
    """
    tournaments_to_import = []

    if isinstance(payload, list):
        tournaments_to_import = payload
    elif isinstance(payload, dict):
        if 'tournaments' in payload and isinstance(payload['tournaments'], list):
            tournaments_to_import = payload['tournaments']
        elif 'tournament' in payload and isinstance(payload['tournament'], dict):
            tournaments_to_import = [payload['tournament']]
        elif 'matches' in payload or 'type' in payload or 'name' in payload:
            tournaments_to_import = [payload]
        else:
            raise ValueError('Định dạng dữ liệu JSON không hợp lệ.')
    else:
        raise ValueError('Dữ liệu không phải là JSON object hoặc array.')

    if not tournaments_to_import:
        raise ValueError('Không tìm thấy dữ liệu giải đấu nào trong file.')

    created_tournaments = []
    for t_data in tournaments_to_import:
        tour = import_tournament_dict(t_data)
        created_tournaments.append(tour)

    db.session.commit()
    return created_tournaments


def delete_tournament_cascade(tour_id):
    """Safely delete a tournament and all associated matches, maps, participants, ratings."""
    tour = db.session.get(Tournament, tour_id)
    if not tour:
        return False

    db.session.delete(tour)
    db.session.commit()
    return True
