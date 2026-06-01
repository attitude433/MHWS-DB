"""카톡 export txt 에서 meals.json 의 음식 메뉴 언급 추출."""
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TXT = Path(r'C:\Users\goodb\OneDrive\바탕 화면\KakaoTalk_20260529_1033_54_175_group.txt')
MEALS = ROOT / 'meals.json'

with open(MEALS, encoding='utf-8') as f:
    raw_meals = json.load(f)
# 1글자 메뉴 (번/난/김/죽 등) 는 false positive 폭주 → 2글자 이상만
meals = sorted([m for m in raw_meals if len(m) >= 2], key=lambda x: -len(x))

# 메시지 본문만 추출
MSG_RE = re.compile(r'^\[(.+?)\]\s*\[(오전|오후)\s*\d{1,2}:\d{2}\]\s*(.*)$')
bodies = []
with open(TXT, encoding='utf-8') as f:
    for line in f:
        m = MSG_RE.match(line.rstrip('\n'))
        if m:
            body = m.group(3).strip()
            # 시스템 메시지 / 봇 메시지 / 이모티콘 / 사진 등 제외
            sender = m.group(1)
            if '엉봇' in sender or '오픈채팅봇' in sender:
                continue
            if body in ('이모티콘', '사진', '동영상', '파일', '음성메시지', ''):
                continue
            bodies.append(body)

print(f'총 메시지: {len(bodies)}')

# 매칭
cnt = Counter()
for body in bodies:
    seen_in_msg = set()
    for meal in meals:
        if meal in body and meal not in seen_in_msg:
            cnt[meal] += 1
            seen_in_msg.add(meal)

print(f'언급된 음식 (1회 이상): {len(cnt)}')
print()
print('=== 상위 50 ===')
for meal, c in cnt.most_common(50):
    print(f'  {c:5d}회  {meal}')

# 메뉴풀에 없는 단어가 음식 같으면 ?
# 일단 풀 매칭 결과만
