import json
from pathlib import Path

ROOT = Path(__file__).parent


def _load(path):
    with open(ROOT / path, encoding='utf-8') as f:
        return json.load(f)


monsters = _load('monsters.json')
for _m in monsters:
    _all = _m.get('parts', [])
    _m['hide_parts'] = [_p for _p in _all if _p.get('part') == 'hide']
    _m['parts'] = [_p for _p in _all if _p.get('part') != 'hide']
skills = _load('skills.json')
item_usage = _load('mapping/item_usage.json')
skill_to_equipment = _load('mapping/skill_to_equipment_1.json')
external_guides = _load('external_guides.json')
gathering = _load('gathering.json')
weapons = _load('weapons.json')
weapons_all = _load('weapons_all.json')
armor = _load('armor.json')
charm = _load('charm.json')
meals = _load('meals.json')
meal_ingredients = _load('mapping/meal_ingredients.json')
meal_village = _load('mapping/meal_village.json')
meal_random_skills = _load('mapping/meal_random_skills.json')
meal_notes = _load('mapping/meal_notes.json')

monster_index = {m['name_kr']: m for m in monsters}
skill_index = {s['name_kr']: s for s in skills}
