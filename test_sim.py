"""Test: render Swiss UI for Major and Master."""
import sys
sys.path.insert(0, '.')
from app import create_app
from models import db, Club, ClubRating, MatchMap, Match, TournamentParticipant, Tournament
from engine.tournament import create_tournament, generate_bracket, simulate_all_pending
from services.bracket_service import get_swiss_data

app = create_app()
with app.app_context():
    ClubRating.query.delete(); MatchMap.query.delete(); Match.query.delete()
    TournamentParticipant.query.delete(); Tournament.query.delete()
    db.session.commit()

    pools = {}
    for c in Club.query.all():
        pools.setdefault(c.region.slug, []).append(c)

    for ttype, slots in [('major', 2), ('master', 3)]:
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

        # Test get_swiss_data
        swiss_data = get_swiss_data(tour)
        print(f'\n=== {ttype.upper()} ===')
        print(f'  Standings: {len(swiss_data["standings"])} teams')
        for s in swiss_data['standings'][:3]:
            print(f'    #{s["club"].short_code:5s} {s["wins"]}-{s["losses"]} results={s["results"]} adv={s["advanced"]}')
        print(f'  Rounds: {list(swiss_data["rounds"].keys())}')
        for rn, rd in swiss_data['rounds'].items():
            print(f'    {rn} ({rd["label"]}): {len(rd["matches"])} matches')
        print(f'  Direct qualifiers: {len(swiss_data["direct_qualifiers"])}')
        for dq in swiss_data['direct_qualifiers']:
            print(f'    S{dq["regional_seed"]} {dq["club"].short_code}')

        # Test page render
        with app.test_client() as client:
            r = client.get(f'/tournament/{tour.id}')
            print(f'  Page: {r.status_code}')
            if r.status_code == 200:
                html = r.data.decode('utf-8', errors='replace')
                checks = [
                    ('swiss-standings-table', 'standings table'),
                    ('swiss-round-block', 'round blocks'),
                    ('swiss-round-header', 'round headers'),
                    ('Vòng 1', 'Round 1 label'),
                    ('Vòng 2', 'Round 2 label'),
                    ('Vòng 3', 'Round 3 label'),
                ]
                if ttype == 'master':
                    checks.append(('direct-qualifiers-card', 'direct qualifiers card'))
                    checks.append(('Auto-Advanced', 'auto-advanced label'))
                    checks.append(('dq-team', 'dq team item'))
                for needle, label in checks:
                    found = needle in html.encode('latin-1', errors='replace').decode('latin-1')
                    print(f'    {label}: {found}')
