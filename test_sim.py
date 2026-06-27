"""Test: create Champion, run Group Stage + Playoffs."""
import sys
sys.path.insert(0, '.')
from app import create_app
from models import db, Club, Tournament, TournamentParticipant, Match, MatchMap, ClubRating
from engine.tournament import create_tournament, generate_bracket
from engine.tournament import simulate_all_pending

app = create_app()
with app.app_context():
    ClubRating.query.delete()
    MatchMap.query.delete()
    Match.query.delete()
    TournamentParticipant.query.delete()
    Tournament.query.delete()
    db.session.commit()

    clubs = Club.query.order_by(Club.current_rating.desc()).limit(16).all()
    club_ids = [c.id for c in clubs]
    print('Champion 16 doi:')
    for i, c in enumerate(clubs):
        print(f'  {c.short_code:5s} ({c.current_rating})')

    tour = create_tournament('champion', 'Champion Test', club_ids)
    generate_bracket(tour)
    db.session.commit()
    print(f'\nGroup Stage 4 bang:')
    group_matches = Match.query.filter_by(tournament_id=tour.id, round_type='group').all()
    for m in group_matches:
        print(f'  {m.round_name}: {m.team_a.short_code} vs {m.team_b.short_code}')

    print('\n=== Simulating all ===')
    simulate_all_pending(tour)
    db.session.commit()

    all_matches = Match.query.filter_by(tournament_id=tour.id).order_by(Match.match_order).all()
    print(f'\n=== All Results ({tour.status}) ===')
    for m in all_matches:
        status = 'DONE' if m.status == 'completed' else 'PEND'
        scores = f'{m.team_a_score}-{m.team_b_score}' if m.team_a_score is not None else '?-?'
        maps_str = ' '.join(f'M{mp.map_number}:{mp.team_a_score}-{mp.team_b_score}' for mp in m.maps)
        winner = m.winner.short_code if m.winner else '?'
        ta = m.team_a.short_code if m.team_a else 'TBD'
        tb = m.team_b.short_code if m.team_b else 'TBD'
        print(f'  [{m.round_type:6s}] {m.round_name:28s} | {ta:5s} {scores:5s} {tb:5s} | {status:5s} | W={winner:5s} | {maps_str}')

    print('\n=== Group Winners & Runners ===')
    for p in sorted(tour.participants, key=lambda p: p.seed):
        grp = p.group_label or '?'
        seed_info = f'Seed{p.seed}' if p.seed else ''
        print(f'  {grp} {seed_info:6s} {p.club.short_code:5s} (rank={p.final_rank})')

    print('\n=== Playoffs Quarterfinal Draw ===')
    qf_matches = Match.query.filter_by(
        tournament_id=tour.id, round_type='upper', round_name='upper_quarterfinal_1',
    ).all()
    for i in range(1, 5):
        m = Match.query.filter_by(
            tournament_id=tour.id,
            round_name=f'upper_quarterfinal_{i}',
        ).first()
        if m:
            ta = m.team_a.short_code if m.team_a else '?'
            tb = m.team_b.short_code if m.team_b else '?'
            ta_grp = '?'
            tb_grp = '?'
            pa = TournamentParticipant.query.filter_by(
                tournament_id=tour.id, club_id=m.team_a_id).first()
            pb = TournamentParticipant.query.filter_by(
                tournament_id=tour.id, club_id=m.team_b_id).first()
            if pa: ta_grp = pa.group_label or '?'
            if pb: tb_grp = pb.group_label or '?'
            print(f'  UQ{i}: [{ta_grp}]{ta} vs [{tb_grp}]{tb}  (same group? {ta_grp == tb_grp})')

    print('\n=== Final Standings ===')
    for p in sorted(tour.participants, key=lambda p: (p.final_rank or 99, p.seed)):
        rank = f'#{p.final_rank}' if p.final_rank else '?'
        grp = f'[{p.group_label or "?"}]'
        print(f'  {rank:4s} {grp} {p.club.short_code:5s} {p.club.name}')
