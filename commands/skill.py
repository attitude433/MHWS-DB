import db


def format_skill(skill: dict) -> str:
    lines = [
        f'[스킬] {skill["name_kr"]} ({skill["kind_kr"]} / {skill["category_kr"]})',
        '',
        skill['description_kr'],
        '',
        '[레벨별 효과]',
    ]
    for rank in skill.get('ranks', []):
        lines.append(f'Lv{rank["level"]}: {rank["description_kr"]}')
    return '\n'.join(lines)


def format_skill_equipment(skill_name: str, equip: dict) -> str:
    lines = [f'[스킬] {skill_name} - 보유 장비', '']

    accessories = equip.get('accessories', [])
    if accessories:
        lines.append(f'장식주 ({len(accessories)})')
        for a in accessories:
            lines.append(f'- {a["name_kr"]} Lv{a["level"]}')
        lines.append('')

    charms = equip.get('charms', [])
    if charms:
        lines.append(f'호신구 ({len(charms)})')
        for c in charms:
            lines.append(f'- {c["name_kr"]} (Lv{c["level"]})')
        lines.append('')

    armors = equip.get('armor', [])
    if armors:
        from collections import defaultdict
        level_sets: dict = defaultdict(list)
        set_seen: dict = {}
        for a in armors:
            set_name = a.get('set_name_kr') or a['name_kr']
            lv = a.get('level', 0)
            key = (lv, set_name)
            if key not in set_seen:
                set_seen[key] = []
            set_seen[key].append(a['kind_kr'])
        for (lv, set_name), kinds in set_seen.items():
            level_sets[lv].append((set_name, kinds))

        lines.append(f'방어구 ({len(armors)})')
        for lv in sorted(level_sets):
            lines.append(f'[Lv{lv}]')
            for set_name, kinds in sorted(level_sets[lv]):
                lines.append(f'- {set_name}: {", ".join(kinds)}')

    return '\n'.join(lines).rstrip()
