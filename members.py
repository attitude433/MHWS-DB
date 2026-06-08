import random
import sqlite3
from datetime import datetime
from pathlib import Path

import nicknames as _nicknames

DB_PATH = Path(__file__).parent / 'members.db'


def _conn():
    c = sqlite3.connect(DB_PATH)
    c.execute('''
        CREATE TABLE IF NOT EXISTS members (
            user_id INTEGER PRIMARY KEY,
            nickname TEXT,
            last_seen TEXT,
            first_seen TEXT
        )
    ''')
    # 제니/룰렛 컬럼 마이그레이션 (멱등)
    cols = {row[1] for row in c.execute('PRAGMA table_info(members)').fetchall()}
    if 'zenny' not in cols:
        c.execute('ALTER TABLE members ADD COLUMN zenny INTEGER DEFAULT 0')
    if 'last_attend' not in cols:
        c.execute('ALTER TABLE members ADD COLUMN last_attend TEXT')
    if 'roulette_count' not in cols:
        c.execute('ALTER TABLE members ADD COLUMN roulette_count INTEGER DEFAULT 0')
    if 'last_roulette' not in cols:
        c.execute('ALTER TABLE members ADD COLUMN last_roulette TEXT')
    if 'neg_streak' not in cols:
        c.execute('ALTER TABLE members ADD COLUMN neg_streak INTEGER DEFAULT 0')
    if 'attend_bonus' not in cols:
        c.execute('ALTER TABLE members ADD COLUMN attend_bonus INTEGER DEFAULT 0')
    if 'season_start_zenny' not in cols:
        c.execute('ALTER TABLE members ADD COLUMN season_start_zenny INTEGER DEFAULT 0')
    c.execute('''
        CREATE TABLE IF NOT EXISTS zenny_history (
            user_id INTEGER NOT NULL,
            date    TEXT NOT NULL,
            zenny   INTEGER NOT NULL,
            PRIMARY KEY (user_id, date)
        )
    ''')
    # 단일 이벤트 로그 (.출석 / .룰렛 / .가위·바위·보 각각 한 줄씩)
    c.execute('''
        CREATE TABLE IF NOT EXISTS zenny_events (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id       INTEGER NOT NULL,
            ts            TEXT    NOT NULL,
            kind          TEXT    NOT NULL,
            bet           INTEGER,
            payout        INTEGER,
            delta         INTEGER NOT NULL,
            outcome       TEXT    NOT NULL,
            balance_after INTEGER NOT NULL
        )
    ''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_events_user ON zenny_events (user_id, ts)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_events_kind ON zenny_events (kind, ts)')
    return c


def record_event(user_id: int, kind: str, bet, payout, delta: int,
                 outcome: str, balance_after: int) -> None:
    """단일 이벤트 한 줄 기록. 실패해도 게임 동작 막지 않게 best-effort."""
    from datetime import datetime
    try:
        with _conn() as c:
            c.execute(
                '''INSERT INTO zenny_events
                   (user_id, ts, kind, bet, payout, delta, outcome, balance_after)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                (
                    int(user_id),
                    datetime.now().isoformat(timespec='seconds'),
                    kind, bet, payout, int(delta), outcome, int(balance_after),
                ),
            )
    except Exception:
        pass


def exists(user_id: int) -> bool:
    if not user_id:
        return False
    with _conn() as c:
        row = c.execute('SELECT 1 FROM members WHERE user_id = ?', (user_id,)).fetchone()
    return row is not None


def upsert(user_id: int, nickname: str):
    if not user_id or not nickname:
        return
    # 매핑에 평문 닉이 있으면 그것을 우선 (raw 토큰 덮어쓰기)
    mapped = _nicknames.get(user_id)
    if mapped:
        nickname = mapped
    now = datetime.now().isoformat(timespec='seconds')
    with _conn() as c:
        c.execute('''
            INSERT INTO members (user_id, nickname, last_seen, first_seen)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                nickname = excluded.nickname,
                last_seen = excluded.last_seen
        ''', (user_id, nickname, now, now))


def get_random_nickname() -> str | None:
    with _conn() as c:
        rows = c.execute(
            'SELECT nickname FROM members WHERE nickname IS NOT NULL AND length(nickname) > 0'
        ).fetchall()
    if not rows:
        return None
    return random.choice(rows)[0]


def get_mentioned_in(query: str, min_len: int = 3) -> list[str]:
    if not query:
        return []
    with _conn() as c:
        rows = c.execute(
            'SELECT nickname FROM members WHERE length(nickname) >= ?',
            (min_len,),
        ).fetchall()
    found = []
    for (nick,) in rows:
        if nick and nick in query and nick not in found:
            found.append(nick)
    return found
