"""Debug Champion."""
import sys
sys.path.insert(0, '.')
from app import create_app
from models import db, Club, ClubRating, MatchMap, Match, TournamentParticipant, Tournament
from engine.tournament import create_tournament, generate_bracket, simulate_all_pending
from services.bracket_service import generate_playoff_matches, _team_to_dict

app = create_app()
with app.app_context():
    ClubRating.query.delete(); MatchMap.query.delete(); Match.query.delete()
    TournamentParticipant.query.delete(); Tournament.query.delete()
    db.session.commit()

    pools = {}
    for c in Club.query.all():
        pools.setdefault(c.region.slug, []).append(c)
    cids, rseeds = [], []
    for region in ['pacific', 'americas', 'emea', 'china']:
        sorted_c = sorted(pools[region], key=lambda c: c.current_rating, reverse=True)
        for i in range(4):
            cids.append(sorted_c[i].id)
            rseeds.append(i + 1)
    tour = create_tournament('champion', 'C', cids, rseeds)
    generate_bracket(tour)
    db.session.commit()
    simulate_all_pending(tour)
    db.session.commit()

    # Direct query, not via relationship
    advancing = TournamentParticipant.query.filter_by(
        tournament_id=tour.id,
    ).filter(TournamentParticipant.seed.isnot(None)).filter(TournamentParticipant.seed > 0).all()
    print(f'Advancing from DB: {len(advancing)}')
    for p in sorted(advancing, key=lambda p: p.seed or 0):
        print(f'  seed={p.seed} club_id={p.club_id}')

    templates = generate_playoff_matches(tour, advancing)
    print(f'\nTemplates: {len(templates)}')
    for t in templates:
        print(f'  {t.get("round_name")}')
