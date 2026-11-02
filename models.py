from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Region(db.Model):
    __tablename__ = 'regions'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    slug = db.Column(db.String(20), unique=True, nullable=False)
    clubs = db.relationship('Club', backref='region', lazy=True)

    def to_dict(self):
        return {'id': self.id, 'name': self.name, 'slug': self.slug}


class Club(db.Model):
    __tablename__ = 'clubs'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    short_code = db.Column(db.String(5), unique=True, nullable=False)
    region_id = db.Column(db.Integer, db.ForeignKey('regions.id'), nullable=False)
    base_rating = db.Column(db.Integer, default=80)
    current_rating = db.Column(db.Integer, default=80)
    logo_url = db.Column(db.String(300))
    is_active = db.Column(db.Boolean, default=True)

    rating_history = db.relationship('ClubRating', backref='club', lazy=True,
                                     order_by='ClubRating.id.desc()')

    def to_dict(self):
        return {
            'id': self.id, 'name': self.name, 'short_code': self.short_code,
            'region_id': self.region_id, 'region_slug': self.region.slug if self.region else None,
            'base_rating': self.base_rating, 'current_rating': self.current_rating,
            'logo_url': self.logo_url, 'is_active': self.is_active
        }


class Role(db.Model):
    __tablename__ = 'roles'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(30), unique=True, nullable=False)

    def to_dict(self):
        return {'id': self.id, 'name': self.name}


class Player(db.Model):
    __tablename__ = 'players'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    age = db.Column(db.Integer, default=20)
    club_id = db.Column(db.Integer, db.ForeignKey('clubs.id'))
    role_id = db.Column(db.Integer, db.ForeignKey('roles.id'))
    rating = db.Column(db.Integer, default=80)
    is_active = db.Column(db.Boolean, default=True)

    club = db.relationship('Club', backref='players')
    role = db.relationship('Role', backref='players')

    def to_dict(self):
        return {
            'id': self.id, 'name': self.name, 'age': self.age,
            'club_id': self.club_id, 'role_id': self.role_id,
            'rating': self.rating, 'is_active': self.is_active,
        }


class Tournament(db.Model):
    __tablename__ = 'tournaments'
    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(20), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    status = db.Column(db.String(20), default='setup')
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    participants = db.relationship('TournamentParticipant', backref='tournament', lazy=True,
                                   order_by='TournamentParticipant.seed',
                                   cascade='all, delete-orphan')
    matches = db.relationship('Match', backref='tournament', lazy=True,
                              cascade='all, delete-orphan')
    ratings = db.relationship('ClubRating', backref='tournament', lazy=True,
                              cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id, 'type': self.type, 'name': self.name,
            'status': self.status, 'created_at': self.created_at.isoformat(),
        }


class TournamentParticipant(db.Model):
    __tablename__ = 'tournament_participants'
    id = db.Column(db.Integer, primary_key=True)
    tournament_id = db.Column(db.Integer, db.ForeignKey('tournaments.id'), nullable=False)
    club_id = db.Column(db.Integer, db.ForeignKey('clubs.id'), nullable=False)
    seed = db.Column(db.Integer)
    regional_seed = db.Column(db.Integer)
    region = db.Column(db.String(20))
    group_label = db.Column(db.String(5))
    final_rank = db.Column(db.Integer)

    club = db.relationship('Club', backref='participations')

    def to_dict(self):
        return {
            'id': self.id, 'tournament_id': self.tournament_id,
            'club_id': self.club_id, 'seed': self.seed,
            'regional_seed': self.regional_seed,
            'region': self.region, 'final_rank': self.final_rank,
            'club': self.club.to_dict() if self.club else None,
        }


class Match(db.Model):
    __tablename__ = 'matches'
    id = db.Column(db.Integer, primary_key=True)
    tournament_id = db.Column(db.Integer, db.ForeignKey('tournaments.id'), nullable=False)
    round_type = db.Column(db.String(20), nullable=False)
    round_name = db.Column(db.String(30), nullable=False)
    match_order = db.Column(db.Integer, default=0)
    team_a_id = db.Column(db.Integer, db.ForeignKey('clubs.id'))
    team_b_id = db.Column(db.Integer, db.ForeignKey('clubs.id'))
    team_a_score = db.Column(db.Integer)
    team_b_score = db.Column(db.Integer)
    winner_id = db.Column(db.Integer, db.ForeignKey('clubs.id'))
    loser_id = db.Column(db.Integer, db.ForeignKey('clubs.id'))
    status = db.Column(db.String(20), default='pending')
    is_manual = db.Column(db.Boolean, default=False)

    team_a = db.relationship('Club', foreign_keys=[team_a_id])
    team_b = db.relationship('Club', foreign_keys=[team_b_id])
    winner = db.relationship('Club', foreign_keys=[winner_id])
    loser = db.relationship('Club', foreign_keys=[loser_id])
    maps = db.relationship('MatchMap', backref='match', lazy=True,
                           order_by='MatchMap.map_number',
                           cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id, 'tournament_id': self.tournament_id,
            'round_type': self.round_type, 'round_name': self.round_name,
            'match_order': self.match_order,
            'team_a': self.team_a.to_dict() if self.team_a else None,
            'team_b': self.team_b.to_dict() if self.team_b else None,
            'team_a_score': self.team_a_score, 'team_b_score': self.team_b_score,
            'winner_id': self.winner_id,
            'status': self.status, 'is_manual': self.is_manual,
            'maps': [m.to_dict() for m in self.maps] if self.maps else [],
        }


class MatchMap(db.Model):
    __tablename__ = 'match_maps'
    id = db.Column(db.Integer, primary_key=True)
    match_id = db.Column(db.Integer, db.ForeignKey('matches.id'), nullable=False)
    map_number = db.Column(db.Integer, nullable=False)
    team_a_score = db.Column(db.Integer, nullable=False)
    team_b_score = db.Column(db.Integer, nullable=False)
    winner_id = db.Column(db.Integer, db.ForeignKey('clubs.id'))

    winner = db.relationship('Club', foreign_keys=[winner_id])

    def to_dict(self):
        return {
            'id': self.id, 'match_id': self.match_id,
            'map_number': self.map_number,
            'team_a_score': self.team_a_score, 'team_b_score': self.team_b_score,
            'winner_id': self.winner_id,
        }


class ClubRating(db.Model):
    __tablename__ = 'club_ratings'
    id = db.Column(db.Integer, primary_key=True)
    club_id = db.Column(db.Integer, db.ForeignKey('clubs.id'), nullable=False)
    tournament_id = db.Column(db.Integer, db.ForeignKey('tournaments.id'), nullable=False)
    rating_before = db.Column(db.Integer, nullable=False)
    rating_after = db.Column(db.Integer, nullable=False)

    def to_dict(self):
        return {
            'id': self.id, 'club_id': self.club_id,
            'tournament_id': self.tournament_id,
            'rating_before': self.rating_before,
            'rating_after': self.rating_after,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Campaign / Story Mode (Chế độ Cốt truyện)
# ─────────────────────────────────────────────────────────────────────────────

class Campaign(db.Model):
    __tablename__ = 'campaigns'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    current_year = db.Column(db.Integer, default=2027)
    current_stage = db.Column(db.String(30), default='open_qualifier')
    status = db.Column(db.String(20), default='active')  # 'active', 'completed'
    league_ratings = db.Column(db.Text, default='{"pacific": 1500.0, "americas": 1500.0, "emea": 1500.0, "china": 1500.0}')
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    club_states = db.relationship('CampaignClubState', backref='campaign', lazy=True,
                                  cascade='all, delete-orphan')
    stages = db.relationship('CampaignStage', backref='campaign', lazy=True,
                             cascade='all, delete-orphan')
    seasons = db.relationship('CampaignSeason', backref='campaign', lazy=True,
                              cascade='all, delete-orphan')
    placements = db.relationship('CampaignStagePlacement', backref='campaign', lazy=True,
                                 cascade='all, delete-orphan')

    def to_dict(self):
        import json
        lr = {"pacific": 1500.0, "americas": 1500.0, "emea": 1500.0, "china": 1500.0}
        try:
            if self.league_ratings:
                lr = json.loads(self.league_ratings)
        except Exception:
            pass
        return {
            'id': self.id,
            'name': self.name,
            'current_year': self.current_year,
            'current_stage': self.current_stage,
            'status': self.status,
            'league_ratings': lr,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class CampaignClubState(db.Model):
    __tablename__ = 'campaign_club_states'
    id = db.Column(db.Integer, primary_key=True)
    campaign_id = db.Column(db.Integer, db.ForeignKey('campaigns.id'), nullable=False)
    club_id = db.Column(db.Integer, db.ForeignKey('clubs.id'), nullable=False)
    story_rating = db.Column(db.Integer, default=80)
    form_modifier = db.Column(db.Integer, default=0)
    championship_points = db.Column(db.Integer, default=0)
    is_partner = db.Column(db.Boolean, default=False)
    stage_ranks = db.Column(db.Text, default='{}')  # JSON: {'kickoff': 1, 'major': 2, ...}
    regular_season_wins = db.Column(db.Integer, default=0)
    map_differential = db.Column(db.Integer, default=0)
    round_differential = db.Column(db.Integer, default=0)

    # Riot Global Power Rankings (GPR x AWS) Fields
    team_elo = db.Column(db.Float, default=1500.0)
    power_score = db.Column(db.Float, default=1500.0)
    power_rating = db.Column(db.Float, default=80.0)
    previous_rank = db.Column(db.Integer, nullable=True)
    win_streak = db.Column(db.Integer, default=0)

    club = db.relationship('Club', backref='campaign_states')

    @property
    def effective_rating(self):
        return (self.story_rating or 80) + (self.form_modifier or 0)

    def get_stage_rank(self, stage_key):
        import json
        try:
            ranks = json.loads(self.stage_ranks or '{}')
            return ranks.get(stage_key)
        except Exception:
            return None

    def set_stage_rank(self, stage_key, rank):
        import json
        try:
            ranks = json.loads(self.stage_ranks or '{}')
        except Exception:
            ranks = {}
        ranks[stage_key] = rank
        self.stage_ranks = json.dumps(ranks)

    def to_dict(self):
        import json
        from engine.power_rating import get_tier_info
        ranks = {}
        try:
            ranks = json.loads(self.stage_ranks or '{}')
        except Exception:
            pass
        ps = self.power_score if self.power_score is not None else 1500.0
        tier_data = get_tier_info(ps)
        return {
            'id': self.id,
            'campaign_id': self.campaign_id,
            'club_id': self.club_id,
            'story_rating': self.story_rating,
            'form_modifier': self.form_modifier,
            'effective_rating': self.effective_rating,
            'championship_points': self.championship_points,
            'is_partner': self.is_partner,
            'stage_ranks': ranks,
            'regular_season_wins': self.regular_season_wins,
            'map_differential': self.map_differential,
            'round_differential': self.round_differential,
            'team_elo': round(self.team_elo if self.team_elo is not None else 1500.0, 1),
            'power_score': round(ps, 1),
            'power_rating': round(self.power_rating if self.power_rating is not None else 80.0, 1),
            'previous_rank': self.previous_rank,
            'win_streak': self.win_streak or 0,
            'tier': tier_data,
            'club': self.club.to_dict() if self.club else None,
        }



class CampaignStage(db.Model):
    __tablename__ = 'campaign_stages'
    id = db.Column(db.Integer, primary_key=True)
    campaign_id = db.Column(db.Integer, db.ForeignKey('campaigns.id'), nullable=False)
    year = db.Column(db.Integer, nullable=False)
    stage_key = db.Column(db.String(30), nullable=False)
    stage_name = db.Column(db.String(100), nullable=False)
    status = db.Column(db.String(20), default='pending')  # 'pending', 'in_progress', 'completed'
    stage_data = db.Column(db.Text, nullable=True)  # JSON formatted results
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    completed_at = db.Column(db.DateTime, nullable=True)

    def to_dict(self):
        return {
            'id': self.id,
            'campaign_id': self.campaign_id,
            'year': self.year,
            'stage_key': self.stage_key,
            'stage_name': self.stage_name,
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
        }


class CampaignSeason(db.Model):
    __tablename__ = 'campaign_seasons'
    id = db.Column(db.Integer, primary_key=True)
    campaign_id = db.Column(db.Integer, db.ForeignKey('campaigns.id'), nullable=False)
    year = db.Column(db.Integer, nullable=False)
    major_winner_id = db.Column(db.Integer, db.ForeignKey('clubs.id'), nullable=True)
    master_winner_id = db.Column(db.Integer, db.ForeignKey('clubs.id'), nullable=True)
    ewc_winner_id = db.Column(db.Integer, db.ForeignKey('clubs.id'), nullable=True)
    champion_winner_id = db.Column(db.Integer, db.ForeignKey('clubs.id'), nullable=True)
    mvp_club_id = db.Column(db.Integer, db.ForeignKey('clubs.id'), nullable=True)
    recap_data = db.Column(db.Text, nullable=True)
    completed_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    major_winner = db.relationship('Club', foreign_keys=[major_winner_id])
    master_winner = db.relationship('Club', foreign_keys=[master_winner_id])
    ewc_winner = db.relationship('Club', foreign_keys=[ewc_winner_id])
    champion_winner = db.relationship('Club', foreign_keys=[champion_winner_id])
    mvp_club = db.relationship('Club', foreign_keys=[mvp_club_id])

    def to_dict(self):
        return {
            'id': self.id,
            'campaign_id': self.campaign_id,
            'year': self.year,
            'major_winner': self.major_winner.to_dict() if self.major_winner else None,
            'master_winner': self.master_winner.to_dict() if self.master_winner else None,
            'ewc_winner': self.ewc_winner.to_dict() if self.ewc_winner else None,
            'champion_winner': self.champion_winner.to_dict() if self.champion_winner else None,
            'mvp_club': self.mvp_club.to_dict() if self.mvp_club else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
        }


class CampaignStagePlacement(db.Model):
    """Stores persistent historical final placements for each tournament/stage across all campaign years."""
    __tablename__ = 'campaign_stage_placements'
    id = db.Column(db.Integer, primary_key=True)
    campaign_id = db.Column(db.Integer, db.ForeignKey('campaigns.id'), nullable=False)
    year = db.Column(db.Integer, nullable=False)
    stage_key = db.Column(db.String(30), nullable=False)
    tournament_name = db.Column(db.String(100), nullable=False)
    region_slug = db.Column(db.String(20), nullable=True)  # 'pacific', 'americas', 'emea', 'china', or None for intl
    club_id = db.Column(db.Integer, db.ForeignKey('clubs.id'), nullable=False)

    rank = db.Column(db.Integer, nullable=False)
    rank_display = db.Column(db.String(30), nullable=False)  # '1st (Vô địch)', '2nd (Á quân)', '3rd', 'Top 4', etc.
    elimination_stage = db.Column(db.String(50), nullable=True)
    stage_points_earned = db.Column(db.Integer, default=0)
    matches_won = db.Column(db.Integer, default=0)
    matches_lost = db.Column(db.Integer, default=0)

    # Snapshot Power Ratings at the moment of stage completion
    power_score_snapshot = db.Column(db.Float, default=1500.0)
    power_rating_snapshot = db.Column(db.Float, default=80.0)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    club = db.relationship('Club', backref='placements')

    def to_dict(self):
        from engine.power_rating import get_tier_info
        ps = self.power_score_snapshot if self.power_score_snapshot is not None else 1500.0
        return {
            'id': self.id,
            'campaign_id': self.campaign_id,
            'year': self.year,
            'stage_key': self.stage_key,
            'tournament_name': self.tournament_name,
            'region_slug': self.region_slug,
            'club_id': self.club_id,
            'rank': self.rank,
            'rank_display': self.rank_display,
            'elimination_stage': self.elimination_stage,
            'stage_points_earned': self.stage_points_earned or 0,
            'matches_won': self.matches_won or 0,
            'matches_lost': self.matches_lost or 0,
            'power_score_snapshot': round(ps, 1),
            'power_rating_snapshot': round(self.power_rating_snapshot if self.power_rating_snapshot is not None else 80.0, 1),
            'tier': get_tier_info(ps),
            'club': self.club.to_dict() if self.club else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


