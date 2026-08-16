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
    # 분포 페이지 메인 데이터 = 누적 잔고 (cumulative_zenny + zenny)
    with members._conn() as c:
        rows_raw = c.execute(
            'SELECT user_id, nickname, COALESCE(cumulative_zenny, 0) + zenny FROM members'
        ).fetchall()
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

    # 시즌 정보 (현재 시즌 + 상위 10 + 역대 시즌 1·2·3등)
    from commands import season as _season
    cur_season = _season.get_current_season()
    season_top10 = []
    if cur_season:
        s_ranking = _season.get_season_ranking(active_uids=active_set)
        for e in s_ranking[:10]:
            season_top10.append({'rank': e['rank'], 'nick': e['nick'], 'score': e['score']})
    past_seasons = _season.get_past_season_medalists(limit=12)

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
        'season': {
            'title': cur_season['title'] if cur_season else '',
            'top10': season_top10,
        } if cur_season else None,
        'past_seasons': past_seasons,
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

  <div class="grid" id="season-wrap" style="display:none;">
    <div class="card full">
      <h3>🏆 <span id="season-title">이번 시즌</span> 랭킹 (상위 10)</h3>
      <div class="ranking-list" id="season-list" style="max-height:none;"></div>
    </div>
  </div>
  <div class="grid" id="past-wrap" style="display:none;">
    <div class="card full">
      <h3>🏅 역대 시즌 챔피언</h3>
      <div class="ranking-list" id="past-list" style="max-height:none;"></div>
    </div>
  </div>

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
  const _qs = location.search || '';

  document.querySelector('.subtitle').textContent =
    `몬헌 와일즈 카톡봇 · 활성 멤버 ${d.total_members}명 · 실시간 데이터 (새로고침으로 갱신)`;

  // 역대 시즌 챔피언
  if (d.past_seasons && d.past_seasons.length) {
    document.getElementById('past-wrap').style.display = '';
    const medalEmoji = r => r === 1 ? '🥇' : r === 2 ? '🥈' : r === 3 ? '🥉' : '';
    const rankCls = r => r === 1 ? 'gold' : r === 2 ? 'silver' : r === 3 ? 'bronze' : '';
    document.getElementById('past-list').innerHTML = d.past_seasons.map(s => {
      const medals = (s.medalists || []).map(m => `
        <span style="margin-right:14px;">
          <span class="${rankCls(m.rank)}">${medalEmoji(m.rank)}</span>
          ${m.nick} <span style="color:#888;font-size:11px;">(+${(m.score||0).toLocaleString('ko-KR')})</span>
        </span>`).join('');
      return `
        <div class="ranking-row" style="grid-template-columns:120px 1fr;">
          <div class="name" style="color:#ffd700;">${s.title}</div>
          <div class="name">${medals}</div>
        </div>`;
    }).join('');
  }

  // 시즌 랭킹
  if (d.season && d.season.top10 && d.season.top10.length) {
    document.getElementById('season-wrap').style.display = '';
    document.getElementById('season-title').textContent = d.season.title;
    const signed = v => (v >= 0 ? '+' : '') + v.toLocaleString('ko-KR');
    document.getElementById('season-list').innerHTML = d.season.top10.map(e => {
      let cls = '', icon = `${e.rank}`;
      if (e.rank === 1) { cls = 'gold'; icon = '🥇'; }
      else if (e.rank === 2) { cls = 'silver'; icon = '🥈'; }
      else if (e.rank === 3) { cls = 'bronze'; icon = '🥉'; }
      const href = `/u/${encodeURIComponent(e.nick)}${_qs}`;
      return `
        <a href="${href}" style="text-decoration:none;color:inherit;">
          <div class="ranking-row">
            <div class="rank ${cls}">${icon}</div>
            <div class="name">${e.nick}</div>
            <div class="zenny">${signed(e.score)}</div>
          </div>
        </a>`;
    }).join('');
  }

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

  // 랭킹 리스트 — 닉 클릭 시 멤버 페이지로 (현재 query string 그대로 전달, _qs 위에서 선언됨)
  document.getElementById('rankList').innerHTML = data.map((r, i) => {
    let rankClass = '', icon = `${i + 1}`;
    if (i === 0) { rankClass = 'gold'; icon = '🥇'; }
    else if (i === 1) { rankClass = 'silver'; icon = '🥈'; }
    else if (i === 2) { rankClass = 'bronze'; icon = '🥉'; }
    const href = `/u/${encodeURIComponent(r.nick)}${_qs}`;
    return `
      <a href="${href}" style="text-decoration:none;color:inherit;">
        <div class="ranking-row">
          <div class="rank ${rankClass}">${icon}</div>
          <div class="name">${r.nick}</div>
          <div class="zenny">${r.zenny.toLocaleString()} z</div>
        </div>
      </a>`;
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



def _collect_user(nick_query: str) -> Optional[dict]:
    """특정 닉네임의 멤버 프로필 데이터. 없으면 None."""
    import re as _re
    from collections import Counter, defaultdict

    full = _collect()
    if not full['ranking']:
        return None

    rank_idx = None
    target_nick = None
    for i, r in enumerate(full['ranking']):
        if r['nick'] == nick_query:
            rank_idx = i
            target_nick = r['nick']
            break
    if rank_idx is None:
        partials = [(i, r['nick']) for i, r in enumerate(full['ranking']) if nick_query in r['nick']]
        if len(partials) == 1:
            rank_idx, target_nick = partials[0]

    if rank_idx is None:
        return None

    target_uid = None
    for uid, n in _nicknames.all_mappings().items():
        if n == target_nick:
            target_uid = int(uid)
            break
    if target_uid is None:
        return None

    balance = full['ranking'][rank_idx]['zenny']  # 누적 잔고 (cumulative + zenny)

    # 시즌 잔고 별도 조회
    with members._conn() as c:
        row = c.execute(
            'SELECT zenny FROM members WHERE user_id = ?', (target_uid,)
        ).fetchone()
        season_balance = int(row[0]) if row else 0

    with members._conn() as c:
        events = c.execute(
            'SELECT ts, kind, bet, payout, delta, outcome, balance_after FROM zenny_events '
            'WHERE user_id=? ORDER BY ts',
            (target_uid,),
        ).fetchall()
        history = c.execute(
            'SELECT date, zenny FROM zenny_history WHERE user_id=? ORDER BY date',
            (target_uid,),
        ).fetchall()

    attend_count = sum(1 for e in events if e[1] == 'attend')
    roulette_count = sum(1 for e in events if e[1] == 'roulette')
    rps_count = sum(1 for e in events if e[1] == 'rps')
    jackpot_count = sum(1 for e in events if e[5] == 'jackpot')
    reset_count = sum(1 for e in events if e[5] == 'reset')

    roul_outcome = Counter(e[5] for e in events if e[1] == 'roulette')

    rps_user_hand = Counter()
    rps_bot_hand = Counter()
    rps_result = Counter()
    RPS_OUT_RE = _re.compile(r'^rps_(win|draw|lose)_(가위|바위|보)_vs_(가위|바위|보)$')
    for e in events:
        if e[1] != 'rps':
            continue
        m = RPS_OUT_RE.match(e[5] or '')
        if m:
            rps_result[m.group(1)] += 1
            rps_user_hand[m.group(2)] += 1
            rps_bot_hand[m.group(3)] += 1

    valid_delta = [e for e in events if e[4] is not None]
    if valid_delta:
        max_gain_e = max(valid_delta, key=lambda e: e[4])
        max_loss_e = min(valid_delta, key=lambda e: e[4])
    else:
        max_gain_e = max_loss_e = None

    def _ev_dict(e):
        if not e:
            return {'delta': 0, 'kind': '', 'outcome': '', 'ts': ''}
        return {'delta': e[4] or 0, 'kind': e[1], 'outcome': e[5] or '', 'ts': e[0] or ''}

    cur_win = cur_lose = max_win = max_lose = 0
    for e in events:
        if e[1] != 'roulette' or e[4] is None:
            continue
        if e[4] > 0:
            cur_win += 1
            cur_lose = 0
            if cur_win > max_win:
                max_win = cur_win
        elif e[4] < 0:
            cur_lose += 1
            cur_win = 0
            if cur_lose > max_lose:
                max_lose = cur_lose
        else:
            cur_win = cur_lose = 0

    bets = [e[2] for e in events if e[2] is not None and e[1] in ('roulette', 'rps')]
    payouts = [e[3] for e in events if e[3] is not None]
    avg_bet = round(sum(bets) / len(bets)) if bets else 0
    max_bet = max(bets) if bets else 0
    total_bet = sum(bets)
    total_payout = sum(payouts)

    # 도박 순손익 (출석 제외) — 룰렛 + 가위바위보 delta 합
    attend_sum = sum(e[4] for e in events if e[1] == 'attend' and e[4] is not None)
    roul_pnl = sum(e[4] for e in events if e[1] == 'roulette' and e[4] is not None)
    rps_pnl = sum(e[4] for e in events if e[1] == 'rps' and e[4] is not None)
    gambling_pnl = roul_pnl + rps_pnl

    daily = defaultdict(int)
    for e in events:
        if e[0] and e[4] is not None:
            day = e[0][:10]
            daily[day] += e[4]
    daily_sorted = sorted(daily.items())[-60:]

    history_series = [{'date': d, 'zenny': z} for d, z in history][-60:]

    return {
        'nick': target_nick,
        'balance': balance,            # 누적 잔고 (cumulative + zenny)
        'season_balance': season_balance,  # 시즌 잔고 (zenny)
        'rank': rank_idx + 1,
        'total_members': full['total_members'],
        'mean': full['mean'],
        'median': full['median'],
        'attend_count': attend_count,
        'roulette_count': roulette_count,
        'rps_count': rps_count,
        'jackpot_count': jackpot_count,
        'reset_count': reset_count,
        'roul_outcome': dict(roul_outcome),
        'rps_user_hand': dict(rps_user_hand),
        'rps_bot_hand': dict(rps_bot_hand),
        'rps_result': dict(rps_result),
        'max_gain': _ev_dict(max_gain_e),
        'max_loss': _ev_dict(max_loss_e),
        'max_win_streak': max_win,
        'max_lose_streak': max_lose,
        'avg_bet': avg_bet,
        'max_bet': max_bet,
        'total_bet': total_bet,
        'total_payout': total_payout,
        'attend_sum': attend_sum,
        'roul_pnl': roul_pnl,
        'rps_pnl': rps_pnl,
        'gambling_pnl': gambling_pnl,
        'history': history_series,
        'daily_events': [{'date': d, 'delta': v} for d, v in daily_sorted],
        'season': _season_user_stats(target_uid, events),
        'medals': _user_medals(target_uid),
    }


def _user_medals(user_id: int) -> list:
    from commands import season as _season
    return _season.get_user_medals(user_id)


def _season_user_stats(user_id: int, events: list) -> Optional[dict]:
    """현재 시즌 기준 멤버 통계 (점수·순위·시즌 이벤트 카운트)."""
    from commands import season as _season
    cur = _season.get_current_season()
    if not cur:
        return None
    score = _season.get_season_score(user_id)
    s_ranking = _season.get_season_ranking()
    rank = next((e['rank'] for e in s_ranking if e['user_id'] == user_id), None)
    start_ts = cur['start_ts']
    s_events = [e for e in events if e[0] and e[0] >= start_ts]
    return {
        'title': cur['title'],
        'score': score,
        'rank': rank,
        'attend_count': sum(1 for e in s_events if e[1] == 'attend'),
        'roulette_count': sum(1 for e in s_events if e[1] == 'roulette'),
        'rps_count': sum(1 for e in s_events if e[1] == 'rps'),
        'jackpot_count': sum(1 for e in s_events if e[5] == 'jackpot'),
        'reset_count': sum(1 for e in s_events if e[5] == 'reset'),
    }


USER_PAGE = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<title>__NICK__ — 프로필</title>
<meta property="og:title" content="__NICK__ — 멤버 프로필">
<meta property="og:description" content="몬헌 와일즈 카톡봇 멤버 통계">
<meta property="og:type" content="profile">
<meta property="og:locale" content="ko_KR">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: 'Segoe UI','Apple SD Gothic Neo',sans-serif;
         background: linear-gradient(135deg,#0f0c29,#302b63,#24243e);
         color:#fff; min-height:100vh; padding:30px; }
  .container { max-width:1200px; margin:0 auto; }
  .back { display:inline-block; color:#aaa; text-decoration:none; font-size:13px;
          margin-bottom:14px; padding:6px 12px; border:1px solid rgba(255,255,255,0.1);
          border-radius:6px; transition:all 0.2s; }
  .back:hover { background:rgba(255,255,255,0.05); color:#ffd700; }
  .header { background:rgba(255,255,255,0.05); backdrop-filter:blur(10px);
            border:1px solid rgba(255,255,255,0.1); border-radius:14px; padding:24px;
            margin-bottom:20px; display:flex; align-items:center; gap:24px; flex-wrap:wrap; }
  .header h1 { color:#ffd700; font-size:24px; text-shadow:0 0 16px rgba(255,215,0,0.4); }
  .header .sub { color:#aaa; font-size:13px; margin-top:6px; }
  .header .balance { margin-left:auto; text-align:right; }
  .header .balance .v { color:#00d4ff; font-size:28px; font-weight:bold; }
  .header .balance .s { color:#888; font-size:12px; }
  .summary { display:grid; grid-template-columns:repeat(5,1fr); gap:12px; margin-bottom:20px; }
  .stat-card { background:rgba(255,255,255,0.05); backdrop-filter:blur(10px);
               border:1px solid rgba(255,255,255,0.1); border-radius:10px;
               padding:14px; text-align:center; }
  .stat-card .label { color:#aaa; font-size:11px; margin-bottom:4px; }
  .stat-card .value { color:#ffd700; font-size:20px; font-weight:bold; }
  .grid { display:grid; grid-template-columns:1fr 1fr; gap:20px; margin-bottom:20px; }
  .card { background:rgba(255,255,255,0.05); backdrop-filter:blur(10px);
          border:1px solid rgba(255,255,255,0.1); border-radius:12px; padding:20px; }
  .card.full { grid-column:1/-1; }
  .card h3 { color:#ffd700; font-size:15px; margin-bottom:14px; }
  .chart-wrap { position:relative; height:280px; }
  .events { display:grid; grid-template-columns:repeat(4,1fr); gap:12px; }
  .ev { background:rgba(255,255,255,0.03); padding:12px; border-radius:8px; }
  .ev .l { color:#aaa; font-size:11px; }
  .ev .v { font-size:18px; font-weight:bold; margin-top:4px; }
  .ev .s { color:#666; font-size:11px; margin-top:2px; }
  .green { color:#44dd88; }
  .red { color:#ff6688; }
  .gold { color:#ffd700; }
  .silver { color:#c0c0c0; }
  .bronze { color:#cd7f32; }
  ::-webkit-scrollbar { width:6px; }
  ::-webkit-scrollbar-track { background:rgba(255,255,255,0.05); }
  ::-webkit-scrollbar-thumb { background:#ffd700; border-radius:3px; }
  @media(max-width:768px){ .summary{grid-template-columns:repeat(2,1fr);} .grid{grid-template-columns:1fr;} .events{grid-template-columns:repeat(2,1fr);} }
</style>
</head>
<body>
<div class="container">
  <a class="back" href="/?key=__KEY__">← 분포 페이지로</a>
  <div class="header">
    <div>
      <h1>__NICK__</h1>
      <div class="sub" id="rank-sub">-</div>
    </div>
    <div class="balance">
      <div class="v" id="balance">-</div>
      <div class="s">📊 누적 잔고 · 🎰 시즌 <span id="season-balance">-</span></div>
    </div>
  </div>
  <div class="summary" id="summary"></div>
  <div class="grid" id="season-wrap" style="display:none;">
    <div class="card full">
      <h3>🏆 <span id="season-title">시즌</span> 통계</h3>
      <div class="events" id="season-stats"></div>
    </div>
  </div>
  <div class="grid" id="medals-wrap" style="display:none;">
    <div class="card full">
      <h3>🏅 시즌 우승 기록</h3>
      <div class="events" id="medals-list"></div>
    </div>
  </div>
  <div class="grid">
    <div class="card full">
      <h3>📈 잔고 추이 (최근 60일)</h3>
      <div class="chart-wrap"><canvas id="historyChart"></canvas></div>
    </div>
  </div>
  <div class="grid">
    <div class="card"><h3>🎰 룰렛 결과 분포</h3><div class="chart-wrap"><canvas id="roulChart"></canvas></div></div>
    <div class="card"><h3>✌️ 가위바위보 손 패턴</h3><div class="chart-wrap"><canvas id="rpsChart"></canvas></div></div>
  </div>
  <div class="grid">
    <div class="card full">
      <h3>🔥 큰 사건</h3>
      <div class="events" id="big-events"></div>
    </div>
  </div>
  <div class="grid">
    <div class="card full">
      <h3>💰 베팅 패턴</h3>
      <div class="events" id="bet-pattern"></div>
    </div>
  </div>
  <div class="grid">
    <div class="card full">
      <h3>🎲 도박 순손익 (출석 제외)</h3>
      <div class="events" id="gambling"></div>
    </div>
  </div>
  <div class="grid">
    <div class="card full">
      <h3>📊 일별 손익 (양수=초록, 음수=빨강)</h3>
      <div class="chart-wrap"><canvas id="dailyChart"></canvas></div>
    </div>
  </div>
</div>
<script>
const fmt = n => (n||0).toLocaleString('ko-KR');
const signed = n => (n>0?'+':'')+fmt(n);
fetch('/api/user/__NICK_ENCODED__?key=__KEY__').then(r => r.json()).then(d => {
  if (d.error) { document.querySelector('.container').innerHTML = '<div class="card" style="text-align:center;padding:50px;">'+d.error+'</div>'; return; }
  document.getElementById('balance').textContent = fmt(d.balance);
  document.getElementById('season-balance').textContent = fmt(d.season_balance ?? 0);
  document.getElementById('rank-sub').textContent =
    `전체 ${d.rank}위 / ${d.total_members}명 · 평균 ${fmt(d.mean)} · 중앙값 ${fmt(d.median)}`;

  document.getElementById('summary').innerHTML = `
    <div class="stat-card"><div class="label">출석</div><div class="value">${d.attend_count}일</div></div>
    <div class="stat-card"><div class="label">룰렛</div><div class="value">${d.roulette_count}회</div></div>
    <div class="stat-card"><div class="label">가위바위보</div><div class="value">${d.rps_count}회</div></div>
    <div class="stat-card"><div class="label">잭팟 🎰</div><div class="value gold">${d.jackpot_count}</div></div>
    <div class="stat-card"><div class="label">초기화 💸</div><div class="value red">${d.reset_count}</div></div>
  `;

  // 옛 시즌 메달
  if (d.medals && d.medals.length) {
    document.getElementById('medals-wrap').style.display = '';
    const medalEmoji = r => r === 1 ? '🥇' : r === 2 ? '🥈' : r === 3 ? '🥉' : '';
    const rankCls = r => r === 1 ? 'gold' : r === 2 ? 'silver' : r === 3 ? 'bronze' : '';
    document.getElementById('medals-list').innerHTML = d.medals.map(m => `
      <div class="ev">
        <div class="l">${m.title}</div>
        <div class="v ${rankCls(m.rank)}">${medalEmoji(m.rank)} ${m.rank}위</div>
        <div class="s">+${fmt(m.score)}</div>
      </div>`).join('');
  }

  // 시즌 통계
  if (d.season) {
    document.getElementById('season-wrap').style.display = '';
    document.getElementById('season-title').textContent = d.season.title;
    const s = d.season;
    const rankLabel = s.rank ? `전체 ${s.rank}위` : '집계 외';
    document.getElementById('season-stats').innerHTML = `
      <div class="ev"><div class="l">시즌 점수</div><div class="v gold">${signed(s.score)}</div><div class="s">${rankLabel}</div></div>
      <div class="ev"><div class="l">시즌 출석</div><div class="v">${s.attend_count}일</div></div>
      <div class="ev"><div class="l">시즌 룰렛 / RPS</div><div class="v">${s.roulette_count} / ${s.rps_count}</div></div>
      <div class="ev"><div class="l">시즌 잭팟 / 초기화</div><div class="v"><span class="gold">${s.jackpot_count}</span> / <span class="red">${s.reset_count}</span></div></div>
    `;
  }

  // 60일 잔고 추이
  new Chart(document.getElementById('historyChart'), {
    type:'line',
    data:{ labels:d.history.map(h=>h.date.slice(5)),
           datasets:[{ data:d.history.map(h=>h.zenny), borderColor:'#ffd700',
             backgroundColor:'rgba(255,215,0,0.15)', fill:true, tension:0.25,
             pointRadius:2, pointHoverRadius:5 }] },
    options:{ responsive:true, maintainAspectRatio:false, plugins:{ legend:{display:false} },
      scales:{ y:{ ticks:{color:'#aaa'}, grid:{color:'rgba(255,255,255,0.05)'} },
               x:{ ticks:{color:'#aaa', maxRotation:60}, grid:{display:false} } } }
  });

  // 룰렛 outcome 분포
  const roul_order = ['reset','r-70','r-50','r-20','r+0','r+25','r+60','r+80','r+120','jackpot'];
  const roul_label = {reset:'초기화','r-70':'-70%','r-50':'-50%','r-20':'-20%','r+0':'본전','r+25':'+25%','r+60':'+60%','r+80':'+80%','r+120':'+120%',jackpot:'잭팟'};
  const roul_color = {reset:'#ff4466','r-70':'#ff6688','r-50':'#ff8844','r-20':'#ffcc44','r+0':'#888','r+25':'#88dd44','r+60':'#44dd88','r+80':'#44cccc','r+120':'#00d4ff',jackpot:'#ffd700'};
  const roul_data = roul_order.map(k => d.roul_outcome[k] || 0);
  const roul_present = roul_order.map((k,i)=>roul_data[i]>0?k:null).filter(Boolean);
  new Chart(document.getElementById('roulChart'), {
    type:'doughnut',
    data:{ labels:roul_present.map(k=>roul_label[k]),
           datasets:[{ data:roul_present.map(k=>d.roul_outcome[k]),
             backgroundColor:roul_present.map(k=>roul_color[k]),
             borderColor:'rgba(0,0,0,0.3)', borderWidth:2 }] },
    options:{ responsive:true, maintainAspectRatio:false,
      plugins:{ legend:{ position:'right', labels:{color:'#fff', font:{size:11}} } } }
  });

  // 가위바위보 — 본인 손
  const hands = ['가위','바위','보'];
  const total_rps = (d.rps_user_hand['가위']||0)+(d.rps_user_hand['바위']||0)+(d.rps_user_hand['보']||0);
  new Chart(document.getElementById('rpsChart'), {
    type:'bar',
    data:{ labels:['본인 손','봇 손'],
           datasets: hands.map((h,i) => ({
             label:h, data:[d.rps_user_hand[h]||0, d.rps_bot_hand[h]||0],
             backgroundColor:['#ff6688','#ffcc44','#44dd88'][i], borderRadius:6
           })) },
    options:{ responsive:true, maintainAspectRatio:false,
      plugins:{ legend:{ labels:{color:'#fff'} },
        title:{ display:true, color:'#aaa', text: total_rps===0 ? '아직 가위바위보 기록 없음' : `승/무/패: ${d.rps_result.win||0}·${d.rps_result.draw||0}·${d.rps_result.lose||0} (총 ${total_rps})` } },
      scales:{ y:{beginAtZero:true, ticks:{color:'#aaa',precision:0}, grid:{color:'rgba(255,255,255,0.05)'}},
               x:{ticks:{color:'#aaa'}, grid:{display:false}} } }
  });

  // 큰 사건
  const fmt_outcome = (kind, oc) => {
    if (oc==='jackpot') return '🎰 잭팟';
    if (oc==='reset') return '💸 초기화';
    if (oc==='attend' || oc==='attend_bonus') return '🎯 출석';
    if (oc && oc.startsWith('r')) return '🎰 룰렛 '+oc.slice(1);
    if (oc && oc.startsWith('rps_')) {
      const p = oc.split('_');
      return '✌️ '+(p[1]==='win'?'승':p[1]==='draw'?'무':'패');
    }
    return oc || '';
  };
  document.getElementById('big-events').innerHTML = `
    <div class="ev"><div class="l">📈 최대 이득</div><div class="v green">${signed(d.max_gain.delta)}</div><div class="s">${fmt_outcome(d.max_gain.kind,d.max_gain.outcome)} · ${d.max_gain.ts.slice(0,10)}</div></div>
    <div class="ev"><div class="l">📉 최대 손실</div><div class="v red">${signed(d.max_loss.delta)}</div><div class="s">${fmt_outcome(d.max_loss.kind,d.max_loss.outcome)} · ${d.max_loss.ts.slice(0,10)}</div></div>
    <div class="ev"><div class="l">🔥 최장 연승</div><div class="v gold">${d.max_win_streak}회</div><div class="s">룰렛 양수 연속</div></div>
    <div class="ev"><div class="l">🧊 최장 연패</div><div class="v red">${d.max_lose_streak}회</div><div class="s">룰렛 음수 연속</div></div>
  `;

  // 베팅 패턴
  document.getElementById('bet-pattern').innerHTML = `
    <div class="ev"><div class="l">평균 베팅</div><div class="v">${fmt(d.avg_bet)}</div><div class="s">룰렛+가위바위보</div></div>
    <div class="ev"><div class="l">최대 베팅</div><div class="v">${fmt(d.max_bet)}</div></div>
    <div class="ev"><div class="l">누적 베팅</div><div class="v red">${fmt(d.total_bet)}</div></div>
    <div class="ev"><div class="l">누적 환급</div><div class="v green">${fmt(d.total_payout)}</div></div>
  `;

  // 도박 순손익 (출석 제외)
  const pnlCls = v => v>=0 ? 'green' : 'red';
  document.getElementById('gambling').innerHTML = `
    <div class="ev"><div class="l">🎲 도박 순손익</div><div class="v ${pnlCls(d.gambling_pnl)}">${signed(d.gambling_pnl)}</div><div class="s">룰렛+가위바위보 delta 합</div></div>
    <div class="ev"><div class="l">🎯 출석 누적</div><div class="v green">+${fmt(d.attend_sum)}</div><div class="s">${d.attend_count}일</div></div>
    <div class="ev"><div class="l">🎰 룰렛 손익</div><div class="v ${pnlCls(d.roul_pnl)}">${signed(d.roul_pnl)}</div></div>
    <div class="ev"><div class="l">✌️ 가위바위보 손익</div><div class="v ${pnlCls(d.rps_pnl)}">${signed(d.rps_pnl)}</div></div>
  `;

  // 일별 손익 막대
  new Chart(document.getElementById('dailyChart'), {
    type:'bar',
    data:{ labels:d.daily_events.map(e=>e.date.slice(5)),
           datasets:[{ data:d.daily_events.map(e=>e.delta),
             backgroundColor: d.daily_events.map(e=>e.delta>=0?'#44dd88':'#ff6688'),
             borderRadius:3 }] },
    options:{ responsive:true, maintainAspectRatio:false,
      plugins:{ legend:{display:false} },
      scales:{ y:{ ticks:{color:'#aaa'}, grid:{color:'rgba(255,255,255,0.05)'} },
               x:{ ticks:{color:'#aaa', maxRotation:60, font:{size:9}}, grid:{display:false} } } }
  });
});
</script>
</body></html>
"""


@app.route('/u/<path:nick>')
def user_page(nick):
    key = request.args.get('key', '')
    wk = _current_key()
    if wk and key != wk:
        return GATE_PAGE
    import urllib.parse
    safe_nick = urllib.parse.quote(nick, safe='')
    return (USER_PAGE
            .replace('__NICK_ENCODED__', safe_nick)
            .replace('__NICK__', nick)
            .replace('__KEY__', key))


@app.route('/api/user/<path:nick>')
def api_user(nick):
    if not _key_ok():
        return jsonify({'error': 'unauthorized'}), 403
    data = _collect_user(nick)
    if data is None:
        return jsonify({'error': f'멤버를 찾을 수 없어요: {nick}'}), 404
    return jsonify(data)



def start_server(host: str = '0.0.0.0', port: int = 80):
    print(f'[web] starting on {host}:{port}', flush=True)
    try:
        app.run(host=host, port=port, threaded=True, use_reloader=False)
    except Exception as ex:
        print(f'[web] error: {ex}', flush=True)
