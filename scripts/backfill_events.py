"""카톡 export txt 파싱 → 봇 응답 매칭 → zenny_events 백필 (v2 정확도 강화).

v2 개선:
- 잭팟·초기화는 봇 공지의 닉을 직접 매칭 (큐 무시, 가장 신뢰)
- 봇 거부 응답 패턴 인식 → 명령 큐 정확히 비움
- 명령 큐 항목이 봇 응답보다 N분 이상 오래되면 버림 (시간 정합성)

dry-run 기본 (DB 안 건드림). 실제 INSERT 는 --apply.
"""
from __future__ import annotations
import argparse
import json
import re
import sqlite3
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NICK_PATH = ROOT / 'nicknames.json'
DB_PATH = ROOT / 'members.db'

DATE_RE = re.compile(r'^-+\s*(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일.*-+$')
MSG_RE = re.compile(r'^\[(.+?)\]\s*\[(오전|오후)\s*(\d{1,2}):(\d{2})\]\s*(.*)$')

BOT_NICKS = {'다이애나/피리'}

# === 봇 응답 패턴 ===
# 출석 성공
ATTEND_OK_RE = re.compile(r'^출석 완료!\s*\+(\d+)제니\s*\(현재:\s*([\d,]+)제니\)')
# 출석 거부
ATTEND_NG_RE = re.compile(r'^이미 오늘 출석했어요')

# 잭팟·초기화 공지 (가장 정확 — 닉이 직접 들어있음)
JACKPOT_NOTICE_RE = re.compile(r'^🎰\s*(.+?)님이 잭팟을 터뜨렸습니다')
RESET_NOTICE_RE = re.compile(r'^💸\s*(.+?)님의 제니가 전부 사라졌습니다')

# 룰렛 결과 헤드 (+900%·초기화 제외하고 일반만 큐 매칭)
ROUL_HEAD_RE = re.compile(r'^[🎰💸]\s*룰렛 결과:\s*(.+)$')
ROUL_BETPAY_RE = re.compile(
    r'^([\d,]+)\s*→\s*([\d,]+)제니\s*\(([+-]?[\d,]+)제니\)'
    r'|^([\d,]+)\s*→\s*0제니\s*\(잔고 전부 소멸\)'
)
BAL_RE = re.compile(r'현재 제니:\s*([\d,]+)제니')

# 룰렛 거부 응답들
ROUL_NG_RE = re.compile(
    r'^오늘 룰렛 횟수를 다 사용했어요'
    r'|^\.룰렛 \[금액\]'
    r'|^\.룰렛 \[금액\] 또는'
    r'|^1 이상의 숫자를 입력해주세요'
    r'|^제니가 부족해요'
    r'|^제니가 없어요'
    r'|^1~100% 사이로 입력해주세요'
    r'|^\.룰렛 50% 처럼'
)

# 가위바위보 결과
RPS_HEAD_RE = re.compile(r'^([✌✊✋][️]?)\s*(가위|바위|보)\s+vs\s+([✌✊✋][️]?)\s*(가위|바위|보)')
RPS_RESULT_RE = re.compile(r'^(승리|무승부|패배)!')

# 가위바위보 거부 응답들
RPS_NG_RE = re.compile(
    r'^오늘 게임 횟수를 다 사용했어요'
    r'|^가위바위보는 올 베팅이 안 돼요'
    r'|^가위바위보는 지면 베팅을 전부 잃어요'
    r'|^\.가위 \[금액'
    r'|^\.가위 \[금액 또는 %\]'
    r'|^1 이상의 숫자를 입력해주세요'
    r'|^제니가 부족해요'
    r'|^1~100% 사이로 입력해주세요'
    r'|^\.가위 50% 처럼'
)

# 시간 매칭 최대 허용 (분) — 큐 항목이 이보다 오래되면 버림
MAX_LAG_MIN = 10


def parse_txt(path: Path):
    msgs = []
    current_date = None
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.rstrip('\n')
            m = DATE_RE.match(line)
            if m:
                y, mo, d = map(int, m.groups())
                current_date = (y, mo, d)
                continue
            if current_date is None:
                continue
            m = MSG_RE.match(line)
            if m:
                nick = m.group(1)
                ampm = m.group(2)
                hh = int(m.group(3))
                mm = int(m.group(4))
                if ampm == '오후' and hh != 12:
                    hh += 12
                elif ampm == '오전' and hh == 12:
                    hh = 0
                y, mo, d = current_date
                ts = datetime(y, mo, d, hh, mm)
                msgs.append([ts, nick, m.group(5)])
            elif msgs:
                msgs[-1][2] = (msgs[-1][2] or '') + '\n' + line
    return [(t, n, b) for t, n, b in msgs]


def parse_bet_arg(arg: str, balance_hint: int = 0):
    arg = (arg or '').strip()
    if not arg:
        return None
    if arg == '올':
        return balance_hint if balance_hint > 0 else None
    if arg.endswith('%'):
        try:
            pct = float(arg[:-1])
        except ValueError:
            return None
        if balance_hint <= 0:
            return None
        import math
        return math.ceil(balance_hint * pct / 100)
    try:
        return int(arg)
    except ValueError:
        return None


def prune_queue(queue, now: datetime):
    """큐에서 봇 응답보다 MAX_LAG_MIN 분 이상 오래된 명령 제거 (응답 없이 버려진 것)."""
    cutoff = now - timedelta(minutes=MAX_LAG_MIN)
    while queue and queue[0][0] < cutoff:
        queue.pop(0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('txt', type=Path)
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--db', type=Path, default=DB_PATH)
    ap.add_argument('--wipe', action='store_true', help='적용 전 zenny_events 전체 비움')
    args = ap.parse_args()

    with open(NICK_PATH, encoding='utf-8') as f:
        raw = json.load(f)
    nick_to_uid = {nick: int(uid) for uid, nick in raw.items()}

    print(f'txt: {args.txt}')
    print(f'nicknames: {len(nick_to_uid)} entries')
    print(f'DB: {args.db}')
    print(f'apply: {args.apply}  wipe: {args.wipe}')
    print()

    msgs = parse_txt(args.txt)
    print(f'파싱된 메시지: {len(msgs)}')

    cmds_attend = []   # [(ts, nick), ...]
    cmds_roul = []     # [(ts, nick, bet_arg)]
    cmds_rps = []      # [(ts, nick, hand, bet_arg)]
    balance_by_uid = {}
    events = []
    unmapped_for_notice = Counter()
    stat = Counter()

    def _lookback_roulette_info(idx, expect_head_starts):
        """직전 봇 메시지의 룰렛 결과 헤드에서 bet/payout/delta/balance 추출."""
        if idx == 0:
            return None, None, None, None
        prev_ts, prev_nick, prev_body = msgs[idx - 1]
        if prev_nick not in BOT_NICKS:
            return None, None, None, None
        plines = (prev_body or '').split('\n')
        if not plines or not any(plines[0].strip().startswith(p) for p in expect_head_starts):
            return None, None, None, None
        bet = payout = delta = balance = None
        if len(plines) >= 2:
            mm = ROUL_BETPAY_RE.match(plines[1].strip())
            if mm:
                if mm.group(1):
                    bet = int(mm.group(1).replace(',', ''))
                    payout = int(mm.group(2).replace(',', ''))
                    delta = int(mm.group(3).replace(',', ''))
                elif mm.group(4):  # 초기화 패턴 "X → 0제니 (잔고 전부 소멸)"
                    bet = int(mm.group(4).replace(',', ''))
                    payout = 0
                    delta = -bet
        if len(plines) >= 3:
            bm = BAL_RE.search(plines[2])
            if bm:
                balance = int(bm.group(1).replace(',', ''))
        return bet, payout, delta, balance

    for idx, (ts, nick, body) in enumerate(msgs):
        if not body:
            continue

        if nick in BOT_NICKS:
            lines = body.split('\n')
            line0 = lines[0].strip() if lines else ''

            # 1. 잭팟 공지 — 닉 직접 매칭 (가장 신뢰) + 직전 룰렛 헤드 lookback
            mj = JACKPOT_NOTICE_RE.match(line0)
            if mj:
                tnick = mj.group(1).strip()
                uid = nick_to_uid.get(tnick)
                if uid:
                    bet, payout, delta, bal = _lookback_roulette_info(idx, ['🎰 룰렛 결과: +900%'])
                    events.append((uid, ts, 'roulette', bet, payout, delta if delta is not None else 0,
                                   'jackpot', bal if bal is not None else 0))
                    stat['jackpot_notice'] += 1
                else:
                    unmapped_for_notice[tnick] += 1
                continue

            # 2. 초기화 공지 — 닉 직접 매칭 + 직전 룰렛 헤드 lookback
            mr = RESET_NOTICE_RE.match(line0)
            if mr:
                tnick = mr.group(1).strip()
                uid = nick_to_uid.get(tnick)
                if uid:
                    bet, payout, delta, bal = _lookback_roulette_info(idx, ['💸 룰렛 결과: 초기화'])
                    events.append((uid, ts, 'roulette', bet, 0, delta if delta is not None else 0,
                                   'reset', 0))
                    stat['reset_notice'] += 1
                else:
                    unmapped_for_notice[tnick] += 1
                continue

            # 3. 룰렛 결과 헤드 — 잭팟/초기화는 공지로 처리하니 큐 pop 안 함
            mh = ROUL_HEAD_RE.match(line0)
            if mh:
                outcome_raw = mh.group(1).strip()
                if outcome_raw in ('+900%', '초기화'):
                    continue  # 다음 공지에서 처리됨
                # 일반 룰렛 결과 → 큐 매칭
                prune_queue(cmds_roul, ts)
                if not cmds_roul:
                    stat['roul_no_queue'] += 1
                    continue
                bet = payout = delta = None
                balance = 0
                if len(lines) >= 2:
                    mm = ROUL_BETPAY_RE.match(lines[1].strip())
                    if mm:
                        if mm.group(1):
                            bet = int(mm.group(1).replace(',', ''))
                            payout = int(mm.group(2).replace(',', ''))
                            delta = int(mm.group(3).replace(',', ''))
                if len(lines) >= 3:
                    bm = BAL_RE.search(lines[2])
                    if bm:
                        balance = int(bm.group(1).replace(',', ''))
                sign = '+' if outcome_raw.startswith('+') else '-' if outcome_raw.startswith('-') else '+'
                num = re.sub(r'[^\d]', '', outcome_raw)
                out = f'r{sign}{num}'
                cmd_ts, cmd_nick, _bet_arg = cmds_roul.pop(0)
                uid = nick_to_uid.get(cmd_nick)
                if uid:
                    events.append((uid, cmd_ts, 'roulette', bet, payout, delta, out, balance))
                    if balance:
                        balance_by_uid[uid] = balance
                    stat['roul_ok'] += 1
                else:
                    stat['roul_unmapped'] += 1
                continue

            # 4. 룰렛 거부 응답 — 큐 pop만
            if ROUL_NG_RE.match(line0):
                prune_queue(cmds_roul, ts)
                if cmds_roul:
                    cmds_roul.pop(0)
                    stat['roul_reject'] += 1
                continue

            # 5. 출석 성공
            m = ATTEND_OK_RE.match(line0)
            if m:
                reward = int(m.group(1))
                balance = int(m.group(2).replace(',', ''))
                prune_queue(cmds_attend, ts)
                if not cmds_attend:
                    stat['attend_no_queue'] += 1
                    continue
                cmd_ts, cmd_nick = cmds_attend.pop(0)
                uid = nick_to_uid.get(cmd_nick)
                if uid:
                    events.append((uid, cmd_ts, 'attend', None, reward, reward, 'attend', balance))
                    balance_by_uid[uid] = balance
                    stat['attend_ok'] += 1
                else:
                    stat['attend_unmapped'] += 1
                continue

            # 6. 출석 거부
            if ATTEND_NG_RE.match(line0):
                prune_queue(cmds_attend, ts)
                if cmds_attend:
                    cmds_attend.pop(0)
                    stat['attend_reject'] += 1
                continue

            # 7. 가위바위보 결과
            if RPS_HEAD_RE.match(line0):
                rh = RPS_HEAD_RE.match(line0)
                bot_hand = rh.group(4)
                result_kr = None
                if len(lines) >= 2:
                    rr = RPS_RESULT_RE.match(lines[1].strip())
                    if rr:
                        result_kr = rr.group(1)
                if result_kr is None:
                    stat['rps_no_result'] += 1
                    continue
                balance = 0
                if len(lines) >= 3:
                    bm = BAL_RE.search(lines[2])
                    if bm:
                        balance = int(bm.group(1).replace(',', ''))
                prune_queue(cmds_rps, ts)
                if not cmds_rps:
                    stat['rps_no_queue'] += 1
                    continue
                cmd_ts, cmd_nick, cmd_hand, bet_arg = cmds_rps.pop(0)
                uid = nick_to_uid.get(cmd_nick)
                if uid is None:
                    stat['rps_unmapped'] += 1
                    continue
                bet = parse_bet_arg(bet_arg, balance_by_uid.get(uid, 0))
                if result_kr == '승리':
                    res = 'win'; payout = int(round((bet or 0) * 2.5)); delta = payout - (bet or 0)
                elif result_kr == '무승부':
                    res = 'draw'; payout = bet or 0; delta = 0
                else:
                    res = 'lose'; payout = 0; delta = -(bet or 0)
                events.append((uid, cmd_ts, 'rps', bet, payout, delta,
                               f'rps_{res}_{cmd_hand}_vs_{bot_hand}', balance))
                if balance:
                    balance_by_uid[uid] = balance
                stat['rps_ok'] += 1
                continue

            # 8. 가위바위보 거부
            if RPS_NG_RE.match(line0):
                prune_queue(cmds_rps, ts)
                if cmds_rps:
                    cmds_rps.pop(0)
                    stat['rps_reject'] += 1
                continue

            continue  # 다른 봇 메시지

        # 사용자 메시지 — 명령 큐 push
        b = body.strip()
        if b in ('.출석', '.출석체크', '.출첵'):
            cmds_attend.append((ts, nick))
        elif b.startswith('.룰렛'):
            arg = b[len('.룰렛'):].strip()
            cmds_roul.append((ts, nick, arg))
        elif b.startswith('.가위') or b.startswith('.바위') or b.startswith('.보'):
            for h in ('가위', '바위', '보'):
                pre = '.' + h
                if b == pre or b.startswith(pre + ' '):
                    arg = b[len(pre):].strip()
                    cmds_rps.append((ts, nick, h, arg))
                    break

    print()
    print('=== 통계 ===')
    for k in sorted(stat):
        print(f'  {k:22}: {stat[k]}')
    print(f'\n전체 이벤트: {len(events)}')

    print('\n=== 잭팟 사례 ===')
    jp = [e for e in events if e[6] == 'jackpot']
    print(f'총 {len(jp)}회')
    for e in jp:
        u = next((n for n, x in nick_to_uid.items() if x == e[0]), str(e[0]))
        print(f'  {e[1]}  {u}')

    print('\n=== 초기화 사례 ===')
    rs = [e for e in events if e[6] == 'reset']
    print(f'총 {len(rs)}회')
    for e in rs:
        u = next((n for n, x in nick_to_uid.items() if x == e[0]), str(e[0]))
        print(f'  {e[1]}  {u}')

    if unmapped_for_notice:
        print('\n=== 잭팟/초기화 공지인데 매핑 없는 닉 ===')
        for n, c in unmapped_for_notice.most_common():
            print(f'  {c}회  {n}')

    if not args.apply:
        print('\n(dry-run)')
        return

    conn = sqlite3.connect(args.db)
    cur = conn.cursor()
    if args.wipe:
        n = cur.execute('SELECT COUNT(*) FROM zenny_events').fetchone()[0]
        cur.execute('DELETE FROM zenny_events')
        print(f'\nWIPE: {n} rows deleted')
    inserted = skipped = 0
    for uid, ts, kind, bet, payout, delta, outcome, bal in events:
        ts_iso = ts.isoformat(timespec='seconds')
        dup = cur.execute(
            'SELECT 1 FROM zenny_events WHERE user_id=? AND ts=? AND kind=? AND outcome=?',
            (uid, ts_iso, kind, outcome),
        ).fetchone()
        if dup:
            skipped += 1
            continue
        cur.execute(
            '''INSERT INTO zenny_events
               (user_id, ts, kind, bet, payout, delta, outcome, balance_after)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
            (uid, ts_iso, kind, bet, payout, delta, outcome, bal),
        )
        inserted += 1
    conn.commit()
    conn.close()
    print(f'\nINSERT: {inserted}  SKIP(중복): {skipped}')


if __name__ == '__main__':
    main()
