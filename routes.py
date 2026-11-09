"""Flask routes for VALORANT Tournament Simulator."""

import json
from datetime import datetime, timezone
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

    @app.context_processor
    def inject_global_data():
        try:
            return {'clubs_by_id': {c.id: c for c in Club.query.all()}}
        except Exception:
            return {'clubs_by_id': {}}

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
        data = request.get_json(silent=True)
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
        if not match.team_a_id or not match.team_b_id:
            return jsonify({'error': 'Chưa có đủ 2 đội'}), 400

        # Cho phép roll lại (re-roll) trận đã đấu nếu giải chưa kết thúc
        if match.status == 'completed':
            tour = Tournament.query.get(tour_id)
            if tour and tour.status == 'completed':
                return jsonify({'error': 'Giải đấu đã kết thúc, không thể roll lại'}), 400
            MatchMap.query.filter_by(match_id=match.id).delete()
            match.team_a_score = None
            match.team_b_score = None
            match.winner_id = None
            match.status = 'pending'
            db.session.flush()

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

        data = request.get_json(silent=True)
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
        data = request.get_json(silent=True) or {}
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
        data = request.get_json(silent=True)
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
        try:
            import os
            save_dir = os.path.join(os.getcwd(), 'saves', 'single')
            os.makedirs(save_dir, exist_ok=True)
            with open(os.path.join(save_dir, filename), 'w', encoding='utf-8') as f:
                f.write(json_str)
        except Exception:
            pass
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
                payload = request.get_json(silent=True)
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
        create_campaign, get_campaign, list_campaigns, get_stage_record,
        get_campaign_club_states, update_club_form, bulk_update_form, bulk_update_campaign_clubs,
        run_open_qualifier_stage, get_open_qualifier_data,
        resolve_oq_match, sim_oq_round, sim_oq_region,
        get_championship_leaderboard, get_champions_paris_qualifiers,
        get_kickoff_data, run_kickoff_stage, override_kickoff_match,
        resolve_ko_match, sim_ko_round, sim_ko_region,
        get_major_data, run_major_stage, override_major_match,
        resolve_major_match_interactive, sim_major_round_interactive, sim_major_tournament_interactive,
        get_stage1_data, resolve_stage1_match_interactive, sim_stage1_round_interactive,
        sim_stage1_region_interactive, sim_stage1_all_interactive,
        get_oq_stage1_data, resolve_oq_stage1_match, sim_oq_stage1_round,
        sim_oq_stage1_region, sim_oq_stage1_all,
        get_ewc_qualifier_data, resolve_ewc_qualifier_match_interactive,
        sim_ewc_qualifier_round_interactive, sim_ewc_qualifier_region_interactive,
        sim_ewc_qualifier_all_interactive,
        get_master_data, resolve_master_match_interactive,
        sim_master_round_interactive, sim_master_tournament_interactive,
        run_master_stage,
        get_ewc_data, resolve_ewc_match_interactive,
        sim_ewc_round_interactive, sim_ewc_tournament_interactive,
        run_ewc_stage,
        get_oq_stage2_data, resolve_oq_stage2_match, sim_oq_stage2_round,
        sim_oq_stage2_region, sim_oq_stage2_all,
        get_stage2_data, resolve_stage2_match_interactive, sim_stage2_round_interactive,
        sim_stage2_region_interactive, sim_stage2_all_interactive,
        get_champion_data, resolve_champion_match_interactive,
        sim_champion_round_interactive, sim_champion_tournament_interactive,
        run_champion_stage, get_season_summary_data, advance_campaign_to_next_year,
        get_stage_placements_history, get_all_time_trophy_table, get_global_power_rankings,
        recalculate_campaign_gpr,
        get_team_profile_data,
        confirm_stage_region, confirm_stage_tournament, confirm_stage_all,
        unlock_stage_region, unlock_stage_tournament,
        get_season_hosts,
    )
    from services.campaign_export_service import (
        export_campaign_save,
        import_campaign_save,
    )
    from services.storyline_engine import (
        get_scenario_catalog,
        generate_season_storylines_draft,
        commit_season_storylines,
        get_active_campaign_storylines,
        delete_campaign_storyline,
    )
    from services.partnership_service import (
        get_partnership_cycle_status,
        generate_partnership_evaluation,
        commit_partnership_selection,
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
        try:
            import os
            data = export_campaign_save(campaign.id)
            safe_name = "".join(c for c in campaign.name if c.isalnum() or c in (' ', '_', '-')).strip().replace(' ', '_')
            filename = f"vct_save_{safe_name}_{campaign.current_year}.json"
            save_dir = os.path.join(os.getcwd(), 'saves', 'campaign')
            os.makedirs(save_dir, exist_ok=True)
            with open(os.path.join(save_dir, filename), 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception:
            pass
        return redirect(url_for('campaign_detail', campaign_id=campaign.id, reveal='1'))

    @app.route('/campaign/<int:campaign_id>/delete', methods=['POST'])
    def campaign_delete(campaign_id):
        campaign = get_campaign(campaign_id)
        if campaign:
            try:
                import os
                safe_name = "".join(c for c in campaign.name if c.isalnum() or c in (' ', '_', '-')).strip().replace(' ', '_')
                filename = f"vct_save_{safe_name}_{campaign.current_year}.json"
                filepath = os.path.join(os.getcwd(), 'saves', 'campaign', filename)
                if os.path.exists(filepath):
                    os.remove(filepath)
            except Exception:
                pass
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
        oq_stage1_data = get_oq_stage1_data(campaign_id)
        stage1_data = get_stage1_data(campaign_id)
        ewc_qual_data = get_ewc_qualifier_data(campaign_id)
        master_data = get_master_data(campaign_id)
        ewc_data = get_ewc_data(campaign_id)
        oq_stage2_data = get_oq_stage2_data(campaign_id)
        stage2_data = get_stage2_data(campaign_id)
        champion_data = get_champion_data(campaign_id)

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
        season_hosts = get_season_hosts(campaign.id, campaign.current_year)
        show_season_reveal = bool(request.args.get('reveal') == '1')

        active_storylines = get_active_campaign_storylines(campaign_id, campaign.current_year)
        club_storylines = {}
        for st in active_storylines:
            if st.get('club_id'):
                club_storylines.setdefault(st['club_id'], []).append(st)

        partnership_cycle = get_partnership_cycle_status(campaign_id, campaign.current_year)

        return render_template(
            'campaign/detail.html',
            campaign=campaign,
            club_states=club_states,
            active_storylines=active_storylines,
            club_storylines=club_storylines,
            partnership_cycle=partnership_cycle,
            stages_info=stages_info,
            oq_data=oq_data,
            kickoff_data=kickoff_data,
            major_data=major_data,
            oq_stage1_data=oq_stage1_data,
            stage1_data=stage1_data,
            ewc_qual_data=ewc_qual_data,
            master_data=master_data,
            ewc_data=ewc_data,
            oq_stage2_data=oq_stage2_data,
            stage2_data=stage2_data,
            champion_data=champion_data,
            cp_leaderboards=cp_leaderboards,
            season_hosts=season_hosts,
            show_season_reveal=show_season_reveal,
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

        req_year = request.args.get('year', type=int) or campaign.current_year
        stage = get_stage_record(campaign_id, 'open_qualifier', year=req_year)
        oq_data = get_open_qualifier_data(campaign_id)
        selected_region = request.args.get('region', 'pacific')

        return render_template(
            'campaign/open_qualifier.html',
            campaign=campaign,
            stage=stage,
            req_year=req_year,
            oq_data=oq_data,
            selected_region=selected_region,
            active_region=selected_region,
            clubs_by_id={c.id: c for c in Club.query.all()},
            cfg=Config,
        )

    @app.route('/api/campaign/<int:campaign_id>/open_qualifier/sim', methods=['POST'])
    def api_campaign_open_qualifier_sim(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404

        data = request.get_json(silent=True) or {}
        region_slug = data.get('region_slug')
        if region_slug == '':
            region_slug = None

        try:
            auto_confirm = data.get('auto_confirm', True)
            results = run_open_qualifier_stage(campaign_id, region_slug=region_slug, auto_confirm=auto_confirm)
            return jsonify({'success': True, 'results': results})
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    @app.route('/api/campaign/<int:campaign_id>/open_qualifier/match/sim', methods=['POST'])
    def api_campaign_oq_match_sim(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404

        data = request.get_json(silent=True) or {}
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

        data = request.get_json(silent=True) or {}
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

        data = request.get_json(silent=True) or {}
        region_slug = data.get('region_slug')
        if not region_slug:
            return jsonify({'error': 'region_slug is required'}), 400

        try:
            auto_confirm = data.get('auto_confirm', True)
            res = sim_oq_round(campaign_id, region_slug, auto_confirm=auto_confirm)
            return jsonify({'success': True, 'result': res})
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    @app.route('/api/campaign/<int:campaign_id>/open_qualifier/sim-region', methods=['POST'])
    def api_campaign_oq_sim_region(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404

        data = request.get_json(silent=True) or {}
        region_slug = data.get('region_slug')
        if not region_slug:
            return jsonify({'error': 'region_slug is required'}), 400

        try:
            auto_confirm = data.get('auto_confirm', True)
            res = sim_oq_region(campaign_id, region_slug, auto_confirm=auto_confirm)
            return jsonify({'success': True, 'result': res})
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    @app.route('/api/campaign/<int:campaign_id>/form/update', methods=['POST'])
    def api_campaign_form_update(campaign_id):
        data = request.get_json(silent=True) or {}
        club_id = data.get('club_id')
        form_modifier = data.get('form_modifier', 0)

        if not club_id:
            return jsonify({'error': 'club_id is required'}), 400

        success = update_club_form(campaign_id, club_id, form_modifier)
        return jsonify({'success': success})

    @app.route('/api/campaign/<int:campaign_id>/clubs/bulk-update', methods=['POST'])
    def api_campaign_clubs_bulk_update(campaign_id):
        data = request.get_json(silent=True) or {}
        updates = data.get('updates', {})
        if not updates or not isinstance(updates, dict):
            return jsonify({'error': 'updates dictionary is required'}), 400

        try:
            count = bulk_update_campaign_clubs(campaign_id, updates)
            return jsonify({'success': True, 'updated_count': count})
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    @app.route('/api/campaign/<int:campaign_id>/clubs')
    def api_campaign_clubs_list(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404
        cstates = get_campaign_club_states(campaign_id)
        clubs_list = []
        for cs in cstates:
            c = cs.club
            clubs_list.append({
                'id': c.id,
                'name': c.name,
                'short_code': c.short_code,
                'region_id': c.region_id,
                'region_name': c.region.name if c.region else '',
                'region_slug': c.region.slug if c.region else '',
                'base_rating': c.base_rating,
                'story_rating': cs.story_rating,
                'form_modifier': cs.form_modifier,
            })
        return jsonify({'success': True, 'clubs': clubs_list})

    @app.route('/api/campaign/<int:campaign_id>/storylines/catalog')
    def api_campaign_storylines_catalog(campaign_id):
        return jsonify({'success': True, 'catalog': get_scenario_catalog()})

    @app.route('/api/campaign/<int:campaign_id>/storylines/draft')
    def api_campaign_storylines_draft(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404
        year = request.args.get('year', type=int) or campaign.current_year
        try:
            draft = generate_season_storylines_draft(campaign_id, target_year=year)
            return jsonify({'success': True, 'draft': draft, 'year': year})
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    @app.route('/api/campaign/<int:campaign_id>/storylines')
    def api_campaign_storylines_list(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404
        year = request.args.get('year', type=int) or campaign.current_year
        storylines = get_active_campaign_storylines(campaign_id, year=year)
        return jsonify({'success': True, 'storylines': storylines, 'year': year})

    @app.route('/api/campaign/<int:campaign_id>/storylines/commit', methods=['POST'])
    def api_campaign_storylines_commit(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404
        data = request.get_json(silent=True) or {}
        storylines = data.get('storylines', [])
        year = data.get('year') or campaign.current_year
        try:
            res = commit_season_storylines(campaign_id, storylines, year=year)
            return jsonify(res)
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    @app.route('/api/campaign/<int:campaign_id>/storylines/<int:storyline_id>', methods=['DELETE'])
    def api_campaign_storylines_delete(campaign_id, storyline_id):
        success = delete_campaign_storyline(storyline_id)
        return jsonify({'success': success})

    # ─────────────────────────────────────────────────────────────────────────
    # Partnership Evaluation & 2-Year Partner Restructuring APIs
    # ─────────────────────────────────────────────────────────────────────────

    @app.route('/api/campaign/<int:campaign_id>/partnership/status')
    def api_campaign_partnership_status(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404
        year = request.args.get('year', type=int) or campaign.current_year
        try:
            st = get_partnership_cycle_status(campaign_id, year=year)
            return jsonify({'success': True, 'status': st})
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    @app.route('/api/campaign/<int:campaign_id>/partnership/review')
    def api_campaign_partnership_review(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404
        year = request.args.get('year', type=int) or campaign.current_year
        force = request.args.get('force') in ('1', 'true', 'yes')
        try:
            review_data = generate_partnership_evaluation(campaign_id, year=year, force_recalculate=force)
            return jsonify({'success': True, 'review': review_data})
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    @app.route('/api/campaign/<int:campaign_id>/partnership/commit', methods=['POST'])
    def api_campaign_partnership_commit(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404
        data = request.get_json(silent=True) or {}
        selections = data.get('selections_by_region') or data.get('selections')
        year = data.get('year') or campaign.current_year
        try:
            res = commit_partnership_selection(campaign_id, selections, year=int(year))
            return jsonify(res)
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    @app.route('/campaign/<int:campaign_id>/stage/kickoff')
    def campaign_kickoff_view(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return "Campaign not found", 404

        req_year = request.args.get('year', type=int) or campaign.current_year
        kickoff_data = get_kickoff_data(campaign_id, year=req_year)
        selected_region = request.args.get('region', 'pacific')
        stage = get_stage_record(campaign_id, 'kickoff', year=req_year)
        season_hosts = get_season_hosts(campaign.id, req_year)

        return render_template(
            'campaign/kickoff.html',
            campaign=campaign,
            stage=stage,
            req_year=req_year,
            kickoff_data=kickoff_data,
            selected_region=selected_region,
            active_region=selected_region,
            clubs_by_id={c.id: c for c in Club.query.all()},
            season_hosts=season_hosts,
            cfg=Config,
        )

    @app.route('/api/campaign/<int:campaign_id>/kickoff/match/sim', methods=['POST'])
    def api_campaign_ko_match_sim(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404

        data = request.get_json(silent=True) or {}
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

        data = request.get_json(silent=True) or {}
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

        data = request.get_json(silent=True) or {}
        region_slug = data.get('region_slug')
        if not region_slug:
            return jsonify({'error': 'region_slug is required'}), 400

        try:
            auto_confirm = data.get('auto_confirm', True)
            res = sim_ko_round(campaign_id, region_slug, auto_confirm=auto_confirm)
            return jsonify({'success': True, 'result': res})
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    @app.route('/api/campaign/<int:campaign_id>/kickoff/sim-region', methods=['POST'])
    def api_campaign_ko_sim_region(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404

        data = request.get_json(silent=True) or {}
        region_slug = data.get('region_slug')
        if not region_slug:
            return jsonify({'error': 'region_slug is required'}), 400

        try:
            auto_confirm = data.get('auto_confirm', True)
            res = sim_ko_region(campaign_id, region_slug, auto_confirm=auto_confirm)
            return jsonify({'success': True, 'result': res})
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    @app.route('/api/campaign/<int:campaign_id>/kickoff/sim', methods=['POST'])
    def api_campaign_kickoff_sim(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404

        data = request.get_json(silent=True) or {}
        region_slug = data.get('region_slug')
        if region_slug == '':
            region_slug = None

        try:
            auto_confirm = data.get('auto_confirm', True)
            results = run_kickoff_stage(campaign_id, region_slug=region_slug, auto_confirm=auto_confirm)
            return jsonify({'success': True, 'results': results})
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    @app.route('/api/campaign/<int:campaign_id>/kickoff/match/override', methods=['POST'])
    def api_campaign_kickoff_match_override(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404

        data = request.get_json(silent=True) or {}
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

        req_year = request.args.get('year', type=int) or campaign.current_year
        stage = get_stage_record(campaign_id, 'major', year=req_year)
        major_data = get_major_data(campaign_id, year=req_year)
        cp_leaderboards = {
            r: get_championship_leaderboard(campaign_id, region_slug=r)
            for r in ['pacific', 'americas', 'emea', 'china']
        }
        season_hosts = get_season_hosts(campaign.id, req_year)

        return render_template(
            'campaign/major.html',
            campaign=campaign,
            stage=stage,
            req_year=req_year,
            major_data=major_data,
            cp_leaderboards=cp_leaderboards,
            season_hosts=season_hosts,
            cfg=Config,
        )

    @app.route('/api/campaign/<int:campaign_id>/major/match/sim', methods=['POST'])
    def api_campaign_major_match_sim(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404

        data = request.get_json(silent=True) or {}
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

        data = request.get_json(silent=True) or {}
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

        data = request.get_json(silent=True) or {}
        try:
            auto_confirm = data.get('auto_confirm', True)
            res = sim_major_round_interactive(campaign_id, auto_confirm=auto_confirm)
            return jsonify({'success': True, 'result': res})
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    @app.route('/api/campaign/<int:campaign_id>/major/sim', methods=['POST'])
    def api_campaign_major_sim(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404

        data = request.get_json(silent=True) or {}
        try:
            auto_confirm = data.get('auto_confirm', True)
            results = run_major_stage(campaign_id, auto_confirm=auto_confirm)
            return jsonify({'success': True, 'results': results})
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    @app.route('/api/campaign/<int:campaign_id>/major/match/override', methods=['POST'])
    def api_campaign_major_match_override(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404

        data = request.get_json(silent=True) or {}
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

        req_year = request.args.get('year', type=int) or campaign.current_year
        stage = get_stage_record(campaign_id, 'stage1', year=req_year)
        stage1_data = get_stage1_data(campaign_id, year=req_year)
        cp_leaderboards = {
            r: get_championship_leaderboard(campaign_id, region_slug=r)
            for r in ['pacific', 'americas', 'emea', 'china']
        }
        season_hosts = get_season_hosts(campaign.id, req_year)

        return render_template(
            'campaign/stage1.html',
            campaign=campaign,
            stage=stage,
            req_year=req_year,
            active_region=active_region,
            stage1_data=stage1_data,
            cp_leaderboards=cp_leaderboards,
            season_hosts=season_hosts,
            cfg=Config,
        )

    @app.route('/api/campaign/<int:campaign_id>/stage1/match/sim', methods=['POST'])
    def api_campaign_stage1_match_sim(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404

        data = request.get_json(silent=True) or {}
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

        data = request.get_json(silent=True) or {}
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

        data = request.get_json(silent=True) or {}
        region_slug = data.get('region')
        if not region_slug:
            return jsonify({'error': 'region is required'}), 400

        try:
            auto_confirm = data.get('auto_confirm', True)
            res = sim_stage1_round_interactive(campaign_id, region_slug, auto_confirm=auto_confirm)
            return jsonify({'success': True, 'result': res})
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    @app.route('/api/campaign/<int:campaign_id>/stage1/sim-region', methods=['POST'])
    def api_campaign_stage1_sim_region(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404

        data = request.get_json(silent=True) or {}
        region_slug = data.get('region')
        if not region_slug:
            return jsonify({'error': 'region is required'}), 400

        try:
            auto_confirm = data.get('auto_confirm', True)
            res = sim_stage1_region_interactive(campaign_id, region_slug, auto_confirm=auto_confirm)
            return jsonify({'success': True, 'result': res})
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    @app.route('/api/campaign/<int:campaign_id>/stage1/sim-all', methods=['POST'])
    def api_campaign_stage1_sim_all(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404

        data = request.get_json(silent=True) or {}
        try:
            auto_confirm = data.get('auto_confirm', True)
            res = sim_stage1_all_interactive(campaign_id, auto_confirm=auto_confirm)
            return jsonify({'success': True, 'result': res})
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    @app.route('/campaign/<int:campaign_id>/stage/oq_stage1')
    def campaign_oq_stage1_view(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return "Campaign not found", 404

        active_region = request.args.get('region', 'pacific').lower()
        if active_region not in ['pacific', 'americas', 'emea', 'china']:
            active_region = 'pacific'

        req_year = request.args.get('year', type=int) or campaign.current_year
        stage = get_stage_record(campaign_id, 'oq_stage1', year=req_year)
        oq_data = get_oq_stage1_data(campaign_id)
        return render_template(
            'campaign/oq_stage1.html',
            campaign=campaign,
            stage=stage,
            req_year=req_year,
            active_region=active_region,
            selected_region=active_region,
            oq_data=oq_data,
            clubs_by_id={c.id: c for c in Club.query.all()},
            cfg=Config,
        )

    @app.route('/api/campaign/<int:campaign_id>/oq_stage1/match/sim', methods=['POST'])
    def api_campaign_oq_stage1_match_sim(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404

        data = request.get_json(silent=True) or {}
        region_slug = data.get('region_slug') or data.get('region')
        match_id = data.get('match_id')

        if not region_slug or not match_id:
            return jsonify({'error': 'region and match_id are required'}), 400

        try:
            res = resolve_oq_stage1_match(campaign_id, region_slug, match_id, winner_id=None)
            return jsonify({'success': True, 'result': res})
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    @app.route('/api/campaign/<int:campaign_id>/oq_stage1/match/manual', methods=['POST'])
    def api_campaign_oq_stage1_match_manual(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404

        data = request.get_json(silent=True) or {}
        region_slug = data.get('region_slug') or data.get('region')
        match_id = data.get('match_id')
        winner_id = data.get('winner_id')
        maps = data.get('maps')

        if not region_slug or not match_id or not winner_id:
            return jsonify({'error': 'region, match_id and winner_id are required'}), 400

        try:
            res = resolve_oq_stage1_match(campaign_id, region_slug, match_id, winner_id=int(winner_id), maps=maps)
            return jsonify({'success': True, 'result': res})
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    @app.route('/api/campaign/<int:campaign_id>/oq_stage1/sim-round', methods=['POST'])
    def api_campaign_oq_stage1_sim_round(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404

        data = request.get_json(silent=True) or {}
        region_slug = data.get('region_slug') or data.get('region')
        if not region_slug:
            return jsonify({'error': 'region is required'}), 400

        try:
            auto_confirm = data.get('auto_confirm', True)
            res = sim_oq_stage1_round(campaign_id, region_slug, auto_confirm=auto_confirm)
            return jsonify({'success': True, 'result': res})
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    @app.route('/api/campaign/<int:campaign_id>/oq_stage1/sim-region', methods=['POST'])
    def api_campaign_oq_stage1_sim_region(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404

        data = request.get_json(silent=True) or {}
        region_slug = data.get('region_slug') or data.get('region')
        if not region_slug:
            return jsonify({'error': 'region is required'}), 400

        try:
            auto_confirm = data.get('auto_confirm', True)
            res = sim_oq_stage1_region(campaign_id, region_slug, auto_confirm=auto_confirm)
            return jsonify({'success': True, 'result': res})
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    @app.route('/api/campaign/<int:campaign_id>/oq_stage1/sim-all', methods=['POST'])
    def api_campaign_oq_stage1_sim_all(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404

        data = request.get_json(silent=True) or {}
        try:
            auto_confirm = data.get('auto_confirm', True)
            res = sim_oq_stage1_all(campaign_id, auto_confirm=auto_confirm)
            return jsonify({'success': True, 'result': res})
        except Exception as e:
            return jsonify({'error': str(e)}), 400
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    # ─────────────────────────────────────────────────────────────────────────
    # Campaign Stage: EWC Regional Qualifier (Interactive View & APIs)
    # ─────────────────────────────────────────────────────────────────────────

    @app.route('/campaign/<int:campaign_id>/stage/ewc_qualifier')
    def campaign_ewc_qualifier_view(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return "Campaign not found", 404

        all_regions = ['pacific', 'americas', 'emea', 'china']
        region_slug = request.args.get('region', 'pacific')
        if region_slug not in all_regions:
            region_slug = 'pacific'

        req_year = request.args.get('year', type=int) or campaign.current_year
        stage = get_stage_record(campaign_id, 'ewc_qualifier', year=req_year)
        eq_data = get_ewc_qualifier_data(campaign_id, year=req_year)
        reg_data = eq_data.get('regions', {}).get(region_slug, {})
        direct_qualifiers = eq_data.get('direct_ewc_qualifiers', {}).get(region_slug, [])

        return render_template(
            'campaign/ewc_qualifier.html',
            campaign=campaign,
            stage=stage,
            req_year=req_year,
            stage_key='ewc_qualifier',
            region_slug=region_slug,
            all_regions=all_regions,
            reg_data=reg_data,
            direct_qualifiers=direct_qualifiers,
            eq_data=eq_data,
            cfg=Config,
        )

    @app.route('/api/campaign/<int:campaign_id>/ewc_qualifier/match/sim', methods=['POST'])
    def api_campaign_ewc_qualifier_match_sim(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404

        data = request.get_json(silent=True) or {}
        region_slug = data.get('region_slug') or data.get('region')
        match_id = data.get('match_id')

        if not region_slug or not match_id:
            return jsonify({'error': 'region and match_id are required'}), 400

        try:
            res = resolve_ewc_qualifier_match_interactive(campaign_id, region_slug, match_id, winner_id=None)
            return jsonify({'success': True, 'result': res})
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    @app.route('/api/campaign/<int:campaign_id>/ewc_qualifier/match/manual', methods=['POST'])
    def api_campaign_ewc_qualifier_match_manual(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404

        data = request.get_json(silent=True) or {}
        region_slug = data.get('region_slug') or data.get('region')
        match_id = data.get('match_id')
        winner_id = data.get('winner_id')
        maps = data.get('maps')

        if not region_slug or not match_id or not winner_id:
            return jsonify({'error': 'region, match_id and winner_id are required'}), 400

        try:
            res = resolve_ewc_qualifier_match_interactive(
                campaign_id, region_slug, match_id, winner_id=int(winner_id), maps=maps
            )
            return jsonify({'success': True, 'result': res})
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    @app.route('/api/campaign/<int:campaign_id>/ewc_qualifier/sim-round', methods=['POST'])
    def api_campaign_ewc_qualifier_sim_round(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404

        data = request.get_json(silent=True) or {}
        region_slug = data.get('region_slug') or data.get('region')
        if not region_slug:
            return jsonify({'error': 'region is required'}), 400

        try:
            auto_confirm = data.get('auto_confirm', True)
            res = sim_ewc_qualifier_round_interactive(campaign_id, region_slug, auto_confirm=auto_confirm)
            return jsonify({'success': True, 'result': res})
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    @app.route('/api/campaign/<int:campaign_id>/ewc_qualifier/sim-region', methods=['POST'])
    def api_campaign_ewc_qualifier_sim_region(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404

        data = request.get_json(silent=True) or {}
        region_slug = data.get('region_slug') or data.get('region')
        if not region_slug:
            return jsonify({'error': 'region is required'}), 400

        try:
            auto_confirm = data.get('auto_confirm', True)
            res = sim_ewc_qualifier_region_interactive(campaign_id, region_slug, auto_confirm=auto_confirm)
            return jsonify({'success': True, 'result': res})
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    @app.route('/api/campaign/<int:campaign_id>/ewc_qualifier/sim-all', methods=['POST'])
    def api_campaign_ewc_qualifier_sim_all(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404

        data = request.get_json(silent=True) or {}
        try:
            auto_confirm = data.get('auto_confirm', True)
            res = sim_ewc_qualifier_all_interactive(campaign_id, auto_confirm=auto_confirm)
            return jsonify({'success': True, 'result': res})
        except Exception as e:
            return jsonify({'error': str(e)}), 400
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    @app.route('/campaign/<int:campaign_id>/stage/master')
    def campaign_master_view(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return "Campaign not found", 404

        req_year = request.args.get('year', type=int) or campaign.current_year
        stage = get_stage_record(campaign_id, 'master', year=req_year)
        master_data = get_master_data(campaign_id, year=req_year)
        ewc_data = get_ewc_data(campaign_id, year=req_year)
        cp_leaderboards = {
            r: get_championship_leaderboard(campaign_id, region_slug=r)
            for r in ['pacific', 'americas', 'emea', 'china']
        }
        season_hosts = get_season_hosts(campaign.id, req_year)

        return render_template(
            'campaign/master.html',
            campaign=campaign,
            stage=stage,
            req_year=req_year,
            master_data=master_data,
            ewc_data=ewc_data,
            cp_leaderboards=cp_leaderboards,
            season_hosts=season_hosts,
            cfg=Config,
        )

    @app.route('/api/campaign/<int:campaign_id>/master/match/sim', methods=['POST'])
    def api_campaign_master_match_sim(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404

        data = request.get_json(silent=True) or {}
        match_id = data.get('match_id')
        if not match_id:
            return jsonify({'error': 'match_id is required'}), 400

        try:
            res = resolve_master_match_interactive(campaign_id, match_id, winner_id=None)
            return jsonify({'success': True, 'result': res})
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    @app.route('/api/campaign/<int:campaign_id>/master/match/manual', methods=['POST'])
    def api_campaign_master_match_manual(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404

        data = request.get_json(silent=True) or {}
        match_id = data.get('match_id')
        winner_id = data.get('winner_id')
        maps = data.get('maps')

        if not match_id or not winner_id:
            return jsonify({'error': 'match_id and winner_id are required'}), 400

        try:
            res = resolve_master_match_interactive(campaign_id, match_id, winner_id=int(winner_id), maps=maps)
            return jsonify({'success': True, 'result': res})
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    @app.route('/api/campaign/<int:campaign_id>/master/sim-round', methods=['POST'])
    def api_campaign_master_sim_round(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404

        data = request.get_json(silent=True) or {}
        try:
            auto_confirm = data.get('auto_confirm', True)
            res = sim_master_round_interactive(campaign_id, auto_confirm=auto_confirm)
            return jsonify({'success': True, 'result': res})
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    @app.route('/api/campaign/<int:campaign_id>/master/sim-all', methods=['POST'])
    def api_campaign_master_sim_all(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404

        data = request.get_json(silent=True) or {}
        try:
            auto_confirm = data.get('auto_confirm', True)
            res = sim_master_tournament_interactive(campaign_id, auto_confirm=auto_confirm)
            return jsonify({'success': True, 'result': res})
        except Exception as e:
            return jsonify({'error': str(e)}), 400
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    @app.route('/campaign/<int:campaign_id>/stage/ewc')
    def campaign_ewc_view(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return "Campaign not found", 404

        req_year = request.args.get('year', type=int) or campaign.current_year
        stage = get_stage_record(campaign_id, 'ewc', year=req_year)
        ewc_data = get_ewc_data(campaign_id, year=req_year)
        cp_leaderboards = {
            r: get_championship_leaderboard(campaign_id, region_slug=r)
            for r in ['pacific', 'americas', 'emea', 'china']
        }
        season_hosts = get_season_hosts(campaign.id, req_year)

        return render_template(
            'campaign/ewc.html',
            campaign=campaign,
            stage=stage,
            req_year=req_year,
            ewc_data=ewc_data,
            cp_leaderboards=cp_leaderboards,
            season_hosts=season_hosts,
            cfg=Config,
        )

    @app.route('/api/campaign/<int:campaign_id>/ewc/match/sim', methods=['POST'])
    def api_campaign_ewc_match_sim(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404

        data = request.get_json(silent=True) or {}
        match_id = data.get('match_id')
        if not match_id:
            return jsonify({'error': 'match_id is required'}), 400

        try:
            res = resolve_ewc_match_interactive(campaign_id, match_id, winner_id=None)
            return jsonify({'success': True, 'result': res})
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    @app.route('/api/campaign/<int:campaign_id>/ewc/match/manual', methods=['POST'])
    def api_campaign_ewc_match_manual(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404

        data = request.get_json(silent=True) or {}
        match_id = data.get('match_id')
        winner_id = data.get('winner_id')
        maps = data.get('maps')

        if not match_id or not winner_id:
            return jsonify({'error': 'match_id and winner_id are required'}), 400

        try:
            res = resolve_ewc_match_interactive(campaign_id, match_id, winner_id=int(winner_id), maps=maps)
            return jsonify({'success': True, 'result': res})
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    @app.route('/api/campaign/<int:campaign_id>/ewc/sim-round', methods=['POST'])
    def api_campaign_ewc_sim_round(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404

        data = request.get_json(silent=True) or {}
        try:
            auto_confirm = data.get('auto_confirm', True)
            res = sim_ewc_round_interactive(campaign_id, auto_confirm=auto_confirm)
            return jsonify({'success': True, 'result': res})
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    @app.route('/api/campaign/<int:campaign_id>/ewc/sim-all', methods=['POST'])
    def api_campaign_ewc_sim_all(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404

        data = request.get_json(silent=True) or {}
        try:
            auto_confirm = data.get('auto_confirm', True)
            res = sim_ewc_tournament_interactive(campaign_id, auto_confirm=auto_confirm)
            return jsonify({'success': True, 'result': res})
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    # ─────────────────────────────────────────────────────────────────────────
    # Campaign Stage: Open Qualifier Stage 2 (Interactive View & APIs)
    # ─────────────────────────────────────────────────────────────────────────

    @app.route('/campaign/<int:campaign_id>/stage/oq_stage2')
    def campaign_oq_stage2_view(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return "Campaign not found", 404

        active_region = request.args.get('region', 'pacific').lower()
        if active_region not in ['pacific', 'americas', 'emea', 'china']:
            active_region = 'pacific'

        req_year = request.args.get('year', type=int) or campaign.current_year
        stage = get_stage_record(campaign_id, 'oq_stage2', year=req_year)
        oq_data = get_oq_stage2_data(campaign_id)
        return render_template(
            'campaign/oq_stage2.html',
            campaign=campaign,
            stage=stage,
            req_year=req_year,
            active_region=active_region,
            selected_region=active_region,
            oq_data=oq_data,
            cfg=Config,
        )

    @app.route('/api/campaign/<int:campaign_id>/oq_stage2/match/sim', methods=['POST'])
    def api_campaign_oq_stage2_match_sim(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404

        data = request.get_json(silent=True) or {}
        region_slug = data.get('region_slug') or data.get('region')
        match_id = data.get('match_id')

        if not region_slug or not match_id:
            return jsonify({'error': 'region and match_id are required'}), 400

        try:
            res = resolve_oq_stage2_match(campaign_id, region_slug, match_id, winner_id=None)
            return jsonify({'success': True, 'result': res})
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    @app.route('/api/campaign/<int:campaign_id>/oq_stage2/match/manual', methods=['POST'])
    def api_campaign_oq_stage2_match_manual(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404

        data = request.get_json(silent=True) or {}
        region_slug = data.get('region_slug') or data.get('region')
        match_id = data.get('match_id')
        winner_id = data.get('winner_id')
        maps = data.get('maps')

        if not region_slug or not match_id or not winner_id:
            return jsonify({'error': 'region, match_id and winner_id are required'}), 400

        try:
            res = resolve_oq_stage2_match(campaign_id, region_slug, match_id, winner_id=int(winner_id), maps=maps)
            return jsonify({'success': True, 'result': res})
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    @app.route('/api/campaign/<int:campaign_id>/oq_stage2/sim-round', methods=['POST'])
    def api_campaign_oq_stage2_sim_round(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404

        data = request.get_json(silent=True) or {}
        region_slug = data.get('region_slug') or data.get('region')
        if not region_slug:
            return jsonify({'error': 'region is required'}), 400

        try:
            auto_confirm = data.get('auto_confirm', True)
            res = sim_oq_stage2_round(campaign_id, region_slug, auto_confirm=auto_confirm)
            return jsonify({'success': True, 'result': res})
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    @app.route('/api/campaign/<int:campaign_id>/oq_stage2/sim-region', methods=['POST'])
    def api_campaign_oq_stage2_sim_region(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404

        data = request.get_json(silent=True) or {}
        region_slug = data.get('region_slug') or data.get('region')
        if not region_slug:
            return jsonify({'error': 'region is required'}), 400

        try:
            auto_confirm = data.get('auto_confirm', True)
            res = sim_oq_stage2_region(campaign_id, region_slug, auto_confirm=auto_confirm)
            return jsonify({'success': True, 'result': res})
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    @app.route('/api/campaign/<int:campaign_id>/oq_stage2/sim-all', methods=['POST'])
    def api_campaign_oq_stage2_sim_all(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404

        data = request.get_json(silent=True) or {}
        try:
            auto_confirm = data.get('auto_confirm', True)
            res = sim_oq_stage2_all(campaign_id, auto_confirm=auto_confirm)
            return jsonify({'success': True, 'result': res})
        except Exception as e:
            return jsonify({'error': str(e)}), 400
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    # ─────────────────────────────────────────────────────────────────────────
    # Campaign Stage: VCT Stage 2 (Interactive View & APIs)
    # ─────────────────────────────────────────────────────────────────────────

    @app.route('/campaign/<int:campaign_id>/stage/stage2')
    def campaign_stage2_view(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return "Campaign not found", 404

        active_region = request.args.get('region', 'pacific').lower()
        if active_region not in ['pacific', 'americas', 'emea', 'china']:
            active_region = 'pacific'

        req_year = request.args.get('year', type=int) or campaign.current_year
        stage = get_stage_record(campaign_id, 'stage2', year=req_year)
        stage2_data = get_stage2_data(campaign_id, year=req_year)
        cp_leaderboards = {
            r: get_championship_leaderboard(campaign_id, region_slug=r)
            for r in ['pacific', 'americas', 'emea', 'china']
        }
        season_hosts = get_season_hosts(campaign.id, req_year)
        return render_template(
            'campaign/stage2.html',
            campaign=campaign,
            stage=stage,
            req_year=req_year,
            active_region=active_region,
            stage2_data=stage2_data,
            cp_leaderboards=cp_leaderboards,
            season_hosts=season_hosts,
            cfg=Config,
        )

    @app.route('/api/campaign/<int:campaign_id>/stage2/match/sim', methods=['POST'])
    def api_campaign_stage2_match_sim(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404

        data = request.get_json(silent=True) or {}
        region_slug = data.get('region_slug') or data.get('region')
        match_id = data.get('match_id')

        if not region_slug or not match_id:
            return jsonify({'error': 'region and match_id are required'}), 400

        try:
            res = resolve_stage2_match_interactive(campaign_id, region_slug, match_id, winner_id=None)
            return jsonify({'success': True, 'result': res})
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    @app.route('/api/campaign/<int:campaign_id>/stage2/match/manual', methods=['POST'])
    def api_campaign_stage2_match_manual(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404

        data = request.get_json(silent=True) or {}
        region_slug = data.get('region_slug') or data.get('region')
        match_id = data.get('match_id')
        winner_id = data.get('winner_id')
        maps = data.get('maps')

        if not region_slug or not match_id or not winner_id:
            return jsonify({'error': 'region, match_id and winner_id are required'}), 400

        try:
            res = resolve_stage2_match_interactive(
                campaign_id, region_slug, match_id, winner_id=int(winner_id), maps=maps
            )
            return jsonify({'success': True, 'result': res})
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    @app.route('/api/campaign/<int:campaign_id>/stage2/sim-round', methods=['POST'])
    def api_campaign_stage2_sim_round(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404

        data = request.get_json(silent=True) or {}
        region_slug = data.get('region_slug') or data.get('region')
        if not region_slug:
            return jsonify({'error': 'region is required'}), 400

        try:
            auto_confirm = data.get('auto_confirm', True)
            res = sim_stage2_round_interactive(campaign_id, region_slug, auto_confirm=auto_confirm)
            return jsonify({'success': True, 'result': res})
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    @app.route('/api/campaign/<int:campaign_id>/stage2/sim-region', methods=['POST'])
    def api_campaign_stage2_sim_region(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404

        data = request.get_json(silent=True) or {}
        region_slug = data.get('region_slug') or data.get('region')
        if not region_slug:
            return jsonify({'error': 'region is required'}), 400

        try:
            auto_confirm = data.get('auto_confirm', True)
            res = sim_stage2_region_interactive(campaign_id, region_slug, auto_confirm=auto_confirm)
            return jsonify({'success': True, 'result': res})
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    @app.route('/api/campaign/<int:campaign_id>/stage2/sim-all', methods=['POST'])
    def api_campaign_stage2_sim_all(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404

        data = request.get_json(silent=True) or {}
        try:
            auto_confirm = data.get('auto_confirm', True)
            res = sim_stage2_all_interactive(campaign_id, auto_confirm=auto_confirm)
            return jsonify({'success': True, 'result': res})
        except Exception as e:
            return jsonify({'error': str(e)}), 400
    # ─────────────────────────────────────────────────────────────────────────
    # Campaign Stage: VALORANT Champions Paris (Interactive View & APIs)
    # ─────────────────────────────────────────────────────────────────────────

    @app.route('/campaign/<int:campaign_id>/stage/champion')
    def campaign_champion_view(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return "Campaign not found", 404

        req_year = request.args.get('year', type=int) or campaign.current_year
        stage = get_stage_record(campaign_id, 'champion', year=req_year)
        champion_data = get_champion_data(campaign_id, year=req_year)
        season_hosts = get_season_hosts(campaign.id, req_year)
        return render_template(
            'campaign/champion.html',
            campaign=campaign,
            stage=stage,
            req_year=req_year,
            champion_data=champion_data,
            season_hosts=season_hosts,
            cfg=Config,
        )

    @app.route('/api/campaign/<int:campaign_id>/champion/match/sim', methods=['POST'])
    def api_campaign_champion_match_sim(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404

        data = request.get_json(silent=True) or {}
        match_id = data.get('match_id')
        if not match_id:
            return jsonify({'error': 'match_id is required'}), 400

        try:
            res = resolve_champion_match_interactive(campaign_id, match_id, winner_id=None)
            return jsonify({'success': True, 'result': res})
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    @app.route('/api/campaign/<int:campaign_id>/champion/match/manual', methods=['POST'])
    def api_campaign_champion_match_manual(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404

        data = request.get_json(silent=True) or {}
        match_id = data.get('match_id')
        winner_id = data.get('winner_id')
        maps = data.get('maps')

        if not match_id or not winner_id:
            return jsonify({'error': 'match_id and winner_id are required'}), 400

        try:
            res = resolve_champion_match_interactive(campaign_id, match_id, winner_id=int(winner_id), maps=maps)
            return jsonify({'success': True, 'result': res})
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    @app.route('/api/campaign/<int:campaign_id>/champion/sim-round', methods=['POST'])
    def api_campaign_champion_sim_round(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404

        data = request.get_json(silent=True) or {}
        try:
            auto_confirm = data.get('auto_confirm', True)
            res = sim_champion_round_interactive(campaign_id, auto_confirm=auto_confirm)
            return jsonify({'success': True, 'result': res})
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    @app.route('/api/campaign/<int:campaign_id>/champion/sim-all', methods=['POST'])
    def api_campaign_champion_sim_all(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404

        data = request.get_json(silent=True) or {}
        try:
            auto_confirm = data.get('auto_confirm', True)
            res = sim_champion_tournament_interactive(campaign_id, auto_confirm=auto_confirm)
            return jsonify({'success': True, 'result': res})
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    # ─────────────────────────────────────────────────────────────────────────
    # Campaign Stage: Year-End Hall of Fame & Season Summary View & Rollover
    # ─────────────────────────────────────────────────────────────────────────

    @app.route('/campaign/<int:campaign_id>/stage/season_summary')
    @app.route('/campaign/<int:campaign_id>/hall-of-fame')
    def campaign_season_summary_view(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return "Campaign not found", 404

        req_year = request.args.get('year', type=int)
        summary_data = get_season_summary_data(campaign_id, year=req_year)
        partnership_cycle = get_partnership_cycle_status(campaign_id, year=summary_data.get('year', campaign.current_year))
        return render_template(
            'campaign/season_summary.html',
            campaign=campaign,
            summary_data=summary_data,
            partnership_cycle=partnership_cycle,
            cfg=Config,
        )

    @app.route('/api/campaign/<int:campaign_id>/stage-history/<stage_key>')
    def api_campaign_stage_history(campaign_id, stage_key):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404

        year = request.args.get('year', type=int)
        region = request.args.get('region')
        history_data = get_stage_placements_history(campaign_id, stage_key, year=year, region_slug=region)
        return jsonify({'success': True, 'data': history_data})

    @app.route('/api/campaign/<int:campaign_id>/hall-of-fame-data')
    def api_campaign_hall_of_fame_data(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404

        year = request.args.get('year', type=int)
        summary_data = get_season_summary_data(campaign_id, year=year)
        return jsonify({'success': True, 'data': summary_data})

    @app.route('/api/campaign/<int:campaign_id>/power-rankings')
    def api_campaign_power_rankings(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404

        region = request.args.get('region')
        rankings = get_global_power_rankings(campaign_id, region_slug=region)
        return jsonify({'success': True, 'rankings': rankings})

    @app.route('/api/campaign/<int:campaign_id>/gpr/recalculate', methods=['POST'])
    def api_campaign_gpr_recalculate(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404

        try:
            rankings = recalculate_campaign_gpr(campaign_id)
            return jsonify({'success': True, 'count': len(rankings), 'rankings': rankings})
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    @app.route('/api/campaign/<int:campaign_id>/all-time-trophies')
    def api_campaign_all_time_trophies(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404

        trophies = get_all_time_trophy_table(campaign_id)
        return jsonify({'success': True, 'trophies': trophies})

    @app.route('/campaign/<int:campaign_id>/team/<int:club_id>')
    def campaign_team_profile_view(campaign_id, club_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return "Campaign not found", 404

        profile_data = get_team_profile_data(campaign_id, club_id)
        if not profile_data:
            return "Club profile not found", 404

        return render_template(
            'campaign/team_profile.html',
            campaign=campaign,
            profile=profile_data,
            cfg=Config,
        )

    @app.route('/api/campaign/<int:campaign_id>/team/<int:club_id>')
    def api_campaign_team_profile(campaign_id, club_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404

        profile_data = get_team_profile_data(campaign_id, club_id)
        if not profile_data:
            return jsonify({'error': 'Club not found'}), 404

        return jsonify({'success': True, 'profile': profile_data})

    @app.route('/api/campaign/<int:campaign_id>/advance-year', methods=['POST'])
    def api_campaign_advance_year(campaign_id):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404

        try:
            data = request.get_json(silent=True) or {}
            storylines_payload = data.get('storylines')
            partnership_selections = data.get('partnership_selections')
            if partnership_selections and isinstance(partnership_selections, dict):
                commit_partnership_selection(campaign_id, partnership_selections, year=campaign.current_year)
            res = advance_campaign_to_next_year(campaign_id)
            if storylines_payload and isinstance(storylines_payload, list):
                commit_season_storylines(campaign_id, storylines_payload, year=campaign.current_year)
            return jsonify({'success': True, 'result': res})
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    @app.route('/api/campaign/<int:campaign_id>/<stage_key>/confirm-region', methods=['POST'])
    def api_campaign_confirm_stage_region(campaign_id, stage_key):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404

        data = request.get_json(silent=True) or {}
        region_slug = data.get('region') or data.get('region_slug')
        if not region_slug:
            return jsonify({'error': 'region is required'}), 400

        try:
            res = confirm_stage_region(campaign_id, stage_key, region_slug)
            return jsonify({'success': True, 'result': res})
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    @app.route('/api/campaign/<int:campaign_id>/<stage_key>/confirm-all', methods=['POST'])
    def api_campaign_confirm_stage_all(campaign_id, stage_key):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404

        try:
            res = confirm_stage_all(campaign_id, stage_key)
            return jsonify({'success': True, 'result': res})
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    @app.route('/api/campaign/<int:campaign_id>/<stage_key>/confirm-tournament', methods=['POST'])
    def api_campaign_confirm_stage_tournament(campaign_id, stage_key):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404

        try:
            res = confirm_stage_tournament(campaign_id, stage_key)
            return jsonify({'success': True, 'result': res})
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    @app.route('/api/campaign/<int:campaign_id>/<stage_key>/confirm', methods=['POST'])
    def api_campaign_confirm_stage_unified(campaign_id, stage_key):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404

        data = request.get_json(silent=True) or {}
        region_slug = data.get('region') or data.get('region_slug')
        try:
            if region_slug:
                res = confirm_stage_region(campaign_id, stage_key, region_slug)
            elif stage_key in ['major', 'master', 'ewc', 'champion']:
                res = confirm_stage_tournament(campaign_id, stage_key)
            else:
                res = confirm_stage_all(campaign_id, stage_key)
            return jsonify({'success': True, 'result': res})
        except Exception as e:
            return jsonify({'error': str(e)}), 400
    @app.route('/api/campaign/<int:campaign_id>/<stage_key>/unlock-region', methods=['POST'])
    def api_campaign_unlock_stage_region(campaign_id, stage_key):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404

        data = request.get_json(silent=True) or {}
        region_slug = data.get('region') or data.get('region_slug')
        if not region_slug:
            return jsonify({'error': 'region is required'}), 400

        try:
            res = unlock_stage_region(campaign_id, stage_key, region_slug)
            return jsonify({'success': True, 'result': res})
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    @app.route('/api/campaign/<int:campaign_id>/<stage_key>/unlock', methods=['POST'])
    def api_campaign_unlock_stage_unified(campaign_id, stage_key):
        campaign = get_campaign(campaign_id)
        if not campaign:
            return jsonify({'error': 'Campaign not found'}), 404

        data = request.get_json(silent=True) or {}
        region_slug = data.get('region') or data.get('region_slug')
        try:
            if region_slug:
                res = unlock_stage_region(campaign_id, stage_key, region_slug)
            else:
                res = unlock_stage_tournament(campaign_id, stage_key)
            return jsonify({'success': True, 'result': res})
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    # ==================== CAMPAIGN EXPORT & IMPORT ROUTES ====================

    @app.route('/api/campaign/<int:campaign_id>/export', methods=['GET'])
    def api_campaign_export(campaign_id):
        try:
            data = export_campaign_save(campaign_id)
            safe_name = "".join(c for c in data['campaign']['name'] if c.isalnum() or c in (' ', '_', '-')).strip().replace(' ', '_')
            filename = f"vct_save_{safe_name or 'campaign'}_{data['campaign']['current_year']}.json"
            try:
                import os
                save_dir = os.path.join(os.getcwd(), 'saves', 'campaign')
                os.makedirs(save_dir, exist_ok=True)
                with open(os.path.join(save_dir, filename), 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
            except Exception:
                pass
            return Response(
                json.dumps(data, indent=2, ensure_ascii=False),
                mimetype='application/json',
                headers={'Content-Disposition': f'attachment; filename="{filename}"'}
            )
        except Exception as e:
            return jsonify({'error': str(e)}), 400

    @app.route('/api/campaign/import', methods=['POST'])
    def api_campaign_import():
        try:
            custom_name = None
            if 'file' in request.files:
                file = request.files['file']
                if not file or not file.filename:
                    return jsonify({'error': 'Chưa chọn file lưu (.json)'}), 400
                content = file.read().decode('utf-8')
                payload = json.loads(content)
                custom_name = request.form.get('custom_name')
            else:
                payload = request.get_json(silent=True)
                if not payload:
                    return jsonify({'error': 'Không có dữ liệu save file'}), 400
                custom_name = payload.get('custom_name')

            campaign = import_campaign_save(payload, custom_name=custom_name)
            return jsonify({
                'success': True,
                'campaign_id': campaign.id,
                'name': campaign.name,
                'redirect_url': url_for('campaign_detail', campaign_id=campaign.id)
            })
        except Exception as e:
            db.session.rollback()
            return jsonify({'error': str(e)}), 400

    @app.route('/api/saves/<mode>', methods=['GET'])
    def api_list_saves(mode):
        if mode not in ('single', 'campaign'):
            return jsonify({'error': 'Invalid mode'}), 400
        import os
        save_dir = os.path.join(os.getcwd(), 'saves', mode)
        os.makedirs(save_dir, exist_ok=True)
        files = []
        for fname in os.listdir(save_dir):
            if fname.endswith('.json'):
                fpath = os.path.join(save_dir, fname)
                st = os.stat(fpath)
                files.append({
                    'filename': fname,
                    'size': st.st_size,
                    'modified_at': datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
                })
        files.sort(key=lambda x: x['modified_at'], reverse=True)
        return jsonify({'success': True, 'mode': mode, 'files': files})

    @app.route('/api/saves/<mode>/load/<path:filename>', methods=['POST'])
    def api_load_save_file(mode, filename):
        if mode not in ('single', 'campaign'):
            return jsonify({'error': 'Invalid mode'}), 400
        import os
        safe_fname = os.path.basename(filename)
        save_path = os.path.join(os.getcwd(), 'saves', mode, safe_fname)
        if not os.path.exists(save_path):
            return jsonify({'error': 'File not found'}), 404

        try:
            with open(save_path, 'r', encoding='utf-8') as f:
                payload = json.load(f)

            if mode == 'campaign':
                campaign = import_campaign_save(payload)
                return jsonify({'success': True, 'redirect_url': f'/campaign/{campaign.id}'})
            else:
                tour = import_payload(payload)
                return jsonify({'success': True, 'redirect_url': f'/tournament/{tour.id}'})
        except Exception as e:
            return jsonify({'error': str(e)}), 400


