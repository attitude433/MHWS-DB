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

KST = ZoneInfo('Asia/Seoul')

_cache: dict[date, list[str]] = {}

# 제외 키워드 — 가벼운 톤에 안 맞는 것들.
BLACKLIST = (
    # 정치·국가
    '독립', '해방', '광복', '건국', '국경일', '국가', '국민', '혁명', '선포', '제정', '각성',
    # 추모·전쟁
    '기억', '추모', '전사', '학살', '테러', '전쟁', '희생', '순국', '전몰', '학도',
    # 종교
    '부처님', '예수', '성탄', '주현', '재림', '성공회', '니케아', '가톨릭', '천주교', '기독교',
    # 사회 이슈 — 가볍게 다루기 어려운 것
    '인종차별', '인권', '빈곤', '학대', '자살', '폭력', '난민', '에이즈',
)


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
        if any(kw in full for kw in BLACKLIST):
            continue
        short = _short_name(full)
        if not short or short in kept:
            continue
        kept.append(short)

    _cache[today] = kept
    return kept


def morning_holiday_line() -> str | None:
    """모닝 인사에 붙일 1줄. 없으면 None."""
    items = fetch_today()
    if not items:
        return None
    today = datetime.now(KST).date()
    pick = random.sample(items, min(2, len(items)))
    joined = ', '.join(pick)
    templates = [
        f'오늘은 {joined}이래요!',
        f'{today.month}월 {today.day}일은 {joined}이래요',
        f'오늘 {joined}인 거 알고 있었어요? 신기해요!',
        f'오늘은 {joined}이라네요',
    ]
    return random.choice(templates)
