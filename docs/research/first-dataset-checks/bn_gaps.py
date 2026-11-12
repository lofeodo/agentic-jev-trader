"""Throwaway: download Binance Vision monthly 15m klines and count missing bars per year."""
import io, sys, urllib.request, zipfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

def months():
    y, m = 2017, 8
    while (y, m) <= (2026, 10):
        yield f"{y}-{m:02d}"
        m += 1
        if m == 13: y, m = y + 1, 1

def get(sym, mo):
    url = f"https://data.binance.vision/data/spot/monthly/klines/{sym}/15m/{sym}-15m-{mo}.zip"
    try:
        raw = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "python-client"}), timeout=60).read()
    except Exception as e:
        return mo, None, str(e)
    z = zipfile.ZipFile(io.BytesIO(raw))
    rows = []
    for line in z.read(z.namelist()[0]).decode().strip().splitlines():
        p = line.split(",")
        if not p[0].isdigit(): continue
        t = int(p[0])
        if t > 10**14: t //= 1000  # microseconds from 2025
        rows.append((t // 1000, float(p[5])))
    return mo, rows, None

for sym in sys.argv[1:]:
    with ThreadPoolExecutor(8) as ex:
        res = list(ex.map(lambda mo: get(sym, mo), months()))
    failed = [(mo, e) for mo, r, e in res if r is None]
    ts = sorted({t: v for mo, r, e in res if r for t, v in r}.items())
    print(f"== {sym}: {len(ts)} bars, files failed: {failed}")
    f = lambda t: datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d %H:%M")
    print("   first", f(ts[0][0]), "last", f(ts[-1][0]), "off-grid", sum(t % 900 != 0 for t, _ in ts), "zero-volume bars", sum(v == 0 for _, v in ts))
    miss = Counter(); gaps = []
    for (a, _), (b, _) in zip(ts, ts[1:]):
        n = (b - a) // 900 - 1
        if n > 0:
            miss[f(a)[:4]] += n; gaps.append((n, f(a + 900), f(b)))
    zero = Counter(f(t)[:4] for t, v in ts if v == 0)
    print("   missing bars per year:", dict(sorted(miss.items())), "total", sum(miss.values()))
    print("   zero-volume bars per year:", dict(sorted(zero.items())))
    for n, a, b in sorted(gaps, reverse=True)[:12]:
        print(f"   gap of {n} bars ({n/4:.1f} h): {a} -> {b}")
    print("   gaps since 2021:", [(n, a) for n, a, b in gaps if a >= "2021"])
