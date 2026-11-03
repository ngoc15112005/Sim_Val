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
        self.assertIn("VCT Major", m_stage.stage_name)
        self.assertNotIn("Masters Bangkok", m_stage.stage_name)
        self.assertIn(hosts['major']['city_name'], m_stage.stage_name)

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
        self.assertIn("VCT Masters", mt_stage.stage_name)
        self.assertNotIn("Masters Toronto", mt_stage.stage_name)
        self.assertIn(hosts['master']['city_name'], mt_stage.stage_name)

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
        self.assertIn("VALORANT Champions", ch_stage.stage_name)
        self.assertNotIn("Champions Paris", ch_stage.stage_name)
        self.assertIn(hosts['champion']['city_name'], ch_stage.stage_name)

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


if __name__ == '__main__':
    unittest.main()
