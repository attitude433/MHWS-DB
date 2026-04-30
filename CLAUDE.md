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
| `.소재 [소재명]` | 로컬 DB 조회 | 무료 (미완성) |
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
- `skill_to_equipment.json` (4,587 연결)
- `item_usage.json` (8,535 연결)
- `weapon_trees.json` / `series_to_weapons.json` / `species_to_monsters.json`
- `monster_to_materials.json` / `material_to_monsters.json`
- `external_guides.json` (디씨 무기별 가이드 14개)
- `reference.json` (종족/부위/시리즈/강화 테이블)

## 별칭 사전 v1.0

몬스터 별칭 16종 등록. 상세는 `MHWS_BOT_SPEC.md` 참조.

## 미해결 작업

### 1. DB 한글화 보강 (`.소재` 명령어 블로커)
- `kind_kr` 7개 enum 한글 매핑 적용
- `carve` "박피" → "갈무리" 일괄 수정
- 매핑 표는 `MHWS_BOT_SPEC.md` 참조
- 적용 대상 파일: `monsters.json`, `mapping/item_usage.json`

### 2. `.소재` 명령어 출력 형식
- 정렬 기준 미정

### 3. `.챗` 구현 세부
- 모델 선택 (Haiku vs Sonnet)
- 시스템 프롬프트
- DB 컨텍스트 추출 로직 (키워드 매칭? 임베딩?)

### 4. 검색 미스 처리
- 못 찾았을 때 응답 형식

### 5. 추가 기능 (선택)
- 공식 SNS (X / 인스타) 새 글 알림 (하루 2회 폴링)

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
