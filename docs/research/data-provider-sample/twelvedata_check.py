"""Throwaway: with a real Twelve Data key, report plan usage and the earliest 15-minute bar per symbol.

Usage: python twelvedata_check.py <env_file> <symbol> [<symbol> ...]

Reads TWELVE_DATA_API_KEY from <env_file>. Never prints it.
"""
import json
import sys
import time
import urllib.parse
import urllib.request

BASE = "https://api.twelvedata.com/"


def load_key(path):
    for line in open(path, encoding="utf-8"):
        if line.strip().startswith("TWELVE_DATA_API_KEY="):
            key = line.split("=", 1)[1].strip().strip('"').strip("'")
            if key:
                return key
    sys.exit("TWELVE_DATA_API_KEY is missing or empty in the env file")


def call(key, endpoint, **params):
    params["apikey"] = key
    req = urllib.request.Request(
        BASE + endpoint + "?" + urllib.parse.urlencode(params), headers={"User-Agent": "python-client"}
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        text = r.read().decode("utf-8", "replace").replace(key, "<key>")
    return json.loads(text)


def main(env_file, symbols):
    key = load_key(env_file)
    print("usage before:", json.dumps(call(key, "api_usage")), flush=True)
    for s in symbols:
        time.sleep(8)
        print(s, json.dumps(call(key, "earliest_timestamp", symbol=s, interval="15min")), flush=True)
    time.sleep(8)
    print("usage after:", json.dumps(call(key, "api_usage")), flush=True)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
