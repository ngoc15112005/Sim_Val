import unittest
import json
from app import create_app
from models import db, Campaign, CampaignClubState, CampaignStage


class TestCampaignRoutes(unittest.TestCase):

    def setUp(self):
        self.app = create_app()
        self.client = self.app.test_client()
        self.app_context = self.app.app_context()
        self.app_context.push()

    def tearDown(self):
        db.session.remove()
        self.app_context.pop()

    def test_campaign_lifecycle_routes(self):
        # 1. Access campaigns list page
        r = self.client.get('/campaigns')
        self.assertEqual(r.status_code, 200)
        self.assertIn('Chế độ Cốt truyện'.encode('utf-8'), r.data)

        # 2. Create campaign via POST
        r = self.client.post('/campaigns/create', data={
            'name': 'VCT Route Test 2027',
            'year': '2027'
        }, follow_redirects=True)
        self.assertEqual(r.status_code, 200)
        self.assertIn('VCT Route Test 2027'.encode('utf-8'), r.data)

        campaign = Campaign.query.filter_by(name='VCT Route Test 2027').first()
        self.assertIsNotNone(campaign)

        # 3. Access campaign detail page
        r = self.client.get(f'/campaign/{campaign.id}')
        self.assertEqual(r.status_code, 200)
        self.assertIn('Open Qualifier'.encode('utf-8'), r.data)

        # 4. Access Open Qualifier stage page
        r = self.client.get(f'/campaign/{campaign.id}/stage/open_qualifier?region=pacific')
        self.assertEqual(r.status_code, 200)
        self.assertIn('Open Qualifier (16 Non-Partner / Khu vực)'.encode('utf-8'), r.data)

        # 5. Update form modifier via API
        state = CampaignClubState.query.filter_by(campaign_id=campaign.id).first()
        r = self.client.post(f'/api/campaign/{campaign.id}/form/update', json={
            'club_id': state.club_id,
            'form_modifier': 4
        })
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.data)
        self.assertTrue(data['success'])

        # 6. Simulate Pacific Open Qualifier via API
        r = self.client.post(f'/api/campaign/{campaign.id}/open_qualifier/sim', json={
            'region_slug': 'pacific'
        })
        self.assertEqual(r.status_code, 200)
        res_data = json.loads(r.data)
        self.assertTrue(res_data['success'])
        self.assertIn('pacific', res_data['results'])
        self.assertEqual(res_data['results']['pacific']['total_matches'], 43)

        # 7. Render Pacific Open Qualifier with completed matches
        r = self.client.get(f'/campaign/{campaign.id}/stage/open_qualifier?region=pacific')
        self.assertEqual(r.status_code, 200)
        self.assertIn('4 ĐỘI TUYỂN GIÀNH VÉ THAM DỰ VCT KICKOFF'.encode('utf-8'), r.data)

        # 8. Delete campaign
        r = self.client.post(f'/campaign/{campaign.id}/delete', follow_redirects=True)
        self.assertEqual(r.status_code, 200)
        deleted = Campaign.query.filter_by(id=campaign.id).first()
        self.assertIsNone(deleted)


if __name__ == '__main__':
    unittest.main()
