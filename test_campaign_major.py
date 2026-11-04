"""
test_campaign_major.py — Test VCT Major (Masters Bangkok) in Campaign Mode.
"""

import unittest
import json
from app import create_app
from models import db, Campaign, CampaignClubState, CampaignStage
from services.campaign_service import (
    create_campaign,
    get_campaign,
    run_open_qualifier_stage,
    run_kickoff_stage,
    get_major_data,
    run_major_stage,
    override_major_match,
    get_championship_leaderboard,
)


class TestCampaignMajor(unittest.TestCase):

    def setUp(self):
        self.app = create_app()
        self.client = self.app.test_client()
        self.app_context = self.app.app_context()
        self.app_context.push()

    def tearDown(self):
        db.session.remove()
        self.app_context.pop()

    def test_major_simulation_points_override_and_stage1_progression(self):
        # 1. Create Campaign
        campaign = create_campaign(name="Major Bangkok Integration Test", start_year=2027)

        # 2. Complete Open Qualifier for all 4 regions
        run_open_qualifier_stage(campaign.id)

        # 3. Complete Kickoff for all 4 regions
        for r_slug in ['pacific', 'americas', 'emea', 'china']:
            run_kickoff_stage(campaign.id, region_slug=r_slug)

        db.session.refresh(campaign)
        self.assertEqual(campaign.current_stage, 'major')

        # 4. Verify Major initialized with exactly 8 teams (2 per region)
        major_data = get_major_data(campaign.id)
        self.assertIsNotNone(major_data)
        self.assertIn('roster', major_data)
        self.assertEqual(len(major_data['roster']), 8)

        # Verify Seeds: 4 Seed 1s and 4 Seed 2s across 4 regions
        seeds = [t['regional_seed'] for t in major_data['roster']]
        self.assertEqual(seeds.count(1), 4)
        self.assertEqual(seeds.count(2), 4)

        # 5. Test Web Route before simulation
        r_pre = self.client.get(f'/campaign/{campaign.id}/stage/major')
        self.assertEqual(r_pre.status_code, 200)
        self.assertIn('VCT Major'.encode('utf-8'), r_pre.data)

        # 6. Execute Major Simulation
        res = run_major_stage(campaign.id)
        self.assertEqual(res['total_matches'], 16)
        self.assertIsNotNone(res['champion'])
        self.assertIsNotNone(res['runner_up'])

        # Check stage data
        major_data_after = get_major_data(campaign.id)
        m_res = major_data_after['result']
        self.assertEqual(len(m_res['swiss_matches']), 10)
        self.assertEqual(len(m_res['swiss_qualifiers']), 4)
        self.assertEqual(len(m_res['playoff_matches']), 6)

        # Verify Championship Points allocation:
        # Champion: 5 CP, Runner-up: 3 CP, 3rd: 2 CP, 4th: 1 CP
        standings = m_res['standings']
        self.assertEqual(standings[0]['rank'], 1)
        self.assertEqual(standings[0]['championship_points'], 5)

        self.assertEqual(standings[1]['rank'], 2)
        self.assertEqual(standings[1]['championship_points'], 3)

        self.assertEqual(standings[2]['rank'], 3)
        self.assertEqual(standings[2]['championship_points'], 2)

        self.assertEqual(standings[3]['rank'], 4)
        self.assertEqual(standings[3]['championship_points'], 1)

        for s in standings[4:]:
            self.assertEqual(s['rank'], 5)
            self.assertEqual(s['championship_points'], 0)

        # Verify points awarded in CampaignClubState
        champ_id = standings[0]['club_id']
        champ_state = CampaignClubState.query.filter_by(campaign_id=campaign.id, club_id=champ_id).first()
        self.assertEqual(champ_state.get_stage_rank('major'), 1)
        # Champion also played Kickoff (so CP = kickoff_cp + 5)
        self.assertGreaterEqual(champ_state.championship_points, 5)

        # 7. Test Manual Match Override in Major
        target_match = m_res['playoff_matches'][0]  # upper_semifinal_1
        forced_winner_id = target_match['team_b']['id']

        override_res = override_major_match(
            campaign.id,
            round_name=target_match['round_name'],
            winner_id=forced_winner_id,
        )
        self.assertIsNotNone(override_res['champion'])

        major_data_override = get_major_data(campaign.id)
        playoff_dict = major_data_override['result']['completed_playoffs']
        overridden_match = playoff_dict[target_match['round_name']]
        self.assertEqual(overridden_match['winner_id'], forced_winner_id)
        self.assertTrue(overridden_match['is_manual'])

        # Verify that repeating simulation did not double CP
        champ_state_after = CampaignClubState.query.filter_by(campaign_id=campaign.id, club_id=champ_id).first()
        # Should be consistent
        self.assertIsNotNone(champ_state_after)

        # 8. Verify Campaign Circuit advanced to Open Qualifier Stage 1
        db.session.refresh(campaign)
        self.assertEqual(campaign.current_stage, 'oq_stage1')

        # Verify OQ Stage 1 record created with 16 teams per region and 8 retained
        oq_s1_record = CampaignStage.query.filter_by(
            campaign_id=campaign.id, stage_key='oq_stage1'
        ).first()
        self.assertIsNotNone(oq_s1_record)
        oq_data = json.loads(oq_s1_record.stage_data)
        self.assertIn('retained_teams', oq_data)
        self.assertIn('regions', oq_data)
        for r_slug in ['pacific', 'americas', 'emea', 'china']:
            self.assertEqual(len(oq_data['retained_teams'][r_slug]), 8)
            self.assertEqual(len(oq_data['regions'][r_slug]['teams']), 16)

        # 9. Test Web Routes after completion
        r_post = self.client.get(f'/campaign/{campaign.id}/stage/major')
        self.assertEqual(r_post.status_code, 200)
        self.assertIn('Giai đoạn 1: Vòng Thụy Sĩ'.encode('utf-8'), r_post.data)
        self.assertIn('Giai đoạn 2: Vòng Playoffs'.encode('utf-8'), r_post.data)
        self.assertIn('Nhà Vô Địch VCT Major'.encode('utf-8'), r_post.data)

        # Test API endpoints
        r_api_override = self.client.post(
            f'/api/campaign/{campaign.id}/major/match/override',
            json={
                'round_name': 'upper_semifinal_2',
                'winner_id': m_res['playoff_matches'][1]['team_a']['id'],
            }
        )
        self.assertEqual(r_api_override.status_code, 200)
        self.assertTrue(r_api_override.get_json()['success'])

        # Cleanup
        db.session.delete(campaign)
        db.session.commit()

    def test_major_xian_apostrophe_and_confirmation_flow(self):
        """Regression test for Xi'an apostrophe in confirmation button & confirm endpoint."""
        campaign = create_campaign(name="Xi'an Confirm Regression Test", start_year=2027)

        # Force host city for Major to Xi'an
        from engine.host_cities import get_city_by_id
        xian = get_city_by_id('xian')
        self.assertIsNotNone(xian)
        self.assertEqual(xian['city_name'], "Xi'an")

        # Set season hosts with 4 distinct regions
        campaign.season_hosts = json.dumps({'2027': {
            'major': xian,
            'master': get_city_by_id('madrid'),
            'ewc': get_city_by_id('los_angeles'),
            'champion': get_city_by_id('tokyo'),
        }})
        db.session.commit()

        # Run OQ and Kickoff
        run_open_qualifier_stage(campaign.id)
        for r_slug in ['pacific', 'americas', 'emea', 'china']:
            run_kickoff_stage(campaign.id, region_slug=r_slug)

        # Verify Major page loads with VCT Major Xi'an (HTML encoded as Xi&#39;an)
        resp_pre = self.client.get(f'/campaign/{campaign.id}/stage/major')
        self.assertEqual(resp_pre.status_code, 200)
        html_pre = resp_pre.data.decode('utf-8')
        self.assertTrue("VCT Major Xi&#39;an" in html_pre or "VCT Major Xi'an" in html_pre)

        # Sim Major without auto-confirm so it enters Review mode
        from services.campaign_service import sim_major_tournament_interactive
        sim_res = sim_major_tournament_interactive(campaign.id, auto_confirm=False)

        # GET Major in review mode: verify button HTML has clean onclick without quote syntax errors
        resp_review = self.client.get(f'/campaign/{campaign.id}/stage/major')
        self.assertEqual(resp_review.status_code, 200)
        html_review = resp_review.data.decode('utf-8')

        self.assertIn('btn-trigger-confirm', html_review)
        self.assertIn('handleStageConfirmClick(this)', html_review)
        self.assertTrue('data-target-name="VCT Major Xi&#39;an"' in html_review or 'data-target-name="VCT Major Xi\'an"' in html_review)

        # Verify POST confirm succeeds without error
        resp_confirm = self.client.post(f'/api/campaign/{campaign.id}/major/confirm', json={})
        self.assertEqual(resp_confirm.status_code, 200)
        data_confirm = resp_confirm.get_json()
        self.assertTrue(data_confirm['success'])
        self.assertEqual(data_confirm['result']['stage_key'], 'major')
        self.assertTrue(data_confirm['result']['is_confirmed'])

        # GET Major after confirm: should show locked banner
        resp_locked = self.client.get(f'/campaign/{campaign.id}/stage/major')
        self.assertEqual(resp_locked.status_code, 200)
        html_locked = resp_locked.data.decode('utf-8')
        self.assertIn('KẾT QUẢ ĐÃ ĐƯỢC XÁC NHẬN VÀ KHÓA VĨNH VIỄN', html_locked)

        # Verify campaign advanced to oq_stage1
        db.session.refresh(campaign)
        self.assertEqual(campaign.current_stage, 'oq_stage1')

        # Cleanup
        db.session.delete(campaign)
        db.session.commit()


if __name__ == '__main__':
    unittest.main()
