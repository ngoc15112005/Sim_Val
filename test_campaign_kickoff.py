import unittest
import json
from app import create_app
from models import db, Campaign, CampaignClubState, CampaignStage
from services.campaign_service import (
    create_campaign,
    get_campaign,
    run_open_qualifier_stage,
    run_kickoff_stage,
    override_kickoff_match,
    get_kickoff_data,
    get_championship_leaderboard,
)


class TestCampaignKickoff(unittest.TestCase):

    def setUp(self):
        self.app = create_app()
        self.client = self.app.test_client()
        self.app_context = self.app.app_context()
        self.app_context.push()

    def tearDown(self):
        db.session.remove()
        self.app_context.pop()

    def test_open_qualifier_to_kickoff_to_major_progression(self):
        # 1. Create Campaign
        campaign = create_campaign(name="Kickoff Full Test", start_year=2027)
        self.assertEqual(campaign.current_stage, 'open_qualifier')

        # 2. Run Open Qualifier for all 4 regions (172 matches total)
        oq_res = run_open_qualifier_stage(campaign.id)
        self.assertEqual(len(oq_res), 4)

        db.session.refresh(campaign)
        self.assertEqual(campaign.current_stage, 'kickoff')

        # 3. Verify Kickoff stage initialized with 12 teams per region
        k_data = get_kickoff_data(campaign.id)
        self.assertIsNotNone(k_data)
        self.assertIn('rosters', k_data)
        for r_slug in ['pacific', 'americas', 'emea', 'china']:
            self.assertEqual(len(k_data['rosters'][r_slug]), 12)

        # 4. Run Kickoff for Pacific region
        pac_res = run_kickoff_stage(campaign.id, region_slug='pacific')
        self.assertIn('pacific', pac_res)
        self.assertEqual(pac_res['pacific']['total_matches'], 22)
        self.assertEqual(len(pac_res['pacific']['major_qualifiers']), 2)

        # 5. Verify CP awarded in leaderboard
        pac_lb = get_championship_leaderboard(campaign.id, region_slug='pacific')
        self.assertEqual(pac_lb[0]['championship_points'], 3)  # Kickoff Champion
        self.assertEqual(pac_lb[1]['championship_points'], 2)  # Kickoff Runner-up
        self.assertEqual(pac_lb[2]['championship_points'], 1)  # 3rd place
        self.assertEqual(pac_lb[3]['championship_points'], 1)  # 4th place
        self.assertEqual(pac_lb[4]['championship_points'], 0)  # 5th place

        # 6. Test manual match override
        k_data_updated = get_kickoff_data(campaign.id)
        pac_matches = k_data_updated['regional_results']['pacific']['matches']
        m1 = pac_matches[0]  # upper_r1_m1
        underdog_id = m1['team_b']['id']

        override_res = override_kickoff_match(
            campaign.id, region_slug='pacific',
            round_name=m1['round_name'], winner_id=underdog_id
        )
        self.assertIn('pacific', override_res)

        k_data_after_override = get_kickoff_data(campaign.id)
        m1_after = k_data_after_override['regional_results']['pacific']['completed_dict'][m1['round_name']]
        self.assertEqual(m1_after['winner_id'], underdog_id)
        self.assertTrue(m1_after['is_manual'])

        # 7. Complete Kickoff for remaining 3 regions
        for r in ['americas', 'emea', 'china']:
            run_kickoff_stage(campaign.id, region_slug=r)

        db.session.refresh(campaign)
        self.assertEqual(campaign.current_stage, 'major')

        # 8. Verify Major stage prepared with exactly 8 teams (2 per region)
        major_stage = CampaignStage.query.filter_by(
            campaign_id=campaign.id, stage_key='major'
        ).first()
        self.assertIsNotNone(major_stage)
        major_data = json.loads(major_stage.stage_data)
        self.assertEqual(len(major_data['roster']), 8)

        # 9. Test Web Routes for Kickoff
        r = self.client.get(f'/campaign/{campaign.id}/stage/kickoff?region=pacific')
        self.assertEqual(r.status_code, 200)
        self.assertIn('VCT Kickoff (12 Đội / Khu Vực)'.encode('utf-8'), r.data)
        self.assertIn('KẾT QUẢ VCT KICKOFF PACIFIC 2025'.encode('utf-8'), r.data)

        # Cleanup
        db.session.delete(campaign)
        db.session.commit()


if __name__ == '__main__':
    unittest.main()
