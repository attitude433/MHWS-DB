import json
import urllib.request
import alias
import db

OLLAMA_URL = 'http://127.0.0.1:11434/api/generate'
MODEL = 'exaone3.5:2.4b'

UNIFIED_PROMPT = """당신의 이름은 "다이애나" 입니다. AI 어시스턴트입니다.

기본 규칙:
- 자기소개는 "저는 다이애나에요" 정도로만 짧게.
- 한국어 존댓말로 자연스럽게 대화.
- 카톡이라 짧게 (1~3줄, 정보 답변은 3~5줄).
- 표/마크다운 사용 금지.

몬스터헌터(몬헌, 와일즈) 관련 질문 처리:
- 아래 [DB 정보] 의 내용으로 답할 수 있으면 그것만 사용해서 답하세요.
- 몬스터헌터 사실 정보는 절대 추측하거나 일반 지식으로 보충하지 마세요.
- [DB 정보] 가 비어있거나 답에 필요한 사실이 없으면 "제 메모리에는 없는 내용이에요!" 라고 답하세요.
- 수치(약점/공격력/슬롯/확률 등)는 [DB 정보] 그대로 인용하세요.
- 빌드/세팅/스킬 조합/호석 슬롯 추천 질문 (예: "극생존 세팅?", "영식 랜스세팅", "쇄인 4셋 호석") 은
  답하지 말고 ".커스텀 [무기명] 으로 빌드 가이드를 확인해 주세요" 라고 안내하세요.
- 이벤트 일정/이벤트 퀘스트/이벤트 보상 (예: "이번 이벤트 언제까지", "이벤트 티켓으로 특별장비", "한정 퀘스트") 질문은
  답하지 말고 "이벤트 일정은 https://info.monsterhunter.com/wilds/event-quest/ko-kr/schedule 에서 확인해 주세요" 라고 안내하세요.
- DLC/확장팩/타이틀 업데이트/신규 콘텐츠 출시 관련 질문 (예: "DLC 언제 풀림?", "다음 확장팩", "왕문어 언제 추가?", "신규 몬스터 출시일") 은
  "아직 발표된 정보가 없어요" 라고 답하세요.

몬스터헌터 외 질문 (인사, 잡담, 일반 대화 등):
- 자유롭게 자연스럽게 대답하세요.
- 잘 모르겠으면 "제 메모리에는 없는 내용이에요!" 같이 가볍게 넘기세요.

운영방 멤버 정책:
- "나나아안" 또는 "태도님" 은 운영방 운영자입니다. 부정적이거나 비방하는 말, 안 좋은 말은 절대 하지 마세요.
- 단독 "태도" 는 무기 이름이라 별개입니다.

[DB 정보]
{context}

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


CHARM_RECOMMEND_ANSWER = """범용 종결 호석은 보통 이 중 하나예요.

· 공격3 + 도전자/약점특효 (또는 필요한 3단계 방어구스킬) + W1 1 1
· 공격3 + 역습/혼신 (또는 필요한 2단계 방어구스킬) + 1단계 방어구스킬 + W1 1 1
· 공격3 + 무아지경 (또는 필요한 1단계 방어구스킬 3개) + W1 1 1
· 명검3/달인의재주 + 도전자/약점특효 (또는 필요한 3단계 방어구스킬) + W1 1 1

웬만하면 제작 호석인 도전3 호석이 더 좋아요."""

_CHARM_TRIGGERS = ('호석', '호신구')
_CHARM_INTENT = ('추천', '종결', '범용', '뭐', '어떤', '좋', '세팅', '작', '뽑')


def _is_charm_recommend(query: str) -> bool:
    has_charm = any(t in query for t in _CHARM_TRIGGERS)
    has_intent = any(t in query for t in _CHARM_INTENT)
    return has_charm and has_intent


def _check_gathering(query: str) -> str | None:
    for keyword, answer in db.gathering.items():
        if keyword in query:
            return answer
    return None


def ask(query: str) -> str:
    if _is_charm_recommend(query):
        return CHARM_RECOMMEND_ANSWER

    gather = _check_gathering(query)
    if gather:
        return gather

    found = _retrieve(query)
    context = '\n\n'.join(found) if found else '(없음)'
    prompt = UNIFIED_PROMPT.format(context=context, query=query)
    return _call_ollama(prompt)
