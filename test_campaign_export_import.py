"""
Unit tests for Campaign Save Game Export & Import (JSON) functionality.
Tests the service methods (export_campaign_save, import_campaign_save)
and the API endpoints (/api/campaign/<id>/export, /api/campaign/import).
"""

import io
import json
import unittest
from app import create_app
from models import db, Campaign, CampaignClubState, CampaignStage, Club
from services.campaign_service import create_campaign, run_open_qualifier_stage
from services.campaign_export_service import export_campaign_save, import_campaign_save


class TestCampaignExportImport(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.app_context = self.app.app_context()
        self.app_context.push()
        self.client = self.app.test_client()
        self.cleanup_campaign_ids = []

    def tearDown(self):
        for cid in self.cleanup_campaign_ids:
            camp = Campaign.query.get(cid)
            if camp:
                db.session.delete(camp)
        db.session.commit()
        self.app_context.pop()

    def test_export_and_import_service(self):
        # 1. Create a campaign and simulate Open Qualifier
        camp = create_campaign(name="Test Export VCT 2027", start_year=2027)
        self.cleanup_campaign_ids.append(camp.id)

        # Sim OQ to produce stage data & points
        run_open_qualifier_stage(camp.id)

        # 2. Export campaign
        data = export_campaign_save(camp.id)
        self.assertEqual(data.get('format_version'), '1.0')
        self.assertEqual(data.get('export_type'), 'vct_campaign_save')
        self.assertIn('campaign', data)
        self.assertEqual(data['campaign']['name'], "Test Export VCT 2027")
        self.assertEqual(data['campaign']['current_year'], 2027)
        self.assertGreaterEqual(len(data['club_states']), 44)
        self.assertGreaterEqual(len(data['stages']), 1)

        # Verify club states contain short_code
        first_cs = data['club_states'][0]
        self.assertIn('short_code', first_cs)
        self.assertIn('championship_points', first_cs)
        self.assertIn('team_elo', first_cs)

        # 3. Import back into database with a new custom name
        restored_camp = import_campaign_save(data, custom_name="Restored Test VCT 2027")
        self.cleanup_campaign_ids.append(restored_camp.id)

        self.assertNotEqual(restored_camp.id, camp.id)
        self.assertEqual(restored_camp.name, "Restored Test VCT 2027")
        self.assertEqual(restored_camp.current_year, 2027)
        self.assertEqual(restored_camp.current_stage, camp.current_stage)

        # Verify club states count and points match
        orig_states = {cs.club.short_code: cs.championship_points for cs in camp.club_states if cs.club}
        restored_states = {cs.club.short_code: cs.championship_points for cs in restored_camp.club_states if cs.club}
        self.assertEqual(len(orig_states), len(restored_states))
        for code, pts in orig_states.items():
            self.assertEqual(restored_states.get(code), pts)

        # Verify stages
        self.assertEqual(len(camp.stages), len(restored_camp.stages))

    def test_api_export_endpoint(self):
        camp = create_campaign(name="API Export Campaign", start_year=2027)
        self.cleanup_campaign_ids.append(camp.id)

        resp = self.client.get(f'/api/campaign/{camp.id}/export')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('application/json', resp.content_type)
        self.assertIn('attachment; filename=', resp.headers.get('Content-Disposition', ''))

        payload = json.loads(resp.data.decode('utf-8'))
        self.assertEqual(payload.get('export_type'), 'vct_campaign_save')
        self.assertEqual(payload['campaign']['name'], "API Export Campaign")

    def test_api_import_endpoint_multipart_file(self):
        camp = create_campaign(name="Original API Save", start_year=2027)
        self.cleanup_campaign_ids.append(camp.id)

        exported_dict = export_campaign_save(camp.id)
        json_bytes = json.dumps(exported_dict, ensure_ascii=False).encode('utf-8')

        # Upload as multipart file
        file_storage = (io.BytesIO(json_bytes), 'vct_save_test.json')
        resp = self.client.post(
            '/api/campaign/import',
            data={'file': file_storage, 'custom_name': 'Uploaded From Web'},
            content_type='multipart/form-data'
        )

        self.assertEqual(resp.status_code, 200)
        res_data = json.loads(resp.data.decode('utf-8'))
        self.assertTrue(res_data.get('success'))
        imported_id = res_data.get('campaign_id')
        self.assertIsNotNone(imported_id)
        self.cleanup_campaign_ids.append(imported_id)
        self.assertEqual(res_data.get('redirect_url'), f'/campaign/{imported_id}')

        imported_camp = Campaign.query.get(imported_id)
        self.assertIsNotNone(imported_camp)
        self.assertEqual(imported_camp.name, 'Uploaded From Web')

    def test_api_import_endpoint_json_body(self):
        camp = create_campaign(name="Direct JSON Campaign", start_year=2027)
        self.cleanup_campaign_ids.append(camp.id)

        exported_dict = export_campaign_save(camp.id)
        exported_dict['custom_name'] = 'Restored Via JSON API'

        resp = self.client.post(
            '/api/campaign/import',
            data=json.dumps(exported_dict),
            content_type='application/json'
        )

        self.assertEqual(resp.status_code, 200)
        res_data = json.loads(resp.data.decode('utf-8'))
        self.assertTrue(res_data.get('success'))
        imported_id = res_data.get('campaign_id')
        self.assertIsNotNone(imported_id)
        self.cleanup_campaign_ids.append(imported_id)

        imported_camp = Campaign.query.get(imported_id)
        self.assertEqual(imported_camp.name, 'Restored Via JSON API')

    def test_import_invalid_payload_error_handling(self):
        # 1. Invalid payload format
        resp = self.client.post(
            '/api/campaign/import',
            data=json.dumps({'invalid_key': 'no_save'}),
            content_type='application/json'
        )
        self.assertEqual(resp.status_code, 400)
        res_data = json.loads(resp.data.decode('utf-8'))
        self.assertIn('error', res_data)

        # 2. Empty request
        resp2 = self.client.post(
            '/api/campaign/import',
            data='',
            content_type='application/json'
        )
        self.assertEqual(resp2.status_code, 400)


if __name__ == '__main__':
    unittest.main()
