import numpy as np, talib
rng = np.random.default_rng(1)
names = ["CDL3STARSINSOUTH","CDLABANDONEDBABY","CDLCONCEALBABYSWALL","CDLKICKING","CDLKICKINGBYLENGTH","CDLMATHOLD","CDLBREAKAWAY","CDLUPSIDEGAP2CROWS","CDLCOUNTERATTACK"]
n = 3_000_000
# bars with frequent gaps, marubozu-like and doji-like bodies, tiny shadows
prev = 100.0
O = np.empty(n); H = np.empty(n); L = np.empty(n); C = np.empty(n)
kind = rng.integers(0, 5, n)
for i in range(n):
    gap = rng.normal(0, 1.2) if rng.random() < 0.5 else rng.normal(0, 0.1)
    o = prev + gap
    k = kind[i]
    if k == 0: body = rng.normal(0, 0.05)
    elif k == 1: body = rng.normal(0, 0.8)
    elif k == 2: body = rng.choice([-1, 1]) * rng.uniform(1, 3)
    else: body = rng.normal(0, 0.3)
    c = o + body
    sh = 0.0 if k == 2 and rng.random() < .7 else rng.uniform(0, 1.0)
    H[i] = max(o, c) + sh * rng.random(); L[i] = min(o, c) - sh * rng.random()
    O[i] = o; C[i] = c; prev = c
O += 100; H += 100; L += 100; C += 100
for nm in names:
    out = getattr(talib, nm)(O, H, L, C)
    u, c = np.unique(out[out != 0], return_counts=True)
    print(nm, dict(zip(u.tolist(), c.tolist())))
