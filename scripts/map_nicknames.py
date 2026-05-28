"""카톡 export txt + chat_logs dump 매칭 → user_id ↔ nickname 매핑 추출."""
from __future__ import annotations
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TXT_PATH = Path(r'C:\Users\goodb\Downloads\KakaoTalk_20260528_2152_16_380_group.txt')
DUMP_PATH = ROOT / 'chat_logs_decrypted.json'
OUT_PATH = ROOT / 'nicknames.json'

DATE_RE = re.compile(r'^-+\s*(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일.*-+$')
MSG_RE = re.compile(r'^\[(.+?)\]\s*\[(오전|오후)\s*(\d{1,2}):(\d{2})\]\s*(.*)$')


def parse_txt(path: Path) -> list[tuple[int, str, str]]:
    """(timestamp_unix_minute, nickname, message_first_line) 리스트."""
    out = []
    current_date = None
    current_msg = None
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.rstrip('\n')
            m_date = DATE_RE.match(line)
            if m_date:
                y, mo, d = map(int, m_date.groups())
                current_date = (y, mo, d)
                current_msg = None
                continue
            if current_date is None:
                continue
            m_msg = MSG_RE.match(line)
            if m_msg:
                nick, ampm, hh, mm = m_msg.group(1), m_msg.group(2), int(m_msg.group(3)), int(m_msg.group(4))
                if ampm == '오후' and hh != 12:
                    hh += 12
                elif ampm == '오전' and hh == 12:
                    hh = 0
                y, mo, d = current_date
                ts = int(datetime(y, mo, d, hh, mm).timestamp())
                body = m_msg.group(5)
                out.append((ts, nick, body))
                current_msg = (ts, nick, body)
            elif current_msg:
                # 멀티라인 메시지 이어지는 라인 — 첫 줄 위주 매칭이라 skip
                pass
    return out


def main():
    print(f'txt: {TXT_PATH}')
    print(f'dump: {DUMP_PATH}')

    txt_msgs = parse_txt(TXT_PATH)
    print(f'  → txt 파싱: {len(txt_msgs)} 메시지')

    # chat_logs dump 로드
    with open(DUMP_PATH, encoding='utf-8') as f:
        dump = json.load(f)
    print(f'  → dump 로드: {len(dump)} rows')

    # (minute, message) → user_id 인덱스
    # chat_logs.created_at 은 string unix 초
    # txt 의 시간은 분 단위 → 같은 분 (60초 윈도우) + 같은 메시지 본문 매칭
    dump_index: dict = defaultdict(list)  # (minute_bucket, message) → [user_id]
    for r in dump:
        try:
            ts = int(r['created_at'])
        except (ValueError, TypeError):
            continue
        minute_bucket = ts // 60
        msg = (r.get('message') or '').strip()
        if not msg:
            continue
        uid = int(r['user_id'])
        dump_index[(minute_bucket, msg)].append(uid)

    # txt 매칭: (minute, msg) 찾기. ±1 분 윈도우 (시계 차이 보정)
    nick_to_uids: dict = defaultdict(Counter)  # nickname → Counter[user_id]
    matched = 0
    for ts, nick, body in txt_msgs:
        body = body.strip()
        if not body or body in ('사진', '이모티콘', '동영상', '파일', '음성메시지'):
            continue
        minute_bucket = ts // 60
        # ±1 분 윈도우
        for delta in (0, -1, 1):
            candidates = dump_index.get((minute_bucket + delta, body))
            if candidates:
                for uid in candidates:
                    nick_to_uids[nick][uid] += 1
                matched += 1
                break

    print(f'  → 매칭된 txt 메시지: {matched} / {len(txt_msgs)}')

    # 닉네임별 가장 자주 매칭된 user_id 채택
    uid_to_nick: dict = {}
    nick_stats = []
    for nick, counter in nick_to_uids.items():
        if not counter:
            continue
        uid, cnt = counter.most_common(1)[0]
        # 최소 매칭 임계 (false positive 거르기): 2회 이상
        if cnt >= 2:
            # 같은 user_id 가 다른 닉으로 잡힐 수도 — 가장 많이 잡힌 닉만 유지
            if uid in uid_to_nick:
                # 기존 채택 닉의 cnt 와 비교
                prev_nick, prev_cnt = uid_to_nick[uid]
                if cnt > prev_cnt:
                    uid_to_nick[uid] = (nick, cnt)
            else:
                uid_to_nick[uid] = (nick, cnt)
            nick_stats.append((nick, uid, cnt))

    print(f'  → 잠정 닉 매핑: {len(nick_stats)}')
    print(f'  → 최종 user_id 매핑: {len(uid_to_nick)}')

    # 정리
    final = {str(uid): nick for uid, (nick, _) in uid_to_nick.items()}

    with open(OUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(final, f, ensure_ascii=False, indent=2)
    print(f'\n저장: {OUT_PATH}  ({len(final)} 엔트리)')

    # 상위 10개 샘플
    print('\n--- 매칭 수 상위 20 ---')
    top = sorted(nick_stats, key=lambda x: -x[2])[:20]
    for nick, uid, cnt in top:
        print(f'  {cnt:5d}회  {uid}  → {nick}')


if __name__ == '__main__':
    main()
