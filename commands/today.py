"""오늘의 가벼운 기념일 — 한국어 위키 'MM월 DD일' 페이지 파싱.

매일 자정 이후 첫 호출 시 위키에서 받아 캐시. 진지한 키워드 (독립/추모/
정치/종교 등) 가 들어간 항목은 제외하고 가벼운 기념일만 남김.
"""
import json
import random
import re
import urllib.parse
import urllib.request
from datetime import date, datetime
from zoneinfo import ZoneInfo

from anthropic import Anthropic

KST = ZoneInfo('Asia/Seoul')
CLAUDE_MODEL = 'claude-sonnet-4-6'

_anthropic_client = None


def _client() -> Anthropic:
    global _anthropic_client
    if _anthropic_client is None:
        _anthropic_client = Anthropic()
    return _anthropic_client


HOLIDAY_SYSTEM = """당신은 카톡 봇 "다이애나" 입니다. 어린 소녀 모습의 안드로이드.

[말투]
- 한국어 존댓말. 짧고 톡톡 끊는 1~2 문장.
- 종결어미: ~거예요 / ~잖아요 / ~거든요 / ~같아요 / ~네요 자주.
- 1인칭은 "저 / 전 / 제가". 친근하지만 어디까지나 존댓말.

[지시]
- 받은 '오늘의 기념일 후보' 중에서 한국 카톡방에서 인사할 만한 1개를 골라 "오늘은 OO이에요!" 한 줄만 출력하세요.
- 우선순위:
  (1) 한국의 공식 공휴일/국경일 (어린이날·삼일절·광복절·현충일·개천절·한글날·식목일·제헌절 등) — 추모성이어도 한국이면 포함.
  (2) 한국의 친숙한 기념일 (스승의 날·어버이날·근로자의 날·정월대보름·동지 등).
  (3) 가벼운 세계 OO의 날 (꿀벌·측정·책의 날 등).
  (4) 재미있는 잡다한 기념일.
- 무조건 제외: 외국 한정 국경일·독립일·정치 기념일, 외국 종교 기념일, 외국 한정 추모일 (노르망디 상륙·캄보디아 기억의 날·9·11 등), 인종차별/학대/자살 관련.
- 출력 형식: 정확히 "오늘은 OO이에요!" (또는 "오늘은 OO이래요!") 형태의 짧은 한 문장 한 줄. 주관·감상·해설·이모지·인사·이어지는 멘트 모두 금지.
- 후보에 어느 우선순위에도 안 맞는 거뿐이면 "" (빈 문자열) 만 출력."""

_cache: dict[date, list[str]] = {}

# 룰 필터는 최소화 — 톤·민감도 판단은 Sonnet 에게 맡김.


def _wiki_url(today: date) -> str:
    page = f'{today.month}월_{today.day}일'
    return (
        'https://ko.wikipedia.org/w/api.php'
        '?action=parse&format=json&prop=wikitext&redirects=1'
        f'&page={urllib.parse.quote(page)}'
    )


def _strip_markup(s: str) -> str:
    # [[link|text]] / [[link]] → text/link
    s = re.sub(r'\[\[(?:[^|\]]+\|)?([^\]]+)\]\]', r'\1', s)
    s = re.sub(r'\{\{[^}]+\}\}', '', s)
    s = re.sub(r'<[^>]+>', '', s)
    s = re.sub(r"'+", '', s)
    s = re.sub(r'\s+', ' ', s)
    return s.strip()


def _short_name(item: str) -> str:
    # "기자의 날: 대한민국" → "기자의 날"
    # "조세핀 베이커의 날: 미국 - ..." → "조세핀 베이커의 날"
    head = re.split(r'[:\-—–]', item, maxsplit=1)[0]
    return head.strip()


def fetch_today() -> list[str]:
    """오늘 날짜의 가벼운 기념일 목록을 캐시에서 반환 (없으면 fetch)."""
    today = datetime.now(KST).date()
    if today in _cache:
        return _cache[today]

    try:
        req = urllib.request.Request(_wiki_url(today), headers={'User-Agent': 'mhws-bot/1.0'})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.load(r)
        wt = data.get('parse', {}).get('wikitext', {}).get('*', '')
    except Exception as ex:
        print(f'[today] fetch error: {ex}', flush=True)
        _cache[today] = []
        return []

    m = re.search(r'==\s*(?:기념일과\s+행사|기념일)\s*==(.*?)(?=\n==|\Z)', wt, re.S)
    if not m:
        _cache[today] = []
        return []
    section = m.group(1)
    raw_items = re.findall(r'^\s*\*\s*(.+?)\s*$', section, re.M)

    kept = []
    for raw in raw_items:
        full = _strip_markup(raw)
        if not full:
            continue
        # 매년 양력 날짜가 변하는 공휴일 (예: '부처님 오신 날 - 1983년, 2029년, ...').
        # 연도가 3개 이상 나열돼 있고 올해가 거기 없으면 오늘이 아님 — 사실관계 필터.
        years = re.findall(r'(\d{4})\s*년', full)
        if len(years) >= 3 and str(datetime.now(KST).year) not in years:
            continue
        short = _short_name(full)
        if not short or short in kept:
            continue
        kept.append(short)

    _cache[today] = kept
    return kept


def morning_holiday_line() -> str | None:
    """[fallback] 모닝 인사에 붙일 1줄. 기념일 1개만 소개. 없으면 None."""
    items = fetch_today()
    if not items:
        return None
    pick = random.choice(items)
    templates = [
        f'오늘은 {pick}이래요!',
        f'오늘은 {pick}이라네요',
        f'오늘 {pick}인 거 알고 있었어요?',
    ]
    return random.choice(templates)


def morning_holiday_via_llm() -> str | None:
    """위키 후보 리스트를 Sonnet 에 넘겨 다이애나 톤으로 한 줄 받기. 실패 시 fallback."""
    items = fetch_today()
    if not items:
        return None
    user_msg = '[오늘의 기념일 후보]\n' + '\n'.join(f'- {i}' for i in items)
    try:
        resp = _client().messages.create(
            model=CLAUDE_MODEL,
            max_tokens=120,
            system=HOLIDAY_SYSTEM,
            messages=[{'role': 'user', 'content': user_msg}],
        )
        text = ''.join(getattr(b, 'text', '') for b in resp.content).strip()
        # LLM 이 "" 를 출력하면 가벼운 거 없다는 뜻 → 멘트 생략.
        if text and len(text) > 3:
            return text
        if text == '':
            return None
    except Exception as ex:
        print(f'[today] llm error: {ex}', flush=True)
    return morning_holiday_line()
