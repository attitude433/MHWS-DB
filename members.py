import random
import sqlite3
from datetime import datetime
from pathlib import Path

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
    return c


def upsert(user_id: int, nickname: str):
    if not user_id or not nickname:
        return
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
