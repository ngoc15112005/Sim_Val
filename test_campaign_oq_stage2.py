"""
test_campaign_oq_stage2.py — Integration test for Open Qualifier Stage 2 in Campaign Mode.
"""

import unittest
from app import create_app
from models import db, Campaign, CampaignStage
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
    get_oq_stage2_data,
    resolve_oq_stage2_match,
    sim_oq_stage2_round,
    sim_oq_stage2_region,
    sim_oq_stage2_all,
)


class TestCampaignOQStage2Integration(unittest.TestCase):
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

    def test_oq_stage2_pipeline(self):
        # 1. Advance campaign through EWC
        campaign = create_campaign("OQ Stage 2 Integration Test", start_year=2027)
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

        # 2. Campaign current stage must now be 'oq_stage2'
        campaign = db.session.get(Campaign, cid)
        self.assertEqual(campaign.current_stage, 'oq_stage2')

        # 3. Verify OQ Stage 2 data structure
        oq2_data = get_oq_stage2_data(cid)
        self.assertIsNotNone(oq2_data)
        self.assertIn('regions', oq2_data)
        self.assertIn('retained_teams', oq2_data)

        for r_slug in ['pacific', 'americas', 'emea', 'china']:
            # 8 retained teams from Stage 1
            retained = oq2_data['retained_teams'].get(r_slug, [])
            self.assertEqual(len(retained), 8)

            reg_data = oq2_data['regions'].get(r_slug)
            self.assertIsNotNone(reg_data)
            self.assertEqual(reg_data['status'], 'in_progress')
            self.assertEqual(reg_data['current_stage'], 'swiss')
            self.assertEqual(len(reg_data['teams']), 16)

        # 4. Web view GET
        resp = self.client.get(f'/campaign/{cid}/stage/oq_stage2?region=pacific')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Open Qualifier Stage 2', resp.data)

        # 5. Test manual match input
        pac = oq2_data['regions']['pacific']
        r1_m1 = pac['swiss_matches'][0]
        m_id = r1_m1['id']
        team_a_id = r1_m1['team_a']['id']

        man_res = self.client.post(
            f'/api/campaign/{cid}/oq_stage2/match/manual',
            json={
                'region_slug': 'pacific',
                'match_id': m_id,
                'winner_id': team_a_id,
                'maps': [
                    {'map_number': 1, 'team_a_score': 13, 'team_b_score': 7, 'winner_id': team_a_id},
                    {'map_number': 2, 'team_a_score': 13, 'team_b_score': 10, 'winner_id': team_a_id},
                ]
            }
        )
        self.assertEqual(man_res.status_code, 200)
        self.assertTrue(man_res.get_json()['success'])

        # 6. Test match sim
        r1_m2 = pac['swiss_matches'][1]
        sim_res = self.client.post(
            f'/api/campaign/{cid}/oq_stage2/match/sim',
            json={'region_slug': 'pacific', 'match_id': r1_m2['id']}
        )
        self.assertEqual(sim_res.status_code, 200)
        self.assertTrue(sim_res.get_json()['success'])

        # 7. Test sim round
        round_res = self.client.post(
            f'/api/campaign/{cid}/oq_stage2/sim-round',
            json={'region_slug': 'pacific'}
        )
        self.assertEqual(round_res.status_code, 200)
        self.assertTrue(round_res.get_json()['success'])

        # 8. Test sim region
        reg_res = self.client.post(
            f'/api/campaign/{cid}/oq_stage2/sim-region',
            json={'region_slug': 'pacific'}
        )
        self.assertEqual(reg_res.status_code, 200)
        self.assertTrue(reg_res.get_json()['success'])
        updated_data = get_oq_stage2_data(cid)
        self.assertEqual(updated_data['regions']['pacific']['status'], 'completed')
        self.assertEqual(len(updated_data['regions']['pacific']['qualified_teams']), 4)

        # 9. Test sim all 4 regions
        all_res = self.client.post(
            f'/api/campaign/{cid}/oq_stage2/sim-all',
            json={}
        )
        self.assertEqual(all_res.status_code, 200)
        self.assertTrue(all_res.get_json()['success'])

        # 10. Check that campaign advanced to 'stage2'
        campaign = db.session.get(Campaign, cid)
        self.assertEqual(campaign.current_stage, 'stage2')

        stage_rec = CampaignStage.query.filter_by(campaign_id=cid, stage_key='oq_stage2').first()
        self.assertEqual(stage_rec.status, 'completed')


if __name__ == '__main__':
    unittest.main()
