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
  const look = (key, name, from, words) => `<li><h3>${name}</h3><p class="small muted" style="margin-bottom:.25rem">From: ${from}</p><p class="small">${words} <a href="?look=${key}#/run/rise-on-1" style="text-decoration:underline">Open it →</a></p></li>`;
  return `<div class="guide"><span class="kicker">Prototype · round 4 · all data made up</span>
    <h1 class="display title" style="max-width:none">The web app's look, fourth pass</h1>
    <p class="lead mt2">Five looks built from the pictures you sent, on the layout you already settled. Each one is drawn differently, not only coloured differently: where the title sits, how a heading is marked, how a table's column names are set off, how the chart is drawn. Purple boxes and the purple bar are notes to you, not part of the design.</p>
    <div class="g12 mt3"><div class="c7">
      ${sechead("01", "Five looks")}
      <p class="small"><a href="${runHref("rise-on-1")}" style="text-decoration:underline">Open the trading sim page</a> and use "Look" in the bar at the bottom, or the ← → keys. The look now covers every screen, so the forms and the error box can be judged too.</p>
      <ol class="list mt1">
        ${look("plasma", "1 · Plasma", "your main picture, the 1986 GRiDCase trading terminal with the orange screen.", "One orange on near-black. The title sits in the middle of the screen. Values sit in lit blocks (dark letters on an orange block), as the date fields do in the picture. Thin rules, a command line under the header, plenty of empty screen. The chart is a plain box with tick marks on the inside, serif numbers, and a smooth line. Two typefaces, as in the picture: a thin fixed-width one for the system's own words, a plain one for titles and sentences. All capitals.")}
        ${look("desk", "2 · Dealing desk", "the two-screen colour terminal and the Reuters monitors.", "Black with amber text, and four more colours that each have one job: red bars for headings, white for the number to read first, blue for labels, green and red for a gain and a loss. Normal case, rows packed closer. The chart has a blue frame and grid.")}
        ${look("page", "3 · Page", "the green screen with INDEX and COMMAND across the top.", "Two bars in reverse video across the top (light bar, dark letters). Titles centred in plain capitals. Column names inside a drawn box. Values lined up by rows of dots, meters made of thin upright bars. The chart is drawn in hard steps. One fixed-width typeface at nearly one size.")}
        ${look("work", "4 · Workstation", "the black-and-white screen with windows and the pie chart.", "A striped desktop, and each part of the page is a window with a double border and a title bar. Where a colour screen would use colour, this one uses patterns: hatching in bars and meters, and a different mark on each chart line (a plus, a box, a star). Its letters are the real ones of a 1980s PC, which makes it the hardest of the five to read.")}
        ${look("wire", "5 · Wireframe", "the orange poster with the wireframe city.", "Red-orange lines and amber letters, with every part of the screen in an outlined box. A label and its value share a box split by a line. Headings have a numbered cell and a line running off to the right. The day of the sim is a ruler with a pointer. A heavy typeface for the title. A faint glow on the boxes only, never on the letters.")}
      </ol>
      <div class="mt3">${sechead("02", "What keeps every look easy to read")}</div>
      <ol class="list">
        <li><p class="small"><b>More than one text size.</b> Round 3 used a single size for everything, as a character screen did, and nothing stood out. Here the title, the four key figures, and the headings are larger, so the eye finds them first.</p></li>
        <li><p class="small"><b>Sharp letters at normal spacing.</b> No glow on text, no scanlines, no blur, and no typeface that spreads its letters so far apart that words stop reading as words.</p></li>
        <li><p class="small"><b>Sentences in a plain typeface</b> where the picture has one (looks 1 and 5). Fixed-width letters are kept for labels, numbers, and tables, where columns have to line up.</p></li>
        <li><p class="small"><b>Text shown word for word stays as it was sent.</b> What Jev and the LLM were sent, in the side panel, is never turned into capitals, in any look.</p></li>
      </ol>
      <div class="mt3">${sechead("03", "The switches in the bar")}</div>
      <ol class="list">
        <li><p class="small"><b>Look</b> moves between the five.</p></li>
        <li><p class="small"><b>Letters</b> switches the look you are on between all capitals and normal case. Each look starts in the case its picture uses.</p></li>
        <li><p class="small"><b>Colour</b> shows the look you are on in another screen colour (orange, amber, green, white), so a look is not turned down for its colour alone.</p></li>
        <li><p class="small"><b>Chart line</b> draws the chart's lines smooth, straight, or in steps, whatever the look. See question 3.</p></li>
      </ol>
      <div class="mt3">${sechead("04", "Where to look")}</div>
      <ol class="list">
        <li><p class="small"><a href="${runHref("rise-on-1")}" style="text-decoration:underline">The trading sim page</a>: the header, the chart (hover it, click it), the tables, the measurements.</p></li>
        <li><p class="small">The decision trail: on the sim page, click any row of the trades table. This is where the longest text is.</p></li>
        <li><p class="small"><a href="${href("new-run")}" style="text-decoration:underline">The new sim form</a>: entry fields, and the error box (click "Free sim" to see it).</p></li>
        <li><p class="small"><a href="${href("runs")}" style="text-decoration:underline">The list of sims</a> and <a href="${href("datasets")}" style="text-decoration:underline">datasets</a>: the same look on screens I did not polish.</p></li>
      </ol>
    </div><div class="c5"><div class="sticky">
      <div class="pnote" style="margin:0"><b class="t">Questions for you</b>
        <ul>
          <li><b>1. Which look, or which parts of which?</b> "The header of 1 with the boxes of 5" is a fine answer. <i>My pick: Plasma. It is your main picture, it is the calmest, and it stayed readable in every part of the page, including the long text in the side panel.</i></li>
          <li><b>2. Capitals or normal case?</b> Try "Letters" on the measurements section of the sim page, which has the longest sentences. <i>My pick: capitals, as in the picture. If the long sentences tire you, the middle way is capitals for labels and headings and normal case for sentences.</i></li>
          <li><b>3. The chart's line: smooth or exact?</b> Plasma draws a smooth curve, as the picture does. A smooth curve rounds the corners between two measured points, so it can swing a little past the true number between them. Example: the account is worth $10,400 at noon and $10,200 at 18:00; a smooth curve may dip to about $10,190 on the way, a value the account never had. Straight lines between the points are exact. <i>My pick: straight. The chart exists to show what the account was worth, and it still looks right in the box with the tick marks. "Chart line" in the bar shows both.</i></li>
          <li><b>4. The colour.</b> <i>My pick: the orange of the picture.</i></li>
          <li><b>5. The typefaces.</b> Plasma's fixed-width one is JetBrains Mono, which is free to use and ships with the app. Its titles and sentences use Helvetica or Arial, whichever the computer already has, so a Mac and a Windows PC would show slightly different letters. Is that fine, or should the app ship one free typeface so it looks the same everywhere? <i>My pick: ship one, chosen and its licence checked when the spec is written.</i></li>
        </ul>
        <p style="margin-top:.6rem"><b>Two things I assumed:</b> the target is now the 1986 trading terminal in your main picture, not a Bloomberg screen in particular · faithfulness stops at the styling: the screens, their order, and the side panel are as you left them in round 3.</p>
      </div>
    </div></div></div></div>`;
}
