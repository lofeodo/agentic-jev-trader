"""Throwaway: what does Twelve Data's free plan give for crypto 15-minute bars?

Usage: python td_crypto_check.py <env file>
"""
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://api.twelvedata.com/"


def key_from(env_file):
    for line in open(env_file, encoding="utf-8"):
        if line.strip().startswith("TWELVE_DATA_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    sys.exit("no key")


def get(path, key, **params):
    params["apikey"] = key
    req = urllib.request.Request(
        BASE + path + "?" + urllib.parse.urlencode(params), headers={"User-Agent": "python-client"}
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read())
        except Exception:
            return {"code": e.code, "status": "error"}


def main(env_file):
    key = key_from(env_file)
    listing = get("cryptocurrencies", key, symbol="BTC/USD")
    for row in listing.get("data", [])[:5]:
        print("listing:", json.dumps(row))
    time.sleep(8)
    for symbol, exchange in [("BTC/USD", None), ("BTC/USD", "Coinbase Pro"), ("BTC/USD", "Kraken"),
                             ("BTC/USD", "Bitstamp"), ("ETH/USD", None)]:
        p = {"symbol": symbol, "interval": "15min"}
        if exchange:
            p["exchange"] = exchange
        e = get("earliest_timestamp", key, **p)
        print("earliest", symbol, exchange, json.dumps(e))
        time.sleep(8)
        p.update({"start_date": "2026-11-03 00:00:00", "end_date": "2026-11-10 00:00:00",
                  "outputsize": 5000, "order": "ASC", "timezone": "UTC"})
        t = get("time_series", key, **p)
        vals = t.get("values", [])
        print("  meta:", json.dumps(t.get("meta", {k: v for k, v in t.items() if k != "values"})))
        print("  bars in 7 days:", len(vals), "(672 expected)")
        if vals:
            print("  first:", json.dumps(vals[0]))
            print("  last :", json.dumps(vals[-1]))
            print("  has volume:", "volume" in vals[0])
        time.sleep(8)


if __name__ == "__main__":
    main(sys.argv[1])
