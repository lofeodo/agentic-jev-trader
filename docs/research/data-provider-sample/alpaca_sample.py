"""Throwaway: pull Alpaca 15-minute stock bars and compare the single-exchange and all-exchange feeds.

Usage: python alpaca_sample.py <env_file> <out_dir> <symbol> [<twelvedata_csv>]

Reads ALPACA_API_KEY and ALPACA_API_SECRET from <env_file>. Never prints them.
"""
import csv
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

URL = "https://data.alpaca.markets/v2/stocks/bars?"
NY = ZoneInfo("America/New_York")
HISTORY_START = "2016-01-01T00:00:00Z"


def load_env(path):
    env = {}
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def fetch_all(env, symbol, feed, adjustment, start, end):
    """Return (bars, error). bars is a list of dicts with t, o, h, l, c, v."""
    bars, token, requests = [], None, 0
    while True:
        q = {
            "symbols": symbol,
            "timeframe": "15Min",
            "start": start,
            "end": end,
            "limit": 10000,
            "adjustment": adjustment,
            "feed": feed,
            "sort": "asc",
        }
        if token:
            q["page_token"] = token
        req = urllib.request.Request(
            URL + urllib.parse.urlencode(q),
            headers={
                "APCA-API-KEY-ID": env["ALPACA_API_KEY"],
                "APCA-API-SECRET-KEY": env["ALPACA_API_SECRET"],
                "User-Agent": "python-client",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                body = json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(20)
                continue
            return bars, f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:300]}"
        requests += 1
        bars.extend((body.get("bars") or {}).get(symbol, []))
        token = body.get("next_page_token")
        if not token:
            return bars, None
        time.sleep(0.4)


def summarize(bars):
    """Split bars into regular hours (09:30 to 15:45 New York) and the rest; count per day and year."""
    days = defaultdict(lambda: {"bars": 0, "volume": 0})
    outside = 0
    for b in bars:
        t = datetime.fromisoformat(b["t"].replace("Z", "+00:00")).astimezone(NY)
        hm = t.hour * 60 + t.minute
        if 9 * 60 + 30 <= hm <= 15 * 60 + 45:
            d = days[t.date().isoformat()]
            d["bars"] += 1
            d["volume"] += b["v"]
        else:
            outside += 1
    per_year = defaultdict(lambda: {"days": 0, "bars": 0, "days_not_26_bars": 0, "volume": 0})
    for d, v in days.items():
        y = per_year[d[:4]]
        y["days"] += 1
        y["bars"] += v["bars"]
        y["days_not_26_bars"] += v["bars"] != 26
        y["volume"] += v["volume"]
    for y in per_year.values():
        y["avg_daily_volume"] = round(y.pop("volume") / y["days"])
    return {
        "first_bar": bars[0]["t"] if bars else None,
        "last_bar": bars[-1]["t"] if bars else None,
        "bars_total": len(bars),
        "bars_outside_regular_hours": outside,
        "trading_days": len(days),
        "per_year": dict(sorted(per_year.items())),
        "days_not_26_bars": {d: v["bars"] for d, v in sorted(days.items()) if v["bars"] != 26},
    }, days


def main(env_file, out_dir, symbol, td_csv=None):
    env = load_env(env_file)
    if not env.get("ALPACA_API_KEY") or not env.get("ALPACA_API_SECRET"):
        sys.exit("ALPACA_API_KEY or ALPACA_API_SECRET is empty in the env file")
    now = datetime.now(timezone.utc)
    ends = {
        "now minus 20 minutes": (now - timedelta(minutes=20)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "now minus 1 day": (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    report, daily = {"symbol": symbol, "run_at": now.isoformat()}, {}
    for feed in ("iex", "sip"):
        for label, end in ends.items():
            bars, err = fetch_all(env, symbol, feed, "all", HISTORY_START, end)
            if not err:
                break
            print(f"{feed} ending {label}: {err}", flush=True)
        entry = {"end_used": label, "error": err}
        if bars:
            entry["summary"], daily[feed] = summarize(bars)
            with open(f"{out_dir}/alpaca_{symbol}_{feed}_15m.csv", "w", newline="") as f:
                w = csv.writer(f)
                w.writerow(["time_utc", "open", "high", "low", "close", "volume"])
                for b in bars:
                    w.writerow([b["t"], b["o"], b["h"], b["l"], b["c"], b["v"]])
        report[feed] = entry

    # Adjustment check around Apple's 4-for-1 split on 2020-08-31 (only meaningful for AAPL).
    split = {}
    for adj in ("raw", "split", "all"):
        feed = "sip" if "sip" in daily else "iex"
        bars, err = fetch_all(env, symbol, feed, adj, "2020-08-28T19:30:00Z", "2020-08-31T14:00:00Z")
        split[adj] = err or {b["t"]: b["c"] for b in bars[:1] + bars[-1:]}
    report["closes_around_2020_split_by_adjustment"] = split

    # Daily regular-hours volume side by side for the last 15 finished days.
    td = defaultdict(int)
    if td_csv:
        for r in csv.DictReader(open(td_csv)):
            td[r["datetime_exchange_local"][:10]] += int(r["volume"])
    all_days = sorted(set().union(*[set(d) for d in daily.values()])) if daily else []
    today = now.astimezone(NY).date().isoformat()
    compare = []
    for d in [d for d in all_days if d < today][-15:]:
        row = {"day": d}
        for feed, days in daily.items():
            row[feed] = round(days[d]["volume"]) if d in days else None
        if td:
            row["twelvedata"] = td.get(d)
        compare.append(row)
    report["daily_volume_last_15_days"] = compare

    with open(f"{out_dir}/alpaca_{symbol}_summary.json", "w") as f:
        json.dump(report, f, indent=2)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main(*sys.argv[1:5])
