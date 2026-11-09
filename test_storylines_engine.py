import unittest
import json
from app import create_app
from models import db, Campaign, CampaignClubState, CampaignStoryline, Club
from services.campaign_service import create_campaign, advance_campaign_to_next_year
from services.storyline_engine import (
    SCENARIO_CATALOG,
    get_scenario_catalog,
    generate_season_storylines_draft,
    commit_season_storylines,
    get_active_campaign_storylines,
    delete_campaign_storyline,
)


class TestStorylineEngine(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.app_context = self.app.app_context()
        self.app_context.push()
        self.client = self.app.test_client()

        # Tạo campaign test
        self.campaign = create_campaign('Test Storylines Circuit', start_year=2027)

    def tearDown(self):
        # Dọn dẹp campaign test
        try:
            camp = Campaign.query.get(self.campaign.id)
            if camp:
                db.session.delete(camp)
                db.session.commit()
        except Exception:
            db.session.rollback()
        self.app_context.pop()

    def test_scenario_catalog(self):
        """Kiểm tra danh mục 14 kịch bản đầy đủ thông tin chuẩn."""
        catalog = get_scenario_catalog()
        self.assertEqual(len(catalog), 14)
        for key, sc in catalog.items():
            self.assertEqual(sc['key'], key)
            self.assertIn(sc['target_type'], ['rating', 'form'])
            self.assertTrue(len(sc['headlines']) > 0)
            self.assertTrue(len(sc['badge']) > 0)
            self.assertTrue(isinstance(sc['default_impact'], int))

    def test_draft_generation(self):
        """Kiểm tra máy tự sinh dự thảo kịch bản mùa mới."""
        draft = generate_season_storylines_draft(self.campaign.id, target_year=2027)
        self.assertTrue(3 <= len(draft) <= 6)

        seen_clubs = set()
        has_rating = False
        has_form = False

        for item in draft:
            self.assertIn(item['scenario_key'], SCENARIO_CATALOG)
            self.assertIsNotNone(item['club_id'])
            self.assertTrue(len(item['headline']) > 0)
            self.assertTrue(len(item['badge']) > 0)
            self.assertIn(item['target_type'], ['rating', 'form'])
            if item['target_type'] == 'rating':
                has_rating = True
            elif item['target_type'] == 'form':
                has_form = True

            # Mỗi CLB chỉ dính 1 kịch bản cá nhân
            self.assertNotIn(item['club_id'], seen_clubs)
            seen_clubs.add(item['club_id'])

        # Phải có cả biến động rating và biến động form
        self.assertTrue(has_rating)
        self.assertTrue(has_form)

    def test_commit_storylines(self):
        """Kiểm tra lưu kịch bản vào DB và cập nhật rating / form của CLB."""
        cstate = CampaignClubState.query.filter_by(campaign_id=self.campaign.id).first()
        cid = cstate.club_id
        old_rating = cstate.story_rating
        old_form = cstate.form_modifier

        payload = [
            {
                'scenario_key': 'SC_SUPER_TEAM',
                'title': 'Super Team Triệu Đô',
                'badge': '💰 Super Team',
                'badge_color': 'purple',
                'target_type': 'rating',
                'impact_value': 6,
                'club_id': cid,
                'headline': 'NRG xây dựng Super Team triệu đô!',
                'description': 'Mô tả chi tiết',
            }
        ]

        res = commit_season_storylines(self.campaign.id, payload, year=2027)
        self.assertTrue(res['success'])
        self.assertEqual(res['total_storylines'], 1)

        # Kiểm tra CampaignClubState đã được cập nhật
        updated_cs = CampaignClubState.query.filter_by(campaign_id=self.campaign.id, club_id=cid).first()
        self.assertEqual(updated_cs.story_rating, min(99, old_rating + 6))

        # Kiểm tra bản ghi CampaignStoryline được lưu
        active = get_active_campaign_storylines(self.campaign.id, year=2027)
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]['club_id'], cid)
        self.assertEqual(active[0]['scenario_key'], 'SC_SUPER_TEAM')

    def test_storylines_api_endpoints(self):
        """Kiểm tra các API endpoint của Hệ thống Kịch bản."""
        # 1. Catalog
        res = self.client.get(f'/api/campaign/{self.campaign.id}/storylines/catalog')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(len(data['catalog']), 14)

        # 2. Clubs list
        res = self.client.get(f'/api/campaign/{self.campaign.id}/clubs')
        self.assertEqual(res.status_code, 200)
        cdata = res.get_json()
        self.assertTrue(cdata['success'])
        self.assertEqual(len(cdata['clubs']), 96)

        # 3. Draft
        res = self.client.get(f'/api/campaign/{self.campaign.id}/storylines/draft?year=2027')
        self.assertEqual(res.status_code, 200)
        ddata = res.get_json()
        self.assertTrue(ddata['success'])
        self.assertTrue(len(ddata['draft']) >= 3)

        # 4. Commit via API
        commit_payload = {
            'year': 2027,
            'storylines': ddata['draft'][:2]
        }
        res = self.client.post(
            f'/api/campaign/{self.campaign.id}/storylines/commit',
            data=json.dumps(commit_payload),
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 200)
        c_res = res.get_json()
        self.assertTrue(c_res['success'])
        self.assertEqual(c_res['total_storylines'], 2)

        # 5. Get active storylines
        res = self.client.get(f'/api/campaign/{self.campaign.id}/storylines?year=2027')
        self.assertEqual(res.status_code, 200)
        sdata = res.get_json()
        self.assertTrue(sdata['success'])
        self.assertEqual(len(sdata['storylines']), 2)

        # 6. Delete a storyline
        st_id = sdata['storylines'][0]['id']
        res = self.client.delete(f'/api/campaign/{self.campaign.id}/storylines/{st_id}')
        self.assertEqual(res.status_code, 200)
        del_data = res.get_json()
        self.assertTrue(del_data['success'])

        # Verify remaining is 1
        res = self.client.get(f'/api/campaign/{self.campaign.id}/storylines?year=2027')
        self.assertEqual(len(res.get_json()['storylines']), 1)


if __name__ == '__main__':
    unittest.main()
