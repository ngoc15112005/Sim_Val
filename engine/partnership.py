"""
VALORANT PARTNERSHIP EVALUATION SYSTEM (Version 1.0)
====================================================
Engine đánh giá, chấm điểm 100 điểm (5 trụ cột, 19 chỉ số), kiểm duyệt tư cách (Eligibility Gate),
kiểm tra điểm sàn danh mục (Category Floors), theo dõi tiến độ 8 Quý (24 tháng) và áp dụng
quy tắc giới hạn Quốc gia / Tiểu khu vực (Country / Sub-region Cap <= 2 đội Partner).

Lưu ý: Đây là hệ thống mô phỏng tùy chỉnh lấy cảm hứng từ 5 trụ cột đánh giá của Riot Games,
không phải công thức hay trọng số công bố chính thức của Riot.
"""

from __future__ import annotations
import copy
import hashlib
from typing import Dict, List, Any, Optional, Tuple


# ─────────────────────────────────────────────────────────────────────────────
# 1. DEFAULT CONFIGURATION (SPECIFICATION SECTION 10)
# ─────────────────────────────────────────────────────────────────────────────

DEFAULT_PARTNERSHIP_CONFIG: Dict[str, Any] = {
    "config_version": "1.0.0",
    "program": {
        "cycle_months": 24,
        "evaluation_window_months": 24,
        "max_partners_per_country": 2,
        "regional_capacity": 8,
        "total_score": 100.0,
        "minimum_total_score": 75.0,
    },
    "criteria": {
        "community_growth": {
            "code": "A",
            "name_en": "Community Growth",
            "name_vi": "Phát triển Cộng đồng",
            "weight": 25.0,
            "minimum_score": 12.5,
            "indicators": {
                "grassroots_events": {
                    "code": "A1",
                    "name_vi": "Giải đấu cộng đồng & phong trào (Grassroots)",
                    "weight": 7.0,
                    "floor_value": 10.0,
                    "target_value": 100.0,
                    "direction": "higher_is_better",
                    "unit": "index",
                },
                "new_players": {
                    "code": "A2",
                    "name_vi": "Thu hút người chơi mới (Chuẩn hóa quy mô thị trường)",
                    "weight": 7.0,
                    "floor_value": 15.0,
                    "target_value": 100.0,
                    "direction": "higher_is_better",
                    "unit": "index",
                },
                "development_programs": {
                    "code": "A3",
                    "name_vi": "Đào tạo trẻ, Học viện & Phát triển tài năng",
                    "weight": 6.0,
                    "floor_value": 10.0,
                    "target_value": 100.0,
                    "direction": "higher_is_better",
                    "unit": "index",
                },
                "local_community": {
                    "code": "A4",
                    "name_vi": "Sáng kiến gắn kết cộng đồng bản địa",
                    "weight": 5.0,
                    "floor_value": 15.0,
                    "target_value": 100.0,
                    "direction": "higher_is_better",
                    "unit": "index",
                },
            },
        },
        "fandom_content": {
            "code": "B",
            "name_en": "Fandom & Content",
            "name_vi": "Sức hút Fan & Nội dung",
            "weight": 25.0,
            "minimum_score": 12.5,
            "indicators": {
                "real_fanbase": {
                    "code": "B1",
                    "name_vi": "Quy mô người hâm mộ thực tế (Đã lọc bot)",
                    "weight": 6.0,
                    "floor_value": 15.0,
                    "target_value": 100.0,
                    "direction": "higher_is_better",
                    "unit": "index",
                },
                "engagement": {
                    "code": "B2",
                    "name_vi": "Chất lượng tương tác & Lượt xem trực tiếp",
                    "weight": 7.0,
                    "floor_value": 15.0,
                    "target_value": 100.0,
                    "direction": "higher_is_better",
                    "unit": "index",
                },
                "content_quality": {
                    "code": "B3",
                    "name_vi": "Chất lượng sản xuất & Sáng tạo nội dung (Rubric 0-5)",
                    "weight": 6.0,
                    "floor_value": 0.0,
                    "target_value": 5.0,
                    "direction": "qualitative_rubric",
                    "unit": "rubric_0_5",
                },
                "fan_retention": {
                    "code": "B4",
                    "name_vi": "Tỷ lệ giữ chân & Tương tác lặp lại của khán giả",
                    "weight": 6.0,
                    "floor_value": 20.0,
                    "target_value": 95.0,
                    "direction": "higher_is_better",
                    "unit": "percent",
                },
            },
        },
        "business_sustainability": {
            "code": "C",
            "name_en": "Business Sustainability",
            "name_vi": "Bền vững Tài chính & Kinh doanh",
            "weight": 20.0,
            "minimum_score": 12.0,
            "indicators": {
                "financial_health": {
                    "code": "C1",
                    "name_vi": "Sức khỏe tài chính & Dòng tiền vận hành (Runway)",
                    "weight": 8.0,
                    "floor_value": 20.0,
                    "target_value": 100.0,
                    "direction": "higher_is_better",
                    "unit": "index",
                },
                "salary_compliance": {
                    "code": "C2",
                    "name_vi": "Tuân thủ nghĩa vụ lương thưởng & hợp đồng",
                    "weight": 6.0,
                    "floor_value": 30.0,
                    "target_value": 100.0,
                    "direction": "higher_is_better",
                    "unit": "index",
                },
                "revenue_diversification": {
                    "code": "C3",
                    "name_vi": "Đa dạng hóa doanh thu & Nhà tài trợ thương mại",
                    "weight": 3.0,
                    "floor_value": 15.0,
                    "target_value": 100.0,
                    "direction": "higher_is_better",
                    "unit": "index",
                },
                "governance": {
                    "code": "C4",
                    "name_vi": "Minh bạch quản trị & Kiểm toán (Rubric 0-5)",
                    "weight": 3.0,
                    "floor_value": 0.0,
                    "target_value": 5.0,
                    "direction": "qualitative_rubric",
                    "unit": "rubric_0_5",
                },
            },
        },
        "operational_excellence": {
            "code": "D",
            "name_en": "Operational Excellence",
            "name_vi": "Năng lực Vận hành Tổ chức",
            "weight": 15.0,
            "minimum_score": 9.0,
            "indicators": {
                "staffing": {
                    "code": "D1",
                    "name_vi": "Cấu trúc Ban huấn luyện, Phân tích viên & Quản lý",
                    "weight": 4.0,
                    "floor_value": 20.0,
                    "target_value": 100.0,
                    "direction": "higher_is_better",
                    "unit": "index",
                },
                "infrastructure": {
                    "code": "D2",
                    "name_vi": "Cơ sở vật chất, Gaming House & Sân nhà",
                    "weight": 3.0,
                    "floor_value": 20.0,
                    "target_value": 100.0,
                    "direction": "higher_is_better",
                    "unit": "index",
                },
                "event_operations": {
                    "code": "D3",
                    "name_vi": "Hậu cần, Tác phong sự kiện & Tuân thủ giải đấu",
                    "weight": 3.0,
                    "floor_value": 25.0,
                    "target_value": 100.0,
                    "direction": "higher_is_better",
                    "unit": "index",
                },
                "player_welfare": {
                    "code": "D4",
                    "name_vi": "Phúc lợi tuyển thủ, Y tế & Môi trường làm việc",
                    "weight": 5.0,
                    "floor_value": 25.0,
                    "target_value": 100.0,
                    "direction": "higher_is_better",
                    "unit": "index",
                },
            },
        },
        "competitive_success": {
            "code": "E",
            "name_en": "Competitive Success",
            "name_vi": "Thành tích Thi đấu (24 Tháng)",
            "weight": 15.0,
            "minimum_score": 5.0,
            "indicators": {
                "tournament_results": {
                    "code": "E1",
                    "name_vi": "Kết quả giải đấu chính thức trong 24 tháng",
                    "weight": 8.0,
                    "floor_value": 0.0,
                    "target_value": 100.0,
                    "direction": "higher_is_better",
                    "unit": "points",
                },
                "player_development": {
                    "code": "E2",
                    "name_vi": "Phát triển tuyển thủ & Đột phá lực lượng",
                    "weight": 4.0,
                    "floor_value": 10.0,
                    "target_value": 100.0,
                    "direction": "higher_is_better",
                    "unit": "index",
                },
                "competitive_consistency": {
                    "code": "E3",
                    "name_vi": "Sự ổn định phong độ qua các mùa giải",
                    "weight": 3.0,
                    "floor_value": 10.0,
                    "target_value": 100.0,
                    "direction": "higher_is_better",
                    "unit": "index",
                },
            },
        },
    },
    "score_thresholds": {
        "priority_renewal": 85.0,
        "eligible": 75.0,
        "below_standard": 65.0,
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# 2. COUNTRY & SUB-REGION MAPPING FOR ALL 96 CLUBS (MAX 2 PARTNERS PER GROUP)
# ─────────────────────────────────────────────────────────────────────────────

SUBREGION_METADATA: Dict[str, Dict[str, Any]] = {
    # PACIFIC (8 Quốc gia / Tiểu khu vực)
    "KR": {"code": "KR", "name": "Hàn Quốc (South Korea)", "short_name": "Hàn Quốc", "flag": "🇰🇷", "region": "pacific", "market_norm": 1.05},
    "JP": {"code": "JP", "name": "Nhật Bản (Japan)", "short_name": "Nhật Bản", "flag": "🇯🇵", "region": "pacific", "market_norm": 1.08},
    "SG_MY": {"code": "SG_MY", "name": "Singapore & Malaysia", "short_name": "SG / MY", "flag": "🇸🇬", "region": "pacific", "market_norm": 1.12},
    "ID": {"code": "ID", "name": "Indonesia", "short_name": "Indonesia", "flag": "🇮🇩", "region": "pacific", "market_norm": 1.04},
    "TH": {"code": "TH", "name": "Thái Lan (Thailand)", "short_name": "Thái Lan", "flag": "🇹🇭", "region": "pacific", "market_norm": 1.06},
    "VN": {"code": "VN", "name": "Việt Nam (Vietnam)", "short_name": "Việt Nam", "flag": "🇻🇳", "region": "pacific", "market_norm": 1.06},
    "PH": {"code": "PH", "name": "Philippines", "short_name": "Philippines", "flag": "🇵🇭", "region": "pacific", "market_norm": 1.06},
    "SA": {"code": "SA", "name": "Nam Á / Ấn Độ (South Asia)", "short_name": "Nam Á", "flag": "🇮🇳", "region": "pacific", "market_norm": 1.05},

    # EMEA (7 Quốc gia / Tiểu khu vực)
    "TR": {"code": "TR", "name": "Thổ Nhĩ Kỳ (Turkey)", "short_name": "Thổ Nhĩ Kỳ", "flag": "🇹🇷", "region": "emea", "market_norm": 1.06},
    "FR": {"code": "FR", "name": "Pháp (France)", "short_name": "Pháp", "flag": "🇫🇷", "region": "emea", "market_norm": 1.06},
    "EU_WEST": {"code": "EU_WEST", "name": "Liên Âu / Benelux (Pan-EU)", "short_name": "Liên Âu (Pan-EU)", "flag": "🇪🇺", "region": "emea", "market_norm": 1.05},
    "UK_NORD": {"code": "UK_NORD", "name": "Anh & Bắc Âu (UK & Nordics)", "short_name": "Anh & Bắc Âu", "flag": "🇬🇧", "region": "emea", "market_norm": 1.06},
    "ES": {"code": "ES", "name": "Tây Ban Nha & Iberia (Spain)", "short_name": "Tây Ban Nha", "flag": "🇪🇸", "region": "emea", "market_norm": 1.06},
    "DACH": {"code": "DACH", "name": "Đức / Áo / Thụy Sĩ (DACH)", "short_name": "DACH (Đức)", "flag": "🇩🇪", "region": "emea", "market_norm": 1.06},
    "CIS_MENA": {"code": "CIS_MENA", "name": "Đông Âu & MENA (CIS & MENA)", "short_name": "CIS & MENA", "flag": "🇺🇦", "region": "emea", "market_norm": 1.08},

    # AMERICAS (5 Quốc gia / Tiểu khu vực)
    "BR": {"code": "BR", "name": "Brazil", "short_name": "Brazil", "flag": "🇧🇷", "region": "americas", "market_norm": 1.06},
    "LATAM": {"code": "LATAM", "name": "Nam Mỹ (LATAM - Argentina/Chile)", "short_name": "Nam Mỹ (LATAM)", "flag": "🇦🇷", "region": "americas", "market_norm": 1.08},
    "NA_WEST": {"code": "NA_WEST", "name": "Bắc Mỹ - Bờ Tây (NA West / Cali)", "short_name": "NA - Bờ Tây", "flag": "🇺🇸", "region": "americas", "market_norm": 1.04},
    "NA_EAST": {"code": "NA_EAST", "name": "Bắc Mỹ - Trung & Đông (NA East/Texas)", "short_name": "NA - Trung & Đông", "flag": "🇺🇸", "region": "americas", "market_norm": 1.04},
    "NA_NORTH": {"code": "NA_NORTH", "name": "Bắc Mỹ - Canada & Bắc Lục Địa", "short_name": "Canada & Bắc Mỹ", "flag": "🇨🇦", "region": "americas", "market_norm": 1.08},

    # CHINA (6 Tiểu khu vực Đô thị Sân nhà VCT CN)
    "CN_SH": {"code": "CN_SH", "name": "Hoa Đông - Thượng Hải (Shanghai Hub)", "short_name": "Hoa Đông (Thượng Hải)", "flag": "🏙️", "region": "china", "market_norm": 1.04},
    "CN_BJ": {"code": "CN_BJ", "name": "Hoa Bắc - Bắc Kinh (Beijing Hub)", "short_name": "Hoa Bắc (Bắc Kinh)", "flag": "🏯", "region": "china", "market_norm": 1.05},
    "CN_SZ": {"code": "CN_SZ", "name": "Hoa Nam - Thâm Quyến / Quảng Đông", "short_name": "Hoa Nam (Thâm Quyến)", "flag": "🌊", "region": "china", "market_norm": 1.06},
    "CN_HZ": {"code": "CN_HZ", "name": "Giang Chiết - Hàng Châu / Tô Châu", "short_name": "Giang Chiết (Hàng Châu)", "flag": "🌉", "region": "china", "market_norm": 1.06},
    "CN_CS": {"code": "CN_CS", "name": "Hoa Trung - Trường Sa / Vũ Hán", "short_name": "Hoa Trung (Trường Sa)", "flag": "🔥", "region": "china", "market_norm": 1.07},
    "CN_CD": {"code": "CN_CD", "name": "Tây Nam - Thành Đô / Trùng Khánh", "short_name": "Tây Nam (Thành Đô)", "flag": "🐼", "region": "china", "market_norm": 1.07},
}

# Ánh xạ từng đội trong 96 CLB vào đúng Quốc gia / Tiểu khu vực và chỉ số nền tảng của tổ chức (Org Prestige Tier: 1=Tier-S, 2=Tier-A, 3=Tier-B)
CLUB_COUNTRY_MAP: Dict[str, Dict[str, Any]] = {
    # ── PACIFIC (24) ──
    # Hàn Quốc (KR): 7 đội (Partner gốc: T1, GEN)
    "T1": {"country_code": "KR", "org_tier": 1},
    "GEN": {"country_code": "KR", "org_tier": 1},
    "DRX": {"country_code": "KR", "org_tier": 1},
    "NS": {"country_code": "KR", "org_tier": 2},
    "DK": {"country_code": "KR", "org_tier": 1},
    "SPG": {"country_code": "KR", "org_tier": 3},
    "SLT": {"country_code": "KR", "org_tier": 3},
    # Nhật Bản (JP): 5 đội (Partner gốc: ZETA, CR)
    "ZETA": {"country_code": "JP", "org_tier": 1},
    "CR": {"country_code": "JP", "org_tier": 1},
    "DFM": {"country_code": "JP", "org_tier": 2},
    "FL": {"country_code": "JP", "org_tier": 2},
    "RID": {"country_code": "JP", "org_tier": 2},
    # Singapore & Malaysia (SG_MY): 3 đội (Partner gốc: PRX)
    "PRX": {"country_code": "SG_MY", "org_tier": 1},
    "BLD": {"country_code": "SG_MY", "org_tier": 3},
    "DSG": {"country_code": "SG_MY", "org_tier": 2},
    # Indonesia (ID): 2 đội (Partner gốc: RRQ)
    "RRQ": {"country_code": "ID", "org_tier": 1},
    "BOOM": {"country_code": "ID", "org_tier": 2},
    # Thái Lan (TH): 3 đội (Partner gốc: FS)
    "FS": {"country_code": "TH", "org_tier": 2},
    "TLN": {"country_code": "TH", "org_tier": 1},
    "MITH": {"country_code": "TH", "org_tier": 2},
    # Việt Nam (VN): 2 đội (Partner gốc: GAM)
    "GAM": {"country_code": "VN", "org_tier": 1},
    "FC": {"country_code": "VN", "org_tier": 2},
    # Philippines (PH): 1 đội
    "TS": {"country_code": "PH", "org_tier": 1},
    # Nam Á (SA): 1 đội
    "GE": {"country_code": "SA", "org_tier": 1},

    # ── AMERICAS (24) ──
    # Brazil (BR): 6 đội (Partner gốc: LOUD, MIBR)
    "LOUD": {"country_code": "BR", "org_tier": 1},
    "MIBR": {"country_code": "BR", "org_tier": 1},
    "FUR": {"country_code": "BR", "org_tier": 2},
    "2G": {"country_code": "BR", "org_tier": 2},
    "GLR": {"country_code": "BR", "org_tier": 3},
    "RED": {"country_code": "BR", "org_tier": 2},
    # Nam Mỹ (LATAM): 4 đội (Partner gốc: LEV, KRU)
    "LEV": {"country_code": "LATAM", "org_tier": 1},
    "KRU": {"country_code": "LATAM", "org_tier": 1},
    "9z": {"country_code": "LATAM", "org_tier": 2},
    "AK": {"country_code": "LATAM", "org_tier": 3},
    # Bắc Mỹ - Bờ Tây (NA_WEST): 5 đội (Partner gốc: SEN, 100T)
    "SEN": {"country_code": "NA_WEST", "org_tier": 1},
    "100T": {"country_code": "NA_WEST", "org_tier": 1},
    "C9": {"country_code": "NA_WEST", "org_tier": 1},
    "EG": {"country_code": "NA_WEST", "org_tier": 2},
    "SR": {"country_code": "NA_WEST", "org_tier": 2},
    # Bắc Mỹ - Trung & Đông (NA_EAST): 6 đội (Partner gốc: NRG, G2)
    "NRG": {"country_code": "NA_EAST", "org_tier": 1},
    "G2": {"country_code": "NA_EAST", "org_tier": 1},
    "NV": {"country_code": "NA_EAST", "org_tier": 1},
    "TSM": {"country_code": "NA_EAST", "org_tier": 2},
    "DZ": {"country_code": "NA_EAST", "org_tier": 2},
    "OXG": {"country_code": "NA_EAST", "org_tier": 3},
    # Bắc Mỹ - Canada & Bắc Lục Địa (NA_NORTH): 3 đội
    "MxS": {"country_code": "NA_NORTH", "org_tier": 2},
    "YFP": {"country_code": "NA_NORTH", "org_tier": 3},
    "TT": {"country_code": "NA_NORTH", "org_tier": 3},

    # ── EMEA (24) ──
    # Thổ Nhĩ Kỳ (TR): 4 đội (Partner gốc: FUT, BBL)
    "FUT": {"country_code": "TR", "org_tier": 1},
    "BBL": {"country_code": "TR", "org_tier": 1},
    "EF": {"country_code": "TR", "org_tier": 2},
    "PCF": {"country_code": "TR", "org_tier": 3},
    # Pháp (FR): 4 đội (Partner gốc: KC, M8)
    "KC": {"country_code": "FR", "org_tier": 1},
    "M8": {"country_code": "FR", "org_tier": 1},
    "JL": {"country_code": "FR", "org_tier": 2},
    "MDR": {"country_code": "FR", "org_tier": 2},
    # Liên Âu / Benelux (EU_WEST): 4 đội (Partner gốc: VIT, TL)
    "VIT": {"country_code": "EU_WEST", "org_tier": 1},
    "TL": {"country_code": "EU_WEST", "org_tier": 1},
    "ACE": {"country_code": "EU_WEST", "org_tier": 2},
    "DSY": {"country_code": "EU_WEST", "org_tier": 3},
    # Anh & Bắc Âu (UK_NORD): 3 đội (Partner gốc: FNC)
    "FNC": {"country_code": "UK_NORD", "org_tier": 1},
    "APK": {"country_code": "UK_NORD", "org_tier": 2},
    "GX": {"country_code": "UK_NORD", "org_tier": 2},
    # Tây Ban Nha & Iberia (ES): 4 đội (Partner gốc: TH)
    "TH": {"country_code": "ES", "org_tier": 1},
    "KOI": {"country_code": "ES", "org_tier": 1},
    "CASE": {"country_code": "ES", "org_tier": 2},
    "BAR": {"country_code": "ES", "org_tier": 2},
    # Đức / DACH (DACH): 3 đội
    "MOUZ": {"country_code": "DACH", "org_tier": 1},
    "FKS": {"country_code": "DACH", "org_tier": 2},
    "CGN": {"country_code": "DACH", "org_tier": 3},
    # Đông Âu & MENA (CIS_MENA): 2 đội
    "NAVI": {"country_code": "CIS_MENA", "org_tier": 1},
    "FLC": {"country_code": "CIS_MENA", "org_tier": 1},

    # ── CHINA (24) — 6 Tiểu khu vực Đô thị Sân nhà ──
    # Hoa Đông - Thượng Hải (CN_SH): 6 đội (Partner gốc: EDG, BLG)
    "EDG": {"country_code": "CN_SH", "org_tier": 1},
    "BLG": {"country_code": "CN_SH", "org_tier": 1},
    "FPX": {"country_code": "CN_SH", "org_tier": 1},
    "iG": {"country_code": "CN_SH", "org_tier": 2},
    "TES": {"country_code": "CN_SH", "org_tier": 2},
    "RA": {"country_code": "CN_SH", "org_tier": 3},
    # Hoa Bắc - Bắc Kinh (CN_BJ): 4 đội (Partner gốc: JDG, WBG)
    "JDG": {"country_code": "CN_BJ", "org_tier": 1},
    "WBG": {"country_code": "CN_BJ", "org_tier": 1},
    "RNG": {"country_code": "CN_BJ", "org_tier": 2},
    "NIP": {"country_code": "CN_BJ", "org_tier": 2},
    # Hoa Nam - Thâm Quyến / Quảng Đông (CN_SZ): 4 đội (Partner gốc: XLG)
    "XLG": {"country_code": "CN_SZ", "org_tier": 2},
    "WOL": {"country_code": "CN_SZ", "org_tier": 1},
    "DRG": {"country_code": "CN_SZ", "org_tier": 2},
    "Q9": {"country_code": "CN_SZ", "org_tier": 3},
    # Giang Chiết - Hàng Châu / Tô Châu (CN_HZ): 4 đội (Partner gốc: TYL)
    "TYL": {"country_code": "CN_HZ", "org_tier": 1},
    "LGD": {"country_code": "CN_HZ", "org_tier": 2},
    "NOVA": {"country_code": "CN_HZ", "org_tier": 2},
    "KBG": {"country_code": "CN_HZ", "org_tier": 3},
    # Hoa Trung - Trường Sa / Vũ Hán (CN_CS): 3 đội (Partner gốc: TE)
    "TE": {"country_code": "CN_CS", "org_tier": 1},
    "TEC": {"country_code": "CN_CS", "org_tier": 2},
    "ASE": {"country_code": "CN_CS", "org_tier": 3},
    # Tây Nam - Thành Đô / Trùng Khánh (CN_CD): 3 đội (Partner gốc: AG)
    "AG": {"country_code": "CN_CD", "org_tier": 1},
    "4AM": {"country_code": "CN_CD", "org_tier": 2},
    "CCG": {"country_code": "CN_CD", "org_tier": 3},
}


def get_club_country_info(short_code: str, region_slug: str = "pacific") -> Dict[str, Any]:
    """Lấy thông tin Quốc gia / Tiểu khu vực của một CLB theo mã viết tắt."""
    entry = CLUB_COUNTRY_MAP.get(short_code)
    if entry:
        c_code = entry["country_code"]
        meta = SUBREGION_METADATA.get(c_code, {})
        return {
            "country_code": c_code,
            "country_name": meta.get("name", c_code),
            "short_name": meta.get("short_name", c_code),
            "flag": meta.get("flag", "🏳️"),
            "org_tier": entry.get("org_tier", 2),
            "market_norm": meta.get("market_norm", 1.0),
        }
    # Fallback nếu phát sinh CLB mới
    fallback_by_region = {
        "pacific": "SG_MY",
        "americas": "NA_NORTH",
        "emea": "EU_WEST",
        "china": "CN_CD",
    }
    c_code = fallback_by_region.get(region_slug, "SG_MY")
    meta = SUBREGION_METADATA[c_code]
    return {
        "country_code": c_code,
        "country_name": meta["name"],
        "short_name": meta["short_name"],
        "flag": meta["flag"],
        "org_tier": 2,
        "market_norm": meta["market_norm"],
    }


def get_region_subregions(region_slug: str) -> List[Dict[str, Any]]:
    """Trả về danh sách các Quốc gia / Tiểu khu vực thuộc một khu vực lớn."""
    return [
        dict(meta)
        for meta in SUBREGION_METADATA.values()
        if meta.get("region") == region_slug
    ]


# ─────────────────────────────────────────────────────────────────────────────
# 3. CONFIGURATION VALIDATION & NORMALIZATION FORMULAS (SECTIONS 4 & 11)
# ─────────────────────────────────────────────────────────────────────────────

def validate_partnership_config(config: Optional[Dict[str, Any]]) -> Tuple[bool, List[str]]:
    """Kiểm tra tính hợp lệ của cấu hình trọng số, điểm sàn và hướng chuẩn hóa (Section 11)."""
    errors: List[str] = []
    if not config or not isinstance(config, dict):
        return False, ["Configuration is missing or not a valid dictionary."]

    prog = config.get("program")
    criteria = config.get("criteria")
    if not prog or not criteria:
        return False, ["Missing 'program' or 'criteria' section in configuration."]

    expected_total = float(prog.get("total_score", 100.0))
    cat_weight_sum = 0.0

    for cat_key, cat_data in criteria.items():
        w = float(cat_data.get("weight", 0.0))
        floor = float(cat_data.get("minimum_score", 0.0))
        cat_weight_sum += w

        if floor > w or floor < 0:
            errors.append(f"Category '{cat_key}' minimum_score ({floor}) must be between 0 and weight ({w}).")

        indicators = cat_data.get("indicators", {})
        if not indicators:
            errors.append(f"Category '{cat_key}' has no indicators.")
            continue

        ind_weight_sum = 0.0
        for ind_key, ind_val in indicators.items():
            if isinstance(ind_val, (int, float)):
                ind_w = float(ind_val)
                ind_weight_sum += ind_w
            elif isinstance(ind_val, dict):
                ind_w = float(ind_val.get("weight", 0.0))
                ind_weight_sum += ind_w
                direction = ind_val.get("direction", "higher_is_better")
                f_val = float(ind_val.get("floor_value", 0.0))
                t_val = float(ind_val.get("target_value", 100.0))
                if direction in ("higher_is_better", "qualitative_rubric"):
                    if t_val <= f_val:
                        errors.append(
                            f"Indicator '{cat_key}.{ind_key}' has target_value ({t_val}) <= floor_value ({f_val}) for {direction}."
                        )
                elif direction == "lower_is_better":
                    if t_val >= f_val:
                        errors.append(
                            f"Indicator '{cat_key}.{ind_key}' has target_value ({t_val}) >= floor_value ({f_val}) for lower_is_better."
                        )
                else:
                    errors.append(f"Indicator '{cat_key}.{ind_key}' has invalid direction '{direction}'.")

        if abs(ind_weight_sum - w) > 1e-4:
            errors.append(
                f"Category '{cat_key}' indicator weights sum to {ind_weight_sum}, expected {w}."
            )

    if abs(cat_weight_sum - expected_total) > 1e-4:
        errors.append(f"Category weights sum to {cat_weight_sum}, expected {expected_total}.")

    if int(prog.get("max_partners_per_country", 2)) < 1:
        errors.append("max_partners_per_country must be >= 1.")
    if int(prog.get("regional_capacity", 8)) < 1:
        errors.append("regional_capacity must be >= 1.")

    return (len(errors) == 0), errors


def clamp(val: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, val))


def normalize_higher_is_better(actual_value: float, floor_value: float, target_value: float) -> float:
    """Chuẩn hóa cho chỉ số càng cao càng tốt: clamp((actual - floor) / (target - floor), 0, 1)."""
    if target_value <= floor_value:
        raise ValueError(f"Invalid configuration: target_value ({target_value}) <= floor_value ({floor_value})")
    return clamp((actual_value - floor_value) / (target_value - floor_value), 0.0, 1.0)


def normalize_lower_is_better(actual_value: float, floor_value: float, target_value: float) -> float:
    """Chuẩn hóa ngược cho chỉ số càng thấp càng tốt: clamp((floor - actual) / (floor - target), 0, 1) khi target < floor."""
    if target_value >= floor_value:
        raise ValueError(f"Invalid inverse configuration: target_value ({target_value}) >= floor_value ({floor_value})")
    return clamp((floor_value - actual_value) / (floor_value - target_value), 0.0, 1.0)


def score_qualitative_rubric(rubric_score: float, max_points: float) -> float:
    """Chấm điểm theo thang Rubric 0..5: score = max_points * clamp(rubric_score, 0, 5) / 5."""
    r = clamp(float(rubric_score), 0.0, 5.0)
    return round(max_points * (r / 5.0), 2)


# ─────────────────────────────────────────────────────────────────────────────
# 4. DETERMINISTIC HASH HELPER FOR REPRODUCIBLE ORGANIZATIONAL BASELINES
# ─────────────────────────────────────────────────────────────────────────────

def _det_offset(seed_str: str, low: float, high: float) -> float:
    """Sinh số thực tất định (reproducible) trong khoảng [low, high] từ chuỗi định danh."""
    digest = hashlib.sha256(seed_str.encode("utf-8")).hexdigest()
    ratio = int(digest[:8], 16) / 0xFFFFFFFF
    return low + ratio * (high - low)


# ─────────────────────────────────────────────────────────────────────────────
# 5. SINGLE CLUB 24-MONTH PARTNERSHIP EVALUATION ENGINE
# ─────────────────────────────────────────────────────────────────────────────

def evaluate_club_partnership(
    club_dict: Dict[str, Any],
    club_state_dict: Dict[str, Any],
    placements_24m: List[Dict[str, Any]],
    storylines_24m: List[Dict[str, Any]],
    evaluation_year: int,
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Tính toán toàn diện điểm Partnership 100 điểm (5 trụ cột, 19 chỉ số, Eligibility Gate, 8 Quý)
    của 1 đội tuyển dựa trên dữ liệu xác thực trong chu kỳ 24 tháng (evaluation_year - 1 và evaluation_year).
    """
    cfg = config or DEFAULT_PARTNERSHIP_CONFIG
    is_valid, cfg_errors = validate_partnership_config(cfg)
    if not is_valid:
        raise ValueError(f"Invalid partnership configuration: {'; '.join(cfg_errors)}")

    club_id = club_dict.get("id") or club_state_dict.get("club_id")
    short_code = club_dict.get("short_code", "UNK")
    club_name = club_dict.get("name", short_code)
    region_slug = club_dict.get("region_slug") or club_dict.get("region") or "pacific"
    base_rating = float(club_dict.get("base_rating") or 80)

    story_rating = float(club_state_dict.get("story_rating") or base_rating)
    power_score = float(club_state_dict.get("power_score") or 1500.0)
    is_incumbent_partner = bool(club_state_dict.get("is_partner", False))

    country_info = get_club_country_info(short_code, region_slug)
    org_tier = country_info["org_tier"]  # 1 (Tier-S), 2 (Tier-A), 3 (Tier-B)
    market_norm = country_info["market_norm"]

    # ── Phân tích dữ liệu giải đấu thực tế trong 24 tháng (placements_24m) ──
    intl_stages = {"major", "master", "ewc", "champion"}
    main_regional_stages = {"kickoff", "stage1", "stage2"}
    oq_stages = {"open_qualifier", "oq_stage1", "oq_stage2", "ewc_qualifier"}

    total_matches_won = 0
    total_matches_lost = 0
    total_cp_earned = 0
    intl_appearances = 0
    intl_titles = 0
    intl_podiums = 0
    regional_titles = 0
    regional_podiums = 0
    main_stage_appearances = 0
    tournament_points_raw = 0.0

    # Phân bổ theo năm (Year 1 = evaluation_year - 1, Year 2 = evaluation_year)
    y1_points = 0.0
    y2_points = 0.0

    for p in placements_24m:
        s_key = p.get("stage_key", "")
        rank = int(p.get("rank") or 99)
        p_year = int(p.get("year") or evaluation_year)
        m_won = int(p.get("matches_won") or 0)
        m_lost = int(p.get("matches_lost") or 0)
        cp_val = int(p.get("stage_points_earned") or 0)

        total_matches_won += m_won
        total_matches_lost += m_lost
        total_cp_earned += cp_val

        # Trọng số giải đấu theo cấp độ (Section 5 - E1)
        stage_pts = 0.0
        if s_key in intl_stages:
            intl_appearances += 1
            main_stage_appearances += 1
            tier_mult = 1.4 if s_key == "champion" else (1.2 if s_key in ("master", "ewc") else 1.0)
            if rank == 1:
                intl_titles += 1
                intl_podiums += 1
                stage_pts = 28.0 * tier_mult
            elif rank == 2:
                intl_podiums += 1
                stage_pts = 20.0 * tier_mult
            elif rank in (3, 4):
                intl_podiums += 1
                stage_pts = 14.0 * tier_mult
            elif rank <= 8:
                stage_pts = 9.0 * tier_mult
            else:
                stage_pts = 5.0 * tier_mult
        elif s_key in main_regional_stages:
            main_stage_appearances += 1
            if rank == 1:
                regional_titles += 1
                regional_podiums += 1
                stage_pts = 16.0
            elif rank == 2:
                regional_podiums += 1
                stage_pts = 12.0
            elif rank == 3:
                regional_podiums += 1
                stage_pts = 9.0
            elif rank == 4:
                stage_pts = 7.0
            elif rank <= 6:
                stage_pts = 5.0
            elif rank <= 8:
                stage_pts = 3.5
            else:
                stage_pts = 1.5
        elif s_key in oq_stages:
            if rank <= 4:
                stage_pts = 4.0
            elif rank <= 8:
                stage_pts = 2.0
            else:
                stage_pts = 0.5

        # Recency weight: năm gần nhất (evaluation_year) x1.1, năm trước x0.9
        if p_year >= evaluation_year:
            y2_points += stage_pts
            tournament_points_raw += stage_pts * 1.1
        else:
            y1_points += stage_pts
            tournament_points_raw += stage_pts * 0.9

    total_matches = total_matches_won + total_matches_lost
    win_rate = (total_matches_won / total_matches) if total_matches > 0 else 0.45

    # ── Phân tích tác động từ Kịch bản Cốt truyện (Storylines) trong 24 tháng ──
    fin_story_mod = 0.0
    fan_story_mod = 0.0
    dev_story_mod = 0.0
    ops_story_mod = 0.0
    compliance_breach_flag = False
    storyline_notes: List[str] = []

    for st in storylines_24m:
        sc_key = st.get("scenario_key", "")
        st_title = st.get("title") or sc_key
        imp = int(st.get("impact_value") or 0)
        storyline_notes.append(f"[{st.get('year', evaluation_year)}] {st_title} ({imp:+d})")

        if sc_key in ("mega_sponsor", "superteam_formed", "home_crowd_buff"):
            fin_story_mod += 14.0
            fan_story_mod += 10.0
            ops_story_mod += 6.0
        elif sc_key in ("rookie_prodigy", "ascension_miracle", "underdog_awakening"):
            dev_story_mod += 18.0
            fan_story_mod += 8.0
        elif sc_key in ("mastermind_coach", "meta_innovator", "bootcamp_enlightenment"):
            ops_story_mod += 14.0
            dev_story_mod += 8.0
        elif sc_key in ("financial_crisis", "org_turmoil"):
            fin_story_mod -= 26.0
            ops_story_mod -= 12.0
        elif sc_key in ("internal_drama", "star_burnout", "igl_departure", "brain_drain"):
            ops_story_mod -= 10.0
            fan_story_mod -= 5.0
        elif imp > 0:
            fan_story_mod += 5.0
            ops_story_mod += 4.0
        elif imp < 0:
            ops_story_mod -= 6.0

    # ── Nền tảng Tổ chức (Org Baseline) theo Tier + Uy tín câu lạc bộ ──
    # Tier 1 (T1, SEN, FNC, LOUD, EDG, PRX, ZETA, GEN, DRX, KC, G2, VIT, TL...): Nền tảng cộng đồng/fan/vận hành rất mạnh
    tier_base_map = {1: 76.0, 2: 65.0, 3: 55.0}
    org_base = tier_base_map.get(org_tier, 64.0)
    if is_incumbent_partner:
        org_base += 5.5  # Đội Partner đương nhiệm có sẵn hệ thống vận hành & kênh fan VCT

    # Hiệu ứng phong độ và sức mạnh câu lạc bộ lên sức hút truyền thông & tài trợ
    perf_momentum = clamp((power_score - 1380.0) / 320.0, 0.0, 1.0) * 18.0
    intl_clout = min(20.0, intl_appearances * 4.5 + intl_titles * 7.0 + regional_titles * 3.5)

    # ── TÍNH ĐIỂM CHI TIẾT 19 CHỈ SỐ (A1..E3) ──
    seed_prefix = f"{short_code}_{evaluation_year}"

    # 1. Pillar A: Community Growth (25 pts)
    a1_actual = clamp(
        org_base + _det_offset(f"{seed_prefix}_A1", -5.0, 9.0) + (regional_podiums * 3.0) + (fan_story_mod * 0.3),
        15.0, 100.0
    )
    a2_actual = clamp(
        (org_base * 0.92 + perf_momentum * 0.7 + _det_offset(f"{seed_prefix}_A2", -4.0, 8.0)) * market_norm,
        18.0, 100.0
    )
    a3_actual = clamp(
        org_base * 0.90 + dev_story_mod + max(0.0, (story_rating - base_rating) * 2.2) + _det_offset(f"{seed_prefix}_A3", -4.0, 10.0),
        15.0, 100.0
    )
    a4_actual = clamp(
        (org_base + _det_offset(f"{seed_prefix}_A4", -4.0, 9.0) + (4.0 if region_slug == "china" else 2.0)) * (market_norm * 0.97),
        20.0, 100.0
    )

    # 2. Pillar B: Fandom & Content (25 pts)
    b1_actual = clamp(
        (org_base * 0.95 + intl_clout * 0.85 + fan_story_mod + _det_offset(f"{seed_prefix}_B1", -3.0, 8.0)) * market_norm,
        20.0, 100.0
    )
    b2_actual = clamp(
        org_base * 0.88 + perf_momentum * 0.85 + intl_clout * 0.9 + fan_story_mod * 0.6 + _det_offset(f"{seed_prefix}_B2", -4.0, 8.0),
        20.0, 100.0
    )
    # B3 là Qualitative Rubric (0..5)
    b3_raw_100 = clamp(
        org_base * 0.92 + intl_clout * 0.5 + fan_story_mod * 0.5 + _det_offset(f"{seed_prefix}_B3", -4.0, 8.0),
        25.0, 98.0
    )
    b3_rubric = round(clamp(b3_raw_100 / 20.0, 1.5, 5.0), 2)
    b4_actual = clamp(
        52.0 + (org_base - 55.0) * 0.7 + (win_rate * 22.0) + _det_offset(f"{seed_prefix}_B4", -3.0, 6.0),
        30.0, 95.0
    )

    # 3. Pillar C: Business Sustainability (20 pts)
    c1_actual = clamp(
        org_base * 0.96 + fin_story_mod + (intl_clout * 0.45) + _det_offset(f"{seed_prefix}_C1", -5.0, 8.0),
        18.0, 100.0
    )
    c2_actual = clamp(
        82.0 + (8.0 if org_tier == 1 else (3.0 if org_tier == 2 else -2.0)) + (fin_story_mod * 0.55) + _det_offset(f"{seed_prefix}_C2", -4.0, 6.0),
        25.0, 100.0
    )
    c3_actual = clamp(
        org_base * 0.90 + (intl_clout * 0.6) + (fin_story_mod * 0.7) + _det_offset(f"{seed_prefix}_C3", -5.0, 9.0),
        20.0, 100.0
    )
    # C4 là Qualitative Rubric (0..5)
    c4_raw_100 = clamp(
        74.0 + (10.0 if org_tier == 1 else 2.0) + (fin_story_mod * 0.4) + _det_offset(f"{seed_prefix}_C4", -5.0, 7.0),
        30.0, 98.0
    )
    c4_rubric = round(clamp(c4_raw_100 / 20.0, 1.5, 5.0), 2)

    # 4. Pillar D: Operational Excellence (15 pts)
    d1_actual = clamp(
        org_base * 0.90 + ops_story_mod + (story_rating - 72.0) * 0.8 + _det_offset(f"{seed_prefix}_D1", -4.0, 7.0),
        25.0, 100.0
    )
    # Đặc thù VCT China: chú trọng cơ sở vật chất Sân nhà (Home Venue Infrastructure)
    cn_infra_bonus = 6.0 if (region_slug == "china" and org_tier in (1, 2)) else 0.0
    d2_actual = clamp(
        org_base * 0.94 + cn_infra_bonus + (fin_story_mod * 0.35) + _det_offset(f"{seed_prefix}_D2", -4.0, 8.0),
        25.0, 100.0
    )
    d3_actual = clamp(
        75.0 + (main_stage_appearances * 2.2) + (ops_story_mod * 0.4) + _det_offset(f"{seed_prefix}_D3", -4.0, 6.0),
        30.0, 100.0
    )
    d4_actual = clamp(
        74.0 + (8.0 if org_tier == 1 else 2.0) + (ops_story_mod * 0.6) + (fin_story_mod * 0.3) + _det_offset(f"{seed_prefix}_D4", -4.0, 7.0),
        28.0, 100.0
    )

    # 5. Pillar E: Competitive Success (15 pts) — Bám sát thành tích thực tế 24 tháng
    # Nếu là mùa đầu hoặc ít dữ liệu, kết hợp với power_score và story_rating thực tế
    fallback_comp = clamp((story_rating - 65.0) * 2.4 + (power_score - 1420.0) * 0.12, 12.0, 92.0)
    if len(placements_24m) > 0:
        e1_from_placements = clamp(
            tournament_points_raw * 1.35 + (total_cp_earned * 2.2) + (win_rate * 22.0),
            8.0, 100.0
        )
        e1_actual = round(0.78 * e1_from_placements + 0.22 * fallback_comp, 2)
    else:
        e1_actual = round(fallback_comp, 2)

    rating_delta = story_rating - base_rating
    non_partner_breakthrough = 14.0 if (not is_incumbent_partner and main_stage_appearances >= 2) else 0.0
    e2_actual = clamp(
        52.0 + (rating_delta * 3.2) + dev_story_mod + non_partner_breakthrough + (win_rate * 18.0) + _det_offset(f"{seed_prefix}_E2", -3.0, 6.0),
        15.0, 100.0
    )
    e3_actual = clamp(
        30.0 + (main_stage_appearances * 7.5) + (win_rate * 35.0) + (intl_appearances * 5.0),
        15.0, 100.0
    )

    actual_Lookup = {
        "grassroots_events": (a1_actual, "Verified Event Registry & Community Logs"),
        "new_players": (a2_actual, "Riot Telemetry Attribution (Market-Normalized)"),
        "development_programs": (a3_actual, "Academy & Youth Pathway Audit"),
        "local_community": (a4_actual, "Regional Community Partnership Reports"),
        "real_fanbase": (b1_actual, "Deduplicated Active Fanbase Telemetry"),
        "engagement": (b2_actual, "Co-stream & Official Broadcast Watch-Time Analytics"),
        "content_quality": (b3_rubric, "Dual-Reviewer Media Rubric Assessment (0-5)"),
        "fan_retention": (b4_actual, "8-Quarter Cohort Return Analytics"),
        "financial_health": (c1_actual, "Audited Financial Runway & Solvency Statements"),
        "salary_compliance": (c2_actual, "League Payroll & Contract Fulfillment Audit"),
        "revenue_diversification": (c3_actual, "Commercial Sponsorship Portfolio Review"),
        "governance": (c4_rubric, "Corporate Governance & Ownership Audit (0-5)"),
        "staffing": (d1_actual, "Coaching & Performance Staff Registry"),
        "infrastructure": (d2_actual, "Training Facility & Arena Standards Inspection"),
        "event_operations": (d3_actual, "Tournament Logistics & League Ops Report"),
        "player_welfare": (d4_actual, "Player Association Welfare & Safety Audit"),
        "tournament_results": (e1_actual, f"Official VCT Placements ({len(placements_24m)} stages, {total_cp_earned} CP)"),
        "player_development": (e2_actual, f"Roster Progression & Rating Delta ({rating_delta:+.0f} OVR)"),
        "competitive_consistency": (e3_actual, f"24M Win Rate ({win_rate * 100:.1f}%) & {main_stage_appearances} Main Stages"),
    }

    # ── Chấm điểm từng Category và Indicator ──
    categories_result: Dict[str, Any] = {}
    total_score = 0.0
    passed_all_floors = True
    failed_floors_list: List[str] = []

    for cat_key, cat_cfg in cfg["criteria"].items():
        cat_weight = float(cat_cfg["weight"])
        cat_floor = float(cat_cfg["minimum_score"])
        cat_score = 0.0
        indicators_result: Dict[str, Any] = {}

        for ind_key, ind_cfg in cat_cfg["indicators"].items():
            max_pts = float(ind_cfg["weight"])
            f_val = float(ind_cfg["floor_value"])
            t_val = float(ind_cfg["target_value"])
            direction = ind_cfg.get("direction", "higher_is_better")
            actual_val, data_src = actual_Lookup[ind_key]

            if direction == "qualitative_rubric":
                ind_score = score_qualitative_rubric(actual_val, max_pts)
                norm_val = clamp(actual_val / 5.0, 0.0, 1.0)
            elif direction == "lower_is_better":
                norm_val = normalize_lower_is_better(actual_val, f_val, t_val)
                ind_score = round(max_pts * norm_val, 2)
            else:
                norm_val = normalize_higher_is_better(actual_val, f_val, t_val)
                ind_score = round(max_pts * norm_val, 2)

            cat_score += ind_score
            indicators_result[ind_key] = {
                "code": ind_cfg["code"],
                "key": ind_key,
                "name_vi": ind_cfg["name_vi"],
                "max_points": max_pts,
                "floor_value": f_val,
                "target_value": t_val,
                "actual_value": round(actual_val, 2),
                "normalized": round(norm_val, 4),
                "score": round(ind_score, 2),
                "direction": direction,
                "unit": ind_cfg.get("unit", "index"),
                "data_source": data_src,
                "confidence": "verified",
                "evaluation_period": f"{evaluation_year - 1}-{evaluation_year}",
                "config_version": cfg.get("config_version", "1.0.0"),
            }

        cat_score = round(min(cat_weight, cat_score), 2)
        passed_floor = cat_score >= cat_floor
        if not passed_floor:
            passed_all_floors = False
            failed_floors_list.append(f"{cat_cfg['code']}. {cat_cfg['name_vi']} ({cat_score:.2f}/{cat_floor:.1f})")

        total_score += cat_score
        categories_result[cat_key] = {
            "key": cat_key,
            "code": cat_cfg["code"],
            "name_en": cat_cfg["name_en"],
            "name_vi": cat_cfg["name_vi"],
            "weight": cat_weight,
            "minimum_score": cat_floor,
            "score": cat_score,
            "passed_floor": passed_floor,
            "indicators": indicators_result,
        }

    total_score = round(total_score, 2)

    # ── 3. Eligibility Gate (Section 3: Pass/Fail Before Scoring) ──
    gate_checks = [
        {"key": "legal_identity", "label": "Tư cách pháp nhân & Định danh tổ chức hợp lệ", "passed": True},
        {"key": "ownership_disclosure", "label": "Minh bạch cấu trúc sở hữu tối hậu ( Không công ty vỏ bọc )", "passed": True},
        {"key": "financial_capacity", "label": "Chứng minh năng lực tài chính duy trì vận hành", "passed": c1_actual >= 22.0},
        {"key": "contract_compliance", "label": "Hợp đồng tuyển thủ hợp lệ & Thực hiện đầy đủ nghĩa vụ lương thưởng", "passed": not compliance_breach_flag and c2_actual >= 35.0},
        {"key": "competitive_integrity", "label": "Không vi phạm dàn xếp tỉ số, gian lận hoặc đạo đức nghiêm trọng", "passed": True},
        {"key": "accurate_reporting", "label": "Báo cáo trung thực (Không mua bot follower / khai khống tài chính)", "passed": True},
    ]
    gate_passed = all(ch["passed"] for ch in gate_checks)

    # ── 6. Score Band (Section 6) ──
    thresholds = cfg["score_thresholds"]
    if total_score >= thresholds["priority_renewal"]:
        score_band = "priority_renewal"
        score_band_label = "Ứng viên Ưu tiên (85-100)"
        score_band_color = "gold"
    elif total_score >= thresholds["eligible"]:
        score_band = "eligible"
        score_band_label = "Đủ chuẩn Partner (75-84.99)"
        score_band_color = "green"
    elif total_score >= thresholds["below_standard"]:
        score_band = "below_standard"
        score_band_label = "Dưới chuẩn (65-74.99)"
        score_band_color = "amber"
    else:
        score_band = "not_eligible"
        score_band_label = "Không đủ điều kiện (<65)"
        score_band_color = "red"

    # ── 9. Quarterly Dashboard (8 Quý trong chu kỳ 24 tháng: Q1..Q8) ──
    quarterly_trend: List[Dict[str, Any]] = []
    for q_idx in range(1, 9):
        q_year = (evaluation_year - 1) if q_idx <= 4 else evaluation_year
        q_num = q_idx if q_idx <= 4 else (q_idx - 4)
        q_label = f"{q_year}-Q{q_num}"
        # Dao động nhẹ theo tiến trình năm 1 -> năm 2, hội tụ về total_score ở Q8
        if q_idx == 8:
            q_score = total_score
        else:
            year_bias = -1.2 if (q_idx <= 4 and y2_points > y1_points) else (0.8 if (q_idx <= 4 and y1_points > y2_points) else 0.0)
            wave = _det_offset(f"{seed_prefix}_Q{q_idx}", -2.4, 2.4) + year_bias * ((8 - q_idx) / 7.0)
            q_score = round(clamp(total_score + wave, 35.0, 99.5), 2)
        quarterly_trend.append({
            "quarter_index": q_idx,
            "label": q_label,
            "total_score": q_score,
            "audit_status": "verified",
        })

    return {
        "club_id": club_id,
        "short_code": short_code,
        "name": club_name,
        "logo_url": club_dict.get("logo_url", ""),
        "region_slug": region_slug,
        "country_code": country_info["country_code"],
        "country_name": country_info["country_name"],
        "country_short_name": country_info["short_name"],
        "country_flag": country_info["flag"],
        "org_tier": org_tier,
        "was_partner": is_incumbent_partner,
        "story_rating": int(story_rating),
        "power_score": round(power_score, 1),
        "total_score": total_score,
        "score_band": score_band,
        "score_band_label": score_band_label,
        "score_band_color": score_band_color,
        "eligibility_gate": {
            "passed": gate_passed,
            "checks": gate_checks,
        },
        "passed_all_floors": passed_all_floors,
        "failed_floors": failed_floors_list,
        "fully_qualified": gate_passed and passed_all_floors and (total_score >= float(cfg["program"]["minimum_total_score"])),
        "categories": categories_result,
        "quarterly_trend": quarterly_trend,
        "stats_24m": {
            "tournaments_played": len(placements_24m),
            "main_stage_appearances": main_stage_appearances,
            "intl_appearances": intl_appearances,
            "intl_titles": intl_titles,
            "regional_titles": regional_titles,
            "total_cp": total_cp_earned,
            "matches_won": total_matches_won,
            "matches_lost": total_matches_lost,
            "win_rate": round(win_rate * 100, 1),
            "storyline_notes": storyline_notes,
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# 6. REGION RANKING & COUNTRY CAP SELECTION (SECTION 7 - 10-STEP PROCESS)
# ─────────────────────────────────────────────────────────────────────────────

def evaluate_region_partnership(
    region_slug: str,
    evaluated_clubs: List[Dict[str, Any]],
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Thực thi quy trình 10 bước lựa chọn Đội Partner cho 1 khu vực (24 đội -> chọn 8 đội):
    1. Chạy Eligibility Gate
    2. Kiểm tra Điểm sàn 5 danh mục & ngưỡng điểm
    3. Xếp hạng trong khu vực
    4. Áp dụng quy tắc tối đa 2 đội Partner / Quốc gia hoặc Tiểu khu vực (max_partners_per_country = 2)
    5. Đánh dấu đội Giữ vé (Retained), Thăng hạng (Promoted), Rớt hạng (Demoted), Bị chặn bởi Country Cap (Cap Blocked).
    """
    cfg = config or DEFAULT_PARTNERSHIP_CONFIG
    max_per_country = int(cfg["program"].get("max_partners_per_country", 2))
    capacity = int(cfg["program"].get("regional_capacity", 8))
    min_total = float(cfg["program"].get("minimum_total_score", 75.0))

    # Sắp xếp:
    # Ưu tiên 1: Vượt qua Eligibility Gate (True > False)
    # Ưu tiên 2: Vượt qua tất cả Category Floors (True > False)
    # Ưu tiên 3: Tổng điểm 100 (total_score giảm dần)
    # Ưu tiên 4: Điểm Competitive Success (E) giảm dần -> Power Score giảm dần
    sorted_clubs = sorted(
        copy.deepcopy(evaluated_clubs),
        key=lambda c: (
            1 if c["eligibility_gate"]["passed"] else 0,
            1 if c["passed_all_floors"] else 0,
            c["total_score"],
            c["categories"]["competitive_success"]["score"],
            c["power_score"],
        ),
        reverse=True,
    )

    country_counts: Dict[str, int] = {}
    recommended_ids: List[int] = []
    cap_blocked_ids: List[int] = []

    # Lượt 1: Chọn các đội đạt chuẩn đầy đủ (Gate Passed + All Floors Passed + Score >= 75) theo thứ tự điểm, tôn trọng Country Cap <= 2
    for idx, club in enumerate(sorted_clubs, start=1):
        club["region_rank"] = idx
        c_code = club["country_code"]
        cur_c = country_counts.get(c_code, 0)

        if len(recommended_ids) < capacity:
            if club["eligibility_gate"]["passed"] and club["passed_all_floors"] and club["total_score"] >= min_total:
                if cur_c < max_per_country:
                    recommended_ids.append(club["club_id"])
                    country_counts[c_code] = cur_c + 1
                else:
                    cap_blocked_ids.append(club["club_id"])

    # Lượt 2: Nếu khu vực chưa đủ 8 đội đạt ngưỡng >= 75 sau khi lọc Country Cap,
    # lấy tiếp các đội có Gate Passed và điểm tổng cao nhất kế tiếp mà vẫn TUYỆT ĐỐI tôn trọng Country Cap <= 2
    if len(recommended_ids) < capacity:
        for club in sorted_clubs:
            if len(recommended_ids) >= capacity:
                break
            cid = club["club_id"]
            if cid in recommended_ids:
                continue
            c_code = club["country_code"]
            cur_c = country_counts.get(c_code, 0)
            if club["eligibility_gate"]["passed"]:
                if cur_c < max_per_country:
                    recommended_ids.append(cid)
                    country_counts[c_code] = cur_c + 1
                    club["selected_via_capacity_fill"] = True
                else:
                    if cid not in cap_blocked_ids:
                        cap_blocked_ids.append(cid)

    # Gán nhãn trạng thái đề xuất cho từng đội
    recommended_set = set(recommended_ids)
    cap_blocked_set = set(cap_blocked_ids)

    retained_count = 0
    promoted_count = 0
    demoted_count = 0

    for club in sorted_clubs:
        cid = club["club_id"]
        was_p = club["was_partner"]
        is_rec = cid in recommended_set
        club["ai_recommended"] = is_rec
        club["selected"] = is_rec  # Trạng thái mặc định trên UI trước khi người chơi chỉnh sửa

        if is_rec:
            if was_p:
                club["recommendation_status"] = "retained"
                club["recommendation_label"] = "🟢 Đề xuất Giữ vé"
                retained_count += 1
            else:
                club["recommendation_status"] = "promoted"
                club["recommendation_label"] = "🚀 Đề xuất Thăng hạng"
                promoted_count += 1
        else:
            if cid in cap_blocked_set:
                club["recommendation_status"] = "cap_blocked"
                club["recommendation_label"] = f"⛔ Chặn Country Cap ({club['country_short_name']} 2/2)"
                if was_p:
                    demoted_count += 1
            elif not club["eligibility_gate"]["passed"]:
                club["recommendation_status"] = "gate_failed"
                club["recommendation_label"] = "🚫 Vi phạm Cổng Kiểm duyệt"
                if was_p:
                    demoted_count += 1
            elif not club["passed_all_floors"]:
                club["recommendation_status"] = "floor_failed"
                club["recommendation_label"] = "⚠️ Rớt Điểm sàn Danh mục"
                if was_p:
                    demoted_count += 1
            elif was_p:
                club["recommendation_status"] = "demoted"
                club["recommendation_label"] = "🔻 Đề xuất Thu hồi vé"
                demoted_count += 1
            else:
                club["recommendation_status"] = "challenger"
                club["recommendation_label"] = "⚪ Hạng Challenger"

    # Tổng hợp bộ đếm theo từng Quốc gia / Tiểu khu vực trong khu vực này
    subregions_summary = []
    for sub in get_region_subregions(region_slug):
        scode = sub["code"]
        teams_in_sub = [c for c in sorted_clubs if c["country_code"] == scode]
        selected_in_sub = [c for c in teams_in_sub if c["club_id"] in recommended_set]
        subregions_summary.append({
            "code": scode,
            "name": sub["name"],
            "short_name": sub["short_name"],
            "flag": sub["flag"],
            "max_cap": max_per_country,
            "total_teams": len(teams_in_sub),
            "selected_count": len(selected_in_sub),
            "selected_codes": [c["short_code"] for c in selected_in_sub],
            "is_full": len(selected_in_sub) >= max_per_country,
        })

    return {
        "region_slug": region_slug,
        "regional_capacity": capacity,
        "max_partners_per_country": max_per_country,
        "recommended_club_ids": recommended_ids,
        "retained_count": retained_count,
        "promoted_count": promoted_count,
        "demoted_count": demoted_count,
        "subregions": subregions_summary,
        "clubs": sorted_clubs,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 7. HARD VALIDATION FOR USER MANUAL PARTNER SELECTION
# ─────────────────────────────────────────────────────────────────────────────

def validate_manual_partner_selection(
    region_slug: str,
    selected_club_ids: List[int],
    region_clubs: List[Dict[str, Any]],
    config: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, str, List[Dict[str, Any]]]:
    """Kiểm tra nghiêm ngặt danh sách đội Partner do người chơi chốt cho 1 khu vực:
    1. Bắt buộc chọn đúng 8 đội (regional_capacity = 8).
    2. Tất cả đội được chọn phải thuộc khu vực đó.
    3. RÀNG BUỘC CỨNG: Không một Quốc gia / Tiểu khu vực nào được vượt quá 2 đội (max_partners_per_country = 2).
    """
    cfg = config or DEFAULT_PARTNERSHIP_CONFIG
    max_per_country = int(cfg["program"].get("max_partners_per_country", 2))
    capacity = int(cfg["program"].get("regional_capacity", 8))

    unique_ids = []
    for cid in selected_club_ids:
        icid = int(cid)
        if icid not in unique_ids:
            unique_ids.append(icid)

    club_map = {int(c.get("club_id") or c.get("id")): c for c in region_clubs}
    violations: List[Dict[str, Any]] = []

    # Kiểm tra các đội có thuộc khu vực không
    invalid_clubs = [cid for cid in unique_ids if cid not in club_map]
    if invalid_clubs:
        return (
            False,
            f"Khu vực {region_slug.upper()} có ID đội không hợp lệ: {invalid_clubs}",
            [{"type": "invalid_club", "club_ids": invalid_clubs}],
        )

    # Kiểm tra giới hạn Quốc gia / Tiểu khu vực (<= 2 đội)
    by_country: Dict[str, List[Dict[str, Any]]] = {}
    for cid in unique_ids:
        c_obj = club_map[cid]
        s_code = c_obj.get("short_code", "")
        c_code = c_obj.get("country_code") or get_club_country_info(s_code, region_slug)["country_code"]
        by_country.setdefault(c_code, []).append(c_obj)

    for c_code, c_list in by_country.items():
        if len(c_list) > max_per_country:
            meta = SUBREGION_METADATA.get(c_code, {"name": c_code, "flag": "🏳️"})
            team_names = ", ".join(f"{t.get('name')} ({t.get('short_code')})" for t in c_list)
            msg = (
                f"Vi phạm giới hạn Quốc gia / Tiểu khu vực tại {region_slug.upper()}: "
                f"{meta.get('flag', '')} {meta.get('name', c_code)} đang có {len(c_list)}/{max_per_country} đội được chọn ({team_names}). "
                f"Chỉ được phép tối đa {max_per_country} đội Partner cho mỗi quốc gia/tiểu khu vực!"
            )
            violations.append({
                "type": "country_cap_exceeded",
                "region": region_slug,
                "country_code": c_code,
                "country_name": meta.get("name", c_code),
                "selected_count": len(c_list),
                "max_allowed": max_per_country,
                "teams": [t.get("short_code") for t in c_list],
                "message": msg,
            })

    if violations:
        return False, violations[0]["message"], violations

    # Kiểm tra tổng số lượng đội Partner trong khu vực
    if len(unique_ids) != capacity:
        msg = (
            f"Khu vực {region_slug.upper()} hiện đang chọn {len(unique_ids)}/{capacity} đội Partner. "
            f"Vui lòng chọn đúng {capacity} đội cho mỗi khu vực!"
        )
        violations.append({
            "type": "capacity_mismatch",
            "region": region_slug,
            "selected_count": len(unique_ids),
            "required_capacity": capacity,
            "message": msg,
        })
        return False, msg, violations

    return True, "Hợp lệ", []
