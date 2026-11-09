import copy
import unittest
from app import create_app
from models import db, Campaign, CampaignClubState, CampaignPartnershipReview, Club
from services.campaign_service import create_campaign
from engine.partnership import (
    DEFAULT_PARTNERSHIP_CONFIG,
    CLUB_COUNTRY_MAP,
    SUBREGION_METADATA,
    get_club_country_info,
    validate_partnership_config,
    normalize_higher_is_better,
    normalize_lower_is_better,
    score_qualitative_rubric,
    evaluate_club_partnership,
    evaluate_region_partnership,
    validate_manual_partner_selection,
)
from services.partnership_service import (
    get_partnership_cycle_status,
    generate_partnership_evaluation,
    commit_partnership_selection,
)


class TestPartnershipEvaluationSystem(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.app_context = self.app.app_context()
        self.app_context.push()
        self.client = self.app.test_client()

        self.campaign = create_campaign('Test Partnership Evaluation', start_year=2027)

    def tearDown(self):
        try:
            camp = db.session.get(Campaign, self.campaign.id)
            if camp:
                db.session.delete(camp)
                db.session.commit()
        except Exception:
            db.session.rollback()
        db.session.remove()
        self.app_context.pop()

    def test_validate_partnership_config(self):
        """Kiểm tra bộ quy tắc cấu hình 100 điểm (5 trụ cột, 19 chỉ số A1..E3)."""
        ok, errors = validate_partnership_config(DEFAULT_PARTNERSHIP_CONFIG)
        self.assertTrue(ok, f"Default config should be valid, got: {errors}")
        self.assertEqual(len(errors), 0)

        # Thử sửa tổng trọng số khác 100
        bad_cfg = copy.deepcopy(DEFAULT_PARTNERSHIP_CONFIG)
        bad_cfg['criteria']['community_growth']['weight'] = 30.0
        ok2, errors2 = validate_partnership_config(bad_cfg)
        self.assertFalse(ok2)
        self.assertTrue(any('100.0' in e for e in errors2))

        # Thử sửa sàn điểm vượt quá trọng số
        bad_floor_cfg = copy.deepcopy(DEFAULT_PARTNERSHIP_CONFIG)
        bad_floor_cfg['criteria']['competitive_success']['minimum_score'] = 20.0
        ok3, errors3 = validate_partnership_config(bad_floor_cfg)
        self.assertFalse(ok3)

    def test_normalization_and_rubric_formulas(self):
        """Kiểm tra công thức chuẩn hóa điểm định lượng & định tính (Rubric 0-5)."""
        # Higher is better (floor=10, target=50)
        self.assertAlmostEqual(normalize_higher_is_better(10, 10, 50), 0.0)
        self.assertAlmostEqual(normalize_higher_is_better(5, 10, 50), 0.0)
        self.assertAlmostEqual(normalize_higher_is_better(50, 10, 50), 1.0)
        self.assertAlmostEqual(normalize_higher_is_better(70, 10, 50), 1.0)
        self.assertAlmostEqual(normalize_higher_is_better(30, 10, 50), 0.5)

        # Lower is better (floor=0.35, target=0.05)
        self.assertAlmostEqual(normalize_lower_is_better(0.05, 0.35, 0.05), 1.0)
        self.assertAlmostEqual(normalize_lower_is_better(0.01, 0.35, 0.05), 1.0)
        self.assertAlmostEqual(normalize_lower_is_better(0.35, 0.35, 0.05), 0.0)
        self.assertAlmostEqual(normalize_lower_is_better(0.50, 0.35, 0.05), 0.0)
        self.assertAlmostEqual(normalize_lower_is_better(0.20, 0.35, 0.05), 0.5)

        # Rubric 0-5
        self.assertAlmostEqual(score_qualitative_rubric(0, 6.0), 0.0)
        self.assertAlmostEqual(score_qualitative_rubric(5, 6.0), 6.0)
        self.assertAlmostEqual(score_qualitative_rubric(2.5, 6.0), 3.0)

    def test_all_96_clubs_country_mapping_and_default_partners(self):
        """Kiểm tra toàn bộ 96 CLB đều có mã quốc gia/tiểu khu vực hợp lệ và mặc định <= 2 đội/nước."""
        clubs = Club.query.all()
        self.assertEqual(len(clubs), 96)

        for c in clubs:
            self.assertIn(c.short_code, CLUB_COUNTRY_MAP, f"Missing {c.short_code} in CLUB_COUNTRY_MAP")
            c_info = get_club_country_info(c.short_code, c.region.slug)
            cc = c_info['country_code']
            self.assertIn(cc, SUBREGION_METADATA, f"Missing {cc} in SUBREGION_METADATA")
            d = c.to_dict()
            self.assertEqual(d['country_code'], cc)
            self.assertTrue(len(d['country_flag']) > 0)

        # Kiểm tra 8 đội Partner mặc định mỗi khu vực đều thỏa mãn <= 2 đội/quốc gia
        for r_slug in ['pacific', 'americas', 'emea', 'china']:
            region_states = (
                CampaignClubState.query
                .join(Club)
                .filter(CampaignClubState.campaign_id == self.campaign.id, Club.region.has(slug=r_slug))
                .all()
            )
            region_clubs = [cs.club.to_dict() for cs in region_states]
            partner_ids = [cs.club_id for cs in region_states if cs.is_partner]
            is_valid, err_msg, violations = validate_manual_partner_selection(r_slug, partner_ids, region_clubs)
            self.assertTrue(is_valid, f"Default partners in {r_slug} failed validation: {err_msg} ({violations})")

    def test_ai_recommendation_enforces_country_cap_max_2(self):
        """Kiểm tra AI đề xuất tự động luôn chặn ở mức tối đa 2 đội mỗi Quốc gia/Tiểu khu vực."""
        # Giả lập khu vực Pacific có 4 đội Hàn Quốc (T1, GEN, DRX, NS) đều có sức mạnh 99 và vô địch quốc tế
        pacific_states = (
            CampaignClubState.query
            .join(Club)
            .filter(CampaignClubState.campaign_id == self.campaign.id, Club.region.has(slug='pacific'))
            .all()
        )
        evaluated_clubs = []
        for cs in pacific_states:
            code = cs.club.short_code
            is_kr_powerhouse = code in ('T1', 'GEN', 'DRX', 'NS')
            c_dict = cs.club.to_dict()
            cs_dict = {
                'club_id': cs.club_id,
                'story_rating': 99 if is_kr_powerhouse else 74,
                'power_score': 1850.0 if is_kr_powerhouse else 1480.0,
                'is_partner': cs.is_partner,
            }
            placements = [
                {'stage_key': 'champion', 'rank': 1, 'year': 2028, 'matches_won': 7, 'matches_lost': 0, 'stage_points_earned': 20},
                {'stage_key': 'master', 'rank': 1, 'year': 2027, 'matches_won': 6, 'matches_lost': 0, 'stage_points_earned': 15},
            ] if is_kr_powerhouse else []

            ev = evaluate_club_partnership(
                club_dict=c_dict,
                club_state_dict=cs_dict,
                placements_24m=placements,
                storylines_24m=[],
                evaluation_year=2028,
            )
            evaluated_clubs.append(ev)

        region_eval = evaluate_region_partnership(
            region_slug='pacific',
            evaluated_clubs=evaluated_clubs,
        )

        rec_ids = set(region_eval['recommended_club_ids'])
        self.assertEqual(len(rec_ids), 8)

        # Đếm số đội KR được đề xuất: bắt buộc == 2, và ít nhất 2 đội KR khác bị gắn cờ cap_blocked
        kr_recommended = [t for t in region_eval['clubs'] if t['country_code'] == 'KR' and t['ai_recommended']]
        kr_blocked = [t for t in region_eval['clubs'] if t['country_code'] == 'KR' and t['recommendation_status'] == 'cap_blocked']

        self.assertEqual(len(kr_recommended), 2, "Chỉ tối đa 2 đội Hàn Quốc được phép vào danh sách Partner!")
        self.assertGreaterEqual(len(kr_blocked), 2, "Các đội Hàn Quốc thứ 3, 4 dù điểm cao vẫn phải bị chặn bởi Country Cap!")

        # Mọi tiểu khu vực trong đề xuất của AI đều không vượt quá 2
        for sub in region_eval['subregions']:
            self.assertLessEqual(sub['selected_count'], 2, f"Subregion {sub['code']} exceeded cap of 2!")

    def test_manual_selection_validation_blocks_over_2_and_allows_valid_swap(self):
        """Kiểm tra hàm chốt danh sách Partner chặn cứng nếu người chơi chọn > 2 đội cùng nước hoặc != 8 đội."""
        eval_data = generate_partnership_evaluation(self.campaign.id, year=2028, force_recalculate=True)
        self.assertIn('regions', eval_data)

        # Lấy danh sách đề xuất của cả 4 khu vực
        valid_selections = {}
        for r_slug in ['pacific', 'americas', 'emea', 'china']:
            valid_selections[r_slug] = list(eval_data['regions'][r_slug]['recommended_club_ids'])

        # 1. Thử chọn 3 đội Hàn Quốc ở Pacific (thay 1 đội không phải KR bằng 1 đội KR chưa được chọn)
        pac_teams = eval_data['regions']['pacific']['clubs']
        pac_sel_set = set(valid_selections['pacific'])
        unselected_kr = next(t for t in pac_teams if t['country_code'] == 'KR' and t['club_id'] not in pac_sel_set)
        selected_non_kr = next(t for t in pac_teams if t['country_code'] != 'KR' and t['club_id'] in pac_sel_set)

        invalid_kr_selections = copy.deepcopy(valid_selections)
        pac_list = [cid for cid in invalid_kr_selections['pacific'] if cid != selected_non_kr['club_id']]
        pac_list.append(unselected_kr['club_id'])
        invalid_kr_selections['pacific'] = pac_list

        with self.assertRaises(ValueError) as ctx_kr:
            commit_partnership_selection(self.campaign.id, invalid_kr_selections, year=2028)
        self.assertIn('Hàn Quốc', str(ctx_kr.exception))

        # 2. Thử chọn 3 đội Thượng Hải (CN_SH) ở China (EDG, BLG, FPX)
        cn_teams = eval_data['regions']['china']['clubs']
        sh_teams = [t for t in cn_teams if t['country_code'] == 'CN_SH'][:3]
        other_cn_teams = [t for t in cn_teams if t['country_code'] != 'CN_SH']
        # Chọn 3 đội CN_SH + 5 đội từ các tiểu khu vực khác (mỗi nơi <= 2)
        picked_others = []
        sub_c = {}
        for t in other_cn_teams:
            cc = t['country_code']
            if sub_c.get(cc, 0) < 2 and len(picked_others) < 5:
                picked_others.append(t['club_id'])
                sub_c[cc] = sub_c.get(cc, 0) + 1

        invalid_cn_selections = copy.deepcopy(valid_selections)
        invalid_cn_selections['china'] = [t['club_id'] for t in sh_teams] + picked_others

        with self.assertRaises(ValueError) as ctx_cn:
            commit_partnership_selection(self.campaign.id, invalid_cn_selections, year=2028)
        self.assertIn('Thượng Hải', str(ctx_cn.exception))

        # 3. Thử chọn thiếu đội (7/8 đội ở EMEA)
        invalid_count_selections = copy.deepcopy(valid_selections)
        invalid_count_selections['emea'] = invalid_count_selections['emea'][:7]
        with self.assertRaises(ValueError) as ctx_cnt:
            commit_partnership_selection(self.campaign.id, invalid_count_selections, year=2028)
        self.assertIn('7/8', str(ctx_cnt.exception))

        # 4. Chọn hợp lệ: Hoán đổi 1 đội Hàn Quốc chưa được chọn thay cho 1 đội Hàn Quốc đang được chọn -> Vẫn giữ đúng 2 đội KR
        selected_kr = next(t for t in pac_teams if t['country_code'] == 'KR' and t['club_id'] in pac_sel_set)
        valid_swap_selections = copy.deepcopy(valid_selections)
        pac_swap_list = [cid for cid in valid_swap_selections['pacific'] if cid != selected_kr['club_id']]
        pac_swap_list.append(unselected_kr['club_id'])
        valid_swap_selections['pacific'] = pac_swap_list

        res_ok = commit_partnership_selection(self.campaign.id, valid_swap_selections, year=2028)
        self.assertTrue(res_ok['success'])
        self.assertEqual(res_ok['retained_count'] + res_ok['promoted_count'], 32)

        # Kiểm tra DB đã cập nhật trạng thái Partner
        promoted_state = CampaignClubState.query.filter_by(campaign_id=self.campaign.id, club_id=unselected_kr['club_id']).first()
        demoted_state = CampaignClubState.query.filter_by(campaign_id=self.campaign.id, club_id=selected_kr['club_id']).first()
        self.assertTrue(promoted_state.is_partner)
        self.assertFalse(demoted_state.is_partner)

    def test_2_year_cycle_detection_and_api_routes(self):
        """Kiểm tra chu kỳ 2 năm (2027 = Năm 1/2, 2028 = Năm 2/2 cần đánh giá lại) và các API endpoints."""
        # Năm 2027 (Năm 1 của chu kỳ): chưa bắt buộc tái xét duyệt cuối năm
        status_2027 = get_partnership_cycle_status(self.campaign.id, year=2027)
        self.assertEqual(status_2027['seasons_elapsed'], 1)
        self.assertFalse(status_2027['is_review_cycle'])
        self.assertFalse(status_2027['is_due'])

        # Năm 2028 (Năm 2 của chu kỳ): bắt buộc tái xét duyệt cuối năm
        status_2028 = get_partnership_cycle_status(self.campaign.id, year=2028)
        self.assertEqual(status_2028['seasons_elapsed'], 2)
        self.assertTrue(status_2028['is_review_cycle'])
        self.assertTrue(status_2028['is_due'])

        # Test GET /api/campaign/<id>/partnership/review
        resp = self.client.get(f'/api/campaign/{self.campaign.id}/partnership/review?year=2028')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data['success'])
        self.assertIn('review', data)
        self.assertEqual(len(data['review']['regions']), 4)

        # Test POST /api/campaign/<id>/partnership/commit với dữ liệu không hợp lệ (3 đội KR) -> 400
        ai_selections = {
            r: list(data['review']['regions'][r]['recommended_club_ids'])
            for r in ['pacific', 'americas', 'emea', 'china']
        }
        pac_teams = data['review']['regions']['pacific']['clubs']
        pac_set = set(ai_selections['pacific'])
        extra_kr = next(t['club_id'] for t in pac_teams if t['country_code'] == 'KR' and t['club_id'] not in pac_set)
        non_kr = next(t['club_id'] for t in pac_teams if t['country_code'] != 'KR' and t['club_id'] in pac_set)
        bad_selections = copy.deepcopy(ai_selections)
        bad_selections['pacific'] = [cid for cid in bad_selections['pacific'] if cid != non_kr] + [extra_kr]

        bad_resp = self.client.post(
            f'/api/campaign/{self.campaign.id}/partnership/commit',
            json={'year': 2028, 'selections': bad_selections},
        )
        self.assertEqual(bad_resp.status_code, 400)
        self.assertIn('Hàn Quốc', bad_resp.get_json().get('error', ''))

        # Test POST /api/campaign/<id>/partnership/commit với dữ liệu đề xuất hợp lệ của AI -> 200
        commit_resp = self.client.post(
            f'/api/campaign/{self.campaign.id}/partnership/commit',
            json={'year': 2028, 'selections': ai_selections},
        )
        self.assertEqual(commit_resp.status_code, 200)
        commit_data = commit_resp.get_json()
        self.assertTrue(commit_data['success'])

        # Sau khi đã commit, is_due cho năm 2028 phải chuyển thành False
        status_after = get_partnership_cycle_status(self.campaign.id, year=2028)
        self.assertTrue(status_after['is_committed'])
        self.assertFalse(status_after['is_due'])


if __name__ == '__main__':
    unittest.main()
