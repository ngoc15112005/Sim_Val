import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'val-sim-dev-key')
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL', f'sqlite:///{os.path.join(BASE_DIR, "instance", "val.db")}'
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
    }

    REGION_SLOTS = {
        'major': {'pacific': 2, 'americas': 2, 'emea': 2, 'china': 2},
        'master': {'pacific': 3, 'americas': 3, 'emea': 3, 'china': 3},
        'champion': {'pacific': 4, 'americas': 4, 'emea': 4, 'china': 4},
    }
