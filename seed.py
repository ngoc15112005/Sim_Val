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
        ('Paper Rex', 'PRX', 92, '1630018120582_paper-rex-2021.png'),
        ('DRX', 'DRX', 88, '1651626649157_download1.png'),
        ('Gen.G', 'GEN', 87, '1775114509356_GENGLOGO_GOLD.png'),
        ('T1', 'T1', 83, '1677137430839_T1_infoboximage1.png'),
        ('Rex Regum Qeon', 'RRQ', 80, '1707306458590_LOGO_RRQ_orange.png'),
        ('Talon Esports', 'TLN', 78, '1766141618825_PCIFIC_Esports_allmode.png'),
        ('Team Secret', 'TS', 76, '1636575342048_team-secret-on-dark.png'),
        ('ZETA DIVISION', 'ZETA', 75, '1630017899610_zeta.png'),
        ('Global Esports', 'GE', 73, '1677137854820_GERedandBlue-WhiteBG.png'),
        ('DetonatioN FocusMe', 'DFM', 72, '1675669923678_190px-DetonatioN_FocusMe_2022_darkmode1.png'),
        ('BOOM Esports', 'BOOM', 70, '1705915075330_FULLSENSE.png'),
        ('Nongshim RedForce', 'NS', 82, '1674219422693_NS_.png'),
    ],
    'americas': [
        ('G2 Esports', 'G2', 93, '1675329807714_G2-Esports-Logo1.png'),
        ('Sentinels', 'SEN', 90, '1739254422982_sent.png'),
        ('NRG Esports', 'NRG', 87, '1731490666442_NRGWHT.png'),
        ('Leviatan', 'LEV', 86, '1644148043034_Leviatncolor.png'),
        ('LOUD', 'LOUD', 85, '1644060140569_LOUDGreen.png'),
        ('MIBR', 'MIBR', 83, '1648844013086_mibr_white-logo.png'),
        ('100 Thieves', '100T', 82, '1644966311613_100TVAL.png'),
        ('Cloud9', 'C9', 79, '1725635348011_C9-Logo.png'),
        ('Evil Geniuses', 'EG', 77, '1731490673901_VintageEG.png'),
        ('FURIA', 'FUR', 75, '1644059765262_FURIA-LOGO.png'),
        ('KRU Esports', 'KRU', 73, '1630017626481_kru.png'),
        ('2GAME Esports', '2G', 70, '4542485597_download38.png'),
    ],
    'emea': [
        ('FNATIC', 'FNC', 94, '1644542427486_download37.png'),
        ('Team Vitality', 'VIT', 91, '1722030793680_VITALITY_YELLOW.png'),
        ('Team Heretics', 'TH', 88, '1674060672534_600px-Team_Heretics_2022_allmode1.png'),
        ('FUT Esports', 'FUT', 85, '1644342678681_FUT_VRL_DARK.png'),
        ('Karmine Corp', 'KC', 83, '1766141700090_ULFLOGO.png'),
        ('Natus Vincere', 'NAVI', 82, '1627386036528_Natus_Vincere_2021_lightmode.png'),
        ('Gentle Mates', 'M8', 80, '1772419824776_M8-Logo.png'),
        ('BBL Esports', 'BBL', 78, '1674060310685_BBL-GOLD-EMBLEM1.png'),
        ('Team Liquid', 'TL', 77, '1637252586938_teamliquid.png'),
        ('GIANTX', 'GX', 75, '1706547566185_GX.png'),
        ('KOI', 'KOI', 73, '1774348464161_EternalFireLogo.png'),
        ('Apeks', 'APK', 71, '1774420104898_.png'),
    ],
    'china': [
        ('EDward Gaming', 'EDG', 93, '1735920597800_edg1.png'),
        ('FunPlus Phoenix', 'FPX', 89, '1776403053335_TEC.png'),
        ('Trace Esports', 'TE', 85, '1736345448590_TE.png'),
        ('All Gamers', 'AG', 82, '1707126806655_AG.png'),
        ('Dragon Ranger Gaming', 'DRG', 80, '1707126143797_DRG.png'),
        ('Bilibili Gaming', 'BLG', 78, '1707126028220_BLG.png'),
        ('TYLOO', 'TYL', 76, '1776403069581_TYLLOGO.png'),
        ('Nova Esports', 'NOVA', 74, '1741178535000_NOVA.png'),
        ('JDG Esports', 'JDG', 73, '1707126862498_JDG.png'),
        ('Xi Lai Gaming', 'XLG', 72, '1735920774181_XLGA.PNG'),
        ('Rare Atom', 'RA', 70, '1764151573361_ENVY_Standard_Light.png'),
        ('Wolves Esports', 'WOL', 68, '1707126969882_WOL.png'),
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
