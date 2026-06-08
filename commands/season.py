"""시즌 시스템 — 매월 1일 KST 자정 자동 전환.

설계:
- 시즌 점수는 별도 저장 X. `seasons.start_ts` 이후 `zenny_events.delta` 합으로 실시간 계산.
- 시즌 종료 시 그 시점 멤버별 점수를 `season_results` 에 스냅샷 (1·2·3등 영구 보존).
- `members.zenny` (누적) 는 시즌과 무관. 봇 동작 코드 (출석/룰렛/가위바위보) 수정 0 건.
"""
from __future__ import annotations
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import members
import nicknames as _nicknames
from commands.zenny import EXCLUDED_USER_IDS

KST = timezone(timedelta(hours=9))


def _ensure_tables() -> None:
    """seasons / season_results 테이블 마이그레이션 (멱등)."""
    with members._conn() as c:
        c.execute('''
            CREATE TABLE IF NOT EXISTS seasons (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                start_ts  TEXT NOT NULL,
                end_ts    TEXT,
                title     TEXT
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS season_results (
                season_id INTEGER NOT NULL,
                user_id   INTEGER NOT NULL,
                rank      INTEGER NOT NULL,
                score     INTEGER NOT NULL,
                PRIMARY KEY (season_id, user_id)
            )
        ''')
        c.execute('CREATE INDEX IF NOT EXISTS idx_season_results_season ON season_results (season_id, rank)')


def _month_start_kst(year: int, month: int) -> str:
    """해당 월 1일 KST 자정의 ISO 포맷 (naive, 봇 record_event 와 동일 포맷)."""
    return datetime(year, month, 1, 0, 0, 0).isoformat(timespec='seconds')


def _next_month_start(dt_kst: datetime) -> datetime:
    """다음 달 1일 0시 KST."""
    if dt_kst.month == 12:
        return dt_kst.replace(year=dt_kst.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    return dt_kst.replace(month=dt_kst.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0)


def get_current_season() -> Optional[dict]:
    """현재 진행 중인 시즌 (end_ts IS NULL). 없으면 None."""
    with members._conn() as c:
        row = c.execute(
            'SELECT id, start_ts, end_ts, title FROM seasons WHERE end_ts IS NULL '
            'ORDER BY id DESC LIMIT 1'
        ).fetchone()
    if not row:
        return None
    return {'id': row[0], 'start_ts': row[1], 'end_ts': row[2], 'title': row[3]}


def ensure_current_season() -> dict:
    """현재 시즌이 없으면 이번 달 1일 KST 자정 기준으로 생성. 있으면 그대로 반환.

    봇 시작 시 호출 권장.
    """
    _ensure_tables()
    cur = get_current_season()
    if cur:
        return cur
    now_kst = datetime.now(KST)
    start_ts = _month_start_kst(now_kst.year, now_kst.month)
    title = f'{now_kst.year}년 {now_kst.month}월'
    with members._conn() as c:
        c.execute(
            'INSERT INTO seasons (start_ts, end_ts, title) VALUES (?, NULL, ?)',
            (start_ts, title),
        )
    return get_current_season()


def get_season_score(user_id: int, season_id: Optional[int] = None) -> int:
    """특정 시즌의 멤버 점수 — zenny_events delta 합 (시즌 시작 이후).

    season_id 미지정 시 현재 시즌. 종료된 시즌은 season_results 에서 우선 조회.
    """
    cur = get_current_season()
    target_id = season_id if season_id is not None else (cur['id'] if cur else None)
    if target_id is None:
        return 0
    if cur and target_id == cur['id']:
        start_ts = cur['start_ts']
        with members._conn() as c:
            row = c.execute(
                "SELECT COALESCE(SUM(delta), 0) FROM zenny_events "
                "WHERE user_id = ? AND ts >= ?",
                (user_id, start_ts),
            ).fetchone()
        return int(row[0])
    # 종료된 시즌
    with members._conn() as c:
        row = c.execute(
            'SELECT score FROM season_results WHERE season_id = ? AND user_id = ?',
            (target_id, user_id),
        ).fetchone()
    return int(row[0]) if row else 0


def get_season_ranking(season_id: Optional[int] = None, active_uids: Optional[set] = None) -> list[dict]:
    """시즌 랭킹 — [{user_id, nick, score, rank}] 점수 내림차순.

    종료된 시즌은 season_results 그대로, 현재 시즌은 zenny_events 에서 실시간 계산.
    운영자 제외, 닉네임 매핑된 멤버만, active_uids 주면 그 안에서만.
    """
    cur = get_current_season()
    target_id = season_id if season_id is not None else (cur['id'] if cur else None)
    if target_id is None:
        return []

    if cur and target_id == cur['id']:
        start_ts = cur['start_ts']
        with members._conn() as c:
            rows = c.execute(
                "SELECT user_id, SUM(delta) FROM zenny_events "
                "WHERE ts >= ? GROUP BY user_id",
                (start_ts,),
            ).fetchall()
    else:
        with members._conn() as c:
            rows = c.execute(
                'SELECT user_id, score FROM season_results WHERE season_id = ?',
                (target_id,),
            ).fetchall()

    out = []
    for uid, score in rows:
        if uid in EXCLUDED_USER_IDS:
            continue
        nick = _nicknames.get(uid)
        if not nick:
            continue
        if active_uids is not None and uid not in active_uids:
            continue
        out.append({'user_id': uid, 'nick': nick, 'score': int(score)})

    out.sort(key=lambda x: (-x['score'], x['nick']))
    # 동점 동순위
    prev_score = None
    rank_cursor = 0
    for i, e in enumerate(out, 1):
        if e['score'] != prev_score:
            rank_cursor = i
            prev_score = e['score']
        e['rank'] = rank_cursor
    return out


def end_current_season_and_start_new(now_kst: Optional[datetime] = None) -> dict:
    """현재 시즌 종료 + 점수 스냅샷 + 새 시즌 시작.

    1) 현재 시즌 랭킹 계산 → season_results INSERT
    2) seasons.end_ts 채움
    3) 새 시즌 row INSERT (start_ts = 종료 시점)
    """
    _ensure_tables()
    if now_kst is None:
        now_kst = datetime.now(KST)
    end_ts = now_kst.replace(microsecond=0).isoformat()
    cur = get_current_season()
    if cur:
        ranking = get_season_ranking(cur['id'])
        with members._conn() as c:
            for e in ranking:
                c.execute(
                    '''INSERT OR REPLACE INTO season_results
                       (season_id, user_id, rank, score) VALUES (?, ?, ?, ?)''',
                    (cur['id'], e['user_id'], e['rank'], e['score']),
                )
            c.execute('UPDATE seasons SET end_ts = ? WHERE id = ?', (end_ts, cur['id']))
        print(f'[season] 종료: id={cur["id"]} "{cur["title"]}" → {len(ranking)}명 기록', flush=True)

    # 새 시즌
    next_title = f'{now_kst.year}년 {now_kst.month}월'
    new_start_ts = _month_start_kst(now_kst.year, now_kst.month)
    with members._conn() as c:
        c.execute(
            'INSERT INTO seasons (start_ts, end_ts, title) VALUES (?, NULL, ?)',
            (new_start_ts, next_title),
        )
    new_cur = get_current_season()
    print(f'[season] 시작: id={new_cur["id"]} "{new_cur["title"]}"', flush=True)
    return new_cur


def get_past_season_medalists(limit: int = 6) -> list[dict]:
    """옛 시즌별 1·2·3등 명단 (최근 limit 개 시즌)."""
    with members._conn() as c:
        season_rows = c.execute(
            'SELECT id, title, start_ts, end_ts FROM seasons '
            'WHERE end_ts IS NOT NULL ORDER BY id DESC LIMIT ?',
            (limit,),
        ).fetchall()
        out = []
        for sid, title, start_ts, end_ts in season_rows:
            medals = c.execute(
                'SELECT user_id, rank, score FROM season_results '
                'WHERE season_id = ? AND rank <= 3 ORDER BY rank',
                (sid,),
            ).fetchall()
            medalists = []
            for uid, rank, score in medals:
                nick = _nicknames.get(uid) or f'uid:{uid}'
                medalists.append({'rank': rank, 'nick': nick, 'score': score})
            out.append({
                'id': sid, 'title': title, 'start_ts': start_ts, 'end_ts': end_ts,
                'medalists': medalists,
            })
    return out


def _scheduler_loop():
    """매월 1일 KST 자정에 시즌 전환. 1분 단위로 깨어남."""
    while True:
        try:
            now = datetime.now(KST)
            # 다음 달 1일 0시까지 sleep
            target = _next_month_start(now)
            sleep_sec = max(60, (target - now).total_seconds())
            # 한 번에 너무 길게 자지 않게 1시간 단위
            time.sleep(min(sleep_sec, 3600))
            now = datetime.now(KST)
            # 새 달 1일이고 현재 시즌이 이전 달이면 전환
            cur = get_current_season()
            if cur:
                start = datetime.fromisoformat(cur['start_ts'])
                if (now.year, now.month) != (start.year, start.month):
                    end_current_season_and_start_new(now)
        except Exception as ex:
            print(f'[season] scheduler error: {ex}', flush=True)
            time.sleep(300)


def start_scheduler():
    """봇 시작 시 호출 — 시즌 보장 + 백그라운드 스케줄러 기동."""
    ensure_current_season()
    threading.Thread(target=_scheduler_loop, daemon=True).start()
    print('[season] scheduler started', flush=True)
