/* PROTOTYPE. Which screen is showing (from the address after #), the switcher bar, and a pretend live tick. */

function parseHash() {
  const h = location.hash.slice(1) || "/", cut = h.indexOf("?");
  return { parts: (cut < 0 ? h : h.slice(0, cut)).split("/").filter(Boolean), q: new URLSearchParams(cut < 0 ? "" : h.slice(cut + 1)) };
}
const onGuide = () => !parseHash().parts[0];
function cycleOf(list, now, by) { return list[(list.indexOf(now) + by + list.length) % list.length]; }
/* The look, the letters, and the colour are kept in the address (?look=plasma&caps=1&tube=green), so a view can be reloaded or shared. */
(() => { const s = new URLSearchParams(location.search); if (LOOKS[s.get("look")]) LOOK = s.get("look"); if (s.has("caps")) CAPS = +s.get("caps") ? 1 : 0; if (TUBES[s.get("tube")]) TUBE = s.get("tube"); if (CURVES[s.get("line")]) CURVE = s.get("line");
  (s.get("mix") || "").split(",").forEach(k => { if (MIXES[k]) MIX.add(k); }); if (FACES[s.get("face")]) FACE = s.get("face"); if (MARKS_WORDS[s.get("marks")]) MARKS = s.get("marks");
  /* an address with no switches at all opens the look the developer chose after round 5 */
  if (!location.search) { MIX = new Set(MIX_YOURS); CURVE = "line"; FACE = "arimo"; } })();
function saveLook() { const s = new URLSearchParams(); s.set("look", LOOK); if (CAPS != null) s.set("caps", CAPS); if (TUBE) s.set("tube", TUBE); if (CURVE) s.set("line", CURVE); s.set("mix", mixList() || "none"); if (FACE) s.set("face", FACE); if (MARKS) s.set("marks", MARKS);
  try { history.replaceState(null, "", "?" + s.toString().replace(/%2C/g, ",") + location.hash); } catch (e) { /* opened as a file in a browser that refuses: the view still switches */ } }
/* round 5: the Wireframe parts, each switched on its own, always listed in the order the bar shows them */
const mixList = () => Object.keys(MIXES).filter(k => MIX.has(k)).join(",");
function redrawInPlace() { saveLook(); draw.keepScroll = true; draw(); }
function toggleMix(k) { if (MIX.has(k)) MIX.delete(k); else MIX.add(k); redrawInPlace(); }
function setMix(keys) { MIX = new Set(keys); redrawInPlace(); }
function cycleMarks() { MARKS = cycleOf(Object.keys(MARKS_WORDS), MARKS, 1); redrawInPlace(); }
function cycleFace() { FACE = cycleOf(Object.keys(FACES), FACE, 1); redrawInPlace(); }
const capsNow = () => (CAPS == null ? CAPS_DEFAULT[LOOK] : CAPS);
function cycleLook(by) { LOOK = cycleOf(Object.keys(LOOKS), LOOK, by); CAPS = null; saveLook(); draw.keepScroll = true; draw(); }
function toggleCaps() { CAPS = capsNow() ? 0 : 1; saveLook(); draw.keepScroll = true; draw(); }
function cycleCurve() { CURVE = cycleOf(Object.keys(CURVES), CURVE, 1); saveLook(); draw.keepScroll = true; draw(); }
function cycleTube() { TUBE = cycleOf(Object.keys(TUBES), TUBE, 1); saveLook(); draw.keepScroll = true; draw(); }
function cycleFlow(by) { FLOW = cycleOf(Object.keys(FLOWS), FLOW, by); drawPanel(); drawBar(); }
function cycleWord() { WORD = (WORD + 1) % WORDS.length; draw.keepScroll = true; draw(); }

function drawBar() {
  const sep = `<span class="sep">|</span>`;
  const plasma = !onGuide() && LOOK === "plasma", same = keys => keys.length === MIX.size && keys.every(k => MIX.has(k));
  const preset = (label, keys) => `<button class="${same(keys) ? "on" : ""}" onclick='setMix(${JSON.stringify(keys)})'>${label}</button>`;
  document.getElementById("bar").innerHTML = `<div class="row"><b>PROTOTYPE</b>${sep}<button onclick="location.hash='#/'">Guide and questions</button>`
    + (onGuide() ? `${sep}<button onclick="location.hash='${runHref("rise-on-1")}'">Open the trading sim page</button>`
      : `${sep}<span>Look</span><button onclick="cycleLook(-1)" aria-label="Previous look">←</button><b>${LOOKS[LOOK]}</b><button onclick="cycleLook(1)" aria-label="Next look">→</button>`
      + `${sep}<span>Letters</span><button onclick="toggleCaps()">${capsNow() ? "ALL CAPITALS" : "Normal case"}</button>`
      + `${sep}<span>Colour</span><button onclick="cycleTube()">${TUBES[TUBE]}</button>`
      + (parseHash().parts[0] === "run" ? `${sep}<span>Chart line</span><button onclick="cycleCurve()">${CURVES[CURVE]}</button>` : "")
      + (plasma && parseHash().parts[0] === "run" ? `${sep}<span>Trade marks</span><button class="${MARKS ? "on" : ""}" onclick="cycleMarks()">${MARKS_WORDS[MARKS]}</button>` : "")
      + (plasma ? `${sep}<span>Typeface</span><button onclick="cycleFace()">${FACES[FACE]}</button>` : ""))
    + `${sep}<button onclick="document.body.classList.toggle('nonotes')">Notes on/off</button></div>`
    /* round 5: a second row, on Plasma only. One button per Wireframe part; a lit button is switched on. */
    + (plasma ? `<div class="row mixrow"><span>Add from Wireframe</span>${Object.keys(MIXES).map((k, i) => `<button class="${MIX.has(k) ? "on" : ""}" aria-pressed="${MIX.has(k)}" onclick="toggleMix('${k}')">${i + 1} ${MIXES[k]}</button>`).join("")}`
      + `${sep}${preset("None", [])}${preset("Your pick", MIX_YOURS)}${preset("All", Object.keys(MIXES))}</div>` : "");
}
function draw() {
  let { parts, q } = parseHash(), page = parts[0] || "guide";
  /* an address that names an exchange opens the trade's page with the side panel over it */
  if (page === "decision") { page = "trade"; if (!PANEL) PANEL = { kind: "exchange", tid: parts[1] }; }
  const screen = page === "runs" ? screenRuns() : page === "new-run" ? screenNewRun() : page === "run" ? screenRunV2(parts[1], q) : page === "trade" ? screenTrade(parts[1])
    : page === "comparison" ? screenComparison() : page === "datasets" ? screenDatasets() : page === "dataset" ? screenDataset()
    : page === "playbook" ? screenPlaybook() : page === "spending" ? screenSpending() : screenGuide();
  const active = { run: "runs", "new-run": "runs", trade: "runs", dataset: "datasets" }[page] || page;
  /* round 4: every screen wears the look, except the guide, which is notes to the developer */
  const de = document.documentElement, guide = page === "guide";
  de.dataset.look = guide ? "paper" : LOOK;
  if (guide) { delete de.dataset.r4; delete de.dataset.caps; delete de.dataset.tube; }
  else { de.dataset.r4 = "1"; de.dataset.caps = capsNow(); if (TUBE) de.dataset.tube = TUBE; else delete de.dataset.tube; }
  /* round 5: the Wireframe parts switched on, and the typeface, apply to Plasma only */
  if (!guide && LOOK === "plasma" && MIX.size) de.dataset.mix = mixList().replace(/,/g, " "); else delete de.dataset.mix;
  if (!guide && LOOK === "plasma" && FACE) de.dataset.face = FACE; else delete de.dataset.face;
  const app = document.getElementById("app");
  app.innerHTML = `<main>${masthead(active)}${guide ? "" : cmdLine(page)}${screen}</main>`;
  if (page === "run") wireChart();
  applyWord(app); markSigns(app);
  drawPanel(); drawBar();
  if (!draw.keepScroll) window.scrollTo(0, 0);
  draw.keepScroll = false;
}
window.addEventListener("hashchange", () => { if (parseHash().parts[0] !== "decision") { PANEL = null; PANEL_BACK = []; } draw(); });
window.addEventListener("keydown", e => {
  if (e.key === "Escape" && PANEL) { closePanel(); return; }
  if (e.target.matches("input, textarea, select, [contenteditable]")) return;
  const by = e.key === "ArrowLeft" ? -1 : e.key === "ArrowRight" ? 1 : 0; if (!by) return;
  if (!onGuide()) cycleLook(by);
});
document.addEventListener("click", e => {
  /* any link to an exchange opens the side panel in place */
  const link = e.target.closest('a[href^="#/decision/"]');
  if (link) { e.preventDefault(); openPanel({ kind: "exchange", tid: link.getAttribute("href").split("/")[2].split("?")[0] }); return; }
  /* clicking a filter should not jump back to the top of the page */
  if (e.target.closest("a.tog")) draw.keepScroll = true;
});

/* A pretend live run: every 5 seconds the step and the replayed time move on, in place. Nothing else is animated. */
let sinceTick = 0;
setInterval(() => {
  const ago = document.getElementById("live-ago"); if (!ago) return;
  sinceTick = (sinceTick + 1) % 5;
  if (sinceTick === 0) {
    const step = document.getElementById("live-step"), clock = document.getElementById("live-clock");
    step.textContent = (parseInt(step.textContent.replace(/,/g, ""), 10) + 2).toLocaleString("en-US");
    const [h, m] = clock.textContent.split(":").map(Number);
    clock.textContent = hhmm((h * 60 + m + 30) % 1440);
  }
  ago.textContent = sinceTick === 0 ? "updated just now" : "updated " + sinceTick + " s ago";
}, 1000);

draw();
