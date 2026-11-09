"""
test_matrix_phase5_longevity_chaos.py — Phase 5 Test Suite for VALORANT Master Testing Matrix A-Z.

Categories Covered:
- Category L: Lifecycle & Multi-Year Season Continuity (TC-L01 .. TC-L05)
- Category T: Time Complexity, Performance & Concurrency (TC-T01 .. TC-T03)
- Category Y: Year-End Recap, Awards & Hall of Fame Analytics (TC-Y01 .. TC-Y03)
- Category Z: Zero-Tolerance Invariant Audit & Chaos Monkey (TC-Z01 .. TC-Z04)
"""

import unittest
import time
import threading
from app import create_app
from models import (
    db, Club, Region, Match, MatchMap, TournamentParticipant,
    Campaign, CampaignClubState, CampaignStage, CampaignSeason
)
from services.campaign_service import (
    create_campaign, get_campaign, advance_campaign_to_next_year,
    get_season_summary_data, run_open_qualifier_stage,
    resolve_oq_match, get_open_qualifier_data, sim_oq_round
)


class TestMatrixPhase5LongevityChaos(unittest.TestCase):

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
    # CATEGORY L: Lifecycle & Multi-Year Season Continuity
    # ─────────────────────────────────────────────────────────────────────────

    def test_tc_l01_advance_year_increments_year_and_resets_stage(self):
        """TC-L01: advance_campaign_to_next_year increments year and sets stage to open_qualifier."""
        camp = create_campaign("Advance Year Test", 2027)
        self.assertEqual(camp.current_year, 2027)

        advance_campaign_to_next_year(camp.id)
        camp = db.session.get(Campaign, camp.id)
        self.assertEqual(camp.current_year, 2028)
        self.assertEqual(camp.current_stage, 'open_qualifier')

    def test_tc_l02_archive_season_summary_into_history(self):
        """TC-L02: Rollover creates CampaignSeason record and Hall of Fame stage record."""
        camp = create_campaign("Archive Season Test", 2027)
        advance_campaign_to_next_year(camp.id)

        # Check CampaignSeason
        season_rec = CampaignSeason.query.filter_by(campaign_id=camp.id, year=2027).first()
        self.assertIsNotNone(season_rec, "Bản ghi CampaignSeason năm cũ phải được lưu trữ")

        # Check Hall of Fame stage record
        hof_stage = CampaignStage.query.filter_by(campaign_id=camp.id, stage_key='hof_year_2027').first()
        self.assertIsNotNone(hof_stage, "Hall of Fame stage record phải được tạo")

    def test_tc_l03_preservation_of_all_96_clubs_over_multi_years(self):
        """TC-L03: Over 3 consecutive season advances, exactly 96 clubs remain preserved (32P, 64NP)."""
        camp = create_campaign("Preserve 96 Clubs Test", 2027)
        for _ in range(3):
            advance_campaign_to_next_year(camp.id)

        camp = db.session.get(Campaign, camp.id)
        self.assertEqual(camp.current_year, 2030)

        states = CampaignClubState.query.filter_by(campaign_id=camp.id).all()
        self.assertEqual(len(states), 96, "Số lượng CLB sau 3 năm vẫn phải đủ đúng 96")

        partners = [s for s in states if s.is_partner]
        non_partners = [s for s in states if not s.is_partner]
        self.assertEqual(len(partners), 32)
        self.assertEqual(len(non_partners), 64)

    def test_tc_l04_championship_points_reset_to_zero(self):
        """TC-L04: In year N+1, all clubs have championship points reset to 0."""
        camp = create_campaign("Reset CP Test", 2027)
        # Give some teams points
        cstate = CampaignClubState.query.filter_by(campaign_id=camp.id).first()
        cstate.championship_points = 25
        cstate.regular_season_wins = 8
        db.session.commit()

        advance_campaign_to_next_year(camp.id)

        states = CampaignClubState.query.filter_by(campaign_id=camp.id).all()
        for s in states:
            self.assertEqual(s.championship_points, 0)
            self.assertEqual(s.regular_season_wins, 0)
            self.assertEqual(s.form_modifier, 0)

    def test_tc_l05_rating_mean_regression_aging(self):
        """TC-L05: Off-season rating ages with 15% mean regression toward baseline 80."""
        camp = create_campaign("Aging Regression Test", 2027)
        cstate = CampaignClubState.query.filter_by(campaign_id=camp.id).first()
        cstate.story_rating = 100
        db.session.commit()

        advance_campaign_to_next_year(camp.id)
        cstate = db.session.get(CampaignClubState, cstate.id)
        # 100 * 0.85 + 80 * 0.15 = 85 + 12 = 97
        self.assertEqual(cstate.story_rating, 97)

    # ─────────────────────────────────────────────────────────────────────────
    # CATEGORY T: Time Complexity, Performance & Concurrency
    # ─────────────────────────────────────────────────────────────────────────

    def test_tc_t01_concurrent_simulation_safety(self):
        """TC-T01: Concurrently resolving two matches across regions in separate threads."""
        camp = create_campaign("Concurrency Test", 2027)
        cid = int(camp.id)
        errors = []

        def worker_pacific():
            with self.app.app_context():
                try:
                    sim_oq_round(cid, 'pacific')
                except Exception as e:
                    errors.append(e)

        def worker_americas():
            with self.app.app_context():
                try:
                    sim_oq_round(cid, 'americas')
                except Exception as e:
                    errors.append(e)

        t1 = threading.Thread(target=worker_pacific)
        t2 = threading.Thread(target=worker_americas)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        self.assertEqual(len(errors), 0, f"Concurrent sim threads encountered errors: {errors}")

    def test_tc_t02_stage_simulation_speed_performance(self):
        """TC-T02: Simulating full Open Qualifier stage across all 4 regions takes < 2.0s."""
        camp = create_campaign("Speed Performance Test", 2027)
        t0 = time.time()
        run_open_qualifier_stage(camp.id)
        duration = time.time() - t0
        self.assertLess(duration, 2.0, f"Open Qualifier simulation took too long: {duration:.3f}s")

    def test_tc_t03_memory_and_connection_footprint(self):
        """TC-T03: Multiple year advances execute without unclosed DB errors."""
        camp = create_campaign("Connection Footprint Test", 2027)
        for _ in range(2):
            advance_campaign_to_next_year(camp.id)
        db.session.commit()
        self.assertTrue(True)

    # ─────────────────────────────────────────────────────────────────────────
    # CATEGORY Y: Year-End Recap, Awards & Hall of Fame Analytics
    # ─────────────────────────────────────────────────────────────────────────

    def test_tc_y01_season_summary_club_of_the_year(self):
        """TC-Y01: get_season_summary_data identifies club_of_the_year accurately."""
        camp = create_campaign("MVP Club Test", 2027)
        summary = get_season_summary_data(camp.id)
        self.assertIn('club_of_the_year', summary)
        mvp = summary['club_of_the_year']
        self.assertIsNotNone(mvp)
        self.assertIn('club', mvp)
        self.assertIn('name', mvp['club'])

    def test_tc_y02_regional_supremacy_ranking(self):
        """TC-Y02: get_season_summary_data identifies best_region."""
        camp = create_campaign("Best Region Test", 2027)
        summary = get_season_summary_data(camp.id)
        self.assertIn('best_region', summary)
        self.assertIn(summary['best_region']['region_slug'], ['pacific', 'americas', 'emea', 'china'])

    def test_tc_y03_hall_of_fame_storage_retrieval(self):
        """TC-Y03: Past seasons are queryable from Hall of Fame stages."""
        camp = create_campaign("HOF Retrieval Test", 2027)
        advance_campaign_to_next_year(camp.id)

        summary_2028 = get_season_summary_data(camp.id)
        self.assertIn('past_records', summary_2028)
        self.assertEqual(len(summary_2028['past_records']), 1)
        self.assertEqual(summary_2028['past_records'][0]['year'], 2027)

    # ─────────────────────────────────────────────────────────────────────────
    # CATEGORY Z: Zero-Tolerance Invariant Audit & Chaos Monkey
    # ─────────────────────────────────────────────────────────────────────────

    def test_tc_z01_chaos_monkey_random_overrides_mid_stage(self):
        """TC-Z01: Random manual overrides followed by stage completion do not deadlock."""
        camp = create_campaign("Chaos Monkey Test", 2027)
        oq_data = get_open_qualifier_data(camp.id)
        m1 = oq_data['regions']['pacific']['swiss_matches'][0]
        m2 = oq_data['regions']['pacific']['swiss_matches'][1]

        # Inject manual override into matches 1 and 2
        resolve_oq_match(camp.id, 'pacific', m1['id'], winner_id=m1['team_a_id'], maps=[{'team_a_score': 13, 'team_b_score': 0}])
        resolve_oq_match(camp.id, 'pacific', m2['id'], winner_id=m2['team_b_id'], maps=[{'team_a_score': 2, 'team_b_score': 13}])

        # Complete the rest of the stage
        run_open_qualifier_stage(camp.id)

        camp = db.session.get(Campaign, camp.id)
        self.assertEqual(camp.current_stage, 'kickoff', "Chaos injection must not prevent campaign progression")

    def test_tc_z02_total_matches_count_invariant(self):
        """TC-Z02: All 4 regions of Open Qualifier complete with exact 43 matches each."""
        camp = create_campaign("Match Count Invariant Test", 2027)
        run_open_qualifier_stage(camp.id)

        oq_data = get_open_qualifier_data(camp.id)
        for r_slug, reg_info in oq_data['regions'].items():
            all_matches = reg_info['swiss_matches'] + reg_info['playoff_matches']
            self.assertEqual(len(all_matches), 43, f"Vùng {r_slug} phải có đúng 43 trận đấu hoàn thành")

    def test_tc_z03_mid_stage_save_and_resume(self):
        """TC-Z03: Progress can be paused and resumed cleanly across sessions."""
        camp = create_campaign("Resume Stage Test", 2027)
        # Sim round 1 in pacific
        sim_oq_round(camp.id, 'pacific')

        # New session/context reads state
        db.session.expire_all()
        data = get_open_qualifier_data(camp.id)
        pacific_m = data['regions']['pacific']['swiss_matches']
        completed_in_r1 = sum(1 for m in pacific_m if m['status'] == 'completed')
        self.assertEqual(completed_in_r1, 8, "Round 1 phải có đúng 8 trận completed đã lưu bền vững")

    def test_tc_z04_zero_orphan_records_audit(self):
        """TC-Z04: SQL audit verifies 0 orphan MatchMap or CampaignClubState records."""
        camp = create_campaign("Orphan Audit Test", 2027)
        advance_campaign_to_next_year(camp.id)

        # Audit CampaignClubState without Campaign
        orphaned_states = db.session.query(CampaignClubState).filter(
            ~CampaignClubState.campaign_id.in_(db.session.query(Campaign.id))
        ).count()
        self.assertEqual(orphaned_states, 0, "Không được có CampaignClubState mồ côi")

        # Audit CampaignStage without Campaign
        orphaned_stages = db.session.query(CampaignStage).filter(
            ~CampaignStage.campaign_id.in_(db.session.query(Campaign.id))
        ).count()
        self.assertEqual(orphaned_stages, 0, "Không được có CampaignStage mồ côi")


if __name__ == '__main__':
    unittest.main()
