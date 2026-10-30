import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
INSTANCE_DIR = os.path.join(BASE_DIR, 'instance')
os.makedirs(INSTANCE_DIR, exist_ok=True)


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'val-sim-dev-key')
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL', f'sqlite:///{os.path.join(INSTANCE_DIR, "val.db")}'
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    TOURNAMENT_TYPES = {
        'major': {
            'name': 'Major',
            'team_count': 8,
            'swiss_teams': 8,
            'swiss_win_target': 2,
            'swiss_loss_target': 2,
            'advance_count': 4,
            'direct_qualifiers': 0,
        },
        'master': {
            'name': 'Master',
            'team_count': 12,
            'swiss_teams': 8,
            'swiss_win_target': 2,
            'swiss_loss_target': 2,
            'advance_count': 4,
            'direct_qualifiers': 4,
        },
        'champion': {
            'name': 'Champion',
            'team_count': 16,
            'group_stage': True,
            'advance_count': 8,
            'direct_qualifiers': 0,
        },
        'ewc': {
            'name': 'EWC',
            'team_count': 16,
            'group_stage': True,
            'advance_count': 8,
            'direct_qualifiers': 0,
            'playoff_type': 'single_elim',
        },
    }

    REGION_SLOTS = {
        'major': {'pacific': 2, 'americas': 2, 'emea': 2, 'china': 2},
        'master': {'pacific': 3, 'americas': 3, 'emea': 3, 'china': 3},
        'champion': {'pacific': 4, 'americas': 4, 'emea': 4, 'china': 4},
        'ewc': {'pacific': 4, 'americas': 4, 'emea': 4, 'china': 4},
    }

    PARTNER_TEAMS_BY_REGION = {
        'pacific': ['PRX', 'GEN', 'T1', 'ZETA', 'RRQ', 'CR', 'FS', 'GAM'],
        'americas': ['100T', 'G2', 'KRU', 'LEV', 'LOUD', 'MIBR', 'NRG', 'SEN'],
        'emea': ['BBL', 'FNC', 'FUT', 'M8', 'KC', 'TH', 'TL', 'VIT'],
        'china': ['AG', 'BLG', 'EDG', 'JDG', 'TE', 'TYL', 'WBG', 'XLG'],
    }

    CIRCUIT_STAGES = [
        {'key': 'open_qualifier', 'name': 'Open Qualifier', 'type': 'regional', 'desc': '16 Non-partners → 4 Kickoff qualifiers per region'},
        {'key': 'kickoff', 'name': 'Regional Kickoff', 'type': 'regional', 'desc': '8 Partners + 4 Qualifiers → Top 2 to Major'},
        {'key': 'major', 'name': 'VCT Major (Masters 1)', 'type': 'international', 'desc': '8 World elite teams (Top 2 per region)'},
        {'key': 'stage1', 'name': 'Regional Stage 1', 'type': 'regional', 'desc': '12 teams → Top 3 to Masters, Top 4 to EWC'},
        {'key': 'master', 'name': 'VCT Masters (Masters 2)', 'type': 'international', 'desc': '12 International teams'},
        {'key': 'ewc', 'name': 'Esports World Cup (EWC)', 'type': 'international', 'desc': '16 World teams (GSL Groups + Playoffs)'},
        {'key': 'stage2', 'name': 'Regional Stage 2', 'type': 'regional', 'desc': '12 teams → Final Championship Points battle'},
        {'key': 'champion', 'name': 'VALORANT Champions', 'type': 'international', 'desc': '16 Best teams worldwide (World Championship)'},
        {'key': 'season_summary', 'name': 'Year-End Hall of Fame', 'type': 'summary', 'desc': 'Annual Recap, Title Winners & MVP'},
    ]

