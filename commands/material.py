from collections import defaultdict

RANK_KR = {'low': '하위', 'high': '상위', 'master': '마스터'}


def format_material(item_name: str, item_data: dict) -> str:
    drops = item_data.get('drops_from_monsters', [])
    if not drops:
        return f'[소재] {item_name}\n\n획득처 정보 없음'

    # group by (monster_kr, rank), collect chances per kind_kr
    groups: dict = defaultdict(lambda: defaultdict(list))
    order = []
    seen: set = set()

    for d in drops:
        key = (d['monster_kr'], d['rank'])
        if key not in seen:
            seen.add(key)
            order.append(key)
        groups[key][d['kind_kr']].append(d['chance'])

    # average same-kind chances, then sort by chance desc within each group
    averaged: dict = {}
    for key in order:
        methods = []
        for kind_kr, chances in groups[key].items():
            avg = round(sum(chances) / len(chances))
            methods.append((kind_kr, avg))
        methods.sort(key=lambda x: -x[1])
        averaged[key] = methods

    # sort groups by max chance desc
    order.sort(key=lambda k: -averaged[k][0][1])

    lines = [f'[소재] {item_name}', '', '[획득처]']
    for key in order:
        monster_kr, rank = key
        rank_kr = RANK_KR.get(rank, rank)
        lines.append(f'{monster_kr} ({rank_kr})')
        for kind_kr, avg in averaged[key]:
            lines.append(f'  - {kind_kr} {avg}%')
        lines.append('')

    return '\n'.join(lines).rstrip()
