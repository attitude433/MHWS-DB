# 몬스터헌터 와일즈 카톡봇

## 프로젝트 개요

- 몬스터헌터 와일즈 카카오톡 오픈채팅방 정보 봇
- DB는 게임 파일 직접 추출 (mhdb-wilds-data 기반) + 인벤/나무위키 보강

## 운영 환경

- 서버: Oracle Cloud Always Free (ARM Ampere A1 인스턴스)
- 봇 클라이언트: redroid (도커 안드로이드) + Iris + 카카오톡
- 봇 서버: 파이썬 (irispy-client로 Iris와 HTTP 통신)
- 봇 계정: 별도 카카오 계정 (본 계정과 분리)

### 동작 흐름

```
[카카오톡 오픈채팅방]
    ↓
[redroid: 카카오톡 + Iris]
    ↓ HTTP
[Python 서버: 명령어 파싱 + DB 조회 + 응답 생성]
    ↓
[Iris → 카카오톡 → 오픈채팅방]
```

## 명령어 명세

| 명령어 | 처리 방식 | 비용 |
|---|---|---|
| `.명령어` | 고정 응답 | 무료 |
| `.정보 [몬스터]` | 로컬 DB 조회 | 무료 |
| `.스킬 [스킬명]` | 로컬 DB 조회 | 무료 |
| `.스킬 [스킬명] 장비` | 로컬 DB 조회 | 무료 |
| `.소재 [소재명]` | 로컬 DB 조회 | 무료 |
| `.커스텀` | 고정 응답 (시뮬레이터 링크) | 무료 |
| `.커스텀 [무기]` | 고정 응답 (디씨 가이드 링크) | 무료 |
| `.챗 [질문]` | Claude API (RAG) | 유료 (1~2원/질문) |

상세 출력 형식은 `MHWS_BOT_SPEC.md` 참조.

## DB 구조

### 메인 게임 데이터
- `items.json` (773): 아이템
- `monsters.json` (34): 대형 몬스터
- `armor.json` (194 세트 / 714 피스): 방어구
- `weapons_all.json` (1,188): 무기 14종
- `accessories.json` (361): 장식주
- `charms.json` (187): 호신구
- `skills.json` (179): 스킬
- `kinsects.json` (21): 사냥벌레
- `stages.json` (5): 필드

### Enemy 통합
- `all_enemies.json` (148): 통합 마스터
- `small_monsters.json` (19): 소형
- `animals_official.json` (70): 환경생물
- `animals_fishing.json` (20): 낚시 환경생물
- `boss_titles.json` (140): 보스 칭호
- `enemy_packs.json` (4): 무리

### 전투/공략
- `weapon_attributes.json`: 9속성
- `special_attack_types.json`: 특수공격 29종
- `special_attack_countermeasures.json`: 특수공격 대처
- `status_countermeasures.json`: 속성/상태이상별 효과적 무기/스킬

### 퀘스트/세계관
- `quests_official.json`: 146 미션
- `monster_to_quests_official.json`: 몬스터→퀘스트
- `environments.json`: 필드/캠프/시간대/계절/기상
- `game_misc.json`: NPC + 시설 + 요리

### 매핑 (mapping/)
- `skill_to_equipment_1.json` (4,587 연결)
- `item_usage.json` (8,535 연결)
- `weapon_trees.json` / `series_to_weapons.json` / `species_to_monsters.json`
- `external_guides.json` (디씨 무기별 가이드 14개)
- `reference.json` (종족/부위/시리즈/강화 테이블)

## 별칭 사전 v1.0

몬스터 별칭 16종 등록. 상세는 `MHWS_BOT_SPEC.md` 참조.

## 완료된 작업

- DB 한글화: `kind_kr` 9개 enum 보강 + `carve` 박피→갈무리 (`monsters.json`, `mapping/item_usage.json`)
- Python 서버 코드 구현 완료: `main.py`, `db.py`, `alias.py`, `commands/` (info/skill/material/custom/chat)
- 모든 명령어 출력 형식 확정 및 검증
- 운영 환경 셋업 (Oracle Cloud + redroid + Iris + 봇 systemd 영구화) — 절차는 아래 "운영 환경 셋업 절차" 섹션 참조

## 미해결 작업

### 1. 검색 미스 처리
- 못 찾았을 때 응답 형식 (유사어 제안 등)

### 2. `.챗` 고도화 (선택)
- 현재: 키워드 매칭 기반 RAG (Haiku)
- 개선 시: 임베딩 검색 / 모델 업그레이드

### 3. 추가 기능 (선택)
- 공식 SNS (X / 인스타) 새 글 알림 (하루 2회 폴링)

## 운영 환경 셋업 절차

> 인스턴스 IP, SSH 사용자명, 키 경로 등 실제 값은 `OPS_LOCAL.md` 참조 (gitignored).

### 인프라
- Oracle Cloud Always Free / ARM Ampere A1 / Ubuntu 24.04 / 4 OCPU / 24GB RAM
- 호스트네임: `server`

### 부팅 자동화 (영구화)
- `/etc/modules-load.d/binder.conf` — `binder_linux` 자동 적재
- `/etc/systemd/system/dev-binderfs.mount` — binderfs 자동 마운트 (enabled)
- redroid 컨테이너 — `--restart unless-stopped`
- `mhws-iris.service` (oneshot) — redroid 부팅 대기 + `adb forward tcp:3000 tcp:3000` + Iris 시작
- `mhws-bot.service` — Python 봇 (After=mhws-iris.service)

### 핵심 파일/경로
- `/etc/systemd/system/mhws-iris.service`, `mhws-bot.service`
- `/usr/local/bin/mhws-iris-wait.sh`, `mhws-iris-start.sh`
- `~/mhws-bot/` — 봇 코드 + venv + `.env`
- `~/redroid-data/` — 안드 컨테이너 데이터 (카톡 로그인 보존)
- `/data/local/tmp/Iris.apk` — redroid 안

### redroid 컨테이너
```
docker run -itd --privileged --name redroid \
  --restart unless-stopped \
  -v ~/redroid-data:/data \
  -p 5555:5555 \
  redroid/redroid:13.0.0_64only-latest
```

### 봇 의존성
- `requirements.txt` 의 `irisclient` 는 ❌ (PyPI 의 동명 다른 프로젝트)
- ✅ `pip install git+https://github.com/dolidolih/irispy-client.git` 로 설치 (`from iris import Bot`)

### .env 형식
```
IRIS_SERVER_URL=127.0.0.1:3000   # IP:PORT (http:// 제외, localhost 안 됨)
ANTHROPIC_API_KEY=               # .챗 명령용 (선택)
SNS_ROOM_NAME=                   # SNS 폴러용 (선택)
```

### 카톡 부계정 첫 셋업
1. scrcpy 로 redroid 화면 미러링 후 카톡 로그인
2. 본인 메인 카톡 → 부계정으로 메시지 1~2개 보내서 NotificationReferer 채우기
3. (없으면 Iris 가 `failed to extract referer from data` 로 시작 안 됨)

### 알려진 이슈
- redroid 안에 옛 Iris process 가 남아 포트 3000 잡고 있으면 새 카톡 메시지 인식 못 함 → `adb shell su root pkill -f party.qwer.iris.Main` 후 `mhws-iris.service` 재시작
- 새 카카오 계정 만들 때 보안 정보(비번/백업 이메일) 미리 등록해야 redroid 첫 로그인 시 12시간 락 회피

## 봇 계정

- 본 계정과 분리된 별도 카카오 계정 사용
- 계정 정보(이메일/비번/번호 등)는 `.env`에 보관
- `.env`는 `.gitignore`에 등록 (절대 커밋 금지)

## 작업 규칙

- 코드/문서 수정 전 허락 구하기
- 사용자가 요청하지 않은 부분 임의 추가 금지
- 교정/수정 요청 시 결과물만 출력 (변경 이유 부연 생략)
- 코드는 핵심 로직만 (주석/예시/사용법 추가 요청 없으면 생략)
- 형식·구조 임의 변경 금지
- 모르는 건 추측하지 말고 "모른다"고 하기
- 한국어 응답
