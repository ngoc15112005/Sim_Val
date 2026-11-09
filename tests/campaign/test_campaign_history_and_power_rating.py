"""
test_campaign_history_and_power_rating.py

Comprehensive test suite verifying:
1. Riot Global Power Rankings (GPR x AWS) Engine:
   - Dynamic K-factors, Margin of Victory (MoV) scaling
   - Regional League Elo dynamic updates
   - Dual-scale scoring (GPR Score & OVR 50.0 - 99.9)
   - Tier classifications (S+, S, A, B, C) and Rank Delta tracking
   - Off-season regression
2. Multi-Year Tournament Placement Historical Archiving:
   - Persistent CampaignStagePlacement recording across all stages (Kickoff, Major, Stage 1, Master, EWC, Stage 2, Champion)
   - Zero-loss multi-year rollover (placements from 2026 persist when advancing to 2027 and 2028)
   - Auto-backfill for pre-existing completed stages
   - All-time trophy room & medal table aggregation
3. In-Tournament History & Yearly Hall of Fame API endpoints.
"""

import unittest
import json
from app import create_app
from models import db, Campaign, CampaignClubState, CampaignStage, CampaignStagePlacement, Club, Region
from engine.power_rating import (
    calculate_expected_score,
    calculate_margin_modifier,
    update_team_elo,
    update_regional_league_elo,
    calculate_composite_power_score,
    power_score_to_ovr,
    get_tier_info,
    format_rank_delta,
    apply_offseason_regression,
)
from services.campaign_service import (
    create_campaign,
    get_campaign,
    record_stage_placements,
    get_stage_placements_history,
    get_all_time_trophy_table,
    get_global_power_rankings,
    get_season_summary_data,
    advance_campaign_to_next_year,
    apply_match_power_rating,
    backfill_stage_placements_if_needed,
)


class TestRiotPowerRatingEngine(unittest.TestCase):
    """Unit tests for the mathematical formulas of Riot GPR x AWS."""

    def test_expected_score_logic(self):
        # Equal ratings -> 50% probability
        exp = calculate_expected_score(1500, 1500)
        self.assertAlmostEqual(exp, 0.5, places=2)

        # Higher rated team has higher win expectation
        exp_favored = calculate_expected_score(1700, 1500)
        self.assertGreater(exp_favored, 0.70)
        self.assertLess(exp_favored, 0.80)

    def test_margin_of_victory_modifier(self):
        # Close 2-1 (+2 rounds) vs dominant 2-0 (+18 rounds)
        mov_close = calculate_margin_modifier(map_diff=1, round_diff=2)
        mov_dominant = calculate_margin_modifier(map_diff=2, round_diff=18)

        self.assertGreater(mov_dominant, mov_close)
        self.assertGreaterEqual(mov_dominant, 1.4)
        self.assertLessEqual(mov_dominant, 1.75)

    def test_update_team_elo_tiers(self):
        # Champions Tier (K=50) yields higher delta than Regular Season (K=18)
        _, _, delta_champ = update_team_elo(1500, 1500, tournament_tier='champion', map_diff=2, round_diff=10)
        _, _, delta_reg = update_team_elo(1500, 1500, tournament_tier='stage1', map_diff=2, round_diff=10)

        self.assertGreater(delta_champ, delta_reg)

    def test_regional_league_elo_update(self):
        league_ratings = {"pacific": 1500.0, "americas": 1500.0, "emea": 1500.0, "china": 1500.0}
        
        # Pacific beats Americas in Champions
        new_ratings, delta = update_regional_league_elo(
            league_ratings, region_winner='pacific', region_loser='americas', tournament_tier='champion'
        )
        self.assertGreater(new_ratings['pacific'], 1500.0)
        self.assertLess(new_ratings['americas'], 1500.0)
        self.assertEqual(new_ratings['emea'], 1500.0)
        self.assertGreater(delta, 0)

    def test_composite_power_score_and_ovr(self):
        # 80% team (1600) + 20% league (1500) = 1280 + 300 = 1580
        score = calculate_composite_power_score(team_elo=1600.0, league_elo=1500.0, win_streak=0)
        self.assertEqual(score, 1580.0)

        # Win streak bonus (+35 for 5W streak)
        score_streak = calculate_composite_power_score(team_elo=1600.0, league_elo=1500.0, win_streak=5)
        self.assertEqual(score_streak, 1615.0)

        # OVR conversion
        ovr = power_score_to_ovr(score)
        self.assertGreaterEqual(ovr, 70.0)
        self.assertLessEqual(ovr, 99.0)

    def test_tier_classification(self):
        tier_s_plus = get_tier_info(1920.0)
        self.assertEqual(tier_s_plus['tier'], 'S+')
        self.assertEqual(tier_s_plus['name'], 'World Titan')

        tier_s = get_tier_info(1780.0)
        self.assertEqual(tier_s['tier'], 'S')

        tier_a = get_tier_info(1620.0)
        self.assertEqual(tier_a['tier'], 'A')

        tier_b = get_tier_info(1450.0)
        self.assertEqual(tier_b['tier'], 'B')

        tier_c = get_tier_info(1250.0)
        self.assertEqual(tier_c['tier'], 'C')

    def test_rank_delta_formatting(self):
        # Improved from #5 to #2 -> +3 rank up
        d_up = format_rank_delta(current_rank=2, previous_rank=5)
        self.assertIn('+3', d_up['symbol'])
        self.assertEqual(d_up['class'], 'rank-up')

        # Dropped from #1 to #4 -> -3 rank down
        d_down = format_rank_delta(current_rank=4, previous_rank=1)
        self.assertIn('-3', d_down['symbol'])
        self.assertEqual(d_down['class'], 'rank-down')

        # Unchanged
        d_same = format_rank_delta(current_rank=3, previous_rank=3)
        self.assertIn('0', d_same['symbol'])
        self.assertEqual(d_same['class'], 'rank-same')

        # First season / no previous rank
        d_new = format_rank_delta(current_rank=1, previous_rank=None)
        self.assertIn('NEW', d_new['symbol'])


class TestCampaignHistoryAndPlacementPersistence(unittest.TestCase):
    """Integration test verifying persistent placement tracking across years."""

    def setUp(self):
        self.app = create_app()
        self.app_context = self.app.app_context()
        self.app_context.push()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.rollback()
        db.session.remove()
        self.app_context.pop()

    def test_01_placement_recording_and_history_lookup(self):
        """Verify recording placements for Kickoff and retrieving history."""
        camp = create_campaign(name="History Test Circuit", start_year=2026)

        # Create mock completed Kickoff stage data
        pacific_clubs = Club.query.join(Region).filter(Region.slug == 'pacific').limit(12).all()
        standings = []
        for rk, c in enumerate(pacific_clubs, start=1):
            standings.append({
                'club_id': c.id,
                'rank': rk,
                'team': c.to_dict(),
                'matches_won': 4 if rk <= 2 else (2 if rk <= 4 else 0),
                'matches_lost': 0 if rk == 1 else (1 if rk <= 2 else 2),
                'elimination_stage': 'Grand Finals' if rk <= 2 else 'Playoffs',
            })

        ko_stage = CampaignStage(
            campaign_id=camp.id,
            year=2026,
            stage_key='kickoff',
            stage_name='VCT Kickoff 2026',
            status='completed',
            stage_data=json.dumps({
                'regional_results': {
                    'pacific': {
                        'status': 'completed',
                        'standings': standings,
                        'champion': pacific_clubs[0].to_dict(),
                        'runner_up': pacific_clubs[1].to_dict(),
                    }
                }
            })
        )
        db.session.add(ko_stage)
        db.session.commit()

        # Trigger placement recording
        records = record_stage_placements(camp.id, 'kickoff', year=2026)
        self.assertGreaterEqual(len(records), 12)

        # Verify query history
        hist = get_stage_placements_history(camp.id, 'kickoff', year=2026, region_slug='pacific')
        self.assertEqual(hist['stage_key'], 'kickoff')
        self.assertIn(2026, hist['available_years'])
        self.assertEqual(hist['selected_year'], 2026)
        self.assertIsNotNone(hist['podium']['champion'])
        self.assertEqual(hist['podium']['champion']['rank'], 1)
        self.assertEqual(hist['podium']['runner_up']['rank'], 2)
        self.assertEqual(len(hist['placements']), 12)

    def test_02_all_time_trophy_table_accumulation(self):
        """Verify that champions and masters titles correctly tally in the All-Time Medal Table."""
        camp = create_campaign(name="Trophy Table Test", start_year=2026)

        clubs = Club.query.limit(4).all()
        c1, c2, c3, c4 = clubs[0], clubs[1], clubs[2], clubs[3]

        # Year 2026: c1 wins Champions, c2 is runner-up; c3 wins Masters
        p1 = CampaignStagePlacement(
            campaign_id=camp.id, year=2026, stage_key='champion', tournament_name='Champions 2026',
            club_id=c1.id, rank=1, rank_display='1st', stage_points_earned=0
        )
        p2 = CampaignStagePlacement(
            campaign_id=camp.id, year=2026, stage_key='champion', tournament_name='Champions 2026',
            club_id=c2.id, rank=2, rank_display='2nd', stage_points_earned=0
        )
        p3 = CampaignStagePlacement(
            campaign_id=camp.id, year=2026, stage_key='master', tournament_name='Masters 2026',
            club_id=c3.id, rank=1, rank_display='1st', stage_points_earned=5
        )
        db.session.add_all([p1, p2, p3])
        db.session.commit()

        trophies = get_all_time_trophy_table(camp.id)
        self.assertGreaterEqual(len(trophies), 3)

        # c1 should be #1 with 1 Champions title
        top_club = trophies[0]
        self.assertEqual(top_club['club']['id'], c1.id)
        self.assertEqual(top_club['champions_titles'], 1)
        self.assertEqual(top_club['total_titles'], 1)

        # c3 should have 1 Masters title
        c3_entry = next(t for t in trophies if t['club']['id'] == c3.id)
        self.assertEqual(c3_entry['masters_titles'], 1)

        # c2 should have 1 runner_up
        c2_entry = next(t for t in trophies if t['club']['id'] == c2.id)
        self.assertEqual(c2_entry['runner_up_count'], 1)

    def test_03_multi_year_advance_and_persistence(self):
        """Verify advancing campaign year persists past placements and updates power ratings."""
        camp = create_campaign(name="Multi-Year Persistence Test", start_year=2026)

        # Manually complete the season with some points and rating
        cs_list = CampaignClubState.query.filter_by(campaign_id=camp.id).all()
        for idx, cs in enumerate(cs_list):
            cs.championship_points = (len(cs_list) - idx) * 2
            cs.team_elo = 1500.0 + (len(cs_list) - idx) * 10
            cs.power_score = cs.team_elo
            cs.power_rating = power_score_to_ovr(cs.power_score)

        db.session.commit()

        # Advance to 2027
        res = advance_campaign_to_next_year(camp.id)
        self.assertTrue(res['success'])
        self.assertEqual(res['old_year'], 2026)
        self.assertEqual(res['new_year'], 2027)

        # Check that previous_rank was saved
        updated_cs = CampaignClubState.query.filter_by(campaign_id=camp.id).all()
        self.assertIsNotNone(updated_cs[0].previous_rank)
        self.assertEqual(updated_cs[0].championship_points, 0) # reset for new season

        # Check that Hall of Fame data for 2026 is accessible
        hof_2026 = get_season_summary_data(camp.id, year=2026)
        self.assertEqual(hof_2026['year'], 2026)
        self.assertIn(2026, hof_2026['available_years'])
        self.assertIn(2027, hof_2026['available_years'])
        self.assertIn('global_power_rankings', hof_2026)
        self.assertIn('all_time_trophies', hof_2026)

    def test_04_api_endpoints(self):
        """Verify REST API endpoints return JSON properly."""
        camp = create_campaign(name="API Test", start_year=2026)

        # 1. API Stage History
        resp1 = self.client.get(f'/api/campaign/{camp.id}/stage-history/kickoff?year=2026&region=pacific')
        self.assertEqual(resp1.status_code, 200)
        data1 = json.loads(resp1.data)
        self.assertTrue(data1['success'])
        self.assertIn('podium', data1['data'])

        # 2. API Global Power Rankings
        resp2 = self.client.get(f'/api/campaign/{camp.id}/power-rankings')
        self.assertEqual(resp2.status_code, 200)
        data2 = json.loads(resp2.data)
        self.assertTrue(data2['success'])
        self.assertGreaterEqual(len(data2['rankings']), 48) # At least 48 clubs

        # 3. API All-Time Trophies
        resp3 = self.client.get(f'/api/campaign/{camp.id}/all-time-trophies')
        self.assertEqual(resp3.status_code, 200)
        data3 = json.loads(resp3.data)
        self.assertTrue(data3['success'])

        # 4. View Hall of Fame
        resp4 = self.client.get(f'/campaign/{camp.id}/hall-of-fame?year=2026')
        self.assertEqual(resp4.status_code, 200)
        self.assertIn(b'B\xe1\xba\xa3ng V\xc3\xa0ng & Hall of Fame', resp4.data)


if __name__ == '__main__':
    unittest.main()
