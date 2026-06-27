"""Parse shorthand match notation like 13*-8 W into structured data."""

import re

MAP_LINE_RE = re.compile(r'^(\d{1,2})\*?-(\d{1,2})\*?\s+([WL])$')
SERIES_LINE_RE = re.compile(r'^[=\->]*(\d)\*?-(\d)\*?\s*\(?(\d+)%?\)?\s*(.*)$')


def parse_map_line(line):
    """Parse a single map line like '13*-8 W' or '10-13* L'.

    Returns: {'our_score': 13, 'their_score': 8, 'result': 'W'}
             or None if invalid.
    The * marks our team's score. W/L confirms our result.
    """
    m = MAP_LINE_RE.match(line.strip())
    if not m:
        return None

    score_a = int(m.group(1))
    score_b = int(m.group(2))
    result = m.group(3)

    has_star_on_a = '*' in line.split('-')[0]
    has_star_on_b = '*' in line.split('-')[1]

    if has_star_on_a and not has_star_on_b:
        our_score, their_score = score_a, score_b
    elif has_star_on_b and not has_star_on_a:
        our_score, their_score = score_b, score_a
    else:
        our_score, their_score = score_a, score_b

    return {'our_score': our_score, 'their_score': their_score, 'result': result}


def parse_series_line(line):
    """Parse a series result line like '=>2*-0(98%) 1-0'.

    Returns: {'our_maps': 2, 'their_maps': 0, 'pct': 98, 'extra': '1-0'}
    """
    m = SERIES_LINE_RE.match(line.strip())
    if not m:
        return None

    maps_a = int(m.group(1))
    maps_b = int(m.group(2))
    pct = int(m.group(3)) if m.group(3) else None
    extra = m.group(4).strip() if m.group(4) else ''

    has_star_on_a = '*' in line.split('-')[0]
    if has_star_on_a:
        our_maps, their_maps = maps_a, maps_b
    else:
        our_maps, their_maps = maps_b, maps_a

    return {'our_maps': our_maps, 'their_maps': their_maps, 'pct': pct, 'extra': extra}


def parse_match_block(text):
    """Parse a full match block:

    TEAM_NAME
    13*-3 W
    10-13* W
    =>2*-0(98%) 1-0

    Returns a dict with 'opponent', 'maps', 'series'.
    """
    lines = [l.strip() for l in text.strip().split('\n') if l.strip()]
    if len(lines) < 2:
        return None

    opponent = lines[0]
    maps = []
    series = None

    for line in lines[1:]:
        map_data = parse_map_line(line)
        if map_data:
            maps.append(map_data)
            continue
        series_data = parse_series_line(line)
        if series_data:
            series = series_data

    return {'opponent': opponent, 'maps': maps, 'series': series}


def maps_to_shorthand(maps_data):
    """Convert map data to shorthand lines. Inverse of parse_map_line.

    maps_data: list of {'our_score': int, 'their_score': int, 'result': str}
    Returns list of strings.
    """
    lines = []
    for m in maps_data:
        our = m['our_score']
        their = m['their_score']
        result = m['result']
        lines.append(f'{our}*-{their} {result}')
    return lines
