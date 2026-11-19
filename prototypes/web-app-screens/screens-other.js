/* PROTOTYPE. Every screen other than the run, trade, and decision pages, plus the guide. */

function masthead(active) {
  const nav = [["runs", "Runs"], ["comparison", "Comparison"], ["datasets", "Datasets"], ["playbook", "Playbook"], ["spending", "Spending"]];
  return `<header class="mast"><a class="wordmark" href="${href("runs")}">jev<span class="accent">/</span>trader</a>
    <nav>${nav.map(n => `<a class="${n[0] === active ? "on" : ""}" href="${href(n[0])}">${n[1]}</a>`).join("")}</nav>
    <a class="kicker spend" href="${href("spending")}">models: <b style="color:var(--ink)">${cents(totalSpent())}</b> of $${CEILING} spent</a></header>`;
}

/* ---------- runs ---------- */
function screenRuns() {
  const running = RUNS.filter(r => r.status === "running"), spent = totalSpent();
  let rows = "";
  Object.keys(KINDS).forEach(k => {
    const list = RUNS.filter(r => r.kind === k); if (!list.length) return;
    rows += `<tr class="group"><td colspan="7"><span style="font:600 1.25rem var(--display)">${KINDS[k]}</span> <span class="kicker">&nbsp;${{ measurement: "their results count", "build-up": "fills the base memory; its results never count", tuning: "short runs to adjust the agent; never count", practice: "one day on the real paid services; never count" }[k]}</span></td></tr>`;
    list.forEach(r => {
      const d = r.value - r.holding, n = tradesOf(r).length;
      rows += `<tr class="click" onclick="location.hash='${runHref(r.id)}'"><td><b style="font:600 1rem var(--display)">${r.market ? r.market + " · " + VARIANT_WORDS[r.variant] + " · repeat " + r.repeat : r.title}</b><div class="meta">${r.label}${r.market ? "" : " · " + VARIANT_WORDS[r.variant]}${r.note ? " · " + r.note : ""}</div></td>
        <td>${statusBadge(r)}</td><td class="num">${r.daysDone} of ${r.days}</td><td class="num">${fmt$(r.value)}</td><td class="num">${sgn$(d)}</td><td class="num">${r.kind === "build-up" ? "1,912" : n}</td><td class="num">${cents(r.spent)} <span class="muted">/ ${cents(r.cap)}</span></td></tr>`;
    });
  });
  return note("runs", `The home screen: every run, grouped by kind. Holding the five assets is stored as a run of its own, but here it is the "against holding" column, so each line answers "did trading beat doing nothing?" at a glance. For tuning, this table is how two tuning runs are compared side by side. Replaces the brief's Runs.`, "first") + `
    <div class="g12"><div class="c3">
      <span class="kicker">Spent on the models · all of version 1</span>
      <div class="keyfig mt1">${cents(spent)} <small>of $${CEILING}</small></div>${track(spent / CEILING)}
      <p class="meta">real dollars paid to Jev and the LLM · <a href="${href("spending")}" style="text-decoration:underline">where it went →</a></p>
      <div class="mt2"><span class="kicker">Running now</span></div>
      <ol class="list timeline mt1">${running.map(r => `<li><span class="mk run"></span><a style="flex:1" href="${runHref(r.id)}"><span class="t">${r.market}, ${VARIANT_WORDS[r.variant]}</span><div class="small muted">day ${r.daysDone + 1} of ${r.days} · ${fmt$(r.value)}</div></a></li>`).join("")}</ol>
      <p class="mt2"><a class="btn hot wide" href="${href("new-run")}">New run →</a></p>
    </div><div class="c9">
      <h1 class="display title" style="margin-bottom:1.5rem">Runs</h1>
      <div class="tablewrap"><table><thead><tr><th>Run</th><th>Status</th><th class="num">Days</th><th class="num">Account value</th><th class="num">Against holding</th><th class="num">Trades</th><th class="num">Spent / cap</th></tr></thead><tbody>${rows}</tbody></table></div>
      <p class="meta mt1">${RUNS.length} runs · every run starts with $10,000 · "against holding" is the run's account value minus what holding the five assets ended with over the same days</p>
    </div></div>`;
}

function screenNewRun() {
  const left = CEILING - totalSpent();
  const f = (label, control, help) => `<label class="f"><span>${label}</span>${control}${help ? `<small>${help}</small>` : ""}</label>`;
  const sel = opts => `<select>${opts.map(o => `<option>${o}</option>`).join("")}</select>`;
  return note("new run", `Starting a run from the app. The app shows the estimated cost before the start and sets the spending cap at one and a half times that. Code refuses three kinds of run; all three refusals are shown at once on the right so you can see how they read. The first runs (practice and tuning) are started from the command line, so this screen can come later.`, "later") + `
    <span class="kicker"><a href="${href("runs")}">← All runs</a></span><h1 class="display title" style="margin-bottom:2rem">New run</h1>
    <div class="g12"><div class="c5">
      ${f("kind", sel(["measurement", "tuning", "build-up", "practice"]), "A measurement run counts toward the verdict. The other three never do.")}
      ${f("dataset", sel(["first dataset v1 · published"]), "Only published datasets are listed.")}
      ${f("stretch of the test period", sel(["Rising market · 9 Apr to 8 May 2025", "Falling market · 10 Mar to 8 Apr 2025"]), "A tuning, build-up, or practice run picks its own dates instead, outside the test period.")}
      ${f("variant", sel(["both sides of a repeat: with memory and without, side by side", "with memory only", "without memory only"]), "The two runs of a repeat start together, so both face the same version of Jev.")}
      ${f("repeat", `<input value="2">`, "Repeat 1 is running. Three are planned for each market.")}
      ${f("memory to start from", sel(["the base memory · left by the build-up run · 1,912 closed trades"]), "Each run with memory gets its own fresh copy.")}
      ${f("starting account value", `<input value="$10,000">`)}
      ${f("risk profile", sel(["medium"]), "Its settings are frozen. Only a tuning run may change them.")}
    </div><div class="c7">
      <span class="kicker">What it will cost · real dollars</span>
      <div class="keyfig mt1">$3.30 <small>estimated</small></div>
      <dl class="pairs mt2"><dt class="small">With memory, 30 days at about $0.08</dt><dd>$2.40</dd><dt class="small">Without memory, 30 days at about $0.03</dt><dd>$0.90</dd><dt class="small">Spending cap for the pair (1.5 times the estimate)</dt><dd>$4.95</dd><dt class="small">Still unspent under the $${CEILING} ceiling</dt><dd>${cents(left)}</dd><dt class="small">Unspent after this run, at worst</dt><dd>${cents(left - 4.95)}</dd></dl>
      <p class="mt2"><button class="btn hot wide">Start both runs →</button></p>
      <div class="subhead">What the app refuses <span class="kicker">prototype: all three shown at once</span></div>
      <div class="callout" role="alert">A tuning run cannot touch the test period (10 March to 8 May 2025). Pick dates outside it.</div>
      <div class="callout" role="alert">This memory holds records from after the run's first day. A run may only start from a memory whose records all end before it begins.</div>
      <div class="callout" role="alert">This run's spending cap ($4.95) could take the project's total past the $${CEILING} ceiling. Raising the ceiling is the developer's decision.</div>
    </div></div>`;
}

/* ---------- comparison ---------- */
function verdictOf(market) {
  const pick = v => RUNS.filter(r => r.kind === "measurement" && r.market === market && r.variant === v).sort((a, b) => a.repeat - b.repeat);
  const on = pick("memory_on"), off = pick("memory_off");
  if (on.length < 3 || on.concat(off).some(r => r.status !== "finished")) return { on, off, ready: false };
  const a = on.map(r => r.value), b = off.map(r => r.value), diff = mean(a) - mean(b), threshold = Math.sqrt((sd(a) ** 2 + sd(b) ** 2) / 2);
  return { on, off, ready: true, a, b, diff, threshold, words: diff > threshold ? "Memory helped" : diff < -threshold ? "Memory hurt" : "Can't tell" };
}
function screenComparison() {
  const section = (market, no) => {
    const v = verdictOf(market), m = MARKETS[market];
    if (!v.ready) return `<section>${sechead(no, market, m.label)}<div class="waiting"><span class="kicker">Not yet</span><p>No repeat has finished yet. A verdict needs all three.</p></div>
      <ol class="list">${v.on.concat(v.off).map(r => `<li style="display:flex;gap:.75rem;align-items:baseline"><a href="${runHref(r.id)}" style="font:600 1rem var(--display)">${r.title}</a> ${statusBadge(r)} <span class="meta" style="margin-left:auto">day ${r.daysDone + 1} of ${r.days} · ${fmt$(r.value)} so far</span></li>`).join("")}<li class="muted small">Repeats 2 and 3 have not been started.</li></ol></section>`;
    const avg = runs => seriesOf(runs[0]).agent.map((_, i) => mean(runs.map(r => seriesOf(r).agent[i])));
    const on = avg(v.on), off = avg(v.off), hold = walk(900 + no.length, m.days, m.holdingEnd, 120), xt = []; for (let d = 0; d <= m.days; d += 5) xt.push({ i: d * 4, label: dayDate(m.start, d) });
    return `<section>${sechead(no, market, m.label + " · 3 repeats")}
      <div class="g12"><div class="c4">
        <span class="kicker">Verdict</span><div class="keyfig mt1 ${v.words === "Can't tell" ? "muted" : ""}">${v.words}</div>
        <p class="lede mt2">With memory the agent ended <b class="accent">${fmt$(Math.abs(v.diff))} ${v.diff >= 0 ? "higher" : "lower"}</b> on average. That is ${Math.abs(v.diff) > v.threshold ? "more" : "less"} than the <b>${fmt$(v.threshold)}</b> by which repeats differ from each other by chance.</p>
        <dl class="pairs mt2"><dt class="small">Average with memory</dt><dd>${fmt$(mean(v.a))}</dd><dt class="small">Average without memory</dt><dd>${fmt$(mean(v.b))}</dd><dt class="small">Difference</dt><dd>${sgn$(v.diff)}</dd><dt class="small">Threshold: 1 standard deviation</dt><dd>${fmt$(v.threshold)}</dd><dt class="small">Holding the five assets ended at</dt><dd>${fmt$(m.holdingEnd)}</dd></dl>
        <p class="small muted mt2">The standard deviation says how far repeats typically land from their average. If memory did nothing at all, luck alone would still give "helped" about 1 time in 7.</p>
      </div><div class="c8">
        ${figure(no === "01" ? 1 : 3, "Account value, with memory against without", `<span><i class="sw"></i>with memory</span><span><i class="sw ctx"></i>without memory</span><span><i class="sw ref" style="border-top:1.25px dotted var(--ink)"></i>holding the five assets</span>`,
          lineChart({ series: [{ name: "with memory " + fmt$(mean(v.a)), vals: on, kind: "subject" }, { name: "without " + fmt$(mean(v.b)), vals: off, kind: "context" }, { name: "holding " + fmt$(m.holdingEnd), vals: hold, kind: "dashed" }], xticks: xt, ref: { v: 10000, label: "start $10,000" }, label: "Average account value with and without memory" }),
          "each line is the average of 3 runs · 4 points a day · prototype: made-up numbers, except what holding ended at")}
        <div class="tablewrap mt2"><table style="min-width:0"><thead><tr><th>Repeat</th><th class="num">With memory</th><th class="num">Without memory</th><th class="num">Difference</th></tr></thead><tbody>
          ${v.on.map((r, i) => `<tr><td class="mono small">${r.repeat}</td><td class="num"><a href="${runHref(r.id)}" style="text-decoration:underline">${fmt$(r.value)}</a></td><td class="num"><a href="${runHref(v.off[i].id)}" style="text-decoration:underline">${fmt$(v.off[i].value)}</a></td><td class="num">${sgn$(r.value - v.off[i].value)}</td></tr>`).join("")}
          <tr><td><b>Average</b></td><td class="num">${fmt$(mean(v.a))}</td><td class="num">${fmt$(mean(v.b))}</td><td class="num">${sgn$(v.diff)}</td></tr>
          <tr><td>Standard deviation</td><td class="num">${fmt$(sd(v.a))}</td><td class="num">${fmt$(sd(v.b))}</td><td class="num muted">combined ${fmt$(v.threshold)}</td></tr></tbody></table></div>
      </div></div>
      <div class="g12 mt3"><div class="c4"><div class="subhead" style="margin-top:0">What memory did</div>
        <dl class="pairs"><dt class="small">The LLM took the top results as they came</dt><dd>41%</dd><dt class="small">It picked a more one-sided set than it was shown</dt><dd>19%</dd><dt class="small">The text ranking helped</dt><dd>33%</dd></dl>
        <p class="small muted mt1">The same memory measurements as on each run's page, averaged over the three runs with memory.</p>
      </div><div class="c8">
        ${figure(no === "01" ? 2 : 4, "The gap between the two averages, day by day", "", lineChart({ series: [{ name: sgn$(v.diff), vals: on.map((x, i) => x - off[i]), kind: "subject" }], xticks: xt, h: 240, yfmt: sgn$, ref: { v: 0, label: "no difference" }, label: "Difference between the two averages over time" }), "with memory minus without · above the dashed line, memory is ahead")}
      </div></div></section>`;
  };
  return note("comparison", `The screen that answers the project's question: does the agent end with more money when it has memory? One verdict per market, never merged. It replaces the brief's Overview and Learning. It is not needed for tuning (tuning runs have no memory), so it is built later, before the measurement runs.`, "later") + `
    <span class="kicker">Measurement runs · memory on against memory off</span><h1 class="display title" style="margin-bottom:2.5rem">Did memory help?</h1>
    <div class="stack">${section("Falling market", "01")}${section("Rising market", "02")}</div>`;
}

/* ---------- datasets ---------- */
function screenDatasets() {
  const f = (label, control, help) => `<label class="f"><span>${label}</span>${control}${help ? `<small>${help}</small>` : ""}</label>`;
  return note("datasets, with the new dataset form", `The brief's Datasets and New dataset screens, on one page. The dataset builder works from the command line first, so these screens come later. Futures and options are gone from the form.`, "later") + `
    <div class="g12"><div class="c4">
      <span class="kicker">Build a new dataset</span>
      ${f("assets", `<input placeholder="search by name or symbol">`, `<span class="chip ink">SPY ×</span> <span class="chip ink">AAPL ×</span> <span class="chip ink">JPM ×</span> <span class="chip ink">XOM ×</span> <span class="chip ink">BTCUSDT ×</span>`)}
      ${f("first day", `<input value="2023-04-03">`)}${f("last day", `<input value="2026-10-31">`)}
      ${f("test period", `<input value="2025-03-10 to 2025-04-08 · falling market">`, "One or more stretches, each with a name. Every other day is development period; its first three months are the warm-up period, in which no run trades.")}
      <p class="mt2"><button class="btn hot wide">Build →</button></p>
      <p class="small muted mt1">A published dataset never changes. A different asset list is a new dataset.</p>
    </div><div class="c8">
      <h1 class="display title" style="margin-bottom:1.5rem">Datasets</h1>
      <ol class="list">
        <li><a href="${href("dataset")}" style="display:block"><div style="display:flex;gap:.75rem;align-items:baseline;flex-wrap:wrap"><span style="font:600 1.5rem var(--display)">first dataset v1</span><span class="badge ink">published</span><span class="meta" style="margin-left:auto">built 20 Nov 2026 · 14 runs use it</span></div>
          <div class="small">S&P 500 fund, JPMorgan, Apple, Exxon, Bitcoin · 3 Apr 2023 to 31 Oct 2026 · test period 10 Mar to 8 May 2025</div><div class="meta">quality: at most 0.09% of bars missing (limit 0.5%) · at most 17 partial-volume days per stock (limit 26)</div></a></li>
        <li><div style="display:flex;gap:.75rem;align-items:baseline;flex-wrap:wrap"><span style="font:600 1.5rem var(--display)" class="muted">first dataset v0</span><span class="badge fill">failed</span><span class="meta" style="margin-left:auto">19 Nov 2026</span></div>
          <div class="callout">Build refused to publish: Exxon had 3.4% of its sessions as partial-volume days (limit 3%). Nothing was kept.</div></li>
      </ol></div></div>`;
}
function screenDataset() {
  const ids = Object.keys(ASSETS), q = { ASSET_01: [0.03, 6], ASSET_02: [0.05, 11], ASSET_03: [0.02, 8], ASSET_04: [0.09, 17], ASSET_05: [0.04, 0] };
  const stages = [["Download bars", "5 assets · 412,300 bars · 20 lead-in sessions"], ["Check the data", "missing bars and partial-volume days found"], ["Mask", "masked IDs, rescaled prices, step numbers"], ["Work out candle patterns and measurements", "61 patterns · 58 measurements"], ["Embed the situation texts", "412,300 texts"], ["Publish", "20 Nov 2026 14:02"]];
  const periods = [["warm-up", 3, "no run trades"], ["development", 20.3, "tuning and the build-up run"], ["falling", 1, ""], ["rising", 1, ""], ["development", 17.7, ""]];
  return note("dataset", `The brief's Dataset detail: build progress, the quality report, the asset key, and a price chart of each asset. This is the one screen where the asset key (real names and price scales) is shown as a table.`, "later") + `
    <div class="g12"><div class="c9"><span class="kicker"><a href="${href("datasets")}">← All datasets</a> &nbsp;·&nbsp; dataset</span><h1 class="display title">First dataset v1</h1>
      <p class="meta mt1"><span class="badge ink">published</span> &nbsp;3 Apr 2023 to 31 Oct 2026 · 4 stocks and Bitcoin · 15-minute bars · stocks from Twelve Data, Bitcoin from Binance</p></div></div>
    <div class="g12 mt3"><div class="c3"><div class="sticky"><span class="kicker">The build</span><ol class="list timeline mt1">${stages.map((s, i) => `<li><span class="mk"></span><div style="flex:1"><span class="meta">0${i + 1}</span> <span class="t">${s[0]}</span><div class="small muted">${s[1]}</div></div></li>`).join("")}</ol></div></div>
    <div class="c9"><div class="stack">
      <section>${sechead("01", "Periods", "what each stretch of days is for")}
        <div style="display:flex;border:2px solid var(--ink);height:2.6rem">${periods.map(p => `<div title="${p[0]}" style="flex:${p[1]};${p[0] === "falling" || p[0] === "rising" ? "background:var(--accent)" : p[0] === "warm-up" ? "background:var(--hair)" : ""};border-right:1px solid var(--ink)"></div>`).join("")}</div>
        <div class="meta mt1" style="display:flex;justify-content:space-between"><span>3 Apr 2023</span><span>test period: falling market 10 Mar to 8 Apr 2025, rising market 9 Apr to 8 May 2025</span><span>31 Oct 2026</span></div>
        <p class="small muted mt1">Grey: the warm-up period (the first three months, in which no run trades). Accent: the test period, used only for final measurement. Everything else is development period.</p></section>
      <section>${sechead("02", "Quality report", "what the build found wrong with the data provider's bars")}
        <div class="tablewrap"><table><thead><tr><th>Asset</th><th class="num">Bars</th><th class="num">Missing for any other reason</th><th class="num">Partial-volume days</th><th>Verdict</th></tr></thead><tbody>${ids.map(id => `<tr><td>${assetTag(id)}</td><td class="num">${ASSETS[id].cls === "stock" ? "23,374" : "125,472"}</td><td class="num">${q[id][0].toFixed(2)}% <span class="muted">of 0.5%</span></td><td class="num">${ASSETS[id].cls === "stock" ? q[id][1] + ` <span class="muted">of 899 sessions, limit 26</span>` : `<span class="muted">none: trades around the clock</span>`}</td><td class="small">inside both limits</td></tr>`).join("")}</tbody></table></div>
        <p class="small muted mt1">A partial-volume day is a day on which the data provider's bars for a stock carry only part of the market's trading. The stock sits that day out: every bar it has that day counts as missing, and none is ever made up. Each number opens the list of days behind it.</p></section>
      <section>${sechead("03", "Asset key", "the only place real names live · never visible to the agent")}
        <div class="tablewrap"><table><thead><tr><th>Masked ID</th><th>Real name</th><th>Symbol</th><th>Asset class</th><th class="num">Price scale</th><th class="num">A rescaled 100.00 is really</th></tr></thead><tbody>${ids.map(id => `<tr><td><span class="chip">${id}</span></td><td><b style="font:600 1rem var(--display)">${ASSETS[id].name}</b></td><td class="mono small">${ASSETS[id].symbol}</td><td class="small">${ASSETS[id].cls}</td><td class="num">× ${ASSETS[id].scale}</td><td class="num">${realPrice(id, 100)}</td></tr>`).join("")}</tbody></table></div></section>
      <section>${sechead("04", "Prices", "the last session of each asset")}
        <div class="g12" style="row-gap:2rem">${ids.slice(0, 4).map((id, i) => `<div class="c5" style="grid-column:span 6">${figure(i + 1, ASSETS[id].name, "", candleChart({ bars: makeBars(70 + i, 26, ASSETS[id].base * ASSETS[id].scale, 0), h: 230, fmt: money2, label: "Candle chart" }), `${id} · 26 bars · real prices`)}</div>`).join("")}</div></section>
    </div></div></div>`;
}

/* ---------- playbook ---------- */
function screenPlaybook() {
  const shapes = { "bullish engulfing": "A falling bar followed by a larger rising bar whose body covers the first one's body.", hammer: "A small body at the top of the bar with a long lower shadow, at least twice the body.", doji: "Open and close are almost the same price: a bar with next to no body.", "bearish engulfing": "A rising bar followed by a larger falling bar whose body covers the first one's body.", "shooting star": "A small body at the bottom of the bar with a long upper shadow.", "belt-hold": "A long rising bar that opens at its low, with no lower shadow.", "spinning top": "A small body with an upper and a lower shadow both longer than the body.", harami: "A long falling bar followed by a small rising bar whose body sits inside the first one's body.", "three white soldiers": "Three long rising bars in a row, each closing higher than the last.", "dark cloud cover": "A long rising bar followed by a falling bar that opens above its high and closes below its middle." };
  return note("playbook", `The brief's Playbook. Each entry is a candle pattern's name, its lean, and its shape, exactly as TA-Lib gives them. Version 1 has no textbook meanings (out of scope), so there is no "traditional meaning" column.`, "later") + `
    <div class="g12"><div class="c3"><span class="kicker">Reference · shared by all runs</span><h1 class="display title">Playbook</h1>
      <p class="small muted mt2">A candle pattern is a named shape of one to five bars that traders read as a hint about where the price goes next. Its lean is that hint: bullish (the price will rise), bearish (it will fall), or neutral.</p>
      <div class="filters mt2"><span class="tog on">All <span>61</span></span><span class="tog">Bullish <span>27</span></span><span class="tog">Bearish <span>25</span></span><span class="tog">Neutral <span>9</span></span></div></div>
    <div class="c9"><ol class="list">${PATTERNS.map(p => `<li class="g12" style="row-gap:.2rem"><div class="c3"><span style="font:600 1.25rem var(--display)">${p}</span><br><span class="badge ${LEANS[p] === "neutral" ? "" : "ink"}">${LEANS[p]}</span></div><div class="c9 small">${shapes[p]}<div class="meta">recognised on 15-minute, hourly, and daily bars · <a href="${runHref("rise-on-1", { tab: "track" })}" style="text-decoration:underline">its track record in a run →</a></div></div></li>`).join("")}</ol>
      <p class="meta mt1">10 of 61 shown · TA-Lib 0.8.3</p></div></div>`;
}

/* ---------- spending ---------- */
function screenSpending() {
  const spent = totalSpent(), sumKind = k => RUNS.filter(r => r.kind === k).reduce((s, r) => s + r.spent, 0);
  const plan = [["Build-up run", 10.20, sumKind("build-up")], ["Measurement runs", 19.80, sumKind("measurement")], ["Tuning runs", 5.00, sumKind("tuning")], ["Trial week with memory", 0.60, 0], ["Practice runs and saving test answers", 2.00, sumKind("practice") + OUTSIDE_RUNS[1].spent], ["LLM benchmark", 1.00, OUTSIDE_RUNS[0].spent]];
  const caps = RUNS.filter(r => r.status === "running").reduce((s, r) => s + r.cap - r.spent, 0);
  return note("spending", `New, not in the brief. Every paid call to Jev and the LLM is stored, including calls made outside any run, so the project's total is one sum. The masthead shows the total on every screen from the first dashboard on; this page is the breakdown and can come later.`, "later") + `
    <div class="g12"><div class="c4"><span class="kicker">Real dollars · Jev and the LLM · all of version 1</span>
      <div class="keyfig mt1">${cents(spent)} <small>of $${CEILING}</small></div>${track(spent / CEILING)}
      <p class="lede mt2">The running runs could still spend up to <b>${cents(caps)}</b> before their caps stop them. That leaves <b class="accent">${cents(CEILING - spent - caps)}</b> the app would let a new run claim.</p>
      <p class="small muted mt2">Snowflake and LangSmith are free on their current plans and are not counted here.</p>
    </div><div class="c8"><h1 class="display title" style="margin-bottom:1.5rem">Spending</h1>
      <div class="tablewrap"><table style="min-width:0"><thead><tr><th>Item</th><th class="num">Planned</th><th class="num">Spent</th><th style="width:38%">Against the plan</th></tr></thead><tbody>${plan.map(p => `<tr><td>${p[0]}</td><td class="num">${cents(p[1])}</td><td class="num">${cents(p[2])}</td><td>${track(p[2] / p[1], p[2] > p[1])}</td></tr>`).join("")}
        <tr><td><b>Total</b></td><td class="num">about $39</td><td class="num">${cents(spent)}</td><td class="small muted">about $11 of the ceiling is unassigned</td></tr></tbody></table></div>
      <div class="subhead">By what the call was for</div>
      ${rankedBars([{ name: "LLM turns", v: spent * 0.62 }, { name: "Screens", v: spent * 0.17 }, { name: "Position checks", v: spent * 0.08 }, { name: "Picks and sizes", v: spent * 0.09 }, { name: "Benchmark, test answers", v: spent * 0.04 }], cents)}
      <p class="meta mt1">from the stored record of every paid call: tokens, cost, latency, retries</p>
    </div></div>`;
}

/* ---------- the guide: what is proposed, and the questions ---------- */
function screenGuide() {
  const rows = [
    ["Runs", "runs", "Every run, grouped by kind, each with its status, its account value against holding the five assets, and its spending.", "Runs", 1],
    ["Run", "run/rise-on-1", "One page per run, live while it replays: the account value chart, open positions, notable moments, all the measurements, every trade, every decision, the track record, and the settings it ran under.", "Live run, Overview, Trades, Patterns, Calibration", 1],
    ["Trade", "trade/rise-on-1-t40", "One trade reviewed the way a trader reviews it: the price chart with entry, stop price, and close marked, the order with its trimming and costs, every position check, and the memory Jev read.", "Trade detail", 1],
    ["The exchange behind a decision", "decision/rise-on-1-t40", "Word for word: what Jev was asked at the screen, the LLM's whole exchange with memory, Jev's pick, and Jev's size.", "new", 1],
    ["Comparison", "comparison", "One verdict per market (memory helped, memory hurt, or can't tell), with both groups' averages and standard deviations, and the gap over time.", "Overview, Learning", 0],
    ["New run", "new-run", "Start a run: the estimated cost before the start, the spending cap, and the refusals.", "New run", 0],
    ["Datasets", "datasets", "All datasets, and the form to build a new one.", "Datasets, New dataset", 0],
    ["Dataset", "dataset", "The build's progress, the quality report, the asset key, and a price chart per asset.", "Dataset detail", 0],
    ["Playbook", "playbook", "The 61 candle patterns: name, lean, shape.", "Playbook", 0],
    ["Spending", "spending", "Real dollars paid to Jev and the LLM against the $50 ceiling, by item.", "new", 0],
  ];
  return `<div class="guide"><span class="kicker">Prototype · all data made up · thrown away once the questions below are answered</span>
    <h1 class="display title" style="max-width:none">The web app's screens: a rough outline to react to</h1>
    <p class="lead mt2">This page lists the screens proposed for version 1 and what each shows. Every screen is clickable and drawn in the editorial paper style, on made-up numbers, so you can judge what is there, what is missing, and how it reads. The purple boxes and the purple bar at the bottom are notes to you; they are not part of the design.</p>
    <div class="g12 mt3"><div class="c8">
      ${sechead("01", "The proposed screens", "10 screens replace the brief's 13")}
      <table><thead><tr><th>Screen</th><th>What it shows</th><th>In the brief as</th><th>When</th></tr></thead><tbody>${rows.map(r => `<tr><td style="white-space:nowrap"><a href="${r[1].startsWith("run/") ? runHref("rise-on-1") : href(r[1])}" style="font:600 1.1rem var(--display);text-decoration:underline">${r[0]} →</a></td><td class="small">${r[2]}</td><td class="small muted">${r[3]}</td><td>${r[4] ? `<span class="badge fill">first dashboard</span>` : `<span class="badge">later</span>`}</td></tr>`).join("")}</tbody></table>
      <p class="small muted mt1"><b>Folded in, no longer screens of their own:</b> Patterns (now the run's Track record tab), Calibration (now "Jev's confidence" among the run's measurements), Learning (now on Comparison). <b>Gone:</b> the coded candle-pattern strategy, the target price, futures and options, a trade "still open" at a run's end.</p>

      <div class="mt3">${sechead("02", "What is proposed for the ticket's five points")}</div>
      <ol class="list">
        <li><h3>1. What the editorial-ui skill fixes</h3><p class="small">It fixes the look: paper background, three fonts (a bold display face, a serif for reading, a monospace for every number), lines and whitespace in place of boxes, one accent colour used only to point. It names no framework. So the brief's fallback applies: <b>React with TypeScript</b>, built with Vite, styled with Tailwind (the skill's own examples are written in it), charts drawn with D3 as the editorial-viz skill asks. A gain or a loss is told by its sign (+$41, −$52), never by green and red: the style allows one accent only.</p></li>
        <li><h3>2. The screen list</h3><p class="small">The table above. The idea behind it: the app is the agent's trading journal. A day trader reviews the day, then each trade, then asks "why did I take this one?" The screens follow that order: run, trade, the exchange behind the decision.</p></li>
        <li><h3>3. The first screens to exist</h3><p class="small">The four marked "first dashboard": Runs, Run, Trade, and the exchange behind a decision, plus the spending total in the top bar. They are enough to judge a tuning run: is it trading often, how wild is the ride, why did it take this trade? Until the New run screen exists, runs are started from the command line.</p></li>
        <li><h3>4. The live run screen</h3><p class="small">It is the run page itself. While the run replays, the page asks the API for fresh numbers <b>every 5 seconds</b> and changes them in place: the step and the replayed date, the account value chart (which grows to the right), open positions, the day's change against the daily loss limit, what is held against the exposure limit, spending against the cap, the latest decisions, and the notable moments. A Stop button ends the run cleanly at the end of the step. Nothing slides or flashes.</p></li>
        <li><h3>5. Real names beside masked ones</h3><p class="small">The real name leads and the masked ID follows as a small grey tag: ${assetTag("ASSET_03")}. A price is shown real, with the rescaled price the agent saw beside it: ${priceTag("ASSET_03", 104.2)}. Dates are real, with the step number in the fine print. One exception: the exchange behind a decision shows the exact text that was sent, so it stays masked, with a key beside it.</p></li>
      </ol>
    </div><div class="c4"><div class="sticky">
      <div class="pnote" style="margin:0"><b class="t">Questions for you</b>
        <ul>
          <li><b>1. The run page layout.</b> Open <a href="${runHref("rise-on-1")}" style="text-decoration:underline">the run page</a> and switch between A, B, and C with the bar at the bottom. Which one, or which mix? <i>My pick: A's tabs, with C's day list added as a "Days" tab.</i></li>
          <li><b>2. The screen list.</b> Is anything missing, or is anything here not worth building? <i>My pick: the ten as listed.</i></li>
          <li><b>3. The first dashboard.</b> Are those four screens enough to judge a tuning run, with runs started from the command line at first? <i>My pick: yes.</i></li>
          <li><b>4. The clock.</b> Every time on screen is UTC, the agent's own clock, with "bar 3 of 26" telling where a stock is in its session. The other choice is New York time (your own time zone) for stocks. <i>My pick: UTC everywhere, so a "day" on screen is the same day the daily loss limit uses.</i></li>
          <li><b>5. The framework.</b> React with TypeScript, Vite, Tailwind, and D3. <i>My pick: yes; it is the brief's fallback and the most asked-for combination in job postings.</i></li>
        </ul>
        <p style="margin-top:.6rem"><b>Smaller things I assumed</b> (say so if any is wrong): the exchange behind a decision is a full page, not a side panel · a rising bar is hollow and a falling bar is filled · the accent is this red-orange · holding the five assets is a column on Runs, not a row · a finished run and a live run share one page.</p>
      </div>
    </div></div></div></div>`;
}
