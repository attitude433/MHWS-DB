import json
import asyncio
from pathlib import Path
import feedparser

STATE_FILE = Path(__file__).parent.parent / 'sns_state.json'

ACCOUNTS = [
    {'handle': 'MH_Wilds',       'label': '몬헌 와일즈 공식'},
    {'handle': 'monsterhunter',  'label': '몬헌 시리즈 공식'},
]

RSSHUB_BASE = 'https://rsshub.app/twitter/user'


def _load_state() -> dict:
    if STATE_FILE.exists():
        with open(STATE_FILE, encoding='utf-8') as f:
            return json.load(f)
    return {}


def _save_state(state: dict):
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def _fetch_latest(handle: str) -> list[dict]:
    url = f'{RSSHUB_BASE}/{handle}'
    feed = feedparser.parse(url)
    posts = []
    for entry in feed.entries:
        posts.append({
            'id': entry.get('id') or entry.get('link'),
            'link': entry.get('link', ''),
            'title': entry.get('title', ''),
        })
    return posts


def check_new_posts() -> list[str]:
    state = _load_state()
    messages = []

    for account in ACCOUNTS:
        handle = account['handle']
        label = account['label']
        posts = _fetch_latest(handle)

        if not posts:
            continue

        last_seen = state.get(handle)
        new_posts = []

        if last_seen is None:
            # 첫 실행: 최신 1개만 기준점으로 저장
            state[handle] = posts[0]['id']
            continue

        for post in posts:
            if post['id'] == last_seen:
                break
            new_posts.append(post)

        if new_posts:
            state[handle] = new_posts[0]['id']
            for post in reversed(new_posts):
                messages.append(post['link'])

    _save_state(state)
    return messages


async def start_poller(bot, room_name: str):
    # 첫 실행: 기준점 설정만 하고 알림 없음
    check_new_posts()

    while True:
        await asyncio.sleep(12 * 3600)
        messages = check_new_posts()
        if messages:
            room = await bot.get_room(room_name)
            if room:
                for msg in messages:
                    await room.send(msg)
