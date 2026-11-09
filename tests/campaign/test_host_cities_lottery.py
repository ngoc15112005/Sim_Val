"""
Unit tests for VCT Tournament Legitimacy, Host Cities Lottery, and Major/Masters Separation.
Tests:
1. 50+ host cities database integrity (metadata, venues, capacities, atmosphere tiers).
2. pick_season_hosts deterministic lottery with 4-region balance (Option 1 & Option B).
3. Separation of VCT Major and VCT Masters in stages, placements, and trophy cabinet.
4. Dynamic stage name assignment and season summary hosts resolution.
"""

import json
import unittest
from app import create_app
from models import db, Campaign, CampaignStage, CampaignClubState, CampaignStagePlacement
from engine.host_cities import (
    HOST_CITIES,
    get_all_host_cities,
    get_city_by_id,
    get_cities_by_region,
    pick_season_hosts,
)
from services.campaign_service import (
    create_campaign,
    get_season_hosts,
    get_stage_record,
    get_major_data,
    get_master_data,
    get_ewc_data,
    get_champion_data,
    get_all_time_trophy_table,
    get_team_profile_data,
    record_stage_placements,
    _prepare_major_stage,
    _prepare_master_stage,
    _prepare_ewc_stage,
    _prepare_champion_stage,
)


class TestHostCitiesAndTournamentLegitimacy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config['TESTING'] = True
        cls.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        cls.client = cls.app.test_client()

        with cls.app.app_context():
            db.create_all()
            from seed import seed_initial_data
            seed_initial_data()

    def setUp(self):
        self.app_context = self.app.app_context()
        self.app_context.push()

    def tearDown(self):
        self.app_context.pop()

    def test_host_cities_database_integrity(self):
        """Ensure >= 50 host cities exist with complete, valid real-world metadata."""
        cities = get_all_host_cities()
        self.assertGreaterEqual(len(cities), 50, "Should have at least 50 host cities")

        required_regions = {'pacific', 'americas', 'emea', 'china'}
        for r in required_regions:
            reg_cities = get_cities_by_region(r)
            self.assertGreaterEqual(len(reg_cities), 8, f"Region {r} should have at least 8 cities")

        city_ids = set()
        for c in cities:
            # Unique ID
            self.assertNotIn(c['id'], city_ids, f"Duplicate city id: {c['id']}")
            city_ids.add(c['id'])

            # Metadata non-empty
            self.assertTrue(c.get('city_name'))
            self.assertTrue(c.get('city_name_vi'))
            self.assertTrue(c.get('country'))
            self.assertTrue(c.get('flag'))
            self.assertIn(c.get('region_slug'), required_regions)
            self.assertTrue(c.get('venue'))
            self.assertGreater(c.get('capacity', 0), 1000)
            self.assertTrue(c.get('atmosphere_tier'))

        # Check lookup by ID
        sample = cities[0]
        self.assertEqual(get_city_by_id(sample['id']), sample)

    def test_season_hosts_lottery_four_regions_balance(self):
        """Verify pick_season_hosts assigns exactly 4 tournaments to 4 distinct regions."""
        for year in [2026, 2027, 2028, 2029, 2030]:
            hosts = pick_season_hosts(year, seed=12345 + year)

            self.assertEqual(set(hosts.keys()), {'major', 'master', 'ewc', 'champion'})

            # Regions assigned to each tournament
            regions = [h['region_slug'] for h in hosts.values()]
            self.assertEqual(len(regions), 4)
            self.assertEqual(set(regions), {'pacific', 'americas', 'emea', 'china'},
                             f"Year {year} should rotate across all 4 regions: {regions}")

            # All 4 cities must be distinct
            city_ids = [h['id'] for h in hosts.values()]
            self.assertEqual(len(set(city_ids)), 4, "4 tournaments must have 4 distinct host cities")

    def test_season_hosts_determinism_and_year_rotation(self):
        """Verify deterministic picks for same seed and rotation across different years."""
        hosts_a = pick_season_hosts(2027, seed=999)
        hosts_b = pick_season_hosts(2027, seed=999)
        self.assertEqual(hosts_a, hosts_b, "Same year and seed must yield identical host cities")

        # Changing year should give a fresh lottery
        hosts_2028 = pick_season_hosts(2028, seed=999)
        # Not all 4 cities can be identical to the previous year
        same_count = sum(1 for k in hosts_a if hosts_a[k]['id'] == hosts_2028[k]['id'])
        self.assertLess(same_count, 4, "Subsequent seasons should feature new host assignments")

    def test_campaign_stage_dynamic_names_and_host_persistence(self):
        """Verify stages receive dynamic host names and persist host_city in stage_data."""
        campaign = create_campaign(name="Dynamic Host City Test", start_year=2027)
        hosts = get_season_hosts(campaign.id, 2027)

        # 1. Major Stage preparation
        dummy_ko_results = {
            r: {'major_qualifiers': [{'id': 1, 'name': 'T1', 'short_code': 'T1'},
                                     {'id': 2, 'name': 'GEN', 'short_code': 'GEN'}]}
            for r in ['pacific', 'americas', 'emea', 'china']
        }
        _prepare_major_stage(campaign, dummy_ko_results)
        m_stage = get_stage_record(campaign.id, 'major', year=2027)
        self.assertIsNotNone(m_stage)
        self.assertEqual(m_stage.stage_name, f"VCT Major {hosts['major']['city_name']} 2027")

        m_data = json.loads(m_stage.stage_data)
        self.assertEqual(m_data['host_city']['city_name'], hosts['major']['city_name'])

        # 2. Masters Stage preparation
        dummy_s1_results = {
            r: {'masters_qualifiers': [{'team': {'id': 1, 'name': 'T1', 'short_code': 'T1'}}]}
            for r in ['pacific', 'americas', 'emea', 'china']
        }
        _prepare_master_stage(campaign, dummy_s1_results)
        mt_stage = get_stage_record(campaign.id, 'master', year=2027)
        self.assertIsNotNone(mt_stage)
        self.assertEqual(mt_stage.stage_name, f"VCT Masters {hosts['master']['city_name']} 2027")

        # 3. EWC Stage preparation
        _prepare_ewc_stage(campaign, dummy_s1_results)
        ewc_stage = get_stage_record(campaign.id, 'ewc', year=2027)
        self.assertIsNotNone(ewc_stage)
        self.assertIn("Esports World Cup", ewc_stage.stage_name)
        self.assertIn(hosts['ewc']['city_name'], ewc_stage.stage_name)

        # 4. Champions Stage preparation
        _prepare_champion_stage(campaign, qualifiers=[])
        ch_stage = get_stage_record(campaign.id, 'champion', year=2027)
        self.assertIsNotNone(ch_stage)
        self.assertEqual(ch_stage.stage_name, f"VALORANT Champions {hosts['champion']['city_name']} 2027")

    def test_major_and_masters_separation_in_trophies_and_profiles(self):
        """Verify Major and Masters are tracked separately in trophy tables and team profiles."""
        campaign = create_campaign(name="Separation Test", start_year=2027)

        # Simulate a Major title and a Masters title for club 1
        p_major = CampaignStagePlacement(
            campaign_id=campaign.id,
            year=2027,
            stage_key='major',
            club_id=1,
            rank=1,
            rank_display='1st',
            tournament_name='VCT Major Tokyo 2027',
        )
        p_master = CampaignStagePlacement(
            campaign_id=campaign.id,
            year=2027,
            stage_key='master',
            club_id=1,
            rank=1,
            rank_display='1st',
            tournament_name='VCT Masters Madrid 2027',
        )
        p_champ = CampaignStagePlacement(
            campaign_id=campaign.id,
            year=2027,
            stage_key='champion',
            club_id=1,
            rank=1,
            rank_display='1st',
            tournament_name='VALORANT Champions Seoul 2027',
        )
        db.session.add_all([p_major, p_master, p_champ])
        db.session.commit()

        # Check all time trophies
        trophy_table = get_all_time_trophy_table(campaign.id)
        club_row = next((r for r in trophy_table if r['club']['id'] == 1), None)
        self.assertIsNotNone(club_row)
        self.assertEqual(club_row['champions_titles'], 1)
        self.assertEqual(club_row['major_titles'], 1, "Major titles must be recorded separately")
        self.assertEqual(club_row['masters_titles'], 1, "Masters titles must be distinct from Major")
        self.assertEqual(club_row['total_titles'], 3)

        # Check team profile data
        profile = get_team_profile_data(campaign.id, 1)
        self.assertIsNotNone(profile)
        cabinet = profile['trophy_cabinet']
        self.assertEqual(cabinet['champions_titles'], 1)
        self.assertEqual(cabinet['major_titles'], 1)
        self.assertEqual(cabinet['masters_titles'], 1)
        self.assertEqual(cabinet['total_titles'], 3)


    def test_season_hosts_true_randomness_across_saves(self):
        """Verify that separate campaigns receive different random host draws and stay persistent."""
        camp_a = create_campaign(name="Save A", start_year=2027)
        camp_b = create_campaign(name="Save B", start_year=2027)
        camp_c = create_campaign(name="Save C", start_year=2027)

        hosts_a = get_season_hosts(camp_a.id, 2027)
        hosts_b = get_season_hosts(camp_b.id, 2027)
        hosts_c = get_season_hosts(camp_c.id, 2027)

        # Persistence check: reloading hosts for camp_a returns identical cities
        hosts_a_reload = get_season_hosts(camp_a.id, 2027)
        self.assertEqual(hosts_a, hosts_a_reload, "Reloading the same campaign must return identical host cities")

        # Randomness check: across 3 different saves, they shouldn't all have identical 4 cities
        keys_a = tuple(hosts_a[k]['id'] for k in sorted(hosts_a.keys()))
        keys_b = tuple(hosts_b[k]['id'] for k in sorted(hosts_b.keys()))
        keys_c = tuple(hosts_c[k]['id'] for k in sorted(hosts_c.keys()))

        distinct_draws = len({keys_a, keys_b, keys_c})
        self.assertGreater(distinct_draws, 1, "Separate campaigns should roll distinct host cities combinations")

    def test_five_year_per_tournament_cooldown_rule(self):
        """Test the 5-Year Per-Tournament Cooldown Rule:
        If City X hosts tournament T in year Y:
        - City X CANNOT host tournament T in years [Y+1, Y+5].
        - City X CAN host other tournaments in those 5 years.
        - After 5 years (year Y+6), City X can host tournament T again.
        """
        history = {}
        # Fixed 2027 hosts: force major=tokyo, master=madrid, ewc=los_angeles, champion=shanghai
        tokyo = get_city_by_id('tokyo')
        madrid = get_city_by_id('madrid')
        la = get_city_by_id('los_angeles')
        shanghai = get_city_by_id('shanghai')

        history["2027"] = {
            "major": tokyo,
            "master": madrid,
            "ewc": la,
            "champion": shanghai,
        }

        # In years 2028-2032 (5 years cooldown):
        # Madrid CANNOT host 'master'
        for y in range(2028, 2033):
            # Run multiple lottery draws for year y using history
            for seed_val in range(10):
                draw = pick_season_hosts(y, seed=seed_val, history_hosts=history)
                # Madrid cannot be 'master' in these 5 years
                self.assertNotEqual(draw['master']['id'], 'madrid',
                                    f"Madrid cannot host Masters in year {y} due to 5-year cooldown!")

        # However, Madrid CAN host Major/EWC/Champions if EMEA is picked for them
        # Let's verify pick_season_hosts does NOT ban Madrid from other tournaments
        # We simulate 100 draws for year 2028 to verify Madrid is eligible for other tournaments
        madrid_other_count = 0
        for s in range(100):
            d = pick_season_hosts(2028, seed=s, history_hosts=history)
            if d['major']['id'] == 'madrid' or d['ewc']['id'] == 'madrid' or d['champion']['id'] == 'madrid':
                madrid_other_count += 1
        self.assertGreater(madrid_other_count, 0, "Madrid should still be eligible for other tournaments during Masters cooldown")

        # After 5 years (Year 2033 = 2027 + 6):
        # Madrid is eligible again to host Masters!
        # Fill history up to 2032 with other cities
        for y in range(2028, 2033):
            history[str(y)] = pick_season_hosts(y, seed=y * 11, history_hosts=history)

        # In 2033, Madrid can be chosen for Masters
        can_be_master_2033 = False
        for s in range(200):
            d = pick_season_hosts(2033, seed=s, history_hosts=history)
            if d['master']['id'] == 'madrid':
                can_be_master_2033 = True
                break
        self.assertTrue(can_be_master_2033, "Madrid should be eligible to host Masters again after 5-year cooldown (Year 2033)")

    def test_season_reveal_poster_rendering(self):
        """Verify the Season Reveal Poster modal and trigger buttons render correctly."""
        campaign = create_campaign(name="Poster UI Test", start_year=2027)

        # 1. Normal view: Poster button is visible on page
        resp = self.client.get(f'/campaign/{campaign.id}')
        self.assertEqual(resp.status_code, 200)
        html = resp.data.decode('utf-8')
        self.assertIn('Áp Phích Đăng Cai Mùa Giải', html)
        self.assertIn('season-reveal-poster-modal', html)
        self.assertIn('CÔNG BỐ 4 THÀNH PHỐ ĐĂNG CAI MÙA GIẢI 2027', html)

        # 2. View with reveal=1 (auto-popup triggered)
        resp_reveal = self.client.get(f'/campaign/{campaign.id}?reveal=1')
        self.assertEqual(resp_reveal.status_code, 200)
        html_reveal = resp_reveal.data.decode('utf-8')
        self.assertIn('openSeasonPosterModal()', html_reveal)

        # 3. Strict Regional Consistency: Every card's region badge must match its city's region
        import re
        p1 = html.find('id="season-reveal-poster-modal"')
        p2 = html.find('Rule & Cooldown Note', p1)
        modal_fragment = html[p1:p2]

        cities_rendered = [c.strip() for c in re.findall(r'<h3[^>]*>(.*?)</h3>', modal_fragment, re.DOTALL)]
        regions_rendered = [r.strip() for r in re.findall(r'<span style="font-size: 0.75em; color:[^>]*>(.*?)</span>', modal_fragment, re.DOTALL)]

        self.assertEqual(len(cities_rendered), 4)
        self.assertEqual(len(regions_rendered), 4)
        self.assertEqual(set(regions_rendered), {'PACIFIC', 'EMEA', 'AMERICAS', 'CHINA'})

        # Map each city name back to its actual region
        from engine.host_cities import HOST_CITIES
        city_to_region = {c['city_name']: c['region_slug'].upper() for c in HOST_CITIES}

        for c_name, r_badge in zip(cities_rendered, regions_rendered):
            self.assertIn(c_name, city_to_region, f"Rendered city {c_name} must exist in HOST_CITIES")
            self.assertEqual(r_badge, city_to_region[c_name],
                             f"Card for {c_name} must display region {city_to_region[c_name]}, but showed {r_badge}!")

        # Explicitly verify China is NOT Seoul and Americas is NOT Riyadh
        if 'CHINA' in regions_rendered:
            idx = regions_rendered.index('CHINA')
            self.assertNotEqual(cities_rendered[idx], 'Seoul', "China tournament card can NEVER host Seoul!")
        if 'AMERICAS' in regions_rendered:
            idx = regions_rendered.index('AMERICAS')
            self.assertNotEqual(cities_rendered[idx], 'Riyadh', "Americas tournament card can NEVER host Riyadh!")

    def test_riyadh_and_world_tour_100_draws_strict_regional_pairing(self):
        """Verify Riyadh is in EMEA pool and 100 draws maintain strict 1-to-1 region pairing."""
        # 1. Riyadh integrity
        riyadh = get_city_by_id('riyadh')
        self.assertIsNotNone(riyadh, "Riyadh must exist in HOST_CITIES")
        self.assertEqual(riyadh['region_slug'], 'emea', "Riyadh must belong to EMEA")
        self.assertEqual(riyadh['country_code'], 'SA')
        self.assertEqual(riyadh['flag'], '🇸🇦')
        self.assertEqual(riyadh['venue'], 'Boulevard City Arena')

        # 2. 100 random draws test
        for s in range(100):
            draw = pick_season_hosts(2027 + (s % 5), seed=s * 73)
            self.assertEqual(set(draw.keys()), {'major', 'master', 'ewc', 'champion'})
            
            regions_in_draw = {c['region_slug'] for c in draw.values()}
            self.assertEqual(regions_in_draw, {'pacific', 'emea', 'americas', 'china'},
                             "Every draw must contain exactly 4 distinct regions")

            # Verify China tournament only picks from China cities
            for tourney, city in draw.items():
                if city['region_slug'] == 'china':
                    self.assertIn(city['country'], ['China', 'Hong Kong'])
                elif city['region_slug'] == 'pacific':
                    self.assertNotIn(city['country'], ['China', 'Hong Kong'])
                elif city['region_slug'] == 'emea':
                    self.assertIn(city['country'], ['Saudi Arabia', 'Germany', 'Spain', 'France', 'United Kingdom',
                                                    'Denmark', 'Iceland', 'Turkey', 'Poland', 'Sweden',
                                                    'Netherlands', 'Portugal', 'Austria', 'United Arab Emirates'])
                elif city['region_slug'] == 'americas':
                    self.assertIn(city['country'], ['United States', 'Brazil', 'Canada', 'Mexico', 'Argentina', 'Chile'])


if __name__ == '__main__':
    unittest.main()
