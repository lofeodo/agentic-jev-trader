import sys
import numpy as np, pandas as pd, talib
d = sys.argv[1]
for sym in ["SPY", "AAPL", "JPM", "XOM", "BTCUSDT"]:
    df = pd.read_csv(f"{d}/{sym}_15m.csv", parse_dates=["datetime"])
    df = df[df.volume > 0].reset_index(drop=True)
    h, l, c, o = (df[k].to_numpy(float) for k in ("high", "low", "close", "open"))
    atr = talib.ATR(h, l, c, 14) / c * 100
    atr = atr[~np.isnan(atr)]
    df["date"] = df.datetime.dt.date
    g = df.groupby("date").agg(o=("open", "first"), h=("high", "max"), l=("low", "min"), c=("close", "last"), n=("close", "size"))
    rng = (g.h - g.l) / g.o * 100
    oc = (g.c - g.o).abs() / g.o * 100
    gap = (g.o / g.c.shift(1) - 1).abs().dropna() * 100
    m4 = np.abs(c[4:] / c[:-4] - 1) * 100
    print(f"{sym}: bars {len(df)} days {len(g)}")
    print(f"  ATR14 %price: p10 {np.percentile(atr,10):.3f} median {np.median(atr):.3f} p90 {np.percentile(atr,90):.3f}")
    print(f"  1-hour abs move %: median {np.median(m4):.3f} p90 {np.percentile(m4,90):.3f}")
    print(f"  day range %: median {rng.median():.2f} p90 {rng.quantile(.9):.2f} | day open-to-close abs %: median {oc.median():.2f} p90 {oc.quantile(.9):.2f} max {oc.max():.2f}")
    print(f"  gap between days abs %: median {gap.median():.2f} p95 {gap.quantile(.95):.2f} p99 {gap.quantile(.99):.2f} max {gap.max():.2f}")
    a = np.median(atr)
    for pos in (2000, 10000, 20000, 40000):
        cost = (2 + pos * 0.001) if sym != "BTCUSDT" else pos * 0.003
        print(f"  ${pos}: loss at 1/2/3 ATR stop ${pos*a/100:.0f}/${pos*2*a/100:.0f}/${pos*3*a/100:.0f}; in+out costs ${cost:.0f}; typical day move ${pos*oc.median()/100:.0f}")
