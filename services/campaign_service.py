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
from typing import List, Dict, Optional, Any
from models import db, Club, Region, Campaign, CampaignClubState, CampaignStage, CampaignSeason
from config import Config
from engine.format.open_qualifier import (
    init_open_qualifier_region_state,
    resolve_open_qualifier_match,
    advance_open_qualifier_region,
    sim_open_qualifier_round,
    sim_open_qualifier_remaining,
    simulate_open_qualifier,
)
from engine.format.kickoff import simulate_kickoff_tournament
from engine.format.major_sim import simulate_major_tournament



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
    db.session.add(campaign)
    db.session.flush()

    clubs = Club.query.join(Region).all()
    partner_map = Config.PARTNER_TEAMS_BY_REGION

    for club in clubs:
        reg_slug = club.region.slug if club.region else ''
        partner_codes = partner_map.get(reg_slug, [])
        is_partner = club.short_code in partner_codes

        state = CampaignClubState(
            campaign_id=campaign.id,
            club_id=club.id,
            story_rating=club.current_rating or club.base_rating or 80,
            form_modifier=0,
            championship_points=0,
            is_partner=is_partner,
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
    """Tweak a club's form modifier (-10 to +10) before a stage."""
    state = CampaignClubState.query.filter_by(campaign_id=campaign_id, club_id=club_id).first()
    if not state:
        return False
    state.form_modifier = max(-15, min(15, form_modifier))
    db.session.commit()
    return True


def bulk_update_form(campaign_id: int, updates: Dict[int, int]) -> int:
    """Batch update form modifiers for clubs."""
    count = 0
    for club_id, form_val in updates.items():
        state = CampaignClubState.query.filter_by(campaign_id=campaign_id, club_id=club_id).first()
        if state:
            state.form_modifier = max(-15, min(15, int(form_val)))
            count += 1
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
    return data


def _check_and_finalize_oq_regions(campaign: Campaign, stage: CampaignStage, data: Dict[str, Any]):
    """Helper to update dynamic ratings and advance campaign if all 4 regions are finished."""
    all_regions = ['pacific', 'americas', 'emea', 'china']
    club_states = {cs.club_id: cs for cs in CampaignClubState.query.filter_by(campaign_id=campaign.id).all()}

    for r_slug in all_regions:
        reg_res = data.get('regions', {}).get(r_slug)
        if reg_res and reg_res.get('status') == 'completed':
            if not reg_res.get('ratings_awarded'):
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

    if all(data.get('regions', {}).get(r, {}).get('status') == 'completed' for r in all_regions):
        stage.status = 'completed'
        stage.completed_at = datetime.now(timezone.utc)
        campaign.current_stage = 'kickoff'
        _prepare_kickoff_stage(campaign, data['regions'])


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


def sim_oq_round(campaign_id: int, region_slug: str) -> Dict[str, Any]:
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
        data = json.loads(stage.stage_data)

    reg_data = data['regions'][region_slug]
    club_states = CampaignClubState.query.filter_by(campaign_id=campaign_id).all()
    rating_lookup = {cs.club_id: cs.story_rating for cs in club_states}
    form_lookup = {cs.club_id: cs.form_modifier for cs in club_states}

    sim_count = sim_open_qualifier_round(reg_data, rating_lookup=rating_lookup, form_lookup=form_lookup)

    _check_and_finalize_oq_regions(campaign, stage, data)
    db.session.commit()
    return {'sim_count': sim_count, 'region_data': reg_data}


def sim_oq_region(campaign_id: int, region_slug: str) -> Dict[str, Any]:
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
        data = json.loads(stage.stage_data)

    reg_data = data['regions'][region_slug]
    club_states = CampaignClubState.query.filter_by(campaign_id=campaign_id).all()
    rating_lookup = {cs.club_id: cs.story_rating for cs in club_states}
    form_lookup = {cs.club_id: cs.form_modifier for cs in club_states}

    sim_open_qualifier_remaining(reg_data, rating_lookup=rating_lookup, form_lookup=form_lookup)

    _check_and_finalize_oq_regions(campaign, stage, data)
    db.session.commit()
    return {'region_data': reg_data}


def run_open_qualifier_stage(campaign_id: int, region_slug: Optional[str] = None) -> Dict[str, Any]:
    """Execute Open Qualifier simulation for one region or all regions (backward compatible)."""
    regions_to_run = [region_slug] if region_slug else ['pacific', 'americas', 'emea', 'china']
    results_summary = {}

    for r_slug in regions_to_run:
        res = sim_oq_region(campaign_id, r_slug)
        r_data = res['region_data']
        results_summary[r_slug] = {
            'qualified_teams': r_data.get('qualified_teams', []),
            'total_matches': r_data.get('total_matches_count', 43),
        }
    return results_summary


def _prepare_kickoff_stage(campaign: Campaign, oq_regions_data: Dict[str, Any]):
    """Assemble 12 Kickoff teams per region (8 Partners + 4 Open Qualifiers)."""
    kickoff_stage = CampaignStage.query.filter_by(
        campaign_id=campaign.id, year=campaign.current_year, stage_key='kickoff'
    ).first()

    kickoff_rosters = {}
    for r_slug in ['pacific', 'americas', 'emea', 'china']:
        # 8 Partner teams
        partner_states = CampaignClubState.query.filter_by(
            campaign_id=campaign.id, is_partner=True
        ).join(Club).join(Region).filter(Region.slug == r_slug).all()

        partner_teams = [
            {
                'id': cs.club.id,
                'name': cs.club.name,
                'short_code': cs.club.short_code,
                'story_rating': cs.story_rating,
                'effective_rating': cs.effective_rating,
                'is_partner': True,
                'entry_source': 'Partner Direct Entry',
            }
            for cs in partner_states
        ]

        # 4 Qualified teams from Open Qualifier
        oq_qualifiers = oq_regions_data.get(r_slug, {}).get('qualified_teams', [])
        qual_teams = [
            {
                'id': t['id'],
                'name': t['name'],
                'short_code': t['short_code'],
                'story_rating': t.get('story_rating', 80),
                'is_partner': False,
                'entry_source': f'Open Qualifier Seed #{idx + 1}',
            }
            for idx, t in enumerate(oq_qualifiers)
        ]

        kickoff_rosters[r_slug] = partner_teams + qual_teams

    if not kickoff_stage:
        kickoff_stage = CampaignStage(
            campaign_id=campaign.id,
            year=campaign.current_year,
            stage_key='kickoff',
            stage_name=f'VCT Kickoff {campaign.current_year}',
            status='pending',
            stage_data=json.dumps({'rosters': kickoff_rosters, 'regional_results': {}}),
        )
        db.session.add(kickoff_stage)
    else:
        current_data = json.loads(kickoff_stage.stage_data) if kickoff_stage.stage_data else {}
        current_data['rosters'] = kickoff_rosters
        kickoff_stage.stage_data = json.dumps(current_data)





# ─────────────────────────────────────────────────────────────────────────────
# VCT Kickoff Stage Execution
# ─────────────────────────────────────────────────────────────────────────────

def get_kickoff_data(campaign_id: int) -> Optional[Dict[str, Any]]:
    """Retrieve full Kickoff data for all regions in a campaign."""
    stage = get_stage_record(campaign_id, 'kickoff')
    if not stage or not stage.stage_data:
        return None
    return json.loads(stage.stage_data)


def run_kickoff_stage(campaign_id: int, region_slug: Optional[str] = None,
                      manual_overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Execute Kickoff simulation (22 matches per region) for one or all regions."""
    campaign = get_campaign(campaign_id)
    if not campaign:
        raise ValueError(f"Campaign {campaign_id} not found")

    stage = get_stage_record(campaign_id, 'kickoff')
    if not stage:
        raise ValueError("Kickoff stage not initialized yet. Please complete Open Qualifier first.")

    data = json.loads(stage.stage_data) if stage.stage_data else {'rosters': {}, 'regional_results': {}}
    if 'regional_results' not in data:
        data['regional_results'] = {}
    if 'manual_overrides' not in data:
        data['manual_overrides'] = {}

    regions_to_run = [region_slug] if region_slug else ['pacific', 'americas', 'emea', 'china']
    summary_results = {}

    for r_slug in regions_to_run:
        roster = data.get('rosters', {}).get(r_slug, [])
        if len(roster) != 12:
            raise ValueError(f"Roster for {r_slug} Kickoff does not have 12 teams")

        # Refresh rating & form from CampaignClubState
        states = {cs.club_id: cs for cs in CampaignClubState.query.filter_by(campaign_id=campaign_id).all()}
        for t in roster:
            c_id = t['id']
            if c_id in states:
                t['story_rating'] = states[c_id].story_rating
                t['form_modifier'] = states[c_id].form_modifier
                t['effective_rating'] = states[c_id].effective_rating

        rating_lookup = {t['id']: t['story_rating'] for t in roster}
        form_lookup = {t['id']: t['form_modifier'] for t in roster}

        # Combine stored overrides with any new overrides passed in
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

        data['regional_results'][r_slug] = sim_res

        # Award official VCT 2025 Championship Points
        cp_awards = []
        for s in sim_res['standings']:
            cp_awards.append({
                'club_id': s['club_id'],
                'rank': s['rank'],
            })
        award_stage_cp(campaign_id, 'kickoff', cp_awards)

        summary_results[r_slug] = {
            'champion': sim_res['standings'][0]['team'],
            'runner_up': sim_res['standings'][1]['team'],
            'major_qualifiers': sim_res['major_qualifiers'],
            'total_matches': sim_res['total_matches_count'],
        }

    stage.stage_data = json.dumps(data)

    # Check if all 4 regions are finished
    all_regions = ['pacific', 'americas', 'emea', 'china']
    if all(r in data['regional_results'] for r in all_regions):
        stage.status = 'completed'
        stage.completed_at = datetime.now(timezone.utc)

        # Advance campaign to Major
        campaign.current_stage = 'major'
        _prepare_major_stage(campaign, data['regional_results'])

    db.session.commit()
    return summary_results


def override_kickoff_match(campaign_id: int, region_slug: str, round_name: str,
                           winner_id: int, maps: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Force a specific winner / map scores for a Kickoff match and re-simulate the bracket."""
    overrides = {
        round_name: {
            'winner_id': winner_id,
            'maps': maps or [],
        }
    }
    return run_kickoff_stage(campaign_id, region_slug=region_slug, manual_overrides=overrides)


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

    if not major_stage:
        major_stage = CampaignStage(
            campaign_id=campaign.id,
            year=campaign.current_year,
            stage_key='major',
            stage_name=f'VCT Major {campaign.current_year} (Masters Bangkok)',
            status='pending',
            stage_data=json.dumps({'roster': major_roster}),
        )
        db.session.add(major_stage)
    else:
        m_data = json.loads(major_stage.stage_data) if major_stage.stage_data else {}
        m_data['roster'] = major_roster
        major_stage.stage_data = json.dumps(m_data)


# ─────────────────────────────────────────────────────────────────────────────
# VCT Major (Masters Bangkok) Stage Execution
# ─────────────────────────────────────────────────────────────────────────────

def get_major_data(campaign_id: int) -> Optional[Dict[str, Any]]:
    """Retrieve full Major data (roster, matches, standings) for a campaign."""
    stage = get_stage_record(campaign_id, 'major')
    if not stage or not stage.stage_data:
        return None
    return json.loads(stage.stage_data)


def run_major_stage(campaign_id: int, manual_overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
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
    data['result'] = sim_res

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
    stage.stage_data = json.dumps(data)

    # Advance campaign circuit to Stage 1
    campaign.current_stage = 'stage1'
    _prepare_stage1_stage(campaign)

    db.session.commit()
    return {
        'champion': sim_res['champion'],
        'runner_up': sim_res['runner_up'],
        'total_matches': sim_res['total_matches_count'],
        'standings': sim_res['standings'],
    }


def override_major_match(campaign_id: int, round_name: str,
                         winner_id: int, maps: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Force a specific winner / map scores for a Major match and re-simulate the bracket."""
    overrides = {
        round_name: {
            'winner_id': winner_id,
            'maps': maps or [],
        }
    }
    return run_major_stage(campaign_id, manual_overrides=overrides)


def _prepare_stage1_stage(campaign: Campaign):
    """Assemble 12 teams per region for VCT Stage 1 (from Kickoff rosters)."""
    stage1_record = CampaignStage.query.filter_by(
        campaign_id=campaign.id, year=campaign.current_year, stage_key='stage1'
    ).first()

    kickoff_stage = CampaignStage.query.filter_by(
        campaign_id=campaign.id, year=campaign.current_year, stage_key='kickoff'
    ).first()

    rosters = {}
    if kickoff_stage and kickoff_stage.stage_data:
        try:
            k_data = json.loads(kickoff_stage.stage_data)
            rosters = k_data.get('rosters', {})
        except Exception:
            rosters = {}

    if not stage1_record:
        stage1_record = CampaignStage(
            campaign_id=campaign.id,
            year=campaign.current_year,
            stage_key='stage1',
            stage_name=f'VCT Stage 1 {campaign.current_year}',
            status='pending',
            stage_data=json.dumps({'rosters': rosters, 'status': 'ready'}),
        )
        db.session.add(stage1_record)
    else:
        s1_data = json.loads(stage1_record.stage_data) if stage1_record.stage_data else {}
        s1_data['rosters'] = rosters
        stage1_record.stage_data = json.dumps(s1_data)


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

        # Deduct previous points from this stage if re-awarding (idempotency)
        old_rank = state.get_stage_rank(stage_key)
        old_pts = get_stage_points(stage_key, rank=old_rank) if old_rank else 0
        new_pts = get_stage_points(stage_key, rank=rank, regular_wins=reg_wins)

        state.championship_points = max(0, (state.championship_points or 0) - old_pts + new_pts)
        if rank:
            state.set_stage_rank(stage_key, rank)
        if reg_wins:
            state.regular_season_wins = (state.regular_season_wins or 0) + reg_wins
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

