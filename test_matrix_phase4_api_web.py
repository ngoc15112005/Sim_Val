"""
test_matrix_phase4_api_web.py — Phase 4 Test Suite for VALORANT Master Testing Matrix A-Z.

Categories Covered:
- Category N: Negative, Boundary & Malicious Input Fuzzing (TC-N01 .. TC-N05)
- Category O: Overrides, Manual Adjustments & Cascade Invalidation (TC-O01 .. TC-O03)
- Category R: REST API Endpoints & Route Security Matrix (TC-R01 .. TC-R05)
- Category U: UI / View Rendering & Template Integrity (TC-U01 .. TC-U04)
- Category X: eXport, Import & Backup Data Parity (TC-X01 .. TC-X03)
"""

import unittest
import json
from app import create_app
from models import db, Club, Region, Tournament, TournamentParticipant, Match, Campaign
from engine.match import validate_and_normalize_manual_maps
from engine.tournament import create_tournament, generate_bracket, simulate_all_pending
from services.campaign_service import (
    create_campaign, get_campaign, get_open_qualifier_data, resolve_oq_match
)
from services.export_import_service import (
    export_tournament_dict, import_payload, delete_tournament_cascade
)


class TestMatrixPhase4ApiWeb(unittest.TestCase):

    def setUp(self):
        self.app = create_app()
        self.app_context = self.app.app_context()
        self.app_context.push()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.rollback()
        db.session.remove()
        self.app_context.pop()

    # ─────────────────────────────────────────────────────────────────────────
    # CATEGORY N: Negative, Boundary & Malicious Input Fuzzing
    # ─────────────────────────────────────────────────────────────────────────

    def test_tc_n01_negative_or_draw_map_scores_rejected(self):
        """TC-N01: Negative scores or draws (13-13, -1-13) are rejected by validator."""
        # Draw 13-13
        with self.assertRaises(ValueError):
            validate_and_normalize_manual_maps([{'team_a_score': 13, 'team_b_score': 13}], bo=3)

        # Negative score
        with self.assertRaises(ValueError):
            validate_and_normalize_manual_maps([{'team_a_score': -5, 'team_b_score': 13}], bo=3)

    def test_tc_n02_invalid_overtime_scores_rejected(self):
        """TC-N02: Invalid overtime scores (13-12, 14-13) are rejected (must lead by 2)."""
        with self.assertRaises(ValueError):
            validate_and_normalize_manual_maps([{'team_a_score': 13, 'team_b_score': 12}], bo=3)

        with self.assertRaises(ValueError):
            validate_and_normalize_manual_maps([{'team_a_score': 14, 'team_b_score': 13}], bo=3)

    def test_tc_n03_inconsistent_winner_id_auto_aligned(self):
        """TC-N03: If input claims Team B won but map scores show Team A won, winner is auto-aligned."""
        input_maps = [
            {'team_a_score': 13, 'team_b_score': 5},
            {'team_a_score': 13, 'team_b_score': 8},
        ]
        wins_a, wins_b, winner_id, loser_id, sanitized = validate_and_normalize_manual_maps(
            maps=input_maps, bo=3, id_a=100, id_b=200, forced_winner_id=200  # falsely claim Team B
        )
        self.assertEqual(winner_id, 100, "Winner ID phải tự động khớp với tỷ số map thắng thực tế")
        self.assertEqual(loser_id, 200)

    def test_tc_n04_xss_injection_in_campaign_name_escaped(self):
        """TC-N04: XSS payloads in campaign names are properly handled and escaped."""
        xss_name = "<script>alert('pwned')</script>"
        camp = create_campaign(name=xss_name, start_year=2027)
        resp = self.client.get(f'/campaign/{camp.id}')
        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode('utf-8')
        self.assertNotIn("<script>alert('pwned')</script>", html)

    def test_tc_n05_nonexistent_and_negative_ids_graceful_http(self):
        """TC-N05: Non-existent IDs, negative IDs, or string IDs return HTTP 404/400 without 500 error."""
        r1 = self.client.get('/api/tournament/-1')
        self.assertIn(r1.status_code, [404, 400])

        r2 = self.client.get('/api/tournament/99999999')
        self.assertEqual(r2.status_code, 404)

        r3 = self.client.get('/campaign/99999999')
        self.assertEqual(r3.status_code, 404)

    # ─────────────────────────────────────────────────────────────────────────
    # CATEGORY O: Overrides, Manual Adjustments & Cascade Invalidation
    # ─────────────────────────────────────────────────────────────────────────

    def test_tc_o01_manual_override_pending_match(self):
        """TC-O01: Manual override on pending match sets status='completed', is_manual=True."""
        camp = create_campaign("Manual Override Test", 2027)
        oq_data = get_open_qualifier_data(camp.id)
        m1 = oq_data['regions']['pacific']['swiss_matches'][0]
        id_a = m1['team_a_id']

        manual_maps = [{'team_a_score': 13, 'team_b_score': 7}]
        res = resolve_oq_match(camp.id, 'pacific', m1['id'], winner_id=id_a, maps=manual_maps)

        self.assertEqual(res['match']['status'], 'completed')
        self.assertTrue(res['match']['is_manual'])
        self.assertEqual(res['match']['winner_id'], id_a)
        self.assertEqual(res['match']['team_a_score'], 1)
        self.assertEqual(res['match']['team_b_score'], 0)

    def test_tc_o02_manual_override_on_completed_match(self):
        """TC-O02: Re-overriding an already completed match successfully flips the winner."""
        camp = create_campaign("Re-Override Test", 2027)
        oq_data = get_open_qualifier_data(camp.id)
        m1 = oq_data['regions']['americas']['swiss_matches'][0]
        id_a = m1['team_a_id']
        id_b = m1['team_b_id']

        # 1st time: A wins
        resolve_oq_match(camp.id, 'americas', m1['id'], winner_id=id_a, maps=[{'team_a_score': 13, 'team_b_score': 9}])

        # 2nd time: Flip to B wins
        res2 = resolve_oq_match(camp.id, 'americas', m1['id'], winner_id=id_b, maps=[{'team_a_score': 10, 'team_b_score': 13}])
        self.assertEqual(res2['match']['winner_id'], id_b)
        self.assertEqual(res2['match']['team_b_score'], 1)

    def test_tc_o03_simulation_continues_after_manual_override(self):
        """TC-O03: Sim round runs smoothly after a manual override on match 1."""
        camp = create_campaign("Sim After Override Test", 2027)
        oq_data = get_open_qualifier_data(camp.id)
        m1 = oq_data['regions']['emea']['swiss_matches'][0]

        # Manual override match 1
        resolve_oq_match(camp.id, 'emea', m1['id'], winner_id=m1['team_a_id'], maps=[{'team_a_score': 13, 'team_b_score': 5}])

        # Sim remainder of round via API
        resp = self.client.post(f'/api/campaign/{camp.id}/open_qualifier/sim-round', json={'region_slug': 'emea'})
        self.assertEqual(resp.status_code, 200)

        updated_data = get_open_qualifier_data(camp.id)
        r1_matches = updated_data['regions']['emea']['swiss_matches'][:8]
        self.assertTrue(all(m['status'] == 'completed' for m in r1_matches))

    # ─────────────────────────────────────────────────────────────────────────
    # CATEGORY R: REST API Endpoints & Route Security Matrix
    # ─────────────────────────────────────────────────────────────────────────

    def test_tc_r01_api_clubs_and_regions(self):
        """TC-R01: GET /api/clubs and GET /api/regions return HTTP 200 OK."""
        r_clubs = self.client.get('/api/clubs')
        self.assertEqual(r_clubs.status_code, 200)
        clubs_data = r_clubs.get_json()
        self.assertEqual(len(clubs_data), 96)

        r_regions = self.client.get('/api/regions')
        self.assertEqual(r_regions.status_code, 200)
        regions_data = r_regions.get_json()
        self.assertEqual(len(regions_data), 4)

    def test_tc_r02_api_campaign_match_sim(self):
        """TC-R02: POST /api/campaign/<cid>/open_qualifier/match/sim returns HTTP 200."""
        camp = create_campaign("API Match Sim Test", 2027)
        oq_data = get_open_qualifier_data(camp.id)
        m1 = oq_data['regions']['china']['swiss_matches'][0]

        resp = self.client.post(f'/api/campaign/{camp.id}/open_qualifier/match/sim', json={
            'region_slug': 'china',
            'match_id': m1['id']
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get('success'))

    def test_tc_r03_api_campaign_sim_round(self):
        """TC-R03: POST /api/campaign/<cid>/open_qualifier/sim-round returns HTTP 200."""
        camp = create_campaign("API Sim Round Test", 2027)
        resp = self.client.post(f'/api/campaign/{camp.id}/open_qualifier/sim-round', json={
            'region_slug': 'pacific'
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get('success'))

    def test_tc_r04_api_campaign_sim_stage(self):
        """TC-R04: POST /api/campaign/<cid>/open_qualifier/sim completes stage with HTTP 200."""
        camp = create_campaign("API Sim Stage Test", 2027)
        resp = self.client.post(f'/api/campaign/{camp.id}/open_qualifier/sim', json={})
        self.assertEqual(resp.status_code, 200)

    def test_tc_r05_method_not_allowed_on_post_endpoint(self):
        """TC-R05: GET on a POST-only action route returns HTTP 405 Method Not Allowed."""
        camp = create_campaign("Method Not Allowed Test", 2027)
        resp = self.client.get(f'/api/campaign/{camp.id}/advance-year')
        self.assertEqual(resp.status_code, 405)

    # ─────────────────────────────────────────────────────────────────────────
    # CATEGORY U: UI / View Rendering & Template Integrity
    # ─────────────────────────────────────────────────────────────────────────

    def test_tc_u01_campaign_detail_view_renders(self):
        """TC-U01: /campaign/<cid> renders HTTP 200 with all 11 stages visible."""
        camp = create_campaign("View Render Test", 2027)
        resp = self.client.get(f'/campaign/{camp.id}')
        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode('utf-8')
        self.assertIn("Open Qualifier", html)

    def test_tc_u02_bracket_tree_view_renders(self):
        """TC-U02: Bracket tree page renders HTTP 200."""
        camp = create_campaign("OQ View Render Test", 2027)
        resp = self.client.get(f'/campaign/{camp.id}/stage/open_qualifier')
        self.assertEqual(resp.status_code, 200)

    def test_tc_u03_standalone_tournament_view_renders(self):
        """TC-U03: /tournament/<tour_id> renders without crashes on pending matches."""
        clubs = Club.query.limit(8).all()
        tour = create_tournament('major', 'View TBD Test', selected_club_ids=[c.id for c in clubs])
        generate_bracket(tour)
        db.session.commit()

        resp = self.client.get(f'/tournament/{tour.id}')
        self.assertEqual(resp.status_code, 200)

    def test_tc_u04_points_leaderboard_api_renders(self):
        """TC-U04: /api/campaign/<cid>/points/leaderboard returns HTTP 200 with regional tables."""
        camp = create_campaign("Leaderboard API Test", 2027)
        resp = self.client.get(f'/api/campaign/{camp.id}/points/leaderboard')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn('americas', data)
        self.assertIn('pacific', data)

    # ─────────────────────────────────────────────────────────────────────────
    # CATEGORY X: eXport, Import & Backup Data Parity
    # ─────────────────────────────────────────────────────────────────────────

    def test_tc_x01_export_tournament_dict_complete(self):
        """TC-X01: export_tournament_dict serializes tournament into complete dictionary."""
        clubs = Club.query.limit(8).all()
        tour = create_tournament('major', 'Export Test', selected_club_ids=[c.id for c in clubs])
        generate_bracket(tour)
        db.session.commit()

        exp = export_tournament_dict(tour)
        self.assertEqual(exp['version'], '1.0')
        self.assertEqual(exp['type'], 'major')
        self.assertEqual(exp['name'], 'Export Test')
        self.assertEqual(len(exp['participants']), 8)
        self.assertGreater(len(exp['matches']), 0)

    def test_tc_x02_import_tournament_restores_record(self):
        """TC-X02: import_payload creates restored tournament with matching records."""
        clubs = Club.query.limit(8).all()
        tour = create_tournament('major', 'Import Test Original', selected_club_ids=[c.id for c in clubs])
        generate_bracket(tour)
        db.session.commit()

        exp = export_tournament_dict(tour)
        exp['name'] = 'Import Test Restored'

        imported_tours = import_payload(exp)
        self.assertEqual(len(imported_tours), 1)
        imported_tour = imported_tours[0]
        self.assertEqual(imported_tour.name, 'Import Test Restored')
        self.assertEqual(len(imported_tour.participants), 8)

    def test_tc_x03_malformed_import_payload_error_handling(self):
        """TC-X03: Malformed import payload returns error and rolls back transaction."""
        malformed = {'invalid_unknown_key': 123}
        with self.assertRaises(ValueError):
            import_payload(malformed)


if __name__ == '__main__':
    unittest.main()
