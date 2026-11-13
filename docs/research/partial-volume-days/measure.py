"""Count partial-volume days in Twelve Data's 15-minute stock bars. Raw bars are written OUTSIDE the repo.

Usage: python measure.py <bars_dir> <env_file> <results_md>
Range: 2023-04-03 through 2026-10-31. Only counts and dates are written to <results_md>, never prices.
"""
import csv, json, os, statistics, sys, time, urllib.error, urllib.parse, urllib.request
from collections import defaultdict
from datetime import date, timedelta

START, LAST = date(2023, 4, 3), date(2026, 10, 31)
STOCKS = ["SPY", "AAPL", "JPM", "XOM"]
URL = "https://api.twelvedata.com/time_series?"
SHARE, LOOKBACK, MIN_EARLIER = 0.25, 20, 10
# A day the market closed at 13:00 New York time. Found from the bars (fewer than 20 bar times in the day),
# plus 2023-07-03, where Twelve Data returns zero-volume bars up to the usual close. A real build uses the exchange calendar.
EXTRA_EARLY_CLOSE = {"2023-07-03"}
WINDOWS = [("warm-up period", "2023-04-03", "2023-07-02"), ("spare days", "2023-07-03", "2024-03-09"),
           ("build-up year", "2024-03-10", "2025-03-09"), ("falling market", "2025-03-10", "2025-04-08"),
           ("rising market", "2025-04-09", "2025-05-08"), ("after", "2025-05-09", "2026-10-31")]


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


def load(sym, bars_dir, env_file):
    path = f"{bars_dir}/{sym}_15m.csv"
    if not os.path.exists(path):
        key, rows, d = resolve_key(env_file), {}, START
        while d <= LAST:
            e = min(d + timedelta(days=150), LAST + timedelta(days=1))
            vals = fetch(sym, key, d.isoformat() + " 00:00:00", e.isoformat() + " 00:00:00")
            if len(vals) >= 5000:
                print("WARNING 5000 cap hit", sym, d, flush=True)
            for v in vals:
                rows[v["datetime"]] = v
            d = e
            time.sleep(9)
        with open(path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["datetime", "open", "high", "low", "close", "volume"])
            for k in sorted(rows):
                v = rows[k]
                w.writerow([k, v["open"], v["high"], v["low"], v["close"], v["volume"]])
    return {r["datetime"]: float(r["volume"]) for r in csv.DictReader(open(path))
            if START.isoformat() <= r["datetime"][:10] <= LAST.isoformat()}


def main():
    bars_dir, env_file, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
    data = {sym: load(sym, bars_dir, env_file) for sym in STOCKS}
    all_ts = set().union(*[set(v) for v in data.values()])
    times = defaultdict(set)
    for t in all_ts:
        times[t[:10]].add(t[11:16])
    early = {d for d in times if len(times[d]) < 20} | EXTRA_EARLY_CLOSE

    def in_hours(t):
        return "09:30" <= t[11:16] <= ("12:45" if t[:10] in early else "15:45")

    expected = {t for t in all_ts if in_hours(t)}
    days = sorted({t[:10] for t in expected})
    out = [f"Range {START} to {LAST}: {len(days)} sessions, {len(expected)} bars expected per stock inside its sessions.",
           f"Early-close days: {', '.join(sorted(early))}.", "",
           "| Stock | Bars not supplied | Zero-volume bars (sessions) | Partial-volume days | Share of bars | " + " | ".join(w[0] for w in WINDOWS) + " |",
           "|---|---|---|---|---|" + "---|" * len(WINDOWS)]
    detail = []
    for sym, vols in data.items():
        sess = {t: v for t, v in vols.items() if in_hours(t)}
        absent = len(expected - set(sess))
        stray_zero = sum(1 for t, v in vols.items() if not in_hours(t) and v == 0)
        tot, n, zero = defaultdict(float), defaultdict(int), defaultdict(int)
        for t, v in sess.items():
            tot[t[:10]] += v
            n[t[:10]] += 1
            zero[t[:10]] += v == 0
        avg = {d: tot[d] / n[d] for d in tot}
        dl = sorted(avg)
        ratio = {}
        for i, d in enumerate(dl):
            prev = [avg[x] for x in dl[max(0, i - LOOKBACK):i]]
            if len(prev) >= MIN_EARLIER:
                ratio[d] = avg[d] / statistics.median(prev)
        zdays = {d for d in zero if zero[d]}
        low = {d for d, r in ratio.items() if r < SHARE}
        flagged = sorted(zdays | low)
        lost = sum(n[d] for d in flagged)
        per_window = [f"{sum(1 for d in flagged if a <= d <= b)} of {sum(1 for d in dl if a <= d <= b)}" for _, a, b in WINDOWS]
        out.append(f"| {sym} | {absent} | {sum(zero.values())} ({len(zdays)}) | {len(flagged)} | {100 * lost / len(expected):.2f}% | " + " | ".join(per_window) + " |")
        caught = sorted(ratio[d] for d in low)
        passed = sorted((r, d) for d, r in ratio.items() if d not in flagged)
        detail += [f"**{sym}**", "",
                   f"- Sessions with a zero-volume bar: {', '.join(sorted(zdays)) or 'none'}.",
                   f"- Sessions under {SHARE:.0%} of the median of the previous {LOOKBACK} sessions (share of usual in brackets): "
                   + (", ".join(f"{d} ({ratio[d]:.0%})" for d in sorted(low)) or "none") + ".",
                   f"- Highest share among sessions the volume test caught: {caught[-1]:.0%}. Lowest share among sessions not flagged: {passed[0][0]:.0%} ({passed[0][1]}), then {passed[1][0]:.0%} and {passed[2][0]:.0%}.",
                   f"- Zero-volume bars outside the session (dropped before the test): {stray_zero}.", ""]
    open(out_path, "w", encoding="utf-8", newline="\n").write("\n".join(out + [""] + detail))
    print("\n".join(out + [""] + detail))


main()
