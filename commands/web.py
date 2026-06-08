"""다이애나 도메인용 웹 서버 — 제니 분포도 페이지.

`d-i-0336-7.p-e.kr` 도메인으로 접속 시 members.db 의 제니 분포를 HTML 로 제공.
봇 프로세스 백그라운드 스레드로 기동, 0.0.0.0:80 listen.
"""
from __future__ import annotations
import statistics
from typing import Optional

from flask import Flask, jsonify
import logging

import members
import nicknames as _nicknames
from commands.zenny import EXCLUDED_USER_IDS

app = Flask(__name__)
logging.getLogger('werkzeug').setLevel(logging.WARNING)


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
    # 운영자 제외 + 닉네임 매핑된 멤버만 포함 (raw 토큰 노출 방지)
    rows = []
    for uid, nick, z in rows_raw:
        if uid in EXCLUDED_USER_IDS:
            continue
        mapped = _nicknames.get(uid)
        if not mapped:
            continue
        rows.append((uid, mapped, z))
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

    return {
        'total_members': len(rows),
        'total_zenny': total,
        'mean': round(statistics.mean(zennies)),
        'median': int(statistics.median(zennies)),
        'top5_sum': top5_sum,
        'top5_pct': top5_pct,
        'buckets': [{'label': l, 'count': c} for (l, _, _), c in zip(BUCKETS, bucket_counts)],
        'ranking': [{'nick': nick, 'zenny': z} for _, nick, z in rows_sorted],
    }


PAGE = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<title>몬헌 와일즈 봇 - 제니 분포</title>
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
fetch('/api/zenny').then(r => r.json()).then(d => {
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
    return PAGE


@app.route('/api/zenny')
def api_zenny():
    return jsonify(_collect())


def start_server(host: str = '0.0.0.0', port: int = 80):
    print(f'[web] starting on {host}:{port}', flush=True)
    try:
        app.run(host=host, port=port, threaded=True, use_reloader=False)
    except Exception as ex:
        print(f'[web] error: {ex}', flush=True)
