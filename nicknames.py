"""user_id → nickname 매핑.

nicknames.json 을 모듈 load 시 한 번 읽어 메모리에 캐싱.
+ Iris db2.open_chat_member 의 암호화 닉을 봇 계정 키로 실시간 복호화해 자동 채움
  (refresh_from_iris / resolve_one). 수동 update() 는 오버라이드로 계속 사용 가능.
"""
from __future__ import annotations
import json
import threading
import time
from pathlib import Path

JSON_PATH = Path(__file__).resolve().parent / 'nicknames.json'

# 카톡 이름은 DB 소유자(봇 계정) user_id 키로 enc 복호화됨. 자동 감지 실패 시 폴백.
BOT_UID_FALLBACK = 441510000
_bot_uid: int | None = None

_lock = threading.Lock()
_data: dict = {}
# uid → 마지막으로 관측한 암호화 닉 토큰 (ctx.sender.name). 값이 바뀌면 닉변으로 간주.
_last_cipher: dict = {}


def _load():
    global _data
    if JSON_PATH.exists():
        try:
            with open(JSON_PATH, encoding='utf-8') as f:
                raw = json.load(f)
            _data = {int(k): v for k, v in raw.items() if v}
        except Exception:
            _data = {}
    else:
        _data = {}


def _persist() -> None:
    try:
        with open(JSON_PATH, 'w', encoding='utf-8') as f:
            json.dump({str(k): v for k, v in _data.items()}, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def get(user_id: int) -> str:
    return _data.get(int(user_id), '')


def update(user_id: int, nickname: str) -> None:
    if not user_id or not nickname:
        return
    with _lock:
        _data[int(user_id)] = nickname
        _persist()


def all_mappings() -> dict:
    return dict(_data)


# === Iris 실시간 닉 복호화 ===

def _detect_bot_uid(api) -> int:
    """봇 자신이 보낸 로그(isMine:true)의 user_id = DB 소유자. 실패 시 폴백 상수."""
    global _bot_uid
    if _bot_uid:
        return _bot_uid
    try:
        rows = api.query(
            'SELECT user_id FROM chat_logs WHERE v LIKE ? '
            'GROUP BY user_id ORDER BY COUNT(*) DESC LIMIT 1',
            ['%"isMine":true%'],
        )
        if rows:
            _bot_uid = int(rows[0]['user_id'])
    except Exception:
        pass
    if not _bot_uid:
        _bot_uid = BOT_UID_FALLBACK
    return _bot_uid


def _decrypt_member(api, user_id: int) -> str:
    """open_chat_member 암호화 닉 → 봇 키로 복호화. 실패 시 ''"""
    try:
        rows = api.query(
            'SELECT nickname, enc FROM db2.open_chat_member WHERE user_id = ?',
            [int(user_id)],
        )
        if not rows:
            return ''
        cipher, enc = rows[0].get('nickname'), rows[0].get('enc')
        if not cipher or enc is None:
            return ''
        return api.decrypt(int(enc), cipher, _detect_bot_uid(api)) or ''
    except Exception:
        return ''


def cipher_changed(user_id: int, ciphertext: str) -> bool:
    """이 유저의 암호화 닉 토큰이 마지막 관측값과 달라졌으면 True (닉변 감지).

    관측값을 즉시 갱신하므로, True 를 받은 쪽에서 resolve_one 재복호화하면 됨.
    """
    if not ciphertext:
        return False
    uid = int(user_id)
    if _last_cipher.get(uid) != ciphertext:
        _last_cipher[uid] = ciphertext
        return True
    return False


def resolve_one(api, user_id: int) -> str:
    """단일 유저 실시간 복호화 + 캐시. 실패 시 기존 캐시값."""
    plain = _decrypt_member(api, user_id)
    if plain:
        with _lock:
            if _data.get(int(user_id)) != plain:
                _data[int(user_id)] = plain
                _persist()
        return plain
    return get(user_id)


def resolve_from_feed(api, user_id: int) -> str:
    """open_chat_member 복호화 실패 폴백: 최근 feed 메시지(입장/닉변)의 평문 nickName 추출.

    feedType 피드 JSON 의 members[].nickName 이 평문이라, open_chat_member 가 깨진
    특이 케이스도 잡음. 메시지는 발신자 키로 복호화.
    """
    uid = int(user_id)
    try:
        rows = api.query(
            'SELECT v, message FROM chat_logs WHERE user_id = ? '
            'ORDER BY created_at DESC LIMIT 10', [uid])
    except Exception:
        return ''
    for r in rows:
        cipher = r.get('message')
        if not cipher:
            continue
        enc = 31
        try:
            enc = int((json.loads(r.get('v') or '{}')).get('enc', 31))
        except Exception:
            pass
        try:
            plain = api.decrypt(enc, cipher, uid)
        except Exception:
            continue
        if not plain or 'nickName' not in plain:
            continue
        try:
            fd = json.loads(plain)
        except Exception:
            continue
        for mem in fd.get('members', []):
            try:
                if int(mem.get('userId', 0)) == uid and mem.get('nickName'):
                    nn = mem['nickName']
                    with _lock:
                        if _data.get(uid) != nn:
                            _data[uid] = nn
                            _persist()
                    return nn
            except Exception:
                continue
    return ''


def refresh_from_iris(api) -> int:
    """open_chat_member 를 봇 키로 복호화해 캐시 갱신. 변경 건수 반환.

    최적화: 암호문(nickname 토큰)이 직전과 달라진 유저만 복호화.
    → 평소엔 쿼리 1번 + 복호화 0건 (닉변 시에만 그 사람만). 짧은 주기로 돌려도 부하 ~0.
    """
    try:
        rows = api.query('SELECT user_id, nickname, enc FROM db2.open_chat_member')
    except Exception:
        return 0
    bot_uid = _detect_bot_uid(api)
    todo = []  # 암호문 바뀐 유저만
    for r in rows:
        try:
            uid = int(r['user_id'])
            cipher, enc = r.get('nickname'), r.get('enc')
            if not cipher or enc is None:
                continue
            if _last_cipher.get(uid) == cipher:
                continue  # 변경 없음 → 복호화 스킵
            todo.append((uid, cipher, enc))
        except Exception:
            continue
    changed = 0
    for uid, cipher, enc in todo:
        try:
            plain = api.decrypt(int(enc), cipher, bot_uid)
        except Exception:
            continue
        if not plain:
            continue
        with _lock:
            _last_cipher[uid] = cipher  # 토큰 시딩
            if _data.get(uid) != plain:
                _data[uid] = plain
                changed += 1
    if changed:
        with _lock:
            _persist()
    return changed


def start_auto_refresh(api, interval: int = 180) -> None:
    """백그라운드: 시작 시 1회 + interval(기본 3분)마다 open_chat_member 복호화 갱신.

    변경분만 복호화하므로 짧은 주기여도 부하 거의 없음. 닉변이 ≤interval 내 반영됨.
    """
    def _loop():
        while True:
            try:
                n = refresh_from_iris(api)
                print(f'[nicknames] refresh: {n}건 갱신 (총 {len(_data)})', flush=True)
            except Exception as ex:
                print(f'[nicknames] refresh error: {ex}', flush=True)
            time.sleep(interval)
    threading.Thread(target=_loop, daemon=True).start()


_load()
