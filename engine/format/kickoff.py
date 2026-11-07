"""
engine/format/kickoff.py — VCT Kickoff 2025 Format Engine

Format Specification:
- 12 teams per region (8 Partner teams + 4 Open Qualifier teams)
- Double-Elimination Bracket with 4 Byes:
  * 4 teams receive direct byes into Upper Bracket Quarterfinals (Round 2):
    - Year 1: Top 4 Partner teams with highest Story Rating.
    - Year 2+: 4 teams that qualified for Champions the previous year.
  * 8 teams play in Upper Round 1:
    - 4 remaining Partner teams vs 4 Open Qualifier teams (Defend the throne match-ups).
- Match structure (Exactly 22 matches per region):
  * Upper Bracket (11 matches):
    - Upper R1: 4 matches (BO3)
    - Upper Quarterfinals: 4 matches (BO3) (4 Bye teams vs 4 Upper R1 winners)
    - Upper Semifinals: 2 matches (BO3)
    - Upper Final: 1 match (BO3) -> Winner to Grand Final & secures Major spot #1!
  * Lower Bracket (10 matches):
    - Lower R1: 4 matches (BO3) (4 losers from Upper R1 vs 4 losers from Upper QF). Losers out (Rank 9-12).
    - Lower R2: 2 matches (BO3) (4 winners from Lower R1 play each other). Losers out (Rank 7-8).
    - Lower R3 (Quarterfinals): 2 matches (BO3) (2 winners Lower R2 vs 2 losers Upper SF). Losers out (Rank 5-6).
    - Lower Semifinal: 1 match (BO3). Loser finishes 4th place (+1 CP). Winner to Lower Final.
    - Lower Final: 1 match (BO5). Loser finishes 3rd place (+1 CP). Winner to Grand Final & secures Major spot #2!
  * Grand Final: 1 match (BO5)
    - Winner: Kickoff Champion (+3 CP, Major Regional Seed 1)
    - Loser: Kickoff Runner-up (+2 CP, Major Regional Seed 2)

Total: 22 matches per region (88 matches for 4 regions).
"""

import random
from typing import List, Dict, Tuple, Optional, Any
from engine.points import get_stage_points


def kickoff_config() -> Dict[str, Any]:
    return {
        'team_count': 12,
        'partner_count': 8,
        'open_qualifier_count': 4,
        'byes_count': 4,
        'upper_r1_teams': 8,
        'upper_matches': 11,
        'lower_matches': 10,
        'grand_final_matches': 1,
        'total_matches': 22,
        'major_qualifiers': 2,
    }


def seed_kickoff_participants(participants: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Seed the 12 participants into:
    - 4 Bye teams (Seeds 1..4):
      * Priority 1: Teams that qualified for Champions the previous year (prev_champions_qualified == True).
        Can be Partner or Non-Partner (who qualified via Open Qualifier).
        Sorted by prev_champions_seed ascending (1..4) or rating descending.
      * Priority 2 (Fallback / Year 1): If fewer than 4 Champions qualifiers are present (e.g. Year 1 save,
        or a non-partner Champions team failed in Open Qualifier), the remaining Bye slots
        are awarded to the Partner teams with highest Story/Current Rating.
    - 4 Upper R1 High Seeds (Seeds 5..8):
      * The top 4 of the remaining 8 teams (prioritizing Partner teams, then rating).
    - 4 Upper R1 Low Seeds (Seeds 9..12):
      * The remaining 4 teams (sorted by oq_seed or rating).
    
    Each participant is expected to have:
    - 'id' or 'club_id'
    - 'name', 'short_code'
    - 'is_partner': bool
    - 'story_rating': int
    - Optional: 'prev_champions_qualified': bool, 'prev_champions_seed': int, 'oq_seed': int
    """
    # 1. Identify teams that qualified for Champions the previous year
    champions_qualifiers = [p for p in participants if p.get('prev_champions_qualified')]
    champions_qualifiers.sort(key=lambda x: (
        x.get('prev_champions_seed') if x.get('prev_champions_seed') is not None else 99,
        -(x.get('story_rating') or x.get('current_rating') or 80)
    ))

    byes = list(champions_qualifiers[:4])
    bye_ids = {b.get('id') or b.get('club_id') for b in byes}

    # If fewer than 4 Byes (Year 1 or missing qualifiers), fill with top partner teams
    if len(byes) < 4:
        eligible_partners = [
            p for p in participants
            if p.get('is_partner') and (p.get('id') or p.get('club_id')) not in bye_ids
        ]
        eligible_partners.sort(key=lambda x: -(x.get('story_rating') or x.get('current_rating') or 80))
        needed = 4 - len(byes)
        for p in eligible_partners[:needed]:
            byes.append(p)
            bye_ids.add(p.get('id') or p.get('club_id'))

    # 2. The remaining 8 teams play in Upper Round 1 (Seeds 5..12)
    remaining_teams = [
        p for p in participants
        if (p.get('id') or p.get('club_id')) not in bye_ids
    ]

    rem_partners = [p for p in remaining_teams if p.get('is_partner')]
    rem_non_partners = [p for p in remaining_teams if not p.get('is_partner')]

    rem_partners.sort(key=lambda x: -(x.get('story_rating') or x.get('current_rating') or 80))
    rem_non_partners.sort(key=lambda x: x.get('oq_seed', 99))

    # Standard distribution:
    # If 4 partners and 4 non-partners remain:
    # Seeds 5..8 are rem_partners[:4], Seeds 9..12 are rem_non_partners[:4]
    # If a non-partner made it to Byes, then rem_partners has 5 teams, rem_non_partners has 3 teams.
    # Top 4 partners get Seeds 5..8.
    # The 5th partner + 3 non-partners get Seeds 9..12.
    if len(rem_partners) >= 4:
        ub_teams = rem_partners[:4]
        lower_teams = rem_partners[4:] + rem_non_partners
        lower_teams.sort(key=lambda x: (
            0 if x.get('is_partner') else 1,
            x.get('oq_seed', 99) if not x.get('is_partner') else -(x.get('story_rating') or 80)
        ))
    else:
        ub_teams = list(rem_partners)
        needed_ub = 4 - len(ub_teams)
        ub_teams.extend(rem_non_partners[:needed_ub])
        lower_teams = rem_non_partners[needed_ub:]

    seeded_dict = {}
    for idx, team in enumerate(byes):
        seeded_dict[idx + 1] = team  # Seeds 1..4 (Byes)

    for idx, team in enumerate(ub_teams):
        seeded_dict[idx + 5] = team  # Seeds 5..8 (Upper R1 Team A)

    for idx, team in enumerate(lower_teams):
        seeded_dict[idx + 9] = team  # Seeds 9..12 (Upper R1 Team B)

    return {
        'seeds': seeded_dict,
        'byes': byes,
        'upper_partners': ub_teams,
        'open_qualifiers': lower_teams,
    }


def get_kickoff_bracket_templates() -> List[Dict[str, Any]]:
    """Generate the 22 match templates for the 12-team Double Elimination bracket.
    
    Structure:
    - Upper R1: 4 matches (BO3)
      * UB_R1_M1: Seed 5 (Partner) vs Seed 12 (OQ 4)
      * UB_R1_M2: Seed 6 (Partner) vs Seed 11 (OQ 3)
      * UB_R1_M3: Seed 7 (Partner) vs Seed 10 (OQ 2)
      * UB_R1_M4: Seed 8 (Partner) vs Seed 9  (OQ 1)
    
    - Upper QF: 4 matches (BO3)
      * UB_QF_M1: Seed 1 (Bye 1) vs Winner UB_R1_M1
      * UB_QF_M2: Seed 4 (Bye 4) vs Winner UB_R1_M2
      * UB_QF_M3: Seed 2 (Bye 2) vs Winner UB_R1_M3
      * UB_QF_M4: Seed 3 (Bye 3) vs Winner UB_R1_M4
    
    - Upper SF: 2 matches (BO3)
      * UB_SF_M1: Winner UB_QF_M1 vs Winner UB_QF_M2
      * UB_SF_M2: Winner UB_QF_M3 vs Winner UB_QF_M4
      
    - Upper Final: 1 match (BO3)
      * UB_Final: Winner UB_SF_M1 vs Winner UB_SF_M2
      (Winner to Grand Final & secures Major spot #1; Loser to LB Final)
      
    - Lower R1: 4 matches (BO3) - Cross-paired to prevent rematches
      * LB_R1_M1: Loser UB_R1_M1 vs Loser UB_QF_M2
      * LB_R1_M2: Loser UB_R1_M2 vs Loser UB_QF_M1
      * LB_R1_M3: Loser UB_R1_M3 vs Loser UB_QF_M4
      * LB_R1_M4: Loser UB_R1_M4 vs Loser UB_QF_M3
      (Losers eliminated, Rank 9-12)
      
    - Lower R2: 2 matches (BO3)
      * LB_R2_M1: Winner LB_R1_M1 vs Winner LB_R1_M2
      * LB_R2_M2: Winner LB_R1_M3 vs Winner LB_R1_M4
      (Losers eliminated, Rank 7-8)
      
    - Lower R3 (Quarterfinals): 2 matches (BO3) - Cross-paired
      * LB_R3_M1: Winner LB_R2_M1 vs Loser UB_SF_M2
      * LB_R3_M2: Winner LB_R2_M2 vs Loser UB_SF_M1
      (Losers eliminated, Rank 5-6)
      
    - Lower Semifinal: 1 match (BO3)
      * LB_Semi: Winner LB_R3_M1 vs Winner LB_R3_M2
      (Loser eliminated, Rank 4, +1 CP; Winner to LB Final)
      
    - Lower Final: 1 match (BO5)
      * LB_Final: Winner LB_Semi vs Loser UB_Final
      (Loser eliminated, Rank 3, +1 CP; Winner to Grand Final & secures Major spot #2!)
      
    - Grand Final: 1 match (BO5)
      * Grand_Final: Winner UB_Final vs Winner LB_Final
      (Winner: Champion, +3 CP, Major Seed 1; Loser: Runner-up, +2 CP, Major Seed 2)
    """
    return [
        # ── Upper Round 1 (4 matches, BO3) ──
        {
            'match_code': 'UB_R1_M1',
            'round_type': 'upper',
            'round_name': 'upper_r1_m1',
            'label': 'Upper Round 1 - Trận 1',
            'team_a_source': {'type': 'seed', 'value': 5},
            'team_b_source': {'type': 'seed', 'value': 12},
            'bo': 3,
        },
        {
            'match_code': 'UB_R1_M2',
            'round_type': 'upper',
            'round_name': 'upper_r1_m2',
            'label': 'Upper Round 1 - Trận 2',
            'team_a_source': {'type': 'seed', 'value': 6},
            'team_b_source': {'type': 'seed', 'value': 11},
            'bo': 3,
        },
        {
            'match_code': 'UB_R1_M3',
            'round_type': 'upper',
            'round_name': 'upper_r1_m3',
            'label': 'Upper Round 1 - Trận 3',
            'team_a_source': {'type': 'seed', 'value': 7},
            'team_b_source': {'type': 'seed', 'value': 10},
            'bo': 3,
        },
        {
            'match_code': 'UB_R1_M4',
            'round_type': 'upper',
            'round_name': 'upper_r1_m4',
            'label': 'Upper Round 1 - Trận 4',
            'team_a_source': {'type': 'seed', 'value': 8},
            'team_b_source': {'type': 'seed', 'value': 9},
            'bo': 3,
        },

        # ── Upper Quarterfinals (4 matches, BO3) ──
        {
            'match_code': 'UB_QF_M1',
            'round_type': 'upper',
            'round_name': 'upper_qf_m1',
            'label': 'Tứ kết Nhánh thắng 1',
            'team_a_source': {'type': 'seed', 'value': 1},
            'team_b_source': {'type': 'winner_of', 'value': 'upper_r1_m1'},
            'bo': 3,
        },
        {
            'match_code': 'UB_QF_M2',
            'round_type': 'upper',
            'round_name': 'upper_qf_m2',
            'label': 'Tứ kết Nhánh thắng 2',
            'team_a_source': {'type': 'seed', 'value': 4},
            'team_b_source': {'type': 'winner_of', 'value': 'upper_r1_m2'},
            'bo': 3,
        },
        {
            'match_code': 'UB_QF_M3',
            'round_type': 'upper',
            'round_name': 'upper_qf_m3',
            'label': 'Tứ kết Nhánh thắng 3',
            'team_a_source': {'type': 'seed', 'value': 2},
            'team_b_source': {'type': 'winner_of', 'value': 'upper_r1_m3'},
            'bo': 3,
        },
        {
            'match_code': 'UB_QF_M4',
            'round_type': 'upper',
            'round_name': 'upper_qf_m4',
            'label': 'Tứ kết Nhánh thắng 4',
            'team_a_source': {'type': 'seed', 'value': 3},
            'team_b_source': {'type': 'winner_of', 'value': 'upper_r1_m4'},
            'bo': 3,
        },

        # ── Upper Semifinals (2 matches, BO3) ──
        {
            'match_code': 'UB_SF_M1',
            'round_type': 'upper',
            'round_name': 'upper_sf_m1',
            'label': 'Bán kết Nhánh thắng 1',
            'team_a_source': {'type': 'winner_of', 'value': 'upper_qf_m1'},
            'team_b_source': {'type': 'winner_of', 'value': 'upper_qf_m2'},
            'bo': 3,
        },
        {
            'match_code': 'UB_SF_M2',
            'round_type': 'upper',
            'round_name': 'upper_sf_m2',
            'label': 'Bán kết Nhánh thắng 2',
            'team_a_source': {'type': 'winner_of', 'value': 'upper_qf_m3'},
            'team_b_source': {'type': 'winner_of', 'value': 'upper_qf_m4'},
            'bo': 3,
        },

        # ── Upper Final (1 match, BO3) ──
        {
            'match_code': 'UB_Final',
            'round_type': 'upper',
            'round_name': 'upper_final',
            'label': 'Chung kết Nhánh thắng (Tranh vé Major 1)',
            'team_a_source': {'type': 'winner_of', 'value': 'upper_sf_m1'},
            'team_b_source': {'type': 'winner_of', 'value': 'upper_sf_m2'},
            'bo': 3,
            'is_major_decider': 1,  # Winner earns Major qualification spot #1
        },

        # ── Lower Round 1 (4 matches, BO3) ──
        {
            'match_code': 'LB_R1_M1',
            'round_type': 'lower',
            'round_name': 'lower_r1_m1',
            'label': 'Vòng 1 Nhánh thua 1',
            'team_a_source': {'type': 'loser_of', 'value': 'upper_r1_m1'},
            'team_b_source': {'type': 'loser_of', 'value': 'upper_qf_m2'},
            'bo': 3,
        },
        {
            'match_code': 'LB_R1_M2',
            'round_type': 'lower',
            'round_name': 'lower_r1_m2',
            'label': 'Vòng 1 Nhánh thua 2',
            'team_a_source': {'type': 'loser_of', 'value': 'upper_r1_m2'},
            'team_b_source': {'type': 'loser_of', 'value': 'upper_qf_m1'},
            'bo': 3,
        },
        {
            'match_code': 'LB_R1_M3',
            'round_type': 'lower',
            'round_name': 'lower_r1_m3',
            'label': 'Vòng 1 Nhánh thua 3',
            'team_a_source': {'type': 'loser_of', 'value': 'upper_r1_m3'},
            'team_b_source': {'type': 'loser_of', 'value': 'upper_qf_m4'},
            'bo': 3,
        },
        {
            'match_code': 'LB_R1_M4',
            'round_type': 'lower',
            'round_name': 'lower_r1_m4',
            'label': 'Vòng 1 Nhánh thua 4',
            'team_a_source': {'type': 'loser_of', 'value': 'upper_r1_m4'},
            'team_b_source': {'type': 'loser_of', 'value': 'upper_qf_m3'},
            'bo': 3,
        },

        # ── Lower Round 2 (2 matches, BO3) ──
        {
            'match_code': 'LB_R2_M1',
            'round_type': 'lower',
            'round_name': 'lower_r2_m1',
            'label': 'Vòng 2 Nhánh thua 1',
            'team_a_source': {'type': 'winner_of', 'value': 'lower_r1_m1'},
            'team_b_source': {'type': 'winner_of', 'value': 'lower_r1_m2'},
            'bo': 3,
        },
        {
            'match_code': 'LB_R2_M2',
            'round_type': 'lower',
            'round_name': 'lower_r2_m2',
            'label': 'Vòng 2 Nhánh thua 2',
            'team_a_source': {'type': 'winner_of', 'value': 'lower_r1_m3'},
            'team_b_source': {'type': 'winner_of', 'value': 'lower_r1_m4'},
            'bo': 3,
        },

        # ── Lower Round 3 (Lower Quarterfinals - 2 matches, BO3) ──
        {
            'match_code': 'LB_R3_M1',
            'round_type': 'lower',
            'round_name': 'lower_r3_m1',
            'label': 'Tứ kết Nhánh thua 1',
            'team_a_source': {'type': 'winner_of', 'value': 'lower_r2_m1'},
            'team_b_source': {'type': 'loser_of', 'value': 'upper_sf_m2'},
            'bo': 3,
        },
        {
            'match_code': 'LB_R3_M2',
            'round_type': 'lower',
            'round_name': 'lower_r3_m2',
            'label': 'Tứ kết Nhánh thua 2',
            'team_a_source': {'type': 'winner_of', 'value': 'lower_r2_m2'},
            'team_b_source': {'type': 'loser_of', 'value': 'upper_sf_m1'},
            'bo': 3,
        },

        # ── Lower Semifinal (1 match, BO3) ──
        {
            'match_code': 'LB_Semi',
            'round_type': 'lower',
            'round_name': 'lower_semifinal',
            'label': 'Bán kết Nhánh thua (Tranh vé vào Chung kết nhánh thua)',
            'team_a_source': {'type': 'winner_of', 'value': 'lower_r3_m1'},
            'team_b_source': {'type': 'winner_of', 'value': 'lower_r3_m2'},
            'bo': 3,
            'loser_standing_rank': 4,  # Loser is Rank 4 (+1 CP)
        },

        # ── Lower Final (1 match, BO5) ──
        {
            'match_code': 'LB_Final',
            'round_type': 'lower',
            'round_name': 'lower_final',
            'label': 'Chung kết Nhánh thua (Tranh vé Major 2 & Vé Chung kết tổng)',
            'team_a_source': {'type': 'winner_of', 'value': 'lower_semifinal'},
            'team_b_source': {'type': 'loser_of', 'value': 'upper_final'},
            'bo': 5,
            'loser_standing_rank': 3,  # Loser is Rank 3 (+1 CP)
            'is_major_decider': 2,    # Winner earns Major qualification spot #2
        },

        # ── Grand Final (1 match, BO5) ──
        {
            'match_code': 'Grand_Final',
            'round_type': 'grand',
            'round_name': 'grand_final',
            'label': 'Chung kết Tổng (Phân định Vô địch VCT Kickoff & Hạt giống 1 Major)',
            'team_a_source': {'type': 'winner_of', 'value': 'upper_final'},
            'team_b_source': {'type': 'winner_of', 'value': 'lower_final'},
            'bo': 5,
            'is_championship_match': True,
        },
    ]


def resolve_kickoff_slot(template: Dict[str, Any], seeds: Dict[int, Dict[str, Any]], completed_matches: Dict[str, Dict[str, Any]]) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """Resolve team_a and team_b for a match template given seeds and completed matches."""
    def resolve_source(src: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        stype = src.get('type')
        sval = src.get('value')
        if stype == 'seed':
            return seeds.get(sval)
        if stype == 'winner_of':
            m = completed_matches.get(sval)
            return m.get('winner') if m else None
        if stype == 'loser_of':
            m = completed_matches.get(sval)
            return m.get('loser') if m else None
        return None

    team_a = resolve_source(template['team_a_source'])
    team_b = resolve_source(template['team_b_source'])
    return team_a, team_b


def _gen_map_score_kickoff(winner_rating: int, loser_rating: int) -> Tuple[int, int]:
    """Generate map score based on power rating difference for Kickoff matches."""
    diff = winner_rating - loser_rating
    if diff >= 25:
        score_pool = [(13, 2), (13, 3), (13, 4), (13, 5), (13, 6)]
    elif diff >= 15:
        score_pool = [(13, 4), (13, 5), (13, 6), (13, 7), (13, 8)]
    elif diff >= 8:
        score_pool = [(13, 6), (13, 7), (13, 8), (13, 9), (13, 10)]
    elif diff >= 2:
        score_pool = [(13, 8), (13, 9), (13, 10), (13, 11)]
    elif diff >= -5:
        score_pool = [(13, 9), (13, 10), (13, 11), (14, 12), (15, 13)]
    elif diff >= -15:
        score_pool = [(13, 10), (13, 11), (14, 12), (15, 13)]
    else:
        score_pool = [(13, 11), (14, 12), (15, 13), (16, 14), (17, 15)]
    return random.choice(score_pool)


def simulate_kickoff_match(team_a: Dict[str, Any], team_b: Dict[str, Any], bo: int = 3,
                           rating_lookup: Optional[Dict[int, int]] = None,
                           form_lookup: Optional[Dict[int, int]] = None,
                           manual_override: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Simulate a Kickoff match or apply manual override.
    
    manual_override: optional dict:
      - 'winner_id': int (force this team to win)
      - 'maps': list of {'team_a_score': int, 'team_b_score': int}
    """
    id_a = team_a['id'] if 'id' in team_a else team_a.get('club_id')
    id_b = team_b['id'] if 'id' in team_b else team_b.get('club_id')

    r_a = (rating_lookup.get(id_a) if rating_lookup else None) or team_a.get('story_rating') or team_a.get('current_rating') or 80
    r_b = (rating_lookup.get(id_b) if rating_lookup else None) or team_b.get('story_rating') or team_b.get('current_rating') or 80

    f_a = (form_lookup.get(id_a) if form_lookup else None) or team_a.get('form_modifier') or 0
    f_b = (form_lookup.get(id_b) if form_lookup else None) or team_b.get('form_modifier') or 0

    eff_a = r_a + f_a
    eff_b = r_b + f_b

    target_wins = 3 if bo == 5 else 2
    max_maps = bo

    if manual_override and manual_override.get('winner_id') in (id_a, id_b):
        winner_id = manual_override['winner_id']
        winner = team_a if winner_id == id_a else team_b
        loser = team_b if winner == team_a else team_a
        
        custom_maps = manual_override.get('maps', [])
        if custom_maps:
            wins_a = sum(1 for m in custom_maps if m['team_a_score'] > m['team_b_score'])
            wins_b = sum(1 for m in custom_maps if m['team_b_score'] > m['team_a_score'])
            return {
                'team_a': team_a, 'team_b': team_b,
                'team_a_id': id_a, 'team_b_id': id_b,
                'team_a_score': wins_a, 'team_b_score': wins_b,
                'winner': winner, 'loser': loser,
                'winner_id': winner_id, 'loser_id': loser['id'] if 'id' in loser else loser.get('club_id'),
                'maps': custom_maps,
                'bo': bo,
                'is_manual': True,
            }
        else:
            # Default clean win (e.g. 2-0 / 2-1 or 3-0 / 3-1)
            wins_a = target_wins if winner == team_a else 1
            wins_b = target_wins if winner == team_b else 1
            maps = []
            for i in range(target_wins):
                sc_w, sc_l = _gen_map_score_kickoff(eff_a if winner == team_a else eff_b, eff_b if winner == team_a else eff_a)
                maps.append({
                    'map_number': i + 1,
                    'team_a_score': sc_w if winner == team_a else sc_l,
                    'team_b_score': sc_l if winner == team_a else sc_w,
                    'winner_id': winner_id,
                })
            return {
                'team_a': team_a, 'team_b': team_b,
                'team_a_id': id_a, 'team_b_id': id_b,
                'team_a_score': wins_a, 'team_b_score': wins_b,
                'winner': winner, 'loser': loser,
                'winner_id': winner_id, 'loser_id': loser['id'] if 'id' in loser else loser.get('club_id'),
                'maps': maps,
                'bo': bo,
                'is_manual': True,
            }

    # Dynamic rating probability
    diff = eff_a - eff_b
    prob_a = max(0.15, min(0.85, 0.50 + diff * 0.0125))

    wins_a = 0
    wins_b = 0
    maps = []

    for map_idx in range(max_maps):
        roll = random.random()
        if roll < prob_a:
            sc_win, sc_lose = _gen_map_score_kickoff(eff_a, eff_b)
            wins_a += 1
            maps.append({
                'map_number': map_idx + 1,
                'team_a_score': sc_win,
                'team_b_score': sc_lose,
                'winner_id': id_a,
            })
        else:
            sc_win, sc_lose = _gen_map_score_kickoff(eff_b, eff_a)
            wins_b += 1
            maps.append({
                'map_number': map_idx + 1,
                'team_a_score': sc_lose,
                'team_b_score': sc_win,
                'winner_id': id_b,
            })

        if wins_a >= target_wins or wins_b >= target_wins:
            break

    winner = team_a if wins_a >= target_wins else team_b
    loser = team_b if winner == team_a else team_a
    winner_id = id_a if winner == team_a else id_b
    loser_id = id_b if winner == team_a else id_a

    return {
        'team_a': team_a,
        'team_b': team_b,
        'team_a_id': id_a,
        'team_b_id': id_b,
        'team_a_score': wins_a,
        'team_b_score': wins_b,
        'winner': winner,
        'loser': loser,
        'winner_id': winner_id,
        'loser_id': loser_id,
        'maps': maps,
        'bo': bo,
        'is_manual': False,
    }


def _get_kickoff_source_label(src: Dict[str, Any]) -> str:
    stype = src.get('type')
    sval = src.get('value')
    if stype == 'seed':
        return f"Hạt giống #{sval}"

    code_labels = {
        'upper_r1_m1': 'Thắng UB R1 - Trận 1',
        'upper_r1_m2': 'Thắng UB R1 - Trận 2',
        'upper_r1_m3': 'Thắng UB R1 - Trận 3',
        'upper_r1_m4': 'Thắng UB R1 - Trận 4',
        'upper_qf_m1': 'Thắng Tứ kết NT 1',
        'upper_qf_m2': 'Thắng Tứ kết NT 2',
        'upper_qf_m3': 'Thắng Tứ kết NT 3',
        'upper_qf_m4': 'Thắng Tứ kết NT 4',
        'upper_sf_m1': 'Thắng Bán kết NT 1',
        'upper_sf_m2': 'Thắng Bán kết NT 2',
        'upper_final': 'Thắng Chung kết NT',
        'lower_r1_m1': 'Thắng Vòng 1 Nhánh thua 1',
        'lower_r1_m2': 'Thắng Vòng 1 Nhánh thua 2',
        'lower_r1_m3': 'Thắng Vòng 1 Nhánh thua 3',
        'lower_r1_m4': 'Thắng Vòng 1 Nhánh thua 4',
        'lower_r2_m1': 'Thắng Vòng 2 Nhánh thua 1',
        'lower_r2_m2': 'Thắng Vòng 2 Nhánh thua 2',
        'lower_r3_m1': 'Thắng Tứ kết Nhánh thua 1',
        'lower_r3_m2': 'Thắng Tứ kết Nhánh thua 2',
        'lower_semifinal': 'Thắng Bán kết Nhánh thua',
        'lower_final': 'Thắng Chung kết Nhánh thua',
    }
    loser_labels = {
        'upper_r1_m1': 'Thua UB R1 - Trận 1',
        'upper_r1_m2': 'Thua UB R1 - Trận 2',
        'upper_r1_m3': 'Thua UB R1 - Trận 3',
        'upper_r1_m4': 'Thua UB R1 - Trận 4',
        'upper_qf_m1': 'Thua Tứ kết NT 1',
        'upper_qf_m2': 'Thua Tứ kết NT 2',
        'upper_qf_m3': 'Thua Tứ kết NT 3',
        'upper_qf_m4': 'Thua Tứ kết NT 4',
        'upper_sf_m1': 'Thua Bán kết NT 1',
        'upper_sf_m2': 'Thua Bán kết NT 2',
        'upper_final': 'Thua Chung kết NT',
    }
    if stype == 'winner_of':
        return code_labels.get(sval, f"Thắng {sval}")
    if stype == 'loser_of':
        return loser_labels.get(sval, f"Thua {sval}")
    return "TBD"


def _resolve_kickoff_slots_for_region(region_data: Dict[str, Any]):
    """Resolve team_a and team_b for any kickoff match where sources are determined."""
    raw_seeds = region_data.get('seeds', {})
    seeds = {int(k): v for k, v in raw_seeds.items()}

    matches = region_data.get('matches', [])
    completed_map = {m['round_name']: m for m in matches if m['status'] == 'completed'}

    def resolve_team(src):
        stype = src['type']
        sval = src['value']
        if stype == 'seed':
            return seeds.get(int(sval))
        if stype == 'winner_of':
            feeder = completed_map.get(sval)
            return feeder['winner'] if feeder else None
        if stype == 'loser_of':
            feeder = completed_map.get(sval)
            return feeder['loser'] if feeder else None
        return None

    for m in matches:
        if m['status'] == 'pending':
            t_a = resolve_team(m['team_a_source'])
            t_b = resolve_team(m['team_b_source'])

            if t_a:
                m['team_a'] = t_a
                m['team_a_id'] = t_a['id']
                m['placeholder_a'] = None
            else:
                m['team_a'] = None
                m['team_a_id'] = None
                m['placeholder_a'] = _get_kickoff_source_label(m['team_a_source'])

            if t_b:
                m['team_b'] = t_b
                m['team_b_id'] = t_b['id']
                m['placeholder_b'] = None
            else:
                m['team_b'] = None
                m['team_b_id'] = None
                m['placeholder_b'] = _get_kickoff_source_label(m['team_b_source'])


def init_kickoff_region_state(region_slug: str, participants: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Initialize state for VCT Kickoff double-elimination bracket (22 matches)."""
    if len(participants) != 12:
        raise ValueError(f"Kickoff requires exactly 12 teams, received {len(participants)}")

    norm_participants = []
    for p in participants:
        norm = dict(p)
        c_id = norm.get('id') or norm.get('club_id')
        norm['id'] = c_id
        norm['club_id'] = c_id
        norm_participants.append(norm)

    seeding_info = seed_kickoff_participants(norm_participants)
    seeds = seeding_info['seeds']

    templates = get_kickoff_bracket_templates()
    matches = []
    for idx, tpl in enumerate(templates):
        match_id = f"ko_{region_slug}_{tpl['round_name']}"
        matches.append({
            'id': match_id,
            'round_name': tpl['round_name'],
            'round_type': tpl['round_type'],
            'match_code': tpl['match_code'],
            'label': tpl['label'],
            'match_order': idx + 1,
            'bo': tpl['bo'],
            'status': 'pending',
            'team_a_source': tpl['team_a_source'],
            'team_b_source': tpl['team_b_source'],
            'team_a': None,
            'team_b': None,
            'team_a_id': None,
            'team_b_id': None,
            'placeholder_a': None,
            'placeholder_b': None,
            'team_a_score': 0,
            'team_b_score': 0,
            'winner_id': None,
            'loser_id': None,
            'winner': None,
            'loser': None,
            'maps': [],
            'is_manual': False,
            'is_major_decider': tpl.get('is_major_decider'),
            'loser_standing_rank': tpl.get('loser_standing_rank'),
        })

    region_data = {
        'region_slug': region_slug,
        'status': 'in_progress',
        'participants': norm_participants,
        'seeds': {k: v for k, v in seeds.items()},
        'matches': matches,
        'completed_dict': {},
        'standings': [],
        'major_qualifiers': [],
        'total_matches_count': 0,
    }

    _resolve_kickoff_slots_for_region(region_data)
    return region_data


def advance_kickoff_region(region_data: Dict[str, Any]) -> bool:
    """Advance the Kickoff tournament state:
    - Resolves placeholder slots in downstream matches
    - Computes real-time standings
    - Determines Major qualifiers and final CP awards when Grand Final finishes.
    """
    matches = region_data.get('matches', [])
    completed_dict = {m['round_name']: m for m in matches if m['status'] == 'completed'}
    region_data['completed_dict'] = completed_dict

    _resolve_kickoff_slots_for_region(region_data)

    standings = []
    # If Grand Final is completed:
    if 'grand_final' in completed_dict:
        gf = completed_dict['grand_final']
        lb_final = completed_dict.get('lower_final')
        lb_semi = completed_dict.get('lower_semifinal')

        champion = gf['winner']
        runner_up = gf['loser']
        third_place = lb_final['loser'] if lb_final else None
        fourth_place = lb_semi['loser'] if lb_semi else None

        standings.append({
            'rank': 1, 'team': champion, 'club_id': champion['id'],
            'title': 'Vô địch Kickoff', 'major_qualified': True, 'major_seed': 1,
            'championship_points': get_stage_points('kickoff', rank=1),  # 3 CP
        })
        standings.append({
            'rank': 2, 'team': runner_up, 'club_id': runner_up['id'],
            'title': 'Á quân Kickoff', 'major_qualified': True, 'major_seed': 2,
            'championship_points': get_stage_points('kickoff', rank=2),  # 2 CP
        })
        if third_place:
            standings.append({
                'rank': 3, 'team': third_place, 'club_id': third_place['id'],
                'title': 'Hạng 3 (Thua Chung kết Nhánh thua)', 'major_qualified': False, 'major_seed': None,
                'championship_points': get_stage_points('kickoff', rank=3),  # 1 CP
            })
        if fourth_place:
            standings.append({
                'rank': 4, 'team': fourth_place, 'club_id': fourth_place['id'],
                'title': 'Hạng 4 (Thua Bán kết Nhánh thua)', 'major_qualified': False, 'major_seed': None,
                'championship_points': get_stage_points('kickoff', rank=4),  # 1 CP
            })

        for r_name in ['lower_r3_m1', 'lower_r3_m2']:
            if r_name in completed_dict:
                t = completed_dict[r_name]['loser']
                standings.append({
                    'rank': 5, 'team': t, 'club_id': t['id'],
                    'title': 'Top 5-6 (Thua Tứ kết Nhánh thua)', 'major_qualified': False, 'major_seed': None,
                    'championship_points': 0,
                })

        for r_name in ['lower_r2_m1', 'lower_r2_m2']:
            if r_name in completed_dict:
                t = completed_dict[r_name]['loser']
                standings.append({
                    'rank': 7, 'team': t, 'club_id': t['id'],
                    'title': 'Top 7-8 (Thua Vòng 2 Nhánh thua)', 'major_qualified': False, 'major_seed': None,
                    'championship_points': 0,
                })

        for r_name in ['lower_r1_m1', 'lower_r1_m2', 'lower_r1_m3', 'lower_r1_m4']:
            if r_name in completed_dict:
                t = completed_dict[r_name]['loser']
                standings.append({
                    'rank': 9, 'team': t, 'club_id': t['id'],
                    'title': 'Top 9-12 (Thua Vòng 1 Nhánh thua)', 'major_qualified': False, 'major_seed': None,
                    'championship_points': 0,
                })

        region_data['standings'] = standings
        region_data['champion'] = champion
        region_data['runner_up'] = runner_up
        region_data['major_qualifiers'] = [champion, runner_up]
        region_data['matches_completed'] = True
        region_data['status'] = 'completed'
        region_data['total_matches_count'] = len(matches)
        return True

    # Standings in progress
    for r_name in ['lower_r1_m1', 'lower_r1_m2', 'lower_r1_m3', 'lower_r1_m4']:
        if r_name in completed_dict:
            t = completed_dict[r_name]['loser']
            standings.append({
                'rank': 9, 'team': t, 'club_id': t['id'],
                'title': 'Top 9-12 (Đã bị loại)', 'major_qualified': False, 'major_seed': None,
                'championship_points': 0,
            })
    for r_name in ['lower_r2_m1', 'lower_r2_m2']:
        if r_name in completed_dict:
            t = completed_dict[r_name]['loser']
            standings.append({
                'rank': 7, 'team': t, 'club_id': t['id'],
                'title': 'Top 7-8 (Đã bị loại)', 'major_qualified': False, 'major_seed': None,
                'championship_points': 0,
            })
    for r_name in ['lower_r3_m1', 'lower_r3_m2']:
        if r_name in completed_dict:
            t = completed_dict[r_name]['loser']
            standings.append({
                'rank': 5, 'team': t, 'club_id': t['id'],
                'title': 'Top 5-6 (Đã bị loại)', 'major_qualified': False, 'major_seed': None,
                'championship_points': 0,
            })
    if 'lower_semifinal' in completed_dict:
        t = completed_dict['lower_semifinal']['loser']
        standings.append({
            'rank': 4, 'team': t, 'club_id': t['id'],
            'title': 'Hạng 4 (Đã bị loại)', 'major_qualified': False, 'major_seed': None,
            'championship_points': get_stage_points('kickoff', rank=4),
        })
    if 'lower_final' in completed_dict:
        t = completed_dict['lower_final']['loser']
        standings.append({
            'rank': 3, 'team': t, 'club_id': t['id'],
            'title': 'Hạng 3 (Đã bị loại)', 'major_qualified': False, 'major_seed': None,
            'championship_points': get_stage_points('kickoff', rank=3),
        })

    region_data['standings'] = standings
    return False


def resolve_kickoff_match(region_data: Dict[str, Any], match_id_or_round_name: str,
                          winner_id: Optional[int] = None,
                          maps: Optional[List[Dict[str, Any]]] = None,
                          rating_lookup: Optional[Dict[int, int]] = None,
                          form_lookup: Optional[Dict[int, int]] = None) -> Dict[str, Any]:
    """Resolve a Kickoff match by either manual score or simulation roll."""
    matches = region_data.get('matches', [])
    match_obj = None
    for m in matches:
        if m['id'] == match_id_or_round_name or m['round_name'] == match_id_or_round_name:
            match_obj = m
            break

    if not match_obj:
        raise ValueError(f"Match {match_id_or_round_name} not found in Kickoff {region_data.get('region_slug')}")

    if not match_obj.get('team_a') or not match_obj.get('team_b'):
        raise ValueError(f"Match {match_obj['round_name']} does not have both teams determined yet")

    if region_data.get('is_confirmed'):
        raise ValueError("Không thể chỉnh sửa trận đấu vì kết quả giải đấu Kickoff của khu vực này đã được xác nhận và khóa chính thức!")

    # Guard against invalid edits if downstream matches are completed
    if match_obj.get('status') == 'completed':
        r_name = match_obj['round_name']
        downstream = [
            m for m in matches
            if m.get('team_a_source', {}).get('value') == r_name or m.get('team_b_source', {}).get('value') == r_name
        ]
        if any(m.get('status') == 'completed' for m in downstream):
            raise ValueError("Không thể sửa trận đấu này vì trận đấu nhánh tiếp theo đã hoàn thành!")

    t_a = match_obj['team_a']
    t_b = match_obj['team_b']
    id_a = t_a['id']
    id_b = t_b['id']
    bo = match_obj.get('bo', 3)
    target_wins = 3 if bo == 5 else 2

    r_a = (rating_lookup.get(id_a) if rating_lookup else None) or t_a.get('story_rating') or t_a.get('current_rating') or 80
    r_b = (rating_lookup.get(id_b) if rating_lookup else None) or t_b.get('story_rating') or t_b.get('current_rating') or 80

    if winner_id is not None:
        if winner_id not in (id_a, id_b):
            raise ValueError(f"winner_id {winner_id} is neither team A ({id_a}) nor team B ({id_b})")

        winner = t_a if winner_id == id_a else t_b
        loser = t_b if winner == t_a else t_a

        if maps:
            wins_a = sum(1 for m_item in maps if m_item['team_a_score'] > m_item['team_b_score'])
            wins_b = sum(1 for m_item in maps if m_item['team_b_score'] > m_item['team_a_score'])
            resolved_maps = maps
        else:
            wins_a = target_wins if winner == t_a else 1
            wins_b = target_wins if winner == t_b else 1
            resolved_maps = []
            for i in range(target_wins):
                sc_w, sc_l = _gen_map_score_kickoff(r_a if winner == t_a else r_b, r_b if winner == t_a else r_a)
                resolved_maps.append({
                    'map_number': i + 1,
                    'team_a_score': sc_w if winner == t_a else sc_l,
                    'team_b_score': sc_l if winner == t_a else sc_w,
                    'winner_id': winner_id,
                })

        match_obj.update({
            'status': 'completed',
            'team_a_score': wins_a,
            'team_b_score': wins_b,
            'winner_id': winner_id,
            'loser_id': loser['id'],
            'winner': winner,
            'loser': loser,
            'maps': resolved_maps,
            'is_manual': True,
        })
    else:
        # Simulation roll
        sim = simulate_kickoff_match(t_a, t_b, bo=bo, rating_lookup=rating_lookup, form_lookup=form_lookup)
        match_obj.update({
            'status': 'completed',
            'team_a_score': sim['team_a_score'],
            'team_b_score': sim['team_b_score'],
            'winner_id': sim['winner_id'],
            'loser_id': sim['loser_id'],
            'winner': sim['winner'],
            'loser': sim['loser'],
            'maps': sim['maps'],
            'is_manual': False,
        })

    advance_kickoff_region(region_data)
    return match_obj


def sim_kickoff_round(region_data: Dict[str, Any],
                      rating_lookup: Optional[Dict[int, int]] = None,
                      form_lookup: Optional[Dict[int, int]] = None) -> int:
    """Simulate all currently playable pending matches in the Kickoff bracket."""
    playable = [
        m for m in region_data.get('matches', [])
        if m['status'] == 'pending' and m.get('team_a') and m.get('team_b')
    ]
    if not playable:
        return 0

    count = 0
    for m in playable:
        resolve_kickoff_match(region_data, m['round_name'], winner_id=None,
                              rating_lookup=rating_lookup, form_lookup=form_lookup)
        count += 1

    return count


def sim_kickoff_remaining(region_data: Dict[str, Any],
                          rating_lookup: Optional[Dict[int, int]] = None,
                          form_lookup: Optional[Dict[int, int]] = None) -> int:
    """Simulate all remaining matches until Grand Final finishes."""
    total_sim = 0
    max_loops = 50
    loop_idx = 0

    while region_data.get('status') != 'completed' and loop_idx < max_loops:
        c = sim_kickoff_round(region_data, rating_lookup=rating_lookup, form_lookup=form_lookup)
        if c == 0:
            break
        total_sim += c
        loop_idx += 1

    return total_sim


def simulate_kickoff_tournament(region_slug: str, participants: List[Dict[str, Any]],
                                rating_lookup: Optional[Dict[int, int]] = None,
                                form_lookup: Optional[Dict[int, int]] = None,
                                manual_overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Execute complete 22-match VCT Kickoff double-elimination tournament."""
    state = init_kickoff_region_state(region_slug, participants)
    overrides = manual_overrides or {}

    max_loops = 50
    loop_idx = 0
    while state.get('status') != 'completed' and loop_idx < max_loops:
        playable = [m for m in state['matches'] if m['status'] == 'pending' and m.get('team_a') and m.get('team_b')]
        if not playable:
            break
        for m in playable:
            r_name = m['round_name']
            if r_name in overrides:
                ov = overrides[r_name]
                resolve_kickoff_match(
                    state, r_name,
                    winner_id=ov.get('winner_id'),
                    maps=ov.get('maps'),
                    rating_lookup=rating_lookup,
                    form_lookup=form_lookup
                )
            else:
                resolve_kickoff_match(
                    state, r_name,
                    winner_id=None,
                    rating_lookup=rating_lookup,
                    form_lookup=form_lookup
                )
        loop_idx += 1

    return state
