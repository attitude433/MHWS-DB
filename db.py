import json
from pathlib import Path

ROOT = Path(__file__).parent


def _load(path):
    with open(ROOT / path, encoding='utf-8') as f:
        return json.load(f)


monsters = _load('data/monsters/monsters.json')
for _m in monsters:
    _all = _m.get('parts', [])
    _m['hide_parts'] = [_p for _p in _all if _p.get('part') == 'hide']
    _m['parts'] = [_p for _p in _all if _p.get('part') != 'hide']
skills = _load('data/equipment/skills.json')
item_usage = _load('mapping/item_usage.json')
skill_to_equipment = _load('mapping/skill_to_equipment_1.json')
external_guides = _load('data/misc/external_guides.json')
gathering = _load('data/misc/gathering.json')
weapons = _load('data/equipment/weapons.json')
weapons_all = _load('data/equipment/weapons_all.json')
armor = _load('data/equipment/armor.json')
charm = _load('data/equipment/charm.json')
charms = _load('data/equipment/charms.json')
artian = _load('data/equipment/artian.json')
meals = _load('meals.json')
horn_melodies = _load('data/combat/horn_melodies.json')
meal_ingredients = _load('mapping/meal_ingredients.json')
meal_village = _load('mapping/meal_village.json')
meal_random_skills = _load('mapping/meal_random_skills.json')
meal_notes = _load('mapping/meal_notes.json')
dlc_news = _load('data/world/dlc_news.json')

monster_index = {m['name_kr']: m for m in monsters}
skill_index = {s['name_kr']: s for s in skills}


monster_to_equipment: dict = {}


def build_monster_to_equipment(alias_groups: dict) -> dict:
    """각 몬스터에 대해 그 몬스터 시리즈 무기/방어구 인덱싱.

    무기: weapon.series_name_kr (예: "천인룡 파생") prefix 가 monster 별칭/소재 prefix 와
          정확 매칭. 한 시리즈 = 한 몬스터.
    방어구: 시리즈 모든 piece 의 crafting.inputs 와 monster.rewards 교집합 다수결.
          매칭 ≥3개 또는 ≥40% 인 monster 가 primary 가 됨.
    """
    from collections import Counter
    canonical_to_keywords: dict = {}
    monster_mats: dict = {}
    for m in monsters:
        kws = {m['name_kr']}
        for a in alias_groups.get(m['name_kr'], []):
            kws.add(a)
        mats = set()
        prefix_cnt: Counter = Counter()
        for r in (m.get('rewards') or []):
            name = r.get('item_name_kr', '')
            if not name:
                continue
            mats.add(name)
            if '의 ' in name:
                prefix = name.split('의 ', 1)[0]
            elif ' 사냥증' in name:
                prefix = name.split(' 사냥증', 1)[0]
            else:
                continue
            if len(prefix) >= 2:
                prefix_cnt[prefix] += 1
        # 가장 자주 나온 prefix 1개만 (cross-reward 무시)
        if prefix_cnt:
            top, _ = prefix_cnt.most_common(1)[0]
            kws.add(top)
        canonical_to_keywords[m['name_kr']] = kws
        monster_mats[m['name_kr']] = mats

    result = {n: {'weapons': [], 'armor_series': []} for n in canonical_to_keywords}

    for w in weapons_all:
        sname = (w.get('series_name_kr') or '').strip()
        if not sname:
            continue
        series_prefix = sname[:-3].strip() if sname.endswith(' 파생') else sname
        for mname, kws in canonical_to_keywords.items():
            if series_prefix in kws:
                result[mname]['weapons'].append({
                    'name_kr': w['name_kr'],
                    'kind_kr': w.get('kind_kr', ''),
                })
                break

    for s in armor:
        match_count: dict = {}
        total = 0
        for p in (s.get('pieces') or []):
            for i in ((p.get('crafting') or {}).get('inputs') or []):
                iname = i.get('name_kr', '')
                if not iname:
                    continue
                total += 1
                for mname, mats in monster_mats.items():
                    if iname in mats:
                        match_count[mname] = match_count.get(mname, 0) + 1
        if not match_count or total == 0:
            continue
        primary = max(match_count, key=match_count.get)
        cnt = match_count[primary]
        if cnt >= 3 or cnt / total >= 0.4:
            result[primary]['armor_series'].append({
                'name_kr': s['name_kr'],
                'pieces': [p.get('name_kr', '') for p in (s.get('pieces') or [])],
            })

    return result
