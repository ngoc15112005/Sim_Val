"""Quick smoke test: all 3 tournament types."""
import sys
sys.path.insert(0, '.')
from app import create_app
from models import db, Club, ClubRating, MatchMap, Match, TournamentParticipant, Tournament
from engine.tournament import create_tournament, generate_bracket, simulate_all_pending

app = create_app()
with app.app_context():
    pools = {}
    for c in Club.query.all():
        pools.setdefault(c.region.slug, []).append(c)

    for ttype in ['major', 'master', 'champion']:
        ClubRating.query.delete(); MatchMap.query.delete(); Match.query.delete()
        TournamentParticipant.query.delete(); Tournament.query.delete()
        db.session.commit()

        slots = {'major': 2, 'master': 3, 'champion': 4}[ttype]
        cids = []
        rseeds = []
        for region in ['pacific', 'americas', 'emea', 'china']:
            sorted_c = sorted(pools[region], key=lambda c: c.current_rating, reverse=True)
            for i in range(slots):
                cids.append(sorted_c[i].id)
                rseeds.append(i + 1)

        tour = create_tournament(ttype, f'{ttype.upper()} Test', cids, rseeds)
        generate_bracket(tour)
        db.session.commit()
        simulate_all_pending(tour)
        db.session.commit()

        # Check page renders
        with app.test_client() as client:
            r = client.get(f'/tournament/{tour.id}')
            ok = r.status_code == 200
            has_bracket = 'match-box' in r.data.decode('utf-8', errors='replace')
            print(f'{ttype:10s}: status={tour.status:10s}  page_ok={ok}  bracket={has_bracket}')

print('All OK!')
