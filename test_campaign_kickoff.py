import unittest
import json
from app import create_app
from models import db, Campaign, CampaignClubState, CampaignStage
from services.campaign_service import (
    create_campaign,
    get_campaign,
    run_open_qualifier_stage,
    run_kickoff_stage,
    override_kickoff_match,
    get_kickoff_data,
    get_championship_leaderboard,
)


class TestCampaignKickoff(unittest.TestCase):

    def setUp(self):
        self.app = create_app()
        self.client = self.app.test_client()
        self.app_context = self.app.app_context()
        self.app_context.push()

    def tearDown(self):
        db.session.remove()
        self.app_context.pop()

    def test_open_qualifier_to_kickoff_to_major_progression(self):
        # 1. Create Campaign
        campaign = create_campaign(name="Kickoff Full Test", start_year=2027)
        self.assertEqual(campaign.current_stage, 'open_qualifier')

        # 2. Run Open Qualifier for all 4 regions (172 matches total)
        oq_res = run_open_qualifier_stage(campaign.id)
        self.assertEqual(len(oq_res), 4)

        db.session.refresh(campaign)
        self.assertEqual(campaign.current_stage, 'kickoff')

        # 3. Verify Kickoff stage initialized with 12 teams per region
        k_data = get_kickoff_data(campaign.id)
        self.assertIsNotNone(k_data)
        self.assertIn('rosters', k_data)
        for r_slug in ['pacific', 'americas', 'emea', 'china']:
            self.assertEqual(len(k_data['rosters'][r_slug]), 12)

        # 4. Run Kickoff for Pacific region
        pac_res = run_kickoff_stage(campaign.id, region_slug='pacific')
        self.assertIn('pacific', pac_res)
        self.assertEqual(pac_res['pacific']['total_matches'], 22)
        self.assertEqual(len(pac_res['pacific']['major_qualifiers']), 2)

        # 5. Verify CP awarded in leaderboard
        pac_lb = get_championship_leaderboard(campaign.id, region_slug='pacific')
        self.assertEqual(pac_lb[0]['championship_points'], 3)  # Kickoff Champion
        self.assertEqual(pac_lb[1]['championship_points'], 2)  # Kickoff Runner-up
        self.assertEqual(pac_lb[2]['championship_points'], 1)  # 3rd place
        self.assertEqual(pac_lb[3]['championship_points'], 1)  # 4th place
        self.assertEqual(pac_lb[4]['championship_points'], 0)  # 5th place

        # 6. Test manual match override
        k_data_updated = get_kickoff_data(campaign.id)
        pac_matches = k_data_updated['regional_results']['pacific']['matches']
        m1 = pac_matches[0]  # upper_r1_m1
        underdog_id = m1['team_b']['id']

        override_res = override_kickoff_match(
            campaign.id, region_slug='pacific',
            round_name=m1['round_name'], winner_id=underdog_id
        )
        self.assertIn('pacific', override_res)

        k_data_after_override = get_kickoff_data(campaign.id)
        m1_after = k_data_after_override['regional_results']['pacific']['completed_dict'][m1['round_name']]
        self.assertEqual(m1_after['winner_id'], underdog_id)
        self.assertTrue(m1_after['is_manual'])

        # 7. Complete Kickoff for remaining 3 regions
        for r in ['americas', 'emea', 'china']:
            run_kickoff_stage(campaign.id, region_slug=r)

        db.session.refresh(campaign)
        self.assertEqual(campaign.current_stage, 'major')

        # 8. Verify Major stage prepared with exactly 8 teams (2 per region)
        major_stage = CampaignStage.query.filter_by(
            campaign_id=campaign.id, stage_key='major'
        ).first()
        self.assertIsNotNone(major_stage)
        major_data = json.loads(major_stage.stage_data)
        self.assertEqual(len(major_data['roster']), 8)

        # 9. Test Web Routes for Kickoff
        r = self.client.get(f'/campaign/{campaign.id}/stage/kickoff?region=pacific')
        self.assertEqual(r.status_code, 200)
        self.assertIn('VCT Kickoff (12 Đội / Khu Vực)'.encode('utf-8'), r.data)
        self.assertIn(f'KẾT QUẢ VCT KICKOFF PACIFIC {campaign.current_year}'.encode('utf-8'), r.data)

        # Cleanup
        db.session.delete(campaign)
        db.session.commit()

    def test_year2_kickoff_seeds_from_champions_including_non_partner(self):
        """Verify that in Year 2, Kickoff byes are awarded to the previous year Champions qualifiers,
        even if one of them is a Non-Partner team!
        """
        campaign = create_campaign(name="Kickoff Multi-Year Test", start_year=2027)

        # Find Pacific clubs from CampaignClubState
        from models import Region, Club
        pac_region = Region.query.filter_by(slug='pacific').first()
        pac_partner_states = CampaignClubState.query.filter_by(campaign_id=campaign.id, is_partner=True).join(Club).filter(Club.region_id == pac_region.id).all()
        pac_non_partner_states = CampaignClubState.query.filter_by(campaign_id=campaign.id, is_partner=False).join(Club).filter(Club.region_id == pac_region.id).all()

        pac_partners = [s.club for s in pac_partner_states]
        pac_non_partners = [s.club for s in pac_non_partner_states]

        # Suppose in 2027 Champions, the 4 Pacific qualifiers were:
        # 3 partners: pac_partners[0], pac_partners[1], pac_partners[2]
        # 1 non-partner: pac_non_partners[0] (e.g. DRX)
        selected_partner_ids = [p.id for p in pac_partners[:3]]
        selected_np = pac_non_partners[0]

        # Mock Year 2027 Champions stage
        champ_roster = [
            {'id': pac_partners[0].id, 'club_id': pac_partners[0].id, 'name': pac_partners[0].name, 'region_slug': 'pacific', 'champions_seed': 1, 'is_partner': True},
            {'id': pac_partners[1].id, 'club_id': pac_partners[1].id, 'name': pac_partners[1].name, 'region_slug': 'pacific', 'champions_seed': 2, 'is_partner': True},
            {'id': pac_partners[2].id, 'club_id': pac_partners[2].id, 'name': pac_partners[2].name, 'region_slug': 'pacific', 'champions_seed': 3, 'is_partner': True},
            {'id': selected_np.id, 'club_id': selected_np.id, 'name': selected_np.name, 'region_slug': 'pacific', 'champions_seed': 4, 'is_partner': False},
        ]
        champ_stage = CampaignStage(
            campaign_id=campaign.id,
            year=2027,
            stage_key='champion',
            stage_name='VALORANT Champions Paris 2027',
            status='completed',
            stage_data=json.dumps({'roster': champ_roster}),
        )
        db.session.add(champ_stage)
        db.session.commit()

        # Advance to Year 2028 Kickoff
        campaign.current_year = 2028
        campaign.current_stage = 'kickoff'
        db.session.commit()

        # Provide 4 qualified teams for each region so all 4 regions have 12 teams
        mock_oq_data = {
            'pacific': {
                'qualified_teams': [
                    {'id': selected_np.id, 'name': selected_np.name, 'short_code': selected_np.short_code, 'story_rating': 88},
                    {'id': pac_non_partners[1].id, 'name': pac_non_partners[1].name, 'short_code': pac_non_partners[1].short_code, 'story_rating': 75},
                    {'id': pac_non_partners[2].id, 'name': pac_non_partners[2].name, 'short_code': pac_non_partners[2].short_code, 'story_rating': 74},
                    {'id': pac_non_partners[3].id, 'name': pac_non_partners[3].name, 'short_code': pac_non_partners[3].short_code, 'story_rating': 73},
                ]
            },
        }
        for r_slug in ['americas', 'emea', 'china']:
            reg_obj = Region.query.filter_by(slug=r_slug).first()
            np_states = CampaignClubState.query.filter_by(campaign_id=campaign.id, is_partner=False).join(Club).filter(Club.region_id == reg_obj.id).limit(4).all()
            mock_oq_data[r_slug] = {
                'qualified_teams': [{'id': s.club_id, 'name': s.club.name, 'short_code': s.club.short_code, 'story_rating': 75} for s in np_states]
            }

        from services.campaign_service import _prepare_kickoff_stage
        _prepare_kickoff_stage(campaign, mock_oq_data)

        # Retrieve Kickoff data for Year 2028
        k_data = get_kickoff_data(campaign.id, year=2028)
        self.assertIsNotNone(k_data)
        pac_seeds = k_data['regional_results']['pacific']['seeds']

        # Byes (seeds 1..4) MUST contain the 3 partners and the 1 non-partner (selected_np)
        bye_1 = pac_seeds.get('1') or pac_seeds.get(1)
        bye_2 = pac_seeds.get('2') or pac_seeds.get(2)
        bye_3 = pac_seeds.get('3') or pac_seeds.get(3)
        bye_4 = pac_seeds.get('4') or pac_seeds.get(4)
        bye_ids = {bye_1['id'], bye_2['id'], bye_3['id'], bye_4['id']}
        self.assertIn(selected_np.id, bye_ids, "Non-Partner Champions qualifier must receive a Bye in Kickoff!")
        for pid in selected_partner_ids:
            self.assertIn(pid, bye_ids, f"Partner {pid} from Champions must receive a Bye in Kickoff!")

        # Verify selected_np gets Seed 4 because their champions_seed was 4
        self.assertEqual(bye_4['id'], selected_np.id)

        # Cleanup
        db.session.delete(campaign)
        db.session.commit()


if __name__ == '__main__':
    unittest.main()
