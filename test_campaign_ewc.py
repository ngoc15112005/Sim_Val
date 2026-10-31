"""
test_campaign_ewc.py — Integration test for Esports World Cup (EWC) in Campaign Mode.
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
    get_ewc_data,
    resolve_ewc_match_interactive,
    sim_ewc_round_interactive,
    sim_ewc_tournament_interactive,
)


class TestCampaignEWCIntegration(unittest.TestCase):
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

    def test_ewc_pipeline_and_features(self):
        # 1. Progress circuit up to EWC
        campaign = create_campaign("EWC Integration Test", start_year=2027)
        self.cid = campaign.id
        cid = campaign.id

        run_open_qualifier_stage(cid)
        run_kickoff_stage(cid)
        run_major_stage(cid)
        sim_oq_stage1_all(cid)
        sim_stage1_all_interactive(cid)
        sim_ewc_qualifier_all_interactive(cid)
        sim_master_tournament_interactive(cid)

        # 2. Campaign current stage should now be 'ewc'
        campaign = db.session.get(Campaign, cid)
        self.assertEqual(campaign.current_stage, 'ewc')

        # 3. Verify EWC stage data initialized
        ewc_data = get_ewc_data(cid)
        self.assertIsNotNone(ewc_data)
        self.assertIn('roster', ewc_data)
        self.assertEqual(len(ewc_data['roster']), 16)

        res = ewc_data.get('result')
        self.assertIsNotNone(res)
        self.assertEqual(res['status'], 'in_progress')
        self.assertEqual(res['current_stage'], 'groups')
        self.assertEqual(len(res['groups']), 4)

        # Verify Group A has 4 teams, max 1 per region, seeds 1 to 4
        grp_a = res['groups']['A']
        self.assertEqual(len(grp_a['teams']), 4)
        grp_a_seeds = [t['regional_seed'] for t in grp_a['teams']]
        self.assertEqual(sorted(grp_a_seeds), [1, 2, 3, 4])
        grp_a_regs = [t['region'] for t in grp_a['teams']]
        self.assertEqual(len(set(grp_a_regs)), 4)

        # 4. Verify Web Route GET /campaign/<cid>/stage/ewc
        # Note: If template is not created yet, client test will fail until template exists.
        # Let's test the engine & API first.

        # 5. Test API: Manual match override on Group A Opening 1
        m1 = grp_a['matches']['groupA_opening1']
        team_a_id = m1['team_a']['id']

        manual_res = self.client.post(
            f'/api/campaign/{cid}/ewc/match/manual',
            json={
                'match_id': m1['id'],
                'winner_id': team_a_id,
                'maps': [
                    {'map_number': 1, 'team_a_score': 13, 'team_b_score': 9, 'winner_id': team_a_id},
                    {'map_number': 2, 'team_a_score': 13, 'team_b_score': 11, 'winner_id': team_a_id},
                ]
            }
        )
        self.assertEqual(manual_res.status_code, 200)
        manual_data = manual_res.get_json()
        self.assertTrue(manual_data['success'])
        self.assertEqual(manual_data['result']['match']['winner_id'], team_a_id)
        self.assertTrue(manual_data['result']['match']['is_manual'])

        # 6. Test API: Sim single match roll on Group A Opening 2
        m2 = grp_a['matches']['groupA_opening2']
        sim_res = self.client.post(
            f'/api/campaign/{cid}/ewc/match/sim',
            json={'match_id': m2['id']}
        )
        self.assertEqual(sim_res.status_code, 200)
        sim_data = sim_res.get_json()
        self.assertTrue(sim_data['success'])
        self.assertIsNotNone(sim_data['result']['match']['winner_id'])

        # 7. Test API: Sim active round
        round_res = self.client.post(f'/api/campaign/{cid}/ewc/sim-round', json={})
        self.assertEqual(round_res.status_code, 200)
        self.assertTrue(round_res.get_json()['success'])

        # 8. Test API: Sim entire remaining tournament
        all_res = self.client.post(f'/api/campaign/{cid}/ewc/sim-all', json={})
        self.assertEqual(all_res.status_code, 200)
        self.assertTrue(all_res.get_json()['success'])

        # 9. Verify completion state
        updated_data = get_ewc_data(cid)
        final_res = updated_data['result']
        self.assertEqual(final_res['status'], 'completed')
        self.assertEqual(final_res['current_stage'], 'playoffs')
        self.assertEqual(len(final_res['playoff_matches']), 8)
        self.assertIsNotNone(final_res['champion'])
        self.assertIsNotNone(final_res['runner_up'])
        self.assertIsNotNone(final_res['third_place'])
        self.assertIsNotNone(final_res['fourth_place'])

        # 10. Verify Standings (16 teams total, 0 CP)
        standings = final_res['standings']
        self.assertEqual(len(standings), 16)
        self.assertEqual(standings[0]['rank'], 1)
        self.assertEqual(standings[1]['rank'], 2)
        self.assertEqual(standings[2]['rank'], 3)
        self.assertEqual(standings[3]['rank'], 4)
        for s in standings:
            self.assertEqual(s.get('cp', 0), 0)

        # 11. Verify Campaign transition to 'stage2'
        campaign = db.session.get(Campaign, cid)
        self.assertEqual(campaign.current_stage, 'stage2')
        ewc_stage = CampaignStage.query.filter_by(campaign_id=cid, stage_key='ewc').first()
        self.assertEqual(ewc_stage.status, 'completed')


if __name__ == '__main__':
    unittest.main()
