import json
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
    get_ewc_qualifier_data,
    sim_ewc_qualifier_round_interactive,
    sim_ewc_qualifier_region_interactive,
    sim_ewc_qualifier_all_interactive,
    resolve_ewc_qualifier_match_interactive,
    is_stage_region_actually_completed,
)


class TestCampaignEWCQualifierIntegration(unittest.TestCase):
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

    def test_ewc_qualifier_full_pipeline(self):
        # 1. Create campaign and progress through OQ, Kickoff, Major, OQ Stage 1, Stage 1
        campaign = create_campaign("EWC Qualifier Pipeline Test", start_year=2027)
        self.cid = campaign.id
        cid = campaign.id

        run_open_qualifier_stage(cid)
        run_kickoff_stage(cid)
        run_major_stage(cid)
        sim_oq_stage1_all(cid)
        sim_stage1_all_interactive(cid)

        # 2. Campaign should now be at 'ewc_qualifier'
        campaign = Campaign.query.get(cid)
        self.assertEqual(campaign.current_stage, 'ewc_qualifier')

        # 3. Verify EWC Qualifier data initialized
        eq_data = get_ewc_qualifier_data(cid)
        self.assertIsNotNone(eq_data)
        self.assertIn('regions', eq_data)
        self.assertIn('direct_ewc_qualifiers', eq_data)

        # In Pacific: exactly 16 teams in Phase 1 and 6 direct in Phase 2
        pac_reg = eq_data['regions']['pacific']
        self.assertEqual(len(pac_reg['phase1_teams']), 16)
        self.assertEqual(len(pac_reg['phase2_direct_teams']), 6)
        self.assertEqual(pac_reg['status'], 'in_progress')
        self.assertEqual(pac_reg['current_phase'], 'phase1')

        # Direct qualifiers from Stage 1: exactly 2 teams per region
        pac_direct = eq_data['direct_ewc_qualifiers']['pacific']
        self.assertEqual(len(pac_direct), 2)
        self.assertEqual(pac_direct[0]['pool'], 1)
        self.assertEqual(pac_direct[1]['pool'], 2)

        # 4. Test View Web Route
        resp = self.client.get(f'/campaign/{cid}/stage/ewc_qualifier?region=pacific')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('EWC Regional Qualifier'.encode('utf-8'), resp.data)

        # 5. Test Match Roll via API
        m1_id = pac_reg['phase1_matches'][0]['id']
        resp_roll = self.client.post(
            f'/api/campaign/{cid}/ewc_qualifier/match/sim',
            json={'region': 'pacific', 'match_id': m1_id}
        )
        self.assertEqual(resp_roll.status_code, 200)
        self.assertTrue(resp_roll.get_json()['success'])

        # 6. Test Manual Match Score Entry and Edit via API
        m2 = pac_reg['phase1_matches'][1]
        team_a_id = m2['team_a']['id']
        resp_manual = self.client.post(
            f'/api/campaign/{cid}/ewc_qualifier/match/manual',
            json={'region': 'pacific', 'match_id': m2['id'], 'winner_id': team_a_id}
        )
        self.assertEqual(resp_manual.status_code, 200)
        self.assertTrue(resp_manual.get_json()['success'])

        # 7. Test Sim Round via API
        resp_round = self.client.post(
            f'/api/campaign/{cid}/ewc_qualifier/sim-round',
            json={'region': 'pacific'}
        )
        self.assertEqual(resp_round.status_code, 200)
        self.assertTrue(resp_round.get_json()['success'])

        # 8. Sim all 4 regions in EWC Qualifier to completion
        resp_all = self.client.post(
            f'/api/campaign/{cid}/ewc_qualifier/sim-all',
            json={}
        )
        self.assertEqual(resp_all.status_code, 200)
        self.assertTrue(resp_all.get_json()['success'])

        # 9. Verify progression to 'master' (Masters Toronto)
        campaign = Campaign.query.get(cid)
        self.assertEqual(campaign.current_stage, 'master')

        # 10. Verify EWC roster now has all 16 teams (4 per region: pools 1, 2, 3, 4)
        ewc_rec = CampaignStage.query.filter_by(campaign_id=cid, stage_key='ewc').first()
        self.assertIsNotNone(ewc_rec)
        e_data = json.loads(ewc_rec.stage_data)
        self.assertEqual(len(e_data['roster']), 16)

        # Verify pool distribution
        pools = [t['pool'] for t in e_data['roster'] if t['region_slug'] == 'pacific']
        self.assertEqual(sorted(pools), [1, 2, 3, 4])

        # 11. Crucial regression check: calling get_ewc_qualifier_data does not revert stage
        re_data = get_ewc_qualifier_data(cid)
        campaign = db.session.get(Campaign, cid)
        self.assertEqual(campaign.current_stage, 'master')
        self.assertTrue(re_data['regions']['pacific']['is_confirmed'])

    def test_ewc_qualifier_review_lock_flow(self):
        """Test the interactive flow without auto-confirm: review mode, lock, and continue buttons."""
        campaign = create_campaign("EWC Qualifier Review Lock Test", start_year=2027)
        self.cid = campaign.id
        cid = campaign.id

        run_open_qualifier_stage(cid)
        run_kickoff_stage(cid)
        run_major_stage(cid)
        sim_oq_stage1_all(cid)
        sim_stage1_all_interactive(cid)

        # 1. Sim Pacific region only with auto_confirm=False (as done by frontend UI)
        resp_reg = self.client.post(
            f'/api/campaign/{cid}/ewc_qualifier/sim-region',
            json={'region': 'pacific', 'auto_confirm': False}
        )
        self.assertEqual(resp_reg.status_code, 200)

        # 2. Pacific is completed but NOT confirmed
        eq_data = get_ewc_qualifier_data(cid)
        pac = eq_data['regions']['pacific']
        is_done, reason = is_stage_region_actually_completed('ewc_qualifier', pac)
        self.assertTrue(is_done, f"Completion check failed: {reason}")
        self.assertTrue(pac['matches_completed'])
        self.assertEqual(pac['status'], 'completed')
        self.assertFalse(pac.get('is_confirmed', False))

        # 3. View Pacific: Review banner and lock button should be present
        resp_view = self.client.get(f'/campaign/{cid}/stage/ewc_qualifier?region=pacific')
        self.assertEqual(resp_view.status_code, 200)
        html = resp_view.data.decode('utf-8')
        self.assertIn('review-confirmation-banner', html)
        self.assertIn('Xác nhận & Khóa PACIFIC', html)

        # 4. Confirm Pacific individually
        resp_lock = self.client.post(
            f'/api/campaign/{cid}/ewc_qualifier/confirm-region',
            json={'region_slug': 'pacific'}
        )
        self.assertEqual(resp_lock.status_code, 200)
        self.assertTrue(resp_lock.get_json()['success'])

        # View Pacific again: Locked banner should be present
        resp_view2 = self.client.get(f'/campaign/{cid}/stage/ewc_qualifier?region=pacific')
        html2 = resp_view2.data.decode('utf-8')
        self.assertIn('KẾT QUẢ ĐÃ ĐƯỢC XÁC NHẬN VÀ KHÓA VĨNH VIỄN', html2)

        # 5. Sim remaining regions with auto_confirm=False
        for r in ['americas', 'emea', 'china']:
            resp_sim = self.client.post(
                f'/api/campaign/{cid}/ewc_qualifier/sim-region',
                json={'region': r, 'auto_confirm': False}
            )
            self.assertEqual(resp_sim.status_code, 200)

        # 6. Confirm all remaining via confirm-all
        resp_lock_all = self.client.post(
            f'/api/campaign/{cid}/ewc_qualifier/confirm-all',
            json={}
        )
        self.assertEqual(resp_lock_all.status_code, 200)
        self.assertTrue(resp_lock_all.get_json()['success'])

        # 7. Campaign advanced to 'master', EWC stage populated
        campaign = db.session.get(Campaign, cid)
        self.assertEqual(campaign.current_stage, 'master')

        # 8. View should show Advance button and Header button to Masters Toronto
        resp_view3 = self.client.get(f'/campaign/{cid}/stage/ewc_qualifier?region=pacific')
        html3 = resp_view3.data.decode('utf-8')
        self.assertIn(f'/campaign/{cid}/stage/master', html3)
        self.assertIn('Tới VCT Masters Toronto', html3)
        self.assertIn('Tiếp tục sang giải đấu tiếp theo', html3)


if __name__ == '__main__':
    unittest.main()
