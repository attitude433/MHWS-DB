"""카톡 export txt 파싱 → 봇 응답 매칭 → zenny_events 백필.

dry-run 기본 (DB 안 건드림). 실제 INSERT 는 --apply 인자.
"""
from __future__ import annotations
import argparse
import json
import re
import sqlite3
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NICK_PATH = ROOT / 'nicknames.json'
DB_PATH = ROOT / 'members.db'  # 인스턴스에서 실행시엔 /home/ubuntu/mhws-bot/members.db

DATE_RE = re.compile(r'^-+\s*(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일.*-+$')
MSG_RE = re.compile(r'^\[(.+?)\]\s*\[(오전|오후)\s*(\d{1,2}):(\d{2})\]\s*(.*)$')

BOT_NICKS = {'다이애나/피리'}  # 봇 이름. 닉변 시 확장

# 봇 응답 패턴
ATTEND_RE = re.compile(r'^출석 완료!\s*\+(\d+)제니\s*\(현재:\s*([\d,]+)제니\)')
# 룰렛 헤드: "🎰 룰렛 결과: +25%" 또는 "💸 룰렛 결과: 초기화" 또는 "🎰 룰렛 결과: +900%"
ROUL_HEAD_RE = re.compile(r'^[🎰💸]\s*룰렛 결과:\s*(.+)$')
# 룰렛 베팅/환급 줄: "1,000 → 1,250제니 (+250제니)" 또는 "1,000 → 0제니 (잔고 전부 소멸)"
ROUL_BETPAY_RE = re.compile(
    r'^([\d,]+)\s*→\s*([\d,]+)제니\s*\(([+-]?[\d,]+)제니\)$'
    r'|^([\d,]+)\s*→\s*0제니\s*\(잔고 전부 소멸\)$'
)
# 가위바위보 헤드: "✌️ 가위  vs  ✊ 바위"
RPS_HEAD_RE = re.compile(r'^([✌✊✋][️]?)\s*(가위|바위|보)\s+vs\s+([✌✊✋][️]?)\s*(가위|바위|보)')
# 가위바위보 결과: "승리! +750제니" / "패배! -500제니" / "무승부! 베팅 반환"
RPS_RESULT_RE = re.compile(r'^(승리|무승부|패배)!')
# 현재 잔고 줄: "현재 제니: 10,750제니 (오늘 2회 남음)"
BAL_RE = re.compile(r'현재 제니:\s*([\d,]+)제니')


def parse_txt(path: Path):
    """각 메시지를 (ts, nick, body) 로 반환. 멀티라인 body 이어붙임."""
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
                # 멀티라인 — 직전 메시지에 이어붙임
                msgs[-1][2] = (msgs[-1][2] or '') + '\n' + line
    return [(t, n, b) for t, n, b in msgs]


def parse_bet_arg(arg: str, balance_hint: int = 0) -> int | None:
    """`.룰렛 1000` / `.룰렛 50%` / `.룰렛 올` 에서 베팅액 추출.

    퍼센트/올은 balance 알아야 정확. 모르면 None.
    """
    arg = arg.strip()
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('txt', type=Path)
    ap.add_argument('--apply', action='store_true', help='DB INSERT 실제 적용')
    ap.add_argument('--db', type=Path, default=DB_PATH)
    args = ap.parse_args()

    # 닉 → uid 매핑 (역방향)
    with open(NICK_PATH, encoding='utf-8') as f:
        raw = json.load(f)
    nick_to_uid = {nick: int(uid) for uid, nick in raw.items()}

    print(f'txt: {args.txt}')
    print(f'nicknames: {len(nick_to_uid)} entries')
    print(f'DB: {args.db}')
    print(f'apply: {args.apply}')
    print()

    msgs = parse_txt(args.txt)
    print(f'파싱된 메시지: {len(msgs)}')

    # 사용자 명령 큐 (시간 순)
    cmds_attend = []  # (ts, nick)
    cmds_roulette = []  # (ts, nick, bet_arg)
    cmds_rps = []  # (ts, nick, hand, bet_arg)

    # 사용자별 잔고 추적 (퍼센트/올 베팅 계산용)
    balance_by_uid = {}

    events = []  # 매칭된 이벤트
    unmapped_nicks = Counter()
    matched_cmds_attend = 0
    matched_cmds_roul = 0
    matched_cmds_rps = 0

    for ts, nick, body in msgs:
        if not body:
            continue

        # 봇 메시지
        if nick in BOT_NICKS:
            lines = body.split('\n')
            line0 = lines[0].strip() if lines else ''

            # 출석 응답
            m = ATTEND_RE.match(line0)
            if m and cmds_attend:
                reward = int(m.group(1))
                balance = int(m.group(2).replace(',', ''))
                cmd_ts, cmd_nick = cmds_attend.pop(0)
                uid = nick_to_uid.get(cmd_nick)
                if uid:
                    events.append((uid, cmd_ts, 'attend', None, reward, reward, 'attend', balance))
                    balance_by_uid[uid] = balance
                    matched_cmds_attend += 1
                else:
                    unmapped_nicks[cmd_nick] += 1
                continue

            # 룰렛 응답
            m = ROUL_HEAD_RE.match(line0)
            if m and cmds_roulette:
                outcome_raw = m.group(1).strip()  # "+25%", "초기화", "+900%"
                bet = payout = delta = None
                balance = 0
                if len(lines) >= 2:
                    mm = ROUL_BETPAY_RE.match(lines[1].strip())
                    if mm:
                        if mm.group(1):  # 일반
                            bet = int(mm.group(1).replace(',', ''))
                            payout = int(mm.group(2).replace(',', ''))
                            delta = int(mm.group(3).replace(',', ''))
                        else:  # 초기화
                            bet = int(mm.group(4).replace(',', ''))
                            payout = 0
                            delta = -bet  # 룰렛 초기화는 잔고 전부 소멸이므로 사실 delta != -bet 인데... 일단 베팅액으로
                if len(lines) >= 3:
                    bm = BAL_RE.search(lines[2])
                    if bm:
                        balance = int(bm.group(1).replace(',', ''))

                if outcome_raw == '초기화':
                    out = 'reset'
                    # 초기화는 잔고 전부 사라지므로 delta = -prev_balance
                    # bet 은 베팅액(=올이면 prev_balance, 일부면 그 일부)
                    # 정확한 delta 는 prev_balance - 0 = prev_balance
                    prev_bal = balance_by_uid.get(0, 0)  # not really needed
                elif outcome_raw == '+900%':
                    out = 'jackpot'
                else:
                    # "+25%" 같은 형태
                    sign = '+' if outcome_raw.startswith('+') else '-' if outcome_raw.startswith('-') else '+'
                    num = re.sub(r'[^\d]', '', outcome_raw)
                    out = f'r{sign}{num}'

                cmd_ts, cmd_nick, bet_arg = cmds_roulette.pop(0)
                uid = nick_to_uid.get(cmd_nick)
                if uid:
                    # 초기화면 delta 는 balance_by_uid[uid] (직전 잔고)
                    if out == 'reset':
                        prev = balance_by_uid.get(uid, bet or 0)
                        delta = -prev
                        bet = bet or prev
                    events.append((uid, cmd_ts, 'roulette', bet, payout, delta, out, balance))
                    if balance:
                        balance_by_uid[uid] = balance
                    matched_cmds_roul += 1
                else:
                    unmapped_nicks[cmd_nick] += 1
                continue

            # 가위바위보 응답
            if RPS_HEAD_RE.match(line0) and cmds_rps:
                rh_match = RPS_HEAD_RE.match(line0)
                user_hand = rh_match.group(2)
                bot_hand = rh_match.group(4)
                result_kr = None
                if len(lines) >= 2:
                    rm = RPS_RESULT_RE.match(lines[1].strip())
                    if rm:
                        result_kr = rm.group(1)
                balance = 0
                if len(lines) >= 3:
                    bm = BAL_RE.search(lines[2])
                    if bm:
                        balance = int(bm.group(1).replace(',', ''))

                cmd_ts, cmd_nick, cmd_hand, bet_arg = cmds_rps.pop(0)
                uid = nick_to_uid.get(cmd_nick)
                if uid:
                    bet = parse_bet_arg(bet_arg, balance_by_uid.get(uid, 0))
                    if result_kr == '승리':
                        result_en = 'win'
                        payout = int(round((bet or 0) * 2.5))
                        delta = payout - (bet or 0)
                    elif result_kr == '무승부':
                        result_en = 'draw'
                        payout = bet or 0
                        delta = 0
                    elif result_kr == '패배':
                        result_en = 'lose'
                        payout = 0
                        delta = -(bet or 0)
                    else:
                        cmds_rps.insert(0, (cmd_ts, cmd_nick, cmd_hand, bet_arg))
                        continue
                    events.append((uid, cmd_ts, 'rps', bet, payout, delta,
                                   f'rps_{result_en}_{cmd_hand}_vs_{bot_hand}', balance))
                    if balance:
                        balance_by_uid[uid] = balance
                    matched_cmds_rps += 1
                else:
                    unmapped_nicks[cmd_nick] += 1
                continue

            continue  # 봇 메시지지만 위 패턴 매칭 안 됨 (잡담·공지 등)

        # 사용자 메시지 — 명령어 큐에 push
        b = body.strip()
        if b in ('.출석', '.출석체크', '.출첵'):
            cmds_attend.append((ts, nick))
        elif b.startswith('.룰렛'):
            arg = b[len('.룰렛'):].strip()
            if not arg or arg in ('올',) or arg.endswith('%') or arg.replace(',', '').replace('-', '').isdigit():
                cmds_roulette.append((ts, nick, arg))
        elif b.startswith('.가위') or b.startswith('.바위') or b.startswith('.보'):
            for h in ('가위', '바위', '보'):
                pre = '.' + h
                if b == pre or b.startswith(pre + ' '):
                    arg = b[len(pre):].strip()
                    cmds_rps.append((ts, nick, h, arg))
                    break

    print()
    print(f'사용자 명령 큐 잔여(매칭 실패) — 출석 {len(cmds_attend)} / 룰렛 {len(cmds_roulette)} / 가위바위보 {len(cmds_rps)}')
    print(f'매칭 성공 — 출석 {matched_cmds_attend} / 룰렛 {matched_cmds_roul} / 가위바위보 {matched_cmds_rps}')
    print(f'전체 이벤트 추출: {len(events)}')

    # 종류별 분포
    kind_cnt = Counter(e[2] for e in events)
    outcome_cnt = Counter(e[6] for e in events)
    print('\n=== 종류별 ===')
    for k, c in kind_cnt.most_common():
        print(f'  {k:10}: {c}')
    print('\n=== outcome 상위 15 ===')
    for o, c in outcome_cnt.most_common(15):
        print(f'  {o:30}: {c}')

    if unmapped_nicks:
        print(f'\n=== 매핑 안 된 닉으로 명령 친 사람들 (top 10) ===')
        for n, c in unmapped_nicks.most_common(10):
            print(f'  {c:4d}회  {n}')

    # 잭팟·초기화 샘플
    print('\n=== 잭팟 사례 (top 10) ===')
    jp = [e for e in events if e[6] == 'jackpot']
    print(f'  총 {len(jp)}회')
    for e in jp[:10]:
        uid_nick = next((n for n, u in nick_to_uid.items() if u == e[0]), str(e[0]))
        print(f'  {e[1]}  {uid_nick}  bet={e[3]} payout={e[4]} delta={e[5]:+}')

    print('\n=== 초기화 사례 (top 10) ===')
    rs = [e for e in events if e[6] == 'reset']
    print(f'  총 {len(rs)}회')
    for e in rs[:10]:
        uid_nick = next((n for n, u in nick_to_uid.items() if u == e[0]), str(e[0]))
        print(f'  {e[1]}  {uid_nick}  delta={e[5]:+}')

    if not args.apply:
        print('\n(dry-run — DB 안 건드림. --apply 로 실제 적용)')
        return

    # 실제 적용
    conn = sqlite3.connect(args.db)
    cur = conn.cursor()
    # 중복 방지 — 같은 user_id + ts + kind + outcome 있으면 skip
    inserted = 0
    skipped = 0
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
    print(f'\nINSERT: {inserted} / SKIP (중복): {skipped}')


if __name__ == '__main__':
    main()
