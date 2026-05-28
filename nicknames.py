"""user_id → nickname 매핑 (카톡 export 기반).

nicknames.json 을 모듈 load 시 한 번 읽어 메모리에 캐싱.
update_nickname() 으로 런타임에 추가/갱신.
"""
from __future__ import annotations
import json
import threading
from pathlib import Path

JSON_PATH = Path(__file__).resolve().parent / 'nicknames.json'

_lock = threading.Lock()
_data: dict = {}


def _load():
    global _data
    if JSON_PATH.exists():
        try:
            with open(JSON_PATH, encoding='utf-8') as f:
                raw = json.load(f)
            _data = {int(k): v for k, v in raw.items() if v}
        except Exception:
            _data = {}
    else:
        _data = {}


def get(user_id: int) -> str:
    return _data.get(int(user_id), '')


def update(user_id: int, nickname: str) -> None:
    if not user_id or not nickname:
        return
    with _lock:
        _data[int(user_id)] = nickname
        try:
            with open(JSON_PATH, 'w', encoding='utf-8') as f:
                json.dump({str(k): v for k, v in _data.items()}, f, ensure_ascii=False, indent=2)
        except Exception:
            pass


def all_mappings() -> dict:
    return dict(_data)


_load()
