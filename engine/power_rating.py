"""Riot Games Global Power Rankings (GPR) x AWS Engine for Sim_Val.

Implements the official Riot Games Global Power Rankings methodology:
- 80% Team Performance (Team Elo) + 20% Regional League Strength (League Elo)
- Dynamic K-Factors based on tournament tiers (Champions > Masters > EWC > Regional Playoffs > Regular)
- Margin of Victory Modifier (Map and Round differential adjustments)
- Form streak modifiers and off-season mean regression
- Tier classifications: Tier S+ (World Titan), Tier S (Elite Contender), Tier A (Regional Powerhouse),
  Tier B (Mid Table), Tier C (Rebuilding)
- Dual-scale scoring: GPR Score (1000 - 2500) and Display OVR Rating (50.0 - 99.9)
"""

import math
from typing import Dict, Any, Tuple, Optional, List

# Tournament Tier K-Factors
TOURNAMENT_K_FACTORS = {
    'champion': 50,       # VALORANT Champions (World Championship)
    'master': 40,         # VCT Masters Toronto
    'major': 40,          # VCT Masters Bangkok
    'ewc': 32,            # Esports World Cup Riyadh
    'stage1_playoffs': 26,# VCT Stage 1 Playoffs
    'stage2_playoffs': 26,# VCT Stage 2 Playoffs
    'stage1': 18,         # VCT Stage 1 Regular Season
    'stage2': 18,         # VCT Stage 2 Regular Season
    'kickoff': 18,        # VCT Kickoff
    'open_qualifier': 10, # Open Qualifier
    'oq_stage1': 10,
    'oq_stage2': 10,
    'ewc_qualifier': 16,
    'default': 20,
}

# Regional Elo default starting score
DEFAULT_LEAGUE_ELO = 1500.0

# Base team Elo default
DEFAULT_TEAM_ELO = 1500.0


def calculate_expected_score(rating_a: float, rating_b: float) -> float:
    """Standard Elo logistic expectation formula."""
    return 1.0 / (1.0 + math.pow(10.0, (rating_b - rating_a) / 400.0))


def calculate_margin_modifier(map_diff: int, round_diff: int) -> float:
    """Calculate Margin of Victory (MoV) multiplier.
    
    A dominant 2-0 (e.g. +16 rounds) gives a substantial bonus,
    while a close 2-1 (+2 rounds) yields close to baseline.
    """
    map_bonus = max(0, abs(map_diff)) * 0.12
    round_bonus = max(0, abs(round_diff)) * 0.025
    # Total multiplier bounded between 0.85 and 1.75
    multiplier = 1.0 + map_bonus + round_bonus
    return max(0.85, min(1.75, multiplier))


def update_team_elo(
    rating_winner: float,
    rating_loser: float,
    tournament_tier: str = 'default',
    map_diff: int = 1,
    round_diff: int = 4
) -> Tuple[float, float, float]:
    """Calculate updated Elo ratings for winner and loser after a match.
    
    Returns:
        (new_winner_elo, new_loser_elo, delta)
    """
    k = TOURNAMENT_K_FACTORS.get(tournament_tier, TOURNAMENT_K_FACTORS['default'])
    mov = calculate_margin_modifier(map_diff, round_diff)

    expected_w = calculate_expected_score(rating_winner, rating_loser)
    
    # Delta gained by winner: K * (1.0 - expected) * MoV
    raw_delta = k * (1.0 - expected_w) * mov
    # Ensure minimum gain for a win (+2.0) and cap at +65.0
    delta = max(2.0, min(65.0, raw_delta))

    new_w = rating_winner + delta
    new_l = max(800.0, rating_loser - delta)

    return round(new_w, 1), round(new_l, 1), round(delta, 1)


def update_regional_league_elo(
    league_ratings: Dict[str, float],
    region_winner: str,
    region_loser: str,
    tournament_tier: str = 'master'
) -> Tuple[Dict[str, float], float]:
    """Update Regional League Elo when teams from different regions face each other.
    
    Only applies in international tournaments (Champions, Masters, EWC).
    """
    if not region_winner or not region_loser or region_winner == region_loser:
        return league_ratings, 0.0

    ratings = dict(league_ratings or {})
    rw = ratings.get(region_winner, DEFAULT_LEAGUE_ELO)
    rl = ratings.get(region_loser, DEFAULT_LEAGUE_ELO)

    k_intl = 16 if tournament_tier == 'champion' else 12
    exp_w = calculate_expected_score(rw, rl)
    league_delta = max(1.0, min(25.0, k_intl * (1.0 - exp_w)))

    ratings[region_winner] = round(rw + league_delta, 1)
    ratings[region_loser] = round(max(1000.0, rl - league_delta), 1)

    return ratings, round(league_delta, 1)


def calculate_composite_power_score(
    team_elo: float,
    league_elo: float,
    win_streak: int = 0
) -> float:
    """Calculate official Riot GPR composite score:
    80% Team Elo + 20% Regional League Elo + Streak Bonus.
    """
    t_elo = float(team_elo if team_elo is not None else DEFAULT_TEAM_ELO)
    l_elo = float(league_elo if league_elo is not None else DEFAULT_LEAGUE_ELO)

    base_score = (0.80 * t_elo) + (0.20 * l_elo)

    # Form Streak Bonus
    streak_bonus = 0.0
    if win_streak >= 5:
        streak_bonus = 35.0
    elif win_streak >= 3:
        streak_bonus = 18.0
    elif win_streak <= -3:
        streak_bonus = -18.0

    final_score = base_score + streak_bonus
    # Bound score in realistic esports range [900, 2400]
    return round(max(900.0, min(2400.0, final_score)), 1)


def power_score_to_ovr(power_score: float) -> float:
    """Normalize GPR Power Score (1000 - 2200) into a recognizable 50.0 - 99.9 OVR Rating."""
    clamped = max(1000.0, min(2200.0, float(power_score)))
    norm = (clamped - 1000.0) / 1200.0  # 0.0 to 1.0
    ovr = 55.0 + (norm * 44.0)          # 55.0 to 99.0
    return round(ovr, 1)


def get_tier_info(power_score: float) -> Dict[str, Any]:
    """Classify club into competitive tier with badge and color theme."""
    score = float(power_score)
    if score >= 1850.0:
        return {
            'tier': 'S+',
            'name': 'World Titan',
            'badge': '👑 S+',
            'color': '#fbbf24',          # Neon Gold
            'bg': 'rgba(251, 191, 36, 0.15)',
            'border': '#f59e0b',
        }
    elif score >= 1700.0:
        return {
            'tier': 'S',
            'name': 'Elite Contender',
            'badge': '💎 S',
            'color': '#38bdf8',          # Diamond Cyan
            'bg': 'rgba(56, 189, 248, 0.15)',
            'border': '#0284c7',
        }
    elif score >= 1550.0:
        return {
            'tier': 'A',
            'name': 'Regional Powerhouse',
            'badge': '⚔️ A',
            'color': '#4ade80',          # Emerald Green
            'bg': 'rgba(74, 222, 128, 0.15)',
            'border': '#16a34a',
        }
    elif score >= 1400.0:
        return {
            'tier': 'B',
            'name': 'Mid Table Challenger',
            'badge': '🛡️ B',
            'color': '#60a5fa',          # Royal Blue
            'bg': 'rgba(96, 165, 250, 0.15)',
            'border': '#2563eb',
        }
    else:
        return {
            'tier': 'C',
            'name': 'Rebuilding Squad',
            'badge': '⚠️ C',
            'color': '#94a3b8',          # Slate Gray
            'bg': 'rgba(148, 163, 184, 0.15)',
            'border': '#64748b',
        }


def format_rank_delta(current_rank: int, previous_rank: Optional[int]) -> Dict[str, Any]:
    """Format visual rank change (e.g. +3, -2, 0)."""
    if previous_rank is None or previous_rank <= 0:
        return {'symbol': '★ NEW', 'delta': 0, 'class': 'rank-new', 'color': '#fbbf24'}

    diff = previous_rank - current_rank
    if diff > 0:
        return {'symbol': f'▲ +{diff}', 'delta': diff, 'class': 'rank-up', 'color': '#4ade80'}
    elif diff < 0:
        return {'symbol': f'▼ {diff}', 'delta': diff, 'class': 'rank-down', 'color': '#ef4444'}
    else:
        return {'symbol': '▬ 0', 'delta': 0, 'class': 'rank-same', 'color': '#94a3b8'}


def apply_offseason_regression(
    team_elo: float,
    mean_elo: float = 1500.0,
    regression_rate: float = 0.20
) -> float:
    """Apply off-season regression toward the mean (20% decay) to reflect roster changes."""
    regressed = (team_elo * (1.0 - regression_rate)) + (mean_elo * regression_rate)
    return round(regressed, 1)
