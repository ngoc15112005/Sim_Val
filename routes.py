"""Flask routes for VALORANT Tournament Simulator."""

import json
from flask import request, jsonify, render_template, Response, redirect, url_for
from models import (
    db, Club, Region, Tournament, TournamentParticipant, Match, MatchMap,
    Campaign, CampaignClubState, CampaignStage, CampaignSeason
)
from engine.tournament import (
    create_tournament, generate_bracket, progress_tournament, simulate_all_pending,
    simulate_round,
)
from engine.match import simulate_match, resolve_manual_match
from engine.rating import update_ratings
from services.bracket_service import (
    get_swiss_standings, group_playoff_rounds, resolve_match_display,
    get_groups_data, get_swiss_data, get_final_standings,
)
from services.export_import_service import (
    export_tournament_dict, export_all_tournaments_dict,
    import_payload, delete_tournament_cascade,
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

    @app.route('/api/tournament/<int:tour_id>/sim-round', methods=['POST'])
    def api_sim_round(tour_id):
        tour = Tournament.query.get_or_404(tour_id)
        data = request.get_json() or {}
        round_name = data.get('round_name')
        group_label = data.get('group')
        stage = data.get('stage')
        match_ids = data.get('match_ids')

        try:
            res = simulate_round(
                tour,
                round_name=round_name,
                group_label=group_label,
                stage=stage,
                match_ids=match_ids,
            )
            db.session.commit()
            return jsonify(res)
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

    # ==================== EXPORT & IMPORT & DELETE ROUTES ====================

    @app.route('/api/tournament/<int:tour_id>/export', methods=['GET'])
    def api_export_tournament(tour_id):
        tour = Tournament.query.get_or_404(tour_id)
        data = export_tournament_dict(tour)
        json_str = json.dumps(data, indent=2, ensure_ascii=False)
        safe_name = "".join(c for c in tour.name if c.isalnum() or c in (' ', '_', '-')).strip().replace(' ', '_')
        filename = f"tournament_{tour_id}_{safe_name or 'val'}.json"
        return Response(
            json_str,
            mimetype='application/json',
            headers={'Content-Disposition': f'attachment; filename="{filename}"'}
        )

    @app.route('/api/tournaments/export', methods=['GET'])
    def api_export_all_tournaments():
        data = export_all_tournaments_dict()
        json_str = json.dumps(data, indent=2, ensure_ascii=False)
        filename = "tournaments_backup.json"
        return Response(
            json_str,
            mimetype='application/json',
            headers={'Content-Disposition': f'attachment; filename="{filename}"'}
        )

    @app.route('/api/tournaments/import', methods=['POST'])
    def api_import_tournaments():
        try:
            if 'file' in request.files:
                file = request.files['file']
                if not file.filename:
                    return jsonify({'error': 'Chưa chọn file'}), 400
                content = file.read().decode('utf-8')
                payload = json.loads(content)
            else:
                payload = request.get_json()
                if not payload:
                    return jsonify({'error': 'Không có dữ liệu'}), 400

            imported = import_payload(payload)
            return jsonify({
                'success': True,
                'count': len(imported),
                'tournaments': [t.to_dict() for t in imported],
            })
        except Exception as e:
            db.session.rollback()
            return jsonify({'error': str(e)}), 400

    @app.route('/api/tournament/<int:tour_id>/delete', methods=['POST', 'DELETE'])
    def api_delete_tournament(tour_id):
        try:
            success = delete_tournament_cascade(tour_id)
            if not success:
                return jsonify({'error': 'Không tìm thấy giải đấu'}), 404
            return jsonify({'success': True, 'id': tour_id})
        except Exception as e:
            db.session.rollback()
            return jsonify({'error': str(e)}), 500

    # ==================== VIEW ROUTES ====================

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
        if tour.type in ('champion', 'ewc'):
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

    # ─────────────────────────────────────────────────────────────────────────
    # Campaign / Story Mode (Chế độ Cốt truyện)
    # ─────────────────────────────────────────────────────────────────────────

    from services.campaign_service import (
        create_campaign, get_campaign, list_campaigns,
        get_campaign_club_states, update_club_form, bulk_update_form,
        run_open_qualifier_stage, get_open_qualifier_data,
        resolve_oq_match, sim_oq_round, sim_oq_region,
        get_championship_leaderboard, get_champions_paris_qualifiers,
        get_kickoff_data, run_kickoff_stage, override_kickoff_match,
        resolve_ko_match, sim_ko_round, sim_ko_region,
        get_major_data, run_major_stage, override_major_match,
        resolve_major_match_interactive, sim_major_round_interactive, sim_major_tournament_interactive,
        get_stage1_data, resolve_stage1_match_interactive, sim_stage1_round_interactive,
        sim_stage1_region_interactive, sim_stage1_all_interactive,
    )

    @app.route('/campaigns')
    def campaigns_list():
        campaigns = list_campaigns()
        return render_template('campaign/list.html', campaigns=campaigns, cfg=Config)

    @app.route('/campaigns/create', methods=['POST'])
    def campaign_create():
        name = request.form.get('name', 'VCT 2027 Circuit Journey').strip()
        year = int(request.form.get('year', 2027))
        campaign = create_campaign(name=name, start_year=year)
        return redirect(url_for('campaign_detail', campaign_id=campaign.id))

    @app.route('/campaign/<int:campaign_id>/delete', methods=['POST'])
    def campaign_delete(campaign_id):
        campaign = get_campaign(campaign_id)
        if campaign:
            db.session.delete(campaign)
            db.session.commit()
        return redirect(url_for('campaigns_list'))

    @app.route('/campaign/<int:campaign_id>')
    def campaign_detail(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return "Campaign not found", 404

        club_states = get_campaign_club_states(campaign_id)
        oq_data = get_open_qualifier_data(campaign_id)
        kickoff_data = get_kickoff_data(campaign_id)
        major_data = get_major_data(campaign_id)
        stage1_data = get_stage1_data(campaign_id)

        stages_info = []
        current_found = False
        for s in Config.CIRCUIT_STAGES:
            is_past = not current_found and s['key'] != campaign.current_stage
            if s['key'] == campaign.current_stage:
                current_found = True
            stages_info.append({
                'key': s['key'],
                'name': s['name'],
                'desc': s['desc'],
                'is_past': is_past,
            })

        cp_leaderboards = {
            r: get_championship_leaderboard(campaign_id, region_slug=r)
            for r in ['pacific', 'americas', 'emea', 'china']
        }

        return render_template(
            'campaign/detail.html',
            campaign=campaign,
            club_states=club_states,
            stages_info=stages_info,
            oq_data=oq_data,
            kickoff_data=kickoff_data,
            major_data=major_data,
            stage1_data=stage1_data,
            cp_leaderboards=cp_leaderboards,
            cfg=Config,
        )

    @app.route('/api/campaign/<int:campaign_id>/points/leaderboard')
    def api_campaign_cp_leaderboard(campaign_id):
        region_slug = request.args.get('region')
        if region_slug:
            lb = get_championship_leaderboard(campaign_id, region_slug=region_slug)
            return jsonify({'region': region_slug, 'leaderboard': lb})
        all_lbs = {
            r: get_championship_leaderboard(campaign_id, region_slug=r)
            for r in ['pacific', 'americas', 'emea', 'china']
        }
        return jsonify(all_lbs)


    @app.route('/campaign/<int:campaign_id>/stage/open_qualifier')
    def campaign_open_qualifier_view(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return "Campaign not found", 404

        oq_data = get_open_qualifier_data(campaign_id)
        selected_region = request.args.get('region', 'pacific')

        return render_template(
            'campaign/open_qualifier.html',
            campaign=campaign,
            oq_data=oq_data,
            selected_region=selected_region,
            cfg=Config,
        )

    @app.route('/api/campaign/<int:campaign_id>/open_qualifier/sim', methods=['POST'])
    def api_campaign_open_qualifier_sim(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404

        data = request.get_json() or {}
        region_slug = data.get('region_slug')
        if region_slug == '':
            region_slug = None

        try:
            results = run_open_qualifier_stage(campaign_id, region_slug=region_slug)
            return jsonify({'success': True, 'results': results})
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    @app.route('/api/campaign/<int:campaign_id>/open_qualifier/match/sim', methods=['POST'])
    def api_campaign_oq_match_sim(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404

        data = request.get_json() or {}
        region_slug = data.get('region_slug')
        match_id = data.get('match_id')

        if not region_slug or not match_id:
            return jsonify({'error': 'region_slug and match_id are required'}), 400

        try:
            res = resolve_oq_match(campaign_id, region_slug, match_id, winner_id=None)
            return jsonify({'success': True, 'result': res})
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    @app.route('/api/campaign/<int:campaign_id>/open_qualifier/match/manual', methods=['POST'])
    def api_campaign_oq_match_manual(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404

        data = request.get_json() or {}
        region_slug = data.get('region_slug')
        match_id = data.get('match_id')
        winner_id = data.get('winner_id')
        maps = data.get('maps')

        if not region_slug or not match_id or not winner_id:
            return jsonify({'error': 'region_slug, match_id, and winner_id are required'}), 400

        try:
            res = resolve_oq_match(campaign_id, region_slug, match_id, winner_id=int(winner_id), maps=maps)
            return jsonify({'success': True, 'result': res})
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    @app.route('/api/campaign/<int:campaign_id>/open_qualifier/sim-round', methods=['POST'])
    def api_campaign_oq_sim_round(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404

        data = request.get_json() or {}
        region_slug = data.get('region_slug')
        if not region_slug:
            return jsonify({'error': 'region_slug is required'}), 400

        try:
            res = sim_oq_round(campaign_id, region_slug)
            return jsonify({'success': True, 'result': res})
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    @app.route('/api/campaign/<int:campaign_id>/open_qualifier/sim-region', methods=['POST'])
    def api_campaign_oq_sim_region(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404

        data = request.get_json() or {}
        region_slug = data.get('region_slug')
        if not region_slug:
            return jsonify({'error': 'region_slug is required'}), 400

        try:
            res = sim_oq_region(campaign_id, region_slug)
            return jsonify({'success': True, 'result': res})
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    @app.route('/api/campaign/<int:campaign_id>/form/update', methods=['POST'])
    def api_campaign_form_update(campaign_id):
        data = request.get_json() or {}
        club_id = data.get('club_id')
        form_modifier = data.get('form_modifier', 0)

        if not club_id:
            return jsonify({'error': 'club_id is required'}), 400

        success = update_club_form(campaign_id, club_id, form_modifier)
        return jsonify({'success': success})

    @app.route('/campaign/<int:campaign_id>/stage/kickoff')
    def campaign_kickoff_view(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return "Campaign not found", 404

        kickoff_data = get_kickoff_data(campaign_id)
        selected_region = request.args.get('region', 'pacific')

        return render_template(
            'campaign/kickoff.html',
            campaign=campaign,
            kickoff_data=kickoff_data,
            selected_region=selected_region,
            cfg=Config,
        )

    @app.route('/api/campaign/<int:campaign_id>/kickoff/match/sim', methods=['POST'])
    def api_campaign_ko_match_sim(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404

        data = request.get_json() or {}
        region_slug = data.get('region_slug')
        match_id = data.get('match_id')

        if not region_slug or not match_id:
            return jsonify({'error': 'region_slug and match_id are required'}), 400

        try:
            res = resolve_ko_match(campaign_id, region_slug, match_id, winner_id=None)
            return jsonify({'success': True, 'result': res})
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    @app.route('/api/campaign/<int:campaign_id>/kickoff/match/manual', methods=['POST'])
    def api_campaign_ko_match_manual(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404

        data = request.get_json() or {}
        region_slug = data.get('region_slug')
        match_id = data.get('match_id')
        winner_id = data.get('winner_id')
        maps = data.get('maps')

        if not region_slug or not match_id or not winner_id:
            return jsonify({'error': 'region_slug, match_id, and winner_id are required'}), 400

        try:
            res = resolve_ko_match(campaign_id, region_slug, match_id, winner_id=int(winner_id), maps=maps)
            return jsonify({'success': True, 'result': res})
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    @app.route('/api/campaign/<int:campaign_id>/kickoff/sim-round', methods=['POST'])
    def api_campaign_ko_sim_round(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404

        data = request.get_json() or {}
        region_slug = data.get('region_slug')
        if not region_slug:
            return jsonify({'error': 'region_slug is required'}), 400

        try:
            res = sim_ko_round(campaign_id, region_slug)
            return jsonify({'success': True, 'result': res})
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    @app.route('/api/campaign/<int:campaign_id>/kickoff/sim-region', methods=['POST'])
    def api_campaign_ko_sim_region(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404

        data = request.get_json() or {}
        region_slug = data.get('region_slug')
        if not region_slug:
            return jsonify({'error': 'region_slug is required'}), 400

        try:
            res = sim_ko_region(campaign_id, region_slug)
            return jsonify({'success': True, 'result': res})
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    @app.route('/api/campaign/<int:campaign_id>/kickoff/sim', methods=['POST'])
    def api_campaign_kickoff_sim(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404

        data = request.get_json() or {}
        region_slug = data.get('region_slug')
        if region_slug == '':
            region_slug = None

        try:
            results = run_kickoff_stage(campaign_id, region_slug=region_slug)
            return jsonify({'success': True, 'results': results})
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    @app.route('/api/campaign/<int:campaign_id>/kickoff/match/override', methods=['POST'])
    def api_campaign_kickoff_match_override(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404

        data = request.get_json() or {}
        region_slug = data.get('region_slug')
        round_name = data.get('round_name')
        winner_id = data.get('winner_id')
        maps = data.get('maps')

        if not region_slug or not round_name or not winner_id:
            return jsonify({'error': 'region_slug, round_name, and winner_id are required'}), 400

        try:
            results = override_kickoff_match(campaign_id, region_slug, round_name, int(winner_id), maps)
            return jsonify({'success': True, 'results': results})
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    @app.route('/campaign/<int:campaign_id>/stage/major')
    def campaign_major_view(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return "Campaign not found", 404

        major_data = get_major_data(campaign_id)
        cp_leaderboards = {
            r: get_championship_leaderboard(campaign_id, region_slug=r)
            for r in ['pacific', 'americas', 'emea', 'china']
        }

        return render_template(
            'campaign/major.html',
            campaign=campaign,
            major_data=major_data,
            cp_leaderboards=cp_leaderboards,
            cfg=Config,
        )

    @app.route('/api/campaign/<int:campaign_id>/major/match/sim', methods=['POST'])
    def api_campaign_major_match_sim(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404

        data = request.get_json() or {}
        match_id = data.get('match_id')
        if not match_id:
            return jsonify({'error': 'match_id is required'}), 400

        try:
            res = resolve_major_match_interactive(campaign_id, match_id, winner_id=None)
            return jsonify({'success': True, 'result': res})
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    @app.route('/api/campaign/<int:campaign_id>/major/match/manual', methods=['POST'])
    def api_campaign_major_match_manual(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404

        data = request.get_json() or {}
        match_id = data.get('match_id')
        winner_id = data.get('winner_id')
        maps = data.get('maps')

        if not match_id or not winner_id:
            return jsonify({'error': 'match_id and winner_id are required'}), 400

        try:
            res = resolve_major_match_interactive(campaign_id, match_id, winner_id=int(winner_id), maps=maps)
            return jsonify({'success': True, 'result': res})
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    @app.route('/api/campaign/<int:campaign_id>/major/sim-round', methods=['POST'])
    def api_campaign_major_sim_round(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404

        try:
            res = sim_major_round_interactive(campaign_id)
            return jsonify({'success': True, 'result': res})
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    @app.route('/api/campaign/<int:campaign_id>/major/sim', methods=['POST'])
    def api_campaign_major_sim(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404

        try:
            results = run_major_stage(campaign_id)
            return jsonify({'success': True, 'results': results})
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    @app.route('/api/campaign/<int:campaign_id>/major/match/override', methods=['POST'])
    def api_campaign_major_match_override(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404

        data = request.get_json() or {}
        round_name = data.get('round_name')
        winner_id = data.get('winner_id')
        maps = data.get('maps')

        if not round_name or not winner_id:
            return jsonify({'error': 'round_name and winner_id are required'}), 400

        try:
            results = override_major_match(campaign_id, round_name, int(winner_id), maps)
            return jsonify({'success': True, 'results': results})
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    @app.route('/campaign/<int:campaign_id>/stage/stage1')
    def campaign_stage1_view(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return "Campaign not found", 404

        active_region = request.args.get('region', 'pacific').lower()
        if active_region not in ['pacific', 'americas', 'emea', 'china']:
            active_region = 'pacific'

        stage1_data = get_stage1_data(campaign_id)
        cp_leaderboards = {
            r: get_championship_leaderboard(campaign_id, region_slug=r)
            for r in ['pacific', 'americas', 'emea', 'china']
        }

        return render_template(
            'campaign/stage1.html',
            campaign=campaign,
            active_region=active_region,
            stage1_data=stage1_data,
            cp_leaderboards=cp_leaderboards,
            cfg=Config,
        )

    @app.route('/api/campaign/<int:campaign_id>/stage1/match/sim', methods=['POST'])
    def api_campaign_stage1_match_sim(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404

        data = request.get_json() or {}
        region_slug = data.get('region')
        match_id = data.get('match_id')
        if not region_slug or not match_id:
            return jsonify({'error': 'region and match_id are required'}), 400

        try:
            res = resolve_stage1_match_interactive(campaign_id, region_slug, match_id, winner_id=None)
            return jsonify({'success': True, 'result': res})
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    @app.route('/api/campaign/<int:campaign_id>/stage1/match/manual', methods=['POST'])
    def api_campaign_stage1_match_manual(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404

        data = request.get_json() or {}
        region_slug = data.get('region')
        match_id = data.get('match_id')
        winner_id = data.get('winner_id')
        maps = data.get('maps')

        if not region_slug or not match_id or not winner_id:
            return jsonify({'error': 'region, match_id and winner_id are required'}), 400

        try:
            res = resolve_stage1_match_interactive(
                campaign_id, region_slug, match_id,
                winner_id=int(winner_id), maps=maps
            )
            return jsonify({'success': True, 'result': res})
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    @app.route('/api/campaign/<int:campaign_id>/stage1/sim-round', methods=['POST'])
    def api_campaign_stage1_sim_round(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404

        data = request.get_json() or {}
        region_slug = data.get('region')
        if not region_slug:
            return jsonify({'error': 'region is required'}), 400

        try:
            res = sim_stage1_round_interactive(campaign_id, region_slug)
            return jsonify({'success': True, 'result': res})
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    @app.route('/api/campaign/<int:campaign_id>/stage1/sim-region', methods=['POST'])
    def api_campaign_stage1_sim_region(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404

        data = request.get_json() or {}
        region_slug = data.get('region')
        if not region_slug:
            return jsonify({'error': 'region is required'}), 400

        try:
            res = sim_stage1_region_interactive(campaign_id, region_slug)
            return jsonify({'success': True, 'result': res})
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    @app.route('/api/campaign/<int:campaign_id>/stage1/sim-all', methods=['POST'])
    def api_campaign_stage1_sim_all(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404

        try:
            res = sim_stage1_all_interactive(campaign_id)
            return jsonify({'success': True, 'result': res})
        except Exception as e:
            return jsonify({'error': str(e)}), 400



