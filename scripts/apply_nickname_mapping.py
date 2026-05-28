"""nicknames.json 매핑을 members.db 의 nickname 컬럼에 일괄 적용."""
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / 'members.db'
JSON_PATH = ROOT / 'nicknames.json'

with open(JSON_PATH, encoding='utf-8') as f:
    mapping = json.load(f)
print(f'매핑 entry: {len(mapping)}')

conn = sqlite3.connect(DB_PATH)
updated = 0
inserted = 0
for uid_str, nick in mapping.items():
    uid = int(uid_str)
    row = conn.execute('SELECT user_id FROM members WHERE user_id = ?', (uid,)).fetchone()
    if row:
        conn.execute('UPDATE members SET nickname = ? WHERE user_id = ?', (nick, uid))
        updated += 1
    else:
        from datetime import datetime
        now = datetime.now().isoformat(timespec='seconds')
        conn.execute(
            'INSERT INTO members (user_id, nickname, last_seen, first_seen) VALUES (?, ?, ?, ?)',
            (uid, nick, now, now),
        )
        inserted += 1
conn.commit()
conn.close()
print(f'UPDATE {updated} / INSERT {inserted}')
