"""Run 1000 simulations per tournament type and collect statistics.

Usage: python bench.py
Outputs team performance stats to help tune ratings.
"""
import sys
from collections import defaultdict

sys.path.insert(0, '.')
from app import create_app
from models import db, Club, Tournament, TournamentParticipant, Match, MatchMap, ClubRating

# Reset all per iteration - use fresh context
def reset_db(app):
    with app.app_context():
        ClubRating.query.delete()
        MatchMap.query.delete()
        Match.query.delete()
        TournamentParticipant.query.delete()
        Tournament.query.delete()
        db.session.commit()

def get_region_pools(app):
    with app.app_context():
        clubs = Club.query.all()
        pools = {}
        for c in clubs:
            pools.setdefault(c.region.slug, []).append(c)
        return pools

def run_sim(app, pools, tour_type, count=1000):
    from engine.tournament import create_tournament, generate_bracket, simulate_all_pending

    cfg = {
        'major': {'count': 8, 'slots': {'pacific': 2, 'americas': 2, 'emea': 2, 'china': 2}},
        'master': {'count': 12, 'slots': {'pacific': 3, 'americas': 3, 'emea': 3, 'china': 3}},
        'champion': {'count': 16, 'slots': {'pacific': 4, 'americas': 4, 'emea': 4, 'china': 4}},
    }
    tc = cfg[tour_type]

    stats = defaultdict(lambda: {
        'champion': 0, 'top2': 0, 'top4': 0, 'top8': 0,
        'sum_rank': 0, 'played': 0, 'wins': 0, 'losses': 0,
    })

    for sim_idx in range(count):
        reset_db(app)
        with app.app_context():
            # Pick teams: top N per region by current_rating
            club_ids = []
            regional_seeds = []
            for region_slug, slot_count in tc['slots'].items():
                region_clubs = sorted(pools[region_slug], key=lambda c: c.current_rating, reverse=True)
                for i in range(slot_count):
                    club_ids.append(region_clubs[i].id)
                    regional_seeds.append(i + 1)

            tour = create_tournament(tour_type, f'{tour_type} #{sim_idx}', club_ids, regional_seeds)
            generate_bracket(tour)
            db.session.commit()

            simulate_all_pending(tour)
            db.session.commit()

            # Collect stats
            for p in tour.participants:
                code = p.club.short_code
                rank = p.final_rank or 0
                stats[code]['sum_rank'] += rank
                stats[code]['played'] += 1
                if rank == 1:
                    stats[code]['champion'] += 1
                if rank <= 2:
                    stats[code]['top2'] += 1
                if rank <= 4:
                    stats[code]['top4'] += 1
                if rank <= 8:
                    stats[code]['top8'] += 1

            for m in tour.matches:
                if m.status != 'completed':
                    continue
                if m.team_a and m.winner:
                    stats[m.team_a.short_code]['wins'] += int(m.winner_id == m.team_a_id)
                    stats[m.team_a.short_code]['losses'] += int(m.winner_id != m.team_a_id)
                if m.team_b and m.winner:
                    stats[m.team_b.short_code]['wins'] += int(m.winner_id == m.team_b_id)
                    stats[m.team_b.short_code]['losses'] += int(m.winner_id != m.team_b_id)

        if (sim_idx + 1) % 100 == 0:
            print(f'  {tour_type}: {sim_idx + 1}/{count}...')

    return stats

def print_stats(stats, title, min_played=10):
    print(f'\n{"=" * 90}')
    print(f'  {title}')
    print(f'{"=" * 90}')
    print(f'{"Team":6s} {"Rating":>6s} {"Played":>7s} {"Win%":>7s} {"Champ":>7s} {"Top2":>7s} {"Top4":>7s} {"Top8":>7s} {"AvgRank":>8s}')
    print('-' * 80)

    items = []
    for code, s in stats.items():
        if s['played'] < min_played:
            continue
        win_rate = s['wins'] / max(1, s['wins'] + s['losses']) * 100
        avg_rank = s['sum_rank'] / s['played']
        items.append((code, win_rate, s['champion'], s['top2'], s['top4'], s['top8'], avg_rank, s['played']))

    items.sort(key=lambda x: -x[1])

    for code, win_rate, champ, top2, top4, top8, avg_rank, played in items:
        print(f'{code:6s} {win_rate:6.1f}% {played:7d} {win_rate:6.1f}% {champ:7d} {top2:7d} {top4:7d} {top8:7d} {avg_rank:8.2f}')

if __name__ == '__main__':
    print('Loading...')
    app = create_app()
    pools = get_region_pools(app)

    for ttype in ['major', 'master', 'champion']:
        N = 1000
        print(f'\nRunning {N} {ttype.upper()} simulations...')
        stats = run_sim(app, pools, ttype, N)
        print_stats(stats, f'{ttype.upper()} (n={N})')

    print('\nDone!')
