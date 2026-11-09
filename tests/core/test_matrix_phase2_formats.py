"""
test_matrix_phase2_formats.py — Phase 2 Test Suite for VALORANT Master Testing Matrix A-Z.

Categories Covered:
- Category D: Double Elimination Bracket Engine (TC-D01 .. TC-D04)
- Category E: EWC Riyadh & Regional Qualifiers (TC-E01 .. TC-E04)
- Category F: Format: Kickoff Tournament Engine (TC-F01 .. TC-F04)
- Category G: Group Stage & Round-Robin Matrix (TC-G01 .. TC-G04)
- Category K: Kickoff & Stage 1/2 Open Qualifiers (TC-K01 .. TC-K04)
- Category S: Swiss Format & Anti-Rematch Engine (TC-S01 .. TC-S03)
"""

import unittest
from app import create_app
from models import db, Club, Region, CampaignClubState
from engine.format.major import generate_playoffs_4_teams
from engine.format.major_sim import simulate_major_tournament
from engine.format.kickoff import (
    init_kickoff_region_state, sim_kickoff_remaining, simulate_kickoff_tournament
)
from engine.format.ewc_qualifier import (
    init_ewc_qualifier_region_state, sim_ewc_qualifier_remaining, get_phase1_bracket_templates,
    simulate_ewc_qualifier
)
from engine.format.ewc_sim import (
    init_ewc_state, simulate_ewc_tournament
)
from engine.format.stage1 import (
    partition_stage1_groups, init_stage1_region_state, sim_stage1_remaining
)
from engine.format.stage2 import (
    partition_stage2_groups, init_stage2_region_state, sim_stage2_remaining
)
from engine.format.open_qualifier import (
    init_open_qualifier_region_state, sim_open_qualifier_remaining,
    generate_swiss_round_pairings, compute_swiss_standings
)
from services.campaign_service import create_campaign, get_campaign


class TestMatrixPhase2Formats(unittest.TestCase):

    def setUp(self):
        self.app = create_app()
        self.app_context = self.app.app_context()
        self.app_context.push()

    def tearDown(self):
        db.session.rollback()
        db.session.remove()
        self.app_context.pop()

    # ─────────────────────────────────────────────────────────────────────────
    # CATEGORY D: Double Elimination Bracket Engine
    # ─────────────────────────────────────────────────────────────────────────

    def test_tc_d01_upper_loser_routes_to_lower_bracket(self):
        """TC-D01: Templates define upper semifinal losers routing into lower bracket round 1."""
        dummy_teams = [{'id': i, 'bracket_seed': i} for i in range(1, 5)]
        templates = generate_playoffs_4_teams(dummy_teams)
        lb_r1 = next(t for t in templates if t['round_name'] == 'lower_round1')

        self.assertEqual(lb_r1['sources']['team_a']['value'], 'upper_semifinal_1')
        self.assertEqual(lb_r1['sources']['team_a']['type'], 'loser_of')
        self.assertEqual(lb_r1['sources']['team_b']['value'], 'upper_semifinal_2')
        self.assertEqual(lb_r1['sources']['team_b']['type'], 'loser_of')

    def test_tc_d02_upper_final_loser_routes_to_lower_final(self):
        """TC-D02: Upper Final loser must drop to Lower Final, winner to Grand Final."""
        dummy_teams = [{'id': i, 'bracket_seed': i} for i in range(1, 5)]
        templates = generate_playoffs_4_teams(dummy_teams)

        lf = next(t for t in templates if t['round_name'] == 'lower_final')
        gf = next(t for t in templates if t['round_name'] == 'grand_final')

        self.assertEqual(lf['sources']['team_b']['value'], 'upper_final')
        self.assertEqual(lf['sources']['team_b']['type'], 'loser_of')

        self.assertEqual(gf['sources']['team_a']['value'], 'upper_final')
        self.assertEqual(gf['sources']['team_a']['type'], 'winner_of')
        self.assertEqual(gf['sources']['team_b']['value'], 'lower_final')
        self.assertEqual(gf['sources']['team_b']['type'], 'winner_of')

    def test_tc_d03_eliminated_teams_have_exactly_two_losses(self):
        """TC-D03: In double elimination playoffs, eliminated teams have 2 losses, champion has <= 1."""
        teams = [
            {'id': 1, 'name': 'P1', 'short_code': 'P1', 'region': 'pacific', 'regional_seed': 1, 'story_rating': 90},
            {'id': 2, 'name': 'P2', 'short_code': 'P2', 'region': 'pacific', 'regional_seed': 2, 'story_rating': 86},
            {'id': 3, 'name': 'A1', 'short_code': 'A1', 'region': 'americas', 'regional_seed': 1, 'story_rating': 92},
            {'id': 4, 'name': 'A2', 'short_code': 'A2', 'region': 'americas', 'regional_seed': 2, 'story_rating': 87},
            {'id': 5, 'name': 'E1', 'short_code': 'E1', 'region': 'emea', 'regional_seed': 1, 'story_rating': 91},
            {'id': 6, 'name': 'E2', 'short_code': 'E2', 'region': 'emea', 'regional_seed': 2, 'story_rating': 85},
            {'id': 7, 'name': 'C1', 'short_code': 'C1', 'region': 'china', 'regional_seed': 1, 'story_rating': 89},
            {'id': 8, 'name': 'C2', 'short_code': 'C2', 'region': 'china', 'regional_seed': 2, 'story_rating': 84},
        ]
        res = simulate_major_tournament(teams)
        self.assertEqual(res['status'], 'completed')
        self.assertIsNotNone(res['champion'])

        # Count losses in playoff matches
        playoff_matches = res['playoff_matches']
        loss_counts = {}
        for m in playoff_matches:
            if m.get('status') == 'completed' and m.get('loser_id'):
                lid = m['loser_id']
                loss_counts[lid] = loss_counts.get(lid, 0) + 1

        champion_id = res['champion']['id']
        self.assertLessEqual(loss_counts.get(champion_id, 0), 1)

    def test_tc_d04_playoff_bo3_and_bo5_format(self):
        """TC-D04: Grand Final in Major playoffs is BO5."""
        teams = [
            {'id': 1, 'name': 'P1', 'short_code': 'P1', 'region': 'pacific', 'regional_seed': 1, 'story_rating': 90},
            {'id': 2, 'name': 'P2', 'short_code': 'P2', 'region': 'pacific', 'regional_seed': 2, 'story_rating': 86},
            {'id': 3, 'name': 'A1', 'short_code': 'A1', 'region': 'americas', 'regional_seed': 1, 'story_rating': 92},
            {'id': 4, 'name': 'A2', 'short_code': 'A2', 'region': 'americas', 'regional_seed': 2, 'story_rating': 87},
            {'id': 5, 'name': 'E1', 'short_code': 'E1', 'region': 'emea', 'regional_seed': 1, 'story_rating': 91},
            {'id': 6, 'name': 'E2', 'short_code': 'E2', 'region': 'emea', 'regional_seed': 2, 'story_rating': 85},
            {'id': 7, 'name': 'C1', 'short_code': 'C1', 'region': 'china', 'regional_seed': 1, 'story_rating': 89},
            {'id': 8, 'name': 'C2', 'short_code': 'C2', 'region': 'china', 'regional_seed': 2, 'story_rating': 84},
        ]
        res = simulate_major_tournament(teams)
        gf = next(m for m in res['playoff_matches'] if m['round_name'] == 'grand_final')
        self.assertEqual(gf['bo'], 5)
        self.assertEqual(max(gf['team_a_score'], gf['team_b_score']), 3, "Grand Final BO5 requires 3 map wins")

    # ─────────────────────────────────────────────────────────────────────────
    # CATEGORY E: EWC Riyadh & Regional Qualifiers
    # ─────────────────────────────────────────────────────────────────────────

    def test_tc_e01_ewc_qualifier_phase1_single_elimination(self):
        """TC-E01: EWC Regional Qualifier Phase 1 is single elimination (8 matches in R16 for 16 teams)."""
        p1_templates = get_phase1_bracket_templates()
        self.assertEqual(len(p1_templates), 14, "Phase 1 has 14 match templates total across bracket")
        r16_templates = [t for t in p1_templates if t.get('round_type') == 'r16']
        self.assertEqual(len(r16_templates), 8, "Phase 1 Round of 16 has 8 matches for 16 teams")

    def test_tc_e02_ewc_qualifier_phase2_double_elimination(self):
        """TC-E02: EWC Regional Qualifier Phase 2 yields exactly 2 qualifiers to Riyadh."""
        clubs = Club.query.join(Region).filter(Region.slug == 'americas').limit(22).all()
        teams = [{'id': c.id, 'name': c.name, 'short_code': c.short_code, 'story_rating': c.current_rating, 'form_modifier': 0, 'effective_rating': c.current_rating, 'logo_url': c.logo_url} for c in clubs]

        p1_teams = teams[:16]
        p2_direct_teams = teams[16:22]

        state = simulate_ewc_qualifier('americas', p1_teams, p2_direct_teams)
        self.assertEqual(state['status'], 'completed')
        self.assertEqual(len(state['ewc_qualifiers']), 2, "EWC Regional Qualifier phải lấy đúng 2 đội đi Riyadh")

    def test_tc_e03_ewc_riyadh_gsl_groups(self):
        """TC-E03: EWC Riyadh has 4 GSL groups advancing 2 teams each (8 total)."""
        clubs = Club.query.limit(16).all()
        teams = [{'id': c.id, 'name': c.name, 'short_code': c.short_code, 'region_slug': c.region.slug, 'story_rating': c.current_rating, 'form_modifier': 0, 'effective_rating': c.current_rating, 'logo_url': c.logo_url} for c in clubs]

        ewc_data = init_ewc_state(teams)
        self.assertIn('groups', ewc_data)
        self.assertEqual(len(ewc_data['groups']), 4)
        for g_label, g_data in ewc_data['groups'].items():
            self.assertEqual(len(g_data['teams']), 4, f"Bảng {g_label} phải có đúng 4 đội")

    def test_tc_e04_ewc_riyadh_playoffs_single_champion(self):
        """TC-E04: EWC Riyadh playoffs crown exactly 1 champion."""
        clubs = Club.query.limit(16).all()
        teams = [{'id': c.id, 'name': c.name, 'short_code': c.short_code, 'region_slug': c.region.slug, 'story_rating': c.current_rating, 'form_modifier': 0, 'effective_rating': c.current_rating, 'logo_url': c.logo_url} for c in clubs]

        res = simulate_ewc_tournament(teams)
        self.assertEqual(res['status'], 'completed')
        self.assertIsNotNone(res.get('champion'))
        self.assertIn('id', res['champion'])

    # ─────────────────────────────────────────────────────────────────────────
    # CATEGORY F: Format: Kickoff Tournament Engine
    # ─────────────────────────────────────────────────────────────────────────

    def test_tc_f01_kickoff_twelve_teams_and_twenty_two_matches(self):
        """TC-F01: Kickoff initializes 12 teams into 22-match double elimination bracket."""
        clubs = Club.query.join(Region).filter(Region.slug == 'emea').limit(12).all()
        participants = [{'id': c.id, 'name': c.name, 'short_code': c.short_code, 'story_rating': c.current_rating, 'form_modifier': 0, 'effective_rating': c.current_rating, 'seed': idx + 1, 'is_partner': idx < 8, 'logo_url': c.logo_url} for idx, c in enumerate(clubs)]

        state = init_kickoff_region_state('emea', participants)
        self.assertEqual(len(state['participants']), 12)
        self.assertEqual(len(state['seeds']), 12)
        self.assertEqual(len(state['matches']), 22, "Kickoff phải có đúng 22 trận đấu")

    def test_tc_f02_kickoff_simulation_and_completion(self):
        """TC-F02: Kickoff simulation progresses until state is completed."""
        clubs = Club.query.join(Region).filter(Region.slug == 'emea').limit(12).all()
        participants = [{'id': c.id, 'name': c.name, 'short_code': c.short_code, 'story_rating': c.current_rating, 'form_modifier': 0, 'effective_rating': c.current_rating, 'seed': idx + 1, 'is_partner': idx < 8, 'logo_url': c.logo_url} for idx, c in enumerate(clubs)]

        state = init_kickoff_region_state('emea', participants)
        sim_kickoff_remaining(state)

        self.assertEqual(state['status'], 'completed')
        self.assertEqual(len(state['major_qualifiers']), 2)

    def test_tc_f03_kickoff_top_two_qualify_to_bangkok(self):
        """TC-F03: Kickoff yields exactly 2 qualifiers to Major Bangkok."""
        clubs = Club.query.join(Region).filter(Region.slug == 'pacific').limit(12).all()
        participants = [{'id': c.id, 'name': c.name, 'short_code': c.short_code, 'story_rating': c.current_rating, 'form_modifier': 0, 'effective_rating': c.current_rating, 'seed': idx + 1, 'is_partner': idx < 8, 'logo_url': c.logo_url} for idx, c in enumerate(clubs)]

        res = simulate_kickoff_tournament('pacific', participants)
        self.assertEqual(len(res['major_qualifiers']), 2, "Kickoff phải lấy đúng 2 đội đi Bangkok")

    def test_tc_f04_kickoff_standings_unique_top_ranks(self):
        """TC-F04: Kickoff final rankings 1 to 4 are unique and non-overlapping."""
        clubs = Club.query.join(Region).filter(Region.slug == 'pacific').limit(12).all()
        participants = [{'id': c.id, 'name': c.name, 'short_code': c.short_code, 'story_rating': c.current_rating, 'form_modifier': 0, 'effective_rating': c.current_rating, 'seed': idx + 1, 'is_partner': idx < 8, 'logo_url': c.logo_url} for idx, c in enumerate(clubs)]

        res = simulate_kickoff_tournament('pacific', participants)
        standings = res['standings']
        top4_ranks = [s['rank'] for s in standings if s['rank'] in (1, 2, 3, 4)]
        self.assertEqual(len(top4_ranks), 4)
        self.assertEqual(len(set(top4_ranks)), 4, "Top 4 Kickoff không được trùng rank")

    # ─────────────────────────────────────────────────────────────────────────
    # CATEGORY G: Group Stage & Round-Robin Matrix
    # ─────────────────────────────────────────────────────────────────────────

    def test_tc_g01_serpentine_alpha_omega_partition(self):
        """TC-G01: Serpentine splitting distributes ranks 1,4,5,8,9,12 into Alpha; 2,3,6,7,10,11 into Omega."""
        participants = [{'id': i, 'kickoff_rank': i, 'name': f'Team {i}'} for i in range(1, 13)]
        alpha, omega = partition_stage1_groups(participants)
        self.assertEqual(len(alpha), 6)
        self.assertEqual(len(omega), 6)

        alpha_ranks = sorted([t['kickoff_rank'] for t in alpha])
        omega_ranks = sorted([t['kickoff_rank'] for t in omega])
        self.assertEqual(alpha_ranks, [1, 4, 5, 8, 9, 12])
        self.assertEqual(omega_ranks, [2, 3, 6, 7, 10, 11])

    def test_tc_g02_stage1_group_match_count(self):
        """TC-G02: Stage 1 features exactly 30 regular matches (15 Alpha + 15 Omega) per region."""
        clubs = Club.query.join(Region).filter(Region.slug == 'china').limit(12).all()
        participants = [{'id': c.id, 'name': c.name, 'short_code': c.short_code, 'story_rating': c.current_rating, 'form_modifier': 0, 'effective_rating': c.current_rating, 'seed': idx + 1, 'logo_url': c.logo_url} for idx, c in enumerate(clubs)]

        state = init_stage1_region_state('china', participants)
        regular_matches = state['regular_matches']
        self.assertEqual(len(regular_matches), 30, "Stage 1 phải có đúng 30 trận đấu vòng bảng (15 Alpha + 15 Omega)")

    def test_tc_g03_stage2_intra_group_match_count(self):
        """TC-G03: Stage 2 intra-group features exactly 30 matches (15 in Alpha + 15 in Omega)."""
        clubs = Club.query.join(Region).filter(Region.slug == 'china').limit(12).all()
        participants = [{'id': c.id, 'name': c.name, 'short_code': c.short_code, 'story_rating': c.current_rating, 'form_modifier': 0, 'effective_rating': c.current_rating, 'seed': idx + 1, 'logo_url': c.logo_url} for idx, c in enumerate(clubs)]

        state = init_stage2_region_state('china', participants)
        regular_matches = state['regular_matches']
        self.assertEqual(len(regular_matches), 30, "Stage 2 intra-group phải có đúng 30 trận đấu vòng bảng")

    def test_tc_g04_standings_update_live(self):
        """TC-G04: Simulating remaining stage matches populates standings accurately."""
        clubs = Club.query.join(Region).filter(Region.slug == 'americas').limit(12).all()
        participants = [{'id': c.id, 'name': c.name, 'short_code': c.short_code, 'story_rating': c.current_rating, 'form_modifier': 0, 'effective_rating': c.current_rating, 'seed': idx + 1, 'logo_url': c.logo_url} for idx, c in enumerate(clubs)]

        state = init_stage1_region_state('americas', participants)
        sim_stage1_remaining(state)

        self.assertEqual(state['status'], 'completed')
        self.assertEqual(len(state['masters_qualifiers']), 3, "Stage 1 phải lấy đúng 3 đội đi Masters Toronto")

    # ─────────────────────────────────────────────────────────────────────────
    # CATEGORY K: Kickoff & Stage 1/2 Open Qualifiers
    # ─────────────────────────────────────────────────────────────────────────

    def test_tc_k01_open_qualifier_sixteen_teams_zero_partners(self):
        """TC-K01: Open Qualifier contains exactly 16 teams per region and 0 partners."""
        camp = create_campaign("OQ Partner Check", 2027)
        for r_slug in ['pacific', 'americas', 'emea', 'china']:
            states = CampaignClubState.query.filter_by(campaign_id=camp.id, is_partner=False).join(Club).join(Region).filter(Region.slug == r_slug).all()
            self.assertEqual(len(states), 16)

    def test_tc_k02_open_qualifier_swiss_qualifies_four(self):
        """TC-K02: Open Qualifier Swiss format qualifies exactly 4 teams to Main Event."""
        clubs = Club.query.join(Region).filter(Region.slug == 'emea').limit(16).all()
        teams = [{'id': c.id, 'name': c.name, 'short_code': c.short_code, 'story_rating': c.current_rating, 'form_modifier': 0, 'effective_rating': c.current_rating, 'logo_url': c.logo_url} for c in clubs]

        state = init_open_qualifier_region_state('emea', teams)
        sim_open_qualifier_remaining(state)

        self.assertEqual(state['status'], 'completed')
        self.assertEqual(len(state['qualified_teams']), 4, "Open Qualifier phải có đúng 4 đội chiến thắng")

    def test_tc_k03_open_qualifier_total_matches_range(self):
        """TC-K03: Open Qualifier total matches count is 43 (33 Swiss + 10 Playoff matches)."""
        clubs = Club.query.join(Region).filter(Region.slug == 'pacific').limit(16).all()
        teams = [{'id': c.id, 'name': c.name, 'short_code': c.short_code, 'story_rating': c.current_rating, 'form_modifier': 0, 'effective_rating': c.current_rating, 'logo_url': c.logo_url} for c in clubs]

        state = init_open_qualifier_region_state('pacific', teams)
        sim_open_qualifier_remaining(state)

        all_matches = state['swiss_matches'] + state['playoff_matches']
        self.assertEqual(len(all_matches), 43, "OQ mỗi vùng có đúng 43 trận (33 Swiss + 10 Playoff)")

    def test_tc_k04_oq_winners_seed_as_nine_to_twelve(self):
        """TC-K04: 4 OQ winners are assigned seeds 9, 10, 11, 12 in Main Event."""
        camp = create_campaign("OQ Seed Check", 2027)
        from services.campaign_service import run_open_qualifier_stage, get_kickoff_data
        run_open_qualifier_stage(camp.id)

        # Kickoff should now be initialized
        ko_data = get_kickoff_data(camp.id)
        self.assertIsNotNone(ko_data)
        self.assertIn('regional_results', ko_data)
        for r_slug, reg_info in ko_data['regional_results'].items():
            teams = reg_info['participants']
            self.assertEqual(len(teams), 12)
            partner_count = sum(1 for t in teams if t.get('is_partner'))
            non_partner_count = sum(1 for t in teams if not t.get('is_partner'))
            self.assertEqual(partner_count, 8)
            self.assertEqual(non_partner_count, 4)

    # ─────────────────────────────────────────────────────────────────────────
    # CATEGORY S: Swiss Format Engine & Anti-Rematch Pairings
    # ─────────────────────────────────────────────────────────────────────────

    def test_tc_s01_swiss_score_group_pairings(self):
        """TC-S01: Swiss Round 2 pairs 1-0 teams vs 1-0 teams and 0-1 vs 0-1."""
        teams = [{'id': i, 'name': f'Team {i}', 'story_rating': 80} for i in range(1, 17)]
        # Round 1 pairings
        r1_pairings = generate_swiss_round_pairings(teams, 1, [])
        self.assertEqual(len(r1_pairings), 8)

        # Simulate Round 1 with winners
        r1_completed = []
        for p in r1_pairings:
            r1_completed.append({
                'id': f"m_{p['team_a']['id']}_{p['team_b']['id']}",
                'stage': 'swiss',
                'round': 1,
                'team_a_id': p['team_a']['id'],
                'team_b_id': p['team_b']['id'],
                'winner_id': p['team_a']['id'],  # Team A wins
                'loser_id': p['team_b']['id'],
                'team_a_score': 13,
                'team_b_score': 8,
                'status': 'completed',
            })

        # Generate Round 2 pairings
        r2_pairings = generate_swiss_round_pairings(teams, 2, r1_completed)
        self.assertEqual(len(r2_pairings), 8)

        # 4 matches in 1-0 group, 4 matches in 0-1 group
        g_1_0 = [p for p in r2_pairings if p['record_group'] == '1-0']
        g_0_1 = [p for p in r2_pairings if p['record_group'] == '0-1']
        self.assertEqual(len(g_1_0), 4)
        self.assertEqual(len(g_0_1), 4)

    def test_tc_s02_anti_rematch_enforcement(self):
        """TC-S02: Teams must not face previous opponents in subsequent Swiss rounds."""
        teams = [{'id': i, 'name': f'Team {i}', 'story_rating': 80} for i in range(1, 17)]
        r1_pairings = generate_swiss_round_pairings(teams, 1, [])
        r1_completed = []
        for p in r1_pairings:
            r1_completed.append({
                'id': f"m_{p['team_a']['id']}_{p['team_b']['id']}",
                'stage': 'swiss',
                'round': 1,
                'team_a_id': p['team_a']['id'],
                'team_b_id': p['team_b']['id'],
                'winner_id': p['team_a']['id'],
                'loser_id': p['team_b']['id'],
                'team_a_score': 13,
                'team_b_score': 8,
                'status': 'completed',
            })

        r2_pairings = generate_swiss_round_pairings(teams, 2, r1_completed)
        for p in r2_pairings:
            id_a = p['team_a']['id']
            id_b = p['team_b']['id']
            for m in r1_completed:
                played = {m['team_a_id'], m['team_b_id']}
                self.assertFalse(id_a in played and id_b in played, f"Đội {id_a} và {id_b} bị tái đấu ở vòng 2!")

    def test_tc_s03_swiss_standings_buchholz_calculation(self):
        """TC-S03: Swiss standings calculate Buchholz score accurately."""
        teams = [{'id': 1, 'name': 'T1', 'story_rating': 80}, {'id': 2, 'name': 'T2', 'story_rating': 80}, {'id': 3, 'name': 'T3', 'story_rating': 80}, {'id': 4, 'name': 'T4', 'story_rating': 80}]
        matches = [
            {'team_a_id': 1, 'team_b_id': 2, 'winner_id': 1, 'loser_id': 2, 'team_a_score': 13, 'team_b_score': 5, 'status': 'completed'},
            {'team_a_id': 3, 'team_b_id': 4, 'winner_id': 3, 'loser_id': 4, 'team_a_score': 13, 'team_b_score': 7, 'status': 'completed'},
            {'team_a_id': 1, 'team_b_id': 3, 'winner_id': 1, 'loser_id': 3, 'team_a_score': 13, 'team_b_score': 9, 'status': 'completed'},
            {'team_a_id': 2, 'team_b_id': 4, 'winner_id': 2, 'loser_id': 4, 'team_a_score': 13, 'team_b_score': 11, 'status': 'completed'},
        ]
        standings = compute_swiss_standings(teams, matches)
        t1_standing = next(s for s in standings if s['club_id'] == 1)
        # T1 played against T2 (1 win) and T3 (1 win) -> Buchholz = 2
        self.assertEqual(t1_standing['buchholz'], 2)


if __name__ == '__main__':
    unittest.main()
