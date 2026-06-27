from flask import Flask
from config import Config
from models import db


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)

    with app.app_context():
        from models import Region, Club, Role, Player, Tournament
        from models import TournamentParticipant, Match, MatchMap, ClubRating
        db.create_all()

    from routes import register_routes
    register_routes(app)

    return app


if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, port=5000)
