"""Candle detector firing counts on real 15-minute bars (throwaway measurement for issue #28).

Usage: python analyze.py <bars_dir> <out_results_md>
Reads <bars_dir>/{SPY,AAPL,JPM,XOM,BTCUSDT}_15m.csv (raw bars live outside the repo) and writes
aggregated tables only (no price rows) to the results file.
"""
import sys
from itertools import combinations

import numpy as np
import pandas as pd
import talib

ASSETS = ["SPY", "AAPL", "JPM", "XOM", "BTCUSDT"]
STOCKS = ASSETS[:4]
LAST_DAY = "2026-04-30"

# (name, talib function, sign filter, bars referenced (span), prior-move first-bar offset span,
#  direction for section C (+1 needs a decline, -1 needs an advance, 0 none), direction for section F)
TALIB = [
    ("doji", "CDLDOJI", 1, 1, 1, 0, 0),
    ("dragonfly_doji", "CDLDRAGONFLYDOJI", 1, 1, 1, +1, +1),
    ("gravestone_doji", "CDLGRAVESTONEDOJI", 1, 1, 1, -1, -1),
    ("spinning_top_up", "CDLSPINNINGTOP", 1, 1, 1, 0, +1),
    ("spinning_top_down", "CDLSPINNINGTOP", -1, 1, 1, 0, -1),
    ("marubozu_up", "CDLMARUBOZU", 1, 1, 1, 0, +1),
    ("marubozu_down", "CDLMARUBOZU", -1, 1, 1, 0, -1),
    ("hammer", "CDLHAMMER", 1, 2, 1, +1, +1),
    ("hanging_man", "CDLHANGINGMAN", -1, 2, 1, -1, -1),
    ("inverted_hammer", "CDLINVERTEDHAMMER", 1, 2, 1, +1, +1),
    ("shooting_star", "CDLSHOOTINGSTAR", -1, 2, 1, -1, -1),
    ("engulfing_bull", "CDLENGULFING", 1, 2, 2, +1, +1),
    ("engulfing_bear", "CDLENGULFING", -1, 2, 2, -1, -1),
    ("harami_bull", "CDLHARAMI", 1, 2, 2, +1, +1),
    ("harami_bear", "CDLHARAMI", -1, 2, 2, -1, -1),
    ("piercing", "CDLPIERCING", 1, 2, 2, +1, +1),
    ("dark_cloud", "CDLDARKCLOUDCOVER", -1, 2, 2, -1, -1),
    ("morning_star", "CDLMORNINGSTAR", 1, 3, 3, +1, +1),
    ("evening_star", "CDLEVENINGSTAR", -1, 3, 3, -1, -1),
    ("three_inside_up", "CDL3INSIDE", 1, 3, 3, +1, +1),
    ("three_inside_down", "CDL3INSIDE", -1, 3, 3, -1, -1),
    ("three_white_soldiers", "CDL3WHITESOLDIERS", 1, 3, 3, 0, +1),
    ("three_black_crows", "CDL3BLACKCROWS", -1, 4, 4, 0, -1),
    ("rise_fall_3_up", "CDLRISEFALL3METHODS", 1, 5, 5, 0, +1),
    ("rise_fall_3_down", "CDLRISEFALL3METHODS", -1, 5, 5, 0, -1),
]
TA_NAMES = [t[0] for t in TALIB]


def load(bars_dir, sym):
    df = pd.read_csv(f"{bars_dir}/{sym}_15m.csv")
    df["datetime"] = pd.to_datetime(df["datetime"])
    n_raw = len(df)
    df = df.drop_duplicates("datetime").sort_values("datetime")
    n_zero = int((df["volume"] == 0).sum())
    df = df[df["volume"] != 0].reset_index(drop=True)
    assert df["datetime"].max() <= pd.Timestamp(LAST_DAY + " 23:59:59"), "data past the allowed range"
    return df, dict(raw=n_raw, zero_volume_dropped=n_zero)


class Asset:
    def __init__(self, sym, df, info):
        self.sym, self.info = sym, info
        self.crypto = sym == "BTCUSDT"
        self.o, self.h, self.l, self.c = (df[k].to_numpy(float) for k in ("open", "high", "low", "close"))
        self.n = len(df)
        ts = df["datetime"]
        self.secs = (ts.astype("int64") // 10**9 if ts.dt.tz is None else ts.astype("int64") // 10**9).to_numpy()
        self.secs = ts.values.astype("datetime64[s]").astype("int64")
        self.date = ts.dt.date.to_numpy()
        self.n_days = len(set(self.date))
        dt = np.diff(self.secs, prepend=self.secs[0])
        same_day = np.r_[False, self.date[1:] == self.date[:-1]]
        if self.crypto:
            self.ovn = np.zeros(self.n, bool)
            self.miss = dt > 900
            self.first = np.zeros(self.n, bool)
        else:
            self.ovn = ~same_day
            self.ovn[0] = False
            self.miss = same_day & (dt > 900)
            self.first = ~same_day
        self.consec = (dt == 900)
        self.consec[0] = False
        self.cs_ovn = np.r_[0, np.cumsum(self.ovn)]
        self.cs_miss = np.r_[0, np.cumsum(self.miss)]
        self.atr = talib.ATR(self.h, self.l, self.c, 14)
        self.zero_range = int((self.h == self.l).sum())
        self.build_prior()
        self.entries = {}

    # prior-move flags indexed by f (first bar): uses close[f-1], close[f-5], ATR[f-1]
    def build_prior(self):
        n, c = self.n, self.c
        c1, c5, a1 = np.full(n, np.nan), np.full(n, np.nan), np.full(n, np.nan)
        c1[1:], c5[5:], a1[1:] = c[:-1], c[:-5], self.atr[:-1]
        with np.errstate(invalid="ignore"):
            self.decl_i = c1 < c5
            self.adv_i = c1 > c5
            self.decl_ii = (c5 - c1) >= a1
            self.adv_ii = (c1 - c5) >= a1
        for k in ("decl_i", "adv_i", "decl_ii", "adv_ii"):
            getattr(self, k)[:5] = False

    def add(self, name, fire, span, fspan, cdir, fdir, both=False, group=""):
        fire = np.asarray(fire, bool).copy()
        fire[: max(span, 1) - 1] = False
        self.entries[name] = dict(fire=fire, span=span, fspan=fspan, cdir=cdir, fdir=fdir, both=both, group=group)

    def straddle(self, idx, span):
        if span <= 1:
            return np.zeros(len(idx), bool), np.zeros(len(idx), bool)
        a = np.clip(idx - span + 2, 0, None)
        return (self.cs_ovn[idx + 1] - self.cs_ovn[a]) > 0, (self.cs_miss[idx + 1] - self.cs_miss[a]) > 0

    def prior(self, e, kind):  # kind in decl_i, decl_ii, adv_i, adv_ii; returns survivors count
        idx = np.flatnonzero(e["fire"])
        f = idx - (e["fspan"] - 1)
        ok = f >= 0
        return int(getattr(self, kind)[f[ok]].sum())


def sma_prev(x, n):
    """Mean of the n values BEFORE each index (TA-Lib's 'average of the previous n candles')."""
    s = pd.Series(x).rolling(n).mean().shift(1)
    return s.to_numpy()


def ta_entries(a):
    for name, fn, sign, span, fspan, cdir, fdir in TALIB:
        out = getattr(talib, fn)(a.o, a.h, a.l, a.c)
        a.add(name, out > 0 if sign > 0 else out < 0, span, fspan, cdir, fdir, group="talib")
    eng = talib.CDLENGULFING(a.o, a.h, a.l, a.c)
    a.add("engulfing_bull_strict100", eng == 100, 2, 2, +1, +1, group="extra")
    a.add("engulfing_bear_strict100", eng == -100, 2, 2, -1, -1, group="extra")
    a.engulf_raw = eng


def relaxed_entries(a):
    o, h, l, c = a.o, a.h, a.l, a.c
    body = np.abs(c - o)
    ab = sma_prev(body, 10)  # average body of previous 10, evaluated "at" each bar
    ar = sma_prev(h - l, 10)  # average high-low range of previous 10
    up, down = c >= o, c < o
    with np.errstate(invalid="ignore"):
        long_ = body > ab
        short_ = body < ab
        shortle = body <= ab
    p = lambda x: np.r_[False, x[:-1]]  # value at i-1 seen from i
    p2 = lambda x: np.r_[False, False, x[:-2]]
    sh = lambda x, k: np.r_[np.full(k, np.nan), x[:-k]]
    o1, c1, b1 = sh(o, 1), sh(c, 1), sh(body, 1)
    o2, c2, b2 = sh(o, 2), sh(c, 2), sh(body, 2)
    with np.errstate(invalid="ignore"):
        pierc = p(down) & p(long_) & up & long_ & (o <= c1) & (c < o1) & (c > c1 + 0.5 * b1)
        dcc = p(up) & p(long_) & down & long_ & (o >= c1) & (c > o1) & (c < c1 - 0.5 * b1)
        # morning star: bar1 = i-2, bar2 = i-1 (short), bar3 = i
        top2 = np.maximum(sh(o, 1), sh(c, 1))
        bot2 = np.minimum(sh(o, 1), sh(c, 1))
        ms_base = p2(down) & p2(long_) & p(shortle) & up & (body > ab) & (c > c2 + 0.3 * b2)
        es_base = p2(up) & p2(long_) & p(shortle) & down & (body > ab) & (c < c2 - 0.3 * b2)
        ms_touch = ms_base & (top2 <= c2)
        es_touch = es_base & (bot2 >= c2)
        # hammer / inverted hammer shapes without any previous-bar condition
        lower = np.minimum(o, c) - l
        upper = h - np.maximum(o, c)
        ham = short_ & (lower > body) & (upper < 0.1 * ar)
        inv = short_ & (upper > body) & (lower < 0.1 * ar)
    a.add("piercing_relaxed", pierc, 2, 2, +1, +1, group="relaxed")
    a.add("dark_cloud_relaxed", dcc, 2, 2, -1, -1, group="relaxed")
    a.add("morning_star_relaxed_touch", ms_touch, 3, 3, +1, +1, group="relaxed")
    a.add("morning_star_relaxed_any", ms_base, 3, 3, +1, +1, group="relaxed")
    a.add("evening_star_relaxed_touch", es_touch, 3, 3, -1, -1, group="relaxed")
    a.add("evening_star_relaxed_any", es_base, 3, 3, -1, -1, group="relaxed")
    a.add("hammer_shape_no_prev_test", ham, 1, 1, 0, 0, both=True, group="shape")
    a.add("inverted_hammer_shape_no_gap", inv, 1, 1, 0, 0, both=True, group="shape")
    # shapes conditioned on prior move (definition (i)) for section F
    for nm, f in (("hammer_shape", ham), ("inverted_hammer_shape", inv)):
        a.add(f"{nm}_after_decline_i", f & a.decl_i, 1, 1, +1, +1, group="shape_f")
        a.add(f"{nm}_after_advance_i", f & a.adv_i, 1, 1, -1, -1, group="shape_f")


TOLS = (0.05, 0.10, 0.20)


def tweezer_entries(a):
    o, h, l, c = a.o, a.h, a.l, a.c
    sh = lambda x: np.r_[np.nan, x[:-1]]
    l1, h1, o1, c1 = sh(l), sh(h), sh(o), sh(c)
    consec = a.consec
    ovn_pair = a.ovn  # stocks: bar i first of a new date (pair crosses overnight)
    for tol in TOLS:
        with np.errstate(invalid="ignore"):
            bot = np.abs(l - l1) <= tol * a.atr
            top = np.abs(h - h1) <= tol * a.atr
            bot_b = bot & (c1 < o1) & (c >= o)
            top_b = top & (c1 >= o1) & (c < o)
        for tag, same, ov in (("", consec, None), ("_overnight", None, ovn_pair)):
            m = same if ov is None else ov
            if m is None or (ov is not None and a.crypto):
                continue
            a.add(f"tweezer_bottom_a_tol{tol:.2f}{tag}", bot & m, 2, 2, +1, +1, group="tweezer")
            a.add(f"tweezer_bottom_b_tol{tol:.2f}{tag}", bot_b & m, 2, 2, +1, +1, group="tweezer")
            a.add(f"tweezer_top_a_tol{tol:.2f}{tag}", top & m, 2, 2, -1, -1, group="tweezer")
            a.add(f"tweezer_top_b_tol{tol:.2f}{tag}", top_b & m, 2, 2, -1, -1, group="tweezer")


# ---------------------------------------------------------------- tables
def md(header, rows):
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    out += ["| " + " | ".join(str(x) for x in r) + " |" for r in rows]
    return "\n".join(out) + "\n"


def pct(x, n, d=2):
    return f"{100 * x / n:.{d}f}%" if n else "-"


def stats_A(A, names, title):
    L = [f"#### {title}\n"]
    rows = []
    for nm in names:
        r = [nm]
        for s in ASSETS:
            a = A[s]
            e = a.entries.get(nm)
            r.append("n/a" if e is None else f"{int(e['fire'].sum())} ({pct(e['fire'].sum(), a.n)})")
        rows.append(r)
    L.append("Firings (percent of all bars)\n")
    L.append(md(["entry"] + ASSETS, rows))
    rows = []
    for nm in names:
        r = [nm]
        for s in ASSETS:
            a = A[s]
            e = a.entries.get(nm)
            r.append("n/a" if e is None else f"{e['fire'].sum() / a.n_days:.3f}")
        rows.append(r)
    L.append("Average firings per calendar day with bars\n")
    L.append(md(["entry"] + ASSETS, rows))
    rows = []
    for nm in names:
        r = [nm]
        for s in STOCKS:
            a = A[s]
            e = a.entries.get(nm)
            if e is None:
                r.append("n/a")
                continue
            nf = int((e["fire"] & a.first).sum())
            no = int(e["fire"].sum()) - nf
            r.append(f"{nf} first / {no} other")
        rows.append(r)
    L.append("Stocks: firing bar is the first bar of the session / any other bar (the first bar is about 1 in 26 of all bars)\n")
    L.append(md(["entry"] + STOCKS, rows))
    rows = []
    for nm in names:
        e0 = A["SPY"].entries.get(nm)
        if e0 is None or e0["span"] <= 1:
            continue
        r = [nm, e0["span"]]
        for s in ASSETS:
            a = A[s]
            e = a.entries.get(nm)
            if e is None:
                r.append("n/a")
                continue
            idx = np.flatnonzero(e["fire"])
            ov, ms = a.straddle(idx, e["span"])
            if a.crypto:
                r.append(f"missing-bar {int(ms.sum())}")
            else:
                r.append(f"overnight {pct(ov.sum(), len(idx), 1)} ({int(ov.sum())}); missing-bar {int(ms.sum())}")
        rows.append(r)
    L.append("Multi-bar entries: firings whose bars straddle an overnight boundary (stocks; share of firings and count) and the count straddling a missing bar (all assets). 'bars' = number of bars the detector looks at\n")
    L.append(md(["entry", "bars"] + ASSETS, rows))
    return "\n".join(L)


def stats_C(A, names, title):
    L = [f"#### {title}\n"]
    L.append("Cells: firings, then how many (percent of firings) survive prior-move test (i) = close[f-1] vs close[f-5], and (ii) = move of at least 1.0 x ATR(14) at f-1. Bearish entries need a prior advance, bullish a prior decline. Rows marked 'after decline'/'after advance' belong to shape entries with no direction of their own.\n")
    rows = []
    for nm in names:
        e0 = A["SPY"].entries.get(nm)
        if e0 is None:
            continue
        variants = [("", e0["cdir"])] if not e0["both"] else [(" after decline", +1), (" after advance", -1)]
        if not e0["both"] and e0["cdir"] == 0:
            continue
        for suff, d in variants:
            r = [nm + suff]
            for s in ASSETS:
                a = A[s]
                e = a.entries.get(nm)
                if e is None:
                    r.append("n/a")
                    continue
                n = int(e["fire"].sum())
                ki, kii = ("decl_i", "decl_ii") if d > 0 else ("adv_i", "adv_ii")
                si, sii = a.prior(e, ki), a.prior(e, kii)
                r.append(f"{n}: (i) {si} ({pct(si, n, 1)}), (ii) {sii} ({pct(sii, n, 1)})")
            rows.append(r)
    L.append(md(["entry"] + ASSETS, rows))
    return "\n".join(L)


def baseline_C(A):
    rows = []
    for k, lab in (("decl_i", "decline (i)"), ("decl_ii", "decline (ii)"), ("adv_i", "advance (i)"), ("adv_ii", "advance (ii)")):
        rows.append([lab] + [pct(getattr(A[s], k).sum(), A[s].n, 1) for s in ASSETS])
    return md(["share of ALL bars satisfying"] + ASSETS, rows)


def table_B(A):
    L = []
    rows = []
    groups = {
        "all 25 TA-Lib entries": [],
        "without doji, spinning top (both), engulfing (both), harami (both)": ["doji", "spinning_top_up", "spinning_top_down", "engulfing_bull", "engulfing_bear", "harami_bull", "harami_bear"],
        "same, also without dragonfly and gravestone doji (whole doji family)": ["doji", "dragonfly_doji", "gravestone_doji", "spinning_top_up", "spinning_top_down", "engulfing_bull", "engulfing_bear", "harami_bull", "harami_bear"],
        "without engulfing at +-80 only (strict +-100 engulfing kept)": None,
    }
    for lab, drop in groups.items():
        r = [lab]
        for s in ASSETS:
            a = A[s]
            keep = np.zeros(a.n, bool)
            if drop is None:
                for nm in TA_NAMES:
                    if nm not in ("engulfing_bull", "engulfing_bear"):
                        keep |= a.entries[nm]["fire"]
                keep |= a.entries["engulfing_bull_strict100"]["fire"] | a.entries["engulfing_bear_strict100"]["fire"]
            else:
                for nm in TA_NAMES:
                    if nm not in drop:
                        keep |= a.entries[nm]["fire"]
            valid = np.arange(a.n) >= 14  # detectors are blank for the first 14 bars
            r.append(pct((~keep & valid).sum(), valid.sum(), 1))
        rows.append(r)
    L.append("Percent of bars (after the first 14 warm-up bars) on which none of the listed entries fires\n")
    L.append(md(["entries counted"] + ASSETS, rows))
    return "\n".join(L)


def cofire(A):
    L = []
    mats = {}
    for s in ASSETS:
        F = np.stack([A[s].entries[nm]["fire"] for nm in TA_NAMES]).astype(np.int32)
        mats[s] = F @ F.T
    pooled = sum(mats[s] for s in STOCKS)
    k = len(TA_NAMES)
    pairs = sorted(((pooled[i, j], i, j) for i, j in combinations(range(k), 2)), reverse=True)[:15]
    L.append("Top 15 pairs of entries firing on the same bar, ranked by the four stocks pooled (counts of bars). Pairs where one entry is a special case of the other (doji with dragonfly doji) are expected at the top.\n")
    L.append(md(["pair", "stocks pooled"] + ASSETS, [[f"{TA_NAMES[i]} + {TA_NAMES[j]}", n] + [mats[s][i, j] for s in ASSETS] for n, i, j in pairs]))
    pb = sorted(((mats["BTCUSDT"][i, j], i, j) for i, j in combinations(range(k), 2)), reverse=True)[:15]
    L.append("Top 15 pairs for BTCUSDT\n")
    L.append(md(["pair", "BTCUSDT"] + ["stocks pooled"], [[f"{TA_NAMES[i]} + {TA_NAMES[j]}", n, pooled[i, j]] for n, i, j in pb]))
    named = [
        ("doji + dragonfly_doji", ["doji"], ["dragonfly_doji"]),
        ("doji + gravestone_doji", ["doji"], ["gravestone_doji"]),
        ("doji + harami (either direction)", ["doji"], ["harami_bull", "harami_bear"]),
        ("hammer + dragonfly_doji", ["hammer"], ["dragonfly_doji"]),
        ("engulfing (either) + three_inside (either)", ["engulfing_bull", "engulfing_bear"], ["three_inside_up", "three_inside_down"]),
        ("engulfing_bull + piercing", ["engulfing_bull"], ["piercing"]),
        ("engulfing_bear + dark_cloud", ["engulfing_bear"], ["dark_cloud"]),
        ("engulfing (either) + piercing or dark_cloud", ["engulfing_bull", "engulfing_bear"], ["piercing", "dark_cloud"]),
    ]
    rows = []
    for lab, x, y in named:
        r = [lab]
        for s in ASSETS:
            a = A[s]
            fx = np.any([a.entries[n]["fire"] for n in x], axis=0)
            fy = np.any([a.entries[n]["fire"] for n in y], axis=0)
            both = int((fx & fy).sum())
            r.append(f"{both} (of {int(fx.sum())} / {int(fy.sum())})")
        rows.append(r)
    L.append("Named pairs: bars where both fire (of: firings of the first / of the second)\n")
    L.append(md(["pair"] + ASSETS, rows))
    return "\n".join(L)


# ---------------------------------------------------------------- section F
def fwd(a, e, h, exclude_overnight):
    """Direction-adjusted move in ATR units for firings in e (close[i] -> close[i+h])."""
    idx = np.flatnonzero(e["fire"] if isinstance(e, dict) else e)
    idx = idx[idx + h < a.n]
    bad = (a.cs_miss[idx + h + 1] - a.cs_miss[idx + 1]) > 0
    if exclude_overnight and not a.crypto:
        bad |= (a.cs_ovn[idx + h + 1] - a.cs_ovn[idx + 1]) > 0
    idx = idx[~bad]
    mv = (a.c[idx + h] - a.c[idx]) / a.atr[idx]
    ok = np.isfinite(mv)
    return idx[ok], mv[ok]


def mstats(mv):
    n = len(mv)
    if n < 2:
        return f"{n} | - | - | -"
    return f"{n} | {mv.mean():+.3f} | {mv.std(ddof=1) / np.sqrt(n):.3f} | {100 * (mv > 0).mean():.1f}%"


def section_F(A):
    names = [(nm, TALIB[TA_NAMES.index(nm)][6]) for nm in TA_NAMES if TALIB[TA_NAMES.index(nm)][6] != 0]
    extra = []
    for nm, e in A["SPY"].entries.items():
        if e["group"] in ("relaxed", "shape_f") or nm in ("tweezer_bottom_b_tol0.10", "tweezer_top_b_tol0.10"):
            extra.append((nm, e["fdir"]))
    names += extra
    L = []
    for label, pop, excl in (("Stocks pooled (SPY, AAPL, JPM, XOM), moves that cross an overnight boundary EXCLUDED", STOCKS, True),
                             ("Stocks pooled, moves crossing overnight INCLUDED (missing-bar moves still excluded)", STOCKS, False),
                             ("BTCUSDT (no overnight; moves across a missing bar excluded)", ["BTCUSDT"], False)):
        rows = []
        # baseline: all bars, direction up
        base = {}
        for h in (1, 4):
            mvs = [fwd(A[s], np.ones(A[s].n, bool), h, excl)[1] for s in pop]
            base[h] = np.concatenate(mvs)
        rows.append(["ALL BARS (baseline, up)", mstats(base[1]), mstats(base[4])])
        for nm, d in names:
            r = [nm + (" (down = bearish)" if d < 0 else "")]
            for h in (1, 4):
                mvs = []
                for s in pop:
                    e = A[s].entries.get(nm)
                    if e is None:
                        continue
                    mvs.append(d * fwd(A[s], e, h, excl)[1])
                r.append(mstats(np.concatenate(mvs)) if mvs else "n/a")
            rows.append(r)
        L.append(f"##### {label}\n")
        L.append("Columns per horizon: n moves | mean move in the entry's direction (ATR units) | standard error | share of moves in the entry's direction\n")
        hdr = ["entry"] + [f"{h} bar(s) later: {k}" for h in (1, 4) for k in ("n", "mean", "SE", "share")]
        rows = [[r[0]] + " | ".join(r[1:]).split(" | ") for r in rows]
        L.append(md(hdr, rows))
    return "\n".join(L)


# ---------------------------------------------------------------- main
def main(bars_dir, out):
    A, L = {}, []
    for s in ASSETS:
        df, info = load(bars_dir, s)
        a = Asset(s, df, info)
        a.info.update(first=str(df["datetime"].iloc[0]), last=str(df["datetime"].iloc[-1]))
        ta_entries(a)
        relaxed_entries(a)
        tweezer_entries(a)
        A[s] = a
    L.append("### Bar counts\n")
    L.append(md(["asset", "bars used", "rows downloaded", "zero-volume bars dropped", "first bar", "last bar", "calendar days with bars", "bars with high == low (TA-Lib doji fires on these)", "missing-bar gaps inside sessions (count)"],
                [[s, A[s].n, A[s].info["raw"], A[s].info["zero_volume_dropped"], A[s].info["first"], A[s].info["last"], A[s].n_days, A[s].zero_range, int(A[s].miss.sum())] for s in ASSETS]))
    extra = ["engulfing_bull_strict100", "engulfing_bear_strict100"]
    L.append("## A. Firing rates (TA-Lib, default settings)\n")
    L.append(stats_A(A, TA_NAMES + extra, "A. All 19 TA-Lib detectors as 25 entries (plus strict 100 engulfing rows, extra)"))
    L.append("## B. Overlap\n")
    L.append(table_B(A))
    L.append(cofire(A))
    L.append("## C. Prior-move filter\n")
    L.append("#### Baseline\n")
    L.append(baseline_C(A))
    creversal = [t[0] for t in TALIB if t[5] != 0]
    L.append(stats_C(A, creversal, "C. TA-Lib reversal entries"))
    D = [n for n, e in A["SPY"].entries.items() if e["group"] in ("relaxed", "shape")]
    L.append("## D. Relaxed versions and shapes without the gap or previous-bar test\n")
    L.append(stats_A(A, D, "D. Same breakdown as A"))
    L.append(stats_C(A, D, "D. Prior-move survival (same as C)"))
    T = [n for n, e in A["SPY"].entries.items() if e["group"] == "tweezer"]
    Tbtc = [n for n in T]
    L.append("## E. Tweezers\n")
    L.append("Entries without the suffix are two bars in the same session with no missing bar between (for BTC: consecutive bars). Entries ending `_overnight` (stocks only) are pairs where bar 2 is the first bar of a new day. Variant a = no colour test, b = colour test. Tolerance is a multiple of ATR(14) at bar 2.\n")
    L.append(stats_A(A, T, "E. Tweezer counts"))
    L.append(stats_C(A, T, "E. Tweezer prior-move survival"))
    L.append("## F. Forward moves (DESCRIPTIVE ONLY, NOT a basis for choosing patterns)\n")
    L.append("Move = close of the firing bar to the close 1 or 4 bars later, in ATR(14) units at the firing bar, signed so that positive = the entry's direction. Directions: bullish entries up, bearish down; spinning top and marubozu use their colour; continuation entries (three white soldiers, three black crows, rise/fall three methods) use their own direction; plain doji has no direction and is left out. Standard errors are naive (they treat moves as independent; neighbouring bars overlap, especially for 4-bar moves). Hammer/inverted-hammer shape entries in F are the shapes after a decline (bullish) or advance (bearish) under prior-move test (i).\n")
    L.append(section_F(A))
    open(out, "w", encoding="utf-8").write("\n".join(L))
    print("wrote", out)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
