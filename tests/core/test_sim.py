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
    cids, rseeds = [], []
    for region in ['pacific', 'americas', 'emea', 'china']:
        sorted_c = sorted(pools[region], key=lambda c: c.current_rating, reverse=True)
        for i in range(3):
            cids.append(sorted_c[i].id); rseeds.append(i+1)

    tour = create_tournament('master', 'T', cids, rseeds)
    generate_bracket(tour); db.session.commit()
    simulate_all_pending(tour); db.session.commit()

    with app.test_client() as client:
        r = client.get(f'/tournament/{tour.id}')
        assert r.status_code == 200, f'Status: {r.status_code}'
        html = r.data.decode('utf-8', errors='replace')
        checks = [
            ('playoff-tree', 'tree container'),
            ('upper-bracket', 'upper bracket div'),
            ('lower-bracket', 'lower bracket div'),
            ('bracket-rounds', 'rounds container'),
            ('bracket-column', 'column'),
            ('round-header', 'round header'),
            ('match-box', 'match box'),
            ('round-matches', 'matches container'),
            ('grand-final-column', 'grand final col'),
            ('status-pending', 'status class'),
            ('status-completed', 'completed class'),
        ]
        print('=== CSS class render checks ===')
        for needle, label in checks:
            print(f'  {label}: {needle in html}')

    css_path = r'E:\SIM\VAL\val-sim\static\style.css'
    with open(css_path, 'r', encoding='utf-8') as f:
        css = f.read()

    leftover = '.bracket-round:not(:last-child) .match-box::after' in css
    print(f'\nLeftover old bracket-round rules: {leftover}')

    leftover2 = '\n.bracket {' in css
    print(f'Leftover old .bracket top-level: {leftover2}')

    dup = css.count('.swiss-round-matches {')
    print(f'Duplicate .swiss-round-matches definitions: {dup}')

    total_lines = css.count('\n')
    print(f'Total CSS lines: {total_lines}')
