"""items.json description 의 '특산품' 표기로 stage 추출 → item_usage.json gathering 필드 채움."""
from __future__ import annotations
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ITEMS_PATH = ROOT / 'data' / 'misc' / 'items.json'
USAGE_PATH = ROOT / 'mapping' / 'item_usage.json'

STAGE_PATTERNS = [
    '경계의 모래 평원',
    '주홍빛 숲',
    '기름 솟는 계곡',
    '빙무의 절벽',
    '용도의 폐허',
    '동쪽 지역',
]

items = json.loads(ITEMS_PATH.read_text(encoding='utf-8'))
usage = json.loads(USAGE_PATH.read_text(encoding='utf-8'))

changed_count = 0
added_count = 0
results = []

for item in items:
    desc = (item.get('description_kr') or '').replace('\r', '').replace('\n', ' ')
    if '특산품' not in desc:
        continue
    name_kr = item.get('name_kr')
    if not name_kr:
        continue

    matched_stage = None
    for stage in STAGE_PATTERNS:
        if stage in desc:
            matched_stage = stage
            break
    if not matched_stage:
        continue

    if re.search(r'귀중한\s*(?:\s*특산품|특산품)', desc) or '귀중한' in desc.split('특산품')[0][-15:]:
        grade = '귀중한'
    elif re.search(r'진귀한\s*(?:\s*특산품|특산품)', desc) or '진귀한' in desc.split('특산품')[0][-15:]:
        grade = '진귀한'
    else:
        grade = ''

    label = f'{matched_stage} 특산' if not grade else f'{matched_stage} {grade} 특산'

    entry = usage.get(name_kr)
    created = False
    if entry is None:
        entry = {
            'item_id': item.get('id'),
            'name_kr': name_kr,
            'name_en': item.get('name_en', ''),
            'drops_count': 0,
            'used_in_armor_count': 0,
            'used_in_weapons_count': 0,
            'used_in_charms_count': 0,
            'used_in_items_count': 0,
            'drops_from_monsters': [],
            'used_in_armor': [],
            'used_in_weapons': [],
            'used_in_charms': [],
            'used_in_items': [],
        }
        usage[name_kr] = entry
        created = True
        added_count += 1

    gathering = entry.get('gathering') or []
    if label not in gathering:
        gathering.insert(0, label)
        entry['gathering'] = gathering
        if not created:
            changed_count += 1
        results.append(f"{'NEW' if created else 'UPD'}  {name_kr:20s}  → {label}")

print(f'특산 매칭: {len(results)} 건  (신규 entry: {added_count}, 기존 갱신: {changed_count})')
for r in results:
    print(r)

USAGE_PATH.write_text(json.dumps(usage, ensure_ascii=False, indent=2), encoding='utf-8')
print(f'\n저장: {USAGE_PATH}')
