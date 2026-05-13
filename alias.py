import db

MONSTER_ALIASES = {
    "고그마지오스": ["고구마", "고그마", "거극룡"],
    "오메가 플라네테스": ["오메가", "영식"],
    "진 다하드": ["진다하드", "진다", "이긴다소프트", "동봉룡"],
    "알슈베르도": ["알슈", "쇄인룡"],
    "리오레우스": ["레우스", "레후스", "화룡"],
    "라기아크루스": ["라기아", "해룡"],
    "고어 마가라": ["고어", "마가라", "흑식룡"],
    "셀레기오스": ["셀레기", "천인룡"],
    "우드 투나": ["나무참치", "파의룡"],
    "그라비모스": ["그라비", "개룡"],
    "타마미츠네": ["미츠네", "포호룡"],
    "누 이그드라": ["문어", "염옥소"],
    "리오레이아": ["레이아", "자화룡"],
    "얀쿡크": ["얀쿡", "얀센세", "얀선생", "괴조"],
    "푸푸로포루": ["바즈", "소분룡"],
    "랑고스타": ["란고스타", "모기"],
    "조 시아": ["백열룡"],
    "수호룡 도샤구마": ["호벽수"],
    "레 다우": ["황뢰룡"],
    "라바라 바리나": ["자화지주"],
    "바바콩가": ["도모수"],
    "네르스큐라": ["영지주"],
    "수호룡 알슈베르도": ["호쇄인룡"],
    "케마트리스": ["염미룡"],
    "도샤구마": ["벽수"],
    "발라하라": ["사해룡"],
    "차타카브라": ["전와"],
    "수호룡 안쟈나프 아종": ["호뢰악룡"],
    "히라바미": ["풍협룡"],
    "아자라칸": ["혁원수"],
    "게리오스": ["독괴조"],
    "시이우": ["암기소"],
    "수호룡 리오레우스": ["호화룡"],
    "수호룡 오도가론 아종": ["호흉조룡"],
    "도도블랑고": ["눈사자"],
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

GLYPH_VARIANTS = {
    'α': ('알파', 'A', 'a'),
    'β': ('베타', 'B', 'b'),
    'γ': ('감마', 'Y', 'y'),
    'Ⅰ': ('I', '1'),
    'Ⅱ': ('II', '2'),
    'Ⅲ': ('III', '3'),
    'Ⅳ': ('IV', '4'),
    'Ⅴ': ('V', '5'),
}


def _variant_keys(key: str) -> set[str]:
    keys = {key}
    for src, alts in GLYPH_VARIANTS.items():
        if src not in key:
            continue
        new_keys = set()
        for k in keys:
            for alt in alts:
                new_keys.add(k.replace(src, alt))
        keys |= new_keys
    return keys


_item_index: dict[str, dict] = {}
for _name, _data in db.item_usage.items():
    _key = _name.replace(' ', '')
    for _variant in _variant_keys(_key):
        _item_index.setdefault(_variant, _data)

_weapon_full_index: dict[str, dict] = {}
_weapon_series_groups: dict[str, list[dict]] = {}
for _w in db.weapons_all:
    _key = _w['name_kr'].replace(' ', '')
    for _variant in _variant_keys(_key):
        _weapon_full_index.setdefault(_variant, _w)
    _series = (_w.get('series_name_kr') or '').replace(' ', '')
    if _series:
        _weapon_series_groups.setdefault(_series, []).append(_w)


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
    key = query.replace(' ', '')
    return _item_index.get(key)


def find_monster_partial(query: str):
    tokens = query.replace(' ', '')
    for key in sorted(_monster_index.keys(), key=len, reverse=True):
        if len(key) >= 2 and key in tokens:
            return db.monster_index.get(_monster_index[key])
    return None


def find_skill_partial(query: str) -> str | None:
    tokens = query.replace(' ', '')
    for key in sorted(_skill_index.keys(), key=len, reverse=True):
        if len(key) >= 2 and key in tokens:
            return _skill_index[key]
    return None


def find_item_partial(query: str):
    tokens = query.replace(' ', '')
    for key in sorted(_item_index.keys(), key=len, reverse=True):
        if len(key) >= 2 and key in tokens:
            return _item_index[key]
    return None


def find_weapon(query: str):
    key = query.replace(' ', '')
    return _weapon_full_index.get(key)


def find_weapon_candidates(query: str, limit: int = 15) -> list[str]:
    key = query.replace(' ', '')
    if len(key) < 2:
        return []
    seen: dict[str, dict] = {}
    for k, w in _weapon_full_index.items():
        if key in k:
            name = w['name_kr']
            if name not in seen:
                seen[name] = w
        if len(seen) >= limit:
            break
    return list(seen.keys())


# 방어구 인덱스 (피스 단위)
_armor_piece_index: dict[str, dict] = {}
for _set in db.armor:
    for _piece in _set.get('pieces', []):
        _piece['_set'] = _set
        _key = _piece['name_kr'].replace(' ', '')
        for _variant in _variant_keys(_key):
            _armor_piece_index.setdefault(_variant, _piece)


def find_armor_piece(query: str):
    key = query.replace(' ', '')
    return _armor_piece_index.get(key)


def find_armor_candidates(query: str, limit: int = 15) -> list[str]:
    key = query.replace(' ', '')
    if len(key) < 2:
        return []
    seen: dict[str, dict] = {}
    for k, p in _armor_piece_index.items():
        if key in k:
            name = p['name_kr']
            if name not in seen:
                seen[name] = p
        if len(seen) >= limit:
            break
    return list(seen.keys())
