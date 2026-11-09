import unittest
import json
from app import create_app
from models import db, Campaign, CampaignStage
from services.campaign_service import (
    create_campaign,
    get_campaign,
    get_stage_record,
    run_open_qualifier_stage,
    run_kickoff_stage,
    override_kickoff_match,
    get_kickoff_data,
    confirm_stage_region,
    confirm_stage_all,
    confirm_stage_tournament,
    run_major_stage,
    get_major_data,
    override_major_match,
)


class TestCampaignConfirmationFlow(unittest.TestCase):

    def setUp(self):
        self.app = create_app()
        self.client = self.app.test_client()
        self.app_context = self.app.app_context()
        self.app_context.push()

    def tearDown(self):
        db.session.remove()
        self.app_context.pop()

    def test_regional_confirmation_and_locking(self):
        # 1. Create Campaign
        campaign = create_campaign(name="Confirmation Flow Test", start_year=2028)
        self.assertEqual(campaign.current_stage, 'open_qualifier')

        # Auto-confirm OQ to get to Kickoff
        run_open_qualifier_stage(campaign.id, auto_confirm=True)
        db.session.refresh(campaign)
        self.assertEqual(campaign.current_stage, 'kickoff')

        # 2. Simulate Pacific Kickoff with auto_confirm=False
        res = run_kickoff_stage(campaign.id, region_slug='pacific', auto_confirm=False)
        pac = res['pacific']
        self.assertTrue(pac['matches_completed'])
        self.assertFalse(pac['is_confirmed'])

        # Stage record should NOT be marked completed yet
        stage_rec = get_stage_record(campaign.id, 'kickoff')
        data = json.loads(stage_rec.stage_data)
        self.assertFalse(data['regional_results']['pacific']['is_confirmed'])
        self.assertNotEqual(stage_rec.status, 'completed')

        # 3. Score override works while in review state
        first_match = pac['matches'][0]
        match_id = first_match['id']
        t_a = first_match['team_a']
        t_b = first_match['team_b']
        self.assertIsNotNone(t_a)
        self.assertIsNotNone(t_b)

        # Override winner to team_b
        updated = override_kickoff_match(
            campaign_id=campaign.id,
            region_slug='pacific',
            match_id=match_id,
            winner_id=t_b['id'],
            maps=[{'map_number': 1, 'team_a_score': 8, 'team_b_score': 13, 'winner_id': t_b['id']}]
        )
        self.assertIsNotNone(updated)

        # 4. Confirm Pacific region
        c_res = confirm_stage_region(campaign.id, 'kickoff', 'pacific')
        self.assertTrue(c_res['is_confirmed'])

        stage_rec = get_stage_record(campaign.id, 'kickoff')
        data = json.loads(stage_rec.stage_data)
        self.assertTrue(data['regional_results']['pacific']['is_confirmed'])

        # 5. Score override MUST fail now that the region is confirmed & locked
        from services.campaign_service import resolve_ko_match
        with self.assertRaises(ValueError) as ctx:
            resolve_ko_match(
                campaign_id=campaign.id,
                region_slug='pacific',
                match_id=match_id,
                winner_id=t_a['id'],
                maps=[]
            )
        self.assertIn("khóa", str(ctx.exception).lower())

        # API endpoint also returns 400 error when locked
        api_resp = self.client.post(f'/api/campaign/{campaign.id}/kickoff/match/manual', json={
            'region_slug': 'pacific',
            'match_id': match_id,
            'winner_id': t_a['id']
        })
        self.assertEqual(api_resp.status_code, 400)
        self.assertIn("khóa", api_resp.get_json()['error'].lower())

        # 6. Sim remaining regions with auto_confirm=False and confirm_stage_all
        for r in ['americas', 'emea', 'china']:
            run_kickoff_stage(campaign.id, region_slug=r, auto_confirm=False)

        all_res = confirm_stage_all(campaign.id, 'kickoff')
        self.assertTrue(all_res['is_confirmed'])

        db.session.refresh(campaign)
        self.assertEqual(campaign.current_stage, 'major')

    def test_international_confirmation_and_locking(self):
        # 1. Create Campaign and advance to Major
        campaign = create_campaign(name="Major Confirmation Test", start_year=2028)
        run_open_qualifier_stage(campaign.id, auto_confirm=True)
        run_kickoff_stage(campaign.id, auto_confirm=True)
        db.session.refresh(campaign)
        self.assertEqual(campaign.current_stage, 'major')

        # 2. Simulate Major with auto_confirm=False
        m_res = run_major_stage(campaign.id, auto_confirm=False)
        self.assertTrue(m_res['matches_completed'])
        self.assertFalse(m_res['is_confirmed'])

        # 3. Can override match in review state
        first_m = m_res['matches'][0]
        m_id = first_m['id']
        t_a = first_m['team_a']
        t_b = first_m['team_b']
        override_res = override_major_match(
            campaign_id=campaign.id,
            match_id=m_id,
            winner_id=t_b['id'],
            maps=[{'map_number': 1, 'team_a_score': 7, 'team_b_score': 13, 'winner_id': t_b['id']}]
        )
        self.assertIsNotNone(override_res)

        # 4. Confirm tournament
        c_res = confirm_stage_tournament(campaign.id, 'major')
        self.assertTrue(c_res['is_confirmed'])

        # 5. Overriding score after lock MUST raise ValueError
        from services.campaign_service import resolve_major_match_interactive
        with self.assertRaises(ValueError) as ctx:
            resolve_major_match_interactive(
                campaign_id=campaign.id,
                match_id=m_id,
                winner_id=t_a['id'],
                maps=[]
            )
        self.assertIn("khóa", str(ctx.exception).lower())

        # API endpoint also returns 400 error when locked
        api_resp = self.client.post(f'/api/campaign/{campaign.id}/major/match/manual', json={
            'match_id': m_id,
            'winner_id': t_a['id']
        })
        self.assertEqual(api_resp.status_code, 400)
        self.assertIn("khóa", api_resp.get_json()['error'].lower())

        # 6. Campaign advanced to oq_stage1
        db.session.refresh(campaign)
        self.assertEqual(campaign.current_stage, 'oq_stage1')

    def test_api_confirmation_endpoint(self):
        campaign = create_campaign(name="API Confirmation Test", start_year=2028)
        run_open_qualifier_stage(campaign.id, auto_confirm=True)
        run_kickoff_stage(campaign.id, region_slug='pacific', auto_confirm=False)

        # Test POST /api/campaign/<id>/kickoff/confirm-region
        resp = self.client.post(f'/api/campaign/{campaign.id}/kickoff/confirm-region', json={
            'region_slug': 'pacific'
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data['success'])
        self.assertTrue(data['result']['is_confirmed'])

    def test_cannot_confirm_incomplete_region_and_all(self):
        campaign = create_campaign(name="Incomplete Lock Guard Test", start_year=2028)
        # Open Qualifier is newly initialized, 0 matches played
        # 1. Directly trying to confirm an incomplete region MUST raise ValueError
        with self.assertRaises(ValueError) as ctx:
            confirm_stage_region(campaign.id, 'open_qualifier', 'americas')
        self.assertIn('khóa', str(ctx.exception).lower())

        # 2. Directly trying to confirm-all when regions are not finished MUST raise ValueError
        with self.assertRaises(ValueError) as ctx:
            confirm_stage_all(campaign.id, 'open_qualifier')
        self.assertIn('khóa', str(ctx.exception).lower())

        # 3. API endpoint also returns 400
        resp = self.client.post(f'/api/campaign/{campaign.id}/open_qualifier/confirm-region', json={
            'region_slug': 'americas'
        })
        self.assertEqual(resp.status_code, 400)
        self.assertIn('khóa', resp.get_json()['error'].lower())

    def test_auto_healing_prematurely_locked_region(self):
        campaign = create_campaign(name="Auto Healing Test", start_year=2028)
        stage_rec = get_stage_record(campaign.id, 'open_qualifier')
        data = json.loads(stage_rec.stage_data)

        # Simulate corrupted / premature lock state like the reported bug
        data['regions']['americas']['is_confirmed'] = True
        data['regions']['americas']['matches_completed'] = True
        data['regions']['americas']['status'] = 'completed'
        stage_rec.stage_data = json.dumps(data)
        db.session.commit()

        # Reading through get_open_qualifier_data should auto-detect and heal
        from services.campaign_service import get_open_qualifier_data
        healed_data = get_open_qualifier_data(campaign.id)
        am_data = healed_data['regions']['americas']

        self.assertFalse(am_data.get('is_confirmed'))
        self.assertFalse(am_data.get('matches_completed'))
        self.assertEqual(am_data.get('status'), 'in_progress')

    def test_unlock_region_api(self):
        campaign = create_campaign(name="Unlock Test", start_year=2028)
        run_open_qualifier_stage(campaign.id, auto_confirm=True)
        run_kickoff_stage(campaign.id, region_slug='pacific', auto_confirm=False)

        # Confirm Pacific
        c_res = confirm_stage_region(campaign.id, 'kickoff', 'pacific')
        self.assertTrue(c_res['is_confirmed'])

        # Unlock Pacific via API
        resp = self.client.post(f'/api/campaign/{campaign.id}/kickoff/unlock-region', json={
            'region_slug': 'pacific'
        })
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json()['success'])
        self.assertFalse(resp.get_json()['result']['is_confirmed'])

        # Verify DB state is unlocked
        ko_data = get_kickoff_data(campaign.id)
        self.assertFalse(ko_data['regional_results']['pacific']['is_confirmed'])


if __name__ == '__main__':
    unittest.main()
