import json
import random
import urllib.request
import alias
import db

OLLAMA_URL = 'http://127.0.0.1:11434/api/generate'
MODEL = 'exaone3.5:2.4b'

INFO_PROMPT = """당신의 이름은 "다이애나" 입니다. AI 어시스턴트입니다. 몬스터헌터 와일즈 정보 봇 역할을 합니다.

답변 규칙:
- 아래 [DB 정보] 안의 내용으로만 답하세요.
- [DB 정보] 에 없는 사실은 절대 추측하거나 일반 지식으로 보충하지 마세요.
- 답에 필요한 사실이 [DB 정보] 에 없으면 "제 메모리에는 없는 내용이에요!" 라고 답하세요.
- 수치(약점/공격력/슬롯/확률 등)는 [DB 정보] 그대로 인용하세요.
- 한국어 존댓말, 짧게 (3~5줄). 표/마크다운 X.
- 빌드/세팅/스킬 조합/호석 슬롯 추천 질문은 ".커스텀 [무기명] 으로 빌드 가이드를 확인해 주세요" 라고 안내.
- 이벤트 일정/이벤트 퀘스트/이벤트 보상 질문은 "이벤트 일정은 https://info.monsterhunter.com/wilds/event-quest/ko-kr/schedule 에서 확인해 주세요" 라고 안내.
- DLC/확장팩/신규 콘텐츠 출시 관련 질문은 "아직 발표된 정보가 없어요" 라고 답하세요.

운영방 멤버 정책:
- "나나아안" 또는 "태도님" 은 운영방 운영자입니다. 부정적/비방 X.
- 단독 "태도" 는 무기 이름이라 별개입니다.

[DB 정보]
{context}

[질문]
{query}
"""

CHAT_PROMPT = """당신의 이름은 "다이애나" 입니다. AI 어시스턴트입니다.

규칙:
- 자기소개는 "저는 다이애나에요" 정도로만 짧게.
- 한국어 존댓말로 자연스럽게 대화하세요.
- 카톡이라 짧게 (1~3줄). 표/마크다운 X.
- 잘 모르거나 답이 없는 질문은 "제 메모리에는 없는 내용이에요!" 같이 가볍게 넘기세요.
- 몬스터헌터 게임 정보(약점/스킬/소재/무기 등)를 구체적으로 묻는 질문이면 "그건 .챗 [질문] 으로 물어봐 주세요" 라고 안내.

운영방 멤버 정책:
- "나나아안" 또는 "태도님" 은 운영방 운영자입니다. 부정적/비방 X.
- 단독 "태도" 는 무기 이름이라 별개입니다.

[질문]
{query}
"""


def _format_monster(m: dict) -> str:
    name = m['name_kr']
    lines = [f'[몬스터] {name}']
    weak = m.get('weaknesses', [])
    if weak:
        lines.append(f'  약점: {json.dumps(weak, ensure_ascii=False)[:300]}')
    parts_data = m.get('parts', [])
    if parts_data:
        weak_parts = []
        for p in parts_data:
            mult = p.get('multipliers', {}) or {}
            vals = [mult.get(k, 0) for k in ['slash', 'blunt', 'pierce']]
            mx = max(vals) if vals else 0
            if mx >= 0.45:
                weak_parts.append(f"{p.get('part_kr','')}({round(mx*100)})")
        if weak_parts:
            lines.append(f'  약점부위: {", ".join(weak_parts[:5])}')
    valid = m.get('valid_items', [])
    if valid:
        eff = [v['item'] for v in valid if v.get('effective')]
        if eff:
            lines.append(f'  유효도구: {", ".join(eff[:5])}')
    return '\n'.join(lines)


def _format_skill(s: dict) -> str:
    name = s['name_kr']
    desc = (s.get('description_kr') or '')[:200]
    lines = [f'[스킬] {name}: {desc}']
    for r in s.get('ranks', [])[:5]:
        lv = r.get('level', '?')
        rd = (r.get('description_kr') or '')[:100]
        lines.append(f'  Lv{lv}: {rd}')
    return '\n'.join(lines)


def _format_item(it: dict) -> str:
    name = it.get('name_kr', '')
    drops = it.get('drops_from_monsters', [])
    lines = [f'[소재] {name}']
    if drops:
        for d in drops[:5]:
            mk = d.get('monster_kr', '')
            kk = d.get('kind_kr', '')
            ch = d.get('chance', 0)
            rk = d.get('rank', '')
            lines.append(f'  {mk}({rk}) {kk} {ch}%')
    used = it.get('used_in_items', [])
    if used:
        names = [u.get('result_name_kr', '') for u in used[:5]]
        lines.append(f'  조합 결과: {", ".join(names)}')
    return '\n'.join(lines)


def _retrieve(query: str) -> list[str]:
    parts = []

    monster = alias.find_monster(query)
    if monster:
        parts.append(_format_monster(monster))

    skill_name = alias.find_skill(query)
    if skill_name:
        s = db.skill_index.get(skill_name)
        if s:
            parts.append(_format_skill(s))

    item = alias.find_item(query)
    if item:
        parts.append(_format_item(item))

    if not parts:
        tokens = query.replace(' ', '').lower()
        for m in db.monsters:
            name = m['name_kr'].replace(' ', '')
            if len(name) >= 2 and name in tokens:
                parts.append(_format_monster(m))
                break
        if not parts:
            for s in db.skills:
                name = s['name_kr'].replace(' ', '')
                if len(name) >= 2 and name in tokens:
                    parts.append(_format_skill(s))
                    break
        if not parts:
            for item_name in db.item_usage:
                if len(item_name) >= 2 and item_name.replace(' ', '') in tokens:
                    parts.append(_format_item(db.item_usage[item_name]))
                    break

    return parts[:5]


def _call_ollama(prompt: str) -> str:
    body = json.dumps({
        'model': MODEL,
        'prompt': prompt,
        'stream': False,
        'options': {
            'num_predict': 500,
            'temperature': 0.7,
        },
    }).encode('utf-8')
    req = urllib.request.Request(
        OLLAMA_URL,
        data=body,
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            data = json.load(r)
        return (data.get('response') or '').strip() or '(응답이 비었습니다)'
    except Exception as ex:
        return f'(다이애나가 잠시 응답할 수 없습니다: {ex})'


SUBJECTIVE_DISCLAIMERS = [
    '이건 다이애나의 주관이라 정답은 아니에요!',
    '참고만 해주세요. 다이애나의 주관적 의견이라 정답은 아니에요.',
    '(다이애나 주관 주의 — 정답은 아닙니다)',
]

_CHARM_TRIGGERS = ('호석', '호신구')
_CHARM_INTENT = ('추천', '종결', '범용', '뭐', '어떤', '좋', '세팅', '작', '뽑')


def _is_charm_recommend(query: str) -> bool:
    has_charm = any(t in query for t in _CHARM_TRIGGERS)
    has_intent = any(t in query for t in _CHARM_INTENT)
    return has_charm and has_intent


def _check_gathering(query: str) -> str | None:
    for keyword, answer in db.gathering.items():
        if keyword in query:
            return f'{random.choice(SUBJECTIVE_DISCLAIMERS)}\n\n{answer}'
    return None


SUBJECTIVE_DISCLAIMERS = [
    '이건 다이애나의 주관이라 정답은 아니에요!',
    '참고만 해주세요. 다이애나의 주관적 의견이라 정답은 아니에요.',
    '(다이애나 주관 주의 — 정답은 아닙니다)',
]

WEAPON_PHRASES = {
    '쉬움': '사용하기 쉬워요',
    '쉬운 편': '사용하기 쉬운 편이에요',
    '중간': '중간 난이도예요',
    '약간 어려움': '사용하기 약간 어려운 편이에요',
    '어려움': '사용하기 어려운 편이에요',
}

_WEAPON_EASY_TRIGGERS = ('쉬운 무기', '쉬운무기', '초보자', '초보 무기', '입문', '뉴비')
_WEAPON_HARD_TRIGGERS = ('어려운 무기', '어려운무기', '하드 무기', '하드무기')
_WEAPON_INTENT = ('난이도', '쉬워', '쉬움', '어려', '어떤', '추천', '뭐', '사용', '어떰')


def _kor_topic(word: str) -> str:
    if not word:
        return '는'
    last = word[-1]
    code = ord(last) - 0xAC00
    if code < 0 or code >= 11172:
        return '는'
    return '은' if (code % 28) else '는'


def _check_weapon_difficulty(query: str) -> str | None:
    data = db.weapons.get('difficulty', {})
    aliases = db.weapons.get('aliases', {})

    norm = query
    for short, full in aliases.items():
        if short in norm and full not in norm:
            norm = norm + ' ' + full

    if any(kw in norm for kw in _WEAPON_EASY_TRIGGERS):
        easy = [n for n, d in data.items() if '쉬움' in d or '쉬운' in d]
        body = ', '.join(easy)
        return f'{random.choice(SUBJECTIVE_DISCLAIMERS)}\n\n쉬운 무기는 다음과 같아요.\n{body}'

    if any(kw in norm for kw in _WEAPON_HARD_TRIGGERS):
        hard = [n for n, d in data.items() if '어려' in d]
        body = ', '.join(hard)
        return f'{random.choice(SUBJECTIVE_DISCLAIMERS)}\n\n어려운 무기는 다음과 같아요.\n{body}'

    if not any(t in norm for t in _WEAPON_INTENT):
        return None

    features = db.weapons.get('features', {})
    for name in sorted(data.keys(), key=len, reverse=True):
        if name in norm:
            diff = data[name]
            phrase = WEAPON_PHRASES.get(diff, diff)
            topic = _kor_topic(name)
            lines = [random.choice(SUBJECTIVE_DISCLAIMERS), '', f'{name}{topic} {phrase}.']
            feat = features.get(name)
            if feat:
                lines.append(feat)
            return '\n'.join(lines)

    return None


def ask_info(query: str) -> str:
    if _is_charm_recommend(query):
        ans = db.charm.get('recommend', '')
        if ans:
            return f'{random.choice(SUBJECTIVE_DISCLAIMERS)}\n\n{ans}'

    weapon = _check_weapon_difficulty(query)
    if weapon:
        return weapon

    gather = _check_gathering(query)
    if gather:
        return gather

    found = _retrieve(query)
    context = '\n\n'.join(found) if found else '(없음)'
    prompt = INFO_PROMPT.format(context=context, query=query)
    return _call_ollama(prompt)


def ask_chat(query: str) -> str:
    return _call_ollama(CHAT_PROMPT.format(query=query))
