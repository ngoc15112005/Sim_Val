import unittest
import sys
sys.path.insert(0, '.')

from app import create_app
from models import db, Club, Region, Match, Tournament, TournamentParticipant, ClubRating
from engine.tournament import create_tournament, generate_bracket, progress_tournament, simulate_all_pending
from engine.format import ewc
from services.bracket_service import get_final_standings, group_playoff_rounds, get_groups_data


class TestEWCFormatPure(unittest.TestCase):
    def setUp(self):
        self.regions = ['pacific', 'americas', 'emea', 'china']
        self.teams = []
        tid = 1
        for region in self.regions:
            for s in range(4):
                self.teams.append({
                    'id': tid,
                    'region': region,
                    'regional_seed': s + 1,
                    'short_code': f'{region[:3].upper()}{s+1}',
                    'rating': 90 - s * 5 - tid,
                })
                tid += 1

    def test_group_config(self):
        cfg = ewc.group_config()
        self.assertEqual(cfg['group_count'], 4)
        self.assertEqual(cfg['teams_per_group'], 4)
        self.assertEqual(cfg['total_advance'], 8)
        self.assertEqual(cfg['bo'], 3)

    def test_generate_gsl_groups(self):
        groups = ewc.generate_gsl_groups(self.teams)
        self.assertEqual(set(groups.keys()), {'A', 'B', 'C', 'D'})
        for label, group_teams in groups.items():
            self.assertEqual(len(group_teams), 4)
            # Exactly 1 from each regional seed
            seeds = [t['regional_seed'] for t in group_teams]
            self.assertEqual(sorted(seeds), [1, 2, 3, 4])
            # Max 1 per region
            grp_regions = [t['region'] for t in group_teams]
            self.assertEqual(len(set(grp_regions)), 4)

    def test_playoffs_draw_constraints(self):
        winners = [
            {'id': 1, 'group': 'A', 'short_code': 'W_A'},
            {'id': 2, 'group': 'B', 'short_code': 'W_B'},
            {'id': 3, 'group': 'C', 'short_code': 'W_C'},
            {'id': 4, 'group': 'D', 'short_code': 'W_D'},
        ]
        runners = [
            {'id': 5, 'group': 'A', 'short_code': 'R_A'},
            {'id': 6, 'group': 'B', 'short_code': 'R_B'},
            {'id': 7, 'group': 'C', 'short_code': 'R_C'},
            {'id': 8, 'group': 'D', 'short_code': 'R_D'},
        ]

        templates = ewc.generate_ewc_playoffs_draw(winners, runners)
        self.assertEqual(len(templates), 8)  # 4 QF + 2 SF + 1 GF + 1 3rd Place

        qfs = [t for t in templates if 'quarterfinal' in t['round_name']]
        self.assertEqual(len(qfs), 4)

        tp = next((t for t in templates if t['round_name'] == 'third_place_match'), None)
        self.assertIsNotNone(tp)
        self.assertEqual(tp['sources']['team_a']['value'], 'semifinal_1')
        self.assertEqual(tp['sources']['team_b']['value'], 'semifinal_2')

        # 1. Winner vs Runner in every QF
        winner_ids = {w['id'] for w in winners}
        runner_ids = {r['id'] for r in runners}
        for qf in qfs:
            self.assertIn(qf['high_team']['id'], winner_ids)
            self.assertIn(qf['low_team']['id'], runner_ids)
            # 2. No same group in QF
            self.assertNotEqual(qf['high_team']['group'], qf['low_team']['group'])

        # 3. Opposite halves constraint:
        top_winners_groups = {qfs[0]['high_team']['group'], qfs[1]['high_team']['group']}
        top_runners_groups = {qfs[0]['low_team']['group'], qfs[1]['low_team']['group']}
        bottom_winners_groups = {qfs[2]['high_team']['group'], qfs[3]['high_team']['group']}
        bottom_runners_groups = {qfs[2]['low_team']['group'], qfs[3]['low_team']['group']}

        # Top winners must not have their runners in the top half
        self.assertTrue(top_runners_groups.issubset(bottom_winners_groups))
        self.assertTrue(bottom_runners_groups.issubset(top_winners_groups))

    def test_resolve_slot(self):
        completed = [
            {'round_name': 'quarterfinal_1', 'winner_id': 101, 'loser_id': 201},
            {'round_name': 'quarterfinal_2', 'winner_id': 102, 'loser_id': 202},
            {'round_name': 'semifinal_1', 'winner_id': 101, 'loser_id': 102},
        ]
        sf1_tmpl = {
            'round_name': 'semifinal_1',
            'sources': {
                'team_a': {'type': 'winner_of', 'value': 'quarterfinal_1'},
                'team_b': {'type': 'winner_of', 'value': 'quarterfinal_2'},
            }
        }
        a, b = ewc.resolve_slot(sf1_tmpl, completed)
        self.assertEqual(a, 101)
        self.assertEqual(b, 102)


class TestEWCTournamentLifecycle(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.ctx = self.app.app_context()
        self.ctx.push()

    def tearDown(self):
        db.session.rollback()
        self.ctx.pop()

    def test_full_ewc_simulation(self):
        # Gather 16 clubs: 4 per region with regional seeds 1..4
        regions = ['pacific', 'americas', 'emea', 'china']
        cids = []
        rseeds = []
        for r_slug in regions:
            r = Region.query.filter_by(slug=r_slug).first()
            self.assertIsNotNone(r, f"Region {r_slug} must exist in seed")
            clubs = Club.query.filter_by(region_id=r.id, is_active=True).limit(4).all()
            self.assertEqual(len(clubs), 4)
            for i, c in enumerate(clubs):
                cids.append(c.id)
                rseeds.append(i + 1)

        # 1. Create Tournament
        tour = create_tournament('ewc', 'EWC Riyadh 2026', cids, rseeds)
        db.session.commit()
        self.assertEqual(tour.type, 'ewc')
        self.assertEqual(len(tour.participants), 16)

        # 2. Generate Bracket -> groups
        generate_bracket(tour)
        db.session.commit()
        self.assertEqual(tour.status, 'groups')
        # 8 opening matches initially
        group_matches = Match.query.filter_by(tournament_id=tour.id, round_type='group').all()
        self.assertEqual(len(group_matches), 8)

        # 3. Simulate all pending
        simulate_all_pending(tour)
        db.session.commit()

        # After full simulation, tournament should be finished
        self.assertEqual(tour.status, 'finished')

        # Check total matches:
        # Group stage: 4 groups * 5 matches = 20 matches
        # Playoffs: 4 QF + 2 SF + 1 GF + 1 3rd Place = 8 matches
        # Total = 28 matches
        all_matches = Match.query.filter_by(tournament_id=tour.id).all()
        self.assertEqual(len(all_matches), 28)

        # Grand final & 3rd place check
        gf = Match.query.filter_by(tournament_id=tour.id, round_name='grand_final').first()
        self.assertIsNotNone(gf)
        self.assertEqual(gf.status, 'completed')
        self.assertIsNotNone(gf.winner_id)

        tp = Match.query.filter_by(tournament_id=tour.id, round_name='third_place_match').first()
        self.assertIsNotNone(tp)
        self.assertEqual(tp.status, 'completed')
        self.assertIsNotNone(tp.winner_id)

        # Check final rankings of all 16 participants
        participants = TournamentParticipant.query.filter_by(tournament_id=tour.id).all()
        ranks = [p.final_rank for p in participants]
        self.assertEqual(len(ranks), 16)
        self.assertNotIn(None, ranks)
        self.assertEqual(sorted(ranks), list(range(1, 17)))

        # Winner is rank 1, GF loser is rank 2
        p_champ = next(p for p in participants if p.final_rank == 1)
        p_runner = next(p for p in participants if p.final_rank == 2)
        p_third = next(p for p in participants if p.final_rank == 3)
        p_fourth = next(p for p in participants if p.final_rank == 4)
        self.assertEqual(p_champ.club_id, gf.winner_id)
        self.assertEqual(p_runner.club_id, gf.loser_id)
        self.assertEqual(p_third.club_id, tp.winner_id)
        self.assertEqual(p_fourth.club_id, tp.loser_id)

        # Check bracket rounds
        playoff_data = group_playoff_rounds(tour)
        self.assertTrue(playoff_data['is_8team'])
        self.assertTrue(playoff_data.get('is_single_elim'))
        self.assertIn('quarterfinals', playoff_data['upper'])
        self.assertIn('semifinals', playoff_data['upper'])
        self.assertEqual(len(playoff_data['upper']['quarterfinals']), 4)
        self.assertEqual(len(playoff_data['upper']['semifinals']), 2)
        self.assertEqual(len(playoff_data['grand']), 1)
        self.assertEqual(len(playoff_data['third_place']), 1)
        self.assertEqual(len(playoff_data['lower']), 0)

        # Check final standings service
        standings = get_final_standings(tour)
        self.assertEqual(len(standings), 16)
        self.assertEqual(standings[0]['status_label'], 'Vô địch')
        self.assertEqual(standings[1]['status_label'], 'Á quân')
        self.assertEqual(standings[2]['status_label'], 'Hạng ba')
        self.assertEqual(standings[3]['status_label'], 'Hạng tư')
        for i in range(4, 8):
            self.assertEqual(standings[i]['status_label'], 'Top 5-8')

        # Web page render check
        with self.app.test_client() as client:
            resp = client.get(f'/tournament/{tour.id}')
            self.assertEqual(resp.status_code, 200)
            html = resp.data.decode('utf-8')
            self.assertIn('is-single-elim', html)
            self.assertIn('Quarterfinals', html)
            self.assertIn('Grand Final', html)
            self.assertIn('3rd Place', html)
            self.assertIn('EWC', html)


if __name__ == '__main__':
    unittest.main()
