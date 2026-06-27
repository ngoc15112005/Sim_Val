"""Seed database with regions, clubs, and roles."""
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
        ('Paper Rex', 'PRX', 93, '1630018120582_paper-rex-2021.png'),
        ('Nongshim RedForce', 'NS', 83, '1674219422693_NS_.png'),
        ('T1', 'T1', 81, '1677137430839_T1_infoboximage1.png'),
        ('DRX', 'DRX', 78, '1651626649157_download1.png'),
        ('Rex Regum Qeon', 'RRQ', 75, '1707306458590_LOGO_RRQ_orange.png'),
        ('Gen.G', 'GEN', 74, '1775114509356_GENGLOGO_GOLD.png'),
        ('FULL SENSE', 'FS', 68, '1705915075330_FULLSENSE.png'),
        ('ZETA DIVISION', 'ZETA', 63, '1630017899610_zeta.png'),
        ('Team Secret', 'TS', 60, '1636575342048_team-secret-on-dark.png'),
        ('DetonatioN FocusMe', 'DFM', 58, '1675669923678_190px-DetonatioN_FocusMe_2022_darkmode1.png'),
        ('Global Esports', 'GE', 55, '1677137854820_GERedandBlue-WhiteBG.png'),
        ('BOOM Esports', 'BOOM', 52, '1325_BOOM_logo.png'),
    ],
    'americas': [
        ('G2 Esports', 'G2', 90, '1675329807714_G2-Esports-Logo1.png'),
        ('NRG Esports', 'NRG', 85, '1731490666442_NRGWHT.png'),
        ('MIBR', 'MIBR', 80, '1648844013086_mibr_white-logo.png'),
        ('Sentinels', 'SEN', 77, '1739254422982_sent.png'),
        ('100 Thieves', '100T', 74, '1644966311613_100TVAL.png'),
        ('Cloud9', 'C9', 71, '1725635348011_C9-Logo.png'),
        ('Leviatan', 'LEV', 68, '1644148043034_Leviatncolor.png'),
        ('LOUD', 'LOUD', 65, '1644060140569_LOUDGreen.png'),
        ('Evil Geniuses', 'EG', 62, '1731490673901_VintageEG.png'),
        ('FURIA', 'FUR', 58, '1644059765262_FURIA-LOGO.png'),
        ('KRU Esports', 'KRU', 55, '1630017626481_kru.png'),
        ('2GAME Esports', '2G', 52, '4542485597_download38.png'),
    ],
    'emea': [
        ('FNATIC', 'FNC', 88, '1644542427486_download37.png'),
        ('Team Liquid', 'TL', 86, '1637252586938_teamliquid.png'),
        ('BBL Esports', 'BBL', 84, '1674060310685_BBL-GOLD-EMBLEM1.png'),
        ('Team Heretics', 'TH', 81, '1674060672534_600px-Team_Heretics_2022_allmode1.png'),
        ('GIANTX', 'GX', 78, '1706547566185_GX.png'),
        ('Natus Vincere', 'NAVI', 75, '1627386036528_Natus_Vincere_2021_lightmode.png'),
        ('Team Vitality', 'VIT', 72, '1722030793680_VITALITY_YELLOW.png'),
        ('Gentle Mates', 'M8', 68, '1772419824776_M8-Logo.png'),
        ('FUT Esports', 'FUT', 65, '1644342678681_FUT_VRL_DARK.png'),
        ('Karmine Corp', 'KC', 62, '1766141700090_ULFLOGO.png'),
        ('Apeks', 'APK', 55, '1774420104898_.png'),
        ('KOI', 'KOI', 52, '1774348464161_EternalFireLogo.png'),
    ],
    'china': [
        ('EDward Gaming', 'EDG', 87, '1735920597800_edg1.png'),
        ('Bilibili Gaming', 'BLG', 85, '1707126028220_BLG.png'),
        ('Xi Lai Gaming', 'XLG', 82, '1735920774181_XLGA.PNG'),
        ('Dragon Ranger Gaming', 'DRG', 80, '1707126143797_DRG.png'),
        ('All Gamers', 'AG', 77, '1707126806655_AG.png'),
        ('FunPlus Phoenix', 'FPX', 74, '1776403053335_TEC.png'),
        ('Trace Esports', 'TE', 71, '1736345448590_TE.png'),
        ('Wolves Esports', 'WOL', 68, '1707126969882_WOL.png'),
        ('Nova Esports', 'NOVA', 65, '1741178535000_NOVA.png'),
        ('TYLOO', 'TYL', 62, '1776403069581_TYLLOGO.png'),
        ('JDG Esports', 'JDG', 58, '1707126862498_JDG.png'),
        ('Rare Atom', 'RA', 55, '1764151573361_ENVY_Standard_Light.png'),
    ],
}

ROLES = ['Duelist', 'Initiator', 'Controller', 'Sentinel', 'Flex']


LOGO_BASE = 'http://static.lolesports.com/teams/'


def seed():
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
                club = Club(
                    name=name, short_code=code,
                    region_id=region_id,
                    base_rating=rating, current_rating=rating,
                    logo_url=LOGO_BASE + logo_file,
                )
                db.session.add(club)

        for role_name in ROLES:
            db.session.add(Role(name=role_name))

        db.session.commit()
        print(f'Seeded {len(REGIONS)} regions, {sum(len(c) for c in CLUBS.values())} clubs, {len(ROLES)} roles.')


if __name__ == '__main__':
    seed()
