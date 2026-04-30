SIMULATOR_MSG = """스킬 시뮬레이터에서 직접 짜보세요

https://mhf.inven.co.kr/db/mhwilds/skillsimulator/

무기별 추천 빌드는 .커스텀 [무기명] 으로 확인하세요"""


def format_custom() -> str:
    return SIMULATOR_MSG


def format_custom_weapon(weapon_name: str, guides: dict) -> str:
    key = weapon_name.replace(' ', '').lower()
    for g in guides['guides']:
        if g['weapon_kr'].replace(' ', '') == weapon_name.replace(' ', ''):
            return _guide_msg(g, guides['source_kr'])
        for alias in g.get('aliases', []):
            if alias.replace(' ', '').lower() == key:
                return _guide_msg(g, guides['source_kr'])
    return f'{weapon_name} 가이드를 찾을 수 없습니다'


def _guide_msg(guide: dict, source_kr: str) -> str:
    return f'[{guide["weapon_kr"]}] 추천 빌드 가이드\n\n{guide["url"]}\n\n({source_kr})'
