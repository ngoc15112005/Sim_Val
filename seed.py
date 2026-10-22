"""Seed database with regions, clubs, and roles."""
import sys
from app import create_app
from models import db, Region, Club, Role

REGIONS = [
    {'name': 'Pacific', 'slug': 'pacific'},
    {'name': 'Americas', 'slug': 'americas'},
    {'name': 'EMEA', 'slug': 'emea'},
    {'name': 'China', 'slug': 'china'},
]

CLUBS = {
    'pacific': [
        ('Paper Rex', 'PRX', 94, '1630018120582_paper-rex-2021.png'),
        ('Gen.G', 'GEN', 91, '1775114509356_GENGLOGO_GOLD.png'),
        ('Nongshim RedForce', 'NS', 90, '1674219422693_NS_.png'),
        ('T1', 'T1', 90, '1677137430839_T1_infoboximage1.png'),
        ('DRX', 'DRX', 89, '1651626649157_download1.png'),
        ('Rex Regum Qeon', 'RRQ', 85, '1707306458590_LOGO_RRQ_orange.png'),
        ('Talon Esports', 'TLN', 83, 'https://liquipedia.net/commons/images/thumb/7/7c/Talon_Esports_2019_allmode.png/600px-Talon_Esports_2019_allmode.png'),
        ('Global Esports', 'GE', 80, '1677137854820_GERedandBlue-WhiteBG.png'),
        ('GAM Esports', 'GAM', 78, 'https://liquipedia.net/commons/images/b/ba/GAM_Esports_2021_allmode.png'),
        ('FULL SENSE', 'FS', 78, '1705915075330_FULLSENSE.png'),
        ('SLT Seongnam', 'SLT', 75, ''),
        ('Sin Prisa Gaming', 'SPG', 74, ''),
        ('Crazy Raccoon', 'CR', 70, 'https://liquipedia.net/commons/images/6/64/Crazy_Raccoon_2020_allmode.png'),
        ('Riddle Order', 'RID', 70, ''),
        ('Dplus KIA', 'DK', 66, ''),
        ('Bleed Esports', 'BLD', 65, 'https://liquipedia.net/commons/images/4/42/Bleed_eSports_2021_allmode.png'),
        ('ZETA DIVISION', 'ZETA', 64, '1630017899610_zeta.png'),
        ('Fancy United Esports', 'FC', 63, ''),
        ('Team Secret', 'TS', 62, '1636575342048_team-secret-on-dark.png'),
        ('DetonatioN FocusMe', 'DFM', 58, '1675669923678_190px-DetonatioN_FocusMe_2022_darkmode1.png'),
        ('BOOM Esports', 'BOOM', 55, '1325_BOOM_logo.png'),
    ],
    'americas': [
        ('LOUD', 'LOUD', 93, '1644060140569_LOUDGreen.png'),
        ('Leviatan', 'LEV', 92, '1644148043034_Leviatncolor.png'),
        ('NRG Esports', 'NRG', 92, '1731490666442_NRGWHT.png'),
        ('Sentinels', 'SEN', 91, '1739254422982_sent.png'),
        ('G2 Esports', 'G2', 91, '1675329807714_G2-Esports-Logo1.png'),
        ('100 Thieves', '100T', 89, '1644966311613_100TVAL.png'),
        ('KRU Esports', 'KRU', 81, '1630017626481_kru.png'),
        ('Team Envy', 'NV', 80, '1764151573361_ENVY_Standard_Light.png'),
        ('Oxygen Esports', 'OXG', 78, 'https://liquipedia.net/commons/images/8/83/Oxygen_Esports_allmode.png'),
        ('TSM', 'TSM', 77, 'https://liquipedia.net/commons/images/e/e3/Team_SoloMid_lightmode.png'),
        ('Cloud9', 'C9', 76, '1725635348011_C9-Logo.png'),
        ('Moist x Shopify', 'MxS', 75, ''),
        ('Evil Geniuses', 'EG', 72, '1731490673901_VintageEG.png'),
        ('All Knights', 'AK', 71, ''),
        ('Galorys', 'GLR', 69, ''),
        ('DarkZero Esports', 'DZ', 67, ''),
        ('MIBR', 'MIBR', 65, '1648844013086_mibr_white-logo.png'),
        ('FURIA', 'FUR', 61, '1644059765262_FURIA-LOGO.png'),
        ('2GAME Esports', '2G', 60, '4542485597_download38.png'),
    ],
    'emea': [
        ('FNATIC', 'FNC', 93, '1644542427486_download37.png'),
        ('Team Vitality', 'VIT', 92, '1722030793680_VITALITY_YELLOW.png'),
        ('Team Heretics', 'TH', 92, '1674060672534_600px-Team_Heretics_2022_allmode1.png'),
        ('Karmine Corp', 'KC', 88, '1766141700090_ULFLOGO.png'),
        ('Team Liquid', 'TL', 86, '1637252586938_teamliquid.png'),
        ('FUT Esports', 'FUT', 84, '1644342678681_FUT_VRL_DARK.png'),
        ('BBL Esports', 'BBL', 79, '1674060310685_BBL-GOLD-EMBLEM1.png'),
        ('Gentle Mates', 'M8', 78, '1772419824776_M8-Logo.png'),
        ('Eternal Fire', 'EF', 77, '1774348464161_EternalFireLogo.png'),
        ('Natus Vincere', 'NAVI', 76, '1627386036528_Natus_Vincere_2021_lightmode.png'),
        ('PCIFIC Esports', 'PCF', 73, ''),
        ('Team Falcons', 'FLC', 73, ''),
        ('Acend', 'ACE', 71, 'https://liquipedia.net/commons/images/thumb/7/7d/Acend_allmode.png/600px-Acend_allmode.png'),
        ('Joblife', 'JL', 70, ''),
        ('Mandatory', 'MDR', 68, ''),
        ('CGN Esports', 'CGN', 67, ''),
        ('Case Esports', 'CASE', 66, ''),
        ('GIANTX', 'GX', 64, '1706547566185_GX.png'),
        ('KOI', 'KOI', 59, '1774348464161_EternalFireLogo.png'),
        ('Apeks', 'APK', 57, '1774420104898_.png'),
    ],
    'china': [
        ('EDward Gaming', 'EDG', 93, '1735920597800_edg1.png'),
        ('Bilibili Gaming', 'BLG', 87, '1707126028220_BLG.png'),
        ('Xi Lai Gaming', 'XLG', 85, '1735920774181_XLGA.PNG'),
        ('FunPlus Phoenix', 'FPX', 85, '1776403053335_TEC.png'),
        ('Trace Esports', 'TE', 84, '1736345448590_TE.png'),
        ('Wolves Esports', 'WOL', 80, '1707126969882_WOL.png'),
        ('TYLOO', 'TYL', 80, '1776403069581_TYLLOGO.png'),
        ('Dragon Ranger Gaming', 'DRG', 78, '1707126143797_DRG.png'),
        ('JDG Esports', 'JDG', 78, '1707126862498_JDG.png'),
        ('All Gamers', 'AG', 77, '1707126806655_AG.png'),
        ('Weibo Gaming', 'WBG', 77, 'https://liquipedia.net/commons/images/8/86/Weibo_Gaming_HoK_allmode.png'),
        ('Titan Esports Club', 'TEC', 75, '1776403053335_TEC.png'),
        ('KeepBest Gaming', 'KBG', 73, ''),
        ('Attacking Soul Esports', 'ASE', 71, 'https://liquipedia.net/commons/images/e/e1/Attacking_Soul_Esports_2024_allmode.png'),
        ('Four Angry Men', '4AM', 69, ''),
        ('Chosen Clique Gaming', 'CCG', 68, ''),
        ('Top Esports', 'TES', 68, ''),
        ('Invictus Gaming', 'iG', 66, ''),
        ('Nova Esports', 'NOVA', 63, '1741178535000_NOVA.png'),
        ('Rare Atom', 'RA', 57, '1764151573361_ENVY_Standard_Light.png'),
    ],
}

ROLES = ['Duelist', 'Initiator', 'Controller', 'Sentinel', 'Flex']
LOGO_BASE = 'http://static.lolesports.com/teams/'


def sync_teams_only():
    """Add any missing clubs to the DB without touching existing clubs or dropping tables."""
    app = create_app()
    with app.app_context():
        region_map = {r.slug: r.id for r in Region.query.all()}
        existing_codes = {c.short_code: c for c in Club.query.all()}
        added_count = 0

        for slug, club_list in CLUBS.items():
            region_id = region_map.get(slug)
            if not region_id:
                continue
            for name, code, rating, logo_file in club_list:
                if code not in existing_codes:
                    logo = get_club_logo(code, logo_file)
                    club = Club(
                        name=name, short_code=code,
                        region_id=region_id,
                        base_rating=rating, current_rating=rating,
                        logo_url=logo,
                    )
                    db.session.add(club)
                    added_count += 1

        db.session.commit()
        print(f'Successfully added {added_count} new clubs. Existing clubs were preserved unchanged.')


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
    if len(sys.argv) > 1 and sys.argv[1] == 'sync':
        sync_teams_only()
    else:
        # Default when running directly with no args can safely sync or reseed if requested
        sync_teams_only()
