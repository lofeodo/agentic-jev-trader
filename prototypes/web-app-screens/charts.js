/* PROTOTYPE. Hand-drawn SVG in the editorial-viz chart language: one subject in the accent, context in ink,
   labels beside their marks, quiet scaffolding. The real build draws these with D3. */

function niceStep(raw) { const p = Math.pow(10, Math.floor(Math.log10(raw))); const f = raw / p; return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10) * p; }
function scaleY(values, H, top, bottom, ticksWanted) {
  let lo = Math.min(...values), hi = Math.max(...values); const pad = (hi - lo) * 0.08 || 1; lo -= pad; hi += pad;
  const step = niceStep((hi - lo) / (ticksWanted || 5)); lo = Math.floor(lo / step) * step; hi = Math.ceil(hi / step) * step;
  const ticks = []; for (let v = lo; v <= hi + step / 2; v += step) ticks.push(v);
  return { y: v => top + (H - top - bottom) * (1 - (v - lo) / (hi - lo)), ticks };
}

/* series: [{ name, vals, kind: "subject" | "context" | "dashed" }]. n: how many points wide the x axis is
   (wider than the data for a run still in progress). xticks: [{ i, label }]. ref: a dashed reference level. */
function lineChart({ series, n, xticks, h = 330, ref, anno, yfmt = fmt$, label }) {
  const W = 900, m = { t: 16, r: 150, b: 30, l: 62 };
  const all = series.flatMap(s => s.vals).concat(ref ? [ref.v] : []);
  const { y, ticks } = scaleY(all, h, m.t, m.b);
  n = n || Math.max(...series.map(s => s.vals.length));
  const x = i => m.l + (W - m.l - m.r) * i / (n - 1);
  const path = vals => vals.map((v, i) => (i ? "L" : "M") + x(i).toFixed(1) + " " + y(v).toFixed(1)).join("");
  let g = "";
  ticks.forEach(t => { g += `<line x1="${m.l}" x2="${W - m.r}" y1="${y(t)}" y2="${y(t)}" stroke="var(--grid)"/><text class="tick" x="${m.l - 8}" y="${y(t) + 4}" text-anchor="end">${yfmt(t)}</text>`; });
  g += `<line x1="${m.l}" x2="${W - m.r}" y1="${h - m.b}" y2="${h - m.b}" stroke="var(--ink)"/><line x1="${m.l}" x2="${m.l}" y1="${m.t}" y2="${h - m.b}" stroke="var(--ink)"/>`;
  (xticks || []).forEach(t => { g += `<line x1="${x(t.i)}" x2="${x(t.i)}" y1="${h - m.b}" y2="${h - m.b + 5}" stroke="var(--ink)"/><text class="tick" x="${x(t.i)}" y="${h - m.b + 19}" text-anchor="middle">${t.label}</text>`; });
  if (ref) g += `<line x1="${m.l}" x2="${W - m.r}" y1="${y(ref.v)}" y2="${y(ref.v)}" stroke="var(--ink)" stroke-dasharray="4 3"/>`;
  const order = { dashed: 0, context: 1, subject: 2 };
  [...series].sort((a, b) => order[a.kind] - order[b.kind]).forEach(s => {
    const style = s.kind === "subject" ? `stroke="var(--accent)" stroke-width="2.5"` : s.kind === "dashed" ? `stroke="var(--ink)" stroke-width="1.25" stroke-dasharray="2 4"` : `stroke="var(--dot)" stroke-width="1.25"`;
    g += `<path d="${path(s.vals)}" fill="none" ${style} stroke-linejoin="miter"/>`;
  });
  /* one label per line at its last point, pushed apart so none overlap */
  const ends = series.filter(s => s.name).map(s => ({ s, x: x(s.vals.length - 1), y: y(s.vals[s.vals.length - 1]) }));
  if (ref) ends.push({ s: { name: ref.label, kind: "ref" }, x: W - m.r, y: y(ref.v) });   /* the reference level is named in the right margin */
  ends.sort((a, b) => a.y - b.y);
  for (let i = 1; i < ends.length; i++) if (ends[i].y < ends[i - 1].y + 14) ends[i].y = ends[i - 1].y + 14;
  ends.forEach(e => {
    if (e.s.kind === "subject") g += `<circle cx="${e.x}" cy="${y(e.s.vals[e.s.vals.length - 1])}" r="4.5" fill="var(--accent)" stroke="var(--paper)" stroke-width="2"/>`;
    g += `<text class="lbl ${e.s.kind === "subject" ? "subject" : ""}" x="${e.x + 9}" y="${e.y + 4}">${e.s.name}</text>`;
  });
  if (anno) g += `<text class="anno" x="${W - m.r - 10}" y="${h - m.b - 14}" text-anchor="end">${anno}</text>`;
  return `<svg viewBox="0 0 ${W} ${h}" role="img" aria-label="${label || "Line chart"}">${g}</svg>`;
}

/* Candles: a rising bar is hollow, a falling bar is filled, both in ink. The trade is the subject, in the accent.
   marks: [{ i, price, text, kind: "in" | "out" | "check" }]. stop: the stop price, drawn as a dashed level. */
function candleChart({ bars, marks = [], stop, h = 360, fmt, span, xticks, label, n }) {
  const W = 900, m = { t: 16, r: 22, b: 30, l: 70 };
  const vals = bars.flatMap(b => [b.h, b.l]).concat(stop ? [stop] : []);
  const { y, ticks } = scaleY(vals, h, m.t, m.b, 6);
  const bw = (W - m.l - m.r) / (n || bars.length), x = i => m.l + bw * (i + 0.5);
  let g = "";
  if (span) g += `<rect x="${x(span[0]) - bw / 2}" y="${m.t}" width="${bw * (span[1] - span[0] + 1)}" height="${h - m.t - m.b}" fill="var(--accentsoft)" opacity=".55"/>`;
  ticks.forEach(t => { g += `<line x1="${m.l}" x2="${W - m.r}" y1="${y(t)}" y2="${y(t)}" stroke="var(--grid)"/><text class="tick" x="${m.l - 8}" y="${y(t) + 4}" text-anchor="end">${fmt(t)}</text>`; });
  g += `<line x1="${m.l}" x2="${W - m.r}" y1="${h - m.b}" y2="${h - m.b}" stroke="var(--ink)"/><line x1="${m.l}" x2="${m.l}" y1="${m.t}" y2="${h - m.b}" stroke="var(--ink)"/>`;
  (xticks || []).forEach(t => { g += `<text class="tick" x="${x(t.i)}" y="${h - m.b + 19}" text-anchor="middle">${t.label}</text>`; });
  bars.forEach((b, i) => {
    const up = b.c >= b.o, top = y(Math.max(b.o, b.c)), bot = y(Math.min(b.o, b.c));
    g += `<line x1="${x(i)}" x2="${x(i)}" y1="${y(b.h)}" y2="${y(b.l)}" stroke="var(--ink)"/><rect x="${x(i) - bw * 0.32}" y="${top}" width="${bw * 0.64}" height="${Math.max(1, bot - top)}" fill="${up ? "var(--paper)" : "var(--ink)"}" stroke="var(--ink)"/>`;
  });
  if (stop) g += `<line x1="${m.l}" x2="${W - m.r}" y1="${y(stop)}" y2="${y(stop)}" stroke="var(--accent)" stroke-dasharray="4 3"/><text class="lbl subject" x="${W - m.r - 6}" y="${y(stop) + 15}" text-anchor="end">stop price ${fmt(stop)}</text>`;
  marks.forEach(k => {
    if (k.kind === "check") { g += `<rect x="${x(k.i) - 3}" y="${h - m.b - 12}" width="6" height="6" fill="var(--paper)" stroke="var(--dot)"><title>${k.text}</title></rect>`; return; }
    const above = k.kind === "out";
    g += `<circle cx="${x(k.i)}" cy="${y(k.price)}" r="6" fill="var(--accent)" stroke="var(--paper)" stroke-width="2"/><text class="lbl subject" x="${x(k.i) + (above ? 10 : -10)}" y="${y(k.price) + (above ? -10 : 18)}" text-anchor="${above ? "start" : "end"}">${k.text}</text>`;
  });
  return `<svg viewBox="0 0 ${W} ${h}" role="img" aria-label="${label || "Candle chart"}">${g}</svg>`;
}

function spark(vals) {
  const lo = Math.min(...vals), hi = Math.max(...vals), x = i => 2 + 100 * i / (vals.length - 1), y = v => 21 - 18 * (v - lo) / (hi - lo || 1);
  return `<svg width="104" height="24" viewBox="0 0 104 24" aria-hidden="true" style="vertical-align:-5px"><path d="${vals.map((v, i) => (i ? "L" : "M") + x(i).toFixed(1) + " " + y(v).toFixed(1)).join("")}" fill="none" stroke="var(--ink)" stroke-width="1.25"/><circle cx="${x(vals.length - 1)}" cy="${y(vals[vals.length - 1])}" r="2.5" fill="var(--accent)"/></svg>`;
}

/* Ranked bars: values written at the bar ends, no axis. A loss is a dotted bar; the sign carries the meaning, not a colour. */
function rankedBars(rows, fmt) {
  const top = Math.max(...rows.map(r => Math.abs(r.v)));
  return rows.map(r => `<div class="rbar ${r.v < 0 ? "neg" : ""} ${r.subject ? "subject" : ""}"><span class="nm">${r.name}</span><span class="b"><i style="width:${(80 * Math.abs(r.v) / top).toFixed(1)}%"></i>${fmt(r.v)}${r.note ? ` <span class="muted">${r.note}</span>` : ""}</span></div>`).join("");
}
function figure(no, title, legend, plot, caption) {
  return `<figure class="figure"><div class="fighead"><span class="kicker accent" style="font-weight:600">Fig. ${no}</span><h3>${title}</h3><span class="kicker legend">${legend || ""}</span></div><div class="plot">${plot}</div><figcaption>${caption}</figcaption></figure>`;
}
