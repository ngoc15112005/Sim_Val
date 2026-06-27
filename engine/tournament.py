"""Tournament lifecycle: create, bracket generation, progression.

Delegates format logic to engine/format/ and services/bracket_service.py.
"""

import random
from models import db, Club, Tournament, TournamentParticipant, Match
from config import Config


def create_tournament(tour_type, name, selected_club_ids, regional_seeds=None):
    cfg = Config.TOURNAMENT_TYPES[tour_type]
    team_count = cfg['team_count']

    if len(selected_club_ids) != team_count:
        raise ValueError(f'{tour_type} can dung {team_count} doi, nhan {len(selected_club_ids)}')

    clubs = Club.query.filter(Club.id.in_(selected_club_ids)).all()
    if len(clubs) != team_count:
        raise ValueError('Mot so club_id khong ton tai')

    club_map = {c.id: c for c in clubs}

    tour = Tournament(type=tour_type, name=name, status='setup')
    db.session.add(tour)
    db.session.flush()

    for seed, cid in enumerate(selected_club_ids, 1):
        club = club_map[cid]
        r_seed = regional_seeds[seed - 1] if regional_seeds and seed - 1 < len(regional_seeds) else None
        p = TournamentParticipant(
            tournament_id=tour.id, club_id=cid, seed=seed,
            regional_seed=r_seed,
            region=club.region.slug if club.region else None,
        )
        db.session.add(p)

    db.session.flush()
    return tour


def generate_bracket(tournament):
    """Generate initial matches via format modules."""
    if tournament.type == 'champion':
        _generate_groups(tournament)
        tournament.status = 'groups'
    else:
        _generate_swiss_r1(tournament)
        tournament.status = 'swiss'
    db.session.flush()


def _generate_swiss_r1(tournament):
    """Delegate Swiss R1 to format module."""
    from services.bracket_service import generate_swiss_matches
    pairs = generate_swiss_matches(tournament, 1)
    for i, (a_id, b_id) in enumerate(pairs):
        m = Match(
            tournament_id=tournament.id, round_type='swiss',
            round_name='swiss_round1', match_order=i + 1,
            team_a_id=a_id, team_b_id=b_id,
        )
        db.session.add(m)
    db.session.flush()


def progress_tournament(tournament):
    """Advance tournament to next round/stage."""
    cfg = Config.TOURNAMENT_TYPES[tournament.type]

    if tournament.status in ('setup',):
        generate_bracket(tournament)
        return {'action': 'bracket_generated', 'status': tournament.status}

    if tournament.status == 'swiss':
        generated = _generate_swiss_next_round(tournament)
        if generated:
            return {'action': 'swiss_next'}
        return {'action': 'swiss_done', 'status': 'playoffs'}

    if tournament.status == 'groups':
        _resolve_group_placeholder_matches(tournament)
        return {'action': 'groups_done', 'status': tournament.status}

    if tournament.status == 'playoffs':
        _resolve_playoff_slots(tournament)
        if _is_bracket_finished(tournament):
            tournament.status = 'finished'
            return {'action': 'done', 'status': 'finished'}
        return {'action': 'playoffs_progress'}

    return {'action': 'nothing'}


# ────────────────────────────────────────────────
# Swiss: round progression via format module
# ────────────────────────────────────────────────

def _generate_swiss_next_round(tournament):
    """Generate next Swiss round. Returns True if matches added."""
    cfg = Config.TOURNAMENT_TYPES[tournament.type]

    # Check which teams are still active
    records = _get_swiss_records(tournament)
    active = [cid for cid, r in records.items()
              if r['wins'] < cfg.get('swiss_win_target', 2)
              and r['losses'] < cfg.get('swiss_loss_target', 2)]

    if not active:
        _finalize_swiss(tournament, records)
        return False

    current_round = _current_swiss_round(tournament) + 1

    from services.bracket_service import generate_swiss_matches
    pairs = generate_swiss_matches(tournament, current_round)

    if not pairs:
        _finalize_swiss(tournament, records)
        return False

    next_order = Match.query.filter_by(tournament_id=tournament.id).count()
    for i, (a_id, b_id) in enumerate(pairs):
        next_order += 1
        m = Match(
            tournament_id=tournament.id, round_type='swiss',
            round_name=f'swiss_round{current_round}', match_order=next_order,
            team_a_id=a_id, team_b_id=b_id,
        )
        db.session.add(m)

    db.session.flush()
    return True


def _current_swiss_round(tournament):
    swiss_matches = Match.query.filter_by(tournament_id=tournament.id, round_type='swiss').all()
    rounds = set()
    for m in swiss_matches:
        rounds.add(m.round_name)
    return len(rounds)


def _get_swiss_records(tournament):
    records = {}
    for p in tournament.participants:
        records[p.club_id] = {'wins': 0, 'losses': 0, 'participant': p}

    swiss_matches = Match.query.filter_by(tournament_id=tournament.id, round_type='swiss').all()
    for m in swiss_matches:
        if m.winner_id is None:
            continue
        records[m.team_a_id]['wins'] += int(m.winner_id == m.team_a_id)
        records[m.team_a_id]['losses'] += int(m.winner_id != m.team_a_id)
        records[m.team_b_id]['wins'] += int(m.winner_id == m.team_b_id)
        records[m.team_b_id]['losses'] += int(m.winner_id != m.team_b_id)

    return records


def _finalize_swiss(tournament, records):
    cfg = Config.TOURNAMENT_TYPES[tournament.type]
    advance_count = cfg['advance_count']

    ranked = []
    for cid, rec in records.items():
        p = rec['participant']
        w, l = rec['wins'], rec['losses']
        ranked.append((w, -l, p.club.current_rating, cid, p))

    ranked.sort(key=lambda x: (-x[0], -x[1], -x[2]))

    advancing = []
    for i, (w, nl, rating, cid, p) in enumerate(ranked):
        if i < advance_count:
            p.seed = i + 1
            advancing.append(p)
        else:
            ev = 9 if tournament.type == 'major' else 13
            p.final_rank = ev + (i - advance_count)

    if tournament.type == 'master':
        directs = [p for p in tournament.participants if p.regional_seed == 1]
        for dp in directs:
            advancing.append(dp)
        for sp in advancing:
            if sp.regional_seed and sp.regional_seed >= 2:
                sp.seed = 5 + [i for i, x in enumerate(advancing) if x.regional_seed and x.regional_seed >= 2].index(sp)

    _generate_playoffs(tournament, advancing)
    tournament.status = 'playoffs'
    db.session.flush()


# ────────────────────────────────────────────────
# Playoffs
# ────────────────────────────────────────────────

def _generate_playoffs(tournament, advancing):
    """Generate playoff bracket using format module templates."""
    from services.bracket_service import generate_playoff_matches

    templates = generate_playoff_matches(tournament, advancing)
    if not templates:
        return

    # Count existing playoff matches for order offset
    existing_count = Match.query.filter_by(tournament_id=tournament.id).count()
    next_order = max(100, existing_count + 1)

    for i, tmpl in enumerate(templates):
        rn = tmpl.get('round_name', f'playoff_{i}')
        rt = tmpl.get('round_type', 'upper')

        # Resolve team IDs from template sources
        a_id = None
        b_id = None
        sources = tmpl.get('sources', {}).get('team_a', {})
        sourceb = tmpl.get('sources', {}).get('team_b', {})

        if sources.get('type') == 'seed':
            seed_val = sources['value']
            p = next((p for p in advancing if p.seed == seed_val), None)
            a_id = p.club_id if p else None
        if sourceb.get('type') == 'seed':
            seed_val = sourceb['value']
            p = next((p for p in advancing if p.seed == seed_val), None)
            b_id = p.club_id if p else None

        # For high_team/low_team (champion/master draw)
        if 'high_team' in tmpl:
            ht = tmpl['high_team']
            lt = tmpl['low_team']
            a_id = ht.get('id')
            b_id = lt.get('id')

        m = Match(
            tournament_id=tournament.id, round_type=rt,
            round_name=rn, match_order=next_order + i,
            team_a_id=a_id, team_b_id=b_id,
        )
        db.session.add(m)

    db.session.flush()


def _resolve_playoff_slots(tournament):
    """Resolve TBD slots using format module."""
    from services.bracket_service import resolve_playoff_slot, generate_playoff_matches

    pending = Match.query.filter_by(
        tournament_id=tournament.id, status='pending',
    ).order_by(Match.match_order).all()

    # Get format templates for slot resolution
    advancing = [p for p in tournament.participants if p.final_rank is None]
    templates = generate_playoff_matches(tournament, advancing)

    for m in pending:
        if m.round_type in ('swiss', 'group'):
            continue
        if m.team_a_id and m.team_b_id:
            continue

        # Find matching template
        tmpl = next((t for t in templates if t.get('round_name') == m.round_name), None)
        if tmpl is None:
            continue

        a_id, b_id = resolve_playoff_slot(tmpl, tournament)
        if a_id:
            m.team_a_id = a_id
        if b_id:
            m.team_b_id = b_id

    db.session.flush()


def _is_bracket_finished(tournament):
    gf = Match.query.filter_by(tournament_id=tournament.id, round_type='grand').first()
    if gf and gf.status == 'completed':
        _finalize_tournament(tournament)
        return True
    return False


def _finalize_tournament(tournament):
    gf = Match.query.filter_by(tournament_id=tournament.id, round_type='grand').first()
    if not gf or gf.status != 'completed':
        return

    rank_map = {gf.winner_id: 1, gf.loser_id: 2}

    for rn in ['lower_final', 'lower_semifinal', 'lower_quarterfinal_1', 'lower_quarterfinal_2',
               'lower_round1_1', 'lower_round1_2', 'lower_round1']:
        m = Match.query.filter_by(tournament_id=tournament.id, round_name=rn, status='completed').first()
        if m and m.loser_id:
            lf = Match.query.filter_by(tournament_id=tournament.id, round_name='lower_final', status='completed').first()
            if rn == 'lower_final' and m.loser_id:
                rank_map.setdefault(m.loser_id, 3)
            elif rn == 'lower_semifinal' and m.loser_id:
                rank_map.setdefault(m.loser_id, 4)
            elif 'quarterfinal' in rn and m.loser_id:
                rank_map.setdefault(m.loser_id, 5)
            elif 'round1' in rn and m.loser_id:
                rank_map.setdefault(m.loser_id, 7)

    for p in tournament.participants:
        if p.final_rank is None and p.club_id in rank_map:
            p.final_rank = rank_map[p.club_id]

    db.session.flush()


def simulate_all_pending(tournament):
    """Simulate all pending matches, looping through rounds."""
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


# ────────────────────────────────────────────────
# Group Stage (Champion) - kept here for now
# ────────────────────────────────────────────────

def _generate_groups(tournament):
    from engine.format.champion import generate_gsl_groups

    participants = tournament.participants
    from services.bracket_service import _team_to_dict
    team_dicts = [_team_to_dict(p) for p in participants]

    groups = generate_gsl_groups(team_dicts)

    match_order = 1
    for grp_label, team_list in groups.items():
        # Assign group_label to participants
        for tdict in team_list:
            p = next((p for p in participants if p.club_id == tdict['id']), None)
            if p:
                p.group_label = grp_label

        random.shuffle(team_list)
        t1, t2, t3, t4 = team_list[:4]

        _add_match(tournament, 'group', f'group{grp_label}_opening1', match_order,
                   t1['id'], t2['id'])
        match_order += 1
        _add_match(tournament, 'group', f'group{grp_label}_opening2', match_order,
                   t3['id'], t4['id'])
        match_order += 1

    db.session.flush()


def _add_match(tournament, round_type, round_name, order, a_id, b_id):
    m = Match(
        tournament_id=tournament.id, round_type=round_type,
        round_name=round_name, match_order=order,
        team_a_id=a_id, team_b_id=b_id,
    )
    db.session.add(m)
    return m


def _resolve_group_placeholder_matches(tournament):
    if tournament.status != 'groups':
        return

    existing = Match.query.filter_by(tournament_id=tournament.id, round_type='group').all()
    existing_names = {m.round_name for m in existing}

    for grp_num in range(1, 5):
        label = chr(64 + grp_num)  # A, B, C, D
        prefix = f'group{label}'
        op1 = Match.query.filter_by(tournament_id=tournament.id,
                                    round_name=f'{prefix}_opening1', status='completed').first()
        op2 = Match.query.filter_by(tournament_id=tournament.id,
                                    round_name=f'{prefix}_opening2', status='completed').first()
        if not op1 or not op2:
            continue

        w1, l1 = op1.winner_id, op1.loser_id
        w2, l2 = op2.winner_id, op2.loser_id

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
                           wm.loser_id, em.winner_id)
                existing_names.add(dm_name)

    _check_all_groups_done(tournament)


def _check_all_groups_done(tournament):
    dm_count = Match.query.filter(
        Match.tournament_id == tournament.id,
        Match.round_type == 'group',
        Match.round_name.like('group%_decider_match'),
        Match.status == 'completed',
    ).count()
    if dm_count >= 4:
        _finalize_groups(tournament)


def _finalize_groups(tournament):
    tournament.status = 'playoffs'
    advancing = []

    for grp_num in range(1, 5):
        label = chr(64 + grp_num)
        prefix = f'group{label}'
        wm = Match.query.filter_by(tournament_id=tournament.id,
                                   round_name=f'{prefix}_winners_match', status='completed').first()
        dm = Match.query.filter_by(tournament_id=tournament.id,
                                   round_name=f'{prefix}_decider_match', status='completed').first()

        if wm and wm.winner_id:
            p = TournamentParticipant.query.filter_by(
                tournament_id=tournament.id, club_id=wm.winner_id).first()
            if p:
                p.seed = grp_num
                p.group_label = label
                advancing.append(p)
        if dm and dm.winner_id:
            p = TournamentParticipant.query.filter_by(
                tournament_id=tournament.id, club_id=dm.winner_id).first()
            if p:
                p.seed = grp_num + 4
                p.group_label = label
                advancing.append(p)

    for p in tournament.participants:
        if p not in advancing and p.final_rank is None:
            p.final_rank = 13

    advancing.sort(key=lambda p: p.seed)
    _generate_playoffs(tournament, advancing)
    db.session.flush()
