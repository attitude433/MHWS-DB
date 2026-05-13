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
| `.소재 [소재명]` | 로컬 DB 조회 (NPC 교환·낚시·역전왕 보상 포함) | 무료 |
| `.커스텀` | 고정 응답 (시뮬레이터 링크) | 무료 |
| `.커스텀 [무기 종류]` | 고정 응답 (디씨 가이드 링크) | 무료 |
| `.무기 [무기명]` | 로컬 DB 조회 (스탯·강화 트리·재료, 후보 안내) | 무료 |
| `.방어구 [방어구명]` | 로컬 DB 조회 (스킬·슬롯·세트보너스·재료, 후보 안내) | 무료 |
| `.다이애나 [질문/잡담]` | Claude Sonnet + Tool Use (호석/무기난이도/채집/이벤트/날씨/무작위 도구 10종) | 유료 (1~5원/질문) |
| `.메뉴추천` (ㅈㅁㅊ/점메추/저메추) | 1352개 메뉴 무작위 + 단식 3% 가중치 | 무료 |
| `.디스코드` | 고정 응답 | 무료 |
| `.고양이` | 야옹 또는 사진 1/3 | 무료 |

자동 응답:
- `A vs B` 패턴 → "다이애나는 X 골랐어요!"
- 새 멤버 입장/퇴장 환영·아쉬움 인사

백그라운드:
- 스케줄러: 9시 모닝(7개 풀) / 12시 점심(6) / 18시 저녁(6) / 0시 굿나잇(9) / 10:30~22:30 매시 30분 15% 잡담
- SNS 폴러: 캡콤 아시아 X, 몬스터헌터 공식 X, 공식 YouTube, 캡콤 아시아 YouTube
- Steam 할인 폴러: MH 시리즈 8타이틀 (와일즈/라이즈+선브레이크/월드+아이스본/스토리즈1/2/3) 12시간 폴링, 시작·종료 알림. 일반/희귀 가중치는 정가 기준 정렬

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

## 별칭 사전

- 몬스터 별칭 35종 등록 (`alias.py` `MONSTER_ALIASES`)
- 표기 변형 자동 매핑 (`GLYPH_VARIANTS`): α↔알파↔A/a, β↔베타↔B/b, γ↔감마↔Y/y, Ⅰ↔I↔1, Ⅱ↔II↔2, … Ⅴ
- 무기/방어구/소재 검색에 자동 적용 (`.소재 황뢰룡사냥증감마`, `.방어구 고어헬름a`, `.무기 호프블레이드5` 다 매칭)

## 완료된 작업

- DB 한글화: `kind_kr` 9개 enum 보강 + `carve` 박피→갈무리 (`monsters.json`, `mapping/item_usage.json`)
- Python 서버 코드 구현 완료: `main.py`, `db.py`, `alias.py`, `commands/` (info/skill/material/custom/chat/weapon/armor/scheduler/sns/meal/weather/steam_sale)
- 모든 명령어 출력 형식 확정 및 검증
- 운영 환경 셋업 (Oracle Cloud + redroid + Iris + 봇 systemd 영구화) — 절차는 아래 "운영 환경 셋업 절차" 섹션 참조
- `.챗` → `.다이애나` 통합 (Sonnet + DB context 주입 + Tool Use 10종)
- 메뉴추천 풀 1352개 + 단식 3% 가중치
- 스케줄러 메시지 풀 확장 (모닝 7 / 점심 6 / 저녁 6 / 굿나잇 9)
- `.무기` / `.방어구` 명령 (검색 미스 시 부분 일치 후보 안내)
- 사냥증 γ 5개 + 역전 사냥의 증표 Ⅰ/Ⅱ/Ⅲ drops 데이터 + 4개 누락 mapping (역전 연마/보석 어란/로열 아이루/픽토맨서) + `[NPC 교환]` 출력 섹션
- 소형 몬스터 19종 갈무리·NPC 교환 데이터 수동 채움 (콩가/블랑고/랑고스타/달루토돈/탈리오스/네마라치카/수호룡 세크레트/필라길/브브라치카/크라노다스/케라토노스/바오노스/하르푸스/가쟈우)
- Steam 할인 폴러 (MH 시리즈 8타이틀, 12h 주기)
- 봇 자가 진단 cron (5분마다 systemd 상태 체크, 변경 시 1:1 카톡 알림): `/usr/local/bin/mhws-health.sh`
- Anthropic API 사용량 일일 리포트 cron (UTC 00:00 = KST 09:00): `/usr/local/bin/mhws-daily-report.py` (`ANTHROPIC_ADMIN_KEY` 필요)
- 게임 코드 직접 추출 환경 구축 (`D:\gamecode\`): ree-pak-cli + REasy + 와일즈 RSZ 스키마. PAK 26개에서 user/msg/scn/pfb/poglst 28만 파일 추출. PGL 포맷 reverse engineering 성공
- 채집물 reward 매핑 추출 (gimmickrewarddata.user.3 파싱): 약 50종 채집 아이템 → gimmick prefab 매핑

## 미해결 작업

### 1. `.정보` / `.스킬` / `.소재` 검색 미스 후보 안내
- `.무기` / `.방어구`처럼 부분 일치 후보 안내 미적용 (해당 명령들은 `정확히 입력해주세요` 만 반환)

### 2. 일부 채집/도구 소재 매핑 빈 칸
- mapping에 있지만 drops/exchanges 빈 항목 ~115개 (광물·뼈·일반 도구·이벤트 보상)
- items.json엔 있지만 mapping에 키 없는 항목 264개 (도구·포션 류 — items.json `recipes` 활용 가능했으나 보류)

### 3. 소형 몬스터 보상 추가 정리
- 라프마/포케피나/젤레도론/가지오스/바오노스(개별)/네르스큐라 베이비/오메가 미크로스 등은 외부 자료 부족으로 미반영

### 4. 데이터 추출 자산 (D:\gamecode\)
- `gathering_extracted.json` — 191 아이템 채집 매핑 (stage 무관) + RARE 특산 stage 매핑. 봇 DB 통합 보류 중
- PGL 파싱 가능 (`parse_pgl_stages.py`), gimmick reward 추출 가능 (`extract_gimmick_rewards.py`)
- DLC/패치 나오면 재추출 가능

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
ANTHROPIC_API_KEY=               # .다이애나 명령용
ANTHROPIC_ADMIN_KEY=             # 일일 사용량 리포트용 (선택)
SNS_ROOM_ID=                     # 운영방 (스케줄러·SNS·Steam 폴러)
ALERT_ROOM_ID=                   # 1:1 알림방 (자가 진단·일일 리포트)
YOUTUBE_API_KEY=                 # SNS YouTube 폴링
DATA_GO_KR_API_KEY=              # 날씨/미세먼지 (KMA + AirKorea)
```

### Cron (인스턴스)
```
*/5 * * * * /usr/local/bin/mhws-health.sh
0 0 * * * /usr/local/bin/mhws-daily-report.py >> /var/log/mhws-daily-report.log 2>&1
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
