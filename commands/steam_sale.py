import json
import time
import urllib.request
from pathlib import Path

STATE_PATH = Path(__file__).parent.parent / 'steam_sale_state.json'

WATCH_APPS = [
    {'appid': 2246340, 'name': '와일즈',     'group': '와일즈'},
    {'appid': 1446780, 'name': '라이즈',     'group': '라이즈'},
    {'appid': 1880360, 'name': '선브레이크', 'group': '라이즈'},
    {'appid': 582010,  'name': '월드',       'group': '월드'},
    {'appid': 1118010, 'name': '아이스본',   'group': '월드'},
    {'appid': 2356560, 'name': '스토리즈',   'group': '스토리즈'},
    {'appid': 1277400, 'name': '스토리즈 2', 'group': '스토리즈 2'},
    {'appid': 2852190, 'name': '스토리즈 3', 'group': '스토리즈 3'},
]

POLL_INTERVAL_SEC = 12 * 3600


def _fetch(appid: int) -> dict | None:
    url = (
        f'https://store.steampowered.com/api/appdetails'
        f'?appids={appid}&cc=kr&l=koreana&filters=basic,price_overview'
    )
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            data = json.loads(r.read())
        entry = data.get(str(appid), {})
        if not entry.get('success'):
            return None
        return entry.get('data', {})
    except Exception:
        return None


def _load_state() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding='utf-8'))
        except Exception:
            return {}
    return {}


def _save_state(state: dict):
    STATE_PATH.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )


def _current_sales() -> dict:
    out = {}
    for app in WATCH_APPS:
        data = _fetch(app['appid'])
        if not data:
            continue
        po = data.get('price_overview') or {}
        dc = po.get('discount_percent', 0)
        if dc > 0:
            out[str(app['appid'])] = {
                'discount': dc,
                'final': po.get('final_formatted', ''),
                'original': po.get('initial_formatted', ''),
                'original_raw': po.get('initial', 0),
                'name': app['name'],
                'group': app['group'],
            }
        time.sleep(0.5)
    return out


def _format_message(sales: dict) -> str:
    groups: dict = {}
    for appid, info in sales.items():
        groups.setdefault(info['group'], []).append((appid, info))

    summaries = []
    for gname, items in groups.items():
        items.sort(key=lambda x: -x[1]['original_raw'])
        lead_appid, lead = items[0]
        label = ' + '.join(i[1]['name'] for i in items) if len(items) > 1 else lead['name']
        summaries.append({
            'label': label,
            'appid': lead_appid,
            'discount': lead['discount'],
            'final': lead['final'],
            'original': lead['original'],
            'original_raw': lead['original_raw'],
        })

    summaries.sort(key=lambda x: -x['original_raw'])
    top = summaries[0]

    lines = [
        '🎮 지금 할인중이래요!',
        '',
        f"{top['label']} {top['discount']}% 할인",
        f"{top['original']} → {top['final']}",
        f"https://store.steampowered.com/app/{top['appid']}/",
    ]
    if len(summaries) > 1:
        others = ', '.join(s['label'] for s in summaries[1:])
        lines += ['', f'같이 할인 중: {others}']
    return '\n'.join(lines)


def _ended_group_labels(state: dict, current: dict) -> list[str]:
    ended = [appid for appid, dc in state.items() if int(dc) > 0 and appid not in current]
    if not ended:
        return []
    app_by_id = {str(a['appid']): a for a in WATCH_APPS}
    groups: dict = {}
    for appid in ended:
        app = app_by_id.get(appid)
        if app:
            groups.setdefault(app['group'], []).append(app['name'])
    group_order = []
    for app in WATCH_APPS:
        if app['group'] in groups and app['group'] not in group_order:
            group_order.append(app['group'])
    labels = []
    for gname in group_order:
        items = groups[gname]
        labels.append(' + '.join(items) if len(items) > 1 else items[0])
    return labels


def _format_end(labels: list[str]) -> str:
    if len(labels) == 1:
        return f'😢 {labels[0]} 할인이 끝났어요'
    return '😢 할인이 끝났어요\n\n' + ', '.join(labels)


def start_poller(bot, room_id: int):
    print(f'[steam_sale] poller started, room_id={room_id}', flush=True)
    first_run = not STATE_PATH.exists()
    while True:
        try:
            state = _load_state()
            current = _current_sales()
            newly = {appid: info for appid, info in current.items() if int(state.get(appid, 0)) == 0}
            ended_labels = _ended_group_labels(state, current)
            if first_run:
                print(
                    f'[steam_sale] first run, skip alert. current sales: {list(current.keys())}',
                    flush=True,
                )
            else:
                if newly:
                    msg = _format_message(newly)
                    bot.api.reply(room_id, msg)
                    print(f'[steam_sale] start alert: {list(newly.keys())}', flush=True)
                if ended_labels:
                    msg = _format_end(ended_labels)
                    bot.api.reply(room_id, msg)
                    print(f'[steam_sale] end alert: {ended_labels}', flush=True)
            new_state = {
                str(app['appid']): current.get(str(app['appid']), {}).get('discount', 0)
                for app in WATCH_APPS
            }
            _save_state(new_state)
            first_run = False
        except Exception as ex:
            print(f'[steam_sale] error: {ex}', flush=True)
        time.sleep(POLL_INTERVAL_SEC)
