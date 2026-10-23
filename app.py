import os
from flask import Flask
from config import Config
from models import db


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Ensure SQLite directory exists
    db_uri = app.config.get('SQLALCHEMY_DATABASE_URI', '')
    if db_uri.startswith('sqlite:///'):
        db_path = db_uri[len('sqlite:///'):]
        db_dir = os.path.dirname(os.path.abspath(db_path))
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
    os.makedirs(app.instance_path, exist_ok=True)

    db.init_app(app)

    with app.app_context():
        from models import Region, Club, Role, Player, Tournament
        from models import TournamentParticipant, Match, MatchMap, ClubRating
        db.create_all()
        if Region.query.count() == 0 or Club.query.count() == 0:
            from seed import seed_initial_data
            seed_initial_data()
        else:
            from seed import sync_club_logos_internal
            sync_club_logos_internal()

    from routes import register_routes
    register_routes(app)

    # Register Jinja2 globals (pure helper functions callable from templates)
    from services.bracket_service import _match_label, _match_short_label
    app.jinja_env.globals['_match_label'] = _match_label
    app.jinja_env.globals['_match_short_label'] = _match_short_label

    return app


if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, port=5000)
