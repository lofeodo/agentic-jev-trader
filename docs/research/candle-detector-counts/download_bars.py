"""Download 15-minute bars for the candle-detector counts. Raw bars are written OUTSIDE the repo.

Usage: python download_bars.py <out_dir> <env_file> [stocks|crypto|all]
Range: 2022-01-03 through 2026-04-30 only (later data is the project's unseen test period).
"""
import csv, io, json, sys, time, urllib.error, urllib.parse, urllib.request, zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone

START, LAST = date(2022, 1, 3), date(2026, 4, 30)
STOCKS = ["SPY", "AAPL", "JPM", "XOM"]
URL = "https://api.twelvedata.com/time_series?"


def resolve_key(path):
    for line in open(path, encoding="utf-8"):
        if line.strip().startswith("TWELVE_DATA_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    sys.exit("TWELVE_DATA_API_KEY not found")


def fetch(symbol, key, start, end):
    q = urllib.parse.urlencode({
        "symbol": symbol, "interval": "15min", "start_date": start, "end_date": end,
        "outputsize": 5000, "order": "ASC", "adjust": "all", "apikey": key})
    for _ in range(8):
        req = urllib.request.Request(URL + q, headers={"User-Agent": "python-client"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                body = json.loads(r.read())
        except urllib.error.HTTPError as e:
            body = {"code": e.code, "status": "error"}
        if body.get("status") == "ok":
            return body["values"]
        if body.get("code") == 429:
            print("rate limited, waiting 65 s", flush=True)
            time.sleep(65)
            continue
        if body.get("code") == 400:
            return []
        raise RuntimeError({k: v for k, v in body.items() if k != "apikey"})
    raise RuntimeError("gave up")


def stocks(out_dir, key):
    for sym in STOCKS:
        rows, d, n_req = {}, START, 0
        while d <= LAST:
            e = min(d + timedelta(days=180), LAST + timedelta(days=1))
            end = e.isoformat() + " 00:00:00" if e <= LAST else LAST.isoformat() + " 23:59:59"
            vals = fetch(sym, key, d.isoformat() + " 00:00:00", end)
            n_req += 1
            if len(vals) >= 5000:
                print("WARNING 5000 cap hit", sym, d, flush=True)
            for v in vals:
                if v["datetime"][:10] <= LAST.isoformat():
                    rows[v["datetime"]] = v
            print(sym, d, e, len(vals), flush=True)
            d = e
            time.sleep(9)
        with open(f"{out_dir}/{sym}_15m.csv", "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["datetime", "open", "high", "low", "close", "volume"])
            for k in sorted(rows):
                v = rows[k]
                w.writerow([k, v["open"], v["high"], v["low"], v["close"], v["volume"]])
        print(sym, "bars", len(rows), "requests", n_req, flush=True)


def binance_month(sym, mo):
    url = f"https://data.binance.vision/data/spot/monthly/klines/{sym}/15m/{sym}-15m-{mo}.zip"
    raw = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "python-client"}), timeout=60).read()
    z = zipfile.ZipFile(io.BytesIO(raw))
    out = []
    for line in z.read(z.namelist()[0]).decode().strip().splitlines():
        p = line.split(",")
        if not p[0].isdigit():
            continue
        t = int(p[0])
        if t > 10**14:  # microseconds from 2025
            t //= 1000
        out.append((t // 1000, p[1], p[2], p[3], p[4], p[5]))
    return out


def crypto(out_dir, sym="BTCUSDT"):
    mos, y, m = [], 2022, 1
    while (y, m) <= (2026, 4):
        mos.append(f"{y}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    with ThreadPoolExecutor(6) as ex:
        res = list(ex.map(lambda mo: binance_month(sym, mo), mos))
    rows = {}
    for r in res:
        for t, o, h, l, c, v in r:
            rows[t] = (o, h, l, c, v)
    with open(f"{out_dir}/{sym}_15m.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["datetime", "open", "high", "low", "close", "volume"])
        for t in sorted(rows):
            dt = datetime.fromtimestamp(t, timezone.utc)
            if dt.date() > LAST or dt.date() < START:
                continue
            w.writerow([dt.strftime("%Y-%m-%d %H:%M:%S"), *rows[t]])
    print(sym, "bars", len(rows))


if __name__ == "__main__":
    out, envf = sys.argv[1], sys.argv[2]
    what = sys.argv[3] if len(sys.argv) > 3 else "all"
    if what in ("crypto", "all"):
        crypto(out)
    if what in ("stocks", "all"):
        stocks(out, resolve_key(envf))
