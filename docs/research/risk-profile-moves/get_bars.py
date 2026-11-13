import sys
from datetime import date
import download_bars as d
d.START, d.LAST = date(2024, 3, 10), date(2025, 3, 9)
out, envf = sys.argv[1], sys.argv[2]
# crypto: only the months needed
import csv
from datetime import datetime, timezone
mos = ["2024-%02d" % m for m in range(3, 13)] + ["2025-%02d" % m for m in range(1, 4)]
rows = {}
for mo in mos:
    for t, o, h, l, c, v in d.binance_month("BTCUSDT", mo):
        rows[t] = (o, h, l, c, v)
with open(f"{out}/BTCUSDT_15m.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(["datetime", "open", "high", "low", "close", "volume"])
    for t in sorted(rows):
        dt = datetime.fromtimestamp(t, timezone.utc)
        if d.START <= dt.date() <= d.LAST:
            w.writerow([dt.strftime("%Y-%m-%d %H:%M:%S"), *rows[t]])
print("btc done", flush=True)
d.stocks(out, d.resolve_key(envf))
