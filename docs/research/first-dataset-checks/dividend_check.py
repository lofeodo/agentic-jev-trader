"""Throwaway: does Twelve Data's adjust=all correct 15-minute bars for dividends?

For each symbol, pull about a year of 15-minute bars twice (adjust=splits and adjust=all),
take each day's last close, and print the days where the ratio all/splits steps. A step of
about dividend/price on the ex-dividend day means dividends are corrected.

Usage: python dividend_check.py <env file> <symbol> [<symbol> ...]
"""
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta

URL = "https://api.twelvedata.com/time_series?"


def key_from(env_file):
    for line in open(env_file, encoding="utf-8"):
        if line.strip().startswith("TWELVE_DATA_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    sys.exit("no key")


def fetch(symbol, key, start, end, adjust):
    q = urllib.parse.urlencode(
        {
            "symbol": symbol,
            "interval": "15min",
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "outputsize": 5000,
            "order": "ASC",
            "adjust": adjust,
            "apikey": key,
        }
    )
    for _ in range(6):
        req = urllib.request.Request(URL + q, headers={"User-Agent": "python-client"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                body = json.loads(r.read())
        except urllib.error.HTTPError as e:
            body = {"code": e.code, "status": "error"}
        if body.get("status") == "ok":
            return body["values"]
        if body.get("code") == 429:
            time.sleep(65)
            continue
        if body.get("code") == 400:
            return []
        raise RuntimeError({k: v for k, v in body.items() if k != "apikey"})
    raise RuntimeError("gave up")


def daily_last_close(symbol, key, adjust):
    out = {}
    start = date(2025, 10, 1)
    stop = date(2026, 11, 10)
    while start < stop:
        end = min(start + timedelta(days=150), stop)
        for v in fetch(symbol, key, start, end, adjust):
            out[v["datetime"][:10]] = float(v["close"])
        start = end
        time.sleep(8)
    return out


def main(env_file, symbols):
    key = key_from(env_file)
    for symbol in symbols:
        s = daily_last_close(symbol, key, "splits")
        a = daily_last_close(symbol, key, "all")
        days = sorted(set(s) & set(a))
        print(f"== {symbol}: {len(days)} days, {days[0]} to {days[-1]}")
        print(f"   first day close splits={s[days[0]]:.2f} all={a[days[0]]:.2f}; "
              f"last day close splits={s[days[-1]]:.2f} all={a[days[-1]]:.2f}")
        prev = None
        for d in days:
            ratio = a[d] / s[d]
            if prev is not None and abs(ratio - prev) > 0.0003:
                implied = (ratio - prev) / ratio * s[d]
                print(f"   step on {d}: ratio {prev:.5f} -> {ratio:.5f} "
                      f"(implied dividend about ${implied:.2f} on a ${s[d]:.2f} share)")
            prev = ratio


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
