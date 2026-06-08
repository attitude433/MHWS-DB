"""제니/룰렛 시스템.

스펙: docs/superpowers/specs/2026-05-24-zenny-roulette-design.md
"""
from __future__ import annotations
import io
import math
import random
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

import members
import nicknames as _nicknames


def _safe_nick(nick: Optional[str], user_id: Optional[int] = None) -> str:
    """매핑된 평문 닉 우선, 없으면 카톡 raw 토큰 처리."""
    if user_id:
        mapped = _nicknames.get(user_id)
        if mapped:
            return mapped
    if not nick:
        return '익명 헌터'
    if nick.endswith('=') and re.fullmatch(r'[A-Za-z0-9+/]+=+', nick):
        return '익명 헌터'
    return nick

KST = timezone(timedelta(hours=9))

ATTEND_MIN = 10
ATTEND_MAX = 30
ROULETTE_DAILY_LIMIT = 3

# 운영자 본인 등 제니 시스템 제외 대상 user_id
EXCLUDED_USER_IDS = {395932031}


def is_excluded(uid: int) -> bool:
    try:
        return int(uid) in EXCLUDED_USER_IDS
    except (ValueError, TypeError):
        return False

# (수익률 r, 확률) — 합 = 1.0. r=None 은 초기화 (잔고 전체 리셋)
# 잭팟·초기화 1.0% / 1.0% 로 상향, 잭팟 수익률 +900% (×10) 로 조정
ROULETTE_OUTCOMES = [
    (None, 0.010),   # 초기화 0.1 → 1.0%
    (-0.70, 0.056),  # 5.7 → 5.6
    (-0.50, 0.169),  # 17.2 → 16.9
    (-0.20, 0.265),  # 27.0 → 26.5
    (0.0,   0.098),  # 10.0 → 9.8
    (0.25,  0.164),  # 16.7 → 16.4
    (0.60,  0.118),  # 12.0 → 11.8
    (0.80,  0.079),  # 8.0 → 7.9
    (1.20,  0.031),  # 3.2 → 3.1
    (9.00,  0.010),  # 잭팟 +1500% → +900% (×16 → ×10), 0.1 → 1.0%
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
        'SELECT zenny, last_attend, roulette_count, last_roulette, nickname, neg_streak, attend_bonus FROM members WHERE user_id = ?',
        (user_id,),
    ).fetchone()
    return row or (0, None, 0, None, None, 0, 0)


def _pick_with_pity(neg_streak: int) -> tuple:
    """비밀 pity timer: 5회 연속 음수면 양수 outcome (잭팟 제외) 무작위 강제.

    Returns: (r, pity_triggered)
    """
    if neg_streak >= 5:
        positives = [(r, p) for r, p in ROULETTE_OUTCOMES if r is not None and 0 < r < 9.0]
        total = sum(p for _, p in positives)
        rr = random.random() * total
        cum = 0.0
        for r, p in positives:
            cum += p
            if rr < cum:
                return r, True
        return positives[-1][0], True
    return _pick_outcome(), False


def check_attend(user_id: int, nickname: str) -> str:
    today = today_kst()
    unlimited = is_excluded(user_id)  # 운영자: 1일 1회 제한 없음
    with members._conn() as c:
        # 멤버 row 보장
        c.execute(
            '''INSERT INTO members (user_id, nickname, last_seen, first_seen)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET nickname = excluded.nickname, last_seen = excluded.last_seen''',
            (user_id, nickname, datetime.now().isoformat(timespec='seconds'),
             datetime.now().isoformat(timespec='seconds')),
        )
        zenny, last_attend, _rc, _lr, _nk, _ns, attend_bonus = _get_row(c, user_id)
        if last_attend == today and not unlimited:
            return f'이미 오늘 출석했어요 (현재: {zenny:,}제니)'
        # 비밀: 직전에 룰렛 초기화당한 사람은 다음 출석 1회 30제니 확정
        if attend_bonus:
            reward = ATTEND_MAX
        else:
            reward = random.randint(ATTEND_MIN, ATTEND_MAX)
        new_zenny = zenny + reward
        c.execute(
            'UPDATE members SET zenny = ?, last_attend = ?, attend_bonus = 0 WHERE user_id = ?',
            (new_zenny, today, user_id),
        )
        _record_history(c, user_id, new_zenny)
    members.record_event(
        user_id, kind='attend', bet=None, payout=reward, delta=reward,
        outcome='attend_bonus' if attend_bonus else 'attend',
        balance_after=new_zenny,
    )
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
    unlimited = is_excluded(user_id)  # 운영자: 횟수 무제한 + 방 공지 억제
    with members._conn() as c:
        c.execute(
            '''INSERT INTO members (user_id, nickname, last_seen, first_seen)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET nickname = excluded.nickname, last_seen = excluded.last_seen''',
            (user_id, nickname, datetime.now().isoformat(timespec='seconds'),
             datetime.now().isoformat(timespec='seconds')),
        )
        zenny, _la, roulette_count, last_roulette, _nk, neg_streak, attend_bonus = _get_row(c, user_id)

        # 자정 리셋
        if last_roulette != today:
            roulette_count = 0

        if bet_arg == '':
            remaining = ROULETTE_DAILY_LIMIT - roulette_count
            if remaining <= 0 and not unlimited:
                return ('오늘 룰렛 횟수를 다 사용했어요', '')
            return (
                f'.룰렛 [금액] / [%] / 올 (오늘 {remaining}회 남음, 보유: {zenny:,}제니)',
                '',
            )

        if roulette_count >= ROULETTE_DAILY_LIMIT and not unlimited:
            return ('오늘 룰렛 횟수를 다 사용했어요', '')

        # 베팅 금액 파싱 (올 / 퍼센트 / 금액)
        if bet_arg == '올':
            if zenny <= 0:
                return ('제니가 없어요', '')
            bet = zenny
        elif bet_arg.endswith('%'):
            try:
                pct = float(bet_arg[:-1])
            except ValueError:
                return ('.룰렛 50% 처럼 입력해주세요', '')
            if pct <= 0 or pct > 100:
                return ('1~100% 사이로 입력해주세요', '')
            if zenny <= 0:
                return ('제니가 없어요', '')
            bet = math.ceil(zenny * pct / 100)  # 소수점 올림
        else:
            try:
                bet = int(bet_arg)
            except ValueError:
                return ('.룰렛 [금액] / [%] / 올 형식으로 입력해주세요', '')
            if bet <= 0:
                return ('1 이상의 숫자를 입력해주세요', '')
            if bet > zenny:
                return ('제니가 부족해요', '')

        # 룰렛 굴리기 (비밀 pity timer 적용)
        r, _pity = _pick_with_pity(neg_streak)
        if not unlimited:
            roulette_count += 1
        remaining_after = ROULETTE_DAILY_LIMIT - roulette_count

        # neg_streak 갱신: 초기화/본전/양수면 리셋, 음수면 +1
        if r is None or (r is not None and r >= 0):
            new_streak = 0
        else:
            new_streak = neg_streak + 1

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

        # 비밀: 초기화당하면 다음 출석 30제니 확정 플래그 set, 그 외엔 기존 값 보존
        new_attend_bonus = 1 if r is None else attend_bonus
        c.execute(
            'UPDATE members SET zenny = ?, roulette_count = ?, last_roulette = ?, neg_streak = ?, attend_bonus = ? WHERE user_id = ?',
            (new_zenny, roulette_count, today, new_streak, new_attend_bonus, user_id),
        )
        _record_history(c, user_id, new_zenny)
    # 이벤트 로그
    if r is None:
        _outcome = 'reset'
        _delta = -zenny
        _payout = 0
    elif r == 9.00:
        _outcome = 'jackpot'
        _delta = diff
        _payout = payback
    else:
        _outcome = f'r{int(round(r * 100)):+d}'  # 'r+25', 'r-50', 'r+0'
        _delta = diff
        _payout = payback
    members.record_event(
        user_id, kind='roulette', bet=bet, payout=_payout, delta=_delta,
        outcome=_outcome, balance_after=new_zenny,
    )

    # 응답 텍스트
    safe = _safe_nick(nickname, user_id)
    if r is None:
        body = (
            f'{head_emoji} 룰렛 결과: 초기화\n'
            f'{bet:,} → 0제니 (잔고 전부 소멸)\n'
            f'현재 제니: 0제니 (오늘 {remaining_after}회 남음)'
        )
        notice = '' if unlimited else f'💸 {safe}님의 제니가 전부 사라졌습니다... 아이루도 울고 있어요'
        return (body, notice)

    diff_sign = '+' if diff > 0 else ''
    body = (
        f'{head_emoji} 룰렛 결과: {pct_str}\n'
        f'{bet:,} → {payback:,}제니 ({diff_sign}{diff:,}제니)\n'
        f'현재 제니: {new_zenny:,}제니 (오늘 {remaining_after}회 남음)'
    )
    notice = ''
    if r == 9.00 and not unlimited:
        notice = f'🎰 {safe}님이 잭팟을 터뜨렸습니다!! 제니가 폭발했어요! 💥'
    return (body, notice)


def find_user(query: str) -> tuple:
    """닉 검색 — 정확 일치 우선, 없으면 부분 일치.

    Returns:
        (user_id, nickname, candidates_list)
        - 매치 1건: (uid, nick, [])
        - 매치 0건: (None, '', [])
        - 매치 여러 건: (None, '', [(uid, nick), ...])
    """
    query = query.strip()
    if not query:
        return (None, '', [])

    # nicknames.json + members.db 통합
    pool: dict = {}  # uid -> nick
    for uid, nick in _nicknames.all_mappings().items():
        pool[int(uid)] = nick
    with members._conn() as c:
        rows = c.execute('SELECT user_id, nickname FROM members WHERE nickname IS NOT NULL').fetchall()
    for uid, nick in rows:
        if uid not in pool and nick:
            pool[uid] = nick

    # 정확 일치
    exact = [(uid, nick) for uid, nick in pool.items() if nick == query]
    if len(exact) == 1:
        return (exact[0][0], exact[0][1], [])
    if len(exact) > 1:
        return (None, '', exact)

    # 부분 일치
    partial = [(uid, nick) for uid, nick in pool.items() if query in nick]
    if len(partial) == 1:
        return (partial[0][0], partial[0][1], [])
    if len(partial) > 1:
        return (None, '', partial)

    return (None, '', [])


def my_zenny(user_id: int, nickname: str) -> str:
    with members._conn() as c:
        zenny, *_ = _get_row(c, user_id)
    return f'{_safe_nick(nickname, user_id)} 현재 제니: {zenny:,}'


MEDALS = {1: '🥇', 2: '🥈', 3: '🥉'}


def _signed(n: int) -> str:
    return f'{n:+,}'.replace('+', '+')  # 그대로지만 명시적


def leaderboard(viewer_user_id: int = 0) -> str:
    from commands import season as _season

    # 시즌 랭킹 (현재 진행 중)
    cur_season = _season.get_current_season()
    season_ranking = _season.get_season_ranking() if cur_season else []

    # 누적 랭킹 (잔고)
    with members._conn() as c:
        rows = c.execute(
            'SELECT user_id, nickname, zenny FROM members WHERE zenny > 0 ORDER BY zenny DESC, nickname'
        ).fetchall()
    rows = [r for r in rows if not is_excluded(r[0])]

    if not season_ranking and not rows:
        return '아직 제니 보유자가 없어요'

    body = '[제니 랭킹]\n\n'

    # ━━ 시즌 섹션 (위, 미리보기) ━━
    if cur_season and season_ranking:
        title = cur_season['title']
        body += f'▼ 🎰 {title} 시즌 (상위 10)\n\n'
        top10_season = [e for e in season_ranking if e['rank'] <= 10]
        for e in top10_season:
            medal = MEDALS.get(e['rank'], '')
            head = f"{medal} [{e['rank']}위]" if medal else f"[{e['rank']}위]"
            body += f"{head} {e['nick']} — {_signed(e['score'])}\n"

        # viewer 시즌 11위 이하 본인 순위
        if viewer_user_id:
            v = next((e for e in season_ranking if e['user_id'] == viewer_user_id), None)
            if v and v['rank'] > 10:
                body += f"(나) [{v['rank']}위] {v['nick']} — {_signed(v['score'])}\n"
        body += '\n'

    # ━━ 누적 섹션 (아래, 전체 표시 — 카톡 자동 접힘 발동용 길이 확보) ━━
    cumulative_ranks = []
    prev_zenny = None
    rank_cursor = 0
    for i, (uid, nick, z) in enumerate(rows, 1):
        if z != prev_zenny:
            rank_cursor = i
            prev_zenny = z
        cumulative_ranks.append((rank_cursor, uid, nick, z))

    body += f'━━━━━━━━━━━━\n📊 누적 순위 (전체 기간, {len(cumulative_ranks)}명)\n\n'
    for rk, uid, nick, z in cumulative_ranks:
        medal = MEDALS.get(rk, '')
        head = f'{medal} [{rk}위]' if medal else f'[{rk}위]'
        body += f'{head} {_safe_nick(nick, uid)} — {z:,}제니\n'

    body += (
        '\n━━━━━━━━━━━━\n'
        '📆 매월 1일 시즌 점수 리셋 (KST 자정)\n'
        '📅 매일 KST 자정 출석·룰렛 횟수 리셋\n'
        '🎯 .출석 / 🎰 .룰렛 / ✌️ .가위 / 💰 .제니'
    )
    return body


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
    ax.set_title(f'{_safe_nick(nickname, user_id)} 제니 변화 ({len(rows)}일)')
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
