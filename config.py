import os
import urllib.parse

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
INSTANCE_DIR = os.path.join(BASE_DIR, 'instance')
os.makedirs(INSTANCE_DIR, exist_ok=True)


def _clean_database_url(url: str | None) -> str:
    if not url:
        return f'sqlite:///{os.path.join(INSTANCE_DIR, "val.db")}'
    if url.startswith('postgres://'):
        url = url.replace('postgres://', 'postgresql://', 1)
    if url.startswith('libsql://'):
        url = url.replace('libsql://', 'sqlite+libsql://', 1)
        # Ensure trailing slash before query parameters (required by libsql HTTP endpoint parser)
        if '?' in url:
            base, qs = url.split('?', 1)
            if not base.endswith('/'):
                base += '/'
            url = f"{base}?{qs}"
        else:
            if not url.endswith('/'):
                url += '/'
            url = f"{url}?secure=true"
        if 'secure=true' not in url:
            url += '&secure=true'

        turso_token = os.environ.get('TURSO_AUTH_TOKEN')
        if turso_token and 'authToken=' not in url:
            url += f"&authToken={turso_token}"

    try:
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme.startswith('postgres'):
            query_params = urllib.parse.parse_qs(parsed.query)
            # Connection poolers (Neon / Supabase PgBouncer) do NOT support channel_binding.
            # Stripping channel_binding prevents "channel binding not supported" OperationalError.
            query_params.pop('channel_binding', None)
            if 'sslmode' not in query_params:
                query_params['sslmode'] = ['require']
            new_query = urllib.parse.urlencode([(k, v) for k, vals in query_params.items() for v in vals])
            parsed = parsed._replace(query=new_query)
            url = urllib.parse.urlunsplit(parsed)
    except Exception:
        pass
    return url


class Config:
    CURRENT_CAMPAIGN_SCHEMA_VERSION = 2
    CURRENT_SAVE_FORMAT_VERSION = '2.0'
    SECRET_KEY = os.environ.get('SECRET_KEY', 'val-sim-dev-key')
    SQLALCHEMY_DATABASE_URI = _clean_database_url(
        os.environ.get('TURSO_DATABASE_URL') or os.environ.get('DATABASE_URL')
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
    }
    _turso_token = os.environ.get('TURSO_AUTH_TOKEN')
    if _turso_token:
        SQLALCHEMY_ENGINE_OPTIONS['connect_args'] = {
            'auth_token': _turso_token,
            'timeout': 15.0,
        }

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
        {'key': 'kickoff', 'name': 'Regional Kickoff', 'type': 'regional', 'desc': '8 Partners + 4 Qualifiers → Top 2 to Major, Top 8 safe for Stage 1'},
        {'key': 'major', 'name': 'VCT Major', 'type': 'international', 'desc': '8 World elite teams (Top 2 per region)'},
        {'key': 'oq_stage1', 'name': 'Open Qualifier Stage 1', 'type': 'regional', 'desc': '4 Kickoff bottom teams + 12 Challenger teams → 4 Stage 1 qualifiers'},
        {'key': 'stage1', 'name': 'Regional Stage 1', 'type': 'regional', 'desc': '12 teams (8 Retained + 4 Qualifiers) → Top 3 to Masters, Top 2 to EWC'},
        {'key': 'ewc_qualifier', 'name': 'EWC Regional Qualifier', 'type': 'regional', 'desc': 'Phase 1 (16 teams) + Phase 2 (8 teams) → 2 EWC berths'},
        {'key': 'master', 'name': 'VCT Masters', 'type': 'international', 'desc': '12 International teams (Top 3 per region)'},
        {'key': 'ewc', 'name': 'Esports World Cup (EWC)', 'type': 'international', 'desc': '16 World teams (GSL Groups + Playoffs)'},
        {'key': 'oq_stage2', 'name': 'Open Qualifier Stage 2', 'type': 'regional', 'desc': '4 Stage 1 bottom teams + 12 Challenger teams → 4 Stage 2 qualifiers'},
        {'key': 'stage2', 'name': 'Regional Stage 2', 'type': 'regional', 'desc': '12 teams → Final Championship Points battle'},
        {'key': 'champion', 'name': 'VALORANT Champions', 'type': 'international', 'desc': '16 Best teams worldwide (World Championship)'},
        {'key': 'season_summary', 'name': 'Year-End Hall of Fame', 'type': 'summary', 'desc': 'Annual Recap, Title Winners & MVP'},
    ]

    CHAMPIONSHIP_POINTS_RULES = {
        'kickoff': {1: 3, 2: 2, 3: 1, 4: 1},
        'major': {1: 5, 2: 3, 3: 2, 4: 1},                    # Masters Bangkok (Major)
        'stage1_regular_win': 1,                              # 1 CP per regular season win
        'stage1_playoffs': {1: 5, 2: 3, 3: 2, 4: 1},
        'master': {1: 7, 2: 5, 3: 4, 4: 3, 5: 2, 6: 2},         # Masters Toronto (Master)
        'stage2_regular_win': 1,                              # 1 CP per regular season win
        'stage2_playoffs': {1: 7, 2: 5, 3: 4, 4: 3},
        'champions_slots_per_region': {
            'stage2_champion': 1,
            'stage2_runner_up': 1,
            'points_slot_1': 1,
            'points_slot_2': 1,
            'total': 4,
        },
        'tiebreaker_priority': [
            'stage2_rank',
            'master_rank',       # Masters Toronto
            'stage1_rank',
            'major_rank',        # Masters Bangkok
            'kickoff_rank',
            'season_regular_wins',
            'map_diff',
            'round_diff',
            'h2h_match',
            'h2h_map_diff',
            'h2h_round_diff',
        ]
    }

    PRIZE_POOLS_BY_STAGE = {
        'champion': {
            'total': 2_250_000,
            'ranks': {
                1: 1_000_000, 2: 400_000, 3: 250_000, 4: 130_000,
                5: 85_000, 6: 85_000, 7: 50_000, 8: 50_000,
                9: 30_000, 10: 30_000, 11: 30_000, 12: 30_000,
                13: 20_000, 14: 20_000, 15: 20_000, 16: 20_000,
            },
        },
        'ewc': {
            'total': 3_500_000,
            'ranks': {
                1: 1_500_000, 2: 650_000, 3: 350_000, 4: 200_000,
                5: 100_000, 6: 100_000, 7: 100_000, 8: 100_000,
                9: 60_000, 10: 60_000, 11: 60_000, 12: 60_000,
                13: 40_000, 14: 40_000, 15: 40_000, 16: 40_000,
            },
        },
        'master': {
            'total': 1_000_000,
            'ranks': {
                1: 350_000, 2: 200_000, 3: 125_000, 4: 75_000,
                5: 50_000, 6: 50_000, 7: 35_000, 8: 35_000,
                9: 25_000, 10: 25_000, 11: 15_000, 12: 15_000,
            },
        },
        'major': {
            'total': 750_000,
            'ranks': {
                1: 300_000, 2: 160_000, 3: 100_000, 4: 70_000,
                5: 35_000, 6: 35_000, 7: 25_000, 8: 25_000,
            },
        },
        'stage1': {
            'total': 250_000,
            'ranks': {1: 100_000, 2: 65_000, 3: 40_000, 4: 25_000, 5: 10_000, 6: 10_000},
        },
        'stage2': {
            'total': 250_000,
            'ranks': {1: 100_000, 2: 65_000, 3: 40_000, 4: 25_000, 5: 10_000, 6: 10_000},
        },
        'kickoff': {
            'total': 100_000,
            'ranks': {1: 50_000, 2: 25_000, 3: 15_000, 4: 10_000},
        },
        'open_qualifier': {
            'total': 30_000,
            'ranks': {1: 12_000, 2: 8_000, 3: 5_000, 4: 5_000},
        },
        'oq_stage1': {
            'total': 30_000,
            'ranks': {1: 12_000, 2: 8_000, 3: 5_000, 4: 5_000},
        },
        'oq_stage2': {
            'total': 30_000,
            'ranks': {1: 12_000, 2: 8_000, 3: 5_000, 4: 5_000},
        },
        'ewc_qualifier': {
            'total': 30_000,
            'ranks': {1: 12_000, 2: 8_000, 3: 5_000, 4: 5_000},
        },
    }


def get_stage_prize_money(stage_key: str, rank: int | None) -> int:
    """Tra cứu O(1) tiền thưởng USD theo stage_key và thứ hạng."""
    if not stage_key or not rank or rank <= 0:
        return 0
    pool = Config.PRIZE_POOLS_BY_STAGE.get(stage_key)
    if not pool:
        return 0
    return int(pool.get('ranks', {}).get(int(rank), 0))


def get_stage_total_prize_pool(stage_key: str) -> int:
    """Tổng quỹ tiền thưởng USD của một giải đấu."""
    pool = Config.PRIZE_POOLS_BY_STAGE.get(stage_key or '')
    return int(pool.get('total', 0)) if pool else 0


def format_usd(amount: int | float | None) -> str:
    """Định dạng tiền thưởng USD gọn đẹp ($1,000,000)."""
    val = int(round(amount or 0))
    return f"${val:,}"



