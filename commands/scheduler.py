import time
from datetime import datetime
from zoneinfo import ZoneInfo

KST = ZoneInfo('Asia/Seoul')

SCHEDULES = [
    {'hour': 9, 'minute': 0, 'message': '오늘도 좋은 하루! ٩(๑˃̵ᴗ˂̵)و'},
    {'hour': 0, 'minute': 0, 'message': '모두 잘자요 (づ.-)'},
]


def start_scheduler(bot, room_id: int):
    last_sent: dict = {}
    print(
        f'[scheduler] started, room_id={room_id}, schedules={len(SCHEDULES)}',
        flush=True,
    )
    while True:
        try:
            now = datetime.now(KST)
            for s in SCHEDULES:
                key = (s['hour'], s['minute'])
                if (
                    now.hour == s['hour']
                    and now.minute == s['minute']
                    and last_sent.get(key) != now.date()
                ):
                    bot.api.reply(room_id, s['message'])
                    last_sent[key] = now.date()
                    print(
                        f'[scheduler] sent at {now.isoformat()}: {s["message"]}',
                        flush=True,
                    )
        except Exception as ex:
            print(f'[scheduler] error: {ex}', flush=True)
        time.sleep(30)
