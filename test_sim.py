"""Test: full tree structure verification."""
import sys
sys.path.insert(0, '.')
from app import create_app
from models import db, Club, ClubRating, MatchMap, Match, TournamentParticipant, Tournament
from engine.tournament import create_tournament, generate_bracket, simulate_all_pending

app = create_app()
with app.app_context():
    ClubRating.query.delete(); MatchMap.query.delete(); Match.query.delete()
    TournamentParticipant.query.delete(); Tournament.query.delete()
    db.session.commit()
    pools = {}
    for c in Club.query.all(): pools.setdefault(c.region.slug, []).append(c)

    for ttype, slots in [('major', 2), ('master', 3), ('champion', 4)]:
        cids, rseeds = [], []
        for region in ['pacific', 'americas', 'emea', 'china']:
            sorted_c = sorted(pools[region], key=lambda c: c.current_rating, reverse=True)
            for i in range(slots):
                cids.append(sorted_c[i].id); rseeds.append(i+1)
        tour = create_tournament(ttype, f'{ttype.upper()}', cids, rseeds)
        generate_bracket(tour); db.session.commit()
        simulate_all_pending(tour); db.session.commit()

        with app.test_client() as client:
            r = client.get(f'/tournament/{tour.id}')
            html = r.data.decode('utf-8', errors='replace')
            assert 'playoff-tree' in html, f'{ttype} missing playoff-tree'
            assert 'upper-bracket' in html, f'{ttype} missing upper-bracket'
            assert 'lower-bracket' in html, f'{ttype} missing lower-bracket'
            assert 'grand-final-column' in html, f'{ttype} missing grand-final-column'
            assert 'bracket-column' in html, f'{ttype} missing bracket-column'

        # Count matches
        from models import Match
        upper_count = Match.query.filter_by(tournament_id=tour.id, round_type='upper').count()
        lower_count = Match.query.filter_by(tournament_id=tour.id, round_type='lower').count()
        grand_count = Match.query.filter_by(tournament_id=tour.id, round_type='grand').count()
        print(f'{ttype:10s}: status={tour.status:10s}  upper={upper_count} lower={lower_count} grand={grand_count}')

    print('All 3 types render with tree layout!')
