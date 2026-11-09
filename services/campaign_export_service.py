"""
services/campaign_export_service.py — Xuất & Nạp Save Game (Export / Import Save JSON).

Cho phép người chơi:
1. Tải toàn bộ tiến trình chiến dịch (Campaign) về máy tính cá nhân dưới dạng file .json.
2. Tải file .json lên để khôi phục lại nguyên vẹn 100% chiến dịch (kể cả khi đổi máy,
   hoặc khi cơ sở dữ liệu trên máy chủ Render bị reset).
"""

import json
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from models import (
    db, Club, Campaign, CampaignClubState, CampaignStage,
    CampaignSeason, CampaignStagePlacement, CampaignPartnershipReview
)


def export_campaign_save(campaign_id: int) -> Dict[str, Any]:
    """Export an entire campaign into a JSON-serializable dictionary."""
    campaign = Campaign.query.get(campaign_id)
    if not campaign:
        raise ValueError(f"Không tìm thấy chiến dịch với ID {campaign_id}")

    # 1. Campaign metadata
    camp_meta = {
        'name': campaign.name,
        'current_year': campaign.current_year,
        'current_stage': campaign.current_stage,
        'status': campaign.status,
        'league_ratings': campaign.league_ratings or '{}',
        'season_hosts': campaign.season_hosts or '{}',
        'created_at': campaign.created_at.isoformat() if campaign.created_at else None,
        'updated_at': campaign.updated_at.isoformat() if campaign.updated_at else None,
    }

    # 2. Club states (mapped by club.short_code for database-agnostic resilience)
    club_states_data = []
    for cs in campaign.club_states:
        if not cs.club:
            continue
        club_states_data.append({
            'short_code': cs.club.short_code,
            'story_rating': cs.story_rating,
            'form_modifier': cs.form_modifier,
            'championship_points': cs.championship_points,
            'is_partner': cs.is_partner,
            'stage_ranks': cs.stage_ranks or '{}',
            'regular_season_wins': cs.regular_season_wins,
            'map_differential': cs.map_differential,
            'round_differential': cs.round_differential,
            'team_elo': cs.team_elo,
            'power_score': cs.power_score,
            'power_rating': cs.power_rating,
            'previous_rank': cs.previous_rank,
            'win_streak': cs.win_streak,
        })

    # 3. Campaign Stages
    stages_data = []
    for st in campaign.stages:
        stages_data.append({
            'year': st.year,
            'stage_key': st.stage_key,
            'stage_name': st.stage_name,
            'status': st.status,
            'stage_data': st.stage_data or '{}',
            'created_at': st.created_at.isoformat() if st.created_at else None,
            'completed_at': st.completed_at.isoformat() if st.completed_at else None,
        })

    # 4. Campaign Placements
    placements_data = []
    for p in campaign.placements:
        if not p.club:
            continue
        placements_data.append({
            'year': p.year,
            'stage_key': p.stage_key,
            'tournament_name': p.tournament_name,
            'region_slug': p.region_slug,
            'club_short_code': p.club.short_code,
            'rank': p.rank,
            'rank_display': p.rank_display,
            'elimination_stage': p.elimination_stage,
            'stage_points_earned': p.stage_points_earned,
            'matches_won': p.matches_won,
            'matches_lost': p.matches_lost,
            'power_score_snapshot': p.power_score_snapshot,
            'power_rating_snapshot': p.power_rating_snapshot,
            'created_at': p.created_at.isoformat() if p.created_at else None,
        })

    # 5. Campaign Seasons (Annual summaries)
    seasons_data = []
    for s in campaign.seasons:
        seasons_data.append({
            'year': s.year,
            'major_winner_code': s.major_winner.short_code if s.major_winner else None,
            'master_winner_code': s.master_winner.short_code if s.master_winner else None,
            'ewc_winner_code': s.ewc_winner.short_code if s.ewc_winner else None,
            'champion_winner_code': s.champion_winner.short_code if s.champion_winner else None,
            'mvp_club_code': s.mvp_club.short_code if s.mvp_club else None,
            'recap_data': s.recap_data or '{}',
            'completed_at': s.completed_at.isoformat() if s.completed_at else None,
        })

    # 6. Partnership Reviews (2-year evaluation history)
    partnership_reviews_data = []
    for pr in getattr(campaign, 'partnership_reviews', []):
        partnership_reviews_data.append({
            'year': pr.year,
            'cycle_label': pr.cycle_label,
            'status': pr.status,
            'evaluation_data': pr.evaluation_data or '{}',
            'created_at': pr.created_at.isoformat() if pr.created_at else None,
            'committed_at': pr.committed_at.isoformat() if pr.committed_at else None,
        })

    return {
        'format_version': '1.0',
        'export_type': 'vct_campaign_save',
        'exported_at': datetime.now(timezone.utc).isoformat(),
        'campaign': camp_meta,
        'club_states': club_states_data,
        'stages': stages_data,
        'placements': placements_data,
        'seasons': seasons_data,
        'partnership_reviews': partnership_reviews_data,
    }


def import_campaign_save(payload: Dict[str, Any], custom_name: Optional[str] = None) -> Campaign:
    """Import a campaign JSON payload and reconstruct all records in database."""
    if not isinstance(payload, dict):
        raise ValueError("Dữ liệu save file không hợp lệ (phải là đối tượng JSON)")

    if payload.get('export_type') != 'vct_campaign_save':
        raise ValueError("File này không phải là định dạng Save Game VCT Circuit hợp lệ")

    camp_meta = payload.get('campaign')
    if not camp_meta or not isinstance(camp_meta, dict):
        raise ValueError("Dữ liệu thông tin chiến dịch bị thiếu hoặc hỏng")

    # Map existing clubs by short_code
    all_clubs = Club.query.all()
    if not all_clubs:
        from seed import seed_initial_data
        seed_initial_data()
        all_clubs = Club.query.all()

    clubs_by_code = {c.short_code: c for c in all_clubs}

    # 1. Create new Campaign
    camp_name = custom_name or camp_meta.get('name') or 'VCT Mùa Giải Khôi Phục'
    new_campaign = Campaign(
        name=camp_name,
        current_year=camp_meta.get('current_year', 2027),
        current_stage=camp_meta.get('current_stage', 'open_qualifier'),
        status=camp_meta.get('status', 'active'),
        league_ratings=camp_meta.get('league_ratings', '{"pacific": 1500.0, "americas": 1500.0, "emea": 1500.0, "china": 1500.0}'),
        season_hosts=camp_meta.get('season_hosts', '{}'),
    )
    db.session.add(new_campaign)
    db.session.flush()

    # 2. Reconstruct Club States
    imported_club_ids = set()
    for cs_data in payload.get('club_states', []):
        code = cs_data.get('short_code')
        club = clubs_by_code.get(code)
        if not club:
            continue

        imported_club_ids.add(club.id)
        new_cs = CampaignClubState(
            campaign_id=new_campaign.id,
            club_id=club.id,
            story_rating=cs_data.get('story_rating', 80),
            form_modifier=cs_data.get('form_modifier', 0),
            championship_points=cs_data.get('championship_points', 0),
            is_partner=cs_data.get('is_partner', False),
            stage_ranks=cs_data.get('stage_ranks', '{}'),
            regular_season_wins=cs_data.get('regular_season_wins', 0),
            map_differential=cs_data.get('map_differential', 0),
            round_differential=cs_data.get('round_differential', 0),
            team_elo=cs_data.get('team_elo', 1500.0),
            power_score=cs_data.get('power_score', 1500.0),
            power_rating=cs_data.get('power_rating', 80.0),
            previous_rank=cs_data.get('previous_rank'),
            win_streak=cs_data.get('win_streak', 0),
        )
        db.session.add(new_cs)

    # If any clubs in system weren't in save file, initialize default state
    for club in all_clubs:
        if club.id not in imported_club_ids:
            db.session.add(CampaignClubState(
                campaign_id=new_campaign.id,
                club_id=club.id,
                story_rating=club.reputation or 80,
                form_modifier=0,
                championship_points=0,
                is_partner=club.is_partner,
                stage_ranks='{}',
                regular_season_wins=0,
                map_differential=0,
                round_differential=0,
                team_elo=1500.0,
                power_score=1500.0,
                power_rating=80.0,
                win_streak=0,
            ))

    # 3. Reconstruct Stages
    for st_data in payload.get('stages', []):
        c_at = None
        if st_data.get('completed_at'):
            try:
                c_at = datetime.fromisoformat(st_data['completed_at'])
            except Exception:
                c_at = None

        new_st = CampaignStage(
            campaign_id=new_campaign.id,
            year=st_data.get('year', new_campaign.current_year),
            stage_key=st_data.get('stage_key', 'open_qualifier'),
            stage_name=st_data.get('stage_name', 'Stage'),
            status=st_data.get('status', 'pending'),
            stage_data=st_data.get('stage_data', '{}'),
            completed_at=c_at,
        )
        db.session.add(new_st)

    # 4. Reconstruct Placements
    for p_data in payload.get('placements', []):
        code = p_data.get('club_short_code')
        club = clubs_by_code.get(code)
        if not club:
            continue

        new_p = CampaignStagePlacement(
            campaign_id=new_campaign.id,
            year=p_data.get('year', new_campaign.current_year),
            stage_key=p_data.get('stage_key', 'major'),
            tournament_name=p_data.get('tournament_name', ''),
            region_slug=p_data.get('region_slug'),
            club_id=club.id,
            rank=p_data.get('rank', 1),
            rank_display=p_data.get('rank_display', '#1'),
            elimination_stage=p_data.get('elimination_stage'),
            stage_points_earned=p_data.get('stage_points_earned', 0),
            matches_won=p_data.get('matches_won', 0),
            matches_lost=p_data.get('matches_lost', 0),
            power_score_snapshot=p_data.get('power_score_snapshot', 1500.0),
            power_rating_snapshot=p_data.get('power_rating_snapshot', 80.0),
        )
        db.session.add(new_p)

    # 5. Reconstruct Seasons
    for s_data in payload.get('seasons', []):
        c_at = None
        if s_data.get('completed_at'):
            try:
                c_at = datetime.fromisoformat(s_data['completed_at'])
            except Exception:
                c_at = None

        major_win = clubs_by_code.get(s_data.get('major_winner_code'))
        master_win = clubs_by_code.get(s_data.get('master_winner_code'))
        ewc_win = clubs_by_code.get(s_data.get('ewc_winner_code'))
        champ_win = clubs_by_code.get(s_data.get('champion_winner_code'))
        mvp_c = clubs_by_code.get(s_data.get('mvp_club_code'))

        new_s = CampaignSeason(
            campaign_id=new_campaign.id,
            year=s_data.get('year', new_campaign.current_year),
            major_winner_id=major_win.id if major_win else None,
            master_winner_id=master_win.id if master_win else None,
            ewc_winner_id=ewc_win.id if ewc_win else None,
            champion_winner_id=champ_win.id if champ_win else None,
            mvp_club_id=mvp_c.id if mvp_c else None,
            recap_data=s_data.get('recap_data', '{}'),
            completed_at=c_at or datetime.now(timezone.utc),
        )
        db.session.add(new_s)

    # 6. Reconstruct Partnership Reviews
    for pr_data in payload.get('partnership_reviews', []):
        cm_at = None
        if pr_data.get('committed_at'):
            try:
                cm_at = datetime.fromisoformat(pr_data['committed_at'])
            except Exception:
                cm_at = None
        new_pr = CampaignPartnershipReview(
            campaign_id=new_campaign.id,
            year=pr_data.get('year', new_campaign.current_year),
            cycle_label=pr_data.get('cycle_label', ''),
            status=pr_data.get('status', 'committed'),
            evaluation_data=pr_data.get('evaluation_data', '{}'),
            committed_at=cm_at,
        )
        db.session.add(new_pr)

    db.session.commit()
    return new_campaign
