import unittest
import json
from app import create_app, db
from models import Campaign, CampaignStage, CampaignClubState, CampaignStagePlacement, Club, Region
from services.campaign_service import (
    recalculate_campaign_gpr,
    get_global_power_rankings,
)
from engine.power_rating import (
    update_team_elo,
    calculate_composite_power_score,
    power_score_to_ovr,
    get_tier_info,
    format_rank_delta,
)


class TestGprDynamicProgression(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.app_context = self.app.app_context()
        self.app_context.push()
        self.client = self.app.test_client()

    def tearDown(self):
        self.app_context.pop()

    def test_gpr_formulas_and_deltas(self):
        # 1. Test update_team_elo win gain and loser loss
        w_elo, l_elo, delta = update_team_elo(
            rating_winner=1500.0,
            rating_loser=1500.0,
            tournament_tier='champion',
            map_diff=2,
            round_diff=10,
        )
        self.assertGreater(w_elo, 1500.0)
        self.assertLess(l_elo, 1500.0)
        self.assertGreater(delta, 10.0)

        # 2. Test composite score with streak bonus
        score_normal = calculate_composite_power_score(team_elo=1800.0, league_elo=1500.0, win_streak=0)
        score_hot = calculate_composite_power_score(team_elo=1800.0, league_elo=1500.0, win_streak=5)
        self.assertGreater(score_hot, score_normal)
        self.assertEqual(score_hot - score_normal, 35.0)

        # 3. Test tier classification
        tier_s_plus = get_tier_info(1950.0)
        self.assertEqual(tier_s_plus['tier'], 'S+')
        tier_s = get_tier_info(1750.0)
        self.assertEqual(tier_s['tier'], 'S')

        # 4. Test rank delta formatting
        delta_up = format_rank_delta(current_rank=1, previous_rank=10)
        self.assertEqual(delta_up['delta'], 9)
        self.assertEqual(delta_up['symbol'], '▲ +9')

        delta_down = format_rank_delta(current_rank=15, previous_rank=5)
        self.assertEqual(delta_down['delta'], -10)
        self.assertEqual(delta_down['symbol'], '▼ -10')

        delta_same = format_rank_delta(current_rank=3, previous_rank=3)
        self.assertEqual(delta_same['delta'], 0)
        self.assertEqual(delta_same['symbol'], '▬ 0')

        delta_new = format_rank_delta(current_rank=8, previous_rank=None)
        self.assertEqual(delta_new['symbol'], '★ NEW')

    def test_recalculate_campaign_gpr_end_to_end(self):
        # Verify recalculate_campaign_gpr runs on existing campaign 1
        rankings = recalculate_campaign_gpr(campaign_id=1)
        self.assertTrue(len(rankings) > 0)
        top1 = rankings[0]
        self.assertIn('rank', top1)
        self.assertIn('power_score', top1)
        self.assertIn('team_elo', top1)
        self.assertIn('win_streak', top1)
        self.assertIn('tier', top1)
        self.assertIn('rank_delta', top1)
        self.assertEqual(top1['rank'], 1)

        # Verify club states in DB were actually updated
        states = CampaignClubState.query.filter_by(campaign_id=1).all()
        # Streaks should not all be zero
        streaks = [cs.win_streak for cs in states if cs.win_streak is not None]
        self.assertTrue(any(s != 0 for s in streaks), "Streaks should be dynamically computed")

        # Previous rank should be snapshotted
        prev_ranks = [cs.previous_rank for cs in states if cs.previous_rank is not None]
        self.assertTrue(len(prev_ranks) > 0, "Previous ranks should be populated")

    def test_recalculate_gpr_api_endpoint(self):
        # Test POST /api/campaign/1/gpr/recalculate
        response = self.client.post('/api/campaign/1/gpr/recalculate')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data['success'])
        self.assertIn('count', data)
        self.assertGreater(data['count'], 0)
        self.assertIn('rankings', data)

    def test_dominant_team_golden_road_reaches_top(self):
        # Create a mock campaign to simulate GAM winning Golden Road (all 7 tournaments)
        c = Campaign(
            name="Test Golden Road Campaign",
            current_stage="season_summary",
            current_year=2027,
            status="active"
        )
        db.session.add(c)
        db.session.flush()

        # Pick 4 clubs
        clubs = Club.query.limit(4).all()
        self.assertTrue(len(clubs) >= 4)
        c_states = []
        for i, club in enumerate(clubs):
            cs = CampaignClubState(
                campaign_id=c.id,
                club_id=club.id,
                team_elo=club.base_rating * 18.75,
                power_score=club.base_rating * 18.75,
                power_rating=club.base_rating,
                story_rating=club.base_rating,
                win_streak=0,
                championship_points=0
            )
            c_states.append(cs)
            db.session.add(cs)
        db.session.flush()

        hero_club = clubs[0]
        hero_cs = c_states[0]
        rival_club = clubs[1]

        # Simulate Golden Road: hero_club wins Kickoff, Major, Stage 1, Masters, EWC, Stage 2, Champions
        stages_info = [
            ('kickoff', 'regional_results', {'pacific': {'matches': [{'team_a_id': hero_club.id, 'team_b_id': rival_club.id, 'team_a_score': 2, 'team_b_score': 0, 'winner_id': hero_club.id}]}}),
            ('major', 'result', {'matches': [{'team_a_id': hero_club.id, 'team_b_id': rival_club.id, 'team_a_score': 2, 'team_b_score': 0, 'winner_id': hero_club.id}]}),
            ('stage1', 'regional_results', {'pacific': {'regular_matches': [{'team_a_id': hero_club.id, 'team_b_id': rival_club.id, 'team_a_score': 2, 'team_b_score': 0, 'winner_id': hero_club.id}]}}),
            ('master', 'result', {'matches': [{'team_a_id': hero_club.id, 'team_b_id': rival_club.id, 'team_a_score': 2, 'team_b_score': 0, 'winner_id': hero_club.id}]}),
            ('ewc', 'result', {'matches': [{'team_a_id': hero_club.id, 'team_b_id': rival_club.id, 'team_a_score': 2, 'team_b_score': 0, 'winner_id': hero_club.id}]}),
            ('stage2', 'regional_results', {'pacific': {'regular_matches': [{'team_a_id': hero_club.id, 'team_b_id': rival_club.id, 'team_a_score': 2, 'team_b_score': 0, 'winner_id': hero_club.id}]}}),
            ('champion', 'result', {'matches': [{'team_a_id': hero_club.id, 'team_b_id': rival_club.id, 'team_a_score': 3, 'team_b_score': 1, 'winner_id': hero_club.id}]}),
        ]

        for sk, key_type, stage_inner in stages_info:
            data = {key_type: stage_inner}
            st = CampaignStage(
                campaign_id=c.id,
                year=2027,
                stage_key=sk,
                stage_name=sk.upper(),
                status='completed',
                stage_data=json.dumps(data)
            )
            db.session.add(st)
            # Add placement 1st
            pl = CampaignStagePlacement(
                campaign_id=c.id,
                year=2027,
                stage_key=sk,
                club_id=hero_club.id,
                tournament_name=sk.upper(),
                rank=1,
                rank_display='1st (Vô địch)',
                matches_won=5,
                matches_lost=0
            )
            db.session.add(pl)

        # Boost story rating to 99 like user's season
        hero_cs.story_rating = 99
        hero_cs.championship_points = 37
        db.session.commit()

        # Recalculate GPR
        rankings = recalculate_campaign_gpr(campaign_id=c.id)
        hero_rank = next((r for r in rankings if r['club']['id'] == hero_club.id), None)
        self.assertIsNotNone(hero_rank)
        # Hero club MUST be #1
        self.assertEqual(hero_rank['rank'], 1)
        self.assertEqual(hero_rank['tier']['tier'], 'S+')
        self.assertGreater(hero_rank['power_score'], 1850.0)
        self.assertGreater(hero_rank['win_streak'], 5)

        # Cleanup test campaign
        CampaignStagePlacement.query.filter_by(campaign_id=c.id).delete()
        CampaignStage.query.filter_by(campaign_id=c.id).delete()
        CampaignClubState.query.filter_by(campaign_id=c.id).delete()
        Campaign.query.filter_by(id=c.id).delete()
        db.session.commit()


if __name__ == '__main__':
    unittest.main()
