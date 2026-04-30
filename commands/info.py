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

    if weak_parts:
        weak_parts.sort(key=lambda x: -x[0])
        lines.append('')
        lines.append('[약점 부위]')
        for _, part_kr, entries in weak_parts:
            lines.append(f'{part_kr} : {" / ".join(entries)}')

    # 약점 속성
    elements = [(w['level'], w['element']) for w in monster.get('weaknesses', []) if w['kind'] == 'element']
    elements.sort(key=lambda x: -x[0])
    if elements:
        lines.append('')
        lines.append('[약점 속성]')
        lines.append(' / '.join(f'{ELEMENT_KR.get(e, e)} {_stars(lv)}' for lv, e in elements))

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
