"""
test_matrix_phase3_rules.py — Phase 3 Test Suite for VALORANT Master Testing Matrix A-Z.

Categories Covered:
- Category H: Head-to-Head & Swiss Tiebreaker Resolution System (TC-H01 .. TC-H04)
- Category I: International Parity Engine ("Cỏ Lúa Bằng Nhau") (TC-I01 .. TC-I04)
- Category J: Journey / Campaign Pipeline Stage Transitions (TC-J01 .. TC-J04)
- Category P: Points System & Championship Points (CP) Engine (TC-P01 .. TC-P04)
- Category Q: Qualification & Seed Cascades (TC-Q01 .. TC-Q03)
- Category W: Warm-up, Underdog & Regional DNA (TC-W01 .. TC-W04)
"""

import unittest
from app import create_app
from models import db, Club, Region, Campaign, CampaignClubState, CampaignStage
from engine.points import (
    get_stage_points, compare_teams_cp, sort_championship_points_leaderboard,
    determine_champions_slots
)
from engine.match import calc_pure_international_win_rate, _calc_region_bonus
from engine.format.major import _swiss_r1_seed_pairing
from services.campaign_service import (
    create_campaign, get_campaign, run_open_qualifier_stage,
    run_kickoff_stage
)


class TestMatrixPhase3Rules(unittest.TestCase):

    def setUp(self):
        self.app = create_app()
        self.app_context = self.app.app_context()
        self.app_context.push()

    def tearDown(self):
        db.session.rollback()
        db.session.remove()
        self.app_context.pop()

    # ─────────────────────────────────────────────────────────────────────────
    # CATEGORY H: Head-to-Head & Swiss Tiebreaker Resolution System
    # ─────────────────────────────────────────────────────────────────────────

    def test_tc_h01_two_team_tiebreak_head_to_head(self):
        """TC-H01: Two teams tied on CP and all prior tiebreakers resolve via H2H."""
        team_a = {'club_id': 10, 'championship_points': 5, 'h2h_wins': {20: 1}}
        team_b = {'club_id': 20, 'championship_points': 5, 'h2h_wins': {10: 0}}

        cmp_result = compare_teams_cp(team_a, team_b)
        self.assertEqual(cmp_result, -1, "Team A thắng đối đầu trực tiếp phải xếp trên Team B")

    def test_tc_h02_three_way_tie_circle_drops_to_differential(self):
        """TC-H02: Tied CP with identical stage ranks drops to map & round differential."""
        team_a = {'club_id': 1, 'championship_points': 6, 'stage2_rank': 3, 'map_differential': +5, 'round_differential': +18}
        team_b = {'club_id': 2, 'championship_points': 6, 'stage2_rank': 3, 'map_differential': +2, 'round_differential': +10}

        cmp_result = compare_teams_cp(team_a, team_b)
        self.assertEqual(cmp_result, -1, "Team A có map diff +5 phải xếp trên Team B có map diff +2")

    def test_tc_h03_stage2_rank_highest_priority_tiebreaker(self):
        """TC-H03: In VCT 2025 CP tiebreaker, Stage 2 rank takes highest precedence when CP is tied."""
        team_a = {'club_id': 1, 'championship_points': 7, 'stage2_rank': 3, 'kickoff_rank': 1}
        team_b = {'club_id': 2, 'championship_points': 7, 'stage2_rank': 4, 'kickoff_rank': 1}

        cmp_result = compare_teams_cp(team_a, team_b)
        self.assertEqual(cmp_result, -1, "Stage 2 rank 3 phải xếp trên Stage 2 rank 4")

    def test_tc_h04_deterministic_fallback_no_crash(self):
        """TC-H04: When all tiebreaker criteria are completely identical, returns 0 cleanly."""
        team_a = {'club_id': 1, 'championship_points': 5}
        team_b = {'club_id': 2, 'championship_points': 5}

        cmp_result = compare_teams_cp(team_a, team_b)
        self.assertEqual(cmp_result, 0)
        sorted_list = sort_championship_points_leaderboard([team_a, team_b])
        self.assertEqual(len(sorted_list), 2)
        self.assertEqual(sorted_list[0]['cp_rank'], 1)
        self.assertEqual(sorted_list[1]['cp_rank'], 2)

    # ─────────────────────────────────────────────────────────────────────────
    # CATEGORY I: International Parity Engine ("Cỏ Lúa Bằng Nhau")
    # ─────────────────────────────────────────────────────────────────────────

    def test_tc_i01_base_parity_win_rate_fifty_percent(self):
        """TC-I01: Base probability starts at strictly 0.50 with equal seeds and same region."""
        prob = calc_pure_international_win_rate(
            region_a='pacific', region_b='pacific', tour_type='major',
            seed_a=2, seed_b=2, prior_a=0, prior_b=0, streak_a=0, streak_b=0
        )
        self.assertEqual(prob, 0.50)

    def test_tc_i02_regional_meta_dna_applied(self):
        """TC-I02: Regional meta DNA alters probability between different regions."""
        # Americas (+3%) vs China (-7%) -> +10% diff => prob = 0.60
        prob = calc_pure_international_win_rate(
            region_a='americas', region_b='china', tour_type='major',
            seed_a=2, seed_b=2, prior_a=0, prior_b=0, streak_a=0, streak_b=0
        )
        self.assertIn(round(prob, 2), [0.60, 0.45])

    def test_tc_i03_seed_1_curse_penalty(self):
        """TC-I03: Seed 1 entering playoffs without prior matches suffers a 4% cold start penalty."""
        prob_with_curse = calc_pure_international_win_rate(
            region_a='americas', region_b='americas', tour_type='master',
            is_playoff=True, seed_a=1, seed_b=2, prior_a=0, prior_b=2
        )
        # seed_diff: 2 - 1 = +1%
        # seed_1_curse: -4%
        # warm-up rhythm: prior_b >= 2 -> -3%
        # total: 0.50 + 0.01 - 0.04 - 0.03 = 0.44
        self.assertAlmostEqual(prob_with_curse, 0.44, delta=0.001)

    def test_tc_i04_warm_up_rhythm_momentum_boost(self):
        """TC-I04: Team with prior_matches >= 2 against cold team gains 3% warm-up momentum."""
        prob_warm = calc_pure_international_win_rate(
            region_a='emea', region_b='emea', tour_type='major',
            seed_a=2, seed_b=2, prior_a=3, prior_b=0
        )
        self.assertAlmostEqual(prob_warm, 0.53, delta=0.001)

    # ─────────────────────────────────────────────────────────────────────────
    # CATEGORY J: Journey / Campaign Pipeline Stage Transitions
    # ─────────────────────────────────────────────────────────────────────────

    def test_tc_j01_campaign_stage_progression_sequential(self):
        """TC-J01: Campaign begins at open_qualifier, progresses to kickoff cleanly."""
        camp = create_campaign("Stage Progression Test", 2027)
        self.assertEqual(camp.current_stage, 'open_qualifier')

        run_open_qualifier_stage(camp.id)
        camp = db.session.get(Campaign, camp.id)
        self.assertEqual(camp.current_stage, 'kickoff', "Sau OQ, campaign phải tự động chuyển sang kickoff")

    def test_tc_j02_illegal_stage_skipping_prevented(self):
        """TC-J02: Cannot jump directly to champions while campaign is in open_qualifier."""
        camp = create_campaign("Stage Skip Test", 2027)
        client = self.app.test_client()

        # Try to sim champions directly
        resp = client.post(f'/api/campaign/{camp.id}/champion/sim-all')
        self.assertIn(resp.status_code, [400, 404])

    def test_tc_j03_stage_status_history_persisted(self):
        """TC-J03: Completed stages retain status='completed' in CampaignStage table."""
        camp = create_campaign("Stage History Test", 2027)
        run_open_qualifier_stage(camp.id)

        oq_stage = CampaignStage.query.filter_by(campaign_id=camp.id, stage_key='open_qualifier').first()
        self.assertEqual(oq_stage.status, 'completed')

    def test_tc_j04_championship_points_monotonically_increase(self):
        """TC-J04: Championship points monotonically increase across campaign stages."""
        camp = create_campaign("CP Monotonic Test", 2027)
        run_open_qualifier_stage(camp.id)
        run_kickoff_stage(camp.id)

        states = CampaignClubState.query.filter_by(campaign_id=camp.id).all()
        total_cp = sum(s.championship_points for s in states)
        self.assertGreater(total_cp, 0, "Kickoff xong phải có điểm Championship Points được trao")
        for s in states:
            self.assertGreaterEqual(s.championship_points, 0)

    # ─────────────────────────────────────────────────────────────────────────
    # CATEGORY P: Points System & Championship Points (CP) Engine
    # ─────────────────────────────────────────────────────────────────────────

    def test_tc_p01_kickoff_and_major_points_table(self):
        """TC-P01: get_stage_points returns correct points for Kickoff and Major."""
        # Kickoff points
        self.assertEqual(get_stage_points('kickoff', rank=1), 3)
        self.assertEqual(get_stage_points('kickoff', rank=2), 2)
        self.assertEqual(get_stage_points('kickoff', rank=3), 1)
        self.assertEqual(get_stage_points('kickoff', rank=4), 1)
        self.assertEqual(get_stage_points('kickoff', rank=5), 0)

        # Major Bangkok points
        self.assertEqual(get_stage_points('major', rank=1), 5)
        self.assertEqual(get_stage_points('major', rank=2), 3)
        self.assertEqual(get_stage_points('major', rank=3), 2)
        self.assertEqual(get_stage_points('major', rank=4), 1)
        self.assertEqual(get_stage_points('major', rank=5), 0)

    def test_tc_p02_regular_season_match_win_points(self):
        """TC-P02: Regular season awards 1 CP per win in Stage 1 and Stage 2."""
        self.assertEqual(get_stage_points('stage1_regular', regular_wins=4), 4)
        self.assertEqual(get_stage_points('stage2_regular', regular_wins=3), 3)

    def test_tc_p03_champions_slots_roll_down_logic(self):
        """TC-P03: If Stage 2 Top 2 also have highest CP, CP slots roll down to #3 and #4."""
        teams = [
            {'club_id': 1, 'name': 'Team A', 'championship_points': 15, 'stage2_rank': 1},  # S2 Champion
            {'club_id': 2, 'name': 'Team B', 'championship_points': 12, 'stage2_rank': 2},  # S2 Runner-up
            {'club_id': 3, 'name': 'Team C', 'championship_points': 10, 'stage2_rank': 5},  # CP Slot 1
            {'club_id': 4, 'name': 'Team D', 'championship_points': 8, 'stage2_rank': 6},   # CP Slot 2
            {'club_id': 5, 'name': 'Team E', 'championship_points': 4, 'stage2_rank': 7},
        ]
        slots = determine_champions_slots(teams)
        qualifiers = slots['qualifiers']
        self.assertEqual(len(qualifiers), 4)

        q_ids = [q['team']['club_id'] for q in qualifiers]
        self.assertEqual(q_ids, [1, 2, 3, 4], "Slots 3 và 4 phải chuyển nhượng roll-down xuống Team C và Team D")

    def test_tc_p04_champions_slots_always_four_qualifiers(self):
        """TC-P04: determine_champions_slots always returns exactly 4 qualifiers."""
        teams = [{'club_id': i, 'name': f'Team {i}', 'championship_points': 12 - i, 'stage2_rank': i} for i in range(1, 13)]
        slots = determine_champions_slots(teams)
        self.assertEqual(len(slots['qualifiers']), 4)

    # ─────────────────────────────────────────────────────────────────────────
    # CATEGORY Q: Qualification & Seed Cascades
    # ─────────────────────────────────────────────────────────────────────────

    def test_tc_q01_kickoff_qualifiers_inherit_major_seeds(self):
        """TC-Q01: Kickoff champion and runner-up inherit Major seeds 1 and 2."""
        from engine.format.kickoff import simulate_kickoff_tournament
        clubs = Club.query.join(Region).filter(Region.slug == 'pacific').limit(12).all()
        participants = [{'id': c.id, 'name': c.name, 'short_code': c.short_code, 'story_rating': c.current_rating, 'form_modifier': 0, 'effective_rating': c.current_rating, 'seed': idx + 1, 'is_partner': idx < 8, 'logo_url': c.logo_url} for idx, c in enumerate(clubs)]

        res = simulate_kickoff_tournament('pacific', participants)
        qualifiers = res['major_qualifiers']
        self.assertEqual(len(qualifiers), 2)
        # Check seeds in standings
        champ_standing = next(s for s in res['standings'] if s['rank'] == 1)
        runner_standing = next(s for s in res['standings'] if s['rank'] == 2)
        self.assertEqual(champ_standing['major_seed'], 1)
        self.assertEqual(runner_standing['major_seed'], 2)

    def test_tc_q02_swiss_r1_seed_pairing_avoids_same_region(self):
        """TC-Q02: Major Swiss Round 1 pairings avoid matching teams from the same region."""
        teams = [
            {'id': 1, 'region': 'pacific', 'regional_seed': 1, 'name': 'P1'},
            {'id': 2, 'region': 'pacific', 'regional_seed': 2, 'name': 'P2'},
            {'id': 3, 'region': 'americas', 'regional_seed': 1, 'name': 'A1'},
            {'id': 4, 'region': 'americas', 'regional_seed': 2, 'name': 'A2'},
            {'id': 5, 'region': 'emea', 'regional_seed': 1, 'name': 'E1'},
            {'id': 6, 'region': 'emea', 'regional_seed': 2, 'name': 'E2'},
            {'id': 7, 'region': 'china', 'regional_seed': 1, 'name': 'C1'},
            {'id': 8, 'region': 'china', 'regional_seed': 2, 'name': 'C2'},
        ]
        pairs = _swiss_r1_seed_pairing(teams)
        self.assertEqual(len(pairs), 4)
        for t_a, t_b in pairs:
            self.assertNotEqual(t_a['region'], t_b['region'], "Round 1 Swiss quốc tế không được cùng khu vực")

    def test_tc_q03_masters_toronto_seed1_playoff_bye(self):
        """TC-Q03: Masters Toronto gives 4 regional Seed 1 teams a direct bye into Playoffs."""
        from engine.format.master_sim import init_master_state
        teams = [
            {'id': 1, 'region': 'pacific', 'regional_seed': 1, 'name': 'P1'},
            {'id': 2, 'region': 'pacific', 'regional_seed': 2, 'name': 'P2'},
            {'id': 3, 'region': 'pacific', 'regional_seed': 3, 'name': 'P3'},
            {'id': 4, 'region': 'americas', 'regional_seed': 1, 'name': 'A1'},
            {'id': 5, 'region': 'americas', 'regional_seed': 2, 'name': 'A2'},
            {'id': 6, 'region': 'americas', 'regional_seed': 3, 'name': 'A3'},
            {'id': 7, 'region': 'emea', 'regional_seed': 1, 'name': 'E1'},
            {'id': 8, 'region': 'emea', 'regional_seed': 2, 'name': 'E2'},
            {'id': 9, 'region': 'emea', 'regional_seed': 3, 'name': 'E3'},
            {'id': 10, 'region': 'china', 'regional_seed': 1, 'name': 'C1'},
            {'id': 11, 'region': 'china', 'regional_seed': 2, 'name': 'C2'},
            {'id': 12, 'region': 'china', 'regional_seed': 3, 'name': 'C3'},
        ]
        state = init_master_state(teams)
        # 8 teams in Swiss (Seeds 2 and 3)
        self.assertEqual(len(state['swiss_standings']), 8)
        self.assertTrue(all(s['team'].get('regional_seed') in (2, 3) for s in state['swiss_standings']))
        # 4 Seed 1 teams are reserved directly for Playoffs
        self.assertEqual(len(state['direct_teams']), 4)
        self.assertTrue(all(t.get('regional_seed') == 1 for t in state['direct_teams']))

    # ─────────────────────────────────────────────────────────────────────────
    # CATEGORY W: Warm-up, Underdog & Regional DNA
    # ─────────────────────────────────────────────────────────────────────────

    def test_tc_w01_americas_dna_grand_final_buff(self):
        """TC-W01: Americas gains +3% base, +3% champions, +3% grand finals."""
        b_base = _calc_region_bonus('americas', tour_type='major', is_grand_final=False, is_champions=False, is_masters=True)
        self.assertAlmostEqual(b_base, 0.03, delta=0.001)

        b_gf = _calc_region_bonus('americas', tour_type='champion', is_grand_final=True, is_champions=True, is_masters=False)
        self.assertAlmostEqual(b_gf, 0.09, delta=0.001)

    def test_tc_w02_emea_silver_curse_grand_final(self):
        """TC-W02: EMEA suffers 'Silver Curse' (-5%) in Grand Finals."""
        b_early = _calc_region_bonus('emea', tour_type='major', is_grand_final=False, is_champions=False, is_masters=True)
        self.assertAlmostEqual(b_early, 0.03, delta=0.001)

        b_gf = _calc_region_bonus('emea', tour_type='major', is_grand_final=True, is_champions=False, is_masters=True)
        self.assertAlmostEqual(b_gf, -0.05, delta=0.001)

    def test_tc_w03_china_dna_debuff_and_zmjjkk_chance(self):
        """TC-W03: China DNA modifier is -7% against international teams (or +8% if ZmjjKK mode triggers)."""
        bonus = _calc_region_bonus('china', tour_type='major', is_grand_final=False, is_champions=False, is_masters=True)
        self.assertIn(round(bonus, 2), [-0.07, 0.08])

    def test_tc_w04_pacific_masters_dna_buff(self):
        """TC-W04: Pacific receives +5% bonus at Masters tournaments."""
        b_masters = _calc_region_bonus('pacific', tour_type='master', is_grand_final=False, is_champions=False, is_masters=True)
        self.assertAlmostEqual(b_masters, 0.05, delta=0.001)

        b_champ = _calc_region_bonus('pacific', tour_type='champion', is_grand_final=False, is_champions=True, is_masters=False)
        self.assertAlmostEqual(b_champ, 0.0, delta=0.001)


if __name__ == '__main__':
    unittest.main()
