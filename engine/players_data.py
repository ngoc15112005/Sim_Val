"""
engine/players_data.py — Pool Tuyển thủ Thực tế (Real-Life VCT Database), Quy tắc Quỹ lương,
Bản sắc Ngoại binh và Bộ tên sinh Tân binh (Regens) theo từng Quốc gia / Tiểu khu vực.
"""

from __future__ import annotations
from typing import Dict, List, Any, Tuple

CORE_ROLES: Tuple[str, ...] = ("Duelist", "Initiator", "Controller", "Sentinel")
ALL_ROLES: Tuple[str, ...] = ("Duelist", "Initiator", "Controller", "Sentinel", "Flex")

ROLE_LABELS: Dict[str, str] = {
    "Duelist": "⚔️ Duelist",
    "Initiator": "⚡ Initiator",
    "Controller": "🌫️ Controller",
    "Sentinel": "🛡️ Sentinel",
    "Flex": "✨ Flex",
}

# Biểu phí lương hàng năm theo Bonus Rating (lũy tiến để ngăn tích trữ siêu sao +4/+5)
SALARY_BY_BONUS: Dict[int, int] = {
    0: 60,    # $60K / mùa
    1: 110,   # $110K / mùa
    2: 180,   # $180K / mùa
    3: 280,   # $280K / mùa
    4: 400,   # $400K / mùa
    5: 550,   # $550K / mùa (siêu sao thế hệ ngốn ~37-45% quỹ lương cả đội Partner)
}

FLEX_SALARY_MULTIPLIER: float = 1.15
BENCH_SALARY_MULTIPLIER: float = 0.50

# Quỹ lương trần hàng năm ($K) dựa theo Vị thế Partner và Org Tier (từ CLUB_COUNTRY_MAP)
SALARY_CAP_CONFIG: Dict[str, Dict[int, int]] = {
    "partner": {
        1: 1500,  # Partner Tier-S (VD: PRX, T1, SEN, FNC, EDG...)
        2: 1300,  # Partner Tier-A
        3: 1200,  # Partner Tier-B
    },
    "non_partner": {
        1: 850,   # Challenger đại gia
        2: 750,   # Challenger tiêu chuẩn
        3: 650,   # Challenger quy mô nhỏ
    },
}

MAX_FOREIGN_STARTERS: int = 2
MAX_STARTERS: int = 5
MAX_BENCH: int = 2

# Độ cởi mở ngoại binh theo Quốc gia / Tiểu khu vực (0.05 = cực kỳ khắt khe nội địa, 0.45 = rất cởi mở)
IMPORT_OPENNESS_BY_COUNTRY: Dict[str, float] = {
    # PACIFIC
    "KR": 0.05,       # Hàn Quốc: Cực kỳ khắt khe, rất ít dùng ngoại binh (hiếm mới thấy 1 người)
    "VN": 0.06,       # Việt Nam: Bản sắc thuần Việt cao, rất ít ngoại binh
    "CN_SH": 0.14,    # Trung Quốc (cộng đồng China coi các hub CN là nội binh; rất ít lấy ngoại binh ngoài TQ)
    "CN_BJ": 0.12,
    "CN_SZ": 0.14,
    "CN_HZ": 0.12,
    "CN_CS": 0.08,
    "CN_CD": 0.08,
    "JP": 0.18,       # Nhật Bản: Ưu tiên nội địa Nhật, thỉnh thoảng kẹp 1-2 ngoại binh Hàn/Châu Á
    "ID": 0.15,
    "TH": 0.16,
    "PH": 0.15,
    "SA": 0.25,
    "SG_MY": 0.40,    # Đông Nam Á quốc tế (PRX, DSG): cởi mở cao
    # AMERICAS
    "BR": 0.10,       # Brazil: Bản sắc Brazil mạnh, rất ít ngoại binh
    "LATAM": 0.22,
    "NA_WEST": 0.28,
    "NA_EAST": 0.28,
    "NA_NORTH": 0.30,
    # EMEA
    "TR": 0.12,       # Thổ Nhĩ Kỳ: Ưu tiên đội hình thuần Thổ
    "FR": 0.24,
    "ES": 0.28,
    "DACH": 0.26,
    "CIS_MENA": 0.22,
    "UK_NORD": 0.40,
    "EU_WEST": 0.45,  # Pan-EMEA quốc tế (FNC, VIT, TL, TH)
}

# Ghi đè độ khắt khe ngoại binh cho một số CLB đặc thù (ít chứ không phải 0%)
CLUB_IMPORT_OPENNESS_OVERRIDES: Dict[str, float] = {
    "T1": 0.08,
    "GEN": 0.04,
    "DRX": 0.05,
    "NS": 0.03,
    "DK": 0.04,
    "GAM": 0.05,
    "FC": 0.05,
    "LOUD": 0.08,
    "PRX": 0.42,
    "FNC": 0.45,
    "TH": 0.45,
    "VIT": 0.45,
    "EDG": 0.06,
    "BLG": 0.06,
    "TE": 0.05,
}


# ─────────────────────────────────────────────────────────────────────────────
# REAL-LIFE ROSTERS POOL (Tuổi chuẩn ~2026-2027, chỉ số 0..+5 giữ cân bằng chặt chẽ)
# Định dạng mỗi tuyển thủ: (ign, age, nationality, primary_role, bonus_rating, secondary_role, is_flex)
# ─────────────────────────────────────────────────────────────────────────────

REAL_LIFE_ROSTERS: Dict[str, List[Tuple[str, int, str, str, int, str | None, bool]]] = {
    # ── PACIFIC ──
    "PRX": [
        ("f0rsakeN", 22, "ID", "Flex", 2, "Initiator", True),
        ("something", 24, "CIS_MENA", "Duelist", 2, None, False),
        ("Jinggg", 23, "SG_MY", "Duelist", 2, "Controller", False),
        ("d4v41", 27, "SG_MY", "Sentinel", 0, "Initiator", True),
        ("PatMen", 22, "PH", "Controller", 0, "Initiator", False),
    ],
    "T1": [
        ("Meteor", 26, "KR", "Sentinel", 3, "Duelist", False),
        ("BuZz", 23, "KR", "Duelist", 2, "Sentinel", False),
        ("stax", 26, "KR", "Initiator", 2, None, False),
        ("iZu", 21, "KR", "Duelist", 1, "Controller", False),
        ("Sylvan", 25, "KR", "Controller", 1, None, False),
    ],
    "GEN": [
        ("t3xture", 26, "KR", "Duelist", 3, None, False),
        ("Karon", 23, "KR", "Controller", 3, None, False),
        ("Munchkin", 28, "KR", "Flex", 2, "Initiator", True),
        ("Foxy9", 21, "KR", "Sentinel", 1, "Duelist", False),
        ("Lakia", 25, "KR", "Initiator", 1, None, False),
    ],
    "DRX": [
        ("MaKo", 24, "KR", "Controller", 3, None, False),
        ("Flashback", 21, "KR", "Sentinel", 2, None, False),
        ("HYUNMIN", 20, "KR", "Duelist", 1, None, False),
        ("free1ng", 22, "KR", "Initiator", 1, "Sentinel", False),
        ("BeYN", 22, "KR", "Initiator", 1, None, False),
    ],
    "NS": [
        ("Margaret", 21, "KR", "Sentinel", 2, None, False),
        ("Dambi", 22, "KR", "Duelist", 2, None, False),
        ("persia", 23, "KR", "Controller", 1, None, False),
        ("Francis", 23, "KR", "Initiator", 1, None, False),
        ("Ivy", 21, "KR", "Flex", 1, "Sentinel", True),
    ],
    "ZETA": [
        ("Dep", 25, "JP", "Duelist", 2, None, False),
        ("SugarZ3ro", 23, "JP", "Controller", 2, None, False),
        ("Laz", 30, "JP", "Sentinel", 2, None, False),
        ("CLZ", 24, "JP", "Initiator", 1, None, False),
        ("SyouTa", 22, "JP", "Controller", 1, "Duelist", False),
    ],
    "CR": [
        ("neth", 29, "JP", "Sentinel", 1, "Flex", True),
        ("Meiy", 23, "JP", "Duelist", 2, None, False),
        ("Akame", 21, "KR", "Initiator", 1, None, False),
        ("Medusa", 25, "KR", "Sentinel", 1, None, False),
        ("popogachi", 23, "JP", "Controller", 1, None, False),
    ],
    "DFM": [
        ("MeiyJP", 23, "JP", "Duelist", 2, None, False),
        ("Art", 25, "JP", "Initiator", 1, None, False),
        ("Jinboong", 24, "KR", "Sentinel", 1, None, False),
        ("gyen", 20, "JP", "Controller", 0, None, False),
        ("SSeeS", 23, "JP", "Controller", 0, None, False),
    ],
    "RRQ": [
        ("Jemkin", 22, "CIS_MENA", "Duelist", 2, None, False),
        ("xffero", 24, "ID", "Controller", 2, "Sentinel", False),
        ("Monyet", 21, "ID", "Controller", 1, "Duelist", False),
        ("Kushy", 22, "ID", "Initiator", 1, None, False),
        ("Estrella", 24, "KR", "Sentinel", 1, "Initiator", False),
    ],
    "TLN": [
        ("Primmie", 20, "TH", "Duelist", 3, None, False),
        ("JitBoyS", 22, "TH", "Sentinel", 2, "Controller", False),
        ("Crws", 29, "TH", "Initiator", 1, None, False),
        ("ban", 25, "NA_EAST", "Controller", 1, None, False),
        ("Governor", 23, "NA_WEST", "Initiator", 1, "Duelist", False),
    ],
    "TS": [
        ("JessieVash", 35, "PH", "Initiator", 1, None, False),
        ("Jremy", 21, "PH", "Duelist", 2, None, False),
        ("invy", 22, "PH", "Flex", 2, "Initiator", True),
        ("wild0reoo", 23, "PH", "Controller", 1, None, False),
        ("2GE", 23, "PH", "Sentinel", 0, "Controller", False),
    ],
    "GE": [
        ("SkRossi", 26, "SA", "Duelist", 1, None, False),
        ("kellyS", 26, "PH", "Initiator", 1, "Flex", True),
        ("PapiChulo", 25, "PH", "Controller", 1, None, False),
        ("UdoTan", 21, "KR", "Sentinel", 1, None, False),
        ("Kr1stal", 24, "CIS_MENA", "Initiator", 2, None, False),
    ],
    "GAM": [
        ("Nizzy", 23, "VN", "Duelist", 2, None, False),
        ("crazyguy", 29, "VN", "Initiator", 2, "Flex", True),
        ("K1LLua", 22, "VN", "Controller", 1, None, False),
        ("f1cio", 21, "VN", "Sentinel", 1, None, False),
        ("P1nA", 22, "VN", "Controller", 0, None, False),
    ],
    "FC": [
        ("YESicaN", 24, "VN", "Duelist", 2, None, False),
        ("gin", 23, "VN", "Controller", 1, None, False),
        ("f1n", 22, "VN", "Initiator", 1, None, False),
        ("Sscary", 26, "TH", "Controller", 2, "Sentinel", False),
        ("Hyores", 21, "VN", "Sentinel", 0, None, False),
    ],
    "FS": [
        ("JohnOlsen", 25, "TH", "Duelist", 2, None, False),
        ("PTC", 26, "TH", "Controller", 1, None, False),
        ("Leviathan", 23, "TH", "Initiator", 1, None, False),
        ("KilluaTH", 21, "TH", "Sentinel", 1, None, False),
        ("Lazyy", 22, "TH", "Flex", 0, "Initiator", True),
    ],
    "BOOM": [
        ("Famouz", 24, "ID", "Duelist", 2, None, False),
        ("BerserX", 23, "ID", "Sentinel", 1, None, False),
        ("Shiro", 23, "ID", "Initiator", 1, None, False),
        ("dos9", 22, "CIS_MENA", "Controller", 1, None, False),
        ("NcSlasher", 25, "ID", "Flex", 0, "Initiator", True),
    ],
    # ── AMERICAS ──
    "SEN": [
        ("zekken", 21, "NA_EAST", "Duelist", 4, "Flex", True),
        ("johnqt", 27, "EU_WEST", "Sentinel", 3, "Initiator", False),
        ("N4RRATE", 23, "NA_WEST", "Initiator", 2, "Duelist", False),
        ("bang", 22, "NA_WEST", "Controller", 2, None, False),
        ("Zellsis", 28, "NA_EAST", "Flex", 1, "Sentinel", True),
    ],
    "G2": [
        ("jawgemo", 26, "NA_WEST", "Duelist", 3, "Controller", False),
        ("trent", 21, "NA_WEST", "Initiator", 3, None, False),
        ("valyn", 23, "NA_WEST", "Controller", 3, None, False),
        ("leaf", 22, "NA_EAST", "Sentinel", 3, None, False),
        ("JonahP", 26, "NA_NORTH", "Flex", 2, "Initiator", True),
    ],
    "NRG": [
        ("s0m", 24, "NA_WEST", "Controller", 3, None, False),
        ("Ethan", 26, "NA_WEST", "Initiator", 3, "Flex", True),
        ("mada", 22, "NA_NORTH", "Duelist", 2, None, False),
        ("brawk", 25, "NA_EAST", "Initiator", 2, None, False),
        ("skuba", 22, "NA_WEST", "Sentinel", 1, "Controller", False),
    ],
    "100T": [
        ("Asuna", 23, "NA_EAST", "Flex", 2, "Duelist", True),
        ("Cryocells", 23, "NA_WEST", "Duelist", 3, "Controller", False),
        ("eeiu", 25, "NA_NORTH", "Initiator", 2, None, False),
        ("Boostio", 25, "NA_WEST", "Sentinel", 2, None, False),
        ("zander", 24, "NA_NORTH", "Controller", 1, None, False),
    ],
    "LOUD": [
        ("cauanzin", 21, "BR", "Initiator", 3, None, False),
        ("tuyz", 22, "BR", "Controller", 2, "Duelist", False),
        ("dgzin", 24, "BR", "Duelist", 2, None, False),
        ("pANcada", 26, "BR", "Controller", 2, None, False),
        ("v1nNy", 26, "BR", "Sentinel", 1, "Initiator", False),
    ],
    "LEV": [
        ("kiNgg", 24, "LATAM", "Controller", 3, "Flex", True),
        ("Demon1", 23, "NA_WEST", "Duelist", 3, "Controller", False),
        ("tex", 26, "NA_WEST", "Sentinel", 2, None, False),
        ("C0M", 25, "NA_EAST", "Initiator", 2, None, False),
        ("nataNk", 26, "FR", "Flex", 1, "Initiator", True),
    ],
    "MIBR": [
        ("aspas", 23, "BR", "Duelist", 5, None, False),
        ("nzr", 27, "LATAM", "Initiator", 2, None, False),
        ("cortezia", 20, "BR", "Sentinel", 2, None, False),
        ("xenom", 20, "BR", "Controller", 1, None, False),
        ("artzin", 22, "BR", "Flex", 1, "Initiator", True),
    ],
    "KRU": [
        ("keznit", 24, "LATAM", "Duelist", 3, None, False),
        ("Melser", 27, "LATAM", "Controller", 2, None, False),
        ("Shyy", 21, "LATAM", "Sentinel", 2, None, False),
        ("Mazino", 24, "LATAM", "Initiator", 2, "Flex", True),
        ("adverso", 25, "LATAM", "Initiator", 1, None, False),
    ],
    "C9": [
        ("OXY", 20, "NA_EAST", "Duelist", 3, None, False),
        ("Xeppaa", 25, "NA_WEST", "Initiator", 1, "Flex", True),
        ("v1c", 22, "NA_WEST", "Controller", 1, None, False),
        ("mitch", 29, "NA_EAST", "Sentinel", 1, None, False),
        ("neT", 23, "NA_WEST", "Sentinel", 1, None, False),
    ],
    "EG": [
        ("icy", 21, "NA_WEST", "Duelist", 1, None, False),
        ("Derrek", 28, "NA_WEST", "Initiator", 2, None, False),
        ("NaturE", 25, "NA_EAST", "Sentinel", 1, None, False),
        ("supamen", 27, "NA_WEST", "Controller", 1, None, False),
        ("yay", 27, "NA_EAST", "Sentinel", 2, "Duelist", False),
    ],
    "FUR": [
        ("heat", 23, "BR", "Sentinel", 2, None, False),
        ("havoc", 20, "BR", "Duelist", 1, None, False),
        ("mwzera", 24, "BR", "Initiator", 2, "Duelist", False),
        ("Khalil", 22, "BR", "Controller", 1, None, False),
        ("raafa", 26, "BR", "Initiator", 0, None, False),
    ],
    # ── EMEA ──
    "FNC": [
        ("Alfajer", 21, "TR", "Sentinel", 4, "Duelist", False),
        ("Chronicle", 24, "CIS_MENA", "Flex", 4, "Initiator", True),
        ("Boaster", 31, "UK_NORD", "Controller", 2, None, False),
        ("kaajak", 21, "EU_WEST", "Duelist", 3, None, False),
        ("crashies", 28, "NA_WEST", "Initiator", 2, None, False),
    ],
    "TH": [
        ("Wo0t", 20, "TR", "Flex", 4, "Initiator", True),
        ("benjyfishy", 22, "UK_NORD", "Sentinel", 3, None, False),
        ("RieNs", 21, "TR", "Initiator", 3, None, False),
        ("MiniBoo", 21, "EU_WEST", "Duelist", 3, None, False),
        ("Boo", 28, "EU_WEST", "Controller", 2, None, False),
    ],
    "VIT": [
        ("Derke", 23, "UK_NORD", "Duelist", 4, None, False),
        ("Less", 21, "BR", "Sentinel", 4, None, False),
        ("Sayf", 25, "UK_NORD", "Flex", 3, "Duelist", True),
        ("trexx", 22, "CIS_MENA", "Initiator", 2, None, False),
        ("Kicks", 20, "EU_WEST", "Controller", 2, "Initiator", False),
    ],
    "TL": [
        ("nAts", 24, "CIS_MENA", "Sentinel", 4, "Controller", False),
        ("kamo", 21, "EU_WEST", "Duelist", 2, None, False),
        ("keiko", 22, "UK_NORD", "Controller", 2, "Duelist", False),
        ("paTiTek", 26, "EU_WEST", "Initiator", 2, "Flex", True),
        ("kamyk", 22, "EU_WEST", "Sentinel", 1, "Initiator", False),
    ],
    "KC": [
        ("marteen", 21, "EU_WEST", "Duelist", 2, None, False),
        ("SUYGETSU", 24, "CIS_MENA", "Sentinel", 3, "Controller", False),
        ("saadhak", 29, "LATAM", "Initiator", 3, "Flex", True),
        ("Avez", 21, "CIS_MENA", "Controller", 1, "Initiator", False),
        ("Elite", 21, "TR", "Sentinel", 2, None, False),
    ],
    "FUT": [
        ("xeus", 21, "TR", "Duelist", 3, None, False),
        ("MrFaliN", 25, "TR", "Initiator", 2, None, False),
        ("qRaxs", 25, "TR", "Flex", 2, "Initiator", True),
        ("yetujey", 21, "TR", "Sentinel", 2, None, False),
        ("ataKaptan", 23, "TR", "Controller", 2, None, False),
    ],
    "NAVI": [
        ("hiro", 20, "EU_WEST", "Sentinel", 2, None, False),
        ("koalanoob", 22, "NA_NORTH", "Duelist", 1, None, False),
        ("Ruxic", 20, "TR", "Controller", 2, None, False),
        ("Shao", 26, "CIS_MENA", "Initiator", 2, "Flex", True),
        ("ANGE1", 36, "CIS_MENA", "Controller", 1, "Initiator", False),
    ],
    "BBL": [
        ("LewN", 20, "TR", "Duelist", 2, None, False),
        ("Jamppi", 25, "UK_NORD", "Initiator", 2, "Sentinel", False),
        ("sociablEE", 22, "TR", "Flex", 1, "Initiator", True),
        ("PROFEK", 21, "EU_WEST", "Controller", 1, None, False),
        ("vakk", 25, "EU_WEST", "Sentinel", 1, None, False),
    ],
    "M8": [
        ("kAdavra", 25, "FR", "Controller", 1, None, False),
        ("Click", 22, "DACH", "Duelist", 2, None, False),
        ("RobbieBk", 22, "EU_WEST", "Initiator", 1, None, False),
        ("Minny", 20, "EU_WEST", "Sentinel", 1, None, False),
        ("Zyppan", 24, "UK_NORD", "Flex", 1, "Initiator", True),
    ],
    "GX": [
        ("westside", 22, "EU_WEST", "Sentinel", 1, None, False),
        ("purp0", 23, "CIS_MENA", "Duelist", 2, None, False),
        ("Cloud", 22, "CIS_MENA", "Initiator", 2, None, False),
        ("tomaszy", 21, "ES", "Controller", 1, None, False),
        ("runner", 22, "EU_WEST", "Flex", 1, None, True),
    ],
    # ── CHINA ──
    "EDG": [
        ("ZmjjKK", 22, "CN_SH", "Duelist", 5, None, False),
        ("CHICHOO", 24, "CN_SH", "Controller", 2, "Sentinel", False),
        ("nobody", 23, "CN_BJ", "Initiator", 2, None, False),
        ("Smoggy", 23, "CN_SZ", "Flex", 3, "Controller", True),
        ("S1Mon", 22, "CN_HZ", "Initiator", 1, "Sentinel", False),
    ],
    "BLG": [
        ("whzy", 23, "CN_SH", "Duelist", 3, None, False),
        ("knight", 23, "CN_BJ", "Initiator", 2, None, False),
        ("nephh", 23, "SG_MY", "Flex", 2, "Initiator", True),
        ("Levius", 21, "CN_SZ", "Sentinel", 1, None, False),
        ("rushia", 20, "CN_CD", "Controller", 1, None, False),
    ],
    "FPX": [
        ("Life", 23, "CN_SH", "Duelist", 2, None, False),
        ("AAAAY", 25, "CN_BJ", "Initiator", 1, None, False),
        ("autumn", 26, "NA_NORTH", "Sentinel", 2, "Flex", True),
        ("Berlin", 24, "CN_HZ", "Controller", 2, None, False),
        ("yosemite", 23, "CN_CS", "Sentinel", 1, None, False),
    ],
    "TE": [
        ("FengF", 22, "CN_BJ", "Duelist", 3, None, False),
        ("Kai", 23, "CN_SZ", "Duelist", 2, "Sentinel", False),
        ("LuoK1ng", 22, "CN_CD", "Controller", 2, None, False),
        ("Biank", 24, "CN_BJ", "Initiator", 2, None, False),
        ("heybay", 26, "CN_SZ", "Flex", 1, "Sentinel", True),
    ],
    "DRG": [
        ("vo0kashu", 24, "CIS_MENA", "Sentinel", 3, None, False),
        ("Flex1n", 23, "CN_SZ", "Controller", 1, None, False),
        ("Nicc", 23, "CN_HZ", "Initiator", 1, None, False),
        ("SpiritZ1", 21, "CN_CS", "Duelist", 1, None, False),
        ("Shion7", 22, "CN_SH", "Flex", 1, None, True),
    ],
    "WOL": [
        ("Spring", 22, "CN_SZ", "Flex", 2, "Duelist", True),
        ("SiuFatBB", 25, "CN_SZ", "Initiator", 2, None, False),
        ("Lysoar", 21, "CN_CD", "Sentinel", 1, None, False),
        ("Yuicaw", 22, "CN_SH", "Duelist", 2, None, False),
        ("Juicy", 20, "SG_MY", "Duelist", 1, "Controller", False),
    ],
    "XLG": [
        ("Rarga", 24, "CIS_MENA", "Duelist", 2, None, False),
        ("YOU", 25, "CN_BJ", "Initiator", 1, None, False),
        ("coconut", 23, "CN_HZ", "Controller", 1, None, False),
        ("happywei", 21, "CN_SH", "Sentinel", 2, None, False),
        ("Viva", 22, "CN_CD", "Initiator", 1, None, False),
    ],
    "JDG": [
        ("stew", 21, "KR", "Duelist", 2, None, False),
        ("jkuro", 23, "CN_SZ", "Controller", 1, None, False),
        ("Z1yan", 22, "CN_CD", "Sentinel", 1, None, False),
        ("Babyblue", 22, "CN_HZ", "Initiator", 1, None, False),
        ("MrCANI", 23, "CN_BJ", "Flex", 1, None, True),
    ],
    "AG": [
        ("DeLb", 24, "ID", "Sentinel", 1, None, False),
        ("Monk", 23, "CN_CD", "Controller", 1, None, False),
        ("Lsn", 22, "CN_CS", "Initiator", 1, None, False),
        ("K1ra", 21, "CN_BJ", "Duelist", 1, None, False),
        ("shr1mp", 22, "CN_SH", "Initiator", 1, None, False),
    ],
    "TYL": [
        ("ninebody", 24, "CN_CS", "Duelist", 1, None, False),
        ("Slowly", 25, "CN_CD", "Initiator", 2, None, False),
        ("hfmi0dzjc9z7", 23, "CN_BJ", "Controller", 1, None, False),
        ("Eren", 22, "CN_SH", "Sentinel", 1, None, False),
        ("Scales", 21, "CN_SZ", "Flex", 1, None, True),
    ],
}

# Nhóm Tuyển thủ Tự do (Free Agents) nổi tiếng ngoài đời ở thời điểm khởi đầu
REAL_LIFE_FREE_AGENTS: List[Tuple[str, int, str, str, int, str | None, bool, str]] = [
    # (ign, age, nationality, primary_role, bonus_rating, secondary_role, is_flex, region_slug)
    ("TenZ", 25, "NA_NORTH", "Controller", 4, "Duelist", True, "americas"),
    ("Sacy", 28, "BR", "Initiator", 3, None, False, "americas"),
    ("Marved", 26, "NA_NORTH", "Controller", 2, None, False, "americas"),
    ("FNS", 34, "NA_NORTH", "Sentinel", 2, None, False, "americas"),
    ("ardiis", 28, "UK_NORD", "Duelist", 2, "Sentinel", False, "emea"),
    ("ScreaM", 32, "EU_WEST", "Duelist", 2, "Flex", False, "emea"),
    ("cNed", 24, "TR", "Duelist", 2, None, False, "emea"),
    ("Leo", 22, "UK_NORD", "Initiator", 4, None, False, "emea"),
    ("mindfreak", 26, "ID", "Controller", 2, None, False, "pacific"),
    ("Zest", 25, "KR", "Initiator", 1, None, False, "pacific"),
    ("rb", 24, "KR", "Flex", 2, "Sentinel", True, "pacific"),
    ("crwsJr", 21, "TH", "Controller", 1, None, False, "pacific"),
    ("KiNggJr", 20, "LATAM", "Sentinel", 1, None, False, "americas"),
    ("KangkangJr", 19, "CN_SH", "Duelist", 1, None, False, "china"),
    ("ZmjSub", 21, "CN_BJ", "Controller", 1, None, False, "china"),
    ("KiraVN", 20, "VN", "Duelist", 1, None, False, "pacific"),
    ("SiuVN", 21, "VN", "Sentinel", 1, None, False, "pacific"),
    ("TakiKR", 19, "KR", "Controller", 1, None, False, "pacific"),
    ("SeoriKR", 20, "KR", "Initiator", 1, None, False, "pacific"),
    ("SoraJP", 19, "JP", "Duelist", 1, None, False, "pacific"),
]


# ─────────────────────────────────────────────────────────────────────────────
# BỘ TỪ VỰNG SINH TÊN IGN CHUẨN QUỐC GIA (CHO CÁC ĐỘI TIER 2 & REGEN TƯƠNG LAI)
# ─────────────────────────────────────────────────────────────────────────────

COUNTRY_IGN_POOLS: Dict[str, List[str]] = {
    "KR": ["Haneul", "Jinho", "Taeyang", "Minjun", "Seojun", "Jiho", "DoYun", "SiWoo", "Yeon", "Kael", "Ryu", "Sion", "Woon", "Bori", "Chae", "Hyuk", "Jin", "Gyu", "Myung", "Tae"],
    "JP": ["Sora", "Kuro", "Ren", "Haru", "Yuki", "Kaito", "Riku", "Takumi", "Shun", "Nagi", "Aoi", "Rei", "Akira", "Daichi", "Toma", "Kenta", "Ryo", "Hayato"],
    "SG_MY": ["Lix", "Zenith", "Kage", "RazeMY", "Syz", "Velo", "Zeph", "Xel", "Aiden", "KaelSG", "Jovan", "NeroSG", "Rayn"],
    "ID": ["Bima", "Raka", "Zaky", "Diaz", "Fajar", "Hafiz", "Rey", "Candra", "Arga", "Naufal", "Galih", "Bagas", "Vino"],
    "TH": ["Klao", "Namo", "TaeTH", "Poon", "Bozz", "MewTH", "Oat", "Khao", "Nonny", "BossTH", "Winz", "Tle", "BankTH"],
    "VN": ["Hoang", "PhongZ", "Khang", "MinhZ", "DucAnh", "TuanKiet", "V1et", "Loi", "Quang", "Huy", "BinVN", "Nhat", "Phat", "Dat", "Bao", "Nghia"],
    "PH": ["Marco", "Caleb", "Renz", "Jace", "Drei", "ZekePH", "Gelo", "Yohan", "KenjiPH", "Vince", "Kiko", "EnzoPH"],
    "SA": ["Aryan", "Rohan", "Kabir", "Dev", "Zaid", "Vihaan", "Rehan", "Arjun", "Karan", "Samar", "Nikhil", "Ishaan"],
    "TR": ["Emre", "Kaan", "Kerem", "Arda", "Efe", "Bora", "Mert", "Burak", "Yigit", "Deniz", "Ozan", "Sarp", "Alp", "Cem"],
    "FR": ["Léo", "Théo", "Mathis", "Enzo", "Lucas", "Kylian", "Raph", "Noé", "Hugo", "Sacha", "Gabin", "Malo", "Jules"],
    "EU_WEST": ["Niels", "Bram", "Marek", "Kuba", "Viktor", "Lukas", "Matteo", "Sven", "Daan", "Stijn", "Radek", "Tomek", "Filip"],
    "UK_NORD": ["Olle", "Elias", "Oskar", "LeoSE", "Anton", "Kasper", "Mikkel", "TheoUK", "Alfie", "Callum", "Archie", "Joonas", "Aleksi"],
    "ES": ["Iker", "Mateo", "Álvaro", "Pablo", "Diego", "Tiago", "Martín", "Raúl", "Gael", "BrunoES", "Nuno", "Diogo"],
    "DACH": ["Leon", "Felix", "Maxi", "Jonas", "Timo", "Niklas", "Jan", "Moritz", "Noah", "Basti", "Kilian", "Tobi"],
    "CIS_MENA": ["Artem", "Danya", "Sasha", "Ilya", "Egor", "Maxim", "Yura", "Kamil", "Omar", "Tariq", "Ziad", "Rami", "Kirill", "Nikita"],
    "BR": ["Cauã", "LucasBR", "Vini", "Guiz", "Breno", "Thiago", "Luan", "Gabriel", "Mateus", "Pedro", "Rafael", "EnzoBR", "Murilo", "Kaio"],
    "LATAM": ["Santi", "MateoAR", "Feli", "Nacho", "Joaco", "TobiAR", "Nico", "Benja", "Lautaro", "Tomas", "Valen", "Fede", "Gabo"],
    "NA_WEST": ["Cole", "EthanW", "Ryan", "Tyler", "Brandon", "CalebW", "Austin", "Dylan", "Logan", "Gavin", "Kyle", "Jake", "Zane"],
    "NA_EAST": ["Mason", "Carter", "Hunter", "Bryce", "Devon", "Jaden", "Chase", "Trevor", "NoahE", "Grant", "Blake", "Owen", "Luke"],
    "NA_NORTH": ["Liam", "NoahCA", "Xavier", "OwenCA", "FelixCA", "CalebCA", "SamCA", "Marc", "GabrielCA", "Tristan", "MaxCA"],
    "CN_SH": ["HaoRan", "YuZe", "MingXu", "ZiHan", "JiaHao", "WenBo", "YiFan", "ChenXi", "JunYi", "ZhiYuan", "BoWen", "LinFeng"],
    "CN_BJ": ["BeiChen", "JunHao", "TianYu", "ZeYu", "SiYuan", "HongYu", "Qiang", "PengFei", "BoLin", "YuHeng", "KaiWen"],
    "CN_SZ": ["Guang", "Shen", "Zhe", "Dong", "LinSZ", "Jie", "HongSZ", "Rui", "WeiSZ", "Xuan", "JiaSZ", "YuSZ"],
    "CN_HZ": ["Su", "Hang", "ZheJiang", "Lan", "Qing", "FengHZ", "Mu", "Yao", "Yun", "HuiHZ", "ChengHZ", "ZeHZ"],
    "CN_CS": ["Xiang", "Chu", "Han", "LinCS", "BoCS", "Yang", "HaoCS", "Lei", "Zheng", "RuiCS", "Fei"],
    "CN_CD": ["Shu", "Ba", "Chuan", "Rong", "FeiCD", "YuCD", "LinCD", "PengCD", "ZhiCD", "HaoCD", "Sen"],
}

IGN_SUFFIXES: Tuple[str, ...] = ("", "z", "FPS", "x", "1", "GG", "Jr", "zz", "k", "n", "V")
