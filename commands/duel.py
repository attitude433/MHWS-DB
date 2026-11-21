"""1대1 제니 승부 (웹 진행).

톡방: .승부 [닉] [금액] → 지목 상대 .수락 / .거절 (5분) → 수락 시 경기 링크.
웹: 두 사람이 직접 주사위 굴리기 / 가위바위보 고르기. 비기면 재경기, 5분 초과 시 무효.
"""
from __future__ import annotations
import random
import secrets
import threading
import time
from typing import Optional

import members
from commands import zenny
from commands.zenny import today_kst, is_excluded, _record_history, _safe_nick

TIMEOUT = 300
BASE_URL = 'http://mhws.diana.ai.kr/duel/'
GAMES = {'rps': '가위바위보', 'dice': '주사위'}
HANDS = ('가위', '바위', '보')
_BEATS = {'가위': '보', '바위': '가위', '보': '바위'}

send = None  # main.py 에서 bot.api.reply 주입 (room_id, msg)

_lock = threading.RLock()
_pending: dict = {}  # target_uid -> {'from', 'amount', 'ts'}
_matches: dict = {}  # match_id -> match dict


def _notify(room, msg: str):
    if send and room:
        try:
            send(room, msg)
        except Exception as e:
            print(f'[duel] send error: {e}', flush=True)


def _expire():
    now = time.time()
    for t in [t for t, p in _pending.items() if now - p['ts'] > TIMEOUT]:
        del _pending[t]
    for m in _matches.values():
        if m['status'] == 'playing' and now - m['ts'] > TIMEOUT:
            m['status'] = 'void'
            m['reason'] = '시간 초과'
    for mid in [k for k, m in _matches.items() if now - m['ts'] > 3600]:
        del _matches[mid]


def _busy(uid: int) -> bool:
    if uid in _pending or any(p['from'] == uid for p in _pending.values()):
        return True
    return any(m['status'] == 'playing' and uid in (m['a'], m['b']) for m in _matches.values())


def _zenny(c, uid: int) -> int:
    row = c.execute('SELECT zenny FROM members WHERE user_id = ?', (uid,)).fetchone()
    return row[0] if row else 0


def _used_today(c, uid: int) -> bool:
    c.execute('CREATE TABLE IF NOT EXISTS duel_daily (user_id INTEGER PRIMARY KEY, date TEXT)')
    row = c.execute('SELECT date FROM duel_daily WHERE user_id = ?', (uid,)).fetchone()
    return bool(row and row[0] == today_kst())


# ── 톡방 명령 ──────────────────────────────────────────

def challenge(uid: int, arg: str) -> str:
    parts = arg.rsplit(' ', 1)
    if len(parts) != 2 or not parts[1].isdigit() or int(parts[1]) <= 0:
        return '.승부 [닉네임] [금액]'
    query, amount = parts[0].strip(), int(parts[1])

    target, tnick, cands = zenny.find_user(query)
    if cands:
        return '누구인지 골라주세요: ' + ', '.join(n for _, n in cands[:10])
    if not target:
        return '그 닉네임을 찾을 수 없어요'
    if target == uid:
        return '자기 자신과는 승부할 수 없어요'

    with _lock:
        _expire()
        if _busy(uid) or _busy(target):
            return '이미 진행 중인 승부가 있어요'
        with members._conn() as c:
            if _used_today(c, uid) and not is_excluded(uid):
                return '승부 신청은 하루 한 번이에요'
            if _zenny(c, uid) < amount:
                return '제니가 부족해요'
            if _zenny(c, target) < amount:
                return f'{tnick}님 제니가 부족해요'
        _pending[target] = {'from': uid, 'amount': amount, 'ts': time.time()}
    return f'⚔️ {_safe_nick(None, uid)} → {tnick} ({amount:,}제니)\n.수락 / .거절 (5분)'


def reject(uid: int) -> Optional[str]:
    with _lock:
        _expire()
        if _pending.pop(uid, None) is None:
            return None
    return '승부 거절'


def accept(uid: int, room) -> Optional[str]:
    with _lock:
        _expire()
        p = _pending.pop(uid, None)
        if p is None:
            return None
        mid = secrets.token_urlsafe(6)
        _matches[mid] = {
            'a': p['from'], 'b': uid, 'amount': p['amount'], 'room': room, 'ts': time.time(),
            'game': random.choice(list(GAMES)), 'status': 'playing',
            'tokens': {}, 'picks': {}, 'history': [], 'winner': None, 'reason': '',
        }
    a, b = _safe_nick(None, p['from']), _safe_nick(None, uid)
    return f'⚔️ {a} vs {b} 승부 시작! (5분)\n{BASE_URL}{mid}'


# ── 웹 API ─────────────────────────────────────────────

def _role(m: dict, token: str) -> Optional[str]:
    for r, t in m['tokens'].items():
        if token and t == token:
            return r
    return None


def _nick_match(nick: str, uid: int) -> bool:
    full = _safe_nick(None, uid)
    short = full.replace('\\', '/').split('/')[0].strip()
    return nick.strip() in (full, short)


def join(mid: str, nick: str) -> dict:
    with _lock:
        _expire()
        m = _matches.get(mid)
        if not m:
            return {'error': '없는 승부예요'}
        for r in ('a', 'b'):
            if _nick_match(nick, m[r]):
                if r in m['tokens']:
                    return {'error': '이미 입장한 참가자예요'}
                m['tokens'][r] = secrets.token_urlsafe(12)
                return {'token': m['tokens'][r], 'role': r}
        return {'role': None}


def state(mid: str, token: str = '') -> Optional[dict]:
    with _lock:
        _expire()
        m = _matches.get(mid)
        if not m:
            return None
        me = _role(m, token)
        picks = {}
        for r in ('a', 'b'):
            v = m['picks'].get(r)
            # 가위바위보는 본인 것만 공개 (둘 다 고르면 history 로 공개됨)
            picks[r] = v if (m['game'] == 'dice' or r == me) else (v is not None or None)
        return {
            'game': m['game'], 'game_kr': GAMES[m['game']], 'amount': m['amount'],
            'nick': {'a': _safe_nick(None, m['a']), 'b': _safe_nick(None, m['b'])},
            'joined': {r: r in m['tokens'] for r in ('a', 'b')},
            'me': me, 'picks': picks, 'history': m['history'],
            'status': m['status'], 'winner': m['winner'], 'reason': m['reason'],
            'left': max(0, int(TIMEOUT - (time.time() - m['ts']))),
        }


def act(mid: str, token: str, hand: str = '') -> dict:
    with _lock:
        _expire()
        m = _matches.get(mid)
        if not m or m['status'] != 'playing':
            return {'error': '끝난 승부예요'}
        me = _role(m, token)
        if not me:
            return {'error': '참가자가 아니에요'}
        if m['picks'].get(me) is not None:
            return {'error': '이미 냈어요'}
        if m['game'] == 'rps':
            if hand not in HANDS:
                return {'error': '잘못된 손이에요'}
            m['picks'][me] = hand
        else:
            m['picks'][me] = random.randint(1, 6)

        pa, pb = m['picks'].get('a'), m['picks'].get('b')
        if pa is None or pb is None:
            return {'ok': True}
        if pa == pb:
            m['history'].append({'a': pa, 'b': pb, 'w': None})
            m['picks'] = {}
            return {'ok': True}
        a_win = _BEATS[pa] == pb if m['game'] == 'rps' else pa > pb
        m['history'].append({'a': pa, 'b': pb, 'w': 'a' if a_win else 'b'})
        m['picks'] = {}
        _settle(m, 'a' if a_win else 'b')
    return {'ok': True}


def _settle(m: dict, w: str):
    """_lock 보유 상태에서 호출. 잔고 재확인 후 제니 이동 + 톡방 공지."""
    amount = m['amount']
    winner, loser = (m['a'], m['b']) if w == 'a' else (m['b'], m['a'])
    with members._conn() as c:
        if _zenny(c, m['a']) < amount or _zenny(c, m['b']) < amount:
            m['status'], m['reason'] = 'void', '제니 부족'
            _notify(m['room'], '⚔️ 제니가 부족해서 승부가 무효됐어요')
            return
        bal = {}
        for u, d in ((winner, amount), (loser, -amount)):
            c.execute('UPDATE members SET zenny = zenny + ? WHERE user_id = ?', (d, u))
            bal[u] = _zenny(c, u)
            _record_history(c, u, bal[u])
        c.execute('INSERT INTO duel_daily (user_id, date) VALUES (?, ?) '
                  'ON CONFLICT(user_id) DO UPDATE SET date = excluded.date', (m['a'], today_kst()))
    for u, d in ((winner, amount), (loser, -amount)):
        members.record_event(u, kind='duel', bet=amount, payout=amount * 2 if d > 0 else 0,
                             delta=d, outcome='duel_win' if d > 0 else 'duel_lose',
                             balance_after=bal[u])
    m['status'], m['winner'] = 'done', w
    a, b = _safe_nick(None, m['a']), _safe_nick(None, m['b'])
    _notify(m['room'], f'⚔️ {a} vs {b} — {_safe_nick(None, winner)} 승리! +{amount:,}제니')
