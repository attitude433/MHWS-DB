ELEMENT_KR = {'fire': '화', 'water': '수', 'thunder': '뇌', 'ice': '빙', 'dragon': '용'}
STATUS_KR = {'paralysis': '마비', 'poison': '독', 'sleep': '수면', 'blastblight': '폭파'}
EFFECT_KR = {'flash': '섬광', 'stun': '기절', 'exhaust': '소모'}
PHYS_KR = [('slash', '참격'), ('blunt', '타격'), ('pierce', '탄')]


def _stars(level: int) -> str:
    return '★' * level


def format_info(monster: dict) -> str:
    lines = [monster['name_kr']]

    # 약점 부위
    weak_parts = []
    for part in monster.get('parts', []):
        mult = part['multipliers']
        entries = []
        for key, label in PHYS_KR:
            val = round(mult[key] * 100)
            if val >= 45:
                entries.append(f'{label} {val}')
        if entries:
            max_val = max(round(mult[k] * 100) for k, _ in PHYS_KR)
            weak_parts.append((max_val, part['part_kr'], entries))

    lines.append('')
    lines.append('[약점 부위]')
    if weak_parts:
        weak_parts.sort(key=lambda x: -x[0])
        for _, part_kr, entries in weak_parts:
            lines.append(f'{part_kr} : {" / ".join(entries)}')
    else:
        lines.append('(45% 이상 부위 없음 — 약점특효 미발동)')

    # 특수 상태 부위 (hide)
    hide_parts = monster.get('hide_parts', [])
    if hide_parts:
        lines.append('')
        lines.append('[특수 상태 부위]')
        seen = set()
        for part in hide_parts:
            mult = part['multipliers']
            vals = tuple(round(mult[key] * 100) for key, _ in PHYS_KR)
            if vals in seen:
                continue
            seen.add(vals)
            entries = [f'{label} {val}' for (_, label), val in zip(PHYS_KR, vals)]
            lines.append(f'{part["part_kr"]} : {" / ".join(entries)}')

    # 약점 속성
    elements = [(w['level'], w['element'], w.get('note')) for w in monster.get('weaknesses', []) if w['kind'] == 'element']
    elements.sort(key=lambda x: -x[0])
    if elements:
        lines.append('')
        lines.append('[약점 속성]')
        parts_out = []
        for lv, e, note in elements:
            s = f'{ELEMENT_KR.get(e, e)} {_stars(lv)}'
            if note:
                s += f' ({note})'
            parts_out.append(s)
        lines.append(' / '.join(parts_out))

    # 상태이상
    statuses = [(w['level'], w['status']) for w in monster.get('weaknesses', []) if w['kind'] == 'status']
    statuses.sort(key=lambda x: -x[0])
    if statuses:
        lines.append('')
        lines.append('[상태이상]')
        lines.append(' / '.join(f'{STATUS_KR.get(s, s)} {_stars(lv)}' for lv, s in statuses))

    # 특수효과
    effects = [(w['level'], w['effect']) for w in monster.get('weaknesses', []) if w['kind'] == 'effect']
    effects.sort(key=lambda x: -x[0])
    if effects:
        lines.append('')
        lines.append('[특수효과]')
        lines.append(' / '.join(f'{EFFECT_KR.get(e, e)} {_stars(lv)}' for lv, e in effects))

    # 함정·도구
    valid_items = monster.get('valid_items', [])
    if valid_items:
        effective = [v['item'] for v in valid_items if v['effective']]
        ineffective = [v['item'] for v in valid_items if not v['effective']]
        lines.append('')
        lines.append('[함정·도구]')
        if effective:
            lines.append(f'유효: {", ".join(effective)}')
        if ineffective:
            lines.append(f'무효: {", ".join(ineffective)}')

    return '\n'.join(lines)
