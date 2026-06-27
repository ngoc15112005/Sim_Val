"""Test: Champion group stage display."""
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

    clubs = Club.query.order_by(Club.current_rating.desc()).limit(16).all()
    club_ids = [c.id for c in clubs]
    regional_seeds = [1, 2, 3, 4, 1, 2, 3, 4, 1, 2, 3, 4, 1, 2, 3, 4]

    tour = create_tournament('champion', 'Champion Test', club_ids, regional_seeds)
    generate_bracket(tour)
    db.session.commit()

    with app.test_client() as client:
        r = client.get(f'/tournament/{tour.id}')
        assert r.status_code == 200
        html = r.data.decode('utf-8')
        assert 'Group Stage' in html
        assert 'group' in html.lower()
        print('OK: Champion group stage renders correctly')
