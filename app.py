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

    db_uri = app.config.get('SQLALCHEMY_DATABASE_URI', '')
    is_remote = 'libsql' in db_uri or 'postgres' in db_uri

    # Only run heavy DDL checks and migrations synchronously on local SQLite.
    # On remote DB (Turso/Postgres), schema & data are already imported,
    # and blocking startup with 100+ synchronous queries causes Render port-binding timeouts (502).
    if not is_remote:
        with app.app_context():
            try:
                if db.engine.dialect.name == 'sqlite':
                    from sqlalchemy import event

                    @event.listens_for(db.engine, "connect")
                    def _set_sqlite_pragma(dbapi_connection, _connection_record):
                        cur = dbapi_connection.cursor()
                        cur.execute("PRAGMA journal_mode=WAL")
                        cur.execute("PRAGMA synchronous=NORMAL")
                        cur.execute("PRAGMA temp_store=MEMORY")
                        cur.execute("PRAGMA cache_size=-32000")
                        cur.close()

                from models import Region, Club, Role, Player, Tournament
                from models import TournamentParticipant, Match, MatchMap, ClubRating
                from models import (
                    Campaign, CampaignClubState, CampaignStage, CampaignSeason,
                    CampaignStagePlacement, CampaignStoryline, CampaignPartnershipReview,
                    CampaignPlayer, CampaignMatchRecord,
                )
                db.create_all()

                # Graceful SQLite Schema Migration for GPR, History & Player System v2.0 columns
                if db.engine.dialect.name == 'sqlite':
                    try:
                        with db.engine.connect() as conn:
                            cursor = conn.connection.cursor()
                            cursor.execute("PRAGMA table_info(campaigns)")
                            cols = [row[1] for row in cursor.fetchall()]
                            if cols and 'league_ratings' not in cols:
                                cursor.execute("ALTER TABLE campaigns ADD COLUMN league_ratings TEXT DEFAULT '{\"pacific\": 1500.0, \"americas\": 1500.0, \"emea\": 1500.0, \"china\": 1500.0}'")
                            if cols and 'season_hosts' not in cols:
                                cursor.execute("ALTER TABLE campaigns ADD COLUMN season_hosts TEXT DEFAULT '{}'")
                            if cols and 'schema_version' not in cols:
                                # Mark pre-existing v1 saves as schema_version=1 so incompatible saves are safely locked
                                cursor.execute("ALTER TABLE campaigns ADD COLUMN schema_version INTEGER DEFAULT 1")

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
                                if 'player_bonus' not in state_cols:
                                    cursor.execute("ALTER TABLE campaign_club_states ADD COLUMN player_bonus INTEGER DEFAULT 0")
                                if 'salary_cap' not in state_cols:
                                    cursor.execute("ALTER TABLE campaign_club_states ADD COLUMN salary_cap INTEGER DEFAULT 1200")

                            cursor.execute("PRAGMA table_info(campaign_stage_placements)")
                            pl_cols = [row[1] for row in cursor.fetchall()]
                            if pl_cols and 'prize_money' not in pl_cols:
                                cursor.execute("ALTER TABLE campaign_stage_placements ADD COLUMN prize_money INTEGER DEFAULT 0")

                            cursor.execute("PRAGMA table_info(campaign_stages)")
                            cs_cols = [row[1] for row in cursor.fetchall()]
                            if cs_cols:
                                if 'data_version' not in cs_cols:
                                    cursor.execute("ALTER TABLE campaign_stages ADD COLUMN data_version INTEGER NOT NULL DEFAULT 1")
                                if 'h2h_synced_version' not in cs_cols:
                                    cursor.execute("ALTER TABLE campaign_stages ADD COLUMN h2h_synced_version INTEGER NOT NULL DEFAULT 0")

                            # Ensure composite indexes exist on legacy SQLite databases
                            for idx_sql in (
                                "CREATE INDEX IF NOT EXISTS ix_ccs_campaign_club ON campaign_club_states (campaign_id, club_id)",
                                "CREATE INDEX IF NOT EXISTS ix_cs_campaign_year_stage ON campaign_stages (campaign_id, year, stage_key)",
                                "CREATE INDEX IF NOT EXISTS ix_cs_campaign_status ON campaign_stages (campaign_id, status)",
                                "CREATE INDEX IF NOT EXISTS ix_cs_h2h_sync ON campaign_stages (campaign_id, h2h_synced_version, data_version)",
                                "CREATE INDEX IF NOT EXISTS ix_cseason_campaign_year ON campaign_seasons (campaign_id, year)",
                                "CREATE INDEX IF NOT EXISTS ix_csp_campaign_year_stage ON campaign_stage_placements (campaign_id, year, stage_key)",
                                "CREATE INDEX IF NOT EXISTS ix_csp_campaign_club ON campaign_stage_placements (campaign_id, club_id)",
                                "CREATE INDEX IF NOT EXISTS ix_cstory_campaign_year ON campaign_storylines (campaign_id, year)",
                                "CREATE INDEX IF NOT EXISTS ix_cpr_campaign_year ON campaign_partnership_reviews (campaign_id, year)",
                                "CREATE INDEX IF NOT EXISTS ix_cplayer_campaign_club ON campaign_players (campaign_id, club_id)",
                                "CREATE INDEX IF NOT EXISTS ix_cplayer_campaign_status ON campaign_players (campaign_id, status)",
                                "CREATE INDEX IF NOT EXISTS ix_cmr_h2h ON campaign_match_records (campaign_id, pair_low_id, pair_high_id)",
                                "CREATE INDEX IF NOT EXISTS ix_cmr_camp_year_stage ON campaign_match_records (campaign_id, year, stage_key)",
                            ):
                                cursor.execute(idx_sql)

                            conn.connection.commit()
                    except Exception as _e:
                        pass

                if Region.query.count() == 0 or Club.query.count() == 0:
                    from seed import seed_initial_data
                    seed_initial_data()
                else:
                    from seed import sync_club_logos_internal
                    sync_club_logos_internal()
            except Exception as e:
                app.logger.warning(f"Database initialization deferred or failed: {e}")

    from routes import register_routes
    register_routes(app)

    # Register Jinja2 globals (pure helper functions callable from templates)
    from config import get_stage_prize_money, get_stage_total_prize_pool, format_usd
    from services.bracket_service import _match_label, _match_short_label
    app.jinja_env.globals['_match_label'] = _match_label
    app.jinja_env.globals['_match_short_label'] = _match_short_label
    app.jinja_env.globals['get_stage_prize_money'] = get_stage_prize_money
    app.jinja_env.globals['get_stage_total_prize_pool'] = get_stage_total_prize_pool
    app.jinja_env.globals['format_usd'] = format_usd

    return app


if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, port=5000)
