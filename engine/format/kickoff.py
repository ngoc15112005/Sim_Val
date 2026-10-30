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
    - 4 Bye teams (Seeds 1..4): Top 4 partners (by Champions qualification or story_rating)
    - 4 Upper R1 Partner teams (Seeds 5..8): remaining 4 partners
    - 4 Upper R1 Open Qualifier teams (Seeds 9..12): 4 qualifiers from Open Qualifier
    
    Each participant is expected to have:
    - 'id' or 'club_id'
    - 'name', 'short_code'
    - 'is_partner': bool
    - 'story_rating': int
    """
    partners = [p for p in participants if p.get('is_partner')]
    non_partners = [p for p in participants if not p.get('is_partner')]

    # Sort partners: by prior champions seed if present, else by rating desc
    partners.sort(key=lambda x: (
        -(1 if x.get('prev_champions_qualified') else 0),
        -(x.get('story_rating') or x.get('current_rating') or 80)
    ))

    # Top 4 partners get Byes
    byes = partners[:4]
    ub_partners = partners[4:]

    # Open qualifiers (sorted by their Open Qualifier seed 1..4)
    non_partners.sort(key=lambda x: x.get('oq_seed', 99))

    seeded_dict = {}
    for idx, team in enumerate(byes):
        seeded_dict[idx + 1] = team  # Seeds 1..4

    for idx, team in enumerate(ub_partners):
        seeded_dict[idx + 5] = team  # Seeds 5..8

    for idx, team in enumerate(non_partners):
        seeded_dict[idx + 9] = team  # Seeds 9..12 (Open Qualifiers 1..4)

    return {
        'seeds': seeded_dict,
        'byes': byes,
        'upper_partners': ub_partners,
        'open_qualifiers': non_partners,
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


def simulate_kickoff_tournament(region_slug: str, participants: List[Dict[str, Any]],
                                rating_lookup: Optional[Dict[int, int]] = None,
                                form_lookup: Optional[Dict[int, int]] = None,
                                manual_overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Execute complete 22-match VCT Kickoff double-elimination tournament.
    
    Args:
        region_slug: e.g. 'pacific', 'americas', 'emea', 'china'
        participants: list of 12 team dicts (8 Partner + 4 Open Qualifiers)
        rating_lookup: optional dict {club_id: rating}
        form_lookup: optional dict {club_id: form}
        manual_overrides: optional dict {round_name: {'winner_id': int, ...}}
    
    Returns:
        {
            'region_slug': str,
            'matches': list of 22 match dicts,
            'completed_dict': dict mapping round_name -> match dict,
            'standings': list of 12 team standings dicts (ranked 1..12 with CP awarded),
            'major_qualifiers': list of 2 team dicts (Champion and Runner-up),
            'total_matches_count': 22,
        }
    """
    if len(participants) != 12:
        raise ValueError(f"Kickoff requires exactly 12 teams, received {len(participants)}")

    seeding_info = seed_kickoff_participants(participants)
    seeds = seeding_info['seeds']

    templates = get_kickoff_bracket_templates()
    completed_matches: Dict[str, Dict[str, Any]] = {}
    matches_list: List[Dict[str, Any]] = []

    overrides = manual_overrides or {}

    for tpl in templates:
        r_name = tpl['round_name']
        t_a, t_b = resolve_kickoff_slot(tpl, seeds, completed_matches)
        if not t_a or not t_b:
            raise RuntimeError(f"Kickoff match {r_name} could not resolve teams")

        m_override = overrides.get(r_name)
        sim = simulate_kickoff_match(
            t_a, t_b, bo=tpl['bo'],
            rating_lookup=rating_lookup, form_lookup=form_lookup,
            manual_override=m_override
        )
        sim.update({
            'round_name': r_name,
            'round_type': tpl['round_type'],
            'match_code': tpl['match_code'],
            'label': tpl['label'],
        })

        completed_matches[r_name] = sim
        matches_list.append(sim)

    # Compute Standings and CP Points
    gf = completed_matches['grand_final']
    lb_final = completed_matches['lower_final']
    lb_semi = completed_matches['lower_semifinal']

    champion = gf['winner']
    runner_up = gf['loser']
    third_place = lb_final['loser']
    fourth_place = lb_semi['loser']

    # 5-6th place: Losers of Lower R3
    lb_r3_losers = [completed_matches['lower_r3_m1']['loser'], completed_matches['lower_r3_m2']['loser']]
    # 7-8th place: Losers of Lower R2
    lb_r2_losers = [completed_matches['lower_r2_m1']['loser'], completed_matches['lower_r2_m2']['loser']]
    # 9-12th place: Losers of Lower R1
    lb_r1_losers = [
        completed_matches['lower_r1_m1']['loser'],
        completed_matches['lower_r1_m2']['loser'],
        completed_matches['lower_r1_m3']['loser'],
        completed_matches['lower_r1_m4']['loser'],
    ]

    standings = [
        {
            'rank': 1,
            'team': champion,
            'club_id': champion['id'] if 'id' in champion else champion.get('club_id'),
            'title': 'Vô địch Kickoff',
            'major_qualified': True,
            'major_seed': 1,
            'championship_points': get_stage_points('kickoff', rank=1),  # 3 CP
        },
        {
            'rank': 2,
            'team': runner_up,
            'club_id': runner_up['id'] if 'id' in runner_up else runner_up.get('club_id'),
            'title': 'Á quân Kickoff',
            'major_qualified': True,
            'major_seed': 2,
            'championship_points': get_stage_points('kickoff', rank=2),  # 2 CP
        },
        {
            'rank': 3,
            'team': third_place,
            'club_id': third_place['id'] if 'id' in third_place else third_place.get('club_id'),
            'title': 'Hạng 3 (Thua Chung kết Nhánh thua)',
            'major_qualified': False,
            'major_seed': None,
            'championship_points': get_stage_points('kickoff', rank=3),  # 1 CP
        },
        {
            'rank': 4,
            'team': fourth_place,
            'club_id': fourth_place['id'] if 'id' in fourth_place else fourth_place.get('club_id'),
            'title': 'Hạng 4 (Thua Bán kết Nhánh thua)',
            'major_qualified': False,
            'major_seed': None,
            'championship_points': get_stage_points('kickoff', rank=4),  # 1 CP
        },
    ]

    for t in lb_r3_losers:
        standings.append({
            'rank': 5,
            'team': t,
            'club_id': t['id'] if 'id' in t else t.get('club_id'),
            'title': 'Top 5-6 (Thua Tứ kết Nhánh thua)',
            'major_qualified': False,
            'major_seed': None,
            'championship_points': 0,
        })

    for t in lb_r2_losers:
        standings.append({
            'rank': 7,
            'team': t,
            'club_id': t['id'] if 'id' in t else t.get('club_id'),
            'title': 'Top 7-8 (Thua Vòng 2 Nhánh thua)',
            'major_qualified': False,
            'major_seed': None,
            'championship_points': 0,
        })

    for t in lb_r1_losers:
        standings.append({
            'rank': 9,
            'team': t,
            'club_id': t['id'] if 'id' in t else t.get('club_id'),
            'title': 'Top 9-12 (Thua Vòng 1 Nhánh thua)',
            'major_qualified': False,
            'major_seed': None,
            'championship_points': 0,
        })

    major_qualifiers = [champion, runner_up]

    return {
        'region_slug': region_slug,
        'matches': matches_list,
        'completed_dict': completed_matches,
        'standings': standings,
        'major_qualifiers': major_qualifiers,
        'total_matches_count': len(matches_list),
        'seeds': seeds,
    }
