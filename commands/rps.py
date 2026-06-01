"""가위바위보 베팅 게임.

룰렛과 일일 횟수 공유 (members.db roulette_count / last_roulette 컬럼 공용).
승 x2.5 / 무 본전 / 패 몰수 → EV +16.7% (리스크 프리미엄, 룰렛보다 우위). 무승부도 횟수 차감.
올 키워드는 차단하고 100% 로 명시 입력해야 전액 베팅 가능.
"""
from __future__ import annotations
import math
import random
from datetime import datetime

import members
from commands.zenny import (
    today_kst,
    is_excluded,
    _get_row,
    _record_history,
    _safe_nick,
    ROULETTE_DAILY_LIMIT,
)

WIN_MULT = 2.5  # 승리 환급 배율, EV=(2.5-2)/3 ≈ +16.7%

HANDS = {'가위': '✌️', '바위': '✊', '보': '✋'}
# user_hand 가 이기는 상대
_BEATS = {'가위': '보', '바위': '가위', '보': '바위'}


def _judge(user_hand: str, bot_hand: str) -> str:
    if user_hand == bot_hand:
        return 'draw'
    return 'win' if _BEATS[user_hand] == bot_hand else 'lose'


def play(user_id: int, nickname: str, user_hand: str, bet_arg: str) -> str:
    unlimited = is_excluded(user_id)  # 운영자: 횟수 무제한
    if bet_arg == '올':
        return '가위바위보는 지면 베팅을 전부 잃어요. 그래도 다 걸려면 .가위 100% 로 입력해주세요'

    today = today_kst()
    with members._conn() as c:
        c.execute(
            '''INSERT INTO members (user_id, nickname, last_seen, first_seen)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET nickname = excluded.nickname, last_seen = excluded.last_seen''',
            (user_id, nickname, datetime.now().isoformat(timespec='seconds'),
             datetime.now().isoformat(timespec='seconds')),
        )
        zenny, _la, game_count, last_game, _nk, _ns, _ab = _get_row(c, user_id)

        # 자정 리셋 (룰렛과 공유 카운터)
        if last_game != today:
            game_count = 0

        if bet_arg == '':
            remaining = ROULETTE_DAILY_LIMIT - game_count
            if remaining <= 0 and not unlimited:
                return '오늘 게임 횟수를 다 사용했어요 (룰렛·가위바위보 공유)'
            return (
                f'.가위 / .바위 / .보 [금액 또는 %] '
                f'(오늘 {remaining}회 남음, 보유: {zenny:,}제니)'
            )

        if game_count >= ROULETTE_DAILY_LIMIT and not unlimited:
            return '오늘 게임 횟수를 다 사용했어요 (룰렛·가위바위보 공유)'

        if bet_arg.endswith('%'):
            try:
                pct = float(bet_arg[:-1])
            except ValueError:
                return '.가위 50% 처럼 입력해주세요'
            if pct <= 0 or pct > 100:
                return '1~100% 사이로 입력해주세요'
            if zenny <= 0:
                return '제니가 부족해요'
            bet = math.ceil(zenny * pct / 100)  # 소수점 올림
        else:
            try:
                bet = int(bet_arg)
            except ValueError:
                return '.가위 [금액] / [%] 형식으로 입력해주세요 (예: .가위 100)'
            if bet <= 0:
                return '1 이상의 숫자를 입력해주세요'
            if bet > zenny:
                return '제니가 부족해요'

        bot_hand = random.choice(list(HANDS))
        result = _judge(user_hand, bot_hand)
        if not unlimited:
            game_count += 1
        remaining_after = ROULETTE_DAILY_LIMIT - game_count

        if result == 'win':
            payback = int(round(bet * WIN_MULT))
            new_zenny = zenny - bet + payback
        elif result == 'draw':
            new_zenny = zenny
        else:
            new_zenny = zenny - bet

        c.execute(
            'UPDATE members SET zenny = ?, roulette_count = ?, last_roulette = ? WHERE user_id = ?',
            (new_zenny, game_count, today, user_id),
        )
        _record_history(c, user_id, new_zenny)

    uh = f'{HANDS[user_hand]} {user_hand}'
    bh = f'{HANDS[bot_hand]} {bot_hand}'
    head = f'{uh}  vs  {bh}'
    if result == 'win':
        gain = new_zenny - zenny
        line = f'승리! +{gain:,}제니'
    elif result == 'draw':
        line = '무승부! 베팅 반환'
    else:
        line = f'패배! -{bet:,}제니'
    return f'{head}\n{line}\n현재 제니: {new_zenny:,}제니 (오늘 {remaining_after}회 남음)'
