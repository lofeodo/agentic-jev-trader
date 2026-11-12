"""Throwaway: page Coinbase Exchange public 15-minute candles and report depth and gaps.

Usage: python coinbase_sample.py <out_dir> <product> [<product> ...]
"""
import csv
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

BASE = "https://api.exchange.coinbase.com/products/{p}/candles?granularity=900&start={s}&end={e}"
STEP = 900
WINDOW = 300 * STEP
CRAWL_START = int(datetime(2015, 1, 1, tzinfo=timezone.utc).timestamp())


def iso(ts):
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch(product, start, end):
    url = BASE.format(p=product, s=iso(start), e=iso(end))
    for attempt in range(8):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "python-client"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(1.5 * (attempt + 1))
                continue
            raise
        except (urllib.error.URLError, TimeoutError):
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"gave up on {url}")


def crawl(product, out_dir):
    now = int(time.time()) // STEP * STEP
    bars = {}
    requests = 0
    start = CRAWL_START
    while start < now:
        end = min(start + WINDOW - STEP, now)
        rows = fetch(product, start, end)
        requests += 1
        for t, lo, hi, op, cl, vol in rows:
            bars[t] = (lo, hi, op, cl, vol)
        start = end + STEP
        time.sleep(0.2)
    ts = sorted(bars)
    with open(f"{out_dir}/coinbase_{product}_15m.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["time_utc", "low", "high", "open", "close", "volume"])
        for t in ts:
            w.writerow([iso(t), *bars[t]])

    gaps = []
    for a, b in zip(ts, ts[1:]):
        if b - a > STEP:
            gaps.append((a + STEP, b - STEP, (b - a) // STEP - 1))
    per_year = {}
    for t in ts:
        y = datetime.fromtimestamp(t, tz=timezone.utc).year
        per_year.setdefault(y, {"bars": 0, "missing": 0, "gaps": 0, "zero_volume": 0})
        per_year[y]["bars"] += 1
        if bars[t][4] == 0:
            per_year[y]["zero_volume"] += 1
    for s, e, n in gaps:
        y = datetime.fromtimestamp(s, tz=timezone.utc).year
        per_year[y]["missing"] += n
        per_year[y]["gaps"] += 1
    off_grid = sum(1 for t in ts if t % STEP)
    bad_ohlc = sum(
        1 for t in ts if not (bars[t][0] <= min(bars[t][2], bars[t][3]) and bars[t][1] >= max(bars[t][2], bars[t][3]))
    )
    summary = {
        "product": product,
        "requests": requests,
        "first_bar": iso(ts[0]),
        "last_bar": iso(ts[-1]),
        "bars": len(ts),
        "missing_bars_total": sum(n for _, _, n in gaps),
        "gap_count": len(gaps),
        "off_grid_timestamps": off_grid,
        "bars_with_inconsistent_ohlc": bad_ohlc,
        "per_year": per_year,
        "longest_gaps": [
            {"from": iso(s), "to": iso(e), "missing_bars": n}
            for s, e, n in sorted(gaps, key=lambda g: -g[2])[:15]
        ],
    }
    with open(f"{out_dir}/coinbase_{product}_summary.json", "w") as f:
        json.dump(summary, f, indent=2)
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    out = sys.argv[1]
    for p in sys.argv[2:]:
        crawl(p, out)
