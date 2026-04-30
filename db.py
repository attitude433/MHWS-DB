import json
from pathlib import Path

ROOT = Path(__file__).parent


def _load(path):
    with open(ROOT / path, encoding='utf-8') as f:
        return json.load(f)


monsters = _load('monsters.json')
skills = _load('skills.json')
item_usage = _load('mapping/item_usage.json')
skill_to_equipment = _load('mapping/skill_to_equipment_1.json')
external_guides = _load('external_guides.json')

monster_index = {m['name_kr']: m for m in monsters}
skill_index = {s['name_kr']: s for s in skills}
