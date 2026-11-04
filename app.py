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
        from models import Campaign, CampaignClubState, CampaignStage, CampaignSeason, CampaignStagePlacement
        db.create_all()

        # Graceful SQLite Schema Migration for GPR & History columns
        try:
            with db.engine.connect() as conn:
                cursor = conn.connection.cursor()
                cursor.execute("PRAGMA table_info(campaigns)")
                cols = [row[1] for row in cursor.fetchall()]
                if cols and 'league_ratings' not in cols:
                    cursor.execute("ALTER TABLE campaigns ADD COLUMN league_ratings TEXT DEFAULT '{\"pacific\": 1500.0, \"americas\": 1500.0, \"emea\": 1500.0, \"china\": 1500.0}'")
                if cols and 'season_hosts' not in cols:
                    cursor.execute("ALTER TABLE campaigns ADD COLUMN season_hosts TEXT DEFAULT '{}'")

                cursor.execute("PRAGMA table_info(campaign_club_states)")
                state_cols = [row[1] for row in cursor.fetchall()]
                if state_cols:
                    if 'team_elo' not in state_cols:
                        cursor.execute("ALTER TABLE campaign_club_states ADD COLUMN team_elo REAL DEFAULT 1500.0")
                    if 'power_score' not in state_cols:
                        cursor.execute("ALTER TABLE campaign_club_states ADD COLUMN power_score REAL DEFAULT 1500.0")
                    if 'power_rating' not in state_cols:
                        cursor.execute("ALTER TABLE campaign_club_states ADD COLUMN power_rating REAL DEFAULT 80.0")
                    if 'previous_rank' not in state_cols:
                        cursor.execute("ALTER TABLE campaign_club_states ADD COLUMN previous_rank INTEGER")
                    if 'win_streak' not in state_cols:
                        cursor.execute("ALTER TABLE campaign_club_states ADD COLUMN win_streak INTEGER DEFAULT 0")

                conn.connection.commit()
        except Exception as _e:
            pass

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
