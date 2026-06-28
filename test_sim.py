"""Test: Sim All still works for all 3 types after the fix."""
import sys
sys.path.insert(0, '.')
from app import create_app
from models import db, Club, ClubRating, MatchMap, Match, TournamentParticipant, Tournament
from engine.tournament import create_tournament, generate_bracket, simulate_all_pending

app = create_app()
with app.app_context():
    ClubRating.query.delete(); MatchMap.query.delete(); Match.query.delete()
    TournamentParticipant.query.delete(); Tournament.query.delete()
    db.session.commit()

    pools = {}
    for c in Club.query.all():
        pools.setdefault(c.region.slug, []).append(c)

    for ttype, slots in [('major', 2), ('master', 3), ('champion', 4)]:
        cids, rseeds = [], []
        for region in ['pacific', 'americas', 'emea', 'china']:
            sorted_c = sorted(pools[region], key=lambda c: c.current_rating, reverse=True)
            for i in range(slots):
                cids.append(sorted_c[i].id)
                rseeds.append(i + 1)
        tour = create_tournament(ttype, f'{ttype.upper()}', cids, rseeds)
        generate_bracket(tour)
        db.session.commit()
        simulate_all_pending(tour)
        db.session.commit()
        print(f'{ttype:10s}: status={tour.status}')

        # Verify no 3-0 records
        from engine.format.major import _compute_swiss_records
        from services.bracket_service import _team_to_dict, _match_to_dict
        if ttype in ('major', 'master'):
            team_dicts = [_team_to_dict(p) for p in tour.participants
                          if not (ttype == 'master' and p.regional_seed == 1)]
            completed = [_match_to_dict(m) for m in tour.matches
                         if m.status == 'completed' and m.round_type == 'swiss']
            if completed:
                records = _compute_swiss_records(team_dicts, completed)
                max_w = max(r['wins'] for r in records.values())
                max_l = max(r['losses'] for r in records.values())
                if max_w > 2 or max_l > 2:
                    print(f'  BUG: max wins={max_w} max losses={max_l}')
                else:
                    print(f'  Records OK (max 2-2)')
