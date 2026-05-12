import json
import os
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timedelta

KMA_URL = 'https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getUltraSrtNcst'
AIR_URL = 'https://apis.data.go.kr/B552584/ArpltnInforInqireSvc/getCtprvnRltmMesureDnsty'

LOCATIONS = {
    '서울': (60, 127, '서울'),
    '부산': (98, 76, '부산'),
    '대구': (89, 90, '대구'),
    '인천': (55, 124, '인천'),
    '광주': (58, 74, '광주'),
    '대전': (67, 100, '대전'),
    '울산': (102, 84, '울산'),
    '세종': (66, 103, '세종'),
    '수원': (60, 121, '경기'),
    '청주': (69, 106, '충북'),
    '천안': (63, 110, '충남'),
    '전주': (63, 89, '전북'),
    '강릉': (92, 131, '강원'),
    '춘천': (73, 134, '강원'),
    '원주': (79, 124, '강원'),
    '제주': (53, 38, '제주'),
    '안동': (91, 106, '경북'),
    '포항': (102, 94, '경북'),
    '창원': (91, 77, '경남'),
    '진주': (81, 75, '경남'),
    '목포': (50, 67, '전남'),
    '여수': (73, 66, '전남'),
}

PTY_KR = {
    '0': '',
    '1': '비',
    '2': '비/눈',
    '3': '눈',
    '5': '빗방울',
    '6': '빗방울눈날림',
    '7': '눈날림',
}

GRADE_KR = {
    '1': '좋음',
    '2': '보통',
    '3': '나쁨',
    '4': '매우나쁨',
}


def _key() -> str:
    return os.environ.get('DATA_GO_KR_API_KEY', '')


def _base_time() -> tuple[str, str]:
    now = datetime.now()
    if now.minute < 40:
        now = now - timedelta(hours=1)
    return now.strftime('%Y%m%d'), now.strftime('%H00')


def _fetch_kma(nx: int, ny: int) -> dict | None:
    base_date, base_time = _base_time()
    params = {
        'serviceKey': _key(),
        'numOfRows': '10',
        'pageNo': '1',
        'dataType': 'JSON',
        'base_date': base_date,
        'base_time': base_time,
        'nx': nx,
        'ny': ny,
    }
    url = KMA_URL + '?' + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            data = json.load(r)
    except Exception:
        return None

    items = data.get('response', {}).get('body', {}).get('items', {}).get('item', [])
    out = {}
    for item in items:
        out[item.get('category', '')] = item.get('obsrValue', '')
    return out if out else None


def _fetch_air(sido: str) -> dict | None:
    params = {
        'sidoName': sido,
        'returnType': 'json',
        'numOfRows': '50',
        'pageNo': '1',
        'ver': '1.0',
        'serviceKey': _key(),
    }
    url = AIR_URL + '?' + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            data = json.load(r)
    except Exception:
        return None

    items = data.get('response', {}).get('body', {}).get('items', [])
    pm10_vals, pm10_grades = [], []
    pm25_vals, pm25_grades = [], []
    for it in items:
        try:
            v = float(it.get('pm10Value', '-'))
            if v >= 0:
                pm10_vals.append(v)
                pm10_grades.append(it.get('pm10Grade'))
        except (ValueError, TypeError):
            pass
        try:
            v = float(it.get('pm25Value', '-'))
            if v >= 0:
                pm25_vals.append(v)
                pm25_grades.append(it.get('pm25Grade'))
        except (ValueError, TypeError):
            pass

    if not pm10_vals and not pm25_vals:
        return None

    def _mode(grades):
        c = Counter(g for g in grades if g)
        return c.most_common(1)[0][0] if c else ''

    return {
        'pm10': sum(pm10_vals) / len(pm10_vals) if pm10_vals else 0,
        'pm10_grade': GRADE_KR.get(_mode(pm10_grades), '?'),
        'pm25': sum(pm25_vals) / len(pm25_vals) if pm25_vals else 0,
        'pm25_grade': GRADE_KR.get(_mode(pm25_grades), '?'),
    }


def format_weather(location: str = '서울') -> str:
    if location not in LOCATIONS:
        cities = ' / '.join(LOCATIONS.keys())
        return f'다이애나는 "{location}" 데이터가 없어요.\n지원: {cities}'

    nx, ny, sido = LOCATIONS[location]
    kma = _fetch_kma(nx, ny)
    air = _fetch_air(sido)

    lines = [f'{location} 날씨에요!']
    if kma:
        temp = kma.get('T1H', '?')
        hum = kma.get('REH', '?')
        wind = kma.get('WSD', '?')
        rain = kma.get('RN1', '0')
        pty = PTY_KR.get(kma.get('PTY', '0'), '')

        line = f'기온 {temp}°C, 습도 {hum}%, 풍속 {wind}m/s'
        if pty:
            line += f' ({pty})'
        try:
            if rain not in ('0', '강수없음') and float(rain) > 0:
                line += f', 강수 {rain}mm'
        except (ValueError, TypeError):
            pass
        lines.append(line)
    else:
        lines.append('(기상 데이터 가져오기 실패)')

    if air:
        lines.append(
            f'미세먼지 {air["pm10_grade"]}({air["pm10"]:.0f}㎍/㎥) · '
            f'초미세먼지 {air["pm25_grade"]}({air["pm25"]:.0f}㎍/㎥)'
        )
    else:
        lines.append('(미세먼지 데이터 가져오기 실패)')

    return '\n'.join(lines)
