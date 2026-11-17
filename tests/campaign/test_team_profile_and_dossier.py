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
import time
from config import get_stage_prize_money, get_stage_total_prize_pool, format_usd
from app import create_app
from models import (
    db, Campaign, CampaignClubState, CampaignStage, CampaignStagePlacement,
    CampaignMatchRecord, Club, Region,
)
from services.campaign_service import (
    create_campaign,
    get_team_profile_data,
    get_stage_replay_data,
    get_head_to_head_history,
    sync_stage_match_records,
    run_open_qualifier_stage,
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
        self.assertIn("Đội Hình Chính Thức", html)
        self.assertIn("Tài Chính", html)
        self.assertIn("openTournamentReplayModal", html)

    def test_web_campaign_team_profile_view_404(self):
        """Verify Web view returns 404 for invalid campaign or club ID."""
        resp_bad_camp = self.client.get(f"/campaign/999999/team/{self.club_id}")
        self.assertEqual(resp_bad_camp.status_code, 404)

        resp_bad_club = self.client.get(f"/campaign/{self.campaign_id}/team/999999")
        self.assertEqual(resp_bad_club.status_code, 404)

    def test_prize_money_roster_and_stage_replay(self):
        """Verify prize money math, dossier roster, and O(1) multi-year tournament replay."""
        # 1. Verify prize pool formulas
        self.assertEqual(get_stage_prize_money('champion', 1), 1_000_000)
        self.assertEqual(get_stage_prize_money('master', 1), 350_000)
        self.assertEqual(get_stage_prize_money('ewc', 1), 1_500_000)
        self.assertEqual(get_stage_prize_money('stage1', 1), 100_000)
        self.assertEqual(get_stage_prize_money('kickoff', 1), 50_000)
        self.assertEqual(get_stage_total_prize_pool('champion'), 2_250_000)
        self.assertEqual(get_stage_total_prize_pool('ewc'), 3_500_000)
        self.assertGreater(get_stage_total_prize_pool('ewc'), get_stage_total_prize_pool('champion'))
        self.assertEqual(format_usd(1_400_000), "$1,400,000")

        # 2. Seed placements across 2 years (2026 & 2027)
        p_2026 = CampaignStagePlacement(
            campaign_id=self.campaign_id, year=2026, stage_key='champion',
            tournament_name='VALORANT Champions 2026', region_slug=None,
            club_id=self.club_id, rank=1, rank_display='1st (Vô địch)',
            elimination_stage='Grand Final', stage_points_earned=0,
            prize_money=get_stage_prize_money('champion', 1),
            matches_won=5, matches_lost=1, power_score_snapshot=1850.0, power_rating_snapshot=96.0,
        )
        p_2027 = CampaignStagePlacement(
            campaign_id=self.campaign_id, year=2027, stage_key='master',
            tournament_name='VCT Masters 2027', region_slug=None,
            club_id=self.club_id, rank=2, rank_display='2nd (Á quân)',
            elimination_stage='Grand Final', stage_points_earned=5,
            prize_money=get_stage_prize_money('master', 2),
            matches_won=4, matches_lost=2, power_score_snapshot=1810.0, power_rating_snapshot=94.0,
        )
        db.session.add_all([p_2026, p_2027])

        # Also add stage JSON with GSL group + playoff maps for replay
        opp = Club.query.filter(Club.id != self.club_id).first()
        champ_stage = CampaignStage(
            campaign_id=self.campaign_id, year=2026, stage_key='champion',
            stage_name='VALORANT Champions 2026', status='completed',
            stage_data=json.dumps({
                'result': {
                    'groups': {
                        'A': {
                            'matches': {
                                'm1': {
                                    'id': 'm1', 'round_name': 'Group A Opening', 'bo': 3,
                                    'team_a_id': self.club_id, 'team_b_id': opp.id,
                                    'team_a_score': 2, 'team_b_score': 1, 'winner_id': self.club_id,
                                    'status': 'completed',
                                    'maps': [
                                        {'map_name': 'Ascent', 'team_a_score': 13, 'team_b_score': 7},
                                        {'map_name': 'Haven', 'team_a_score': 9, 'team_b_score': 13},
                                        {'map_name': 'Bind', 'team_a_score': 13, 'team_b_score': 10},
                                    ],
                                }
                            }
                        }
                    },
                    'playoff_matches': [
                        {
                            'id': 'gf', 'round_name': 'Grand Final', 'bo': 5,
                            'team_a_id': self.club_id, 'team_b_id': opp.id,
                            'team_a_score': 3, 'team_b_score': 1, 'winner_id': self.club_id,
                            'status': 'completed',
                        }
                    ],
                }
            }),
        )
        db.session.add(champ_stage)
        db.session.commit()

        # Verify Team Profile contains roster, prize money & season breakdown
        profile = get_team_profile_data(self.campaign_id, self.club_id)
        self.assertIn('roster', profile)
        self.assertEqual(len(profile['roster']['starters']), 5)
        self.assertTrue(profile['roster']['metrics']['roles_ok'])
        self.assertEqual(profile['career_stats']['lifetime_prize_money'], 1_200_000)
        self.assertEqual(profile['career_stats']['lifetime_prize_money_display'], "$1,200,000")
        self.assertEqual(profile['career_stats']['current_season_prize_money'], 1_000_000)
        self.assertEqual(profile['career_stats']['best_placement']['rank'], 1)
        self.assertEqual(len(profile['season_breakdown']), 2)
        self.assertEqual(profile['tournament_results'][0]['prize_money_display'], "$200,000")
        self.assertIn('year=2027', profile['tournament_results'][0]['replay_url'])

        # 3. Verify O(1) Stage Replay API (Champion 2026)
        replay_resp = self.client.get(
            f"/api/campaign/{self.campaign_id}/stage-replay/champion?year=2026&club_id={self.club_id}"
        )
        self.assertEqual(replay_resp.status_code, 200)
        rp_data = replay_resp.get_json()
        self.assertTrue(rp_data.get('success'))
        rp = rp_data['replay']
        self.assertEqual(rp['year'], 2026)
        self.assertEqual(rp['prize_pool'], 2_250_000)
        self.assertEqual(rp['total_matches'], 2)
        self.assertEqual(rp['standings'][0]['prize_money'], 1_000_000)
        self.assertTrue(rp['standings'][0]['is_highlight'])
        self.assertEqual(rp['sections'][0]['matches'][0]['maps'][0]['map_name'], 'Ascent')

        # 4. Verify Regional Replay & Historical Stage View (?year=2026 after advancing year)
        run_open_qualifier_stage(self.campaign_id)
        camp = db.session.get(Campaign, self.campaign_id)
        camp.current_year = 2027
        db.session.commit()

        oq_replay = get_stage_replay_data(self.campaign_id, 'open_qualifier', year=2026, region_slug='pacific')
        self.assertTrue(oq_replay['is_regional'])
        self.assertEqual(oq_replay['region_slug'], 'pacific')
        self.assertGreater(oq_replay['total_matches'], 0)

        view_resp = self.client.get(f"/campaign/{self.campaign_id}/stage/open_qualifier?year=2026&region=pacific")
        self.assertEqual(view_resp.status_code, 200)


class TestHeadToHeadSystem(unittest.TestCase):
    """Tests for indexed CampaignMatchRecord H2H lookups, orientation symmetry, and 20-year scalability."""

    def setUp(self):
        self.app = create_app()
        self.app_context = self.app.app_context()
        self.app_context.push()
        self.client = self.app.test_client()
        self.campaign = create_campaign(name="VCT H2H Test Circuit", start_year=2027)
        self.campaign_id = self.campaign.id
        clubs = Club.query.limit(4).all()
        self.team_a = clubs[0]
        self.team_b = clubs[1]
        self.team_c = clubs[2]

    def tearDown(self):
        db.session.rollback()
        camp = db.session.get(Campaign, self.campaign_id)
        if camp:
            db.session.delete(camp)
            db.session.commit()
        db.session.remove()
        self.app_context.pop()

    def test_h2h_symmetry_exclude_and_reroll_idempotency(self):
        """Verify (A vs B) mirrors (B vs A), re-rolling updates in place, and exclude_match_key hides current slot."""
        s_ko = CampaignStage(
            campaign_id=self.campaign_id, year=2027, stage_key='kickoff',
            stage_name='VCT Kickoff 2027', status='completed',
            stage_data=json.dumps({
                'regional_results': {
                    'pacific': {
                        'matches': [
                            {
                                'id': 'ko_ub_1',
                                'status': 'completed',
                                'round_name': 'Upper R1',
                                'team_a_id': self.team_a.id,
                                'team_b_id': self.team_b.id,
                                'team_a_score': 2,
                                'team_b_score': 1,
                                'winner_id': self.team_a.id,
                                'maps': [
                                    {'map_name': 'Ascent', 'team_a_score': 13, 'team_b_score': 9},
                                    {'map_name': 'Bind', 'team_a_score': 10, 'team_b_score': 13},
                                    {'map_name': 'Haven', 'team_a_score': 13, 'team_b_score': 7},
                                ],
                            },
                            {
                                'id': 'ko_lb_2',
                                'status': 'completed',
                                'round_name': 'Lower Final',
                                'team_a_id': self.team_b.id,
                                'team_b_id': self.team_a.id,
                                'team_a_score': 3,
                                'team_b_score': 0,
                                'winner_id': self.team_b.id,
                                'maps': [
                                    {'map_name': 'Lotus', 'team_a_score': 13, 'team_b_score': 8},
                                    {'map_name': 'Split', 'team_a_score': 13, 'team_b_score': 5},
                                    {'map_name': 'Pearl', 'team_a_score': 13, 'team_b_score': 11},
                                ],
                            },
                        ]
                    }
                }
            }),
        )
        # Also simulate an active in_progress stage1 with both regular_matches and later playoff Grand Final
        s_s1_data = {
            'regional_results': {
                'pacific': {
                    'regular_matches': [
                        {
                            'match_id': 'reg_w1_m1',
                            'status': 'completed',
                            'round_name': 'Group Stage W1',
                            'team_a_id': self.team_a.id,
                            'team_b_id': self.team_b.id,
                            'team_a_score': 2,
                            'team_b_score': 0,
                            'winner_id': self.team_a.id,
                            'maps': [{'map_name': 'Sunset', 'team_a_score': 13, 'team_b_score': 6}],
                        }
                    ],
                    'playoff_matches': [],
                }
            }
        }
        s_s1 = CampaignStage(
            campaign_id=self.campaign_id, year=2027, stage_key='stage1',
            stage_name='VCT Stage 1 2027', status='in_progress',
            stage_data=json.dumps(s_s1_data),
        )
        camp = db.session.get(Campaign, self.campaign_id)
        camp.current_stage = 'stage1'
        db.session.add_all([s_ko, s_s1])
        db.session.commit()

        # Perspective A vs B across 3 matches (including stage1 regular_matches -> A leads 2-1, maps 4-4)
        h2h_ab = get_head_to_head_history(self.campaign_id, self.team_a.id, self.team_b.id)
        self.assertEqual(h2h_ab['summary']['total_matches'], 3)
        self.assertEqual(h2h_ab['summary']['team_a_wins'], 2)
        self.assertEqual(h2h_ab['summary']['team_b_wins'], 1)
        self.assertEqual(h2h_ab['summary']['team_a_maps'], 4)
        self.assertEqual(h2h_ab['summary']['team_b_maps'], 4)
        self.assertEqual(h2h_ab['summary']['recent_form'], ['W', 'L', 'W'])
        self.assertEqual(len(h2h_ab['matches'][1]['maps_list']), 3)
        # Confirm flipped map summary on ko_lb_2 (stored as B 13-8 A -> displayed as A 8-13 B)
        self.assertIn('Lotus 8-13', h2h_ab['matches'][1]['maps_summary'])

        # Symmetric B vs A perspective
        h2h_ba = get_head_to_head_history(self.campaign_id, self.team_b.id, self.team_a.id)
        self.assertEqual(h2h_ba['summary']['team_a_wins'], 1)
        self.assertEqual(h2h_ba['summary']['team_b_wins'], 2)
        self.assertEqual(h2h_ba['summary']['recent_form'], ['L', 'W', 'L'])
        self.assertIn('Lotus 13-8', h2h_ba['matches'][1]['maps_summary'])

        # Excluding currently edited match 'reg_w1_m1' drops count to 2
        h2h_ex = get_head_to_head_history(
            self.campaign_id, self.team_a.id, self.team_b.id,
            exclude_match_key='reg_w1_m1', exclude_year=2027, exclude_stage_key='stage1',
            exclude_region_slug='pacific',
        )
        self.assertEqual(h2h_ex['summary']['total_matches'], 2)

        # Simulate finishing Stage 1 Grand Final AFTER stage1 was already partially synced + advancing campaign!
        s_s1_data['regional_results']['pacific']['playoff_matches'] = [
            {
                'match_id': 'GF',
                'status': 'completed',
                'round_name': 'Grand Final',
                'team_a_id': self.team_a.id,
                'team_b_id': self.team_b.id,
                'team_a_score': 3,
                'team_b_score': 1,
                'winner_id': self.team_a.id,
                'maps': [
                    {'map_name': 'Abyss', 'team_a_score': 13, 'team_b_score': 10},
                    {'map_name': 'Haven', 'team_a_score': 10, 'team_b_score': 13},
                    {'map_name': 'Bind', 'team_a_score': 13, 'team_b_score': 7},
                    {'map_name': 'Split', 'team_a_score': 13, 'team_b_score': 9},
                ],
            }
        ]
        prev_dv = s_s1.data_version
        s_s1.stage_data = json.dumps(s_s1_data)
        s_s1.status = 'completed'
        camp.current_stage = 'master'
        db.session.commit()
        self.assertGreater(s_s1.data_version, prev_dv)

        # Even after moving to master and marking stage1 completed, data_version != h2h_synced_version catches GF!
        h2h_after_gf = get_head_to_head_history(self.campaign_id, self.team_a.id, self.team_b.id)
        self.assertEqual(h2h_after_gf['summary']['total_matches'], 4)
        self.assertEqual(h2h_after_gf['summary']['team_a_wins'], 3)
        self.assertEqual(h2h_after_gf['summary']['team_b_wins'], 1)
        self.assertEqual(h2h_after_gf['summary']['regional_a_wins'], 3)
        self.assertEqual(s_s1.h2h_synced_version, s_s1.data_version)

        # Re-roll 'reg_w1_m1' cleanly updates existing row in place instead of duplicating
        s_s1_data['regional_results']['pacific']['regular_matches'][0]['winner_id'] = self.team_b.id
        s_s1_data['regional_results']['pacific']['regular_matches'][0]['team_a_score'] = 1
        s_s1_data['regional_results']['pacific']['regular_matches'][0]['team_b_score'] = 2
        s_s1.stage_data = json.dumps(s_s1_data)
        db.session.commit()

        h2h_rerolled = get_head_to_head_history(self.campaign_id, self.team_a.id, self.team_b.id)
        self.assertEqual(h2h_rerolled['summary']['total_matches'], 4)
        self.assertEqual(h2h_rerolled['summary']['team_a_wins'], 2)
        self.assertEqual(h2h_rerolled['summary']['team_b_wins'], 2)
        self.assertEqual(
            CampaignMatchRecord.query.filter_by(campaign_id=self.campaign_id).count(),
            4,
        )

    def test_20_year_save_h2h_performance_and_endpoint(self):
        """Simulate a 20-year save (120 historical stages) and verify instant H2H API + full history."""
        bulk_stages = []
        # Populate 20 seasons x 6 completed stages = 120 heavy stages
        for yr in range(2027, 2047):
            for sk in ('kickoff', 'major', 'stage1', 'master', 'ewc', 'champion'):
                matches = []
                for idx in range(10):
                    ta = self.team_a.id if (idx == 0 and sk in ('kickoff', 'champion')) else self.team_c.id
                    tb = self.team_b.id
                    if ta == tb:
                        ta = self.team_a.id
                    matches.append({
                        'id': f'{yr}_{sk}_{idx}',
                        'status': 'completed',
                        'round_name': f'Round {idx + 1}',
                        'team_a_id': ta,
                        'team_b_id': tb,
                        'team_a_score': 2,
                        'team_b_score': 1,
                        'winner_id': ta,
                    })
                bulk_stages.append(CampaignStage(
                    campaign_id=self.campaign_id,
                    year=yr,
                    stage_key=sk,
                    stage_name=f'{sk.upper()} {yr}',
                    status='completed',
                    stage_data=json.dumps({'result': {'matches': matches}}),
                ))
        db.session.add_all(bulk_stages)
        camp = db.session.get(Campaign, self.campaign_id)
        camp.current_year = 2047
        db.session.commit()

        # First call backfills 120 completed stages once; second call hits pure B-tree index in O(log N)
        first = get_head_to_head_history(self.campaign_id, self.team_a.id, self.team_b.id, limit=15)
        self.assertEqual(first['summary']['total_matches'], 40)
        self.assertFalse(first['is_full_history'])

        t0 = time.perf_counter()
        resp = self.client.get(
            f"/api/campaign/{self.campaign_id}/h2h?team_a_id={self.team_a.id}&team_b_id={self.team_b.id}&limit=15"
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        self.assertEqual(resp.status_code, 200)
        payload = resp.get_json()
        self.assertTrue(payload.get('success'))
        self.assertEqual(payload['summary']['total_matches'], 40)
        self.assertEqual(payload['summary']['regional_a_wins'], 20)
        self.assertEqual(payload['summary']['international_a_wins'], 20)
        self.assertEqual(len(payload['summary']['available_years']), 20)
        self.assertEqual(len(payload['matches']), 15)
        self.assertLess(elapsed_ms, 250.0)

        # Verify Full History (?all=1) returns ALL 40 matches quickly
        full_resp = self.client.get(
            f"/api/campaign/{self.campaign_id}/h2h?team_a_id={self.team_a.id}&team_b_id={self.team_b.id}&all=1"
        )
        self.assertEqual(full_resp.status_code, 200)
        full_payload = full_resp.get_json()
        self.assertTrue(full_payload['is_full_history'])
        self.assertEqual(len(full_payload['matches']), 40)

        # Verify stage templates automatically include H2H panel & Full H2H Modal via base.html
        camp.current_year = 2027
        db.session.commit()
        run_open_qualifier_stage(self.campaign_id)
        for sk_url in ('open_qualifier', 'kickoff'):
            stage_resp = self.client.get(f"/campaign/{self.campaign_id}/stage/{sk_url}?year=2027")
            self.assertEqual(stage_resp.status_code, 200)
            html = stage_resp.get_data(as_text=True)
            self.assertIn('id="match-h2h-side-panel"', html)
            self.assertIn('id="h2h-full-history-modal"', html)
            self.assertIn('/h2h?', html)


if __name__ == '__main__':
    unittest.main()
