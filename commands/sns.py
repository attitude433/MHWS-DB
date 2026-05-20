import json
import time
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

STATE_FILE = Path(__file__).parent.parent / 'sns_state.json'

YOUTUBE_CHANNELS = [
    {'id': 'UCVS0xBpOtXBAl12rdG67-OQ', 'label': '몬헌 공식'},
    {'id': 'UC02q4A9aCXUARMI51rFcl5A', 'label': '캡콤 아시아'},
]

X_ACCOUNTS = [
    {'handle': 'Capcom_Asia_KR', 'label': '캡콤 아시아'},
    {'handle': 'monsterhunter', 'label': '몬스터헌터 공식'},
]
RSSHUB_BASE = 'http://127.0.0.1:1200/twitter/user'

POLL_INTERVAL = 3600


def _load_state() -> dict:
    if STATE_FILE.exists():
        with open(STATE_FILE, encoding='utf-8') as f:
            return json.load(f)
    return {}


def _save_state(state: dict):
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def _fetch_youtube(api_key: str, channel_id: str) -> list[dict]:
    url = (
        f'https://www.googleapis.com/youtube/v3/search'
        f'?key={api_key}&channelId={channel_id}'
        f'&part=snippet&order=date&maxResults=10&type=video'
    )
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            data = json.load(r)
        videos = []
        for it in data.get('items', []):
            vid = it['id']['videoId']
            sn = it['snippet']
            videos.append({
                'id': vid,
                'title': sn['title'],
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
            posts.append({'id': tweet_id, 'link': link})
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
                messages.append(p['link'])

    return messages


def start_poller(bot, room_id: int, api_key: str):
    state = _load_state()
    _check_new(api_key, state)
    _save_state(state)
    print(f'[sns] poller started, room_id={room_id}', flush=True)
    while True:
        time.sleep(POLL_INTERVAL)
        try:
            messages = _check_new(api_key, state)
            _save_state(state)
            for msg in messages:
                bot.api.reply(room_id, msg)
                print(f'[sns] sent: {msg}', flush=True)
        except Exception as ex:
            print(f'[sns] poll error: {ex}', flush=True)
