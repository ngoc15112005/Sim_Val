"""
services/player_service.py — Dịch vụ Quản lý Tuyển thủ, Đội hình, Quỹ lương & Biến động Tiền mùa giải (v2.0).
"""

from __future__ import annotations
import json
import random
from typing import Dict, List, Any, Optional
from sqlalchemy.orm import joinedload

from models import (
    db, Club, Campaign, CampaignClubState, CampaignPlayer, CampaignStagePlacement
)
from engine.partnership import SUBREGION_METADATA, get_club_country_info
from engine.players_data import (
    CORE_ROLES,
    ALL_ROLES,
    MAX_STARTERS,
    MAX_BENCH,
    MAX_FOREIGN_STARTERS,
    REAL_LIFE_ROSTERS,
    REAL_LIFE_FREE_AGENTS,
)
from engine.player_engine import (
    clamp_bonus,
    calculate_player_salary,
    get_club_salary_cap,
    get_club_import_openness,
    is_foreign_player,
    is_cross_region_import,
    calculate_roster_bonus,
    calculate_roster_payroll,
    check_4_roles_covered,
    validate_roster_lineup,
    generate_authentic_ign,
    generate_rookie_player_dict,
    evaluate_offseason_player_events,
    pick_ai_replacement_player,
)


def _initial_club_bonus_for_tier(club_rating: int, slot_idx: int) -> int:
    """Phân bổ chỉ số khởi tạo nhẹ [0..+2] cho các đội Tier-2/3 chưa nằm trong danh sách thực tế,
    đảm bảo tổng bonus hợp lý và không làm vỡ cân bằng.
    """
    if club_rating >= 82:
        pattern = [2, 1, 1, 1, 0]
    elif club_rating >= 75:
        pattern = [1, 1, 1, 0, 0]
    else:
        pattern = [1, 0, 0, 0, 0]
    return pattern[slot_idx % 5]


def initialize_campaign_players(campaign_id: int, start_year: int = 2027) -> int:
    """Khởi tạo toàn bộ pool tuyển thủ ban đầu (thực tế + sinh chuẩn bản sắc cho đủ 96 CLB)
    và đồng bộ quỹ lương + player_bonus vào CampaignClubState.
    """
    existing_cnt = CampaignPlayer.query.filter_by(campaign_id=campaign_id).count()
    if existing_cnt > 0:
        return existing_cnt

    rng = random.Random(campaign_id * 1009 + start_year)
    club_states = (
        CampaignClubState.query
        .options(joinedload(CampaignClubState.club).joinedload(Club.region))
        .filter_by(campaign_id=campaign_id)
        .all()
    )

    used_igns: set[str] = set()
    # Thu thập trước IGN của các đội thực tế & free agents để không trùng
    for roster in REAL_LIFE_ROSTERS.values():
        for entry in roster:
            used_igns.add(entry[0].lower())
    for fa in REAL_LIFE_FREE_AGENTS:
        used_igns.add(fa[0].lower())

    created_count = 0

    for cs in club_states:
        club = cs.club
        if not club:
            continue
        reg_slug = club.region.slug if club.region else "pacific"
        c_info = get_club_country_info(club.short_code, reg_slug)
        c_code = c_info["country_code"]

        cap = get_club_salary_cap(club.short_code, bool(cs.is_partner), reg_slug)
        cs.salary_cap = cap

        roster_entries = REAL_LIFE_ROSTERS.get(club.short_code)
        starters_bonus_sum = 0

        if roster_entries:
            for ign, age, nat, p_role, b_val, sec_role, is_flx in roster_entries:
                b = clamp_bonus(b_val)
                sal = calculate_player_salary(b, is_flex=is_flx, roster_slot="starter")
                cp = CampaignPlayer(
                    campaign_id=campaign_id,
                    club_id=club.id,
                    ign=ign,
                    real_name=ign,
                    age=age,
                    nationality=nat,
                    region_slug=reg_slug,
                    primary_role=p_role,
                    secondary_role=sec_role,
                    is_flex=bool(is_flx or p_role == "Flex"),
                    bonus_rating=b,
                    salary=sal,
                    roster_slot="starter",
                    status="active",
                    debut_year=start_year - max(1, age - 18),
                    seasons_played=max(1, age - 19),
                    is_custom=False,
                    is_real_life=True,
                )
                db.session.add(cp)
                starters_bonus_sum += b
                created_count += 1
        else:
            # Sinh 5 tuyển thủ chuẩn 4 Role + 1 Flex/thứ 5 mang quốc tịch bản địa
            roles_5 = ["Duelist", "Initiator", "Controller", "Sentinel", rng.choice(["Flex", "Initiator", "Controller"])]
            for idx, r_name in enumerate(roles_5):
                is_flx = (r_name == "Flex") or (rng.random() < 0.08)
                b = _initial_club_bonus_for_tier(club.base_rating or 74, idx)
                p_age = rng.randint(18, 25)
                # Xác suất nhỏ ngoại binh ngay từ mùa 1 dựa trên import_openness
                openness = get_club_import_openness(club.short_code, c_code)
                nat = c_code
                if idx == 4 and rng.random() < (openness * 0.5):
                    same_reg_codes = [k for k, m in SUBREGION_METADATA.items() if m["region"] == reg_slug and k != c_code]
                    if same_reg_codes:
                        nat = rng.choice(same_reg_codes)

                ign = generate_authentic_ign(nat, used_igns, rng=rng)
                sec = rng.choice([cr for cr in CORE_ROLES if cr != r_name]) if (is_flx or rng.random() < 0.2) else None
                sal = calculate_player_salary(b, is_flex=is_flx, roster_slot="starter")
                cp = CampaignPlayer(
                    campaign_id=campaign_id,
                    club_id=club.id,
                    ign=ign,
                    real_name=ign,
                    age=p_age,
                    nationality=nat,
                    region_slug=reg_slug,
                    primary_role=r_name,
                    secondary_role=sec,
                    is_flex=is_flx,
                    bonus_rating=b,
                    salary=sal,
                    roster_slot="starter",
                    status="active",
                    debut_year=start_year - max(0, p_age - 18),
                    seasons_played=max(0, p_age - 19),
                    is_custom=False,
                    is_real_life=False,
                )
                db.session.add(cp)
                starters_bonus_sum += b
                created_count += 1

        cs.player_bonus = starters_bonus_sum

    # Tạo Pool Tuyển thủ Tự do (Free Agents) thực tế + dự trữ vùng để thị trường chuyển nhượng hoạt động ngay
    for ign, age, nat, p_role, b_val, sec_role, is_flx, reg_slug in REAL_LIFE_FREE_AGENTS:
        b = clamp_bonus(b_val)
        sal = calculate_player_salary(b, is_flex=is_flx, roster_slot="free_agent")
        fa = CampaignPlayer(
            campaign_id=campaign_id,
            club_id=None,
            ign=ign,
            real_name=ign,
            age=age,
            nationality=nat,
            region_slug=reg_slug,
            primary_role=p_role,
            secondary_role=sec_role,
            is_flex=bool(is_flx or p_role == "Flex"),
            bonus_rating=b,
            salary=sal,
            roster_slot="free_agent",
            status="free_agent",
            debut_year=start_year - max(1, age - 18),
            seasons_played=max(1, age - 19),
            is_custom=False,
            is_real_life=True,
            career_note="Ngôi sao tự do sẵn sàng gia nhập thị trường VCT",
        )
        db.session.add(fa)
        created_count += 1

    # Bổ sung thêm ~52 Free Agents phân bố khắp các quốc gia/tiểu khu vực (để Hàn, VN, BR, CN... luôn có hàng nội địa)
    all_codes = list(SUBREGION_METADATA.keys())
    for i in range(52):
        cc = all_codes[i % len(all_codes)]
        reg_slug = SUBREGION_METADATA[cc]["region"]
        role = CORE_ROLES[i % 4]
        rookie_d = generate_rookie_player_dict(
            country_code=cc,
            region_slug=reg_slug,
            debut_year=start_year,
            role=role,
            existing_igns=used_igns,
            age=rng.randint(18, 25),
            rng=rng,
        )
        fa = CampaignPlayer(
            campaign_id=campaign_id,
            club_id=None,
            ign=rookie_d["ign"],
            real_name=rookie_d["ign"],
            age=rookie_d["age"],
            nationality=cc,
            region_slug=reg_slug,
            primary_role=rookie_d["primary_role"],
            secondary_role=rookie_d["secondary_role"],
            is_flex=rookie_d["is_flex"],
            bonus_rating=rookie_d["bonus_rating"],
            salary=rookie_d["salary"],
            roster_slot="free_agent",
            status="free_agent",
            debut_year=start_year,
            seasons_played=max(0, rookie_d["age"] - 19),
            is_custom=False,
            is_real_life=False,
            career_note=f"Tuyển thủ tự do khu vực {SUBREGION_METADATA[cc]['short_name']}",
        )
        db.session.add(fa)
        created_count += 1

    db.session.flush()
    return created_count


def sync_club_player_bonus(campaign_id: int, club_id: int) -> int:
    """Tính lại và lưu CampaignClubState.player_bonus từ danh sách Starters hiện tại của CLB."""
    starters = CampaignPlayer.query.filter_by(
        campaign_id=campaign_id,
        club_id=club_id,
        status="active",
        roster_slot="starter",
    ).all()
    bonus = calculate_roster_bonus([{"bonus_rating": p.bonus_rating} for p in starters])
    cs = CampaignClubState.query.filter_by(campaign_id=campaign_id, club_id=club_id).first()
    if cs:
        cs.player_bonus = bonus
    return bonus


def sync_all_club_player_bonuses_and_caps(campaign_id: int):
    """Đồng bộ hàng loạt player_bonus và salary_cap cho cả 96 CLB trong chiến dịch."""
    club_states = (
        CampaignClubState.query
        .options(joinedload(CampaignClubState.club).joinedload(Club.region))
        .filter_by(campaign_id=campaign_id)
        .all()
    )
    active_starters = CampaignPlayer.query.filter_by(
        campaign_id=campaign_id, status="active", roster_slot="starter"
    ).all()
    by_club: Dict[int, List[CampaignPlayer]] = {}
    for p in active_starters:
        if p.club_id:
            by_club.setdefault(p.club_id, []).append(p)

    for cs in club_states:
        if cs.club:
            reg_slug = cs.club.region.slug if cs.club.region else "pacific"
            cs.salary_cap = get_club_salary_cap(cs.club.short_code, bool(cs.is_partner), reg_slug)
        plist = by_club.get(cs.club_id, [])
        cs.player_bonus = calculate_roster_bonus([{"bonus_rating": p.bonus_rating} for p in plist])


def get_campaign_players(
    campaign_id: int,
    region_slug: Optional[str] = None,
    club_id: Optional[int] = None,
    status: Optional[str] = None,
    role: Optional[str] = None,
    nationality: Optional[str] = None,
    search: Optional[str] = None,
) -> Dict[str, Any]:
    """Lấy danh sách tuyển thủ trong chiến dịch kèm thông kê tổng quan."""
    q = (
        CampaignPlayer.query
        .options(joinedload(CampaignPlayer.club).joinedload(Club.region))
        .filter_by(campaign_id=campaign_id)
    )
    if region_slug and region_slug != "all":
        q = q.filter_by(region_slug=region_slug)
    if club_id:
        q = q.filter_by(club_id=int(club_id))
    if status and status != "all":
        q = q.filter_by(status=status)
    if nationality and nationality != "all":
        q = q.filter_by(nationality=nationality)
    if role and role != "all":
        if role == "Flex":
            q = q.filter((CampaignPlayer.primary_role == "Flex") | (CampaignPlayer.is_flex == True))
        else:
            q = q.filter_by(primary_role=role)
    if search and search.strip():
        term = f"%{search.strip()}%"
        q = q.filter(CampaignPlayer.ign.ilike(term))

    players = q.order_by(
        CampaignPlayer.bonus_rating.desc(),
        CampaignPlayer.age.asc(),
        CampaignPlayer.ign.asc(),
    ).all()

    all_counts = (
        db.session.query(CampaignPlayer.status, db.func.count(CampaignPlayer.id))
        .filter_by(campaign_id=campaign_id)
        .group_by(CampaignPlayer.status)
        .all()
    )
    counts_map = {st: cnt for st, cnt in all_counts}

    return {
        "players": [p.to_dict() for p in players],
        "counts": {
            "active": counts_map.get("active", 0),
            "free_agent": counts_map.get("free_agent", 0),
            "retired": counts_map.get("retired", 0),
            "total": sum(counts_map.values()),
        },
        "subregions": list(SUBREGION_METADATA.values()),
        "roles": list(ALL_ROLES),
    }


def get_campaign_clubs_roster_summary(campaign_id: int) -> Dict[int, Dict[str, Any]]:
    """Lấy tóm tắt nhanh đội hình (5 starters, payroll, roles_ok, player_bonus) của cả 96 CLB bằng 1 query."""
    active_players = CampaignPlayer.query.filter_by(
        campaign_id=campaign_id, status="active"
    ).all()

    by_club: Dict[int, Dict[str, List[Dict[str, Any]]]] = {}
    for p in active_players:
        if not p.club_id:
            continue
        bucket = by_club.setdefault(p.club_id, {"starter": [], "bench": []})
        slot = "starter" if p.roster_slot == "starter" else "bench"
        bucket[slot].append({
            "ign": p.ign,
            "primary_role": p.primary_role,
            "secondary_role": p.secondary_role,
            "is_flex": bool(p.is_flex or p.primary_role == "Flex"),
            "bonus_rating": clamp_bonus(p.bonus_rating),
            "salary": p.salary,
            "nationality": p.nationality,
        })

    summaries: Dict[int, Dict[str, Any]] = {}
    for cid, slots in by_club.items():
        starters = slots["starter"]
        bench = slots["bench"]
        roles_ok, _, missing = check_4_roles_covered(starters)
        payroll = sum(s["salary"] for s in starters) + sum(b["salary"] for b in bench)
        summaries[cid] = {
            "starter_count": len(starters),
            "bench_count": len(bench),
            "roles_ok": roles_ok,
            "missing_roles": missing,
            "payroll": payroll,
            "starter_igns": [f"{s['ign']} (+{s['bonus_rating']})" for s in starters],
        }
    return summaries


def get_club_roster_details(campaign_id: int, club_id: int) -> Dict[str, Any]:
    """Lấy chi tiết đội hình, 4 Role check, Quỹ lương, Ngoại binh và Free Agents khả dụng cho 1 CLB."""
    club = db.session.get(Club, club_id)
    if not club:
        raise ValueError("Không tìm thấy CLB")

    cs = CampaignClubState.query.filter_by(campaign_id=campaign_id, club_id=club_id).first()
    if not cs:
        raise ValueError("Không tìm thấy dữ liệu CLB trong chiến dịch này")

    reg_slug = club.region.slug if club.region else "pacific"
    c_info = get_club_country_info(club.short_code, reg_slug)
    salary_cap = cs.salary_cap or get_club_salary_cap(club.short_code, bool(cs.is_partner), reg_slug)

    club_players = (
        CampaignPlayer.query
        .filter_by(campaign_id=campaign_id, club_id=club_id, status="active")
        .order_by(CampaignPlayer.roster_slot.desc(), CampaignPlayer.bonus_rating.desc())
        .all()
    )
    starters = [p.to_dict() for p in club_players if p.roster_slot == "starter"]
    bench = [p.to_dict() for p in club_players if p.roster_slot == "bench"]

    is_valid, errors, metrics = validate_roster_lineup(
        starters=starters,
        bench=bench,
        club_country_code=c_info["country_code"],
        club_region_slug=reg_slug,
        salary_cap=salary_cap,
        strict_starter_count=True,
    )

    fa_players = (
        CampaignPlayer.query
        .filter_by(campaign_id=campaign_id, status="free_agent")
        .order_by(CampaignPlayer.bonus_rating.desc(), CampaignPlayer.age.asc())
        .all()
    )

    # Gợi ý ưu tiên Free Agents cùng quốc gia / khu vực lên đầu danh sách
    fa_list = []
    for fa in fa_players:
        d = fa.to_dict()
        d["is_foreign_for_club"] = is_foreign_player(fa.nationality, c_info["country_code"], reg_slug)
        fa_list.append(d)
    fa_list.sort(key=lambda x: (
        1 if x["is_foreign_for_club"] else 0,
        0 if x["region_slug"] == reg_slug else 1,
        -x["bonus_rating"],
        x["age"],
    ))

    return {
        "club": club.to_dict(),
        "club_state": cs.to_dict(),
        "import_openness": get_club_import_openness(club.short_code, c_info["country_code"]),
        "starters": starters,
        "bench": bench,
        "validation": {
            "is_valid": is_valid,
            "errors": errors,
            "metrics": metrics,
        },
        "free_agents": fa_list,
    }


def update_club_roster_bulk(
    campaign_id: int,
    club_id: int,
    starter_ids: List[int],
    bench_ids: Optional[List[int]] = None,
) -> Dict[str, Any]:
    """Cập nhật toàn bộ đội hình CLB (cho phép ký từ Free Agent, đẩy xuống Bench hoặc thanh lý về FA).
    Kiểm tra nghiêm ngặt: Đúng 5 Starters, phủ đủ 4 Role cốt lõi, tối đa 2 Ngoại binh, trong Quỹ lương!
    """
    club = db.session.get(Club, club_id)
    if not club:
        raise ValueError("Không tìm thấy CLB")

    cs = CampaignClubState.query.filter_by(campaign_id=campaign_id, club_id=club_id).first()
    if not cs:
        raise ValueError("Không tìm thấy trạng thái CLB")

    reg_slug = club.region.slug if club.region else "pacific"
    c_info = get_club_country_info(club.short_code, reg_slug)
    salary_cap = cs.salary_cap or get_club_salary_cap(club.short_code, bool(cs.is_partner), reg_slug)

    s_ids = [int(pid) for pid in (starter_ids or [])]
    b_ids = [int(pid) for pid in (bench_ids or []) if int(pid) not in s_ids]

    if len(set(s_ids)) != len(s_ids):
        raise ValueError("Danh sách Starters có ID trùng lặp")

    target_ids = s_ids + b_ids
    selected_players = (
        CampaignPlayer.query
        .filter(CampaignPlayer.campaign_id == campaign_id, CampaignPlayer.id.in_(target_ids))
        .all()
        if target_ids else []
    )
    by_id = {p.id: p for p in selected_players}

    for pid in target_ids:
        p = by_id.get(pid)
        if not p:
            raise ValueError(f"Không tìm thấy tuyển thủ ID {pid}")
        if p.status == "retired":
            raise ValueError(f"Tuyển thủ {p.ign} đã giải nghệ, không thể đăng ký thi đấu")
        if p.club_id is not None and p.club_id != club_id:
            raise ValueError(f"Tuyển thủ {p.ign} đang thuộc biên chế CLB khác")

    starter_dicts = []
    for pid in s_ids:
        p = by_id[pid]
        d = p.to_dict()
        d["salary"] = calculate_player_salary(p.bonus_rating, d["is_flex"], "starter")
        starter_dicts.append(d)

    bench_dicts = []
    for pid in b_ids:
        p = by_id[pid]
        d = p.to_dict()
        d["salary"] = calculate_player_salary(p.bonus_rating, d["is_flex"], "bench")
        d["roster_slot"] = "bench"
        bench_dicts.append(d)

    is_valid, errors, metrics = validate_roster_lineup(
        starters=starter_dicts,
        bench=bench_dicts,
        club_country_code=c_info["country_code"],
        club_region_slug=reg_slug,
        salary_cap=salary_cap,
        strict_starter_count=True,
    )
    if not is_valid:
        raise ValueError(" | ".join(errors))

    # Thanh lý các cầu thủ cũ không còn nằm trong starters/bench ra Free Agent
    current_club_players = CampaignPlayer.query.filter_by(
        campaign_id=campaign_id, club_id=club_id, status="active"
    ).all()
    target_set = set(target_ids)
    for old_p in current_club_players:
        if old_p.id not in target_set:
            old_p.club_id = None
            old_p.status = "free_agent"
            old_p.roster_slot = "free_agent"
            old_p.salary = calculate_player_salary(old_p.bonus_rating, old_p.is_flex or old_p.primary_role == "Flex", "free_agent")

    # Cập nhật trạng thái mới cho Starters và Bench
    for pid in s_ids:
        p = by_id[pid]
        p.club_id = club_id
        p.status = "active"
        p.roster_slot = "starter"
        p.salary = calculate_player_salary(p.bonus_rating, p.is_flex or p.primary_role == "Flex", "starter")

    for pid in b_ids:
        p = by_id[pid]
        p.club_id = club_id
        p.status = "active"
        p.roster_slot = "bench"
        p.salary = calculate_player_salary(p.bonus_rating, p.is_flex or p.primary_role == "Flex", "bench")

    cs.player_bonus = metrics["player_bonus"]
    db.session.commit()
    return get_club_roster_details(campaign_id, club_id)


def create_custom_player(campaign_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
    """Cho phép người chơi tự tạo Tuyển thủ mới (tùy chọn ký thẳng cho CLB hoặc đưa vào Free Agent)."""
    campaign = db.session.get(Campaign, campaign_id)
    if not campaign:
        raise ValueError("Không tìm thấy chiến dịch")

    ign = str(data.get("ign") or "").strip()
    if not ign:
        raise ValueError("Tên thi đấu (IGN) không được để trống")

    existing = CampaignPlayer.query.filter(
        CampaignPlayer.campaign_id == campaign_id,
        db.func.lower(CampaignPlayer.ign) == ign.lower(),
    ).first()
    if existing:
        raise ValueError(f"Đã tồn tại tuyển thủ có IGN '{ign}' trong chiến dịch này")

    try:
        age = int(data.get("age", 19))
    except (ValueError, TypeError):
        age = 19
    if age < 16 or age > 45:
        raise ValueError("Tuổi tuyển thủ phải từ 16 đến 45")

    nat = str(data.get("nationality") or "VN").strip()
    if nat not in SUBREGION_METADATA:
        raise ValueError(f"Mã quốc tịch '{nat}' không hợp lệ")
    reg_slug = SUBREGION_METADATA[nat]["region"]

    role = str(data.get("primary_role") or "Duelist").strip()
    if role not in ALL_ROLES:
        raise ValueError(f"Role '{role}' không hợp lệ")

    sec_role = data.get("secondary_role")
    if sec_role and sec_role not in CORE_ROLES:
        sec_role = None

    is_flex = bool(data.get("is_flex")) or (role == "Flex")
    bonus_val = clamp_bonus(data.get("bonus_rating", 1))
    try:
        raw_bonus = int(data.get("bonus_rating", 1))
        if raw_bonus < 0 or raw_bonus > 5:
            raise ValueError("Chỉ số cộng thêm của tuyển thủ chỉ được nằm trong khoảng 0 đến +5")
        bonus_val = raw_bonus
    except (ValueError, TypeError):
        raise ValueError("Chỉ số cộng thêm phải là số nguyên từ 0 đến 5")

    club_id_raw = data.get("club_id")
    club_id = int(club_id_raw) if club_id_raw not in (None, "", "null", "fa") else None
    target_slot = str(data.get("roster_slot") or ("starter" if club_id else "free_agent"))
    if club_id is None:
        target_slot = "free_agent"
    elif target_slot not in ("starter", "bench"):
        target_slot = "bench"

    salary = calculate_player_salary(bonus_val, is_flex=is_flex, roster_slot=target_slot)

    new_p = CampaignPlayer(
        campaign_id=campaign_id,
        club_id=club_id,
        ign=ign,
        real_name=str(data.get("real_name") or ign).strip(),
        age=age,
        nationality=nat,
        region_slug=reg_slug,
        primary_role=role,
        secondary_role=sec_role,
        is_flex=is_flex,
        bonus_rating=bonus_val,
        salary=salary,
        roster_slot=target_slot,
        status="active" if club_id else "free_agent",
        debut_year=campaign.current_year,
        seasons_played=0,
        is_custom=True,
        is_real_life=False,
        career_note=str(data.get("career_note") or "Tuyển thủ tự tạo bởi Đạo diễn Giải đấu"),
    )

    # Nếu ký thẳng vào CLB, kiểm tra Quỹ lương & Slot
    if club_id:
        club = db.session.get(Club, club_id)
        if not club:
            raise ValueError("CLB chỉ định không tồn tại")
        cs = CampaignClubState.query.filter_by(campaign_id=campaign_id, club_id=club_id).first()
        c_reg = club.region.slug if club.region else reg_slug
        c_info = get_club_country_info(club.short_code, c_reg)
        salary_cap = (cs.salary_cap if cs else None) or get_club_salary_cap(club.short_code, bool(cs.is_partner if cs else False), c_reg)

        cur_players = CampaignPlayer.query.filter_by(campaign_id=campaign_id, club_id=club_id, status="active").all()
        cur_starters = [p.to_dict() for p in cur_players if p.roster_slot == "starter"]
        cur_bench = [p.to_dict() for p in cur_players if p.roster_slot == "bench"]

        if target_slot == "starter":
            if len(cur_starters) >= MAX_STARTERS:
                # Tự động chuyển vào Bench nếu 5 Starter đã đầy
                target_slot = "bench"
                new_p.roster_slot = "bench"
                new_p.salary = calculate_player_salary(bonus_val, is_flex=is_flex, roster_slot="bench")
        if target_slot == "bench" and len(cur_bench) >= MAX_BENCH:
            raise ValueError(f"{club.short_code} đã đủ tối đa {MAX_STARTERS} Starters và {MAX_BENCH} Bench! Hãy nhả bớt người hoặc đưa vào Chợ Tự Do.")

        test_starters = cur_starters + ([new_p.to_dict()] if target_slot == "starter" else [])
        test_bench = cur_bench + ([new_p.to_dict()] if target_slot == "bench" else [])
        payroll = calculate_roster_payroll(test_starters, test_bench)
        if payroll > salary_cap:
            raise ValueError(
                f"Không thể ký trực tiếp cho {club.short_code}: vượt trần quỹ lương (${payroll}K / ${salary_cap}K)!"
            )

        if target_slot == "starter":
            f_cnt = sum(1 for sp in test_starters if is_cross_region_import(sp.get("nationality", ""), c_reg))
            if f_cnt > MAX_FOREIGN_STARTERS:
                raise ValueError(f"Không thể đưa thẳng vào Starter của {club.short_code}: vượt quá {MAX_FOREIGN_STARTERS} ngoại binh liên khu vực!")

    db.session.add(new_p)
    db.session.flush()
    if club_id:
        sync_club_player_bonus(campaign_id, club_id)
    db.session.commit()
    return new_p.to_dict()


def _fill_club_roster_to_valid(
    campaign_id: int,
    club: Club,
    cs: CampaignClubState,
    fa_pool: List[CampaignPlayer],
    rng: random.Random,
    debut_year: int = 2027,
) -> Dict[str, Any]:
    """AI tự động hoàn thiện đội hình 5 Starters đủ 4 Role, <= 2 ngoại binh và <= Salary Cap cho 1 CLB."""
    reg_slug = club.region.slug if club.region else "pacific"
    c_info = get_club_country_info(club.short_code, reg_slug)
    c_code = c_info["country_code"]
    salary_cap = get_club_salary_cap(club.short_code, bool(cs.is_partner), reg_slug)
    cs.salary_cap = salary_cap

    club_players = CampaignPlayer.query.filter_by(
        campaign_id=campaign_id, club_id=club.id, status="active"
    ).all()
    starters = [p for p in club_players if p.roster_slot == "starter"]
    bench = [p for p in club_players if p.roster_slot == "bench"]

    # 1. Nếu có cầu thủ trên Bench giúp ích hoặc đủ 5 Starter vượt quỹ lương -> cân đối lại
    def _current_payroll() -> int:
        return sum(p.salary for p in starters) + sum(p.salary for p in bench)

    # Nếu vượt trần quỹ lương, nhả bớt Bench trước rồi tới Starter đắt nhất không làm gãy 4 role
    while _current_payroll() > salary_cap and bench:
        priciest_b = max(bench, key=lambda p: p.salary)
        bench.remove(priciest_b)
        priciest_b.club_id = None
        priciest_b.status = "free_agent"
        priciest_b.roster_slot = "free_agent"
        priciest_b.salary = calculate_player_salary(priciest_b.bonus_rating, priciest_b.is_flex or priciest_b.primary_role == "Flex", "free_agent")
        fa_pool.append(priciest_b)

    while _current_payroll() > salary_cap and starters:
        # Nhả người lương cao nhất mà sau đó có thể bù bằng cầu thủ rẻ +0 (+60K)
        priciest_s = max(starters, key=lambda p: p.salary)
        starters.remove(priciest_s)
        priciest_s.club_id = None
        priciest_s.status = "free_agent"
        priciest_s.roster_slot = "free_agent"
        priciest_s.salary = calculate_player_salary(priciest_s.bonus_rating, priciest_s.is_flex or priciest_s.primary_role == "Flex", "free_agent")
        fa_pool.append(priciest_s)

    # 2. Nếu có Bench và thiếu Starter -> đôn Bench lên trước nếu hợp lệ
    while len(starters) < MAX_STARTERS and bench:
        cand = bench.pop(0)
        new_sal = calculate_player_salary(cand.bonus_rating, cand.is_flex or cand.primary_role == "Flex", "starter")
        if _current_payroll() - cand.salary + new_sal <= salary_cap:
            cand.roster_slot = "starter"
            cand.salary = new_sal
            starters.append(cand)
        else:
            cand.club_id = None
            cand.status = "free_agent"
            cand.roster_slot = "free_agent"
            fa_pool.append(cand)

    signings = []
    # 3. Nếu thiếu vị trí Starter (< 5) hoặc thiếu Role trong 4 Role -> ký từ Free Agent Pool (hoặc sinh tân binh khẩn cấp nếu cạn pool)
    safety_guard = 0
    while (len(starters) < MAX_STARTERS or not check_4_roles_covered([p.to_dict() for p in starters])[0]) and safety_guard < 10:
        safety_guard += 1
        if len(starters) >= MAX_STARTERS:
            # Đủ 5 người nhưng bị trùng/thiếu 1 role -> thả 1 người trùng role rẻ/yếu nhất ra FA để ký đúng role thiếu
            roles_ok, _, missing = check_4_roles_covered([p.to_dict() for p in starters])
            if roles_ok or not missing:
                break
            role_counts: Dict[str, int] = {}
            for sp in starters:
                role_counts[sp.primary_role] = role_counts.get(sp.primary_role, 0) + 1
            dup_candidates = [sp for sp in starters if role_counts.get(sp.primary_role, 0) > 1]
            drop_target = min(dup_candidates or starters, key=lambda x: x.bonus_rating)
            starters.remove(drop_target)
            drop_target.club_id = None
            drop_target.status = "free_agent"
            drop_target.roster_slot = "free_agent"
            drop_target.salary = calculate_player_salary(drop_target.bonus_rating, drop_target.is_flex or drop_target.primary_role == "Flex", "free_agent")
            fa_pool.append(drop_target)

        slots_left = MAX_STARTERS - len(starters)
        # Dành tối thiểu $60K cho mỗi slot còn lại sau lượt ký này
        reserve_for_others = max(0, (slots_left - 1) * 60)
        budget_now = max(60, salary_cap - _current_payroll() - reserve_for_others)

        _, _, missing_roles = check_4_roles_covered([p.to_dict() for p in starters])
        needed = missing_roles if (missing_roles and len(missing_roles) >= slots_left) or (len(starters) >= 3 and missing_roles) else (missing_roles or list(CORE_ROLES))
        foreign_cnt = sum(1 for sp in starters if is_cross_region_import(sp.nationality, reg_slug))

        fa_dicts = [
            {
                "id": f.id,
                "ign": f.ign,
                "nationality": f.nationality,
                "region_slug": f.region_slug,
                "primary_role": f.primary_role,
                "secondary_role": f.secondary_role,
                "is_flex": bool(f.is_flex or f.primary_role == "Flex"),
                "bonus_rating": f.bonus_rating,
                "salary": calculate_player_salary(f.bonus_rating, bool(f.is_flex or f.primary_role == "Flex"), "starter"),
            }
            for f in fa_pool
        ]
        chosen_d = pick_ai_replacement_player(
            free_agents=fa_dicts,
            needed_roles=needed,
            club_short_code=club.short_code,
            club_country_code=c_code,
            club_region_slug=reg_slug,
            current_foreign_count=foreign_cnt,
            remaining_budget=budget_now,
            rng=rng,
        )

        chosen_obj = None
        if chosen_d:
            chosen_obj = next((f for f in fa_pool if f.id == chosen_d["id"]), None)
            if chosen_obj:
                fa_pool.remove(chosen_obj)

        if not chosen_obj:
            # Sinh gấp 1 học viện nội địa giá $60K (+0) đúng role còn thiếu để đảm bảo không bao giờ thiếu người!
            existing_igns = {
                r[0].lower() for r in db.session.query(CampaignPlayer.ign).filter_by(campaign_id=campaign_id).all()
            }
            role_pick = needed[0] if needed else "Flex"
            rk_dict = generate_rookie_player_dict(
                country_code=c_code,
                region_slug=reg_slug,
                debut_year=debut_year,
                role=role_pick,
                existing_igns=existing_igns,
                bonus_rating=0,
                rng=rng,
            )
            chosen_obj = CampaignPlayer(
                campaign_id=campaign_id,
                club_id=club.id,
                ign=rk_dict["ign"],
                real_name=rk_dict["ign"],
                age=rk_dict["age"],
                nationality=c_code,
                region_slug=reg_slug,
                primary_role=rk_dict["primary_role"],
                secondary_role=rk_dict["secondary_role"],
                is_flex=rk_dict["is_flex"],
                bonus_rating=0,
                salary=60,
                roster_slot="starter",
                status="active",
                debut_year=debut_year,
                is_real_life=False,
                career_note=f"Đôn lên từ đội trẻ {club.short_code}",
            )
            db.session.add(chosen_obj)
            db.session.flush()

        chosen_obj.club_id = club.id
        chosen_obj.status = "active"
        chosen_obj.roster_slot = "starter"
        chosen_obj.salary = calculate_player_salary(
            chosen_obj.bonus_rating, bool(chosen_obj.is_flex or chosen_obj.primary_role == "Flex"), "starter"
        )
        starters.append(chosen_obj)
        signings.append({
            "club_code": club.short_code,
            "club_name": club.name,
            "player_id": chosen_obj.id,
            "ign": chosen_obj.ign,
            "nationality": chosen_obj.nationality,
            "role": chosen_obj.primary_role,
            "bonus_rating": chosen_obj.bonus_rating,
            "salary": chosen_obj.salary,
        })

    cs.player_bonus = calculate_roster_bonus([{"bonus_rating": p.bonus_rating} for p in starters])
    return {"club_code": club.short_code, "signings": signings, "player_bonus": cs.player_bonus}


def auto_fill_club_roster(campaign_id: int, club_id: int) -> Dict[str, Any]:
    """Tự động ghép đội hình hợp lệ (5 người, đủ 4 Role, trong Quỹ lương) cho 1 CLB cụ thể."""
    club = db.session.get(Club, club_id)
    cs = CampaignClubState.query.filter_by(campaign_id=campaign_id, club_id=club_id).first()
    if not club or not cs:
        raise ValueError("Không tìm thấy CLB")

    fa_pool = CampaignPlayer.query.filter_by(campaign_id=campaign_id, status="free_agent").all()
    _fill_club_roster_to_valid(campaign_id, club, cs, fa_pool, random.Random())
    db.session.commit()
    return get_club_roster_details(campaign_id, club_id)


def generate_preseason_personnel_draft(campaign_id: int, target_year: Optional[int] = None) -> Dict[str, Any]:
    """Sinh Dự thảo Biến động Nhân sự Tiền Mùa Giải (Giải nghệ, Comeback, Tiến hóa Role/Flex, Tân binh)
    để trình lên người chơi duyệt trước khi sang năm mới.
    """
    camp = db.session.get(Campaign, campaign_id)
    if not camp:
        raise ValueError("Không tìm thấy chiến dịch")

    next_year = int(target_year or (camp.current_year + 1))
    prev_year = next_year - 1

    # Tính thành tích mùa vừa qua của từng CLB để hỗ trợ tăng chỉ số cho các đội mạnh
    placements = CampaignStagePlacement.query.filter_by(campaign_id=campaign_id, year=prev_year).all()
    club_success: Dict[int, float] = {}
    for p in placements:
        score = 0.4
        if p.rank == 1:
            score = 0.95
        elif p.rank == 2:
            score = 0.85
        elif p.rank <= 4:
            score = 0.72
        club_success[p.club_id] = max(club_success.get(p.club_id, 0.4), score)

    players = (
        CampaignPlayer.query
        .options(joinedload(CampaignPlayer.club).joinedload(Club.region))
        .filter_by(campaign_id=campaign_id)
        .all()
    )
    player_dicts = [p.to_dict() for p in players]

    draft = evaluate_offseason_player_events(
        players=player_dicts,
        next_year=next_year,
        club_success_scores=club_success,
        target_pool_size=560,
    )
    draft["campaign_id"] = campaign_id
    return draft


def commit_preseason_personnel_decisions(
    campaign_id: int,
    decisions: Optional[Dict[str, Any]] = None,
    target_year: Optional[int] = None,
    run_ai_transfers: bool = True,
) -> Dict[str, Any]:
    """Áp dụng các quyết định Tiền Mùa Giải đã được người chơi phê duyệt:
    1. Tăng 1 tuổi cho toàn bộ tuyển thủ, cập nhật years_retired / seasons_played.
    2. Thực thi Giải nghệ, Comeback, Tiến hóa Role/Flex, Điều chỉnh chỉ số đã duyệt.
    3. Thêm các Tân binh Debut đã duyệt vào Free Agents.
    4. Cho AI các CLB chuyển nhượng bổ sung đủ 5 Starter, đủ 4 Role, trong Quỹ lương & đúng Bản sắc Ngoại binh.
    """
    camp = db.session.get(Campaign, campaign_id)
    if not camp:
        raise ValueError("Không tìm thấy chiến dịch")

    eff_year = int(target_year or camp.current_year)
    if decisions is None:
        decisions = generate_preseason_personnel_draft(campaign_id, target_year=eff_year)

    players_by_id = {
        p.id: p
        for p in CampaignPlayer.query.filter_by(campaign_id=campaign_id).all()
    }

    # 1. Tăng tuổi & thâm niên cho toàn bộ pool
    for p in players_by_id.values():
        p.age = int(p.age or 20) + 1
        if p.status == "retired":
            p.years_retired = int(p.years_retired or 0) + 1
        elif p.status == "active":
            p.seasons_played = int(p.seasons_played or 0) + 1

    # 2. Thực thi Giải nghệ (chỉ những người có approved=True)
    approved_retirements = 0
    for item in decisions.get("retirements", []):
        if not item.get("approved", True):
            continue
        p = players_by_id.get(int(item["player_id"]))
        if p and p.status != "retired":
            p.status = "retired"
            p.roster_slot = "retired"
            p.club_id = None
            p.retired_year = eff_year
            p.years_retired = 0
            p.career_note = item.get("reason") or f"Giải nghệ cuối mùa {eff_year - 1}"
            approved_retirements += 1

    # 3. Thực thi Comeback (chỉ những người có approved=True)
    approved_comebacks = 0
    for item in decisions.get("comebacks", []):
        if not item.get("approved", True):
            continue
        p = players_by_id.get(int(item["player_id"]))
        if p and p.status == "retired":
            p.status = "free_agent"
            p.roster_slot = "free_agent"
            p.club_id = None
            p.years_retired = 0
            p.bonus_rating = clamp_bonus(item.get("bonus_rating", p.bonus_rating))
            p.salary = calculate_player_salary(p.bonus_rating, bool(p.is_flex or p.primary_role == "Flex"), "free_agent")
            p.career_note = f"Comeback gây chấn động ở tuổi {p.age} (Mùa {eff_year})"
            approved_comebacks += 1

    # 4. Thực thi Tiến hóa Role / Flex
    approved_evolutions = 0
    for item in decisions.get("role_evolutions", []):
        if not item.get("approved", True):
            continue
        p = players_by_id.get(int(item["player_id"]))
        if p and p.status != "retired":
            p.primary_role = item.get("new_role", p.primary_role)
            p.secondary_role = item.get("new_secondary_role", p.secondary_role)
            p.is_flex = bool(item.get("new_is_flex", p.is_flex or p.primary_role == "Flex"))
            p.salary = calculate_player_salary(p.bonus_rating, p.is_flex, p.roster_slot)
            approved_evolutions += 1

    # 5. Thực thi Điều chỉnh chỉ số (+0..+5)
    for item in decisions.get("rating_changes", []):
        if not item.get("approved", True):
            continue
        p = players_by_id.get(int(item["player_id"]))
        if p and p.status != "retired":
            p.bonus_rating = clamp_bonus(item.get("new_bonus", p.bonus_rating))
            p.salary = calculate_player_salary(p.bonus_rating, bool(p.is_flex or p.primary_role == "Flex"), p.roster_slot)

    # 6. Thêm Tân binh Debut được duyệt
    existing_igns = {p.ign.lower() for p in players_by_id.values()}
    approved_rookies = 0
    for rk in decisions.get("rookies", []):
        if not rk.get("approved", True):
            continue
        ign = str(rk.get("ign") or "").strip()
        if not ign or ign.lower() in existing_igns:
            continue
        existing_igns.add(ign.lower())
        cc = rk.get("nationality", "SG_MY")
        rg = rk.get("region_slug") or SUBREGION_METADATA.get(cc, {}).get("region", "pacific")
        b = clamp_bonus(rk.get("bonus_rating", 0))
        is_flx = bool(rk.get("is_flex") or rk.get("primary_role") == "Flex")
        new_rk = CampaignPlayer(
            campaign_id=campaign_id,
            club_id=None,
            ign=ign,
            real_name=ign,
            age=int(rk.get("age", 18)),
            nationality=cc,
            region_slug=rg,
            primary_role=rk.get("primary_role", "Duelist"),
            secondary_role=rk.get("secondary_role"),
            is_flex=is_flx,
            bonus_rating=b,
            salary=calculate_player_salary(b, is_flex=is_flx, roster_slot="free_agent"),
            roster_slot="free_agent",
            status="free_agent",
            debut_year=eff_year,
            seasons_played=0,
            is_custom=bool(rk.get("is_custom", False)),
            is_real_life=False,
            career_note=rk.get("career_note") or f"Tân binh debut mùa {eff_year}",
        )
        db.session.add(new_rk)
        approved_rookies += 1

    db.session.flush()

    # 7. AI chuyển nhượng điền đủ 5 Starters, đủ 4 Role, trong Quỹ lương cho toàn bộ 96 CLB
    ai_transfers: List[Dict[str, Any]] = []
    if run_ai_transfers:
        rng = random.Random()
        fa_pool = CampaignPlayer.query.filter_by(campaign_id=campaign_id, status="free_agent").all()
        club_states = (
            CampaignClubState.query
            .options(joinedload(CampaignClubState.club).joinedload(Club.region))
            .filter_by(campaign_id=campaign_id)
            .order_by(CampaignClubState.is_partner.desc(), CampaignClubState.story_rating.desc())
            .all()
        )
        for cs in club_states:
            if not cs.club:
                continue
            fill_res = _fill_club_roster_to_valid(campaign_id, cs.club, cs, fa_pool, rng, debut_year=eff_year)
            ai_transfers.extend(fill_res.get("signings", []))
    else:
        sync_all_club_player_bonuses_and_caps(campaign_id)

    db.session.commit()
    return {
        "success": True,
        "year": eff_year,
        "approved_retirements": approved_retirements,
        "approved_comebacks": approved_comebacks,
        "approved_evolutions": approved_evolutions,
        "approved_rookies": approved_rookies,
        "ai_signings_count": len(ai_transfers),
        "ai_signings_preview": ai_transfers[:20],
    }
