"""Flask routes for VALORANT Tournament Simulator."""

from flask import request, jsonify, render_template
from models import db, Club, Region, Tournament, TournamentParticipant, Match, MatchMap
from engine.tournament import (
    create_tournament, generate_bracket, progress_tournament, simulate_all_pending,
)
from engine.match import simulate_match, resolve_manual_match
from engine.rating import update_ratings
from services.bracket_service import (
    get_swiss_standings, group_playoff_rounds, resolve_match_display,
    get_groups_data, get_swiss_data, get_final_standings,
)
from config import Config


def register_routes(app):

    @app.route('/')
    def index():
        tournaments = Tournament.query.order_by(Tournament.created_at.desc()).all()
        return render_template('index.html', tournaments=tournaments, cfg=Config)

    @app.route('/api/clubs')
    def api_clubs():
        region_filter = request.args.get('region')
        q = Club.query.filter_by(is_active=True)
        if region_filter:
            region = Region.query.filter_by(slug=region_filter).first()
            if region:
                q = q.filter_by(region_id=region.id)
        clubs = q.order_by(Club.current_rating.desc()).all()
        return jsonify([c.to_dict() for c in clubs])

    @app.route('/api/regions')
    def api_regions():
        regions = Region.query.all()
        return jsonify([r.to_dict() for r in regions])

    @app.route('/api/tournament/start', methods=['POST'])
    def api_start_tournament():
        data = request.get_json()
        tour_type = data.get('type')
        name = data.get('name', tour_type.upper())
        club_ids = data.get('club_ids', [])
        regional_seeds = data.get('regional_seeds', [])

        if tour_type not in Config.TOURNAMENT_TYPES:
            return jsonify({'error': f'Loại giải không hợp lệ: {tour_type}'}), 400

        team_count = Config.TOURNAMENT_TYPES[tour_type]['team_count']
        if len(club_ids) != team_count:
            return jsonify({'error': f'Cần {team_count} đội, nhận {len(club_ids)}'}), 400

        slots = Config.REGION_SLOTS.get(tour_type, {})
        if slots:
            region_counts = {}
            clubs = Club.query.filter(Club.id.in_(club_ids)).all()
            for c in clubs:
                slug = c.region.slug if c.region else 'unknown'
                region_counts[slug] = region_counts.get(slug, 0) + 1
            for region_slug, limit in slots.items():
                actual = region_counts.get(region_slug, 0)
                if actual > limit:
                    return jsonify({
                        'error': f'Khu vực {region_slug.upper()} tối đa {limit} đội, hiện có {actual}'
                    }), 400

        try:
            tour = create_tournament(tour_type, name, club_ids, regional_seeds)
            generate_bracket(tour)
            db.session.commit()
            return jsonify(tour.to_dict())
        except Exception as e:
            db.session.rollback()
            return jsonify({'error': str(e)}), 400

    @app.route('/api/tournament/<int:tour_id>')
    def api_get_tournament(tour_id):
        tour = Tournament.query.get_or_404(tour_id)
        participants = TournamentParticipant.query.filter_by(
            tournament_id=tour_id,
        ).order_by(TournamentParticipant.seed).all()
        matches = Match.query.filter_by(
            tournament_id=tour_id,
        ).order_by(Match.match_order).all()

        return jsonify({
            'tournament': tour.to_dict(),
            'participants': [p.to_dict() for p in participants],
            'matches': [m.to_dict() for m in matches],
        })

    @app.route('/api/tournament/<int:tour_id>/match/<int:match_id>/sim', methods=['POST'])
    def api_sim_match(tour_id, match_id):
        match = Match.query.filter_by(id=match_id, tournament_id=tour_id).first_or_404()
        if match.status == 'completed':
            return jsonify({'error': 'Trận này đã hoàn thành'}), 400
        if not match.team_a_id or not match.team_b_id:
            return jsonify({'error': 'Chưa có đủ 2 đội'}), 400

        try:
            winner_id, maps_data = simulate_match(match)
            progress_tournament(Tournament.query.get(tour_id))
            db.session.commit()
            return jsonify({'match': match.to_dict()})
        except Exception as e:
            db.session.rollback()
            return jsonify({'error': str(e)}), 500

    @app.route('/api/tournament/<int:tour_id>/match/<int:match_id>/manual', methods=['POST'])
    def api_manual_match(tour_id, match_id):
        match = Match.query.filter_by(id=match_id, tournament_id=tour_id).first_or_404()
        if not match.team_a_id or not match.team_b_id:
            return jsonify({'error': 'Chưa có đủ 2 đội'}), 400

        data = request.get_json()
        maps_input = data.get('maps', [])

        if not maps_input:
            return jsonify({'error': 'Cần ít nhất 1 map'}), 400

        try:
            resolve_manual_match(match, maps_input)
            progress_tournament(Tournament.query.get(tour_id))
            db.session.commit()
            return jsonify({'match': match.to_dict()})
        except Exception as e:
            db.session.rollback()
            return jsonify({'error': str(e)}), 500

    @app.route('/api/tournament/<int:tour_id>/sim-all', methods=['POST'])
    def api_sim_all(tour_id):
        tour = Tournament.query.get_or_404(tour_id)
        try:
            simulate_all_pending(tour)
            if tour.status == 'finished':
                update_ratings(tour)
            db.session.commit()
            return jsonify(tour.to_dict())
        except Exception as e:
            db.session.rollback()
            return jsonify({'error': str(e)}), 500

    @app.route('/api/tournament/<int:tour_id>/progress', methods=['POST'])
    def api_progress_tournament(tour_id):
        tour = Tournament.query.get_or_404(tour_id)
        try:
            result = progress_tournament(tour)
            db.session.commit()
            return jsonify(result)
        except Exception as e:
            db.session.rollback()
            return jsonify({'error': str(e)}), 500

    @app.route('/api/parser/test', methods=['POST'])
    def api_parse_shorthand():
        from engine.parser import parse_match_block
        data = request.get_json()
        text = data.get('text', '')
        result = parse_match_block(text)
        return jsonify({'result': result})

    @app.route('/tournament/<int:tour_id>')
    def view_tournament(tour_id):
        tour = Tournament.query.get_or_404(tour_id)

        swiss_data = None
        if tour.type in ('major', 'master'):
            swiss_data = get_swiss_data(tour)

        matches = Match.query.filter_by(tournament_id=tour_id).order_by(Match.match_order).all()
        resolved_matches = [resolve_match_display(m) for m in matches]
        playoff_rounds = group_playoff_rounds(tour)

        groups_data = None
        if tour.type == 'champion':
            groups_data = get_groups_data(tour)

        final_standings = get_final_standings(tour) if tour.status == 'finished' else None

        # Sort participants: with rank first (by rank asc), then without rank (by seed asc)
        participants = sorted(
            tour.participants,
            key=lambda p: (
                p.final_rank if p.final_rank is not None else 999,
                p.seed if p.seed is not None else 999,
            ),
        )

        return render_template(
            'tournament.html',
            tour=tour, cfg=Config,
            swiss_data=swiss_data,
            playoff_rounds=playoff_rounds,
            resolved_matches=resolved_matches,
            sorted_participants=participants,
            groups_data=groups_data,
            final_standings=final_standings,
        )
