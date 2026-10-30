import unittest
import json
from app import create_app
from models import db, Campaign, CampaignClubState, CampaignStage
from services.campaign_service import (
    create_campaign,
    get_campaign,
    update_club_form,
    bulk_update_form,
    run_open_qualifier_stage,
    get_open_qualifier_data,
)


class TestCampaignService(unittest.TestCase):

    def setUp(self):
        self.app = create_app()
        self.app_context = self.app.app_context()
        self.app_context.push()

    def tearDown(self):
        db.session.remove()
        self.app_context.pop()

    def test_campaign_creation_and_partner_initialization(self):
        campaign = create_campaign(name="Test Story VCT", start_year=2027)
        self.assertIsNotNone(campaign.id)
        self.assertEqual(campaign.current_stage, 'open_qualifier')
        self.assertEqual(campaign.current_year, 2027)

        # Verify exactly 96 clubs initialized
        states = CampaignClubState.query.filter_by(campaign_id=campaign.id).all()
        self.assertEqual(len(states), 96)

        # Verify 32 partners and 64 non-partners
        partners = [s for s in states if s.is_partner]
        non_partners = [s for s in states if not s.is_partner]
        self.assertEqual(len(partners), 32)
        self.assertEqual(len(non_partners), 64)

        # Check by region (8 partners + 16 non-partners each)
        for r_slug in ['pacific', 'americas', 'emea', 'china']:
            reg_states = [s for s in states if s.club.region.slug == r_slug]
            self.assertEqual(len(reg_states), 24)
            p_count = sum(1 for s in reg_states if s.is_partner)
            np_count = sum(1 for s in reg_states if not s.is_partner)
            self.assertEqual(p_count, 8)
            self.assertEqual(np_count, 16)

        # Cleanup test campaign
        db.session.delete(campaign)
        db.session.commit()

    def test_form_modifier_update(self):
        campaign = create_campaign(name="Test Form Modifier", start_year=2027)
        state = CampaignClubState.query.filter_by(campaign_id=campaign.id).first()
        self.assertEqual(state.form_modifier, 0)

        # Update form
        success = update_club_form(campaign.id, state.club_id, 5)
        self.assertTrue(success)
        db.session.refresh(state)
        self.assertEqual(state.form_modifier, 5)
        self.assertEqual(state.effective_rating, state.story_rating + 5)

        # Test clamp (-15 to +15)
        update_club_form(campaign.id, state.club_id, 25)
        db.session.refresh(state)
        self.assertEqual(state.form_modifier, 15)

        # Bulk update
        bulk_update_form(campaign.id, {state.club_id: -4})
        db.session.refresh(state)
        self.assertEqual(state.form_modifier, -4)

        # Cleanup
        db.session.delete(campaign)
        db.session.commit()

    def test_run_open_qualifier_and_kickoff_transition(self):
        campaign = create_campaign(name="Test Open Qualifier Run", start_year=2027)

        # Run Open Qualifier for all 4 regions
        res = run_open_qualifier_stage(campaign.id)
        self.assertEqual(len(res), 4)

        for r_slug in ['pacific', 'americas', 'emea', 'china']:
            self.assertIn(r_slug, res)
            self.assertEqual(res[r_slug]['total_matches'], 43)
            self.assertEqual(len(res[r_slug]['qualified_teams']), 4)

        # Verify Stage is now completed and campaign transitioned to Kickoff
        db.session.refresh(campaign)
        self.assertEqual(campaign.current_stage, 'kickoff')

        oq_stage = CampaignStage.query.filter_by(
            campaign_id=campaign.id, stage_key='open_qualifier'
        ).first()
        self.assertEqual(oq_stage.status, 'completed')

        # Check Kickoff roster prepared: 12 teams per region (8 partner + 4 qualifiers)
        kickoff_stage = CampaignStage.query.filter_by(
            campaign_id=campaign.id, stage_key='kickoff'
        ).first()
        self.assertIsNotNone(kickoff_stage)
        kickoff_data = json.loads(kickoff_stage.stage_data)
        rosters = kickoff_data['rosters']

        for r_slug in ['pacific', 'americas', 'emea', 'china']:
            self.assertIn(r_slug, rosters)
            reg_roster = rosters[r_slug]
            self.assertEqual(len(reg_roster), 12)
            partner_in_roster = [t for t in reg_roster if t['is_partner']]
            qual_in_roster = [t for t in reg_roster if not t['is_partner']]
            self.assertEqual(len(partner_in_roster), 8)
            self.assertEqual(len(qual_in_roster), 4)

        # Cleanup
        db.session.delete(campaign)
        db.session.commit()


if __name__ == '__main__':
    unittest.main()
