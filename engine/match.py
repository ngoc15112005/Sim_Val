"""Match simulation with weighted random outcomes and regional meta DNA."""

import random
from models import db, Match, MatchMap


def _calc_region_bonus(region, tour_type, is_grand_final, is_champions, is_masters):
    """Calculate regional meta modifier for international matches.

    Regional Meta Traits:
    - Americas: Heavily buffed (+3% base, +3% at Champions, +3% in Grand Finals/BO5).
    - EMEA: Slightly buffed in regular rounds (+3% macro), but suffers 'Silver Curse' (-5%) in Grand Finals.
    - China: Heavily debuffed (-7% international pace), with 8% chance of 'ZmjjKK God Mode' (+8%).
    - Pacific: Buffed in Masters (+5% explosive Masters tempo).
    """
    if not region:
        return 0.0

    bonus = 0.0
    if region == 'americas':
        bonus += 0.03  # Base Americas buff in international LAN
        if is_champions:
            bonus += 0.03  # Champions world stage Kings
        if is_grand_final:
            bonus += 0.03  # Grand final clutch & mental factor
    elif region == 'emea':
        if is_grand_final:
            bonus -= 0.05  # 'Silver Curse' - choke in Grand Finals
        else:
            bonus += 0.03  # Solid macro in groups & early playoffs
    elif region == 'china':
        if random.random() < 0.08:
            bonus += 0.08  # 'ZmjjKK Mode' (8% chance of god-tier carry)
        else:
            bonus -= 0.07  # Heavy debuff against international opposition
    elif region == 'pacific':
        if is_masters:
            bonus += 0.05  # Masters specialist (fast tempo & aim duel)
    return bonus


def _calc_win_rate(rating_a, rating_b, streak_a=0, streak_b=0, match=None):
    """Calculate probability of team_a winning.

    Philosophy:
    - In-tournament 'Cỏ lúa bằng nhau': Base probability starts at 0.50 (50%).
      Base rating differences only give a minimal edge (±2% to ±3% max).
    - Seed 1 Curse: Teams entering playoffs directly without warm-up suffer 'Cold Start' (-4%).
    - Warm-up / Momentum: Teams playing multiple matches from Swiss/lower bracket gain momentum (+3%).
    - Regional DNA: Buffs/debuffs applied in cross-region matches (Americas buff, EMEA choke in finals,
      China heavy debuff with rare god-carry, Pacific Masters buff).
    - Returns clamped probability (0.18 - 0.82).
    """
    prob_a = 0.50

    # 1. 'Cỏ lúa bằng nhau' - Rating difference has very compressed influence (max ~±3%)
    rating_diff = rating_a - rating_b
    prob_a += (rating_diff / 50.0) * 0.03

    # 2. Context from match (Tournament, Seeds, Rounds, Regions)
    if match:
        tour = match.tournament
        tour_type = tour.type if tour else None
        round_type = (match.round_type or '').lower()
        round_name = (match.round_name or '').lower()

        is_grand_final = (round_type == 'grand' or 'grand' in round_name)
        is_masters = (tour_type in ('major', 'master'))
        is_champions = (tour_type == 'champion')

        team_a = match.team_a
        team_b = match.team_b
        region_a = team_a.region.slug if (team_a and team_a.region) else None
        region_b = team_b.region.slug if (team_b and team_b.region) else None

        # Regional Seeds and Match Count in Tournament
        seed_a = 2
        seed_b = 2
        prior_a = 0
        prior_b = 0

        if tour:
            if tour.participants:
                for p in tour.participants:
                    if p.club_id == match.team_a_id and p.regional_seed:
                        seed_a = p.regional_seed
                    elif p.club_id == match.team_b_id and p.regional_seed:
                        seed_b = p.regional_seed

            if tour.matches:
                for m in tour.matches:
                    if m.status == 'completed' and m.id != match.id:
                        if m.team_a_id == match.team_a_id or m.team_b_id == match.team_a_id:
                            prior_a += 1
                        if m.team_a_id == match.team_b_id or m.team_b_id == match.team_b_id:
                            prior_b += 1

        # Seed Difference Advantage (minor: ~1% per seed step)
        seed_diff = seed_b - seed_a
        prob_a += seed_diff * 0.01

        # 'Seed 1 Curse' (Cold Start in first playoff match)
        is_playoff = round_type in ('upper', 'lower', 'playoff', 'grand')
        if seed_a == 1 and prior_a == 0 and is_playoff:
            prob_a -= 0.04  # Team A cold start
        if seed_b == 1 and prior_b == 0 and is_playoff:
            prob_a += 0.04  # Team B cold start (favors Team A)

        # Warm-up / Match Rhythm (teams having fought through Swiss or lower bracket)
        if prior_a >= 2 and prior_b < 2:
            prob_a += 0.03
        elif prior_b >= 2 and prior_a < 2:
            prob_a -= 0.03

        # Streak Bonus (hot hands)
        streak_diff = min(streak_a, 3) - min(streak_b, 3)
        prob_a += streak_diff * 0.015

        # Regional Meta DNA (cross-region matches only)
        if region_a and region_b and region_a != region_b:
            bonus_a = _calc_region_bonus(region_a, tour_type, is_grand_final, is_champions, is_masters)
            bonus_b = _calc_region_bonus(region_b, tour_type, is_grand_final, is_champions, is_masters)
            prob_a += (bonus_a - bonus_b)
    else:
        # Fallback if match instance not passed
        form_bonus_a = min(streak_a * 1, 3)
        form_bonus_b = min(streak_b * 1, 3)
        prob_a += (form_bonus_a - form_bonus_b) * 0.01

    # Clamp win rate within realistic, exciting bounds
    return max(0.18, min(0.82, prob_a))


def _gen_map_score(our_rating, their_rating, is_bo5=False):
    """Generate a realistic Valorant map score.

    Reflects the 'cỏ lúa bằng nhau' philosophy with predominantly close games,
    overtimes, and rare blowouts.
    """
    roll = random.random()

    # 45% close / overtime games (13-11, 13-10, 14-12, 15-13, 16-14)
    # 40% standard games (13-9, 13-8, 13-7)
    # 15% dominant map (13-6, 13-5, 13-4, 13-3)
    if roll < 0.45:
        score_pool = [
            (13, 11), (13, 10), (14, 12), (15, 13), (16, 14), (13, 11), (13, 10),
        ]
    elif roll < 0.85:
        score_pool = [
            (13, 9), (13, 8), (13, 7), (13, 9), (13, 8),
        ]
    else:
        score_pool = [
            (13, 6), (13, 5), (13, 4), (13, 3),
        ]

    our_score, their_score = random.choice(score_pool)
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

    win_rate_a = _calc_win_rate(rating_a, rating_b, streak_a, streak_b, match=match)

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
            wins_a += 1
            maps_data.append({
                'map_number': map_num,
                'team_a_score': our_score,
                'team_b_score': their_score,
                'winner_id': match.team_a_id,
            })
        else:
            their_score, our_score = _gen_map_score(rating_b, rating_a, is_bo5)
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
            Or list of shorthand string lines like '13*-8 W'.
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
