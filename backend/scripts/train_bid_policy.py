"""입찰 정책 신경망 학습 — CEM(교차엔트로피법), 10년 실데이터 시장."""
import json, math, random, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services import market_data
from app.core.resources import MARKET_RULES, ess_resources

market_data._load_once()
DAYS = sorted({(k[0], k[1], k[2]) for k in market_data._price if k[3] == 12 and k[0] < 2026})
CAP = MARKET_RULES["price_cap"]; CP = MARKET_RULES["cp_rate"]; PEN = MARKET_RULES["penalty_factor"]
POWER = sum(r["max_discharge_kw"] for r in ess_resources().values())          # 225
E_USE = sum((60 - r["soc_min"]) / 100 * r["capacity_kwh"] for r in ess_resources().values())  # 180
DEG = 50.0

def day_curve(y, m, d, jit, rng):
    out = []
    for h in range(24):
        base = market_data._price.get((y, m, d, h), 84.5)
        pct = market_data._dpct.get((y, m, d, h), 0.5)
        out.append(base * (0.95 + 0.55 * pct**2) * (1 + rng.uniform(-.03, .03) * jit))
    return out

N_IN, N_H = 5, 8
N_PAR = N_IN * N_H + N_H + N_H * 2 + 2
def policy(theta, fc):
    W1 = theta[:N_IN*N_H].reshape(N_IN, N_H); b1 = theta[N_IN*N_H:N_IN*N_H+N_H]
    o = N_IN*N_H+N_H; W2 = theta[o:o+N_H*2].reshape(N_H, 2); b2 = theta[o+N_H*2:]
    mx = max(fc); rank = np.argsort(np.argsort(fc)) / 23.0
    bids = []
    for h in range(24):
        x = np.array([fc[h]/mx, math.sin(2*math.pi*h/24), math.cos(2*math.pi*h/24), rank[h], E_USE/(POWER*24)])
        hdn = np.tanh(x @ W1 + b1); q, p = 1/(1+np.exp(-(hdn @ W2 + b2)))
        qty = round(q * POWER / 10) * 10 if q > 0.35 else 0
        bids.append((qty, min(CAP, fc[h] * (0.75 + 0.24 * p))))
    return bids

def simulate(bids, actual):
    rev = pen = cp = 0.0; energy = E_USE
    for h in range(24):
        qty, price = bids[h]
        if qty <= 0: continue
        cp += qty * CP
        if price <= actual[h]:
            deliv = min(qty, energy); energy -= deliv
            rev += deliv * actual[h] - DEG * deliv
            short = qty - deliv
            if short > 0.5: pen += short * actual[h] * PEN
    return rev + cp - pen

def evaluate(theta, days, seed=0):
    rng = random.Random(seed); tot = 0.0
    for (y, m, d) in days:
        fc = day_curve(y, m, d, 0, rng); ac = day_curve(y, m, d, 1, rng)
        tot += simulate(policy(theta, fc), ac)
    return tot / len(days)

def base_naive(fc):  # '전략 채움' (스크린샷의 손실 전략)
    top = sorted(range(24), key=lambda h: -fc[h])[:8]
    return [(100 if h in top else 0, fc[h]*0.92) for h in range(24)]
def base_rule(fc):   # 90원 고정 입찰
    return [(100, 90.0) for _ in range(24)]

rng = np.random.default_rng(7)
mu, sig = np.zeros(N_PAR), np.ones(N_PAR) * 1.5
for it in range(30):
    pop = rng.normal(mu, sig, (28, N_PAR))
    days = random.Random(it).sample(DAYS, 10)
    scores = [evaluate(th, days, it) for th in pop]
    elite = pop[np.argsort(scores)[-7:]]
    mu, sig = elite.mean(0), elite.std(0) + 0.05
    if it % 10 == 9: print(f"iter {it+1}: elite avg ₩{np.mean(sorted(scores)[-7:]):,.0f}")

test = random.Random(999).sample(DAYS, 150)
ai = evaluate(mu, test, 999)
r = random.Random(999); nv = rl = 0.0
for (y, m, d) in test:
    fc = day_curve(y, m, d, 0, r); ac = day_curve(y, m, d, 1, r)
    nv += simulate(base_naive(fc), ac); rl += simulate(base_rule(fc), ac)
nv /= len(test); rl /= len(test)
print(f"\n=== 검증 (150일 홀드아웃) — 일평균 순수익 ===")
print(f"AI 정책      : ₩{ai:,.0f}")
print(f"전략채움(8구간): ₩{nv:,.0f}")
print(f"90원 고정    : ₩{rl:,.0f}")
out = {"weights": mu.tolist(), "arch": [N_IN, N_H, 2], "trained_days": 300,
       "eval": {"ai": round(ai), "naive": round(nv), "rule90": round(rl), "test_days": 150}}
Path("models").mkdir(exist_ok=True)
json.dump(out, open("models/bid_policy.json", "w"))
print("saved models/bid_policy.json")
