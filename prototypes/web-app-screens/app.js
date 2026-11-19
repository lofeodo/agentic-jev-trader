/* PROTOTYPE. Which screen is showing (from the address after #), the switcher bar, and a pretend live tick. */

function parseHash() {
  const h = location.hash.slice(1) || "/", cut = h.indexOf("?");
  return { parts: (cut < 0 ? h : h.slice(0, cut)).split("/").filter(Boolean), q: new URLSearchParams(cut < 0 ? "" : h.slice(cut + 1)) };
}
const onRunPage = () => parseHash().parts[0] === "run";
function cycleOf(list, now, by) { return list[(list.indexOf(now) + by + list.length) % list.length]; }
function cycleLook(by) { LOOK = cycleOf(Object.keys(LOOKS), LOOK, by); draw.keepScroll = true; draw(); }
function cycleFlow(by) { FLOW = cycleOf(Object.keys(FLOWS), FLOW, by); drawPanel(); drawBar(); }
function cycleWord() { WORD = (WORD + 1) % WORDS.length; draw.keepScroll = true; draw(); }

function drawBar() {
  const exchangeOpen = PANEL && PANEL.kind === "exchange", sep = `<span class="sep">|</span>`;
  document.getElementById("bar").innerHTML = `<b>PROTOTYPE</b>${sep}<button onclick="location.hash='#/'">Guide and questions</button>`
    + (onRunPage() ? `${sep}<span>Look</span><button onclick="cycleLook(-1)" aria-label="Previous look">←</button><b>${LOOKS[LOOK]}</b><button onclick="cycleLook(1)" aria-label="Next look">→</button>` : "")
    + `${sep}<span>Word for "run"</span><button onclick="cycleWord()">${WORDS[WORD].full}</button>`
    + `${sep}<button onclick="document.body.classList.toggle('nonotes')">Notes on/off</button>`;
}
function draw() {
  let { parts, q } = parseHash(), page = parts[0] || "guide";
  /* an address that names an exchange opens the trade's page with the side panel over it */
  if (page === "decision") { page = "trade"; if (!PANEL) PANEL = { kind: "exchange", tid: parts[1] }; }
  const screen = page === "runs" ? screenRuns() : page === "new-run" ? screenNewRun() : page === "run" ? screenRunV2(parts[1], q) : page === "trade" ? screenTrade(parts[1])
    : page === "comparison" ? screenComparison() : page === "datasets" ? screenDatasets() : page === "dataset" ? screenDataset()
    : page === "playbook" ? screenPlaybook() : page === "spending" ? screenSpending() : screenGuide();
  const active = { run: "runs", "new-run": "runs", trade: "runs", dataset: "datasets" }[page] || page;
  /* the three terminal looks are tried on the run page only */
  document.documentElement.dataset.look = page === "run" ? LOOK : "paper";
  if (page === "run" && VT_LOOKS.includes(LOOK)) document.documentElement.dataset.vt = "1"; else delete document.documentElement.dataset.vt;
  const app = document.getElementById("app");
  app.innerHTML = `<main>${masthead(active)}${screen}</main>`;
  if (page === "run") wireChart();
  applyWord(app);
  drawPanel(); drawBar();
  if (!draw.keepScroll) window.scrollTo(0, 0);
  draw.keepScroll = false;
}
window.addEventListener("hashchange", () => { if (parseHash().parts[0] !== "decision") { PANEL = null; PANEL_BACK = []; } draw(); });
window.addEventListener("keydown", e => {
  if (e.key === "Escape" && PANEL) { closePanel(); return; }
  if (e.target.matches("input, textarea, select, [contenteditable]")) return;
  const by = e.key === "ArrowLeft" ? -1 : e.key === "ArrowRight" ? 1 : 0; if (!by) return;
  if (onRunPage()) cycleLook(by);
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
