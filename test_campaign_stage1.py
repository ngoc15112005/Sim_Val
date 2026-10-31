import json
import unittest
from app import create_app
from models import db, Campaign, CampaignStage, CampaignClubState
from services.campaign_service import (
    create_campaign,
    run_open_qualifier_stage,
    run_kickoff_stage,
    run_major_stage,
    sim_oq_stage1_all,
    get_stage1_data,
    sim_stage1_region_interactive,
    sim_stage1_all_interactive,
    run_ewc_qualifier_stage,
    get_championship_leaderboard,
)


class TestCampaignStage1Integration(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.client = self.app.test_client()
        self.app_context = self.app.app_context()
        self.app_context.push()
        self.cid = None

    def tearDown(self):
        if self.cid:
            camp = Campaign.query.get(self.cid)
            if camp:
                db.session.delete(camp)
                db.session.commit()
        db.session.remove()
        self.app_context.pop()

    def test_full_stage1_pipeline_and_qualification(self):
        # 1. Create Campaign and advance through Open Qualifier, Kickoff, Major
        campaign = create_campaign("Stage 1 Pipeline Test", start_year=2027)
        self.cid = campaign.id
        cid = campaign.id

        # Advance Open Qualifier
        run_open_qualifier_stage(cid)
        # Advance Kickoff
        run_kickoff_stage(cid)
        # Advance Major
        run_major_stage(cid)
        # Advance Open Qualifier Stage 1
        sim_oq_stage1_all(cid)

        # Campaign should now be at 'stage1'
        campaign = Campaign.query.get(cid)
        self.assertEqual(campaign.current_stage, 'stage1')

        # 2. Verify Stage 1 Data auto-initialized with 12 teams and 2 groups per region
        data = get_stage1_data(cid)
        self.assertIsNotNone(data)
        self.assertIn('regional_results', data)
        pac = data['regional_results']['pacific']
        self.assertEqual(len(pac['group_alpha']), 6)
        self.assertEqual(len(pac['group_omega']), 6)
        self.assertEqual(len(pac['regular_matches']), 30)
        self.assertEqual(len(pac['playoff_matches']), 8)

        # 3. Test HTTP View
        resp = self.client.get(f'/campaign/{cid}/stage/stage1?region=pacific')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'VCT Stage 1', resp.data)
        self.assertIn(b'B\xe1\xba\xa3ng Alpha', resp.data)  # Bảng Alpha in UTF-8
        self.assertIn(b'B\xe1\xba\xa3ng Omega', resp.data)  # Bảng Omega in UTF-8

        # 4. Test Match Roll via API
        pac = get_stage1_data(cid)['regional_results']['pacific']
        m1_id = pac['regular_matches'][0]['match_id']

        resp_roll = self.client.post(
            f'/api/campaign/{cid}/stage1/match/sim',
            json={'region': 'pacific', 'match_id': m1_id}
        )
        self.assertEqual(resp_roll.status_code, 200)
        data_roll = resp_roll.get_json()
        self.assertTrue(data_roll['success'])
        self.assertEqual(data_roll['result']['match']['status'], 'completed')

        # 5. Test Manual Match Score via API
        pac = get_stage1_data(cid)['regional_results']['pacific']
        m2 = pac['regular_matches'][1]
        m2_id = m2['match_id']
        winner_id = m2['team_a_id']

        resp_manual = self.client.post(
            f'/api/campaign/{cid}/stage1/match/manual',
            json={
                'region': 'pacific',
                'match_id': m2_id,
                'winner_id': winner_id,
                'maps': [
                    {'map_number': 1, 'team_a_score': 13, 'team_b_score': 9},
                    {'map_number': 2, 'team_a_score': 13, 'team_b_score': 7},
                ]
            }
        )
        self.assertEqual(resp_manual.status_code, 200)
        data_manual = resp_manual.get_json()
        self.assertTrue(data_manual['success'])
        self.assertEqual(data_manual['result']['match']['winner_id'], winner_id)
        self.assertTrue(data_manual['result']['match']['is_manual'])

        # 6. Test Sim Round via API
        resp_round = self.client.post(
            f'/api/campaign/{cid}/stage1/sim-round',
            json={'region': 'pacific'}
        )
        self.assertEqual(resp_round.status_code, 200)
        self.assertTrue(resp_round.get_json()['success'])

        # 7. Sim all 4 regions to completion
        resp_all = self.client.post(f'/api/campaign/{cid}/stage1/sim-all', json={})
        self.assertEqual(resp_all.status_code, 200)
        self.assertTrue(resp_all.get_json()['success'])

        # 8. Verify Stage 1 Completion and Next Stage Transitions
        campaign = Campaign.query.get(cid)
        stage1_rec = CampaignStage.query.filter_by(campaign_id=cid, stage_key='stage1').first()
        self.assertEqual(stage1_rec.status, 'completed')

        # Campaign moved to 'ewc_qualifier'
        self.assertEqual(campaign.current_stage, 'ewc_qualifier')

        # Verify Masters Toronto record prepared with 12 teams (3 per region)
        master_rec = CampaignStage.query.filter_by(campaign_id=cid, stage_key='master').first()
        self.assertIsNotNone(master_rec)
        m_data = json.loads(master_rec.stage_data)
        self.assertEqual(len(m_data['roster']), 12)

        # Verify EWC Qualifier record prepared
        ewc_qual_rec = CampaignStage.query.filter_by(campaign_id=cid, stage_key='ewc_qualifier').first()
        self.assertIsNotNone(ewc_qual_rec)
        eq_data = json.loads(ewc_qual_rec.stage_data)
        self.assertIn('regions', eq_data)
        self.assertEqual(len(eq_data['regions']['pacific']['phase1_teams']), 16)
        self.assertEqual(len(eq_data['regions']['pacific']['phase2_direct_teams']), 6)

        # Run EWC Qualifier to completion
        run_ewc_qualifier_stage(cid)
        campaign = Campaign.query.get(cid)
        self.assertEqual(campaign.current_stage, 'master')

        # Verify EWC record now has all 16 teams (4 per region)
        ewc_rec = CampaignStage.query.filter_by(campaign_id=cid, stage_key='ewc').first()
        self.assertIsNotNone(ewc_rec)
        e_data = json.loads(ewc_rec.stage_data)
        self.assertEqual(len(e_data['roster']), 16)

        # Check that CP points were awarded properly
        pacific_lb = get_championship_leaderboard(cid, region_slug='pacific')
        self.assertGreater(pacific_lb[0]['championship_points'], 0)


if __name__ == '__main__':
    unittest.main()
