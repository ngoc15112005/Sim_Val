"""Tournament lifecycle: create, bracket generation, progression."""

import random
from models import db, Club, Tournament, TournamentParticipant, Match
from config import Config


def create_tournament(tour_type, name, selected_club_ids):
    """Create a tournament with given participants."""
    cfg = Config.TOURNAMENT_TYPES[tour_type]
    team_count = cfg['team_count']

    if len(selected_club_ids) != team_count:
        raise ValueError(f'{tour_type} can dung {team_count} doi, nhan {len(selected_club_ids)}')

    clubs = Club.query.filter(Club.id.in_(selected_club_ids)).all()
    if len(clubs) != team_count:
        raise ValueError('Mot so club_id khong ton tai')

    club_map = {c.id: c for c in clubs}
    sorted_ids = sorted(selected_club_ids, key=lambda cid: club_map[cid].current_rating, reverse=True)

    tour = Tournament(type=tour_type, name=name, status='setup')
    db.session.add(tour)
    db.session.flush()

    for seed, cid in enumerate(sorted_ids, 1):
        club = club_map[cid]
        p = TournamentParticipant(
            tournament_id=tour.id, club_id=cid, seed=seed,
            region=club.region.slug if club.region else None,
        )
        db.session.add(p)

    db.session.flush()
    return tour


def generate_bracket(tournament):
    """Generate all initial matches based on tournament type."""
    cfg = Config.TOURNAMENT_TYPES[tournament.type]

    if tournament.type == 'champion':
        _generate_groups(tournament)
        tournament.status = 'groups'
    elif tournament.type == 'master':
        _generate_master_swiss_round1(tournament)
        tournament.status = 'swiss'
    else:
        _generate_swiss_round1(tournament, tournament.participants)
        tournament.status = 'swiss'

    db.session.flush()


def _generate_swiss_round1(tournament, participants):
    """Generate Swiss Round 1: random pairing among given participants."""
    teams = list(participants)
    random.shuffle(teams)

    for i in range(0, len(teams), 2):
        p_a = teams[i]
        p_b = teams[i + 1]
        m = Match(
            tournament_id=tournament.id, round_type='swiss',
            round_name='swiss_round1', match_order=i // 2 + 1,
            team_a_id=p_a.club_id, team_b_id=p_b.club_id,
        )
        db.session.add(m)
    db.session.flush()


def _generate_master_swiss_round1(tournament):
    """Master: top 4 seeds auto-qualify playoffs, remaining 8 play Swiss."""
    participants = tournament.participants
    swiss_teams = [p for p in participants if p.seed > 4]
    _generate_swiss_round1(tournament, swiss_teams)


def _get_team_swiss_record(tournament, club_id):
    """Get win-loss record for a team in Swiss stage."""
    matches = Match.query.filter_by(tournament_id=tournament.id, round_type='swiss').all()
    wins = 0
    losses = 0
    for m in matches:
        if m.winner_id is None:
            continue
        if m.team_a_id == club_id:
            wins += int(m.winner_id == club_id)
            losses += int(m.winner_id != club_id)
        elif m.team_b_id == club_id:
            wins += int(m.winner_id == club_id)
            losses += int(m.winner_id != club_id)
    return wins, losses


def _get_all_swiss_records(tournament, participants):
    """Get Swiss records for given participants."""
    records = {}
    for p in participants:
        w, l = _get_team_swiss_record(tournament, p.club_id)
        records[p.club_id] = {'wins': w, 'losses': l, 'participant': p}
    return records


def _swiss_pair_same_record(team_ids, records):
    """Randomly pair teams with matching records. Returns list of (cid_a, cid_b)."""
    teams = list(team_ids)
    random.shuffle(teams)
    pairs = []
    for i in range(0, len(teams), 2):
        if i + 1 < len(teams):
            pairs.append((teams[i], teams[i + 1]))
    return pairs


def _generate_swiss_next_round(tournament, win_target, loss_target, advance_count):
    """Generate next Swiss round based on current records.

    VCT 2025: teams with N wins advance, N losses eliminated.
    """
    cfg = Config.TOURNAMENT_TYPES[tournament.type]
    if tournament.type == 'master':
        swiss_participants = [p for p in tournament.participants if p.seed > 4]
    else:
        swiss_participants = list(tournament.participants)

    records = _get_all_swiss_records(tournament, swiss_participants)

    advanced = {cid for cid, r in records.items() if r['wins'] >= win_target}
    eliminated = {cid for cid, r in records.items() if r['losses'] >= loss_target}
    active = [cid for cid in records if cid not in advanced and cid not in eliminated]

    if not active:
        _finalize_swiss(tournament, records, advance_count)
        return False

    record_groups = {}
    for cid in active:
        key = (records[cid]['wins'], records[cid]['losses'])
        record_groups.setdefault(key, []).append(cid)

    next_order = Match.query.filter_by(tournament_id=tournament.id).count()
    matches_made = 0

    for (w, l), team_ids in sorted(record_groups.items()):
        pairs = _swiss_pair_same_record(team_ids, records)
        current_round = w + l + 1
        for cid_a, cid_b in pairs:
            next_order += 1
            matches_made += 1
            m = Match(
                tournament_id=tournament.id, round_type='swiss',
                round_name=f'swiss_round{current_round}',
                match_order=next_order,
                team_a_id=cid_a, team_b_id=cid_b,
            )
            db.session.add(m)

    db.session.flush()
    if matches_made == 0:
        _finalize_swiss(tournament, records, advance_count)
        return False
    return True


def _finalize_swiss(tournament, records, advance_count):
    """Determine advancing teams from Swiss and generate playoffs."""
    ranked = []
    for cid, rec in records.items():
        w, l = rec['wins'], rec['losses']
        p = rec['participant']
        ranked.append((w, -l, p.club.current_rating, p))

    ranked.sort(key=lambda x: (-x[0], -x[1], -x[2]))

    advancing = []
    swiss_advancing = []
    for i, (w, nl, rating, p) in enumerate(ranked):
        if i < advance_count:
            swiss_advancing.append(p)
        else:
            p.final_rank = 9 + (i - advance_count) if tournament.type == 'major' else 13 + (i - advance_count)

    if tournament.type == 'master':
        directs = [p for p in tournament.participants if p.seed <= 4]
        for dp in directs:
            advancing.append(dp)
        for sp in swiss_advancing:
            sp.seed = 5 + swiss_advancing.index(sp)
            advancing.append(sp)
    else:
        for i, p in enumerate(swiss_advancing):
            p.seed = i + 1
            advancing.append(p)

    _generate_playoffs(tournament, advancing)
    tournament.status = 'playoffs'
    db.session.flush()


def _generate_playoffs(tournament, advancing, draw_order=None):
    """Generate Double Elimination playoffs bracket.

    For 4-team: upper_semifinal_1, upper_semifinal_2, upper_final,
                lower_round1, lower_final, grand_final.
    For 8-team: upper_quarterfinal_1..4, upper_semifinal_1, upper_semifinal_2,
                upper_final, lower_round1_1, lower_round1_2,
                lower_quarterfinal_1, lower_quarterfinal_2,
                lower_semifinal, lower_final, grand_final.
    """
    seeds = sorted(advancing, key=lambda p: (p.seed, p.club.current_rating))
    next_order = 100
    n = len(seeds)

    if n == 4:
        _add_match(tournament, 'upper', 'upper_semifinal_1', next_order,
                   seeds[0], seeds[3])
        _add_match(tournament, 'upper', 'upper_semifinal_2', next_order + 1,
                   seeds[1], seeds[2])
        next_order += 2
        _add_match(tournament, 'upper', 'upper_final', next_order)
        next_order += 1
        _add_match(tournament, 'lower', 'lower_round1', next_order)
        next_order += 1
        _add_match(tournament, 'lower', 'lower_final', next_order)
        next_order += 1
        _add_match(tournament, 'grand', 'grand_final', next_order)

    elif n == 8:
        if tournament.type == 'master':
            _generate_master_quarterfinals(tournament, seeds, draw_order)
        elif tournament.type == 'champion':
            _generate_champion_quarterfinals(tournament, seeds)
        else:
            _add_match(tournament, 'upper', 'upper_quarterfinal_1', next_order,
                       seeds[0], seeds[7])
            _add_match(tournament, 'upper', 'upper_quarterfinal_2', next_order + 1,
                       seeds[1], seeds[6])
            _add_match(tournament, 'upper', 'upper_quarterfinal_3', next_order + 2,
                       seeds[2], seeds[5])
            _add_match(tournament, 'upper', 'upper_quarterfinal_4', next_order + 3,
                       seeds[3], seeds[4])
        next_order += 4

        _add_match(tournament, 'upper', 'upper_semifinal_1', next_order)
        _add_match(tournament, 'upper', 'upper_semifinal_2', next_order + 1)
        next_order += 2

        _add_match(tournament, 'upper', 'upper_final', next_order)
        next_order += 1

        _add_match(tournament, 'lower', 'lower_round1_1', next_order)
        _add_match(tournament, 'lower', 'lower_round1_2', next_order + 1)
        next_order += 2

        _add_match(tournament, 'lower', 'lower_quarterfinal_1', next_order)
        _add_match(tournament, 'lower', 'lower_quarterfinal_2', next_order + 1)
        next_order += 2

        _add_match(tournament, 'lower', 'lower_semifinal', next_order)
        next_order += 1

        _add_match(tournament, 'lower', 'lower_final', next_order)
        next_order += 1

        _add_match(tournament, 'grand', 'grand_final', next_order)

    db.session.flush()


def _generate_master_quarterfinals(tournament, seeds, draw_order=None):
    """Master playoffs: top 4 seeds pick Swiss qualifiers.

    Seeds 1-4 draw random order, each picks opponent from seeds 5-8.
    """
    directs = [s for s in seeds if s.seed <= 4]
    swiss_qualifiers = [s for s in seeds if s.seed > 4]

    pick_order = list(directs)
    random.shuffle(pick_order)
    if draw_order:
        pick_order = draw_order

    available = list(swiss_qualifiers)
    random.shuffle(available)

    next_order = 100
    for i, picker in enumerate(pick_order):
        opponent = available[i]
        _add_match(tournament, 'upper', f'upper_quarterfinal_{i + 1}', next_order + i,
                   picker, opponent)


def _generate_champion_quarterfinals(tournament, seeds):
    """Champion playoffs: group winners vs runners-up with constraints.

    VCT 2025 rules:
      1. Each match pairs 1 group winner with 1 group runner-up.
      2. Teams from same group cannot face each other.
      3. Teams from same group must be on opposite bracket halves.
         Top Half = UQ1+UQ2, Bottom Half = UQ3+UQ4.

    Algorithm: randomly assign winners, then place runners on opposite half.
    """
    winners = [s for s in seeds if s.seed <= 4]
    runners = [s for s in seeds if s.seed >= 5]

    if len(winners) != 4 or len(runners) != 4:
        _generate_playoffs_fallback(tournament, seeds)
        return

    random.shuffle(winners)

    top_runners = []
    bottom_runners = []

    for i, w in enumerate(winners):
        winner_half = 'top' if i < 2 else 'bottom'
        group = w.group_label
        try:
            r = next(r for r in runners if r.group_label == group)
        except StopIteration:
            _generate_playoffs_fallback(tournament, seeds)
            return
        if winner_half == 'top':
            bottom_runners.append(r)
        else:
            top_runners.append(r)

    random.shuffle(top_runners)
    random.shuffle(bottom_runners)

    pairs = [
        (winners[0], top_runners[0]),
        (winners[1], top_runners[1]),
        (winners[2], bottom_runners[0]),
        (winners[3], bottom_runners[1]),
    ]

    next_order = 100
    for i, (p1, p2) in enumerate(pairs):
        _add_match(tournament, 'upper', f'upper_quarterfinal_{i + 1}',
                   next_order + i, p1, p2)


def _generate_playoffs_fallback(tournament, seeds):
    """Fallback: fixed seeding 1v8, 2v7, 3v6, 4v5."""
    seeds_sorted = sorted(seeds, key=lambda p: (p.seed, p.club.current_rating))
    next_order = 100
    _add_match(tournament, 'upper', 'upper_quarterfinal_1', next_order,
               seeds_sorted[0], seeds_sorted[7])
    _add_match(tournament, 'upper', 'upper_quarterfinal_2', next_order + 1,
               seeds_sorted[1], seeds_sorted[6])
    _add_match(tournament, 'upper', 'upper_quarterfinal_3', next_order + 2,
               seeds_sorted[2], seeds_sorted[5])
    _add_match(tournament, 'upper', 'upper_quarterfinal_4', next_order + 3,
               seeds_sorted[3], seeds_sorted[4])


def _add_match(tournament, round_type, round_name, order, p1=None, p2=None):
    def _get_id(obj):
        if obj is None:
            return None
        if hasattr(obj, 'club_id'):
            return obj.club_id
        return obj.id

    m = Match(
        tournament_id=tournament.id, round_type=round_type,
        round_name=round_name, match_order=order,
        team_a_id=_get_id(p1),
        team_b_id=_get_id(p2),
    )
    db.session.add(m)
    return m


def progress_tournament(tournament):
    """Progress tournament to next round/stage.

    Returns dict with action status.
    """
    cfg = Config.TOURNAMENT_TYPES[tournament.type]

    if tournament.status in ('setup',):
        generate_bracket(tournament)
        return {'action': 'bracket_generated', 'status': tournament.status}

    if tournament.status == 'swiss':
        generated = _generate_swiss_next_round(
            tournament,
            win_target=cfg['swiss_win_target'],
            loss_target=cfg['swiss_loss_target'],
            advance_count=cfg['advance_count'],
        )
        if generated:
            return {'action': 'swiss_next'}
        else:
            return {'action': 'swiss_done', 'status': 'playoffs'}

    if tournament.status == 'groups':
        _resolve_group_placeholder_matches(tournament)
        return {'action': 'groups_done', 'status': 'playoffs'}

    if tournament.status == 'playoffs':
        _resolve_playoff_placeholder_matches(tournament)
        if _is_bracket_finished(tournament):
            tournament.status = 'finished'
            return {'action': 'done', 'status': 'finished'}
        return {'action': 'playoffs_progress'}

    return {'action': 'nothing'}


def _resolve_playoff_placeholder_matches(tournament):
    """Fill TBD slots in playoffs after match results."""
    all_matches = Match.query.filter_by(
        tournament_id=tournament.id,
    ).order_by(Match.match_order).all()

    for m in all_matches:
        if m.status == 'completed' or m.round_type in ('swiss', 'group'):
            continue
        if m.team_a_id and m.team_b_id:
            continue

        rn = m.round_name

        if m.round_type == 'upper':
            if 'semifinal_1' in rn:
                _fill_from_winners(tournament, m, all_matches,
                                   ['upper_quarterfinal_1', 'upper_quarterfinal_4'])
            elif 'semifinal_2' in rn:
                _fill_from_winners(tournament, m, all_matches,
                                   ['upper_quarterfinal_2', 'upper_quarterfinal_3'])
            elif 'semifinal' in rn:
                _fill_from_winners(tournament, m, all_matches,
                                   ['upper_semifinal_1', 'upper_semifinal_2'])
            elif 'final' in rn:
                _fill_from_winners(tournament, m, all_matches,
                                   ['upper_semifinal_1', 'upper_semifinal_2'],
                                   fallback=['upper_semifinal_1'])

        elif m.round_type == 'lower':
            if 'round1_1' in rn:
                _fill_from_losers(tournament, m, all_matches,
                                  ['upper_quarterfinal_1', 'upper_quarterfinal_4'])
            elif 'round1_2' in rn:
                _fill_from_losers(tournament, m, all_matches,
                                  ['upper_quarterfinal_2', 'upper_quarterfinal_3'])
            elif 'round1' in rn:
                _fill_from_losers(tournament, m, all_matches,
                                  ['upper_semifinal_1', 'upper_semifinal_2'],
                                  fallback=['upper_semifinal_1'])
            elif 'quarterfinal_1' in rn:
                _fill_cross_bracket(tournament, m, all_matches,
                                    lr1_name='lower_round1_1',
                                    us_loser_names=['upper_semifinal_2'])
            elif 'quarterfinal_2' in rn:
                _fill_cross_bracket(tournament, m, all_matches,
                                    lr1_name='lower_round1_2',
                                    us_loser_names=['upper_semifinal_1'])
            elif 'semifinal' in rn:
                _fill_from_winners(tournament, m, all_matches,
                                   ['lower_quarterfinal_1', 'lower_quarterfinal_2'])
            elif 'final' in rn:
                up_final = _match_by_name(all_matches, 'upper_final')
                lo_semi = _match_by_name(all_matches, 'lower_semifinal')
                lo_r1 = _match_by_name(all_matches, 'lower_round1')
                if up_final and up_final.status == 'completed' and not m.team_b_id:
                    m.team_b_id = up_final.loser.id if up_final.loser else None
                if lo_semi and lo_semi.status == 'completed' and not m.team_a_id:
                    m.team_a_id = lo_semi.winner.id if lo_semi.winner else None
                elif lo_r1 and lo_r1.status == 'completed' and not m.team_a_id:
                    m.team_a_id = lo_r1.winner.id if lo_r1.winner else None

        elif m.round_type == 'grand':
            up_final = _match_by_name(all_matches, 'upper_final')
            lo_final = _match_by_name(all_matches, 'lower_final')
            if up_final and up_final.status == 'completed' and not m.team_a_id:
                m.team_a_id = up_final.winner.id if up_final.winner else None
            if lo_final and lo_final.status == 'completed' and not m.team_b_id:
                m.team_b_id = lo_final.winner.id if lo_final.winner else None

    db.session.flush()


def _fill_from_winners(tournament, m, all_matches, names, fallback=None):
    """Fill match slots from winners of previous matches."""
    winners = []
    for name in names:
        prev = _match_by_name(all_matches, name)
        if prev and prev.status == 'completed' and prev.winner:
            winners.append(prev.winner)

    if len(winners) < 2 and fallback:
        for name in fallback:
            if name not in names:
                prev = _match_by_name(all_matches, name)
                if prev and prev.status == 'completed' and prev.winner:
                    winners.append(prev.winner)
                    break

    if len(winners) >= 1 and not m.team_a_id:
        m.team_a_id = winners[0].id
    if len(winners) >= 2 and not m.team_b_id:
        m.team_b_id = winners[1].id


def _fill_from_losers(tournament, m, all_matches, names, fallback=None):
    """Fill match slots from losers of previous matches."""
    losers = []
    for name in names:
        prev = _match_by_name(all_matches, name)
        if prev and prev.status == 'completed' and prev.loser:
            losers.append(prev.loser)

    if len(losers) < 2 and fallback:
        for name in fallback:
            if name not in names:
                prev = _match_by_name(all_matches, name)
                if prev and prev.status == 'completed' and prev.loser:
                    losers.append(prev.loser)
                    break

    if len(losers) >= 1 and not m.team_a_id:
        m.team_a_id = losers[0].id
    if len(losers) >= 2 and not m.team_b_id:
        m.team_b_id = losers[1].id


def _fill_cross_bracket(tournament, m, all_matches, lr1_name, us_loser_names):
    """Cross bracket: winner of LR1 vs loser of US (from opposite side).

    lower_quarterfinal_1: winner(lower_round1_1) vs loser(upper_semifinal_2)
    lower_quarterfinal_2: winner(lower_round1_2) vs loser(upper_semifinal_1)
    """
    lr1 = _match_by_name(all_matches, lr1_name)
    if lr1 and lr1.status == 'completed' and lr1.winner and not m.team_a_id:
        m.team_a_id = lr1.winner.id

    for name in us_loser_names:
        us = _match_by_name(all_matches, name)
        if us and us.status == 'completed' and us.loser and not m.team_b_id:
            m.team_b_id = us.loser.id
            break


def _match_by_name(matches, name):
    for m in matches:
        if m.round_name == name:
            return m
    return None


def _is_bracket_finished(tournament):
    gf = Match.query.filter_by(tournament_id=tournament.id, round_type='grand').first()
    if gf and gf.status == 'completed':
        _finalize_tournament(tournament)
        return True
    return False


def _finalize_tournament(tournament):
    """Assign final rankings after tournament completes."""
    gf = Match.query.filter_by(tournament_id=tournament.id, round_type='grand').first()
    if not gf or gf.status != 'completed':
        return

    lf = Match.query.filter_by(
        tournament_id=tournament.id, round_name='lower_final',
    ).first()

    rank_map = {}
    rank_map[gf.winner_id] = 1
    rank_map[gf.loser_id] = 2

    if lf and lf.status == 'completed' and lf.loser_id:
        rank_map[lf.loser_id] = 3

    ls = Match.query.filter_by(
        tournament_id=tournament.id, round_name='lower_semifinal',
    ).first()
    if ls and ls.status == 'completed' and ls.loser_id:
        rank_map.setdefault(ls.loser_id, 4)

    for lq_name in ['lower_quarterfinal_1', 'lower_quarterfinal_2']:
        lq = Match.query.filter_by(
            tournament_id=tournament.id, round_name=lq_name, status='completed',
        ).first()
        if lq and lq.loser_id:
            rank_map.setdefault(lq.loser_id, 5)

    for lr_name in ['lower_round1_1', 'lower_round1_2', 'lower_round1']:
        lr = Match.query.filter_by(
            tournament_id=tournament.id, round_name=lr_name, status='completed',
        ).first()
        if lr and lr.loser_id:
            rank_map.setdefault(lr.loser_id, 7)

    for p in tournament.participants:
        if p.final_rank is not None:
            continue
        if p.club_id in rank_map:
            p.final_rank = rank_map[p.club_id]

    db.session.flush()


def simulate_all_pending(tournament):
    """Simulate all pending matches in the tournament, looping through rounds."""
    from engine.match import simulate_match

    for _ in range(50):
        pending = Match.query.filter_by(
            tournament_id=tournament.id, status='pending',
        ).order_by(Match.match_order).all()

        if not pending:
            break

        any_simmed = False
        for m in pending:
            if not m.team_a_id or not m.team_b_id:
                continue
            simulate_match(m)
            any_simmed = True

        if not any_simmed:
            break

        db.session.flush()
        progress_tournament(tournament)
        db.session.flush()

    db.session.flush()


def _generate_groups(tournament):
    """Generate Group Stage (4 groups of 4, GSL format)."""
    participants = list(tournament.participants)
    random.shuffle(participants)

    groups = {}
    for i, p in enumerate(participants):
        grp = i % 4 + 1
        groups.setdefault(grp, []).append(p)

    for grp_num, grp_teams in groups.items():
        random.shuffle(grp_teams)
        t1, t2, t3, t4 = grp_teams

        m1 = Match(
            tournament_id=tournament.id, round_type='group',
            round_name=f'group{grp_num}_opening1',
            match_order=(grp_num - 1) * 10 + 1,
            team_a_id=t1.club_id, team_b_id=t2.club_id,
        )
        db.session.add(m1)

        m2 = Match(
            tournament_id=tournament.id, round_type='group',
            round_name=f'group{grp_num}_opening2',
            match_order=(grp_num - 1) * 10 + 2,
            team_a_id=t3.club_id, team_b_id=t4.club_id,
        )
        db.session.add(m2)

    db.session.flush()


def _resolve_group_placeholder_matches(tournament):
    """After opening matches, generate winners/elimination/decider per group."""
    if tournament.status != 'groups':
        return

    existing = Match.query.filter_by(tournament_id=tournament.id, round_type='group').all()
    existing_names = {m.round_name for m in existing}

    for grp_num in range(1, 5):
        prefix = f'group{grp_num}'
        op1 = Match.query.filter_by(
            tournament_id=tournament.id,
            round_name=f'{prefix}_opening1', status='completed',
        ).first()
        op2 = Match.query.filter_by(
            tournament_id=tournament.id,
            round_name=f'{prefix}_opening2', status='completed',
        ).first()

        if not op1 or not op2:
            continue

        w1, l1 = op1.winner, op1.loser
        w2, l2 = op2.winner, op2.loser

        wm_name = f'{prefix}_winners_match'
        if wm_name not in existing_names:
            _add_match(tournament, 'group', wm_name, 1000 + grp_num * 100 + 10, w1, w2)
            existing_names.add(wm_name)

        em_name = f'{prefix}_elimination_match'
        if em_name not in existing_names:
            _add_match(tournament, 'group', em_name, 1000 + grp_num * 100 + 20, l1, l2)
            existing_names.add(em_name)

        wm = Match.query.filter_by(tournament_id=tournament.id, round_name=wm_name).first()
        em = Match.query.filter_by(tournament_id=tournament.id, round_name=em_name).first()

        if wm and wm.status == 'completed' and em and em.status == 'completed':
            dm_name = f'{prefix}_decider_match'
            if dm_name not in existing_names:
                _add_match(tournament, 'group', dm_name, 1000 + grp_num * 100 + 30,
                           wm.loser, em.winner)
                existing_names.add(dm_name)

    _check_all_groups_done(tournament)


def _check_all_groups_done(tournament):
    dm_matches = Match.query.filter(
        Match.tournament_id == tournament.id,
        Match.round_type == 'group',
        Match.round_name.like('group%_decider_match'),
        Match.status == 'completed',
    ).count()

    if dm_matches >= 4:
        _finalize_groups(tournament)


def _finalize_groups(tournament):
    tournament.status = 'playoffs'

    advancing = []
    for grp_num in range(1, 5):
        prefix = f'group{grp_num}'
        wm = Match.query.filter_by(
            tournament_id=tournament.id,
            round_name=f'{prefix}_winners_match', status='completed',
        ).first()
        dm = Match.query.filter_by(
            tournament_id=tournament.id,
            round_name=f'{prefix}_decider_match', status='completed',
        ).first()

        if wm and wm.winner:
            p = TournamentParticipant.query.filter_by(
                tournament_id=tournament.id, club_id=wm.winner.id).first()
            if p:
                p.seed = grp_num
                p.group_label = chr(64 + grp_num)
                advancing.append(p)
        if dm and dm.winner:
            p = TournamentParticipant.query.filter_by(
                tournament_id=tournament.id, club_id=dm.winner.id).first()
            if p:
                p.seed = grp_num + 4
                p.group_label = chr(64 + grp_num)
                advancing.append(p)

    for p in tournament.participants:
        if p not in advancing and p.final_rank is None:
            p.final_rank = 13

    advancing.sort(key=lambda p: p.seed)
    _generate_playoffs(tournament, advancing)
    db.session.flush()
