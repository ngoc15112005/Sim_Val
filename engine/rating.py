"""Rating update logic after tournament matches."""

from models import db, Club, ClubRating


def update_ratings(tournament):
    """Update all participant ratings after tournament completes.

    Simple ELO-inspired update based on final placement.
    """
    participants = tournament.participants
    if not participants:
        return

    rank_points = {
        1: 10, 2: 7, 3: 5, 4: 3,
        5: 1, 6: 1, 7: 0, 8: 0,
    }

    for p in participants:
        if p.final_rank is None:
            continue

        club = p.club
        rating_before = club.current_rating
        delta = rank_points.get(p.final_rank, 0)

        for opp in participants:
            if opp.id == p.id or opp.final_rank is None:
                continue
            if p.final_rank < opp.final_rank:
                delta += 1
            elif p.final_rank > opp.final_rank:
                delta -= 1

        delta = max(-10, min(15, delta))
        new_rating = rating_before + delta
        new_rating = max(40, min(100, new_rating))

        club.current_rating = new_rating

        cr = ClubRating(
            club_id=club.id,
            tournament_id=tournament.id,
            rating_before=rating_before,
            rating_after=new_rating,
        )
        db.session.add(cr)

    db.session.flush()
