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
    if tournament.type == 'champion':
        _generate_groups(tournament)
        tournament.status = 'groups'
    else:
        _generate_swiss_r1(tournament)
        tournament.status = 'swiss'
    db.session.flush()


def _generate_swiss_r1(tournament):
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
        return {'action': 'groups_done', 'status': 'playoffs'}

    if tournament.status == 'playoffs':
        _resolve_playoff_slots(tournament)
        if _is_bracket_finished(tournament):
            tournament.status = 'finished'
            return {'action': 'done', 'status': 'finished'}
        return {'action': 'playoffs_progress'}

    return {'action': 'nothing'}


# ────────────────────────────────────────────────
# Swiss round progression (via format module)
# ────────────────────────────────────────────────

def _generate_swiss_next_round(tournament):
    """Generate next Swiss round. Returns True if matches added."""
    cfg = Config.TOURNAMENT_TYPES[tournament.type]

    # Use format module to compute records + active teams
    team_dicts = _to_team_dicts(tournament)
    completed = _to_match_dicts(tournament, 'swiss')
    standings = _compute_swiss_standings(tournament, team_dicts, completed)

    active = [s['team'] for s in standings
               if s['wins'] < cfg.get('swiss_win_target', 2)
               and s['losses'] < cfg.get('swiss_loss_target', 2)]

    if not active:
        _finalize_swiss(tournament, standings)
        return False

    current_round = _current_swiss_round(tournament) + 1

    from services.bracket_service import generate_swiss_matches
    pairs = generate_swiss_matches(tournament, current_round)

    if not pairs:
        _finalize_swiss(tournament, standings)
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
    return len({m.round_name for m in swiss_matches})


def _to_team_dicts(tournament):
    """Convert tournament participants to format-compatible dicts."""
    from services.bracket_service import _team_to_dict
    participants = TournamentParticipant.query.filter_by(
        tournament_id=tournament.id,
    ).order_by(TournamentParticipant.seed).all()
    return [_team_to_dict(p) for p in participants]


def _to_match_dicts(tournament, round_type):
    """Convert matches to format-compatible dicts."""
    from services.bracket_service import _match_to_dict
    # Query directly to avoid relationship caching
    matches = Match.query.filter_by(
        tournament_id=tournament.id, round_type=round_type,
    ).all()
    return [_match_to_dict(m) for m in matches if m.status == 'completed']


def _compute_swiss_standings(tournament, team_dicts, completed):
    """Use format module to compute Swiss standings."""
    from engine.format.major import get_swiss_standings as _major_std
    from engine.format.master import get_swiss_standings as _master_std

    ttype = tournament.type
    if ttype == 'master':
        swiss_team_dicts = [t for t in team_dicts if t.get('regional_seed', 0) >= 2]
        return _master_std(swiss_team_dicts, completed)
    else:
        return _major_std(team_dicts, completed)


def _finalize_swiss(tournament, standings):
    """Rank teams and assign seeds for playoffs.

    Major: top 4 Swiss qualifiers get seeds 1-4.
    Master: regional_seed=1 (direct) teams get seeds 1-4, top 4 Swiss qualifiers get seeds 5-8.
    """
    cfg = Config.TOURNAMENT_TYPES[tournament.type]
    advance_count = cfg['advance_count']

    all_participants = TournamentParticipant.query.filter_by(
        tournament_id=tournament.id,
    ).all()
    p_by_id = {pp.club_id: pp for pp in all_participants}

    # Identify advancing set (top advance_count from standings, plus directs for Master)
    if tournament.type == 'master':
        directs_club_ids = {pp.club_id for pp in all_participants if pp.regional_seed == 1}
    else:
        directs_club_ids = set()

    advancing_club_ids = set(directs_club_ids)
    for s in standings[:advance_count]:
        advancing_club_ids.add(s['team']['id'])

    # Reset seeds for non-advancing, mark eliminated
    for i, s in enumerate(standings):
        p = p_by_id.get(s['team']['id'])
        if p is None:
            continue
        if s['team']['id'] in advancing_club_ids:
            continue  # will be set below
        # Eliminated: clear seed, set final_rank
        p.seed = None
        if p.final_rank is None:
            ev = 9 if tournament.type == 'major' else 13
            p.final_rank = ev + (i - advance_count)

    # Mark eliminated non-Swiss participants (e.g., direct qualifiers in Master
    # never go through Swiss but should not be eliminated)
    for p in all_participants:
        if p.club_id not in advancing_club_ids and p.club_id not in {s['team']['id'] for s in standings}:
            p.seed = None

    if tournament.type == 'master':
        # Direct qualifiers (regional_seed=1) = seeds 1-4
        directs = [pp for pp in all_participants if pp.regional_seed == 1]
        directs.sort(key=lambda p: p.regional_seed)
        for i, dp in enumerate(directs):
            dp.seed = i + 1
        # Swiss qualifiers = seeds 5-8
        for i, s in enumerate(standings[:advance_count]):
            p = p_by_id.get(s['team']['id'])
            if p:
                p.seed = 5 + i
        advancing = directs + [p_by_id.get(s['team']['id']) for s in standings[:advance_count]]
    else:
        # Major/Champion: top advance_count from Swiss get seeds 1-N
        for i, s in enumerate(standings[:advance_count]):
            p = p_by_id.get(s['team']['id'])
            if p:
                p.seed = i + 1
        advancing = [p_by_id.get(s['team']['id']) for s in standings[:advance_count]]

    advancing = [p for p in advancing if p is not None]
    if not advancing:
        return

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

    existing_count = Match.query.filter_by(tournament_id=tournament.id).count()
    next_order = max(100, existing_count + 1)

    for i, tmpl in enumerate(templates):
        rn = tmpl.get('round_name', f'playoff_{i}')
        rt = tmpl.get('round_type', 'upper')
        a_id, b_id = _resolve_template_seeds(tmpl, advancing)
        m = Match(
            tournament_id=tournament.id, round_type=rt,
            round_name=rn, match_order=next_order + i,
            team_a_id=a_id, team_b_id=b_id,
        )
        db.session.add(m)

    db.session.flush()


def _resolve_template_seeds(tmpl, advancing):
    """Resolve team_a/b IDs from a format template."""
    a_id, b_id = None, None
    sources = tmpl.get('sources', {})

    src_a = sources.get('team_a', {})
    src_b = sources.get('team_b', {})

    if src_a.get('type') == 'seed':
        p = next((p for p in advancing if p.seed == src_a['value']), None)
        a_id = p.club_id if p else None
    if src_b.get('type') == 'seed':
        p = next((p for p in advancing if p.seed == src_b['value']), None)
        b_id = p.club_id if p else None

    if 'high_team' in tmpl:
        a_id = tmpl['high_team'].get('id')
        b_id = tmpl['low_team'].get('id')

    return a_id, b_id


def _resolve_playoff_slots(tournament):
    """Resolve TBD slots in playoff bracket using format module."""
    from services.bracket_service import (
        resolve_playoff_slot, generate_playoff_matches,
    )

    # Advancing teams: have seed AND no final_rank (still in contention)
    advancing = [p for p in tournament.participants
                 if p.seed is not None and p.seed > 0 and p.final_rank is None]
    templates = generate_playoff_matches(tournament, advancing)

    pending = Match.query.filter_by(
        tournament_id=tournament.id, status='pending',
    ).order_by(Match.match_order).all()

    for m in pending:
        if m.round_type in ('swiss', 'group'):
            continue
        if m.team_a_id and m.team_b_id:
            continue
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
    """Assign final rankings to all playoff participants."""
    from services.bracket_service import _match_label
    completed = {m.round_name: m for m in tournament.matches
                 if m.status == 'completed' and m.round_type in ('upper', 'lower', 'grand')}

    if not completed.get('grand_final'):
        return
    if completed['grand_final'].winner_id is None:
        return

    rank_map = {}

    # GF: #1 winner, #2 loser
    gf = completed['grand_final']
    rank_map[gf.winner_id] = 1
    rank_map[gf.loser_id] = 2

    # Lower Final: #3 loser
    if completed.get('lower_final') and completed['lower_final'].loser_id:
        rank_map[completed['lower_final'].loser_id] = 3

    # Lower Semifinal: #4 loser
    if completed.get('lower_semifinal') and completed['lower_semifinal'].loser_id:
        rank_map[completed['lower_semifinal'].loser_id] = 4

    # Lower Quarterfinals: #5, #6 losers
    for lq in ('lower_quarterfinal_1', 'lower_quarterfinal_2'):
        m = completed.get(lq)
        if m and m.loser_id:
            current = rank_map.get(m.loser_id, 5)
            rank_map[m.loser_id] = current

    # Lower Round 1: #7, #8 losers
    for lr in ('lower_round1_1', 'lower_round1_2', 'lower_round1'):
        m = completed.get(lr)
        if m and m.loser_id:
            current = rank_map.get(m.loser_id, 7)
            rank_map[m.loser_id] = current

    for p in tournament.participants:
        if p.final_rank is None and p.club_id in rank_map:
            p.final_rank = rank_map[p.club_id]

    db.session.flush()


def simulate_all_pending(tournament):
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
# Group Stage (Champion) - via format module
# ────────────────────────────────────────────────

def _generate_groups(tournament):
    from engine.format.champion import generate_gsl_groups
    from services.bracket_service import _team_to_dict

    team_dicts = [_team_to_dict(p) for p in tournament.participants]
    groups = generate_gsl_groups(team_dicts)

    match_order = 1
    for grp_label, team_list in groups.items():
        # Persist group_label to participants
        for tdict in team_list:
            p = next((p for p in tournament.participants if p.club_id == tdict['id']), None)
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
    """After opening matches, generate Winners/Elimination/Decider for each group.

    Uses format/champion.get_gsl_matches() to know the structure.
    """
    if tournament.status != 'groups':
        return

    existing = Match.query.filter_by(tournament_id=tournament.id, round_type='group').all()
    existing_names = {m.round_name for m in existing}

    for grp_num in range(1, 5):
        label = chr(64 + grp_num)
        prefix = f'group{label}'

        op1 = Match.query.filter_by(tournament_id=tournament.id,
                                    round_name=f'{prefix}_opening1', status='completed').first()
        op2 = Match.query.filter_by(tournament_id=tournament.id,
                                    round_name=f'{prefix}_opening2', status='completed').first()
        if not op1 or not op2:
            continue

        wm_name = f'{prefix}_winners_match'
        em_name = f'{prefix}_elimination_match'

        if wm_name not in existing_names:
            _add_match(tournament, 'group', wm_name, 1000 + grp_num * 100 + 10,
                       op1.winner_id, op2.winner_id)
            existing_names.add(wm_name)

        if em_name not in existing_names:
            _add_match(tournament, 'group', em_name, 1000 + grp_num * 100 + 20,
                       op1.loser_id, op2.loser_id)
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
