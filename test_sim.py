"""Test: create tournaments with regional_seed system."""
import sys
sys.path.insert(0, '.')
from app import create_app
from models import db, Club, Tournament, TournamentParticipant, Match, MatchMap, ClubRating
from engine.tournament import create_tournament, generate_bracket, simulate_all_pending

app = create_app()
with app.app_context():
    ClubRating.query.delete()
    MatchMap.query.delete()
    Match.query.delete()
    TournamentParticipant.query.delete()
    Tournament.query.delete()
    db.session.commit()

    clubs = Club.query.all()
    region_pools = {}
    for c in clubs:
        region_pools.setdefault(c.region.slug, []).append(c)

    # Test Master: 3 per region, Seed1 = auto-qualify
    club_ids = []
    regional_seeds = []
    print('=== Master: 3 per region, Seed1=auto ===')
    for region_slug in ['pacific', 'americas', 'emea', 'china']:
        pool = sorted(region_pools[region_slug], key=lambda c: c.current_rating, reverse=True)
        for i in range(3):
            club_ids.append(pool[i].id)
            regional_seeds.append(i + 1)
            tag = '[AUTO]' if i == 0 else '[SWISS]'
            print(f'  {region_slug} Seed{i+1} {tag}: {pool[i].short_code} ({pool[i].current_rating})')

    tour = create_tournament('master', 'Master Test', club_ids, regional_seeds)
    generate_bracket(tour)
    db.session.commit()

    # Verify auto-qualifiers got correct regional_seed
    print('\nParticipants:')
    for p in tour.participants:
        auto = '[AUTO]' if p.regional_seed == 1 else '[SWISS]'
        print(f'  {auto} Seed{p.seed} region={p.region} reg_seed={p.regional_seed} {p.club.short_code}')

    swiss_matches = Match.query.filter_by(tournament_id=tour.id, round_type='swiss').all()
    print(f'\nSwiss Round 1: {len(swiss_matches)} matches')
    for m in swiss_matches:
        print(f'  {m.team_a.short_code} vs {m.team_b.short_code}')

    simulate_all_pending(tour)
    db.session.commit()

    print(f'\nFinal standings ({tour.status}):')
    for p in sorted(tour.participants, key=lambda p: (p.final_rank or 99, p.seed)):
        print(f'  #{p.final_rank or "?"} reg_seed={p.regional_seed} {p.club.short_code}')
