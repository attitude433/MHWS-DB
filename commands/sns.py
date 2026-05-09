import json
import time
import urllib.request
from pathlib import Path
import feedparser

STATE_FILE = Path(__file__).parent.parent / 'sns_state.json'

YOUTUBE_CHANNELS = [
    {'id': 'UCVS0xBpOtXBAl12rdG67-OQ', 'label': '몬헌 공식'},
    {'id': 'UCW7h-1mymnJ96akzjrmiIgA', 'label': 'Capcom USA'},
]
STEAM_FEED_URL = 'https://store.steampowered.com/feeds/news/app/2246340/?l=koreana'
WILDS_KEYWORDS = ['wilds', '와일즈']

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


def _fetch_steam() -> list[dict]:
    try:
        feed = feedparser.parse(STEAM_FEED_URL)
        posts = []
        for e in feed.entries:
            posts.append({
                'id': e.get('id') or e.get('link'),
                'title': e.get('title', ''),
                'link': e.get('link', ''),
            })
        return posts
    except Exception as ex:
        print(f'[sns] steam fetch error: {ex}', flush=True)
        return []


def _is_wilds_relevant(title: str) -> bool:
    t = title.lower()
    return any(kw in t for kw in WILDS_KEYWORDS)


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
        for v in videos:
            if v['id'] == last_seen:
                break
            new_videos.append(v)
        new_videos = [v for v in new_videos if _is_wilds_relevant(v['title'])]
        if new_videos:
            state[key] = videos[0]['id']
            for v in reversed(new_videos):
                messages.append(v['link'])

    posts = _fetch_steam()
    if posts:
        last_seen = state.get('steam')
        if last_seen is None:
            state['steam'] = posts[0]['id']
        else:
            new_posts = []
            for p in posts:
                if p['id'] == last_seen:
                    break
                new_posts.append(p)
            if new_posts:
                state['steam'] = new_posts[0]['id']
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
