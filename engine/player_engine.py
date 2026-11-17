"""
engine/player_engine.py — Engine Thuần Toán học & Quy tắc Tuyển thủ VCT (Player System v2.0).

Bao gồm:
- Tính toán mức lương lũy tiến (+0..+5), Quỹ lương CLB (Salary Cap).
- Kiểm tra đội hình chuẩn 5 người phủ đủ 4 Role cốt lõi (Duelist, Initiator, Controller, Sentinel) + Flex.
- Chính sách Bản sắc Ngoại binh theo từng Quốc gia / Tiểu khu vực (tối đa 2 ngoại binh, KR/VN/BR/CN ưu tiên nội địa).
- Vòng đời Tuyển thủ: Tăng tuổi, Tiến hóa Role/Flex, Phát triển chỉ số [0..+5], Giải nghệ, và Comeback (35+ = 0.00000000001%).
- Bộ sinh Tân binh (Regen) & AI chuyển nhượng tự động điền đội hình hợp lệ.
"""

from __future__ import annotations
import math
import random
from typing import Dict, List, Any, Optional, Tuple

from engine.partnership import SUBREGION_METADATA, get_club_country_info
from engine.players_data import (
    CORE_ROLES,
    ALL_ROLES,
    SALARY_BY_BONUS,
    FLEX_SALARY_MULTIPLIER,
    BENCH_SALARY_MULTIPLIER,
    SALARY_CAP_CONFIG,
    MAX_FOREIGN_STARTERS,
    MAX_STARTERS,
    MAX_BENCH,
    IMPORT_OPENNESS_BY_COUNTRY,
    CLUB_IMPORT_OPENNESS_OVERRIDES,
    COUNTRY_IGN_POOLS,
    IGN_SUFFIXES,
)


def clamp_bonus(val: Any) -> int:
    """Ép chỉ số cộng của tuyển thủ nằm gọn trong [0, 5] (không bao giờ âm)."""
    try:
        iv = int(val)
    except (ValueError, TypeError):
        iv = 0
    return max(0, min(5, iv))


def calculate_player_salary(bonus_rating: int, is_flex: bool = False, roster_slot: str = "starter") -> int:
    """Tính lương hàng năm ($K) dựa theo chỉ số cộng (+0..+5), trạng thái Flex và vai trò dự bị."""
    b = clamp_bonus(bonus_rating)
    base_sal = SALARY_BY_BONUS.get(b, 60)
    if is_flex:
        base_sal = round(base_sal * FLEX_SALARY_MULTIPLIER)
    if roster_slot == "bench":
        base_sal = round(base_sal * BENCH_SALARY_MULTIPLIER)
    return int(base_sal)


def get_club_salary_cap(short_code: str, is_partner: bool, region_slug: str = "pacific") -> int:
    """Lấy mức trần quỹ lương ($K) hàng năm cho CLB dựa theo Partner & Org Tier."""
    c_info = get_club_country_info(short_code, region_slug)
    tier = int(c_info.get("org_tier", 2))
    tier = max(1, min(3, tier))
    bucket = "partner" if is_partner else "non_partner"
    return int(SALARY_CAP_CONFIG[bucket].get(tier, 1200 if is_partner else 750))


def get_club_import_openness(short_code: str, country_code: str) -> float:
    """Lấy xác suất cởi mở với ngoại binh (0.04 = cực kỳ chuộng nội địa như T1/GEN/GAM, 0.45 = quốc tế)."""
    if short_code in CLUB_IMPORT_OPENNESS_OVERRIDES:
        return float(CLUB_IMPORT_OPENNESS_OVERRIDES[short_code])
    return float(IMPORT_OPENNESS_BY_COUNTRY.get(country_code, 0.20))


def is_cross_region_import(player_nationality: str, club_region_slug: str = "pacific") -> bool:
    """Kiểm tra tuyển thủ có phải là Ngoại binh Liên khu vực theo luật VCT hay không (VD: KR sang EMEA/NA, BR sang EMEA)."""
    if not player_nationality:
        return False
    p_region = SUBREGION_METADATA.get(player_nationality, {}).get("region")
    if not p_region:
        return False
    return p_region != club_region_slug


def is_foreign_player(player_nationality: str, club_country_code: str, club_region_slug: str = "pacific") -> bool:
    """Kiểm tra một tuyển thủ có khác Quốc gia/Tiểu khu vực bản địa của CLB hay không
    (dùng cho bản sắc tuyển mộ nội địa KR/VN/BR/CN). Đặc thù: mọi Hub CN_* đều là nội địa Trung Quốc.
    """
    if not player_nationality or not club_country_code:
        return False
    if club_region_slug == "china" or club_country_code.startswith("CN_"):
        return not str(player_nationality).startswith("CN_")
    return str(player_nationality) != str(club_country_code)


def calculate_roster_bonus(starters: List[Dict[str, Any]]) -> int:
    """Tổng chỉ số cộng thêm của đội tuyển từ 5 tuyển thủ ra sân chính (không bao giờ âm)."""
    if not starters:
        return 0
    return sum(clamp_bonus(p.get("bonus_rating", 0)) for p in starters[:MAX_STARTERS])


def calculate_roster_payroll(starters: List[Dict[str, Any]], bench: List[Dict[str, Any]] | None = None) -> int:
    """Tính tổng quỹ lương hiện tại của CLB (5 starters + bench nếu có)."""
    total = sum(int(p.get("salary") or calculate_player_salary(p.get("bonus_rating", 0), bool(p.get("is_flex")), "starter")) for p in (starters or []))
    for p in (bench or []):
        # Khi ký bench, tính 50% lương niêm yết hoặc giá đã lưu với slot bench
        sal = int(p.get("salary") or calculate_player_salary(p.get("bonus_rating", 0), bool(p.get("is_flex")), "bench"))
        if p.get("roster_slot") != "bench":
            sal = round(sal * BENCH_SALARY_MULTIPLIER)
        total += sal
    return int(total)


def _player_eligible_roles(p: Dict[str, Any]) -> Tuple[str, ...]:
    """Liệt kê các Core Roles mà tuyển thủ có thể đảm nhận (Flex đánh được cả 4 role)."""
    prole = p.get("primary_role", "")
    is_flex = bool(p.get("is_flex") or prole == "Flex")
    if is_flex:
        return CORE_ROLES
    roles = []
    if prole in CORE_ROLES:
        roles.append(prole)
    sec = p.get("secondary_role")
    if sec in CORE_ROLES and sec not in roles:
        roles.append(sec)
    return tuple(roles)


def check_4_roles_covered(starters: List[Dict[str, Any]]) -> Tuple[bool, Dict[str, Optional[str]], List[str]]:
    """Kiểm tra đội hình 5 người có phủ đủ cả 4 Core Roles (Duelist, Initiator, Controller, Sentinel) hay không.
    Sử dụng thuật toán ghép cặp tối ưu: ưu tiên khớp Role chính trước, sau đó Role phụ / Flex lấp chỗ trống.
    """
    player_list = list(starters)
    # Ưu tiên xếp chuyên gia 1 role lên trước để giữ Flex lấp các ô trống khó hơn
    player_list.sort(key=lambda p: (
        1 if (p.get("is_flex") or p.get("primary_role") == "Flex") else 0,
        len(_player_eligible_roles(p)),
    ))

    assigned_roles: Dict[str, Optional[str]] = {r: None for r in CORE_ROLES}
    used_indices: set[int] = set()

    # Bước 1: Ghép các tuyển thủ chuyên đúng primary_role chưa bị chiếm
    for idx, p in enumerate(player_list):
        prole = p.get("primary_role", "")
        if prole in CORE_ROLES and assigned_roles[prole] is None and not (p.get("is_flex") or prole == "Flex"):
            assigned_roles[prole] = p.get("ign", "Player")
            used_indices.add(idx)

    # Bước 2: Dùng backtracking tìm cách phủ hết các role còn lại bằng những người còn lại (Flex / secondary / primary)
    remaining_roles = [r for r in CORE_ROLES if assigned_roles[r] is None]
    remaining_players = [(idx, p) for idx, p in enumerate(player_list) if idx not in used_indices]

    best_assignment: Dict[str, str] = {}

    def _backtrack(r_idx: int, cur_assign: Dict[str, str], used_p: set[int]) -> bool:
        nonlocal best_assignment
        if len(cur_assign) > len(best_assignment):
            best_assignment = dict(cur_assign)
        if r_idx >= len(remaining_roles):
            return True
        role_need = remaining_roles[r_idx]
        for p_idx, p_obj in remaining_players:
            if p_idx in used_p:
                continue
            if role_need in _player_eligible_roles(p_obj):
                used_p.add(p_idx)
                is_flx = bool(p_obj.get("is_flex") or p_obj.get("primary_role") == "Flex")
                label = f"{p_obj.get('ign', 'Player')} (Flex)" if (is_flx and p_obj.get("primary_role") != role_need) else p_obj.get("ign", "Player")
                cur_assign[role_need] = label
                if _backtrack(r_idx + 1, cur_assign, used_p):
                    return True
                del cur_assign[role_need]
                used_p.remove(p_idx)
        return False

    _backtrack(0, {}, set())
    for r, lbl in best_assignment.items():
        assigned_roles[r] = lbl

    missing = [r for r in CORE_ROLES if assigned_roles[r] is None]
    return (len(missing) == 0), assigned_roles, missing


def validate_roster_lineup(
    starters: List[Dict[str, Any]],
    bench: List[Dict[str, Any]],
    club_country_code: str,
    club_region_slug: str,
    salary_cap: int,
    strict_starter_count: bool = True,
) -> Tuple[bool, List[str], Dict[str, Any]]:
    """Kiểm tra toàn diện đội hình CLB:
    1. Đủ 5 tuyển thủ ra sân chính (hoặc <= 5).
    2. Phủ kín đủ 4 Core Roles (Duelist, Initiator, Controller, Sentinel - Flex có thể lấp).
    3. Không vượt quá 2 ngoại binh trong đội hình ra sân chính.
    4. Tổng quỹ lương <= Trần quỹ lương CLB (salary_cap).
    """
    errors: List[str] = []

    if strict_starter_count and len(starters) != MAX_STARTERS:
        errors.append(f"Đội hình ra sân chính phải có đúng {MAX_STARTERS} tuyển thủ (hiện có {len(starters)}).")
    elif len(starters) > MAX_STARTERS:
        errors.append(f"Tối đa {MAX_STARTERS} tuyển thủ trong đội hình chính.")

    if len(bench) > MAX_BENCH:
        errors.append(f"Tối đa {MAX_BENCH} tuyển thủ dự bị (hiện có {len(bench)}).")

    roles_ok, role_map, missing_roles = check_4_roles_covered(starters)
    if not roles_ok:
        errors.append(f"Đội hình thiếu vai trò bắt buộc: {', '.join(missing_roles)} (cần phủ đủ 4 Role!).")

    # Đếm cả ngoại binh liên khu vực (giới hạn cứng VCT <= 2) và ngoại binh khác quốc gia (thông tin bản sắc)
    cross_region_imports = [
        p for p in starters
        if is_cross_region_import(p.get("nationality", ""), club_region_slug)
    ]
    country_foreign_players = [
        p for p in starters
        if is_foreign_player(p.get("nationality", ""), club_country_code, club_region_slug)
    ]
    if len(cross_region_imports) > MAX_FOREIGN_STARTERS:
        names = ", ".join(p.get("ign", "?") for p in cross_region_imports)
        errors.append(
            f"Vượt giới hạn ngoại binh liên khu vực VCT: đang có {len(cross_region_imports)}/{MAX_FOREIGN_STARTERS} người ({names})."
        )

    payroll = calculate_roster_payroll(starters, bench)
    if payroll > salary_cap:
        errors.append(
            f"Vượt trần quỹ lương CLB: tổng lương ${payroll}K / trần ${salary_cap}K."
        )

    metrics = {
        "starter_count": len(starters),
        "bench_count": len(bench),
        "player_bonus": calculate_roster_bonus(starters),
        "roles_ok": roles_ok,
        "role_coverage": role_map,
        "missing_roles": missing_roles,
        "import_count": len(cross_region_imports),
        "foreign_count": len(country_foreign_players),
        "max_foreign": MAX_FOREIGN_STARTERS,
        "payroll": payroll,
        "salary_cap": salary_cap,
        "cap_space": salary_cap - payroll,
    }
    return (len(errors) == 0), errors, metrics


# ─────────────────────────────────────────────────────────────────────────────
# RETIREMENT, COMEBACK & EVOLUTION CURVES
# ─────────────────────────────────────────────────────────────────────────────

def get_retirement_probability(age: int, seasons_played: int = 0, status: str = "active") -> float:
    """Tính xác suất giải nghệ cuối mùa theo độ tuổi & trạng thái thi đấu."""
    if status == "retired":
        return 0.0

    # Thất nghiệp ở tuổi lớn dễ giải nghệ sớm hơn
    fa_mult = 1.6 if status == "free_agent" else 1.0

    if age <= 21:
        base = 0.002 if status == "free_agent" else 0.0
    elif age <= 24:
        base = 0.015
    elif age <= 26:
        base = 0.035
    elif age <= 28:
        base = 0.08
    elif age == 29:
        base = 0.14
    elif age <= 31:
        base = 0.25
    elif age <= 33:
        base = 0.42
    elif age <= 35:
        base = 0.68
    elif age == 36:
        base = 0.85
    else:
        return 0.98

    # Tuyển thủ dày dạn thi đấu >= 6 mùa có chút mệt mỏi nghề nghiệp
    if age >= 27 and seasons_played >= 6:
        base += 0.04

    return min(0.98, round(base * fa_mult, 4))


def get_comeback_probability(age: int, years_retired: int = 1) -> float:
    """Xác suất giải nghệ lâu ngày bất ngờ Comeback:
    - Càng lớn tuổi xác suất càng tụt thảm hại:
      * < 26 tuổi: 4.5% - 5.5% (dễ tái xuất sau burnout)
      * 26 - 29 tuổi: 1.0% - 2.0%
      * 30 - 34 tuổi: 0.05% (0.0005 — rất rất thấp)
      * 35+ tuổi: 0.00000000001% (1e-13 — phép màu cực hạn!)
    """
    if years_retired < 1:
        return 0.0

    if age >= 35:
        # 0.00000000001% = 0.0000000000001 = 1e-13
        return 1e-13
    elif age >= 30:
        # 30-34 tuổi: rất rất thấp (~0.02% - 0.05%)
        decay = max(0.25, 1.0 - (age - 30) * 0.15)
        return round(0.0005 * decay, 6)
    elif age >= 26:
        # 26-29 tuổi: thấp (~1% - 2%)
        return round(max(0.008, 0.022 - (age - 26) * 0.004), 4)
    else:
        # Dưới 26 tuổi (nghỉ sớm / burnout): cơ hội quay lại cao hơn (~4-6%)
        return 0.055 if years_retired <= 3 else 0.03


def generate_authentic_ign(
    country_code: str,
    existing_igns: set[str],
    rng: random.Random | None = None,
) -> str:
    """Sinh IGN mang bản sắc quốc gia, không trùng lặp với danh sách đã có."""
    r = rng or random
    pool = COUNTRY_IGN_POOLS.get(country_code) or COUNTRY_IGN_POOLS.get("SG_MY", ["Player"])

    for _ in range(40):
        base = r.choice(pool)
        suf = r.choice(IGN_SUFFIXES)
        candidate = f"{base}{suf}"
        if candidate.lower() not in existing_igns:
            existing_igns.add(candidate.lower())
            return candidate

    # Fallback bảo đảm 100% duy nhất
    idx = 10
    while True:
        candidate = f"{r.choice(pool)}{idx}"
        if candidate.lower() not in existing_igns:
            existing_igns.add(candidate.lower())
            return candidate
        idx += 1


def roll_rookie_bonus_rating(rng: random.Random | None = None) -> int:
    """Phân phối chỉ số tân binh (+0 chiếm chủ đạo để không lạm phát giải đấu)."""
    r = (rng or random).random()
    if r < 0.65:
        return 0
    elif r < 0.90:
        return 1
    elif r < 0.98:
        return 2
    else:
        return 3


def generate_rookie_player_dict(
    country_code: str,
    region_slug: str,
    debut_year: int,
    role: str,
    existing_igns: set[str],
    bonus_rating: int | None = None,
    age: int | None = None,
    rng: random.Random | None = None,
) -> Dict[str, Any]:
    """Tạo 1 hồ sơ tân binh (17-19 tuổi) chuẩn bị debut."""
    r = rng or random
    ign = generate_authentic_ign(country_code, existing_igns, rng=r)
    p_age = age if age is not None else r.randint(17, 19)
    p_bonus = clamp_bonus(bonus_rating) if bonus_rating is not None else roll_rookie_bonus_rating(rng=r)

    # 8% tân binh có tố chất đa năng (Flex) ngay từ nhỏ
    is_flex = (role == "Flex") or (r.random() < 0.08)
    sec_choices = [cr for cr in CORE_ROLES if cr != role]
    secondary_role = r.choice(sec_choices) if (is_flex or r.random() < 0.25) and sec_choices else None
    salary = calculate_player_salary(p_bonus, is_flex=is_flex, roster_slot="free_agent")

    meta = SUBREGION_METADATA.get(country_code, {})
    return {
        "ign": ign,
        "real_name": ign,
        "age": p_age,
        "nationality": country_code,
        "nationality_name": meta.get("short_name", country_code),
        "nationality_flag": meta.get("flag", "🏳️"),
        "region_slug": region_slug,
        "primary_role": role,
        "secondary_role": secondary_role,
        "is_flex": is_flex,
        "bonus_rating": p_bonus,
        "salary": salary,
        "roster_slot": "free_agent",
        "status": "free_agent",
        "debut_year": debut_year,
        "is_real_life": False,
        "is_custom": False,
        "career_note": f"Tân binh xuất sắc từ học viện {meta.get('short_name', country_code)} (Lớp {debut_year})",
    }


def evaluate_offseason_player_events(
    players: List[Dict[str, Any]],
    next_year: int,
    club_success_scores: Dict[int, float] | None = None,
    target_pool_size: int = 560,
    rng: random.Random | None = None,
) -> Dict[str, Any]:
    """Tính toán Dự thảo Biến động Nhân sự Tiền Mùa Giải (Chưa lưu DB, trả về để hỏi ý kiến người chơi):
    - Tăng 1 tuổi cho toàn bộ tuyển thủ.
    - Đề xuất Giải nghệ (Retirements).
    - Đề xuất Comeback (Tái xuất cho người đã giải nghệ >= 1 năm, 35+ = 1e-13).
    - Đề xuất Tiến hóa Role / Lên Flex.
    - Biến động chỉ số nhẹ [0..+5].
    - Sinh Tân binh Debut bù lứa giải nghệ & giữ quy mô pool ổn định.
    """
    r = rng or random
    success_map = club_success_scores or {}
    existing_igns = {str(p.get("ign", "")).lower() for p in players}

    retirements: List[Dict[str, Any]] = []
    comebacks: List[Dict[str, Any]] = []
    role_evolutions: List[Dict[str, Any]] = []
    rating_changes: List[Dict[str, Any]] = []

    retired_by_region: Dict[str, List[str]] = {
        "pacific": [], "americas": [], "emea": [], "china": []
    }
    active_count = 0

    for p in players:
        pid = p.get("id")
        status = p.get("status", "active")
        age_next = int(p.get("age", 20)) + 1
        bonus = clamp_bonus(p.get("bonus_rating", 0))
        reg = p.get("region_slug", "pacific")
        cc = p.get("nationality", "SG_MY")

        if status == "retired":
            years_ret = int(p.get("years_retired", 0)) + 1
            prob = get_comeback_probability(age_next, years_retired=years_ret)
            if r.random() < prob:
                comebacks.append({
                    "player_id": pid,
                    "ign": p.get("ign"),
                    "age": age_next,
                    "nationality": cc,
                    "nationality_flag": p.get("nationality_flag", "🏳️"),
                    "nationality_name": p.get("nationality_name", cc),
                    "region_slug": reg,
                    "primary_role": p.get("primary_role"),
                    "is_flex": bool(p.get("is_flex")),
                    "bonus_rating": max(0, bonus - 1) if age_next >= 28 else bonus,
                    "years_retired": years_ret,
                    "probability_pct": f"{prob * 100:.11f}%".rstrip("0").rstrip(".") + "%",
                    "reason": f"Trở lại sau {years_ret} năm vắng bóng ở tuổi {age_next}!",
                    "approved": True,
                })
            continue

        active_count += 1

        # 1. Kiểm tra Giải nghệ
        ret_prob = get_retirement_probability(age_next, int(p.get("seasons_played", 0)), status)
        if r.random() < ret_prob:
            club_info = p.get("club") or {}
            retirements.append({
                "player_id": pid,
                "ign": p.get("ign"),
                "age": age_next,
                "nationality": cc,
                "nationality_flag": p.get("nationality_flag", "🏳️"),
                "nationality_name": p.get("nationality_name", cc),
                "region_slug": reg,
                "club_id": p.get("club_id"),
                "club_code": club_info.get("short_code", "FA"),
                "club_name": club_info.get("name", "Tự do"),
                "primary_role": p.get("primary_role"),
                "bonus_rating": bonus,
                "probability_pct": f"{round(ret_prob * 100, 1)}%",
                "reason": "Nghỉ thi đấu chuyên nghiệp / Giã từ sự nghiệp" if age_next >= 28 else "Tạm ngưng thi đấu chuyên nghiệp",
                "approved": True,
            })
            retired_by_region.setdefault(reg, []).append(cc)
            continue

        # 2. Biến động chỉ số nhẹ [0..+5] (rất tiết chế để cân bằng lâu dài)
        club_id = p.get("club_id")
        team_success = float(success_map.get(club_id, 0.5)) if club_id else 0.25
        delta = 0
        if age_next <= 22 and bonus < 5:
            # Cầu thủ trẻ phát triển nếu thi đấu tốt
            up_prob = 0.08 + team_success * 0.12
            if bonus >= 3:
                up_prob *= 0.45
            if r.random() < up_prob:
                delta = 1
        elif 23 <= age_next <= 26 and bonus < 5:
            if team_success >= 0.75 and r.random() < 0.06:
                delta = 1
        elif age_next >= 29 and bonus > 0:
            down_prob = 0.14 + (age_next - 29) * 0.06
            if r.random() < down_prob:
                delta = -1

        new_bonus = clamp_bonus(bonus + delta)
        if new_bonus != bonus:
            club_info = p.get("club") or {}
            rating_changes.append({
                "player_id": pid,
                "ign": p.get("ign"),
                "age": age_next,
                "club_code": club_info.get("short_code", "FA"),
                "old_bonus": bonus,
                "new_bonus": new_bonus,
                "delta": new_bonus - bonus,
                "approved": True,
            })

        # 3. Tiến hóa Role / Trở thành Flex (tỷ lệ nhỏ 3-5%)
        cur_role = p.get("primary_role", "Duelist")
        cur_flex = bool(p.get("is_flex") or cur_role == "Flex")
        seasons_p = int(p.get("seasons_played", 0))

        # Xác suất lên Flex hoặc chuyển sang Role khác
        if not cur_flex and 21 <= age_next <= 29 and seasons_p >= 1 and r.random() < 0.032:
            club_info = p.get("club") or {}
            role_evolutions.append({
                "player_id": pid,
                "ign": p.get("ign"),
                "age": age_next,
                "club_code": club_info.get("short_code", "FA"),
                "evolution_type": "unlock_flex",
                "old_role": cur_role,
                "new_role": "Flex",
                "new_secondary_role": cur_role if cur_role in CORE_ROLES else p.get("secondary_role"),
                "new_is_flex": True,
                "description": f"Tiến hóa đa năng: {cur_role} ➔ ✨ Flex (chơi được mọi Role)",
                "approved": True,
            })
        elif cur_role in CORE_ROLES and 23 <= age_next <= 31 and r.random() < 0.035:
            # Chuyển hướng vai trò (VD: Duelist lớn tuổi -> Initiator / Sentinel / Controller)
            preferred_targets = {
                "Duelist": ["Initiator", "Flex", "Sentinel"],
                "Initiator": ["Controller", "Sentinel"],
                "Controller": ["Initiator", "Sentinel"],
                "Sentinel": ["Controller", "Initiator"],
            }.get(cur_role, [cr for cr in CORE_ROLES if cr != cur_role])
            target_role = p.get("secondary_role") if p.get("secondary_role") in CORE_ROLES else r.choice(preferred_targets)
            if target_role != cur_role:
                club_info = p.get("club") or {}
                role_evolutions.append({
                    "player_id": pid,
                    "ign": p.get("ign"),
                    "age": age_next,
                    "club_code": club_info.get("short_code", "FA"),
                    "evolution_type": "role_shift",
                    "old_role": cur_role,
                    "new_role": target_role,
                    "new_secondary_role": cur_role,
                    "new_is_flex": (target_role == "Flex") or cur_flex,
                    "description": f"Chuyển đổi vai trò: {cur_role} ➔ {target_role}",
                    "approved": True,
                })

    # 4. Sinh Tân binh Debut bù cho số người giải nghệ (+ bổ sung nhẹ nếu pool dưới mức tối thiểu)
    projected_active = active_count - len(retirements) + len(comebacks)
    min_rookies_needed = max(len(retirements) + 4, target_pool_size - projected_active)
    min_rookies_needed = min(40, max(8, min_rookies_needed))

    rookies: List[Dict[str, Any]] = []
    # Tạo tân binh ưu tiên tại các quốc gia vừa có người giải nghệ
    country_queue: List[Tuple[str, str]] = []
    for reg_slug, c_list in retired_by_region.items():
        for cc in c_list:
            country_queue.append((reg_slug, cc))

    # Bổ sung phân bổ đều 4 khu vực
    subregions_by_reg = {
        "pacific": [k for k, v in SUBREGION_METADATA.items() if v["region"] == "pacific"],
        "americas": [k for k, v in SUBREGION_METADATA.items() if v["region"] == "americas"],
        "emea": [k for k, v in SUBREGION_METADATA.items() if v["region"] == "emea"],
        "china": [k for k, v in SUBREGION_METADATA.items() if v["region"] == "china"],
    }
    reg_cycle = ["pacific", "americas", "emea", "china"]
    idx = 0
    while len(country_queue) < min_rookies_needed:
        rg = reg_cycle[idx % 4]
        cc = r.choice(subregions_by_reg[rg])
        country_queue.append((rg, cc))
        idx += 1

    for i in range(min_rookies_needed):
        rg, cc = country_queue[i]
        role = CORE_ROLES[i % 4]
        rookie = generate_rookie_player_dict(
            country_code=cc,
            region_slug=rg,
            debut_year=next_year,
            role=role,
            existing_igns=existing_igns,
            rng=r,
        )
        rookie["approved"] = True
        rookie["temp_key"] = f"rookie_{next_year}_{i + 1}"
        rookies.append(rookie)

    return {
        "target_year": next_year,
        "summary": {
            "retirements_count": len(retirements),
            "comebacks_count": len(comebacks),
            "role_evolutions_count": len(role_evolutions),
            "rating_changes_count": len(rating_changes),
            "rookies_count": len(rookies),
        },
        "retirements": retirements,
        "comebacks": comebacks,
        "role_evolutions": role_evolutions,
        "rating_changes": rating_changes,
        "rookies": rookies,
    }


def pick_ai_replacement_player(
    free_agents: List[Dict[str, Any]],
    needed_roles: List[str],
    club_short_code: str,
    club_country_code: str,
    club_region_slug: str,
    current_foreign_count: int,
    remaining_budget: int,
    rng: random.Random | None = None,
) -> Optional[Dict[str, Any]]:
    """AI chọn 1 tuyển thủ Tự do phù hợp nhất dựa theo:
    1. Quỹ lương còn lại (remaining_budget).
    2. Vai trò cần thiết để đủ 4 Role cốt lõi.
    3. Giới hạn tối đa 2 Ngoại binh & Bản sắc chuộng nội binh (KR/VN/BR/CN cực kỳ ưu tiên nội địa).
    """
    r = rng or random
    openness = get_club_import_openness(club_short_code, club_country_code)

    affordable = [
        fa for fa in free_agents
        if int(fa.get("salary") or calculate_player_salary(fa.get("bonus_rating", 0), bool(fa.get("is_flex")))) <= remaining_budget
    ]
    if not affordable:
        return None

    # Lọc ngoại binh liên khu vực nếu đội đã đủ 2 người theo luật VCT
    eligible = []
    for fa in affordable:
        fa_nat = fa.get("nationality", "")
        is_cross_imp = is_cross_region_import(fa_nat, club_region_slug)
        is_country_imp = is_foreign_player(fa_nat, club_country_code, club_region_slug)
        if is_cross_imp and current_foreign_count >= MAX_FOREIGN_STARTERS:
            continue
        eligible.append((fa, is_country_imp))

    if not eligible:
        return None

    # Xác định ưu tiên nội địa vs mở cửa ngoại binh (dựa vào bản sắc CLB/Quốc gia)
    allow_import_pick = (r.random() < openness) and (current_foreign_count < MAX_FOREIGN_STARTERS)
    domestic_only = [(fa, imp) for (fa, imp) in eligible if not imp]

    # Nếu chưa kích hoạt ngoại lệ ngoại binh và vẫn có ứng viên nội địa cùng khu vực: ưu tiên ứng viên nội địa!
    same_region_candidates = [(fa, imp) for (fa, imp) in eligible if fa.get("region_slug") == club_region_slug]

    pool_to_score = eligible
    if not allow_import_pick:
        if domestic_only:
            pool_to_score = domestic_only
        elif same_region_candidates:
            pool_to_score = same_region_candidates

    # Nếu còn thiếu role cụ thể, ưu tiên ứng viên phủ role thiếu (hoặc Flex)
    if needed_roles:
        role_matched = [
            (fa, imp) for (fa, imp) in pool_to_score
            if fa.get("primary_role") in needed_roles
            or bool(fa.get("is_flex"))
            or fa.get("secondary_role") in needed_roles
        ]
        if role_matched:
            pool_to_score = role_matched
        else:
            # Thử mở rộng tìm trên toàn eligible cho role bắt buộc
            broad_matched = [
                (fa, imp) for (fa, imp) in eligible
                if (fa.get("primary_role") in needed_roles or bool(fa.get("is_flex")))
                and (not imp or allow_import_pick or not domestic_only)
            ]
            if broad_matched:
                pool_to_score = broad_matched

    def _score_candidate(item: Tuple[Dict[str, Any], bool]) -> float:
        fa, is_imp = item
        b = clamp_bonus(fa.get("bonus_rating", 0))
        score = b * 10.0
        if fa.get("primary_role") in needed_roles:
            score += 25.0
        elif fa.get("is_flex"):
            score += 22.0
        if not is_imp:
            score += 12.0 if openness <= 0.15 else 4.0
        elif fa.get("region_slug") == club_region_slug:
            score += 2.0
        # Yếu tố ngẫu nhiên nhỏ giúp chuyển nhượng đa dạng
        score += r.uniform(0.0, 2.5)
        return score

    best_fa, _ = max(pool_to_score, key=_score_candidate)
    return best_fa
