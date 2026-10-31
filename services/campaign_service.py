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

def get_kickoff_data(campaign_id: int) -> Optional[Dict[str, Any]]:
    """Retrieve full Kickoff data for all regions in a campaign.
    Ensures that regional_results is initialized with interactive states.
    """
    stage = get_stage_record(campaign_id, 'kickoff')
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

    if updated:
        stage.stage_data = json.dumps(data)
        db.session.commit()

    return data


def _check_and_finalize_kickoff_regions(campaign: Campaign, stage: CampaignStage, data: Dict[str, Any]):
    """Award CP, story ratings, and advance campaign when all 4 Kickoff regions complete."""
    all_regions = ['pacific', 'americas', 'emea', 'china']
    club_states = {cs.club_id: cs for cs in CampaignClubState.query.filter_by(campaign_id=campaign.id).all()}

    for r_slug in all_regions:
        reg_data = data.get('regional_results', {}).get(r_slug)
        if reg_data and reg_data.get('status') == 'completed':
            if not reg_data.get('rewards_awarded'):
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

    if all(data.get('regional_results', {}).get(r, {}).get('status') == 'completed' for r in all_regions):
        stage.status = 'completed'
        stage.completed_at = datetime.now(timezone.utc)
        campaign.current_stage = 'major'
        _prepare_major_stage(campaign, data['regional_results'])


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


def sim_ko_round(campaign_id: int, region_slug: str) -> Dict[str, Any]:
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

    _check_and_finalize_kickoff_regions(campaign, stage, data)
    db.session.commit()
    return {'sim_count': sim_count, 'region_data': reg_data}


def sim_ko_region(campaign_id: int, region_slug: str) -> Dict[str, Any]:
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

    _check_and_finalize_kickoff_regions(campaign, stage, data)
    db.session.commit()
    return {'region_data': reg_data}


def run_kickoff_stage(campaign_id: int, region_slug: Optional[str] = None,
                      manual_overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
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

        data['regional_results'][r_slug] = sim_res

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

    all_regions = ['pacific', 'americas', 'emea', 'china']
    if all(r in data['regional_results'] and data['regional_results'][r].get('status') == 'completed' for r in all_regions):
        stage.status = 'completed'
        stage.completed_at = datetime.now(timezone.utc)
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

    initial_result = init_major_state(major_roster) if len(major_roster) == 8 else None

    if not major_stage:
        major_stage = CampaignStage(
            campaign_id=campaign.id,
            year=campaign.current_year,
            stage_key='major',
            stage_name=f'VCT Major {campaign.current_year} (Masters Bangkok)',
            status='pending',
            stage_data=json.dumps({'roster': major_roster, 'result': initial_result}),
        )
        db.session.add(major_stage)
    else:
        m_data = json.loads(major_stage.stage_data) if major_stage.stage_data else {}
        m_data['roster'] = major_roster
        if 'result' not in m_data or not m_data['result']:
            m_data['result'] = initial_result
        major_stage.stage_data = json.dumps(m_data)


# ─────────────────────────────────────────────────────────────────────────────
# VCT Major (Masters Bangkok) Stage Execution & Interactive Resolving
# ─────────────────────────────────────────────────────────────────────────────

def get_major_data(campaign_id: int) -> Optional[Dict[str, Any]]:
    """Retrieve full Major data (roster, matches, standings) for a campaign."""
    stage = get_stage_record(campaign_id, 'major')
    if not stage or not stage.stage_data:
        return None
    data = json.loads(stage.stage_data)
    roster = data.get('roster', [])

    if roster and len(roster) == 8 and ('result' not in data or not data['result'] or not data['result'].get('swiss_matches')):
        data['result'] = init_major_state(roster)
        stage.stage_data = json.dumps(data)
        db.session.commit()

    return data


def _check_and_finalize_major(campaign: Campaign, stage: CampaignStage, data: Dict[str, Any]):
    """Award CP, story ratings, and advance campaign when Major completes."""
    res = data.get('result')
    if res and res.get('status') == 'completed':
        if not res.get('rewards_awarded'):
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

        stage.status = 'completed'
        stage.completed_at = datetime.now(timezone.utc)
        campaign.current_stage = 'oq_stage1'
        _prepare_oq_stage1_stage(campaign)

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


def sim_major_round_interactive(campaign_id: int) -> Dict[str, Any]:
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

    _check_and_finalize_major(campaign, stage, data)
    db.session.commit()
    return {'sim_count': sim_count, 'major_data': major_data}


def sim_major_tournament_interactive(campaign_id: int) -> Dict[str, Any]:
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

    _check_and_finalize_major(campaign, stage, data)
    db.session.commit()
    return {'major_data': major_data}


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

    # Advance campaign circuit to Open Qualifier Stage 1
    campaign.current_stage = 'oq_stage1'
    _prepare_oq_stage1_stage(campaign)

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
        return None
    return json.loads(stage.stage_data)


def _check_and_finalize_oq_stage1(campaign: Campaign, stage: CampaignStage, data: Dict[str, Any]):
    """Update dynamic ratings and advance campaign to Stage 1 when all 4 regions complete."""
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
        campaign.current_stage = 'stage1'
        _prepare_stage1_stage(campaign)


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


def sim_oq_stage1_round(campaign_id: int, region_slug: str) -> Dict[str, Any]:
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
    _check_and_finalize_oq_stage1(campaign, stage, data)
    db.session.commit()
    return {'sim_count': sim_count, 'region_data': reg_data}


def sim_oq_stage1_region(campaign_id: int, region_slug: str) -> Dict[str, Any]:
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
    _check_and_finalize_oq_stage1(campaign, stage, data)
    db.session.commit()
    return {'region_data': reg_data}


def sim_oq_stage1_all(campaign_id: int) -> Dict[str, Any]:
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

    _check_and_finalize_oq_stage1(campaign, stage, data)
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


def get_stage1_data(campaign_id: int) -> Optional[Dict[str, Any]]:
    """Retrieve full Stage 1 data (rosters, regional_results) for a campaign."""
    stage = get_stage_record(campaign_id, 'stage1')
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

    if not master_stage:
        master_stage = CampaignStage(
            campaign_id=campaign.id,
            year=campaign.current_year,
            stage_key='master',
            stage_name=f'VCT Masters {campaign.current_year} (Masters Toronto)',
            status='pending',
            stage_data=json.dumps({'roster': master_roster, 'result': init_state} if init_state else {'roster': master_roster}),
        )
        db.session.add(master_stage)
    else:
        m_data = json.loads(master_stage.stage_data) if master_stage.stage_data else {}
        m_data['roster'] = master_roster
        if init_state and ('result' not in m_data or not m_data['result']):
            m_data['result'] = init_state
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

    if not ewc_stage:
        ewc_stage = CampaignStage(
            campaign_id=campaign.id,
            year=campaign.current_year,
            stage_key='ewc',
            stage_name=f'Esports World Cup (EWC) {campaign.current_year}',
            status='pending',
            stage_data=json.dumps({'roster': ewc_roster}),
        )
        db.session.add(ewc_stage)
    else:
        e_data = json.loads(ewc_stage.stage_data) if ewc_stage.stage_data else {}
        e_data['roster'] = ewc_roster
        ewc_stage.stage_data = json.dumps(e_data)


def _check_and_finalize_stage1(campaign: Campaign, stage: CampaignStage, data: Dict[str, Any]):
    all_regions = ['pacific', 'americas', 'emea', 'china']
    club_states = {cs.club_id: cs for cs in CampaignClubState.query.filter_by(campaign_id=campaign.id).all()}

    for r_slug, reg_data in data.get('regional_results', {}).items():
        if reg_data.get('status') == 'completed' and not reg_data.get('rewards_awarded'):
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

    if all(data.get('regional_results', {}).get(r, {}).get('status') == 'completed' for r in all_regions):
        stage.status = 'completed'
        stage.completed_at = datetime.now(timezone.utc)
        campaign.current_stage = 'ewc_qualifier'
        _prepare_ewc_qualifier_stage(campaign, data['regional_results'])
        _prepare_master_stage(campaign, data['regional_results'])
        _prepare_ewc_stage(campaign, data['regional_results'])


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


def sim_stage1_round_interactive(campaign_id: int, region_slug: str) -> Dict[str, Any]:
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

    _check_and_finalize_stage1(campaign, stage, data)
    db.session.commit()
    return {'sim_count': sim_count, 'region_data': reg_data}


def sim_stage1_region_interactive(campaign_id: int, region_slug: str) -> Dict[str, Any]:
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

    _check_and_finalize_stage1(campaign, stage, data)
    db.session.commit()
    return {'sim_count': sim_count, 'region_data': reg_data}


def sim_stage1_all_interactive(campaign_id: int) -> Dict[str, Any]:
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

    _check_and_finalize_stage1(campaign, stage, data)
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


def get_ewc_qualifier_data(campaign_id: int) -> Optional[Dict[str, Any]]:
    """Retrieve or auto-initialize EWC Qualifier stage data."""
    stage = get_stage_record(campaign_id, 'ewc_qualifier')
    if not stage or not stage.stage_data:
        campaign = get_campaign(campaign_id)
        if campaign:
            s1_data = get_stage1_data(campaign_id)
            if s1_data and s1_data.get('regional_results'):
                _prepare_ewc_qualifier_stage(campaign, s1_data.get('regional_results', {}))
                stage = get_stage_record(campaign_id, 'ewc_qualifier')
    if not stage or not stage.stage_data:
        return None
    return json.loads(stage.stage_data)


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

    if not ewc_stage:
        ewc_stage = CampaignStage(
            campaign_id=campaign.id,
            year=campaign.current_year,
            stage_key='ewc',
            stage_name=f'Esports World Cup (EWC) {campaign.current_year}',
            status='pending',
            stage_data=json.dumps({'roster': ewc_roster}),
        )
        db.session.add(ewc_stage)
    else:
        e_data = json.loads(ewc_stage.stage_data) if ewc_stage.stage_data else {}
        e_data['roster'] = ewc_roster
        ewc_stage.stage_data = json.dumps(e_data)


def _check_and_finalize_ewc_qualifier(campaign: Campaign, stage: CampaignStage, data: Dict[str, Any]):
    all_regions = ['pacific', 'americas', 'emea', 'china']
    club_states = {cs.club_id: cs for cs in CampaignClubState.query.filter_by(campaign_id=campaign.id).all()}

    for r_slug, reg_data in data.get('regions', {}).items():
        if reg_data.get('status') == 'completed' and not reg_data.get('rewards_awarded'):
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

    if all(data.get('regions', {}).get(r, {}).get('status') == 'completed' for r in all_regions):
        stage.status = 'completed'
        stage.completed_at = datetime.now(timezone.utc)
        campaign.current_stage = 'master'
        s1_record = CampaignStage.query.filter_by(
            campaign_id=campaign.id, year=campaign.current_year, stage_key='stage1'
        ).first()
        _finalize_ewc_roster(campaign, s1_record, data)


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


def sim_ewc_qualifier_round_interactive(campaign_id: int, region_slug: str) -> Dict[str, Any]:
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

    _check_and_finalize_ewc_qualifier(campaign, stage, data)
    db.session.commit()
    return {'resolved_count': len(resolved_matches), 'region_data': reg_data}


def sim_ewc_qualifier_region_interactive(campaign_id: int, region_slug: str) -> Dict[str, Any]:
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

    _check_and_finalize_ewc_qualifier(campaign, stage, data)
    db.session.commit()
    return {'simulated_count': count, 'region_data': reg_data}


def sim_ewc_qualifier_all_interactive(campaign_id: int) -> Dict[str, Any]:
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

    _check_and_finalize_ewc_qualifier(campaign, stage, data)
    db.session.commit()
    return {'total_sim': total_sim, 'ewc_qualifier_data': data}


def run_ewc_qualifier_stage(campaign_id: int) -> CampaignStage:
    """Convenience full runner for EWC Qualifier stage."""
    sim_ewc_qualifier_all_interactive(campaign_id)
    return get_stage_record(campaign_id, 'ewc_qualifier')


# ─────────────────────────────────────────────────────────────────────────────
# VCT Masters (Masters Toronto) Stage Execution & Interactive Resolving
# ─────────────────────────────────────────────────────────────────────────────

def get_master_data(campaign_id: int) -> Optional[Dict[str, Any]]:
    """Retrieve full Masters Toronto data (roster, matches, standings) for a campaign."""
    stage = get_stage_record(campaign_id, 'master')
    if not stage or not stage.stage_data:
        return None
    data = json.loads(stage.stage_data)
    roster = data.get('roster', [])

    if roster and len(roster) == 12 and ('result' not in data or not data['result'] or not data['result'].get('swiss_matches')):
        data['result'] = init_master_state(roster)
        stage.stage_data = json.dumps(data)
        db.session.commit()

    return data


def _check_and_finalize_master(campaign: Campaign, stage: CampaignStage, data: Dict[str, Any]):
    """Award CP, story ratings, and advance campaign when Masters Toronto completes."""
    res = data.get('result')
    if res and res.get('status') == 'completed':
        if not res.get('rewards_awarded'):
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

        stage.status = 'completed'
        stage.completed_at = datetime.now(timezone.utc)
        campaign.current_stage = 'ewc'

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


def sim_master_round_interactive(campaign_id: int) -> Dict[str, Any]:
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

    _check_and_finalize_master(campaign, stage, data)
    db.session.commit()
    return {'sim_count': sim_count, 'master_data': master_data}


def sim_master_tournament_interactive(campaign_id: int) -> Dict[str, Any]:
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

    _check_and_finalize_master(campaign, stage, data)
    db.session.commit()
    return {'master_data': master_data}


def run_master_stage(campaign_id: int) -> Dict[str, Any]:
    """Execute VCT Masters (Masters Toronto) 12-team international tournament."""
    sim_master_tournament_interactive(campaign_id)
    stage = get_stage_record(campaign_id, 'master')
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

