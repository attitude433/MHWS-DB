import db

MONSTER_ALIASES = {
    "고그마지오스": ["고구마", "고그마"],
    "오메가 플라네테스": ["오메가", "영식"],
    "진 다하드": ["진다하드", "진다", "이긴다소프트"],
    "알슈베르도": ["알슈"],
    "리오레우스": ["레우스", "레후스"],
    "라기아크루스": ["라기아"],
    "고어 마가라": ["고어", "마가라"],
    "셀레기오스": ["셀레기"],
    "우드 투나": ["나무참치"],
    "그라비모스": ["그라비"],
    "타마미츠네": ["미츠네"],
    "누 이그드라": ["문어"],
    "리오레이아": ["레이아"],
    "얀쿡크": ["얀쿡", "얀센세", "얀선생"],
    "푸푸로포루": ["바즈"],
    "랑고스타": ["란고스타", "모기"],
}

_monster_index: dict[str, str] = {}
for _canonical, _aliases in MONSTER_ALIASES.items():
    _monster_index[_canonical.replace(' ', '')] = _canonical
    for _a in _aliases:
        _monster_index[_a.replace(' ', '')] = _canonical
for _m in db.monsters:
    _key = _m['name_kr'].replace(' ', '')
    if _key not in _monster_index:
        _monster_index[_key] = _m['name_kr']

_weapon_index: dict[str, dict] = {}
for _g in db.external_guides['guides']:
    _key = _g['weapon_kr'].replace(' ', '')
    _weapon_index[_key] = _g
    for _a in _g.get('aliases', []):
        _weapon_index[_a.replace(' ', '').lower()] = _g

_skill_index: dict[str, str] = {}
for _s in db.skills:
    _key = _s['name_kr'].replace(' ', '')
    _skill_index[_key] = _s['name_kr']


def find_monster(query: str):
    key = query.replace(' ', '')
    canonical = _monster_index.get(key)
    return db.monster_index.get(canonical) if canonical else None


def find_skill(query: str) -> str | None:
    key = query.replace(' ', '')
    return _skill_index.get(key)


def find_weapon_guide(query: str):
    key = query.replace(' ', '').lower()
    return _weapon_index.get(key)


def find_item(query: str):
    return db.item_usage.get(query)
