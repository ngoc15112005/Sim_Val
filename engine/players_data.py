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
# REAL-LIFE ROSTERS POOL (Cập nhật thực tế đến cuối mùa VCT 2026: Champions Shanghai,
# Masters Santiago/London, EWC 2026 & Stage 2; chỉ số 0..+5 cân bằng chặt chẽ)
# Định dạng mỗi tuyển thủ: (ign, age, nationality, primary_role, bonus_rating, secondary_role, is_flex)
# ─────────────────────────────────────────────────────────────────────────────

REAL_LIFE_ROSTERS: Dict[str, List[Tuple[str, int, str, str, int, str | None, bool]]] = {
    # ── PACIFIC ──
    "PRX": [
        ("f0rsakeN", 22, "ID", "Flex", 3, "Initiator", True),
        ("something", 24, "CIS_MENA", "Duelist", 2, None, False),
        ("Jinggg", 23, "SG_MY", "Duelist", 1, "Controller", False),
        ("invy", 22, "PH", "Initiator", 1, "Flex", True),
        ("d4v41", 27, "SG_MY", "Sentinel", 0, "Controller", False),
    ],
    "NS": [
        ("Dambi", 22, "KR", "Duelist", 3, "Flex", True),
        ("Francis", 23, "KR", "Flex", 1, "Duelist", True),
        ("Xross", 19, "KR", "Initiator", 1, None, False),
        ("Ivy", 21, "KR", "Sentinel", 1, "Controller", False),
        ("Rb", 25, "KR", "Controller", 0, "Sentinel", False),
    ],
    "T1": [
        ("Meteor", 26, "KR", "Sentinel", 2, "Duelist", False),
        ("BuZz", 23, "KR", "Duelist", 2, None, False),
        ("iZu", 21, "KR", "Controller", 1, "Duelist", False),
        ("stax", 26, "KR", "Initiator", 1, None, False),
        ("carpe", 28, "KR", "Flex", 0, "Initiator", True),
    ],
    "GE": [
        ("PatMen", 24, "PH", "Initiator", 2, "Sentinel", False),
        ("Kr1stal", 24, "CIS_MENA", "Initiator", 2, None, False),
        ("UdoTan", 22, "KR", "Sentinel", 1, "Duelist", False),
        ("autumn", 25, "SG_MY", "Flex", 1, "Duelist", True),
        ("xavi8k", 25, "PH", "Controller", 0, None, False),
    ],
    "GEN": [
        ("t3xture", 26, "KR", "Duelist", 3, None, False),
        ("Karon", 23, "KR", "Controller", 2, None, False),
        ("Lakia", 25, "KR", "Initiator", 1, None, False),
        ("Foxy9", 21, "KR", "Sentinel", 0, "Duelist", False),
        ("Ash", 21, "KR", "Flex", 0, "Initiator", True),
    ],
    "DRX": [
        ("MaKo", 24, "KR", "Controller", 3, None, False),
        ("HYUNMIN", 20, "KR", "Duelist", 2, None, False),
        ("free1ng", 21, "KR", "Sentinel", 1, "Duelist", False),
        ("BeYN", 22, "KR", "Initiator", 1, None, False),
        ("Hermes", 19, "KR", "Flex", 0, "Sentinel", True),
    ],
    "RRQ": [
        ("Jemkin", 22, "CIS_MENA", "Duelist", 2, None, False),
        ("xffero", 24, "ID", "Controller", 1, "Sentinel", False),
        ("Monyet", 21, "ID", "Controller", 1, "Duelist", False),
        ("crazyguy", 29, "VN", "Initiator", 1, "Controller", False),
        ("Kushy", 21, "ID", "Sentinel", 0, "Initiator", False),
    ],
    "FS": [
        ("Primmie", 20, "TH", "Duelist", 3, None, False),
        ("JitBoyS", 22, "TH", "Sentinel", 1, "Controller", False),
        ("KilluaTH", 21, "TH", "Controller", 1, "Sentinel", False),
        ("Leviathan", 23, "TH", "Initiator", 0, None, False),
        ("Seph1roth", 22, "TH", "Flex", 0, "Initiator", True),
    ],
    "TS": [
        ("kellyS", 26, "PH", "Initiator", 1, "Flex", True),
        ("Sylvan", 25, "KR", "Controller", 1, None, False),
        ("Zeus", 22, "PH", "Duelist", 1, None, False),
        ("STYRON", 24, "SG_MY", "Flex", 0, "Initiator", True),
        ("naTz", 22, "ID", "Sentinel", 0, "Controller", False),
    ],
    "DFM": [
        ("Meiy", 23, "JP", "Duelist", 2, None, False),
        ("Akame", 21, "KR", "Flex", 1, "Duelist", True),
        ("Caedye", 21, "JP", "Initiator", 0, None, False),
        ("SSeeS", 23, "JP", "Controller", 0, "Initiator", False),
        ("yatsuka", 20, "JP", "Sentinel", 0, None, False),
    ],
    "ZETA": [
        ("SugarZ3ro", 23, "JP", "Controller", 1, None, False),
        ("SyouTa", 22, "JP", "Duelist", 1, "Controller", False),
        ("Xdll", 21, "JP", "Initiator", 1, None, False),
        ("eKo", 25, "KR", "Flex", 0, "Initiator", True),
        ("Absol", 20, "JP", "Sentinel", 0, "Duelist", False),
    ],
    "TLN": [
        ("PTC", 26, "TH", "Controller", 1, None, False),
        ("JohnOlsen", 25, "TH", "Duelist", 1, None, False),
        ("Governor", 23, "NA_WEST", "Initiator", 1, "Duelist", False),
        ("ban", 25, "NA_EAST", "Controller", 0, None, False),
        ("Lazyy", 22, "TH", "Sentinel", 0, "Flex", True),
    ],
    "GAM": [
        ("Nizzy", 23, "VN", "Duelist", 1, None, False),
        ("Hansia", 22, "VN", "Initiator", 1, None, False),
        ("LightQT", 21, "VN", "Controller", 0, None, False),
        ("lilhieu", 20, "VN", "Sentinel", 0, None, False),
        ("K1LLua", 22, "VN", "Flex", 0, "Controller", True),
    ],
    "FC": [
        ("YESicaN", 24, "VN", "Initiator", 1, None, False),
        ("f1cio", 21, "VN", "Controller", 1, None, False),
        ("Nia", 21, "VN", "Duelist", 1, None, False),
        ("bucute", 21, "VN", "Sentinel", 0, None, False),
        ("twilight", 22, "VN", "Flex", 0, "Duelist", True),
    ],
    "BOOM": [
        ("Famouz", 24, "ID", "Duelist", 1, None, False),
        ("BerserX", 23, "ID", "Sentinel", 1, None, False),
        ("Shiro", 23, "ID", "Initiator", 0, None, False),
        ("NcSlasher", 25, "ID", "Controller", 0, "Initiator", False),
        ("fl1pzjder", 24, "ID", "Flex", 0, None, True),
    ],
    # ── AMERICAS ──
    "LOUD": [
        ("erde", 18, "LATAM", "Controller", 4, "Flex", True),
        ("lukxo", 19, "BR", "Sentinel", 2, "Duelist", False),
        ("tkzin", 18, "BR", "Flex", 1, "Controller", True),
        ("Darker", 21, "LATAM", "Initiator", 1, None, False),
        ("DaviH", 23, "ES", "Duelist", 0, "Sentinel", False),
    ],
    "LEV": [
        ("Neon", 18, "LATAM", "Sentinel", 3, "Flex", True),
        ("Sato", 19, "BR", "Duelist", 2, None, False),
        ("kiNgg", 24, "LATAM", "Controller", 1, "Flex", True),
        ("blowz", 19, "BR", "Initiator", 1, None, False),
        ("spikeziN", 19, "BR", "Flex", 0, "Controller", True),
    ],
    "100T": [
        ("Cryocells", 23, "NA_WEST", "Sentinel", 3, "Duelist", False),
        ("Timotino", 19, "NA_NORTH", "Duelist", 2, None, False),
        ("Asuna", 23, "NA_EAST", "Flex", 1, "Initiator", True),
        ("bang", 22, "NA_WEST", "Controller", 1, None, False),
        ("vora", 22, "NA_NORTH", "Initiator", 0, None, False),
    ],
    "G2": [
        ("leaf", 22, "NA_EAST", "Sentinel", 2, None, False),
        ("trent", 21, "NA_WEST", "Initiator", 2, None, False),
        ("valyn", 23, "NA_WEST", "Controller", 2, None, False),
        ("jawgemo", 26, "NA_WEST", "Duelist", 1, "Controller", False),
        ("JonahP", 26, "NA_NORTH", "Flex", 0, "Initiator", True),
    ],
    "NRG": [
        ("Ethan", 26, "NA_WEST", "Initiator", 2, "Flex", True),
        ("mada", 22, "NA_NORTH", "Duelist", 2, None, False),
        ("Keiko", 22, "UK_NORD", "Controller", 1, "Duelist", False),
        ("brawk", 25, "NA_EAST", "Initiator", 1, None, False),
        ("skuba", 22, "NA_WEST", "Sentinel", 1, "Controller", False),
    ],
    "MIBR": [
        ("aspas", 23, "BR", "Duelist", 3, None, False),
        ("zekken", 21, "NA_EAST", "Duelist", 2, "Flex", True),
        ("Verno", 20, "NA_WEST", "Initiator", 1, None, False),
        ("Mazino", 24, "LATAM", "Controller", 1, "Flex", True),
        ("tex", 26, "NA_WEST", "Sentinel", 0, None, False),
    ],
    "SEN": [
        ("johnqt", 27, "EU_WEST", "Sentinel", 2, "Initiator", False),
        ("cortezia", 21, "BR", "Sentinel", 1, "Controller", False),
        ("reduxx", 19, "NA_EAST", "Duelist", 1, None, False),
        ("Kyu", 21, "NA_EAST", "Controller", 1, "Initiator", False),
        ("Zellsis", 28, "NA_EAST", "Flex", 0, "Initiator", True),
    ],
    "KRU": [
        ("Less", 21, "BR", "Sentinel", 2, None, False),
        ("saadhak", 29, "LATAM", "Initiator", 2, "Flex", True),
        ("mwzera", 24, "BR", "Duelist", 1, "Initiator", False),
        ("silentzz", 22, "BR", "Controller", 1, None, False),
        ("Dantedeu5", 20, "LATAM", "Duelist", 0, "Flex", True),
    ],
    "FUR": [
        ("eeiu", 25, "NA_NORTH", "Initiator", 2, None, False),
        ("koalanoob", 22, "NA_NORTH", "Duelist", 1, None, False),
        ("artzin", 22, "BR", "Flex", 1, "Controller", True),
        ("alym", 20, "NA_WEST", "Duelist", 0, "Sentinel", False),
        ("nerve", 23, "NA_EAST", "Controller", 0, "Sentinel", False),
    ],
    "C9": [
        ("OXY", 20, "NA_EAST", "Duelist", 2, None, False),
        ("v1c", 22, "NA_WEST", "Controller", 1, None, False),
        ("Xeppaa", 25, "NA_WEST", "Initiator", 1, "Flex", True),
        ("mitch", 29, "NA_EAST", "Sentinel", 0, None, False),
        ("Jackk", 21, "NA_WEST", "Flex", 0, "Initiator", True),
    ],
    "EG": [
        ("dgzin", 24, "BR", "Duelist", 1, None, False),
        ("C0M", 25, "NA_EAST", "Initiator", 1, None, False),
        ("Okeanos", 22, "NA_WEST", "Sentinel", 1, "Duelist", False),
        ("supamen", 27, "NA_WEST", "Controller", 0, None, False),
        ("bao", 20, "NA_WEST", "Flex", 0, "Sentinel", True),
    ],
    # ── EMEA ──
    "VIT": [
        ("Derke", 23, "UK_NORD", "Duelist", 3, None, False),
        ("Chronicle", 24, "CIS_MENA", "Flex", 3, "Initiator", True),
        ("Sayonara", 20, "CIS_MENA", "Initiator", 1, "Duelist", False),
        ("Jamppi", 25, "UK_NORD", "Controller", 1, "Sentinel", False),
        ("PROFEK", 21, "EU_WEST", "Sentinel", 0, "Controller", False),
    ],
    "FNC": [
        ("Alfajer", 21, "TR", "Sentinel", 3, "Duelist", False),
        ("kaajak", 21, "EU_WEST", "Duelist", 2, None, False),
        ("crashies", 28, "NA_WEST", "Initiator", 1, None, False),
        ("Cloud", 22, "CIS_MENA", "Initiator", 1, "Flex", True),
        ("Boaster", 31, "UK_NORD", "Controller", 0, None, False),
    ],
    "KC": [
        ("dos9", 22, "CIS_MENA", "Controller", 2, None, False),
        ("N4RRATE", 23, "NA_WEST", "Initiator", 2, "Duelist", False),
        ("SUYGETSU", 24, "CIS_MENA", "Sentinel", 1, "Controller", False),
        ("sheydos", 24, "CIS_MENA", "Flex", 1, "Initiator", True),
        ("Avez", 21, "CIS_MENA", "Duelist", 0, "Controller", False),
    ],
    "TH": [
        ("Wo0t", 20, "TR", "Flex", 2, "Initiator", True),
        ("RieNs", 21, "TR", "Initiator", 2, None, False),
        ("benjyfishy", 22, "UK_NORD", "Sentinel", 1, None, False),
        ("MiniBoo", 21, "EU_WEST", "Duelist", 1, None, False),
        ("Boo", 28, "EU_WEST", "Controller", 0, None, False),
    ],
    "TL": [
        ("nAts", 24, "CIS_MENA", "Sentinel", 2, "Controller", False),
        ("kamo", 21, "EU_WEST", "Duelist", 2, None, False),
        ("kicks", 21, "EU_WEST", "Initiator", 1, None, False),
        ("trexx", 23, "CIS_MENA", "Initiator", 1, "Flex", True),
        ("purp0", 23, "CIS_MENA", "Controller", 0, "Duelist", False),
    ],
    "FUT": [
        ("xeus", 21, "TR", "Duelist", 2, None, False),
        ("yetujey", 21, "TR", "Sentinel", 1, None, False),
        ("ataKaptan", 23, "TR", "Controller", 1, None, False),
        ("qRaxs", 25, "TR", "Flex", 1, "Initiator", True),
        ("s0pp", 20, "TR", "Initiator", 0, None, False),
    ],
    "BBL": [
        ("Lar0k", 20, "TR", "Duelist", 2, None, False),
        ("Loita", 22, "TR", "Controller", 1, None, False),
        ("Rosé", 22, "TR", "Initiator", 1, None, False),
        ("Crewen", 20, "TR", "Sentinel", 1, None, False),
        ("lovers rock", 21, "TR", "Flex", 0, "Initiator", True),
    ],
    "M8": [
        ("marteen", 21, "EU_WEST", "Duelist", 2, None, False),
        ("Minny", 20, "EU_WEST", "Sentinel", 1, None, False),
        ("Proxh", 21, "TR", "Controller", 1, None, False),
        ("starxo", 25, "EU_WEST", "Initiator", 0, "Flex", True),
        ("H1ber", 25, "UK_NORD", "Flex", 0, "Duelist", True),
    ],
    "NAVI": [
        ("hiro", 20, "EU_WEST", "Sentinel", 1, None, False),
        ("Ruxic", 20, "TR", "Controller", 1, None, False),
        ("Shao", 26, "CIS_MENA", "Initiator", 1, "Flex", True),
        ("Filu", 22, "EU_WEST", "Duelist", 1, None, False),
        ("sociablEE", 22, "TR", "Flex", 0, "Initiator", True),
    ],
    "GX": [
        ("westside", 22, "EU_WEST", "Sentinel", 1, None, False),
        ("grubinho", 21, "EU_WEST", "Controller", 1, None, False),
        ("Ara", 21, "EU_WEST", "Duelist", 1, None, False),
        ("Flickless", 22, "ES", "Initiator", 0, None, False),
        ("musz3kk", 20, "TR", "Flex", 0, None, True),
    ],
    # ── CHINA ──
    "EDG": [
        ("ZmjjKK", 22, "CN_SH", "Duelist", 3, None, False),
        ("Smoggy", 23, "CN_SZ", "Flex", 1, "Controller", True),
        ("CHICHOO", 24, "CN_SH", "Sentinel", 1, "Controller", False),
        ("nobody", 23, "CN_BJ", "Initiator", 1, None, False),
        ("Jieni7", 21, "CN_HZ", "Controller", 0, "Duelist", False),
    ],
    "TYL": [
        ("slowly", 25, "CN_CD", "Initiator", 2, "Duelist", False),
        ("SiuFatBB", 25, "CN_SZ", "Controller", 1, "Initiator", False),
        ("Scales", 21, "CN_SZ", "Flex", 1, None, True),
        ("splash", 21, "CN_SH", "Duelist", 1, None, False),
        ("Erv", 21, "CN_BJ", "Sentinel", 0, None, False),
    ],
    "XLG": [
        ("Rarga", 24, "CIS_MENA", "Duelist", 2, None, False),
        ("happywei", 21, "CN_SH", "Sentinel", 2, None, False),
        ("Lysoar", 21, "CN_CD", "Controller", 1, None, False),
        ("NoMan", 23, "CN_SZ", "Initiator", 0, None, False),
        ("WsLeo", 22, "CN_HZ", "Flex", 0, "Controller", True),
    ],
    "TE": [
        ("FengF", 22, "CN_BJ", "Duelist", 2, None, False),
        ("Kai", 23, "CN_SZ", "Sentinel", 1, "Duelist", False),
        ("LuoK1ng", 22, "CN_CD", "Controller", 1, None, False),
        ("deLb", 24, "ID", "Initiator", 1, "Sentinel", False),
        ("FKEY", 20, "CN_SH", "Flex", 0, None, True),
    ],
    "BLG": [
        ("whzy", 23, "CN_SH", "Duelist", 2, None, False),
        ("knight", 23, "CN_BJ", "Initiator", 1, None, False),
        ("nephh", 23, "SG_MY", "Flex", 1, "Initiator", True),
        ("rushia", 20, "CN_CD", "Controller", 1, None, False),
        ("bud", 21, "CN_SZ", "Sentinel", 0, None, False),
    ],
    "DRG": [
        ("vo0kashu", 24, "CIS_MENA", "Sentinel", 2, None, False),
        ("Life", 23, "CN_SH", "Duelist", 1, None, False),
        ("SpiritZ1", 21, "CN_SZ", "Controller", 1, "Duelist", False),
        ("Nicc", 23, "CN_HZ", "Initiator", 1, None, False),
        ("Verse", 21, "CN_BJ", "Flex", 0, "Controller", True),
    ],
    "WOL": [
        ("Spring", 22, "CN_SZ", "Flex", 2, "Duelist", True),
        ("yosemite", 23, "CN_CS", "Sentinel", 1, "Controller", False),
        ("qiutiaN", 22, "CN_CD", "Initiator", 1, None, False),
        ("Juicy", 20, "SG_MY", "Duelist", 0, "Controller", False),
        ("Satoshi", 21, "CN_SH", "Controller", 0, None, False),
    ],
    "AG": [
        ("K1ra", 21, "CN_BJ", "Duelist", 1, None, False),
        ("shr1mp", 22, "CN_SH", "Initiator", 1, None, False),
        ("iamgrq", 22, "CN_CD", "Controller", 1, None, False),
        ("Bai", 21, "CN_SZ", "Sentinel", 1, None, False),
        ("XiYiJi", 22, "CN_HZ", "Flex", 0, None, True),
    ],
    "FPX": [
        ("AAAAY", 25, "CN_BJ", "Initiator", 1, None, False),
        ("sScary", 26, "TH", "Controller", 1, "Sentinel", False),
        ("Setrod", 21, "CN_SH", "Duelist", 1, None, False),
        ("Levius", 21, "CN_SZ", "Sentinel", 1, None, False),
        ("Z1yan", 22, "CN_CD", "Flex", 0, None, True),
    ],
    "JDG": [
        ("stew", 21, "KR", "Duelist", 1, None, False),
        ("BerLIN", 24, "CN_HZ", "Controller", 1, "Initiator", False),
        ("Yuicaw", 22, "CN_SZ", "Sentinel", 1, "Duelist", False),
        ("jkuro", 23, "CN_SZ", "Initiator", 0, "Controller", False),
        ("crownfisher", 21, "CN_BJ", "Flex", 0, None, True),
    ],
    "NOVA": [
        ("GuanG", 21, "CN_CS", "Duelist", 1, None, False),
        ("CB", 22, "CN_BJ", "Sentinel", 1, None, False),
        ("Ezeir", 22, "CN_SZ", "Controller", 0, None, False),
        ("swagzor", 23, "CIS_MENA", "Initiator", 0, None, False),
        ("Monk", 23, "CN_CD", "Flex", 0, "Controller", True),
    ],
}

# Nhóm Tuyển thủ Tự do (Free Agents) nổi tiếng ngoài đời ở thời điểm cuối 2026
REAL_LIFE_FREE_AGENTS: List[Tuple[str, int, str, str, int, str | None, bool, str]] = [
    # (ign, age, nationality, primary_role, bonus_rating, secondary_role, is_flex, region_slug)
    ("TenZ", 25, "NA_NORTH", "Duelist", 2, "Controller", True, "americas"),
    ("Leo", 22, "UK_NORD", "Initiator", 2, None, False, "emea"),
    ("mindfreak", 26, "ID", "Controller", 1, None, False, "pacific"),
    ("keznit", 24, "LATAM", "Duelist", 2, None, False, "americas"),
    ("Demon1", 23, "NA_WEST", "Duelist", 1, "Controller", False, "americas"),
    ("s0m", 24, "NA_WEST", "Controller", 2, None, False, "americas"),
    ("yay", 27, "NA_EAST", "Sentinel", 1, "Duelist", False, "americas"),
    ("Sayf", 25, "UK_NORD", "Flex", 1, "Duelist", True, "emea"),
    ("paTiTek", 26, "EU_WEST", "Initiator", 1, "Flex", True, "emea"),
    ("pANcada", 26, "BR", "Controller", 1, None, False, "americas"),
    ("cauanzin", 21, "BR", "Initiator", 1, None, False, "americas"),
    ("S1Mon", 22, "CN_HZ", "Initiator", 1, None, False, "china"),
    ("Zest", 25, "KR", "Initiator", 1, None, False, "pacific"),
    ("persia", 23, "KR", "Controller", 1, None, False, "pacific"),
    ("Margaret", 21, "KR", "Sentinel", 1, None, False, "pacific"),
    ("Marved", 26, "NA_NORTH", "Controller", 1, None, False, "americas"),
    ("cNed", 24, "TR", "Duelist", 1, None, False, "emea"),
    ("Dep", 25, "JP", "Duelist", 1, None, False, "pacific"),
    ("gin", 23, "VN", "Controller", 1, None, False, "pacific"),
    ("KiraVN", 20, "VN", "Duelist", 1, None, False, "pacific"),
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
