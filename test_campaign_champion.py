"""
test_campaign_champion.py — Integration test for VALORANT Champions Paris in Campaign Mode.
"""

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
    get_champion_data,
    resolve_champion_match_interactive,
    sim_champion_round_interactive,
    sim_champion_tournament_interactive,
)


class TestCampaignChampionIntegration(unittest.TestCase):
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

    def test_champion_full_circuit_and_mechanics(self):
        # 1. Advance campaign through VCT Stage 2
        campaign = create_campaign("Champions Paris Integration Test", start_year=2027)
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

        # 2. Campaign current stage should now be 'champion'
        campaign = db.session.get(Campaign, cid)
        self.assertEqual(campaign.current_stage, 'champion')

        # 3. Verify Champions data structure and 16-team roster
        ch_data = get_champion_data(cid)
        self.assertIsNotNone(ch_data)
        self.assertIn('roster', ch_data)
        self.assertEqual(len(ch_data['roster']), 16)

        # 4 regions x 4 pools
        pools = [t['pool'] for t in ch_data['roster']]
        self.assertEqual(pools.count(1), 4)
        self.assertEqual(pools.count(2), 4)
        self.assertEqual(pools.count(3), 4)
        self.assertEqual(pools.count(4), 4)

        res = ch_data.get('result')
        self.assertIsNotNone(res)
        self.assertEqual(res['status'], 'in_progress')
        self.assertEqual(res['current_stage'], 'groups')
        self.assertEqual(len(res['groups']), 4)

        # Verify GSL Group diversity (4 teams per group, max 1 per region)
        for g_lbl in ['A', 'B', 'C', 'D']:
            grp = res['groups'][g_lbl]
            self.assertEqual(len(grp['teams']), 4)
            regions = [t.get('region_slug') or t.get('region') for t in grp['teams']]
            self.assertEqual(len(set(regions)), 4, f"Group {g_lbl} must have 4 distinct regions")

        # 4. Test Web Route GET /campaign/<cid>/stage/champion
        resp = self.client.get(f'/campaign/{cid}/stage/champion')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'VALORANT Champions Paris', resp.data)

        # 5. Test manual match override on Group A Opening 1
        grp_a = res['groups']['A']
        op1 = grp_a['matches']['groupA_opening1']
        team_a_id = op1['team_a']['id'] if 'id' in op1['team_a'] else op1['team_a']['club_id']

        man_res = self.client.post(
            f'/api/campaign/{cid}/champion/match/manual',
            json={
                'match_id': op1['id'],
                'winner_id': team_a_id,
                'maps': [
                    {'map_number': 1, 'team_a_score': 13, 'team_b_score': 8, 'winner_id': team_a_id},
                    {'map_number': 2, 'team_a_score': 13, 'team_b_score': 10, 'winner_id': team_a_id},
                ]
            }
        )
        self.assertEqual(man_res.status_code, 200)
        man_json = man_res.get_json()
        self.assertTrue(man_json['success'])

        # Verify match updated
        ch_data = get_champion_data(cid)
        up_op1 = ch_data['result']['groups']['A']['matches']['groupA_opening1']
        self.assertEqual(up_op1['status'], 'completed')
        self.assertEqual(up_op1['winner_id'], team_a_id)
        self.assertEqual(up_op1['team_a_score'], 2)

        # 6. Test match roll on Group A Opening 2
        op2 = ch_data['result']['groups']['A']['matches']['groupA_opening2']
        roll_res = self.client.post(
            f'/api/campaign/{cid}/champion/match/sim',
            json={'match_id': op2['id']}
        )
        self.assertEqual(roll_res.status_code, 200)
        self.assertTrue(roll_res.get_json()['success'])

        # 7. Test Sim Round
        rnd_res = self.client.post(f'/api/campaign/{cid}/champion/sim-round', json={})
        self.assertEqual(rnd_res.status_code, 200)
        self.assertTrue(rnd_res.get_json()['success'])

        # 8. Test Sim All Champions Paris
        all_res = self.client.post(f'/api/campaign/{cid}/champion/sim-all', json={})
        self.assertEqual(all_res.status_code, 200)
        self.assertTrue(all_res.get_json()['success'])

        # 9. Verify tournament completed, podium, and standings
        ch_data = get_champion_data(cid)
        final_res = ch_data['result']
        self.assertEqual(final_res['status'], 'completed')
        self.assertIsNotNone(final_res['champion'])
        self.assertIsNotNone(final_res['runner_up'])
        self.assertIsNotNone(final_res['third_place'])
        self.assertIsNotNone(final_res['fourth_place'])
        self.assertEqual(len(final_res['standings']), 16)
        self.assertEqual(final_res['standings'][0]['rank'], 1)
        self.assertEqual(final_res['standings'][1]['rank'], 2)

        # 10. Check Story rating reward applied to World Champion
        champ_id = final_res['champion']['id'] if 'id' in final_res['champion'] else final_res['champion']['club_id']
        champ_state = CampaignClubState.query.filter_by(campaign_id=cid, club_id=champ_id).first()
        self.assertIsNotNone(champ_state)
        self.assertGreaterEqual(champ_state.story_rating, 90)

        # 11. Check campaign transitioned to 'season_summary'
        campaign = db.session.get(Campaign, cid)
        self.assertEqual(campaign.current_stage, 'season_summary')

        champ_stage = CampaignStage.query.filter_by(campaign_id=cid, stage_key='champion').first()
        self.assertEqual(champ_stage.status, 'completed')

        summary_stage = CampaignStage.query.filter_by(campaign_id=cid, stage_key='season_summary').first()
        self.assertIsNotNone(summary_stage)


if __name__ == '__main__':
    unittest.main()
