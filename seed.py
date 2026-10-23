"""Seed database with regions, clubs, and roles."""
import os
import sys
from app import create_app
from models import db, Region, Club, Role

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
STATIC_LOGOS_DIR = os.path.join(BASE_DIR, 'static', 'logos')

REGIONS = [
    {'name': 'Pacific', 'slug': 'pacific'},
    {'name': 'Americas', 'slug': 'americas'},
    {'name': 'EMEA', 'slug': 'emea'},
    {'name': 'China', 'slug': 'china'},
]

CLUBS = {
    'pacific': [
        ('Paper Rex', 'PRX', 94, '1630018120582_paper-rex-2021.png'),
        ('Nongshim RedForce', 'NS', 91, '1674219422693_NS_.png'),
        ('T1', 'T1', 91, '1677137430839_T1_infoboximage1.png'),
        ('Gen.G', 'GEN', 89, '1775114509356_GENGLOGO_GOLD.png'),
        ('DRX', 'DRX', 89, '1651626649157_download1.png'),
        ('Global Esports', 'GE', 87, '1677137854820_GERedandBlue-WhiteBG.png'),
        ('Talon Esports', 'TLN', 82, 'https://liquipedia.net/commons/images/thumb/7/7c/Talon_Esports_2019_allmode.png/600px-Talon_Esports_2019_allmode.png'),
        ('Team Secret', 'TS', 81, '1636575342048_team-secret-on-dark.png'),
        ('Rex Regum Qeon', 'RRQ', 80, '1707306458590_LOGO_RRQ_orange.png'),
        ('Sin Prisa Gaming', 'SPG', 76, ''),
        ('ZETA DIVISION', 'ZETA', 75, '1630017899610_zeta.png'),
        ('BOOM Esports', 'BOOM', 74, '1325_BOOM_logo.png'),
        ('FULL SENSE', 'FS', 73, '1705915075330_FULLSENSE.png'),
        ('Crazy Raccoon', 'CR', 72, 'https://liquipedia.net/commons/images/6/64/Crazy_Raccoon_2020_allmode.png'),
        ('SLT Seongnam', 'SLT', 72, ''),
        ('Riddle Order', 'RID', 71, ''),
        ('Fancy United Esports', 'FC', 71, ''),
        ('Dplus KIA', 'DK', 70, ''),
        ('DetonatioN FocusMe', 'DFM', 70, '1675669923678_190px-DetonatioN_FocusMe_2022_darkmode1.png'),
        ('Bleed Esports', 'BLD', 70, 'https://liquipedia.net/commons/images/4/42/Bleed_eSports_2021_allmode.png'),
        ('GAM Esports', 'GAM', 70, 'https://liquipedia.net/commons/images/b/ba/GAM_Esports_2021_allmode.png'),
    ],
    'americas': [
        ('LOUD', 'LOUD', 96, '1644060140569_LOUDGreen.png'),
        ('Leviatan', 'LEV', 94, '1644148043034_Leviatncolor.png'),
        ('NRG Esports', 'NRG', 93, '1731490666442_NRGWHT.png'),
        ('100 Thieves', '100T', 92, '1644966311613_100TVAL.png'),
        ('G2 Esports', 'G2', 92, '1675329807714_G2-Esports-Logo1.png'),
        ('Sentinels', 'SEN', 90, '1739254422982_sent.png'),
        ('KRU Esports', 'KRU', 83, '1630017626481_kru.png'),
        ('Cloud9', 'C9', 82, '1725635348011_C9-Logo.png'),
        ('MIBR', 'MIBR', 81, '1648844013086_mibr_white-logo.png'),
        ('Evil Geniuses', 'EG', 78, '1731490673901_VintageEG.png'),
        ('2GAME Esports', '2G', 76, '4542485597_download38.png'),
        ('Moist x Shopify', 'MxS', 75, ''),
        ('Oxygen Esports', 'OXG', 74, 'https://liquipedia.net/commons/images/8/83/Oxygen_Esports_allmode.png'),
        ('TSM', 'TSM', 74, 'https://liquipedia.net/commons/images/e/e3/Team_SoloMid_lightmode.png'),
        ('Team Envy', 'NV', 73, '1764151573361_ENVY_Standard_Light.png'),
        ('All Knights', 'AK', 72, ''),
        ('FURIA', 'FUR', 72, '1644059765262_FURIA-LOGO.png'),
        ('Galorys', 'GLR', 71, ''),
        ('DarkZero Esports', 'DZ', 70, ''),
    ],
    'emea': [
        ('Team Vitality', 'VIT', 93, '1722030793680_VITALITY_YELLOW.png'),
        ('FNATIC', 'FNC', 91, '1644542427486_download37.png'),
        ('Team Heretics', 'TH', 89, '1674060672534_600px-Team_Heretics_2022_allmode1.png'),
        ('Karmine Corp', 'KC', 86, '1766141700090_ULFLOGO.png'),
        ('Team Liquid', 'TL', 85, '1637252586938_teamliquid.png'),
        ('FUT Esports', 'FUT', 85, '1644342678681_FUT_VRL_DARK.png'),
        ('Natus Vincere', 'NAVI', 80, '1627386036528_Natus_Vincere_2021_lightmode.png'),
        ('BBL Esports', 'BBL', 77, '1674060310685_BBL-GOLD-EMBLEM1.png'),
        ('Apeks', 'APK', 76, '1774420104898_.png'),
        ('Eternal Fire', 'EF', 75, '1774348464161_EternalFireLogo.png'),
        ('Gentle Mates', 'M8', 74, '1772419824776_M8-Logo.png'),
        ('GIANTX', 'GX', 73, '1706547566185_GX.png'),
        ('Acend', 'ACE', 72, 'https://liquipedia.net/commons/images/thumb/7/7d/Acend_allmode.png/600px-Acend_allmode.png'),
        ('PCIFIC Esports', 'PCF', 71, ''),
        ('Team Falcons', 'FLC', 71, ''),
        ('Joblife', 'JL', 71, ''),
        ('Mandatory', 'MDR', 70, ''),
        ('CGN Esports', 'CGN', 70, ''),
        ('Case Esports', 'CASE', 70, ''),
        ('KOI', 'KOI', 70, '1774348464161_EternalFireLogo.png'),
    ],
    'china': [
        ('EDward Gaming', 'EDG', 88, '1735920597800_edg1.png'),
        ('Trace Esports', 'TE', 84, '1736345448590_TE.png'),
        ('FunPlus Phoenix', 'FPX', 84, '1776403053335_TEC.png'),
        ('Bilibili Gaming', 'BLG', 83, '1707126028220_BLG.png'),
        ('Dragon Ranger Gaming', 'DRG', 78, '1707126143797_DRG.png'),
        ('Wolves Esports', 'WOL', 78, '1707126969882_WOL.png'),
        ('Xi Lai Gaming', 'XLG', 77, '1735920774181_XLGA.PNG'),
        ('JDG Esports', 'JDG', 76, '1707126862498_JDG.png'),
        ('All Gamers', 'AG', 75, '1707126806655_AG.png'),
        ('TYLOO', 'TYL', 75, '1776403069581_TYLLOGO.png'),
        ('Weibo Gaming', 'WBG', 74, 'https://liquipedia.net/commons/images/8/86/Weibo_Gaming_HoK_allmode.png'),
        ('Titan Esports Club', 'TEC', 73, '1776403053335_TEC.png'),
        ('Nova Esports', 'NOVA', 72, '1741178535000_NOVA.png'),
        ('KeepBest Gaming', 'KBG', 72, ''),
        ('Attacking Soul Esports', 'ASE', 71, 'https://liquipedia.net/commons/images/e/e1/Attacking_Soul_Esports_2024_allmode.png'),
        ('Four Angry Men', '4AM', 71, ''),
        ('Chosen Clique Gaming', 'CCG', 70, ''),
        ('Top Esports', 'TES', 70, ''),
        ('Invictus Gaming', 'iG', 70, ''),
        ('Rare Atom', 'RA', 70, '1764151573361_ENVY_Standard_Light.png'),
    ],
}

ROLES = ['Duelist', 'Initiator', 'Controller', 'Sentinel', 'Flex']
LOGO_BASE = 'http://static.lolesports.com/teams/'


def get_club_logo(code, logo_file=None):
    """Return local static logo path if exists, otherwise fallback to external."""
    if not code:
        return ''
    # Check exact match first (.png, then .svg)
    for ext in ['.png', '.svg', '.PNG', '.SVG']:
        filename = f"{code}{ext}"
        if os.path.isfile(os.path.join(STATIC_LOGOS_DIR, filename)):
            return f"/static/logos/{filename}"

    # Case-insensitive check
    if os.path.exists(STATIC_LOGOS_DIR):
        for f in os.listdir(STATIC_LOGOS_DIR):
            base, ext = os.path.splitext(f)
            if base.lower() == code.lower() and ext.lower() in ('.png', '.svg'):
                return f"/static/logos/{f}"

    if logo_file and (logo_file.startswith('http://') or logo_file.startswith('https://')):
        return logo_file
    return ''


def sync_club_logos_internal():
    """Ensure all clubs in database point to valid local logos (runs in current app context)."""
    updated = 0
    for club in Club.query.all():
        correct_logo = get_club_logo(club.short_code)
        if correct_logo and club.logo_url != correct_logo:
            club.logo_url = correct_logo
            updated += 1
    if updated > 0:
        db.session.commit()
        print(f"Synced local logos for {updated} clubs.")


def seed_initial_data():
    """Seed regions, clubs, and roles if database is empty (for fresh cloud deploys)."""
    region_map = {}
    for r in REGIONS:
        existing = Region.query.filter_by(slug=r['slug']).first()
        if not existing:
            region = Region(name=r['name'], slug=r['slug'])
            db.session.add(region)
            db.session.flush()
            region_map[r['slug']] = region.id
        else:
            region_map[r['slug']] = existing.id

    for slug, club_list in CLUBS.items():
        region_id = region_map[slug]
        for name, code, rating, logo_file in club_list:
            if not Club.query.filter_by(short_code=code).first():
                logo = get_club_logo(code, logo_file)
                club = Club(
                    name=name, short_code=code,
                    region_id=region_id,
                    base_rating=rating, current_rating=rating,
                    logo_url=logo,
                )
                db.session.add(club)

    for role_name in ROLES:
        if not Role.query.filter_by(name=role_name).first():
            db.session.add(Role(name=role_name))

    db.session.commit()


def sync_ratings():
    """Update base_rating and current_rating for all existing clubs in DB from CLUBS dictionary."""
    app = create_app()
    with app.app_context():
        rating_map = {}
        for region_slug, club_list in CLUBS.items():
            for name, code, rating, logo_file in club_list:
                rating_map[code.upper()] = (name, rating)

        updated_count = 0
        clubs = Club.query.all()
        for club in clubs:
            code_upper = club.short_code.upper()
            if code_upper in rating_map:
                name, new_rating = rating_map[code_upper]
                club.base_rating = new_rating
                club.current_rating = new_rating
                updated_count += 1

        db.session.commit()
        print(f"Successfully synced power ratings for {updated_count} clubs in database.")


def sync_teams_only():
    """Add any missing clubs to the DB and update ratings for existing clubs."""
    app = create_app()
    with app.app_context():
        region_map = {r.slug: r.id for r in Region.query.all()}
        existing = {c.short_code: c for c in Club.query.all()}
        added_count = 0
        updated_count = 0

        for slug, club_list in CLUBS.items():
            region_id = region_map.get(slug)
            if not region_id:
                continue
            for name, code, rating, logo_file in club_list:
                if code not in existing:
                    logo = get_club_logo(code, logo_file)
                    club = Club(
                        name=name, short_code=code,
                        region_id=region_id,
                        base_rating=rating, current_rating=rating,
                        logo_url=logo,
                    )
                    db.session.add(club)
                    added_count += 1
                else:
                    club = existing[code]
                    club.base_rating = rating
                    club.current_rating = rating
                    updated_count += 1

        db.session.commit()
        print(f'Sync completed: {added_count} clubs added, {updated_count} clubs updated.')


def seed():
    """Drop and re-seed all tables."""
    app = create_app()
    with app.app_context():
        db.drop_all()
        db.create_all()

        region_map = {}
        for r in REGIONS:
            region = Region(name=r['name'], slug=r['slug'])
            db.session.add(region)
            db.session.flush()
            region_map[r['slug']] = region.id

        for slug, club_list in CLUBS.items():
            region_id = region_map[slug]
            for name, code, rating, logo_file in club_list:
                logo = get_club_logo(code, logo_file)
                club = Club(
                    name=name, short_code=code,
                    region_id=region_id,
                    base_rating=rating, current_rating=rating,
                    logo_url=logo,
                )
                db.session.add(club)

        for role_name in ROLES:
            db.session.add(Role(name=role_name))

        db.session.commit()
        print(f'Seeded {len(REGIONS)} regions, {sum(len(c) for c in CLUBS.values())} clubs, {len(ROLES)} roles.')


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'seed':
        seed()
    elif len(sys.argv) > 1 and sys.argv[1] == 'ratings':
        sync_ratings()
    else:
        sync_teams_only()
