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
| `.소재 [소재명]` / `.아이템 [아이템명]` | 로컬 DB 조회 (NPC 교환·낚시·역전왕 보상·조합 레시피·교역선·물자보급소 포함) | 무료 |
| `.커스텀` | 고정 응답 (시뮬레이터 링크) | 무료 |
| `.커스텀 [무기 종류]` | 고정 응답 (디씨 가이드 링크) | 무료 |
| `.무기 [무기명]` | 로컬 DB 조회 (스탯·강화 트리·재료, 활 코팅·피리 선율 포함, 후보 안내) | 무료 |
| `.방어구 [방어구명]` | 로컬 DB 조회 (스킬·슬롯·세트보너스·재료, 후보 안내) | 무료 |
| `.랜덤` (별칭 `.란듐`) | 시리즈/그룹 스킬 1개 발동 보장 풀세트 빌드 무작위 생성 (무기+방어구5+호석+장식주) | 무료 |
| `.출석` / `.출석체크` | 1일 1회, 10~30 제니 균등 | 무료 |
| `.룰렛 [금액]` / `.룰렛 [%]` / `.룰렛 올` | 룰렛·가위바위보 합산 1일 3회, 10단계 확률표, 잭팟·초기화 방 공지, 퍼센트 베팅(1~100%, 소수점 올림) | 무료 |
| `.가위` / `.바위` / `.보 [금액]` / `[%]` | 가위바위보 베팅 (승 ×2.5 / 무 본전 / 패 몰수, EV +16.7%), 룰렛과 횟수 공유, 올 차단·100% 명시 시만 전액, 순수 random (pity 없음) | 무료 |
| `.제니` | 본인 잔고 조회 | 무료 |
| `.제니순위` | 상위 10명 + 11위 이하 호출자는 본인 순위 한 줄 추가 + 짧은 안내 footer | 무료 |
| `.제니그래프` (`.제니그래프 [닉]`) | 본인 또는 지정 사용자 60일 잔고 라인 차트 (숨은 명령어, matplotlib + 나눔고딕) | 무료 |
| `.다이애나 [질문/잡담]` | Claude Sonnet + Tool Use (호석/무기난이도/채집/이벤트/날씨/무작위/랜덤빌드/Steam할인/DLC소식 도구 13종) | 유료 (1~5원/질문) |
| `.메뉴추천` (ㅈㅁㅊ/점메추/저메추) | 1356개 메뉴 무작위 + 단식 3% 가중치 | 무료 |
| `.디스코드` | 고정 응답 | 무료 |
| `.고양이` | 야옹 10% / 사진 90% | 무료 |

자동 응답:
- `A vs B` 패턴 → "다이애나는 X 골랐어요!"
- 새 멤버 입장/퇴장 환영·아쉬움 인사

백그라운드:
- 스케줄러: 9시 모닝(7개 풀) / 12시 점심(6) / 18시 저녁(6) / 23시 룰렛 알림(4) / 0시 굿나잇(9) — 매시 30분 잡담은 비활성화
- SNS 폴러: 캡콤 아시아 X, 몬스터헌터 공식 X, 공식 YouTube, 캡콤 아시아 YouTube
- Steam 할인 폴러: MH 시리즈 8타이틀 (와일즈/라이즈+선브레이크/월드+아이스본/스토리즈1/2/3) 12시간 폴링, 시작·종료 알림. 일반/희귀 가중치는 정가 기준 정렬

> 본 `CLAUDE.md` 가 단일 최신 명세 문서. `MHWS_BOT_SPEC.md` 는 v0.5 초기 설계 아카이브 (현행과 다름, 갱신 안 함).

## DB 구조

### 메인 게임 데이터 (`data/` 하위로 정리)
- `data/misc/items.json` (773): 아이템
- `data/monsters/monsters.json` (34): 대형 몬스터
- `data/equipment/armor.json` (194 세트 / 714 피스): 방어구
- `data/equipment/weapons_all.json` (1,188): 무기 14종 (활 코팅 인벤 자료로 교정 완료, 피리 선율 78종 매핑)
- `data/equipment/accessories.json` (361): 장식주
- `data/equipment/charms.json` (187): 호신구
- `data/equipment/skills.json` (179): 스킬
- `data/equipment/kinsects.json` (21): 사냥벌레
- `data/monsters/stages.json` (5): 필드

### Enemy 통합 (`data/monsters/`)
- `all_enemies.json` (148): 통합 마스터
- `small_monsters.json` (19): 소형
- `animals_official.json` (70): 환경생물
- `animals_fishing.json` (20): 낚시 환경생물
- `boss_titles.json` (140): 보스 칭호
- `enemy_packs.json` (4): 무리

### 전투/공략 (`data/combat/`)
- `weapon_attributes.json`: 9속성
- `special_attack_types.json`: 특수공격 29종
- `special_attack_countermeasures.json`: 특수공격 대처
- `status_countermeasures.json`: 속성/상태이상별 효과적 무기/스킬
- `horn_melodies.json`: 수렵피리 무기별 선율 84종 (인벤 자료 기반)

### 퀘스트/세계관 (`data/world/`)
- `quests_official.json`: 146 미션
- `data/monsters/monster_to_quests_official.json`: 몬스터→퀘스트
- `environments.json`: 필드/캠프/시간대/계절/기상
- `game_misc.json`: NPC + 시설 + 요리
- `dlc_news.json`: 와일즈 DLC(어센던스) 발표·출시 소식 (다이애나 `get_dlc_news` 도구용, `news` 배열에 항목 추가)

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
- 게임 코드 직접 추출 환경 구축 (`D:\gamecode\`): ree-pak-cli + REasy + 와일즈 RSZ 스키마 v0.7.0. PAK 28개에서 user/msg/scn/pfb/poglst 28만 파일 추출. PGL 포맷 reverse engineering 성공
- 채집물 reward 매핑 추출 (gimmickrewarddata.user.3 파싱): 약 50종 채집 아이템 → gimmick prefab 매핑
- 와일즈 데이터 인덱스 구축 (`D:\gamecode\indexing\`): user 45337 / msg 1140 / scn 17629 / pfb 5200 entry 카테고리 분류 + 마크다운 보고서. `npc 7345 / enemy 4913 / gathering 2917 / quest 721` 등 — 봇 매핑 시 검색 키로 즉시 활용
- `.아이템` = `.소재` 알리아스, 인자 필요 명령 단독 입력 시 사용법 자동 안내
- 다이애나 RAG/페르소나 보강: 말투 가이드, 명령어 화이트리스트 (`.스킬 목록` 환각 방지), 더블크로스 등 옛 시리즈 액션 단호 안내, 닉네임 대괄호/슬래시 보존, RAG 컨텍스트에 NPC 교환·채집·조합·노트 포함
- SNS 폴러 옛글 폭주 패치 (last_seen 매칭 실패 시 resync only)
- 메뉴 풀 1352 → 1358 (육회 계열 6 추가), 단식 3% 가중치 유지
- 9시 모닝의 "오늘은 무슨 날" Sonnet 멘트 구현 (`commands/today.py`) — 현재는 비활성, scheduler `_morning_multi` 한 줄로 다시 켜기 가능
- 활 코팅 26종 인벤 자료로 mhdb 오류 교정 (마비/독 혼동) + `.무기` 출력에 `장착 코팅` 라인
- 수렵피리 선율 데이터 78종 매핑 + `.무기` 출력에 `선율` 라인 (84개 중 시즌 무기 6종은 카테고리 fallback)
- 고그마지오스 약점 속성 추가 (화 ★2 기름 부위 / 용 ★3 기름 벗겨진 부위) + `.정보` weakness note 출력
- 게임 코드 기반 자동 매핑 흡수:
  - 채집 의뢰 가능 29종 (`collectionitemdata.user.3`) — `나타에게 채집 의뢰 가능` 노트, 임의 잘못 입력 3개 제거
  - NPC 교환 81 entry + 상점 26 entry (`BarterData`/`ItemShopData`) → mapping 자동 채움
  - 교역선 12종 (`SupportShipData`) + 조사단 티켓 가격 보정 (300→40pt)
  - 비약·회복약 등 64개 아이템 조합법 (items.json `recipes` 활용) → mapping/item_usage.json 자동 흡수
- 데이터 폴더 재배치 — root JSON 들을 `data/{monsters, equipment, world, combat, misc}/` 으로 정리, `db.py` path 갱신
- `.랜덤` (별칭 `.란듐`) 명령어 + 다이애나 `get_random_build` 도구: 시리즈/그룹 스킬 1개 발동 보장 풀세트 빌드 무작위 생성 (최종 강화 무기 439 + R4↑ 5피스 시리즈 114 + 최종 호석 64 + 부위별 첫 슬롯 장식주). 스펙·플랜·sanity 스크립트 `scripts/test_random_build.py` 포함
- 다이애나 RAG 확장: 몬스터 별칭/본명 매칭 시 그 몬스터 시리즈 무기·방어구 자동 주입 (`db.monster_to_equipment` 인덱스, 무기는 `series_name_kr` 매칭, 방어구는 `crafting.inputs` 다수결). query 에 무기 종류 키워드 있으면 그것만 필터. "천인룡 소재 헤비보우건 알려줘" 같은 질문 동작.
- 제니/룰렛 시스템: `.출석` (1일 1회 10~30 균등), `.룰렛`/`.룰렛 [금액]`/`.룰렛 올` (1일 3회, 10단계 확률표 — 초기화 0.1% / 잭팟 0.1% 포함), `.제니`/`.제니순위`/`.제니그래프` (숨김). KST 자정 리셋. members.db 마이그레이션 (zenny/last_attend/roulette_count/last_roulette + zenny_history). 잭팟·초기화 시 방 공지. matplotlib 그래프. 시뮬 검증 스크립트 `scripts/test_zenny_simulation.py` 포함.
- 다이애나 페르소나 영역 분류: 시스템 프롬프트에 "와일즈 영역 / 와일즈 외" 가이드 추가. 잡담·연예인·일상 질문엔 "다이애나의 메모리에 없어요!" + `.명령어` 안내 금지, 자연스럽게 응대.
- 다이애나 속성 무기 RAG: `.다이애나 폭파 슬래시액스` 같은 패턴에 `_format_attribute_weapons` 자동 주입. 9속성(화/수/뇌/빙/용/폭파/마비/독/수면) × 14무기 종류. 결과 없으면 "아티어 무기로 제작 가능" 안내.
- `.고양이` 야옹 확률 1/3 → 10%.
- 스케줄러 23시 룰렛 알림 슬롯 추가 (4종 풀): `"🎰 룰렛은 하루에 세 번!"` 류.
- 닉네임 매핑 시스템: 카톡 sender.name 이 raw base64 토큰 (예: `cn3tiwSkOPTcX5jaQEnDsg==`) 으로 들어오는 문제 해결. (1) 카톡방 대화 export txt + (2) 봇 sqlite chat_logs 의 message 복호화 (iris `/decrypt`, enc=31) → (3) `(분, 메시지)` 매칭으로 `user_id → 평문 닉` 추출. 66명 첫 매핑 성공 (`nicknames.json`). 봇 시작 시 `nicknames.py` 로 메모리 캐싱. members.upsert / `_safe_nick(nick, user_id)` 가 매핑 우선. 관련 스크립트: `scripts/decrypt_chat_logs.py`, `scripts/map_nicknames.py`, `scripts/apply_nickname_mapping.py`.
- 신규 사용자 자동 감지 + 1:1 알림: 새 user_id 발견 시 봇이 `ALERT_ROOM_ID` 로 알림. 운영자가 알림 답장으로 "닉만 입력" 시 `_pending_new_user_id` 와 자동 매핑. 닉변 멤버는 `닉 [구닉 또는 user_id] [신닉]` 형식으로 운영자가 알림방에서 수동 갱신. 동일 닉 중복·부분 일치는 후보 안내.
- 매핑 안 된 사용자 채팅 감지: `_notified_unmapped` 메모리 set 으로 세션당 1회 알림. 첫 채팅 시 1:1 알림 (user_id + raw nick + 매핑 안내). 매핑 후 set 에서 자동 제거.
- 입장/재입장/퇴장 1:1 알림: `on_new_member` 가 매핑/등록 여부로 🆕 신규 vs 🔁 재입장 구분. `on_del_member` 에서 👋 퇴장 알림.
- 룰렛 수익률 1차 상향 (확률표 그대로): +20→+25 / +50→+60 / +70→+80 / +100→+120 / +1000→+1500. 산술 EV +1% → +4.8%, 잭팟 시 베팅의 ×16 환급.
- 룰렛 잭팟·초기화 1.0% 상향 + 잭팟 수익률 ×16 → ×10 으로 보정 (B안). 도파민 관점: 50명 활성 멤버 기준 매일 잭팟·초기화 1~2건씩 발동. 산술 EV +4.8% → +11.5%.
- `.제니순위` 출력 간소화: 상위 10명만 + 짧은 안내 footer (4줄). 카톡 자동 접힘 효과는 멤버 누적되며 자연스레.
- `.제니그래프 [닉네임]` 인자 지원: `zenny.find_user()` 가 nicknames.json + members.db 통합 검색 (정확 일치 우선, 부분 일치 fallback, 여러 건이면 후보 안내). 본인 외 타인 그래프 조회 가능.
- 운영자 본인 user_id 제니 시스템 영구 제외: `commands/zenny.py` 의 `EXCLUDED_USER_IDS = {395932031}`. `.출석` / `.룰렛` 호출 시 무응답, `.제니순위` 자동 필터링. 운영용 1:1 톡방 sender 가 점수 안 쌓이게.
- 그래프 한글 폰트: 서버에 `fonts-nanum` 설치 + matplotlib cache 재생성. 깨짐 없이 출력.
- 메뉴풀 정리·확장 (1358 → 1300): 한국에서 잘 안 알려진 76종 제거 (외국 음식·마이너 빵·옛 한식·향토·옛 부위 — 도리뱅뱅이/명태순대/옹심이/낙곱새 4개만 향토 중 보존) + 트렌드 음식 50종 추가 (두바이 초콜릿/약과/탕후루/베이글류/흑임자·흑당·쑥 라떼/카츠샌드/모찌 도넛 등) - 음료 32종 제거 (라떼/마키아토/에이드/주스/스무디/식혜·수정과·미숫가루 등 마시는 것 전부, 모카빵 등 빵은 보존). 정리 스크립트 `scripts/prune_meals.py`.
- `.제니순위` 본인 순위 표시: 호출자가 11위 이하면 상위 10 아래에 `(나) [N위] 닉 — X제니` 한 줄 자동 추가. `leaderboard(viewer_user_id)` 시그니처.
- 룰렛 pity timer (비밀): 5회 연속 음수 결과 누적된 사용자의 다음 룰렛은 양수 outcome (+25 / +60 / +80 / +120 중 무작위, 잭팟 제외) 확정. 응답 텍스트는 평소 룰렛 결과처럼 표시 — 운영자만 코드 보면 알 수 있음. members.db `neg_streak` 컬럼 자동 마이그레이션. 본전(0%)·양수·초기화는 streak 리셋.
- 룰렛 잭팟·초기화 1.0% 상향 시 잭팟 수익률 ×16 → ×10 (+1500% → +900%) 으로 보정 적용 (B안). 산술 EV +11.5%.
- `.출첵` alias 추가 (`.출석` / `.출석체크` / `.출첵` 동작 동일). HELP_TEXT 미노출.
- 명령어 응답 누락 케이스 해소: `.제니` / `.출석` / `.룰렛` / `.제니그래프` 가 sender.name 의존 (raw 토큰 누락 시 무응답) 이슈 제거. 이제 `uid` 만 있으면 응답, nick falsy 면 "익명 헌터" 로 표시.
- 닉네임 매핑 2차 갱신: 5/29~6/1 카톡 export 반영 → 69 → 72 entry (+3 신규, 닉변 1 갱신). `map_nicknames.py` 의 기존 매핑 보존 + 신규 병합 흐름 추가.
- `.명령어` 카테고리 분류: 🐲 와일즈 DB / 🛠 빌드 / 🎰 제니·룰렛 / 💬 잡담·기타 4개 섹션 + 구분선. 332자.
- `.랜덤` armor 풀 α/β/γ 필터: R4 기본형 8개 시리즈 (호쇄인룡/호벽수/레다젤트/시이우/호화룡/투나물/호흉조룡/이그졸스) 제외 → 114 → 106 시리즈. 강화 단계 (α/β/γ) 들어간 진정한 상위 방어구만 빌드에 포함.
- 룰렛 초기화 → 다음 출석 30제니 확정 (비밀): 초기화당하면 `members.db attend_bonus` 플래그 set, 다음 출석 1회 `ATTEND_MAX(30)` 강제 후 소비. 응답 문구는 평소와 동일 (시스템만 인지). 컬럼 자동 마이그레이션.
- 가위바위보 게임 (`commands/rps.py`): `.가위`/`.바위`/`.보 [금액 또는 %]`. 봇 손 순수 random 1/3 (pity 없음), 승 ×2.5 / 무 본전 / 패 몰수 → EV +16.7% (룰렛 +11.5%보다 리스크 프리미엄). 무승부도 횟수 차감. 룰렛과 하루 3회 **공유** (`roulette_count`/`last_roulette` 컬럼 공용 — 룰렛 코드 무수정). `올` 키워드 차단하고 "지면 전부 잃음, 다 걸려면 100%" 안내 → `100%` 명시 입력 시만 전액. EV·리스크(켈리 최적 13% / 손익분기 26%) 분석 완료.
- 룰렛·가위바위보 퍼센트 베팅: `.룰렛 50%` / `.가위 50%` 처럼 잔고 비율 베팅 (`math.ceil` 소수점 올림). 룰렛 1~100%(100%=올), 가위바위보 1~100%(올 키워드만 차단).
- 운영자(EXCLUDED) 특수처리 재정의: 기존 "전 기능 무응답" → "정상 응답 + 횟수 무제한 + 비노출". 출석 1일 1회·룰렛/가위바위보 3회 제한 모두 스킵, 잭팟·초기화 방 공지 억제, `.제니순위` 제외 유지. `unlimited = is_excluded(uid)` 분기. 일반 유저는 기존 제한 그대로.
- 메뉴풀 1300 → 1356 (흔한데 빠졌던 56종 보강): 카테고리별 누락 스캔 (밥·면·구이·조림·볶음·탕·찌개·정식·배달·해물 등) 으로 경양식돈가스/유산슬/장어덮밥/규카츠/대게/케밥/딤섬/소금구이/부채살/코다리조림/등갈비찜/참치찌개/산채정식 등 추가. 브랜드 상품명·반찬성·단품 중복은 제외.
- SNS YouTube 폴러 RSS 전환: `search` API (quota 100/call → 일 10000 초과로 403/429 빈발 → state 동기화 끊겨 옛 영상 재전송) → `youtube.com/feeds/videos.xml?channel_id=` RSS (quota 0, api_key 불필요). 재전송 원인 제거. `_fetch_youtube` 만 교체, 시그니처·state 로직 유지.
- 다이애나 Steam 할인 도구 추가 (11종 → 12종): Steam 폴러가 매 폴링마다 현재 할인 스냅샷을 `steam_sales_current.json` 에 저장 (알림 state 로직과 분리), `get_steam_sales` 도구가 즉시 읽어 답변. "할인/세일/지금 싼 게임" 질문 대응. 실시간 API 대신 12h 스냅샷 (할인은 며칠~몇 주 지속이라 충분).
- SNS 폴러 재시작 시 신규 누락 방지: 기존 `start_poller` 가 봇 켜질 때마다 시작 `_check_new` 로 새 글을 발송 없이 흡수 → 재시작 잦으면 그 사이 글 영구 누락. `first = not state` 로 변경 (최초 실행만 첫 폴링 발송 스킵, 재시작은 첫 폴링부터 발송). 죽은 state 키(`UCW7h`/`bsky`) 정리.
- SNS 폴러 MH 키워드 필터: 캡콤아시아 채널(YouTube + X)은 캡콤 전체 게임을 다뤄 바하·스파6·귀무자 등 비-몬헌 글이 섞임. `YOUTUBE_CHANNELS`/`X_ACCOUNTS` 각 항목에 `mh_only` 플래그, 캡콤아시아만 `True`. `MH_KEYWORDS` 매칭(몬스터헌터/몬헌/와일즈/라이즈/선브레이크/월드/아이스본/스토리즈/어센던스 + 영문) 안 되는 글은 발송 스킵. state 는 그대로 최신으로 갱신 (필터된 글이 다음 글 발송을 방해 안 함). 몬헌 공식 채널 2개는 필터 없이 그대로.
- DLC 소식 DB + 다이애나 도구 (12종 → 13종): `data/world/dlc_news.json` 에 와일즈 어센던스 DLC 발표·소식 저장, `get_dlc_news` 도구로 "DLC/어센던스/확장팩 언제" 질문 대응. `official_url` 필드 + `news` 배열 (**위가 최신** 컨벤션, 새 소식은 맨 앞에 insert). 도구 출력은 최신 5건만 + 그 이상은 "총 N건 중 최신 5 / 이전 N건 생략" 으로 자름 (소식 누적돼도 응답 길이 안정).
- 닉네임 매핑 3차 갱신: 6/6 카톡 export 반영 → 72 entry 유지 (닉변 2건 — 차뭉 태도/대검, 리례릿 차액/태도). 신규 0건 (인스턴스 chat_logs dump 가 6/1 자라 그 이후 user_id 매칭 불가). export 에 있지만 매핑 안 된 활발한 닉 100+명 발견(simnel/김치볶음/darksara 등) — 운영 중 알림방 흐름으로 처리.
- 매핑 안 된 사용자 1:1 알림에 첫 채팅 메시지 미리보기 추가: 기존엔 `user_id` + `raw nick` 만 보여 누구인지 판단 어려움 → `메시지: {200자 자름}` 한 줄 추가. 운영자가 메시지 내용 보고 어느 닉인지 매칭 가능.
- 다이애나 `sender_nick` 매핑된 평문 닉 우선: 기존 `ctx.sender.name` (카톡 raw 토큰일 수 있음) 을 그대로 LLM 에 전달 → 다이애나가 raw 토큰을 닉인 줄 알고 답에 박는 케이스 발생 (예: 라라가 질문했는데 "FJ﨤S U9 님"으로 호명). `nicknames.get(uid)` 우선, 없으면 raw, 그것도 없으면 빈값. 룰렛/제니의 `_safe_nick` 과 동일 우선순위.
- 다이애나 도메인용 웹 서버 (`commands/web.py`): `d-i-0336-7.p-e.kr` 으로 접속하면 제니 분포 대시보드 HTML 제공. Flask + Chart.js (CDN), 봇 프로세스 백그라운드 스레드로 0.0.0.0:80 listen. 디자인: 보라 그라데이션 + 글래스모피즘 + 골드 강조. 표시: 활성 멤버수 / 전체 제니 / 평균·중앙값 / 상위 5명 점유율 / 구간별 히스토그램 / 상위5 vs 나머지 도넛 / 로그 스케일 전체 랭킹 / 전체 랭킹 리스트(메달). 운영자(EXCLUDED) 및 닉네임 매핑 안 된 멤버 제외 (raw 토큰 노출 방지). 인프라: Oracle Cloud Security List 인그레스 80 추가 + 인스턴스 iptables 80 ACCEPT + systemd unit 에 `AmbientCapabilities=CAP_NET_BIND_SERVICE` 추가 (ubuntu 유저로 80 bind).

## 미해결 작업

### 1. `.정보` / `.스킬` / `.소재` 검색 미스 후보 안내
- `.무기` / `.방어구`처럼 부분 일치 후보 안내 미적용 (해당 명령들은 `정확히 입력해주세요` 만 반환)

### 2. RSZ 파싱 실패 6226개 user.3
- struct.error 가 95% — 와일즈 patch_022 이후 RSZ 포맷 변경, v0.7.0 dump 도 못 따라잡음
- 봇 핵심 카테고리(enemy/npc/equip commondata) 일부 막힘. 커뮤니티 dump 업데이트 시 재처리 가능
- 일부 NPC 교환 데이터는 `USR version 1` 신규 포맷 — RSZ 와 별개 파서 필요

### 3. 소형 몬스터 보상 추가 정리
- 라프마/포케피나/젤레도론/가지오스/바오노스(개별)/네르스큐라 베이비/오메가 미크로스 등은 외부 자료 부족으로 미반영

### 4. 9시 기념일 멘트 비활성화 상태
- `commands/today.py` 의 Sonnet 호출 함수 + 위키 fetch 동작은 검증 완료, scheduler `_morning_multi` 에서 호출만 끔
- 필요 시 한 줄 복원으로 재활성

### 5. 데이터 추출 자산 (D:\gamecode\)
- `gathering_extracted.json` — 191 아이템 채집 매핑 (stage 무관) + RARE 특산 stage 매핑. 봇 DB 통합 보류 중
- 와일즈 인덱스 (`D:\gamecode\indexing\user|msg|scn|pfb`) — 카테고리 + RSZ 타입 인덱스 + 마크다운 보고서. 추가 게임 데이터 추출 시 검색 키로 활용
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
