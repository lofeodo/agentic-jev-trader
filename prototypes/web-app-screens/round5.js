/* PROTOTYPE, rounds 5 and 6. The guide page, rewritten for round 6. It replaces the function of the same name in
   round2.js, which stays as the record of round 4; round 5's guide is in commit d6adcad.
   The switches themselves are in run2.js (MIXES, MARKS_WORDS), app.js (the bar), and round5.css (how each is drawn). */

/* What each Wireframe part does, in the words shown to the developer. Same keys and order as MIXES. */
const MIX_WORDS = {
  ruler: "A ruler under the status line, with a pointer at the day the sim has reached.",
  heads: "Each section heading sits in a box, with its number in a cell of its own and a line running off to the right. The \"on this page\" list on the left is drawn the same way.",
  boxes: "An outlined box round each of the four key figures, and one round the chart.",
  pairs: "Status, day, replaying, step: each label shares one box with its value, with a line between them.",
  top: "The menu and the command line in boxes.",
  title: "The title in Wireframe's heavy typeface.",
  type: "Wireframe's letters: small labels in the plain typeface, spaced wide, and the big figures in the fixed-width one.",
  left: "Everything starts at the left edge, where Plasma centres the header.",
  two: "Red-orange lines with amber letters, where Plasma alone is one orange for both.",
  glow: "A faint glow round boxes and along the chart's main line.",
  grid: "Faint lines across and down the chart, so a value can be read off it.",
  hatch: "Diagonal hatching under the sim's line in the chart.",
};

function screenGuide() {
  const yours = `?look=plasma&mix=${MIX_YOURS.join(",")}&line=line&face=arimo`;
  const at = marks => `${yours}${marks ? "&marks=" + marks : ""}#/run/rise-on-1`;
  const keys = Object.keys(MIXES);
  const part = k => `<li><p class="small"><b>${MIXES[k]}${MIX_YOURS.includes(k) ? "" : " (off)"}.</b> ${MIX_WORDS[k]}</p></li>`;
  return `<div class="guide"><span class="kicker">Prototype · round 6 · all data made up</span>
    <h1 class="display title" style="max-width:none">The web app's look, sixth pass: marks where a trade opens and closes</h1>
    <p class="lead mt2">Your look is settled and is now what the prototype opens with. This round adds the one thing you asked for: marks on the chart where a trade happens. Purple boxes and the purple bar are notes to you, not part of the design.</p>
    <div class="g12 mt3"><div class="c7">
      ${sechead("01", "Trade marks, three ways")}
      <p class="small">A hollow square is where a trade opened. A filled square is a trade that is still open. An x is where a trade closed. The made-up sim has 47 trades in its first 12 days, so that is 92 marks.</p>
      <ol class="list mt1">
        <li><h3>Strip under the chart</h3><p class="small">The marks sit in two rows under the chart, opened above and closed below, each under the moment it happened. The line itself stays clean. Clicking a mark opens that trade's decision trail. <a href="${at("strip")}" style="text-decoration:underline">Open it →</a></p></li>
        <li><h3>On the line</h3><p class="small">Each mark sits on the sim's own line at the moment it happened, the way the Workstation chart put its marks on its lines. <a href="${at("line")}" style="text-decoration:underline">Open it →</a></p></li>
        <li><h3>Ticks along the bottom</h3><p class="small">What the chart had until now: one small tick inside the chart's bottom edge for each trade opened, and nothing for a close. <a href="${at("")}" style="text-decoration:underline">Open it →</a></p></li>
      </ol>
      <p class="small mt1">On the page, <b>Trade marks</b> in the first row of the bar at the bottom moves between the three.</p>
      <div class="mt3">${sechead("02", "Your look, as decided")}</div>
      <ol class="list">
        <li><p class="small"><b>Base:</b> Plasma, drawn from your main picture.</p></li>
        ${keys.filter(k => MIX_YOURS.includes(k)).map(part).join("")}
        <li><p class="small"><b>Letters:</b> all capitals. <b>Chart line:</b> straight. <b>Colour:</b> as pictured. <b>Typeface:</b> Arimo, with JetBrains Mono for fixed-width letters.</p></li>
        <li><p class="small"><b>Left off:</b> ${keys.filter(k => !MIX_YOURS.includes(k)).map(k => MIXES[k].toLowerCase()).join(", ")}.</p></li>
        <li><p class="small"><b>The decision trail</b> keeps its six boxes.</p></li>
      </ol>
      <p class="small mt1">Every switch from round 5 is still in the bar, in case you want to change your mind. <b>Your pick</b> in the second row brings this look back.</p>
    </div><div class="c5"><div class="sticky">
      <div class="pnote" style="margin:0"><b class="t">Questions for you</b>
        <ul>
          <li><b>1. Which way for the trade marks?</b> <i>My pick: the strip under the chart. On the line, 92 marks in 12 days already cover the line they sit on, and a full 30-day sim would have about 230. In the strip you can still see when the agent was busy and when it sat still, the line stays readable, and each mark can be clicked.</i></li>
          <li><b>2. Anything else to change?</b> If not, this closes the ticket: the look goes into the map as decided, with this prototype as the reference for whoever builds the app.</li>
        </ul>
        <p style="margin-top:.6rem"><b>One thing I left out on purpose:</b> the marks do not say whether a trade made or lost money, or whether it bet on the price rising or falling. Two shapes are easy to read at this size; six would not be. The trades table and the decision trail carry that detail. Say so if you want it on the chart.</p>
      </div>
    </div></div></div></div>`;
}
