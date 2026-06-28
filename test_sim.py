"""Test: render Final Standings + new header + check bracket connectors."""
import sys
sys.path.insert(0, '.')
from app import create_app
from models import db, Club, ClubRating, MatchMap, Match, TournamentParticipant, Tournament
from engine.tournament import create_tournament, generate_bracket, simulate_all_pending
from services.bracket_service import get_final_standings

app = create_app()
with app.app_context():
    ClubRating.query.delete(); MatchMap.query.delete(); Match.query.delete()
    TournamentParticipant.query.delete(); Tournament.query.delete()
    db.session.commit()

    pools = {}
    for c in Club.query.all():
        pools.setdefault(c.region.slug, []).append(c)

    # Test Champion (has full ranking #1-16)
    cids, rseeds = [], []
    for region in ['pacific', 'americas', 'emea', 'china']:
        sorted_c = sorted(pools[region], key=lambda c: c.current_rating, reverse=True)
        for i in range(4):
            cids.append(sorted_c[i].id)
            rseeds.append(i + 1)
    tour = create_tournament('champion', 'Test', cids, rseeds)
    generate_bracket(tour)
    db.session.commit()
    simulate_all_pending(tour)
    db.session.commit()

    print(f'Champion status: {tour.status}')

    # Test get_final_standings
    standings = get_final_standings(tour)
    print(f'\nFinal standings ({len(standings)} teams):')
    for s in standings:
        rank_class = 'gold' if s['rank'] == 1 else ('silver' if s['rank'] == 2 else ('bronze' if s['rank'] == 3 else ''))
        print(f'  #{s["rank"]:2d} {s["club"].short_code:5s} {s["wins"]}-{s["losses"]} status={s["status_class"]:10s} {s["status_label"]}')

    # Test page render
    with app.test_client() as client:
        r = client.get(f'/tournament/{tour.id}')
        html = r.data.decode('utf-8', errors='replace')
        checks = [
            ('breadcrumb', 'breadcrumb'),
            ('tour-header-main', 'header 2-row'),
            ('tour-type-badge', 'tour type badge'),
            ('tour-type-champion', 'champion badge style'),
            ('status-badge-large', 'large status badge'),
            ('btn-secondary', 'secondary button'),
            ('btn-primary', 'primary button'),
            ('btn-ghost', 'ghost button'),
            ('info-chip', 'info chip'),
            ('final-standings-card', 'final standings card'),
            ('podium', 'podium'),
            ('champion-card', 'champion card class'),
            ('podium-bar', 'podium bar'),
            ('rank-medal gold', 'gold medal'),
            ('VO DICH', 'champion label'),
            ('full-standings', 'full standings table'),
            ('standings-table', 'standings table'),
        ]
        print(f'\n=== Page render checks ===')
        for needle, label in checks:
            print(f'  {label}: {needle in html}')

    # Test Major
    ClubRating.query.delete(); MatchMap.query.delete(); Match.query.delete()
    TournamentParticipant.query.delete(); Tournament.query.delete()
    db.session.commit()
    cids, rseeds = [], []
    for region in ['pacific', 'americas', 'emea', 'china']:
        sorted_c = sorted(pools[region], key=lambda c: c.current_rating, reverse=True)
        for i in range(2):
            cids.append(sorted_c[i].id)
            rseeds.append(i + 1)
    tour2 = create_tournament('major', 'Major Test', cids, rseeds)
    generate_bracket(tour2); db.session.commit()
    simulate_all_pending(tour2); db.session.commit()

    standings2 = get_final_standings(tour2)
    print(f'\nMajor final standings ({len(standings2)} teams):')
    for s in standings2:
        print(f'  #{s["rank"]:2d} {s["club"].short_code:5s} {s["wins"]}-{s["losses"]} status={s["status_class"]:10s} {s["status_label"]}')

    with app.test_client() as client:
        r = client.get(f'/tournament/{tour2.id}')
        html = r.data.decode('utf-8', errors='replace')
        assert 'tour-type-major' in html, 'major type badge missing'
        assert 'podium' in html, 'podium missing'
        assert 'full-standings' in html, 'full standings missing'
        print('\nMajor render: OK')
