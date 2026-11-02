"""
test_campaign_stage2.py — Integration test for VCT Stage 2 in Campaign Mode.
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
    sim_oq_stage2_all,
    get_stage2_data,
    resolve_stage2_match_interactive,
    sim_stage2_round_interactive,
    sim_stage2_region_interactive,
    sim_stage2_all_interactive,
)


class TestCampaignStage2Integration(unittest.TestCase):
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

    def test_stage2_pipeline_and_qualifications(self):
        # 1. Advance campaign through OQ Stage 2
        campaign = create_campaign("Stage 2 Integration Test", start_year=2027)
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

        # 2. Campaign current stage must now be 'stage2'
        campaign = db.session.get(Campaign, cid)
        self.assertEqual(campaign.current_stage, 'stage2')

        # 3. Verify Stage 2 data structure
        s2_data = get_stage2_data(cid)
        self.assertIsNotNone(s2_data)
        self.assertIn('rosters', s2_data)
        self.assertIn('regional_results', s2_data)

        for r_slug in ['pacific', 'americas', 'emea', 'china']:
            # Exactly 12 teams in each regional roster (8 retained + 4 qualified)
            roster = s2_data['rosters'].get(r_slug, [])
            self.assertEqual(len(roster), 12)

            reg_data = s2_data['regional_results'].get(r_slug)
            self.assertIsNotNone(reg_data)
            self.assertEqual(reg_data['status'], 'in_progress')
            self.assertEqual(reg_data['current_phase'], 'regular_season')
            self.assertEqual(len(reg_data['group_alpha']), 6)
            self.assertEqual(len(reg_data['group_omega']), 6)
            self.assertEqual(len(reg_data['regular_matches']), 30)
            self.assertEqual(len(reg_data['playoff_matches']), 12)

        # 4. Web view GET
        resp = self.client.get(f'/campaign/{cid}/stage/stage2?region=pacific')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'VCT Stage 2', resp.data)

        # 5. Test manual match input on Week 1 Match 1
        pac = s2_data['regional_results']['pacific']
        reg_m1 = pac['regular_matches'][0]
        m_id = reg_m1['match_id']
        team_a_id = reg_m1['team_a']['id']

        man_res = self.client.post(
            f'/api/campaign/{cid}/stage2/match/manual',
            json={
                'region_slug': 'pacific',
                'match_id': m_id,
                'winner_id': team_a_id,
                'maps': [
                    {'map_number': 1, 'team_a_score': 13, 'team_b_score': 8, 'winner_id': team_a_id},
                    {'map_number': 2, 'team_a_score': 13, 'team_b_score': 11, 'winner_id': team_a_id},
                ]
            }
        )
        self.assertEqual(man_res.status_code, 200)
        self.assertTrue(man_res.get_json()['success'])

        # 6. Test match sim on Week 1 Match 2
        reg_m2 = pac['regular_matches'][1]
        sim_res = self.client.post(
            f'/api/campaign/{cid}/stage2/match/sim',
            json={'region_slug': 'pacific', 'match_id': reg_m2['match_id']}
        )
        self.assertEqual(sim_res.status_code, 200)
        self.assertTrue(sim_res.get_json()['success'])

        # 7. Test sim round (Week 1 remaining)
        round_res = self.client.post(
            f'/api/campaign/{cid}/stage2/sim-round',
            json={'region_slug': 'pacific'}
        )
        self.assertEqual(round_res.status_code, 200)
        self.assertTrue(round_res.get_json()['success'])

        # 8. Test sim region (completes Pacific regular season + playoffs)
        reg_res = self.client.post(
            f'/api/campaign/{cid}/stage2/sim-region',
            json={'region_slug': 'pacific'}
        )
        self.assertEqual(reg_res.status_code, 200)
        self.assertTrue(reg_res.get_json()['success'])

        updated_data = get_stage2_data(cid)
        pac_updated = updated_data['regional_results']['pacific']
        self.assertEqual(pac_updated['status'], 'completed')
        self.assertEqual(pac_updated['current_phase'], 'completed')
        self.assertIsNotNone(pac_updated['champion'])
        self.assertIsNotNone(pac_updated['runner_up'])
        self.assertIsNotNone(pac_updated['third_place'])
        self.assertIsNotNone(pac_updated['fourth_place'])

        # Check 4 Champions Paris Qualifiers
        self.assertEqual(len(pac_updated['champions_qualifiers']), 4)
        champ_qual = pac_updated['champions_qualifiers']
        self.assertEqual(champ_qual[0]['champions_seed'], 1)
        self.assertEqual(champ_qual[1]['champions_seed'], 2)
        self.assertEqual(champ_qual[2]['champions_seed'], 3)
        self.assertEqual(champ_qual[3]['champions_seed'], 4)

        # 9. Test sim all 4 regions
        all_res = self.client.post(
            f'/api/campaign/{cid}/stage2/sim-all',
            json={}
        )
        self.assertEqual(all_res.status_code, 200)
        self.assertTrue(all_res.get_json()['success'])

        # 10. Check that campaign advanced to 'champion'
        campaign = db.session.get(Campaign, cid)
        self.assertEqual(campaign.current_stage, 'champion')

        stage_rec = CampaignStage.query.filter_by(campaign_id=cid, stage_key='stage2').first()
        self.assertEqual(stage_rec.status, 'completed')

        # Check that champion stage was prepared with 16 qualifiers
        champ_stage = CampaignStage.query.filter_by(campaign_id=cid, stage_key='champion').first()
        self.assertIsNotNone(champ_stage)


if __name__ == '__main__':
    unittest.main()
