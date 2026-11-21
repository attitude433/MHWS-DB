"""몬헌 프론티어 Z 한국어판 사설 서버 안내 (.프론티어 명령 + 매일 17시 공지).

서버 상태는 같은 인스턴스의 프론티어 웹(mhf-web, 127.0.0.1:8090/status → Erupe API /health)으로 확인.
홈페이지 http://zz.diana.ai.kr (다운로드·설치 안내, 회원가입은 게임 런처에서).
"""
import json
import random
import urllib.request

HOME_URL = 'http://zz.diana.ai.kr'
STATUS_URL = 'http://127.0.0.1:8090/status'


def is_online() -> bool | None:
    """True=열림, False=꺼짐, None=확인 불가"""
    try:
        with urllib.request.urlopen(STATUS_URL, timeout=3) as r:
            return bool(json.loads(r.read().decode('utf-8')).get('online'))
    except Exception:
        return None


def info_text() -> str:
    on = is_online()
    state = {True: '🟢 서버 열림', False: '🔴 서버 꺼짐 (점검 중)', None: '⚪ 서버 상태 확인 불가'}[on]
    return (
        '🐉 몬스터 헌터 프론티어 Z 한국어판 (사설 서버)\n'
        f'{state}\n'
        '\n'
        f'📥 다운로드·설치 안내: {HOME_URL}\n'
        '\n'
        '1. 홈페이지에서 완성본을 받아 압축 풀기\n'
        '2. mhf.exe 실행\n'
        '3. 런처에서 회원가입 → 로그인 → 새 캐릭터 (이름은 영문·숫자)\n'
        '\n'
        '※ 다른 데서 쓰는 아이디·비번은 쓰지 마세요!'
    )


DAILY_MESSAGES = [
    '🐉 몬헌 프론티어 한국어판 사설 서버 열려 있어요! 같이 사냥할 사람~\n📥 {url}  (자세한 건 .프론티어)',
    '🐉 오늘도 프론티어 사설섭 열었어요! 옛날 그 프론티어, 한국어로 해볼 수 있어요\n📥 {url}',
    '🐉 저녁엔 프론티어 한 판 어때요? 한국어판 사설 서버 운영 중이에요\n📥 {url}  (.프론티어 로 안내 보기)',
]


def daily_messages() -> list[str]:
    """스케줄러용: 서버가 꺼져 있으면 공지하지 않음(빈 목록)."""
    if is_online() is False:
        return []
    return [random.choice(DAILY_MESSAGES).format(url=HOME_URL)]
