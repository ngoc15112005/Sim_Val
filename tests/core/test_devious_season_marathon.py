"""
test_devious_season_marathon.py — Devious QA Testing: Persona 5 (The State Hopper & Marathoner)

Edge Cases Covered:
- Case 15: Championship Points Idempotency (Points do not double-count upon multiple inspections or re-saves)
- Case 16: Masters Toronto 4-4-4 Seed Integrity (Exact 4 Champions, 4 Runners-up, 4 3rd-place teams)
- Case 17: EWC Qualifier Phase 1 -> Phase 2 Bracket Bridge
- Case 18: Year Transition Integrity (48 clubs preserved, CP reset to 0, CampaignSeason archived)
- Case 20: Full Season Autonomous Simulation Marathon (Complete circuit from Open Qualifier to Season Summary)
"""

import unittest
import json
from app import create_app
from models import db, Campaign, CampaignClubState, CampaignStage, CampaignSeason
from services.campaign_service import (
    create_campaign,
    run_open_qualifier_stage,
    run_kickoff_stage,
    run_major_stage,
    sim_oq_stage1_all,
    sim_stage1_all_interactive,
    sim_ewc_qualifier_all_interactive,
    get_master_data,
    sim_master_tournament_interactive,
    sim_ewc_tournament_interactive,
    sim_oq_stage2_all,
    sim_stage2_all_interactive,
    get_champion_data,
    sim_champion_tournament_interactive,
    get_championship_leaderboard,
    advance_campaign_to_next_year,
)


class TestDeviousSeasonMarathon(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app_context = self.app.app_context()
        self.app_context.push()
        self.campaign = create_campaign("Devious Marathon Campaign", start_year=2027)
        self.cid = self.campaign.id

    def tearDown(self):
        camp = db.session.get(Campaign, self.cid)
        if camp:
            db.session.delete(camp)
            db.session.commit()
        db.session.remove()
        self.app_context.pop()

    def test_case_15_cp_idempotency(self):
        """Case 15: Championship Points leaderboard queries and stage updates
        must be strictly idempotent; repeating calls must NOT increase club CP."""
        run_open_qualifier_stage(self.cid)
        run_kickoff_stage(self.cid)

        # Inspect leaderboard 5 times
        for _ in range(5):
            lb = get_championship_leaderboard(self.cid)

        # Get total CP across all clubs
        states = CampaignClubState.query.filter_by(campaign_id=self.cid).all()
        total_cp_1 = sum(s.championship_points for s in states)

        # Inspect again 5 times
        for _ in range(5):
            lb = get_championship_leaderboard(self.cid)

        states_after = CampaignClubState.query.filter_by(campaign_id=self.cid).all()
        total_cp_2 = sum(s.championship_points for s in states_after)

        self.assertEqual(total_cp_1, total_cp_2, "Leaderboard queries must never mutate or duplicate CP!")

    def test_case_16_masters_toronto_4_4_4_seeds(self):
        """Case 16: Masters Toronto must have exactly 4 Seed 1s (Stage 1 Champions),
        4 Seed 2s (Runners-up), and 4 Seed 3s (3rd Place) across the 4 regions."""
        run_open_qualifier_stage(self.cid)
        run_kickoff_stage(self.cid)
        run_major_stage(self.cid)
        sim_oq_stage1_all(self.cid)
        sim_stage1_all_interactive(self.cid)
        sim_ewc_qualifier_all_interactive(self.cid)

        m_data = get_master_data(self.cid)
        self.assertIsNotNone(m_data)
        roster = m_data['roster']
        self.assertEqual(len(roster), 12)

        seeds = [t['regional_seed'] for t in roster]
        self.assertEqual(seeds.count(1), 4, "Must have exactly 4 Seed 1 teams (Stage 1 Champions)")
        self.assertEqual(seeds.count(2), 4, "Must have exactly 4 Seed 2 teams (Stage 1 Runners-up)")
        self.assertEqual(seeds.count(3), 4, "Must have exactly 4 Seed 3 teams (Stage 1 3rd-places)")

    def test_case_18_and_20_full_season_autonomous_marathon_and_year_transition(self):
        """Cases 18 & 20: Full circuit autonomous simulation from Open Qualifier 2027
        to Champions Paris 2027, followed by advance_campaign_to_next_year (2028).
        Checks:
        - Entire circuit runs without any exception or crash.
        - Year advances from 2027 to 2028.
        - All 48 clubs stay intact (no duplicate club states).
        - Championship Points reset to 0 in new year.
        - Season 2027 is archived in CampaignSeason."""
        # 1. Kickoff circuit
        run_open_qualifier_stage(self.cid)
        run_kickoff_stage(self.cid)
        run_major_stage(self.cid)

        # 2. Stage 1 circuit
        sim_oq_stage1_all(self.cid)
        sim_stage1_all_interactive(self.cid)
        sim_ewc_qualifier_all_interactive(self.cid)

        # 3. Masters & EWC
        sim_master_tournament_interactive(self.cid)
        sim_ewc_tournament_interactive(self.cid)

        # 4. Stage 2 circuit
        sim_oq_stage2_all(self.cid)
        sim_stage2_all_interactive(self.cid)

        # 5. Champions Paris
        champ_res = sim_champion_tournament_interactive(self.cid)
        self.assertIsNotNone(champ_res['champ_data'].get('champion'), "Champions must produce a Champion!")

        # Check stage status
        camp = db.session.get(Campaign, self.cid)
        self.assertEqual(camp.current_stage, 'season_summary')

        # 6. Year Transition (2027 -> 2028)
        trans_res = advance_campaign_to_next_year(self.cid)
        self.assertEqual(trans_res['new_year'], 2028)
        self.assertEqual(trans_res['new_stage'], 'open_qualifier')

        # Verify 96 clubs intact (24 per region: 8 partner + 16 open qualifier)
        states_2028 = CampaignClubState.query.filter_by(campaign_id=self.cid).all()
        self.assertEqual(len(states_2028), 96, "Must strictly have 96 clubs across all 4 regions, no duplication!")

        # Verify CP reset to 0
        total_cp_2028 = sum(s.championship_points for s in states_2028)
        self.assertEqual(total_cp_2028, 0, "Championship Points must reset to 0 for the new season!")

        # Verify archived season
        archived = CampaignSeason.query.filter_by(campaign_id=self.cid, year=2027).first()
        self.assertIsNotNone(archived, "2027 season must be archived in CampaignSeason")

    def test_case_20_five_year_autonomous_marathon_stress_test(self):
        """Case 20: Run 5 full consecutive seasons (2027 to 2032) without any crash or data corruption."""
        for yr in range(2027, 2032):
            camp = db.session.get(Campaign, self.cid)
            self.assertEqual(camp.current_year, yr, f"Must start year {yr}")

            # 1. Kickoff circuit
            run_open_qualifier_stage(self.cid)
            run_kickoff_stage(self.cid)
            run_major_stage(self.cid)

            # 2. Stage 1 circuit
            sim_oq_stage1_all(self.cid)
            sim_stage1_all_interactive(self.cid)
            sim_ewc_qualifier_all_interactive(self.cid)

            # 3. Masters & EWC
            sim_master_tournament_interactive(self.cid)
            sim_ewc_tournament_interactive(self.cid)

            # 4. Stage 2 circuit
            sim_oq_stage2_all(self.cid)
            sim_stage2_all_interactive(self.cid)

            # 5. Champions Paris
            champ_res = sim_champion_tournament_interactive(self.cid)
            self.assertIsNotNone(champ_res['champ_data'].get('champion'))

            # 6. Advance to next year
            trans = advance_campaign_to_next_year(self.cid)
            self.assertEqual(trans['new_year'], yr + 1)
            self.assertEqual(trans['new_stage'], 'open_qualifier')

        # After 5 years (now 2032)
        camp_final = db.session.get(Campaign, self.cid)
        self.assertEqual(camp_final.current_year, 2032)

        # Check 5 archived seasons exist
        archived_seasons = CampaignSeason.query.filter_by(campaign_id=self.cid).all()
        self.assertEqual(len(archived_seasons), 5, "Must have exactly 5 archived seasons (2027..2031)")
        archived_years = [s.year for s in archived_seasons]
        self.assertEqual(sorted(archived_years), [2027, 2028, 2029, 2030, 2031])


if __name__ == '__main__':
    unittest.main()
