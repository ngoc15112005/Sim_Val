import json
import unittest
from app import create_app
from models import db, Tournament, Club, TournamentParticipant, Match, MatchMap
from services.export_import_service import (
    export_tournament_dict, export_all_tournaments_dict,
    import_payload, delete_tournament_cascade,
)


class TestExportImport(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.app_context = self.app.app_context()
        self.app_context.push()
        self.client = self.app.test_client()

    def tearDown(self):
        self.app_context.pop()

    def test_export_and_import(self):
        # 1. Grab or create a tournament to export
        tour = Tournament.query.first()
        self.assertIsNotNone(tour, "Should have at least one tournament in DB")

        tour_id = tour.id
        exported = export_tournament_dict(tour)

        self.assertEqual(exported['version'], '1.0')
        self.assertEqual(exported['type'], tour.type)
        self.assertEqual(exported['name'], tour.name)
        self.assertIn('participants', exported)
        self.assertIn('matches', exported)
        self.assertGreater(len(exported['participants']), 0)
        self.assertGreater(len(exported['matches']), 0)

        # 2. Modify name slightly to test importing as a duplicate/new record
        exported_copy = json.loads(json.dumps(exported))
        exported_copy['name'] = f"{tour.name} (Restored Copy)"

        imported_list = import_payload({'tournament': exported_copy})
        self.assertEqual(len(imported_list), 1)
        new_tour = imported_list[0]

        self.assertNotEqual(new_tour.id, tour_id)
        self.assertEqual(new_tour.name, f"{tour.name} (Restored Copy)")
        self.assertEqual(new_tour.type, tour.type)
        self.assertEqual(len(new_tour.participants), len(tour.participants))
        self.assertEqual(len(new_tour.matches), len(tour.matches))

        # Check participants match club short_codes
        orig_clubs = {p.club.short_code for p in tour.participants if p.club}
        new_clubs = {p.club.short_code for p in new_tour.participants if p.club}
        self.assertEqual(orig_clubs, new_clubs)

        # 3. Test API export
        resp = self.client.get(f'/api/tournament/{new_tour.id}/export')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.content_type, 'application/json')
        data = json.loads(resp.data)
        self.assertEqual(data['name'], f"{tour.name} (Restored Copy)")

        # 4. Test API delete
        del_resp = self.client.post(f'/api/tournament/{new_tour.id}/delete')
        self.assertEqual(del_resp.status_code, 200)
        self.assertIsNone(Tournament.query.get(new_tour.id))

    def test_export_all_api(self):
        resp = self.client.get('/api/tournaments/export')
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertIn('tournaments', data)
        self.assertGreaterEqual(data['count'], 1)

    def test_import_file_upload(self):
        tour = Tournament.query.first()
        exported = export_tournament_dict(tour)
        exported['name'] = 'Uploaded Tour'
        json_bytes = json.dumps({'tournament': exported}).encode('utf-8')

        import io
        data = {
            'file': (io.BytesIO(json_bytes), 'tour_upload.json')
        }
        resp = self.client.post('/api/tournaments/import', data=data, content_type='multipart/form-data')
        self.assertEqual(resp.status_code, 200)
        res_data = json.loads(resp.data)
        self.assertTrue(res_data['success'])
        self.assertEqual(res_data['count'], 1)
        created_id = res_data['tournaments'][0]['id']

        # Clean up
        delete_tournament_cascade(created_id)


if __name__ == '__main__':
    unittest.main()
