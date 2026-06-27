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
        ('Paper Rex', 'PRX', 92),
        ('DRX', 'DRX', 88),
        ('Gen.G', 'GEN', 87),
        ('T1', 'T1', 83),
        ('Rex Regum Qeon', 'RRQ', 80),
        ('Talon Esports', 'TLN', 78),
        ('Team Secret', 'TS', 76),
        ('ZETA DIVISION', 'ZETA', 75),
        ('Global Esports', 'GE', 73),
        ('DetonatioN FocusMe', 'DFM', 72),
        ('BOOM Esports', 'BOOM', 70),
        ('Nongshim RedForce', 'NS', 82),
    ],
    'americas': [
        ('G2 Esports', 'G2', 93),
        ('Sentinels', 'SEN', 90),
        ('NRG Esports', 'NRG', 87),
        ('Leviatan', 'LEV', 86),
        ('LOUD', 'LOUD', 85),
        ('MIBR', 'MIBR', 83),
        ('100 Thieves', '100T', 82),
        ('Cloud9', 'C9', 79),
        ('Evil Geniuses', 'EG', 77),
        ('FURIA', 'FUR', 75),
        ('KRU Esports', 'KRU', 73),
        ('2GAME Esports', '2G', 70),
    ],
    'emea': [
        ('FNATIC', 'FNC', 94),
        ('Team Vitality', 'VIT', 91),
        ('Team Heretics', 'TH', 88),
        ('FUT Esports', 'FUT', 85),
        ('Karmine Corp', 'KC', 83),
        ('Natus Vincere', 'NAVI', 82),
        ('Gentle Mates', 'M8', 80),
        ('BBL Esports', 'BBL', 78),
        ('Team Liquid', 'TL', 77),
        ('GIANTX', 'GX', 75),
        ('KOI', 'KOI', 73),
        ('Apeks', 'APK', 71),
    ],
    'china': [
        ('EDward Gaming', 'EDG', 93),
        ('FunPlus Phoenix', 'FPX', 89),
        ('Trace Esports', 'TE', 85),
        ('All Gamers', 'AG', 82),
        ('Dragon Ranger Gaming', 'DRG', 80),
        ('Bilibili Gaming', 'BLG', 78),
        ('TYLOO', 'TYL', 76),
        ('Nova Esports', 'NOVA', 74),
        ('JDG Esports', 'JDG', 73),
        ('Xi Lai Gaming', 'XLG', 72),
        ('Rare Atom', 'RA', 70),
        ('Wolves Esports', 'WOL', 68),
    ],
}

ROLES = ['Duelist', 'Initiator', 'Controller', 'Sentinel', 'Flex']


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
            for name, code, rating in club_list:
                club = Club(
                    name=name, short_code=code,
                    region_id=region_id,
                    base_rating=rating, current_rating=rating,
                )
                db.session.add(club)

        for role_name in ROLES:
            db.session.add(Role(name=role_name))

        db.session.commit()
        print(f'Seeded {len(REGIONS)} regions, {sum(len(c) for c in CLUBS.values())} clubs, {len(ROLES)} roles.')


if __name__ == '__main__':
    seed()
