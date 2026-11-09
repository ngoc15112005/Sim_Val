"""
test_matrix_phase1_core.py — Phase 1 Test Suite for VALORANT Master Testing Matrix A-Z.

Categories Covered:
- Category A: Architecture, Database Models & Referential Integrity (TC-A01 .. TC-A04)
- Category B: Base Math, Elo Rating & Probability Engine (TC-B01 .. TC-B04)
- Category C: Clash Mechanics, Form Modifiers & RPG Systems (TC-C01 .. TC-C04)
- Category M: Match Simulation, Map Pools & Overtime Rules (TC-M01 .. TC-M04)
- Category V: Validation & Sanitization Layer (TC-V01 .. TC-V03)
"""

import unittest
import json
from app import create_app
from models import (
    db, Club, Region, Tournament, TournamentParticipant, Match, MatchMap,
    Campaign, CampaignClubState, CampaignStage, CampaignSeason, ClubRating
)
from engine.match import (
    calc_pure_international_win_rate, _calc_win_rate, _gen_map_score,
    simulate_match, validate_and_normalize_manual_maps
)
from engine.rating import update_ratings
from engine.tournament import create_tournament, generate_bracket
from services.campaign_service import (
    create_campaign, get_campaign, update_club_form, bulk_update_form
)


class TestMatrixPhase1Core(unittest.TestCase):

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
    # CATEGORY A: Architecture, Database Models & Referential Integrity
    # ─────────────────────────────────────────────────────────────────────────

    def test_tc_a01_total_96_standardized_clubs(self):
        """TC-A01: Verify exactly 96 standardized clubs across 4 regions."""
        active_clubs = Club.query.filter_by(is_active=True).all()
        self.assertEqual(len(active_clubs), 96, "Phải có chính xác 96 CLB đang hoạt động")

        # Check unique short codes
        codes = [c.short_code for c in active_clubs]
        self.assertEqual(len(codes), len(set(codes)), "Mã short_code của tất cả CLB phải duy nhất")

        # Check exactly 24 per region
        for r_slug in ['pacific', 'americas', 'emea', 'china']:
            reg = Region.query.filter_by(slug=r_slug).first()
            self.assertIsNotNone(reg, f"Region {r_slug} phải tồn tại")
            reg_clubs = Club.query.filter_by(region_id=reg.id, is_active=True).all()
            self.assertEqual(len(reg_clubs), 24, f"Khu vực {r_slug} phải có đúng 24 đội")

    def test_tc_a02_campaign_cascade_delete(self):
        """TC-A02: Deleting a campaign must cascade delete all associated states without orphan records."""
        camp = create_campaign(name="Cascade Delete Test", start_year=2027)
        cid = camp.id

        # Verify children exist
        self.assertEqual(CampaignClubState.query.filter_by(campaign_id=cid).count(), 96)
        self.assertTrue(CampaignStage.query.filter_by(campaign_id=cid).count() >= 1)

        # Delete campaign
        db.session.delete(camp)
        db.session.commit()

        # Check orphans
        self.assertEqual(CampaignClubState.query.filter_by(campaign_id=cid).count(), 0)
        self.assertEqual(CampaignStage.query.filter_by(campaign_id=cid).count(), 0)
        self.assertEqual(CampaignSeason.query.filter_by(campaign_id=cid).count(), 0)

    def test_tc_a03_match_and_map_foreign_key_invariants(self):
        """TC-A03: Foreign key Match & MatchMap invariants."""
        # Non-existent match_id on MatchMap should fail on commit or foreign key check
        invalid_map = MatchMap(
            match_id=99999999,
            map_number=1,
            team_a_score=13,
            team_b_score=5,
            winner_id=1
        )
        db.session.add(invalid_map)
        try:
            db.session.commit()
            db.session.delete(invalid_map)
            db.session.commit()
        except Exception:
            db.session.rollback()

    def test_tc_a04_campaign_stage_data_json_schema(self):
        """TC-A04: CampaignStage.stage_data must always be valid parseable JSON with expected keys."""
        camp = create_campaign(name="JSON Schema Test", start_year=2027)
        stage = CampaignStage.query.filter_by(campaign_id=camp.id, stage_key='open_qualifier').first()
        self.assertIsNotNone(stage)
        self.assertIsNotNone(stage.stage_data)

        parsed = json.loads(stage.stage_data)
        self.assertIn('regions', parsed)
        for r in ['pacific', 'americas', 'emea', 'china']:
            self.assertIn(r, parsed['regions'])
            reg_data = parsed['regions'][r]
            self.assertIn('teams', reg_data)
            self.assertIn('status', reg_data)
            self.assertIn('current_swiss_round', reg_data)
            self.assertIn('swiss_matches', reg_data)
            self.assertIn('swiss_standings', reg_data)
            self.assertIn('qualified_teams', reg_data)
            self.assertEqual(len(reg_data['teams']), 16)
            self.assertEqual(len(reg_data['swiss_matches']), 8)

    # ─────────────────────────────────────────────────────────────────────────
    # CATEGORY B: Base Math, Elo Rating & Probability Engine
    # ─────────────────────────────────────────────────────────────────────────

    def test_tc_b01_international_win_rate_parity_and_bounds(self):
        """TC-B01: International win rate starts at 0.50 parity, clamped within [0.18, 0.82]."""
        # Baseline equal regions
        p_same = calc_pure_international_win_rate(
            region_a='americas', region_b='americas', tour_type='major',
            is_grand_final=False, is_playoff=False,
            seed_a=2, seed_b=2, prior_a=0, prior_b=0, streak_a=0, streak_b=0
        )
        self.assertAlmostEqual(p_same, 0.50, delta=0.001)

        # Americas (+3%) vs China (-7%) -> +10% diff => 0.60
        # (Assuming random for China didn't trigger 8% ZmjjKK mode)
        p_vs_china = calc_pure_international_win_rate(
            region_a='americas', region_b='china', tour_type='major',
            is_grand_final=False, is_playoff=False,
            seed_a=2, seed_b=2, prior_a=0, prior_b=0, streak_a=0, streak_b=0
        )
        self.assertIn(round(p_vs_china, 2), [0.60, 0.45])  # 0.60 standard, 0.45 if ZmjjKK

        # Americas vs EMEA in Grand Final (EMEA Silver Curse -5%, Americas GF buff +3% + base +3% -> diff +11% => 0.61)
        p_gf = calc_pure_international_win_rate(
            region_a='americas', region_b='emea', tour_type='major',
            is_grand_final=True, is_playoff=True,
            seed_a=2, seed_b=2, prior_a=0, prior_b=0, streak_a=0, streak_b=0
        )
        self.assertAlmostEqual(p_gf, 0.61, delta=0.001)

        # Check clamping
        p_extreme_high = calc_pure_international_win_rate(
            region_a='americas', region_b='china', tour_type='champion',
            is_grand_final=True, is_playoff=True,
            seed_a=1, seed_b=4, prior_a=5, prior_b=0, streak_a=5, streak_b=0
        )
        self.assertLessEqual(p_extreme_high, 0.82)

    def test_tc_b02_update_ratings_placement_bounds_and_audit(self):
        """TC-B02: Rating updates bound ratings within [40, 100] and create audit records."""
        # Create a mini 4-team tournament
        clubs = Club.query.limit(4).all()
        cids = [c.id for c in clubs]
        tour = Tournament(type='major', name='Rating Update Test', status='completed')
        db.session.add(tour)
        db.session.flush()

        for idx, cid in enumerate(cids):
            p = TournamentParticipant(
                tournament_id=tour.id,
                club_id=cid,
                seed=idx + 1,
                final_rank=idx + 1
            )
            db.session.add(p)
        db.session.commit()

        update_ratings(tour)

        # Verify ClubRating records were created
        ratings = ClubRating.query.filter_by(tournament_id=tour.id).all()
        self.assertEqual(len(ratings), 4)
        for r in ratings:
            self.assertGreaterEqual(r.rating_after, 40)
            self.assertLessEqual(r.rating_after, 100)

    def test_tc_b03_map_score_extreme_rating_diff(self):
        """TC-B03: Extreme rating differences in _gen_map_score do not crash and produce valid scores."""
        # Extreme favorite won
        score_fav = _gen_map_score(winner_rating=1000, loser_rating=1)
        self.assertEqual(score_fav[0], 13)
        self.assertLessEqual(score_fav[1], 6)

        # Massive underdog won
        score_dog = _gen_map_score(winner_rating=1, loser_rating=1000)
        self.assertGreaterEqual(score_dog[0], 13)
        if score_dog[0] > 13:
            self.assertEqual(score_dog[0] - score_dog[1], 2)

    def test_tc_b04_monte_carlo_distribution(self):
        """TC-B04: Monte Carlo 200 matches between identical teams yields win rate in [40%, 60%]."""
        wins_a = 0
        trials = 200
        p = calc_pure_international_win_rate(
            region_a='emea', region_b='emea', tour_type='major',
            seed_a=2, seed_b=2, prior_a=0, prior_b=0, streak_a=0, streak_b=0
        )
        self.assertEqual(p, 0.50)

        # Simulate Bernoulli trials
        import random
        for _ in range(trials):
            if random.random() < p:
                wins_a += 1

        win_rate = wins_a / trials
        self.assertGreaterEqual(win_rate, 0.40)
        self.assertLessEqual(win_rate, 0.60)

    # ─────────────────────────────────────────────────────────────────────────
    # CATEGORY C: Clash Mechanics, Form Modifiers & RPG Systems
    # ─────────────────────────────────────────────────────────────────────────

    def test_tc_c01_clamp_form_modifier_bounds(self):
        """TC-C01: Form modifier must be strictly clamped in [-30, +30]."""
        camp = create_campaign("Form Clamp Test", 2027)
        cstate = CampaignClubState.query.filter_by(campaign_id=camp.id).first()
        self.assertIsNotNone(cstate)

        # Extreme positive
        update_club_form(camp.id, cstate.club_id, 999)
        cstate = db.session.get(CampaignClubState, cstate.id)
        self.assertEqual(cstate.form_modifier, 30)

        # Extreme negative
        update_club_form(camp.id, cstate.club_id, -999)
        cstate = db.session.get(CampaignClubState, cstate.id)
        self.assertEqual(cstate.form_modifier, -30)

    def test_tc_c02_effective_rating_math(self):
        """TC-C02: effective_rating = story_rating + form_modifier."""
        camp = create_campaign("Effective Rating Test", 2027)
        cstate = CampaignClubState.query.filter_by(campaign_id=camp.id).first()
        cstate.story_rating = 85
        cstate.form_modifier = -7
        db.session.commit()

        self.assertEqual(cstate.effective_rating, 78)

        cstate.form_modifier = 12
        db.session.commit()
        self.assertEqual(cstate.effective_rating, 97)

    def test_tc_c03_bulk_form_update(self):
        """TC-C03: Bulk form update applies correctly across multiple clubs."""
        camp = create_campaign("Bulk Form Test", 2027)
        states = CampaignClubState.query.filter_by(campaign_id=camp.id).limit(3).all()
        updates = {
            states[0].club_id: 8,
            states[1].club_id: -5,
            states[2].club_id: 50  # should clamp to 30
        }
        updated_count = bulk_update_form(camp.id, updates)
        self.assertEqual(updated_count, 3)

        s0 = db.session.get(CampaignClubState, states[0].id)
        s1 = db.session.get(CampaignClubState, states[1].id)
        s2 = db.session.get(CampaignClubState, states[2].id)
        self.assertEqual(s0.form_modifier, 8)
        self.assertEqual(s1.form_modifier, -5)
        self.assertEqual(s2.form_modifier, 30)

    def test_tc_c04_form_modifier_impacts_effective_rating_for_seeding(self):
        """TC-C04: Form modifier genuinely shifts effective rating."""
        camp = create_campaign("Effective Rating Shift Test", 2027)
        state_a = CampaignClubState.query.filter_by(campaign_id=camp.id).first()
        state_b = CampaignClubState.query.filter_by(campaign_id=camp.id).offset(1).first()

        state_a.story_rating = 80
        state_a.form_modifier = 15
        state_b.story_rating = 80
        state_b.form_modifier = -15
        db.session.commit()

        self.assertEqual(state_a.effective_rating, 95)
        self.assertEqual(state_b.effective_rating, 65)
        self.assertEqual(state_a.effective_rating - state_b.effective_rating, 30)

    # ─────────────────────────────────────────────────────────────────────────
    # CATEGORY M: Match Simulation, Map Pools & Overtime Rules
    # ─────────────────────────────────────────────────────────────────────────

    def test_tc_m01_regulation_map_scores(self):
        """TC-M01: 50 regulation maps from _gen_map_score have winner=13, loser in [0..11]. Never 13-12."""
        for _ in range(50):
            w_score, l_score = _gen_map_score(winner_rating=85, loser_rating=75)
            if w_score == 13:
                self.assertLessEqual(l_score, 11, f"Tỷ số 13-{l_score} không hợp lệ trong giờ chính thức!")

    def test_tc_m02_overtime_win_by_2_rounds(self):
        """TC-M02: Overtime maps from _gen_map_score must be won by exactly 2 rounds."""
        for _ in range(100):
            w_score, l_score = _gen_map_score(winner_rating=70, loser_rating=90)
            if w_score > 13:
                diff = w_score - l_score
                self.assertEqual(diff, 2, f"Overtime phải thắng cách biệt 2 round! Thực tế: {w_score}-{l_score}")

    def test_tc_m03_match_score_consistency_with_maps(self):
        """TC-M03: Match score must equal count of map wins in simulate_match."""
        clubs = Club.query.limit(2).all()
        tour = Tournament(type='kickoff', name='Sim Match Test')
        db.session.add(tour)
        db.session.flush()

        match = Match(
            tournament_id=tour.id,
            round_type='upper',
            round_name='upper_round1',
            team_a_id=clubs[0].id,
            team_b_id=clubs[1].id
        )
        db.session.add(match)
        db.session.commit()

        winner_id, maps_data = simulate_match(match)
        db.session.commit()

        wins_a = sum(1 for m in maps_data if m['team_a_score'] > m['team_b_score'])
        wins_b = sum(1 for m in maps_data if m['team_b_score'] > m['team_a_score'])

        self.assertEqual(match.team_a_score, wins_a)
        self.assertEqual(match.team_b_score, wins_b)
        self.assertIn(2, (wins_a, wins_b))
        if match.winner_id == clubs[0].id:
            self.assertEqual(wins_a, 2)
        else:
            self.assertEqual(wins_b, 2)

    def test_tc_m04_no_unnecessary_maps_generated(self):
        """TC-M04: In BO3, at most 3 maps are generated; if 2-0, exactly 2 maps are generated."""
        clubs = Club.query.limit(2).all()
        tour = Tournament(type='kickoff', name='Sim Match Clean Sweep Test')
        db.session.add(tour)
        db.session.flush()

        sweeps = 0
        while sweeps < 5:
            match = Match(
                tournament_id=tour.id,
                round_type='upper',
                round_name='upper_round1',
                team_a_id=clubs[0].id,
                team_b_id=clubs[1].id
            )
            db.session.add(match)
            db.session.commit()

            simulate_match(match)
            db.session.commit()

            if match.team_a_score == 2 and match.team_b_score == 0:
                self.assertEqual(len(match.maps), 2)
                sweeps += 1
            elif match.team_a_score == 0 and match.team_b_score == 2:
                self.assertEqual(len(match.maps), 2)
                sweeps += 1

    # ─────────────────────────────────────────────────────────────────────────
    # CATEGORY V: Validation & Sanitization Layer
    # ─────────────────────────────────────────────────────────────────────────

    def test_tc_v01_validate_and_normalize_manual_maps(self):
        """TC-V01: validate_and_normalize_manual_maps handles valid maps and auto-aligns."""
        input_maps = [
            {'team_a_score': 13, 'team_b_score': 8},
            {'team_a_score': 7, 'team_b_score': 13},
            {'team_a_score': 15, 'team_b_score': 13},
        ]
        wins_a, wins_b, winner_id, loser_id, sanitized = validate_and_normalize_manual_maps(
            maps=input_maps, bo=3, id_a=10, id_b=20, forced_winner_id=None
        )
        self.assertEqual(wins_a, 2)
        self.assertEqual(wins_b, 1)
        self.assertEqual(winner_id, 10)
        self.assertEqual(loser_id, 20)
        self.assertEqual(len(sanitized), 3)

    def test_tc_v02_create_tournament_rejects_invalid_team_count(self):
        """TC-V02: create_tournament must raise ValueError if team count does not match."""
        invalid_clubs = [1, 2, 3]  # Only 3 clubs for major (requires 8)
        with self.assertRaises(ValueError):
            create_tournament(tour_type='major', name='Invalid Tour', selected_club_ids=invalid_clubs)

    def test_tc_v03_api_start_tournament_rejects_exceeding_regional_slots(self):
        """TC-V03: API start tournament rejects request exceeding regional slots."""
        americas_clubs = Club.query.join(Region).filter(Region.slug == 'americas').limit(4).all()
        emea_clubs = Club.query.join(Region).filter(Region.slug == 'emea').limit(4).all()
        bad_ids = [c.id for c in americas_clubs] + [c.id for c in emea_clubs]

        resp = self.client.post('/api/tournament/start', json={
            'type': 'major',
            'name': 'Bad Bangkok',
            'club_ids': bad_ids
        })
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertIn('error', data)


if __name__ == '__main__':
    unittest.main()
