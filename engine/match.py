"""Match simulation with weighted random outcomes."""

import random
from models import db, Match, MatchMap


def _calc_win_rate(rating_a, rating_b, streak_a=0, streak_b=0):
    """Calculate probability of team_a winning.

    Uses rating diff + form bonus (streak).
    Returns 0.0 - 1.0.
    """
    form_bonus_a = min(streak_a * 3, 15)
    form_bonus_b = min(streak_b * 3, 15)
    adj_a = rating_a + form_bonus_a
    adj_b = rating_b + form_bonus_b

    diff = adj_a - adj_b

    if diff <= -40:
        return 0.12
    elif diff <= -30:
        return 0.18
    elif diff <= -20:
        return 0.25
    elif diff <= -15:
        return 0.30
    elif diff <= -10:
        return 0.35
    elif diff <= -5:
        return 0.42
    elif diff <= 0:
        return 0.48
    elif diff <= 5:
        return 0.55
    elif diff <= 10:
        return 0.62
    elif diff <= 15:
        return 0.68
    elif diff <= 20:
        return 0.73
    elif diff <= 30:
        return 0.80
    elif diff <= 40:
        return 0.86
    else:
        return 0.90


def _gen_map_score(our_rating, their_rating, is_bo5=False):
    """Generate a random map score.

    Returns (our_score, their_score) with typical Valorant score distribution.
    """
    diff = our_rating - their_rating

    roll = random.random()

    score_pool = []
    if diff > 20:
        score_pool = [
            (13, 3), (13, 4), (13, 5), (13, 6), (13, 7),
            (13, 8), (13, 9), (14, 12), (13, 11), (13, 10),
        ]
    elif diff > 10:
        score_pool = [
            (13, 5), (13, 6), (13, 7), (13, 8), (13, 9),
            (13, 10), (13, 11), (14, 12), (13, 4),
        ]
    elif diff > 0:
        score_pool = [
            (13, 9), (13, 10), (13, 11), (14, 12), (13, 8),
            (13, 7), (15, 13), (16, 14),
        ]
    elif diff >= -10:
        score_pool = [
            (13, 9), (13, 10), (13, 11), (14, 12), (13, 8),
            (11, 13), (12, 14), (15, 13), (16, 14),
        ]
    else:
        score_pool = [
            (13, 10), (13, 11), (14, 12), (13, 9), (13, 8),
        ]

    our_score, their_score = random.choice(score_pool)

    if random.random() < 0.08:
        their_score = max(their_score - 1, 0)
    if random.random() < 0.08:
        our_score = max(our_score - 1, 0)

    return our_score, their_score


def simulate_match(match, streak_a=0, streak_b=0):
    """Simulate a single match and save map results.

    Args:
        match: Match model instance (with team_a and team_b loaded).
        streak_a: Consecutive wins for team_a.
        streak_b: Consecutive wins for team_b.

    Returns: (winner_club_id, maps_data_list).
    """
    if match.team_a_score is not None:
        return match.winner_id, [m.to_dict() for m in match.maps]

    rating_a = match.team_a.current_rating
    rating_b = match.team_b.current_rating

    win_rate_a = _calc_win_rate(rating_a, rating_b, streak_a, streak_b)

    is_bo5 = False
    if match.round_type == 'grand':
        is_bo5 = True
    elif match.round_type == 'lower' and match.round_name == 'lower_final':
        is_bo5 = True
    max_maps = 5 if is_bo5 else 3
    target_wins = 3 if max_maps == 5 else 2

    wins_a = 0
    wins_b = 0
    maps_data = []

    for i in range(max_maps * 2 - 1):
        map_num = i + 1

        roll = random.random()
        if roll < win_rate_a:
            our_score, their_score = _gen_map_score(rating_a, rating_b, is_bo5)
            map_winner = match.team_a_id
            wins_a += 1
            maps_data.append({
                'map_number': map_num,
                'team_a_score': our_score,
                'team_b_score': their_score,
                'winner_id': match.team_a_id,
            })
        else:
            their_score, our_score = _gen_map_score(rating_b, rating_a, is_bo5)
            map_winner = match.team_b_id
            wins_b += 1
            maps_data.append({
                'map_number': map_num,
                'team_a_score': our_score,
                'team_b_score': their_score,
                'winner_id': match.team_b_id,
            })

        if wins_a >= target_wins or wins_b >= target_wins:
            break

    winner_id = match.team_a_id if wins_a >= target_wins else match.team_b_id
    loser_id = match.team_b_id if winner_id == match.team_a_id else match.team_a_id

    match.team_a_score = wins_a
    match.team_b_score = wins_b
    match.winner_id = winner_id
    match.loser_id = loser_id
    match.status = 'completed'

    for mdata in maps_data:
        mp = MatchMap(
            match_id=match.id,
            map_number=mdata['map_number'],
            team_a_score=mdata['team_a_score'],
            team_b_score=mdata['team_b_score'],
            winner_id=mdata['winner_id'],
        )
        db.session.add(mp)

    db.session.flush()
    return winner_id, maps_data


def resolve_manual_match(match, maps_input):
    """Set match result from manual input.

    Args:
        match: Match model instance.
        maps_input: List of dicts with keys: team_a_score, team_b_score, winner_id.
            Or list of strings in shorthand format: ['13*-8 W', '11-13* L'].
    """
    MatchMap.query.filter_by(match_id=match.id).delete()

    wins_a = 0
    wins_b = 0

    for i, item in enumerate(maps_input):
        if isinstance(item, str):
            from engine.parser import parse_map_line
            parsed = parse_map_line(item)
            if not parsed:
                continue
            if parsed['result'] == 'W':
                ta_score = parsed['our_score']
                tb_score = parsed['their_score']
                winner_id = match.team_a_id
                wins_a += 1
            else:
                ta_score = parsed['their_score']
                tb_score = parsed['our_score']
                winner_id = match.team_b_id
                wins_b += 1
        else:
            ta_score = item.get('team_a_score', 0)
            tb_score = item.get('team_b_score', 0)
            winner_id = item.get('winner_id', match.team_a_id)
            if winner_id == match.team_a_id:
                wins_a += 1
            else:
                wins_b += 1

        mp = MatchMap(
            match_id=match.id, map_number=i + 1,
            team_a_score=ta_score, team_b_score=tb_score,
            winner_id=winner_id,
        )
        db.session.add(mp)

    match.team_a_score = wins_a
    match.team_b_score = wins_b
    match.winner_id = match.team_a_id if wins_a > wins_b else match.team_b_id
    match.loser_id = match.team_b_id if match.winner_id == match.team_a_id else match.team_a_id
    match.status = 'completed'
    match.is_manual = True

    db.session.flush()
    return match.winner_id
