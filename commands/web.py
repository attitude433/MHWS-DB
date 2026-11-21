"""다이애나 도메인(mhws.diana.ai.kr) 웹 서버 — 제니 현황 페이지 + 멤버 프로필.

봇 프로세스 백그라운드 스레드로 기동. duel_web 이 같은 app 에 /duel 라우트를 붙인다.

데이터 기준
- 잔고: 누적(cumulative_zenny + zenny). 시즌 잔고는 members.zenny.
- 흐름·추이: zenny_events (출석/룰렛/가위바위보/승부 전부 기록됨).
  zenny_history 는 시즌 잔고라 매월 1일 0 으로 떨어져서 추이 계산에 쓰지 않는다.
- zenny_events.ts 는 서버 시간(UTC) naive ISO → 날짜는 KST 로 바꿔서 묶는다.
"""
from __future__ import annotations
import html as _html
import json as _json
import os
import statistics
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional

from flask import Flask, jsonify, request
import logging

import members
import nicknames as _nicknames
from commands.zenny import EXCLUDED_USER_IDS

IRIS_QUERY_URL = 'http://127.0.0.1:3000/query'
SNS_ROOM_ID = os.environ.get('SNS_ROOM_ID', '')
KST = timezone(timedelta(hours=9))
TREND_DAYS = 90


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


def _kst_day(ts: str) -> str:
    """zenny_events.ts (UTC naive) → KST 날짜 'YYYY-MM-DD'."""
    try:
        return (datetime.fromisoformat(ts) + timedelta(hours=9)).strftime('%Y-%m-%d')
    except Exception:
        return (ts or '')[:10]


def _kst_ts(ts: str) -> str:
    """UTC naive ts → KST naive ISO (시즌 start_ts 와 비교용)."""
    try:
        return (datetime.fromisoformat(ts) + timedelta(hours=9)).isoformat(timespec='seconds')
    except Exception:
        return ts or ''


def _balance_series(deltas_by_day: dict, end_balance: int, days: int) -> list:
    """일별 delta 합 → 최근 days 일 잔고 시리즈. 마지막 값을 실제 잔고에 맞춘다.

    (이벤트 기록이 빠진 운영자 조정 등이 있어도 현재 값은 정확하게)
    """
    today = datetime.now(KST).date()
    start = today - timedelta(days=days - 1)
    # start 이후 delta 합을 빼면 start 전날 잔고
    after = sum(v for d, v in deltas_by_day.items() if d >= start.isoformat())
    bal = end_balance - after
    out = []
    for i in range(days):
        day = (start + timedelta(days=i)).isoformat()
        bal += deltas_by_day.get(day, 0)
        out.append({'date': day, 'total': bal})
    # 기록 시작 전 구간(전부 0)은 잘라냄
    while len(out) > 1 and out[0]['total'] == 0 and out[1]['total'] == 0:
        out.pop(0)
    return out


# 잔고 구간 (라벨, 하한, 상한) — 상위권이 수십만~백만대라 위쪽을 넓게
BUCKETS = [
    ('0',            0,         0),
    ('1–100',        1,         100),
    ('101–1천',      101,       1_000),
    ('1천–1만',      1_001,     10_000),
    ('1만–10만',     10_001,    100_000),
    ('10만+',        100_001,   float('inf')),
]


def _season_meta(cur: Optional[dict]) -> Optional[dict]:
    if not cur:
        return None
    now = datetime.now(KST)
    nxt = (now.replace(day=1) + timedelta(days=32)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    left = nxt - now
    return {
        'title': cur['title'],
        'start': cur['start_ts'][:10],
        'end': (nxt - timedelta(days=1)).strftime('%Y-%m-%d'),
        'days_left': left.days,
        'hours_left': left.seconds // 3600,
    }


def _collect() -> dict:
    with members._conn() as c:
        rows_raw = c.execute(
            'SELECT user_id, COALESCE(cumulative_zenny, 0) + zenny, zenny FROM members'
        ).fetchall()
        events_raw = c.execute(
            'SELECT user_id, ts, kind, delta, outcome FROM zenny_events ORDER BY ts'
        ).fetchall()
    # 카톡방 현재 활성 멤버 (Iris). 실패 시 None → 필터 비활성 (안전 fallback)
    active_set = _get_active_members()
    rows = []
    nick_map = {}
    for uid, z, sz in rows_raw:
        if uid in EXCLUDED_USER_IDS:
            continue
        mapped = _nicknames.get(uid)
        if not mapped:
            continue
        if active_set is not None and uid not in active_set:
            continue  # 카톡방에서 나간 멤버 제외
        rows.append((uid, mapped, z, sz))
        nick_map[uid] = mapped

    from commands import season as _season
    cur_season = _season.get_current_season()
    season_info = _season_meta(cur_season)
    past_seasons = _season.get_past_season_medalists(limit=12)

    if not rows:
        return {
            'updated': datetime.now(KST).strftime('%Y-%m-%d %H:%M'),
            'total_members': 0, 'total_zenny': 0, 'mean': 0, 'median': 0,
            'top5_sum': 0, 'top5_pct': 0, 'holders': 0,
            'buckets': [{'label': l, 'count': 0} for l, _, _ in BUCKETS],
            'ranking': [], 'pump': 0, 'drain': 0, 'net': 0,
            'max_gain': {'delta': 0, 'nick': '', 'date': '', 'outcome': ''},
            'max_loss': {'delta': 0, 'nick': '', 'date': '', 'outcome': ''},
            'zero_drops': 0, 'jackpots': 0, 'history': [],
            'season': None, 'past_seasons': past_seasons,
        }

    zennies = [z for _, _, z, _ in rows]
    rows_sorted = sorted(rows, key=lambda r: (-r[2], r[1]))
    top5_sum = sum(z for _, _, z, _ in rows_sorted[:5])
    total = sum(zennies)
    top5_pct = round(top5_sum / total * 100, 1) if total > 0 else 0

    bucket_counts = [0] * len(BUCKETS)
    for z in zennies:
        for i, (_, lo, hi) in enumerate(BUCKETS):
            if lo <= z <= hi:
                bucket_counts[i] += 1
                break

    # 흐름 — 이벤트 기준 (시즌 리셋에 영향 안 받음)
    pump = drain = resets = jackpots = 0
    max_gain = {'delta': 0, 'nick': '', 'date': '', 'outcome': ''}
    max_loss = {'delta': 0, 'nick': '', 'date': '', 'outcome': ''}
    by_day: dict = defaultdict(int)
    by_kind: dict = defaultdict(int)
    for uid, ts, kind, delta, outcome in events_raw:
        if uid not in nick_map or delta is None:
            continue
        day = _kst_day(ts)
        by_day[day] += delta
        by_kind[kind] += delta
        if delta > 0:
            pump += delta
            if delta > max_gain['delta']:
                max_gain = {'delta': delta, 'nick': nick_map[uid], 'date': day, 'outcome': outcome}
        elif delta < 0:
            drain += -delta
            if delta < max_loss['delta']:
                max_loss = {'delta': delta, 'nick': nick_map[uid], 'date': day, 'outcome': outcome}
        if outcome == 'reset':
            resets += 1
        elif outcome == 'jackpot':
            jackpots += 1

    # 시즌 상위 10
    season = None
    if cur_season:
        s_ranking = _season.get_season_ranking(active_uids=active_set)
        season = dict(season_info)
        season['top10'] = [{'rank': e['rank'], 'nick': e['nick'], 'score': e['score']}
                           for e in s_ranking[:10]]
        season['players'] = len(s_ranking)

    return {
        'updated': datetime.now(KST).strftime('%Y-%m-%d %H:%M'),
        'total_members': len(rows),
        'holders': sum(1 for z in zennies if z > 0),
        'total_zenny': total,
        'mean': round(statistics.mean(zennies)),
        'median': int(statistics.median(zennies)),
        'top5_sum': top5_sum,
        'top5_pct': top5_pct,
        'buckets': [{'label': l, 'count': c} for (l, _, _), c in zip(BUCKETS, bucket_counts)],
        'ranking': [{'nick': nick, 'zenny': z, 'season': sz} for _, nick, z, sz in rows_sorted],
        'pump': pump,
        'drain': drain,
        'net': pump - drain,
        'by_kind': dict(by_kind),
        'max_gain': max_gain,
        'max_loss': max_loss,
        'zero_drops': resets,        # 이름은 호환용 — 룰렛 초기화 횟수
        'jackpots': jackpots,
        'history': _balance_series(by_day, total, TREND_DAYS),
        'season': season,
        'past_seasons': past_seasons,
    }


# ─────────────────────────────────────────────────────────────
# 공통 스타일 / 스크립트
# ─────────────────────────────────────────────────────────────

BASE_CSS = """
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css">
<style>
:root{
  color-scheme:light;
  --bg:#f4f3ef; --surface:#fcfcfb; --line:#e3e1db; --line-strong:#cfccc4;
  --ink:#141413; --ink-2:#52514e; --ink-3:#8a8882;
  --s1:#2a78d6; --s2:#eb6834; --zero:#b9b7b0;
  --gold:#a8790a; --silver:#7d7f84; --bronze:#9a5b2c;
}
@media (prefers-color-scheme:dark){:root{
  color-scheme:dark;
  --bg:#121211; --surface:#1a1a19; --line:#2b2b29; --line-strong:#3a3a37;
  --ink:#f0efec; --ink-2:#c3c2b7; --ink-3:#8c8b84;
  --s1:#3987e5; --s2:#d95926; --zero:#5a5955;
  --gold:#d9ad3c; --silver:#b4b6bb; --bronze:#c98552;
}}
*{box-sizing:border-box;margin:0;padding:0}
[hidden]{display:none!important}
html{-webkit-text-size-adjust:100%}
body{background:var(--bg);color:var(--ink);font:15px/1.55 'Pretendard Variable',Pretendard,-apple-system,'Apple SD Gothic Neo','Malgun Gothic',sans-serif;
  font-feature-settings:'tnum';-webkit-font-smoothing:antialiased;padding:40px 20px 80px}
a{color:inherit}
.wrap{max-width:1040px;margin:0 auto}
.kicker{font-size:13px;color:var(--ink-3);letter-spacing:.02em}
h1{font-size:30px;font-weight:700;letter-spacing:-.02em;margin-top:2px}
.meta{font-size:13px;color:var(--ink-3);margin-top:6px}
header.top{display:flex;align-items:flex-end;justify-content:space-between;gap:16px;flex-wrap:wrap;
  padding-bottom:20px;border-bottom:1px solid var(--line-strong);margin-bottom:28px}
section{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:22px 24px;margin-bottom:16px}
section > h2{font-size:15px;font-weight:650;margin-bottom:4px}
section > .desc{font-size:13px;color:var(--ink-3);margin-bottom:16px}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.cols > section{margin-bottom:0}
.cols{margin-bottom:16px}
.stats{display:grid;grid-template-columns:repeat(4,1fr);border:1px solid var(--line);border-radius:10px;
  background:var(--surface);margin-bottom:16px;overflow:hidden}
.stat{padding:18px 20px;border-left:1px solid var(--line)}
.stat:first-child{border-left:0}
.stat .l{font-size:12.5px;color:var(--ink-2)}
.stat .v{font-size:24px;font-weight:700;letter-spacing:-.02em;margin-top:2px}
.stat .s{font-size:12px;color:var(--ink-3);margin-top:2px}
.chart{position:relative;height:280px}
.chart.short{height:240px}
table{width:100%;border-collapse:collapse;font-size:14px}
th{font-weight:500;font-size:12.5px;color:var(--ink-3);text-align:left;padding:0 8px 8px;border-bottom:1px solid var(--line-strong)}
td{padding:9px 8px;border-bottom:1px solid var(--line)}
tr:last-child td{border-bottom:0}
th.num,td.num{text-align:right}
td.rank{width:44px;color:var(--ink-3)}
td.rank.r1{color:var(--gold);font-weight:700}
td.rank.r2{color:var(--silver);font-weight:700}
td.rank.r3{color:var(--bronze);font-weight:700}
td a{text-decoration:none}
td a:hover{text-decoration:underline;text-underline-offset:3px}
.muted{color:var(--ink-3)}
.pos{color:var(--s1)} .neg{color:var(--s2)}
.kv{display:grid;grid-template-columns:1fr auto;row-gap:0}
.kv > div{padding:9px 0;border-bottom:1px solid var(--line);font-size:14px}
.kv > div:nth-last-child(-n+2){border-bottom:0}
.kv .k{color:var(--ink-2)} .kv .k small{display:block;color:var(--ink-3);font-size:12px}
.kv .v{text-align:right;font-weight:600}
.search{font:inherit;font-size:14px;width:220px;padding:7px 10px;border:1px solid var(--line-strong);border-radius:7px;
  background:var(--bg);color:var(--ink)}
.search:focus{outline:2px solid var(--s1);outline-offset:-1px}
.sec-head{display:flex;justify-content:space-between;align-items:flex-start;gap:12px;flex-wrap:wrap;margin-bottom:12px}
.sec-head h2{font-size:15px;font-weight:650}
.sec-head .desc{font-size:13px;color:var(--ink-3);margin-top:2px}
.scroll{max-height:560px;overflow-y:auto}
.scroll thead th{position:sticky;top:0;background:var(--surface)}
.pill{display:inline-block;font-size:12px;padding:1px 8px;border:1px solid var(--line-strong);border-radius:99px;color:var(--ink-2)}
.legend{display:flex;gap:14px;font-size:12.5px;color:var(--ink-2);margin:-6px 0 10px}
.legend i{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:5px;vertical-align:-1px}
footer{font-size:12px;color:var(--ink-3);margin-top:28px;text-align:center}
@media(max-width:760px){
  body{padding:24px 14px 60px}
  h1{font-size:25px}
  .cols{grid-template-columns:1fr}
  .stats{grid-template-columns:1fr 1fr}
  .stat:nth-child(3){border-left:0}
  .stat:nth-child(n+3){border-top:1px solid var(--line)}
  section{padding:18px 16px}
  .search{width:100%}
}
</style>
"""

COMMON_JS = r"""
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<script>
const $ = id => document.getElementById(id);
const esc = t => String(t ?? '').replace(/[&<>"']/g, c => '&#' + c.charCodeAt(0) + ';');
const fmt = n => (n || 0).toLocaleString('ko-KR');
const signed = n => (n > 0 ? '+' : '') + fmt(n);
const css = v => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const short = n => {
  const a = Math.abs(n);
  if (a >= 1e8) return (n / 1e8).toFixed(1).replace(/\.0$/, '') + '억';
  if (a >= 1e4) return (n / 1e4).toFixed(a >= 1e5 ? 0 : 1).replace(/\.0$/, '') + '만';
  return fmt(n);
};
const md = s => { const p = (s || '').split('-'); return p.length === 3 ? `${+p[1]}.${+p[2]}` : s; };
const OUTCOME = oc => {
  if (!oc) return '';
  if (oc === 'jackpot') return '룰렛 잭팟';
  if (oc === 'reset') return '룰렛 초기화';
  if (oc === 'attend') return '출석';
  if (oc === 'attend_lucky') return '출석 (행운 순번)';
  if (oc === 'attend_bonus') return '출석 (보너스)';
  if (oc === 'duel_win') return '승부 승리';
  if (oc === 'duel_lose') return '승부 패배';
  if (oc.startsWith('rps_')) { const p = oc.split('_'); return '가위바위보 ' + (p[1] === 'win' ? '승' : p[1] === 'draw' ? '무' : '패'); }
  if (/^r[+-]\d+$/.test(oc)) return '룰렛 ' + (oc === 'r+0' ? '본전' : oc.slice(1) + '%');
  return oc;
};
function chartBase() {
  Chart.defaults.font.family = "'Pretendard Variable', Pretendard, -apple-system, sans-serif";
  Chart.defaults.font.size = 12;
  Chart.defaults.color = css('--ink-3');
  Chart.defaults.borderColor = css('--line');
  Chart.defaults.plugins.legend.display = false;
  Chart.defaults.plugins.tooltip.backgroundColor = css('--ink');
  Chart.defaults.plugins.tooltip.titleColor = css('--surface');
  Chart.defaults.plugins.tooltip.bodyColor = css('--surface');
  Chart.defaults.plugins.tooltip.padding = 10;
  Chart.defaults.plugins.tooltip.cornerRadius = 6;
  Chart.defaults.plugins.tooltip.displayColors = false;
  Chart.defaults.maintainAspectRatio = false;
}
// 축 눈금: 만 단위로 줄이되 눈금끼리 같은 글자가 안 나오게 소수점 자릿수를 눈금 간격에 맞춤
const tickLabel = (v, i, ticks) => {
  const step = ticks.length > 1 ? Math.abs(ticks[1].value - ticks[0].value) : Math.abs(v);
  if (Math.abs(v) < 1e4 || step < 1) return fmt(v);
  const dec = step >= 1e4 ? 0 : step >= 1e3 ? 1 : 2;
  return (v / 1e4).toFixed(dec) + '만';
};
const yAxis = (extra = {}) => ({ border: { display: false }, grid: { color: css('--line') },
  ticks: { callback: tickLabel, maxTicksLimit: 5 }, ...extra });
const xAxis = (extra = {}) => ({ border: { color: css('--line-strong') }, grid: { display: false },
  ticks: { maxRotation: 0, autoSkipPadding: 14 }, ...extra });
</script>
"""

GATE_PAGE = """<!DOCTYPE html>
<html lang="ko"><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>제니 현황</title>
<meta property="og:title" content="제니 현황">
<meta property="og:description" content="몬헌 와일즈 카톡방 제니 분포·시즌 순위">
<meta property="og:type" content="website">
<meta property="og:url" content="http://mhws.diana.ai.kr">
<meta property="og:site_name" content="다이애나">
<meta property="og:locale" content="ko_KR">
""" + BASE_CSS + """
<style>body{display:flex;align-items:center;justify-content:center;min-height:100vh;padding:20px}
.box{max-width:400px}.box p{color:var(--ink-2);margin-top:12px;font-size:14.5px}
code{font:inherit;font-weight:600;color:var(--ink);background:var(--surface);border:1px solid var(--line);padding:1px 7px;border-radius:5px}</style>
</head><body>
<div class="box">
  <div class="kicker">몬헌 와일즈 카톡방</div>
  <h1>제니 현황</h1>
  <p>방 멤버만 볼 수 있는 페이지예요. 카톡방에서 <code>.제니분포</code>를 입력하면 다이애나가 링크를 보내줘요.</p>
</div>
</body></html>
"""


PAGE = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>제니 현황</title>
<meta name="description" content="몬헌 와일즈 카톡방 제니 분포·시즌 순위·전체 랭킹">
<meta property="og:title" content="제니 현황">
<meta property="og:description" content="몬헌 와일즈 카톡방 제니 분포·시즌 순위">
<meta property="og:type" content="website">
<meta property="og:url" content="http://mhws.diana.ai.kr">
<meta property="og:site_name" content="다이애나">
<meta property="og:locale" content="ko_KR">
<meta name="twitter:card" content="summary">
""" + BASE_CSS + COMMON_JS + """
</head>
<body>
<div class="wrap">
  <header class="top">
    <div>
      <div class="kicker">몬헌 와일즈 카톡방</div>
      <h1>제니 현황</h1>
      <div class="meta" id="meta">불러오는 중…</div>
    </div>
  </header>

  <section id="season-sec" hidden>
    <div class="sec-head">
      <div><h2 id="season-title">이번 시즌</h2><div class="desc" id="season-desc"></div></div>
      <span class="pill" id="season-left"></span>
    </div>
    <table><thead><tr><th>순위</th><th>닉네임</th><th class="num">시즌 잔고</th></tr></thead>
      <tbody id="season-body"></tbody></table>
  </section>

  <div class="stats" id="stats"></div>

  <section>
    <h2>방 전체 제니</h2>
    <div class="desc">지금 방에 있는 멤버들의 누적 잔고 합계, 최근 90일</div>
    <div class="chart"><canvas id="trend"></canvas></div>
  </section>

  <div class="cols">
    <section>
      <h2>잔고 구간별 인원</h2>
      <div class="desc" id="bucket-desc"></div>
      <div class="chart short"><canvas id="buckets"></canvas></div>
    </section>
    <section>
      <h2>들어오고 나간 제니</h2>
      <div class="desc">봇 기록 시작 후 전체 기간</div>
      <div class="kv" id="flow"></div>
    </section>
  </div>

  <section id="past-sec" hidden>
    <h2>지난 시즌 1·2·3위</h2>
    <div class="desc">시즌은 매달 1일 0시에 바뀌고, 시즌 잔고는 누적으로 넘어가요</div>
    <table><thead><tr><th>시즌</th><th>1위</th><th>2위</th><th>3위</th></tr></thead>
      <tbody id="past-body"></tbody></table>
  </section>

  <section>
    <div class="sec-head">
      <div><h2>전체 순위</h2><div class="desc">누적 잔고순 · 닉네임을 누르면 개인 기록</div></div>
      <input class="search" id="q" placeholder="닉네임 검색" autocomplete="off">
    </div>
    <div class="scroll">
      <table><thead><tr><th>순위</th><th>닉네임</th><th class="num">누적</th><th class="num">이번 시즌</th></tr></thead>
        <tbody id="rank-body"></tbody></table>
    </div>
  </section>

  <footer>.출석 · .룰렛 · .가위 · .승부 — 매일 0시에 출석·룰렛 횟수가 초기화돼요</footer>
</div>

<script>
const QS = location.search || '';
const userLink = n => `/u/${encodeURIComponent(n)}${QS}`;
const rankCls = r => r <= 3 ? ` r${r}` : '';

fetch('/api/zenny' + QS).then(r => r.json()).then(d => {
  chartBase();
  $('meta').textContent = `멤버 ${d.total_members}명 · ${d.updated} 기준`;

  // 시즌
  if (d.season) {
    const s = d.season;
    $('season-sec').hidden = false;
    $('season-title').textContent = `${s.title} 시즌`;
    $('season-desc').textContent = `${md(s.start)} – ${md(s.end)} · 참여 ${s.players}명`;
    $('season-left').textContent = s.days_left > 0 ? `${s.days_left}일 남음` : `${s.hours_left}시간 남음`;
    $('season-body').innerHTML = s.top10.length ? s.top10.map(e => `
      <tr><td class="rank${rankCls(e.rank)}">${e.rank}</td>
        <td><a href="${userLink(e.nick)}">${esc(e.nick)}</a></td>
        <td class="num">${fmt(e.score)}</td></tr>`).join('')
      : '<tr><td colspan="3" class="muted">아직 기록이 없어요</td></tr>';
  }

  // 요약
  $('stats').innerHTML = `
    <div class="stat"><div class="l">전체 유통량</div><div class="v">${fmt(d.total_zenny)}</div><div class="s">제니 보유 ${d.holders}명</div></div>
    <div class="stat"><div class="l">중앙값</div><div class="v">${fmt(d.median)}</div><div class="s">평균 ${fmt(d.mean)}</div></div>
    <div class="stat"><div class="l">상위 5명 몫</div><div class="v">${d.top5_pct}%</div><div class="s">${fmt(d.top5_sum)}제니</div></div>
    <div class="stat"><div class="l">잭팟 / 초기화</div><div class="v">${fmt(d.jackpots)} / ${fmt(d.zero_drops)}</div><div class="s">룰렛 누적 횟수</div></div>`;

  // 추이
  new Chart($('trend'), {
    type: 'line',
    data: { labels: d.history.map(h => md(h.date)),
      datasets: [{ data: d.history.map(h => h.total), borderColor: css('--s1'), borderWidth: 2,
        pointRadius: 0, pointHoverRadius: 4, pointHoverBackgroundColor: css('--s1'),
        pointHoverBorderColor: css('--surface'), pointHoverBorderWidth: 2, tension: 0.2, fill: false }] },
    options: { interaction: { mode: 'index', intersect: false },
      plugins: { tooltip: { callbacks: { label: c => fmt(c.parsed.y) + '제니' } } },
      scales: { y: yAxis(), x: xAxis({ ticks: { maxRotation: 0, autoSkipPadding: 20 } }) } }
  });

  // 구간
  const nonzero = d.buckets.slice(1).reduce((a, b) => a + b.count, 0);
  $('bucket-desc').textContent = `잔고 0인 멤버 ${d.buckets[0].count}명 · 보유 ${nonzero}명`;
  new Chart($('buckets'), {
    type: 'bar',
    data: { labels: d.buckets.map(b => b.label),
      datasets: [{ data: d.buckets.map(b => b.count),
        backgroundColor: d.buckets.map((b, i) => i === 0 ? css('--zero') : css('--s1')),
        borderRadius: { topLeft: 4, topRight: 4 }, borderSkipped: 'bottom', maxBarThickness: 44 }] },
    options: { plugins: { tooltip: { callbacks: { title: c => c[0].label + ' 제니', label: c => c.parsed.y + '명' } } },
      scales: { y: yAxis({ ticks: { precision: 0, maxTicksLimit: 5 } }), x: xAxis() } }
  });

  // 흐름
  const g = d.max_gain || {}, l = d.max_loss || {}, k = d.by_kind || {};
  const kindRow = (name, key) => key in k ? `<div class="k">${name}</div><div class="v ${k[key] >= 0 ? 'pos' : 'neg'}">${signed(k[key])}</div>` : '';
  $('flow').innerHTML = `
    <div class="k">들어온 제니<small>출석·룰렛·가위바위보·승부에서 번 것</small></div><div class="v pos">+${fmt(d.pump)}</div>
    <div class="k">사라진 제니<small>룰렛·가위바위보에서 잃은 것, 초기화 포함</small></div><div class="v neg">-${fmt(d.drain)}</div>
    ${kindRow('출석으로', 'attend')}${kindRow('룰렛으로', 'roulette')}${kindRow('가위바위보로', 'rps')}${kindRow('승부로', 'duel')}
    <div class="k">한 번에 가장 많이 번 사람<small>${esc(g.nick || '-')} · ${OUTCOME(g.outcome)} · ${md(g.date)}</small></div><div class="v pos">+${fmt(g.delta)}</div>
    <div class="k">한 번에 가장 많이 잃은 사람<small>${esc(l.nick || '-')} · ${OUTCOME(l.outcome)} · ${md(l.date)}</small></div><div class="v neg">${fmt(l.delta)}</div>`;

  // 지난 시즌
  if (d.past_seasons && d.past_seasons.length) {
    $('past-sec').hidden = false;
    $('past-body').innerHTML = d.past_seasons.map(s => {
      const m = r => { const x = (s.medalists || []).find(v => v.rank === r);
        return x ? `${esc(x.nick)} <span class="muted">${short(x.score)}</span>` : '<span class="muted">-</span>'; };
      return `<tr><td class="muted">${esc(s.title)}</td><td>${m(1)}</td><td>${m(2)}</td><td>${m(3)}</td></tr>`;
    }).join('');
  }

  // 전체 순위 (동점 동순위)
  let prev = null, cursor = 0;
  const ranked = d.ranking.map((r, i) => { if (r.zenny !== prev) { cursor = i + 1; prev = r.zenny; } return { ...r, rank: cursor }; });
  const draw = q => {
    const list = q ? ranked.filter(r => r.nick.toLowerCase().includes(q.toLowerCase())) : ranked;
    $('rank-body').innerHTML = list.length ? list.map(r => `
      <tr><td class="rank${rankCls(r.rank)}">${r.rank}</td>
        <td><a href="${userLink(r.nick)}">${esc(r.nick)}</a></td>
        <td class="num">${fmt(r.zenny)}</td>
        <td class="num ${r.season ? '' : 'muted'}">${fmt(r.season)}</td></tr>`).join('')
      : '<tr><td colspan="4" class="muted">찾는 닉네임이 없어요</td></tr>';
  };
  draw('');
  $('q').addEventListener('input', e => draw(e.target.value.trim()));
}).catch(() => { $('meta').textContent = '데이터를 불러오지 못했어요. 잠시 후 새로고침해 주세요.'; });
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
    return PAGE


@app.route('/api/zenny')
def api_zenny():
    if not _key_ok():
        return jsonify({'error': 'unauthorized'}), 403
    return jsonify(_collect())


def _collect_user(nick_query: str) -> Optional[dict]:
    """특정 닉네임의 멤버 프로필 데이터. 없으면 None. (chat.py get_member_stats 도 사용)"""
    import re as _re

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
        heads = [(i, r['nick']) for i, r in enumerate(full['ranking'])
                 if _re.split(r'[/\\]', r['nick'])[0].strip() == nick_query]
        if len(heads) == 1:
            rank_idx, target_nick = heads[0]
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

    balance = full['ranking'][rank_idx]['zenny']          # 누적 잔고
    season_balance = full['ranking'][rank_idx]['season']  # 시즌 잔고
    # 동점 동순위
    rank = 1 + sum(1 for r in full['ranking'] if r['zenny'] > balance)

    with members._conn() as c:
        events = c.execute(
            'SELECT ts, kind, bet, payout, delta, outcome, balance_after FROM zenny_events '
            'WHERE user_id=? ORDER BY ts',
            (target_uid,),
        ).fetchall()

    attend_count = sum(1 for e in events if e[1] == 'attend')
    roulette_count = sum(1 for e in events if e[1] == 'roulette')
    rps_count = sum(1 for e in events if e[1] == 'rps')
    duel_count = sum(1 for e in events if e[1] == 'duel')
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
    duel_result = Counter('win' if e[5] == 'duel_win' else 'lose' for e in events if e[1] == 'duel')

    valid_delta = [e for e in events if e[4] is not None]
    if valid_delta:
        max_gain_e = max(valid_delta, key=lambda e: e[4])
        max_loss_e = min(valid_delta, key=lambda e: e[4])
    else:
        max_gain_e = max_loss_e = None

    def _ev_dict(e):
        if not e:
            return {'delta': 0, 'kind': '', 'outcome': '', 'ts': ''}
        return {'delta': e[4] or 0, 'kind': e[1], 'outcome': e[5] or '', 'ts': _kst_ts(e[0])}

    cur_win = cur_lose = max_win = max_lose = 0
    for e in events:
        if e[1] != 'roulette' or e[4] is None:
            continue
        if e[4] > 0:
            cur_win += 1
            cur_lose = 0
            max_win = max(max_win, cur_win)
        elif e[4] < 0:
            cur_lose += 1
            cur_win = 0
            max_lose = max(max_lose, cur_lose)
        else:
            cur_win = cur_lose = 0

    games = ('roulette', 'rps', 'duel')
    bets = [e[2] for e in events if e[2] is not None and e[1] in games]
    payouts = [e[3] for e in events if e[3] is not None and e[1] in games]
    avg_bet = round(sum(bets) / len(bets)) if bets else 0
    max_bet = max(bets) if bets else 0
    total_bet = sum(bets)
    total_payout = sum(payouts)

    attend_sum = sum(e[4] for e in events if e[1] == 'attend' and e[4] is not None)
    roul_pnl = sum(e[4] for e in events if e[1] == 'roulette' and e[4] is not None)
    rps_pnl = sum(e[4] for e in events if e[1] == 'rps' and e[4] is not None)
    duel_pnl = sum(e[4] for e in events if e[1] == 'duel' and e[4] is not None)
    gambling_pnl = roul_pnl + rps_pnl + duel_pnl

    daily = defaultdict(int)
    for e in events:
        if e[0] and e[4] is not None:
            daily[_kst_day(e[0])] += e[4]
    daily_sorted = sorted(daily.items())[-60:]
    history_series = [{'date': h['date'], 'zenny': h['total']}
                      for h in _balance_series(daily, balance, TREND_DAYS)]

    return {
        'nick': target_nick,
        'balance': balance,
        'season_balance': season_balance,
        'rank': rank,
        'total_members': full['total_members'],
        'mean': full['mean'],
        'median': full['median'],
        'attend_count': attend_count,
        'roulette_count': roulette_count,
        'rps_count': rps_count,
        'duel_count': duel_count,
        'jackpot_count': jackpot_count,
        'reset_count': reset_count,
        'roul_outcome': dict(roul_outcome),
        'rps_user_hand': dict(rps_user_hand),
        'rps_bot_hand': dict(rps_bot_hand),
        'rps_result': dict(rps_result),
        'duel_result': dict(duel_result),
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
        'duel_pnl': duel_pnl,
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
    start_ts = cur['start_ts']  # naive KST
    s_events = [e for e in events if e[0] and _kst_ts(e[0]) >= start_ts]
    return {
        'title': cur['title'],
        'score': score,
        'rank': rank,
        'players': len(s_ranking),
        'attend_count': sum(1 for e in s_events if e[1] == 'attend'),
        'roulette_count': sum(1 for e in s_events if e[1] == 'roulette'),
        'rps_count': sum(1 for e in s_events if e[1] == 'rps'),
        'duel_count': sum(1 for e in s_events if e[1] == 'duel'),
        'jackpot_count': sum(1 for e in s_events if e[5] == 'jackpot'),
        'reset_count': sum(1 for e in s_events if e[5] == 'reset'),
    }


USER_PAGE = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__NICK_HTML__ · 제니 기록</title>
<meta property="og:title" content="__NICK_HTML__ · 제니 기록">
<meta property="og:description" content="몬헌 와일즈 카톡방 멤버 기록">
<meta property="og:type" content="profile">
<meta property="og:locale" content="ko_KR">
""" + BASE_CSS + COMMON_JS + """
<style>
.back{display:inline-block;font-size:13px;color:var(--ink-3);text-decoration:none;margin-bottom:18px}
.back:hover{color:var(--ink)}
.bal{text-align:right}
.bal .v{font-size:30px;font-weight:700;letter-spacing:-.02em;line-height:1.2}
.bal .s{font-size:13px;color:var(--ink-3)}
.stats.six{grid-template-columns:repeat(6,1fr)}
@media(max-width:760px){.bal{text-align:left}.stats.six{grid-template-columns:repeat(3,1fr)}
  .stats.six .stat:nth-child(3){border-left:1px solid var(--line)}
  .stats.six .stat:nth-child(4){border-left:0}
  .stats.six .stat:nth-child(n+3){border-top:0}
  .stats.six .stat:nth-child(n+4){border-top:1px solid var(--line)}}
</style>
</head>
<body>
<div class="wrap">
  <a class="back" id="back" href="/">← 제니 현황</a>
  <header class="top">
    <div>
      <div class="kicker">멤버 기록</div>
      <h1>__NICK_HTML__</h1>
      <div class="meta" id="meta">불러오는 중…</div>
    </div>
    <div class="bal">
      <div class="v" id="bal">-</div>
      <div class="s" id="bal-sub">누적 잔고</div>
    </div>
  </header>

  <div class="stats six" id="stats"></div>

  <section id="season-sec" hidden>
    <div class="sec-head"><div><h2 id="season-title"></h2><div class="desc">이번 달 1일부터</div></div>
      <span class="pill" id="season-rank"></span></div>
    <div class="kv" id="season-kv"></div>
  </section>

  <section id="medal-sec" hidden>
    <h2>지난 시즌 입상</h2>
    <div class="desc">시즌 1·2·3위에 오른 기록</div>
    <table><thead><tr><th>시즌</th><th>순위</th><th class="num">시즌 잔고</th></tr></thead><tbody id="medal-body"></tbody></table>
  </section>

  <section>
    <h2>누적 잔고</h2>
    <div class="desc">최근 90일</div>
    <div class="chart"><canvas id="hist"></canvas></div>
  </section>

  <section>
    <h2>하루 손익</h2>
    <div class="desc">활동한 날 기준 최근 60일</div>
    <div class="legend"><span><i style="background:var(--s1)"></i>번 날</span><span><i style="background:var(--s2)"></i>잃은 날</span></div>
    <div class="chart short"><canvas id="daily"></canvas></div>
  </section>

  <div class="cols">
    <section>
      <h2>룰렛 결과</h2>
      <div class="desc" id="roul-desc"></div>
      <div class="legend"><span><i style="background:var(--s2)"></i>손해</span><span><i style="background:var(--zero)"></i>본전</span><span><i style="background:var(--s1)"></i>이득</span></div>
      <div class="chart short"><canvas id="roul"></canvas></div>
    </section>
    <section>
      <h2>가위바위보</h2>
      <div class="desc" id="rps-desc"></div>
      <div class="legend" id="rps-legend"><span><i style="background:var(--s1)"></i>내가 낸 손</span><span><i style="background:var(--s2)"></i>다이애나가 낸 손</span></div>
      <div class="chart short"><canvas id="rps"></canvas></div>
    </section>
  </div>

  <div class="cols">
    <section>
      <h2>어디서 벌고 잃었나</h2>
      <div class="desc">전체 기간 합계</div>
      <div class="kv" id="pnl"></div>
    </section>
    <section>
      <h2>기록</h2>
      <div class="desc">전체 기간</div>
      <div class="kv" id="records"></div>
    </section>
  </div>
</div>

<script>
const NICK = __NICK_JSON__;
const QS = location.search || '';
$('back').href = '/' + QS;

fetch('/api/user/' + encodeURIComponent(NICK) + QS).then(r => r.json()).then(d => {
  if (d.error) { $('meta').textContent = d.error; return; }
  chartBase();
  $('meta').textContent = `누적 ${d.rank}위 / ${d.total_members}명 · 방 중앙값 ${fmt(d.median)}`;
  $('bal').textContent = fmt(d.balance);
  $('bal-sub').textContent = `누적 잔고 · 이번 시즌 ${fmt(d.season_balance)}`;

  $('stats').innerHTML = [
    ['출석', d.attend_count + '일'], ['룰렛', d.roulette_count + '회'], ['가위바위보', d.rps_count + '회'],
    ['승부', d.duel_count + '회'], ['잭팟', d.jackpot_count + '회'], ['초기화', d.reset_count + '회'],
  ].map(([l, v]) => `<div class="stat"><div class="l">${l}</div><div class="v">${v}</div></div>`).join('');

  if (d.season) {
    const s = d.season;
    $('season-sec').hidden = false;
    $('season-title').textContent = `${s.title} 시즌`;
    $('season-rank').textContent = s.rank ? `${s.rank}위 / ${s.players}명` : '순위 없음';
    $('season-kv').innerHTML = `
      <div class="k">시즌 잔고</div><div class="v">${fmt(s.score)}</div>
      <div class="k">출석</div><div class="v">${s.attend_count}일</div>
      <div class="k">룰렛 · 가위바위보 · 승부</div><div class="v">${s.roulette_count} · ${s.rps_count} · ${s.duel_count}회</div>
      <div class="k">잭팟 · 초기화</div><div class="v">${s.jackpot_count} · ${s.reset_count}회</div>`;
  }

  if (d.medals && d.medals.length) {
    $('medal-sec').hidden = false;
    $('medal-body').innerHTML = d.medals.map(m => `
      <tr><td>${esc(m.title)}</td><td class="rank r${m.rank}">${m.rank}위</td><td class="num">${fmt(m.score)}</td></tr>`).join('');
  }

  // 누적 잔고
  new Chart($('hist'), {
    type: 'line',
    data: { labels: d.history.map(h => md(h.date)),
      datasets: [{ data: d.history.map(h => h.zenny), borderColor: css('--s1'), borderWidth: 2, stepped: false,
        pointRadius: 0, pointHoverRadius: 4, pointHoverBackgroundColor: css('--s1'),
        pointHoverBorderColor: css('--surface'), pointHoverBorderWidth: 2, tension: 0.15 }] },
    options: { interaction: { mode: 'index', intersect: false },
      plugins: { tooltip: { callbacks: { label: c => fmt(c.parsed.y) + '제니' } } },
      scales: { y: yAxis(), x: xAxis({ ticks: { maxRotation: 0, autoSkipPadding: 20 } }) } }
  });

  // 하루 손익
  new Chart($('daily'), {
    type: 'bar',
    data: { labels: d.daily_events.map(e => md(e.date)),
      datasets: [{ data: d.daily_events.map(e => e.delta),
        backgroundColor: d.daily_events.map(e => e.delta >= 0 ? css('--s1') : css('--s2')),
        borderRadius: 3, borderSkipped: false, maxBarThickness: 18 }] },
    options: { plugins: { tooltip: { callbacks: { label: c => signed(c.parsed.y) + '제니' } } },
      scales: { y: yAxis(), x: xAxis() } }
  });

  // 룰렛 결과 — 수익률 순으로 정렬 (예전 배율 기록도 그대로 표시)
  const val = k => k === 'reset' ? -1000 : k === 'jackpot' ? 1000 : parseInt(k.slice(1), 10);
  // 지금 룰렛 배율만 막대로, 예전 배율(+20%·+50% 등) 기록은 개수만 안내
  const CUR = ['reset', 'r-70', 'r-50', 'r-20', 'r+0', 'r+25', 'r+60', 'r+80', 'r+120', 'jackpot'];
  const keys = CUR.filter(k => d.roul_outcome[k]);
  const legacy = Object.entries(d.roul_outcome).filter(([k]) => !CUR.includes(k)).reduce((a, [, v]) => a + v, 0);
  const lab = k => k === 'reset' ? '초기화' : k === 'jackpot' ? '잭팟' : k === 'r+0' ? '본전' : k.slice(1) + '%';
  $('roul-desc').textContent = d.roulette_count ? `총 ${fmt(d.roulette_count)}회 · 최장 연승 ${d.max_win_streak} · 최장 연패 ${d.max_lose_streak}` + (legacy ? ` · 예전 배율 ${legacy}회 제외` : '') : '아직 룰렛 기록이 없어요';
  new Chart($('roul'), {
    type: 'bar',
    data: { labels: keys.map(lab),
      datasets: [{ data: keys.map(k => d.roul_outcome[k]),
        backgroundColor: keys.map(k => val(k) < 0 ? css('--s2') : val(k) === 0 ? css('--zero') : css('--s1')),
        borderRadius: { topLeft: 4, topRight: 4 }, borderSkipped: 'bottom', maxBarThickness: 28 }] },
    options: { plugins: { tooltip: { callbacks: { label: c => c.parsed.y + '회' } } },
      scales: { y: yAxis({ ticks: { precision: 0, maxTicksLimit: 5 } }), x: xAxis({ ticks: { autoSkip: false, maxRotation: 0, font: { size: 11 } } }) } }
  });

  // 가위바위보
  const hands = ['가위', '바위', '보'], rr = d.rps_result || {};
  const rpsTotal = (rr.win || 0) + (rr.draw || 0) + (rr.lose || 0);
  $('rps-desc').textContent = rpsTotal ? `${rr.win || 0}승 ${rr.draw || 0}무 ${rr.lose || 0}패 · 승률 ${Math.round((rr.win || 0) / rpsTotal * 100)}%` : '아직 가위바위보 기록이 없어요';
  if (!rpsTotal) { $('rps').parentElement.hidden = true; $('rps-legend').hidden = true; }
  else new Chart($('rps'), {
    type: 'bar',
    data: { labels: hands, datasets: [
      { label: '내가 낸 손', data: hands.map(h => d.rps_user_hand[h] || 0), backgroundColor: css('--s1'),
        borderRadius: { topLeft: 4, topRight: 4 }, borderSkipped: 'bottom', maxBarThickness: 28 },
      { label: '다이애나가 낸 손', data: hands.map(h => d.rps_bot_hand[h] || 0), backgroundColor: css('--s2'),
        borderRadius: { topLeft: 4, topRight: 4 }, borderSkipped: 'bottom', maxBarThickness: 28 }] },
    options: { interaction: { mode: 'index', intersect: false },
      datasets: { bar: { categoryPercentage: 0.6, barPercentage: 0.9 } },
      plugins: { tooltip: { displayColors: true, callbacks: { label: c => `${c.dataset.label} ${c.parsed.y}회` } } },
      scales: { y: yAxis({ ticks: { precision: 0, maxTicksLimit: 5 } }), x: xAxis() } }
  });

  const cls = v => v >= 0 ? 'pos' : 'neg';
  const dr = d.duel_result || {};
  $('pnl').innerHTML = `
    <div class="k">출석</div><div class="v pos">+${fmt(d.attend_sum)}</div>
    <div class="k">룰렛</div><div class="v ${cls(d.roul_pnl)}">${signed(d.roul_pnl)}</div>
    <div class="k">가위바위보</div><div class="v ${cls(d.rps_pnl)}">${signed(d.rps_pnl)}</div>
    <div class="k">승부<small>${d.duel_count ? `${dr.win || 0}승 ${dr.lose || 0}패` : '기록 없음'}</small></div><div class="v ${cls(d.duel_pnl)}">${signed(d.duel_pnl)}</div>
    <div class="k">출석 빼고 합계<small>룰렛 + 가위바위보 + 승부</small></div><div class="v ${cls(d.gambling_pnl)}">${signed(d.gambling_pnl)}</div>`;

  const g = d.max_gain, l = d.max_loss;
  $('records').innerHTML = `
    <div class="k">한 번에 가장 많이 번 것<small>${OUTCOME(g.outcome) || '-'} · ${md((g.ts || '').slice(0, 10))}</small></div><div class="v pos">${signed(g.delta)}</div>
    <div class="k">한 번에 가장 많이 잃은 것<small>${OUTCOME(l.outcome) || '-'} · ${md((l.ts || '').slice(0, 10))}</small></div><div class="v neg">${signed(l.delta)}</div>
    <div class="k">평균 베팅 · 최대 베팅</div><div class="v">${fmt(d.avg_bet)} · ${fmt(d.max_bet)}</div>
    <div class="k">건 돈 합계</div><div class="v">${fmt(d.total_bet)}</div>
    <div class="k">돌려받은 돈 합계</div><div class="v">${fmt(d.total_payout)}</div>`;
}).catch(() => { $('meta').textContent = '데이터를 불러오지 못했어요. 잠시 후 새로고침해 주세요.'; });
</script>
</body></html>
"""


@app.route('/u/<path:nick>')
def user_page(nick):
    key = request.args.get('key', '')
    wk = _current_key()
    if wk and key != wk:
        return GATE_PAGE
    nick_json = _json.dumps(nick, ensure_ascii=False).replace('</', '<\\/')
    return (USER_PAGE
            .replace('__NICK_JSON__', nick_json)
            .replace('__NICK_HTML__', _html.escape(nick)))


@app.route('/api/user/<path:nick>')
def api_user(nick):
    if not _key_ok():
        return jsonify({'error': 'unauthorized'}), 403
    data = _collect_user(nick)
    if data is None:
        return jsonify({'error': f'지금 방 멤버 중에 "{nick}"님을 찾지 못했어요'}), 404
    return jsonify(data)


def start_server(host: str = os.environ.get('WEB_HOST', '0.0.0.0'), port: int = int(os.environ.get('WEB_PORT', '80'))):
    print(f'[web] starting on {host}:{port}', flush=True)
    try:
        app.run(host=host, port=port, threaded=True, use_reloader=False)
    except Exception as ex:
        print(f'[web] error: {ex}', flush=True)
