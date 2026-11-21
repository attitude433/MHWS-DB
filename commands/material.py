from collections import defaultdict

RANK_KR = {'low': '하위', 'high': '상위', 'master': '마스터', 'tempered': '역전', 'arch-tempered': '역전왕'}


def _format_drops(drops: list) -> list[str]:
    groups: dict = defaultdict(lambda: defaultdict(list))
    order = []
    seen: set = set()
    for d in drops:
        key = (d['monster_kr'], d['rank'])
        if key not in seen:
            seen.add(key)
            order.append(key)
        groups[key][d['kind_kr']].append(d['chance'])

    averaged: dict = {}
    for key in order:
        methods = []
        for kind_kr, chances in groups[key].items():
            avg = round(sum(chances) / len(chances))
            methods.append((kind_kr, avg))
        methods.sort(key=lambda x: -x[1])
        averaged[key] = methods

    order.sort(key=lambda k: -averaged[k][0][1])

    lines = ['[획득처]']
    for key in order:
        monster_kr, rank = key
        rank_kr = RANK_KR.get(rank, rank)
        header = f'{monster_kr} ({rank_kr})' if rank_kr else monster_kr
        lines.append(header)
        for kind_kr, avg in averaged[key]:
            lines.append(f'  - {kind_kr} {avg}%')
        lines.append('')
    return lines


def _format_exchanges(exchanges: list) -> list[str]:
    lines = ['[NPC 교환]']
    for e in exchanges:
        npc = e.get('npc_kr', '')
        give_item = e.get('give_item_kr', '')
        give_amt = e.get('give_amount', 1)
        recv_amt = e.get('receive_amount', 1)
        limit = e.get('limit')
        suffix = f' ({limit}회)' if limit else ''
        lines.append(f'{npc}: {give_item} x{give_amt} → x{recv_amt}{suffix}')
    lines.append('')
    return lines


def crafted_equipment(item_data: dict, limit: int = 10) -> tuple[str, str]:
    weapons = list(dict.fromkeys(w.get('weapon_name_kr', '') for w in item_data.get('used_in_weapons', [])))
    armor_sets = list(dict.fromkeys(a.get('set_name_kr', '') for a in item_data.get('used_in_armor', [])))

    def _join(names: list) -> str:
        s = ', '.join(names[:limit])
        return s + (f' 외 {len(names) - limit}개' if len(names) > limit else '')

    return _join(weapons), _join(armor_sets)


def format_material(item_name: str, item_data: dict) -> str:
    drops = item_data.get('drops_from_monsters', [])
    exchanges = item_data.get('npc_exchanges', [])
    gathering = item_data.get('gathering', [])
    recipes = item_data.get('recipes', [])
    notes = item_data.get('notes', [])
    weapons, armors = crafted_equipment(item_data)

    if not drops and not exchanges and not gathering and not recipes and not notes and not weapons and not armors:
        return f'[소재] {item_name}\n\n획득처 정보 없음'

    lines = [f'[소재] {item_name}', '']
    if drops:
        lines.extend(_format_drops(drops))
    if exchanges:
        lines.extend(_format_exchanges(exchanges))
    if gathering:
        lines.append('[채집]')
        for g in gathering:
            lines.append(f'  - {g}')
        lines.append('')
    if recipes:
        lines.append('[조합]')
        for r in recipes:
            inputs = ' + '.join(r.get('inputs', []))
            amt = r.get('amount', 1)
            lines.append(f'  - {inputs} → x{amt}')
        lines.append('')
    if notes:
        lines.append('[기타]')
        for n in notes:
            lines.append(f'  - {n}')
        lines.append('')
    if weapons or armors:
        lines.append('[제작 장비]')
        if weapons:
            lines.append(f'  - 무기: {weapons}')
        if armors:
            lines.append(f'  - 방어구: {armors}')
        lines.append('')

    return '\n'.join(lines).rstrip()
