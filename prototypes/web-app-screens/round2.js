/* PROTOTYPE, rounds 2 and 3. The two forms and the guide, rewritten after the developer's reactions.
   These three functions replace the ones of the same name in screens-other.js. */

/* The New run form remembers what is picked, so the parts that depend on the kind change as you click. */
const NR = { kind: "measurement", stretch: "rise", variant: "on", pair: false };
function setNR(key, value) { NR[key] = value; draw.keepScroll = true; draw(); }
const FREE_NAME = "Free run";   /* tried as the name of the run on dates you choose */

function screenNewRun() {
  const left = CEILING - totalSpent(), k = NR.kind;
  const f = (label, control, help) => `<label class="f"><span>${label}</span>${control}${help ? `<small>${help}</small>` : ""}</label>`;
  const sel = opts => `<select>${opts.map(o => `<option>${o}</option>`).join("")}</select>`;
  const pick = (key, value, title, words) => `<label class="pick"><input type="radio" name="${key}" ${NR[key] === value ? "checked" : ""} onchange="setNR('${key}','${value}')"><b>${title}</b><small>${words}</small></label>`;
  const days = k === "measurement" ? 30 : k === "buildup" ? 365 : 7;
  const both = k === "measurement" || (k === "free" && NR.pair), withMem = k === "measurement" || (k === "free" && (NR.variant === "on" || NR.pair)), without = k !== "free" || NR.variant === "off" || NR.pair;
  const cost = (withMem ? days * 0.08 : 0) + (without ? days * 0.03 : 0), cap = cost * 1.5;
  const when = k === "measurement" ? `<div class="filters mt1"><a class="tog ${NR.stretch === "rise" ? "on" : ""}" href="javascript:void 0" onclick="setNR('stretch','rise')">Rising market · 9 Apr to 8 May 2025</a><a class="tog ${NR.stretch === "fall" ? "on" : ""}" href="javascript:void 0" onclick="setNR('stretch','fall')">Falling market · 10 Mar to 8 Apr 2025</a></div>
        <p class="small muted">A measurement always uses one of the two stretches of locked test days, whole.</p>`
    : k === "buildup" ? `<div class="two">${f("first day", `<input type="date" value="2024-03-10">`)}${f("last day", `<input type="date" value="2025-03-09">`)}</div><p class="small muted mt1">One year, ending the day before the locked test days begin.</p>`
    : `<div class="two">${f("first day", `<input type="date" value="2025-03-05">`)}${f("last day", `<input type="date" value="2025-03-11">`)}</div><p class="small muted mt1">Any days in the dataset, except the locked test days (10 March to 8 May 2025).</p>`;
  const memory = k === "measurement" ? `<div class="why small mt1"><b>Both, side by side.</b> The same 30 days are played twice at once: one account trades with memory, the other without. The gap between the two at the end is the result. Starting them together means both face the same version of Jev.</div>
        <div class="why small mt1"><span class="kicker">${NR.stretch === "rise" ? "Repeat 2 of 3" : "All 3 repeats are done; this would be a fourth"} · numbered by the app</span><br>Jev answers the same question slightly differently each time, so the same days never replay exactly alike. Three repeats show how much of a result is luck.</div>`
    : k === "buildup" ? `<div class="why small mt1"><b>Without memory.</b> This is the run that fills the memory, so it has none to read yet.</div>`
    : `<div class="mt1">${pick("variant", "on", "With memory", "The LLM selects past episodes for Jev to read before each trade.")}${pick("variant", "off", "Without memory", "Jev decides alone. The LLM is never called.")}</div>
        <label class="f" style="display:flex;gap:.6rem;align-items:baseline"><input type="checkbox" ${NR.pair ? "checked" : ""} onchange="setNR('pair',this.checked)" style="width:auto;accent-color:var(--accent)"><span style="font:inherit;font-family:var(--serif);font-size:15px">Also play the same days ${NR.variant === "on" ? "without" : "with"} memory, side by side, to compare the two</span></label>`;
  const blocked = k === "free";
  return note("new run, round 3", `Changed as you asked. <b>Practice and tuning runs are gone from this form:</b> they are developer tools and stay on the command line. Three kinds remain, and the form now changes as you click a kind. <b>${FREE_NAME}</b> is the one on your own dates (other names for it are on the guide page). The "also play the same days…" tick box exists only for a ${FREE_NAME.toLowerCase()}, is off by default, and always offers the opposite of what you picked. A measurement always plays both, so it has no tick box. Click "${FREE_NAME}" to see a blocked example in the error box.`, "later") + `
    <span class="kicker"><a href="${href("runs")}">← All runs</a></span><h1 class="display title" style="margin-bottom:2rem">New run</h1>
    <div class="g12"><div class="c7">
      <span class="kicker">What kind of run</span>
      <div class="mt1">
        ${pick("kind", "measurement", "Measurement", "The exam. 30 days the agent has never been adjusted on, played once with memory and once without. The gap between the two is the project's answer to \"does memory help?\". Only these results count.")}
        ${pick("kind", "buildup", "Build-up", "The year of practice before the exam. The agent trades one year without memory, and everything it does is stored. That store becomes the memory later runs start from. Done once; its results never count.")}
        ${pick("kind", "free", FREE_NAME, "Any days you choose, to watch the agent trade or to try something. Its results never count, and it cannot use the locked test days.")}
      </div>
      <div class="mt2"><span class="kicker">Which days</span></div>${when}
      <div class="mt2"><span class="kicker">Memory</span></div>${memory}
      <div class="two mt2">${f("dataset", sel(["first dataset v1 · published"]))}${f("starting account value", `<input value="$10,000">`)}</div>
      ${withMem ? f("memory to start from", sel(["the base memory · left by the build-up run · 1,912 closed trades"]), "Each run with memory gets its own fresh copy.") : ""}
    </div><div class="c5"><div class="sticky">
      <span class="kicker">What it will cost · real dollars</span>
      <div class="keyfig mt1">${cents(cost)} <small>estimated</small></div>
      <dl class="pairs mt2">${withMem ? `<dt class="small">With memory, ${days} days at about $0.08</dt><dd>${cents(days * 0.08)}</dd>` : ""}${without ? `<dt class="small">Without memory, ${days} days at about $0.03</dt><dd>${cents(days * 0.03)}</dd>` : ""}<dt class="small">Spending cap (1.5 times the estimate)</dt><dd>${cents(cap)}</dd><dt class="small">Still unspent under the $${CEILING} ceiling</dt><dd>${cents(left)}</dd></dl>
      <p class="mt2"><button class="btn hot wide" ${blocked ? "disabled" : ""}>${both ? "Start both runs" : "Start the run"}</button></p>
      <div class="subhead">Errors</div>
      ${blocked ? `<div class="callout" role="alert"><b>This run can't start.</b><br>10 and 11 March 2025 are locked test days, and a ${FREE_NAME.toLowerCase()} cannot use them.<br>Fix: move the last day to 9 March 2025 or earlier.</div><p class="small muted mt1">Prototype: an example. The other two things that block a run: its memory holds records from after its first day, or its spending cap could take the project past the $${CEILING} ceiling.</p>` : `<p class="small muted">None. This run can start.</p>`}
    </div></div></div>`;
}

function screenDatasets() {
  const f = (label, control, help) => `<label class="f"><span>${label}</span>${control}${help ? `<small>${help}</small>` : ""}</label>`;
  const check = [["ASSET_01", 6, 0.03], ["ASSET_02", 11, 0.05], ["ASSET_03", 8, 0.02], ["ASSET_04", 31, 0.09], ["ASSET_05", 0, 0.04]];
  return note("datasets, round 3", `Changed as you asked: there is one button. Checking the data is the first step of the build, switched on by a tick box that starts ticked. If the check finds the data over your limits, the build stops there, before the slow part, and says why. The example on the right shows that stop.`, "later") + `
    <div class="g12"><div class="c5">
      <span class="kicker">Build a new dataset</span>
      ${f("assets", `<input placeholder="search by name or symbol">`, `<span class="chip ink">SPY ×</span> <span class="chip ink">AAPL ×</span> <span class="chip ink">JPM ×</span> <span class="chip ink">XOM ×</span> <span class="chip ink">BTCUSDT ×</span>`)}
      <div class="two">${f("first day", `<input type="date" value="2023-04-03">`)}${f("last day", `<input type="date" value="2026-10-31">`)}</div>
      <div class="mt2"><span class="kicker">How much bad data to accept</span></div>
      <div class="two">${f("partial-volume days per stock, at most", `<input value="3 %">`, "Days on which the data provider's bars carry only part of the market's trading. The stock sits those days out.")}${f("bars missing for any other reason, at most", `<input value="0.5 %">`, "Bars the data provider did not supply at all.")}</div>
      <div class="mt2"><span class="kicker">Days locked away for the final measurement · optional</span></div>
      <p class="small muted mt1">The test period. The agent is never adjusted on these days, the way an exam paper stays sealed until exam day. The app refuses any run but a measurement here.</p>
      <ol class="list"><li class="small" style="display:flex;gap:.6rem"><span style="flex:1"><b>Falling market</b> · 10 Mar to 8 Apr 2025</span><span class="kicker">remove ×</span></li><li class="small" style="display:flex;gap:.6rem"><span style="flex:1"><b>Rising market</b> · 9 Apr to 8 May 2025</span><span class="kicker">remove ×</span></li></ol>
      <p class="mt1"><button class="btn">Add a stretch</button></p>
      <label class="f" style="display:flex;gap:.6rem;align-items:baseline;margin-top:1.75rem"><input type="checkbox" checked style="width:auto;accent-color:var(--accent)"><span style="font:inherit;font-family:var(--serif);font-size:15px">Check the data first, and stop before building if it is over the limits above <small style="display:inline;color:var(--muted)">(free; adds a few minutes)</small></span></label>
      <p class="mt1"><button class="btn hot wide">Build the dataset</button></p>
      <p class="small muted mt1">About 40 minutes. Uses Snowflake trial credits, no model dollars. A published dataset never changes.</p>
    </div><div class="c7">
      <span class="kicker">The last build · stopped at the check · prototype: an example</span>
      <ol class="list timeline mt1">
        <li><span class="mk"></span><div style="flex:1"><span class="t">Download the bars</span><div class="small muted">5 assets · 412,300 bars</div></div><span class="when">3 min</span></li>
        <li><span class="mk bad"></span><div style="flex:1"><span class="t">Check the data against your limits</span><div class="small muted">stopped here: Exxon is over the limit</div></div><span class="when">1 min</span></li>
        <li class="muted"><span class="mk pend"></span><div style="flex:1"><span class="t" style="color:inherit">Mask, work out the measurements, embed the texts, publish</span><div class="small muted">not started, so nothing was spent on it</div></div></li>
      </ol>
      <div class="callout" role="alert"><b>Exxon has too many partial-volume days: 3.4% of its sessions, and your limit is 3%.</b><br>Ways out: raise the limit to 3.5%, leave Exxon out, or move the first day later (most of its bad days are before June 2023). Then build again.</div>
      <div class="tablewrap mt2"><table style="min-width:0"><thead><tr><th>Asset</th><th class="num">Partial-volume days</th><th class="num">Other missing bars</th><th>Against your limits</th></tr></thead><tbody>${check.map(c => { const share = c[1] / 899, over = share > 0.03; return `<tr><td>${ASSETS[c[0]].name}</td><td class="num">${ASSETS[c[0]].cls === "stock" ? c[1] + " of 899 · " + (share * 100).toFixed(1) + "%" : "none"}</td><td class="num">${c[2].toFixed(2)}%</td><td class="small">${over ? `<span class="badge fill">over 3%</span>` : `<span class="badge ink">fits</span>`}</td></tr>`; }).join("")}</tbody></table></div>
      <div class="subhead">Datasets</div>
      <ol class="list"><li><a href="${href("dataset")}" style="display:block"><div style="display:flex;gap:.75rem;align-items:baseline;flex-wrap:wrap"><span style="font:600 1.5rem var(--display)">first dataset v1</span><span class="badge ink">published</span><span class="meta" style="margin-left:auto">built 20 Nov 2026 · 14 runs use it</span></div>
        <div class="small">S&P 500 fund, JPMorgan, Apple, Exxon, Bitcoin · 3 Apr 2023 to 31 Oct 2026 · test period 10 Mar to 8 May 2025</div></a></li></ol>
    </div></div>`;
}

function screenGuide() {
  const names = (title, words, list) => `<li><h3>${title}</h3><p class="small">${words}</p><p class="small">${list.map((n, i) => `<span class="badge ${i ? "" : "fill"}">${n[0]}</span> ${n[1]}`).join("<br>")}</p></li>`;
  return `<div class="guide"><span class="kicker">Prototype · round 3 · all data made up</span>
    <h1 class="display title" style="max-width:none">The web app's screens, third pass</h1>
    <p class="lead mt2">This pass does two things: four new terminal looks for the run page, built to be period-correct and easy to read, and names to choose from for the four things you wanted renamed. Purple boxes and the purple bar are notes to you, not part of the design.</p>
    <div class="g12 mt3"><div class="c7">
      ${sechead("01", "Four period looks")}
      <p class="small"><a href="${runHref("rise-on-1")}" style="text-decoration:underline">Open the run page</a> and use "Look" in the bar at the bottom, or the ← → keys.</p>
      <ol class="list mt1">
        <li><h3>1 · 3278 green</h3><p class="small">The IBM 3278, the green mainframe terminal on bank and brokerage desks from the late 1970s. One green, in three strengths.</p></li>
        <li><h3>2 · 3279 colour</h3><p class="small">The same terminal with its colour tube. Each colour has a job: turquoise for labels, green for data, white for headings and key figures, yellow for what to look at, red for warnings.</p></li>
        <li><h3>3 · VT220 amber</h3><p class="small">The DEC VT220 with the amber tube, 1983. Amber was sold as the easier colour on the eyes for a full working day.</p></li>
        <li><h3>4 · PC blue</h3><p class="small">An IBM PC in text mode, late 1980s: white, cyan, and yellow on blue, the way desk trading software looked. The odd one out; brightest and highest in contrast.</p></li>
      </ol>
      <p class="small muted mt1"><b>What changed against round 2's Phosphor, and why it looked fake:</b> it used a modern pixel font drawn to look old, a glow, a scanline overlay, and a second colour (amber on green). A real tube had one phosphor and was sharp. These four use the actual typeface of each machine, one colour family, one text size (with exact double size for the title and the four key figures), and reverse video (a light block with dark letters) for emphasis. Sentences are in normal case; only headings and labels are capitals.</p>
      <div class="mt3">${sechead("02", "Names to choose from", "my pick is the filled one, and it is the one the prototype uses")}</div>
      <ol class="list">
        ${names('A word for "run"', 'It has to say "a simulation of trading" in plain words and stay short. "Word" in the bar swaps it across every screen. Each has a long form for titles and a short form inside sentences.', [["Trading sim", '"All trading sims", "the sim ended in cash". Says exactly what it is; "sim" is everyday speech.'], ["Market replay", '"All market replays", "the replay ended". Says how it works: past market days are played again and the agent trades through them.'], ["Trading trial", '"All trading trials", "the trial ended". Plain, but "trial" can sound like a free trial or a court case.']])}
        ${names('A name for "track record"', "It is the agent's own tally of how its past trades turned out, pattern by pattern: \"bullish engulfing, long, stocks: 38 trades, 58% made money\".", [["Scorecard", "Short, and usable in a sentence: \"the scorecard for hammer longs\"."], ["Results by pattern", "Says exactly what the table is, but is long to say every time."], ["Win and loss record", "Plain, but it leaves out the dollar amounts."], ["Pattern history", "Could be mistaken for the history of prices."]])}
        ${names("The side panel's header", "The panel shows every question and answer that led to one decision, in order.", [["Decision trail", "A trail you follow step by step. No technical baggage."], ["Chain of thought", "Your suggestion. One caution: in AI writing it means a model thinking out loud in words, and Jev does not do that. What the panel shows is questions and answers."], ["How it decided", "The plainest, but reads oddly as a label on a button."], ["Behind the trade", "Friendly, but wrong for a decision that ended in no trade."]])}
        ${names("The run on your own dates", "The third kind on the New run form.", [["Free run", "Free to pick any days."], ["Open run", "Same idea; \"open\" also means an open position, which could confuse."], ["Sandbox", "Says \"safe place to try things\", and nothing counts there."]])}
      </ol>
    </div><div class="c5"><div class="sticky">
      <div class="pnote" style="margin:0"><b class="t">Questions for you</b>
        <ul>
          <li><b>1. The look.</b> 3278 green, 3279 colour, VT220 amber, or PC blue? <i>My pick: 3279 colour. It is as period-correct as the green one, and the colours do real work: you can tell a label from a number from a warning without reading.</i></li>
          <li><b>2. The word for "run".</b> Trading sim, market replay, trading trial, or something else? <i>My pick: trading sim.</i></li>
          <li><b>3. "Track record".</b> Scorecard, results by pattern, or another? <i>My pick: scorecard.</i></li>
          <li><b>4. The side panel's header.</b> Decision trail, chain of thought, or another? <i>My pick: decision trail.</i></li>
          <li><b>5. The run on your own dates.</b> Free run, sandbox, or another? <i>My pick: free run.</i></li>
        </ul>
        <p style="margin-top:.6rem"><b>Done as you said, no question:</b> trades and decisions are one table, in the order now, trades, measurements, scorecard, settings · the panel is drawn as the strip · practice and tuning runs are off the <a href="${href("new-run")}" style="text-decoration:underline">New run</a> form · the tick box there is fixed · <a href="${href("datasets")}" style="text-decoration:underline">Datasets</a> has one button, with the check as a ticked box.</p>
        <p style="margin-top:.6rem"><b>Two things I assumed:</b> practice and tuning runs still show in the <a href="${href("runs")}" style="text-decoration:underline">Runs</a> list, marked as developer tools · a ${FREE_NAME.toLowerCase()} cannot use the locked test days, as tuning runs could not.</p>
      </div>
    </div></div></div></div>`;
}
