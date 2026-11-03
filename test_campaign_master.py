"""
test_campaign_master.py — Integration test for VCT Masters (Masters Toronto) in Campaign Mode.
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
    get_master_data,
    resolve_master_match_interactive,
    sim_master_round_interactive,
    sim_master_tournament_interactive,
)


class TestCampaignMasterIntegration(unittest.TestCase):
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

    def test_masters_toronto_pipeline_and_features(self):
        # 1. Create campaign and progress through circuit up to Masters Toronto
        campaign = create_campaign("Masters Toronto Integration Test", start_year=2027)
        self.cid = campaign.id
        cid = campaign.id

        run_open_qualifier_stage(cid)
        run_kickoff_stage(cid)
        run_major_stage(cid)
        sim_oq_stage1_all(cid)
        sim_stage1_all_interactive(cid)
        sim_ewc_qualifier_all_interactive(cid)

        # 2. Campaign current stage should now be 'master'
        campaign = db.session.get(Campaign, cid)
        self.assertEqual(campaign.current_stage, 'master')

        # 3. Verify Master stage data initialized
        master_data = get_master_data(cid)
        self.assertIsNotNone(master_data)
        self.assertIn('roster', master_data)
        self.assertEqual(len(master_data['roster']), 12)

        # Verify Seeds: 4 Seed 1s (Champions), 4 Seed 2s (Runners-up), 4 Seed 3s (3rd place)
        seeds = [t['regional_seed'] for t in master_data['roster']]
        self.assertEqual(seeds.count(1), 4)
        self.assertEqual(seeds.count(2), 4)
        self.assertEqual(seeds.count(3), 4)

        res = master_data.get('result')
        self.assertIsNotNone(res)
        self.assertEqual(res['status'], 'in_progress')
        self.assertEqual(res['current_stage'], 'swiss')
        self.assertEqual(len(res['direct_teams']), 4)
        self.assertEqual(len(res['swiss_teams']), 8)
        self.assertEqual(len(res['swiss_matches']), 4)  # Round 1 matches

        # 4. Verify Web Route GET /campaign/<cid>/stage/master
        resp = self.client.get(f'/campaign/{cid}/stage/master')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('VCT Masters'.encode('utf-8'), resp.data)

        # 5. Test API: Manual match override on first Swiss match
        first_match = res['swiss_matches'][0]
        team_a_id = first_match['team_a']['id']
        team_b_id = first_match['team_b']['id']

        manual_res = self.client.post(
            f'/api/campaign/{cid}/master/match/manual',
            json={
                'match_id': first_match['id'],
                'winner_id': team_a_id,
                'maps': [
                    {'map_number': 1, 'team_a_score': 13, 'team_b_score': 10, 'winner_id': team_a_id},
                    {'map_number': 2, 'team_a_score': 13, 'team_b_score': 8, 'winner_id': team_a_id},
                ]
            }
        )
        self.assertEqual(manual_res.status_code, 200)
        manual_data = manual_res.get_json()
        self.assertTrue(manual_data['success'])
        self.assertEqual(manual_data['result']['match']['winner_id'], team_a_id)
        self.assertTrue(manual_data['result']['match']['is_manual'])

        # 6. Test API: Sim single match roll on second Swiss match
        second_match = res['swiss_matches'][1]
        sim_res = self.client.post(
            f'/api/campaign/{cid}/master/match/sim',
            json={'match_id': second_match['id']}
        )
        self.assertEqual(sim_res.status_code, 200)
        sim_data = sim_res.get_json()
        self.assertTrue(sim_data['success'])
        self.assertIsNotNone(sim_data['result']['match']['winner_id'])

        # 7. Test API: Sim active round
        round_res = self.client.post(f'/api/campaign/{cid}/master/sim-round', json={})
        self.assertEqual(round_res.status_code, 200)
        self.assertTrue(round_res.get_json()['success'])

        # 8. Test API: Sim entire remaining tournament
        all_res = self.client.post(f'/api/campaign/{cid}/master/sim-all', json={})
        self.assertEqual(all_res.status_code, 200)
        self.assertTrue(all_res.get_json()['success'])

        # 9. Verify completion state
        updated_data = get_master_data(cid)
        final_res = updated_data['result']
        self.assertEqual(final_res['status'], 'completed')
        self.assertEqual(final_res['current_stage'], 'playoffs')
        self.assertEqual(len(final_res['swiss_qualifiers']), 4)
        self.assertEqual(len(final_res['swiss_eliminated']), 4)
        self.assertEqual(len(final_res['playoff_matches']), 14)
        self.assertIsNotNone(final_res['champion'])
        self.assertIsNotNone(final_res['runner_up'])

        # 10. Verify Standings and Championship Points (7, 5, 4, 3, 2, 2, 0...)
        standings = final_res['standings']
        self.assertEqual(len(standings), 12)
        self.assertEqual(standings[0]['rank'], 1)
        self.assertEqual(standings[0]['cp'], 7)
        self.assertEqual(standings[1]['rank'], 2)
        self.assertEqual(standings[1]['cp'], 5)
        self.assertEqual(standings[2]['rank'], 3)
        self.assertEqual(standings[2]['cp'], 4)
        self.assertEqual(standings[3]['rank'], 4)
        self.assertEqual(standings[3]['cp'], 3)
        self.assertEqual(standings[4]['rank'], 5)
        self.assertEqual(standings[4]['cp'], 2)
        self.assertEqual(standings[5]['rank'], 6)
        self.assertEqual(standings[5]['cp'], 2)

        # 11. Verify Campaign and Stage transitions
        campaign = db.session.get(Campaign, cid)
        self.assertEqual(campaign.current_stage, 'ewc')
        m_stage = CampaignStage.query.filter_by(campaign_id=cid, stage_key='master').first()
        self.assertEqual(m_stage.status, 'completed')

        # 12. Verify Championship Points in club state for Champion (+7 CP)
        champ_id = final_res['champion']['id']
        champ_cs = CampaignClubState.query.filter_by(campaign_id=cid, club_id=champ_id).first()
        self.assertEqual(champ_cs.get_stage_rank('master'), 1)
        self.assertGreaterEqual(champ_cs.championship_points, 7)


if __name__ == '__main__':
    unittest.main()
