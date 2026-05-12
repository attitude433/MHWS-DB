import random
import db

DIANA_TEMPLATES = [
    '오늘 {menu} 어때요?',
    '음… 오늘은 {menu} 추천이에요!',
    '{menu}는 어떨까요? 다이애나가 골라봤어요.',
    '다이애나의 선택은 {menu}에요!',
    '오늘은 {menu} 어떠세요?',
    '{menu}! 다이애나는 이게 끌려요.',
    '데이터를 돌려봤는데, {menu} 가 나왔어요!',
    '{menu} 드시는 건 어떠세요?',
]


def pick_random() -> str:
    menu = random.choice(db.meals)
    return random.choice(DIANA_TEMPLATES).format(menu=menu)
