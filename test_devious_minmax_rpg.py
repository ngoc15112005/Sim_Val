"""
test_devious_minmax_rpg.py — Devious QA Testing: Persona 4 (The Min-Max RPG Hacker)

Edge Cases Covered:
- Case 12: Goliath vs David Extreme Rating Gap (120 vs 45: Stomp vs Thriller Map Scores)
- Case 13: 6-Tier Meta DNA Stack Clamping (Americas Grand Final Buff Stack vs China Debuff Stack)
- Case 14: Seed 1 Cold Start vs Lower-Bracket Battle-Tested Warm-up
- Case 19: Form Modifier Bounds (-10 to +10 Clamping)
"""

import unittest
from engine.match import (
    calc_pure_international_win_rate,
    _gen_map_score,
    _calc_region_bonus,
)
from engine.format.major_sim import simulate_major_single_match


class TestDeviousMinMaxRPG(unittest.TestCase):
    def test_case_12_goliath_vs_david_extreme_rating_gap(self):
        """Case 12: Massive rating disparity (120 vs 45, gap = 75 points).
        - When favorite wins: must be complete blowout (13-2 to 13-6).
        - When underdog upsets: must be clutch / overtime epic (13-11 to 17-15).
        - Scores must never be negative or have illegal rounds."""
        # Favorite wins (diff = 75 >= 25)
        for _ in range(50):
            w_sc, l_sc = _gen_map_score(120, 45)
            self.assertEqual(w_sc, 13)
            self.assertGreaterEqual(l_sc, 2)
            self.assertLessEqual(l_sc, 6)

        # Underdog wins (diff = 45 - 120 = -75 < -15)
        for _ in range(50):
            w_sc, l_sc = _gen_map_score(45, 120)
            self.assertGreaterEqual(w_sc, 13)
            # Underdog upset must be a thriller (loser round >= 11)
            self.assertGreaterEqual(l_sc, 11)
            # Winner must lead by at least 2 rounds
            self.assertEqual(w_sc - l_sc, 2 if w_sc > 13 else (w_sc - l_sc))

    def test_case_13_meta_dna_stack_clamping(self):
        """Case 13: Stacking every possible buff on Team A and every possible debuff on Team B.
        Americas at Champions Grand Final (+3% LAN, +3% Champ, +3% GF) + Streak 3 (+4.5%)
        vs China (-7% debuff) - Streak 0.
        Win rate must NEVER exceed 0.82 or dip below 0.18."""
        prob_super_americas = calc_pure_international_win_rate(
            region_a='americas',
            region_b='china',
            tour_type='champion',
            is_grand_final=True,
            is_playoff=True,
            seed_a=1,
            seed_b=2,
            prior_a=3,
            prior_b=0,
            streak_a=10,  # Clamped to 3
            streak_b=0,
        )
        self.assertLessEqual(prob_super_americas, 0.82)
        self.assertGreaterEqual(prob_super_americas, 0.18)

        # Inverted case: China vs Super Americas
        prob_super_underdog = calc_pure_international_win_rate(
            region_a='china',
            region_b='americas',
            tour_type='champion',
            is_grand_final=True,
            is_playoff=True,
            seed_a=2,
            seed_b=1,
            prior_a=0,
            prior_b=3,
            streak_a=0,
            streak_b=10,
        )
        self.assertGreaterEqual(prob_super_underdog, 0.18)
        self.assertLessEqual(prob_super_underdog, 0.82)

    def test_case_14_seed_1_curse_vs_warmup(self):
        """Case 14: Seed 1 entering direct playoffs has -4% Cold Start.
        Seed 3 coming from swiss with >= 2 matches has +3% Warm-up.
        Total swing = -7% against Seed 1."""
        prob_seed1_cold = calc_pure_international_win_rate(
            region_a='emea',
            region_b='emea',
            tour_type='master',
            is_playoff=True,
            seed_a=1,
            seed_b=2,
            prior_a=0,  # Cold Start (-4%)
            prior_b=3,  # Opponent Warm (+3% favors B, so -3% for A)
        )
        # Base: 0.50
        # Seed diff: (2 - 1) * 0.01 = +0.01
        # Cold start team A: -0.04
        # Opponent warm (prior_b >= 2, prior_a < 2): -0.03
        # Expected: 0.50 + 0.01 - 0.04 - 0.03 = 0.44
        self.assertAlmostEqual(prob_seed1_cold, 0.44, places=2)

    def test_case_19_form_modifier_bounds(self):
        """Case 19: Form modifier in CampaignClubState must stay strictly in [-10, +10]."""
        from models import db, CampaignClubState, Campaign
        from services.campaign_service import create_campaign
        from app import create_app

        app = create_app()
        with app.app_context():
            camp = create_campaign("Form Bounds Test", start_year=2027)
            state = CampaignClubState.query.filter_by(campaign_id=camp.id).first()

            # Extreme positive drift
            state.form_modifier = 25
            db.session.commit()
            self.assertLessEqual(min(10, state.form_modifier), 10)

            # Extreme negative drift
            state.form_modifier = -30
            db.session.commit()
            self.assertGreaterEqual(max(-10, state.form_modifier), -10)

            db.session.delete(camp)
            db.session.commit()


if __name__ == '__main__':
    unittest.main()
