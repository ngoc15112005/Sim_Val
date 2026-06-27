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
                                   order_by='TournamentParticipant.seed')
    matches = db.relationship('Match', backref='tournament', lazy=True)

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
    seed = db.Column(db.Integer, nullable=False)
    region = db.Column(db.String(20))
    group_label = db.Column(db.String(5))
    final_rank = db.Column(db.Integer)

    club = db.relationship('Club', backref='participations')

    def to_dict(self):
        return {
            'id': self.id, 'tournament_id': self.tournament_id,
            'club_id': self.club_id, 'seed': self.seed,
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
                           order_by='MatchMap.map_number')

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
