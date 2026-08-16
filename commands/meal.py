import random
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
    lambda m: f'다이애나의 선택은 {m}에요!',
    lambda m: f'오늘은 {m} 어떠세요?',
    lambda m: f'{m}! 다이애나는 이게 끌려요.',
    lambda m: f'데이터를 돌려봤는데, {_josa(m, "이", "가")} 나왔어요!',
    lambda m: f'{m} 드시는 건 어떠세요?',
]

SPECIAL_MENU = '단식'
SPECIAL_MENU_PROB = 0.03
_REGULAR_MEALS = [m for m in db.meals if m != SPECIAL_MENU]


def pick_random() -> str:
    if random.random() < SPECIAL_MENU_PROB:
        menu = SPECIAL_MENU
    else:
        menu = random.choice(_REGULAR_MEALS)
    return random.choice(DIANA_TEMPLATES)(menu)
