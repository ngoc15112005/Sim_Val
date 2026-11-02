"""
test_devious_concurrency_race.py — Devious QA Testing: Persona 3 (The Concurrency Goblin)

Edge Cases Covered:
- Case 9: Rapid-Fire / Idempotent Round Simulation (Calling sim_round twice in quick succession does not duplicate or corrupt state)
- Case 10: Premature Playoff Trigger (Attempting to resolve playoff matches before regular season is complete)
- Case 11: Premature Stage Advancement (Advancing campaign pipeline when intermediate regional or group matches are incomplete)
"""

import unittest
from engine.format.stage1 import (
    init_stage1_region_state,
    resolve_stage1_match,
    sim_stage1_round,
    advance_stage1_region,
)
from engine.format.kickoff import (
    init_kickoff_region_state,
    resolve_kickoff_match,
    sim_kickoff_round,
)
from services.campaign_service import (
    create_campaign,
    run_kickoff_stage,
)
from models import db, Campaign


class TestDeviousConcurrencyRace(unittest.TestCase):
    def setUp(self):
        self.teams_stage1 = [
            {'id': i, 'club_id': i, 'name': f"Team {i}", 'short_code': f"T{i}", 'story_rating': 80 + i, 'kickoff_rank': i}
            for i in range(1, 13)
        ]
        self.teams_kickoff = [
            {'id': i, 'club_id': i, 'name': f"Team {i}", 'short_code': f"T{i}", 'story_rating': 80 + i, 'seed': i}
            for i in range(1, 13)
        ]

    def test_case_9_idempotent_double_sim_round(self):
        """Case 9: User double-clicks 'Simulate Round' or rapid-fires two simultaneous requests.
        The second call must be a safe no-op or gracefully advance only pending matches,
        NEVER double-counting matches or jumping rounds prematurely."""
        state = init_stage1_region_state('pacific', self.teams_stage1)

        # First call simulates Week 1 (6 matches)
        simmed_1 = sim_stage1_round(state)
        self.assertEqual(simmed_1, 6, "Week 1 must simulate 6 matches")

        # Immediate second call simulates Week 2 (6 matches), NOT duplicate week 1!
        completed_week1 = [m for m in state['regular_matches'] if m.get('week') == 1 and m.get('status') == 'completed']
        self.assertEqual(len(completed_week1), 6, "Week 1 must have exactly 6 completed matches")

        simmed_2 = sim_stage1_round(state)
        self.assertEqual(simmed_2, 6, "Week 2 must simulate 6 matches")

        total_completed = [m for m in state['regular_matches'] if m.get('status') == 'completed']
        self.assertEqual(len(total_completed), 12, "Total completed must be exactly 12, no duplicates")

    def test_case_10_premature_playoff_trigger(self):
        """Case 10: User tries to resolve a playoff match while regular season matches are still pending.
        System must reject with an error instead of using incomplete standings."""
        state = init_stage1_region_state('americas', self.teams_stage1)

        # Only simulate Week 1 (24 matches still pending)
        sim_stage1_round(state)
        self.assertEqual(state['current_phase'], 'regular_season')

        ko1 = next(m for m in state['playoff_matches'] if m['match_id'] in ('UBR1-M1', 'ko_1') or 'ko_1' in m.get('aliases', []))
        with self.assertRaises(ValueError) as ctx:
            resolve_stage1_match(state, ko1['match_id'])
        # Must complain that teams are not determined / season not complete
        self.assertTrue(
            "chưa đủ 2 đội" in str(ctx.exception).lower() or
            "chưa hoàn thành" in str(ctx.exception).lower()
        )

    def test_case_11_premature_stage_advancement(self):
        """Case 11: Attempting to advance to Kickoff when Open Qualifier is incomplete
        must be blocked."""
        from app import create_app
        app = create_app()
        with app.app_context():
            camp = create_campaign("Race Test Campaign", start_year=2027)
            # In open_qualifier, without simulating anything, call run_kickoff_stage!
            # It must not silently advance to kickoff when 0 matches have been played.
            with self.assertRaises(ValueError) as ctx:
                run_kickoff_stage(camp.id)
            self.assertIn("not initialized", str(ctx.exception).lower())
            db.session.delete(camp)
            db.session.commit()


if __name__ == '__main__':
    unittest.main()
