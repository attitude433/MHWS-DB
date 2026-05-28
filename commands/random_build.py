"""다이애나 랜덤 빌드 generator.

스펙: docs/superpowers/specs/2026-05-22-diana-random-build-design.md
"""
from __future__ import annotations
import random
from typing import Optional

import db

MODE_SET_LV1 = 'set_lv1'
MODE_SET_LV2 = 'set_lv2'
MODE_GROUP = 'group'

PIECE_ORDER = ['head', 'chest', 'arms', 'waist', 'legs']


def _weapon_leaf_pool() -> list[dict]:
    return [
        w for w in db.weapons_all
        if not (w.get('crafting') or {}).get('branches')
    ]


def _armor_pool() -> list[dict]:
    return [
        s for s in db.armor
        if s.get('rarity', 0) >= 4 and len(s.get('pieces') or []) == 5
    ]


def _final_charm_pool() -> list[dict]:
    by_series: dict = {}
    for c in db.charms:
        sid = c.get('series_id')
        if sid is None:
            continue
        cur = by_series.get(sid)
        if cur is None or c.get('level', 0) > cur.get('level', 0):
            by_series[sid] = c
    return list(by_series.values())


def _accessory_pool() -> list[dict]:
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


def _pick_mode_and_series(armor_pool: list[dict]) -> tuple[str, dict, int]:
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


def _pick_armor(armor_pool: list[dict], focus_series: dict, required: int) -> dict:
    focus_pieces = list(focus_series.get('pieces', []))
    chosen_focus = random.sample(focus_pieces, required)
    result: dict = {}
    for p in chosen_focus:
        result[p['kind']] = dict(p, _series_name=focus_series.get('name_kr', ''))

    remaining_kinds = [k for k in PIECE_ORDER if k not in result]
    for kind in remaining_kinds:
        piece = None
        while piece is None:
            cand = random.choice(armor_pool)
            piece = next((p for p in cand.get('pieces', []) if p['kind'] == kind), None)
            if piece:
                result[kind] = dict(piece, _series_name=cand.get('name_kr', ''))
    return result


def _pick_first_slot_accessory(
    slots: list, allowed_kinds: tuple, acc_pool: list[dict]
) -> Optional[dict]:
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
    return format_build(generate_random_build())
