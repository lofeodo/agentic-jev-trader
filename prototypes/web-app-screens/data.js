/* PROTOTYPE. Everything here is made up. Numbers are generated from fixed seeds so the page looks the same on every load. */

const fmt$ = n => (n < 0 ? "−$" : "$") + Math.abs(Math.round(n)).toLocaleString("en-US");
const sgn$ = n => (n < 0 ? "−$" : "+$") + Math.abs(Math.round(n)).toLocaleString("en-US");
const cents = n => "$" + n.toFixed(2);
const money2 = v => "$" + v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const pct = (x, d = 1) => (x < 0 ? "−" : "+") + Math.abs(x * 100).toFixed(d) + "%";
const share = (x, d = 0) => (x * 100).toFixed(d) + "%";
const esc = s => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;");
function rng(seed) { return function () { seed |= 0; seed = seed + 0x6D2B79F5 | 0; let t = Math.imul(seed ^ seed >>> 15, 1 | seed); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; }
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
function dayDate(start, d) { const t = new Date(Date.parse(start + "T00:00:00Z") + d * 864e5); return t.getUTCDate() + " " + MONTHS[t.getUTCMonth()]; }
function dayYear(start, d) { const t = new Date(Date.parse(start + "T00:00:00Z") + d * 864e5); return t.getUTCDate() + " " + MONTHS[t.getUTCMonth()] + " " + t.getUTCFullYear(); }
function isWeekend(start, d) { const w = new Date(Date.parse(start + "T00:00:00Z") + d * 864e5).getUTCDay(); return w === 0 || w === 6; }
const hhmm = m => String(Math.floor(m / 60)).padStart(2, "0") + ":" + String(m % 60).padStart(2, "0");

/* The asset key: the only place real names and price scales live. */
const ASSETS = {
  ASSET_01: { name: "S&P 500 fund", symbol: "SPY", cls: "stock", scale: 5.612, base: 101.4 },
  ASSET_02: { name: "JPMorgan", symbol: "JPM", cls: "stock", scale: 2.310, base: 103.1 },
  ASSET_03: { name: "Apple", symbol: "AAPL", cls: "stock", scale: 2.124, base: 104.2 },
  ASSET_04: { name: "Exxon", symbol: "XOM", cls: "stock", scale: 1.080, base: 98.7 },
  ASSET_05: { name: "Bitcoin", symbol: "BTCUSDT", cls: "crypto", scale: 841.2, base: 112.6 },
};
const assetTag = id => `<span class="asset"><b>${ASSETS[id].name}</b> <span class="chip">${id}</span></span>`;
/* A price: the real one leads, the rescaled one the agent saw follows in small type. */
const realPrice = (id, p) => "$" + (p * ASSETS[id].scale).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const priceTag = (id, p) => `${realPrice(id, p)} <span class="masked" title="The rescaled price the agent saw">${p.toFixed(2)}</span>`;

const MARKETS = {
  "Falling market": { start: "2025-03-10", days: 30, label: "10 Mar to 8 Apr 2025", holdingEnd: 8710 },
  "Rising market": { start: "2025-04-09", days: 30, label: "9 Apr to 8 May 2025", holdingEnd: 11720 },
};
const KINDS = { measurement: "Measurement runs", "build-up": "Build-up run", tuning: "Tuning runs", practice: "Practice runs" };
const VARIANT_WORDS = { memory_on: "with memory", memory_off: "without memory", buy_hold: "holding the five assets" };

const RUNS = [
  { id: "rise-on-1", kind: "measurement", market: "Rising market", variant: "memory_on", repeat: 1, status: "running", day: 12, value: 10684, holding: 10912, est: 2.40, spent: 0.97, seed: 11, badDay: 7 },
  { id: "rise-off-1", kind: "measurement", market: "Rising market", variant: "memory_off", repeat: 1, status: "running", day: 12, value: 10512, holding: 10912, est: 0.90, spent: 0.34, seed: 12 },
  { id: "fall-on-1", kind: "measurement", market: "Falling market", variant: "memory_on", repeat: 1, status: "finished", value: 9410, est: 2.40, spent: 2.38, seed: 21, badDay: 14 },
  { id: "fall-off-1", kind: "measurement", market: "Falling market", variant: "memory_off", repeat: 1, status: "finished", value: 9020, est: 0.90, spent: 0.83, seed: 22 },
  { id: "fall-on-2", kind: "measurement", market: "Falling market", variant: "memory_on", repeat: 2, status: "finished", value: 9180, est: 2.40, spent: 2.44, seed: 23 },
  { id: "fall-off-2", kind: "measurement", market: "Falling market", variant: "memory_off", repeat: 2, status: "finished", value: 9160, est: 0.90, spent: 0.85, seed: 24 },
  { id: "fall-on-3", kind: "measurement", market: "Falling market", variant: "memory_on", repeat: 3, status: "finished", value: 9350, est: 2.40, spent: 2.41, seed: 25 },
  { id: "fall-off-3", kind: "measurement", market: "Falling market", variant: "memory_off", repeat: 3, status: "finished", value: 8940, est: 0.90, spent: 0.84, seed: 26 },
  { id: "build-up", kind: "build-up", variant: "memory_off", status: "finished", start: "2024-03-10", days: 365, label: "10 Mar 2024 to 9 Mar 2025", value: 11240, holding: 12480, est: 10.20, spent: 9.86, seed: 31 },
  { id: "tune-3", kind: "tuning", variant: "memory_off", status: "finished", start: "2025-02-10", days: 7, label: "10 to 16 Feb 2025", value: 10480, holding: 10090, est: 0.21, spent: 0.19, seed: 43, note: "sizes 20% to 200%, cut-off 0.45" },
  { id: "tune-2", kind: "tuning", variant: "memory_off", status: "stopped", why: "spending cap", start: "2025-02-10", days: 7, day: 5, label: "10 to 16 Feb 2025", value: 9730, holding: 10040, est: 0.21, spent: 0.32, seed: 42, note: "cut-off 0.30: too many full evaluations" },
  { id: "tune-1", kind: "tuning", variant: "memory_off", status: "finished", start: "2025-02-10", days: 7, label: "10 to 16 Feb 2025", value: 10120, holding: 10090, est: 0.21, spent: 0.21, seed: 41, note: "settings as decided" },
  { id: "practice-2", kind: "practice", variant: "memory_on", status: "finished", start: "2025-01-14", days: 1, label: "14 Jan 2025", value: 10031, holding: 9992, est: 0.08, spent: 0.07, seed: 52 },
  { id: "practice-1", kind: "practice", variant: "memory_off", status: "failed", why: "Jev failed", start: "2025-01-14", days: 1, day: 1, label: "14 Jan 2025", value: 10004, holding: 9998, est: 0.03, spent: 0.01, seed: 51 },
];
RUNS.forEach(r => {
  const m = MARKETS[r.market];
  if (m) { r.start = m.start; r.days = m.days; r.label = m.label; if (r.status === "finished") r.holding = m.holdingEnd; }
  r.cap = r.kind === "practice" ? 0.25 : Math.round(r.est * 150) / 100;
  r.daysDone = r.status === "finished" ? r.days : (r.day || 0);
  r.name = (r.market ? r.market + " · " : "") + VARIANT_WORDS[r.variant] + (r.repeat ? " · repeat " + r.repeat : "") + (r.market ? "" : " · " + r.label);
  r.title = r.kind === "measurement" ? r.market + ", " + VARIANT_WORDS[r.variant] + ", repeat " + r.repeat
    : r.kind === "build-up" ? "The build-up run" : r.kind === "tuning" ? "Tuning run " + r.id.split("-")[1] : "Practice run " + r.id.split("-")[1];
});
const OUTSIDE_RUNS = [{ purpose: "LLM benchmark (Claude Haiku against GLM Flash)", spent: 0.86 }, { purpose: "Saving answers for the recorded-answer tests", spent: 0.15 }];
const CEILING = 50;
const totalSpent = () => RUNS.reduce((s, r) => s + r.spent, 0) + OUTSIDE_RUNS.reduce((s, r) => s + r.spent, 0);
const runById = id => RUNS.find(r => r.id === id);
const partnerOf = r => RUNS.find(o => o !== r && o.kind === "measurement" && o.market === r.market && o.repeat === r.repeat);

/* A wandering line of account values that starts at $10,000 and lands exactly on `end`. Four points a day. */
function walk(seed, days, end, swing, badDay) {
  const r = rng(seed), n = days * 4 + 1, v = [10000];
  /* badDay: one day made to lose about $560, so the daily loss limit (5%) has something to show */
  for (let i = 1; i < n; i++) v.push(v[i - 1] + (r() - 0.5) * swing - (badDay != null && Math.floor((i - 1) / 4) === badDay && i % 4 !== 0 ? 190 : 0));
  const off = end - v[n - 1];
  return v.map((x, i) => Math.round(x + off * i / (n - 1)));
}
const SERIES = {};
function seriesOf(run) {
  if (!SERIES[run.id]) SERIES[run.id] = { agent: walk(run.seed, Math.max(run.daysDone, 1), run.value, 190, run.badDay), holding: walk(run.seed + 500, Math.max(run.daysDone, 1), run.holding, 120) };
  return SERIES[run.id];
}
function daysOf(run) {
  const s = seriesOf(run).agent, out = [];
  for (let d = 0; d < run.days; d++) {
    if (d >= run.daysDone) { out.push({ d, future: true }); continue; }
    const change = s[(d + 1) * 4] - s[d * 4];
    out.push({ d, change, start: s[d * 4], end: s[(d + 1) * 4], limit: change <= -0.05 * s[d * 4] });
  }
  return out;
}

const PATTERNS = ["bullish engulfing", "hammer", "doji", "bearish engulfing", "shooting star", "belt-hold", "spinning top", "harami", "three white soldiers", "dark cloud cover"];
const LEANS = { "bullish engulfing": "bullish", hammer: "bullish", doji: "neutral", "bearish engulfing": "bearish", "shooting star": "bearish", "belt-hold": "bullish", "spinning top": "neutral", harami: "bullish", "three white soldiers": "bullish", "dark cloud cover": "bearish" };
const REASONS = { choice: "Jev chose to close it", stop: "its stop price was reached", forced: "forced close", run_end: "the run ended" };
const PARTS = { stock: ["first hour", "middle", "last hour"], crypto: ["Asian hours", "European hours", "American hours"] };

const TRADES = {};
function tradesOf(run) {
  if (TRADES[run.id]) return TRADES[run.id];
  const r = rng(run.seed * 7 + 3), ids = Object.keys(ASSETS), out = [];
  const shown = Math.min(run.daysDone, 30), n = Math.max(2, Math.round(shown * 3.9));
  const first = run.daysDone - shown;
  for (let k = 0; k < n; k++) {
    let d = first + Math.floor(k / n * shown), id = ids[Math.floor(r() * 5)];
    if (ASSETS[id].cls === "stock" && isWeekend(run.start, d)) id = "ASSET_05";
    const cls = ASSETS[id].cls, bar = cls === "stock" ? 1 + Math.floor(r() * 24) : Math.floor(r() * 96);
    const minutes = cls === "stock" ? 13 * 60 + 30 + 15 * bar : 15 * bar;
    const chosen = Math.round((2000 + r() * r() * 14000) / 100) * 100, trimmed = r() < 0.4;
    const size = trimmed ? Math.round(chosen * (0.45 + 0.4 * r()) / 10) * 10 : chosen;
    const bars = 1 + Math.floor(r() * r() * 26), pl = Math.round(size * (r() - 0.46) * 0.022);
    out.push({
      n: k + 1, id: run.id + "-t" + (k + 1), asset: id, dir: r() < 0.66 ? "long" : "short", d, minutes, bar, chosen, size, trimmed,
      limit: trimmed ? (r() < 0.82 ? "trade risk limit" : "exposure limit") : null, bars, pl,
      reason: pl < 0 && r() < 0.62 ? "stop" : "choice", pattern: PATTERNS[Math.floor(r() * PATTERNS.length)],
      part: PARTS[cls][cls === "stock" ? (bar <= 4 ? 0 : bar >= 23 ? 2 : 1) : Math.floor(minutes / 480)], overnight: cls === "stock" && bar + bars > 26,
      entry: ASSETS[id].base * (0.97 + r() * 0.06), stopMoves: 1 + Math.floor(r() * 3),
    });
  }
  if (run.status === "running") {
    /* the two positions open right now, opened earlier on the day being replayed (the clock reads 15:15 UTC) */
    const [x, y] = out.slice(-2);
    Object.assign(x, { open: true, reason: null, asset: "ASSET_05", dir: "short", d: run.daysDone, minutes: 11 * 60 + 30, bar: 46, bars: 15, chosen: 4100, size: 4100, trimmed: false, limit: null, pl: 38, part: "European hours", overnight: false, entry: ASSETS.ASSET_05.base * 1.01, stopMoves: 2 });
    Object.assign(y, { open: true, reason: null, asset: "ASSET_03", dir: "long", d: run.daysDone, minutes: 14 * 60 + 15, bar: 3, bars: 4, chosen: 11200, size: 8400, trimmed: true, limit: "trade risk limit", pl: 21, pattern: "bullish engulfing", part: "first hour", overnight: false, entry: 104.25, stopMoves: 2 });
  }
  else if (run.status === "finished") { const t = out[out.length - 1]; t.reason = "run_end"; }
  return TRADES[run.id] = out;
}
function findTrade(tid) { const run = runById(tid.replace(/-t\d+$/, "")); return { run, trade: tradesOf(run).find(t => t.id === tid) }; }
const when = (run, t) => `${dayDate(run.start, t.d)} ${hhmm(t.minutes)}`;
const held = t => t.bars < 4 ? t.bars * 15 + " min" : (t.bars / 4).toFixed(t.bars % 4 ? 1 : 0).replace(".0", "") + " h";

/* Bars for a candle chart: a random walk around `base`. */
function makeBars(seed, n, base, drift) {
  const r = rng(seed), out = []; let c = base;
  for (let i = 0; i < n; i++) {
    const o = c, move = (r() - 0.5 + drift) * base * 0.006; c = o + move;
    out.push({ o, c, h: Math.max(o, c) + r() * base * 0.002, l: Math.min(o, c) - r() * base * 0.002 });
  }
  return out;
}
const mean = a => a.reduce((s, x) => s + x, 0) / a.length;
const sd = a => { const m = mean(a); return Math.sqrt(a.reduce((s, x) => s + (x - m) * (x - m), 0) / (a.length - 1)); };
