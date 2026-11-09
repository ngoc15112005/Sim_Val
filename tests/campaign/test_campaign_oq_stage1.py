import json
import unittest
from app import create_app
from models import db, Campaign, CampaignStage
from services.campaign_service import (
    create_campaign,
    run_open_qualifier_stage,
    run_kickoff_stage,
    run_major_stage,
    get_oq_stage1_data,
    sim_oq_stage1_round,
    sim_oq_stage1_all,
    resolve_oq_stage1_match,
    get_stage1_data,
)


class TestCampaignOQStage1Integration(unittest.TestCase):
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

    def test_oq_stage1_full_pipeline(self):
        # 1. Create campaign and progress through OQ, Kickoff, Major
        campaign = create_campaign("OQ Stage 1 Pipeline Test", start_year=2027)
        self.cid = campaign.id
        cid = campaign.id

        run_open_qualifier_stage(cid)
        run_kickoff_stage(cid)
        run_major_stage(cid)

        # 2. Campaign should now be at 'oq_stage1'
        campaign = db.session.get(Campaign, cid)
        self.assertEqual(campaign.current_stage, 'oq_stage1')

        # 3. Verify OQ Stage 1 data initialized
        oq_s1_data = get_oq_stage1_data(cid)
        self.assertIsNotNone(oq_s1_data)
        self.assertIn('regions', oq_s1_data)
        self.assertIn('retained_teams', oq_s1_data)

        # In Pacific: exactly 16 teams in OQ S1 and 8 teams retained
        pac_retained = oq_s1_data['retained_teams']['pacific']
        self.assertEqual(len(pac_retained), 8)

        pac_reg = oq_s1_data['regions']['pacific']
        self.assertEqual(len(pac_reg['teams']), 16)
        self.assertEqual(pac_reg['status'], 'in_progress')

        # 4. Test View GET
        resp = self.client.get(f'/campaign/{cid}/stage/oq_stage1?region=pacific')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Open Qualifier Stage 1', resp.data)

        # 5. Test Match Roll via API (using region_slug as sent by UI)
        m1 = pac_reg['swiss_matches'][0]
        m1_id = m1['id']
        resp_roll = self.client.post(
            f'/api/campaign/{cid}/oq_stage1/match/sim',
            json={'region_slug': 'pacific', 'match_id': m1_id}
        )
        self.assertEqual(resp_roll.status_code, 200)
        self.assertTrue(resp_roll.get_json()['success'])

        # 6. Test Manual match edit via API
        m2 = pac_reg['swiss_matches'][1]
        team_a_id = m2['team_a']['id']
        resp_man = self.client.post(
            f'/api/campaign/{cid}/oq_stage1/match/manual',
            json={
                'region_slug': 'pacific',
                'match_id': m2['id'],
                'winner_id': team_a_id,
                'maps': [
                    {'map_number': 1, 'team_a_score': 13, 'team_b_score': 7, 'winner_id': team_a_id}
                ]
            }
        )
        self.assertEqual(resp_man.status_code, 200)
        self.assertTrue(resp_man.get_json()['success'])

        # 7. Test Sim Round via API
        resp_round = self.client.post(
            f'/api/campaign/{cid}/oq_stage1/sim-round',
            json={'region_slug': 'pacific'}
        )
        self.assertEqual(resp_round.status_code, 200)
        self.assertTrue(resp_round.get_json()['success'])

        # 8. Test Sim Region via API
        resp_reg = self.client.post(
            f'/api/campaign/{cid}/oq_stage1/sim-region',
            json={'region_slug': 'pacific'}
        )
        self.assertEqual(resp_reg.status_code, 200)
        self.assertTrue(resp_reg.get_json()['success'])

        # 9. Sim all 4 regions in OQ Stage 1 to completion
        resp_all = self.client.post(f'/api/campaign/{cid}/oq_stage1/sim-all', json={})
        self.assertEqual(resp_all.status_code, 200)
        self.assertTrue(resp_all.get_json()['success'])

        # 10. Verify OQ Stage 1 completion and advancement to Stage 1
        campaign = db.session.get(Campaign, cid)
        self.assertEqual(campaign.current_stage, 'stage1')

        # Check Stage 1 data assembled with 12 teams (8 retained + 4 promoted)
        s1_data = get_stage1_data(cid)
        self.assertIsNotNone(s1_data)
        pac_s1 = s1_data['regional_results']['pacific']
        self.assertEqual(len(pac_s1['participants']), 12)
        self.assertEqual(len(pac_s1['group_alpha']), 6)
        self.assertEqual(len(pac_s1['group_omega']), 6)


if __name__ == '__main__':
    unittest.main()
