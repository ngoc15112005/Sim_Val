"""Test: full lifecycle for all 3 tournament types."""
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
    for c in Club.query.all():
        pools.setdefault(c.region.slug, []).append(c)

    for ttype, slots in [('major', 2), ('master', 3), ('champion', 4)]:
        cids, rseeds = [], []
        for region in ['pacific', 'americas', 'emea', 'china']:
            sorted_c = sorted(pools[region], key=lambda c: c.current_rating, reverse=True)
            for i in range(slots):
                cids.append(sorted_c[i].id)
                rseeds.append(i + 1)
        tour = create_tournament(ttype, f'{ttype.upper()}', cids, rseeds)
        generate_bracket(tour)
        db.session.commit()
        simulate_all_pending(tour)
        db.session.commit()

        with app.test_client() as client:
            r = client.get(f'/tournament/{tour.id}')
            ok = r.status_code == 200
            html = r.data.decode('utf-8', errors='replace')
            has_bracket = 'match-box' in html
            has_gsl = 'gsl-container' in html if ttype == 'champion' else True
            has_vietnamese = 'Tứ kết' in html.encode('latin-1', errors='replace').decode('latin-1') or \
                             'Bán kết' in html.encode('latin-1', errors='replace').decode('latin-1') or \
                             'CK Thắng' in html.encode('latin-1', errors='replace').decode('latin-1')
            print(f'{ttype:10s}: status={tour.status:10s}  page_ok={ok}  bracket={has_bracket}  gsl={has_gsl}  vn={has_vietnamese}')
