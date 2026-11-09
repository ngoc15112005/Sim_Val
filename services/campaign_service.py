from engine.host_cities import pick_season_hosts, get_city_by_id, get_all_host_cities
"""
services/campaign_service.py — Service layer for VCT Story / Campaign Mode.

Manages:
- Campaign lifecycle (creation, state persistence, year transitions)
- Dynamic power ratings and form modifiers (isolated from single tournament mode)
- Regional Open Qualifier execution (43 matches per region, 4 qualifiers per region)
- Progression pipeline: Open Qualifier → Kickoff (12 teams) → Major → Stage 1 → Master + EWC → Stage 2 → Champions → Season Summary
- Championship Points tallying and leaderboards
"""

import json
from datetime import datetime, timezone
from typing import List, Dict, Optional, Any, Tuple, Union
from models import (
    db, Club, Region, Campaign, CampaignClubState, CampaignStage, CampaignSeason, CampaignStagePlacement
)
from config import Config
from engine.power_rating import (
    update_team_elo,
    update_regional_league_elo,
    calculate_composite_power_score,
    power_score_to_ovr,
    get_tier_info,
    format_rank_delta,
    apply_offseason_regression,
    DEFAULT_LEAGUE_ELO,
    DEFAULT_TEAM_ELO,
)
from engine.format.open_qualifier import (
    init_open_qualifier_region_state,
    resolve_open_qualifier_match,
    advance_open_qualifier_region,
    sim_open_qualifier_round,
    sim_open_qualifier_remaining,
    simulate_open_qualifier,
)
from engine.format.kickoff import (
    simulate_kickoff_tournament,
    init_kickoff_region_state,
    resolve_kickoff_match,
    advance_kickoff_region,
    sim_kickoff_round,
    sim_kickoff_remaining,
)
from engine.format.major_sim import (
    simulate_major_tournament,
    init_major_state,
    resolve_major_match,
    advance_major_state,
    sim_major_round,
    sim_major_remaining,
)
from engine.format.stage1 import (
    init_stage1_region_state,
    resolve_stage1_match,
    advance_stage1_region,
    sim_stage1_round,
    sim_stage1_remaining,
)
from engine.format.stage2 import (
    init_stage2_region_state,
    resolve_stage2_match,
    advance_stage2_region,
    sim_stage2_round,
    sim_stage2_remaining,
)
from engine.format.ewc_qualifier import (
    init_ewc_qualifier_region_state,
    resolve_ewc_qualifier_match,
    sim_ewc_qualifier_round,
    sim_ewc_qualifier_remaining,
    simulate_ewc_qualifier,
)
from engine.format.master_sim import (
    simulate_master_tournament,
    init_master_state,
    resolve_master_match,
    advance_master_state,
    sim_master_round,
    sim_master_remaining,
)
from engine.format.ewc_sim import (
    simulate_ewc_tournament,
    init_ewc_state,
    resolve_ewc_match,
    advance_ewc_state,
    sim_ewc_round,
    sim_ewc_remaining,
)
from engine.format.champion_sim import (
    simulate_champion_single_match,
    init_champion_state,
    advance_champion_state,
    resolve_champion_match,
    sim_champion_round,
    sim_champion_remaining,
    update_champion_group_standings,
)



def create_campaign(name: str = "VCT 2027 Circuit Journey", start_year: int = 2027) -> Campaign:
    """Initialize a brand-new Story Mode campaign.
    
    Copies all clubs into isolated CampaignClubState instances with:
    - story_rating initialized from Club.current_rating
    - form_modifier = 0
    - championship_points = 0
    - is_partner set according to official VCT 2027 32-team partner list.
    """
    campaign = Campaign(
        name=name,
        current_year=start_year,
        current_stage='open_qualifier',
        status='active'
    )
    # Roll genuinely unique host cities for the starting season
    from engine.host_cities import pick_season_hosts
    init_hosts = pick_season_hosts(start_year, seed=None)
    campaign.season_hosts = json.dumps({str(start_year): init_hosts})

    db.session.add(campaign)
    db.session.flush()

    clubs = Club.query.join(Region).all()
    partner_map = Config.PARTNER_TEAMS_BY_REGION

    for club in clubs:
        reg_slug = club.region.slug if club.region else ''
        partner_codes = partner_map.get(reg_slug, [])
        is_partner = club.short_code in partner_codes

        base_r = club.current_rating or club.base_rating or 80
        t_elo = round(base_r * 18.75, 1)

        state = CampaignClubState(
            campaign_id=campaign.id,
            club_id=club.id,
            story_rating=base_r,
            form_modifier=0,
            championship_points=0,
            is_partner=is_partner,
            team_elo=t_elo,
            power_score=t_elo,
            power_rating=float(base_r),
            win_streak=0,
        )
        db.session.add(state)

    # Initialize Stage 1: Open Qualifier
    oq_stage = CampaignStage(
        campaign_id=campaign.id,
        year=start_year,
        stage_key='open_qualifier',
        stage_name=f'Open Qualifier {start_year}',
        status='in_progress',
        stage_data=json.dumps({'regions': {}}),
    )
    db.session.add(oq_stage)
    db.session.flush()

    init_campaign_open_qualifier(campaign.id)

    db.session.commit()
    return campaign


def get_campaign(campaign_id: int) -> Optional[Campaign]:
    return db.session.get(Campaign, campaign_id)


def list_campaigns() -> List[Campaign]:
    return Campaign.query.order_by(Campaign.id.desc()).all()


def get_campaign_club_states(campaign_id: int, region_slug: Optional[str] = None) -> List[CampaignClubState]:
    query = CampaignClubState.query.filter_by(campaign_id=campaign_id).join(Club).join(Region)
    if region_slug:
        query = query.filter(Region.slug == region_slug)
    return query.order_by(CampaignClubState.is_partner.desc(), CampaignClubState.story_rating.desc()).all()


def update_club_form(campaign_id: int, club_id: int, form_modifier: int) -> bool:
    """Tweak a club's form modifier (-30 to +30) before a stage."""
    state = CampaignClubState.query.filter_by(campaign_id=campaign_id, club_id=club_id).first()
    if not state:
        return False
    state.form_modifier = max(-30, min(30, form_modifier))
    db.session.commit()
    return True


def bulk_update_form(campaign_id: int, updates: Dict[int, int]) -> int:
    """Batch update form modifiers for clubs (-30 to +30)."""
    count = 0
    for club_id, form_val in updates.items():
        state = CampaignClubState.query.filter_by(campaign_id=campaign_id, club_id=club_id).first()
        if state:
            state.form_modifier = max(-30, min(30, int(form_val)))
            count += 1
    db.session.commit()
    return count


def bulk_update_campaign_clubs(campaign_id: int, updates: Dict[Union[int, str], Dict[str, Any]]) -> int:
    """
    Batch update story_rating (50-99) and form_modifier (-30 to +30) for campaign clubs.
    updates format:
    {
        club_id: {
            'story_rating': int (optional, 50-99),
            'form_modifier': int (optional, -30 to 30)
        }
    }
    """
    count = 0
    for club_id, fields in updates.items():
        try:
            cid = int(club_id)
        except (ValueError, TypeError):
            continue
        state = CampaignClubState.query.filter_by(campaign_id=campaign_id, club_id=cid).first()
        if not state:
            continue
        changed = False
        if isinstance(fields, dict):
            if 'form_modifier' in fields and fields['form_modifier'] is not None:
                state.form_modifier = max(-30, min(30, int(fields['form_modifier'])))
                changed = True
            if 'story_rating' in fields and fields['story_rating'] is not None:
                state.story_rating = max(50, min(99, int(fields['story_rating'])))
                changed = True
        if changed:
            count += 1
    if count > 0:
        db.session.commit()
    return count


def get_stage_record(campaign_id: int, stage_key: str, year: Optional[int] = None) -> Optional[CampaignStage]:
    campaign = get_campaign(campaign_id)
    if not campaign:
        return None
    target_year = year or campaign.current_year
    return CampaignStage.query.filter_by(
        campaign_id=campaign_id, year=target_year, stage_key=stage_key
    ).first()


# ─────────────────────────────────────────────────────────────────────────────
# Open Qualifier Interactive & Batch Execution
# ─────────────────────────────────────────────────────────────────────────────

def init_campaign_open_qualifier(campaign_id: int) -> Dict[str, Any]:
    """Initialize Swiss Round 1 pending matches and standings for all 4 regions."""
    stage = get_stage_record(campaign_id, 'open_qualifier')
    if not stage:
        return {'regions': {}}

    data = json.loads(stage.stage_data) if stage.stage_data else {'regions': {}}
    if 'regions' not in data:
        data['regions'] = {}

    for r_slug in ['pacific', 'americas', 'emea', 'china']:
        if r_slug not in data['regions']:
            club_states = CampaignClubState.query.filter_by(
                campaign_id=campaign_id, is_partner=False
            ).join(Club).join(Region).filter(Region.slug == r_slug).all()

            if len(club_states) == 16:
                teams_data = [
                    {
                        'id': cs.club.id,
                        'name': cs.club.name,
                        'short_code': cs.club.short_code,
                        'region_slug': r_slug,
                        'story_rating': cs.story_rating,
                        'form_modifier': cs.form_modifier,
                        'effective_rating': cs.effective_rating,
                        'logo_url': cs.club.logo_url,
                    }
                    for cs in club_states
                ]
                data['regions'][r_slug] = init_open_qualifier_region_state(r_slug, teams_data)

    stage.stage_data = json.dumps(data)
    db.session.commit()
    return data




def get_season_hosts(campaign_id: int, year: int) -> Dict[str, Dict[str, Any]]:
    """Return the 4 host cities for the 4 international tournaments of this year:
    - major: VCT Major (8 teams from Kickoff)
    - master: VCT Masters (12 teams from Stage 1)
    - ewc: Esports World Cup (16 teams)
    - champion: VALORANT Champions (16 teams)

    Business Rules:
    - 4 distinct cities across 4 distinct regions (Pacific, EMEA, Americas, China)
    - Genuinely random per save & permanently persistent throughout the season in Campaign.season_hosts
    - Follows 5-Year Per-Tournament Cooldown Rule (cities cannot host the same tournament within 5 years)
    - Strictly enforces 4 distinct regions: Pacific, EMEA, Americas, China
    """
    from engine.host_cities import pick_season_hosts
    campaign = get_campaign(campaign_id)
    if not campaign:
        return pick_season_hosts(year)

    saved_hosts_map = {}
    if getattr(campaign, 'season_hosts', None):
        try:
            saved_hosts_map = json.loads(campaign.season_hosts)
        except Exception:
            saved_hosts_map = {}

    year_str = str(year)
    required_keys = ['id', 'city_name', 'country', 'flag', 'region_slug']
    tournaments = ['major', 'master', 'ewc', 'champion']

    def is_valid_hosts_set(hosts_dict: Any) -> bool:
        if not isinstance(hosts_dict, dict) or not all(k in hosts_dict for k in tournaments):
            return False
        regions = set()
        for t_k in tournaments:
            c_info = hosts_dict.get(t_k)
            if not isinstance(c_info, dict) or not all(c_info.get(rk) for rk in required_keys):
                return False
            regions.add(c_info.get('region_slug'))
        return regions == {'pacific', 'emea', 'americas', 'china'}

    if year_str in saved_hosts_map and is_valid_hosts_set(saved_hosts_map[year_str]):
        return saved_hosts_map[year_str]

    # Generate genuinely random hosts for this season, respecting 5-year cooldown and 4-region distribution
    hosts = pick_season_hosts(year, seed=None, history_hosts=saved_hosts_map)

    # Sync and heal hosts into CampaignStage records and campaign.season_hosts
    saved_hosts_map[year_str] = hosts
    campaign.season_hosts = json.dumps(saved_hosts_map)

    prefix_map = {
        'major': 'VCT Major',
        'master': 'VCT Masters',
        'ewc': 'Esports World Cup',
        'champion': 'VALORANT Champions'
    }
    for s_key in tournaments:
        st = CampaignStage.query.filter_by(campaign_id=campaign_id, year=year, stage_key=s_key).first()
        if st:
            try:
                s_data = json.loads(st.stage_data) if st.stage_data else {}
                s_data['host_city'] = hosts[s_key]
                st.stage_data = json.dumps(s_data)
                st.stage_name = f"{prefix_map[s_key]} {hosts[s_key]['city_name']} {year}"
            except Exception:
                pass

    db.session.commit()
    return hosts

def is_stage_region_actually_completed(stage_key: str, reg_data: Dict[str, Any]) -> Tuple[bool, str]:
    """Check if a regional tournament stage is genuinely finished and eligible for confirmation.
    Returns (is_completed: bool, reason_if_not: str).
    """
    if not reg_data or not isinstance(reg_data, dict):
        return False, "Dữ liệu khu vực không tồn tại"

    if stage_key in ['open_qualifier', 'oq_stage1', 'oq_stage2']:
        playoffs = reg_data.get('playoff_matches', [])
        if not playoffs:
            return False, "Chưa diễn ra vòng Playoffs"
        if len(playoffs) < 10 or not all(m.get('status') == 'completed' for m in playoffs):
            completed_count = sum(1 for m in playoffs if m.get('status') == 'completed')
            return False, f"Chưa hoàn thành tất cả các trận Playoffs ({completed_count}/{len(playoffs)} trận)"
        qual_teams = reg_data.get('qualified_teams', [])
        if len(qual_teams) < 4:
            return False, f"Chưa xác định đủ 4 đội vượt qua vòng loại ({len(qual_teams)}/4 đội)"
        return True, ""

    elif stage_key == 'kickoff':
        champ = reg_data.get('champion')
        if not champ:
            return False, "Chưa xác định đội Vô địch Kickoff"
        matches = reg_data.get('matches', [])
        if not matches:
            return False, "Chưa có danh sách trận đấu Kickoff"
        gf_match = next((m for m in matches if m.get('round_name') == 'grand_final'), None)
        if not gf_match or gf_match.get('status') != 'completed':
            return False, "Trận Chung kết tổng (Grand Final) chưa hoàn thành"
        return True, ""

    elif stage_key in ['stage1', 'stage2']:
        reg_matches = reg_data.get('regular_matches', [])
        if not reg_matches:
            return False, "Chưa có danh sách trận đấu Vòng bảng"
        if not all(m.get('status') == 'completed' for m in reg_matches):
            done_reg = sum(1 for m in reg_matches if m.get('status') == 'completed')
            return False, f"Vòng bảng chưa hoàn thành ({done_reg}/{len(reg_matches)} trận)"
        playoffs = reg_data.get('playoff_matches', [])
        if not playoffs:
            return False, "Chưa diễn ra vòng Playoffs"
        if not all(m.get('status') == 'completed' for m in playoffs):
            done_po = sum(1 for m in playoffs if m.get('status') == 'completed')
            return False, f"Vòng Playoffs chưa hoàn thành ({done_po}/{len(playoffs)} trận)"
        if not reg_data.get('champion'):
            return False, "Chưa xác định đội Vô địch"
        return True, ""

    elif stage_key == 'ewc_qualifier':
        p1 = reg_data.get('phase1_matches', [])
        p2 = reg_data.get('phase2_matches', [])
        all_matches = p1 + p2
        if not all_matches or len(all_matches) < 28:
            return False, "Chưa đủ danh sách trận đấu EWC Qualifier (cần 28 trận)"
        if not all(m.get('status') == 'completed' for m in all_matches):
            done_cnt = sum(1 for m in all_matches if m.get('status') == 'completed')
            return False, f"Các trận đấu EWC Qualifier chưa hoàn thành ({done_cnt}/{len(all_matches)} trận)"
        if not reg_data.get('champion') or not reg_data.get('runner_up'):
            return False, "Chưa xác định đủ 2 đội giành vé EWC (Champion & Runner-up)"
        return True, ""

    return True, ""


def is_stage_tournament_actually_completed(stage_key: str, res: Dict[str, Any]) -> Tuple[bool, str]:
    """Check if an international tournament is genuinely finished.
    Returns (is_completed: bool, reason_if_not: str).
    """
    if not res or not isinstance(res, dict):
        return False, "Dữ liệu giải đấu không tồn tại"

    target = res.get('result', {}) if 'result' in res else res
    if not target.get('champion'):
        return False, f"Chưa xác định đội Vô địch {stage_key.upper()}"

    playoffs = target.get('playoff_matches') or target.get('bracket_matches') or target.get('matches') or []
    if playoffs and not all(m.get('status') == 'completed' for m in playoffs):
        done_cnt = sum(1 for m in playoffs if m.get('status') == 'completed')
        return False, f"Chưa hoàn thành tất cả các trận Playoffs ({done_cnt}/{len(playoffs)} trận)"

    return True, ""


def heal_stage_regional_state(campaign: Campaign, stage: CampaignStage, stage_key: str, data: Dict[str, Any]) -> bool:
    """Detects and repairs any regions that were prematurely marked confirmed/completed
    before their matches were actually played.
    Returns True if any repairs were made and saved.
    """
    if not campaign or not stage or not data:
        return False

    if stage_key in ['open_qualifier', 'oq_stage1', 'oq_stage2', 'ewc_qualifier']:
        reg_map = data.get('regions', {})
    elif stage_key in ['kickoff', 'stage1', 'stage2']:
        reg_map = data.get('regional_results', {})
    else:
        return False

    all_regions = ['pacific', 'americas', 'emea', 'china']
    club_states = None
    repaired = False

    for r_slug in all_regions:
        reg_data = reg_map.get(r_slug)
        if not reg_data:
            continue
        is_done, _ = is_stage_region_actually_completed(stage_key, reg_data)
        if not is_done:
            # If falsely flagged as confirmed or completed, repair it!
            if reg_data.get('is_confirmed') or reg_data.get('matches_completed') or reg_data.get('status') == 'completed':
                reg_data['is_confirmed'] = False
                reg_data['matches_completed'] = False
                reg_data['status'] = 'in_progress'

                # If ratings were prematurely awarded/deducted on OQ:
                if stage_key in ['open_qualifier', 'oq_stage1', 'oq_stage2'] and reg_data.get('ratings_awarded'):
                    if club_states is None:
                        club_states = {cs.club_id: cs for cs in CampaignClubState.query.filter_by(campaign_id=campaign.id).all()}
                    for s in reg_data.get('swiss_standings', []):
                        cid = s.get('club_id')
                        if s.get('wins', 0) == 0 and cid in club_states:
                            club_states[cid].story_rating = min(99, club_states[cid].story_rating + 1)
                    reg_data['ratings_awarded'] = False

                repaired = True

    if repaired:
        all_truly_confirmed = all(reg_map.get(r, {}).get('is_confirmed') for r in all_regions)
        if not all_truly_confirmed:
            if stage.status == 'completed':
                stage.status = 'in_progress'
                stage.completed_at = None
            stage_order = [
                'open_qualifier', 'kickoff', 'major',
                'oq_stage1', 'stage1', 'ewc_qualifier',
                'master', 'ewc',
                'oq_stage2', 'stage2', 'champion', 'season_summary'
            ]
            if stage_key in stage_order and campaign.current_stage in stage_order:
                if stage_order.index(campaign.current_stage) > stage_order.index(stage_key):
                    campaign.current_stage = stage_key

        stage.stage_data = json.dumps(data)
        db.session.commit()

    return repaired


def heal_stage_tournament_state(campaign: Campaign, stage: CampaignStage, stage_key: str, data: Dict[str, Any]) -> bool:
    """Repairs international tournament state if falsely marked confirmed/completed."""
    if not campaign or not stage or not data:
        return False

    res = data.get('result', {}) if 'result' in data else data
    is_done, _ = is_stage_tournament_actually_completed(stage_key, res)
    if not is_done:
        if res.get('is_confirmed') or res.get('matches_completed') or res.get('status') == 'completed':
            res['is_confirmed'] = False
            res['matches_completed'] = False
            res['status'] = 'in_progress'
            if stage.status == 'completed':
                stage.status = 'in_progress'
                stage.completed_at = None
            stage_order = [
                'open_qualifier', 'kickoff', 'major',
                'oq_stage1', 'stage1', 'ewc_qualifier',
                'master', 'ewc',
                'oq_stage2', 'stage2', 'champion', 'season_summary'
            ]
            if stage_key in stage_order and campaign.current_stage in stage_order:
                if stage_order.index(campaign.current_stage) > stage_order.index(stage_key):
                    campaign.current_stage = stage_key

            stage.stage_data = json.dumps(data)
            db.session.commit()
            return True
    return False


def unlock_stage_region(campaign_id: int, stage_key: str, region_slug: str) -> Dict[str, Any]:
    """Explicitly unlock a locked region to allow reviewing, editing scores, or rolling matches again."""
    campaign = get_campaign(campaign_id)
    if not campaign:
        raise ValueError(f"Campaign {campaign_id} not found")

    stage = get_stage_record(campaign_id, stage_key)
    if not stage:
        raise ValueError(f"Stage {stage_key} not found")

    data = json.loads(stage.stage_data) if stage.stage_data else {}
    if stage_key in ['open_qualifier', 'oq_stage1', 'oq_stage2', 'ewc_qualifier']:
        reg_map = data.get('regions', {})
    elif stage_key in ['kickoff', 'stage1', 'stage2']:
        reg_map = data.get('regional_results', {})
    else:
        raise ValueError(f"Stage {stage_key} is not a regional stage.")

    if region_slug not in reg_map:
        raise ValueError(f"Region {region_slug} not found in stage {stage_key}")

    reg_data = reg_map[region_slug]
    reg_data['is_confirmed'] = False

    if stage.status == 'completed':
        stage.status = 'in_progress'
        stage.completed_at = None

    stage_order = [
        'open_qualifier', 'kickoff', 'major',
        'oq_stage1', 'stage1', 'ewc_qualifier',
        'master', 'ewc',
        'oq_stage2', 'stage2', 'champion', 'season_summary'
    ]
    if stage_key in stage_order and campaign.current_stage in stage_order:
        if stage_order.index(campaign.current_stage) > stage_order.index(stage_key):
            campaign.current_stage = stage_key

    stage.stage_data = json.dumps(data)
    db.session.commit()
    recalculate_campaign_gpr(campaign.id)

    return {
        'success': True,
        'region': region_slug,
        'stage_key': stage_key,
        'is_confirmed': False,
        'message': f"Đã mở khóa thành công khu vực {region_slug.upper()}."
    }


def unlock_stage_tournament(campaign_id: int, stage_key: str) -> Dict[str, Any]:
    """Explicitly unlock a locked international tournament."""
    campaign = get_campaign(campaign_id)
    if not campaign:
        raise ValueError(f"Campaign {campaign_id} not found")

    stage = get_stage_record(campaign_id, stage_key)
    if not stage:
        raise ValueError(f"Stage {stage_key} not found")

    data = json.loads(stage.stage_data) if stage.stage_data else {}
    res = data.get('result', {}) if 'result' in data else data
    res['is_confirmed'] = False

    if stage.status == 'completed':
        stage.status = 'in_progress'
        stage.completed_at = None

    stage_order = [
        'open_qualifier', 'kickoff', 'major',
        'oq_stage1', 'stage1', 'ewc_qualifier',
        'master', 'ewc',
        'oq_stage2', 'stage2', 'champion', 'season_summary'
    ]
    if stage_key in stage_order and campaign.current_stage in stage_order:
        if stage_order.index(campaign.current_stage) > stage_order.index(stage_key):
            campaign.current_stage = stage_key

    stage.stage_data = json.dumps(data)
    db.session.commit()
    recalculate_campaign_gpr(campaign.id)

    return {
        'success': True,
        'stage_key': stage_key,
        'is_confirmed': False,
        'message': f"Đã mở khóa thành công giải đấu {stage_key.upper()}."
    }

def get_open_qualifier_data(campaign_id: int) -> Optional[Dict[str, Any]]:
    """Retrieve full Open Qualifier data for all regions in a campaign.
    Auto-initializes any uninitialized region with Swiss Round 1 matches in 'pending' status.
    """
    stage = get_stage_record(campaign_id, 'open_qualifier')
    if not stage or not stage.stage_data:
        return None
    try:
        data = json.loads(stage.stage_data)
    except Exception:
        data = {'regions': {}}

    regions = data.get('regions', {})
    if any(r not in regions for r in ['pacific', 'americas', 'emea', 'china']):
        data = init_campaign_open_qualifier(campaign_id)
    campaign = get_campaign(campaign_id)
    if campaign:
        heal_stage_regional_state(campaign, stage, 'open_qualifier', data)
    return data


def _check_and_finalize_oq_regions(campaign: Campaign, stage: CampaignStage, data: Dict[str, Any], auto_confirm: bool = True):
    """Helper to update dynamic ratings and advance campaign if all 4 regions are finished."""
    all_regions = ['pacific', 'americas', 'emea', 'china']
    club_states = {cs.club_id: cs for cs in CampaignClubState.query.filter_by(campaign_id=campaign.id).all()}

    for r_slug in all_regions:
        reg_res = data.get('regions', {}).get(r_slug)
        if reg_res:
            is_done, _ = is_stage_region_actually_completed('open_qualifier', reg_res)
            if is_done and (reg_res.get('status') == 'completed' or reg_res.get('matches_completed')):
                reg_res['matches_completed'] = True
                if auto_confirm:
                    reg_res['is_confirmed'] = True

            if reg_res.get('is_confirmed') and not reg_res.get('ratings_awarded'):
                qual_ids = {t['id'] for t in reg_res.get('qualified_teams', [])}
                for cid in qual_ids:
                    if cid in club_states:
                        club_states[cid].story_rating = min(99, club_states[cid].story_rating + 2)
                for s in reg_res.get('swiss_standings', []):
                    cid = s['club_id']
                    if s['wins'] == 0 and cid in club_states:
                        club_states[cid].story_rating = max(60, club_states[cid].story_rating - 1)
                reg_res['ratings_awarded'] = True

    stage.stage_data = json.dumps(data)

    if auto_confirm and all(data.get('regions', {}).get(r, {}).get('status') == 'completed' for r in all_regions):
        for r in all_regions:
            data.get('regions', {}).get(r, {})['is_confirmed'] = True
        stage.status = 'completed'
        stage.completed_at = datetime.now(timezone.utc)
        record_stage_placements(campaign.id, 'open_qualifier', year=stage.year)
        _advance_campaign_to_next_stage(campaign, 'open_qualifier', data)


def resolve_oq_match(campaign_id: int, region_slug: str, match_id: str,
                     winner_id: Optional[int] = None,
                     maps: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Resolve an Open Qualifier match by manual input or single simulation roll."""
    campaign = get_campaign(campaign_id)
    if not campaign:
        raise ValueError(f"Campaign {campaign_id} not found")

    stage = get_stage_record(campaign_id, 'open_qualifier')
    if not stage:
        raise ValueError("Open Qualifier stage not found")

    data = json.loads(stage.stage_data) if stage.stage_data else {'regions': {}}
    if region_slug not in data.get('regions', {}):
        init_campaign_open_qualifier(campaign_id)
        db.session.refresh(stage)
        data = json.loads(stage.stage_data)

    reg_data = data['regions'][region_slug]
    club_states = CampaignClubState.query.filter_by(campaign_id=campaign_id).all()
    rating_lookup = {cs.club_id: cs.story_rating for cs in club_states}
    form_lookup = {cs.club_id: cs.form_modifier for cs in club_states}

    resolved = resolve_open_qualifier_match(
        reg_data, match_id,
        winner_id=winner_id,
        maps=maps,
        rating_lookup=rating_lookup,
        form_lookup=form_lookup,
    )

    _check_and_finalize_oq_regions(campaign, stage, data)
    db.session.commit()
    return {'match': resolved, 'region_data': reg_data}


def sim_oq_round(campaign_id: int, region_slug: str, auto_confirm: bool = True) -> Dict[str, Any]:
    """Simulate all current playable pending matches in the active round of a region."""
    campaign = get_campaign(campaign_id)
    if not campaign:
        raise ValueError(f"Campaign {campaign_id} not found")

    stage = get_stage_record(campaign_id, 'open_qualifier')
    if not stage:
        raise ValueError("Open Qualifier stage not found")

    data = json.loads(stage.stage_data) if stage.stage_data else {'regions': {}}
    if region_slug not in data.get('regions', {}):
        init_campaign_open_qualifier(campaign_id)
        db.session.refresh(stage)
        data = json.loads(stage.stage_data)

    reg_data = data['regions'][region_slug]
    club_states = CampaignClubState.query.filter_by(campaign_id=campaign_id).all()
    rating_lookup = {cs.club_id: cs.story_rating for cs in club_states}
    form_lookup = {cs.club_id: cs.form_modifier for cs in club_states}

    sim_count = sim_open_qualifier_round(reg_data, rating_lookup=rating_lookup, form_lookup=form_lookup)

    _check_and_finalize_oq_regions(campaign, stage, data, auto_confirm=auto_confirm)
    db.session.commit()
    return {'sim_count': sim_count, 'region_data': reg_data}


def sim_oq_region(campaign_id: int, region_slug: str, auto_confirm: bool = True) -> Dict[str, Any]:
    """Simulate all remaining matches for a single region until completed."""
    campaign = get_campaign(campaign_id)
    if not campaign:
        raise ValueError(f"Campaign {campaign_id} not found")

    stage = get_stage_record(campaign_id, 'open_qualifier')
    if not stage:
        raise ValueError("Open Qualifier stage not found")

    data = json.loads(stage.stage_data) if stage.stage_data else {'regions': {}}
    if region_slug not in data.get('regions', {}):
        init_campaign_open_qualifier(campaign_id)
        db.session.refresh(stage)
        data = json.loads(stage.stage_data)

    reg_data = data['regions'][region_slug]
    club_states = CampaignClubState.query.filter_by(campaign_id=campaign_id).all()
    rating_lookup = {cs.club_id: cs.story_rating for cs in club_states}
    form_lookup = {cs.club_id: cs.form_modifier for cs in club_states}

    sim_open_qualifier_remaining(reg_data, rating_lookup=rating_lookup, form_lookup=form_lookup)

    _check_and_finalize_oq_regions(campaign, stage, data, auto_confirm=auto_confirm)
    db.session.commit()
    return {'region_data': reg_data}


def run_open_qualifier_stage(campaign_id: int, region_slug: Optional[str] = None,
                             auto_confirm: bool = True) -> Dict[str, Any]:
    """Execute Open Qualifier simulation for one region or all regions (backward compatible)."""
    regions_to_run = [region_slug] if region_slug else ['pacific', 'americas', 'emea', 'china']
    results_summary = {}

    for r_slug in regions_to_run:
        res = sim_oq_region(campaign_id, r_slug, auto_confirm=auto_confirm)
        r_data = res['region_data']
        results_summary[r_slug] = {
            'qualified_teams': r_data.get('qualified_teams', []),
            'total_matches': r_data.get('total_matches_count', 43),
        }
    return results_summary


def _get_prev_champions_qualifiers_map(campaign_id: int, year: Optional[int]) -> Dict[str, Dict[int, Dict[str, Any]]]:
    """Retrieve mapping of region_slug -> {club_id: {'champions_seed': int, 'slot_type': str}}
    for the champions stage of year - 1.
    """
    result = {'pacific': {}, 'americas': {}, 'emea': {}, 'china': {}}
    if not year or year <= 2026:
        return result

    clubs_by_id = {c.id: c for c in Club.query.all()}
    prev_champ_stage = CampaignStage.query.filter_by(
        campaign_id=campaign_id, year=year - 1, stage_key='champion'
    ).first()

    if prev_champ_stage and prev_champ_stage.stage_data:
        try:
            champ_data = json.loads(prev_champ_stage.stage_data)
            champ_roster = champ_data.get('roster', [])
            for t in champ_roster:
                cid = t.get('id') or t.get('club_id')
                if not cid:
                    continue
                cid = int(cid)
                reg = t.get('region_slug') or t.get('region')
                if not reg and cid in clubs_by_id and clubs_by_id[cid].region:
                    reg = clubs_by_id[cid].region.slug
                if reg in result:
                    result[reg][cid] = {
                        'champions_seed': t.get('champions_seed') or t.get('regional_seed') or 4,
                        'slot_type': t.get('slot_type', 'Champions Qualifier'),
                    }
        except Exception:
            pass
    return result


def _prepare_kickoff_stage(campaign: Campaign, oq_regions_data: Dict[str, Any]):
    """Assemble 12 Kickoff teams per region (8 Partners + 4 Open Qualifiers)."""
    kickoff_stage = CampaignStage.query.filter_by(
        campaign_id=campaign.id, year=campaign.current_year, stage_key='kickoff'
    ).first()

    kickoff_rosters = {}
    clubs_by_id = {c.id: c for c in Club.query.all()}
    prev_champs_map = _get_prev_champions_qualifiers_map(campaign.id, campaign.current_year)

    for r_slug in ['pacific', 'americas', 'emea', 'china']:
        reg_champs = prev_champs_map.get(r_slug, {})

        # 8 Partner teams
        partner_states = CampaignClubState.query.filter_by(
            campaign_id=campaign.id, is_partner=True
        ).join(Club).join(Region).filter(Region.slug == r_slug).all()

        partner_teams = []
        for cs in partner_states:
            cid = cs.club.id
            is_prev_champ = cid in reg_champs
            champ_info = reg_champs.get(cid, {})
            partner_teams.append({
                'id': cid,
                'name': cs.club.name,
                'short_code': cs.club.short_code,
                'logo_url': cs.club.logo_url or (clubs_by_id.get(cid).logo_url if cid in clubs_by_id else ''),
                'story_rating': cs.story_rating,
                'effective_rating': cs.effective_rating,
                'is_partner': True,
                'entry_source': f"Champions Seed #{champ_info.get('champions_seed')}" if is_prev_champ else 'Partner Direct Entry',
                'prev_champions_qualified': is_prev_champ,
                'prev_champions_seed': champ_info.get('champions_seed') if is_prev_champ else None,
            })

        # 4 Qualified teams from Open Qualifier
        oq_qualifiers = oq_regions_data.get(r_slug, {}).get('qualified_teams', [])
        qual_teams = []
        for idx, t in enumerate(oq_qualifiers):
            cid = t.get('id') or t.get('club_id')
            is_prev_champ = cid in reg_champs
            champ_info = reg_champs.get(cid, {})
            qual_teams.append({
                'id': cid,
                'name': t['name'],
                'short_code': t['short_code'],
                'logo_url': t.get('logo_url') or (clubs_by_id.get(cid).logo_url if cid in clubs_by_id else ''),
                'story_rating': t.get('story_rating', 80),
                'effective_rating': t.get('effective_rating', t.get('story_rating', 80)),
                'is_partner': False,
                'oq_seed': idx + 1,
                'entry_source': f"Open Qualifier Seed #{idx + 1} (Champions Seed #{champ_info.get('champions_seed')})" if is_prev_champ else f'Open Qualifier Seed #{idx + 1}',
                'prev_champions_qualified': is_prev_champ,
                'prev_champions_seed': champ_info.get('champions_seed') if is_prev_champ else None,
            })

        kickoff_rosters[r_slug] = partner_teams + qual_teams

    regional_results = {}
    for r_slug in ['pacific', 'americas', 'emea', 'china']:
        regional_results[r_slug] = init_kickoff_region_state(r_slug, kickoff_rosters[r_slug])

    if not kickoff_stage:
        kickoff_stage = CampaignStage(
            campaign_id=campaign.id,
            year=campaign.current_year,
            stage_key='kickoff',
            stage_name=f'VCT Kickoff {campaign.current_year}',
            status='pending',
            stage_data=json.dumps({'rosters': kickoff_rosters, 'regional_results': regional_results}),
        )
        db.session.add(kickoff_stage)
    else:
        current_data = json.loads(kickoff_stage.stage_data) if kickoff_stage.stage_data else {}
        current_data['rosters'] = kickoff_rosters
        if 'regional_results' not in current_data or not current_data['regional_results']:
            current_data['regional_results'] = regional_results
        kickoff_stage.stage_data = json.dumps(current_data)


# ─────────────────────────────────────────────────────────────────────────────
# VCT Kickoff Stage Execution & Interactive Match Resolving
# ─────────────────────────────────────────────────────────────────────────────

def get_kickoff_data(campaign_id: int, year: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """Retrieve full Kickoff data for all regions in a campaign.
    Ensures that regional_results is initialized with interactive states.
    """
    stage = get_stage_record(campaign_id, 'kickoff', year=year)
    if not stage or not stage.stage_data:
        return None
    data = json.loads(stage.stage_data)

    if 'regional_results' not in data:
        data['regional_results'] = {}

    rosters = data.get('rosters', {})
    updated = False
    for r_slug in ['pacific', 'americas', 'emea', 'china']:
        if r_slug in rosters and (r_slug not in data['regional_results'] or not data['regional_results'][r_slug].get('matches')):
            data['regional_results'][r_slug] = init_kickoff_region_state(r_slug, rosters[r_slug])
            updated = True
        elif r_slug in rosters and r_slug in data['regional_results']:
            # Reseed self-healing for pending/unplayed brackets that lack prev_champions_qualified flags
            reg_res = data['regional_results'][r_slug]
            comp_count = len(reg_res.get('completed_dict', {}))
            if comp_count == 0 and stage.year and stage.year > 2026:
                r_roster = rosters[r_slug]
                has_champ_flag = any('prev_champions_qualified' in t for t in r_roster)
                if not has_champ_flag:
                    prev_champs = _get_prev_champions_qualifiers_map(campaign_id, stage.year).get(r_slug, {})
                    if prev_champs:
                        for t in r_roster:
                            cid = t.get('id') or t.get('club_id')
                            if cid in prev_champs:
                                t['prev_champions_qualified'] = True
                                t['prev_champions_seed'] = prev_champs[cid]['champions_seed']
                            else:
                                t['prev_champions_qualified'] = False
                        data['regional_results'][r_slug] = init_kickoff_region_state(r_slug, r_roster)
                        updated = True

    if updated:
        stage.stage_data = json.dumps(data)
        db.session.commit()

    # Hydrate logo_urls for all teams in rosters, matches, standings, major_qualifiers
    club_logos = {c.id: c.logo_url for c in Club.query.all()}
    def _hydrate_team(t):
        if isinstance(t, dict):
            raw_id = t.get('id') or t.get('club_id')
            if raw_id is not None:
                try:
                    tid = int(raw_id)
                    if tid in club_logos and club_logos[tid]:
                        t['logo_url'] = club_logos[tid]
                except (ValueError, TypeError):
                    pass

    for r_slug, r_roster in rosters.items():
        if isinstance(r_roster, list):
            for t in r_roster:
                _hydrate_team(t)

    for r_slug, reg_d in data.get('regional_results', {}).items():
        if isinstance(reg_d, dict):
            for m in reg_d.get('matches', []):
                if isinstance(m, dict):
                    _hydrate_team(m.get('team_a'))
                    _hydrate_team(m.get('team_b'))
                    _hydrate_team(m.get('winner'))
                    _hydrate_team(m.get('loser'))
            for s in reg_d.get('standings', []):
                if isinstance(s, dict):
                    _hydrate_team(s.get('team'))
            for q in reg_d.get('major_qualifiers', []):
                _hydrate_team(q)
            _hydrate_team(reg_d.get('champion'))
            _hydrate_team(reg_d.get('runner_up'))

    campaign = get_campaign(campaign_id)
    if campaign:
        heal_stage_regional_state(campaign, stage, 'kickoff', data)

    return data


def _check_and_finalize_kickoff_regions(campaign: Campaign, stage: CampaignStage, data: Dict[str, Any], auto_confirm: bool = True):
    """Award CP, story ratings, and advance campaign when all 4 Kickoff regions complete."""
    all_regions = ['pacific', 'americas', 'emea', 'china']
    club_states = {cs.club_id: cs for cs in CampaignClubState.query.filter_by(campaign_id=campaign.id).all()}

    for r_slug in all_regions:
        reg_data = data.get('regional_results', {}).get(r_slug)
        if reg_data:
            is_done, _ = is_stage_region_actually_completed('kickoff', reg_data)
            if is_done and (reg_data.get('status') == 'completed' or reg_data.get('matches_completed')):
                reg_data['matches_completed'] = True
                if auto_confirm:
                    reg_data['is_confirmed'] = True

            if reg_data.get('is_confirmed') and not reg_data.get('rewards_awarded'):
                cp_awards = []
                for s in reg_data.get('standings', []):
                    cp_awards.append({
                        'club_id': s['club_id'],
                        'rank': s['rank'],
                    })
                award_stage_cp(campaign.id, 'kickoff', cp_awards)

                if reg_data.get('major_qualifiers'):
                    c_id = reg_data['major_qualifiers'][0]['id']
                    if c_id in club_states:
                        club_states[c_id].story_rating = min(99, club_states[c_id].story_rating + 2)
                    r_id = reg_data['major_qualifiers'][1]['id']
                    if r_id in club_states:
                        club_states[r_id].story_rating = min(99, club_states[r_id].story_rating + 1)
                reg_data['rewards_awarded'] = True

    stage.stage_data = json.dumps(data)

    if auto_confirm and all(data.get('regional_results', {}).get(r, {}).get('status') == 'completed' for r in all_regions):
        stage.status = 'completed'
        stage.completed_at = datetime.now(timezone.utc)
        record_stage_placements(campaign.id, 'kickoff', year=stage.year)
        _advance_campaign_to_next_stage(campaign, 'kickoff', data)


def resolve_ko_match(campaign_id: int, region_slug: str, match_id: str,
                     winner_id: Optional[int] = None,
                     maps: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Resolve a single Kickoff match by manual input or single simulation roll."""
    campaign = get_campaign(campaign_id)
    if not campaign:
        raise ValueError(f"Campaign {campaign_id} not found")

    stage = get_stage_record(campaign_id, 'kickoff')
    if not stage:
        raise ValueError("Kickoff stage not found")

    data = get_kickoff_data(campaign_id)
    if not data or 'regional_results' not in data or region_slug not in data['regional_results']:
        raise ValueError(f"Kickoff data for {region_slug} not initialized")

    reg_data = data['regional_results'][region_slug]
    club_states = CampaignClubState.query.filter_by(campaign_id=campaign_id).all()
    rating_lookup = {cs.club_id: cs.story_rating for cs in club_states}
    form_lookup = {cs.club_id: cs.form_modifier for cs in club_states}

    resolved = resolve_kickoff_match(
        reg_data, match_id,
        winner_id=winner_id,
        maps=maps,
        rating_lookup=rating_lookup,
        form_lookup=form_lookup,
    )

    _check_and_finalize_kickoff_regions(campaign, stage, data)
    db.session.commit()
    return {'match': resolved, 'region_data': reg_data}


def sim_ko_round(campaign_id: int, region_slug: str, auto_confirm: bool = True) -> Dict[str, Any]:
    """Simulate all currently playable pending matches in the active round/wave."""
    campaign = get_campaign(campaign_id)
    if not campaign:
        raise ValueError(f"Campaign {campaign_id} not found")

    stage = get_stage_record(campaign_id, 'kickoff')
    if not stage:
        raise ValueError("Kickoff stage not found")

    data = get_kickoff_data(campaign_id)
    reg_data = data['regional_results'][region_slug]

    club_states = CampaignClubState.query.filter_by(campaign_id=campaign_id).all()
    rating_lookup = {cs.club_id: cs.story_rating for cs in club_states}
    form_lookup = {cs.club_id: cs.form_modifier for cs in club_states}

    sim_count = sim_kickoff_round(reg_data, rating_lookup=rating_lookup, form_lookup=form_lookup)

    _check_and_finalize_kickoff_regions(campaign, stage, data, auto_confirm=auto_confirm)
    db.session.commit()
    return {'sim_count': sim_count, 'region_data': reg_data}


def sim_ko_region(campaign_id: int, region_slug: str, auto_confirm: bool = True) -> Dict[str, Any]:
    """Simulate all remaining matches for a single Kickoff region until completed."""
    campaign = get_campaign(campaign_id)
    if not campaign:
        raise ValueError(f"Campaign {campaign_id} not found")

    stage = get_stage_record(campaign_id, 'kickoff')
    if not stage:
        raise ValueError("Kickoff stage not found")

    data = get_kickoff_data(campaign_id)
    reg_data = data['regional_results'][region_slug]

    club_states = CampaignClubState.query.filter_by(campaign_id=campaign_id).all()
    rating_lookup = {cs.club_id: cs.story_rating for cs in club_states}
    form_lookup = {cs.club_id: cs.form_modifier for cs in club_states}

    sim_kickoff_remaining(reg_data, rating_lookup=rating_lookup, form_lookup=form_lookup)

    _check_and_finalize_kickoff_regions(campaign, stage, data, auto_confirm=auto_confirm)
    db.session.commit()
    return {'region_data': reg_data}


def run_kickoff_stage(campaign_id: int, region_slug: Optional[str] = None,
                      manual_overrides: Optional[Dict[str, Any]] = None,
                      auto_confirm: bool = True) -> Dict[str, Any]:
    """Execute Kickoff simulation (22 matches per region) for one or all regions."""
    campaign = get_campaign(campaign_id)
    if not campaign:
        raise ValueError(f"Campaign {campaign_id} not found")

    stage = get_stage_record(campaign_id, 'kickoff')
    if not stage:
        raise ValueError("Kickoff stage not initialized yet. Please complete Open Qualifier first.")

    data = get_kickoff_data(campaign_id)
    if 'manual_overrides' not in data:
        data['manual_overrides'] = {}

    regions_to_run = [region_slug] if region_slug else ['pacific', 'americas', 'emea', 'china']
    summary_results = {}

    for r_slug in regions_to_run:
        roster = data.get('rosters', {}).get(r_slug, [])
        if len(roster) != 12:
            raise ValueError(f"Roster for {r_slug} Kickoff does not have 12 teams")

        states = {cs.club_id: cs for cs in CampaignClubState.query.filter_by(campaign_id=campaign_id).all()}
        for t in roster:
            c_id = t['id']
            if c_id in states:
                t['story_rating'] = states[c_id].story_rating
                t['form_modifier'] = states[c_id].form_modifier
                t['effective_rating'] = states[c_id].effective_rating

        rating_lookup = {t['id']: t['story_rating'] for t in roster}
        form_lookup = {t['id']: t['form_modifier'] for t in roster}

        existing_overrides = data['manual_overrides'].get(r_slug, {})
        if manual_overrides and region_slug == r_slug:
            existing_overrides.update(manual_overrides)
        data['manual_overrides'][r_slug] = existing_overrides

        sim_res = simulate_kickoff_tournament(
            r_slug, roster,
            rating_lookup=rating_lookup,
            form_lookup=form_lookup,
            manual_overrides=existing_overrides
        )
        sim_res['matches_completed'] = True
        if auto_confirm:
            sim_res['is_confirmed'] = True
            cp_awards = []
            for s in sim_res['standings']:
                cp_awards.append({
                    'club_id': s['club_id'],
                    'rank': s['rank'],
                })
            award_stage_cp(campaign_id, 'kickoff', cp_awards)
        else:
            sim_res['is_confirmed'] = False

        data['regional_results'][r_slug] = sim_res

        summary_results[r_slug] = {
            'champion': sim_res['standings'][0]['team'],
            'runner_up': sim_res['standings'][1]['team'],
            'major_qualifiers': sim_res['major_qualifiers'],
            'total_matches': sim_res['total_matches_count'],
            'matches_completed': sim_res.get('matches_completed', True),
            'is_confirmed': sim_res.get('is_confirmed', False),
            'matches': sim_res.get('matches'),
            'standings': sim_res.get('standings'),
        }

    stage.stage_data = json.dumps(data)

    all_regions = ['pacific', 'americas', 'emea', 'china']
    if auto_confirm and all(r in data['regional_results'] and data['regional_results'][r].get('status') == 'completed' for r in all_regions):
        for r in all_regions:
            data['regional_results'][r]['is_confirmed'] = True
        stage.status = 'completed'
        stage.completed_at = datetime.now(timezone.utc)
        record_stage_placements(campaign.id, 'kickoff', year=stage.year)
        _advance_campaign_to_next_stage(campaign, 'kickoff', data)

    db.session.commit()
    return summary_results


def override_kickoff_match(campaign_id: int, region_slug: str, round_name: Optional[str] = None,
                           winner_id: int = None, maps: Optional[List[Dict[str, Any]]] = None,
                           match_id: Optional[str] = None, auto_confirm: bool = False) -> Dict[str, Any]:
    """Force a specific winner / map scores for a Kickoff match and re-simulate the bracket."""
    key = round_name or match_id
    if not key:
        raise ValueError("round_name or match_id is required")
    overrides = {
        key: {
            'winner_id': winner_id,
            'maps': maps or [],
        }
    }
    return run_kickoff_stage(campaign_id, region_slug=region_slug, manual_overrides=overrides, auto_confirm=auto_confirm)


def _prepare_major_stage(campaign: Campaign, kickoff_regional_results: Dict[str, Any]):
    """Assemble 8 teams for VCT Major (Masters Bangkok): 2 per region (Seed 1 & Seed 2)."""
    major_stage = CampaignStage.query.filter_by(
        campaign_id=campaign.id, year=campaign.current_year, stage_key='major'
    ).first()

    states = {cs.club_id: cs for cs in CampaignClubState.query.filter_by(campaign_id=campaign.id).all()}

    major_roster = []
    for r_slug in ['pacific', 'americas', 'emea', 'china']:
        reg_res = kickoff_regional_results.get(r_slug, {})
        qualifiers = reg_res.get('major_qualifiers', [])
        if len(qualifiers) >= 2:
            c1_id = qualifiers[0]['id'] if 'id' in qualifiers[0] else qualifiers[0].get('club_id')
            c2_id = qualifiers[1]['id'] if 'id' in qualifiers[1] else qualifiers[1].get('club_id')

            cs1 = states.get(c1_id)
            cs2 = states.get(c2_id)

            major_roster.append({
                'id': c1_id,
                'name': qualifiers[0]['name'],
                'short_code': qualifiers[0]['short_code'],
                'region_slug': r_slug,
                'region': r_slug,
                'regional_seed': 1,
                'title': f'{r_slug.upper()} Kickoff Champion',
                'story_rating': cs1.story_rating if cs1 else qualifiers[0].get('story_rating', 80),
                'form_modifier': cs1.form_modifier if cs1 else 0,
                'effective_rating': cs1.effective_rating if cs1 else 80,
                'logo_url': cs1.club.logo_url if cs1 and cs1.club else qualifiers[0].get('logo_url'),
            })
            major_roster.append({
                'id': c2_id,
                'name': qualifiers[1]['name'],
                'short_code': qualifiers[1]['short_code'],
                'region_slug': r_slug,
                'region': r_slug,
                'regional_seed': 2,
                'title': f'{r_slug.upper()} Kickoff Runner-up',
                'story_rating': cs2.story_rating if cs2 else qualifiers[1].get('story_rating', 80),
                'form_modifier': cs2.form_modifier if cs2 else 0,
                'effective_rating': cs2.effective_rating if cs2 else 80,
                'logo_url': cs2.club.logo_url if cs2 and cs2.club else qualifiers[1].get('logo_url'),
            })

    initial_result = init_major_state(major_roster) if len(major_roster) == 8 else None

    hosts = get_season_hosts(campaign.id, campaign.current_year)
    major_host = hosts.get('major')
    major_city = major_host['city_name'] if major_host else 'Tokyo'
    st_name = f'VCT Major {major_city} {campaign.current_year}'

    if not major_stage:
        major_stage = CampaignStage(
            campaign_id=campaign.id,
            year=campaign.current_year,
            stage_key='major',
            stage_name=st_name,
            status='pending',
            stage_data=json.dumps({'roster': major_roster, 'result': initial_result, 'host_city': major_host}),
        )
        db.session.add(major_stage)
    else:
        m_data = json.loads(major_stage.stage_data) if major_stage.stage_data else {}
        m_data['roster'] = major_roster
        if 'result' not in m_data or not m_data['result']:
            m_data['result'] = initial_result
        if 'host_city' not in m_data or not m_data['host_city']:
            m_data['host_city'] = major_host
        major_stage.stage_name = st_name
        major_stage.stage_data = json.dumps(m_data)


# ─────────────────────────────────────────────────────────────────────────────
# VCT Major (Masters Bangkok) Stage Execution & Interactive Resolving
# ─────────────────────────────────────────────────────────────────────────────

def get_major_data(campaign_id: int, year: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """Retrieve full Major data (roster, matches, standings) for a campaign."""
    stage = get_stage_record(campaign_id, 'major', year=year)
    if not stage or not stage.stage_data:
        return None
    data = json.loads(stage.stage_data)
    roster = data.get('roster', [])

    if roster and len(roster) == 8 and ('result' not in data or not data['result'] or not data['result'].get('swiss_matches')):
        data['result'] = init_major_state(roster)
        stage.stage_data = json.dumps(data)
        db.session.commit()

    if 'host_city' not in data or not data['host_city']:
        hosts = get_season_hosts(campaign_id, stage.year)
        data['host_city'] = hosts.get('major')
        if data['host_city']:
            stage.stage_name = f"VCT Major {data['host_city']['city_name']} {stage.year}"
        stage.stage_data = json.dumps(data)
        db.session.commit()

    campaign = get_campaign(campaign_id)
    if campaign:
        heal_stage_tournament_state(campaign, stage, 'major', data)

    res = data.get('result')
    if res and res.get('playoff_matches'):
        healed_matches = False
        for m in res['playoff_matches']:
            if m.get('round_name') == 'lower_final' and m.get('bo') != 5:
                m['bo'] = 5
                m['label'] = 'Chung kết Nhánh thua (BO5)'
                healed_matches = True
        if healed_matches:
            stage.stage_data = json.dumps(data)
            db.session.commit()

    return data


def _check_and_finalize_major(campaign: Campaign, stage: CampaignStage, data: Dict[str, Any], auto_confirm: bool = True):
    """Award CP, story ratings, and advance campaign when Major completes."""
    res = data.get('result')
    if res and (res.get('status') == 'completed' or res.get('matches_completed')):
        res['matches_completed'] = True
        if auto_confirm:
            res['is_confirmed'] = True

        if res.get('is_confirmed') and not res.get('rewards_awarded'):
            cp_awards = []
            for s in res.get('standings', []):
                cp_awards.append({
                    'club_id': s['club_id'],
                    'rank': s['rank'],
                })
            award_stage_cp(campaign.id, 'major', cp_awards)

            club_states = {cs.club_id: cs for cs in CampaignClubState.query.filter_by(campaign_id=campaign.id).all()}
            if res.get('champion'):
                champ_id = res['champion']['id']
                if champ_id in club_states:
                    club_states[champ_id].story_rating = min(99, club_states[champ_id].story_rating + 3)
            if res.get('runner_up'):
                runner_id = res['runner_up']['id']
                if runner_id in club_states:
                    club_states[runner_id].story_rating = min(99, club_states[runner_id].story_rating + 2)

            res['rewards_awarded'] = True

        if auto_confirm:
            stage.status = 'completed'
            stage.completed_at = datetime.now(timezone.utc)
            record_stage_placements(campaign.id, 'major', year=stage.year)
            _advance_campaign_to_next_stage(campaign, 'major', data)

    stage.stage_data = json.dumps(data)


def resolve_major_match_interactive(campaign_id: int, match_id: str,
                                    winner_id: Optional[int] = None,
                                    maps: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Resolve a single Major match by manual input or single simulation roll."""
    campaign = get_campaign(campaign_id)
    if not campaign:
        raise ValueError(f"Campaign {campaign_id} not found")

    stage = get_stage_record(campaign_id, 'major')
    if not stage:
        raise ValueError("Major stage not found")

    data = get_major_data(campaign_id)
    major_data = data['result']

    resolved = resolve_major_match(major_data, match_id, winner_id=winner_id, maps=maps)

    _check_and_finalize_major(campaign, stage, data)
    db.session.commit()
    return {'match': resolved, 'major_data': major_data}


def sim_major_round_interactive(campaign_id: int, auto_confirm: bool = True) -> Dict[str, Any]:
    """Simulate all currently playable pending matches in the active round/wave of Major."""
    campaign = get_campaign(campaign_id)
    if not campaign:
        raise ValueError(f"Campaign {campaign_id} not found")

    stage = get_stage_record(campaign_id, 'major')
    if not stage:
        raise ValueError("Major stage not found")

    data = get_major_data(campaign_id)
    major_data = data['result']

    sim_count = sim_major_round(major_data)

    _check_and_finalize_major(campaign, stage, data, auto_confirm=auto_confirm)
    db.session.commit()
    return {'sim_count': sim_count, 'major_data': major_data}


def sim_major_tournament_interactive(campaign_id: int, auto_confirm: bool = True) -> Dict[str, Any]:
    """Simulate all remaining matches in VCT Major until Grand Final completes."""
    campaign = get_campaign(campaign_id)
    if not campaign:
        raise ValueError(f"Campaign {campaign_id} not found")

    stage = get_stage_record(campaign_id, 'major')
    if not stage:
        raise ValueError("Major stage not found")

    data = get_major_data(campaign_id)
    major_data = data['result']

    sim_major_remaining(major_data)

    _check_and_finalize_major(campaign, stage, data, auto_confirm=auto_confirm)
    db.session.commit()
    return {'major_data': major_data}


def run_major_stage(campaign_id: int, manual_overrides: Optional[Dict[str, Any]] = None, auto_confirm: bool = True) -> Dict[str, Any]:
    """Execute VCT Major (Masters Bangkok) 8-team international tournament:
    - Swiss Stage (8 teams, 10 matches BO3, 4 qualify, 4 out)
    - Double Elimination Playoffs (4 teams, 6 matches BO3/BO5)
    - Award official VCT 2025 Championship Points (+5, +3, +2, +1)
    - Advance campaign to Stage 1 and prepare Stage 1 rosters.
    """
    campaign = get_campaign(campaign_id)
    if not campaign:
        raise ValueError(f"Campaign {campaign_id} not found")

    stage = get_stage_record(campaign_id, 'major')
    if not stage:
        raise ValueError("Major stage not found. Please complete Kickoff first.")

    data = json.loads(stage.stage_data) if stage.stage_data else {'roster': []}
    roster = data.get('roster', [])
    if len(roster) != 8:
        raise ValueError(f"Major requires 8 teams from Kickoff, found {len(roster)}")

    if 'manual_overrides' not in data:
        data['manual_overrides'] = {}

    prev_result = data.get('result') if manual_overrides else None

    if manual_overrides:
        data['manual_overrides'].update(manual_overrides)
    else:
        data['manual_overrides'] = {}

    # Refresh ratings and form from CampaignClubState
    states = {cs.club_id: cs for cs in CampaignClubState.query.filter_by(campaign_id=campaign_id).all()}
    for t in roster:
        c_id = t['id']
        if c_id in states:
            t['story_rating'] = states[c_id].story_rating
            t['form_modifier'] = states[c_id].form_modifier
            t['effective_rating'] = states[c_id].effective_rating
            if states[c_id].club and states[c_id].club.logo_url:
                t['logo_url'] = states[c_id].club.logo_url

    sim_res = simulate_major_tournament(
        roster,
        manual_overrides=data['manual_overrides'],
        previous_result=prev_result
    )
    sim_res['matches_completed'] = True
    data['result'] = sim_res

    if auto_confirm:
        sim_res['is_confirmed'] = True
        # Award official VCT 2025 Championship Points
        # 1st: 5 CP, 2nd: 3 CP, 3rd: 2 CP, 4th: 1 CP, 5th-8th: 0 CP
        cp_awards = []
        for s in sim_res['standings']:
            cp_awards.append({
                'club_id': s['club_id'],
                'rank': s['rank'],
            })
        award_stage_cp(campaign_id, 'major', cp_awards)

        stage.status = 'completed'
        stage.completed_at = datetime.now(timezone.utc)
        record_stage_placements(campaign_id, 'major', year=stage.year)

        # Advance campaign circuit to Open Qualifier Stage 1
        campaign.current_stage = 'oq_stage1'
        _prepare_oq_stage1_stage(campaign)
    else:
        sim_res['is_confirmed'] = False

    stage.stage_data = json.dumps(data)
    db.session.commit()
    return {
        'champion': sim_res['champion'],
        'runner_up': sim_res['runner_up'],
        'total_matches': sim_res['total_matches_count'],
        'standings': sim_res['standings'],
        'matches_completed': sim_res['matches_completed'],
        'is_confirmed': sim_res['is_confirmed'],
        'matches': sim_res.get('swiss_matches', []) + sim_res.get('playoff_matches', []),
    }


def override_major_match(campaign_id: int, round_name: Optional[str] = None,
                         winner_id: int = None, maps: Optional[List[Dict[str, Any]]] = None,
                         auto_confirm: bool = False, match_id: Optional[str] = None) -> Dict[str, Any]:
    """Force a specific winner / map scores for a Major match and re-simulate the bracket."""
    key = round_name or match_id
    if not key:
        raise ValueError("round_name or match_id is required")
    overrides = {
        key: {
            'winner_id': winner_id,
            'maps': maps or [],
        }
    }
    return run_major_stage(campaign_id, manual_overrides=overrides, auto_confirm=auto_confirm)


def _prepare_oq_stage1_stage(campaign: Campaign):
    """Assemble 16 teams per region for Open Qualifier Stage 1:
    - 4 relegated teams from Kickoff (ranks 9-12)
    - 12 non-Kickoff teams (the 12 teams that did not qualify from Open Qualifier 1)
    - Top 8 from Kickoff stay safe and are stored as 'retained_teams'.
    """
    stage_record = CampaignStage.query.filter_by(
        campaign_id=campaign.id, year=campaign.current_year, stage_key='oq_stage1'
    ).first()

    kickoff_stage = CampaignStage.query.filter_by(
        campaign_id=campaign.id, year=campaign.current_year, stage_key='kickoff'
    ).first()

    states = {cs.club_id: cs for cs in CampaignClubState.query.filter_by(campaign_id=campaign.id).all()}
    k_data = json.loads(kickoff_stage.stage_data) if (kickoff_stage and kickoff_stage.stage_data) else {}
    k_regional = k_data.get('regional_results', {})

    regions_data = {}
    retained_all = {}

    for r_slug in ['pacific', 'americas', 'emea', 'china']:
        reg_k = k_regional.get(r_slug, {})
        standings = reg_k.get('standings', [])

        retained_teams = []
        relegated_teams = []

        if len(standings) >= 12:
            retained_teams = [s['team'] for s in standings[:8]]
            relegated_teams = [s['team'] for s in standings[8:12]]
        else:
            roster = k_data.get('rosters', {}).get(r_slug, [])
            retained_teams = roster[:8]
            relegated_teams = roster[8:12]

        retained_ids = {t.get('id') or t.get('club_id') for t in retained_teams}
        retained_all[r_slug] = retained_teams

        region_obj = Region.query.filter_by(slug=r_slug).first()
        all_clubs = Club.query.filter_by(region_id=region_obj.id, is_active=True).all() if region_obj else []

        relegated_ids = {t.get('id') or t.get('club_id') for t in relegated_teams}
        relegated_clubs = [c for c in all_clubs if c.id in relegated_ids]
        challenger_clubs = [c for c in all_clubs if c.id not in retained_ids and c.id not in relegated_ids]

        # Order: 4 relegated clubs (seeds 1-4) followed by 12 challenger clubs (seeds 5-16)
        sorted_clubs = relegated_clubs + sorted(challenger_clubs, key=lambda c: -c.current_rating)

        participants = []
        for idx, c in enumerate(sorted_clubs):
            cs = states.get(c.id)
            participants.append({
                'id': c.id,
                'name': c.name,
                'short_code': c.short_code,
                'region_slug': r_slug,
                'region': r_slug,
                'is_partner': cs.is_partner if cs else False,
                'story_rating': cs.story_rating if cs else c.current_rating,
                'form_modifier': cs.form_modifier if cs else 0,
                'effective_rating': cs.effective_rating if cs else c.current_rating,
                'logo_url': c.logo_url,
                'seed': idx + 1,
            })

        if len(participants) == 16:
            reg_state = init_open_qualifier_region_state(r_slug, participants)
            regions_data[r_slug] = reg_state

    if not stage_record:
        stage_record = CampaignStage(
            campaign_id=campaign.id,
            year=campaign.current_year,
            stage_key='oq_stage1',
            stage_name=f'Open Qualifier Stage 1 {campaign.current_year}',
            status='pending',
            stage_data=json.dumps({
                'regions': regions_data,
                'retained_teams': retained_all,
            }),
        )
        db.session.add(stage_record)
    else:
        curr_data = json.loads(stage_record.stage_data) if stage_record.stage_data else {}
        curr_data['retained_teams'] = retained_all
        if 'regions' not in curr_data or not curr_data['regions']:
            curr_data['regions'] = regions_data
        stage_record.stage_data = json.dumps(curr_data)


def get_oq_stage1_data(campaign_id: int) -> Optional[Dict[str, Any]]:
    """Retrieve full Open Qualifier Stage 1 data for a campaign."""
    stage = get_stage_record(campaign_id, 'oq_stage1')
    if not stage or not stage.stage_data:
        campaign = get_campaign(campaign_id)
        if campaign:
            _prepare_oq_stage1_stage(campaign)
            db.session.commit()
            stage = get_stage_record(campaign_id, 'oq_stage1')
    if not stage or not stage.stage_data:
        return None
    data = json.loads(stage.stage_data)
    campaign = get_campaign(campaign_id)
    if campaign:
        heal_stage_regional_state(campaign, stage, 'oq_stage1', data)
    return data


def _check_and_finalize_oq_stage1(campaign: Campaign, stage: CampaignStage, data: Dict[str, Any], auto_confirm: bool = True):
    """Update dynamic ratings and advance campaign to Stage 1 when all 4 regions complete."""
    all_regions = ['pacific', 'americas', 'emea', 'china']
    club_states = {cs.club_id: cs for cs in CampaignClubState.query.filter_by(campaign_id=campaign.id).all()}

    for r_slug in all_regions:
        reg_res = data.get('regions', {}).get(r_slug)
        if reg_res:
            is_done, _ = is_stage_region_actually_completed('open_qualifier', reg_res)
            if is_done and (reg_res.get('status') == 'completed' or reg_res.get('matches_completed')):
                reg_res['matches_completed'] = True
                if auto_confirm:
                    reg_res['is_confirmed'] = True

            if reg_res.get('is_confirmed') and not reg_res.get('ratings_awarded'):
                qual_ids = {t['id'] for t in reg_res.get('qualified_teams', [])}
                for cid in qual_ids:
                    if cid in club_states:
                        club_states[cid].story_rating = min(99, club_states[cid].story_rating + 2)
                for s in reg_res.get('swiss_standings', []):
                    cid = s['club_id']
                    if s['wins'] == 0 and cid in club_states:
                        club_states[cid].story_rating = max(60, club_states[cid].story_rating - 1)
                reg_res['ratings_awarded'] = True

    stage.stage_data = json.dumps(data)

    if auto_confirm and all(data.get('regions', {}).get(r, {}).get('status') == 'completed' for r in all_regions):
        for r in all_regions:
            data.get('regions', {}).get(r, {})['is_confirmed'] = True
        stage.status = 'completed'
        stage.completed_at = datetime.now(timezone.utc)
        record_stage_placements(campaign.id, 'oq_stage1', year=stage.year)
        _advance_campaign_to_next_stage(campaign, 'oq_stage1', data)


def resolve_oq_stage1_match(campaign_id: int, region_slug: str, match_id: str,
                            winner_id: Optional[int] = None,
                            maps: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Resolve an Open Qualifier Stage 1 match by manual input or single simulation roll."""
    campaign = get_campaign(campaign_id)
    if not campaign:
        raise ValueError(f"Campaign {campaign_id} not found")

    stage = get_stage_record(campaign_id, 'oq_stage1')
    if not stage:
        raise ValueError("Open Qualifier Stage 1 not found")

    data = get_oq_stage1_data(campaign_id)
    reg_data = data['regions'][region_slug]
    club_states = CampaignClubState.query.filter_by(campaign_id=campaign_id).all()
    rating_lookup = {cs.club_id: cs.story_rating for cs in club_states}
    form_lookup = {cs.club_id: cs.form_modifier for cs in club_states}

    resolved = resolve_open_qualifier_match(
        reg_data, match_id,
        winner_id=winner_id,
        maps=maps,
        rating_lookup=rating_lookup,
        form_lookup=form_lookup,
    )
    _check_and_finalize_oq_stage1(campaign, stage, data)
    db.session.commit()
    return {'match': resolved, 'region_data': reg_data}


def sim_oq_stage1_round(campaign_id: int, region_slug: str, auto_confirm: bool = True) -> Dict[str, Any]:
    """Simulate active round in Open Qualifier Stage 1 for a region."""
    campaign = get_campaign(campaign_id)
    if not campaign:
        raise ValueError(f"Campaign {campaign_id} not found")

    stage = get_stage_record(campaign_id, 'oq_stage1')
    if not stage:
        raise ValueError("Open Qualifier Stage 1 not found")

    data = get_oq_stage1_data(campaign_id)
    reg_data = data['regions'][region_slug]
    club_states = CampaignClubState.query.filter_by(campaign_id=campaign_id).all()
    rating_lookup = {cs.club_id: cs.story_rating for cs in club_states}
    form_lookup = {cs.club_id: cs.form_modifier for cs in club_states}

    sim_count = sim_open_qualifier_round(reg_data, rating_lookup=rating_lookup, form_lookup=form_lookup)
    _check_and_finalize_oq_stage1(campaign, stage, data, auto_confirm=auto_confirm)
    db.session.commit()
    return {'sim_count': sim_count, 'region_data': reg_data}


def sim_oq_stage1_region(campaign_id: int, region_slug: str, auto_confirm: bool = True) -> Dict[str, Any]:
    """Simulate all remaining matches for a single region in Open Qualifier Stage 1."""
    campaign = get_campaign(campaign_id)
    if not campaign:
        raise ValueError(f"Campaign {campaign_id} not found")

    stage = get_stage_record(campaign_id, 'oq_stage1')
    if not stage:
        raise ValueError("Open Qualifier Stage 1 not found")

    data = get_oq_stage1_data(campaign_id)
    reg_data = data['regions'][region_slug]
    club_states = CampaignClubState.query.filter_by(campaign_id=campaign_id).all()
    rating_lookup = {cs.club_id: cs.story_rating for cs in club_states}
    form_lookup = {cs.club_id: cs.form_modifier for cs in club_states}

    sim_open_qualifier_remaining(reg_data, rating_lookup=rating_lookup, form_lookup=form_lookup)
    _check_and_finalize_oq_stage1(campaign, stage, data, auto_confirm=auto_confirm)
    db.session.commit()
    return {'region_data': reg_data}


def sim_oq_stage1_all(campaign_id: int, auto_confirm: bool = True) -> Dict[str, Any]:
    """Simulate all 4 regions in Open Qualifier Stage 1 to completion."""
    campaign = get_campaign(campaign_id)
    if not campaign:
        raise ValueError(f"Campaign {campaign_id} not found")

    stage = get_stage_record(campaign_id, 'oq_stage1')
    if not stage:
        raise ValueError("Open Qualifier Stage 1 not found")

    data = get_oq_stage1_data(campaign_id)
    club_states = CampaignClubState.query.filter_by(campaign_id=campaign_id).all()
    rating_lookup = {cs.club_id: cs.story_rating for cs in club_states}
    form_lookup = {cs.club_id: cs.form_modifier for cs in club_states}

    for r_slug in ['pacific', 'americas', 'emea', 'china']:
        if r_slug in data.get('regions', {}):
            reg_data = data['regions'][r_slug]
            sim_open_qualifier_remaining(reg_data, rating_lookup=rating_lookup, form_lookup=form_lookup)

    _check_and_finalize_oq_stage1(campaign, stage, data, auto_confirm=auto_confirm)
    db.session.commit()
    return {'data': data}


def _prepare_stage1_stage(campaign: Campaign):
    """Assemble 12 teams per region for VCT Stage 1:
    - 8 retained teams from Kickoff (Top 1-8)
    - 4 promoted teams from Open Qualifier Stage 1 (or Kickoff fallback)
    """
    stage1_record = CampaignStage.query.filter_by(
        campaign_id=campaign.id, year=campaign.current_year, stage_key='stage1'
    ).first()

    oq_stage1_rec = CampaignStage.query.filter_by(
        campaign_id=campaign.id, year=campaign.current_year, stage_key='oq_stage1'
    ).first()

    kickoff_stage = CampaignStage.query.filter_by(
        campaign_id=campaign.id, year=campaign.current_year, stage_key='kickoff'
    ).first()

    states = {cs.club_id: cs for cs in CampaignClubState.query.filter_by(campaign_id=campaign.id).all()}
    rosters = {}
    regional_results = {}

    oq_s1_data = json.loads(oq_stage1_rec.stage_data) if (oq_stage1_rec and oq_stage1_rec.stage_data) else {}
    k_data = json.loads(kickoff_stage.stage_data) if (kickoff_stage and kickoff_stage.stage_data) else {}

    for r_slug in ['pacific', 'americas', 'emea', 'china']:
        prepared_roster = []

        # Check if we have OQ Stage 1 results (8 retained + 4 qualified)
        if oq_s1_data and 'retained_teams' in oq_s1_data and r_slug in oq_s1_data['retained_teams']:
            retained = oq_s1_data['retained_teams'].get(r_slug, [])
            reg_oq = oq_s1_data.get('regions', {}).get(r_slug, {})
            promoted = reg_oq.get('qualified_teams', [])

            # 8 retained teams (Kickoff rank 1..8)
            for idx, t in enumerate(retained):
                c_id = t.get('id') or t.get('club_id')
                cs = states.get(c_id)
                prepared_roster.append({
                    'id': c_id,
                    'name': t.get('name'),
                    'short_code': t.get('short_code'),
                    'region_slug': r_slug,
                    'region': r_slug,
                    'kickoff_rank': idx + 1,
                    'story_rating': cs.story_rating if cs else t.get('story_rating', 80),
                    'form_modifier': cs.form_modifier if cs else 0,
                    'effective_rating': cs.effective_rating if cs else 80,
                    'logo_url': (cs.club.logo_url if cs and cs.club else None) or t.get('logo_url'),
                })

            # 4 promoted teams (Kickoff rank 9..12)
            for idx, t in enumerate(promoted):
                c_id = t.get('id') or t.get('club_id')
                cs = states.get(c_id)
                prepared_roster.append({
                    'id': c_id,
                    'name': t.get('name'),
                    'short_code': t.get('short_code'),
                    'region_slug': r_slug,
                    'region': r_slug,
                    'kickoff_rank': 9 + idx,
                    'story_rating': cs.story_rating if cs else t.get('story_rating', 80),
                    'form_modifier': cs.form_modifier if cs else 0,
                    'effective_rating': cs.effective_rating if cs else 80,
                    'logo_url': (cs.club.logo_url if cs and cs.club else None) or t.get('logo_url'),
                })

        # Fallback if oq_stage1 wasn't run (e.g. older campaigns or tests)
        if len(prepared_roster) != 12 and k_data:
            raw_rosters = k_data.get('rosters', {})
            k_regional = k_data.get('regional_results', {})
            reg_roster = raw_rosters.get(r_slug, [])
            reg_standings = k_regional.get(r_slug, {}).get('standings', [])
            rank_map = {s['club_id']: s['rank'] for s in reg_standings if 'club_id' in s}
            prepared_roster = []
            for t in reg_roster:
                c_id = t.get('id') or t.get('club_id')
                cs = states.get(c_id)
                prepared_roster.append({
                    'id': c_id,
                    'name': t.get('name'),
                    'short_code': t.get('short_code'),
                    'region_slug': r_slug,
                    'region': r_slug,
                    'kickoff_rank': rank_map.get(c_id, 12),
                    'story_rating': cs.story_rating if cs else t.get('story_rating', 80),
                    'form_modifier': cs.form_modifier if cs else 0,
                    'effective_rating': cs.effective_rating if cs else 80,
                    'logo_url': (cs.club.logo_url if cs and cs.club else None) or t.get('logo_url'),
                })

        rosters[r_slug] = prepared_roster
        if len(prepared_roster) == 12:
            regional_results[r_slug] = init_stage1_region_state(r_slug, prepared_roster)

    if not stage1_record:
        stage1_record = CampaignStage(
            campaign_id=campaign.id,
            year=campaign.current_year,
            stage_key='stage1',
            stage_name=f'VCT Stage 1 {campaign.current_year}',
            status='pending',
            stage_data=json.dumps({'rosters': rosters, 'regional_results': regional_results}),
        )
        db.session.add(stage1_record)
    else:
        s1_data = json.loads(stage1_record.stage_data) if stage1_record.stage_data else {}
        s1_data['rosters'] = rosters
        if 'regional_results' not in s1_data or not s1_data['regional_results']:
            s1_data['regional_results'] = regional_results
        stage1_record.stage_data = json.dumps(s1_data)


def get_stage1_data(campaign_id: int, year: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """Retrieve full Stage 1 data (rosters, regional_results) for a campaign."""
    stage = get_stage_record(campaign_id, 'stage1', year=year)
    if not stage or not stage.stage_data:
        return None
    data = json.loads(stage.stage_data)
    rosters = data.get('rosters', {})
    reg_results = data.get('regional_results', {})

    dirty = False
    for r_slug in ['pacific', 'americas', 'emea', 'china']:
        if r_slug not in reg_results and r_slug in rosters and len(rosters[r_slug]) == 12:
            reg_results[r_slug] = init_stage1_region_state(r_slug, rosters[r_slug])
            dirty = True

    if dirty:
        data['regional_results'] = reg_results
        stage.stage_data = json.dumps(data)
        db.session.commit()

    campaign = get_campaign(campaign_id)
    if campaign:
        heal_stage_regional_state(campaign, stage, 'stage1', data)

    return data


def _prepare_master_stage(campaign: Campaign, s1_regional_results: Dict[str, Any]):
    """Assemble 12 teams for VCT Masters (Masters Toronto): Top 3 per region from Stage 1."""
    master_stage = CampaignStage.query.filter_by(
        campaign_id=campaign.id, year=campaign.current_year, stage_key='master'
    ).first()

    states = {cs.club_id: cs for cs in CampaignClubState.query.filter_by(campaign_id=campaign.id).all()}
    master_roster = []

    for r_slug in ['pacific', 'americas', 'emea', 'china']:
        reg_res = s1_regional_results.get(r_slug, {})
        qualifiers = reg_res.get('masters_qualifiers', [])
        for q in qualifiers:
            t = q.get('team', {})
            c_id = t.get('id') or t.get('club_id')
            cs = states.get(c_id)
            master_roster.append({
                'id': c_id,
                'name': t.get('name'),
                'short_code': t.get('short_code'),
                'region_slug': r_slug,
                'region': r_slug,
                'regional_seed': q.get('regional_seed', 1),
                'title': q.get('title'),
                'story_rating': cs.story_rating if cs else t.get('story_rating', 80),
                'form_modifier': cs.form_modifier if cs else 0,
                'effective_rating': cs.effective_rating if cs else 80,
                'logo_url': cs.club.logo_url if cs and cs.club else t.get('logo_url'),
            })

    init_state = init_master_state(master_roster) if len(master_roster) == 12 else None

    hosts = get_season_hosts(campaign.id, campaign.current_year)
    master_host = hosts.get('master')
    master_city = master_host['city_name'] if master_host else 'Madrid'
    st_name = f'VCT Masters {master_city} {campaign.current_year}'

    if not master_stage:
        master_stage = CampaignStage(
            campaign_id=campaign.id,
            year=campaign.current_year,
            stage_key='master',
            stage_name=st_name,
            status='pending',
            stage_data=json.dumps({'roster': master_roster, 'result': init_state, 'host_city': master_host} if init_state else {'roster': master_roster, 'host_city': master_host}),
        )
        db.session.add(master_stage)
    else:
        m_data = json.loads(master_stage.stage_data) if master_stage.stage_data else {}
        m_data['roster'] = master_roster
        if 'host_city' not in m_data or not m_data['host_city']:
            m_data['host_city'] = master_host
        master_stage.stage_name = st_name
        master_stage.stage_data = json.dumps(m_data)


def _prepare_ewc_stage(campaign: Campaign, s1_regional_results: Dict[str, Any]):
    """Assemble 16 teams for EWC (Esports World Cup): Top 4 per region from Stage 1."""
    ewc_stage = CampaignStage.query.filter_by(
        campaign_id=campaign.id, year=campaign.current_year, stage_key='ewc'
    ).first()

    states = {cs.club_id: cs for cs in CampaignClubState.query.filter_by(campaign_id=campaign.id).all()}
    ewc_roster = []

    for r_slug in ['pacific', 'americas', 'emea', 'china']:
        reg_res = s1_regional_results.get(r_slug, {})
        qualifiers = reg_res.get('ewc_qualifiers', [])
        for q in qualifiers:
            t = q.get('team', {})
            c_id = t.get('id') or t.get('club_id')
            cs = states.get(c_id)
            ewc_roster.append({
                'id': c_id,
                'name': t.get('name'),
                'short_code': t.get('short_code'),
                'region_slug': r_slug,
                'region': r_slug,
                'regional_seed': q.get('pool', 1),
                'pool': q.get('pool', 1),
                'title': q.get('title'),
                'story_rating': cs.story_rating if cs else t.get('story_rating', 80),
                'form_modifier': cs.form_modifier if cs else 0,
                'effective_rating': cs.effective_rating if cs else 80,
                'logo_url': cs.club.logo_url if cs and cs.club else t.get('logo_url'),
            })

    init_state = init_ewc_state(ewc_roster) if len(ewc_roster) == 16 else None

    hosts = get_season_hosts(campaign.id, campaign.current_year)
    ewc_host = hosts.get('ewc')
    ewc_city = ewc_host['city_name'] if ewc_host else 'Riyadh'
    st_name = f'Esports World Cup {ewc_city} {campaign.current_year}'

    if not ewc_stage:
        ewc_stage = CampaignStage(
            campaign_id=campaign.id,
            year=campaign.current_year,
            stage_key='ewc',
            stage_name=st_name,
            status='pending',
            stage_data=json.dumps({'roster': ewc_roster, 'result': init_state, 'host_city': ewc_host} if init_state else {'roster': ewc_roster, 'host_city': ewc_host}),
        )
        db.session.add(ewc_stage)
    else:
        e_data = json.loads(ewc_stage.stage_data) if ewc_stage.stage_data else {}
        e_data['roster'] = ewc_roster
        if 'host_city' not in e_data or not e_data['host_city']:
            e_data['host_city'] = ewc_host
        ewc_stage.stage_name = st_name
        ewc_stage.stage_data = json.dumps(e_data)


def _check_and_finalize_stage1(campaign: Campaign, stage: CampaignStage, data: Dict[str, Any], auto_confirm: bool = True):
    all_regions = ['pacific', 'americas', 'emea', 'china']
    club_states = {cs.club_id: cs for cs in CampaignClubState.query.filter_by(campaign_id=campaign.id).all()}

    for r_slug, reg_data in data.get('regional_results', {}).items():
        if (reg_data.get('status') == 'completed' or reg_data.get('matches_completed')):
            reg_data['matches_completed'] = True
            if auto_confirm:
                reg_data['is_confirmed'] = True

            if reg_data.get('is_confirmed') and not reg_data.get('rewards_awarded'):
                # 1. Award regular season CP (+1 CP per win)
                reg_awards = []
                for s in reg_data.get('alpha_standings', []) + reg_data.get('omega_standings', []):
                    reg_awards.append({
                        'club_id': s['club_id'],
                        'regular_wins': s['wins'],
                        'map_diff': s['map_diff'],
                        'round_diff': s['round_diff'],
                    })
                award_stage_cp(campaign.id, 'stage1_regular', reg_awards)

                # 2. Award playoff CP (1st: 5, 2nd: 3, 3rd: 2, 4th: 1)
                playoff_awards = []
                for s in reg_data.get('standings', []):
                    playoff_awards.append({
                        'club_id': s['club_id'],
                        'rank': s['rank'],
                    })
                award_stage_cp(campaign.id, 'stage1_playoffs', playoff_awards)

                # 3. Rating boosts
                champ = reg_data.get('champion')
                runner = reg_data.get('runner_up')
                third = reg_data.get('third_place')
                if champ:
                    c_id = champ.get('id') or champ.get('club_id')
                    if c_id in club_states:
                        club_states[c_id].story_rating = min(99, club_states[c_id].story_rating + 3)
                if runner:
                    r_id = runner.get('id') or runner.get('club_id')
                    if r_id in club_states:
                        club_states[r_id].story_rating = min(99, club_states[r_id].story_rating + 2)
                if third:
                    t_id = third.get('id') or third.get('club_id')
                    if t_id in club_states:
                        club_states[t_id].story_rating = min(99, club_states[t_id].story_rating + 1)

                reg_data['rewards_awarded'] = True

    stage.stage_data = json.dumps(data)

    if auto_confirm and all(data.get('regional_results', {}).get(r, {}).get('status') == 'completed' for r in all_regions):
        for r in all_regions:
            data.get('regional_results', {}).get(r, {})['is_confirmed'] = True
        stage.status = 'completed'
        stage.completed_at = datetime.now(timezone.utc)
        record_stage_placements(campaign.id, 'stage1', year=stage.year)
        _advance_campaign_to_next_stage(campaign, 'stage1', data)


def resolve_stage1_match_interactive(campaign_id: int, region_slug: str, match_id: str,
                                     winner_id: Optional[int] = None,
                                     maps: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Resolve a single Stage 1 match by manual input or single simulation roll."""
    campaign = get_campaign(campaign_id)
    if not campaign:
        raise ValueError(f"Campaign {campaign_id} not found")

    stage = get_stage_record(campaign_id, 'stage1')
    if not stage:
        raise ValueError("Stage 1 not found")

    data = get_stage1_data(campaign_id)
    reg_data = data['regional_results'][region_slug]

    club_states = CampaignClubState.query.filter_by(campaign_id=campaign_id).all()
    rating_lookup = {cs.club_id: cs.story_rating for cs in club_states}
    form_lookup = {cs.club_id: cs.form_modifier for cs in club_states}

    resolved = resolve_stage1_match(
        reg_data, match_id,
        winner_id=winner_id,
        maps=maps,
        rating_lookup=rating_lookup,
        form_lookup=form_lookup,
    )

    _check_and_finalize_stage1(campaign, stage, data)
    db.session.commit()
    return {'match': resolved, 'region_data': reg_data}


def sim_stage1_round_interactive(campaign_id: int, region_slug: str, auto_confirm: bool = True) -> Dict[str, Any]:
    """Simulate all currently playable pending matches in the active week/wave."""
    campaign = get_campaign(campaign_id)
    if not campaign:
        raise ValueError(f"Campaign {campaign_id} not found")

    stage = get_stage_record(campaign_id, 'stage1')
    if not stage:
        raise ValueError("Stage 1 not found")

    data = get_stage1_data(campaign_id)
    reg_data = data['regional_results'][region_slug]

    club_states = CampaignClubState.query.filter_by(campaign_id=campaign_id).all()
    rating_lookup = {cs.club_id: cs.story_rating for cs in club_states}
    form_lookup = {cs.club_id: cs.form_modifier for cs in club_states}

    sim_count = sim_stage1_round(reg_data, rating_lookup=rating_lookup, form_lookup=form_lookup)

    _check_and_finalize_stage1(campaign, stage, data, auto_confirm=auto_confirm)
    db.session.commit()
    return {'sim_count': sim_count, 'region_data': reg_data}


def sim_stage1_region_interactive(campaign_id: int, region_slug: str, auto_confirm: bool = True) -> Dict[str, Any]:
    """Simulate all remaining matches for a single region in Stage 1."""
    campaign = get_campaign(campaign_id)
    if not campaign:
        raise ValueError(f"Campaign {campaign_id} not found")

    stage = get_stage_record(campaign_id, 'stage1')
    if not stage:
        raise ValueError("Stage 1 not found")

    data = get_stage1_data(campaign_id)
    reg_data = data['regional_results'][region_slug]

    club_states = CampaignClubState.query.filter_by(campaign_id=campaign_id).all()
    rating_lookup = {cs.club_id: cs.story_rating for cs in club_states}
    form_lookup = {cs.club_id: cs.form_modifier for cs in club_states}

    sim_count = sim_stage1_remaining(reg_data, rating_lookup=rating_lookup, form_lookup=form_lookup)

    _check_and_finalize_stage1(campaign, stage, data, auto_confirm=auto_confirm)
    db.session.commit()
    return {'sim_count': sim_count, 'region_data': reg_data}


def sim_stage1_all_interactive(campaign_id: int, auto_confirm: bool = True) -> Dict[str, Any]:
    """Simulate all remaining matches for all 4 regions in Stage 1."""
    campaign = get_campaign(campaign_id)
    if not campaign:
        raise ValueError(f"Campaign {campaign_id} not found")

    stage = get_stage_record(campaign_id, 'stage1')
    if not stage:
        raise ValueError("Stage 1 not found")

    data = get_stage1_data(campaign_id)
    club_states = CampaignClubState.query.filter_by(campaign_id=campaign_id).all()
    rating_lookup = {cs.club_id: cs.story_rating for cs in club_states}
    form_lookup = {cs.club_id: cs.form_modifier for cs in club_states}

    total_sim = 0
    for r_slug in ['pacific', 'americas', 'emea', 'china']:
        if r_slug in data.get('regional_results', {}):
            reg_data = data['regional_results'][r_slug]
            total_sim += sim_stage1_remaining(reg_data, rating_lookup=rating_lookup, form_lookup=form_lookup)

    _check_and_finalize_stage1(campaign, stage, data, auto_confirm=auto_confirm)
    db.session.commit()
    return {'total_sim': total_sim, 'stage1_data': data}


# ─────────────────────────────────────────────────────────────────────────────
# EWC Regional Qualifier (Open Regional Qualifier) Implementation
# ─────────────────────────────────────────────────────────────────────────────

def _prepare_ewc_qualifier_stage(campaign: Campaign, s1_regional_results: Dict[str, Any]):
    stage_record = CampaignStage.query.filter_by(
        campaign_id=campaign.id, year=campaign.current_year, stage_key='ewc_qualifier'
    ).first()

    regions_data = {}
    direct_ewc_qualifiers = {}
    states = {cs.club_id: cs for cs in CampaignClubState.query.filter_by(campaign_id=campaign.id).all()}

    for r_slug in ['pacific', 'americas', 'emea', 'china']:
        reg_res = s1_regional_results.get(r_slug, {})
        region_obj = Region.query.filter_by(slug=r_slug).first()
        all_clubs = Club.query.filter_by(region_id=region_obj.id, is_active=True).all() if region_obj else []

        direct_ewc_qualifiers[r_slug] = reg_res.get('ewc_direct_qualifiers', [])
        p2_direct_teams = reg_res.get('ewc_phase2_teams', [])
        p1_s1_teams = reg_res.get('ewc_phase1_teams', [])

        s1_club_ids = {s['club_id'] for s in reg_res.get('standings', [])}
        challenger_clubs = [c for c in all_clubs if c.id not in s1_club_ids]
        sorted_challengers = sorted(challenger_clubs, key=lambda c: -c.current_rating)

        p1_challenger_teams = []
        for c in sorted_challengers:
            cs = states.get(c.id)
            p1_challenger_teams.append({
                'id': c.id,
                'name': c.name,
                'short_code': c.short_code,
                'region_slug': r_slug,
                'region': r_slug,
                'is_partner': cs.is_partner if cs else False,
                'story_rating': cs.story_rating if cs else c.current_rating,
                'form_modifier': cs.form_modifier if cs else 0,
                'effective_rating': cs.effective_rating if cs else c.current_rating,
                'logo_url': c.logo_url,
            })

        all_p1_teams = p1_s1_teams + p1_challenger_teams
        if len(all_p1_teams) == 16 and len(p2_direct_teams) == 6:
            reg_state = init_ewc_qualifier_region_state(r_slug, all_p1_teams, p2_direct_teams)
            regions_data[r_slug] = reg_state

    init_payload = {
        'direct_ewc_qualifiers': direct_ewc_qualifiers,
        'regions': regions_data,
    }

    if not stage_record:
        stage_record = CampaignStage(
            campaign_id=campaign.id,
            year=campaign.current_year,
            stage_key='ewc_qualifier',
            stage_name=f'EWC Regional Qualifier {campaign.current_year}',
            status='pending',
            stage_data=json.dumps(init_payload),
        )
        db.session.add(stage_record)
    else:
        stage_record.stage_data = json.dumps(init_payload)
        stage_record.status = 'pending'


def get_ewc_qualifier_data(campaign_id: int, year: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """Retrieve or auto-initialize EWC Qualifier stage data."""
    stage = get_stage_record(campaign_id, 'ewc_qualifier', year=year)
    if not stage or not stage.stage_data:
        campaign = get_campaign(campaign_id)
        if campaign:
            s1_data = get_stage1_data(campaign_id, year=year)
            if s1_data and s1_data.get('regional_results'):
                _prepare_ewc_qualifier_stage(campaign, s1_data.get('regional_results', {}))
                stage = get_stage_record(campaign_id, 'ewc_qualifier', year=year)
    if not stage or not stage.stage_data:
        return None
    data = json.loads(stage.stage_data)
    campaign = get_campaign(campaign_id)
    if campaign:
        heal_stage_regional_state(campaign, stage, 'ewc_qualifier', data)
        # Self-heal / state recovery: if all 28 matches are completed for a region, ensure status and matches_completed reflect this
        updated = False
        for r_slug, reg_data in data.get('regions', {}).items():
            for m in reg_data.get('phase2_matches', []):
                if m.get('round_name') in ('p2_lb_f', 'p2_gf') and m.get('bo') != 3:
                    m['bo'] = 3
                    if m.get('status') == 'completed':
                        sc_a = m.get('team_a_score', 0)
                        sc_b = m.get('team_b_score', 0)
                        if sc_a > sc_b:
                            m['team_a_score'] = 2
                            m['team_b_score'] = 1 if sc_b >= 1 else 0
                        elif sc_b > sc_a:
                            m['team_b_score'] = 2
                            m['team_a_score'] = 1 if sc_a >= 1 else 0
                        if len(m.get('maps', [])) > 3:
                            m['maps'] = m['maps'][:3]
                    updated = True

            is_done, _ = is_stage_region_actually_completed('ewc_qualifier', reg_data)
            if is_done:
                if not reg_data.get('matches_completed') or reg_data.get('status') != 'completed':
                    reg_data['matches_completed'] = True
                    reg_data['status'] = 'completed'
                    updated = True
        if updated:
            stage.stage_data = json.dumps(data)
            db.session.commit()
    return data


def _finalize_ewc_roster(campaign: Campaign, stage1_record: CampaignStage, ewc_qual_data: Dict[str, Any]):
    states = {cs.club_id: cs for cs in CampaignClubState.query.filter_by(campaign_id=campaign.id).all()}
    s1_data = json.loads(stage1_record.stage_data) if stage1_record and stage1_record.stage_data else {}
    s1_results = s1_data.get('regional_results', {})

    ewc_roster = []
    for r_slug in ['pacific', 'americas', 'emea', 'china']:
        reg_s1 = s1_results.get(r_slug, {})
        reg_eq = ewc_qual_data.get('regions', {}).get(r_slug, {})

        champ_s1 = reg_s1.get('champion')
        runner_s1 = reg_s1.get('runner_up')
        champ_eq = reg_eq.get('champion')
        runner_eq = reg_eq.get('runner_up')

        qualified_slots = [
            (champ_s1, 1, f"{r_slug.upper()} Stage 1 Champion"),
            (runner_s1, 2, f"{r_slug.upper()} Stage 1 Runner-up"),
            (champ_eq, 3, f"{r_slug.upper()} EWC Qualifier Champion"),
            (runner_eq, 4, f"{r_slug.upper()} EWC Qualifier Runner-up"),
        ]

        for team_obj, pool_num, title in qualified_slots:
            if team_obj:
                c_id = team_obj.get('id') or team_obj.get('club_id')
                cs = states.get(c_id)
                ewc_roster.append({
                    'id': c_id,
                    'name': team_obj.get('name'),
                    'short_code': team_obj.get('short_code'),
                    'region_slug': r_slug,
                    'region': r_slug,
                    'regional_seed': pool_num,
                    'pool': pool_num,
                    'title': title,
                    'story_rating': cs.story_rating if cs else team_obj.get('story_rating', 80),
                    'form_modifier': cs.form_modifier if cs else 0,
                    'effective_rating': cs.effective_rating if cs else 80,
                    'logo_url': cs.club.logo_url if cs and cs.club else team_obj.get('logo_url'),
                })

    ewc_stage = CampaignStage.query.filter_by(
        campaign_id=campaign.id, year=campaign.current_year, stage_key='ewc'
    ).first()

    init_state = init_ewc_state(ewc_roster) if len(ewc_roster) == 16 else None

    hosts = get_season_hosts(campaign.id, campaign.current_year)
    ewc_host = hosts.get('ewc')
    ewc_city = ewc_host['city_name'] if ewc_host else 'Riyadh'
    st_name = f'Esports World Cup {ewc_city} {campaign.current_year}'

    if not ewc_stage:
        ewc_stage = CampaignStage(
            campaign_id=campaign.id,
            year=campaign.current_year,
            stage_key='ewc',
            stage_name=st_name,
            status='pending',
            stage_data=json.dumps({'roster': ewc_roster, 'result': init_state, 'host_city': ewc_host} if init_state else {'roster': ewc_roster, 'host_city': ewc_host}),
        )
        db.session.add(ewc_stage)
    else:
        e_data = json.loads(ewc_stage.stage_data) if ewc_stage.stage_data else {}
        e_data['roster'] = ewc_roster
        if 'host_city' not in e_data or not e_data['host_city']:
            e_data['host_city'] = ewc_host
        ewc_stage.stage_name = st_name
        ewc_stage.stage_data = json.dumps(e_data)


def _check_and_finalize_ewc_qualifier(campaign: Campaign, stage: CampaignStage, data: Dict[str, Any], auto_confirm: bool = True):
    all_regions = ['pacific', 'americas', 'emea', 'china']
    club_states = {cs.club_id: cs for cs in CampaignClubState.query.filter_by(campaign_id=campaign.id).all()}

    for r_slug, reg_data in data.get('regions', {}).items():
        is_done, _ = is_stage_region_actually_completed('ewc_qualifier', reg_data)
        if is_done and (reg_data.get('status') == 'completed' or reg_data.get('matches_completed')):
            reg_data['matches_completed'] = True
            reg_data['status'] = 'completed'
            if auto_confirm:
                reg_data['is_confirmed'] = True

            if reg_data.get('is_confirmed') and not reg_data.get('rewards_awarded'):
                champ = reg_data.get('champion')
                runner = reg_data.get('runner_up')
                if champ:
                    c_id = champ.get('id') or champ.get('club_id')
                    if c_id in club_states:
                        club_states[c_id].story_rating = min(99, club_states[c_id].story_rating + 3)
                if runner:
                    r_id = runner.get('id') or runner.get('club_id')
                    if r_id in club_states:
                        club_states[r_id].story_rating = min(99, club_states[r_id].story_rating + 2)
                reg_data['rewards_awarded'] = True

    stage.stage_data = json.dumps(data)

    if auto_confirm and all(data.get('regions', {}).get(r, {}).get('status') == 'completed' for r in all_regions):
        for r in all_regions:
            data.get('regions', {}).get(r, {})['is_confirmed'] = True
        stage.status = 'completed'
        stage.completed_at = datetime.now(timezone.utc)
        record_stage_placements(campaign.id, 'ewc_qualifier', year=stage.year)
        _advance_campaign_to_next_stage(campaign, 'ewc_qualifier', data)


def resolve_ewc_qualifier_match_interactive(campaign_id: int, region_slug: str, match_id: str,
                                            winner_id: Optional[int] = None,
                                            maps: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Resolve a single match in EWC Regional Qualifier (Phase 1 or Phase 2)."""
    campaign = get_campaign(campaign_id)
    if not campaign:
        raise ValueError(f"Campaign {campaign_id} not found")

    stage = get_stage_record(campaign_id, 'ewc_qualifier')
    if not stage:
        raise ValueError("EWC Qualifier stage not found")

    data = get_ewc_qualifier_data(campaign_id)
    reg_data = data['regions'][region_slug]

    club_states = CampaignClubState.query.filter_by(campaign_id=campaign_id).all()
    rating_lookup = {cs.club_id: cs.story_rating for cs in club_states}
    form_lookup = {cs.club_id: cs.form_modifier for cs in club_states}

    resolved = resolve_ewc_qualifier_match(
        reg_data, match_id,
        winner_id=winner_id,
        maps=maps,
        rating_lookup=rating_lookup,
        form_lookup=form_lookup,
    )

    _check_and_finalize_ewc_qualifier(campaign, stage, data)
    db.session.commit()
    return {'match': resolved, 'region_data': reg_data}


def sim_ewc_qualifier_round_interactive(campaign_id: int, region_slug: str, auto_confirm: bool = True) -> Dict[str, Any]:
    """Simulate currently playable round for the region."""
    campaign = get_campaign(campaign_id)
    if not campaign:
        raise ValueError(f"Campaign {campaign_id} not found")

    stage = get_stage_record(campaign_id, 'ewc_qualifier')
    if not stage:
        raise ValueError("EWC Qualifier stage not found")

    data = get_ewc_qualifier_data(campaign_id)
    reg_data = data['regions'][region_slug]

    club_states = CampaignClubState.query.filter_by(campaign_id=campaign_id).all()
    rating_lookup = {cs.club_id: cs.story_rating for cs in club_states}
    form_lookup = {cs.club_id: cs.form_modifier for cs in club_states}

    resolved_matches = sim_ewc_qualifier_round(reg_data, rating_lookup=rating_lookup, form_lookup=form_lookup)

    _check_and_finalize_ewc_qualifier(campaign, stage, data, auto_confirm=auto_confirm)
    db.session.commit()
    return {'resolved_count': len(resolved_matches), 'region_data': reg_data}


def sim_ewc_qualifier_region_interactive(campaign_id: int, region_slug: str, auto_confirm: bool = True) -> Dict[str, Any]:
    """Simulate all remaining matches in one region until finished."""
    campaign = get_campaign(campaign_id)
    if not campaign:
        raise ValueError(f"Campaign {campaign_id} not found")

    stage = get_stage_record(campaign_id, 'ewc_qualifier')
    if not stage:
        raise ValueError("EWC Qualifier stage not found")

    data = get_ewc_qualifier_data(campaign_id)
    reg_data = data['regions'][region_slug]

    club_states = CampaignClubState.query.filter_by(campaign_id=campaign_id).all()
    rating_lookup = {cs.club_id: cs.story_rating for cs in club_states}
    form_lookup = {cs.club_id: cs.form_modifier for cs in club_states}

    count = sim_ewc_qualifier_remaining(reg_data, rating_lookup=rating_lookup, form_lookup=form_lookup)

    _check_and_finalize_ewc_qualifier(campaign, stage, data, auto_confirm=auto_confirm)
    db.session.commit()
    return {'simulated_count': count, 'region_data': reg_data}


def sim_ewc_qualifier_all_interactive(campaign_id: int, auto_confirm: bool = True) -> Dict[str, Any]:
    """Simulate all remaining matches across all 4 regions in EWC Qualifier."""
    campaign = get_campaign(campaign_id)
    if not campaign:
        raise ValueError(f"Campaign {campaign_id} not found")

    stage = get_stage_record(campaign_id, 'ewc_qualifier')
    if not stage:
        raise ValueError("EWC Qualifier stage not found")

    data = get_ewc_qualifier_data(campaign_id)
    club_states = CampaignClubState.query.filter_by(campaign_id=campaign_id).all()
    rating_lookup = {cs.club_id: cs.story_rating for cs in club_states}
    form_lookup = {cs.club_id: cs.form_modifier for cs in club_states}

    total_sim = 0
    for r_slug in ['pacific', 'americas', 'emea', 'china']:
        if r_slug in data.get('regions', {}):
            reg_data = data['regions'][r_slug]
            total_sim += sim_ewc_qualifier_remaining(reg_data, rating_lookup=rating_lookup, form_lookup=form_lookup)

    _check_and_finalize_ewc_qualifier(campaign, stage, data, auto_confirm=auto_confirm)
    db.session.commit()
    return {'total_sim': total_sim, 'ewc_qualifier_data': data}


def run_ewc_qualifier_stage(campaign_id: int) -> CampaignStage:
    """Convenience full runner for EWC Qualifier stage."""
    sim_ewc_qualifier_all_interactive(campaign_id)
    return get_stage_record(campaign_id, 'ewc_qualifier')


# ─────────────────────────────────────────────────────────────────────────────
# VCT Masters (Masters Toronto) Stage Execution & Interactive Resolving
# ─────────────────────────────────────────────────────────────────────────────

def get_master_data(campaign_id: int, year: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """Retrieve full Masters Toronto data (roster, matches, standings) for a campaign."""
    stage = get_stage_record(campaign_id, 'master', year=year)
    if not stage or not stage.stage_data:
        return None
    data = json.loads(stage.stage_data)
    roster = data.get('roster', [])

    if roster and len(roster) == 12 and ('result' not in data or not data['result'] or not data['result'].get('swiss_matches')):
        data['result'] = init_master_state(roster)
        stage.stage_data = json.dumps(data)
        db.session.commit()

    if 'host_city' not in data or not data['host_city']:
        hosts = get_season_hosts(campaign_id, stage.year)
        data['host_city'] = hosts.get('master')
        if data['host_city']:
            stage.stage_name = f"VCT Masters {data['host_city']['city_name']} {stage.year}"
        stage.stage_data = json.dumps(data)
        db.session.commit()

    campaign = get_campaign(campaign_id)
    if campaign:
        heal_stage_tournament_state(campaign, stage, 'master', data)

    return data


def _check_and_finalize_master(campaign: Campaign, stage: CampaignStage, data: Dict[str, Any], auto_confirm: bool = True):
    """Award CP, story ratings, and advance campaign when Masters Toronto completes."""
    res = data.get('result')
    if res and (res.get('status') == 'completed' or res.get('matches_completed')):
        res['matches_completed'] = True
        if auto_confirm:
            res['is_confirmed'] = True

        if res.get('is_confirmed') and not res.get('rewards_awarded'):
            cp_awards = []
            for s in res.get('standings', []):
                cid = s.get('club_id') or (s.get('team', {}).get('id') if isinstance(s.get('team'), dict) else None)
                if cid:
                    cp_awards.append({
                        'club_id': cid,
                        'rank': s['rank'],
                    })
            award_stage_cp(campaign.id, 'master', cp_awards)

            club_states = {cs.club_id: cs for cs in CampaignClubState.query.filter_by(campaign_id=campaign.id).all()}
            if res.get('champion'):
                champ = res['champion']
                champ_id = champ.get('id') if isinstance(champ, dict) else champ
                if champ_id in club_states:
                    club_states[champ_id].story_rating = min(99, club_states[champ_id].story_rating + 5)
            if res.get('runner_up'):
                runner = res['runner_up']
                runner_id = runner.get('id') if isinstance(runner, dict) else runner
                if runner_id in club_states:
                    club_states[runner_id].story_rating = min(99, club_states[runner_id].story_rating + 3)
            for s in res.get('standings', []):
                cid = s.get('club_id') or (s.get('team', {}).get('id') if isinstance(s.get('team'), dict) else None)
                if cid and cid in club_states:
                    if s.get('rank') == 3:
                        club_states[cid].story_rating = min(99, club_states[cid].story_rating + 2)
                    elif s.get('rank') == 4:
                        club_states[cid].story_rating = min(99, club_states[cid].story_rating + 1)

            res['rewards_awarded'] = True

        if auto_confirm:
            stage.status = 'completed'
            stage.completed_at = datetime.now(timezone.utc)
            record_stage_placements(campaign.id, 'master', year=stage.year)
            _advance_campaign_to_next_stage(campaign, 'master', data)

    stage.stage_data = json.dumps(data)


def resolve_master_match_interactive(campaign_id: int, match_id: str,
                                     winner_id: Optional[int] = None,
                                     maps: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Resolve a single Masters Toronto match by manual input or single simulation roll."""
    campaign = get_campaign(campaign_id)
    if not campaign:
        raise ValueError(f"Campaign {campaign_id} not found")

    stage = get_stage_record(campaign_id, 'master')
    if not stage:
        raise ValueError("Masters stage not found")

    data = get_master_data(campaign_id)
    if not data or not data.get('result'):
        raise ValueError("Masters Toronto data not initialized")

    master_data = data['result']
    resolved = resolve_master_match(master_data, match_id, winner_id=winner_id, maps=maps)

    _check_and_finalize_master(campaign, stage, data)
    db.session.commit()
    return {'match': resolved, 'master_data': master_data}


def sim_master_round_interactive(campaign_id: int, auto_confirm: bool = True) -> Dict[str, Any]:
    """Simulate all currently playable pending matches in the active round/wave of Masters Toronto."""
    campaign = get_campaign(campaign_id)
    if not campaign:
        raise ValueError(f"Campaign {campaign_id} not found")

    stage = get_stage_record(campaign_id, 'master')
    if not stage:
        raise ValueError("Masters stage not found")

    data = get_master_data(campaign_id)
    if not data or not data.get('result'):
        raise ValueError("Masters Toronto data not initialized")

    master_data = data['result']
    sim_count = sim_master_round(master_data)

    _check_and_finalize_master(campaign, stage, data, auto_confirm=auto_confirm)
    db.session.commit()
    return {'sim_count': sim_count, 'master_data': master_data}


def sim_master_tournament_interactive(campaign_id: int, auto_confirm: bool = True) -> Dict[str, Any]:
    """Simulate all remaining matches in Masters Toronto until Grand Final completes."""
    campaign = get_campaign(campaign_id)
    if not campaign:
        raise ValueError(f"Campaign {campaign_id} not found")

    stage = get_stage_record(campaign_id, 'master')
    if not stage:
        raise ValueError("Masters stage not found")

    data = get_master_data(campaign_id)
    if not data or not data.get('result'):
        raise ValueError("Masters Toronto data not initialized")

    master_data = data['result']
    sim_master_remaining(master_data)

    _check_and_finalize_master(campaign, stage, data, auto_confirm=auto_confirm)
    db.session.commit()
    return {'master_data': master_data}


def run_master_stage(campaign_id: int) -> Dict[str, Any]:
    """Execute VCT Masters (Masters Toronto) 12-team international tournament."""
    sim_master_tournament_interactive(campaign_id)
    stage = get_stage_record(campaign_id, 'master')
    return json.loads(stage.stage_data) if stage and stage.stage_data else {}


# ─────────────────────────────────────────────────────────────────────────────
# Esports World Cup (EWC) Stage Execution & Interactive Resolving
# ─────────────────────────────────────────────────────────────────────────────

def get_ewc_data(campaign_id: int, year: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """Retrieve full EWC data (roster, groups, playoffs, standings) for a campaign."""
    stage = get_stage_record(campaign_id, 'ewc', year=year)
    if not stage or not stage.stage_data:
        return None
    data = json.loads(stage.stage_data)
    roster = data.get('roster', [])

    if roster and len(roster) == 16 and ('result' not in data or not data['result'] or not data['result'].get('groups')):
        data['result'] = init_ewc_state(roster)
        stage.stage_data = json.dumps(data)
        db.session.commit()

    if 'host_city' not in data or not data['host_city']:
        hosts = get_season_hosts(campaign_id, stage.year)
        data['host_city'] = hosts.get('ewc')
        if data['host_city']:
            stage.stage_name = f"Esports World Cup {data['host_city']['city_name']} {stage.year}"
        stage.stage_data = json.dumps(data)
        db.session.commit()

    campaign = get_campaign(campaign_id)
    if campaign:
        heal_stage_tournament_state(campaign, stage, 'ewc', data)

    return data


def _check_and_finalize_ewc(campaign: Campaign, stage: CampaignStage, data: Dict[str, Any], auto_confirm: bool = True):
    """Award story ratings and advance campaign when EWC completes."""
    res = data.get('result')
    if res and (res.get('status') == 'completed' or res.get('matches_completed')):
        res['matches_completed'] = True
        if auto_confirm:
            res['is_confirmed'] = True

        if res.get('is_confirmed') and not res.get('rewards_awarded'):
            club_states = {cs.club_id: cs for cs in CampaignClubState.query.filter_by(campaign_id=campaign.id).all()}
            if res.get('champion'):
                champ = res['champion']
                c_id = champ.get('id') if isinstance(champ, dict) else champ
                if c_id in club_states:
                    club_states[c_id].story_rating = min(99, club_states[c_id].story_rating + 5)
            if res.get('runner_up'):
                runner = res['runner_up']
                r_id = runner.get('id') if isinstance(runner, dict) else runner
                if r_id in club_states:
                    club_states[r_id].story_rating = min(99, club_states[r_id].story_rating + 3)
            if res.get('third_place'):
                third = res['third_place']
                t_id = third.get('id') if isinstance(third, dict) else third
                if t_id in club_states:
                    club_states[t_id].story_rating = min(99, club_states[t_id].story_rating + 2)
            if res.get('fourth_place'):
                fourth = res['fourth_place']
                f_id = fourth.get('id') if isinstance(fourth, dict) else fourth
                if f_id in club_states:
                    club_states[f_id].story_rating = min(99, club_states[f_id].story_rating + 1)

            res['rewards_awarded'] = True

        if auto_confirm:
            stage.status = 'completed'
            stage.completed_at = datetime.now(timezone.utc)
            record_stage_placements(campaign.id, 'ewc', year=stage.year)
            _advance_campaign_to_next_stage(campaign, 'ewc', data)

    stage.stage_data = json.dumps(data)


def resolve_ewc_match_interactive(campaign_id: int, match_id: str,
                                  winner_id: Optional[int] = None,
                                  maps: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Resolve a single EWC match by manual input or single simulation roll."""
    campaign = get_campaign(campaign_id)
    if not campaign:
        raise ValueError(f"Campaign {campaign_id} not found")

    stage = get_stage_record(campaign_id, 'ewc')
    if not stage:
        raise ValueError("EWC stage not found")

    data = get_ewc_data(campaign_id)
    if not data or not data.get('result'):
        raise ValueError("EWC data not initialized")

    ewc_data = data['result']
    resolved = resolve_ewc_match(ewc_data, match_id, winner_id=winner_id, maps=maps)

    _check_and_finalize_ewc(campaign, stage, data)
    db.session.commit()
    return {'match': resolved, 'ewc_data': ewc_data}


def sim_ewc_round_interactive(campaign_id: int, auto_confirm: bool = True) -> Dict[str, Any]:
    """Simulate all currently playable pending matches in the active round/wave of EWC."""
    campaign = get_campaign(campaign_id)
    if not campaign:
        raise ValueError(f"Campaign {campaign_id} not found")

    stage = get_stage_record(campaign_id, 'ewc')
    if not stage:
        raise ValueError("EWC stage not found")

    data = get_ewc_data(campaign_id)
    if not data or not data.get('result'):
        raise ValueError("EWC data not initialized")

    ewc_data = data['result']
    sim_count = sim_ewc_round(ewc_data)

    _check_and_finalize_ewc(campaign, stage, data, auto_confirm=auto_confirm)
    db.session.commit()
    return {'sim_count': sim_count, 'ewc_data': ewc_data}


def sim_ewc_tournament_interactive(campaign_id: int, auto_confirm: bool = True) -> Dict[str, Any]:
    """Simulate all remaining matches in EWC until Grand Final completes."""
    campaign = get_campaign(campaign_id)
    if not campaign:
        raise ValueError(f"Campaign {campaign_id} not found")

    stage = get_stage_record(campaign_id, 'ewc')
    if not stage:
        raise ValueError("EWC stage not found")

    data = get_ewc_data(campaign_id)
    if not data or not data.get('result'):
        raise ValueError("EWC data not initialized")

    ewc_data = data['result']
    sim_ewc_remaining(ewc_data)

    _check_and_finalize_ewc(campaign, stage, data, auto_confirm=auto_confirm)
    db.session.commit()
    return {'ewc_data': ewc_data}


def run_ewc_stage(campaign_id: int) -> Dict[str, Any]:
    """Execute Esports World Cup (EWC) 16-team international tournament."""
    sim_ewc_tournament_interactive(campaign_id)
    stage = get_stage_record(campaign_id, 'ewc')
    return json.loads(stage.stage_data) if stage and stage.stage_data else {}


# ─────────────────────────────────────────────────────────────────────────────
# Official Championship Points (CP) Engine Integration
# ─────────────────────────────────────────────────────────────────────────────

from engine.points import get_stage_points, sort_championship_points_leaderboard, determine_champions_slots


def award_stage_cp(campaign_id: int, stage_key: str, results_list: List[Dict[str, Any]]) -> int:
    """Award official VCT 2025 Championship Points to clubs based on stage results.
    
    results_list: list of dicts with:
      - 'club_id': int
      - 'rank': optional int (final standing in the tournament/playoffs)
      - 'regular_wins': optional int (for Stage 1 / Stage 2 regular season)
      - 'map_diff': optional int
      - 'round_diff': optional int
    """
    awarded_count = 0
    for res in results_list:
        club_id = res['club_id']
        rank = res.get('rank')
        reg_wins = res.get('regular_wins', 0)

        state = CampaignClubState.query.filter_by(campaign_id=campaign_id, club_id=club_id).first()
        if not state:
            continue

        if stage_key in ('stage1_regular', 'stage2_regular'):
            old_wins = state.get_stage_rank(stage_key) or 0
            old_pts = get_stage_points(stage_key, regular_wins=old_wins)
            new_pts = get_stage_points(stage_key, regular_wins=reg_wins)
            state.championship_points = max(0, (state.championship_points or 0) - old_pts + new_pts)
            state.regular_season_wins = max(0, (state.regular_season_wins or 0) - old_wins + reg_wins)
            state.set_stage_rank(stage_key, reg_wins)
        else:
            old_rank = state.get_stage_rank(stage_key)
            old_pts = get_stage_points(stage_key, rank=old_rank) if old_rank else 0
            new_pts = get_stage_points(stage_key, rank=rank)
            state.championship_points = max(0, (state.championship_points or 0) - old_pts + new_pts)
            if rank:
                state.set_stage_rank(stage_key, rank)

        if 'map_diff' in res:
            state.map_differential = (state.map_differential or 0) + res['map_diff']
        if 'round_diff' in res:
            state.round_differential = (state.round_differential or 0) + res['round_diff']

        awarded_count += 1

    db.session.commit()
    return awarded_count


def get_championship_leaderboard(campaign_id: int, region_slug: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return sorted Championship Points leaderboard applying all 11 VCT 2025 tiebreakers."""
    query = CampaignClubState.query.filter_by(campaign_id=campaign_id).join(Club).join(Region)
    if region_slug:
        query = query.filter(Region.slug == region_slug)

    states = query.all()
    teams_payload = []
    for s in states:
        teams_payload.append({
            'club_id': s.club_id,
            'name': s.club.name,
            'short_code': s.club.short_code,
            'logo_url': s.club.logo_url,
            'region_slug': s.club.region.slug if s.club.region else '',
            'is_partner': s.is_partner,
            'championship_points': s.championship_points or 0,
            'story_rating': s.story_rating,
            'effective_rating': s.effective_rating,
            'stage2_rank': s.get_stage_rank('stage2_playoffs'),
            'master_rank': s.get_stage_rank('master'),
            'stage1_rank': s.get_stage_rank('stage1_playoffs'),
            'major_rank': s.get_stage_rank('major'),
            'kickoff_rank': s.get_stage_rank('kickoff'),
            'regular_season_wins': s.regular_season_wins or 0,
            'map_differential': s.map_differential or 0,
            'round_differential': s.round_differential or 0,
        })

    return sort_championship_points_leaderboard(teams_payload)


def get_champions_paris_qualifiers(campaign_id: int, region_slug: str) -> Dict[str, Any]:
    """Calculate the 4 Champions qualifiers for a region according to VCT 2025 rules."""
    leaderboard = get_championship_leaderboard(campaign_id, region_slug=region_slug)
    return determine_champions_slots(leaderboard)


# ─────────────────────────────────────────────────────────────────────────────
# Open Qualifier Stage 2 Execution & Interactive Resolving
# ─────────────────────────────────────────────────────────────────────────────

def _prepare_oq_stage2_stage(campaign: Campaign):
    """Assemble 16 teams per region for Open Qualifier Stage 2:
    - 4 relegated teams from Stage 1 (ranks 9-12)
    - 12 non-Stage 1 challenger teams in the region
    - Top 8 from Stage 1 stay safe and are stored as 'retained_teams'.
    """
    stage_record = CampaignStage.query.filter_by(
        campaign_id=campaign.id, year=campaign.current_year, stage_key='oq_stage2'
    ).first()

    stage1_rec = CampaignStage.query.filter_by(
        campaign_id=campaign.id, year=campaign.current_year, stage_key='stage1'
    ).first()

    states = {cs.club_id: cs for cs in CampaignClubState.query.filter_by(campaign_id=campaign.id).all()}
    s1_data = json.loads(stage1_rec.stage_data) if (stage1_rec and stage1_rec.stage_data) else {}
    s1_regional = s1_data.get('regional_results', {})

    regions_data = {}
    retained_all = {}

    for r_slug in ['pacific', 'americas', 'emea', 'china']:
        reg_s1 = s1_regional.get(r_slug, {})
        standings = reg_s1.get('standings', [])

        retained_teams = []
        relegated_teams = []

        if len(standings) >= 12:
            retained_teams = [s['team'] for s in standings[:8]]
            relegated_teams = [s['team'] for s in standings[8:12]]
        else:
            roster = s1_data.get('rosters', {}).get(r_slug, [])
            retained_teams = roster[:8]
            relegated_teams = roster[8:12]

        retained_ids = {t.get('id') or t.get('club_id') for t in retained_teams}
        retained_all[r_slug] = retained_teams

        region_obj = Region.query.filter_by(slug=r_slug).first()
        all_clubs = Club.query.filter_by(region_id=region_obj.id, is_active=True).all() if region_obj else []

        relegated_ids = {t.get('id') or t.get('club_id') for t in relegated_teams}
        relegated_clubs = [c for c in all_clubs if c.id in relegated_ids]
        challenger_clubs = [c for c in all_clubs if c.id not in retained_ids and c.id not in relegated_ids]

        # Order: 4 relegated clubs (seeds 1-4) followed by 12 challenger clubs (seeds 5-16 sorted by rating)
        sorted_clubs = relegated_clubs + sorted(challenger_clubs, key=lambda c: -c.current_rating)

        participants = []
        for idx, c in enumerate(sorted_clubs):
            cs = states.get(c.id)
            participants.append({
                'id': c.id,
                'name': c.name,
                'short_code': c.short_code,
                'region_slug': r_slug,
                'region': r_slug,
                'is_partner': cs.is_partner if cs else False,
                'story_rating': cs.story_rating if cs else c.current_rating,
                'form_modifier': cs.form_modifier if cs else 0,
                'effective_rating': cs.effective_rating if cs else c.current_rating,
                'logo_url': c.logo_url,
                'seed': idx + 1,
            })

        if len(participants) == 16:
            reg_state = init_open_qualifier_region_state(r_slug, participants)
            regions_data[r_slug] = reg_state

    if not stage_record:
        stage_record = CampaignStage(
            campaign_id=campaign.id,
            year=campaign.current_year,
            stage_key='oq_stage2',
            stage_name=f'Open Qualifier Stage 2 {campaign.current_year}',
            status='pending',
            stage_data=json.dumps({
                'regions': regions_data,
                'retained_teams': retained_all,
            }),
        )
        db.session.add(stage_record)
    else:
        curr_data = json.loads(stage_record.stage_data) if stage_record.stage_data else {}
        curr_data['retained_teams'] = retained_all
        if 'regions' not in curr_data or not curr_data['regions']:
            curr_data['regions'] = regions_data
        stage_record.stage_data = json.dumps(curr_data)


def get_oq_stage2_data(campaign_id: int) -> Optional[Dict[str, Any]]:
    """Retrieve full Open Qualifier Stage 2 data for a campaign."""
    stage = get_stage_record(campaign_id, 'oq_stage2')
    if not stage or not stage.stage_data:
        campaign = get_campaign(campaign_id)
        if campaign:
            _prepare_oq_stage2_stage(campaign)
            db.session.commit()
            stage = get_stage_record(campaign_id, 'oq_stage2')
    if not stage or not stage.stage_data:
        return None
    data = json.loads(stage.stage_data)
    campaign = get_campaign(campaign_id)
    if campaign:
        heal_stage_regional_state(campaign, stage, 'oq_stage2', data)
    return data


def _check_and_finalize_oq_stage2(campaign: Campaign, stage: CampaignStage, data: Dict[str, Any], auto_confirm: bool = True):
    """Update dynamic ratings and advance campaign to Stage 2 when all 4 regions complete."""
    all_regions = ['pacific', 'americas', 'emea', 'china']
    club_states = {cs.club_id: cs for cs in CampaignClubState.query.filter_by(campaign_id=campaign.id).all()}

    for r_slug in all_regions:
        reg_res = data.get('regions', {}).get(r_slug)
        if reg_res:
            is_done, _ = is_stage_region_actually_completed('open_qualifier', reg_res)
            if is_done and (reg_res.get('status') == 'completed' or reg_res.get('matches_completed')):
                reg_res['matches_completed'] = True
                if auto_confirm:
                    reg_res['is_confirmed'] = True

            if reg_res.get('is_confirmed') and not reg_res.get('ratings_awarded'):
                qual_ids = {t['id'] for t in reg_res.get('qualified_teams', [])}
                for cid in qual_ids:
                    if cid in club_states:
                        club_states[cid].story_rating = min(99, club_states[cid].story_rating + 2)
                for s in reg_res.get('swiss_standings', []):
                    cid = s['club_id']
                    if s['wins'] == 0 and cid in club_states:
                        club_states[cid].story_rating = max(60, club_states[cid].story_rating - 1)
                reg_res['ratings_awarded'] = True

    stage.stage_data = json.dumps(data)

    if auto_confirm and all(data.get('regions', {}).get(r, {}).get('status') == 'completed' for r in all_regions):
        for r in all_regions:
            data.get('regions', {}).get(r, {})['is_confirmed'] = True
        stage.status = 'completed'
        stage.completed_at = datetime.now(timezone.utc)
        record_stage_placements(campaign.id, 'oq_stage2', year=stage.year)
        _advance_campaign_to_next_stage(campaign, 'oq_stage2', data)


def resolve_oq_stage2_match(campaign_id: int, region_slug: str, match_id: str,
                            winner_id: Optional[int] = None,
                            maps: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Resolve an Open Qualifier Stage 2 match by manual input or single simulation roll."""
    campaign = get_campaign(campaign_id)
    if not campaign:
        raise ValueError(f"Campaign {campaign_id} not found")

    stage = get_stage_record(campaign_id, 'oq_stage2')
    if not stage:
        raise ValueError("Open Qualifier Stage 2 not found")

    data = get_oq_stage2_data(campaign_id)
    reg_data = data['regions'][region_slug]
    club_states = CampaignClubState.query.filter_by(campaign_id=campaign_id).all()
    rating_lookup = {cs.club_id: cs.story_rating for cs in club_states}
    form_lookup = {cs.club_id: cs.form_modifier for cs in club_states}

    resolved = resolve_open_qualifier_match(
        reg_data, match_id,
        winner_id=winner_id,
        maps=maps,
        rating_lookup=rating_lookup,
        form_lookup=form_lookup,
    )
    _check_and_finalize_oq_stage2(campaign, stage, data)
    db.session.commit()
    return {'match': resolved, 'region_data': reg_data}


def sim_oq_stage2_round(campaign_id: int, region_slug: str, auto_confirm: bool = True) -> Dict[str, Any]:
    """Simulate active round in Open Qualifier Stage 2 for a region."""
    campaign = get_campaign(campaign_id)
    if not campaign:
        raise ValueError(f"Campaign {campaign_id} not found")

    stage = get_stage_record(campaign_id, 'oq_stage2')
    if not stage:
        raise ValueError("Open Qualifier Stage 2 not found")

    data = get_oq_stage2_data(campaign_id)
    reg_data = data['regions'][region_slug]
    club_states = CampaignClubState.query.filter_by(campaign_id=campaign_id).all()
    rating_lookup = {cs.club_id: cs.story_rating for cs in club_states}
    form_lookup = {cs.club_id: cs.form_modifier for cs in club_states}

    sim_count = sim_open_qualifier_round(reg_data, rating_lookup=rating_lookup, form_lookup=form_lookup)
    _check_and_finalize_oq_stage2(campaign, stage, data, auto_confirm=auto_confirm)
    db.session.commit()
    return {'sim_count': sim_count, 'region_data': reg_data}


def sim_oq_stage2_region(campaign_id: int, region_slug: str, auto_confirm: bool = True) -> Dict[str, Any]:
    """Simulate all remaining matches for a single region in Open Qualifier Stage 2."""
    campaign = get_campaign(campaign_id)
    if not campaign:
        raise ValueError(f"Campaign {campaign_id} not found")

    stage = get_stage_record(campaign_id, 'oq_stage2')
    if not stage:
        raise ValueError("Open Qualifier Stage 2 not found")

    data = get_oq_stage2_data(campaign_id)
    reg_data = data['regions'][region_slug]
    club_states = CampaignClubState.query.filter_by(campaign_id=campaign_id).all()
    rating_lookup = {cs.club_id: cs.story_rating for cs in club_states}
    form_lookup = {cs.club_id: cs.form_modifier for cs in club_states}

    sim_open_qualifier_remaining(reg_data, rating_lookup=rating_lookup, form_lookup=form_lookup)
    _check_and_finalize_oq_stage2(campaign, stage, data, auto_confirm=auto_confirm)
    db.session.commit()
    return {'region_data': reg_data}


def sim_oq_stage2_all(campaign_id: int, auto_confirm: bool = True) -> Dict[str, Any]:
    """Simulate all 4 regions in Open Qualifier Stage 2 to completion."""
    campaign = get_campaign(campaign_id)
    if not campaign:
        raise ValueError(f"Campaign {campaign_id} not found")

    stage = get_stage_record(campaign_id, 'oq_stage2')
    if not stage:
        raise ValueError("Open Qualifier Stage 2 not found")

    data = get_oq_stage2_data(campaign_id)
    club_states = CampaignClubState.query.filter_by(campaign_id=campaign_id).all()
    rating_lookup = {cs.club_id: cs.story_rating for cs in club_states}
    form_lookup = {cs.club_id: cs.form_modifier for cs in club_states}

    for r_slug in ['pacific', 'americas', 'emea', 'china']:
        if r_slug in data.get('regions', {}):
            reg_data = data['regions'][r_slug]
            sim_open_qualifier_remaining(reg_data, rating_lookup=rating_lookup, form_lookup=form_lookup)

    _check_and_finalize_oq_stage2(campaign, stage, data, auto_confirm=auto_confirm)
    db.session.commit()
    return {'data': data}


# ─────────────────────────────────────────────────────────────────────────────
# VCT Stage 2 Execution & Interactive Resolving
# ─────────────────────────────────────────────────────────────────────────────

def _prepare_stage2_stage(campaign: Campaign):
    """Assemble 12 teams per region for VCT Stage 2:
    - 8 retained teams from Stage 1 (Ranks 1-8)
    - 4 promoted teams from Open Qualifier Stage 2 (or Stage 1 fallback)
    """
    stage2_record = CampaignStage.query.filter_by(
        campaign_id=campaign.id, year=campaign.current_year, stage_key='stage2'
    ).first()

    oq_stage2_rec = CampaignStage.query.filter_by(
        campaign_id=campaign.id, year=campaign.current_year, stage_key='oq_stage2'
    ).first()

    stage1_rec = CampaignStage.query.filter_by(
        campaign_id=campaign.id, year=campaign.current_year, stage_key='stage1'
    ).first()

    states = {cs.club_id: cs for cs in CampaignClubState.query.filter_by(campaign_id=campaign.id).all()}
    rosters = {}
    regional_results = {}

    oq_s2_data = json.loads(oq_stage2_rec.stage_data) if (oq_stage2_rec and oq_stage2_rec.stage_data) else {}
    s1_data = json.loads(stage1_rec.stage_data) if (stage1_rec and stage1_rec.stage_data) else {}

    for r_slug in ['pacific', 'americas', 'emea', 'china']:
        prepared_roster = []

        # 1. Preferred source: 8 retained + 4 qualified from OQ Stage 2
        if oq_s2_data and 'retained_teams' in oq_s2_data and r_slug in oq_s2_data['retained_teams']:
            retained = oq_s2_data['retained_teams'].get(r_slug, [])
            reg_oq = oq_s2_data.get('regions', {}).get(r_slug, {})
            promoted = reg_oq.get('qualified_teams', [])

            for idx, t in enumerate(retained):
                c_id = t.get('id') or t.get('club_id')
                cs = states.get(c_id)
                prepared_roster.append({
                    'id': c_id,
                    'name': t.get('name'),
                    'short_code': t.get('short_code'),
                    'region_slug': r_slug,
                    'region': r_slug,
                    'stage1_rank': idx + 1,
                    'seed': idx + 1,
                    'story_rating': cs.story_rating if cs else t.get('story_rating', 80),
                    'form_modifier': cs.form_modifier if cs else 0,
                    'effective_rating': cs.effective_rating if cs else 80,
                    'logo_url': (cs.club.logo_url if cs and cs.club else None) or t.get('logo_url'),
                })

            for idx, t in enumerate(promoted):
                c_id = t.get('id') or t.get('club_id')
                cs = states.get(c_id)
                prepared_roster.append({
                    'id': c_id,
                    'name': t.get('name'),
                    'short_code': t.get('short_code'),
                    'region_slug': r_slug,
                    'region': r_slug,
                    'stage1_rank': 9 + idx,
                    'seed': 9 + idx,
                    'story_rating': cs.story_rating if cs else t.get('story_rating', 80),
                    'form_modifier': cs.form_modifier if cs else 0,
                    'effective_rating': cs.effective_rating if cs else 80,
                    'logo_url': (cs.club.logo_url if cs and cs.club else None) or t.get('logo_url'),
                })

        # 2. Fallback: if oq_stage2 not available, pull directly from Stage 1 standings/roster
        if len(prepared_roster) != 12 and s1_data:
            s1_regional = s1_data.get('regional_results', {})
            reg_s1 = s1_regional.get(r_slug, {})
            st_list = reg_s1.get('standings', [])
            if len(st_list) >= 12:
                for idx, item in enumerate(st_list[:12]):
                    t = item['team']
                    c_id = t.get('id') or t.get('club_id')
                    cs = states.get(c_id)
                    prepared_roster.append({
                        'id': c_id,
                        'name': t.get('name'),
                        'short_code': t.get('short_code'),
                        'region_slug': r_slug,
                        'region': r_slug,
                        'stage1_rank': idx + 1,
                        'seed': idx + 1,
                        'story_rating': cs.story_rating if cs else t.get('story_rating', 80),
                        'form_modifier': cs.form_modifier if cs else 0,
                        'effective_rating': cs.effective_rating if cs else 80,
                        'logo_url': (cs.club.logo_url if cs and cs.club else None) or t.get('logo_url'),
                    })
            else:
                s1_raw_roster = s1_data.get('rosters', {}).get(r_slug, [])
                for idx, t in enumerate(s1_raw_roster):
                    c_id = t.get('id') or t.get('club_id')
                    cs = states.get(c_id)
                    prepared_roster.append({
                        'id': c_id,
                        'name': t.get('name'),
                        'short_code': t.get('short_code'),
                        'region_slug': r_slug,
                        'region': r_slug,
                        'stage1_rank': idx + 1,
                        'seed': idx + 1,
                        'story_rating': cs.story_rating if cs else t.get('story_rating', 80),
                        'form_modifier': cs.form_modifier if cs else 0,
                        'effective_rating': cs.effective_rating if cs else 80,
                        'logo_url': (cs.club.logo_url if cs and cs.club else None) or t.get('logo_url'),
                    })

        rosters[r_slug] = prepared_roster
        if len(prepared_roster) == 12:
            regional_results[r_slug] = init_stage2_region_state(r_slug, prepared_roster)

    if not stage2_record:
        stage2_record = CampaignStage(
            campaign_id=campaign.id,
            year=campaign.current_year,
            stage_key='stage2',
            stage_name=f'VCT Stage 2 {campaign.current_year}',
            status='pending',
            stage_data=json.dumps({'rosters': rosters, 'regional_results': regional_results}),
        )
        db.session.add(stage2_record)
    else:
        s2_data = json.loads(stage2_record.stage_data) if stage2_record.stage_data else {}
        s2_data['rosters'] = rosters
        if 'regional_results' not in s2_data or not s2_data['regional_results']:
            s2_data['regional_results'] = regional_results
        stage2_record.stage_data = json.dumps(s2_data)


def get_stage2_data(campaign_id: int, year: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """Retrieve full Stage 2 data (rosters, regional_results) for a campaign."""
    stage = get_stage_record(campaign_id, 'stage2', year=year)
    if not stage or not stage.stage_data:
        campaign = get_campaign(campaign_id)
        if campaign:
            _prepare_stage2_stage(campaign)
            db.session.commit()
            stage = get_stage_record(campaign_id, 'stage2', year=year)
    if not stage or not stage.stage_data:
        return None
    data = json.loads(stage.stage_data)

    rosters = data.get('rosters', {})
    reg_results = data.get('regional_results', {})
    changed = False
    for r_slug in ['pacific', 'americas', 'emea', 'china']:
        if (r_slug not in reg_results or not reg_results[r_slug]) and r_slug in rosters and len(rosters[r_slug]) == 12:
            reg_results[r_slug] = init_stage2_region_state(r_slug, rosters[r_slug])
            changed = True
    if changed:
        data['regional_results'] = reg_results
        stage.stage_data = json.dumps(data)
        db.session.commit()

    campaign = get_campaign(campaign_id)
    if campaign:
        heal_stage_regional_state(campaign, stage, 'stage2', data)

    return data


def _prepare_champion_stage(campaign: Campaign, qualifiers: Optional[List[Dict[str, Any]]] = None):
    """Assemble 16 qualified teams from Stage 2 / CP for VALORANT Champions Paris."""
    champ_stage = CampaignStage.query.filter_by(
        campaign_id=campaign.id, year=campaign.current_year, stage_key='champion'
    ).first()

    roster = []
    if qualifiers:
        for q in qualifiers:
            t = dict(q.get('team', q))
            t['id'] = t.get('id') or t.get('club_id')
            t['club_id'] = t['id']
            t['champions_seed'] = q.get('champions_seed') or t.get('champions_seed') or 1
            t['regional_seed'] = t['champions_seed']
            t['pool'] = t['champions_seed']
            t['slot_type'] = q.get('slot_type') or t.get('slot_type') or 'Champions Qualifier'
            roster.append(t)

    # Fallback if qualifiers not passed or incomplete
    if len(roster) != 16:
        roster = []
        for r_slug in ['pacific', 'americas', 'emea', 'china']:
            champs_info = get_champions_paris_qualifiers(campaign.id, r_slug)
            for q in champs_info.get('qualifiers', []):
                t = dict(q.get('team', q))
                t['id'] = t.get('id') or t.get('club_id')
                t['club_id'] = t['id']
                t['champions_seed'] = q.get('champions_seed') or t.get('champions_seed') or 1
                t['regional_seed'] = t['champions_seed']
                t['slot_type'] = q.get('slot_type') or t.get('slot_type') or 'Champions Qualifier'
                roster.append(t)

    champ_result = init_champion_state(roster) if len(roster) == 16 else {}

    hosts = get_season_hosts(campaign.id, campaign.current_year)
    champ_host = hosts.get('champion')
    champ_city = champ_host['city_name'] if champ_host else 'Seoul'
    st_name = f'VALORANT Champions {champ_city} {campaign.current_year}'

    if not champ_stage:
        champ_stage = CampaignStage(
            campaign_id=campaign.id,
            year=campaign.current_year,
            stage_key='champion',
            stage_name=st_name,
            status='pending',
            stage_data=json.dumps({'roster': roster, 'result': champ_result, 'host_city': champ_host}),
        )
        db.session.add(champ_stage)
    else:
        c_data = json.loads(champ_stage.stage_data) if champ_stage.stage_data else {}
        c_data['roster'] = roster
        if 'result' not in c_data or not c_data['result']:
            c_data['result'] = champ_result
        if 'host_city' not in c_data or not c_data['host_city']:
            c_data['host_city'] = champ_host
        champ_stage.stage_name = st_name
        champ_stage.stage_data = json.dumps(c_data)


def _check_and_finalize_stage2(campaign: Campaign, stage: CampaignStage, data: Dict[str, Any], auto_confirm: bool = True):
    """Award CP, update leaderboard and determine Champions Paris qualifiers."""
    all_regions = ['pacific', 'americas', 'emea', 'china']
    club_states = {cs.club_id: cs for cs in CampaignClubState.query.filter_by(campaign_id=campaign.id).all()}

    for r_slug, reg_data in data.get('regional_results', {}).items():
        if (reg_data.get('status') == 'completed' or reg_data.get('matches_completed')):
            reg_data['matches_completed'] = True
            if auto_confirm:
                reg_data['is_confirmed'] = True

            if reg_data.get('is_confirmed') and not reg_data.get('rewards_awarded'):
                # 1. Award regular season CP (+1 CP per win)
                reg_awards = []
                for s in reg_data.get('alpha_standings', []) + reg_data.get('omega_standings', []):
                    reg_awards.append({
                        'club_id': s['club_id'],
                        'regular_wins': s['wins'],
                        'map_diff': s['map_diff'],
                        'round_diff': s['round_diff'],
                    })
                award_stage_cp(campaign.id, 'stage2_regular', reg_awards)

                # 2. Award playoff CP (1st: 7, 2nd: 5, 3rd: 4, 4th: 3)
                playoff_awards = []
                for s in reg_data.get('standings', []):
                    playoff_awards.append({
                        'club_id': s['club_id'],
                        'rank': s['rank'],
                    })
                award_stage_cp(campaign.id, 'stage2_playoffs', playoff_awards)

                # 3. Rating boosts
                champ = reg_data.get('champion')
                runner = reg_data.get('runner_up')
                third = reg_data.get('third_place')
                if champ:
                    c_id = champ.get('id') or champ.get('club_id')
                    if c_id in club_states:
                        club_states[c_id].story_rating = min(99, club_states[c_id].story_rating + 3)
                if runner:
                    r_id = runner.get('id') or runner.get('club_id')
                    if r_id in club_states:
                        club_states[r_id].story_rating = min(99, club_states[r_id].story_rating + 2)
                if third:
                    t_id = third.get('id') or third.get('club_id')
                    if t_id in club_states:
                        club_states[t_id].story_rating = min(99, club_states[t_id].story_rating + 1)

                # 4. Calculate Champions Paris Qualifiers for this region
                champs_info = get_champions_paris_qualifiers(campaign.id, r_slug)
                reg_data['champions_qualifiers'] = champs_info.get('qualifiers', [])
                reg_data['cp_leaderboard'] = champs_info.get('leaderboard', [])

                reg_data['rewards_awarded'] = True

    stage.stage_data = json.dumps(data)

    if auto_confirm and all(data.get('regional_results', {}).get(r, {}).get('status') == 'completed' for r in all_regions):
        for r in all_regions:
            data.get('regional_results', {}).get(r, {})['is_confirmed'] = True
        stage.status = 'completed'
        stage.completed_at = datetime.now(timezone.utc)
        record_stage_placements(campaign.id, 'stage2', year=stage.year)
        _advance_campaign_to_next_stage(campaign, 'stage2', data)


def resolve_stage2_match_interactive(campaign_id: int, region_slug: str, match_id: str,
                                     winner_id: Optional[int] = None,
                                     maps: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Resolve a single Stage 2 match by manual input or single simulation roll."""
    campaign = get_campaign(campaign_id)
    if not campaign:
        raise ValueError(f"Campaign {campaign_id} not found")

    stage = get_stage_record(campaign_id, 'stage2')
    if not stage:
        raise ValueError("Stage 2 not found")

    data = get_stage2_data(campaign_id)
    reg_data = data['regional_results'][region_slug]
    club_states = CampaignClubState.query.filter_by(campaign_id=campaign_id).all()
    rating_lookup = {cs.club_id: cs.story_rating for cs in club_states}
    form_lookup = {cs.club_id: cs.form_modifier for cs in club_states}

    resolved = resolve_stage2_match(
        reg_data, match_id,
        winner_id=winner_id,
        maps=maps,
        rating_lookup=rating_lookup,
        form_lookup=form_lookup,
    )
    _check_and_finalize_stage2(campaign, stage, data)
    db.session.commit()
    return {'match': resolved, 'region_data': reg_data}


def sim_stage2_round_interactive(campaign_id: int, region_slug: str, auto_confirm: bool = True) -> Dict[str, Any]:
    """Simulate active week or active playoff wave for a single region in Stage 2."""
    campaign = get_campaign(campaign_id)
    if not campaign:
        raise ValueError(f"Campaign {campaign_id} not found")

    stage = get_stage_record(campaign_id, 'stage2')
    if not stage:
        raise ValueError("Stage 2 not found")

    data = get_stage2_data(campaign_id)
    reg_data = data['regional_results'][region_slug]
    club_states = CampaignClubState.query.filter_by(campaign_id=campaign_id).all()
    rating_lookup = {cs.club_id: cs.story_rating for cs in club_states}
    form_lookup = {cs.club_id: cs.form_modifier for cs in club_states}

    sim_count = sim_stage2_round(reg_data, rating_lookup=rating_lookup, form_lookup=form_lookup)
    _check_and_finalize_stage2(campaign, stage, data, auto_confirm=auto_confirm)
    db.session.commit()
    return {'sim_count': sim_count, 'region_data': reg_data}


def sim_stage2_region_interactive(campaign_id: int, region_slug: str, auto_confirm: bool = True) -> Dict[str, Any]:
    """Simulate all remaining matches for a single region in Stage 2."""
    campaign = get_campaign(campaign_id)
    if not campaign:
        raise ValueError(f"Campaign {campaign_id} not found")

    stage = get_stage_record(campaign_id, 'stage2')
    if not stage:
        raise ValueError("Stage 2 not found")

    data = get_stage2_data(campaign_id)
    reg_data = data['regional_results'][region_slug]
    club_states = CampaignClubState.query.filter_by(campaign_id=campaign_id).all()
    rating_lookup = {cs.club_id: cs.story_rating for cs in club_states}
    form_lookup = {cs.club_id: cs.form_modifier for cs in club_states}

    sim_count = sim_stage2_remaining(reg_data, rating_lookup=rating_lookup, form_lookup=form_lookup)
    _check_and_finalize_stage2(campaign, stage, data, auto_confirm=auto_confirm)
    db.session.commit()
    return {'sim_count': sim_count, 'region_data': reg_data}


def sim_stage2_all_interactive(campaign_id: int, auto_confirm: bool = True) -> Dict[str, Any]:
    """Simulate all 4 regions in Stage 2 to completion."""
    campaign = get_campaign(campaign_id)
    if not campaign:
        raise ValueError(f"Campaign {campaign_id} not found")

    stage = get_stage_record(campaign_id, 'stage2')
    if not stage:
        raise ValueError("Stage 2 not found")

    data = get_stage2_data(campaign_id)
    club_states = CampaignClubState.query.filter_by(campaign_id=campaign_id).all()
    rating_lookup = {cs.club_id: cs.story_rating for cs in club_states}
    form_lookup = {cs.club_id: cs.form_modifier for cs in club_states}

    total_sim = 0
    for r_slug in ['pacific', 'americas', 'emea', 'china']:
        if r_slug in data.get('regional_results', {}):
            reg_data = data['regional_results'][r_slug]
            total_sim += sim_stage2_remaining(reg_data, rating_lookup=rating_lookup, form_lookup=form_lookup)

    _check_and_finalize_stage2(campaign, stage, data, auto_confirm=auto_confirm)
    db.session.commit()
    return {'total_sim': total_sim, 'stage2_data': data}




# ─────────────────────────────────────────────────────────────────────────────
# VALORANT Champions Paris Stage Execution & Interactive Resolving
# ─────────────────────────────────────────────────────────────────────────────

def get_champion_data(campaign_id: int, year: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """Retrieve full Champions Paris data (roster, groups, playoffs, standings) for a campaign."""
    stage = get_stage_record(campaign_id, 'champion', year=year)
    if not stage or not stage.stage_data:
        campaign = get_campaign(campaign_id)
        if campaign:
            _prepare_champion_stage(campaign)
            db.session.commit()
            stage = get_stage_record(campaign_id, 'champion', year=year)
    if not stage or not stage.stage_data:
        return None
    data = json.loads(stage.stage_data)
    roster = data.get('roster', [])

    if roster and len(roster) == 16 and ('result' not in data or not data['result'] or not data['result'].get('groups')):
        data['result'] = init_champion_state(roster)
        stage.stage_data = json.dumps(data)
        db.session.commit()

    # Hydrate group standings and team logos
    res = data.get('result')
    if res and res.get('groups'):
        club_logos = {c.id: c.logo_url for c in Club.query.all()}
        def _hydrate_t(t):
            if isinstance(t, dict) and t.get('id'):
                tid = t['id']
                if tid in club_logos and club_logos[tid]:
                    t['logo_url'] = club_logos[tid]

        for grp in res['groups'].values():
            update_champion_group_standings(grp)
            for s in grp.get('standings', []):
                _hydrate_t(s.get('team'))
            for t in grp.get('teams', []):
                _hydrate_t(t)
            for m in grp.get('matches', {}).values():
                if isinstance(m, dict):
                    _hydrate_t(m.get('team_a'))
                    _hydrate_t(m.get('team_b'))
                    _hydrate_t(m.get('winner'))
                    _hydrate_t(m.get('loser'))
            _hydrate_t(grp.get('winner_seed1'))
            _hydrate_t(grp.get('winner_seed2'))

        for m in res.get('playoff_matches', []):
            if isinstance(m, dict):
                _hydrate_t(m.get('team_a'))
                _hydrate_t(m.get('team_b'))
                _hydrate_t(m.get('winner'))
                _hydrate_t(m.get('loser'))
        _hydrate_t(res.get('champion'))
        _hydrate_t(res.get('runner_up'))
        _hydrate_t(res.get('third_place'))
        _hydrate_t(res.get('fourth_place'))

    if 'host_city' not in data or not data['host_city']:
        hosts = get_season_hosts(campaign_id, stage.year)
        data['host_city'] = hosts.get('champion')
        if data['host_city']:
            stage.stage_name = f"VALORANT Champions {data['host_city']['city_name']} {stage.year}"
        stage.stage_data = json.dumps(data)
        db.session.commit()

    campaign = get_campaign(campaign_id)
    if campaign:
        heal_stage_tournament_state(campaign, stage, 'champion', data)

    return data


def _check_and_finalize_champion(campaign: Campaign, stage: CampaignStage, data: Dict[str, Any], auto_confirm: bool = True):
    """Award story ratings and advance to Year-End Hall of Fame when Champions completes."""
    res = data.get('result')
    if res and (res.get('status') == 'completed' or res.get('matches_completed')):
        res['matches_completed'] = True
        if auto_confirm:
            res['is_confirmed'] = True

        if res.get('is_confirmed') and not res.get('rewards_awarded'):
            club_states = {cs.club_id: cs for cs in CampaignClubState.query.filter_by(campaign_id=campaign.id).all()}
            if res.get('champion'):
                champ = res['champion']
                c_id = champ.get('id') or champ.get('club_id')
                if c_id in club_states:
                    club_states[c_id].story_rating = min(99, club_states[c_id].story_rating + 10)
                    club_states[c_id].set_stage_rank('champion', 1)
            if res.get('runner_up'):
                runner = res['runner_up']
                r_id = runner.get('id') or runner.get('club_id')
                if r_id in club_states:
                    club_states[r_id].story_rating = min(99, club_states[r_id].story_rating + 6)
                    club_states[r_id].set_stage_rank('champion', 2)
            if res.get('third_place'):
                third = res['third_place']
                t_id = third.get('id') or third.get('club_id')
                if t_id in club_states:
                    club_states[t_id].story_rating = min(99, club_states[t_id].story_rating + 4)
                    club_states[t_id].set_stage_rank('champion', 3)
            if res.get('fourth_place'):
                fourth = res['fourth_place']
                f_id = fourth.get('id') or fourth.get('club_id')
                if f_id in club_states:
                    club_states[f_id].story_rating = min(99, club_states[f_id].story_rating + 3)
                    club_states[f_id].set_stage_rank('champion', 4)

            res['rewards_awarded'] = True

        if auto_confirm:
            stage.status = 'completed'
            stage.completed_at = datetime.now(timezone.utc)
            record_stage_placements(campaign.id, 'champion', year=stage.year)
            _advance_campaign_to_next_stage(campaign, 'champion', data)

    stage.stage_data = json.dumps(data)


def resolve_champion_match_interactive(campaign_id: int, match_id: str,
                                       winner_id: Optional[int] = None,
                                       maps: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Resolve a single Champions Paris match by manual input or single simulation roll."""
    campaign = get_campaign(campaign_id)
    if not campaign:
        raise ValueError(f"Campaign {campaign_id} not found")

    stage = get_stage_record(campaign_id, 'champion')
    if not stage:
        raise ValueError("Champions stage not found")

    data = get_champion_data(campaign_id)
    champ_data = data['result']

    resolved = resolve_champion_match(champ_data, match_id, winner_id=winner_id, maps=maps)
    _check_and_finalize_champion(campaign, stage, data)
    db.session.commit()
    return {'match': resolved, 'champ_data': champ_data}


def sim_champion_round_interactive(campaign_id: int, auto_confirm: bool = True) -> Dict[str, Any]:
    """Simulate active playable wave of matches in Champions Paris."""
    campaign = get_campaign(campaign_id)
    if not campaign:
        raise ValueError(f"Campaign {campaign_id} not found")

    stage = get_stage_record(campaign_id, 'champion')
    if not stage:
        raise ValueError("Champions stage not found")

    data = get_champion_data(campaign_id)
    champ_data = data['result']

    sim_count = sim_champion_round(champ_data)
    _check_and_finalize_champion(campaign, stage, data, auto_confirm=auto_confirm)
    db.session.commit()
    return {'sim_count': sim_count, 'champ_data': champ_data}


def sim_champion_tournament_interactive(campaign_id: int, auto_confirm: bool = True) -> Dict[str, Any]:
    """Simulate all remaining matches until Champions Paris completes."""
    campaign = get_campaign(campaign_id)
    if not campaign:
        raise ValueError(f"Campaign {campaign_id} not found")

    stage = get_stage_record(campaign_id, 'champion')
    if not stage:
        raise ValueError("Champions stage not found")

    data = get_champion_data(campaign_id)
    champ_data = data['result']
    sim_champion_remaining(champ_data)

    _check_and_finalize_champion(campaign, stage, data, auto_confirm=auto_confirm)
    db.session.commit()
    return {'champ_data': champ_data}


def run_champion_stage(campaign_id: int) -> Dict[str, Any]:
    """Execute VALORANT Champions Paris 16-team tournament to completion."""
    sim_champion_tournament_interactive(campaign_id)
    stage = get_stage_record(campaign_id, 'champion')
    return json.loads(stage.stage_data) if stage and stage.stage_data else {}


# ─────────────────────────────────────────────────────────────────────────────
# Year-End Hall of Fame & Season Summary
# ─────────────────────────────────────────────────────────────────────────────

def _prepare_season_summary_stage(campaign: Campaign):
    """Assemble final year-end summary stage for the campaign."""
    summary_stage = CampaignStage.query.filter_by(
        campaign_id=campaign.id, year=campaign.current_year, stage_key='season_summary'
    ).first()
    summary_data = get_season_summary_data(campaign.id)

    if not summary_stage:
        summary_stage = CampaignStage(
            campaign_id=campaign.id,
            year=campaign.current_year,
            stage_key='season_summary',
            stage_name=f'Year-End Hall of Fame {campaign.current_year}',
            status='in_progress',
            stage_data=json.dumps(summary_data),
        )
        db.session.add(summary_stage)
    else:
        summary_stage.stage_data = json.dumps(summary_data)


def _extract_kickoff_titles(campaign_id: int, year: int) -> Dict[str, Any]:
    """Retrieve champions for all 4 Kickoff regions, with fail-safe fallback to placements."""
    all_regions = ['pacific', 'americas', 'emea', 'china']
    k_titles = {}

    k_stage = get_stage_record(campaign_id, 'kickoff', year=year)
    if not k_stage:
        k_stage = CampaignStage.query.filter_by(
            campaign_id=campaign_id, stage_key='kickoff'
        ).order_by(CampaignStage.year.desc()).first()

    if k_stage and k_stage.stage_data:
        try:
            k_data = json.loads(k_stage.stage_data)
            k_reg = k_data.get('regional_results', {})
            for r in all_regions:
                reg_d = k_reg.get(r, {})
                champ = reg_d.get('champion')
                if not champ and reg_d.get('standings'):
                    champ = reg_d['standings'][0].get('team')
                if not champ and reg_d.get('major_qualifiers'):
                    champ = reg_d['major_qualifiers'][0]
                if champ:
                    if isinstance(champ, dict):
                        c_dict = dict(champ)
                        if 'id' not in c_dict and 'club_id' in c_dict:
                            c_dict['id'] = c_dict['club_id']
                        k_titles[r] = c_dict
                    elif isinstance(champ, int):
                        c = Club.query.get(champ)
                        if c:
                            k_titles[r] = c.to_dict()
        except Exception:
            pass

    for r in all_regions:
        if r not in k_titles:
            p = CampaignStagePlacement.query.filter_by(
                campaign_id=campaign_id, year=year, stage_key='kickoff', region_slug=r, rank=1
            ).first()
            if not p:
                p = CampaignStagePlacement.query.filter_by(
                    campaign_id=campaign_id, stage_key='kickoff', region_slug=r, rank=1
                ).order_by(CampaignStagePlacement.year.desc()).first()
            if p and p.club:
                k_titles[r] = p.club.to_dict()

    missing = [r for r in all_regions if r not in k_titles]
    if missing and k_stage and k_stage.stage_data:
        record_stage_placements(campaign_id, 'kickoff', year=k_stage.year)
        for r in missing:
            p = CampaignStagePlacement.query.filter_by(
                campaign_id=campaign_id, year=k_stage.year, stage_key='kickoff', region_slug=r, rank=1
            ).first()
            if not p:
                p = CampaignStagePlacement.query.filter_by(
                    campaign_id=campaign_id, stage_key='kickoff', region_slug=r, rank=1
                ).order_by(CampaignStagePlacement.year.desc()).first()
            if p and p.club:
                k_titles[r] = p.club.to_dict()

    return k_titles


def get_season_summary_data(campaign_id: int, year: Optional[int] = None) -> Dict[str, Any]:
    """Gather all title winners, season awards, leaderboards, placements, and Hall of Fame records for any year."""
    campaign = get_campaign(campaign_id)
    if not campaign:
        return {}

    backfill_stage_placements_if_needed(campaign_id)

    # Determine available years across the campaign
    query_years = db.session.query(CampaignStage.year).filter_by(
        campaign_id=campaign_id
    ).distinct().order_by(CampaignStage.year.asc()).all()
    available_years = sorted(list(set([y[0] for y in query_years] + [campaign.current_year])))

    target_year = year if (year and year in available_years) else campaign.current_year

    # Check if this is an archived past year
    if target_year < campaign.current_year:
        hof_stage = CampaignStage.query.filter_by(
            campaign_id=campaign_id, year=target_year, stage_key=f'hof_year_{target_year}'
        ).first()
        if hof_stage and hof_stage.stage_data:
            try:
                archived = json.loads(hof_stage.stage_data)
                archived['available_years'] = available_years
                archived['year'] = target_year
                archived['all_time_trophies'] = get_all_time_trophy_table(campaign_id)
                archived['global_power_rankings'] = get_global_power_rankings(campaign_id)

                if 'titles' not in archived:
                    archived['titles'] = {}
                arch_ko = archived['titles'].get('kickoff', {})
                missing_ko = [r for r in ['pacific', 'americas', 'emea', 'china'] if r not in arch_ko or not arch_ko[r]]
                if missing_ko:
                    repaired_ko = _extract_kickoff_titles(campaign_id, target_year)
                    if repaired_ko:
                        arch_ko.update(repaired_ko)
                        archived['titles']['kickoff'] = arch_ko

                # Load stage placements for this year
                stage_placements = {}
                for sk in ('kickoff', 'major', 'stage1', 'master', 'ewc', 'stage2', 'champion'):
                    stage_placements[sk] = get_stage_placements_history(campaign_id, sk, year=target_year)
                archived['stage_placements'] = stage_placements
                return archived
            except Exception:
                pass

    year = target_year
    titles = {}

    # 1. Kickoff Regional Winners
    titles['kickoff'] = _extract_kickoff_titles(campaign_id, year)

    # 2. Masters Bangkok (Major)
    m_stage = get_stage_record(campaign_id, 'major', year=year)
    m_champ = None
    m_ru = None
    if m_stage and m_stage.stage_data:
        try:
            m_data = json.loads(m_stage.stage_data)
            m_res = m_data.get('result', {})
            m_champ = m_res.get('champion')
            m_ru = m_res.get('runner_up')
        except Exception:
            pass
    if not m_champ:
        p1 = CampaignStagePlacement.query.filter_by(campaign_id=campaign_id, year=year, stage_key='major', rank=1).first()
        if p1 and p1.club:
            m_champ = p1.club.to_dict()
    if not m_ru:
        p2 = CampaignStagePlacement.query.filter_by(campaign_id=campaign_id, year=year, stage_key='major', rank=2).first()
        if p2 and p2.club:
            m_ru = p2.club.to_dict()
    hosts = get_season_hosts(campaign_id, target_year)
    titles['major'] = {'champion': m_champ, 'runner_up': m_ru, 'host_city': (json.loads(m_stage.stage_data).get('host_city') if (m_stage and m_stage.stage_data) else None) or hosts.get('major')}

    # 3. Stage 1 Regional Winners
    s1_stage = get_stage_record(campaign_id, 'stage1', year=year)
    s1_titles = {}
    if s1_stage and s1_stage.stage_data:
        try:
            s1_data = json.loads(s1_stage.stage_data)
            s1_reg = s1_data.get('regional_results', {})
            for r in ['pacific', 'americas', 'emea', 'china']:
                reg_d = s1_reg.get(r, {})
                champ = reg_d.get('champion')
                if not champ and reg_d.get('standings'):
                    champ = reg_d['standings'][0].get('team')
                if champ:
                    s1_titles[r] = champ
        except Exception:
            pass
    for r in ['pacific', 'americas', 'emea', 'china']:
        if r not in s1_titles:
            p = CampaignStagePlacement.query.filter_by(
                campaign_id=campaign_id, year=year, stage_key='stage1', region_slug=r, rank=1
            ).first()
            if p and p.club:
                s1_titles[r] = p.club.to_dict()
    titles['stage1'] = s1_titles

    # 4. Masters Toronto (Master)
    mt_stage = get_stage_record(campaign_id, 'master', year=year)
    mt_champ = None
    mt_ru = None
    if mt_stage and mt_stage.stage_data:
        try:
            mt_data = json.loads(mt_stage.stage_data)
            mt_res = mt_data.get('result', {})
            mt_champ = mt_res.get('champion')
            mt_ru = mt_res.get('runner_up')
        except Exception:
            pass
    if not mt_champ:
        p1 = CampaignStagePlacement.query.filter_by(campaign_id=campaign_id, year=year, stage_key='master', rank=1).first()
        if p1 and p1.club:
            mt_champ = p1.club.to_dict()
    if not mt_ru:
        p2 = CampaignStagePlacement.query.filter_by(campaign_id=campaign_id, year=year, stage_key='master', rank=2).first()
        if p2 and p2.club:
            mt_ru = p2.club.to_dict()
    titles['master'] = {'champion': mt_champ, 'runner_up': mt_ru, 'host_city': (json.loads(mt_stage.stage_data).get('host_city') if (mt_stage and mt_stage.stage_data) else None) or hosts.get('master')}

    # 5. Esports World Cup (EWC)
    ewc_stage = get_stage_record(campaign_id, 'ewc', year=year)
    ewc_champ = None
    ewc_ru = None
    ewc_3rd = None
    if ewc_stage and ewc_stage.stage_data:
        try:
            ewc_data = json.loads(ewc_stage.stage_data)
            ewc_res = ewc_data.get('result', {})
            ewc_champ = ewc_res.get('champion')
            ewc_ru = ewc_res.get('runner_up')
            ewc_3rd = ewc_res.get('third_place')
        except Exception:
            pass
    if not ewc_champ:
        p1 = CampaignStagePlacement.query.filter_by(campaign_id=campaign_id, year=year, stage_key='ewc', rank=1).first()
        if p1 and p1.club:
            ewc_champ = p1.club.to_dict()
    if not ewc_ru:
        p2 = CampaignStagePlacement.query.filter_by(campaign_id=campaign_id, year=year, stage_key='ewc', rank=2).first()
        if p2 and p2.club:
            ewc_ru = p2.club.to_dict()
    titles['ewc'] = {'champion': ewc_champ, 'runner_up': ewc_ru, 'third_place': ewc_3rd, 'host_city': (json.loads(ewc_stage.stage_data).get('host_city') if (ewc_stage and ewc_stage.stage_data) else None) or hosts.get('ewc')}

    # 6. Stage 2 Regional Winners
    s2_stage = get_stage_record(campaign_id, 'stage2', year=year)
    s2_titles = {}
    if s2_stage and s2_stage.stage_data:
        try:
            s2_data = json.loads(s2_stage.stage_data)
            s2_reg = s2_data.get('regional_results', {})
            for r in ['pacific', 'americas', 'emea', 'china']:
                reg_d = s2_reg.get(r, {})
                champ = reg_d.get('champion')
                if not champ and reg_d.get('standings'):
                    champ = reg_d['standings'][0].get('team')
                if champ:
                    s2_titles[r] = champ
        except Exception:
            pass
    for r in ['pacific', 'americas', 'emea', 'china']:
        if r not in s2_titles:
            p = CampaignStagePlacement.query.filter_by(
                campaign_id=campaign_id, year=year, stage_key='stage2', region_slug=r, rank=1
            ).first()
            if p and p.club:
                s2_titles[r] = p.club.to_dict()
    titles['stage2'] = s2_titles

    # 7. VALORANT Champions Paris
    ch_stage = get_stage_record(campaign_id, 'champion', year=year)
    ch_champ = None
    ch_ru = None
    ch_3rd = None
    ch_4th = None
    if ch_stage and ch_stage.stage_data:
        try:
            ch_data = json.loads(ch_stage.stage_data)
            ch_res = ch_data.get('result', {})
            ch_champ = ch_res.get('champion')
            ch_ru = ch_res.get('runner_up')
            ch_3rd = ch_res.get('third_place')
            ch_4th = ch_res.get('fourth_place')
        except Exception:
            pass
    if not ch_champ:
        p1 = CampaignStagePlacement.query.filter_by(campaign_id=campaign_id, year=year, stage_key='champion', rank=1).first()
        if p1 and p1.club:
            ch_champ = p1.club.to_dict()
    if not ch_ru:
        p2 = CampaignStagePlacement.query.filter_by(campaign_id=campaign_id, year=year, stage_key='champion', rank=2).first()
        if p2 and p2.club:
            ch_ru = p2.club.to_dict()
    titles['champion'] = {
        'champion': ch_champ,
        'runner_up': ch_ru,
        'third_place': ch_3rd,
        'fourth_place': ch_4th,
        'host_city': (json.loads(ch_stage.stage_data).get('host_city') if (ch_stage and ch_stage.stage_data) else None) or hosts.get('champion'),
    }

    # Leaderboards
    leaderboards = {
        r: get_championship_leaderboard(campaign_id, region_slug=r)
        for r in ['pacific', 'americas', 'emea', 'china']
    }

    # Accolades
    world_champion = titles.get('champion', {}).get('champion')

    # Club of the Year: Club with highest Championship Points (and international title bonus)
    all_clubs_states = CampaignClubState.query.filter_by(campaign_id=campaign_id).all()
    best_club_state = max(all_clubs_states, key=lambda cs: (cs.championship_points or 0, cs.story_rating or 0)) if all_clubs_states else None

    # Best Region: Region with highest total CP
    region_totals = {}
    for r, lb in leaderboards.items():
        region_totals[r] = sum(t.get('championship_points', 0) for t in lb)
    best_region_slug = max(region_totals.keys(), key=lambda r: region_totals[r]) if region_totals else 'pacific'

    # Most Improved Club: Club with highest story rating
    most_improved_state = max(all_clubs_states, key=lambda cs: cs.story_rating or 0) if all_clubs_states else None

    # Previous Hall of Fame history
    hof_stages = CampaignStage.query.filter(
        CampaignStage.campaign_id == campaign_id,
        CampaignStage.stage_key.like('hof_year_%')
    ).order_by(CampaignStage.year.asc()).all()

    past_records = []
    for h in hof_stages:
        try:
            past_records.append(json.loads(h.stage_data))
        except Exception:
            pass

    # Stage placements for this year
    stage_placements = {}
    for sk in ('kickoff', 'major', 'stage1', 'master', 'ewc', 'stage2', 'champion'):
        stage_placements[sk] = get_stage_placements_history(campaign_id, sk, year=year)

    return {
        'year': year,
        'available_years': available_years,
        'titles': titles,
        'world_champion': world_champion,
        'club_of_the_year': {
            'club': best_club_state.club.to_dict() if best_club_state and best_club_state.club else None,
            'cp': best_club_state.championship_points if best_club_state else 0,
            'rating': best_club_state.story_rating if best_club_state else 80,
        } if best_club_state else None,
        'best_region': {
            'region_slug': best_region_slug,
            'total_cp': region_totals.get(best_region_slug, 0),
        },
        'most_improved': {
            'club': most_improved_state.club.to_dict() if most_improved_state and most_improved_state.club else None,
            'rating': most_improved_state.story_rating if most_improved_state else 80,
        } if most_improved_state else None,
        'leaderboards': leaderboards,
        'past_records': past_records,
        'all_time_trophies': get_all_time_trophy_table(campaign_id),
        'global_power_rankings': get_global_power_rankings(campaign_id),
        'stage_placements': stage_placements,
        'season_hosts': hosts,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Multi-Year Campaign Rollover (Advance to Next Season)
# ─────────────────────────────────────────────────────────────────────────────

def advance_campaign_to_next_year(campaign_id: int) -> Dict[str, Any]:
    """Advance campaign to Year N+1:
    - Archive current season summary into Hall of Fame
    - Increment current_year
    - Reset current_stage to 'open_qualifier'
    - Age ratings with mean regression (carryover) and reset seasonal points
    - Initialize next year's Open Qualifier
    """
    campaign = get_campaign(campaign_id)
    if not campaign:
        raise ValueError(f"Campaign {campaign_id} not found")

    old_year = campaign.current_year
    backfill_stage_placements_if_needed(campaign.id)
    recalculate_campaign_gpr(campaign.id)
    summary_data = get_season_summary_data(campaign_id)

    # 1. Archive to permanent Hall of Fame stage record
    hof_stage = CampaignStage.query.filter_by(
        campaign_id=campaign.id, year=old_year, stage_key=f'hof_year_{old_year}'
    ).first()
    if not hof_stage:
        hof_stage = CampaignStage(
            campaign_id=campaign.id,
            year=old_year,
            stage_key=f'hof_year_{old_year}',
            stage_name=f'Hall of Fame {old_year}',
            status='completed',
            stage_data=json.dumps(summary_data),
            completed_at=datetime.now(timezone.utc),
        )
        db.session.add(hof_stage)

    # 1b. Archive to CampaignSeason history table
    season_rec = CampaignSeason.query.filter_by(campaign_id=campaign.id, year=old_year).first()
    if not season_rec:
        titles = summary_data.get('titles', {})
        major_champ = titles.get('major', {}).get('champion')
        master_champ = titles.get('master', {}).get('champion')
        ewc_champ = titles.get('ewc', {}).get('champion')
        champ_champ = titles.get('champion', {}).get('champion')

        def _extract_cid(team_dict):
            if not team_dict:
                return None
            return team_dict.get('id') or team_dict.get('club_id')

        mvp_state = summary_data.get('accolades', {}).get('club_of_the_year')
        mvp_cid = mvp_state.get('club_id') if mvp_state else None

        season_rec = CampaignSeason(
            campaign_id=campaign.id,
            year=old_year,
            major_winner_id=_extract_cid(major_champ),
            master_winner_id=_extract_cid(master_champ),
            ewc_winner_id=_extract_cid(ewc_champ),
            champion_winner_id=_extract_cid(champ_champ),
            mvp_club_id=mvp_cid,
            recap_data=json.dumps(summary_data),
            completed_at=datetime.now(timezone.utc),
        )
        db.session.add(season_rec)

    # 2. Advance year and stage
    campaign.current_year = old_year + 1
    campaign.current_stage = 'open_qualifier'
    if campaign.name:
        import re
        campaign.name = re.sub(r'\b20\d\d\b', str(campaign.current_year), campaign.name)

    # 3. Off-season rating aging & CP reset & Power Rating Carryover
    club_states = CampaignClubState.query.filter_by(campaign_id=campaign.id).all()

    # Assign previous_rank based on season-end power scores
    sorted_cs = sorted(club_states, key=lambda x: (x.power_score if x.power_score is not None else 1500.0, x.championship_points or 0), reverse=True)
    for idx, cstate in enumerate(sorted_cs, start=1):
        cstate.previous_rank = idx

    for cs in club_states:
        # 15% regression toward base 80
        curr_r = cs.story_rating or 80
        cs.story_rating = max(60, min(99, int(round(curr_r * 0.85 + 80 * 0.15))))
        cs.form_modifier = 0
        cs.championship_points = 0
        cs.regular_season_wins = 0
        cs.map_differential = 0
        cs.round_differential = 0
        cs.stage_ranks = '{}'

        # Power Rating Off-season Regression (20% decay towards mean 1500 Elo)
        cur_elo = cs.team_elo if cs.team_elo is not None else 1500.0
        cs.team_elo = apply_offseason_regression(cur_elo)
        cs.win_streak = 0
        cs.power_score = calculate_composite_power_score(cs.team_elo, 1500.0, 0)
        cs.power_rating = power_score_to_ovr(cs.power_score)

    # 4. Initialize new year Open Qualifier
    new_oq_stage = CampaignStage(
        campaign_id=campaign.id,
        year=campaign.current_year,
        stage_key='open_qualifier',
        stage_name=f'Open Qualifier {campaign.current_year}',
        status='in_progress',
        stage_data=json.dumps({'regions': {}}),
    )
    db.session.add(new_oq_stage)
    db.session.flush()

    init_campaign_open_qualifier(campaign.id)

    # 4b. Draw and persist new year's host cities with 5-year cooldown
    from engine.host_cities import pick_season_hosts
    saved_hosts_map = {}
    if getattr(campaign, 'season_hosts', None):
        try:
            saved_hosts_map = json.loads(campaign.season_hosts)
        except Exception:
            saved_hosts_map = {}
    new_hosts = pick_season_hosts(campaign.current_year, seed=None, history_hosts=saved_hosts_map)
    saved_hosts_map[str(campaign.current_year)] = new_hosts
    campaign.season_hosts = json.dumps(saved_hosts_map)

    db.session.commit()
    return {
        'success': True,
        'old_year': old_year,
        'new_year': campaign.current_year,
        'new_stage': campaign.current_stage,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Tournament Historical Placements & Riot Global Power Rankings (GPR x AWS)
# ─────────────────────────────────────────────────────────────────────────────

def _get_rank_display(rank: int) -> str:
    """Format human-readable rank display string."""
    if rank == 1:
        return '1st (Vô địch)'
    elif rank == 2:
        return '2nd (Á quân)'
    elif rank == 3:
        return '3rd (Hạng 3)'
    elif rank == 4:
        return '4th (Hạng 4)'
    elif rank in (5, 6):
        return '5th - 6th'
    elif rank in (7, 8):
        return '7th - 8th'
    elif 9 <= rank <= 12:
        return '9th - 12th'
    elif 13 <= rank <= 16:
        return '13th - 16th'
    return f'#{rank}'


def apply_match_power_rating(
    campaign_id: int,
    winner_id: int,
    loser_id: int,
    tournament_tier: str = 'default',
    map_diff: int = 1,
    round_diff: int = 4,
    is_intl: bool = False,
    region_winner: Optional[str] = None,
    region_loser: Optional[str] = None
) -> Dict[str, Any]:
    """Update team Elo and regional league Elo after any match in campaign mode."""
    campaign = get_campaign(campaign_id)
    if not campaign:
        return {}

    w_state = CampaignClubState.query.filter_by(campaign_id=campaign_id, club_id=winner_id).first()
    l_state = CampaignClubState.query.filter_by(campaign_id=campaign_id, club_id=loser_id).first()
    if not w_state or not l_state:
        return {}

    w_elo = w_state.team_elo if w_state.team_elo is not None else 1500.0
    l_elo = l_state.team_elo if l_state.team_elo is not None else 1500.0

    new_w_elo, new_l_elo, delta = update_team_elo(
        rating_winner=w_elo,
        rating_loser=l_elo,
        tournament_tier=tournament_tier,
        map_diff=map_diff,
        round_diff=round_diff,
    )
    w_state.team_elo = new_w_elo
    l_state.team_elo = new_l_elo

    # Update win streak
    w_state.win_streak = (w_state.win_streak or 0) + 1 if (w_state.win_streak or 0) >= 0 else 1
    l_state.win_streak = (l_state.win_streak or 0) - 1 if (l_state.win_streak or 0) <= 0 else -1

    # League Elo for international tournaments
    league_ratings = {"pacific": 1500.0, "americas": 1500.0, "emea": 1500.0, "china": 1500.0}
    try:
        if campaign.league_ratings:
            league_ratings = json.loads(campaign.league_ratings)
    except Exception:
        pass

    if is_intl and region_winner and region_loser and region_winner != region_loser:
        league_ratings, _ = update_regional_league_elo(
            league_ratings, region_winner, region_loser, tournament_tier=tournament_tier
        )
        campaign.league_ratings = json.dumps(league_ratings)

    reg_w = region_winner or (w_state.club.region.slug if w_state.club and w_state.club.region else 'pacific')
    reg_l = region_loser or (l_state.club.region.slug if l_state.club and l_state.club.region else 'pacific')

    l_elo_w = league_ratings.get(reg_w, 1500.0)
    l_elo_l = league_ratings.get(reg_l, 1500.0)

    w_state.power_score = calculate_composite_power_score(w_state.team_elo, l_elo_w, w_state.win_streak)
    w_state.power_rating = power_score_to_ovr(w_state.power_score)

    l_state.power_score = calculate_composite_power_score(l_state.team_elo, l_elo_l, l_state.win_streak)
    l_state.power_rating = power_score_to_ovr(l_state.power_score)

    return {
        'winner_id': winner_id,
        'loser_id': loser_id,
        'delta_elo': delta,
        'winner_power_score': w_state.power_score,
        'loser_power_score': l_state.power_score,
    }


def _extract_all_matches_from_stage(stage_key: str, stage_data: Dict[str, Any]) -> List[Tuple[str, Dict[str, Any]]]:
    """Extract all matches from a stage in chronological order (regular/groups then playoffs)."""
    matches = []
    if not stage_data or not isinstance(stage_data, dict):
        return matches

    # 1. Regional qualifier stages
    if stage_key in ['open_qualifier', 'oq_stage1', 'oq_stage2', 'ewc_qualifier']:
        reg_map = stage_data.get('regions', {})
        if isinstance(reg_map, dict):
            for r_slug, r_data in reg_map.items():
                if not isinstance(r_data, dict):
                    continue
                for k in ['swiss_matches', 'phase1_matches', 'phase2_matches', 'matches']:
                    for m in r_data.get(k, []):
                        if isinstance(m, dict):
                            matches.append(('regular', m))
                for m in r_data.get('playoff_matches', []):
                    if isinstance(m, dict):
                        matches.append(('playoff', m))

    # 2. Main regional circuits (kickoff, stage1, stage2)
    elif stage_key in ['kickoff', 'stage1', 'stage2']:
        reg_map = stage_data.get('regional_results', {})
        if isinstance(reg_map, dict):
            for r_slug, r_data in reg_map.items():
                if not isinstance(r_data, dict):
                    continue
                for k in ['regular_matches', 'alpha_matches', 'omega_matches', 'matches']:
                    for m in r_data.get(k, []):
                        if isinstance(m, dict):
                            matches.append(('regular', m))
                for m in r_data.get('playoff_matches', []):
                    if isinstance(m, dict):
                        matches.append(('playoff', m))

    # 3. International tournaments (major, master, ewc, champion)
    elif stage_key in ['major', 'master', 'ewc', 'champion']:
        res = stage_data.get('result', stage_data)
        if isinstance(res, dict):
            for k in ['swiss_matches', 'group_matches', 'matches']:
                for m in res.get(k, []):
                    if isinstance(m, dict):
                        matches.append(('regular', m))
            for k in ['playoff_matches', 'bracket_matches']:
                for m in res.get(k, []):
                    if isinstance(m, dict):
                        matches.append(('playoff', m))

    return matches


def recalculate_campaign_gpr(campaign_id: int) -> List[Dict[str, Any]]:
    """Comprehensively recalculate dynamic Elo, win/loss streaks, power scores, and rank deltas
    for all 48 clubs across all played matches, placements, and story development in the campaign.
    """
    campaign = get_campaign(campaign_id)
    if not campaign:
        return []

    backfill_stage_placements_if_needed(campaign_id)

    club_states = CampaignClubState.query.filter_by(campaign_id=campaign_id).all()
    if not club_states:
        return []

    clubs = {c.id: c for c in Club.query.all()}
    club_region_map = {c.id: (c.region.slug if c.region else 'pacific') for c in clubs.values()}

    # Initialize ratings from base rating
    team_elo_map = {}
    win_streak_map = {}
    for cs in club_states:
        c = clubs.get(cs.club_id)
        base_r = float(c.base_rating or 75.0) if c else 75.0
        team_elo_map[cs.club_id] = base_r * 18.75
        win_streak_map[cs.club_id] = 0

    # Initial baseline ranking (pre-season snapshot)
    baseline_ranked = sorted(
        club_states,
        key=lambda s: team_elo_map.get(s.club_id, 1500.0),
        reverse=True
    )
    previous_stage_ranks = {cs.club_id: idx for idx, cs in enumerate(baseline_ranked, start=1)}

    league_ratings = {"pacific": 1500.0, "americas": 1500.0, "emea": 1500.0, "china": 1500.0}
    try:
        if campaign.league_ratings:
            parsed = json.loads(campaign.league_ratings)
            if isinstance(parsed, dict) and all(k in parsed for k in ['pacific', 'americas', 'emea', 'china']):
                league_ratings = parsed
    except Exception:
        pass

    STAGE_CHRONOLOGY = [
        'open_qualifier', 'kickoff', 'major',
        'oq_stage1', 'stage1', 'ewc_qualifier',
        'master', 'ewc',
        'oq_stage2', 'stage2', 'champion'
    ]

    all_stages = CampaignStage.query.filter_by(campaign_id=campaign_id).all()
    # Sort stages by year, then by STAGE_CHRONOLOGY order
    sorted_stages = sorted(
        all_stages,
        key=lambda s: (
            s.year,
            STAGE_CHRONOLOGY.index(s.stage_key) if s.stage_key in STAGE_CHRONOLOGY else 99,
            s.id
        )
    )

    stages_with_matches_played = 0

    for st in sorted_stages:
        if not st.stage_data:
            continue
        try:
            st_data = json.loads(st.stage_data)
        except Exception:
            continue

        matches_with_meta = _extract_all_matches_from_stage(st.stage_key, st_data)
        completed_stage_matches = []
        for tag, m in matches_with_meta:
            w_id = m.get('winner_id') or (m.get('winner', {}).get('id') if isinstance(m.get('winner'), dict) else None)
            ta_id = m.get('team_a_id') or (m.get('team_a', {}).get('id') if isinstance(m.get('team_a'), dict) else None)
            tb_id = m.get('team_b_id') or (m.get('team_b', {}).get('id') if isinstance(m.get('team_b'), dict) else None)
            if not w_id:
                sa = m.get('team_a_score', 0)
                sb = m.get('team_b_score', 0)
                if sa is not None and sb is not None and (sa > 0 or sb > 0) and sa != sb:
                    w_id = ta_id if sa > sb else tb_id
            if w_id and ta_id and tb_id and ta_id != tb_id:
                completed_stage_matches.append((tag, m, w_id, ta_id, tb_id))

        if not completed_stage_matches:
            continue

        stages_with_matches_played += 1

        # Snapshot ranks before this stage executes
        temp_ranked = sorted(
            club_states,
            key=lambda s: (
                calculate_composite_power_score(
                    team_elo_map.get(s.club_id, 1500.0),
                    league_ratings.get(club_region_map.get(s.club_id, 'pacific'), 1500.0),
                    win_streak_map.get(s.club_id, 0)
                ),
                s.championship_points or 0
            ),
            reverse=True
        )
        pre_stage_ranks = {s.club_id: idx for idx, s in enumerate(temp_ranked, start=1)}

        for tag, m, w_id, ta_id, tb_id in completed_stage_matches:
            l_id = tb_id if w_id == ta_id else ta_id
            sa = m.get('team_a_score', 0) or 0
            sb = m.get('team_b_score', 0) or 0
            w_score = sa if w_id == ta_id else sb
            l_score = sb if w_id == ta_id else sa
            map_diff = max(1, w_score - l_score)
            round_diff = m.get('round_diff') or (map_diff * 4)

            tier = st.stage_key
            if 'playoff' in tag.lower() and st.stage_key in ('stage1', 'stage2'):
                tier = f'{st.stage_key}_playoffs'

            cur_w = team_elo_map.get(w_id, 1500.0)
            cur_l = team_elo_map.get(l_id, 1500.0)
            nw, nl, delta = update_team_elo(
                cur_w, cur_l,
                tournament_tier=tier,
                map_diff=map_diff,
                round_diff=round_diff
            )
            team_elo_map[w_id] = nw
            team_elo_map[l_id] = nl

            sw = win_streak_map.get(w_id, 0)
            sl = win_streak_map.get(l_id, 0)
            win_streak_map[w_id] = (sw + 1) if sw >= 0 else 1
            win_streak_map[l_id] = (sl - 1) if sl <= 0 else -1

            reg_w = club_region_map.get(w_id, 'pacific')
            reg_l = club_region_map.get(l_id, 'pacific')
            if st.stage_key in ('major', 'master', 'ewc', 'champion') and reg_w != reg_l:
                league_ratings, _ = update_regional_league_elo(
                    league_ratings, reg_w, reg_l, tournament_tier=st.stage_key
                )

        # Apply prestige bonuses for this stage's official placements
        st_placements = CampaignStagePlacement.query.filter_by(
            campaign_id=campaign_id, stage_key=st.stage_key, year=st.year
        ).all()
        for p in st_placements:
            bonus = 0.0
            if p.stage_key == 'champion':
                bonus = 120.0 if p.rank == 1 else (60.0 if p.rank == 2 else (30.0 if p.rank <= 4 else 0.0))
            elif p.stage_key == 'master':
                bonus = 90.0 if p.rank == 1 else (45.0 if p.rank == 2 else (20.0 if p.rank <= 4 else 0.0))
            elif p.stage_key == 'major':
                bonus = 80.0 if p.rank == 1 else (40.0 if p.rank == 2 else (15.0 if p.rank <= 4 else 0.0))
            elif p.stage_key == 'ewc':
                bonus = 70.0 if p.rank == 1 else (35.0 if p.rank == 2 else (15.0 if p.rank <= 4 else 0.0))
            elif p.stage_key in ('kickoff', 'stage1', 'stage2'):
                bonus = 40.0 if p.rank == 1 else (20.0 if p.rank == 2 else 0.0)

            if bonus > 0 and p.club_id in team_elo_map:
                team_elo_map[p.club_id] = round(team_elo_map[p.club_id] + bonus, 1)

        # Update previous stage ranks
        previous_stage_ranks = pre_stage_ranks

    # Synchronize Story Rating development gains
    for cs in club_states:
        c = clubs.get(cs.club_id)
        base_r = float(c.base_rating or 75.0) if c else 75.0
        sr = float(cs.story_rating or base_r)
        if sr > base_r:
            team_elo_map[cs.club_id] = round(team_elo_map[cs.club_id] + (sr - base_r) * 6.0, 1)
        elif sr < base_r:
            team_elo_map[cs.club_id] = round(team_elo_map[cs.club_id] - (base_r - sr) * 4.0, 1)

    # Persist updated values into CampaignClubState
    results = []
    for cs in club_states:
        cid = cs.club_id
        c = clubs.get(cid)
        reg = club_region_map.get(cid, 'pacific')
        le = league_ratings.get(reg, 1500.0)
        t_elo = team_elo_map.get(cid, 1500.0)
        streak = win_streak_map.get(cid, 0)
        ps = calculate_composite_power_score(t_elo, le, streak)
        ovr = power_score_to_ovr(ps)

        cs.team_elo = round(t_elo, 1)
        cs.win_streak = streak
        cs.power_score = round(ps, 1)
        cs.power_rating = round(ovr, 1)
        if stages_with_matches_played > 0:
            cs.previous_rank = previous_stage_ranks.get(cid)

        results.append({
            'club': c.to_dict() if c else {'id': cid},
            'power_score': cs.power_score,
            'power_rating': cs.power_rating,
            'team_elo': cs.team_elo,
            'win_streak': cs.win_streak,
            'championship_points': cs.championship_points or 0,
            'tier': get_tier_info(cs.power_score),
            'previous_rank': cs.previous_rank,
        })

    campaign.league_ratings = json.dumps(league_ratings)
    db.session.commit()

    # Sort descending by power_score and championship_points
    results.sort(key=lambda x: (x['power_score'], x['championship_points']), reverse=True)
    for idx, item in enumerate(results, start=1):
        item['rank'] = idx
        item['rank_delta'] = format_rank_delta(idx, item['previous_rank'])

    return results


def record_stage_placements(campaign_id: int, stage_key: str, year: Optional[int] = None) -> List[Dict[str, Any]]:
    """Extract and persist official final placements for all participating teams in a stage."""
    campaign = get_campaign(campaign_id)
    if not campaign:
        return []

    target_year = year or campaign.current_year
    stage = get_stage_record(campaign_id, stage_key, year=target_year)
    if not stage or not stage.stage_data:
        return []

    try:
        data = json.loads(stage.stage_data)
    except Exception:
        return []

    club_states = {cs.club_id: cs for cs in CampaignClubState.query.filter_by(campaign_id=campaign_id).all()}
    records = []

    def _save_placement(cid, rank, r_slug, tour_name, elim_stage, cp, m_won, m_lost):
        if not cid:
            return
        cs = club_states.get(cid)
        p_score = cs.power_score if cs and cs.power_score is not None else 1500.0
        p_rating = cs.power_rating if cs and cs.power_rating is not None else 80.0

        existing = CampaignStagePlacement.query.filter_by(
            campaign_id=campaign_id,
            year=target_year,
            stage_key=stage_key,
            club_id=cid,
        ).first()

        rank_d = _get_rank_display(rank)
        if not existing:
            rec = CampaignStagePlacement(
                campaign_id=campaign_id,
                year=target_year,
                stage_key=stage_key,
                tournament_name=tour_name,
                region_slug=r_slug,
                club_id=cid,
                rank=rank,
                rank_display=rank_d,
                elimination_stage=elim_stage,
                stage_points_earned=cp,
                matches_won=m_won,
                matches_lost=m_lost,
                power_score_snapshot=p_score,
                power_rating_snapshot=p_rating,
            )
            db.session.add(rec)
            records.append(rec)
        else:
            existing.rank = rank
            existing.rank_display = rank_d
            existing.elimination_stage = elim_stage
            existing.stage_points_earned = cp
            existing.matches_won = m_won
            existing.matches_lost = m_lost
            existing.power_score_snapshot = p_score
            existing.power_rating_snapshot = p_rating
            existing.tournament_name = tour_name
            existing.region_slug = r_slug
            records.append(existing)

    # 1. KICKOFF
    if stage_key == 'kickoff':
        for r_slug, reg_data in data.get('regional_results', {}).items():
            tour_name = f"VCT Kickoff {r_slug.upper()} {target_year}"
            for s in reg_data.get('standings', []):
                cid = s.get('club_id') or (s.get('team', {}).get('id') if isinstance(s.get('team'), dict) else None)
                rk = s.get('rank', 1)
                cp = get_stage_points('kickoff', rank=rk)
                w = s.get('matches_won', s.get('wins', 0))
                l = s.get('matches_lost', s.get('losses', 0))
                _save_placement(cid, rk, r_slug, tour_name, s.get('elimination_stage', ''), cp, w, l)

    # 2. MAJOR
    elif stage_key == 'major':
        hosts = get_season_hosts(campaign_id, target_year)
        m_city = (data.get('host_city') or {}).get('city_name') or (hosts.get('major') or {}).get('city_name', 'Tokyo')
        tour_name = f"VCT Major {m_city} {target_year}"
        res = data.get('result', {})
        for s in res.get('standings', []):
            cid = s.get('club_id') or (s.get('team', {}).get('id') if isinstance(s.get('team'), dict) else None)
            rk = s.get('rank', 1)
            cp = get_stage_points('major', rank=rk)
            w = s.get('matches_won', s.get('wins', 0))
            l = s.get('matches_lost', s.get('losses', 0))
            reg = s.get('region') or (s.get('team', {}).get('region') if isinstance(s.get('team'), dict) else None)
            _save_placement(cid, rk, reg, tour_name, s.get('elimination_stage', ''), cp, w, l)

    # 3. STAGE 1 & STAGE 2
    elif stage_key in ('stage1', 'stage2'):
        prefix = "Stage 1" if stage_key == 'stage1' else "Stage 2"
        for r_slug, reg_data in data.get('regional_results', {}).items():
            tour_name = f"VCT {prefix} {r_slug.upper()} {target_year}"
            playoff_standings = reg_data.get('standings', [])
            playoff_cids = set()

            # Record playoff teams (rank 1..6)
            for s in playoff_standings:
                cid = s.get('club_id') or (s.get('team', {}).get('id') if isinstance(s.get('team'), dict) else None)
                if not cid:
                    continue
                playoff_cids.add(cid)
                rk = s.get('rank', 1)
                reg_wins = s.get('regular_wins', s.get('wins', 0))
                playoff_cp = get_stage_points(f'{stage_key}_playoffs', rank=rk)
                cp_total = playoff_cp + reg_wins
                w = s.get('matches_won', s.get('wins', 0))
                l = s.get('matches_lost', s.get('losses', 0))
                _save_placement(cid, rk, r_slug, tour_name, s.get('elimination_stage', 'Playoffs'), cp_total, w, l)

            # Record non-playoff regular season teams (rank 7..12)
            alpha = reg_data.get('alpha_standings', [])
            omega = reg_data.get('omega_standings', [])
            non_playoffs = [team for team in (alpha + omega) if team.get('club_id') not in playoff_cids]
            non_playoffs.sort(key=lambda t: (t.get('wins', 0), t.get('map_diff', 0), t.get('round_diff', 0)), reverse=True)

            curr_rank = 7
            for team in non_playoffs:
                cid = team.get('club_id')
                w = team.get('wins', 0)
                l = team.get('losses', 0)
                cp = w  # 1 CP per regular win
                _save_placement(cid, curr_rank, r_slug, tour_name, 'Group Stage', cp, w, l)
                curr_rank += 1

    # 4. MASTER
    elif stage_key == 'master':
        hosts = get_season_hosts(campaign_id, target_year)
        mt_city = (data.get('host_city') or {}).get('city_name') or (hosts.get('master') or {}).get('city_name', 'Madrid')
        tour_name = f"VCT Masters {mt_city} {target_year}"
        res = data.get('result', {})
        for s in res.get('standings', []):
            cid = s.get('club_id') or (s.get('team', {}).get('id') if isinstance(s.get('team'), dict) else None)
            rk = s.get('rank', 1)
            cp = get_stage_points('master', rank=rk)
            w = s.get('matches_won', s.get('wins', 0))
            l = s.get('matches_lost', s.get('losses', 0))
            reg = s.get('region') or (s.get('team', {}).get('region') if isinstance(s.get('team'), dict) else None)
            _save_placement(cid, rk, reg, tour_name, s.get('elimination_stage', ''), cp, w, l)

    # 5. EWC
    elif stage_key == 'ewc':
        hosts = get_season_hosts(campaign_id, target_year)
        ewc_city = (data.get('host_city') or {}).get('city_name') or (hosts.get('ewc') or {}).get('city_name', 'Riyadh')
        tour_name = f"Esports World Cup {ewc_city} {target_year}"
        res = data.get('result', {})
        for s in res.get('standings', []):
            cid = s.get('club_id') or (s.get('team', {}).get('id') if isinstance(s.get('team'), dict) else None)
            rk = s.get('rank', 1)
            w = s.get('matches_won', s.get('wins', 0))
            l = s.get('matches_lost', s.get('losses', 0))
            reg = s.get('region') or (s.get('team', {}).get('region') if isinstance(s.get('team'), dict) else None)
            _save_placement(cid, rk, reg, tour_name, s.get('elimination_stage', ''), 0, w, l)

    # 6. CHAMPION
    elif stage_key == 'champion':
        hosts = get_season_hosts(campaign_id, target_year)
        ch_city = (data.get('host_city') or {}).get('city_name') or (hosts.get('champion') or {}).get('city_name', 'Seoul')
        tour_name = f"VALORANT Champions {ch_city} {target_year}"
        res = data.get('result', {})
        for s in res.get('standings', []):
            cid = s.get('club_id') or (s.get('team', {}).get('id') if isinstance(s.get('team'), dict) else None)
            rk = s.get('rank', 1)
            w = s.get('matches_won', s.get('wins', 0))
            l = s.get('matches_lost', s.get('losses', 0))
            reg = s.get('region') or (s.get('team', {}).get('region') if isinstance(s.get('team'), dict) else None)
            _save_placement(cid, rk, reg, tour_name, s.get('elimination_stage', ''), 0, w, l)

    db.session.flush()
    return [r.to_dict() for r in records]


def backfill_stage_placements_if_needed(campaign_id: int):
    """Scan all existing completed stages in database and backfill historical placements if missing."""
    stages = CampaignStage.query.filter_by(campaign_id=campaign_id, status='completed').all()
    valid_keys = ('kickoff', 'major', 'stage1', 'master', 'ewc', 'stage2', 'champion')

    for st in stages:
        if st.stage_key in valid_keys:
            existing_count = CampaignStagePlacement.query.filter_by(
                campaign_id=campaign_id, year=st.year, stage_key=st.stage_key
            ).count()
            if existing_count == 0:
                record_stage_placements(campaign_id, st.stage_key, year=st.year)

    db.session.commit()


def get_stage_placements_history(
    campaign_id: int,
    stage_key: str,
    year: Optional[int] = None,
    region_slug: Optional[str] = None
) -> Dict[str, Any]:
    """Retrieve historical placements and podium for a tournament across years."""
    backfill_stage_placements_if_needed(campaign_id)

    # Find all available years that have records for this stage_key
    query_years = db.session.query(CampaignStagePlacement.year).filter_by(
        campaign_id=campaign_id, stage_key=stage_key
    ).distinct().order_by(CampaignStagePlacement.year.desc()).all()
    available_years = [y[0] for y in query_years]

    campaign = get_campaign(campaign_id)
    cur_year = campaign.current_year if campaign else 2026
    if not available_years and cur_year not in available_years:
        available_years = [cur_year]

    selected_year = year if (year and year in available_years) else (available_years[0] if available_years else cur_year)

    # Query placements for selected year
    q = CampaignStagePlacement.query.filter_by(
        campaign_id=campaign_id, stage_key=stage_key, year=selected_year
    )
    if region_slug and region_slug != 'all':
        q = q.filter_by(region_slug=region_slug)

    placements = q.order_by(CampaignStagePlacement.rank.asc(), CampaignStagePlacement.matches_won.desc()).all()
    plist = [p.to_dict() for p in placements]

    # Construct Podium (Top 1, Top 2, Top 3)
    podium = {
        'champion': plist[0] if len(plist) >= 1 and plist[0]['rank'] == 1 else None,
        'runner_up': plist[1] if len(plist) >= 2 and plist[1]['rank'] == 2 else None,
        'third_place': plist[2] if len(plist) >= 3 and plist[2]['rank'] == 3 else None,
    }

    return {
        'stage_key': stage_key,
        'available_years': available_years,
        'selected_year': selected_year,
        'region_slug': region_slug,
        'podium': podium,
        'placements': plist,
        'total_teams': len(plist),
    }


def get_all_time_trophy_table(campaign_id: int) -> List[Dict[str, Any]]:
    """Generate all-time medal/trophy room table for all clubs across campaign history."""
    backfill_stage_placements_if_needed(campaign_id)

    clubs = Club.query.all()

    # Query all 1st and 2nd placements
    title_placements = CampaignStagePlacement.query.filter(
        CampaignStagePlacement.campaign_id == campaign_id,
        CampaignStagePlacement.rank.in_([1, 2])
    ).all()

    stats = {c.id: {
        'club': c.to_dict(),
        'champions_titles': 0,
        'major_titles': 0,
        'masters_titles': 0,
        'ewc_titles': 0,
        'regional_titles': 0,
        'total_titles': 0,
        'runner_up_count': 0,
        'total_finals': 0,
    } for c in clubs}

    for p in title_placements:
        cid = p.club_id
        if cid not in stats:
            continue

        if p.rank == 1:
            if p.stage_key == 'champion':
                stats[cid]['champions_titles'] += 1
            elif p.stage_key == 'major':
                stats[cid]['major_titles'] += 1
            elif p.stage_key == 'master':
                stats[cid]['masters_titles'] += 1
            elif p.stage_key == 'ewc':
                stats[cid]['ewc_titles'] += 1
            elif p.stage_key in ('kickoff', 'stage1', 'stage2'):
                stats[cid]['regional_titles'] += 1
            stats[cid]['total_titles'] += 1
            stats[cid]['total_finals'] += 1
        elif p.rank == 2:
            stats[cid]['runner_up_count'] += 1
            stats[cid]['total_finals'] += 1

    # Filter clubs that have at least 1 final appearance
    table = [s for s in stats.values() if s['total_finals'] > 0]
    table.sort(key=lambda s: (
        s['champions_titles'],
        s.get('major_titles', 0),
        s['masters_titles'],
        s['ewc_titles'],
        s['regional_titles'],
        s['total_titles'],
        s['runner_up_count'],
    ), reverse=True)

    return table


def get_global_power_rankings(campaign_id: int, region_slug: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieve full 48-team Riot Global Power Rankings (GPR x AWS) leaderboard with Tier Badges & Delta Rank."""
    club_states = CampaignClubState.query.filter_by(campaign_id=campaign_id).all()

    # Auto-synchronize GPR if any completed stage exists but GPR rankings are uninitialized/frozen
    if club_states:
        all_stages = CampaignStage.query.filter_by(campaign_id=campaign_id).all()
        has_completed_stage = any(s.status == 'completed' for s in all_stages)
        all_zero_streaks = all((cs.win_streak or 0) == 0 for cs in club_states)
        all_no_prev_rank = all(cs.previous_rank is None for cs in club_states)
        if has_completed_stage and (all_zero_streaks or all_no_prev_rank):
            recalculate_campaign_gpr(campaign_id)
            club_states = CampaignClubState.query.filter_by(campaign_id=campaign_id).all()

    items = []
    for cs in club_states:
        c = cs.club
        if not c:
            continue
        c_reg = c.region.slug if c.region else ''
        if region_slug and region_slug != 'all' and c_reg != region_slug:
            continue

        ps = cs.power_score if cs.power_score is not None else 1500.0
        ovr = cs.power_rating if cs.power_rating is not None else power_score_to_ovr(ps)

        items.append({
            'club': c.to_dict(),
            'power_score': round(ps, 1),
            'power_rating': round(ovr, 1),
            'team_elo': round(cs.team_elo if cs.team_elo is not None else 1500.0, 1),
            'win_streak': cs.win_streak or 0,
            'championship_points': cs.championship_points or 0,
            'tier': get_tier_info(ps),
            'previous_rank': cs.previous_rank,
        })

    # Sort descending by power_score
    items.sort(key=lambda x: (x['power_score'], x['championship_points']), reverse=True)

    for idx, item in enumerate(items, start=1):
        item['rank'] = idx
        item['rank_delta'] = format_rank_delta(idx, item['previous_rank'])

    return items


# ─────────────────────────────────────────────────────────────────────────────
# Liquipedia-Style Team Dossier & Career Evaluation
# ─────────────────────────────────────────────────────────────────────────────

TEAM_DNA_MAP = {
    'PRX': {'dna': 'W-Gaming Chaos & Relentless Aggression', 'style': 'Ultra-Aggressive Chaos', 'tempo': 'High-Octane'},
    'GEN': {'dna': 'Disciplined Macro & Methodical Retakes', 'style': 'Strategic Protocol', 'tempo': 'Controlled'},
    'SEN': {'dna': 'Clutch Composure & Star Power Duels', 'style': 'Playmaker Heavy', 'tempo': 'Flexible'},
    'FNC': {'dna': 'Tactical Precision & Utility Synergy', 'style': 'Set-Piece Master', 'tempo': 'Methodical'},
    'EDG': {'dna': 'High-Octane Gunplay & Dynamic Space Creation', 'style': 'Explosive Aim', 'tempo': 'High-Tempo'},
    'DRX': {'dna': 'Calculated Protocol & Fundamental Mastery', 'style': 'Fundamental Setups', 'tempo': 'Controlled'},
    'LEV': {'dna': 'Heavy Firepower & Overwhelming Site Takes', 'style': 'Brawling Dominance', 'tempo': 'Fast'},
    'TH':  {'dna': 'Youthful Fearlessness & Adaptable Execution', 'style': 'Dynamic Flex', 'tempo': 'Adaptive'},
    'LOUD': {'dna': 'Championship Resilience & Defensive Wall', 'style': 'Stifling Defense', 'tempo': 'Methodical'},
    'NRG': {'dna': 'Veterans Composure & Mid-Round Calling', 'style': 'Tactical Mid-Round', 'tempo': 'Measured'},
}

DEFAULT_REGIONAL_DNA = {
    'pacific': {'dna': 'Agile Aggression & Creative Playmaking', 'style': 'Fast & Creative', 'tempo': 'High'},
    'americas': {'dna': 'Raw Firepower & Tenacious Defense', 'style': 'Direct Duelists', 'tempo': 'Balanced'},
    'emea': {'dna': 'Structured Execution & Utility Depth', 'style': 'Tactical Protocol', 'tempo': 'Controlled'},
    'china': {'dna': 'Fast-Paced Tempo & Sharp Mechanical Aim', 'style': 'Explosive Skirmish', 'tempo': 'Blitz'},
}


def _extract_recent_matches_for_club(campaign_id: int, club_id: int, limit: int = 5) -> List[Dict[str, Any]]:
    """Extract recent head-to-head match records for a club across campaign stages."""
    stages = CampaignStage.query.filter_by(campaign_id=campaign_id).order_by(
        CampaignStage.year.desc(), CampaignStage.id.desc()
    ).all()

    found_matches = []
    clubs_cache = {c.id: c for c in Club.query.all()}

    for st in stages:
        if not st.stage_data:
            continue
        try:
            d = json.loads(st.stage_data)
        except Exception:
            continue

        raw_matches = []
        # Search in direct result
        if 'result' in d and isinstance(d['result'], dict):
            res = d['result']
            raw_matches.extend(res.get('matches', []))
            raw_matches.extend(res.get('playoff_matches', []))
            raw_matches.extend(res.get('swiss_matches', []))

        # Search in regional results
        if 'regional_results' in d and isinstance(d['regional_results'], dict):
            for reg_data in d['regional_results'].values():
                if isinstance(reg_data, dict):
                    raw_matches.extend(reg_data.get('matches', []))
                    raw_matches.extend(reg_data.get('playoff_matches', []))
                    raw_matches.extend(reg_data.get('alpha_matches', []))
                    raw_matches.extend(reg_data.get('omega_matches', []))

        for m in reversed(raw_matches):
            if not isinstance(m, dict):
                continue
            ta_id = m.get('team_a_id') or (m.get('team_a', {}).get('id') if isinstance(m.get('team_a'), dict) else None)
            tb_id = m.get('team_b_id') or (m.get('team_b', {}).get('id') if isinstance(m.get('team_b'), dict) else None)
            w_id = m.get('winner_id')

            if club_id in (ta_id, tb_id) and w_id:
                is_win = (w_id == club_id)
                opp_id = tb_id if ta_id == club_id else ta_id
                opp_club = clubs_cache.get(opp_id)

                sa = m.get('team_a_score', 0)
                sb = m.get('team_b_score', 0)
                score_for = sa if ta_id == club_id else sb
                score_against = sb if ta_id == club_id else sa

                found_matches.append({
                    'match_code': m.get('match_code') or m.get('id', ''),
                    'tournament_name': st.stage_name,
                    'stage_key': st.stage_key,
                    'round_name': m.get('round_name') or m.get('round_type') or 'Trận đấu',
                    'is_winner': is_win,
                    'score_display': f"{score_for} - {score_against}",
                    'result_badge': 'W' if is_win else 'L',
                    'opponent': opp_club.to_dict() if opp_club else {'name': 'Đối thủ', 'short_code': 'OPP'},
                })

                if len(found_matches) >= limit:
                    return found_matches

    return found_matches


def get_team_profile_data(campaign_id: int, club_id: int) -> Optional[Dict[str, Any]]:
    """Assemble complete Liquipedia-style dossier, tournament history, and current form evaluation for a club."""
    campaign = get_campaign(campaign_id)
    if not campaign:
        return None

    club = db.session.get(Club, club_id)
    if not club:
        return None

    backfill_stage_placements_if_needed(campaign_id)

    c_state = CampaignClubState.query.filter_by(campaign_id=campaign_id, club_id=club_id).first()

    # 1. Global & Regional Ranking Calculation
    all_states = CampaignClubState.query.filter_by(campaign_id=campaign_id).all()
    all_states.sort(key=lambda x: (x.power_score if x.power_score is not None else 1500.0, x.championship_points or 0), reverse=True)

    global_rank = 1
    for idx, s in enumerate(all_states, start=1):
        if s.club_id == club_id:
            global_rank = idx
            break

    c_reg = club.region.slug if club.region else 'pacific'
    reg_states = [s for s in all_states if s.club and s.club.region and s.club.region.slug == c_reg]
    regional_rank = 1
    for idx, s in enumerate(reg_states, start=1):
        if s.club_id == club_id:
            regional_rank = idx
            break

    ps = c_state.power_score if (c_state and c_state.power_score is not None) else 1500.0
    ovr = c_state.power_rating if (c_state and c_state.power_rating is not None) else power_score_to_ovr(ps)
    tier_info = get_tier_info(ps)
    prev_rk = c_state.previous_rank if c_state else None
    rank_delta = format_rank_delta(global_rank, prev_rk)

    # 2. Tournament Placements History (Liquipedia Style)
    placements = CampaignStagePlacement.query.filter_by(
        campaign_id=campaign_id, club_id=club_id
    ).order_by(CampaignStagePlacement.year.desc(), CampaignStagePlacement.id.desc()).all()

    tournament_results = []
    champions_titles = 0
    major_titles = 0
    masters_titles = 0
    ewc_titles = 0
    regional_titles = 0
    runners_up = 0
    total_matches_won = 0
    total_matches_lost = 0
    lifetime_cp = 0

    tier_cat_map = {
        'champion': ('👑 VALORANT Champions', 'tier-world'),
        'major': ('🌟 VCT Major', 'tier-major'),
        'master': ('🏆 VCT Masters', 'tier-master'),
        'ewc': ('🌍 Esports World Cup', 'tier-ewc'),
        'stage1': ('⚡ Regional VCT', 'tier-regional'),
        'stage2': ('⚡ Regional VCT', 'tier-regional'),
        'kickoff': ('⚡ Regional VCT', 'tier-regional'),
    }

    for p in placements:
        # Category
        cat_name, cat_cls = tier_cat_map.get(p.stage_key, ('Giải đấu', 'tier-default'))

        # Placements count
        if p.rank == 1:
            if p.stage_key == 'champion':
                champions_titles += 1
            elif p.stage_key == 'major':
                major_titles += 1
            elif p.stage_key == 'master':
                masters_titles += 1
            elif p.stage_key == 'ewc':
                ewc_titles += 1
            elif p.stage_key in ('kickoff', 'stage1', 'stage2'):
                regional_titles += 1
        elif p.rank == 2:
            runners_up += 1

        w = p.matches_won or 0
        l = p.matches_lost or 0
        total_matches_won += w
        total_matches_lost += l
        cp_pts = p.stage_points_earned or 0
        lifetime_cp += cp_pts

        winrate = round((w / (w + l) * 100), 1) if (w + l) > 0 else 0.0

        p_tier = get_tier_info(p.power_score_snapshot or 1500.0)

        tournament_results.append({
            'year': p.year,
            'stage_key': p.stage_key,
            'tournament_name': p.tournament_name,
            'category_name': cat_name,
            'category_class': cat_cls,
            'rank': p.rank,
            'rank_display': p.rank_display,
            'elimination_stage': p.elimination_stage or '-',
            'matches_won': w,
            'matches_lost': l,
            'win_rate': winrate,
            'stage_points_earned': cp_pts,
            'power_score_snapshot': round(p.power_score_snapshot or 1500.0, 1),
            'power_rating_snapshot': round(p.power_rating_snapshot or 80.0, 1),
            'tier': p_tier,
        })

    total_titles = champions_titles + major_titles + masters_titles + ewc_titles + regional_titles
    total_finals = total_titles + runners_up
    total_matches = total_matches_won + total_matches_lost
    overall_win_rate = round((total_matches_won / total_matches * 100), 1) if total_matches > 0 else 0.0

    intl_count = sum(1 for p in placements if p.stage_key in ('champion', 'master', 'major', 'ewc'))

    # 3. Attributes Radar & Team DNA Evaluation
    base_r = c_state.story_rating if c_state else (club.base_rating or 80)
    form_mod = c_state.form_modifier if c_state else 0
    eff_r = (c_state.effective_rating if c_state else base_r)

    firepower = min(99, max(60, int(eff_r + 2)))
    strategy = min(99, max(60, int(ovr * 0.98)))
    clutch = min(99, max(60, int(75 + ((c_state.win_streak if c_state else 0) * 2.5) + (champions_titles * 5) + (masters_titles * 2.5))))
    consistency = min(99, max(60, int(84 - abs(form_mod) * 2 + (overall_win_rate - 50.0) * 0.2)))

    # Team DNA & Playstyle
    dna_info = TEAM_DNA_MAP.get(club.short_code, DEFAULT_REGIONAL_DNA.get(c_reg, {
        'dna': 'Dynamic Versatility & Team Coordination',
        'style': 'Balanced Combat',
        'tempo': 'Adaptive',
    }))

    # Automated Scouting Assessment
    streak_val = c_state.win_streak if c_state else 0
    if tier_info['tier'] == 'S+':
        scouting_base = "Thế lực đỉnh cao thế giới. Sở hữu khả năng bóp nghẹt đối thủ bằng cả hỏa lực vượt trội lẫn bản lĩnh trận mạc đanh thép, là ứng cử viên số 1 cho mọi giải đấu."
    elif tier_info['tier'] == 'S':
        scouting_base = "Đội tuyển đẳng cấp quốc tế. Có khả năng đánh bại bất kỳ đối thủ nào vào một ngày thăng hoa, luôn là mối đe dọa trực tiếp cho ngôi vương."
    elif tier_info['tier'] == 'A':
        scouting_base = "Sức mạnh khu vực đáng gờm. Thi đấu ổn định ở giải quốc nội, sở hữu tiềm năng tạo địa chấn lớn nếu duy trì được sự tập trung ở những thời khắc then chốt."
    elif tier_info['tier'] == 'B':
        scouting_base = "Đội tuyển nhóm giữa bảng đang tìm kiếm sự đột phá. Cần cải thiện khả năng giao tiếp và bản lĩnh ở các round đấu quyết định 11-12."
    else:
        scouting_base = "Đang trong chu kỳ tái thiết lực lượng. Cần bổ sung thêm kinh nghiệm thi đấu cọ xát và củng cố hệ thống chiến thuật bài bản."

    if streak_val >= 3:
        form_note = f"Phong độ đang cực kỳ thăng hoa với chuỗi {streak_val} trận toàn thắng liên tiếp."
    elif streak_val <= -3:
        form_note = f"Đang gặp áp lực phong độ sau {abs(streak_val)} trận thất bại gần đây, cần sớm xốc lại tinh thần."
    elif form_mod > 0:
        form_note = f"Phong độ thi đấu đang chiều hướng tích cực (+{form_mod} Form Boost)."
    elif form_mod < 0:
        form_note = f"Đang có dấu hiệu chững lại nhẹ ({form_mod} Form Penalty)."
    else:
        form_note = "Phong độ ổn định, sẵn sàng bùng nổ ở giai đoạn then chốt tiếp theo."

    scouting_report = f"{scouting_base} {form_note}"

    # 4. Recent Matches
    recent_matches = _extract_recent_matches_for_club(campaign_id, club_id, limit=5)

    return {
        'club': club.to_dict(),
        'campaign_id': campaign_id,
        'year': campaign.current_year,
        'state': c_state.to_dict() if c_state else None,
        'rankings': {
            'global_rank': global_rank,
            'regional_rank': regional_rank,
            'region_slug': c_reg,
            'power_score': round(ps, 1),
            'power_rating': round(ovr, 1),
            'tier': tier_info,
            'rank_delta': rank_delta,
        },
        'trophy_cabinet': {
            'champions_titles': champions_titles,
            'major_titles': major_titles,
            'masters_titles': masters_titles,
            'ewc_titles': ewc_titles,
            'regional_titles': regional_titles,
            'total_titles': total_titles,
            'runners_up': runners_up,
            'total_finals': total_finals,
        },
        'career_stats': {
            'total_tournaments': len(placements),
            'total_matches': total_matches,
            'matches_won': total_matches_won,
            'matches_lost': total_matches_lost,
            'win_rate': overall_win_rate,
            'lifetime_cp': lifetime_cp,
            'current_season_cp': c_state.championship_points if c_state else 0,
            'international_appearances': intl_count,
        },
        'evaluation': {
            'firepower': firepower,
            'strategy': strategy,
            'clutch': clutch,
            'consistency': consistency,
            'overall_grade': tier_info['badge'],
            'team_dna': dna_info['dna'],
            'playstyle': dna_info['style'],
            'tempo': dna_info['tempo'],
            'win_streak': streak_val,
            'form_modifier': form_mod,
            'scouting_report': scouting_report,
        },
        'recent_matches': recent_matches,
        'tournament_results': tournament_results,
    }




# ─────────────────────────────────────────────────────────────────────────────
# TOURNAMENT CONFIRMATION & LOCKING WORKFLOW (OPTION A)
# ─────────────────────────────────────────────────────────────────────────────

def _advance_campaign_to_next_stage(campaign: Campaign, stage_key: str, data: Dict[str, Any]):
    """Advance campaign circuit to the subsequent stage and initialize stage records/rosters."""
    all_regions = ['pacific', 'americas', 'emea', 'china']
    
    if stage_key == 'open_qualifier':
        campaign.current_stage = 'kickoff'
        _prepare_kickoff_stage(campaign, data.get('regions', {}))
    elif stage_key == 'kickoff':
        campaign.current_stage = 'major'
        _prepare_major_stage(campaign, data.get('regional_results', {}))
    elif stage_key == 'major':
        campaign.current_stage = 'oq_stage1'
        _prepare_oq_stage1_stage(campaign)
    elif stage_key == 'oq_stage1':
        campaign.current_stage = 'stage1'
        _prepare_stage1_stage(campaign)
    elif stage_key == 'stage1':
        campaign.current_stage = 'ewc_qualifier'
        _prepare_ewc_qualifier_stage(campaign, data.get('regional_results', {}))
        _prepare_master_stage(campaign, data.get('regional_results', {}))
        _prepare_ewc_stage(campaign, data.get('regional_results', {}))
    elif stage_key == 'ewc_qualifier':
        campaign.current_stage = 'master'
        s1_record = CampaignStage.query.filter_by(
            campaign_id=campaign.id, year=campaign.current_year, stage_key='stage1'
        ).first()
        _finalize_ewc_roster(campaign, s1_record, data)
    elif stage_key == 'master':
        campaign.current_stage = 'ewc'
    elif stage_key == 'ewc':
        campaign.current_stage = 'oq_stage2'
        _prepare_oq_stage2_stage(campaign)
    elif stage_key == 'oq_stage2':
        campaign.current_stage = 'stage2'
        _prepare_stage2_stage(campaign)
    elif stage_key == 'stage2':
        campaign.current_stage = 'champion'
        all_champions_teams = []
        for r in all_regions:
            reg_q = data.get('regional_results', {}).get(r, {}).get('champions_qualifiers', [])
            all_champions_teams.extend(reg_q)
        _prepare_champion_stage(campaign, all_champions_teams)
    elif stage_key == 'champion':
        campaign.current_stage = 'season_summary'
        _prepare_season_summary_stage(campaign)


def confirm_stage_region(campaign_id: int, stage_key: str, region_slug: str) -> Dict[str, Any]:
    """Explicitly confirm and permanently lock a single region's tournament results (Option A).
    Awards championship points, ratings, sets is_confirmed=True. If all regions confirmed, advances campaign.
    """
    campaign = get_campaign(campaign_id)
    if not campaign:
        raise ValueError(f"Campaign {campaign_id} not found")

    stage = get_stage_record(campaign_id, stage_key)
    if not stage:
        raise ValueError(f"Stage {stage_key} not found")

    data = json.loads(stage.stage_data) if stage.stage_data else {}
    
    if stage_key in ['open_qualifier', 'oq_stage1', 'oq_stage2', 'ewc_qualifier']:
        reg_map = data.get('regions', {})
    elif stage_key in ['kickoff', 'stage1', 'stage2']:
        reg_map = data.get('regional_results', {})
    else:
        raise ValueError(f"Stage {stage_key} is not a regional stage. Use confirm_stage_tournament.")

    if region_slug not in reg_map:
        raise ValueError(f"Region {region_slug} not found in stage {stage_key}")

    reg_data = reg_map[region_slug]

    # Validation guard: ensure regional tournament is actually completed
    is_done, reason = is_stage_region_actually_completed(stage_key, reg_data)
    if not is_done:
        raise ValueError(f"Không thể khóa khu vực {region_slug.upper()}: {reason}")

    if reg_data.get('is_confirmed'):
        return {
            'success': True,
            'already_confirmed': True,
            'region': region_slug,
            'stage_key': stage_key,
            'message': 'Khu vực này đã được xác nhận và khóa trước đó.'
        }

    reg_data['is_confirmed'] = True
    reg_data['matches_completed'] = True
    reg_data['status'] = 'completed'

    # Apply stage-specific awards
    club_states = {cs.club_id: cs for cs in CampaignClubState.query.filter_by(campaign_id=campaign.id).all()}
    
    if stage_key in ['open_qualifier', 'oq_stage1', 'oq_stage2']:
        if not reg_data.get('ratings_awarded'):
            qual_ids = {t['id'] for t in reg_data.get('qualified_teams', [])}
            for cid in qual_ids:
                if cid in club_states:
                    club_states[cid].story_rating = min(99, club_states[cid].story_rating + 2)
            for s in reg_data.get('swiss_standings', []):
                cid = s['club_id']
                if s['wins'] == 0 and cid in club_states:
                    club_states[cid].story_rating = max(60, club_states[cid].story_rating - 1)
            reg_data['ratings_awarded'] = True

    elif stage_key == 'kickoff':
        if not reg_data.get('rewards_awarded'):
            cp_awards = []
            for s in reg_data.get('standings', []):
                cp_awards.append({'club_id': s['club_id'], 'rank': s['rank']})
            award_stage_cp(campaign.id, 'kickoff', cp_awards)
            if reg_data.get('major_qualifiers'):
                c_id = reg_data['major_qualifiers'][0]['id']
                if c_id in club_states:
                    club_states[c_id].story_rating = min(99, club_states[c_id].story_rating + 2)
                r_id = reg_data['major_qualifiers'][1]['id']
                if r_id in club_states:
                    club_states[r_id].story_rating = min(99, club_states[r_id].story_rating + 1)
            reg_data['rewards_awarded'] = True

    elif stage_key == 'stage1':
        if not reg_data.get('rewards_awarded'):
            reg_awards = []
            for s in reg_data.get('alpha_standings', []) + reg_data.get('omega_standings', []):
                reg_awards.append({
                    'club_id': s['club_id'],
                    'regular_wins': s['wins'],
                    'map_diff': s['map_diff'],
                    'round_diff': s['round_diff'],
                })
            award_stage_cp(campaign.id, 'stage1_regular', reg_awards)
            playoff_awards = []
            for s in reg_data.get('standings', []):
                playoff_awards.append({'club_id': s['club_id'], 'rank': s['rank']})
            award_stage_cp(campaign.id, 'stage1_playoffs', playoff_awards)
            champ = reg_data.get('champion')
            runner = reg_data.get('runner_up')
            third = reg_data.get('third_place')
            if champ:
                c_id = champ.get('id') or champ.get('club_id')
                if c_id in club_states:
                    club_states[c_id].story_rating = min(99, club_states[c_id].story_rating + 3)
            if runner:
                r_id = runner.get('id') or runner.get('club_id')
                if r_id in club_states:
                    club_states[r_id].story_rating = min(99, club_states[r_id].story_rating + 2)
            if third:
                t_id = third.get('id') or third.get('club_id')
                if t_id in club_states:
                    club_states[t_id].story_rating = min(99, club_states[t_id].story_rating + 1)
            reg_data['rewards_awarded'] = True

    elif stage_key == 'stage2':
        if not reg_data.get('rewards_awarded'):
            reg_awards = []
            for s in reg_data.get('alpha_standings', []) + reg_data.get('omega_standings', []):
                reg_awards.append({
                    'club_id': s['club_id'],
                    'regular_wins': s['wins'],
                    'map_diff': s['map_diff'],
                    'round_diff': s['round_diff'],
                })
            award_stage_cp(campaign.id, 'stage2_regular', reg_awards)
            playoff_awards = []
            for s in reg_data.get('standings', []):
                playoff_awards.append({'club_id': s['club_id'], 'rank': s['rank']})
            award_stage_cp(campaign.id, 'stage2_playoffs', playoff_awards)
            champ = reg_data.get('champion')
            runner = reg_data.get('runner_up')
            third = reg_data.get('third_place')
            if champ:
                c_id = champ.get('id') or champ.get('club_id')
                if c_id in club_states:
                    club_states[c_id].story_rating = min(99, club_states[c_id].story_rating + 3)
            if runner:
                r_id = runner.get('id') or runner.get('club_id')
                if r_id in club_states:
                    club_states[r_id].story_rating = min(99, club_states[r_id].story_rating + 2)
            if third:
                t_id = third.get('id') or third.get('club_id')
                if t_id in club_states:
                    club_states[t_id].story_rating = min(99, club_states[t_id].story_rating + 1)
            champs_info = get_champions_paris_qualifiers(campaign.id, region_slug)
            reg_data['champions_qualifiers'] = champs_info.get('qualifiers', [])
            reg_data['cp_leaderboard'] = champs_info.get('leaderboard', [])
            reg_data['rewards_awarded'] = True

    elif stage_key == 'ewc_qualifier':
        if not reg_data.get('rewards_awarded'):
            champ = reg_data.get('champion')
            runner = reg_data.get('runner_up')
            if champ:
                c_id = champ.get('id') or champ.get('club_id')
                if c_id in club_states:
                    club_states[c_id].story_rating = min(99, club_states[c_id].story_rating + 2)
            if runner:
                r_id = runner.get('id') or runner.get('club_id')
                if r_id in club_states:
                    club_states[r_id].story_rating = min(99, club_states[r_id].story_rating + 1)
            reg_data['rewards_awarded'] = True

    # Check if all 4 regions are now confirmed
    all_regions = ['pacific', 'americas', 'emea', 'china']
    all_done = all(reg_map.get(r, {}).get('is_confirmed') for r in all_regions)

    if all_done:
        stage.status = 'completed'
        stage.completed_at = datetime.now(timezone.utc)
        record_stage_placements(campaign.id, stage_key, year=stage.year)
        _advance_campaign_to_next_stage(campaign, stage_key, data)

    stage.stage_data = json.dumps(data)
    db.session.commit()
    recalculate_campaign_gpr(campaign.id)

    return {
        'success': True,
        'region': region_slug,
        'stage_key': stage_key,
        'is_confirmed': True,
        'all_confirmed': all_done,
        'champion': reg_data.get('champion'),
        'runner_up': reg_data.get('runner_up'),
        'qualifiers': reg_data.get('major_qualifiers') or reg_data.get('champions_qualifiers') or reg_data.get('ewc_qualifiers') or reg_data.get('qualified_teams', []),
        'campaign_advanced': all_done,
        'current_stage': campaign.current_stage,
    }


def confirm_stage_tournament(campaign_id: int, stage_key: str) -> Dict[str, Any]:
    """Confirm and permanently lock an international tournament (Major, Master, EWC, Champions)."""
    campaign = get_campaign(campaign_id)
    if not campaign:
        raise ValueError(f"Campaign {campaign_id} not found")

    stage = get_stage_record(campaign_id, stage_key)
    if not stage:
        raise ValueError(f"Stage {stage_key} not found")

    data = json.loads(stage.stage_data) if stage.stage_data else {}
    res = data.get('result', {}) if 'result' in data else data

    # Validation guard: ensure international tournament is actually completed
    is_done, reason = is_stage_tournament_actually_completed(stage_key, res)
    if not is_done:
        raise ValueError(f"Không thể khóa giải đấu {stage_key.upper()}: {reason}")

    if res.get('is_confirmed'):
        return {
            'success': True,
            'already_confirmed': True,
            'stage_key': stage_key,
            'message': 'Giải đấu này đã được xác nhận và khóa trước đó.'
        }

    res['is_confirmed'] = True
    res['matches_completed'] = True
    res['status'] = 'completed'

    club_states = {cs.club_id: cs for cs in CampaignClubState.query.filter_by(campaign_id=campaign.id).all()}

    if stage_key == 'major':
        if not res.get('rewards_awarded'):
            cp_awards = []
            for s in res.get('standings', []):
                cp_awards.append({'club_id': s['club_id'], 'rank': s['rank']})
            award_stage_cp(campaign.id, 'major', cp_awards)
            if res.get('champion'):
                champ_id = res['champion']['id']
                if champ_id in club_states:
                    club_states[champ_id].story_rating = min(99, club_states[champ_id].story_rating + 3)
            if res.get('runner_up'):
                runner_id = res['runner_up']['id']
                if runner_id in club_states:
                    club_states[runner_id].story_rating = min(99, club_states[runner_id].story_rating + 2)
            res['rewards_awarded'] = True

    elif stage_key == 'master':
        if not res.get('rewards_awarded'):
            for s in res.get('standings', []):
                cid = s['club_id']
                if cid in club_states:
                    if s.get('rank') == 1:
                        club_states[cid].story_rating = min(99, club_states[cid].story_rating + 4)
                    elif s.get('rank') == 2:
                        club_states[cid].story_rating = min(99, club_states[cid].story_rating + 3)
                    elif s.get('rank') == 3:
                        club_states[cid].story_rating = min(99, club_states[cid].story_rating + 2)
                    elif s.get('rank') == 4:
                        club_states[cid].story_rating = min(99, club_states[cid].story_rating + 1)
            res['rewards_awarded'] = True

    elif stage_key == 'ewc':
        if not res.get('rewards_awarded'):
            if res.get('champion'):
                c_id = res['champion']['id'] if isinstance(res['champion'], dict) else res['champion']
                if c_id in club_states:
                    club_states[c_id].story_rating = min(99, club_states[c_id].story_rating + 4)
            if res.get('runner_up'):
                r_id = res['runner_up']['id'] if isinstance(res['runner_up'], dict) else res['runner_up']
                if r_id in club_states:
                    club_states[r_id].story_rating = min(99, club_states[r_id].story_rating + 3)
            if res.get('third_place'):
                third = res['third_place']
                t_id = third.get('id') if isinstance(third, dict) else third
                if t_id in club_states:
                    club_states[t_id].story_rating = min(99, club_states[t_id].story_rating + 2)
            if res.get('fourth_place'):
                fourth = res['fourth_place']
                f_id = fourth.get('id') if isinstance(fourth, dict) else fourth
                if f_id in club_states:
                    club_states[f_id].story_rating = min(99, club_states[f_id].story_rating + 1)
            res['rewards_awarded'] = True

    elif stage_key == 'champion':
        if not res.get('rewards_awarded'):
            champ = res.get('champion')
            runner = res.get('runner_up')
            third = res.get('third_place')
            fourth = res.get('fourth_place')
            if champ:
                c_id = champ['id'] if isinstance(champ, dict) else champ
                if c_id in club_states:
                    club_states[c_id].story_rating = min(99, club_states[c_id].story_rating + 6)
                    club_states[c_id].set_stage_rank('champion', 1)
            if runner:
                r_id = runner['id'] if isinstance(runner, dict) else runner
                if r_id in club_states:
                    club_states[r_id].story_rating = min(99, club_states[r_id].story_rating + 4)
                    club_states[r_id].set_stage_rank('champion', 2)
            if third:
                t_id = third['id'] if isinstance(third, dict) else third
                if t_id in club_states:
                    club_states[t_id].story_rating = min(99, club_states[t_id].story_rating + 3)
                    club_states[t_id].set_stage_rank('champion', 3)
            if fourth:
                f_id = fourth['id'] if isinstance(fourth, dict) else fourth
                if f_id in club_states:
                    club_states[f_id].story_rating = min(99, club_states[f_id].story_rating + 3)
                    club_states[f_id].set_stage_rank('champion', 4)
            res['rewards_awarded'] = True

    stage.status = 'completed'
    stage.completed_at = datetime.now(timezone.utc)
    record_stage_placements(campaign.id, stage_key, year=stage.year)
    _advance_campaign_to_next_stage(campaign, stage_key, data)

    stage.stage_data = json.dumps(data)
    db.session.commit()
    recalculate_campaign_gpr(campaign.id)

    return {
        'success': True,
        'stage_key': stage_key,
        'is_confirmed': True,
        'champion': res.get('champion'),
        'runner_up': res.get('runner_up'),
        'third_place': res.get('third_place'),
        'fourth_place': res.get('fourth_place'),
        'campaign_advanced': True,
        'current_stage': campaign.current_stage,
    }


def confirm_stage_all(campaign_id: int, stage_key: str) -> Dict[str, Any]:
    """Confirm all regions or entire tournament at once."""
    if stage_key in ['major', 'master', 'ewc', 'champion']:
        return confirm_stage_tournament(campaign_id, stage_key)

    campaign = get_campaign(campaign_id)
    if not campaign:
        raise ValueError(f"Campaign {campaign_id} not found")

    stage = get_stage_record(campaign_id, stage_key)
    if not stage:
        raise ValueError(f"Stage {stage_key} not found")

    data = json.loads(stage.stage_data) if stage.stage_data else {}
    if stage_key in ['open_qualifier', 'oq_stage1', 'oq_stage2', 'ewc_qualifier']:
        reg_map = data.get('regions', {})
    elif stage_key in ['kickoff', 'stage1', 'stage2']:
        reg_map = data.get('regional_results', {})
    else:
        raise ValueError(f"Stage {stage_key} is not a regional stage.")

    all_regions = ['pacific', 'americas', 'emea', 'china']
    incomplete = []
    for r in all_regions:
        reg_data = reg_map.get(r, {})
        is_done, reason = is_stage_region_actually_completed(stage_key, reg_data)
        if not is_done:
            incomplete.append(f"{r.upper()} ({reason})")

    if incomplete:
        raise ValueError(f"Không thể khóa cả 4 khu vực vì còn khu vực chưa hoàn thành: {', '.join(incomplete)}")

    last_res = None
    for r in all_regions:
        last_res = confirm_stage_region(campaign_id, stage_key, r)
    return last_res
