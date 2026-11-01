"""
test_international_parity.py — Verifies exact parity ('Cỏ lúa bằng nhau') and Regional Meta DNA
across all 4 Campaign international tournaments:
1. VCT Major (Masters Bangkok)
2. VCT Masters (Masters Toronto)
3. Esports World Cup (Riyadh)
4. VALORANT Champions (Paris)
"""

import unittest
from engine.match import calc_pure_international_win_rate, _gen_map_score
from engine.format.major_sim import _calc_international_win_rate as major_win_rate
from engine.format.master_sim import _calc_international_win_rate as master_win_rate
from engine.format.ewc_sim import _calc_ewc_win_rate as ewc_win_rate
from engine.format.champion_sim import _calc_champion_win_rate as champion_win_rate


class TestInternationalParity(unittest.TestCase):
    def setUp(self):
        self.team_high = {
            'id': 1,
            'name': 'Titan High',
            'region': 'pacific',
            'region_slug': 'pacific',
            'story_rating': 99,
            'regional_seed': 2,
        }
        self.team_low = {
            'id': 2,
            'name': 'Underdog Low',
            'region': 'pacific',
            'region_slug': 'pacific',
            'story_rating': 60,
            'regional_seed': 2,
        }

    def test_cỏ_lúa_bằng_nhau_base_probability_across_all_four(self):
        """Even with 99 vs 60 rating difference, same-region teams must have exactly 50% win rate."""
        # Major
        p_major = major_win_rate(self.team_high, self.team_low)
        self.assertAlmostEqual(p_major, 0.50, places=2)

        # Masters Toronto (previously bugged with diff * 0.0125)
        p_master = master_win_rate(self.team_high, self.team_low)
        self.assertAlmostEqual(p_master, 0.50, places=2)

        # EWC
        p_ewc = ewc_win_rate(self.team_high, self.team_low)
        self.assertAlmostEqual(p_ewc, 0.50, places=2)

        # Champions
        p_champ = champion_win_rate(self.team_high, self.team_low)
        self.assertAlmostEqual(p_champ, 0.50, places=2)

    def test_regional_dna_applied_consistently(self):
        """Cross-region matches should apply Americas/Pacific/China/EMEA buffs/debuffs."""
        team_americas = {'id': 10, 'region': 'americas', 'story_rating': 85, 'seed': 2}
        team_pacific = {'id': 20, 'region': 'pacific', 'story_rating': 85, 'seed': 2}

        # In Masters, Americas gets +3%, Pacific gets +5% -> Pacific has net +2% advantage (prob Americas = 0.48)
        p_americas_vs_pacific = master_win_rate(team_americas, team_pacific)
        self.assertAlmostEqual(p_americas_vs_pacific, 0.48, places=2)

    def test_seed_1_curse_applied(self):
        """Seed 1 entering playoffs with 0 prior matches suffers -4% cold start."""
        team_seed1 = {'id': 1, 'region': 'americas', 'seed': 1, 'regional_seed': 1}
        team_seed2 = {'id': 2, 'region': 'americas', 'seed': 2, 'regional_seed': 2}

        # Seed diff advantage: (2 - 1) * 0.01 = +1%
        # Seed 1 curse in playoff cold start: -4%
        # Net: 0.50 + 0.01 - 0.04 = 0.47
        p = master_win_rate(team_seed1, team_seed2, is_playoff=True, prior_a=0, prior_b=1)
        self.assertAlmostEqual(p, 0.47, places=2)

    def test_warmup_momentum_applied(self):
        """Team fighting through swiss (prior >= 2) gains +3% against a cold team (< 2)."""
        team_warm = {'id': 1, 'region': 'emea', 'seed': 2}
        team_cold = {'id': 2, 'region': 'emea', 'seed': 2}

        p = major_win_rate(team_warm, team_cold, prior_a=3, prior_b=1)
        self.assertAlmostEqual(p, 0.53, places=2)

    def test_map_score_still_reflects_rating_gap(self):
        """High rating difference generates stomp scores (diff >= 25 -> 13-2..13-6)."""
        scores = [_gen_map_score(99, 65) for _ in range(20)]
        for w, l in scores:
            self.assertEqual(w, 13)
            self.assertLessEqual(l, 6)


if __name__ == '__main__':
    unittest.main()
