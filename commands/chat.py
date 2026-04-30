import os
import json
import anthropic
import db

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])
    return _client


def _extract_context(query: str) -> str:
    tokens = query.replace(' ', '').lower()
    parts = []

    for m in db.monsters:
        name = m['name_kr'].replace(' ', '')
        if name in tokens or tokens in name:
            parts.append(f'[몬스터] {m["name_kr"]}: 약점={json.dumps(m.get("weaknesses", []), ensure_ascii=False)}')

    for s in db.skills:
        name = s['name_kr'].replace(' ', '')
        if name in tokens or tokens in name:
            desc = s.get('description_kr', '')
            parts.append(f'[스킬] {s["name_kr"]}: {desc}')

    return '\n'.join(parts[:10])


SYSTEM_PROMPT = (
    '너는 몬스터헌터 와일즈 전문 봇이야. '
    '아래 DB 정보 안에서만 답해. 모르면 "DB에 없는 정보입니다"라고 해. '
    '답변은 카카오톡에 맞게 짧고 명확하게.'
)


async def ask(query: str) -> str:
    context = _extract_context(query)
    user_msg = f'{query}\n\n[DB 참고]\n{context}' if context else query

    resp = _get_client().messages.create(
        model='claude-haiku-4-5-20251001',
        max_tokens=500,
        system=SYSTEM_PROMPT,
        messages=[{'role': 'user', 'content': user_msg}],
    )
    return resp.content[0].text
