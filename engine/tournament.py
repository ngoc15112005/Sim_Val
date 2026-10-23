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
        raise ValueError(f'{tour_type} cần đúng {team_count} đội, nhận {len(selected_club_ids)}')

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
        # Round not yet fully completed — wait for more results
        if not _is_current_round_complete(tournament):
            return {'action': 'waiting'}
        # Round complete but no new round was generated (finalize)
        return {'action': 'swiss_done', 'status': 'playoffs'}

    if tournament.status == 'groups':
        _resolve_group_placeholder_matches(tournament)
        # Only transition to playoffs when all group matches (including deciders) are done
        if not _is_groups_complete(tournament):
            return {'action': 'waiting'}
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

    current_round = _current_swiss_round(tournament)
    if current_round == 0:
        return False

    # Check if the current round is fully completed.
    # If not, do NOT advance — wait for more manual/simulated results.
    current_round_name = f'swiss_round{current_round}'
    current_round_matches = Match.query.filter_by(
        tournament_id=tournament.id,
        round_type='swiss',
        round_name=current_round_name,
    ).all()
    if not current_round_matches:
        return False
    if any(m.status != 'completed' for m in current_round_matches):
        # Current round not yet complete — do not advance
        return False

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

    next_round = current_round + 1

    from services.bracket_service import generate_swiss_matches
    pairs = generate_swiss_matches(tournament, next_round)

    if not pairs:
        _finalize_swiss(tournament, standings)
        return False

    next_order = Match.query.filter_by(tournament_id=tournament.id).count()
    for i, (a_id, b_id) in enumerate(pairs):
        next_order += 1
        m = Match(
            tournament_id=tournament.id, round_type='swiss',
            round_name=f'swiss_round{next_round}', match_order=next_order,
            team_a_id=a_id, team_b_id=b_id,
        )
        db.session.add(m)

    db.session.flush()
    return True


def _current_swiss_round(tournament):
    swiss_matches = Match.query.filter_by(tournament_id=tournament.id, round_type='swiss').all()
    return len({m.round_name for m in swiss_matches})


def _is_groups_complete(tournament):
    """Check if all group-stage matches (opening, winners, elim, decider) are completed."""
    pending = Match.query.filter_by(
        tournament_id=tournament.id,
        round_type='group',
        status='pending',
    ).count()
    return pending == 0


def _is_current_round_complete(tournament):
    """Check if all matches in the current (latest) Swiss round are completed."""
    current_round = _current_swiss_round(tournament)
    if current_round == 0:
        return True
    current_round_name = f'swiss_round{current_round}'
    pending = Match.query.filter_by(
        tournament_id=tournament.id,
        round_type='swiss',
        round_name=current_round_name,
        status='pending',
    ).count()
    return pending == 0


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
            ev = 5 if tournament.type == 'major' else 9
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
    matches = Match.query.filter_by(tournament_id=tournament.id).all()
    completed = {m.round_name: m for m in matches
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

    if tournament.type == 'major':
        # In Major (4-team playoff): lower_round1 loser is #4
        if completed.get('lower_round1') and completed['lower_round1'].loser_id:
            rank_map[completed['lower_round1'].loser_id] = 4
    else:
        # In Master & Champion (8-team playoff):
        # Lower Semifinal: #4 loser
        if completed.get('lower_semifinal') and completed['lower_semifinal'].loser_id:
            rank_map[completed['lower_semifinal'].loser_id] = 4

        # Lower Quarterfinals: #5, #6 losers
        lq_losers = []
        for lq in ('lower_quarterfinal_1', 'lower_quarterfinal_2'):
            m = completed.get(lq)
            if m and m.loser_id and m.loser_id not in rank_map:
                lq_losers.append(m.loser_id)
        for idx, cid in enumerate(lq_losers):
            rank_map[cid] = 5 + idx

        # Lower Round 1: #7, #8 losers
        lr_losers = []
        for lr in ('lower_round1_1', 'lower_round1_2'):
            m = completed.get(lr)
            if m and m.loser_id and m.loser_id not in rank_map:
                lr_losers.append(m.loser_id)
        for idx, cid in enumerate(lr_losers):
            rank_map[cid] = 7 + idx

    participants = TournamentParticipant.query.filter_by(tournament_id=tournament.id).all()
    for p in participants:
        if p.club_id in rank_map:
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

def simulate_round(tournament, round_name=None, group_label=None, stage=None, match_ids=None):
    """Selectively simulate matches without touching completed or manual matches."""
    from engine.match import simulate_match
    from engine.rating import update_ratings
    from models import ClubRating

    simulated_total = 0

    if group_label and not stage:
        # Simulate entire group iteratively
        prefix = f'group{group_label.upper()}_'
        for _ in range(10):
            pending = Match.query.filter(
                Match.tournament_id == tournament.id,
                Match.round_type == 'group',
                Match.round_name.startswith(prefix),
                Match.status == 'pending',
                Match.team_a_id.isnot(None),
                Match.team_b_id.isnot(None),
            ).order_by(Match.match_order).all()

            if not pending:
                break

            for m in pending:
                simulate_match(m)
                simulated_total += 1

            db.session.flush()
            _resolve_group_placeholder_matches(tournament)
            db.session.flush()

        progress_tournament(tournament)
        db.session.flush()

    elif group_label and stage:
        # Simulate specific stage inside a group
        prefix = f'group{group_label.upper()}_'
        target_names = []
        if stage == 'opening':
            target_names = [f'{prefix}opening1', f'{prefix}opening2']
        elif stage == 'winners':
            target_names = [f'{prefix}winners_match']
        elif stage == 'elimination':
            target_names = [f'{prefix}elimination_match']
        elif stage == 'decider':
            target_names = [f'{prefix}decider_match']
        else:
            target_names = [f'{prefix}{stage}']

        pending = Match.query.filter(
            Match.tournament_id == tournament.id,
            Match.round_name.in_(target_names),
            Match.status == 'pending',
            Match.team_a_id.isnot(None),
            Match.team_b_id.isnot(None),
        ).order_by(Match.match_order).all()

        for m in pending:
            simulate_match(m)
            simulated_total += 1

        db.session.flush()
        _resolve_group_placeholder_matches(tournament)
        progress_tournament(tournament)
        db.session.flush()

    elif round_name:
        # Playoff columns or Swiss rounds
        target_names = []
        if round_name == 'upper_quarterfinals':
            target_names = [f'upper_quarterfinal_{i}' for i in range(1, 5)]
        elif round_name == 'upper_semifinals':
            target_names = ['upper_semifinal_1', 'upper_semifinal_2']
        elif round_name == 'lower_round1':
            target_names = ['lower_round1_1', 'lower_round1_2', 'lower_round1']
        elif round_name == 'lower_quarterfinals':
            target_names = ['lower_quarterfinal_1', 'lower_quarterfinal_2']
        elif round_name == 'lower_semifinals':
            target_names = ['lower_semifinal', 'lower_semifinals']
        elif round_name == 'upper_final':
            target_names = ['upper_final']
        elif round_name == 'lower_final':
            target_names = ['lower_final']
        elif round_name == 'grand_final':
            target_names = ['grand_final']
        else:
            target_names = [round_name]

        pending = Match.query.filter(
            Match.tournament_id == tournament.id,
            Match.round_name.in_(target_names),
            Match.status == 'pending',
            Match.team_a_id.isnot(None),
            Match.team_b_id.isnot(None),
        ).order_by(Match.match_order).all()

        for m in pending:
            simulate_match(m)
            simulated_total += 1

        db.session.flush()
        progress_tournament(tournament)
        db.session.flush()

    elif match_ids:
        pending = Match.query.filter(
            Match.tournament_id == tournament.id,
            Match.id.in_(match_ids),
            Match.status == 'pending',
            Match.team_a_id.isnot(None),
            Match.team_b_id.isnot(None),
        ).order_by(Match.match_order).all()

        for m in pending:
            simulate_match(m)
            simulated_total += 1

        db.session.flush()
        progress_tournament(tournament)
        db.session.flush()

    if tournament.status == 'finished':
        if not ClubRating.query.filter_by(tournament_id=tournament.id).first():
            update_ratings(tournament)
            db.session.flush()

    return {'simulated_count': simulated_total, 'status': tournament.status}


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

        # Seed 1 vs Seed 4, Seed 2 vs Seed 3
        t_s1 = next((t for t in team_list if t.get('regional_seed') == 1), team_list[0])
        t_s2 = next((t for t in team_list if t.get('regional_seed') == 2), team_list[1] if len(team_list) > 1 else team_list[0])
        t_s3 = next((t for t in team_list if t.get('regional_seed') == 3), team_list[2] if len(team_list) > 2 else team_list[0])
        t_s4 = next((t for t in team_list if t.get('regional_seed') == 4), team_list[3] if len(team_list) > 3 else team_list[0])

        _add_match(tournament, 'group', f'group{grp_label}_opening1', match_order,
                   t_s1['id'], t_s4['id'])
        match_order += 1
        _add_match(tournament, 'group', f'group{grp_label}_opening2', match_order,
                   t_s2['id'], t_s3['id'])
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

    # Decider match losers (finished 1-2 in groups): Ranks 9, 10, 11, 12
    # Elimination match losers (finished 0-2 in groups): Ranks 13, 14, 15, 16
    decider_losers = []
    elim_losers = []
    for grp_num in range(1, 5):
        label = chr(64 + grp_num)
        prefix = f'group{label}'
        dm = Match.query.filter_by(tournament_id=tournament.id,
                                   round_name=f'{prefix}_decider_match', status='completed').first()
        em = Match.query.filter_by(tournament_id=tournament.id,
                                   round_name=f'{prefix}_elimination_match', status='completed').first()
        if dm and dm.loser_id:
            decider_losers.append(dm.loser_id)
        if em and em.loser_id:
            elim_losers.append(em.loser_id)

    for idx, cid in enumerate(decider_losers):
        p = TournamentParticipant.query.filter_by(tournament_id=tournament.id, club_id=cid).first()
        if p:
            p.final_rank = 9 + idx
            p.seed = None

    for idx, cid in enumerate(elim_losers):
        p = TournamentParticipant.query.filter_by(tournament_id=tournament.id, club_id=cid).first()
        if p:
            p.final_rank = 13 + idx
            p.seed = None

    for p in tournament.participants:
        if p not in advancing and p.final_rank is None:
            p.final_rank = 16
            p.seed = None

    advancing.sort(key=lambda p: p.seed)
    _generate_playoffs(tournament, advancing)
    db.session.flush()
