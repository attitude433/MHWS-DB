"""봇 서버에서 실행 — chat_logs_dump.json 의 message 들을 iris /decrypt 로 평문화."""
import json
import sys
import requests
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'chat_logs_dump.json'
OUT = ROOT / 'chat_logs_decrypted.json'
IRIS = 'http://127.0.0.1:3000'

with open(SRC, encoding='utf-8') as f:
    rows = json.load(f)

print(f'총 {len(rows)} rows 복호화 시작', flush=True)

session = requests.Session()
out = []
ok = 0
fail = 0
for i, r in enumerate(rows):
    cipher = r.get('message', '')
    try:
        uid = int(r['user_id'])
    except (ValueError, TypeError, KeyError):
        fail += 1
        continue
    if not cipher:
        fail += 1
        continue
    plain = None
    try:
        res = session.post(
            f'{IRIS}/decrypt',
            json={'enc': 31, 'b64_ciphertext': cipher, 'user_id': uid},
            timeout=5,
        )
        data = res.json()
        plain = data.get('plain_text')
    except Exception as ex:
        pass
    if plain:
        ok += 1
        out.append({
            'user_id': uid,
            'created_at': int(r['created_at']),
            'message': plain,
        })
    else:
        fail += 1
    if (i + 1) % 500 == 0:
        print(f'  {i+1}/{len(rows)}  ok={ok}  fail={fail}', flush=True)

print(f'\n완료  ok={ok}  fail={fail}', flush=True)
with open(OUT, 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False)
print(f'저장: {OUT}', flush=True)
