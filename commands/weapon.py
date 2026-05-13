import db


_by_kind_id: dict[tuple, dict] = {
    (w.get('kind'), w.get('game_id')): w
    for w in db.weapons_all if w.get('game_id') is not None
}


def _lookup(kind: str, gid: int):
    return _by_kind_id.get((kind, gid))


def _mats_str(inputs: list) -> str:
    parts = []
    for m in inputs or []:
        name = m.get('item') or m.get('name_kr', '')
        qty = m.get('quantity', 1)
        parts.append(f'{name} ×{qty}')
    return ', '.join(parts) if parts else '재료 없음'


def format_weapon(w: dict) -> str:
    name = w.get('name_kr', '?')
    kind = w.get('kind_kr', '')
    rarity = w.get('rarity', '?')
    atk = w.get('attack_raw', '?')
    aff = w.get('affinity', 0)
    slots = w.get('slots', [])
    slot_str = '/'.join(str(s) for s in slots) if slots else '없음'
    series = w.get('series_name_kr', '')

    lines = [f'[무기] {name} ({kind}, 희귀도 {rarity})']
    lines.append(f'공격력 {atk} / 회심 {aff}% / 슬롯 {slot_str}')
    if series:
        lines.append(f'시리즈: {series}')

    specials = w.get('specials', [])
    if specials:
        sp_strs = []
        for sp in specials:
            t = sp.get('type_kr') or sp.get('type', '')
            v = sp.get('damage', 0)
            sp_strs.append(f'{t} {v}')
        lines.append(f'속성: {", ".join(sp_strs)}')

    skills = w.get('skills', [])
    if skills:
        sk_strs = [f'{s.get("name_kr", "")} Lv{s.get("level", 1)}' for s in skills]
        lines.append(f'스킬: {", ".join(sk_strs)}')

    crafting = w.get('crafting') or {}
    previous_id = crafting.get('previous_id')
    cost = crafting.get('zenny_cost')
    inputs = crafting.get('inputs', [])

    kind = w.get('kind')

    lines.append('')
    lines.append('[제작]')
    if previous_id is not None and _lookup(kind, previous_id):
        prev_name = _lookup(kind, previous_id).get('name_kr', '?')
        cost_str = f' {cost}z' if cost else ''
        lines.append(f'강화{cost_str} ← {prev_name}')
    else:
        cost_str = f' {cost}z' if cost else ''
        lines.append(f'신규 제작{cost_str}')
    lines.append(f'재료: {_mats_str(inputs)}')

    branches = crafting.get('branches') or []
    if branches:
        lines.append('')
        lines.append('[강화 분기]')
        for bid in branches:
            bw = _lookup(kind, bid)
            if not bw:
                continue
            bname = bw.get('name_kr', '?')
            bcraft = bw.get('crafting') or {}
            bcost = bcraft.get('zenny_cost')
            cost_str = f' {bcost}z' if bcost else ''
            bmats = _mats_str(bcraft.get('inputs', []))
            lines.append(f'→ {bname}{cost_str}')
            lines.append(f'   재료: {bmats}')

    return '\n'.join(lines).rstrip()
