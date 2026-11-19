/* PROTOTYPE, round 2. The run page as one long report with the chart front and centre, a chart you can hover
   and click, a side panel for "a moment" and for "the exchange behind a decision", and three ways to draw that exchange. */

let LOOK = "paper";    /* paper (editorial) | phosphor | board | tape */
let FLOW = "rail";     /* rail | lanes | strip: how the exchange is drawn in the side panel */
let WORD = "run";      /* the word tried in place of "run" */
let PANEL = null, PANEL_BACK = [], STRIP_AT = 0, CH = null;
const LOOKS = { paper: "Paper (editorial, as before)", phosphor: "Phosphor", board: "Big board", tape: "Tape and ticket" };
const FLOWS = { rail: "1 · rail", lanes: "2 · lanes", strip: "3 · strip" };
const WORDS = ["run", "backtest", "replay", "simulation"];

const openMin = t => t.d * 1440 + t.minutes;
const closeMin = t => (t.open ? Infinity : openMin(t) + t.bars * 15);
const exch = tid => `openPanel({kind:'exchange',tid:'${tid}'})`;
/* Big-board digits: one tile per character. */
const flap = s => (LOOK === "board" ? `<span class="flap">${String(s).split("").map(c => `<b class="${c === " " ? "gap" : ""}">${c === " " ? "" : c}</b>`).join("")}</span>` : s);

/* ---------- header ---------- */
function runHeader2(run) {
  const f = tradeFacts(run), behind = run.value - run.holding, live = run.status === "running";
  const kind = { measurement: "Measurement run", "build-up": "Build-up run", tuning: "Tuning run", practice: "Practice run" }[run.kind];
  const button = live ? `<button class="btn hot">Stop ■</button>` : run.status === "stopped" ? `<button class="btn">Raise the cap and restart</button>` : run.status === "failed" ? `<button class="btn">Restart from step ${stepAt(run, run.daysDone).toLocaleString("en-US")}</button>` : "";
  const tape = LOOK !== "board" ? "" : `<div class="tape" aria-hidden="true"><span>${[0, 1].map(() => Object.keys(ASSETS).map((id, i) => `${ASSETS[id].symbol} ${realPrice(id, ASSETS[id].base)} ${i % 2 ? "▼" : "▲"}<i>${i % 2 ? "−" : "+"}${(0.2 + i * 0.31).toFixed(2)}%</i>`).join("") + `ACCOUNT ${fmt$(run.value)} ▲<i>${sgn$(run.value - 10000)}</i>HOLDING ${fmt$(run.holding)}<i>&nbsp;</i>`).join("")}</span></div>`;
  return `${tape}<div class="g12 rhead">
    <div class="c9">
      <span class="kicker"><a href="${href("runs")}">← All runs</a> &nbsp;·&nbsp; ${kind} · ${run.label} · ${VARIANT_WORDS[run.variant]}</span>
      <h1 class="display title">${run.title}</h1>
      <p class="meta mt1">${statusBadge(run)} &nbsp; day ${Math.min(run.daysDone + (live ? 1 : 0), run.days)} of ${run.days} · replaying ${dayYear(run.start, Math.min(run.daysDone, run.days - 1))}${live ? ` <span id="live-clock">15:15</span> UTC` : ""} · step <span id="live-step">${(stepAt(run, run.daysDone) + (live ? 61 : 0)).toLocaleString("en-US")}</span>${live ? ` · <span id="live-ago">updated just now</span>` : ""}</p>
    </div>
    <div class="c3" style="align-self:end; text-align:right">${button}</div>
  </div>
  <dl class="statrow mt2 rule" style="padding-top:.9rem">
    <div><dt class="kicker">Account value ${live ? "now" : "at the end"}</dt><dd class="statbig">${flap(fmt$(run.value))} <small>${sgn$(run.value - 10000)}</small></dd><div class="meta mt1">started with $10,000</div></div>
    <div><dt class="kicker">Holding the five assets instead</dt><dd class="statbig">${flap(fmt$(run.holding))}</dd><div class="meta mt1">the agent is <b class="${behind < 0 ? "accent" : ""}">${fmt$(Math.abs(behind))} ${behind < 0 ? "behind" : "ahead"}</b></div></div>
    <div><dt class="kicker">Trades</dt><dd class="statbig">${flap(f.all.length)} <small>${(f.all.length / Math.max(1, Math.min(run.daysDone, 30))).toFixed(1)} a day</small></dd><div class="meta mt1">${f.won.length} made money · ${f.lost.length} lost · ${f.all.length - f.closed.length} open</div></div>
    <div><dt class="kicker">Spent on the models (real dollars)</dt><dd class="statbig">${flap(cents(run.spent))} <small>of ${cents(run.cap)} cap</small></dd>${track(run.spent / run.cap, run.spent >= run.cap)}<div class="meta">estimated ${cents(run.est)} for the whole run</div></div>
  </dl>`;
}

/* ---------- the chart: full width, hover for any moment, click to open it ---------- */
function bigChart(run) {
  const s = seriesOf(run), p = partnerOf(run), W = 1400, H = 480, m = { t: 18, r: 176, b: 48, l: 72 }, n = run.days * 4 + 1;
  const lines = [{ key: "agent", name: "this run " + fmt$(run.value), vals: s.agent, kind: "subject" }, { key: "holding", name: "holding " + fmt$(run.holding), vals: s.holding, kind: "dashed" }];
  if (p) lines.push({ key: "partner", name: (p.variant === "memory_on" ? "with memory " : "without ") + fmt$(p.value), vals: seriesOf(p).agent, kind: "context" });
  const { y, ticks } = scaleY(lines.flatMap(l => l.vals).concat([10000]), H, m.t, m.b, 6);
  const x = i => m.l + (W - m.l - m.r) * i / (n - 1), stepped = LOOK === "phosphor" || LOOK === "board";
  const path = vals => vals.map((v, i) => (i === 0 ? `M${x(0).toFixed(1)} ${y(v).toFixed(1)}` : stepped ? `H${x(i).toFixed(1)}V${y(v).toFixed(1)}` : `L${x(i).toFixed(1)} ${y(v).toFixed(1)}`)).join("");
  let g = "";
  ticks.forEach(t => { g += `<line x1="${m.l}" x2="${W - m.r}" y1="${y(t)}" y2="${y(t)}" stroke="var(--grid)"/><text class="tick" x="${m.l - 9}" y="${y(t) + 4}" text-anchor="end">${fmt$(t)}</text>`; });
  g += `<line x1="${m.l}" x2="${W - m.r}" y1="${H - m.b}" y2="${H - m.b}" stroke="var(--ink)"/><line x1="${m.l}" x2="${m.l}" y1="${m.t}" y2="${H - m.b}" stroke="var(--ink)"/>`;
  const per = run.days > 60 ? 60 : run.days > 10 ? 5 : 1;
  for (let d = 0; d <= run.days; d += per) g += `<line x1="${x(d * 4)}" x2="${x(d * 4)}" y1="${H - m.b}" y2="${H - m.b + 5}" stroke="var(--ink)"/><text class="tick" x="${x(d * 4)}" y="${H - m.b + 20}" text-anchor="middle">${dayDate(run.start, d)}</text>`;
  g += `<line x1="${m.l}" x2="${W - m.r}" y1="${y(10000)}" y2="${y(10000)}" stroke="var(--ink)" stroke-dasharray="4 3"/>`;
  const order = { dashed: 0, context: 1, subject: 2 };
  [...lines].sort((a, b) => order[a.kind] - order[b.kind]).forEach(l => {
    const style = l.kind === "subject" ? (LOOK === "tape" ? `stroke="var(--accent)" stroke-width="4" stroke-dasharray="0.1 7" stroke-linecap="round"` : `stroke="var(--accent)" stroke-width="2.75"`) : l.kind === "dashed" ? `stroke="var(--ink)" stroke-width="1.25" stroke-dasharray="2 4"` : `stroke="var(--dot)" stroke-width="1.25"`;
    g += `<path d="${path(l.vals)}" fill="none" ${style}/>`;
  });
  /* every trade is a small tick along the bottom, at the moment it was opened */
  tradesOf(run).forEach(t => { const tx = x(openMin(t) / 360); if (tx <= W - m.r) g += `<line class="rug ${t.open ? "open" : ""}" x1="${tx.toFixed(1)}" x2="${tx.toFixed(1)}" y1="${H - m.b - 11}" y2="${H - m.b - 1}"/>`; });
  const ends = lines.map(l => ({ l, x: x(l.vals.length - 1), y: y(l.vals[l.vals.length - 1]) }));
  ends.push({ l: { name: "start $10,000", kind: "ref" }, x: W - m.r, y: y(10000) });
  ends.sort((a, b) => a.y - b.y); for (let i = 1; i < ends.length; i++) if (ends[i].y < ends[i - 1].y + 15) ends[i].y = ends[i - 1].y + 15;
  ends.forEach(e => {
    if (e.l.kind === "subject") g += `<circle cx="${e.x}" cy="${y(e.l.vals[e.l.vals.length - 1])}" r="5" fill="var(--accent)" stroke="var(--paper)" stroke-width="2"/>`;
    g += `<text class="lbl ${e.l.kind === "subject" ? "subject" : ""}" x="${e.x + 10}" y="${e.y + 4}">${e.l.name}</text>`;
  });
  g += `<g id="hov" visibility="hidden"><line id="hov-l" y1="${m.t}" y2="${H - m.b}" stroke="var(--ink)"/><circle id="hov-h" r="4" fill="var(--paper)" stroke="var(--ink)" stroke-width="1.5"/><circle id="hov-a" r="6" fill="var(--accent)" stroke="var(--paper)" stroke-width="2"/></g>`;
  g += `<rect id="hov-r" x="${m.l}" y="${m.t}" width="${W - m.l - m.r}" height="${H - m.t - m.b}" fill="transparent"/>`;
  CH = { run, x, y, n, W, m, len: s.agent.length };
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Line chart of account value over the run, against holding the five assets">${g}</svg>`;
}
function momentFacts(run, i) {
  const s = seriesOf(run), d = Math.min(Math.floor(i / 4), run.days - 1), T = i * 360, all = tradesOf(run);
  return {
    i, d, T, label: `${dayYear(run.start, Math.floor(i / 4))}, ${hhmm((i % 4) * 360)} UTC`, value: s.agent[i], holding: s.holding[i], sinceMidnight: s.agent[i] - s.agent[Math.floor(i / 4) * 4],
    held: all.filter(t => openMin(t) <= T && T < closeMin(t)),
    near: all.filter(t => Math.abs(openMin(t) - T) <= 180 || Math.abs(closeMin(t) - T) <= 180),
  };
}
function wireChart() {
  const svg = document.querySelector("#bigplot svg"), tip = document.getElementById("tip"); if (!svg || !CH) return;
  const indexAt = e => { const r = svg.getBoundingClientRect(), vx = (e.clientX - r.left) * CH.W / r.width; return Math.max(0, Math.min(CH.len - 1, Math.round((vx - CH.m.l) / (CH.W - CH.m.l - CH.m.r) * (CH.n - 1)))); };
  const rect = svg.querySelector("#hov-r"), hov = svg.querySelector("#hov");
  rect.addEventListener("pointermove", e => {
    const i = indexAt(e), f = momentFacts(CH.run, i), gap = f.value - f.holding;
    hov.setAttribute("visibility", "visible");
    svg.querySelector("#hov-l").setAttribute("x1", CH.x(i)); svg.querySelector("#hov-l").setAttribute("x2", CH.x(i));
    svg.querySelector("#hov-a").setAttribute("cx", CH.x(i)); svg.querySelector("#hov-a").setAttribute("cy", CH.y(f.value));
    svg.querySelector("#hov-h").setAttribute("cx", CH.x(i)); svg.querySelector("#hov-h").setAttribute("cy", CH.y(f.holding));
    tip.innerHTML = `<div class="tt">${f.label}</div><div class="kicker">day ${f.d + 1} of ${CH.run.days}</div>
      <dl><dt class="s">Account value</dt><dd>${fmt$(f.value)}</dd><dt>Holding the five assets</dt><dd>${fmt$(f.holding)}</dd><dt>${gap < 0 ? "Behind" : "Ahead of"} holding by</dt><dd>${fmt$(Math.abs(gap))}</dd>
      <dt>Since midnight</dt><dd>${sgn$(f.sinceMidnight)}</dd><dt>Since the start</dt><dd>${sgn$(f.value - 10000)}</dd><dt>Positions open then</dt><dd>${f.held.length}</dd><dt>Trades opened or closed nearby</dt><dd>${f.near.length}</dd></dl>
      <div class="go">Click to open this moment</div>`;
    tip.style.display = "block";
    const w = tip.offsetWidth, h = tip.offsetHeight;
    tip.style.left = (e.clientX + 18 + w > innerWidth ? e.clientX - w - 18 : e.clientX + 18) + "px";
    tip.style.top = Math.max(8, Math.min(innerHeight - h - 8, e.clientY + 16)) + "px";
    applyWord(tip);
  });
  rect.addEventListener("pointerleave", () => { hov.setAttribute("visibility", "hidden"); tip.style.display = "none"; });
  rect.addEventListener("click", e => { tip.style.display = "none"; openPanel({ kind: "moment", run: CH.run.id, i: indexAt(e) }); });
}

/* ---------- the "now" pieces, slimmed down ---------- */
function metersBlock(run) {
  const ride = rideOf(run), today = ride.days[ride.days.length - 1], open = tradesOf(run).filter(t => t.open), exposure = open.reduce((s, t) => s + t.size, 0), loan = Math.max(0, exposure - run.value);
  return `<div class="meters">
    <div><span class="kicker">Today, since midnight UTC</span><div class="big mt1">${sgn$(today.change * 0.3)} <small>of ${sgn$(-0.05 * run.value)} allowed</small></div>${track(0.12)}<div class="meta">daily loss limit: past it, code blocks new trades for the day</div></div>
    <div><span class="kicker">Held in positions</span><div class="big mt1">${fmt$(exposure)} <small>of ${fmt$(2 * run.value)} allowed</small></div>${track(exposure / (2 * run.value))}<div class="meta">exposure limit: 2 times account value · loan now ${loan ? fmt$(loan) : "none"}</div></div>
    <div><span class="kicker">Spent on the models</span><div class="big mt1">${cents(run.spent)} <small>of ${cents(run.cap)} cap</small></div>${track(run.spent / run.cap)}<div class="meta">spending cap: the run stops itself there</div></div>
  </div>`;
}
function nowSection(run) {
  const f = tradeFacts(run), open = f.all.filter(t => t.open);
  const positions = `<div class="subhead" style="margin-top:0">Open positions <span class="kicker">what the agent holds right now · click one for the exchange that opened it</span></div><div class="tablewrap"><table><thead><tr><th>Asset</th><th>Direction</th><th class="num">Size</th><th>Opened</th><th class="num">Now</th><th class="num">Stop price</th></tr></thead><tbody>${open.map(t => {
    const stop = t.entry * (1 + (t.dir === "long" ? -1 : 1) * 0.006 * t.stopMoves);
    return `<tr class="click" onclick="${exch(t.id)}"><td>${assetTag(t.asset)}</td><td>${t.dir}</td><td class="num">${fmt$(t.size)}${t.trimmed ? ` <span class="badge out" title="Jev chose ${fmt$(t.chosen)}; code made it smaller">trimmed</span>` : ""}</td><td class="num" style="text-align:left">${when(run, t)} · ${t.bars} bars ago</td><td class="num">${sgn$(t.pl)}</td><td class="num">${priceTag(t.asset, stop)}<div class="meta">would lose ${fmt$(t.size * 0.006 * t.stopMoves)}</div></td></tr>`;
  }).join("")}</tbody></table></div>`;
  const latest = f.all.slice(-6).reverse().map(t => `<li class="click" style="display:flex;gap:.75rem;align-items:baseline;flex-wrap:wrap;cursor:pointer" onclick="${exch(t.id)}"><span class="meta" style="width:6.2rem">${when(run, t)}</span>${assetTag(t.asset)} <span>${t.open ? "opened a " + t.dir + " of " + fmt$(t.size) : "closed its " + t.dir + ", " + sgn$(t.pl) + ": " + REASONS[t.reason]}</span></li>`).join("");
  return positions + `<div class="subhead">Latest decisions <span class="kicker">newest first · click one for its exchange</span></div><ol class="list">${latest}</ol>`;
}

/* ---------- the page ---------- */
function screenRunV2(id, q) {
  const run = runById(id) || RUNS[0], live = run.status === "running", behind = run.value - run.holding;
  const secs = (live ? [["Now", () => nowSection(run)]] : []).concat([["Measurements", () => secMeasurements(run)], ["Trades", () => secTrades(run, q)], ["Decisions", () => secDecisions(run)], ["Track record", () => secTrackRecord(run)], ["Settings", () => secSettings(run)]]);
  const p = partnerOf(run);
  const legend = `<span><i class="sw"></i>this run</span>${p ? `<span><i class="sw ctx"></i>its partner, ${VARIANT_WORDS[p.variant]}</span>` : ""}<span><i class="sw ref" style="border-top:1.25px dotted var(--ink)"></i>holding the five assets</span><span>| a trade opened</span>`;
  const rail = `<div class="sticky"><span class="kicker">On this page</span><ol class="list mt1 onpage">${secs.map((s, i) => `<li style="padding:.4rem 0"><a href="javascript:void 0" onclick="document.getElementById('sec${i}').scrollIntoView()"><span class="meta accent idx" data-f="F${i + 1}">0${i + 1}</span> &nbsp;<span style="font:600 1.05rem var(--display)">${s[0]}</span></a></li>`).join("")}</ol>
    <div class="mt2"><span class="kicker">Notable moments</span></div><div class="mt1">${eventList(run)}</div></div>`;
  return note("the run page, round 2", `Layout B, changed as you asked: the chart now runs the full width at the top, and the "now" briefing is three thin meters under it. <b>Hover the chart</b> for any moment; <b>click it</b> to open that moment in a side panel. <b>Click any trade, position, or decision</b> to open the exchange behind it in the same side panel.
    <ul><li><b>Look</b> in the bar at the bottom (or the ← → keys) switches this page between the paper style and three terminal styles.</li><li><b>Word</b> swaps "run" for another word everywhere on the page, to see how each reads.</li></ul>`, "first") + runHeader2(run) + `
    <section class="chartblock">
      <p class="chartlede">After <b>${run.daysDone} ${run.daysDone === 1 ? "day" : "days"}</b> the account holds <b>${fmt$(run.value)}</b>: <b class="accent">${fmt$(Math.abs(behind))} ${behind < 0 ? "less" : "more"}</b> than holding the five assets and never trading. <span class="hint">hover the chart for any moment · click to open it</span></p>
      ${figure(1, "Account value, against holding the five assets", legend, `<div id="bigplot">${bigChart(run)}</div>`, `${run.daysDone} of ${run.days} days · 4 points a day · times in UTC · prototype: made-up numbers`)}
      ${live ? metersBlock(run) : ""}
    </section>
    <div class="g12 mt3"><div class="c3">${rail}</div><div class="c9"><div class="stack">${secs.map((s, i) => `<section id="sec${i}">${sechead("0" + (i + 1), s[0])}${s[1]()}</section>`).join("")}</div></div></div>`;
}

/* ---------- side panel ---------- */
function openPanel(p) { if (PANEL) PANEL_BACK.push(PANEL); PANEL = p; STRIP_AT = 0; drawPanel(); drawBar(); }
function closePanel() { PANEL = null; PANEL_BACK = []; drawPanel(); drawBar(); }
function backPanel() { PANEL = PANEL_BACK.pop() || null; drawPanel(); drawBar(); }
function drawPanel() {
  const root = document.getElementById("panelroot");
  if (!PANEL) { root.innerHTML = ""; return; }
  const body = PANEL.kind === "moment" ? momentPanel(PANEL) : exchangePanel(PANEL);
  root.innerHTML = `<div id="scrim" onclick="closePanel()"></div><aside id="panel" role="dialog" aria-label="${body.label}">
    <div class="phead">${PANEL_BACK.length ? `<a class="kicker" href="javascript:void 0" onclick="backPanel()">← Back</a>` : ""}<span class="kicker">${body.label}</span><button class="btn" onclick="closePanel()">Esc ×</button></div>${body.html}</aside>`;
  applyWord(root);
}
function momentPanel(p) {
  const run = runById(p.run), f = momentFacts(run, p.i), gap = f.value - f.holding;
  const line = t => { const opened = Math.abs(openMin(t) - f.T) <= 180; return `<li class="click" style="display:flex;gap:.75rem;align-items:baseline;flex-wrap:wrap;cursor:pointer" onclick="${exch(t.id)}"><span class="meta" style="width:6.2rem">${opened ? when(run, t) : dayDate(run.start, Math.floor(closeMin(t) / 1440)) + " " + hhmm(closeMin(t) % 1440)}</span>${assetTag(t.asset)} <span>${opened ? "opened a " + t.dir + " of " + fmt$(t.size) : "closed its " + t.dir + ", " + sgn$(t.pl) + ": " + REASONS[t.reason]}</span></li>`; };
  return { label: "A moment in the run", html: `
    <h2 class="ptitle">${f.label}</h2>
    <p class="meta">day ${f.d + 1} of ${run.days} · step ${(stepAt(run, 0) + Math.round(f.T / 15)).toLocaleString("en-US")} · ${run.title}</p>
    <dl class="statrow mt2 rule" style="padding-top:.8rem"><div><dt class="kicker">Account value</dt><dd class="statbig" style="font-size:1.7rem">${fmt$(f.value)}</dd></div><div><dt class="kicker">Holding the five assets</dt><dd class="statbig" style="font-size:1.7rem">${fmt$(f.holding)}</dd><div class="meta">${fmt$(Math.abs(gap))} ${gap < 0 ? "behind" : "ahead"}</div></div><div><dt class="kicker">Since midnight</dt><dd class="statbig" style="font-size:1.7rem">${sgn$(f.sinceMidnight)}</dd></div><div><dt class="kicker">Since the start</dt><dd class="statbig" style="font-size:1.7rem">${sgn$(f.value - 10000)}</dd></div></dl>
    <div class="subhead">Positions open at that moment <span class="kicker">click one for the exchange that opened it</span></div>
    ${f.held.length ? `<div class="tablewrap"><table style="min-width:0"><thead><tr><th>Asset</th><th>Direction</th><th class="num">Size</th><th>Opened</th><th class="num">Ended with</th></tr></thead><tbody>${f.held.map(t => `<tr class="click" onclick="${exch(t.id)}"><td>${assetTag(t.asset)}</td><td>${t.dir}</td><td class="num">${fmt$(t.size)}</td><td class="num" style="text-align:left">${when(run, t)}</td><td class="num">${t.open ? "still open" : sgn$(t.pl)}</td></tr>`).join("")}</tbody></table></div>` : `<div class="waiting" style="padding:1.2rem 0"><span class="kicker">None</span><p style="font-size:1.2rem">The account was all in cash at that moment.</p></div>`}
    <div class="subhead">Opened or closed within 3 hours of it</div>
    ${f.near.length ? `<ol class="list">${f.near.map(line).join("")}</ol>` : `<div class="waiting" style="padding:1.2rem 0"><span class="kicker">Nothing</span><p style="font-size:1.2rem">No trade was opened or closed around then.</p></div>`}
    <p class="meta mt2">The real screen would also list every check and full evaluation at that exact step.</p>` };
}

/* The exchange as an ordered list of stops, each with the messages that passed. who: jev | code | llm | mem. */
function exchangeStops(run, t) {
  const a = ASSETS[t.asset], mem = run.variant === "memory_on", p = t.entry.toFixed(2), stopWord = ["tight", "medium", "wide"][t.stopMoves - 1];
  const situation = `${a.cls === "stock" ? "Stock, " + t.part + " (bar " + t.bar + " of 26)" : "Crypto, " + t.part}. Patterns in the last 4 bars: ${t.pattern} (this bar), hammer (2 bars ago). Latest hourly bar: none. Latest daily bar: doji. Last 8 bars: five up, three down; this bar is a large up bar closing near its high. Short-term trend up (1.5 typical moves above the 20-bar average). Long-term trend up (2.1 above the 20-day average). Volume high (1.8 times normal). …`;
  const stops = [{ name: "Screen", ask: "Is a closer look worth it?", out: "0.71", say: "Above the cut-off of 0.5, so a full evaluation runs. Under it, nothing more would happen at this step.", msgs: [
    { from: "code", to: "jev", t: "The background and the screen question", meta: "about 1,150 tokens", text: `# The task\nThis is a trading account in a replay of market history. …\n\n# The account now\nAccount value: $10,140.\nCash: $7,122. Loan: none.\n\n# The asset: ${t.asset} (${a.cls})\nLast price: $${p}. Typical move in one bar: $0.63.\n${situation}\n\nQuestion: Is a full evaluation of this asset worth running now? (a number from 0 to 1)` },
    { from: "jev", to: "code", t: "Its answer", out: "0.71", meta: "0.17 s", text: "0.71" }] }];
  if (mem) stops.push({ name: "Memory", ask: "Which past episodes should Jev read?", out: "3 episodes", say: "Code searched first; the LLM looked twice more (2 of its 6 lookups) and selected three.", msgs: [
    { from: "code", to: "mem", t: "First search: episodes like this moment", text: "search_episodes(like the current snapshot)" },
    { from: "mem", to: "code", t: "The 10 most similar", out: "10", text: `E-48213 · 41 days ago · same asset · ${t.part} · long-term trend up · volume high · ${t.pattern}, hammer · long · closed by choice after 9 bars, +$64 (+1.1%)\nE-49190 · 112 days ago · another stock · … · closed at its stop price after 3 bars, -$48 (-0.9%)\n… 8 more lines` },
    { from: "code", to: "llm", t: "The situation and the 10 one-line summaries", meta: "prompt version p-3fa9c1", text: `[standing instructions: 412 words, stored once for this prompt version]\n\nThe situation now:\n${situation}\n\nThe 10 most similar past episodes:\n… 10 lines` },
    { from: "llm", to: "mem", t: "Lookup 1 of 6: a narrower search", text: `tool call: search_episodes(direction="${t.dir}", part_of_day="${t.part}")` },
    { from: "mem", to: "llm", t: "4 more episodes", out: "4", text: "E-50167 · 203 days ago · same asset · … · no trade · price went +0.4% after 4 bars\n… 3 more lines" },
    { from: "llm", to: "mem", t: "Lookup 2 of 6: reads two in full", text: `tool call: read_episodes(ids=["E-48213", "E-50167"])` },
    { from: "mem", to: "llm", t: "The two episodes in full", text: "[the two episodes in full: 31 lines]" },
    { from: "llm", to: "code", t: "Its answer: the selected episodes and a note", out: "3 episodes", meta: "4.1 s · $0.0021", text: `tool call: select_episodes(ids=["E-48213", "E-49190", "E-50167"], note="Same pattern in the ${t.part} with high volume; one winner, one stopped out, one no-trade.")` }] });
  stops.push({ name: "Pick", ask: "Which trade, if any?", out: `${t.dir}, ${stopWord} stop price`, say: `Probabilities are added by direction first: ${t.dir} 0.67, the other direction 0.09, no trade 0.24.`, msgs: [
    { from: "code", to: "jev", t: `The background again${mem ? ", now with the track record and the 3 episodes" : ""}, and the candidate trades`, meta: "about 3,400 tokens", text: `[the background, ${mem ? "with the track record lines and the 3 selected episodes" : "with the note that no memory is read"}]\n\nQuestion: Which trade, if any?\n- long, tight stop price ($${(t.entry * 0.994).toFixed(2)})\n- long, medium stop price ($${(t.entry * 0.988).toFixed(2)})\n- long, wide stop price ($${(t.entry * 0.982).toFixed(2)})\n- short, tight stop price …\n- short, medium stop price …\n- short, wide stop price …\n- no trade` },
    { from: "jev", to: "code", t: "Its answer, averaged over 5 shuffled copies", out: t.dir, text: `${t.dir}, tight 0.14 · ${t.dir}, medium 0.31 · ${t.dir}, wide 0.22 · other direction 0.09 · no trade 0.24\npick: ${t.dir}, ${stopWord} stop price` }] });
  stops.push({ name: "Size", ask: "How much money?", out: fmt$(t.chosen), say: "The average of the five sizes, weighted by the probability Jev gave each.", msgs: [
    { from: "code", to: "jev", t: "The five sizes, each with its loss at the stop price", text: `Question: How much to put into this trade?\n- $2,028 (20% of account value): loses $${(2028 * 0.006 * t.stopMoves).toFixed(0)} at the stop price\n- $4,056 (40%) …\n- $8,112 (80%) …\n- $12,168 (120%) …\n- $20,280 (200%) …` },
    { from: "jev", to: "code", t: "Its answer", out: fmt$(t.chosen), text: `20% … · 40% … · 80% … · 120% … · 200% …\nweighted average: ${fmt$(t.chosen)}` }] });
  stops.push({ name: "Limits", ask: "Does the trade fit the risk limits?", out: t.trimmed ? fmt$(t.size) : "fits", say: t.trimmed ? `Code trimmed ${fmt$(t.chosen)} to ${fmt$(t.size)}: the ${t.limit} would otherwise have been broken.` : `${fmt$(t.chosen)} was inside every risk limit, so nothing was trimmed.`, msgs: [
    { from: "code", to: "code", t: t.trimmed ? "Code trims the size" : "Code checks the limits", out: t.trimmed ? fmt$(t.size) : "fits", text: t.trimmed ? `chosen ${fmt$(t.chosen)} → opened ${fmt$(t.size)} (${t.limit})` : "trade risk limit: fits · position limit: fits · exposure limit: fits" }] });
  stops.push({ name: "Order", ask: "", out: realPrice(t.asset, t.entry * 1.0005), end: true, say: `Carried out at the next bar's open. ${t.open ? "The position is still open." : "It was held " + held(t) + " and ended " + sgn$(t.pl) + ": " + REASONS[t.reason] + "."}`, msgs: [
    { from: "code", to: "code", t: "The order is carried out", out: realPrice(t.asset, t.entry * 1.0005), text: `${t.dir === "long" ? "buy" : "sell short"} ${fmt$(t.size)} of ${t.asset} at the next bar's open, $${(t.entry * 1.0005).toFixed(2)} after slippage` }] });
  return stops;
}
const WHO = { jev: "Jev", code: "Code", llm: "The LLM", mem: "Memory" }, LANE = ["jev", "code", "llm", "mem"];
const whoTag = m => (m.from === m.to ? `<span class="who">code</span>` : `<span class="who ${m.from !== "code" ? "reply" : ""}">${WHO[m.from]} → ${WHO[m.to]}</span>`);
function flowRail(stops) {
  return `<div class="rail">${stops.map((s, i) => `<div class="stop ${s.end ? "end" : ""}"><span class="dot">${i + 1}</span><h3>${s.name}${s.ask ? ` <span class="msay">${s.ask}</span>` : ""}<span class="out">${s.out}</span></h3><p class="msay">${s.say}</p>
    ${s.msgs.map(m => `<details class="m"><summary>${whoTag(m)}<span class="t">${m.t}</span>${m.meta ? `<span class="meta">${m.meta}</span>` : ""}</summary><pre class="mtext">${esc(m.text)}</pre></details>`).join("")}</div>`).join("")}</div>
    <p class="meta">one straight line, top to bottom · each + opens the exact text that was sent, read from storage</p>`;
}
function flowLanes(stops) {
  const rows = stops.flatMap(s => s.msgs.map((m, k) => {
    const a = LANE.indexOf(m.from), b = LANE.indexOf(m.to), stg = k === 0 ? `<span class="stg">${s.name}</span>` : "";
    if (a === b) return `<details class="lm"><summary>${stg}<span class="self" style="left:${a * 25 + 3}%;width:19%">${m.t} <b>${m.out || ""}</b></span></summary><pre class="mtext">${esc(m.text)}</pre></details>`;
    const lo = Math.min(a, b), left = lo * 25 + 12.5, width = Math.abs(a - b) * 25;
    return `<details class="lm"><summary>${stg}<span class="lab" style="left:${left}%;width:${width}%">${m.t}${m.out ? ` <b>${m.out}</b>` : ""}</span><span class="arr ${b > a ? "r" : "l"} ${m.from !== "code" && m.to !== "mem" ? "back" : ""}" style="left:${left}%;width:${width}%"></span></summary><pre class="mtext">${esc(m.text)}</pre></details>`;
  }));
  return `<div class="lanes"><div class="lanehead"><div>Jev<small>decides</small></div><div>Code<small>asks, enforces</small></div><div>The LLM<small>selects episodes</small></div><div>Memory<small>past decisions</small></div></div>
    <div class="lanebody">${[12.5, 37.5, 62.5, 87.5].map(l => `<span class="life" style="left:${l}%"></span>`).join("")}${rows.join("")}</div></div>
    <p class="meta">time runs down the page · a solid arrow is a question or a request, a dashed arrow is the answer coming back · click a row for the exact text</p>`;
}
function flowStrip(stops) {
  const s = stops[Math.min(STRIP_AT, stops.length - 1)];
  return `<div class="strip">${stops.map((x, i) => `<button class="sbox ${i === STRIP_AT ? "on" : ""}" onclick="STRIP_AT=${i};drawPanel()"><span class="k">${i + 1} · ${x.name}</span><span class="o">${x.out}</span></button>`).join("")}</div>
    <div class="sdetail"><span class="kicker">${s.name}${s.ask ? " · " + s.ask : ""}</span><p class="msay" style="margin:.3rem 0 .6rem">${s.say}</p>
    ${s.msgs.map(m => `<div class="one">${whoTag(m)} &nbsp;${m.t}${m.meta ? ` <span class="meta">${m.meta}</span>` : ""}<pre class="mtext" style="margin-top:.4rem">${esc(m.text)}</pre></div>`).join("")}</div>
    <p class="meta">the whole chain on one line · click a box to read what passed at that stage</p>`;
}
function exchangePanel(p) {
  const { run, trade: t } = findTrade(p.tid), a = ASSETS[t.asset], stops = exchangeStops(run, t);
  return { label: "The exchange behind a decision", html: `
    <h2 class="ptitle">Why it opened a ${t.dir} in ${a.name}</h2>
    <p class="meta">trade ${t.n} · ${when(run, t)} UTC · ${fmt$(t.size)} · ${t.open ? "still open, " + sgn$(t.pl) + " so far" : sgn$(t.pl) + ", " + REASONS[t.reason]} · <a href="${href("trade/" + t.id)}" onclick="closePanel()" style="text-decoration:underline">open the trade's own page</a></p>
    <div class="pkey"><span class="chip">${t.asset}</span> is <b>${a.name}</b> (${a.symbol}). The boxed text is exactly what was sent, so it uses the masked ID and rescaled prices: <span class="mono">${t.entry.toFixed(2)}</span> there is <b>${realPrice(t.asset, t.entry)}</b>.</div>
    ${FLOW === "lanes" ? flowLanes(stops) : FLOW === "strip" ? flowStrip(stops) : flowRail(stops)}` };
}

/* ---------- trying another word for "run" ---------- */
function applyWord(root) {
  if (WORD === "run" || !root) return;
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT), nodes = []; let nd;
  while ((nd = walker.nextNode())) nodes.push(nd);
  const cap = WORD[0].toUpperCase() + WORD.slice(1);
  nodes.forEach(x => { if (x.parentElement.closest("pre, .pnote, #bar, .guide")) return; x.nodeValue = x.nodeValue.replace(/(?<!evaluation )\b(R|r)un(s?)\b/g, (all, r, s) => (r === "R" ? cap : WORD) + s); });
}
