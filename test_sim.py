"""Test: create Master, run Swiss + Playoffs."""
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

    clubs = Club.query.order_by(Club.current_rating.desc()).limit(12).all()
    club_ids = [c.id for c in clubs]
    print('Teams (top 4 auto-qualify):')
    for i, c in enumerate(clubs):
        tag = ' [AUTO]' if i < 4 else ''
        print(f'  Seed{i+1:2d} {c.short_code:5s} ({c.current_rating}){tag}')

    tour = create_tournament('master', 'Master Test', club_ids)
    generate_bracket(tour)
    db.session.commit()
    print(f'\nTournament: {tour.name} [{tour.status}]')

    swiss_matches = Match.query.filter_by(tournament_id=tour.id, round_type='swiss').all()
    print(f'\n=== Swiss Round 1 ({len(swiss_matches)} matches) ===')
    for m in swiss_matches:
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

    print('\n=== Final Standings ===')
    for p in sorted(tour.participants, key=lambda p: (p.final_rank or 99, p.seed)):
        rank = f'#{p.final_rank}' if p.final_rank else '?'
        direct = ' [AUTO]' if p.seed <= 4 else ''
        print(f'  {rank:4s} Seed{p.seed:2d} {p.club.short_code:5s} {p.club.name}{direct}')
