"""
test_team_profile_and_dossier.py

Comprehensive test suite verifying:
1. Liquipedia-style Team Profile / Scouting Dossier Backend Service (`get_team_profile_data`):
   - Global Rank, Regional Rank, GPR Power Score, OVR Rating, Tier & Rank Delta
   - Trophy Cabinet aggregation (Champions, Masters, EWC, Regional titles, Runners-up, Finals)
   - Career Lifetime Stats (Total tournaments, W-L records, Win Rate %, Lifetime CP, International appearances)
   - Radar Attributes (Firepower, Strategy, Clutch, Consistency in 60-99 range)
   - Team DNA & Automated Scouting Assessment based on Tier and Win Streaks
   - Multi-stage Tournament Results history (Liquipedia format)
   - Head-to-head recent matches extraction
2. Web View & REST API Endpoints:
   - GET /campaign/<id>/team/<club_id> (HTML 200 with full dossier view)
   - GET /api/campaign/<id>/team/<club_id> (JSON 200 with complete profile structure)
   - 404 handling for invalid campaign or club IDs
"""

import unittest
import json
from app import create_app
from models import db, Campaign, CampaignClubState, CampaignStage, CampaignStagePlacement, Club, Region
from services.campaign_service import (
    create_campaign,
    get_team_profile_data,
    record_stage_placements,
    _extract_recent_matches_for_club,
)


class TestTeamProfileService(unittest.TestCase):
    """Tests for Liquipedia Dossier data extraction and evaluation."""

    def setUp(self):
        self.app = create_app()
        self.app_context = self.app.app_context()
        self.app_context.push()
        self.client = self.app.test_client()

        # Create a fresh campaign
        self.campaign = create_campaign(name="VCT Profile Test Circuit", start_year=2026)
        self.campaign_id = self.campaign.id

        # Fetch clubs in campaign
        self.pacific_clubs = Club.query.join(Region).filter(Region.slug == 'pacific').all()
        self.assertTrue(len(self.pacific_clubs) > 0, "Pacific clubs should exist")
        self.club = self.pacific_clubs[0]
        self.club_id = self.club.id

    def tearDown(self):
        db.session.rollback()
        db.session.remove()
        self.app_context.pop()

    def test_get_team_profile_basic_structure(self):
        """Verify get_team_profile_data returns all essential keys and structures."""
        data = get_team_profile_data(self.campaign_id, self.club_id)
        self.assertIsNotNone(data)

        # Check top-level keys
        expected_keys = [
            'club', 'campaign_id', 'year', 'state', 'rankings',
            'trophy_cabinet', 'career_stats', 'evaluation',
            'recent_matches', 'tournament_results'
        ]
        for k in expected_keys:
            self.assertIn(k, data, f"Key '{k}' must exist in team profile data")

        # Club Identity
        self.assertEqual(data['club']['id'], self.club_id)
        self.assertEqual(data['club']['name'], self.club.name)

        # Rankings
        rankings = data['rankings']
        self.assertIsInstance(rankings['global_rank'], int)
        self.assertGreaterEqual(rankings['global_rank'], 1)
        self.assertIsInstance(rankings['regional_rank'], int)
        self.assertGreaterEqual(rankings['regional_rank'], 1)
        self.assertIn('tier', rankings)
        self.assertIn('badge', rankings['tier'])
        self.assertIn('name', rankings['tier'])
        self.assertIn('power_score', rankings)
        self.assertIn('power_rating', rankings)
        self.assertIn('rank_delta', rankings)

        # Career Stats
        career = data['career_stats']
        self.assertIn('total_tournaments', career)
        self.assertIn('total_matches', career)
        self.assertIn('matches_won', career)
        self.assertIn('matches_lost', career)
        self.assertIn('win_rate', career)
        self.assertIn('lifetime_cp', career)

        # Evaluation & Radar Attributes
        eval_data = data['evaluation']
        self.assertGreaterEqual(eval_data['firepower'], 60)
        self.assertLessEqual(eval_data['firepower'], 99)
        self.assertGreaterEqual(eval_data['strategy'], 60)
        self.assertLessEqual(eval_data['strategy'], 99)
        self.assertGreaterEqual(eval_data['clutch'], 60)
        self.assertLessEqual(eval_data['clutch'], 99)
        self.assertGreaterEqual(eval_data['consistency'], 60)
        self.assertLessEqual(eval_data['consistency'], 99)
        self.assertIn('team_dna', eval_data)
        self.assertIn('playstyle', eval_data)
        self.assertIn('tempo', eval_data)
        self.assertTrue(len(eval_data['scouting_report']) > 10)

    def test_get_team_profile_trophy_cabinet_and_history(self):
        """Verify trophy cabinet aggregation and tournament placement history."""
        # Add 3 placement records for this club
        # 1. Kickoff: 1st Place (Regional Champion)
        # 2. Masters Toronto: 2nd Place (Runner-up)
        # 3. Champions Paris: 1st Place (World Champion)
        stage_ko = CampaignStage(campaign_id=self.campaign_id, year=2026, stage_key='kickoff', stage_name='VCT Kickoff 2026', status='completed')
        stage_ms = CampaignStage(campaign_id=self.campaign_id, year=2026, stage_key='master', stage_name='VCT Masters Toronto 2026', status='completed')
        stage_ch = CampaignStage(campaign_id=self.campaign_id, year=2026, stage_key='champion', stage_name='VALORANT Champions Paris 2026', status='completed')
        db.session.add_all([stage_ko, stage_ms, stage_ch])
        db.session.commit()

        p1 = CampaignStagePlacement(
            campaign_id=self.campaign_id, year=2026,
            stage_key='kickoff', tournament_name='VCT Pacific Kickoff',
            region_slug='pacific', club_id=self.club_id, rank=1,
            rank_display='Quán Quân (1st)', matches_won=4, matches_lost=0,
            stage_points_earned=3, power_rating_snapshot=88.5
        )
        p2 = CampaignStagePlacement(
            campaign_id=self.campaign_id, year=2026,
            stage_key='master', tournament_name='VCT Masters Toronto',
            region_slug=None, club_id=self.club_id, rank=2,
            rank_display='Á Quân (2nd)', matches_won=5, matches_lost=2,
            stage_points_earned=5, power_rating_snapshot=91.0
        )
        p3 = CampaignStagePlacement(
            campaign_id=self.campaign_id, year=2026,
            stage_key='champion', tournament_name='VALORANT Champions Paris',
            region_slug=None, club_id=self.club_id, rank=1,
            rank_display='Vô Địch Thế Giới (1st)', matches_won=6, matches_lost=1,
            stage_points_earned=0, power_rating_snapshot=95.2
        )
        db.session.add_all([p1, p2, p3])
        db.session.commit()

        # Fetch profile
        data = get_team_profile_data(self.campaign_id, self.club_id)
        trophies = data['trophy_cabinet']
        career = data['career_stats']
        results = data['tournament_results']

        # Verify Trophies
        self.assertEqual(trophies['champions_titles'], 1)
        self.assertEqual(trophies['masters_titles'], 0)
        self.assertEqual(trophies['regional_titles'], 1)
        self.assertEqual(trophies['total_titles'], 2)
        self.assertEqual(trophies['runners_up'], 1)
        self.assertEqual(trophies['total_finals'], 3)

        # Verify Career Stats
        self.assertEqual(career['total_tournaments'], 3)
        self.assertEqual(career['matches_won'], 15)  # 4 + 5 + 6
        self.assertEqual(career['matches_lost'], 3)   # 0 + 2 + 1
        self.assertEqual(career['total_matches'], 18)
        self.assertAlmostEqual(career['win_rate'], round(15 / 18 * 100, 1))
        self.assertEqual(career['lifetime_cp'], 8)  # 3 + 5 + 0
        self.assertEqual(career['international_appearances'], 2)  # master + champion

        # Verify Tournament Results (3 rows, sorted by year desc, id desc)
        self.assertEqual(len(results), 3)
        self.assertEqual(results[0]['stage_key'], 'champion')
        self.assertEqual(results[0]['rank'], 1)
        self.assertEqual(results[1]['stage_key'], 'master')
        self.assertEqual(results[1]['rank'], 2)
        self.assertEqual(results[2]['stage_key'], 'kickoff')
        self.assertEqual(results[2]['rank'], 1)

    def test_recent_matches_extraction(self):
        """Verify head-to-head recent matches extraction from campaign stages."""
        opp_club = self.pacific_clubs[1]

        stage_data = {
            'result': {
                'matches': [
                    {
                        'team_a_id': self.club_id,
                        'team_b_id': opp_club.id,
                        'winner_id': self.club_id,
                        'team_a_score': 2,
                        'team_b_score': 1,
                        'round_name': 'Semifinal',
                    },
                    {
                        'team_a_id': opp_club.id,
                        'team_b_id': self.club_id,
                        'winner_id': opp_club.id,
                        'team_a_score': 2,
                        'team_b_score': 0,
                        'round_name': 'Upper Final',
                    }
                ]
            }
        }

        stage = CampaignStage(
            campaign_id=self.campaign_id, year=2026, stage_key='major',
            stage_name='VCT Masters Bangkok 2026',
            status='completed', stage_data=json.dumps(stage_data)
        )
        db.session.add(stage)
        db.session.commit()

        matches = _extract_recent_matches_for_club(self.campaign_id, self.club_id, limit=5)
        self.assertEqual(len(matches), 2)

        # Most recent first
        latest = matches[0]
        self.assertEqual(latest['opponent']['id'], opp_club.id)
        self.assertEqual(latest['round_name'], 'Upper Final')
        self.assertFalse(latest['is_winner'])
        self.assertEqual(latest['result_badge'], 'L')
        self.assertEqual(latest['score_display'], '0 - 2')

        second = matches[1]
        self.assertEqual(second['opponent']['id'], opp_club.id)
        self.assertEqual(second['round_name'], 'Semifinal')
        self.assertTrue(second['is_winner'])
        self.assertEqual(second['result_badge'], 'W')
        self.assertEqual(second['score_display'], '2 - 1')

    def test_nonexistent_club_returns_none(self):
        """Verify get_team_profile_data returns None for an invalid club ID."""
        data = get_team_profile_data(self.campaign_id, 999999)
        self.assertIsNone(data)


class TestTeamProfileWebAndAPI(unittest.TestCase):
    """Tests for Web HTML route and REST API endpoints."""

    def setUp(self):
        self.app = create_app()
        self.app_context = self.app.app_context()
        self.app_context.push()
        self.client = self.app.test_client()

        self.campaign = create_campaign(name="VCT Web Route Circuit", start_year=2026)
        self.campaign_id = self.campaign.id
        self.club = Club.query.first()
        self.club_id = self.club.id

    def tearDown(self):
        db.session.rollback()
        db.session.remove()
        self.app_context.pop()

    def test_api_campaign_team_profile_success(self):
        """Verify GET /api/campaign/<id>/team/<club_id> returns JSON 200 with profile."""
        resp = self.client.get(f"/api/campaign/{self.campaign_id}/team/{self.club_id}")
        self.assertEqual(resp.status_code, 200)

        data = resp.get_json()
        self.assertTrue(data.get('success'))
        self.assertIn('profile', data)

        profile = data['profile']
        self.assertEqual(profile['club']['id'], self.club_id)
        self.assertIn('rankings', profile)
        self.assertIn('trophy_cabinet', profile)
        self.assertIn('career_stats', profile)
        self.assertIn('evaluation', profile)

    def test_api_campaign_team_profile_404(self):
        """Verify API returns 404 for non-existent campaign or club."""
        resp_bad_camp = self.client.get(f"/api/campaign/999999/team/{self.club_id}")
        self.assertEqual(resp_bad_camp.status_code, 404)

        resp_bad_club = self.client.get(f"/api/campaign/{self.campaign_id}/team/999999")
        self.assertEqual(resp_bad_club.status_code, 404)

    def test_web_campaign_team_profile_view_success(self):
        """Verify GET /campaign/<id>/team/<club_id> renders full Liquipedia HTML page."""
        resp = self.client.get(f"/campaign/{self.campaign_id}/team/{self.club_id}")
        self.assertEqual(resp.status_code, 200)

        html = resp.get_data(as_text=True)
        # Verify essential visual components are present
        self.assertIn(self.club.name, html)
        self.assertIn(self.club.short_code, html)
        self.assertIn("Hồ Sơ Đội Tuyển", html)
        self.assertIn("Tủ Cúp Vinh Quang", html)
        self.assertIn("Đánh Giá Thuộc Tính Sức Mạnh", html)
        self.assertIn("Lịch Sử Giải Đấu Đã Tham Gia", html)
        self.assertIn("GPR Power Score", html)
        self.assertIn("OVR Rating", html)

    def test_web_campaign_team_profile_view_404(self):
        """Verify Web view returns 404 for invalid campaign or club ID."""
        resp_bad_camp = self.client.get(f"/campaign/999999/team/{self.club_id}")
        self.assertEqual(resp_bad_camp.status_code, 404)

        resp_bad_club = self.client.get(f"/campaign/{self.campaign_id}/team/999999")
        self.assertEqual(resp_bad_club.status_code, 404)


if __name__ == '__main__':
    unittest.main()
