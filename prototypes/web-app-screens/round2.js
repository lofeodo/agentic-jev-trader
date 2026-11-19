/* PROTOTYPE, round 2. The two forms and the guide, rewritten after the developer's first reaction.
   These three functions replace the ones of the same name in screens-other.js. */

function screenNewRun() {
  const left = CEILING - totalSpent();
  const f = (label, control, help) => `<label class="f"><span>${label}</span>${control}${help ? `<small>${help}</small>` : ""}</label>`;
  const sel = opts => `<select>${opts.map(o => `<option>${o}</option>`).join("")}</select>`;
  const pick = (name, on, title, words) => `<label class="pick"><input type="radio" name="${name}" ${on ? "checked" : ""}><b>${title}</b><small>${words}</small></label>`;
  return note("new run, round 2", `Changed as you asked: each kind says what it is for; the dates offer the two test stretches or your own dates; the variant starts on "with memory"; the repeat field is gone (the app numbers repeats itself and says why they exist); and "what the app refuses" is now an error box that appears only when something blocks the run. One blocked example is shown so you can see how it reads.`, "later") + `
    <span class="kicker"><a href="${href("runs")}">← All runs</a></span><h1 class="display title" style="margin-bottom:2rem">New run</h1>
    <div class="g12"><div class="c7">
      <span class="kicker">What kind of run</span>
      <div class="mt1">
        ${pick("kind", true, "Measurement", "30 days inside the test period. These are the only results the verdict on memory is drawn from.")}
        ${pick("kind", false, "Tuning", "About a week, without memory, to adjust how the agent behaves before anything counts. Never on test period days. Its results never count.")}
        ${pick("kind", false, "Build-up", "One year, without memory, that fills the memory later runs start from. Done once. Its results never count.")}
        ${pick("kind", false, "Practice", "One replayed day on the real paid services, to check that everything works. Stops at $0.25. Its results never count.")}
      </div>
      <div class="mt2"><span class="kicker">Which days</span></div>
      <div class="filters mt1"><span class="tog on">Rising market · 9 Apr to 8 May 2025</span><span class="tog">Falling market · 10 Mar to 8 Apr 2025</span><span class="tog">My own dates</span></div>
      <div class="two">${f("first day", `<input type="date" value="2025-04-09">`)}${f("last day", `<input type="date" value="2025-05-08">`)}</div>
      <div class="mt2"><span class="kicker">With or without memory</span></div>
      <div class="mt1">
        ${pick("variant", true, "With memory", "The LLM selects past episodes for Jev to read before each trade.")}
        ${pick("variant", false, "Without memory", "Jev decides alone. The LLM is never called.")}
      </div>
      <label class="f" style="display:flex;gap:.6rem;align-items:baseline"><input type="checkbox" checked style="width:auto;accent-color:var(--accent)"><span style="font:inherit;font-family:var(--serif);font-size:15px">Also start its partner without memory, side by side <small style="display:inline;color:var(--muted)">(a verdict compares the two, and running them together means both face the same version of Jev)</small></span></label>
      <div class="why small mt2"><span class="kicker">Repeat 2 of 3 · numbered by the app</span><br>Jev answers the same question slightly differently each time, so the same 30 days never replay exactly alike. Running the same pair three times shows how much of a result is luck. Repeat 1 of the rising market is running now.</div>
      <div class="two mt1">${f("dataset", sel(["first dataset v1 · published"]))}${f("starting account value", `<input value="$10,000">`)}</div>
      <div class="two">${f("memory to start from", sel(["the base memory · 1,912 closed trades"]), "Each run with memory gets its own fresh copy.")}${f("risk profile", sel(["medium"]), "Frozen. Only a tuning run may change its settings.")}</div>
    </div><div class="c5"><div class="sticky">
      <span class="kicker">What it will cost · real dollars</span>
      <div class="keyfig mt1">$3.30 <small>estimated</small></div>
      <dl class="pairs mt2"><dt class="small">With memory, 30 days at about $0.08</dt><dd>$2.40</dd><dt class="small">Without memory, 30 days at about $0.03</dt><dd>$0.90</dd><dt class="small">Spending cap for the pair (1.5 times the estimate)</dt><dd>$4.95</dd><dt class="small">Still unspent under the $${CEILING} ceiling</dt><dd>${cents(left)}</dd></dl>
      <p class="mt2"><button class="btn hot wide">Start both runs</button></p>
      <div class="subhead">Errors <span class="kicker">prototype: an example · empty when nothing blocks the run</span></div>
      <div class="callout" role="alert"><b>This run can't start.</b><br>A tuning run can't use test period days, and 10 and 11 March 2025 are in the test period.<br>Fix: move the last day to 9 March 2025 or earlier.</div>
      <p class="small muted mt1">The other two things that block a run: its memory holds records from after its first day, or its spending cap could take the project past the $${CEILING} ceiling. Each says what is wrong and how to fix it.</p>
    </div></div></div>`;
}

function screenDatasets() {
  const f = (label, control, help) => `<label class="f"><span>${label}</span>${control}${help ? `<small>${help}</small>` : ""}</label>`;
  const check = [["ASSET_01", 6, 0.03], ["ASSET_02", 11, 0.05], ["ASSET_03", 8, 0.02], ["ASSET_04", 31, 0.09], ["ASSET_05", 0, 0.04]];
  return note("datasets, round 2", `Changed as you asked: the two days are date pickers; the two quality limits are fields you can change; and <b>the data is checked before anything is built</b>. The check only downloads the bars and counts the problems, which is free and takes a few minutes. The slow part (working out measurements and embedding texts in Snowflake) starts only once the check passes, so no build is thrown away. The example shows Exxon over the limit, with the ways out. The test period is still here, now with its reason: see the question on the guide page.`, "later") + `
    <div class="g12"><div class="c5">
      <span class="kicker">Build a new dataset</span>
      ${f("assets", `<input placeholder="search by name or symbol">`, `<span class="chip ink">SPY ×</span> <span class="chip ink">AAPL ×</span> <span class="chip ink">JPM ×</span> <span class="chip ink">XOM ×</span> <span class="chip ink">BTCUSDT ×</span>`)}
      <div class="two">${f("first day", `<input type="date" value="2023-04-03">`)}${f("last day", `<input type="date" value="2026-10-31">`)}</div>
      <div class="mt2"><span class="kicker">How much bad data to accept</span></div>
      <div class="two">${f("partial-volume days per stock, at most", `<input value="3 %">`, "Days on which the data provider's bars carry only part of the market's trading. The stock sits those days out.")}${f("bars missing for any other reason, at most", `<input value="0.5 %">`, "Bars the data provider did not supply at all.")}</div>
      <div class="mt2"><span class="kicker">Days locked away for the final measurement · optional</span></div>
      <p class="small muted mt1">The test period. The agent is never adjusted on these days, the way an exam paper stays sealed until exam day: tuning on them would flatter the result. The app refuses a tuning run here.</p>
      <ol class="list"><li class="small" style="display:flex;gap:.6rem"><span style="flex:1"><b>Falling market</b> · 10 Mar to 8 Apr 2025</span><span class="kicker">remove ×</span></li><li class="small" style="display:flex;gap:.6rem"><span style="flex:1"><b>Rising market</b> · 9 Apr to 8 May 2025</span><span class="kicker">remove ×</span></li></ol>
      <p class="mt1"><button class="btn">Add a stretch</button></p>
    </div><div class="c7">
      <span class="kicker">Step 1 · free · a few minutes</span>
      <p class="mt1"><button class="btn wide">Check the data</button></p>
      <div class="tablewrap mt2"><table style="min-width:0"><thead><tr><th>Asset</th><th class="num">Partial-volume days</th><th class="num">Other missing bars</th><th>Against your limits</th></tr></thead><tbody>${check.map(c => { const share = c[1] / 899, over = share > 0.03; return `<tr><td>${ASSETS[c[0]].name}</td><td class="num">${ASSETS[c[0]].cls === "stock" ? c[1] + " of 899 · " + (share * 100).toFixed(1) + "%" : "none"}</td><td class="num">${c[2].toFixed(2)}%</td><td class="small">${over ? `<span class="badge fill">over 3%</span>` : `<span class="badge ink">fits</span>`}</td></tr>`; }).join("")}</tbody></table></div>
      <div class="callout" role="alert"><b>Exxon has too many partial-volume days: 3.4% of its sessions, and your limit is 3%.</b><br>Ways out: raise the limit to 3.5%, leave Exxon out, or move the first day later (most of its bad days are before June 2023).</div>
      <div class="mt2"><span class="kicker">Step 2 · about 40 minutes · uses Snowflake trial credits, no model dollars</span></div>
      <p class="mt1"><button class="btn hot wide" disabled>Build the dataset</button></p>
      <p class="small muted mt1">Opens once the check passes. A published dataset never changes; a different asset list is a new dataset.</p>
      <div class="subhead">Datasets</div>
      <ol class="list"><li><a href="${href("dataset")}" style="display:block"><div style="display:flex;gap:.75rem;align-items:baseline;flex-wrap:wrap"><span style="font:600 1.5rem var(--display)">first dataset v1</span><span class="badge ink">published</span><span class="meta" style="margin-left:auto">built 20 Nov 2026 · 14 runs use it</span></div>
        <div class="small">S&P 500 fund, JPMorgan, Apple, Exxon, Bitcoin · 3 Apr 2023 to 31 Oct 2026 · test period 10 Mar to 8 May 2025</div></a></li></ol>
    </div></div>`;
}

function screenGuide() {
  const rows = [
    ["Runs", href("runs"), "Every run, grouped by kind, with its status, its account value against holding the five assets, and its spending.", 1],
    ["Run", runHref("rise-on-1"), "One long report per run, live while it replays: the big chart, then now, measurements, trades, decisions, track record, settings.", 1],
    ["Trade", href("trade/rise-on-1-t40"), "One trade reviewed the way a trader reviews it: price chart with entry, stop price, and close; the order; every position check; the memory Jev read.", 1],
    ["Side panel: the exchange behind a decision", href("decision/rise-on-1-t47"), "No longer a screen. It slides in from the right wherever you click a trade, a position, or a decision.", 1],
    ["Side panel: a moment", runHref("rise-on-1"), "Opens when you click the chart: the account at that moment, the positions it held, what it decided around then.", 1],
    ["Comparison", href("comparison"), "One verdict per market, both groups' averages and standard deviations, the gap over time.", 0],
    ["New run", href("new-run"), "Kind, days, memory or not, cost, and the error box.", 0],
    ["Datasets", href("datasets"), "Check the data, then build; and the list of datasets.", 0],
    ["Dataset", href("dataset"), "Build progress, quality report, asset key, a price chart per asset.", 0],
    ["Playbook", href("playbook"), "The 61 candle patterns: name, lean, shape.", 0],
    ["Spending", href("spending"), "Real dollars paid to Jev and the LLM against the $50 ceiling.", 0],
  ];
  return `<div class="guide"><span class="kicker">Prototype · round 2 · all data made up</span>
    <h1 class="display title" style="max-width:none">The web app's screens, second pass</h1>
    <p class="lead mt2">You picked layout B and asked for changes. This pass makes them, and adds what you asked to see: the exchange as a side panel drawn three ways, and the run page in three terminal looks. Purple boxes and the purple bar are notes to you, not part of the design.</p>
    <div class="g12 mt3"><div class="c7">
      ${sechead("01", "What changed since the first pass")}
      <ol class="list">
        <li><h3>The run page</h3><p class="small">One long report (your pick, B). The chart now runs the full width at the top. The "now" briefing is three thin meters under it. Hover the chart for any moment; click it to open that moment in a side panel. <a href="${runHref("rise-on-1")}" style="text-decoration:underline">Open the run page</a>.</p></li>
        <li><h3>The exchange behind a decision</h3><p class="small">A side panel, reached by clicking any trade, open position, or decision. The section headings are gone. It is drawn three ways for you to compare: a <b>rail</b> (one straight line with six stops), <b>lanes</b> (a column each for Jev, code, the LLM, and memory, with an arrow per message), and a <b>strip</b> (six boxes left to right). With the panel open, switch between them in the bar at the bottom or with the ← → keys. <a href="${href("decision/rise-on-1-t47")}" style="text-decoration:underline">Open one</a>.</p></li>
        <li><h3>Three terminal looks, run page only</h3><p class="small"><b>Phosphor:</b> the green quote terminal at a trading post. <b>Big board:</b> the amber split-flap wall board with a running ticker tape. <b>Tape and ticket:</b> the green-striped printer paper the floor's reports came on. On the run page, "Look" in the bar switches between them and the paper style.</p></li>
        <li><h3>Another word for "run"</h3><p class="small">On the run page, "Word" in the bar swaps "run" for <b>backtest</b>, <b>replay</b>, or <b>simulation</b> across the page, so you can see each in place. A backtest is the finance word for trying a strategy on past prices to see how it would have done.</p></li>
        <li><h3>The two forms</h3><p class="small"><a href="${href("new-run")}" style="text-decoration:underline">New run</a>: each kind explained, own dates allowed, "with memory" first, no repeat field, an error box. <a href="${href("datasets")}" style="text-decoration:underline">Datasets</a>: date pickers, quality limits you can change, and the data is checked before anything is built.</p></li>
      </ol>
      <div class="mt3">${sechead("02", "The screens now", "9 screens and 2 side panels")}</div>
      <table><thead><tr><th>Screen</th><th>What it shows</th><th>When</th></tr></thead><tbody>${rows.map(r => `<tr><td><a href="${r[1]}" style="font:600 1.05rem var(--display);text-decoration:underline">${r[0]}</a></td><td class="small">${r[2]}</td><td>${r[3] ? `<span class="badge fill">first dashboard</span>` : `<span class="badge">later</span>`}</td></tr>`).join("")}</tbody></table>
      <p class="small muted mt1"><b>Settled in the first pass:</b> the first dashboard (yes), UTC as the one clock, React with TypeScript, Vite, Tailwind, and D3.</p>
    </div><div class="c5"><div class="sticky">
      <div class="pnote" style="margin:0"><b class="t">Questions for you</b>
        <ul>
          <li><b>1. The look.</b> Paper, Phosphor, Big board, or Tape and ticket? If a terminal look wins, it becomes the look of the whole app and replaces the editorial paper style. <i>My pick among the three: Big board. It keeps long text readable, which Phosphor's single screen font does not.</i></li>
          <li><b>2. The exchange.</b> Rail, lanes, or strip? <i>My pick: the rail as the default, because it reads top to bottom with the six outcomes down the right edge. Lanes is the one to add if you want to see who spoke to whom.</i></li>
          <li><b>3. The word.</b> Backtest, replay, simulation, or keep run? <i>My pick: backtest. It is what traders and every trading tool call exactly this.</i></li>
          <li><b>4. The run page.</b> Is the chart big enough now, and is the slimmed "now" strip right?</li>
          <li><b>5. Repeats.</b> The repeat field is gone from New run: the app numbers repeats itself and explains them. OK?</li>
          <li><b>6. The test period.</b> It stays on the dataset form as an optional, explained part, because it is what lets the app refuse tuning on those days. The other choice is to mark it later, on the dataset's own page. <i>My pick: keep it on the form.</i></li>
        </ul>
      </div>
    </div></div></div></div>`;
}
