"""다이애나 도메인용 웹 서버 — 제니 분포도 페이지.

`d-i-0336-7.p-e.kr` 도메인으로 접속 시 members.db 의 제니 분포를 HTML 로 제공.
봇 프로세스 백그라운드 스레드로 기동, 0.0.0.0:80 listen.
"""
from __future__ import annotations
import json as _json
import os
import statistics
import urllib.request
from typing import Optional

from flask import Flask, jsonify, request
import logging

import members
import nicknames as _nicknames
from commands.zenny import EXCLUDED_USER_IDS

IRIS_QUERY_URL = 'http://127.0.0.1:3000/query'
SNS_ROOM_ID = os.environ.get('SNS_ROOM_ID', '')


def _get_active_members() -> Optional[set]:
    """Iris /query 로 카톡방 현재 활성 멤버 user_id 셋 반환. 실패 시 None."""
    room_id = os.environ.get('SNS_ROOM_ID', SNS_ROOM_ID)
    if not room_id:
        return None
    try:
        body = _json.dumps({
            'query': f'SELECT active_member_ids FROM chat_rooms WHERE id={int(room_id)}'
        }).encode()
        req = urllib.request.Request(
            IRIS_QUERY_URL, data=body,
            headers={'Content-Type': 'application/json'},
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            resp = _json.load(r)
        rows = resp.get('data', [])
        if not rows:
            return None
        ids_str = rows[0].get('active_member_ids', '[]') or '[]'
        ids = _json.loads(ids_str)
        return {int(x) for x in ids}
    except Exception as ex:
        print(f'[web] active members fetch error: {ex}', flush=True)
        return None

app = Flask(__name__)
logging.getLogger('werkzeug').setLevel(logging.WARNING)

def _current_key() -> str:
    # 매 호출 시 env 읽기 — main.py 의 load_dotenv() 시점 의존 제거
    return os.environ.get('WEB_KEY', '')


def _key_ok() -> bool:
    wk = _current_key()
    if not wk:
        return True
    return request.args.get('key', '') == wk


GATE_PAGE = """<!DOCTYPE html>
<html lang="ko"><head>
<meta charset="UTF-8">
<title>🎰 제니 분포 대시보드</title>
<meta name="description" content="몬헌 와일즈 카톡방 - 실시간 제니 분포 통계">
<meta property="og:title" content="🎰 제니 분포 대시보드">
<meta property="og:description" content="몬헌 와일즈 카톡봇 — 실시간 제니 분포 통계">
<meta property="og:type" content="website">
<meta property="og:url" content="http://mhws.diana.ai.kr">
<meta property="og:site_name" content="다이애나">
<meta property="og:locale" content="ko_KR">
<meta name="twitter:card" content="summary">
<style>
  body { font-family: -apple-system, 'Apple SD Gothic Neo', sans-serif;
         background: linear-gradient(135deg,#0f0c29,#302b63,#24243e); color:#fff;
         min-height:100vh; margin:0; display:flex; align-items:center; justify-content:center; padding:20px; }
  .box { background: rgba(255,255,255,0.05); backdrop-filter: blur(10px);
         border:1px solid rgba(255,255,255,0.1); border-radius:14px; padding:34px 28px;
         text-align:center; max-width:420px; }
  h1 { color:#ffd700; margin:0 0 14px; font-size:22px; }
  p { color:#bbb; line-height:1.6; margin:8px 0; font-size:14px; }
  .cmd { display:inline-block; background:rgba(255,215,0,0.12); color:#ffd700;
         padding:4px 10px; border-radius:6px; font-family:monospace; font-size:14px; }
</style>
</head><body>
<div class="box">
  <h1>🎰 제니 분포 대시보드</h1>
  <p>카톡방 봇 멤버 전용 페이지에요.</p>
  <p>몬헌 와일즈 카톡방에서 <span class="cmd">.제니분포</span> 를 입력하면<br>다이애나가 접속 링크를 알려줘요.</p>
</div>
</body></html>
"""


# 잔고 구간 (라벨, 하한, 상한)
BUCKETS = [
    ('0',          0,      0),
    ('1~100',      1,      100),
    ('101~500',    101,    500),
    ('501~1,000',  501,    1_000),
    ('1,001~3,000',1_001,  3_000),
    ('3,001~10,000', 3_001, 10_000),
    ('10,001+',    10_001, float('inf')),
]


def _safe_nick(uid: int, raw: Optional[str]) -> str:
    mapped = _nicknames.get(uid)
    if mapped:
        return mapped
    return raw or '익명 헌터'


def _collect() -> dict:
    with members._conn() as c:
        rows_raw = c.execute('SELECT user_id, nickname, zenny FROM members').fetchall()
        history_raw = c.execute(
            'SELECT user_id, date, zenny FROM zenny_history ORDER BY user_id, date'
        ).fetchall()
    # 카톡방 현재 활성 멤버 가져옴 (Iris API). 실패 시 None → 필터 비활성 (안전 fallback)
    active_set = _get_active_members()
    # 운영자 제외 + 닉네임 매핑된 멤버 + 카톡방 현재 멤버만
    rows = []
    nick_map = {}
    for uid, nick, z in rows_raw:
        if uid in EXCLUDED_USER_IDS:
            continue
        mapped = _nicknames.get(uid)
        if not mapped:
            continue
        if active_set is not None and uid not in active_set:
            continue  # 카톡방에서 나간 멤버 제외
        rows.append((uid, mapped, z))
        nick_map[uid] = mapped
    if not rows:
        return {
            'total_members': 0, 'total_zenny': 0, 'mean': 0, 'median': 0,
            'top5_sum': 0, 'top5_pct': 0,
            'buckets': [{'label': l, 'count': 0} for l, _, _ in BUCKETS],
            'ranking': [],
        }

    zennies = [z for _, _, z in rows]
    rows_sorted = sorted(rows, key=lambda r: (-r[2], r[1]))
    top5_sum = sum(z for _, _, z in rows_sorted[:5])
    total = sum(zennies)
    top5_pct = round(top5_sum / total * 100, 1) if total > 0 else 0

    bucket_counts = [0] * len(BUCKETS)
    for z in zennies:
        for i, (_, lo, hi) in enumerate(BUCKETS):
            if lo <= z <= hi:
                bucket_counts[i] += 1
                break

    # zenny_history 분석 — 펌프/풀림/단일 최대 이벤트/일별 총량 추이
    # 사용자별 일별 변화량을 펌프(양수) / 풀림(음수절댓값)으로 집계
    pump = 0
    drain = 0
    max_gain = {'delta': 0, 'nick': '', 'date': ''}
    max_loss = {'delta': 0, 'nick': '', 'date': ''}  # delta 는 음수
    zero_drops = 0  # 잔고 0으로 떨어진 횟수 (초기화 추정)
    daily_totals: dict = {}  # date -> 그날 모든 활성 유저 잔고 합
    prev_by_uid: dict = {}

    for uid, date, z in history_raw:
        if uid not in nick_map:
            continue
        prev = prev_by_uid.get(uid, 0)  # 첫 기록 이전엔 0 으로 가정
        delta = z - prev
        if delta > 0:
            pump += delta
            if delta > max_gain['delta']:
                max_gain = {'delta': delta, 'nick': nick_map[uid], 'date': date}
        elif delta < 0:
            drain += -delta
            if delta < max_loss['delta']:
                max_loss = {'delta': delta, 'nick': nick_map[uid], 'date': date}
            if z == 0 and prev > 0:
                zero_drops += 1
        prev_by_uid[uid] = z
        daily_totals[date] = daily_totals.get(date, 0) + z

    # 일별 총량 — 활성 유저 잔고가 그날 기록되지 않은 사람은 직전 잔고 유지로 보정 필요
    # 간단화: 기록 있는 날의 합계만 사용 (정확하진 않지만 추세 신호 충분)
    history_series = sorted(daily_totals.items())[-60:]  # 최근 60일

    return {
        'total_members': len(rows),
        'total_zenny': total,
        'mean': round(statistics.mean(zennies)),
        'median': int(statistics.median(zennies)),
        'top5_sum': top5_sum,
        'top5_pct': top5_pct,
        'buckets': [{'label': l, 'count': c} for (l, _, _), c in zip(BUCKETS, bucket_counts)],
        'ranking': [{'nick': nick, 'zenny': z} for _, nick, z in rows_sorted],
        'pump': pump,
        'drain': drain,
        'net': pump - drain,
        'max_gain': max_gain,
        'max_loss': max_loss,
        'zero_drops': zero_drops,
        'history': [{'date': d, 'total': t} for d, t in history_series],
    }


PAGE = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<title>🎰 제니 분포 대시보드</title>
<meta name="description" content="몬헌 와일즈 카톡방 - 실시간 제니 분포 통계 (활성 멤버 / 평균·중앙값 / 상위 점유율 / 전체 랭킹)">
<meta property="og:title" content="🎰 제니 분포 대시보드">
<meta property="og:description" content="몬헌 와일즈 카톡봇 — 실시간 제니 분포 통계">
<meta property="og:type" content="website">
<meta property="og:url" content="http://mhws.diana.ai.kr">
<meta property="og:site_name" content="다이애나">
<meta property="og:locale" content="ko_KR">
<meta name="twitter:card" content="summary">
<meta name="twitter:title" content="🎰 제니 분포 대시보드">
<meta name="twitter:description" content="몬헌 와일즈 카톡봇 — 실시간 제니 분포 통계">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: 'Segoe UI', 'Apple SD Gothic Neo', sans-serif;
    background: linear-gradient(135deg, #0f0c29, #302b63, #24243e);
    color: #fff;
    min-height: 100vh;
    padding: 30px;
  }
  .container { max-width: 1400px; margin: 0 auto; }
  h1 {
    color: #ffd700;
    text-align: center;
    margin-bottom: 8px;
    font-size: 28px;
    text-shadow: 0 0 20px rgba(255, 215, 0, 0.4);
  }
  .subtitle {
    color: #aaa;
    text-align: center;
    margin-bottom: 30px;
    font-size: 13px;
  }
  .summary {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 15px;
    margin-bottom: 30px;
  }
  .stat-card {
    background: rgba(255, 255, 255, 0.05);
    backdrop-filter: blur(10px);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 12px;
    padding: 18px;
    text-align: center;
  }
  .stat-label { font-size: 12px; color: #aaa; margin-bottom: 6px; }
  .stat-value { font-size: 22px; font-weight: bold; color: #ffd700; }
  .stat-sub { font-size: 11px; color: #888; margin-top: 4px; }
  .grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 20px;
    margin-bottom: 20px;
  }
  .card {
    background: rgba(255, 255, 255, 0.05);
    backdrop-filter: blur(10px);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 12px;
    padding: 20px;
  }
  .card.full { grid-column: 1 / -1; }
  .card h3 { color: #ffd700; margin-bottom: 15px; font-size: 16px; }
  .chart-container { position: relative; height: 320px; }
  .chart-container.tall { height: 500px; }
  .ranking-list {
    max-height: 500px;
    overflow-y: auto;
    padding-right: 8px;
  }
  .ranking-row {
    display: grid;
    grid-template-columns: 40px 1fr auto;
    align-items: center;
    padding: 8px 12px;
    border-radius: 6px;
    margin-bottom: 4px;
    background: rgba(255, 255, 255, 0.03);
    transition: background 0.2s;
  }
  .ranking-row:hover { background: rgba(255, 255, 255, 0.08); }
  .rank { font-weight: bold; color: #888; font-size: 13px; }
  .rank.gold { color: #ffd700; }
  .rank.silver { color: #c0c0c0; }
  .rank.bronze { color: #cd7f32; }
  .name { font-size: 13px; color: #ddd; }
  .zenny { font-weight: bold; color: #00d4ff; font-size: 13px; }
  ::-webkit-scrollbar { width: 6px; }
  ::-webkit-scrollbar-track { background: rgba(255,255,255,0.05); border-radius: 3px; }
  ::-webkit-scrollbar-thumb { background: #ffd700; border-radius: 3px; }
  @media (max-width: 768px) {
    .summary { grid-template-columns: repeat(2, 1fr); }
    .grid { grid-template-columns: 1fr; }
  }
</style>
</head>
<body>
<div class="container">
  <h1>💰 제니 분포 대시보드</h1>
  <p class="subtitle">몬헌 와일즈 카톡봇 · 실시간 데이터 (새로고침으로 갱신)</p>

  <div class="summary" id="summary"></div>

  <div class="grid">
    <div class="card full">
      <h3>📈 방 전체 총제니 추이 (최근 60일)</h3>
      <div class="chart-container"><canvas id="histLine"></canvas></div>
    </div>
  </div>

  <div class="summary" id="flow"></div>

  <div class="grid">
    <div class="card">
      <h3>📊 제니 구간별 인원 분포</h3>
      <div class="chart-container"><canvas id="histChart"></canvas></div>
    </div>
    <div class="card">
      <h3>🏆 상위 5명이 차지하는 비율</h3>
      <div class="chart-container"><canvas id="pieChart"></canvas></div>
    </div>
  </div>

  <div class="grid">
    <div class="card full">
      <h3>📈 전체 랭킹 분포 (로그 스케일)</h3>
      <div class="chart-container tall"><canvas id="rankChart"></canvas></div>
    </div>
  </div>

  <div class="grid">
    <div class="card full">
      <h3>👥 전체 랭킹</h3>
      <div class="ranking-list" id="rankList"></div>
    </div>
  </div>
</div>

<script>
fetch('/api/zenny?key=__KEY__').then(r => r.json()).then(d => {
  const total = d.total_zenny;
  const data = d.ranking;

  document.querySelector('.subtitle').textContent =
    `몬헌 와일즈 카톡봇 · 활성 멤버 ${d.total_members}명 · 실시간 데이터 (새로고침으로 갱신)`;

  document.getElementById('summary').innerHTML = `
    <div class="stat-card">
      <div class="stat-label">활성 멤버</div>
      <div class="stat-value">${d.total_members}</div>
      <div class="stat-sub">제니 보유자</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">전체 제니</div>
      <div class="stat-value">${total.toLocaleString()}</div>
      <div class="stat-sub">유통량</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">평균</div>
      <div class="stat-value">${d.mean.toLocaleString()}</div>
      <div class="stat-sub">중앙값 ${d.median.toLocaleString()}</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">상위 5명 점유율</div>
      <div class="stat-value">${d.top5_pct}%</div>
      <div class="stat-sub">${d.top5_sum.toLocaleString()}제니</div>
    </div>
  `;

  // 시스템 흐름 카드 (펌프/풀림/최대이벤트)
  const mg = d.max_gain || {};
  const ml = d.max_loss || {};
  document.getElementById('flow').innerHTML = `
    <div class="stat-card">
      <div class="stat-label">💧 누적 펌프 (유입)</div>
      <div class="stat-value" style="color:#44dd88">+${d.pump.toLocaleString()}</div>
      <div class="stat-sub">출석·룰렛 양수·잭팟·승</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">🔥 누적 풀림 (소멸)</div>
      <div class="stat-value" style="color:#ff6688">-${d.drain.toLocaleString()}</div>
      <div class="stat-sub">초기화 ${d.zero_drops}회 · 음수 룰렛 · 패</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">📈 최대 단일 이득</div>
      <div class="stat-value" style="color:#44dd88">+${(mg.delta || 0).toLocaleString()}</div>
      <div class="stat-sub">${mg.nick || '-'} (${mg.date || '-'})</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">📉 최대 단일 손실</div>
      <div class="stat-value" style="color:#ff6688">${(ml.delta || 0).toLocaleString()}</div>
      <div class="stat-sub">${ml.nick || '-'} (${ml.date || '-'})</div>
    </div>
  `;

  // 총제니 추이 라인 차트
  new Chart(document.getElementById('histLine'), {
    type: 'line',
    data: {
      labels: d.history.map(h => h.date.slice(5)),  // MM-DD
      datasets: [{
        label: '방 전체 총제니',
        data: d.history.map(h => h.total),
        borderColor: '#ffd700',
        backgroundColor: 'rgba(255,215,0,0.15)',
        fill: true,
        tension: 0.25,
        pointRadius: 2,
        pointHoverRadius: 5,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        y: { beginAtZero: true, ticks: { color: '#aaa' }, grid: { color: 'rgba(255,255,255,0.05)' } },
        x: { ticks: { color: '#aaa', maxRotation: 60, minRotation: 0 }, grid: { display: false } }
      }
    }
  });

  // 히스토그램
  new Chart(document.getElementById('histChart'), {
    type: 'bar',
    data: {
      labels: d.buckets.map(b => b.label),
      datasets: [{
        data: d.buckets.map(b => b.count),
        backgroundColor: ['#ff4466', '#ff8844', '#ffcc44', '#88dd44', '#44dd88', '#44cccc', '#ffd700'],
        borderRadius: 6,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        y: { ticks: { color: '#aaa', precision: 0 }, grid: { color: 'rgba(255,255,255,0.05)' }, title: { display: true, text: '인원수', color: '#aaa' } },
        x: { ticks: { color: '#aaa' }, grid: { display: false } }
      }
    }
  });

  // 도넛 (상위 5 vs 나머지)
  new Chart(document.getElementById('pieChart'), {
    type: 'doughnut',
    data: {
      labels: [`상위 5명`, `나머지 ${Math.max(0, d.total_members - 5)}명`],
      datasets: [{
        data: [d.top5_sum, Math.max(0, total - d.top5_sum)],
        backgroundColor: ['#ffd700', '#444466'],
        borderColor: 'rgba(0,0,0,0.3)',
        borderWidth: 2,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { labels: { color: '#fff' } },
        tooltip: {
          callbacks: {
            label: ctx => `${ctx.label}: ${ctx.parsed.toLocaleString()}제니 (${total > 0 ? (ctx.parsed / total * 100).toFixed(1) : 0}%)`
          }
        }
      }
    }
  });

  // 랭킹 분포 (로그 스케일) — 잔고 0 이상이지만 log에선 1 이상이어야 보임
  const rankData = data.map(r => ({ ...r, plot: Math.max(1, r.zenny) }));
  new Chart(document.getElementById('rankChart'), {
    type: 'bar',
    data: {
      labels: rankData.map((d, i) => `${i + 1}.${d.nick}`),
      datasets: [{
        label: '제니',
        data: rankData.map(d => d.plot),
        backgroundColor: rankData.map((d, i) => {
          if (i === 0) return '#ffd700';
          if (i === 1) return '#c0c0c0';
          if (i === 2) return '#cd7f32';
          if (i < 10) return '#00d4ff';
          return 'rgba(100, 150, 200, 0.6)';
        }),
        borderRadius: 4,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: ctx => `${data[ctx.dataIndex].zenny.toLocaleString()}제니`
          }
        }
      },
      scales: {
        y: {
          type: 'logarithmic',
          ticks: { color: '#aaa' },
          grid: { color: 'rgba(255,255,255,0.05)' },
          title: { display: true, text: '제니 (log)', color: '#aaa' }
        },
        x: { ticks: { color: '#aaa', autoSkip: false, maxRotation: 90, minRotation: 90, font: { size: 9 } }, grid: { display: false } }
      }
    }
  });

  // 랭킹 리스트
  document.getElementById('rankList').innerHTML = data.map((r, i) => {
    let rankClass = '', icon = `${i + 1}`;
    if (i === 0) { rankClass = 'gold'; icon = '🥇'; }
    else if (i === 1) { rankClass = 'silver'; icon = '🥈'; }
    else if (i === 2) { rankClass = 'bronze'; icon = '🥉'; }
    return `
      <div class="ranking-row">
        <div class="rank ${rankClass}">${icon}</div>
        <div class="name">${r.nick}</div>
        <div class="zenny">${r.zenny.toLocaleString()} z</div>
      </div>`;
  }).join('');
});
</script>
</body>
</html>
"""


@app.route('/')
def index():
    key = request.args.get('key', '')
    wk = _current_key()
    if wk and key != wk:
        return GATE_PAGE
    return PAGE.replace('__KEY__', key)


@app.route('/api/zenny')
def api_zenny():
    if not _key_ok():
        return jsonify({'error': 'unauthorized'}), 403
    return jsonify(_collect())


def start_server(host: str = '0.0.0.0', port: int = 80):
    print(f'[web] starting on {host}:{port}', flush=True)
    try:
        app.run(host=host, port=port, threaded=True, use_reloader=False)
    except Exception as ex:
        print(f'[web] error: {ex}', flush=True)
