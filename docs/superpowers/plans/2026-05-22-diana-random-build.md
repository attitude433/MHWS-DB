# 다이애나 랜덤 빌드 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `.랜덤` / `.란듐` 명령어와 다이애나 `get_random_build` 도구로 시리즈/그룹 스킬 1개 발동이 보장된 풀세트 빌드(무기 + 방어구 5부위 + 호석 + 부위별 장식주 1)를 즉시 반환한다.

**Architecture:** 단일 모듈 `commands/random_build.py` 가 데이터 풀 캐시 + generator + formatter 를 모두 담는다. `main.py` 는 `.랜덤` / `.란듐` 라우팅만 추가하고, `commands/chat.py` 는 도구 정의/실행 분기만 추가한다. 빌드는 dict 로 반환되어 텍스트 포맷팅 단계와 분리된다 — 추후 다른 출력 포맷(예: JSON 디버그) 추가가 용이.

**Tech Stack:** Python 3, 표준 라이브러리 `random` / `json` 만 사용. 외부 라이브러리 추가 없음. 테스트는 `scripts/test_random_build.py` (sanity check 스크립트).

**기반 스펙:** `docs/superpowers/specs/2026-05-22-diana-random-build-design.md`

---

## File Structure

| 파일 | 신규/수정 | 책임 |
|---|---|---|
| `commands/random_build.py` | 신규 | 풀 로더 + generator + formatter + 진입점 |
| `scripts/test_random_build.py` | 신규 | sanity check (1000회 호출, 발동 규칙 검증) |
| `main.py` | 수정 | `.랜덤` / `.란듐` 라우팅, `HELP_TEXT` 에 `.랜덤` 추가 |
| `commands/chat.py` | 수정 | `TOOLS` 에 `get_random_build` 추가, `_exec_tool` 분기 추가 |

각 task 는 1~2개 파일 변경 + commit 으로 끝난다.

---

## Task 1: `commands/random_build.py` — 풀 로더 + 발동 모드 enum

**Files:**
- Create: `commands/random_build.py`

- [ ] **Step 1: 신규 파일 생성**

```python
"""다이애나 랜덤 빌드 generator.

스펙: docs/superpowers/specs/2026-05-22-diana-random-build-design.md
"""
from __future__ import annotations
import random
from typing import Optional

import db

# 발동 모드
MODE_SET_LV1 = 'set_lv1'    # 시리즈 2P + 자유 3P → set_bonus Lv1
MODE_SET_LV2 = 'set_lv2'    # 시리즈 4P + 자유 1P → set_bonus Lv2
MODE_GROUP = 'group'         # 시리즈 3P + 자유 2P → group_bonus Lv1

PIECE_ORDER = ['head', 'chest', 'arms', 'waist', 'legs']


def _weapon_leaf_pool() -> list[dict]:
    """crafting.branches 가 비어있는 최종 강화 무기만."""
    return [
        w for w in db.weapons_all
        if not (w.get('crafting') or {}).get('branches')
    ]


def _armor_pool() -> list[dict]:
    """R4 이상이고 5피스 완비된 시리즈만."""
    return [
        s for s in db.armor
        if s.get('rarity', 0) >= 4 and len(s.get('pieces') or []) == 5
    ]


def _final_charm_pool() -> list[dict]:
    """각 series_id 의 level 최댓값에 해당하는 호석 1개씩."""
    by_series: dict = {}
    for c in db.charm if isinstance(db.charm, list) else []:
        sid = c.get('series_id')
        if sid is None:
            continue
        cur = by_series.get(sid)
        if cur is None or c.get('level', 0) > cur.get('level', 0):
            by_series[sid] = c
    return list(by_series.values())


def _accessory_pool() -> list[dict]:
    """모든 스킬 entry 의 accessories 평탄화. name_kr 기준 중복 제거."""
    seen: dict = {}
    for skill_entry in db.skill_to_equipment.values():
        for acc in skill_entry.get('accessories', []) or []:
            name = acc.get('name_kr')
            if not name or name in seen:
                continue
            seen[name] = {
                'name_kr': name,
                'slot_level': acc.get('slot_level', 1),
                'allowed_on_kr': acc.get('allowed_on_kr', ''),
                'level': acc.get('level', 1),
            }
    return list(seen.values())
```

- [ ] **Step 2: 풀 로딩 검증 — 인터프리터에서 직접 호출**

Run:
```bash
python -c "from commands.random_build import _weapon_leaf_pool, _armor_pool, _final_charm_pool, _accessory_pool; print('weapons:', len(_weapon_leaf_pool())); print('armor:', len(_armor_pool())); print('charms:', len(_final_charm_pool())); print('accessories:', len(_accessory_pool()))"
```

Expected (스펙 4종 풀과 정확히 일치):
```
weapons: 439
armor: 114
charms: 64
accessories: 100+
```

charms 가 64 가 아니거나 weapons 가 439 가 아니면 STOP — db.py 의 charm 변수가 charms.json 인지 charm.json 인지 확인 후 수정.

- [ ] **Step 3: db.py 의 charm 변수가 호석 리스트인지 확인**

```bash
python -c "import db; print(type(db.charm), '/', len(db.charm) if hasattr(db.charm, '__len__') else '?')"
```

Expected: `<class 'list'> / 187`

만약 `<class 'dict'>` 가 나오면 db.py 가 `charm.json` (싱글 추천 텍스트) 만 로드한 것 → db.py 에 `charms = _load('data/equipment/charms.json')` 추가 후 random_build.py 가 `db.charms` 를 쓰도록 수정.

- [ ] **Step 4: db.py 보강 (charms 누락 시에만)**

위 step 3 에서 `<class 'dict'>` 가 나왔다면 `db.py` 의 `charm = _load(...)` 줄 아래에 추가:

```python
charms = _load('data/equipment/charms.json')
```

그리고 `commands/random_build.py` 의 `_final_charm_pool` 내부 `db.charm` 을 `db.charms` 로 교체.

- [ ] **Step 5: Commit**

```bash
git add commands/random_build.py db.py
git commit -m "feat: 랜덤 빌드 generator 풀 로더 (Task 1)"
```

---

## Task 2: 발동 모드 + 시리즈 픽

**Files:**
- Modify: `commands/random_build.py` (append)

- [ ] **Step 1: 모드별 후보 시리즈 분류 + 픽 함수 추가**

`commands/random_build.py` 끝에 추가:

```python
def _pick_mode_and_series(armor_pool: list[dict]) -> tuple[str, dict, int]:
    """발동 모드 무작위 선택 + 해당 모드에서 가능한 시리즈 무작위 선택.

    Returns: (mode, series_dict, required_pieces)
    """
    set_series = [s for s in armor_pool if s.get('set_bonus')]
    group_series = [s for s in armor_pool if s.get('group_bonus')]

    candidates = []
    if set_series:
        candidates.append((MODE_SET_LV1, set_series, 2))
        candidates.append((MODE_SET_LV2, set_series, 4))
    if group_series:
        candidates.append((MODE_GROUP, group_series, 3))

    mode, pool, required = random.choice(candidates)
    return mode, random.choice(pool), required
```

- [ ] **Step 2: 방어구 픽 함수 추가**

`commands/random_build.py` 끝에 추가:

```python
def _pick_armor(armor_pool: list[dict], focus_series: dict, required: int) -> dict:
    """발동 시리즈에서 N부위 + 나머지 부위는 풀에서 무작위. piece.kind 별 1개씩.

    Returns: {kind: piece_dict, ...} (5개 key 정확히)
    """
    focus_pieces = list(focus_series.get('pieces', []))
    chosen_focus = random.sample(focus_pieces, required)
    result: dict = {}
    for p in chosen_focus:
        result[p['kind']] = dict(p, _series_name=focus_series.get('name_kr', ''))

    remaining_kinds = [k for k in PIECE_ORDER if k not in result]
    for kind in remaining_kinds:
        candidate_series = random.choice(armor_pool)
        piece = next(
            (p for p in candidate_series.get('pieces', []) if p['kind'] == kind),
            None,
        )
        # 그 시리즈에 해당 kind 가 없을 가능성 — 5피스 풀로 제한했으니 발생 X
        # 방어적으로 다시 뽑기
        while piece is None:
            candidate_series = random.choice(armor_pool)
            piece = next(
                (p for p in candidate_series.get('pieces', []) if p['kind'] == kind),
                None,
            )
        result[kind] = dict(piece, _series_name=candidate_series.get('name_kr', ''))

    return result
```

- [ ] **Step 3: 검증 — 모드 분포 균등성 + 발동 시리즈 부위 수 확인**

```bash
python -c "
from collections import Counter
from commands.random_build import _armor_pool, _pick_mode_and_series, _pick_armor
pool = _armor_pool()
cnt = Counter()
for _ in range(3000):
    mode, series, req = _pick_mode_and_series(pool)
    cnt[mode] += 1
    armor = _pick_armor(pool, series, req)
    focus_count = sum(1 for p in armor.values() if p.get('_series_name') == series.get('name_kr'))
    assert focus_count >= req, f'{mode} expected >= {req}, got {focus_count}'
print(cnt)
"
```

Expected: 각 mode 약 1000회 ±15% (`set_lv1`, `set_lv2`, `group`), assertion error 없음.

- [ ] **Step 4: Commit**

```bash
git add commands/random_build.py
git commit -m "feat: 발동 모드 + 방어구 픽 (Task 2)"
```

---

## Task 3: 무기 / 호석 / 장식주 픽

**Files:**
- Modify: `commands/random_build.py` (append)

- [ ] **Step 1: 무기·호석·장식주 픽 + generate_random_build 함수 추가**

`commands/random_build.py` 끝에 추가:

```python
def _pick_first_slot_accessory(slots: list, allowed_kinds: tuple, acc_pool: list[dict]) -> Optional[dict]:
    """장비의 slots[0] 에 들어갈 장식주 무작위 1개.

    slots: 장비의 slots 배열 (예: [3, 1, 1])
    allowed_kinds: ("무기", "양쪽") 또는 ("방어구", "양쪽")
    """
    if not slots:
        return None
    first_size = slots[0]
    candidates = [
        a for a in acc_pool
        if a.get('slot_level', 99) <= first_size
        and a.get('allowed_on_kr', '') in allowed_kinds
    ]
    if not candidates:
        return None
    return random.choice(candidates)


def generate_random_build() -> dict:
    """랜덤 빌드 1개를 dict 로 반환.

    Returns:
        {
            'mode': 'set_lv1' | 'set_lv2' | 'group',
            'bonus_skill_kr': str,
            'bonus_skill_level': int,
            'weapon': {...},
            'weapon_accessory': dict | None,
            'armor': {'head': {...}, ..., 'legs': {...}},
            'armor_accessories': {'head': dict | None, ...},
            'charm': {...},
        }
    """
    weapon_pool = _weapon_leaf_pool()
    armor_pool = _armor_pool()
    charm_pool = _final_charm_pool()
    acc_pool = _accessory_pool()

    mode, focus_series, required = _pick_mode_and_series(armor_pool)
    armor = _pick_armor(armor_pool, focus_series, required)

    if mode == MODE_SET_LV1:
        bonus = focus_series['set_bonus']
        level = 1
    elif mode == MODE_SET_LV2:
        bonus = focus_series['set_bonus']
        level = 2
    else:
        bonus = focus_series['group_bonus']
        level = 1

    weapon = random.choice(weapon_pool)
    charm = random.choice(charm_pool)

    weapon_acc = _pick_first_slot_accessory(
        weapon.get('slots') or [], ('무기', '양쪽'), acc_pool,
    )
    armor_accs = {
        kind: _pick_first_slot_accessory(
            armor[kind].get('slots') or [], ('방어구', '양쪽'), acc_pool,
        )
        for kind in PIECE_ORDER
    }

    return {
        'mode': mode,
        'bonus_skill_kr': bonus.get('name_kr', ''),
        'bonus_skill_level': level,
        'weapon': weapon,
        'weapon_accessory': weapon_acc,
        'armor': armor,
        'armor_accessories': armor_accs,
        'charm': charm,
    }
```

- [ ] **Step 2: 검증 — 1000회 호출 + 슬롯 룰 위반 검사**

```bash
python -c "
from commands.random_build import generate_random_build, PIECE_ORDER
for _ in range(1000):
    b = generate_random_build()
    # 발동 1개 확정
    assert b['bonus_skill_kr'], 'bonus skill missing'
    # 무기 장식주가 있으면 슬롯 사이즈 룰 통과
    if b['weapon_accessory']:
        ws = b['weapon'].get('slots') or []
        assert ws and b['weapon_accessory']['slot_level'] <= ws[0]
        assert b['weapon_accessory']['allowed_on_kr'] in ('무기', '양쪽')
    # 방어구 장식주 동일
    for k in PIECE_ORDER:
        acc = b['armor_accessories'][k]
        if acc:
            ps = b['armor'][k].get('slots') or []
            assert ps and acc['slot_level'] <= ps[0]
            assert acc['allowed_on_kr'] in ('방어구', '양쪽')
print('OK 1000회')
"
```

Expected: `OK 1000회` (assertion 위반 시 stack trace)

- [ ] **Step 3: Commit**

```bash
git add commands/random_build.py
git commit -m "feat: 무기/호석/장식주 픽 + generate_random_build (Task 3)"
```

---

## Task 4: 빌드 텍스트 포맷팅

**Files:**
- Modify: `commands/random_build.py` (append)

- [ ] **Step 1: format_build 함수 추가**

`commands/random_build.py` 끝에 추가:

```python
def _format_equip_line(piece_name: str, accessory: Optional[dict]) -> str:
    if accessory:
        return f'{piece_name} — {accessory["name_kr"]}'
    return piece_name


def format_build(build: dict) -> str:
    lines = ['[랜덤 빌드]']

    weapon = build['weapon']
    weapon_label = f'{weapon["name_kr"]} ({weapon.get("kind_kr","?")})'
    lines.append(f'무기: {_format_equip_line(weapon_label, build["weapon_accessory"])}')

    for kind in PIECE_ORDER:
        piece = build['armor'][kind]
        acc = build['armor_accessories'][kind]
        lines.append(_format_equip_line(piece['name_kr'], acc))

    lines.append(f'호석: {build["charm"]["name_kr"]}')
    lines.append(f'발동: {build["bonus_skill_kr"]} Lv{build["bonus_skill_level"]}')

    return '\n'.join(lines)


def random_build_text() -> str:
    """진입점: 한 번의 빌드 생성 + 텍스트 반환."""
    return format_build(generate_random_build())
```

- [ ] **Step 2: 검증 — 출력 형식 직접 확인**

```bash
python -c "from commands.random_build import random_build_text; print(random_build_text())"
```

Expected (예시):
```
[랜덤 빌드]
무기: 라울 차지소드 (차지액스) — 공격주【3】
고어헬름β — 회피주【2】
흑식메일β — 회심주【3】
레우스암β — 도전주【3】
흑식코일β
흑식그리브β — 무기력주【2】
호석: 회피의 호석Ⅲ
발동: 흑식룡의 힘 Lv2
```

체크리스트:
- 라인 수: 9 (`[랜덤 빌드]` + 무기 + 방어구 5 + 호석 + 발동)
- 방어구 줄에 부위 라벨 없음
- 슬롯 없는 부위는 ` — 장식주` 부분 생략
- 발동 줄 끝에 `Lv1` 또는 `Lv2`

- [ ] **Step 3: Commit**

```bash
git add commands/random_build.py
git commit -m "feat: 랜덤 빌드 텍스트 포맷터 (Task 4)"
```

---

## Task 5: sanity 스크립트

**Files:**
- Create: `scripts/test_random_build.py`

- [ ] **Step 1: sanity 스크립트 작성**

`scripts/test_random_build.py`:

```python
"""랜덤 빌드 sanity check.

3000회 호출 + 스펙 모든 invariant 검증.
"""
from __future__ import annotations
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from commands.random_build import (
    generate_random_build,
    random_build_text,
    PIECE_ORDER,
    MODE_SET_LV1, MODE_SET_LV2, MODE_GROUP,
)

N = 3000
mode_cnt = Counter()
seen_builds = set()
slot_violations = 0
allowed_violations = 0
missing_bonus = 0

for _ in range(N):
    b = generate_random_build()
    mode_cnt[b['mode']] += 1

    if not b['bonus_skill_kr']:
        missing_bonus += 1

    # 슬롯 룰
    weapon_slots = b['weapon'].get('slots') or []
    wa = b['weapon_accessory']
    if wa:
        if not weapon_slots or wa['slot_level'] > weapon_slots[0]:
            slot_violations += 1
        if wa['allowed_on_kr'] not in ('무기', '양쪽'):
            allowed_violations += 1
    for k in PIECE_ORDER:
        ps = b['armor'][k].get('slots') or []
        a = b['armor_accessories'][k]
        if a:
            if not ps or a['slot_level'] > ps[0]:
                slot_violations += 1
            if a['allowed_on_kr'] not in ('방어구', '양쪽'):
                allowed_violations += 1

    sig = (
        b['weapon']['name_kr'],
        tuple(b['armor'][k]['name_kr'] for k in PIECE_ORDER),
        b['charm']['name_kr'],
    )
    seen_builds.add(sig)

print(f'호출 {N}회')
print(f'  모드 분포: {dict(mode_cnt)}')
print(f'  고유 빌드 비율: {len(seen_builds)}/{N} = {len(seen_builds)/N*100:.1f}%')
print(f'  발동 누락: {missing_bonus}')
print(f'  슬롯 룰 위반: {slot_violations}')
print(f'  무기/방어구 풀 위반: {allowed_violations}')

# 종료 코드
fail = missing_bonus + slot_violations + allowed_violations
sys.exit(1 if fail else 0)

print()
print('--- 샘플 출력 3개 ---')
for _ in range(3):
    print(random_build_text())
    print('---')
```

- [ ] **Step 2: 실행**

```bash
python scripts/test_random_build.py
```

Expected:
```
호출 3000회
  모드 분포: {'set_lv1': ~1000, 'set_lv2': ~1000, 'group': ~1000}
  고유 빌드 비율: 99%+
  발동 누락: 0
  슬롯 룰 위반: 0
  무기/방어구 풀 위반: 0
```

종료 코드 0. 하나라도 위반 시 STOP — Task 2/3 로 돌아가 수정.

- [ ] **Step 3: Commit**

```bash
git add scripts/test_random_build.py
git commit -m "test: 랜덤 빌드 sanity 스크립트 (Task 5)"
```

---

## Task 6: `main.py` 라우팅

**Files:**
- Modify: `main.py:11` (import)
- Modify: `main.py:25-39` (HELP_TEXT)
- Modify: `main.py:42` 이후 (라우팅 분기 추가)

- [ ] **Step 1: import 추가**

`main.py:11` 의 라인을:

```python
from commands import info, skill, material, custom, chat, sns, scheduler, meal, steam_sale, weapon, armor
```

다음으로 변경:

```python
from commands import info, skill, material, custom, chat, sns, scheduler, meal, steam_sale, weapon, armor, random_build
```

- [ ] **Step 2: HELP_TEXT 에 `.랜덤` 한 줄 추가**

`main.py:25-39` 의 `HELP_TEXT` 에서:

```python
.방어구 (방어구명)
.다이애나 (질문/잡담)
```

을 다음으로 변경 (`.방어구` 와 `.다이애나` 사이에 `.랜덤` 추가):

```python
.방어구 (방어구명)
.랜덤
.다이애나 (질문/잡담)
```

`.란듐` 은 절대 HELP_TEXT 에 노출하지 않음.

- [ ] **Step 3: 라우팅 분기 추가**

`main.py` 의 `.고양이` 분기 (현재 173~182 라인) **바로 위** 에 다음을 추가:

```python
    if msg == '.랜덤' or msg == '.란듐':
        ctx.reply(random_build.random_build_text())
        return
```

- [ ] **Step 4: 검증 — 문법/import 점검**

```bash
python -c "import main" 2>&1 | head -20
```

Expected: 출력 없음 (성공). `IRIS_SERVER_URL` 미설정 환경이면 `KeyError` 가 날 수 있는데, 그건 main.py 가 실제 실행되려 한 거니까 정상. 문법 에러만 없으면 OK.

또는 더 안전하게:

```bash
python -c "import ast; ast.parse(open('main.py', encoding='utf-8').read()); print('OK')"
```

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add main.py
git commit -m "feat: .랜덤 / .란듐 라우팅 + HELP_TEXT 갱신 (Task 6)"
```

---

## Task 7: 다이애나 도구 통합

**Files:**
- Modify: `commands/chat.py:242-321` (TOOLS 배열)
- Modify: `commands/chat.py:324-385` (_exec_tool 분기)
- Modify: `commands/chat.py` 상단 import

- [ ] **Step 1: import 추가**

`commands/chat.py` 상단의 import 블록에 `random_build` 모듈 추가. 기존 import 패턴 확인:

```bash
head -30 commands/chat.py
```

같은 디렉토리 내 모듈이므로 다음 형식으로 추가 (파일 상단의 다른 from-import 줄들 옆에):

```python
from commands import random_build
```

(이미 동일 형태 import 가 있으면 거기에 합치되, 기존 패턴 따라가기. 없으면 `import db` 같은 줄 아래에 새 줄로 추가)

- [ ] **Step 2: TOOLS 배열에 `get_random_build` 추가**

`commands/chat.py:242` 의 `TOOLS = [` 배열 마지막 element (현재 `get_random_skill`, ~321 라인) **뒤에** 다음을 추가 (콤마 유지):

```python
    {
        'name': 'get_random_build',
        'description': '시리즈 스킬 또는 그룹 스킬 1개 발동이 보장된 풀세트 와일즈 빌드(무기+방어구5+호석+장식주)를 무작위로 1세트 생성. "랜덤 빌드", "장비 추천 아무거나", "세팅 짜줘", "랜덤 세팅" 같은 요청에 사용.',
        'input_schema': {'type': 'object', 'properties': {}},
    },
```

- [ ] **Step 3: `_exec_tool` 에 분기 추가**

`commands/chat.py` 의 `_exec_tool` 함수 안, `get_random_skill` 분기 (~378~381 라인) **다음에** 추가:

```python
        if name == 'get_random_build':
            return random_build.random_build_text()
```

`return f'(알 수 없는 도구: {name})'` 줄 **전에** 와야 함.

- [ ] **Step 4: 검증 — chat 모듈 import + 도구 직접 실행**

```bash
python -c "
from commands import chat
result = chat._exec_tool('get_random_build', {})
print(result)
assert '[랜덤 빌드]' in result
assert '발동:' in result
print('OK')
"
```

Expected:
```
[랜덤 빌드]
무기: ...
...
발동: ... Lv?
OK
```

- [ ] **Step 5: Commit**

```bash
git add commands/chat.py
git commit -m "feat: 다이애나 get_random_build 도구 (Task 7)"
```

---

## Task 8: 통합 smoke test

**Files:** 없음 (실행만)

- [ ] **Step 1: sanity 스크립트 재실행**

```bash
python scripts/test_random_build.py
```

Expected: Task 5 의 expected 와 동일. 모든 violation 0.

- [ ] **Step 2: 다이애나 도구 시뮬레이션 — Sonnet API 안 거치고 도구만 호출**

```bash
python -c "
from commands import chat
print(chat._exec_tool('get_random_build', {}))
print()
print(chat._exec_tool('get_random_build', {}))
print()
print(chat._exec_tool('get_random_build', {}))
"
```

Expected: 빌드 3개 출력, 매번 다른 무기·방어구·호석. 발동 줄에 시리즈/그룹 스킬 이름 + Lv1 또는 Lv2.

- [ ] **Step 3: HELP_TEXT 노출 확인**

```bash
python -c "import main; print(main.HELP_TEXT)"
```

Expected: 출력에 `.랜덤` 한 줄 있고 `.란듐` 은 없음.

(`IRIS_SERVER_URL` 미설정으로 main 이 import 중 에러나면 다음 우회):

```bash
python -c "
import re
text = open('main.py', encoding='utf-8').read()
m = re.search(r'HELP_TEXT = \"\"\"(.+?)\"\"\"', text, re.S)
print(m.group(1))
"
```

- [ ] **Step 4: 최종 sanity 보고**

수동 체크리스트:
- [ ] `.랜덤` 한 번 호출 → 9줄 출력
- [ ] `.란듐` 호출 → 동일 동작
- [ ] 1000회 호출 → 동일 빌드 중복 < 1%
- [ ] HELP_TEXT 에 `.랜덤` 있고 `.란듐` 없음
- [ ] 다이애나 `get_random_build` 도구 호출 가능

- [ ] **Step 5: 변경 사항 확인 + 최종 commit (필요 시)**

```bash
git status
git log --oneline -10
```

추가 변경 없으면 끝. CLAUDE.md "완료된 작업" 섹션 갱신은 별도 commit:

```bash
# CLAUDE.md 의 "완료된 작업" 마지막 줄에 다음 추가:
#   - `.랜덤` (별칭 `.란듐`) 명령어 + 다이애나 `get_random_build` 도구: 발동 시리즈/그룹 스킬 1개 보장 풀세트 빌드 자동 생성
git add CLAUDE.md
git commit -m "docs: .랜덤 기능 CLAUDE.md 반영"
```

---

## 배포 절차 (참고)

CLAUDE.md memory 의 "인스턴스 배포는 확인 후" 규칙에 따라 — 위 task 모두 끝나도 사용자 OK 받기 전 pscp/restart 금지.

배포 시 (사용자 OK 후):
```bash
pscp -r commands/random_build.py main.py commands/chat.py db.py ubuntu@<server>:/home/ubuntu/mhws-bot/
ssh ubuntu@<server> 'sudo systemctl restart mhws-bot'
```

---

## 자가 리뷰 결과 (Plan 작성 후)

**스펙 커버리지:**
- ✅ 데이터 풀 4종 (스펙 2장) → Task 1
- ✅ 발동 모드 3종 + 시리즈 풀 (스펙 3.1) → Task 2
- ✅ 방어구 픽 + 5피스 풀 제한 (스펙 3.2) → Task 2
- ✅ 무기/호석 픽 (스펙 3.3, 3.4) → Task 3
- ✅ 장식주 첫 슬롯만 + 풀 분리 (스펙 3.5) → Task 3
- ✅ 출력 형식 (스펙 4.1) → Task 4
- ✅ 다이애나 도구 (스펙 4.2, 5) → Task 7
- ✅ 구현 위치 (스펙 6) → Task 1/6/7
- ✅ 엣지케이스 (스펙 7) → Task 3 (첫 슬롯 후보 없음 → None 반환 → format_build 가 생략)
- ✅ 테스트 (스펙 8) → Task 5 sanity 스크립트로 T1/T4/T5 직접 검증, T2 모드 분포, T3 다양성 측정

**Type 일관성:** `bonus_skill_kr`, `bonus_skill_level`, `weapon_accessory`, `armor_accessories` 키가 Task 3/4/5 에서 모두 동일 사용.

**Placeholder 없음.** 모든 step 에 실제 코드/명령어/expected 포함.
