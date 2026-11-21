#!/usr/bin/env python3
"""어제 다이애나(Anthropic API) 사용량 리포트 → 1:1 카톡 알림."""
from __future__ import annotations
import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

ENV_FILE = '/home/ubuntu/mhws-bot/.env'
IRIS_URL = 'http://127.0.0.1:3000/reply'

def load_env(path: str) -> dict:
    out = {}
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                k, v = line.split('=', 1)
                out[k.strip()] = v.strip()
    except Exception:
        pass
    return out

env = load_env(ENV_FILE)
ADMIN_KEY = env.get('ANTHROPIC_ADMIN_KEY', '')
ALERT_ROOM_ID = env.get('ALERT_ROOM_ID', '')

if not ADMIN_KEY or not ALERT_ROOM_ID:
    print('Missing ANTHROPIC_ADMIN_KEY or ALERT_ROOM_ID')
    raise SystemExit(1)

# 어제 UTC 자정 ~ 오늘 UTC 자정 (Anthropic API는 UTC day-aligned bucket 요구)
today_utc = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
yesterday_utc = today_utc - timedelta(days=1)
start_utc = yesterday_utc.strftime('%Y-%m-%dT%H:%M:%SZ')
end_utc = today_utc.strftime('%Y-%m-%dT%H:%M:%SZ')


def fetch(url: str) -> dict:
    req = urllib.request.Request(
        url,
        headers={
            'x-api-key': ADMIN_KEY,
            'anthropic-version': '2023-06-01',
        },
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


# Usage report (토큰)
usage_url = (
    'https://api.anthropic.com/v1/organizations/usage_report/messages'
    f'?starting_at={start_utc}&ending_at={end_utc}&bucket_width=1d'
)
try:
    usage = fetch(usage_url)
except Exception as ex:
    usage = {'error': str(ex)}

# Cost report (비용 USD)
cost_url = (
    'https://api.anthropic.com/v1/organizations/cost_report'
    f'?starting_at={start_utc}&ending_at={end_utc}&bucket_width=1d'
)
try:
    cost = fetch(cost_url)
except Exception as ex:
    cost = {'error': str(ex)}


def sum_usage(data: dict) -> dict:
    totals = {'input': 0, 'output': 0, 'cache_creation': 0, 'cache_read': 0}
    for bucket in data.get('data', []):
        for res in bucket.get('results', []):
            totals['input'] += int(res.get('uncached_input_tokens', 0) or 0)
            totals['output'] += int(res.get('output_tokens', 0) or 0)
            cc = res.get('cache_creation') or {}
            if isinstance(cc, dict):
                totals['cache_creation'] += int(cc.get('ephemeral_5m_input_tokens', 0) or 0)
                totals['cache_creation'] += int(cc.get('ephemeral_1h_input_tokens', 0) or 0)
            totals['cache_read'] += int(res.get('cache_read_input_tokens', 0) or 0)
    return totals


def sum_cost_data(data: dict) -> float:
    total = 0.0
    for bucket in data.get('data', []):
        for res in bucket.get('results', []):
            total += float(res.get('amount', 0) or 0)
    return total


lines = [f"📊 어제 다이애나 사용량 ({yesterday_utc.strftime('%Y-%m-%d')} UTC 기준)"]
if 'error' in usage:
    lines.append(f'토큰 조회 실패: {usage["error"]}')
else:
    t = sum_usage(usage)
    lines.append(f"input {t['input']:,} / output {t['output']:,} 토큰")
    if t['cache_creation'] or t['cache_read']:
        lines.append(f"cache write {t['cache_creation']:,} / read {t['cache_read']:,}")

if 'error' in cost:
    lines.append(f'비용 조회 실패: {cost["error"]}')
else:
    usd = sum_cost_data(cost)
    lines.append(f"비용 ${usd:.4f}")

msg = '\n'.join(lines)
print(msg)

# Iris로 알림
try:
    data = json.dumps({
        'type': 'text',
        'room': str(ALERT_ROOM_ID),
        'data': msg,
    }).encode()
    req = urllib.request.Request(IRIS_URL, data=data, headers={'Content-Type': 'application/json'})
    urllib.request.urlopen(req, timeout=10)
    print('알림 발송 완료')
except Exception as ex:
    print(f'알림 발송 실패: {ex}')
