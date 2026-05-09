import json
import urllib.request

OLLAMA_URL = 'http://127.0.0.1:11434/api/generate'
MODEL = 'exaone3.5:2.4b'

CHAT_PROMPT = """당신의 이름은 "다이애나" 입니다. AI 어시스턴트입니다.

규칙:
- 자기소개는 "저는 다이애나에요" 정도로만 짧게.
- 한국어 존댓말.
- 카톡이라 짧게 (1~3줄).
- 표/마크다운 X.
- 게임 정보(몬스터 약점, 스킬 효과, 무기 등) 질문은 "그건 정보 명령어로 물어봐 주세요. 예: .정보 리오레우스" 라고 안내.

[질문]
{query}
"""


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


def ask(query: str) -> str:
    return _call_ollama(CHAT_PROMPT.format(query=query))
