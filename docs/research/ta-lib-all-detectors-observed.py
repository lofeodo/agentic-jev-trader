"""Run every TA-Lib CDL* detector over real OHLCV CSVs and print lookback and observed output values.

Usage: python -I ta-lib-all-detectors-observed.py <bars_dir> [asset ...]
Reads <bars_dir>/<ASSET>_15m.csv (columns datetime,open,high,low,close,volume), drops volume 0 rows.
Prints one markdown row per detector: name | display name | lookback | values seen (count) per asset | all-asset union.
Only aggregate counts are printed; no raw bars are written anywhere.
"""
import sys
from collections import Counter

import pandas as pd
import talib
from talib import abstract

bars_dir = sys.argv[1]
assets = sys.argv[2:] or ["SPY", "AAPL", "JPM", "XOM", "BTCUSDT"]
names = sorted(talib.get_function_groups()["Pattern Recognition"])
data = {}
for a in assets:
    df = pd.read_csv(f"{bars_dir}/{a}_15m.csv")
    df = df[df["volume"] > 0].reset_index(drop=True)
    data[a] = {c: df[c].to_numpy(dtype=float) for c in ("open", "high", "low", "close")}
print(f"talib {talib.__version__}; detectors: {len(names)}; bars: " + ", ".join(f"{a}={len(d['open'])}" for a, d in data.items()))
print("| function | display name | lookback | observed values, all assets (value:count) | per asset: fires (distinct values) |")
print("|---|---|---|---|---|")
for n in names:
    f = abstract.Function(n)
    tot = Counter()
    per = []
    for a, d in data.items():
        out = getattr(talib, n)(d["open"], d["high"], d["low"], d["close"])
        c = Counter(int(v) for v in out if v != 0)
        tot.update(c)
        per.append(f"{a}: {sum(c.values())} ({','.join(str(k) for k in sorted(c))})")
    vals = ", ".join(f"{k}:{tot[k]}" for k in sorted(tot)) or "never fired"
    print(f"| {n} | {f.info['display_name']} | {f.lookback} | {vals} | {'; '.join(per)} |")
