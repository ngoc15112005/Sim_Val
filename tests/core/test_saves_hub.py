import unittest
import json
import os
from app import create_app
from models import db, Campaign, Tournament
from services.campaign_service import create_campaign


class TestSavesHub(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.app_context = self.app.app_context()
        self.app_context.push()
        self.client = self.app.test_client()

    def tearDown(self):
        self.app_context.pop()

    def test_save_directories_exist(self):
        """Kiểm tra cấu trúc thư mục saves/ riêng biệt cho 2 chế độ."""
        self.assertTrue(os.path.isdir('saves'))
        self.assertTrue(os.path.isdir(os.path.join('saves', 'single')))
        self.assertTrue(os.path.isdir(os.path.join('saves', 'campaign')))

    def test_api_list_saves(self):
        """Kiểm tra API liệt kê file lưu trong thư mục saves."""
        res_c = self.client.get('/api/saves/campaign')
        self.assertEqual(res_c.status_code, 200)
        data_c = res_c.get_json()
        self.assertTrue(data_c['success'])
        self.assertEqual(data_c['mode'], 'campaign')

        res_s = self.client.get('/api/saves/single')
        self.assertEqual(res_s.status_code, 200)
        data_s = res_s.get_json()
        self.assertTrue(data_s['success'])
        self.assertEqual(data_s['mode'], 'single')

    def test_campaign_export_auto_saves_to_hub(self):
        """Kiểm tra export campaign tự động ghi file vào saves/campaign/."""
        camp = create_campaign('Hub Test Campaign', start_year=2027)
        res = self.client.get(f'/api/campaign/{camp.id}/export')
        self.assertEqual(res.status_code, 200)

        # File phải có trong saves/campaign/
        files = os.listdir(os.path.join('saves', 'campaign'))
        matching = [f for f in files if f.startswith('vct_save_Hub_Test_Campaign')]
        self.assertTrue(len(matching) > 0)

        # Dọn dẹp
        db.session.delete(camp)
        db.session.commit()
        for f in matching:
            try:
                os.remove(os.path.join('saves', 'campaign', f))
            except Exception:
                pass


if __name__ == '__main__':
    unittest.main()
