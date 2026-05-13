RESIST_KR = {
    'fire': '불',
    'water': '물',
    'thunder': '번개',
    'ice': '얼음',
    'dragon': '용',
}


def format_armor(p: dict) -> str:
    name = p.get('name_kr', '?')
    kind = p.get('kind_kr', '')
    rarity = p.get('rarity', '?')
    defense = p.get('defense') or {}
    res = p.get('resistances') or {}
    slots = p.get('slots') or []
    skills = p.get('skills') or []
    crafting = p.get('crafting') or {}
    _set = p.get('_set') or {}

    lines = [f'[방어구] {name} ({kind}, 희귀도 {rarity})']
    if defense:
        lines.append(f'방어력 {defense.get("base","?")} / 최대 {defense.get("max","?")}')

    if res:
        res_str = ' / '.join(f'{RESIST_KR.get(k,k)}{v:+}' for k, v in res.items())
        lines.append(f'내성: {res_str}')

    slot_str = '/'.join(str(s) for s in slots) if slots else '없음'
    lines.append(f'슬롯: {slot_str}')

    # 세트/그룹 보너스 스킬은 별도로 분리
    set_bonus = _set.get('set_bonus') or {}
    group_bonus = _set.get('group_bonus') or {}
    bonus_skill_ids = set()
    if set_bonus.get('skill_id') is not None:
        bonus_skill_ids.add(set_bonus['skill_id'])
    if group_bonus.get('skill_id') is not None:
        bonus_skill_ids.add(group_bonus['skill_id'])

    own_skills = [s for s in skills if s.get('skill_id') not in bonus_skill_ids]
    if own_skills:
        sk_str = ', '.join(f'{s.get("name_kr","")} Lv{s.get("level",1)}' for s in own_skills)
        lines.append(f'스킬: {sk_str}')

    # 세트/그룹 보너스 표시
    if set_bonus:
        ranks_str = ', '.join(
            f'{r.get("pieces","?")}피스 Lv{r.get("skill_level","?")}'
            for r in set_bonus.get('ranks', [])
        )
        lines.append(f'세트 보너스: {set_bonus.get("name_kr","")} ({ranks_str})')

    if group_bonus:
        ranks_str = ', '.join(
            f'{r.get("pieces","?")}피스 Lv{r.get("skill_level","?")}'
            for r in group_bonus.get('ranks', [])
        )
        lines.append(f'그룹 보너스: {group_bonus.get("name_kr","")} ({ranks_str})')

    # 제작 재료
    price = crafting.get('price')
    inputs = crafting.get('inputs') or []
    if inputs or price is not None:
        lines.append('')
        lines.append('[제작]')
        if price is not None:
            lines.append(f'비용 {price}z')
        if inputs:
            mats = ', '.join(f'{i.get("name_kr","")} ×{i.get("quantity",1)}' for i in inputs)
            lines.append(f'재료: {mats}')

    return '\n'.join(lines).rstrip()
