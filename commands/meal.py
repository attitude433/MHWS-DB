import random
import time
import db


def _has_batchim(word: str) -> bool:
    last = word[-1]
    if '가' <= last <= '힣':
        return (ord(last) - 0xAC00) % 28 != 0
    return False


def _josa(word: str, with_bat: str, without_bat: str) -> str:
    return f'{word}{with_bat}' if _has_batchim(word) else f'{word}{without_bat}'


DIANA_TEMPLATES = [
    lambda m: f'오늘 {m} 어때요?',
    lambda m: f'음… 오늘은 {m} 추천이에요!',
    lambda m: f'{_josa(m, "은", "는")} 어떨까요? 다이애나가 골라봤어요.',
    lambda m: f'다이애나의 선택은 {_josa(m, "이에요", "예요")}!',
    lambda m: f'오늘은 {m} 어떠세요?',
    lambda m: f'{m}! 다이애나는 이게 끌려요.',
    lambda m: f'데이터를 돌려봤는데, {_josa(m, "이", "가")} 나왔어요!',
    lambda m: f'{m} 드시는 건 어떠세요?',
]

SPECIAL_MENU = '단식'
SPECIAL_MENU_PROB = 0.03
_REGULAR_MEALS = [m for m in db.meals if m != SPECIAL_MENU]

FASTING_TEMPLATES = [
    '오늘은… 굶으세요! 단식 당첨이에요 😅',
    '이런, 단식이 나와버렸어요. 다이애나 잘못 아니에요!',
    '오늘 하루 속을 비워보래요. 단식 당첨! 🙏',
    '데이터를 돌려봤는데… 오늘은 안 먹는 날이래요.',
    '단식이 나왔네요. 한 번 더 돌리실 거죠? 알아요.',
    '오늘의 메뉴는 없음! 단식이에요. 물은 드셔도 돼요 💧',
]

COOLDOWN_SEC = 600
MAX_USES = 3
_recent = {}
_cooldown_notified = set()
COOLDOWN_LINE = '메뉴는 잠깐씩 쉬면서 골라요~ 10분 뒤에 다시 열어드릴게요!'


def pick_random(uid: int = 0):
    if uid:
        now = time.time()
        times = [t for t in _recent.get(uid, []) if now - t < COOLDOWN_SEC]
        if len(times) >= MAX_USES:
            _recent[uid] = times
            if uid in _cooldown_notified:
                return None
            _cooldown_notified.add(uid)
            return COOLDOWN_LINE
        times.append(now)
        _recent[uid] = times
        _cooldown_notified.discard(uid)
    if random.random() < SPECIAL_MENU_PROB:
        return random.choice(FASTING_TEMPLATES)
    menu = random.choice(_REGULAR_MEALS)
    return random.choice(DIANA_TEMPLATES)(menu)
