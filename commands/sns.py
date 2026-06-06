import json
import time
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

STATE_FILE = Path(__file__).parent.parent / 'sns_state.json'

YOUTUBE_CHANNELS = [
    {'id': 'UCVS0xBpOtXBAl12rdG67-OQ', 'label': '몬헌 공식', 'mh_only': False},
    {'id': 'UC02q4A9aCXUARMI51rFcl5A', 'label': '캡콤 아시아', 'mh_only': True},
]

X_ACCOUNTS = [
    {'handle': 'Capcom_Asia_KR', 'label': '캡콤 아시아', 'mh_only': True},
    {'handle': 'monsterhunter', 'label': '몬스터헌터 공식', 'mh_only': False},
]
RSSHUB_BASE = 'http://127.0.0.1:1200/twitter/user'

POLL_INTERVAL = 3600

# 캡콤아시아 채널처럼 캡콤 전체 게임 다루는 곳에서 MH 글만 거르는 키워드.
# 너무 흔한 단어(월드/world/rise/stories)는 단독으로 두면 스파6 "월드 투어",
# "Year 4 rise" 등에서 오탐 → 명확한 MH 시리즈 명칭만 사용.
MH_KEYWORDS = (
    '몬스터헌터', '몬헌', '와일즈', '선브레이크', '아이스본', '어센던스',
    'monster hunter', 'monsterhunter', 'mhwilds', 'wilds',
    'sunbreak', 'iceborne', 'ascendance',
    'mhrise', 'mhworld', 'mhstories', 'mhw',
)


def _is_mh(text: str) -> bool:
    t = (text or '').lower()
    return any(kw.lower() in t for kw in MH_KEYWORDS)


def _load_state() -> dict:
    if STATE_FILE.exists():
        with open(STATE_FILE, encoding='utf-8') as f:
            return json.load(f)
    return {}


def _save_state(state: dict):
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


_YT_NS = {
    'a': 'http://www.w3.org/2005/Atom',
    'yt': 'http://www.youtube.com/xml/schemas/2015',
}


def _fetch_youtube(api_key: str, channel_id: str) -> list[dict]:
    # RSS 피드 사용 (quota 무제한, api_key 불필요 — 인자는 호환 위해 유지)
    url = f'https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}'
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=15) as r:
            xml_data = r.read()
        root = ET.fromstring(xml_data)
        videos = []
        for entry in root.findall('a:entry', _YT_NS):
            vid_el = entry.find('yt:videoId', _YT_NS)
            title_el = entry.find('a:title', _YT_NS)
            if vid_el is None or not vid_el.text:
                continue
            vid = vid_el.text.strip()
            videos.append({
                'id': vid,
                'title': (title_el.text if title_el is not None else '') or '',
                'link': f'https://www.youtube.com/watch?v={vid}',
            })
        return videos
    except Exception as ex:
        print(f'[sns] youtube fetch error ({channel_id}): {ex}', flush=True)
        return []


def _fetch_x(handle: str) -> list[dict]:
    url = f'{RSSHUB_BASE}/{handle}'
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            xml_data = r.read()
        root = ET.fromstring(xml_data)
        posts = []
        for item in root.findall('.//item'):
            link = (item.findtext('link') or '').strip()
            if not link:
                continue
            tweet_id = link.rstrip('/').split('/')[-1]
            title = (item.findtext('title') or '').strip()
            desc = (item.findtext('description') or '').strip()
            posts.append({'id': tweet_id, 'link': link, 'title': title, 'desc': desc})
        return posts
    except Exception as ex:
        print(f'[sns] x fetch error ({handle}): {ex}', flush=True)
        return []


def _check_new(api_key: str, state: dict) -> list[str]:
    messages = []

    for ch in YOUTUBE_CHANNELS:
        cid = ch['id']
        videos = _fetch_youtube(api_key, cid)
        if not videos:
            continue
        key = f'yt:{cid}'
        last_seen = state.get(key)
        if last_seen is None:
            state[key] = videos[0]['id']
            continue
        new_videos = []
        found = False
        for v in videos:
            if v['id'] == last_seen:
                found = True
                break
            new_videos.append(v)
        if not found:
            # last_seen scrolled out of fetch window (or ID format changed) —
            # don't blast every item; just resync state silently.
            state[key] = videos[0]['id']
            print(f'[sns] yt {cid}: last_seen not in window; resync only', flush=True)
            continue
        if new_videos:
            state[key] = videos[0]['id']
            for v in reversed(new_videos):
                if ch.get('mh_only') and not _is_mh(v.get('title', '')):
                    print(f'[sns] yt {cid}: skip non-MH "{v.get("title","")[:40]}"', flush=True)
                    continue
                messages.append(v['link'])

    for acc in X_ACCOUNTS:
        handle = acc['handle']
        posts = _fetch_x(handle)
        if not posts:
            continue
        key = f'x:{handle}'
        last_seen = state.get(key)
        if last_seen is None:
            state[key] = posts[0]['id']
            continue
        new_posts = []
        found = False
        for p in posts:
            if p['id'] == last_seen:
                found = True
                break
            new_posts.append(p)
        if not found:
            state[key] = posts[0]['id']
            print(f'[sns] x {handle}: last_seen not in window; resync only', flush=True)
            continue
        if new_posts:
            state[key] = posts[0]['id']
            for p in reversed(new_posts):
                if acc.get('mh_only'):
                    blob = f"{p.get('title','')} {p.get('desc','')}"
                    if not _is_mh(blob):
                        print(f'[sns] x {handle}: skip non-MH "{p.get("title","")[:40]}"', flush=True)
                        continue
                messages.append(p['link'])

    return messages


def start_poller(bot, room_id: int, api_key: str):
    state = _load_state()
    print(f'[sns] poller started, room_id={room_id}', flush=True)
    # 최초 실행(state 비어있음)만 첫 폴링 발송 스킵 (옛글 폭주 방지).
    # 재시작(state 존재)은 첫 폴링부터 발송 → last_seen 이후 신규 누락 방지.
    first = not state
    while True:
        try:
            messages = _check_new(api_key, state)
            _save_state(state)
            if not first:
                for msg in messages:
                    bot.api.reply(room_id, msg)
                    print(f'[sns] sent: {msg}', flush=True)
            first = False
        except Exception as ex:
            print(f'[sns] poll error: {ex}', flush=True)
        time.sleep(POLL_INTERVAL)
