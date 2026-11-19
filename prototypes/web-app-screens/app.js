/* PROTOTYPE. Which screen is showing (from the address after #), the switcher bar, and a pretend live tick. */

const VARIANTS = { A: "tabs", B: "one long report", C: "day by day" };
function parseHash() {
  const h = location.hash.slice(1) || "/", cut = h.indexOf("?");
  return { parts: (cut < 0 ? h : h.slice(0, cut)).split("/").filter(Boolean), q: new URLSearchParams(cut < 0 ? "" : h.slice(cut + 1)) };
}
function setVariant(v) {
  const { parts, q } = parseHash(); q.set("variant", v); q.delete("tab"); q.delete("day"); q.delete("show");
  location.hash = "#/" + parts.join("/") + "?" + q;
}
function cycle(by) { const keys = Object.keys(VARIANTS); setVariant(keys[(keys.indexOf(V) + by + keys.length) % keys.length]); }

function draw() {
  const { parts, q } = parseHash(), page = parts[0] || "guide";
  if (VARIANTS[q.get("variant")]) V = q.get("variant");
  const screen = page === "runs" ? screenRuns() : page === "new-run" ? screenNewRun() : page === "run" ? screenRun(parts[1], q) : page === "trade" ? screenTrade(parts[1])
    : page === "decision" ? screenDecision(parts[1]) : page === "comparison" ? screenComparison() : page === "datasets" ? screenDatasets() : page === "dataset" ? screenDataset()
    : page === "playbook" ? screenPlaybook() : page === "spending" ? screenSpending() : screenGuide();
  const active = { run: "runs", "new-run": "runs", trade: "runs", decision: "runs", dataset: "datasets" }[page] || page;
  document.getElementById("app").innerHTML = `<main>${masthead(active)}${screen}</main>`;
  const onRun = page === "run";
  document.getElementById("bar").innerHTML = `<b>PROTOTYPE</b><span class="sep">|</span><button onclick="location.hash='#/'">Guide and questions</button>`
    + (onRun ? `<span class="sep">|</span><span>Run page layout</span><button onclick="cycle(-1)" aria-label="Previous layout">←</button><b>${V} (${VARIANTS[V]})</b><button onclick="cycle(1)" aria-label="Next layout">→</button>` : "")
    + `<span class="sep">|</span><button onclick="document.body.classList.toggle('nonotes')">Notes on/off</button>`;
  if (!draw.keepScroll) window.scrollTo(0, 0);
  draw.keepScroll = false;
}
window.addEventListener("hashchange", draw);
window.addEventListener("keydown", e => {
  if (parseHash().parts[0] !== "run" || e.target.matches("input, textarea, select, [contenteditable]")) return;
  if (e.key === "ArrowLeft") cycle(-1); else if (e.key === "ArrowRight") cycle(1);
});
/* Clicking a filter or a day should not jump back to the top of the page. */
document.addEventListener("click", e => { const a = e.target.closest("a.tog, a.day"); if (a) draw.keepScroll = true; });

/* A pretend live run: every 5 seconds the step and the replayed time move on, in place. Nothing else is animated. */
let ticks = 0, sinceTick = 0;
setInterval(() => {
  const ago = document.getElementById("live-ago"); if (!ago) return;
  sinceTick = (sinceTick + 1) % 5;
  if (sinceTick === 0) {
    ticks++;
    const step = document.getElementById("live-step"), clock = document.getElementById("live-clock");
    step.textContent = (parseInt(step.textContent.replace(/,/g, ""), 10) + 2).toLocaleString("en-US");
    const [h, m] = clock.textContent.split(":").map(Number), t = (h * 60 + m + 30) % 1440;
    clock.textContent = hhmm(t);
  }
  ago.textContent = sinceTick === 0 ? "updated just now" : "updated " + sinceTick + " s ago";
}, 1000);

draw();
