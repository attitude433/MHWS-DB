"""meals.json 에서 일반인이 거의 모르는 메뉴 제거."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PATH = ROOT / 'meals.json'

REMOVE = {
    # 외국 음식 (인지도 낮음)
    '참포라도', '나시르막', '페이조아다', '잠발라야', '카오 니아오 마무앙',
    '카오소이', '팟카파오', '팟씨유', '사그파니르', '차나마살라',
    '코르마', '빈달루', '타말레', '사테',

    # 마이너 외국 빵
    '브로아', '슈톨렌', '시미트', '캉파뉴', '키스라', '푸가스',
    '흠바샤', '라바시', '룩브라우트', '소다브레드', '젠빙',
    '만터우', '유탸오', '보르초그', '란고시', '밤브레크', '빵바냐',

    # 옛 한식 / 궁중
    '누르미', '사슬적', '화양적', '돈저냐', '만두과', '편수',
    '숭채만두', '굴림만두', '규아상', '생복만두', '알쌈',
    '타락죽', '너비아니', '애저회', '맥적',

    # 향토 (도리뱅뱅이/명태순대/옹심이/낙곱새 4개 제외)
    '헛제삿밥', '돔배기', '고갈비', '콧등치기국수', '농마국수',
    '막장찌개', '올챙이국수', '자굴밥', '보말국', '다슬깃국',
    '재첩국', '갈낙탕', '조방낙지', '수구레국밥', '선산곱창',
    '양양송이밥', '숭어어란',

    # 정체불명
    '앵미밥', '자미밥', '피밥', '인조고기밥', '클로렐라밥', '따치회',

    # 옛 부위 / 잘 안 찾는 부위
    '참새구이', '토끼탕', '꿩탕', '양깃머리', '천엽', '보신탕', '염소탕',
}

with open(PATH, encoding='utf-8') as f:
    meals = json.load(f)

print(f'before: {len(meals)} 메뉴')
kept = [m for m in meals if m not in REMOVE]
removed = [m for m in meals if m in REMOVE]
not_found = REMOVE - set(meals)

print(f'after:  {len(kept)} 메뉴 (-{len(meals) - len(kept)})')
print(f'명시했지만 풀에 없던 것: {sorted(not_found)}')

# 검증: 보존되어야 할 4개 확인
must_keep = ['도리뱅뱅이', '명태순대', '옹심이', '낙곱새']
for k in must_keep:
    print(f'  {k} 보존 ✓' if k in kept else f'  {k} 누락 ✗')

with open(PATH, 'w', encoding='utf-8') as f:
    json.dump(kept, f, ensure_ascii=False, indent=2)
print(f'\n저장: {PATH}')
