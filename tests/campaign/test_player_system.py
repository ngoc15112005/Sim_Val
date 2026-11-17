"""
Comprehensive tests for Player System v2.0 (Đại Cập Nhật Tuyển Thủ):
- Legacy v1.x save blocking (DB + JSON import/export)
- 96-club seeding & lineup validity (5 starters, 4 core roles, <=2 cross-region imports, <= salary_cap)
- Strength formula: roster_base_rating = story_rating + player_bonus (0..+5, never negative)
- Role coverage & Flex wildcard + Salary Cap & Import Limit validation
- Domestic Identity preference on AI signings (KR/VN/BR/CN)
- Retirement & Comeback probability curves (35+ = 1e-13 = 0.00000000001%)
- Custom Player creation & Pre-Season Approval Draft / Commit / Year Rollover
"""

import json
import random
import unittest
from app import create_app
from models import db, Campaign, CampaignClubState, CampaignPlayer, Club
from engine.player_engine import (
    clamp_bonus,
    calculate_player_salary,
    check_4_roles_covered,
    validate_roster_lineup,
    get_club_import_openness,
    get_retirement_probability,
    get_comeback_probability,
    pick_ai_replacement_player,
)
from services.campaign_service import create_campaign, advance_campaign_to_next_year
from services.campaign_export_service import export_campaign_save
from services.player_service import (
    get_campaign_clubs_roster_summary,
    get_club_roster_details,
    update_club_roster_bulk,
    create_custom_player,
    generate_preseason_personnel_draft,
    commit_preseason_personnel_decisions,
)


class TestPlayerSystemV2(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.app_context = self.app.app_context()
        self.app_context.push()
        self.client = self.app.test_client()
        self.cleanup_campaign_ids = []

    def tearDown(self):
        for cid in self.cleanup_campaign_ids:
            camp = db.session.get(Campaign, cid)
            if camp:
                db.session.delete(camp)
        db.session.commit()
        self.app_context.pop()

    def test_v1_campaign_blocking_and_delete(self):
        camp = create_campaign(name="Test Legacy Guard v1", start_year=2027)
        self.cleanup_campaign_ids.append(camp.id)
        camp.schema_version = 1
        db.session.commit()

        self.assertFalse(camp.is_compatible)

        # Page view blocked with 409 incompatible_v1 page
        resp = self.client.get(f'/campaign/{camp.id}')
        self.assertEqual(resp.status_code, 409)
        html = resp.data.decode('utf-8')
        self.assertIn('v1.x', html)

        # API route blocked with 400 JSON
        api_resp = self.client.get(f'/api/campaign/{camp.id}/players')
        self.assertEqual(api_resp.status_code, 400)
        api_data = json.loads(api_resp.data.decode('utf-8'))
        self.assertTrue(api_data.get('incompatible_v1'))

        # Export blocked
        with self.assertRaises(ValueError):
            export_campaign_save(camp.id)

        # Delete still allowed
        del_resp = self.client.post(f'/campaign/{camp.id}/delete')
        self.assertIn(del_resp.status_code, (302, 200))
        self.assertIsNone(db.session.get(Campaign, camp.id))
        self.cleanup_campaign_ids.remove(camp.id)

    def test_campaign_v2_seeds_96_valid_rosters(self):
        camp = create_campaign(name="Test Seeding v2.0", start_year=2027)
        self.cleanup_campaign_ids.append(camp.id)

        self.assertEqual(camp.schema_version, 2)
        self.assertTrue(camp.is_compatible)

        total_players = CampaignPlayer.query.filter_by(campaign_id=camp.id).count()
        self.assertGreaterEqual(total_players, 500)

        summaries = get_campaign_clubs_roster_summary(camp.id)
        club_states = CampaignClubState.query.filter_by(campaign_id=camp.id).all()
        self.assertEqual(len(club_states), 96)

        for cs in club_states:
            s = summaries.get(cs.club_id)
            self.assertIsNotNone(s, f"Missing roster summary for club_id={cs.club_id}")
            self.assertEqual(s['starter_count'], 5, f"{cs.club.short_code} does not have 5 starters")
            self.assertTrue(s['roles_ok'], f"{cs.club.short_code} missing roles: {s['missing_roles']}")
            self.assertLessEqual(s['payroll'], cs.salary_cap, f"{cs.club.short_code} over cap")
            self.assertGreaterEqual(cs.player_bonus, 0)

    def test_prx_strength_formula_and_bonus_clamp(self):
        self.assertEqual(clamp_bonus(-4), 0)
        self.assertEqual(clamp_bonus(0), 0)
        self.assertEqual(clamp_bonus(5), 5)
        self.assertEqual(clamp_bonus(9), 5)

        camp = create_campaign(name="Test Strength PRX", start_year=2027)
        self.cleanup_campaign_ids.append(camp.id)

        prx_club = Club.query.filter_by(short_code='PRX').first()
        self.assertIsNotNone(prx_club)
        cs = CampaignClubState.query.filter_by(campaign_id=camp.id, club_id=prx_club.id).first()
        cs.story_rating = 90
        cs.form_modifier = 0
        cs.salary_cap = 1500
        db.session.commit()

        # Clear PRX current starters to FA cleanly and create exact 5 players: 3x(+2), 2x(+0) covering 4 roles
        for old_p in CampaignPlayer.query.filter_by(campaign_id=camp.id, club_id=prx_club.id).all():
            old_p.club_id = None
            old_p.status = 'free_agent'
            old_p.roster_slot = 'free_agent'
        db.session.commit()

        spec = [
            ('PRX_Test_1', 'Duelist', 2),
            ('PRX_Test_2', 'Initiator', 2),
            ('PRX_Test_3', 'Controller', 2),
            ('PRX_Test_4', 'Sentinel', 0),
            ('PRX_Test_5', 'Duelist', 0),
        ]
        created_ids = []
        for ign, role, b in spec:
            p = create_custom_player(camp.id, {
                'ign': ign,
                'age': 21,
                'nationality': 'SG_MY',
                'primary_role': role,
                'bonus_rating': b,
                'is_flex': False,
            })
            created_ids.append(p['id'])

        details = update_club_roster_bulk(camp.id, prx_club.id, starter_ids=created_ids, bench_ids=[])
        db.session.refresh(cs)
        self.assertEqual(cs.player_bonus, 6)
        self.assertEqual(cs.roster_base_rating, 96)
        self.assertEqual(cs.effective_rating, 96)
        self.assertEqual(details['club_state']['roster_base_rating'], 96)

        cs.form_modifier = 3
        db.session.commit()
        self.assertEqual(cs.effective_rating, 99)

    def test_role_coverage_flex_salary_and_import_validation(self):
        # 1. Missing Controller fails
        lineup_missing_ctrl = [
            {'ign': 'A', 'primary_role': 'Duelist', 'is_flex': False, 'bonus_rating': 1, 'salary': 110, 'nationality': 'KR', 'region_slug': 'pacific'},
            {'ign': 'B', 'primary_role': 'Duelist', 'is_flex': False, 'bonus_rating': 1, 'salary': 110, 'nationality': 'KR', 'region_slug': 'pacific'},
            {'ign': 'C', 'primary_role': 'Initiator', 'is_flex': False, 'bonus_rating': 1, 'salary': 110, 'nationality': 'KR', 'region_slug': 'pacific'},
            {'ign': 'D', 'primary_role': 'Sentinel', 'is_flex': False, 'bonus_rating': 1, 'salary': 110, 'nationality': 'KR', 'region_slug': 'pacific'},
            {'ign': 'E', 'primary_role': 'Sentinel', 'is_flex': False, 'bonus_rating': 1, 'salary': 110, 'nationality': 'KR', 'region_slug': 'pacific'},
        ]
        ok, errs, metrics = validate_roster_lineup(lineup_missing_ctrl, [], 'KR', 'pacific', 1200)
        self.assertFalse(ok)
        self.assertIn('Controller', metrics['missing_roles'])

        # 2. Replacing one Sentinel with Flex passes all 4 roles
        lineup_with_flex = list(lineup_missing_ctrl)
        lineup_with_flex[4] = {
            'ign': 'E_Flex', 'primary_role': 'Flex', 'is_flex': True,
            'bonus_rating': 2, 'salary': calculate_player_salary(2, True, 'starter'),
            'nationality': 'KR', 'region_slug': 'pacific',
        }
        ok2, errs2, _ = validate_roster_lineup(lineup_with_flex, [], 'KR', 'pacific', 1200)
        self.assertTrue(ok2, f"Expected Flex lineup valid, got: {errs2}")

        # 3. Exceeding salary cap fails
        expensive = [dict(p, bonus_rating=5, salary=550) for p in lineup_with_flex]
        ok3, errs3, _ = validate_roster_lineup(expensive, [], 'KR', 'pacific', 1200)
        self.assertFalse(ok3)
        self.assertTrue(any('quỹ lương' in e for e in errs3))

        # 4. Exceeding 2 cross-region imports fails
        too_many_imports = [
            dict(lineup_with_flex[0], region_slug='emea', nationality='FR'),
            dict(lineup_with_flex[1], region_slug='emea', nationality='UK_NORD'),
            dict(lineup_with_flex[2], region_slug='americas', nationality='NA_EAST'),
            lineup_with_flex[3],
            lineup_with_flex[4],
        ]
        ok4, errs4, m4 = validate_roster_lineup(too_many_imports, [], 'KR', 'pacific', 1500)
        self.assertFalse(ok4)
        self.assertEqual(m4['import_count'], 3)

    def test_domestic_identity_preference_for_strict_regions(self):
        self.assertLessEqual(get_club_import_openness('T1', 'KR'), 0.15)
        self.assertLessEqual(get_club_import_openness('VNTeam', 'VN'), 0.15)

        domestic_fa = {
            'id': 1, 'ign': 'KR_Rookie', 'nationality': 'KR', 'region_slug': 'pacific',
            'primary_role': 'Controller', 'is_flex': False, 'bonus_rating': 2, 'salary': 180, 'age': 19,
        }
        foreign_fa = {
            'id': 2, 'ign': 'EU_Star', 'nationality': 'FR', 'region_slug': 'emea',
            'primary_role': 'Controller', 'is_flex': False, 'bonus_rating': 2, 'salary': 180, 'age': 21,
        }

        kr_picks = 0
        rng = random.Random(42)
        for _ in range(30):
            chosen = pick_ai_replacement_player(
                free_agents=[foreign_fa, domestic_fa],
                needed_roles=['Controller'],
                club_short_code='T1',
                club_country_code='KR',
                club_region_slug='pacific',
                current_foreign_count=0,
                remaining_budget=1400,
                rng=rng,
            )
            if chosen and chosen['id'] == 1:
                kr_picks += 1

        self.assertGreaterEqual(kr_picks, 24, f"Expected strict domestic preference for KR club, got {kr_picks}/30")

    def test_retirement_and_comeback_probability_curves(self):
        # Comeback requires at least 1 year retired
        self.assertEqual(get_comeback_probability(24, years_retired=0), 0.0)

        p24 = get_comeback_probability(24, years_retired=2)
        p27 = get_comeback_probability(27, years_retired=2)
        p32 = get_comeback_probability(32, years_retired=2)
        p35 = get_comeback_probability(35, years_retired=2)
        p40 = get_comeback_probability(40, years_retired=5)

        self.assertGreater(p24, p27)
        self.assertGreater(p27, p32)
        self.assertGreater(p32, p35)
        # 35+ exact probability: 0.00000000001% = 1e-13
        self.assertAlmostEqual(p35, 1e-13, places=16)
        self.assertAlmostEqual(p40, 1e-13, places=16)

        # Retirement curve increases with age
        self.assertLess(get_retirement_probability(19, 1, 'active'), get_retirement_probability(27, 4, 'active'))
        self.assertLess(get_retirement_probability(27, 4, 'active'), get_retirement_probability(33, 8, 'active'))

    def test_preseason_draft_approval_reject_and_rollover(self):
        camp = create_campaign(name="Test Preseason Flow", start_year=2027)
        self.cleanup_campaign_ids.append(camp.id)

        # Pick 2 players and build explicit approval/rejection decisions
        active_sample = CampaignPlayer.query.filter_by(campaign_id=camp.id, status='active').limit(2).all()
        retire_yes = active_sample[0]
        retire_no = active_sample[1]
        old_age_yes = retire_yes.age
        old_age_no = retire_no.age

        draft = generate_preseason_personnel_draft(camp.id, target_year=2028)
        self.assertEqual(draft['target_year'], 2028)
        self.assertIn('rookies', draft)
        self.assertGreaterEqual(len(draft['rookies']), 8)

        decisions = {
            'retirements': [
                {'player_id': retire_yes.id, 'approved': True, 'reason': 'Test Approved Retirement'},
                {'player_id': retire_no.id, 'approved': False, 'reason': 'User Vetoed Retirement'},
            ],
            'comebacks': [],
            'role_evolutions': [],
            'rating_changes': [],
            'rookies': [
                {
                    'ign': 'DebutStarVN28',
                    'age': 18,
                    'nationality': 'VN',
                    'region_slug': 'pacific',
                    'primary_role': 'Duelist',
                    'bonus_rating': 2,
                    'is_flex': False,
                    'approved': True,
                }
            ],
        }

        res = advance_campaign_to_next_year(camp.id, personnel_decisions=decisions)
        self.assertEqual(res['new_year'], 2028)

        db.session.refresh(retire_yes)
        db.session.refresh(retire_no)
        self.assertEqual(retire_yes.status, 'retired')
        self.assertEqual(retire_yes.age, old_age_yes + 1)

        # Vetoed retirement stays active/re-signed and aged by +1
        self.assertNotEqual(retire_no.status, 'retired')
        self.assertEqual(retire_no.age, old_age_no + 1)

        # Approved debut rookie exists in DB
        rookie_db = CampaignPlayer.query.filter_by(campaign_id=camp.id, ign='DebutStarVN28').first()
        self.assertIsNotNone(rookie_db)
        self.assertEqual(rookie_db.bonus_rating, 2)

        # Ensure all 96 clubs still valid after AI offseason transfers!
        summaries = get_campaign_clubs_roster_summary(camp.id)
        for cs in CampaignClubState.query.filter_by(campaign_id=camp.id).all():
            s = summaries.get(cs.club_id)
            self.assertIsNotNone(s)
            self.assertEqual(s['starter_count'], 5, f"Year 2 {cs.club.short_code} starter count mismatch")
            self.assertTrue(s['roles_ok'], f"Year 2 {cs.club.short_code} missing roles: {s['missing_roles']}")


if __name__ == '__main__':
    unittest.main()
