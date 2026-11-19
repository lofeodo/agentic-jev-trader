/* PROTOTYPE. The run page (three variants), the trade page, and the page behind one decision. */

let V = "A";   /* which variant of the run page is showing; set by app.js from ?variant= */
const href = (path, q) => "#/" + path + (q ? "?" + new URLSearchParams(q) : "");
const runHref = (id, extra) => href("run/" + id, Object.assign({ variant: V }, extra || {}));
const DATASET_STEP1 = Date.parse("2023-04-03T00:00:00Z");
const stepAt = (run, d) => Math.round((Date.parse(run.start + "T00:00:00Z") - DATASET_STEP1) / 864e5 + d) * 96;

/* A prototype note: not part of the design. `when` says whether the screen belongs to the first dashboard. */
function note(title, html, when) {
  const tag = when === "first" ? `<span class="tag">in the first dashboard</span>` : when === "later" ? `<span class="tag later">built later</span>` : "";
  return `<div class="pnote"><b class="t">Prototype note · ${title} ${tag}</b>${html}</div>`;
}
function statusBadge(run) {
  if (run.status === "running") return `<span class="badge out"><span class="sq"></span>running</span>`;
  if (run.status === "finished") return `<span class="badge ink">finished</span>`;
  return `<span class="badge fill">${run.status}: ${run.why}</span>`;
}
const sechead = (n, title, kicker) => `<div class="sechead"><span class="n">${n}</span><h2>${title}</h2>${kicker ? `<span class="kicker">${kicker}</span>` : ""}</div>`;
const measure = (name, term, value, words) => `<div class="measure"><div><b>${name}</b>${term ? `<div class="term">${term}</div>` : ""}</div><div class="v">${value}</div><div class="w">${words}</div></div>`;
const track = (ratio, hot) => `<div class="track"><i class="${hot ? "hot" : ""}" style="width:${Math.min(100, ratio * 100).toFixed(1)}%"></i></div>`;

/* ---------- facts worked out from the run's made-up records ---------- */
function rideOf(run) {
  const s = seriesOf(run), days = daysOf(run).filter(d => !d.future), ch = days.map(d => d.change);
  const hold = []; for (let d = 0; d < days.length; d++) hold.push(s.holding[(d + 1) * 4] - s.holding[d * 4]);
  let peak = s.agent[0], drop = 0, dropAt = 0, peakAt = 0, dropPeakAt = 0, dropPeak = peak;
  s.agent.forEach((v, i) => { if (v > peak) { peak = v; peakAt = i; } if (peak - v > drop) { drop = peak - v; dropAt = i; dropPeakAt = peakAt; dropPeak = peak; } });
  let back = null; for (let i = dropAt; i < s.agent.length; i++) if (s.agent[i] >= dropPeak) { back = i; break; }
  const best = days.reduce((a, b) => (b.change > a.change ? b : a)), worst = days.reduce((a, b) => (b.change < a.change ? b : a));
  return {
    days, swing: ch.length > 1 ? sd(ch) : 0, holdSwing: hold.length > 1 ? sd(hold) : 0, avg: mean(ch), best, worst,
    high: Math.max(...s.agent), low: Math.min(...s.agent), drop, dropPeak, dropFrom: Math.floor(dropPeakAt / 4), dropTo: Math.floor(dropAt / 4),
    backDays: back == null ? null : Math.ceil((back - dropAt) / 4), up: ch.filter(c => c > 0).length, limitDays: days.filter(d => d.limit),
  };
}
function tradeFacts(run) {
  const all = tradesOf(run), closed = all.filter(t => !t.open), won = closed.filter(t => t.pl > 0), lost = closed.filter(t => t.pl <= 0);
  const sum = a => a.reduce((s, t) => s + t.pl, 0);
  const by = key => { const m = {}; closed.forEach(t => { const k = key(t); m[k] = (m[k] || 0) + t.pl; }); return Object.entries(m).map(([name, v]) => ({ name, v })).sort((a, b) => b.v - a.v); };
  return { all, closed, won, lost, gains: sum(won), losses: -sum(lost), by, trimmed: all.filter(t => t.trimmed) };
}

/* ---------- header, shared by the three variants ---------- */
function runHeader(run) {
  const f = tradeFacts(run), behind = run.value - run.holding, live = run.status === "running";
  const kind = { measurement: "Measurement run", "build-up": "Build-up run", tuning: "Tuning run", practice: "Practice run" }[run.kind];
  const button = live ? `<button class="btn hot">Stop ■</button>` : run.status === "stopped" ? `<button class="btn">Raise the cap and restart →</button>` : run.status === "failed" ? `<button class="btn">Restart from step ${stepAt(run, run.daysDone).toLocaleString("en-US")} →</button>` : "";
  return `<div class="g12">
    <div class="c8">
      <span class="kicker"><a href="${href("runs")}">← All runs</a> &nbsp;·&nbsp; ${kind} · ${run.label} · ${VARIANT_WORDS[run.variant]}</span>
      <h1 class="display title">${run.title}</h1>
      <p class="meta mt1">${statusBadge(run)} &nbsp; day ${Math.min(run.daysDone + (live ? 1 : 0), run.days)} of ${run.days} · replaying ${dayYear(run.start, Math.min(run.daysDone, run.days - 1))}${live ? ` <span id="live-clock">15:15</span> UTC` : ""} · step <span id="live-step">${(stepAt(run, run.daysDone) + (live ? 61 : 0)).toLocaleString("en-US")}</span>${live ? ` · <span id="live-ago">updated just now</span>` : ""}</p>
    </div>
    <div class="c4" style="align-self:end; text-align:right">${button}</div>
  </div>
  <dl class="statrow mt2 rule" style="padding-top:.9rem">
    <div><dt class="kicker">Account value ${live ? "now" : "at the end"}</dt><dd class="statbig">${fmt$(run.value)} <small>${sgn$(run.value - 10000)}</small></dd><div class="meta mt1">${spark(seriesOf(run).agent)} started with $10,000</div></div>
    <div><dt class="kicker">Holding the five assets instead</dt><dd class="statbig">${fmt$(run.holding)}</dd><div class="meta mt1">the agent is <b class="${behind < 0 ? "accent" : ""}">${fmt$(Math.abs(behind))} ${behind < 0 ? "behind" : "ahead"}</b></div></div>
    <div><dt class="kicker">Trades</dt><dd class="statbig">${f.all.length} <small>${(f.all.length / Math.max(1, Math.min(run.daysDone, 30))).toFixed(1)} a day</small></dd><div class="meta mt1">${f.won.length} made money · ${f.lost.length} lost · ${f.all.length - f.closed.length} open</div></div>
    <div><dt class="kicker">Spent on the models (real dollars)</dt><dd class="statbig">${cents(run.spent)} <small>of ${cents(run.cap)} cap</small></dd>${track(run.spent / run.cap, run.spent >= run.cap)}<div class="meta">estimated ${cents(run.est)} for the whole run</div></div>
  </dl>`;
}

/* ---------- section: now / overview ---------- */
function eventsOf(run) {
  const e = [];
  if (run.id === "rise-on-1") e.push(
    { t: "Daily loss limit reached", w: "16 Apr 17:45", x: "Down 5% since midnight: no entries or adds until the day ends.", bad: true },
    { t: "An LLM limit hit", w: "14 Apr 14:30", x: "6 lookups used on Apple; its answer was taken as it stood." },
    { t: "Restarted", w: "11 Apr 08:02", x: "Continued from the last completed step." },
    { t: "Stopped by hand", w: "10 Apr 23:40", x: "" });
  if (run.status === "stopped") e.push({ t: "Spending cap reached", w: dayDate(run.start, run.daysDone) + " 11:15", x: `Stopped at the end of the step with ${cents(run.spent)} spent.`, bad: true });
  if (run.status === "failed") e.push({ t: "Jev failed after 3 retries", w: dayDate(run.start, 0) + " 13:45", x: "The run stopped; positions stay open so it can be restarted.", bad: true });
  if (run.status === "finished") e.push({ t: "Finished", w: dayDate(run.start, run.days - 1) + " 23:45", x: "Every open position was closed at the last step; the run ended in cash." });
  e.push({ t: "Started", w: dayDate(run.start, 0) + " 00:00", x: run.variant === "memory_on" ? "With a fresh copy of the base memory: 1,912 closed trades." : "It reads no memory." });
  return e;
}
const eventList = run => `<ol class="list timeline">${eventsOf(run).map(e => `<li><span class="mk ${e.bad ? "bad" : ""}"></span><div style="flex:1"><div style="display:flex;gap:.75rem;align-items:baseline"><span class="t">${e.t}</span><span class="when">${e.w}</span></div>${e.x ? `<div class="small muted">${e.x}</div>` : ""}</div></li>`).join("")}</ol>`;

function valueFigure(run, no) {
  const s = seriesOf(run), p = partnerOf(run), per = run.days > 60 ? 60 : run.days > 10 ? 5 : 1;
  const xticks = []; for (let d = 0; d <= run.days; d += per) xticks.push({ i: d * 4, label: dayDate(run.start, d) });
  const series = [{ name: "this run " + fmt$(run.value), vals: s.agent, kind: "subject" }, { name: "holding " + fmt$(run.holding), vals: s.holding, kind: "dashed" }];
  if (p) series.push({ name: (p.variant === "memory_on" ? "with memory " : "without ") + fmt$(p.value), vals: seriesOf(p).agent, kind: "context" });
  const legend = `<span><i class="sw"></i>this run</span>${p ? `<span><i class="sw ctx"></i>its partner, ${VARIANT_WORDS[p.variant]}</span>` : ""}<span><i class="sw ref" style="border-top:1.25px dotted var(--ink)"></i>holding the five assets</span>`;
  return figure(no, "Account value, against holding the five assets", legend,
    lineChart({ series, n: run.days * 4 + 1, xticks, ref: { v: 10000, label: "start $10,000" }, anno: run.status === "running" ? "The right side fills in as the run replays." : "", label: "Line chart of account value over the run" }),
    `${run.daysDone} of ${run.days} days · 4 points a day · UTC days · prototype: made-up numbers`);
}
function secOverview(run, no) {
  const live = run.status === "running", ride = rideOf(run), today = ride.days[ride.days.length - 1], f = tradeFacts(run), behind = run.value - run.holding;
  const open = f.all.filter(t => t.open), exposure = open.reduce((s, t) => s + t.size, 0), loan = Math.max(0, exposure - run.value);
  const lede = `<p class="lede">After <b>${run.daysDone} ${run.daysDone === 1 ? "day" : "days"}</b> the account holds <b>${fmt$(run.value)}</b>: <b class="accent">${fmt$(Math.abs(behind))} ${behind < 0 ? "less" : "more"}</b> than holding the five assets and never trading.</p>`;
  const positions = !live ? `<div class="waiting"><span class="kicker">Open positions</span><p>${run.status === "finished" ? "None. The run ended, so it holds only cash." : "This run stopped early, so its positions are still open."}</p></div>` :
    `<div class="subhead">Open positions <span class="kicker">what the agent holds right now</span></div><div class="tablewrap"><table><thead><tr><th>Asset</th><th>Direction</th><th class="num">Size</th><th>Opened</th><th class="num">Now</th><th class="num">Stop price</th><th></th></tr></thead><tbody>${open.map(t => {
      const stop = t.entry * (1 + (t.dir === "long" ? -1 : 1) * 0.006 * t.stopMoves);
      return `<tr class="click" onclick="openPanel({kind:'exchange',tid:'${t.id}'})"><td>${assetTag(t.asset)}</td><td>${t.dir}</td><td class="num">${fmt$(t.size)}${t.trimmed ? ` <span class="badge out" title="Jev chose ${fmt$(t.chosen)}; code made it smaller">trimmed</span>` : ""}</td><td class="num" style="text-align:left">${when(run, t)} · ${t.bars} bars ago</td><td class="num">${sgn$(t.pl)}</td><td class="num">${priceTag(t.asset, stop)}<div class="meta">would lose ${fmt$(t.size * 0.006 * t.stopMoves)}</div></td><td class="num">→</td></tr>`;
    }).join("")}</tbody></table></div>`;
  const latest = f.all.slice(-6).reverse().map(t => `<li style="display:flex;gap:.75rem;align-items:baseline;flex-wrap:wrap"><span class="meta" style="width:6.2rem">${when(run, t)}</span>${assetTag(t.asset)} <span>${t.open ? "opened a " + t.dir + " of " + fmt$(t.size) : "closed its " + t.dir + ", " + sgn$(t.pl) + ": " + REASONS[t.reason]}</span><a class="chip ink" style="margin-left:auto" href="${href("decision/" + t.id)}">the exchange →</a></li>`).join("");
  const side = live ? `
      <span class="kicker">Today · ${dayDate(run.start, run.daysDone)} · the day runs midnight to midnight UTC</span>
      <dl class="pairs mt1"><dt>Change since midnight</dt><dd>${sgn$(today.change * 0.3)}</dd></dl>${track(0.12)}<div class="meta">daily loss limit: at ${sgn$(-0.05 * run.value)} code blocks new trades for the day</div>
      <dl class="pairs mt2"><dt>Held in positions</dt><dd>${fmt$(exposure)} of ${fmt$(2 * run.value)} allowed</dd></dl>${track(exposure / (2 * run.value))}<div class="meta">exposure limit: 2 times account value · loan now ${loan ? fmt$(loan) : "none"}</div>
      <dl class="pairs mt2"><dt>Spent on the models</dt><dd>${cents(run.spent)} of ${cents(run.cap)}</dd></dl>${track(run.spent / run.cap)}<div class="meta">spending cap: the run stops itself there</div>` : "";
  return `<div class="g12"><div class="c4">${lede}</div><div class="c8">${valueFigure(run, no)}</div></div>
    <div class="g12 mt3"><div class="c8">${positions}
      <div class="subhead">Latest decisions <span class="kicker">newest first</span></div><ol class="list">${latest}</ol></div>
    <div class="c4">${side}<div class="subhead" style="${live ? "" : "margin-top:0"}">Notable moments</div>${eventList(run)}</div></div>`;
}

/* ---------- section: measurements ---------- */
function secMeasurements(run) {
  const r = rideOf(run), f = tradeFacts(run), s = seriesOf(run), n = f.closed.length || 1, sofar = run.status === "running" ? " so far" : "";
  const long = f.all.filter(t => t.dir === "long").length, same = f.closed.filter(t => !t.overnight).length, stops = f.closed.filter(t => t.reason === "stop").length;
  const avgBars = mean(f.closed.map(t => t.bars)), big = f.all.filter(t => t.chosen >= 12000).length;
  const money = measure("Ending money and profit" + sofar, "", `${fmt$(run.value)} · ${sgn$(run.value - 10000)}`, `The account started with $10,000 and is worth ${fmt$(run.value)}${sofar}, after every trading cost.`) +
    measure("Holding the five assets", "buy and hold", `${fmt$(run.holding)} · ${sgn$(run.holding - 10000)}`, `$2,000 in each asset at the first step, never traded. The agent gets credit only for what it ends above this: ${sgn$(run.value - run.holding)}.`) +
    measure("Real dollars spent on the models", "", cents(run.spent), `Paid to Jev and the LLM. Shown beside the result, never subtracted from it.`);
  const ride = measure("Typical daily swing", "standard deviation of daily changes", `${fmt$(r.swing)} · ${share(r.swing / 10000, 1)}`, `On an ordinary day the account moved about ${fmt$(r.swing)} up or down.`) +
    measure("Best and worst day", "", `${sgn$(r.best.change)} · ${sgn$(r.worst.change)}`, `Best: ${dayDate(run.start, r.best.d)}. Worst: ${dayDate(run.start, r.worst.d)}.`) +
    measure("Highest and lowest account value", "", `${fmt$(r.high)} · ${fmt$(r.low)}`, `The range the account travelled over the whole run.`) +
    measure("Biggest drop from a high point", "maximum drawdown", `${fmt$(-r.drop)} · ${share(r.drop / r.dropPeak, 1)}`, `From ${fmt$(r.dropPeak)} on ${dayDate(run.start, r.dropFrom)} down to ${fmt$(r.dropPeak - r.drop)} on ${dayDate(run.start, r.dropTo)}. ${r.backDays == null ? "It has not climbed back yet." : "It took " + r.backDays + (r.backDays === 1 ? " day" : " days") + " to climb back."}`) +
    measure("Days that ended up", "", `${r.up} of ${r.days.length}`, `${share(r.up / r.days.length)} of days ended with more money than they started with.`) +
    measure("Swing against holding", "", `${(r.swing / (r.holdSwing || 1)).toFixed(1)} times`, `Holding the five assets swung about ${fmt$(r.holdSwing)} a day. Above 1 means the agent's ride was wilder than the market's.`) +
    measure("Profit per unit of swing", "Sharpe ratio, per day", (r.avg / (r.swing || 1)).toFixed(2), `Average daily profit (${sgn$(r.avg)}) divided by the typical daily swing. Higher means steadier gains for the same wildness.`);
  const kind = measure("Trades per day", "", (f.all.length / Math.min(run.daysDone || 1, 30)).toFixed(1), `${f.all.length} trades in all. Per asset: ${Object.keys(ASSETS).map(id => ASSETS[id].name + " " + f.all.filter(t => t.asset === id).length).join(", ")}.`) +
    measure("Time and money invested", "", `61% · 74%`, `It held at least one position 61% of the time, and on average 74% of the account was in positions.`) +
    measure("Trade size", "", `${fmt$(mean(f.all.map(t => t.size)))} average`, `Jev picked one of the two largest sizes (120% or 200% of the account) ${big} times out of ${f.all.length}.`) +
    measure("Bets on a rise against bets on a fall", "longs and shorts", `${long} · ${f.all.length - long}`, `A long gains when the price rises; a short gains when it falls.`) +
    measure("How long trades are held", "", `${(avgBars / 4).toFixed(1)} hours`, `${avgBars.toFixed(0)} bars on average. ${share(same / n)} were closed the same day they were opened.`) +
    measure("How trades end", "closing reason", `${stops} · ${n - stops}`, `${stops} at their stop price (code closed them to cap the loss), ${n - stops} by Jev's choice, 0 by forced close${run.status === "finished" ? ", 1 because the run ended" : ""}.`) +
    measure("From a check to a trade", "", `14% · 21%`, `14% of checks led to a full evaluation, and 21% of full evaluations led to a trade. Above 30% on the first number, the developer decides before any measurement run.`) +
    measure("How often a limit held it back", "", `${f.trimmed.length} of ${f.all.length} trades`, `Code made ${f.trimmed.length} trades smaller than Jev chose (${f.trimmed.filter(t => t.limit === "trade risk limit").length} by the trade risk limit, ${f.trimmed.filter(t => t.limit !== "trade risk limit").length} by the exposure limit). The daily loss limit was reached on ${r.limitDays.length} ${r.limitDays.length === 1 ? "day" : "days"}.`) +
    measure("The day after a losing day", "", `4.4 against 3.6`, `Trades on days that follow a losing day, against all other days. More trades after a loss can mean chasing.`);
  const trades = measure("Closed trades", "", `${f.closed.length}`, `${f.won.length} made money: ${share(f.won.length / n)}.`) +
    measure("Average gain and average loss", "", `${sgn$(f.gains / (f.won.length || 1))} · ${sgn$(-f.losses / (f.lost.length || 1))}`, `What a winning trade and a losing trade typically brought, after trading costs.`) +
    measure("Total gains divided by total losses", "profit factor", (f.gains / (f.losses || 1)).toFixed(2), `Winners brought in ${fmt$(f.gains)} and losers gave back ${fmt$(f.losses)}. Above 1 means the trades made money overall.`);
  const split = (title, rows) => `<div><div class="kicker" style="margin-bottom:.4rem">${title}</div>${rankedBars(rows, sgn$)}</div>`;
  const splits = `<div class="g12 mt2" style="row-gap:1.5rem"><div class="c5">${split("Profit by asset", f.by(t => ASSETS[t.asset].name))}</div><div class="c7">${split("Profit by candle pattern", f.by(t => t.pattern).slice(0, 7))}</div>
    <div class="c5">${split("Profit by direction", f.by(t => t.dir))}</div><div class="c7">${split("Profit by how the trade ended", f.by(t => REASONS[t.reason]))}</div></div>`;
  const conf = [["50 to 60%", 0.55, 0.52, 61], ["60 to 70%", 0.65, 0.61, 48], ["70 to 80%", 0.75, 0.66, 27], ["80 to 90%", 0.85, 0.70, 9]];
  const confidence = `<div class="tablewrap"><table style="min-width:0"><thead><tr><th>When Jev said</th><th class="num">It was right</th><th class="num">Times</th><th>In plain words</th></tr></thead><tbody>${conf.map(c => `<tr><td class="mono small">${c[0]}</td><td class="num">${share(c[2])}</td><td class="num">${c[3]}</td><td class="small muted">${c[2] < c[1] - 0.07 ? "Too sure of itself here." : "About as sure as it should be."}</td></tr>`).join("")}</tbody></table></div>`;
  const memory = run.variant !== "memory_on" ? `<div class="waiting"><span class="kicker">Not for this run</span><p>This run never reads memory, so there is nothing to measure here.</p></div>` :
    measure("The LLM took the top results as they came", "", "38%", `In 38% of full evaluations it selected exactly the top-ranked episodes of the first search, adding no choice of its own.`) +
    measure("It picked a more one-sided set than it was shown", "", "22%", `Example: shown 6 winners and 4 losers, it selected 4 winners and no losers. Its one rule is to choose by likeness, not by profit.`) +
    measure("The text ranking helped", "", "31%", `Of the episodes it selected, 31% were ones only the situation text ranked highly; the numbers alone would have missed them.`) +
    measure("Profit per day, with memory against without", "", `<a class="chip hot" href="${href("comparison")}">see the comparison →</a>`, `This needs both runs of a repeat, so it lives on the comparison screen.`);
  return `<div class="subhead" style="margin-top:0">Money</div>${money}
    <div class="subhead">How wild the ride is</div>${ride}
    <div class="subhead">What kind of trader it is</div>${kind}
    <div class="subhead">Trades</div>${trades}${splits}
    <div class="subhead">Jev's confidence <span class="kicker">when Jev says 70% sure, is it right about 70% of the time?</span></div>${confidence}
    <div class="subhead">Memory</div>${memory}`;
}

/* ---------- section: trades ---------- */
function tradeRows(run, list) {
  return list.map(t => `<tr class="click" onclick="openPanel({kind:'exchange',tid:'${t.id}'})"><td class="num" style="text-align:left">${t.n}</td><td>${assetTag(t.asset)}</td><td>${t.dir}</td><td class="num" style="text-align:left">${when(run, t)}</td><td class="num">${held(t)}${t.overnight ? ` <span class="badge" title="A stock held past the end of its session">overnight</span>` : ""}</td>
    <td class="num">${fmt$(t.size)}${t.trimmed ? `<div class="meta"><span class="badge out">trimmed</span> Jev chose ${fmt$(t.chosen)}</div>` : ""}</td><td class="num">${t.open ? `<span class="muted">${sgn$(t.pl)} so far</span>` : sgn$(t.pl)}</td><td class="small">${t.open ? `<span class="badge out"><span class="sq"></span>open</span>` : REASONS[t.reason]}</td><td class="small muted">${t.pattern}</td></tr>`).join("");
}
const TRADE_HEAD = `<thead><tr><th>#</th><th>Asset</th><th>Direction</th><th>Opened (UTC)</th><th class="num">Held</th><th class="num">Size</th><th class="num">Profit or loss</th><th>How it ended</th><th>Pattern at entry</th></tr></thead>`;
function secTrades(run, q) {
  const f = tradeFacts(run), filter = q.get("show") || "all";
  const sets = { all: f.all, lost: f.closed.filter(t => t.pl <= 0), trimmed: f.trimmed, stop: f.closed.filter(t => t.reason === "stop"), overnight: f.all.filter(t => t.overnight) };
  const words = { all: "All", lost: "Lost money", trimmed: "Trimmed by a limit", stop: "Closed at the stop price", overnight: "Held overnight" };
  const togs = Object.keys(sets).map(k => `<a class="tog ${k === filter ? "on" : ""}" href="${runHref(run.id, { tab: "trades", show: k })}">${words[k]} <span>${sets[k].length}</span></a>`).join("");
  return `<div class="filters"><span class="kicker">Show</span>${togs}</div>
    <div class="filters"><span class="kicker">Asset</span>${Object.keys(ASSETS).map(id => `<span class="tog">${ASSETS[id].name} <span>${f.all.filter(t => t.asset === id).length}</span></span>`).join("")}</div>
    <div class="tablewrap mt1"><table>${TRADE_HEAD}<tbody>${tradeRows(run, [...sets[filter]].reverse().slice(0, 40))}</tbody></table></div>
    <p class="meta mt1">newest first · ${Math.min(40, sets[filter].length)} of ${sets[filter].length} shown · profit or loss is after trading costs · click a row for the exchange behind the trade</p>`;
}

/* ---------- section: decisions (the step log) ---------- */
function secDecisions(run) {
  const r = rng(run.seed + 99), f = tradeFacts(run), rows = [];
  f.all.slice(-7).reverse().forEach(t => {
    rows.push({ w: when(run, t), a: t.asset, k: "full evaluation", ans: `screen ${(0.5 + r() * 0.4).toFixed(2)}, then picked a ${t.dir}`, did: `entry, ${fmt$(t.size)}${t.trimmed ? " after trimming" : ""}`, link: t.id });
    rows.push({ w: when(run, t), a: Object.keys(ASSETS)[Math.floor(r() * 5)], k: "full evaluation", ans: `screen ${(0.5 + r() * 0.2).toFixed(2)}, then picked no trade`, did: "nothing", link: t.id });
    if (!t.open) rows.push({ w: when(run, t), a: t.asset, k: "position check", ans: `close ${(0.45 + r() * 0.4).toFixed(2)}, hold ${(0.1 + r() * 0.3).toFixed(2)}`, did: "close", link: t.id });
  });
  return `<div class="filters"><span class="kicker">Show</span><span class="tog on">Full evaluations and position changes <span>1,204</span></span><span class="tog">Every check <span>8,160</span></span><span class="tog">Only those that led to an order <span>96</span></span></div>
    <div class="tablewrap mt1"><table><thead><tr><th>When (UTC)</th><th>Asset</th><th>What was asked</th><th>Jev's answer</th><th>What was done</th><th></th></tr></thead><tbody>
    ${rows.map(x => `<tr><td class="num" style="text-align:left">${x.w}</td><td>${assetTag(x.a)}</td><td class="small">${x.k}</td><td class="small mono">${x.ans}</td><td class="small">${x.did}</td><td class="num"><a class="chip ink" href="${href("decision/" + x.link)}">the exchange →</a></td></tr>`).join("")}
    </tbody></table></div>
    <p class="meta mt1">one line per asset and step the agent looked at · a screen that stayed under the cut-off of 0.5 is hidden unless "every check" is on</p>`;
}

/* ---------- section: track record ---------- */
function secTrackRecord(run) {
  const r = rng(run.seed + 7), rows = [];
  PATTERNS.forEach(p => ["long", "short"].forEach(dir => { if (r() < 0.62) { const nT = Math.floor(3 + r() * r() * 70), won = Math.round(nT * (0.3 + r() * 0.4)); rows.push({ p, dir, cls: r() < 0.8 ? "stocks" : "Bitcoin", n: nT, won, gain: 40 + r() * 80, loss: 30 + r() * 60 }); } }));
  rows.sort((a, b) => b.n - a.n);
  const line = x => { const total = x.won * x.gain - (x.n - x.won) * x.loss; return `<tr class="${x.n < 10 ? "dim" : ""}"><td><b style="font:600 15px var(--display)">${x.p}</b> <span class="badge ${LEANS[x.p] === "neutral" ? "" : "ink"}">${LEANS[x.p]}</span></td><td>${x.dir}</td><td class="small">${x.cls}</td><td class="num">${x.n}</td><td class="num">${share(x.won / x.n)}</td><td class="num">${sgn$(x.gain)}</td><td class="num">${sgn$(-x.loss)}</td><td class="num">${sgn$(total)}</td><td class="small">${x.n < 10 ? `<span class="badge">hidden from the agent</span>` : "shown"}</td></tr>`; };
  const top = rows[0], split = `<tr><td colspan="9" style="padding-left:1.5rem"><div class="why small"><span class="kicker">Split further · ${top.p}, ${top.dir}, ${top.cls}</span><br>
    With the long-term trend: ${Math.round(top.n * 0.6)} trades, ${share(top.won / top.n + 0.06)} made money · against it: ${Math.round(top.n * 0.4)} trades, ${share(top.won / top.n - 0.09)}.<br>
    Volume low / average / high: ${Math.round(top.n * 0.2)} · ${Math.round(top.n * 0.3)} · ${Math.round(top.n * 0.5)} trades. First hour / middle / last hour: ${Math.round(top.n * 0.5)} · ${Math.round(top.n * 0.35)} · ${Math.round(top.n * 0.15)} trades.</div></td></tr>`;
  return `<p class="lead">The track record is the agent's own statistics on its closed trades, counted by code from stored records each time it is asked for. ${run.variant === "memory_on" ? "This run's memory began as a copy of the base memory, so these counts include its 1,912 trades." : "This run stores its trades but never reads them."}</p>
    <div class="tablewrap mt2"><table><thead><tr><th>Candle pattern, with its lean</th><th>Direction</th><th>Asset class</th><th class="num">Closed trades</th><th class="num">Made money</th><th class="num">Average gain</th><th class="num">Average loss</th><th class="num">Total</th><th>To the agent</th></tr></thead><tbody>${line(top)}${split}${rows.slice(1).map(line).join("")}</tbody></table></div>
    <p class="meta mt1">${rows.length} groups · a group with fewer than 10 closed trades (the minimum sample) is never shown to the agent · lean comes from the playbook · click a line to split it further</p>`;
}

/* ---------- section: settings ---------- */
function secSettings(run) {
  const tuning = run.kind === "tuning", v = run.value;
  const rows = [
    ["Most one trade may lose at its stop price", "trade risk limit", "1% of account value", fmt$(0.01 * v), ""],
    ["Sizes Jev chooses among", "size buckets", "20%, 40%, 80%, 120%, 200%", `${fmt$(0.2 * v)} to ${fmt$(2 * v)}`, run.id === "tune-3" ? "was 2% to 20%" : ""],
    ["Most in a single trade", "position limit", "2 times account value", fmt$(2 * v), ""],
    ["Most held in total", "exposure limit", "2 times account value", fmt$(2 * v), ""],
    ["Loss in one day that blocks new trades", "daily loss limit", "5%", fmt$(0.05 * v), ""],
    ["Interest on the loan", "loan interest", "5% a year", "about $1.37 a day on $10,000 owed", ""],
    ["Forced close", "", "account value under a quarter of what is held", "", ""],
    ["Furthest a stop price may sit from the entry price", "", "5%", "", ""],
    ["Cut-off for a full evaluation", "", run.id === "tune-2" ? "0.30" : run.id === "tune-3" ? "0.45" : "0.50", "on the screen's answer, 0 to 1", run.id === "tune-2" ? "was 0.50" : run.id === "tune-3" ? "was 0.30" : ""],
  ];
  const dl = pairs => `<dl class="pairs">${pairs.map(p => `<dt class="small">${p[0]}</dt><dd>${p[1]}</dd>`).join("")}</dl>`;
  return `<div class="g12"><div class="c8">
      <div class="subhead" style="margin-top:0">Risk profile: medium <span class="kicker">the limits code enforced on this run, whatever the models decided</span></div>
      <div class="tablewrap"><table><thead><tr><th>Setting</th><th>Value</th><th>On this account now</th>${tuning ? "<th>Against the tuning run before</th>" : ""}</tr></thead><tbody>${rows.map(x => `<tr><td>${x[0]}${x[1] ? `<div class="meta">${x[1]}</div>` : ""}</td><td class="mono small">${x[2]}</td><td class="mono small muted">${x[3]}</td>${tuning ? `<td class="small">${x[4] ? `<span class="badge out">changed</span> ${x[4]}` : `<span class="muted">same</span>`}</td>` : ""}</tr>`).join("")}</tbody></table></div>
      <div class="subhead">Trading costs <span class="kicker">simulated money</span></div>
      ${dl([["Each stock order (commission)", "$1 flat"], ["Each Bitcoin order (trading fee)", "0.1% of its value"], ["Every order carried out at a worse price (slippage)", "0.05%"], ["A short held at the end of a day (borrow fee)", "0.25% a year stocks · 5% Bitcoin"]])}
    </div><div class="c4">
      <span class="kicker">What ran</span>
      ${dl([["Dataset", `<a class="chip ink" href="${href("dataset")}">first dataset v1</a>`], ["Steps", `${stepAt(run, 0).toLocaleString("en-US")} to ${(stepAt(run, run.days) - 1).toLocaleString("en-US")}`], ["Starting account value", "$10,000"], ["Memory copied from", run.variant === "memory_on" ? `<a class="chip ink" href="${runHref("build-up")}">the build-up run</a>` : "none"], ["Random seed", String(run.seed)], ["Code version", "4e1c9aa"]])}
      <div class="mt2"><span class="kicker">The models</span></div>
      ${dl([["LLM", run.variant === "memory_on" ? "claude-haiku-5-5 · effort low" : "never called"], ["Prompt version", run.variant === "memory_on" ? "p-3fa9c1" : "none"], ["Jev version", "jev-2026-10"], ["Reading version", "r-81be02"], ["Full evaluations traced", run.kind === "practice" ? "every one" : "1 in 30"]])}
      <div class="mt2"><span class="kicker">Money for the models (real dollars)</span></div>
      ${dl([["Estimated before the start", cents(run.est)], ["Spending cap (1.5 times)", cents(run.cap)], ["Spent", cents(run.spent)]])}
    </div></div>`;
}

/* ---------- the run page, three ways ---------- */
const RUN_TABS = [["overview", "Overview"], ["measurements", "Measurements"], ["trades", "Trades"], ["decisions", "Decisions"], ["track", "Track record"], ["settings", "Settings"]];
function runSection(run, tab, q, no) {
  return tab === "measurements" ? secMeasurements(run) : tab === "trades" ? secTrades(run, q) : tab === "decisions" ? secDecisions(run) : tab === "track" ? secTrackRecord(run) : tab === "settings" ? secSettings(run) : secOverview(run, no || 1);
}
function runNote() {
  return note("the run page", `One page per run. It is the brief's Live run, Overview, Trades, Learning, Patterns, and Calibration screens folded into one place. While a run replays, the top line, the chart, the positions, and the notable moments refresh every 5 seconds; a finished run shows the same page, standing still.
    <ul><li><b>Use the bar at the bottom</b> (or the ← → keys) to switch between three layouts of this same page: <b>A</b> tabs, <b>B</b> one long report, <b>C</b> day by day.</li>
    <li>Numbers are made up and do not add up across screens.</li></ul>`, "first");
}
function runA(run, q) {
  const tab = q.get("tab") || "overview", f = tradeFacts(run);
  return runNote() + runHeader(run) + `<nav class="tabs">${RUN_TABS.map(t => `<a class="${t[0] === tab ? "on" : ""}" href="${runHref(run.id, { tab: t[0] })}">${t[0] === "overview" && run.status === "running" ? "Now" : t[1]}${t[0] === "trades" ? `<sup>${f.all.length}</sup>` : ""}</a>`).join("")}</nav>` + runSection(run, tab, q);
}
function runB(run, q) {
  const titles = RUN_TABS.map(t => (t[0] === "overview" && run.status === "running" ? "Now" : t[1]));
  const rail = `<div class="sticky"><span class="kicker">On this page</span><ol class="list mt1">${titles.map((t, i) => `<li style="padding:.4rem 0"><a href="javascript:void 0" onclick="document.getElementById('sec${i}').scrollIntoView()"><span class="meta accent">0${i + 1}</span> &nbsp;<span style="font:600 1.05rem var(--display)">${t}</span></a></li>`).join("")}</ol>
    <div class="mt2"><span class="kicker">Notable moments</span></div><div class="mt1">${eventList(run)}</div></div>`;
  const body = RUN_TABS.map((t, i) => `<section id="sec${i}">${sechead("0" + (i + 1), titles[i])}${runSection(run, t[0], q, 1)}</section>`).join("");
  return runNote() + runHeader(run) + `<div class="g12 mt3"><div class="c3">${rail}</div><div class="c9"><div class="stack">${body}</div></div></div>`;
}
function runC(run, q) {
  const tab = q.get("tab") || "days", days = daysOf(run), done = days.filter(d => !d.future), f = tradeFacts(run);
  const tabs = [["days", "Days"], ["measurements", "Measurements"], ["track", "Track record"], ["settings", "Settings"]];
  const nav = `<nav class="tabs">${tabs.map(t => `<a class="${t[0] === tab ? "on" : ""}" href="${runHref(run.id, { tab: t[0] })}">${t[1]}${t[0] === "days" ? `<sup>${done.length}</sup>` : ""}</a>`).join("")}</nav>`;
  if (tab !== "days") return runNote() + runHeader(run) + nav + runSection(run, tab, q);
  const sel = q.has("day") ? +q.get("day") : done[done.length - 1].d, day = days[sel], top = Math.max(...done.map(d => Math.abs(d.change)));
  const shown = days.length > 31 ? days.slice(Math.max(0, done.length - 31)) : days;
  const list = shown.map(d => d.future ? `<div class="day future"><span class="d">${dayDate(run.start, d.d)}</span><span class="meta">${run.status === "running" && d.d === run.daysDone ? "replaying now" : "not replayed yet"}</span><span></span></div>` :
    `<a class="day ${d.d === sel ? "on" : ""}" href="${runHref(run.id, { tab: "days", day: d.d })}"><span class="d">${dayDate(run.start, d.d)}</span><span class="pl"><i style="${d.change >= 0 ? "left:50%" : "right:50%"};width:${(48 * Math.abs(d.change) / top).toFixed(1)}%"></i></span><span class="v">${sgn$(d.change)}</span>
      <span></span><span class="meta" style="grid-column:2 / span 2">${(k => k + (k === 1 ? " trade" : " trades"))(f.all.filter(t => t.d === d.d).length)}${d.limit ? ` · <b>daily loss limit reached</b>` : ""}${isWeekend(run.start, d.d) ? " · weekend: Bitcoin only" : ""}</span></a>`).join("");
  const dayTrades = f.all.filter(t => t.d === sel), intraday = walk(run.seed * 31 + sel, 24, 10000 + day.change, 60).map(v => v - 10000 + day.start);
  const xt = [0, 6, 12, 18, 24].map(h => ({ i: h * 4, label: hhmm(h * 60) }));
  const detail = `<span class="kicker">Day ${sel + 1} of ${run.days} · midnight to midnight UTC</span>
    <h2 class="display" style="font-size:clamp(1.9rem,3vw,3rem);margin:.3rem 0 1rem">${dayYear(run.start, sel)}: ${sgn$(day.change)}</h2>
    <dl class="statrow"><div><dt class="kicker">Started the day at</dt><dd class="num">${fmt$(day.start)}</dd></div><div><dt class="kicker">Ended it at</dt><dd class="num">${fmt$(day.end)}</dd></div><div><dt class="kicker">Trades opened</dt><dd class="num">${dayTrades.length}</dd></div><div><dt class="kicker">Charged at midnight</dt><dd class="num">$1.12 loan interest</dd></div></dl>
    ${day.limit ? `<div class="callout">Daily loss limit reached at 17:45 UTC: the account was down 5% since midnight, so code blocked entries and adds for the rest of the day. It closed nothing.</div>` : ""}
    <div class="mt2">${figure(1, "Account value through the day", "", lineChart({ series: [{ name: fmt$(day.end), vals: intraday, kind: "subject" }], xticks: xt, h: 240, ref: { v: day.start, label: "midnight " + fmt$(day.start) }, label: "Account value through one day" }), "one point per step · times in UTC · a stock's session runs 13:30 to 20:00 UTC")}</div>
    <div class="subhead">The day's trades</div>${dayTrades.length ? `<div class="tablewrap"><table>${TRADE_HEAD}<tbody>${tradeRows(run, dayTrades)}</tbody></table></div>` : `<div class="waiting"><span class="kicker">Nothing</span><p>No trade was opened on this day.</p></div>`}`;
  return runNote() + runHeader(run) + nav + `<div class="g12"><div class="c4"><span class="kicker">Each day's profit or loss · click a day</span><div class="rule mt1">${list}</div></div><div class="c8">${detail}</div></div>`;
}
function screenRun(id, q) {
  const run = runById(id) || RUNS[0];
  return V === "B" ? runB(run, q) : V === "C" ? runC(run, q) : runA(run, q);
}

/* ---------- the trade page ---------- */
function screenTrade(tid) {
  const { run, trade: t } = findTrade(tid), a = ASSETS[t.asset], stock = a.cls === "stock";
  const n = Math.max(stock ? 26 : 32, t.bars + 12), i0 = Math.min(stock ? t.bar : 6, n - t.bars - 2), i1 = i0 + t.bars;
  const up = (t.pl > 0) === (t.dir === "long"), bars = makeBars(run.seed * 13 + t.n, n, t.entry, up ? 0.12 : -0.12);
  const shift = t.entry - bars[i0].o; bars.forEach(b => { b.o += shift; b.c += shift; b.h += shift; b.l += shift; });
  /* the chart is drawn in real prices, so its axis reads in round real dollars; an open position has no bars after "now" */
  const real = b => ({ o: b.o * a.scale, c: b.c * a.scale, h: b.h * a.scale, l: b.l * a.scale }), drawn = (t.open ? bars.slice(0, i1 + 1) : bars).map(real);
  const stop = t.entry * (1 + (t.dir === "long" ? -1 : 1) * 0.006 * t.stopMoves), exit = t.reason === "stop" ? stop : bars[i1].o;
  const marks = [{ i: i0, price: t.entry * a.scale, text: "entry " + realPrice(t.asset, t.entry), kind: "in" }];
  for (let i = i0 + 1; i <= i1; i++) marks.push({ i, kind: "check", text: "position check" });
  if (!t.open) marks.push({ i: i1, price: exit * a.scale, text: (t.reason === "stop" ? "closed at its stop price " : t.reason === "run_end" ? "closed, run ended " : "closed by choice ") + realPrice(t.asset, exit), kind: "out" });
  const xt = []; for (let i = 0; i < n; i += 4) xt.push({ i, label: hhmm(((stock ? 13 * 60 + 30 : t.minutes - 90) + 15 * i + 1440) % 1440) });
  const units = t.size / (t.entry * 1.0005), slip = t.size * 0.0005, fee = stock ? 1 : t.size * 0.001, loss = t.size * 0.006 * t.stopMoves;
  const checks = []; const r = rng(t.n * 17 + run.seed);
  for (let i = 1; i <= Math.min(t.bars, 6); i++) { const last = i === Math.min(t.bars, 6) && !t.open && t.reason === "choice", c = last ? 0.58 : 0.08 + r() * 0.2, h = last ? 0.27 : 0.62 + r() * 0.1; checks.push({ i, h, c, red: (1 - h - c) * 0.6, add: (1 - h - c) * 0.4, did: last ? "close" : "hold", pl: t.pl * i / t.bars + (r() - 0.5) * 12 }); }
  const journal = [
    ["Screen said yes", when(run, t), "0.71, above the cut-off of 0.5"], ["The LLM selected 3 past episodes", "", "2 lookups of 6 used"], ["Jev picked a " + t.dir, "", `stop price ${t.stopMoves} typical ${t.stopMoves === 1 ? "move" : "moves"} away`],
    ["Jev sized it at " + fmt$(t.chosen), "", t.trimmed ? `code trimmed it to ${fmt$(t.size)}: ${t.limit}` : "inside every limit"], ["Order carried out", "next bar's open", "at " + realPrice(t.asset, t.entry * 1.0005)],
    [`${t.bars} position ${t.bars === 1 ? "check" : "checks"}`, "", "one every 15 minutes"]].concat(t.open ? [["Still open", "", "the next check comes with the next bar"]] : [[{ choice: "Jev chose to close it", stop: "Stop price reached", run_end: "The run ended", forced: "Forced close" }[t.reason], "after " + held(t), sgn$(t.pl) + " after trading costs"]]);
  const dl = pairs => `<dl class="pairs">${pairs.map(p => `<dt class="small">${p[0]}</dt><dd>${p[1]}</dd>`).join("")}</dl>`;
  return note("the trade page", `Everything about one trade on one page, the way a trader reviews a trade afterwards: the price chart with the entry and the close marked, then what was decided at each moment and why. It replaces the brief's Trade detail. The target price is gone from version 1, so no chart shows one.`, "first") + `
    <div class="g12"><div class="c8">
      <span class="kicker"><a href="${runHref(run.id, { tab: "trades" })}">← ${run.title}</a> &nbsp;·&nbsp; trade ${t.n} · ${t.open ? "open position" : "closed trade"}</span>
      <h1 class="display title">${a.name}, ${t.dir}: ${sgn$(t.pl)}${t.open ? " so far" : ""}</h1>
      <p class="meta mt1"><span class="chip">${t.asset}</span> ${a.symbol} · ${a.cls} · opened ${when(run, t)} UTC${stock ? " · bar " + t.bar + " of 26, " + t.part : " · " + t.part} · held ${held(t)} · ${t.open ? "still open" : REASONS[t.reason]}</p>
    </div><div class="c4" style="align-self:end;text-align:right"><a class="btn" href="${href("decision/" + t.id)}">The exchange behind the entry →</a></div></div>
    <div class="g12 mt3"><div class="c3"><div class="sticky"><span class="kicker">The trade, step by step</span><ol class="list timeline mt1">${journal.map(j => `<li><span class="mk"></span><div style="flex:1"><span class="t">${j[0]}</span>${j[1] ? ` <span class="meta">${j[1]}</span>` : ""}<div class="small muted">${j[2]}</div></div></li>`).join("")}</ol></div></div>
    <div class="c9"><div class="stack">
      ${figure(1, `${a.name} around the trade`, `<span><i class="sw"></i>this trade</span><span>hollow bar: price rose · filled bar: price fell</span><span>□ position check</span>`,
        candleChart({ bars: drawn, n, marks, stop: stop * a.scale, span: [i0, i1], fmt: money2, xticks: xt, label: "Candle chart around the trade" }),
        `15-minute bars · real prices (the agent saw them rescaled: ${t.entry.toFixed(2)} for ${realPrice(t.asset, t.entry)}) · times in UTC · the shaded stretch is the time the position was open`)}
      <section><div class="g12" style="row-gap:2rem"><div class="c5">
        <div class="subhead" style="margin-top:0">The order</div>
        ${dl([["Size Jev chose", fmt$(t.chosen)], ["Size after trimming", t.trimmed ? `${fmt$(t.size)} <span class="badge out">${t.limit}</span>` : fmt$(t.size) + " (not trimmed)"], ["Would lose at its stop price", fmt$(loss) + " (limit " + fmt$(0.01 * run.value) + ")"], ["Units", units.toFixed(a.cls === "crypto" ? 4 : 2)], ["Price before slippage", priceTag(t.asset, t.entry)], ["Price paid", priceTag(t.asset, t.entry * (t.dir === "long" ? 1.0005 : 0.9995))], ["Slippage cost", cents(slip)], [stock ? "Commission" : "Trading fee", cents(fee)]])}
        <div class="subhead">Nightly charges</div>
        ${t.overnight ? dl([["Loan interest, 1 night", "$0.84"], t.dir === "short" ? ["Borrow fee, 1 night", "$0.04"] : ["Borrow fee", "none: not a short"]]) : `<p class="small muted">None. It was opened and closed within the day, so it paid no loan interest and no borrow fee.</p>`}
      </div><div class="c7">
        <div class="subhead" style="margin-top:0">Position checks <span class="kicker">Jev's answer every 15 minutes</span></div>
        ${checks.length ? `<div class="tablewrap"><table style="min-width:0"><thead><tr><th>Bar</th><th class="num">Then</th><th class="num">Hold</th><th class="num">Close</th><th class="num">Reduce</th><th class="num">Add</th><th>Done</th><th></th></tr></thead><tbody>${checks.map(c => `<tr><td class="num" style="text-align:left">+${c.i}</td><td class="num">${sgn$(c.pl)}</td><td class="num">${c.h.toFixed(2)}</td><td class="num">${c.c.toFixed(2)}</td><td class="num">${c.red.toFixed(2)}</td><td class="num">${c.add.toFixed(2)}</td><td class="small">${c.did}</td><td class="num"><a class="chip" href="${href("decision/" + t.id)}">→</a></td></tr>`).join("")}</tbody></table></div><p class="meta mt1">${t.bars > 6 ? "first 6 of " + t.bars + " shown · " : ""}each number is the probability Jev gave that option</p>` : `<p class="small muted">None yet.</p>`}
      </div></div></section>
      <section>${sechead("§", "Entry memory", "what Jev read when it opened this position, and again at every check")}
        ${run.variant === "memory_on" ? `<div class="g12" style="row-gap:1.5rem"><div class="c5"><span class="kicker">Track record lines</span><ol class="list mt1"><li class="small"><b>${t.pattern}, ${t.dir}, ${a.cls === "stock" ? "stocks" : "Bitcoin"}:</b> 38 closed trades, 58% made money, average gain +$71, average loss −$52.</li><li class="small"><b>hammer, ${t.dir}, ${a.cls === "stock" ? "stocks" : "Bitcoin"}:</b> 6 closed trades, too few to show totals.</li></ol></div>
        <div class="c7"><span class="kicker">Selected episodes · chosen by the LLM from 14 it was shown</span><ol class="list mt1">${[["41 days ago", "same asset", "long, closed by choice after 9 bars: +$64 (+1.1%)"], ["112 days ago", "another stock", "long, closed at its stop price after 3 bars: −$48 (−0.9%)"], ["203 days ago", "same asset", "no trade: price went +0.4% after 4 bars"]].map((e, i) => `<li class="small"><a class="chip ink" href="${href("decision/" + t.id)}">E-${48213 + i * 977}</a> ${e[0]} · ${e[1]} · ${e[2]}</li>`).join("")}</ol></div></div>` : `<div class="waiting"><span class="kicker">Not for this run</span><p>This run trades without memory, so Jev read no past episodes and no track record.</p></div>`}
      </section>
    </div></div></div>`;
}

/* ---------- the exchange behind one decision ---------- */
function screenDecision(tid) {
  const { run, trade: t } = findTrade(tid), a = ASSETS[t.asset], p = t.entry.toFixed(2), mem = run.variant === "memory_on";
  const msg = (who, text, side, reply) => `<div class="msg ${reply ? "reply" : ""}"><div><span class="kicker ${reply ? "accent" : ""}">${who}</span><pre>${esc(text)}</pre></div><div class="side">${side}</div></div>`;
  const situation = `${a.cls === "stock" ? "Stock, " + t.part + " (bar " + t.bar + " of 26)" : "Crypto, " + t.part}. Patterns in the last 4 bars: ${t.pattern} (this bar), hammer (2 bars ago). Latest hourly bar: none. Latest daily bar: doji. Last 8 bars: five up, three down; this bar is a large up bar closing near its high. Short-term trend up (1.5 typical moves above the 20-bar average). Long-term trend up (2.1 above the 20-day average). Volume high (1.8 times normal). …`;
  const llm = !mem ? `<div class="waiting"><span class="kicker">Not for this run</span><p>This run trades without memory: the LLM is never called and Jev reads no past episodes.</p></div>` :
    msg("Code → the LLM · message 1 · standing instructions and tools stored once for prompt version p-3fa9c1", `[standing instructions: 412 words, shown on demand]\n\nThe situation now:\n${situation}\n\nThe 10 most similar past episodes:\nE-48213 · 41 days ago · same asset · first hour · long-term trend up · volume high · ${t.pattern}, hammer · long · closed by choice after 9 bars, +$64 (+1.1%)\nE-49190 · 112 days ago · another stock · first hour · long-term trend up · volume high · ${t.pattern} · long · closed at its stop price after 3 bars, -$48 (-0.9%)\n… 8 more lines`, `<b>What the LLM is sent.</b> The situation text alone, nothing about the account, then ten one-line episode summaries.`) +
    msg("The LLM → code · lookups used: 1 of 6", `tool call: search_episodes(direction="long", part_of_day="first hour")`, `<b>A lookup:</b> it asks memory for a narrower search.`, true) +
    msg("Code → the LLM", `4 episodes:\nE-50167 · 203 days ago · same asset · first hour · … · no trade · price went +0.4% after 4 bars\n… 3 more lines`, `What the memory server returned.`) +
    msg("The LLM → code · lookups used: 2 of 6", `tool call: read_episodes(ids=["E-48213", "E-50167"])`, `It opens two episodes in full before choosing.`, true) +
    msg("Code → the LLM", `[the two episodes in full: 31 lines]`, ``) +
    msg("The LLM → code · its answer", `tool call: select_episodes(ids=["E-48213", "E-49190", "E-50167"], note="Same pattern in the first hour with high volume; one winner, one stopped out, one no-trade.")`, `<b>Its answer:</b> the selected episodes and its note. Things this box can be marked with: <span class="badge">lookup refused at the limit of 6</span> <span class="badge">reply was not a tool call, asked again</span> <span class="badge">named an episode it was never shown</span>`, true);
  return note("the exchange behind one decision", `Asked for on 2026-11-19: from any step or any trade, read the whole chain word for word. The left column is the exact text that was sent and received, read from storage and never rebuilt, so it shows masked IDs and rescaled prices. The right column is plain words. The layout copies the two walkthrough pages. In this prototype every decision shows the same made-up chain, shortened with "…".`, "first") + `
    <div class="g12"><div class="c8">
      <span class="kicker"><a href="${href("trade/" + t.id)}">← Trade ${t.n}: ${a.name}, ${t.dir}</a> &nbsp;·&nbsp; full evaluation · ${when(run, t)} UTC · step ${(stepAt(run, t.d) + Math.round(t.minutes / 15)).toLocaleString("en-US")}</span>
      <h1 class="display title">Why it opened a ${t.dir} in ${a.name}</h1>
    </div><div class="c4" style="align-self:end">
      <div class="why small"><span class="kicker">Key to the text below</span><br><span class="chip">${t.asset}</span> is <b>${a.name}</b> (${a.symbol}). Prices in the boxes are rescaled: <span class="mono">${p}</span> there is <b>${realPrice(t.asset, t.entry)}</b>. Days are counted, not dated.</div>
      <p class="mt1" style="text-align:right"><button class="btn" ${run.kind === "practice" ? "" : "disabled"} title="Only 1 full evaluation in 30 is traced on a measurement run">Trace ↗</button></p>
    </div></div>
    <div class="stack mt3">
      <section>${sechead("01", "The screen", "Jev · is a full evaluation worth running now?")}
        ${msg("Code → Jev · reading version r-81be02 · about 1,150 tokens", `# The task\nThis is a trading account in a replay of market history. …\n\n# The account now\nAccount value: $10,140.\nCash: $7,122. Loan: none.\nOpen positions: 1, worth $3,018.\n\n# The asset: ${t.asset} (${a.cls})\nLast price: $${p}. Typical move in one bar: $0.63.\n${situation}\n\nQuestion: Is a full evaluation of this asset worth running now? (a number from 0 to 1)`, `<b>The background and the question.</b> A screen reads no memory.`)}
        ${msg("Jev → code · 0.17 seconds", `0.71`, `<b>0.71 is above the cut-off of 0.5,</b> so a full evaluation runs. Under it, nothing more would happen at this step.`, true)}</section>
      <section>${sechead("02", "The LLM selects past episodes", mem ? "claude-haiku-5-5 · 2 lookups of 6 · 4.1 seconds · $0.0021" : "")}${llm}</section>
      <section>${sechead("03", "The pick", "Jev · which candidate trade, or no trade?")}
        ${msg("Code → Jev · about 3,400 tokens", `[the background again, now with the track record lines and the ${mem ? "3 selected episodes" : "note that no memory is read"}]\n\nQuestion: Which trade, if any?\n- long, tight stop price ($${(t.entry * 0.994).toFixed(2)})\n- long, medium stop price ($${(t.entry * 0.988).toFixed(2)})\n- long, wide stop price ($${(t.entry * 0.982).toFixed(2)})\n- short, tight stop price …\n- short, medium stop price …\n- short, wide stop price …\n- no trade`, `<b>The candidate trades</b> are listed by code: a direction and a stop price each.`)}
        ${msg("Jev → code · average of 5 shuffled copies", `${t.dir}, tight 0.14 · ${t.dir}, medium 0.31 · ${t.dir}, wide 0.22 · other direction 0.09 (three options) · no trade 0.24\n\nby direction: ${t.dir} 0.67 · ${t.dir === "long" ? "short" : "long"} 0.09 · no trade 0.24\npick: ${t.dir}, ${["tight", "medium", "wide"][t.stopMoves - 1]} stop price`, `<b>Probabilities are added by direction first,</b> then the best option inside the winning direction is taken.`, true)}</section>
      <section>${sechead("04", "The size", "Jev · how much money to put in?")}
        ${msg("Code → Jev", `Question: How much to put into this trade?\n- $2,028 (20% of account value): loses $${(2028 * 0.006 * t.stopMoves).toFixed(0)} at the stop price\n- $4,056 (40%) …\n- $8,112 (80%) …\n- $12,168 (120%) …\n- $20,280 (200%): code would open at most ${fmt$(Math.min(20280, 101.4 / (0.006 * t.stopMoves)))}`, `Each size option states what it would lose at the stop price, and the most code would open.`)}
        ${msg("Jev → code", `20% 0.18 · 40% 0.27 · 80% 0.33 · 120% 0.16 · 200% 0.06\nweighted average: ${fmt$(t.chosen)}`, `<b>The size is the average of the five,</b> weighted by Jev's probabilities.`, true)}
        <div class="callout" style="background:none">${t.trimmed ? `Code trimmed ${fmt$(t.chosen)} to ${fmt$(t.size)}: at its stop price the trade would otherwise have lost more than the ${t.limit === "trade risk limit" ? "trade risk limit allows (1% of account value)" : "exposure limit leaves room for"}.` : `${fmt$(t.chosen)} was inside every risk limit, so code opened it as chosen.`} The order was carried out at the next bar's open. <a class="chip hot" href="${href("trade/" + t.id)}">see the trade →</a></div></section>
    </div>`;
}
