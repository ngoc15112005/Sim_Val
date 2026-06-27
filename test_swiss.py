import sys
sys.path.insert(0, '.')
from app import create_app
from models import db, Club, ClubRating, MatchMap, Match, TournamentParticipant, Tournament
from engine.tournament import create_tournament, generate_bracket

app = create_app()
with app.app_context():
    ClubRating.query.delete(); MatchMap.query.delete(); Match.query.delete()
    TournamentParticipant.query.delete(); Tournament.query.delete()
    db.session.commit()

    clubs = Club.query.all()
    pools = {}
    for c in clubs:
        pools.setdefault(c.region.slug, []).append(c)

    # Master: 3 per region, top by rating
    cids = []
    rseeds = []
    for region in ['pacific', 'americas', 'emea', 'china']:
        sorted_clubs = sorted(pools[region], key=lambda c: c.current_rating, reverse=True)
        for i in range(3):
            cids.append(sorted_clubs[i].id)
            rseeds.append(i + 1)

    tour = create_tournament('master', 'Test', cids, rseeds)
    generate_bracket(tour)
    db.session.commit()

    print('Master Swiss R1 pairings (seed2 vs seed3, cross-region):')
    swiss = Match.query.filter_by(tournament_id=tour.id, round_type='swiss').all()
    for m in swiss:
        a = TournamentParticipant.query.filter_by(tournament_id=tour.id, club_id=m.team_a_id).first()
        b = TournamentParticipant.query.filter_by(tournament_id=tour.id, club_id=m.team_b_id).first()
        a_seed = a.regional_seed if a else '?'
        b_seed = b.regional_seed if b else '?'
        same = a.region == b.region if a and b else '?'
        print(f'  [{a.region}] S{a_seed} {m.team_a.short_code} vs [{b.region}] S{b_seed} {m.team_b.short_code}  same? {same}')
