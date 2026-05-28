"""제니/룰렛 시뮬레이션 sanity check.

확률 분포 / EV / 100명 2개월 시뮬 / 잭팟·초기화 등장 빈도 검증.
"""
from __future__ import annotations
import random
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from commands.zenny import (
    ROULETTE_OUTCOMES,
    ATTEND_MIN,
    ATTEND_MAX,
    ROULETTE_DAILY_LIMIT,
    _pick_outcome,
)

random.seed(0)

# 1) 확률 합 = 1.0
total_prob = sum(p for _, p in ROULETTE_OUTCOMES)
assert abs(total_prob - 1.0) < 1e-9, f'확률 합 {total_prob} != 1.0'
print(f'✓ 확률 합: {total_prob}')

# 2) 1만회 분포 ±2%
N = 100_000
cnt = Counter()
ev_sum = 0.0
for _ in range(N):
    r = _pick_outcome()
    cnt[r] += 1
    if r is not None:
        ev_sum += r
    else:
        ev_sum += -1.0  # 초기화는 -100% 등가

print(f'\n✓ {N}회 분포:')
for r, prob in ROULETTE_OUTCOMES:
    label = '초기화' if r is None else f'{int(r*100):+}%'
    actual = cnt[r] / N
    diff = actual - prob
    flag = '!' if abs(diff) > 0.02 else ' '
    print(f'  {flag} {label:>8}: expected {prob*100:.1f}%  actual {actual*100:.2f}%  diff {diff*100:+.2f}%')

ev = ev_sum / N
print(f'\n✓ 산술 EV: {ev*100:+.2f}% (기획서 -1% 라고 적혀있지만 실제 확률표 계산으론 +1% 근처. 분산이 커서 장기 기하평균은 손실)')
assert -0.05 < ev < 0.05, f'EV {ev} 가 ±5% 범위 밖'

# 3) 100명 60일 시뮬 (출석 + 매일 룰렛 3회, 잔고 50% 베팅)
N_PEOPLE = 100
DAYS = 60
balances = [0] * N_PEOPLE
jackpot_count = 0
reset_count = 0
for day in range(DAYS):
    for i in range(N_PEOPLE):
        balances[i] += random.randint(ATTEND_MIN, ATTEND_MAX)
        for _ in range(ROULETTE_DAILY_LIMIT):
            if balances[i] <= 0:
                break
            bet = max(1, balances[i] // 2)
            r = _pick_outcome()
            if r is None:
                balances[i] = 0
                reset_count += 1
            else:
                payback = int(round(bet * (1 + r)))
                balances[i] = balances[i] - bet + payback
                if r == 10.0:
                    jackpot_count += 1

avg = sum(balances) / N_PEOPLE
print(f'\n✓ 100명 60일 시뮬:')
print(f'  평균: {avg:.0f}')
print(f'  최고: {max(balances)}')
print(f'  최저: {min(balances)}')
print(f'  잭팟 총: {jackpot_count}회')
print(f'  초기화 총: {reset_count}회')

# 기획서 결과 (평균 293 / 최고 4,633 / 최저 2) 와 자릿수 비슷한지
assert 50 < avg < 5_000, f'평균 {avg} 가 자릿수 이탈'
print(f'\n✓ 시뮬 정상 범위')
