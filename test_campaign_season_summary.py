"""
test_campaign_season_summary.py — Integration test for Season Summary, Hall of Fame, and Next Year Rollover.
"""

import json
import unittest
from app import create_app
from models import db, Campaign, CampaignClubState, CampaignStage
from services.campaign_service import (
    create_campaign,
    run_open_qualifier_stage,
    run_kickoff_stage,
    run_major_stage,
    sim_oq_stage1_all,
    sim_stage1_all_interactive,
    sim_ewc_qualifier_all_interactive,
    sim_master_tournament_interactive,
    sim_ewc_tournament_interactive,
    sim_oq_stage2_all,
    sim_stage2_all_interactive,
    sim_champion_tournament_interactive,
    get_season_summary_data,
    advance_campaign_to_next_year,
)


class TestCampaignSeasonSummaryIntegration(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.client = self.app.test_client()
        self.app_context = self.app.app_context()
        self.app_context.push()
        self.cid = None

    def tearDown(self):
        if self.cid:
            camp = db.session.get(Campaign, self.cid)
            if camp:
                db.session.delete(camp)
                db.session.commit()
        db.session.remove()
        self.app_context.pop()

    def test_season_summary_and_multi_year_rollover(self):
        # 1. Run full competitive circuit of Year 2027
        campaign = create_campaign("Season Summary Rollover Test", start_year=2027)
        self.cid = campaign.id
        cid = campaign.id

        run_open_qualifier_stage(cid)
        run_kickoff_stage(cid)
        run_major_stage(cid)
        sim_oq_stage1_all(cid)
        sim_stage1_all_interactive(cid)
        sim_ewc_qualifier_all_interactive(cid)
        sim_master_tournament_interactive(cid)
        sim_ewc_tournament_interactive(cid)
        sim_oq_stage2_all(cid)
        sim_stage2_all_interactive(cid)
        sim_champion_tournament_interactive(cid)

        # 2. Current stage is season_summary
        campaign = db.session.get(Campaign, cid)
        self.assertEqual(campaign.current_stage, 'season_summary')
        self.assertEqual(campaign.current_year, 2027)

        # 3. Verify get_season_summary_data
        summary = get_season_summary_data(cid)
        self.assertIsNotNone(summary)
        self.assertEqual(summary['year'], 2027)
        self.assertIn('titles', summary)
        self.assertIn('kickoff', summary['titles'])
        self.assertIn('major', summary['titles'])
        self.assertIn('stage1', summary['titles'])
        self.assertIn('master', summary['titles'])
        self.assertIn('ewc', summary['titles'])
        self.assertIn('stage2', summary['titles'])
        self.assertIn('champion', summary['titles'])

        self.assertIsNotNone(summary['world_champion'])
        self.assertIsNotNone(summary['club_of_the_year'])
        self.assertIsNotNone(summary['best_region'])
        self.assertIsNotNone(summary['most_improved'])
        self.assertIn('leaderboards', summary)
        self.assertEqual(len(summary['leaderboards']), 4)

        # 4. Web View GET /campaign/<cid>/stage/season_summary
        resp = self.client.get(f'/campaign/{cid}/stage/season_summary')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Hall of Fame', resp.data)
        self.assertIn(b'2027', resp.data)

        # Record rating before rollover
        top_club_state = CampaignClubState.query.filter_by(campaign_id=cid).order_by(CampaignClubState.championship_points.desc()).first()
        self.assertIsNotNone(top_club_state)
        self.assertGreater(top_club_state.championship_points, 0)
        old_rating = top_club_state.story_rating

        # 5. Advance campaign to next year via API
        adv_res = self.client.post(f'/api/campaign/{cid}/advance-year', json={})
        self.assertEqual(adv_res.status_code, 200)
        adv_json = adv_res.get_json()
        self.assertTrue(adv_json['success'])
        self.assertEqual(adv_json['result']['new_year'], 2028)
        self.assertEqual(adv_json['result']['new_stage'], 'open_qualifier')

        # 6. Verify Campaign state
        campaign = db.session.get(Campaign, cid)
        self.assertEqual(campaign.current_year, 2028)
        self.assertEqual(campaign.current_stage, 'open_qualifier')

        # 7. Check Archived Hall of Fame record for Year 2027
        hof_stage = CampaignStage.query.filter_by(campaign_id=cid, year=2027, stage_key='hof_year_2027').first()
        self.assertIsNotNone(hof_stage)
        self.assertEqual(hof_stage.status, 'completed')
        hof_data = json.loads(hof_stage.stage_data)
        self.assertEqual(hof_data['year'], 2027)
        self.assertIsNotNone(hof_data['world_champion'])

        # 8. Check Season Reset & Aging on Club States
        all_states = CampaignClubState.query.filter_by(campaign_id=cid).all()
        for cs in all_states:
            self.assertEqual(cs.championship_points, 0, "Championship Points must be reset to 0 in new season")
            self.assertEqual(cs.regular_season_wins, 0, "Regular season wins must be reset to 0")
            self.assertEqual(cs.form_modifier, 0, "Form modifier must be reset to 0")

        # 9. Check New Year Open Qualifier Stage initialized for 2028
        new_oq = CampaignStage.query.filter_by(campaign_id=cid, year=2028, stage_key='open_qualifier').first()
        self.assertIsNotNone(new_oq)
        self.assertEqual(new_oq.status, 'in_progress')

        # 10. Check that Season Summary now contains 2027 in past_records
        new_summary = get_season_summary_data(cid)
        self.assertEqual(new_summary['year'], 2028)
        self.assertEqual(len(new_summary['past_records']), 1)
        self.assertEqual(new_summary['past_records'][0]['year'], 2027)


if __name__ == '__main__':
    unittest.main()
