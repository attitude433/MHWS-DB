"""제니/룰렛 시스템.

스펙: docs/superpowers/specs/2026-05-24-zenny-roulette-design.md
"""
from __future__ import annotations
import io
import random
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

import members

KST = timezone(timedelta(hours=9))

ATTEND_MIN = 10
ATTEND_MAX = 30
ROULETTE_DAILY_LIMIT = 3

# (수익률 r, 확률) — 합 = 1.0. r=None 은 초기화 (잔고 전체 리셋)
ROULETTE_OUTCOMES = [
    (None, 0.001),   # 초기화
    (-0.70, 0.057),
    (-0.50, 0.172),
    (-0.20, 0.270),
    (0.0,   0.100),
    (0.20,  0.167),
    (0.50,  0.120),
    (0.70,  0.080),
    (1.00,  0.032),
    (10.00, 0.001),  # 잭팟
]


def today_kst() -> str:
    return datetime.now(KST).strftime('%Y-%m-%d')


def _record_history(c, user_id: int, zenny: int) -> None:
    c.execute(
        '''INSERT INTO zenny_history (user_id, date, zenny) VALUES (?, ?, ?)
           ON CONFLICT(user_id, date) DO UPDATE SET zenny = excluded.zenny''',
        (user_id, today_kst(), zenny),
    )


def _get_row(c, user_id: int) -> tuple:
    row = c.execute(
        'SELECT zenny, last_attend, roulette_count, last_roulette, nickname FROM members WHERE user_id = ?',
        (user_id,),
    ).fetchone()
    return row or (0, None, 0, None, None)


def check_attend(user_id: int, nickname: str) -> str:
    today = today_kst()
    with members._conn() as c:
        # 멤버 row 보장
        c.execute(
            '''INSERT INTO members (user_id, nickname, last_seen, first_seen)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET nickname = excluded.nickname, last_seen = excluded.last_seen''',
            (user_id, nickname, datetime.now().isoformat(timespec='seconds'),
             datetime.now().isoformat(timespec='seconds')),
        )
        zenny, last_attend, _rc, _lr, _nk = _get_row(c, user_id)
        if last_attend == today:
            return f'이미 오늘 출석했어요 (현재: {zenny:,}제니)'
        reward = random.randint(ATTEND_MIN, ATTEND_MAX)
        new_zenny = zenny + reward
        c.execute(
            'UPDATE members SET zenny = ?, last_attend = ? WHERE user_id = ?',
            (new_zenny, today, user_id),
        )
        _record_history(c, user_id, new_zenny)
    return f'출석 완료! +{reward}제니 (현재: {new_zenny:,}제니)'


def _pick_outcome() -> Optional[float]:
    r = random.random()
    cum = 0.0
    for outcome_r, prob in ROULETTE_OUTCOMES:
        cum += prob
        if r < cum:
            return outcome_r
    return ROULETTE_OUTCOMES[-1][0]


def _format_pct(r: Optional[float]) -> str:
    if r is None:
        return '초기화'
    sign = '+' if r > 0 else ''
    return f'{sign}{int(round(r * 100))}%'


def spin_roulette(user_id: int, nickname: str, bet_arg: str) -> tuple[str, str]:
    """룰렛 1회. (응답 텍스트, 방 공지 텍스트 or '') 반환."""
    today = today_kst()
    with members._conn() as c:
        c.execute(
            '''INSERT INTO members (user_id, nickname, last_seen, first_seen)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET nickname = excluded.nickname, last_seen = excluded.last_seen''',
            (user_id, nickname, datetime.now().isoformat(timespec='seconds'),
             datetime.now().isoformat(timespec='seconds')),
        )
        zenny, _la, roulette_count, last_roulette, _nk = _get_row(c, user_id)

        # 자정 리셋
        if last_roulette != today:
            roulette_count = 0

        if bet_arg == '':
            remaining = ROULETTE_DAILY_LIMIT - roulette_count
            if remaining <= 0:
                return ('오늘 룰렛 횟수를 다 사용했어요', '')
            return (
                f'.룰렛 [금액] 또는 .룰렛 올 (오늘 {remaining}회 남음, 보유: {zenny:,}제니)',
                '',
            )

        if roulette_count >= ROULETTE_DAILY_LIMIT:
            return ('오늘 룰렛 횟수를 다 사용했어요', '')

        # 베팅 금액 파싱
        if bet_arg == '올':
            if zenny <= 0:
                return ('제니가 없어요', '')
            bet = zenny
        else:
            try:
                bet = int(bet_arg)
            except ValueError:
                return ('.룰렛 [금액] 또는 .룰렛 올 형식으로 입력해주세요', '')
            if bet <= 0:
                return ('1 이상의 숫자를 입력해주세요', '')
            if bet > zenny:
                return ('제니가 부족해요', '')

        # 룰렛 굴리기
        r = _pick_outcome()
        roulette_count += 1
        remaining_after = ROULETTE_DAILY_LIMIT - roulette_count

        if r is None:
            new_zenny = 0
            payback = 0
            diff = -zenny
            pct_str = '초기화'
            head_emoji = '💸'
        else:
            payback = int(round(bet * (1 + r)))
            new_zenny = zenny - bet + payback
            diff = payback - bet
            pct_str = _format_pct(r)
            head_emoji = '🎰'

        c.execute(
            'UPDATE members SET zenny = ?, roulette_count = ?, last_roulette = ? WHERE user_id = ?',
            (new_zenny, roulette_count, today, user_id),
        )
        _record_history(c, user_id, new_zenny)

    # 응답 텍스트
    if r is None:
        body = (
            f'{head_emoji} 룰렛 결과: 초기화\n'
            f'{bet:,} → 0제니 (잔고 전부 소멸)\n'
            f'현재 제니: 0제니 (오늘 {remaining_after}회 남음)'
        )
        notice = f'💸 {nickname}님의 제니가 전부 사라졌습니다... 아이루도 울고 있어요'
        return (body, notice)

    diff_sign = '+' if diff > 0 else ''
    body = (
        f'{head_emoji} 룰렛 결과: {pct_str}\n'
        f'{bet:,} → {payback:,}제니 ({diff_sign}{diff:,}제니)\n'
        f'현재 제니: {new_zenny:,}제니 (오늘 {remaining_after}회 남음)'
    )
    notice = ''
    if r == 10.00:
        notice = f'🎰 {nickname}님이 잭팟을 터뜨렸습니다!! 제니가 폭발했어요! 💥'
    return (body, notice)


def my_zenny(user_id: int, nickname: str) -> str:
    with members._conn() as c:
        zenny, _la, _rc, _lr, _nk = _get_row(c, user_id)
    return f'{nickname} 현재 제니: {zenny:,}'


MEDALS = {1: '🥇', 2: '🥈', 3: '🥉'}


def leaderboard() -> str:
    with members._conn() as c:
        rows = c.execute(
            'SELECT nickname, zenny FROM members WHERE zenny > 0 ORDER BY zenny DESC, nickname'
        ).fetchall()
    if not rows:
        return '아직 제니 보유자가 없어요'

    # 동점 동순위 계산
    ranks = []
    prev_zenny = None
    rank_cursor = 0
    for i, (nick, z) in enumerate(rows, 1):
        if z != prev_zenny:
            rank_cursor = i
            prev_zenny = z
        ranks.append((rank_cursor, nick, z))

    lines = ['[제니 랭킹]']
    top10 = [r for r in ranks if r[0] <= 10]
    rest = [r for r in ranks if r[0] > 10]
    for rk, nick, z in top10:
        medal = MEDALS.get(rk, '')
        prefix = f'{medal} {rk}.' if medal else f'{rk}.'
        lines.append(f'{prefix} {nick} — {z:,}제니')
    if rest:
        lines.append('---')
        lines.append('[보유자 전체]')
        for rk, nick, z in rest:
            lines.append(f'{rk}. {nick} — {z:,}제니')
    return '\n'.join(lines)


def my_graph(user_id: int, nickname: str) -> Optional[str]:
    """본인 60일 잔고 그래프. 임시 PNG path 반환. 데이터 없으면 None."""
    with members._conn() as c:
        rows = c.execute(
            '''SELECT date, zenny FROM zenny_history
               WHERE user_id = ? ORDER BY date DESC LIMIT 60''',
            (user_id,),
        ).fetchall()
    if not rows:
        return None
    rows = list(reversed(rows))  # 오래된 → 최신
    dates = [r[0] for r in rows]
    zenny_vals = [r[1] for r in rows]

    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib import font_manager

    # 한글 폰트 fallback
    for candidate in ('NanumGothic', 'Noto Sans CJK KR', 'Malgun Gothic', 'AppleGothic', 'DejaVu Sans'):
        try:
            font_manager.findfont(candidate, fallback_to_default=False)
            matplotlib.rcParams['font.family'] = candidate
            break
        except Exception:
            continue
    matplotlib.rcParams['axes.unicode_minus'] = False

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(dates, zenny_vals, marker='o', linewidth=1.5)
    ax.set_title(f'{nickname} 제니 변화 ({len(rows)}일)')
    ax.set_xlabel('날짜')
    ax.set_ylabel('제니')
    ax.grid(True, alpha=0.3)
    step = max(1, len(dates) // 10)
    ax.set_xticks(dates[::step])
    ax.tick_params(axis='x', rotation=45)
    fig.tight_layout()

    out_path = Path(__file__).resolve().parent.parent / 'tmp_graph.png'
    fig.savefig(out_path, dpi=100)
    plt.close(fig)
    return str(out_path)
