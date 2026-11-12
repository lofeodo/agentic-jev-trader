"""Throwaway: page Twelve Data 15-minute bars for one stock with the public demo key.

Usage: python twelvedata_sample.py <out_dir> <symbol> <apikey or env file>
"""
import csv
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import date, datetime, timedelta

URL = "https://api.twelvedata.com/time_series?"


def fetch(symbol, key, start, end):
    q = urllib.parse.urlencode(
        {
            "symbol": symbol,
            "interval": "15min",
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "outputsize": 5000,
            "order": "ASC",
            "apikey": key,
        }
    )
    for attempt in range(6):
        req = urllib.request.Request(URL + q, headers={"User-Agent": "python-client"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                body = json.loads(r.read())
        except urllib.error.HTTPError as e:
            # An empty date range comes back as HTTP 400, rate limiting as HTTP 429.
            body = {"code": e.code, "status": "error"}
        if body.get("status") == "ok":
            return body["values"]
        if body.get("code") == 429:
            print("rate limited, waiting", flush=True)
            time.sleep(65)
            continue
        if body.get("code") == 400:
            return []
        raise RuntimeError(body)
    raise RuntimeError("gave up")


def main(out_dir, symbol, key):
    rows = {}
    start = date(2019, 9, 1)
    today = date.today()
    requests = 0
    while start <= today:
        end = min(start + timedelta(days=150), today + timedelta(days=1))
        vals = fetch(symbol, key, start, end)
        requests += 1
        if len(vals) >= 5000:
            print("WARNING window hit 5000 cap", start, end, flush=True)
        for v in vals:
            rows[v["datetime"]] = v
        print(start, end, len(vals), flush=True)
        start = end
        time.sleep(8)
    keys = sorted(rows)
    with open(f"{out_dir}/twelvedata_{symbol}_15m.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["datetime_exchange_local", "open", "high", "low", "close", "volume"])
        for k in keys:
            v = rows[k]
            w.writerow([k, v["open"], v["high"], v["low"], v["close"], v["volume"]])

    per_day = Counter(k[:10] for k in keys)
    times = Counter(k[11:] for k in keys)
    days = sorted(per_day)
    first, last = date.fromisoformat(days[0]), date.fromisoformat(days[-1])
    weekdays_missing = []
    d = first
    while d <= last:
        if d.weekday() < 5 and d.isoformat() not in per_day:
            weekdays_missing.append(d.isoformat())
        d += timedelta(days=1)
    short_days = {d: n for d, n in per_day.items() if n != 26}
    per_year = {}
    for d, n in per_day.items():
        y = d[:4]
        py = per_year.setdefault(y, {"days": 0, "bars": 0, "days_not_26_bars": 0, "volume": 0})
        py["days"] += 1
        py["bars"] += n
        py["days_not_26_bars"] += n != 26
    for k in keys:
        per_year[k[:4]]["volume"] += int(rows[k]["volume"])
    for y in per_year:
        per_year[y]["avg_daily_volume"] = per_year[y].pop("volume") // per_year[y]["days"]
    # price continuity around the 4-for-1 split on 2020-08-31
    split = {k: rows[k]["close"] for k in keys if k.startswith(("2020-08-28 15:45", "2020-08-31 09:30"))}
    summary = {
        "symbol": symbol,
        "requests": requests,
        "first_bar": keys[0],
        "last_bar": keys[-1],
        "bars": len(keys),
        "trading_days": len(days),
        "distinct_bar_times": dict(sorted(times.items())),
        "weekdays_with_no_bars": weekdays_missing,
        "days_without_exactly_26_bars": dict(sorted(short_days.items())),
        "per_year": dict(sorted(per_year.items())),
        "closes_around_2020_split": split,
    }
    with open(f"{out_dir}/twelvedata_{symbol}_summary.json", "w") as f:
        json.dump(summary, f, indent=2)
    print(json.dumps(summary, indent=2))


def resolve_key(arg):
    """Accept a literal key (e.g. `demo`) or the path of an env file holding TWELVE_DATA_API_KEY."""
    if not os.path.isfile(arg):
        return arg
    for line in open(arg, encoding="utf-8"):
        if line.strip().startswith("TWELVE_DATA_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    sys.exit("TWELVE_DATA_API_KEY not found in the env file")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], resolve_key(sys.argv[3]))
