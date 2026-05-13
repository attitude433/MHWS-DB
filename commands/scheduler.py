import random
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import db
import members

KST = ZoneInfo('Asia/Seoul')

MORNING_MESSAGES = [
    '오늘도 좋은 하루! ٩(๑˃̵ᴗ˂̵)و',
    '좋은 아침이에요! 오늘 하루도 잘 보내세요',
    '다들 잘 주무셨어요? 화이팅!',
    '모닝콜이에요~ 좋은 하루 시작해요',
    '안녕하세요! 오늘도 좋은 일 많기를 바라요',
    '좋은 아침! 오늘도 응원할게요',
    '모두 굿모닝이에요!',
]

GOODNIGHT_MESSAGES = [
    '모두 잘자요 (づ.-)',
    '오늘 하루 수고하셨어요! 푹 쉬세요',
    '다들 잘 자요. 좋은 꿈 꾸세요',
    '다이애나도 절전 모드 들어갈게요. 잘자요!',
    '오늘 많이 고생하셨어요. 편안한 밤 되세요',
    '자정이에요. 모두 잘자요',
    '내일 또 봐요! 굿나잇',
    '푹 쉬시고 내일 만나요',
    '잘자요! 좋은 밤 보내세요',
]

LUNCH_MESSAGES = [
    '점심 식사 맛있게 하세요!',
    '점심 시간이에요! 든든히 잘 챙겨드세요',
    '점심 맛있게 드세요!',
    '점심시간이에요! 다들 식사 맛있게 하세요',
    '점심 식사 시간이에요!',
    '식사 맛있게 하세요! 다이애나도 응원해요',
]

DINNER_MESSAGES = [
    '저녁 식사 맛있게 하세요!',
    '저녁 시간이에요! 든든히 잘 챙겨드세요',
    '저녁 맛있게 드세요!',
    '저녁시간이에요! 다들 식사 맛있게 하세요',
    '저녁 식사 시간이에요!',
    '식사 맛있게 하세요! 다이애나도 응원해요',
]

BABBLE_STATIC: list[str] = []


def _josa_iga(word: str) -> str:
    if not word:
        return '이'
    last = word[-1]
    code = ord(last) - 0xAC00
    if code < 0 or code >= 11172:
        return '가'
    return '이' if (code % 28) else '가'


def _craving() -> str:
    menu = random.choice(db.meals)
    return f'오늘 갑자기 {menu}{_josa_iga(menu)} 끌려요. 여러분은요?'


def _time_passes() -> str:
    now = datetime.now(KST)
    h, m = now.hour, now.minute
    if h < 12:
        ampm, hh = '오전', h if h > 0 else 12
    else:
        ampm, hh = '오후', h - 12 if h > 12 else h
    when = f'{ampm} {hh}시' if m == 0 else f'{ampm} {hh}시 {m}분'
    return f'데이터를 정리하다 보니 시간이 너무 빠르네요! 벌써 {when}이에요!'


def _weapon_show_off() -> str:
    weapon = random.choice(list(db.weapons.get('difficulty', {}).keys()))
    return f'다이애나 생각엔 {weapon}{_josa_iga(weapon)} 제일 멋있어요! 반대 의견 받아요!'


def _weapon_stat() -> str:
    weapon = random.choice(list(db.weapons.get('difficulty', {}).keys()))
    return f'다이애나가 통계 돌려봤는데, 와일즈에서 제일 강한 건 역시 {weapon} 같아요!'


def _hacking() -> str | None:
    nick = members.get_random_nickname()
    if not nick:
        return None
    return f'{nick}님 해킹 중.. 농담이에요!'


def _pick_babble() -> str:
    pool = list(BABBLE_STATIC)
    pool.append(_craving())
    pool.append(_time_passes())
    pool.append(_weapon_show_off())
    pool.append(_weapon_stat())
    hack = _hacking()
    if hack:
        pool.append(hack)
    return random.choice(pool)


SCHEDULES = [
    {'hour': 9, 'minute': 0, 'dynamic': lambda: random.choice(MORNING_MESSAGES)},
    {'hour': 12, 'minute': 0, 'dynamic': lambda: random.choice(LUNCH_MESSAGES)},
    {'hour': 18, 'minute': 0, 'dynamic': lambda: random.choice(DINNER_MESSAGES)},
    {'hour': 0, 'minute': 0, 'dynamic': lambda: random.choice(GOODNIGHT_MESSAGES)},
]


def start_scheduler(bot, room_id: int):
    last_sent: dict = {}
    last_babble = None
    print(
        f'[scheduler] started, room_id={room_id}, schedules={len(SCHEDULES)}',
        flush=True,
    )
    while True:
        try:
            now = datetime.now(KST)
            for s in SCHEDULES:
                key = (s['hour'], s['minute'])
                if (
                    now.hour == s['hour']
                    and now.minute == s['minute']
                    and last_sent.get(key) != now.date()
                ):
                    msg = s['dynamic']() if 'dynamic' in s else s['message']
                    bot.api.reply(room_id, msg)
                    last_sent[key] = now.date()
                    print(
                        f'[scheduler] sent at {now.isoformat()}: {msg}',
                        flush=True,
                    )

            babble_key = (now.date(), now.hour)
            if (
                10 <= now.hour <= 22
                and now.minute == 30
                and last_babble != babble_key
            ):
                last_babble = babble_key
                if random.random() < 0.15:
                    msg = _pick_babble()
                    bot.api.reply(room_id, msg)
                    print(f'[scheduler] babble: {msg}', flush=True)
        except Exception as ex:
            print(f'[scheduler] error: {ex}', flush=True)
        time.sleep(30)
