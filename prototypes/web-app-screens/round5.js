/* PROTOTYPE, round 5. The guide page, rewritten for this round. It replaces the function of the same name in
   round2.js, which stays as the record of round 4. The switches themselves are in run2.js (MIXES), app.js (the bar),
   and round5.css (how each is drawn). */

/* What each switch does, in the words shown to the developer. Same keys and order as MIXES. */
const MIX_WORDS = {
  ruler: "A ruler under the status line, with a pointer at the day the sim has reached. On day 13 of 30 the pointer sits a little before the middle.",
  heads: "Each section heading sits in a box, with its number in a cell of its own and a line running off to the right. The \"on this page\" list on the left is drawn the same way.",
  boxes: "An outlined box round each of the four key figures, and one round the chart.",
  pairs: "Status, day, replaying, step: each label shares one box with its value, with a line between them. Plasma alone shows the value as a lit block (dark letters on an orange block), as the date fields in your main picture do.",
  top: "The menu and the command line in boxes. Plasma alone copies the picture: plain words, then two thin rules across the screen.",
  title: "The title in Wireframe's heavy typeface.",
  type: "Wireframe's letters: small labels in the plain typeface, spaced wide, and the big figures in the fixed-width one. Plasma alone does the opposite, as the picture does.",
  left: "Everything starts at the left edge. Plasma alone centres the title, the status line, the key figures, and the headings, as the picture does.",
  two: "Red-orange lines with amber letters. Plasma alone is one orange for both.",
  glow: "A faint glow round boxes and along the chart's main line, never on small letters. It only shows on something boxed, so try it with Headings, Boxes, or Top bar on.",
  grid: "Faint lines across and down the chart, so a value can be read off it.",
  hatch: "Diagonal hatching under the sim's line in the chart.",
};

function screenGuide() {
  const at = mix => `?look=plasma${mix ? "&mix=" + mix : ""}#/run/rise-on-1`;
  const keys = Object.keys(MIXES);
  const part = (k, i) => `<li><h3>${i + 1} · ${MIXES[k]}${MIX_PICK.includes(k) ? ` <span class="kicker accent">in my pick</span>` : ""}</h3><p class="small">${MIX_WORDS[k]} <a href="${at(k)}" style="text-decoration:underline">See Plasma with only this →</a></p></li>`;
  return `<div class="guide"><span class="kicker">Prototype · round 5 · all data made up</span>
    <h1 class="display title" style="max-width:none">The web app's look, fifth pass: Plasma, with parts of Wireframe</h1>
    <p class="lead mt2">You picked Plasma and wanted to keep some of Wireframe. Plasma is now the base, and every way Wireframe differs from it is a switch of its own. Turn each one on and off on the trading sim page and tell me which stay on. Purple boxes and the purple bar are notes to you, not part of the design.</p>
    <div class="g12 mt3"><div class="c7">
      ${sechead("01", "Three places to start")}
      <ol class="list">
        <li><p class="small"><a href="${at("")}" style="text-decoration:underline"><b>Plasma alone</b></a>: every switch off. This is the look you picked in round 4.</p></li>
        <li><p class="small"><a href="${at(MIX_PICK.join(","))}" style="text-decoration:underline"><b>My pick</b></a>: Plasma with the day ruler, the numbered headings, and the chart grid. The reasons are under question 1 on the right.</p></li>
        <li><p class="small"><a href="${at(keys.join(","))}" style="text-decoration:underline"><b>Everything on</b></a>: close to Wireframe as you saw it in round 4, on Plasma's darker grey screen.</p></li>
      </ol>
      <p class="small mt1">On the page, the second row of the bar at the bottom has one button per switch. A white button is switched on. The address at the top of the browser keeps every switch, so a mix you like can be reloaded, or copied to me as it is.</p>
      <div class="mt3">${sechead("02", "The twelve switches")}</div>
      <p class="small">The ticket listed eight parts. Wireframe differed from Plasma in four more ways (the top bar, the lettering, the left edge, and the hatching apart from the grid), so those have switches too.</p>
      <ol class="list mt1">${keys.map(part).join("")}</ol>
      <div class="mt3">${sechead("03", "The first row of the bar")}</div>
      <ol class="list">
        <li><p class="small"><b>Typeface</b> is new: it changes the letters of titles and sentences. See question 5.</p></li>
        <li><p class="small"><b>Letters</b> switches between all capitals and normal case. <b>Colour</b> shows the screen in orange, amber, green, or white. <b>Chart line</b> draws the chart's lines smooth, straight, or in steps. These are questions 2 to 4, still open from round 4.</p></li>
        <li><p class="small"><b>Look</b> still reaches round 4's other four looks, kept as the record of that round. The second row shows on Plasma only.</p></li>
      </ol>
      <div class="mt3">${sechead("04", "Where to look")}</div>
      <ol class="list">
        <li><p class="small"><a href="${at(MIX_PICK.join(","))}" style="text-decoration:underline">The trading sim page</a>: the header, the chart (hover it, click it), then scroll down for the headings, the tables, and the measurements.</p></li>
        <li><p class="small">The decision trail: on the sim page, click any row of the trades table. This is where the longest text is.</p></li>
        <li><p class="small"><a href="${href("new-run")}" style="text-decoration:underline">The new sim form</a>: entry fields, and the error box (click "Free sim" to see it). <a href="${href("runs")}" style="text-decoration:underline">The list of sims</a> and <a href="${href("datasets")}" style="text-decoration:underline">datasets</a> wear the same switches.</p></li>
      </ol>
    </div><div class="c5"><div class="sticky">
      <div class="pnote" style="margin:0"><b class="t">Questions for you</b>
        <ul>
          <li><b>1. Which parts of Wireframe stay on?</b> It helps to say first what drew you to Wireframe: the boxes, the ruler, the heavy title, the two colours? Then the list of switches, by number or name. <i>My pick: 1, 2, and 11 (day ruler, headings, chart grid). Each of the three helps you find or read something: where the sim is in its 30 days, where a section starts in a very long page, what a point on the chart is worth. They also sit well with your main picture, whose chart already has tick marks like a ruler's. I would leave off the boxes round the figures (Plasma's empty screen is what makes it calm), the second colour and the heavy title (the picture is one orange and one plain typeface), and the glow (glow is what made round 2 hard to read).</i></li>
          <li><b>2. Capitals or normal case?</b> Try "Letters" on the measurements section, which has the longest sentences. <i>My pick: capitals, as in the picture. If long sentences tire you, the middle way is capitals for labels and headings and normal case for sentences.</i></li>
          <li><b>3. The chart's line: smooth or exact?</b> Plasma draws a smooth curve, as the picture does. A smooth curve rounds the corners between two measured points, so it can swing a little past the true number. Example: the account is worth $10,400 at noon and $10,200 at 18:00; a smooth curve may dip to about $10,190 on the way, a value the account never had. Straight lines between the points are exact. <i>My pick: straight.</i></li>
          <li><b>4. The colour.</b> <i>My pick: the orange of the picture.</i></li>
          <li><b>5. The typeface for titles and sentences.</b> Until now this was whatever the computer has: Arial on your Windows PC, Helvetica on a Mac, so the app would look slightly different from one computer to the next. "Typeface" in the bar tries two free ones that would ship with the app. <b>Arimo</b> was drawn to take exactly the same room as Arial, so the page you have been judging stays as it is, on every computer. <b>Inter</b> was drawn for screens and looks a little more modern. <i>My pick: Arimo, with JetBrains Mono (already in use) for the fixed-width letters. Both are under the SIL Open Font License, which lets anyone use and ship them at no cost; the licence texts are saved beside the font files. The heavy title's typeface, if you keep switch 6, is under the same licence.</i></li>
        </ul>
        <p style="margin-top:.6rem"><b>One thing I noticed:</b> the keyboard in your main picture has "Bloomberg" on its space bar. So that machine is a Bloomberg terminal of the 1980s, and Plasma, drawn from its screen, is the faithful 1980s Bloomberg look the ticket first asked for.</p>
        <p style="margin-top:.6rem"><b>Still assumed:</b> faithfulness stops at the styling. The screens, their order, and the side panel are as you left them in round 3.</p>
      </div>
    </div></div></div></div>`;
}
