"""
services/partnership_service.py — Dịch vụ Quản lý Đánh giá & Tái cấu trúc Đội Partner (Chu kỳ 24 Tháng / 2 Năm).

Kết nối dữ liệu thực tế của Chiến dịch (CampaignClubState, CampaignStagePlacement, CampaignStoryline)
với Engine chấm điểm 100 điểm (engine/partnership.py) và lưu trữ lịch sử thẩm định vào DB.
"""

from __future__ import annotations
import json
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional

from models import (
    db, Club, Region, Campaign, CampaignClubState,
    CampaignStage, CampaignSeason, CampaignStagePlacement,
    CampaignStoryline, CampaignPartnershipReview
)
from engine.partnership import (
    DEFAULT_PARTNERSHIP_CONFIG,
    SUBREGION_METADATA,
    get_club_country_info,
    get_region_subregions,
    validate_partnership_config,
    evaluate_club_partnership,
    evaluate_region_partnership,
    validate_manual_partner_selection,
)


ALL_REGIONS = ["pacific", "americas", "emea", "china"]


def get_campaign_start_year(campaign_id: int) -> int:
    """Xác định năm bắt đầu đầu tiên của chiến dịch (mặc định 2027)."""
    min_stage = (
        db.session.query(db.func.min(CampaignStage.year))
        .filter_by(campaign_id=campaign_id)
        .scalar()
    )
    min_season = (
        db.session.query(db.func.min(CampaignSeason.year))
        .filter_by(campaign_id=campaign_id)
        .scalar()
    )
    candidates = [y for y in (min_stage, min_season) if y is not None]
    if candidates:
        return int(min(candidates))
    camp = db.session.get(Campaign, campaign_id)
    return int(camp.current_year) if camp else 2027


def get_partnership_cycle_status(campaign_id: int, year: Optional[int] = None) -> Dict[str, Any]:
    """Kiểm tra trạng thái chu kỳ đánh giá Partner 2 năm/lần tại năm `year`."""
    camp = db.session.get(Campaign, campaign_id)
    if not camp:
        raise ValueError(f"Campaign {campaign_id} not found")

    eval_year = int(year if year is not None else camp.current_year)
    start_year = get_campaign_start_year(campaign_id)
    seasons_elapsed = max(1, eval_year - start_year + 1)

    # Chu kỳ 2 năm/lần: kết thúc mùa 2 (ví dụ 2028), mùa 4 (2030), mùa 6 (2032)...
    is_review_cycle = (seasons_elapsed >= 2) and (seasons_elapsed % 2 == 0)
    cycle_start = eval_year - 1 if eval_year > start_year else start_year
    cycle_label = f"{cycle_start}-{eval_year}"

    if is_review_cycle:
        next_review_year = eval_year
    else:
        next_review_year = eval_year + 1

    review_rec = CampaignPartnershipReview.query.filter_by(
        campaign_id=campaign_id, year=eval_year
    ).first()
    is_committed = bool(review_rec and review_rec.status == "committed")

    return {
        "campaign_id": campaign_id,
        "start_year": start_year,
        "evaluation_year": eval_year,
        "seasons_elapsed": seasons_elapsed,
        "cycle_label": cycle_label,
        "is_review_cycle": is_review_cycle,
        "is_committed": is_committed,
        "is_due": bool(is_review_cycle and not is_committed),
        "next_review_year": next_review_year,
    }


def generate_partnership_evaluation(
    campaign_id: int,
    year: Optional[int] = None,
    force_recalculate: bool = False,
) -> Dict[str, Any]:
    """Chạy chấm điểm 100 điểm (5 trụ cột, 19 chỉ số) cho toàn bộ 96 đội tuyển ở 4 khu vực
    trong cửa sổ 24 tháng (year - 1 và year) và trả về đề xuất 8 đội Partner/khu vực (Country Cap <= 2).
    """
    camp = db.session.get(Campaign, campaign_id)
    if not camp:
        raise ValueError(f"Campaign {campaign_id} not found")

    eval_year = int(year if year is not None else camp.current_year)
    cycle_status = get_partnership_cycle_status(campaign_id, eval_year)
    cycle_label = cycle_status["cycle_label"]

    existing_rec = CampaignPartnershipReview.query.filter_by(
        campaign_id=campaign_id, year=eval_year
    ).first()

    if existing_rec and existing_rec.status == "committed" and not force_recalculate:
        try:
            saved_payload = json.loads(existing_rec.evaluation_data or "{}")
            if saved_payload and "regions" in saved_payload:
                saved_payload["cycle_status"] = cycle_status
                saved_payload["status"] = "committed"
                saved_payload["committed_at"] = (
                    existing_rec.committed_at.isoformat() if existing_rec.committed_at else None
                )
                return saved_payload
        except Exception:
            pass

    # Lấy dữ liệu 24 tháng (eval_year - 1 và eval_year)
    window_years = [eval_year - 1, eval_year]

    placements_q = CampaignStagePlacement.query.filter(
        CampaignStagePlacement.campaign_id == campaign_id,
        CampaignStagePlacement.year.in_(window_years),
    ).all()
    placements_by_club: Dict[int, List[Dict[str, Any]]] = {}
    for p in placements_q:
        placements_by_club.setdefault(p.club_id, []).append(p.to_dict())

    storylines_q = CampaignStoryline.query.filter(
        CampaignStoryline.campaign_id == campaign_id,
        CampaignStoryline.year.in_(window_years),
    ).all()
    storylines_by_club: Dict[int, List[Dict[str, Any]]] = {}
    for st in storylines_q:
        if st.club_id:
            storylines_by_club.setdefault(st.club_id, []).append(st.to_dict())

    club_states = CampaignClubState.query.filter_by(campaign_id=campaign_id).all()
    cs_by_club = {cs.club_id: cs for cs in club_states}

    regions_eval: Dict[str, Any] = {}
    total_retained = 0
    total_promoted = 0
    total_demoted = 0

    for reg_slug in ALL_REGIONS:
        reg_obj = Region.query.filter_by(slug=reg_slug).first()
        if not reg_obj:
            continue
        reg_clubs = Club.query.filter_by(region_id=reg_obj.id).all()

        evaluated_clubs = []
        for club in reg_clubs:
            c_dict = club.to_dict()
            cs = cs_by_club.get(club.id)
            cs_dict = cs.to_dict() if cs else {
                "club_id": club.id,
                "story_rating": club.base_rating or 80,
                "power_score": 1500.0,
                "is_partner": False,
            }
            c_placements = placements_by_club.get(club.id, [])
            c_storylines = storylines_by_club.get(club.id, [])

            ev = evaluate_club_partnership(
                club_dict=c_dict,
                club_state_dict=cs_dict,
                placements_24m=c_placements,
                storylines_24m=c_storylines,
                evaluation_year=eval_year,
                config=DEFAULT_PARTNERSHIP_CONFIG,
            )
            evaluated_clubs.append(ev)

        reg_result = evaluate_region_partnership(
            region_slug=reg_slug,
            evaluated_clubs=evaluated_clubs,
            config=DEFAULT_PARTNERSHIP_CONFIG,
        )
        regions_eval[reg_slug] = reg_result
        total_retained += reg_result["retained_count"]
        total_promoted += reg_result["promoted_count"]
        total_demoted += reg_result["demoted_count"]

    payload = {
        "campaign_id": campaign_id,
        "evaluation_year": eval_year,
        "cycle_label": cycle_label,
        "status": existing_rec.status if existing_rec else "pending_review",
        "cycle_status": cycle_status,
        "config": DEFAULT_PARTNERSHIP_CONFIG,
        "summary": {
            "total_partners": 32,
            "retained_count": total_retained,
            "promoted_count": total_promoted,
            "demoted_count": total_demoted,
        },
        "regions": regions_eval,
    }

    if not existing_rec:
        existing_rec = CampaignPartnershipReview(
            campaign_id=campaign_id,
            year=eval_year,
            cycle_label=cycle_label,
            status="pending_review",
            evaluation_data=json.dumps(payload),
        )
        db.session.add(existing_rec)
    elif existing_rec.status != "committed" or force_recalculate:
        existing_rec.evaluation_data = json.dumps(payload)

    db.session.commit()
    return payload


def commit_partnership_selection(
    campaign_id: int,
    selections_by_region: Dict[str, List[int]],
    year: Optional[int] = None,
) -> Dict[str, Any]:
    """Xác nhận và khóa danh sách 32 đội Partner mới (8 đội x 4 khu vực) do người chơi chốt.
    Bắt buộc kiểm tra RÀNG BUỘC CỨNG:
    - Đúng 8 đội mỗi khu vực.
    - Tối đa 2 đội trên mỗi Quốc gia / Tiểu khu vực (Country/Sub-region Cap <= 2).
    """
    camp = db.session.get(Campaign, campaign_id)
    if not camp:
        raise ValueError(f"Campaign {campaign_id} not found")

    eval_year = int(year if year is not None else camp.current_year)
    if not selections_by_region or not isinstance(selections_by_region, dict):
        raise ValueError("Dữ liệu danh sách đội Partner (selections_by_region) không hợp lệ.")

    # Lấy dữ liệu đánh giá hiện tại để đối chiếu
    eval_payload = generate_partnership_evaluation(campaign_id, year=eval_year, force_recalculate=True)
    regions_data = eval_payload.get("regions", {})

    # 1. Kiểm tra nghiêm ngặt cả 4 khu vực
    validated_selections: Dict[str, List[int]] = {}
    for reg_slug in ALL_REGIONS:
        if reg_slug not in selections_by_region:
            raise ValueError(f"Thiếu danh sách đội Partner cho khu vực {reg_slug.upper()}.")
        raw_ids = selections_by_region[reg_slug]
        if not isinstance(raw_ids, list):
            raise ValueError(f"Danh sách đội khu vực {reg_slug.upper()} phải là một mảng ID.")

        reg_clubs = regions_data.get(reg_slug, {}).get("clubs", [])
        is_valid, err_msg, _violations = validate_manual_partner_selection(
            region_slug=reg_slug,
            selected_club_ids=raw_ids,
            region_clubs=reg_clubs,
            config=DEFAULT_PARTNERSHIP_CONFIG,
        )
        if not is_valid:
            raise ValueError(err_msg)

        validated_selections[reg_slug] = [int(cid) for cid in raw_ids]

    # 2. Cập nhật trạng thái is_partner cho toàn bộ 96 đội trong CampaignClubState
    all_selected_ids = set()
    for r_ids in validated_selections.values():
        all_selected_ids.update(r_ids)

    club_states = CampaignClubState.query.filter_by(campaign_id=campaign_id).all()
    promoted_teams = []
    demoted_teams = []
    retained_teams = []

    for cs in club_states:
        was_p = bool(cs.is_partner)
        now_p = cs.club_id in all_selected_ids
        c_dict = cs.club.to_dict() if cs.club else {"id": cs.club_id, "short_code": "UNK", "name": "Unknown"}

        if not was_p and now_p:
            promoted_teams.append(c_dict)
        elif was_p and not now_p:
            demoted_teams.append(c_dict)
        elif was_p and now_p:
            retained_teams.append(c_dict)

        cs.is_partner = now_p

    # 3. Cập nhật trạng thái selected và summary trong payload lưu trữ
    for reg_slug, reg_data in regions_data.items():
        sel_set = set(validated_selections[reg_slug])
        reg_data["committed_club_ids"] = validated_selections[reg_slug]
        for c in reg_data.get("clubs", []):
            c["selected"] = c["club_id"] in sel_set

        # Cập nhật lại số lượng theo từng tiểu khu vực sau khi người chơi chốt
        for sub in reg_data.get("subregions", []):
            scode = sub["code"]
            sel_in_sub = [
                c for c in reg_data.get("clubs", [])
                if c["country_code"] == scode and c["club_id"] in sel_set
            ]
            sub["selected_count"] = len(sel_in_sub)
            sub["selected_codes"] = [c["short_code"] for c in sel_in_sub]
            sub["is_full"] = len(sel_in_sub) >= sub["max_cap"]

    eval_payload["status"] = "committed"
    eval_payload["committed_summary"] = {
        "retained_count": len(retained_teams),
        "promoted_count": len(promoted_teams),
        "demoted_count": len(demoted_teams),
        "promoted_teams": promoted_teams,
        "demoted_teams": demoted_teams,
        "retained_teams": retained_teams,
    }

    review_rec = CampaignPartnershipReview.query.filter_by(
        campaign_id=campaign_id, year=eval_year
    ).first()
    now_utc = datetime.now(timezone.utc)
    if not review_rec:
        review_rec = CampaignPartnershipReview(
            campaign_id=campaign_id,
            year=eval_year,
            cycle_label=eval_payload["cycle_label"],
            status="committed",
            evaluation_data=json.dumps(eval_payload),
            committed_at=now_utc,
        )
        db.session.add(review_rec)
    else:
        review_rec.status = "committed"
        review_rec.evaluation_data = json.dumps(eval_payload)
        review_rec.committed_at = now_utc

    db.session.flush()

    # 4. Nếu chiến dịch đang ở giai đoạn 'open_qualifier' của mùa giải mới và chưa đá trận nào,
    # khởi tạo lại danh sách 16 đội Non-Partner của Open Qualifier theo danh sách Partner mới!
    if camp.current_stage == "open_qualifier":
        oq_stage = CampaignStage.query.filter_by(
            campaign_id=campaign_id, year=camp.current_year, stage_key="open_qualifier"
        ).first()
        if oq_stage:
            try:
                oq_data = json.loads(oq_stage.stage_data or "{}")
                any_completed = False
                for r_data in oq_data.get("regions", {}).values():
                    for m in r_data.get("swiss_matches", []):
                        if m.get("status") == "completed":
                            any_completed = True
                            break
                if not any_completed:
                    from services.campaign_service import init_campaign_open_qualifier
                    init_campaign_open_qualifier(campaign_id)
            except Exception:
                pass

    db.session.commit()
    return {
        "success": True,
        "campaign_id": campaign_id,
        "evaluation_year": eval_year,
        "cycle_label": eval_payload["cycle_label"],
        "status": "committed",
        "retained_count": len(retained_teams),
        "promoted_count": len(promoted_teams),
        "demoted_count": len(demoted_teams),
        "promoted_teams": promoted_teams,
        "demoted_teams": demoted_teams,
    }
