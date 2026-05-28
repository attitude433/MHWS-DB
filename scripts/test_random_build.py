"""랜덤 빌드 sanity check.

3000회 호출 + 스펙 invariant 검증.
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

print()
print('--- 샘플 출력 3개 ---')
for _ in range(3):
    print(random_build_text())
    print('---')

fail = missing_bonus + slot_violations + allowed_violations
sys.exit(1 if fail else 0)
