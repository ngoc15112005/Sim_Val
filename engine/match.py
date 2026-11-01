"""Match simulation with weighted random outcomes, regional meta DNA, and power-based map scores."""

import random
from typing import List, Dict, Any, Optional, Tuple
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


def calc_pure_international_win_rate(
    region_a=None,
    region_b=None,
    tour_type=None,
    is_grand_final=False,
    is_playoff=False,
    seed_a=2,
    seed_b=2,
    prior_a=0,
    prior_b=0,
    streak_a=0,
    streak_b=0,
):
    """Calculate win probability for team A in an international match.

    Philosophy:
    - Base probability is strictly 0.50 (50/50 equal ground). Rating is NOT added.
    - Seed difference advantage: ~1% per seed step.
    - Seed 1 Curse: Teams entering playoffs directly without warm-up suffer 'Cold Start' (-4%).
    - Warm-up / Match Rhythm: Teams having fought through Swiss or lower bracket gain momentum (+3%).
    - Streak Bonus: +1.5% per consecutive win (clamped to max 3).
    - Regional Meta DNA: Cross-region modifiers (Americas, EMEA Silver Curse, China debuff/ZmjjKK carry, Pacific Masters).
    - Returns clamped probability in [0.18, 0.82].
    """
    prob_a = 0.50

    is_masters = (tour_type in ('major', 'master'))
    is_champions = (tour_type == 'champion')

    # Seed Difference Advantage (minor: ~1% per seed step)
    seed_diff = (seed_b or 2) - (seed_a or 2)
    prob_a += seed_diff * 0.01

    # 'Seed 1 Curse' (Cold Start in first playoff match)
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
    streak_diff = min(streak_a or 0, 3) - min(streak_b or 0, 3)
    prob_a += streak_diff * 0.015

    # Regional Meta DNA (cross-region matches only)
    if region_a and region_b and region_a != region_b:
        bonus_a = _calc_region_bonus(region_a, tour_type, is_grand_final, is_champions, is_masters)
        bonus_b = _calc_region_bonus(region_b, tour_type, is_grand_final, is_champions, is_masters)
        prob_a += (bonus_a - bonus_b)

    return max(0.18, min(0.82, prob_a))


def _calc_win_rate(rating_a, rating_b, streak_a=0, streak_b=0, match=None):
    """Calculate probability of team_a winning.

    Philosophy:
    - In-tournament 'Cỏ lúa bằng nhau': Base probability starts at 0.50 (50%).
      Power rating does NOT affect win/loss probability at all.
      (Power rating is only used for pre-tournament seeding and map score generation).
    - Seed 1 Curse: Teams entering playoffs directly without warm-up suffer 'Cold Start' (-4%).
    - Warm-up / Momentum: Teams playing multiple matches from Swiss/lower bracket gain momentum (+3%).
    - Regional DNA: Buffs/debuffs applied in cross-region matches (Americas buff, EMEA choke in finals,
      China heavy debuff with rare god-carry, Pacific Masters buff).
    - Returns clamped probability (0.18 - 0.82).
    """
    # Context from match (Tournament, Seeds, Rounds, Regions)
    if match:
        tour = match.tournament
        tour_type = tour.type if tour else None
        round_type = (match.round_type or '').lower()
        round_name = (match.round_name or '').lower()

        is_grand_final = (round_type == 'grand' or 'grand' in round_name)
        is_playoff = round_type in ('upper', 'lower', 'playoff', 'grand', 'third_place')

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

        return calc_pure_international_win_rate(
            region_a=region_a,
            region_b=region_b,
            tour_type=tour_type,
            is_grand_final=is_grand_final,
            is_playoff=is_playoff,
            seed_a=seed_a,
            seed_b=seed_b,
            prior_a=prior_a,
            prior_b=prior_b,
            streak_a=streak_a,
            streak_b=streak_b,
        )
    else:
        # Fallback if match instance not passed
        form_bonus_a = min(streak_a * 1, 3)
        form_bonus_b = min(streak_b * 1, 3)
        prob_a = 0.50 + (form_bonus_a - form_bonus_b) * 0.01
        return max(0.18, min(0.82, prob_a))


def _gen_map_score(winner_rating, loser_rating, is_bo5=False):
    """Generate map score based on power rating difference.

    Philosophy:
    - Who wins the map is decided by the game engine (equal ground, regional meta, seed curse).
    - Once the winner is determined, the SCORE itself strongly reflects the power rating difference:
      * Massive favorite won (diff >= 25): Complete stomp (13-2, 13-3, 13-4, 13-5, 13-6).
      * Clear favorite won (15 <= diff < 25): Solid blowout (13-4, 13-5, 13-6, 13-7, 13-8).
      * Moderate favorite won (8 <= diff < 15): Decisive control (13-6, 13-7, 13-8, 13-9, 13-10).
      * Slight favorite won (2 <= diff < 8): Standard competitive win (13-8, 13-9, 13-10, 13-11).
      * Even match (-5 <= diff < 2): Close battle (13-9, 13-10, 13-11, 14-12, 15-13).
      * Underdog won (-15 <= diff < -5): Tough, clutch upset (13-10, 13-11, 14-12, 15-13).
      * Massive underdog won (diff < -15): Intense thriller / overtime epic (13-11, 14-12, 15-13, 16-14, 17-15).
    """
    diff = winner_rating - loser_rating

    if diff >= 25:
        score_pool = [(13, 2), (13, 3), (13, 4), (13, 5), (13, 6)]
    elif diff >= 15:
        score_pool = [(13, 4), (13, 5), (13, 6), (13, 7), (13, 8)]
    elif diff >= 8:
        score_pool = [(13, 6), (13, 7), (13, 8), (13, 9), (13, 10)]
    elif diff >= 2:
        score_pool = [(13, 8), (13, 9), (13, 10), (13, 11)]
    elif diff >= -5:
        score_pool = [(13, 9), (13, 10), (13, 11), (14, 12), (15, 13)]
    elif diff >= -15:
        score_pool = [(13, 10), (13, 11), (14, 12), (15, 13)]
    else:
        score_pool = [(13, 11), (14, 12), (15, 13), (16, 14), (17, 15)]

    return random.choice(score_pool)


def validate_and_normalize_manual_maps(
    maps: List[Dict[str, Any]],
    bo: int = 3,
    id_a: Optional[int] = None,
    id_b: Optional[int] = None,
    forced_winner_id: Optional[int] = None,
) -> Tuple[int, int, Optional[int], Optional[int], List[Dict[str, Any]]]:
    """Validate and sanitize manual map scores according to official Valorant rules.

    Enforces:
    - Max maps cannot exceed bo.
    - Scores must be non-negative integers.
    - No draw rounds: exactly one team has higher score.
    - Standard win: winner has >= 13.
    - Overtime win: if both >= 12, winner must lead by exactly 2 rounds (e.g. 14-12, 15-13).
    - Auto-align winner_id with map scores so stats and bracket never contradict.

    Returns:
    (wins_a, wins_b, winner_id, loser_id, sanitized_maps)
    """
    if not maps:
        raise ValueError("Danh sách bản đồ không được để trống khi nhập điểm thủ công.")

    max_maps = bo

    if len(maps) > max_maps:
        raise ValueError(f"Số lượng bản đồ ({len(maps)}) vượt quá giới hạn thể thức BO{bo} (tối đa {max_maps} map).")

    sanitized_maps = []
    wins_a = 0
    wins_b = 0

    for idx, m in enumerate(maps, 1):
        try:
            sc_a = int(m.get('team_a_score', 0))
            sc_b = int(m.get('team_b_score', 0))
        except (ValueError, TypeError):
            raise ValueError(f"Bản đồ {idx}: Điểm số phải là số nguyên hợp lệ.")

        if sc_a < 0 or sc_b < 0:
            raise ValueError(f"Bản đồ {idx}: Điểm số không được là số âm ({sc_a} - {sc_b}).")

        if sc_a == sc_b:
            raise ValueError(f"Bản đồ {idx}: Không được có kết quả hòa ({sc_a} - {sc_b}). Trong Valorant bắt buộc phải có đội thắng.")

        w_sc = max(sc_a, sc_b)
        l_sc = min(sc_a, sc_b)

        if w_sc < 13:
            raise ValueError(f"Bản đồ {idx}: Đội thắng phải đạt tối thiểu 13 round ({sc_a} - {sc_b}).")

        # Overtime rule: if loser >= 12, difference must be exactly 2
        if l_sc >= 12 and (w_sc - l_sc) != 2:
            raise ValueError(f"Bản đồ {idx}: Trong Overtime, đội thắng phải cách biệt đúng 2 round (ví dụ 14-12, 15-13, không thể là {sc_a}-{sc_b}).")

        w_id = id_a if sc_a > sc_b else id_b
        if sc_a > sc_b:
            wins_a += 1
        else:
            wins_b += 1

        sanitized_maps.append({
            'map_number': m.get('map_number', idx),
            'team_a_score': sc_a,
            'team_b_score': sc_b,
            'winner_id': w_id,
        })

    if wins_a == wins_b:
        raise ValueError("Số map thắng đang bằng nhau, trận đấu phải có đội giành chiến thắng.")

    # Determine real winner based on map scores
    actual_winner_id = id_a if wins_a > wins_b else id_b
    actual_loser_id = id_b if wins_a > wins_b else id_a

    return wins_a, wins_b, actual_winner_id, actual_loser_id, sanitized_maps


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

    # Power rating ban đầu dùng để quyết định tỷ số ván đấu (map score)
    rating_a = match.team_a.base_rating if match.team_a.base_rating else match.team_a.current_rating
    rating_b = match.team_b.base_rating if match.team_b.base_rating else match.team_b.current_rating

    # Tỉ lệ thắng thuần túy theo gameplay (cỏ lúa bằng nhau, vùng miền, seed curse)
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
            # Team A thắng ván này: rating_a là winner, rating_b là loser
            our_score, their_score = _gen_map_score(rating_a, rating_b, is_bo5)
            wins_a += 1
            maps_data.append({
                'map_number': map_num,
                'team_a_score': our_score,
                'team_b_score': their_score,
                'winner_id': match.team_a_id,
            })
        else:
            # Team B thắng ván này: rating_b là winner, rating_a là loser
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
            winner_id = item.get('winner_id')
            if not winner_id:
                winner_id = match.team_a_id if ta_score > tb_score else match.team_b_id
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
