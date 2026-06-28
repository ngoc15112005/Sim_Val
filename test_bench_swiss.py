"""Test: bench 1000 Major sims to see distribution of records."""
import sys
from collections import Counter
sys.path.insert(0, '.')
from app import create_app
from models import db, Club, ClubRating, MatchMap, Match, TournamentParticipant, Tournament
from engine.tournament import create_tournament, generate_bracket, simulate_all_pending
from engine.format.major import _compute_swiss_records
from services.bracket_service import _team_to_dict, _match_to_dict

app = create_app()
with app.app_context():
    import random
    random.seed(42)

    advanced_counts = Counter()
    n_sims = 100
    bad_records = Counter()
    for i in range(n_sims):
        ClubRating.query.delete(); MatchMap.query.delete(); Match.query.delete()
        TournamentParticipant.query.delete(); Tournament.query.delete()
        db.session.commit()

        clubs = Club.query.order_by(Club.current_rating.desc()).limit(8).all()
        cids = [c.id for c in clubs]
        rseeds = [1, 2, 1, 2, 1, 2, 1, 2]
        tour = create_tournament('major', f'T{i}', cids, rseeds)
        generate_bracket(tour)
        db.session.commit()
        simulate_all_pending(tour)
        db.session.commit()

        # Check final records
        if tour.status != 'finished':
            continue
        team_dicts = [_team_to_dict(p) for p in tour.participants]
        completed = [_match_to_dict(m) for m in tour.matches if m.status == 'completed' and m.round_type == 'swiss']
        records = _compute_swiss_records(team_dicts, completed)
        record_str = ','.join(f'{records[c]["wins"]}-{records[c]["losses"]}' for c in sorted(records.keys()))
        advanced_counts[record_str] += 1

        # Check for any 3-0 or 0-3 records (which shouldn't exist)
        for cid, r in records.items():
            if r['wins'] >= 3 or r['losses'] >= 3:
                bad_records[f'{r["wins"]}-{r["losses"]}'] += 1

    print(f'\n=== Records distribution over {n_sims} sims ===')
    for rec, cnt in sorted(advanced_counts.items(), key=lambda x: -x[1])[:20]:
        print(f'  {rec:60s} {cnt:4d}')

    if bad_records:
        print(f'\n=== BUG: Records with 3+ wins/losses ===')
        for r, cnt in bad_records.items():
            print(f'  {r}  {cnt}')
    else:
        print(f'\nNo 3-0/0-3 records found.')
