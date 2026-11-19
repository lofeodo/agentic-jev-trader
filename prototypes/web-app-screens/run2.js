/* PROTOTYPE, round 2. The run page as one long report with the chart front and centre, a chart you can hover
   and click, a side panel for "a moment" and for "the exchange behind a decision", and three ways to draw that exchange. */

let LOOK = "plasma";   /* which round 4 look the app wears */
let FLOW = "strip";    /* the developer picked the strip; rail and lanes stay in the code as the record of round 2 */
let WORD = 1;          /* settled in round 3: a run is a "trading sim" */
let PANEL = null, PANEL_BACK = [], STRIP_AT = 0, CH = null;
/* Round 4: five looks, each drawn from one of the developer's reference pictures. */
const LOOKS = { plasma: "1 · Plasma", desk: "2 · Dealing desk", page: "3 · Page", work: "4 · Workstation", wire: "5 · Wireframe" };
const CAPS_DEFAULT = { plasma: 1, desk: 0, page: 1, work: 0, wire: 1 };
const TUBES = { "": "as pictured", orange: "orange", amber: "amber", green: "green", white: "white" };
let CAPS = null, TUBE = "", CURVE = "";   /* null or "": the look's own default */
const CURVES = { "": "as the look draws it", smooth: "smooth", line: "straight", step: "steps" };
/* How each look draws the big chart. */
const CHART = {
  plasma: { curve: "smooth", grid: "", ticks: "in", frame: 1, minor: 1 },
  desk: { curve: "line", grid: "h", ticks: "", frame: 1 },
  page: { curve: "step", grid: "dots", ticks: "out", frame: 1 },
  work: { curve: "line", grid: "", ticks: "out", frame: 0, markers: 1 },
  wire: { curve: "line", grid: "full", ticks: "out", frame: 1, hatch: 1 },
};
const FLOWS = { rail: "1 · rail", lanes: "2 · lanes", strip: "3 · strip" };
/* full: the name in titles ("All trading sims"). short: the name inside a sentence ("the sim ended"). */
const WORDS = [{ full: "run", short: "run" }, { full: "trading sim", short: "sim" }, { full: "market replay", short: "replay" }, { full: "trading trial", short: "trial" }];
const SCORE_NAME = "Scorecard";        /* tried in place of "Track record" */
const TRAIL_NAME = "Decision trail";   /* tried as the side panel's header */

const openMin = t => t.d * 1440 + t.minutes;
const closeMin = t => (t.open ? Infinity : openMin(t) + t.bars * 15);
const exch = tid => `openPanel({kind:'exchange',tid:'${tid}'})`;
/* Big-board digits: one tile per character. */
const flap = s => (LOOK === "board" ? `<span class="flap">${String(s).split("").map(c => `<b class="${c === " " ? "gap" : ""}">${c === " " ? "" : c}</b>`).join("")}</span>` : s);

/* ---------- header ---------- */
/* One set of markup; each look's CSS arranges it its own way (centred title, title bar, boxed cells, ...). */
function dayRuler(run, day) {
  let marks = "";
  for (let d = 0; d <= run.days; d += run.days > 60 ? 60 : 5) marks += `<span style="left:${(d / run.days * 100).toFixed(2)}%">${d}</span>`;
  return `<div class="ruler" aria-hidden="true" style="--days:${run.days}"><div class="scale">${marks}</div><i style="left:${((day - 0.5) / run.days * 100).toFixed(2)}%"></i></div>`;
}
function runHeader2(run) {
  const f = tradeFacts(run), behind = run.value - run.holding, live = run.status === "running";
  const kind = { measurement: "Measurement run", "build-up": "Build-up run", tuning: "Tuning run", practice: "Practice run" }[run.kind];
  const button = live ? `<button class="btn hot">Stop ■</button>` : run.status === "stopped" ? `<button class="btn">Raise the cap and restart</button>` : run.status === "failed" ? `<button class="btn">Restart from step ${stepAt(run, run.daysDone).toLocaleString("en-US")}</button>` : "";
  const day = Math.min(run.daysDone + (live ? 1 : 0), run.days);
  const status = live ? `<span class="sq"></span>running` : run.status === "finished" ? "finished" : `${run.status}: ${run.why}`;
  const pf = (label, value, after, cls) => `<span class="pf ${cls || ""}"><i>${label}</i><b>${value}</b>${after ? `<em>${after}</em>` : ""}</span>`;
  return `<div class="win r4head">
    <a class="r4crumb kicker" href="${href("runs")}">← All runs</a>
    <h1 class="r4title">${run.title}</h1>
    <p class="r4sub">${kind} · ${run.label} · ${VARIANT_WORDS[run.variant]}</p>
    <div class="r4params">${pf("Status", status, "", live || run.status === "finished" ? "" : "bad")}${pf("Day", day, "of " + run.days)}${pf("Replaying", dayYear(run.start, Math.min(run.daysDone, run.days - 1)) + (live ? ` <span id="live-clock">15:15</span>` : ""), "UTC")}${pf("Step", `<span id="live-step">${(stepAt(run, run.daysDone) + (live ? 61 : 0)).toLocaleString("en-US")}</span>`)}${live ? `<span class="pf note" id="live-ago">updated just now</span>` : ""}${button}</div>
    ${dayRuler(run, day)}
    <dl class="statrow">
      <div><dt class="kicker">Account value ${live ? "now" : "at the end"}</dt><dd class="statbig">${fmt$(run.value)} <small>${sgn$(run.value - 10000)}</small></dd><div class="meta mt1">started with $10,000</div></div>
      <div><dt class="kicker">Holding the five assets instead</dt><dd class="statbig">${fmt$(run.holding)}</dd><div class="meta mt1">the agent is <b class="${behind < 0 ? "accent" : ""}">${fmt$(Math.abs(behind))} ${behind < 0 ? "behind" : "ahead"}</b></div></div>
      <div><dt class="kicker">Trades</dt><dd class="statbig">${f.all.length} <small>${(f.all.length / Math.max(1, Math.min(run.daysDone, 30))).toFixed(1)} a day</small></dd><div class="meta mt1">${f.won.length} made money · ${f.lost.length} lost · ${f.all.length - f.closed.length} open</div></div>
      <div><dt class="kicker">Spent on the models (real dollars)</dt><dd class="statbig">${cents(run.spent)} <small>of ${cents(run.cap)} cap</small></dd>${track(run.spent / run.cap, run.spent >= run.cap)}<div class="meta">estimated ${cents(run.est)} for the whole run</div></div>
    </dl></div>`;
}

/* ---------- the chart: full width, hover for any moment, click to open it ---------- */
function bigChart(run) {
  const cs = Object.assign({}, CHART[LOOK] || CHART.plasma, CURVE ? { curve: CURVE } : {});
  const s = seriesOf(run), p = partnerOf(run), W = 1400, H = 500, m = { t: 20, r: 236, b: 52, l: 96 }, n = run.days * 4 + 1;
  const lines = [{ key: "agent", name: "this run " + fmt$(run.value), vals: s.agent, kind: "subject" }, { key: "holding", name: "holding " + fmt$(run.holding), vals: s.holding, kind: "dashed" }];
  if (p) lines.push({ key: "partner", name: (p.variant === "memory_on" ? "with memory " : "without ") + fmt$(p.value), vals: seriesOf(p).agent, kind: "context" });
  const { y, ticks } = scaleY(lines.flatMap(l => l.vals).concat([10000]), H, m.t, m.b, 6);
  const x0 = m.l, x1 = W - m.r, y0 = m.t, y1 = H - m.b, x = i => x0 + (x1 - x0) * i / (n - 1), f1 = v => v.toFixed(1);
  const path = vals => {
    const P = vals.map((v, i) => [x(i), y(v)]);
    if (cs.curve === "step") return P.map((q, i) => (i ? `H${f1(q[0])}V${f1(q[1])}` : `M${f1(q[0])} ${f1(q[1])}`)).join("");
    if (cs.curve === "line") return P.map((q, i) => (i ? "L" : "M") + f1(q[0]) + " " + f1(q[1])).join("");
    /* smooth: a curve through every point, the way the plasma screen in the picture drew its line */
    let d = `M${f1(P[0][0])} ${f1(P[0][1])}`;
    for (let i = 0; i < P.length - 1; i++) {
      const a = P[Math.max(0, i - 1)], b = P[i], c = P[i + 1], e = P[Math.min(P.length - 1, i + 2)];
      d += `C${f1(b[0] + (c[0] - a[0]) / 6)} ${f1(b[1] + (c[1] - a[1]) / 6)} ${f1(c[0] - (e[0] - b[0]) / 6)} ${f1(c[1] - (e[1] - b[1]) / 6)} ${f1(c[0])} ${f1(c[1])}`;
    }
    return d;
  };
  let g = cs.hatch ? `<defs><pattern id="hatch" width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="7" stroke="var(--line)" stroke-width="1"/></pattern></defs>` : "";
  const ln = (xa, ya, xb, yb, cls) => `<line class="${cls}" x1="${f1(xa)}" y1="${f1(ya)}" x2="${f1(xb)}" y2="${f1(yb)}"/>`;
  ticks.forEach((t, k) => {
    const ty = y(t);
    if (cs.grid && ty > y0 + 1 && ty < y1 - 1) g += ln(x0, ty, x1, ty, cs.grid === "dots" ? "gl dots" : "gl");
    if (cs.ticks === "in") g += ln(x0, ty, x0 + 10, ty, "ax") + ln(x1 - 10, ty, x1, ty, "ax");
    if (cs.ticks === "out") g += ln(x0 - 7, ty, x0, ty, "ax");
    if (cs.minor && k < ticks.length - 1) { const my = (ty + y(ticks[k + 1])) / 2; g += ln(x0, my, x0 + 5, my, "ax") + ln(x1 - 5, my, x1, my, "ax"); }
    g += `<text class="tick" x="${x0 - 12}" y="${ty + 5}" text-anchor="end">${fmt$(t)}</text>`;
  });
  const per = run.days > 60 ? 60 : run.days > 10 ? 5 : 1;
  for (let d = 0; d <= run.days; d++) {
    const major = d % per === 0, tx = x(d * 4);
    if (run.days > 60 && !major) continue;
    if (major && cs.grid === "full" && d > 0 && d < run.days) g += ln(tx, y0, tx, y1, "gl");
    if (major || cs.minor || cs.grid === "full") g += ln(tx, y1, tx, y1 + (major ? 8 : 4), "ax");
    if (major) g += `<text class="tick" x="${tx}" y="${y1 + 27}" text-anchor="middle">${dayDate(run.start, d)}</text>`;
  }
  g += cs.frame ? `<rect class="ax" x="${x0}" y="${y0}" width="${x1 - x0}" height="${y1 - y0}" fill="none"/>` : ln(x0, y0, x0, y1, "ax") + ln(x0, y1, x1, y1, "ax");
  g += ln(x0, y(10000), x1, y(10000), "startline");
  const order = { dashed: 0, context: 1, subject: 2 };
  [...lines].sort((a, b) => order[a.kind] - order[b.kind]).forEach(l => {
    if (cs.hatch && l.kind === "subject") g += `<path d="${path(l.vals)}V${y1}H${x0}Z" fill="url(#hatch)" opacity=".55"/>`;
    g += `<path class="ln ${l.kind}" d="${path(l.vals)}" fill="none"/>`;
    /* the workstation's way of telling lines apart: a mark on each line once a day, as its charts did */
    if (cs.markers) l.vals.forEach((v, i) => {
      if (i % 4) return; const cx = x(i), cy = y(v), r = 5;
      g += l.kind === "subject" ? ln(cx - r, cy, cx + r, cy, "mark") + ln(cx, cy - r, cx, cy + r, "mark")
        : l.kind === "dashed" ? ln(cx - r, cy - r, cx + r, cy + r, "mark") + ln(cx - r, cy + r, cx + r, cy - r, "mark") + ln(cx - r, cy, cx + r, cy, "mark")
        : `<rect class="mark" x="${f1(cx - 4)}" y="${f1(cy - 4)}" width="8" height="8" fill="var(--bg)"/>`;
    });
  });
  /* every trade is a small tick along the bottom, at the moment it was opened */
  tradesOf(run).forEach(t => { const tx = x(openMin(t) / 360); if (tx <= x1) g += `<line class="rug ${t.open ? "open" : ""}" x1="${tx.toFixed(1)}" x2="${tx.toFixed(1)}" y1="${y1 - 13}" y2="${y1 - 2}"/>`; });
  const ends = lines.map(l => ({ l, x: x(l.vals.length - 1), y: y(l.vals[l.vals.length - 1]) }));
  ends.push({ l: { name: "start $10,000", kind: "ref" }, x: x1, y: y(10000) });
  ends.sort((a, b) => a.y - b.y); for (let i = 1; i < ends.length; i++) if (ends[i].y < ends[i - 1].y + 19) ends[i].y = ends[i - 1].y + 19;
  ends.forEach(e => {
    if (e.l.kind === "subject" && !cs.markers) g += `<circle class="enddot" cx="${e.x}" cy="${y(e.l.vals[e.l.vals.length - 1])}" r="5"/>`;
    /* a line's name sits at its end; once the lines reach the right edge, in the margin beyond the frame */
    g += `<text class="lbl ${e.l.kind === "subject" ? "subject" : ""}" x="${e.l.kind !== "ref" && e.x < x1 - 230 ? e.x + 14 : x1 + 14}" y="${e.y + 5}">${e.l.name}</text>`;
  });
  g += `<g id="hov" visibility="hidden"><line id="hov-l" class="ax" y1="${y0}" y2="${y1}"/><circle id="hov-h" r="4" fill="var(--bg)" stroke="var(--fg)" stroke-width="1.5"/><circle id="hov-a" class="enddot" r="6"/></g>`;
  g += `<rect id="hov-r" x="${x0}" y="${y0}" width="${x1 - x0}" height="${y1 - y0}" fill="transparent"/>`;
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
  const positions = `<div class="subhead" style="margin-top:0">Open positions <span class="kicker">what the agent holds right now · click one for its decision trail</span></div><div class="tablewrap"><table><thead><tr><th>Asset</th><th>Direction</th><th class="num">Size</th><th>Opened</th><th class="num">Now</th><th class="num">Stop price</th></tr></thead><tbody>${open.map(t => {
    const stop = t.entry * (1 + (t.dir === "long" ? -1 : 1) * 0.006 * t.stopMoves);
    return `<tr class="click" onclick="${exch(t.id)}"><td>${assetTag(t.asset)}</td><td>${t.dir}</td><td class="num">${fmt$(t.size)}${t.trimmed ? ` <span class="badge out" title="Jev chose ${fmt$(t.chosen)}; code made it smaller">trimmed</span>` : ""}</td><td class="num" style="text-align:left">${when(run, t)} · ${t.bars} bars ago</td><td class="num">${sgn$(t.pl)}</td><td class="num">${priceTag(t.asset, stop)}<div class="meta">would lose ${fmt$(t.size * 0.006 * t.stopMoves)}</div></td></tr>`;
  }).join("")}</tbody></table></div>`;
  const latest = f.all.slice(-6).reverse().map(t => `<li class="click" style="display:flex;gap:.75rem;align-items:baseline;flex-wrap:wrap;cursor:pointer" onclick="${exch(t.id)}"><span class="meta" style="width:6.2rem">${when(run, t)}</span>${assetTag(t.asset)} <span>${t.open ? "opened a " + t.dir + " of " + fmt$(t.size) : "closed its " + t.dir + ", " + sgn$(t.pl) + ": " + REASONS[t.reason]}</span></li>`).join("");
  return positions + `<div class="subhead">Latest decisions <span class="kicker">newest first · click one for its decision trail</span></div><ol class="list">${latest}</ol>`;
}

/* ---------- trades and decisions, one table ---------- */
function secActivity(run, q) {
  const f = tradeFacts(run), show = q.get("show") || "trades";
  /* made-up closer looks that ended in no trade: one beside every second trade, half an hour earlier */
  const looks = f.all.filter((t, i) => i % 2 === 0).map(t => ({ none: true, id: t.id, asset: t.asset, d: t.d, minutes: Math.max(0, t.minutes - 30), pattern: PATTERNS[(t.n * 3) % PATTERNS.length] }));
  const sets = { trades: f.all, all: f.all.concat(looks), lost: f.closed.filter(t => t.pl <= 0), trimmed: f.trimmed, stop: f.closed.filter(t => t.reason === "stop"), overnight: f.all.filter(t => t.overnight) };
  const words = { trades: "Trades", all: "Trades, and closer looks that ended in no trade", lost: "Lost money", trimmed: "Trimmed by a limit", stop: "Closed at the stop price", overnight: "Held overnight" };
  const togs = Object.keys(sets).map(k => `<a class="tog ${k === show ? "on" : ""}" href="${runHref(run.id, { show: k })}">${words[k]} <span>${sets[k].length}</span></a>`).join("");
  const list = [...(sets[show] || sets.trades)].sort((a, b) => (b.d * 1440 + b.minutes) - (a.d * 1440 + a.minutes)).slice(0, 40);
  const row = t => t.none
    ? `<tr class="click dim" onclick="openPanel({kind:'exchange',tid:'${t.id}',none:true})"><td class="num" style="text-align:left">${when(run, t)}</td><td>${assetTag(t.asset)}</td><td>no trade<div class="meta">${t.pattern}</div></td><td class="num">·</td><td class="num">·</td><td class="num">·</td><td class="small">Jev looked closer and picked no trade</td></tr>`
    : `<tr class="click" onclick="${exch(t.id)}"><td class="num" style="text-align:left">${when(run, t)}</td><td>${assetTag(t.asset)}</td><td>${t.dir}<div class="meta">${t.pattern}</div></td>
      <td class="num">${fmt$(t.size)}${t.trimmed ? `<div class="meta"><span class="badge out">trimmed</span> Jev chose ${fmt$(t.chosen)}</div>` : ""}</td><td class="num">${held(t)}${t.overnight ? `<div class="meta">overnight</div>` : ""}</td><td class="num">${t.open ? `<span class="muted">${sgn$(t.pl)} so far</span>` : sgn$(t.pl)}</td><td class="small">${t.open ? `<span class="badge out"><span class="sq"></span>open</span>` : REASONS[t.reason]}</td></tr>`;
  return `<div class="filters"><span class="kicker">Show</span>${togs}</div>
    <div class="tablewrap mt1"><table><thead><tr><th>When (UTC)</th><th>Asset</th><th>Decision</th><th class="num">Size</th><th class="num">Held</th><th class="num">Profit or loss</th><th>How it ended</th></tr></thead><tbody>${list.map(row).join("")}</tbody></table></div>
    <p class="meta mt1">newest first · ${list.length} of ${(sets[show] || sets.trades).length} shown · profit or loss is after trading costs · click a row for its ${TRAIL_NAME.toLowerCase()}</p>`;
}

/* ---------- the page ---------- */
function screenRunV2(id, q) {
  const run = runById(id) || RUNS[0], live = run.status === "running", behind = run.value - run.holding;
  const secs = (live ? [["Now", () => nowSection(run)]] : []).concat([["Trades", () => secActivity(run, q)], ["Measurements", () => secMeasurements(run)], [SCORE_NAME, () => secTrackRecord(run).replace("The track record is", "The " + SCORE_NAME.toLowerCase() + " is")], ["Settings", () => secSettings(run)]]);
  const p = partnerOf(run), cs = CHART[LOOK] || CHART.plasma;
  const mk = cs.markers ? ["+ ", "□ ", "✳ "] : ["", "", ""];
  const legend = `<span><i class="sw"></i>${mk[0]}this run</span>${p ? `<span><i class="sw ctx"></i>${mk[1]}its partner, ${VARIANT_WORDS[p.variant]}</span>` : ""}<span><i class="sw ref"></i>${mk[2]}holding the five assets</span><span>| a trade opened</span>`;
  const rail = `<div class="sticky win railwin"><span class="kicker">On this page</span><ol class="list mt1 onpage">${secs.map((s, i) => `<li><a href="javascript:void 0" onclick="document.getElementById('sec${i}').scrollIntoView()"><span class="idx" data-n="${i + 1}">0${i + 1}</span><span class="nm">${s[0]}</span></a></li>`).join("")}</ol>
    <div class="mt2"><span class="kicker">Notable moments</span></div><div class="mt1">${eventList(run)}</div></div>`;
  return note("the trading sim page, round 4", `Five looks drawn from your pictures, on the layout from round 3. <b>Look</b> in the bar at the bottom (or the ← → keys) switches between them. <b>Letters</b> switches between all capitals and normal case; the text sent to Jev and the LLM, shown in the side panel, always stays exactly as it was sent. <b>Colour</b> tries any look in another screen colour. Click a row for its ${TRAIL_NAME.toLowerCase()}; hover and click the chart. The <a href="#/" style="text-decoration:underline">guide page</a> says which picture each look comes from.`, "first") + runHeader2(run) + `
    <section class="chartblock win">
      <p class="chartlede">After <b>${run.daysDone} ${run.daysDone === 1 ? "day" : "days"}</b> the account holds <b>${fmt$(run.value)}</b>: <b class="accent">${fmt$(Math.abs(behind))} ${behind < 0 ? "less" : "more"}</b> than holding the five assets and never trading.</p>
      ${figure(1, "Account value, against holding the five assets", legend, `<div id="bigplot">${bigChart(run)}</div>`, `${run.daysDone} of ${run.days} days · 4 points a day · times in UTC · prototype: made-up numbers`)}
      ${live ? metersBlock(run) : ""}
    </section>
    <div class="g12 mt3"><div class="c3">${rail}</div><div class="c9"><div class="stack">${secs.map((s, i) => `<section id="sec${i}" class="win">${sechead("0" + (i + 1), s[0])}${s[1]()}</section>`).join("")}</div></div></div>`;
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
  applyWord(root); markSigns(root);
}
function momentPanel(p) {
  const run = runById(p.run), f = momentFacts(run, p.i), gap = f.value - f.holding;
  const line = t => { const opened = Math.abs(openMin(t) - f.T) <= 180; return `<li class="click" style="display:flex;gap:.75rem;align-items:baseline;flex-wrap:wrap;cursor:pointer" onclick="${exch(t.id)}"><span class="meta" style="width:6.2rem">${opened ? when(run, t) : dayDate(run.start, Math.floor(closeMin(t) / 1440)) + " " + hhmm(closeMin(t) % 1440)}</span>${assetTag(t.asset)} <span>${opened ? "opened a " + t.dir + " of " + fmt$(t.size) : "closed its " + t.dir + ", " + sgn$(t.pl) + ": " + REASONS[t.reason]}</span></li>`; };
  return { label: "A moment in the run", html: `
    <h2 class="ptitle">${f.label}</h2>
    <p class="meta">day ${f.d + 1} of ${run.days} · step ${(stepAt(run, 0) + Math.round(f.T / 15)).toLocaleString("en-US")} · ${run.title}</p>
    <dl class="statrow mt2 rule" style="padding-top:.8rem"><div><dt class="kicker">Account value</dt><dd class="statbig" style="font-size:1.7rem">${fmt$(f.value)}</dd></div><div><dt class="kicker">Holding the five assets</dt><dd class="statbig" style="font-size:1.7rem">${fmt$(f.holding)}</dd><div class="meta">${fmt$(Math.abs(gap))} ${gap < 0 ? "behind" : "ahead"}</div></div><div><dt class="kicker">Since midnight</dt><dd class="statbig" style="font-size:1.7rem">${sgn$(f.sinceMidnight)}</dd></div><div><dt class="kicker">Since the start</dt><dd class="statbig" style="font-size:1.7rem">${sgn$(f.value - 10000)}</dd></div></dl>
    <div class="subhead">Positions open at that moment <span class="kicker">click one for its decision trail</span></div>
    ${f.held.length ? `<div class="tablewrap"><table style="min-width:0"><thead><tr><th>Asset</th><th>Direction</th><th class="num">Size</th><th>Opened</th><th class="num">Ended with</th></tr></thead><tbody>${f.held.map(t => `<tr class="click" onclick="${exch(t.id)}"><td>${assetTag(t.asset)}</td><td>${t.dir}</td><td class="num">${fmt$(t.size)}</td><td class="num" style="text-align:left">${when(run, t)}</td><td class="num">${t.open ? "still open" : sgn$(t.pl)}</td></tr>`).join("")}</tbody></table></div>` : `<div class="waiting" style="padding:1.2rem 0"><span class="kicker">None</span><p style="font-size:1.2rem">The account was all in cash at that moment.</p></div>`}
    <div class="subhead">Opened or closed within 3 hours of it</div>
    ${f.near.length ? `<ol class="list">${f.near.map(line).join("")}</ol>` : `<div class="waiting" style="padding:1.2rem 0"><span class="kicker">Nothing</span><p style="font-size:1.2rem">No trade was opened or closed around then.</p></div>`}
    <p class="meta mt2">The real screen would also list every check and full evaluation at that exact step.</p>` };
}

/* The exchange as an ordered list of stops, each with the messages that passed. who: jev | code | llm | mem. */
function exchangeStops(run, t, none) {
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
  if (none) {
    stops[0].out = "0.58"; stops[0].msgs[1].out = "0.58"; stops[0].msgs[1].text = "0.58";
    stops.push({ name: "Pick", ask: "Which trade, if any?", out: "no trade", end: true, say: "No trade (0.46) beat long (0.38) and short (0.16), so nothing was opened and the step ended here.", msgs: [
      { from: "code", to: "jev", t: "The background again, and the candidate trades", meta: "about 3,400 tokens", text: "[the background]\n\nQuestion: Which trade, if any?\n- long, tight stop price …\n- … 5 more\n- no trade" },
      { from: "jev", to: "code", t: "Its answer, averaged over 5 shuffled copies", out: "no trade", text: "long 0.38 · short 0.16 · no trade 0.46\npick: no trade" }] });
    return stops;
  }
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
  const { run, trade: t } = findTrade(p.tid), a = ASSETS[t.asset], stops = exchangeStops(run, t, p.none);
  return { label: TRAIL_NAME, html: `
    <h2 class="ptitle">${p.none ? "No trade in " + a.name : (t.dir === "long" ? "Long" : "Short") + " in " + a.name + ", " + fmt$(t.size)}</h2>
    <p class="meta">${p.none ? when(run, t) + " UTC · a closer look that ended in no trade" : `trade ${t.n} · ${when(run, t)} UTC · ${t.open ? "still open, " + sgn$(t.pl) + " so far" : sgn$(t.pl) + ", " + REASONS[t.reason]} · <a href="${href("trade/" + t.id)}" onclick="closePanel()" style="text-decoration:underline">open the trade's own page</a>`}</p>
    <div class="pkey"><span class="chip">${t.asset}</span> is <b>${a.name}</b> (${a.symbol}). The boxed text is exactly what was sent, so it uses the masked ID and rescaled prices: <span class="mono">${t.entry.toFixed(2)}</span> there is <b>${realPrice(t.asset, t.entry)}</b>.</div>
    ${FLOW === "lanes" ? flowLanes(stops) : FLOW === "strip" ? flowStrip(stops) : flowRail(stops)}` };
}

/* ---------- trying another word for "run" ---------- */
function applyWord(root) {
  if (!WORD || !root) return;
  const w = WORDS[WORD], cap = s => s[0].toUpperCase() + s.slice(1);
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT), nodes = []; let nd;
  while ((nd = walker.nextNode())) nodes.push(nd);
  nodes.forEach(x => {
    if (x.parentElement.closest("pre, .pnote, #bar, .guide")) return;
    let s = x.nodeValue;
    if (s.trim() === "Runs") s = s.replace("Runs", cap(w.full) + "s");
    s = s.replace(/\b(All|New|all|new) runs?\b/g, (all, lead) => lead + " " + w.full + (/s$/.test(all) ? "s" : ""));
    x.nodeValue = s.replace(/(?<!evaluation )\b(R|r)un(s?)\b/g, (all, r, plural) => (r === "R" ? cap(w.short) : w.short) + plural);
  });
}

/* ---------- round 4: the command line under the masthead, and marking gains and losses ---------- */
/* The line every reference screen has under its header: what to do on this page. */
function cmdLine(page) {
  const text = { run: "Hover the chart for any moment and click to open it", runs: "Pick a run to open it", "new-run": "Enter all values and hit", datasets: "Enter all values and hit", trade: "Click a mark on the chart for its decision trail" }[page] || "Read only";
  return `<div class="cmd"><span class="cl">Command</span><span class="ct">${text}</span><kbd>&lt;GO&gt;</kbd></div>`;
}
/* A cell that holds only a gain or a loss gets a class, so a look with colours can colour it. */
function markSigns(root) {
  if (!root) return;
  root.querySelectorAll("td, dd, small, b, span, .big").forEach(el => {
    if (el.children.length || el.closest("pre, .pnote")) return;
    const sign = /^\s*([+−])\$[\d,.]+/.exec(el.textContent);
    if (sign) el.classList.add(sign[1] === "+" ? "up" : "dn");
  });
}
