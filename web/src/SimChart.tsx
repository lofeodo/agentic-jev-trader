// The sim page's chart (spec appendix 7, sections 5 and 12): account value over time for the sim,
// holding the five assets, and the other sims over the same days. Straight lines between points
// (a smooth curve could show values the account never had), a faint grid, hatching under the
// sim's line, and a small tick along the bottom for each trade opened: clicking one opens the
// decision trail of the decision that opened it.
import { bisector, line as d3line, area as d3area, scaleLinear } from "d3";
import { useRef, useState } from "react";

import type { ChartLine, TradeTick } from "./api/client";
import type { OpenTrail } from "./pieces";
import { dayAndTime, dollars, shortDay, signedDollars, stepTime } from "./format";

const W = 1400;
const H = 500;
const M = { t: 20, r: 236, b: 52, l: 96 };
const X0 = M.l;
// A line's name at its end takes about this much width per letter (letter-spaced capitals).
const LABEL_CHAR_W = 10.5;
const Y0 = M.t;
const Y1 = H - M.b;
const STEPS_PER_DAY = 96;

type Point = ChartLine["points"][number];
const byStep = bisector((p: Point) => p.step).right;

// The line's value at a step: its last point at or before it.
function valueAt(points: Point[], step: number): number | null {
  const i = byStep(points, step);
  return i === 0 ? null : points[i - 1].value;
}

// Holding stores many steps at once and can be behind: compared only once it reached the step.
function reachedValueAt(points: Point[], step: number): number | null {
  const last = points[points.length - 1];
  return last && last.step >= step ? valueAt(points, step) : null;
}

// A line's name and value, written at its end.
function endLabel(line: ChartLine, value: number) {
  const name = line.role === "sim" ? "This sim" : line.role === "holding" ? "Holding" : line.label;
  return `${name} ${dollars(value)}`;
}

export type ChartProps = {
  lines: ChartLine[];
  ticks: TradeTick[];
  firstStep: number;
  lastStep: number;
  startingValue: number;
  stepsStartAt: string | null;
  windowSteps: number;
  onPick: (step: number) => void;
  onOpenTrail: OpenTrail;
};

type Hover = { step: number; clientX: number; clientY: number };

export function SimChart(props: ChartProps) {
  const { lines, ticks, firstStep, lastStep, startingValue, stepsStartAt, windowSteps, onPick, onOpenTrail } =
    props;
  const svgRef = useRef<SVGSVGElement>(null);
  const [hover, setHover] = useState<Hover | null>(null);

  const values = lines.flatMap((l) => l.points.map((p) => p.value)).concat(startingValue);
  const low = Math.min(...values);
  const high = Math.max(...values);
  const pad = Math.max((high - low) * 0.08, startingValue * 0.002);
  // Room on the right for each line's name at its end: at least M.r, more for a long name
  // ("With memory / GLM Flash $9,300").
  const longest = Math.max(0, ...lines.map((l) => endLabel(l, high).length));
  const X1 = W - Math.max(M.r, 14 + longest * LABEL_CHAR_W + 12);
  const y = scaleLinear().domain([low - pad, high + pad]).nice(6).range([Y1, Y0]);
  const x = scaleLinear().domain([firstStep - 1, lastStep]).range([X0, X1]);

  const path = d3line<Point>()
    .x((p) => x(p.step))
    .y((p) => y(p.value));
  const hatch = d3area<Point>()
    .x((p) => x(p.step))
    .y0(Y1)
    .y1((p) => y(p.value));

  const sim = lines.find((l) => l.role === "sim");
  const holding = lines.find((l) => l.role === "holding");
  const order = { "same days": 0, holding: 1, sim: 2 } as Record<string, number>;
  const drawn = [...lines].sort((a, b) => (order[a.role] ?? 0) - (order[b.role] ?? 0));
  // A measurement sim has two partners (its repeat's other sims): the second is dash-dotted.
  const partners = lines.filter((l) => l.role === "same days");

  // Midnights UTC: step 96 ends the first day. Labelled every day, or every 5 or 30 on long sims.
  const days = Math.ceil((lastStep - firstStep + 1) / STEPS_PER_DAY);
  const every = days > 60 ? 30 : days > 10 ? 5 : 1;
  const midnights: number[] = [];
  for (let s = Math.ceil((firstStep - 1) / STEPS_PER_DAY) * STEPS_PER_DAY; s <= lastStep; s += STEPS_PER_DAY) {
    midnights.push(s);
  }

  // Each line's name at its end, pushed apart so they never overlap.
  const ends = lines
    .filter((l) => l.points.length > 0)
    .map((l) => {
      const last = l.points[l.points.length - 1];
      return { line: l, y: y(last.value), value: last.value };
    })
    .sort((a, b) => a.y - b.y);
  for (let i = 1; i < ends.length; i++) {
    if (ends[i].y < ends[i - 1].y + 19) ends[i].y = ends[i - 1].y + 19;
  }

  function stepAt(clientX: number) {
    const box = svgRef.current!.getBoundingClientRect();
    const vx = ((clientX - box.left) * W) / box.width;
    return Math.round(Math.min(lastStep, Math.max(firstStep, x.invert(vx))));
  }

  const hoverValue = hover && sim ? valueAt(sim.points, hover.step) : null;

  return (
    <div className="relative border-[1.5px] border-rule px-2 pt-3 pb-1">
      <svg
        ref={svgRef}
        viewBox={`0 0 ${W} ${H}`}
        className="block w-full"
        role="img"
        aria-label="Line chart of account value over the sim, against holding the five assets"
      >
        <defs>
          <pattern id="hatch" width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <line x1="0" y1="0" x2="0" y2="7" stroke="var(--color-rule)" strokeWidth="1" />
          </pattern>
        </defs>

        {y.ticks(6).map((t) => (
          <g key={t}>
            {y(t) > Y0 + 1 && y(t) < Y1 - 1 && <line className="stroke-grid" x1={X0} x2={X1} y1={y(t)} y2={y(t)} />}
            <line className="stroke-rule" x1={X0} x2={X0 + 10} y1={y(t)} y2={y(t)} />
            <line className="stroke-rule" x1={X1 - 10} x2={X1} y1={y(t)} y2={y(t)} />
            <text className="axis-number" x={X0 - 12} y={y(t) + 5} textAnchor="end">
              {dollars(t)}
            </text>
          </g>
        ))}

        {midnights.map((s) => {
          const labelled = (s / STEPS_PER_DAY) % every === 0;
          return (
            <g key={s}>
              {labelled && s > firstStep - 1 && s < lastStep && (
                <line className="stroke-grid" x1={x(s)} x2={x(s)} y1={Y0} y2={Y1} />
              )}
              <line className="stroke-rule" x1={x(s)} x2={x(s)} y1={Y1} y2={Y1 + (labelled ? 8 : 4)} />
              {labelled && stepsStartAt && (
                <text className="axis-number" x={x(s)} y={Y1 + 27} textAnchor="middle">
                  {shortDay(stepTime(stepsStartAt, s + 1))}
                </text>
              )}
            </g>
          );
        })}

        <rect className="stroke-rule" x={X0} y={Y0} width={X1 - X0} height={Y1 - Y0} fill="none" strokeWidth="1.5" />
        <line className="stroke-dim" x1={X0} x2={X1} y1={y(startingValue)} y2={y(startingValue)} strokeDasharray="2 5" />

        {drawn.map((l) =>
          l.points.length === 0 ? null : (
            <g key={l.sim_id}>
              {l.role === "sim" && <path d={hatch(l.points) ?? ""} fill="url(#hatch)" opacity={0.55} />}
              <path
                d={path(l.points) ?? ""}
                fill="none"
                className={l.role === "sim" ? "stroke-amber" : l.role === "holding" ? "stroke-pale" : "stroke-dim"}
                strokeWidth={l.role === "sim" ? 2.5 : 1.5}
                strokeDasharray={
                  l.role === "holding" ? "7 5" : l.role === "same days" && partners.indexOf(l) > 0 ? "10 4 2 4" : undefined
                }
                opacity={l.role === "same days" ? 0.8 : 1}
              />
            </g>
          ),
        )}

        {ticks.map((t) => (
          <line
            key={t.position}
            className="stroke-amber"
            x1={x(t.opened_step)}
            x2={x(t.opened_step)}
            y1={Y1 - 13}
            y2={Y1 - 2}
            strokeWidth="1.5"
          >
            <title>{`${t.asset.name}: ${t.direction} opened`}</title>
          </line>
        ))}

        {ends.map((e) => (
          <g key={e.line.sim_id}>
            {e.line.role === "sim" && (
              <circle className="fill-amber" cx={x(e.line.points[e.line.points.length - 1].step)} cy={y(e.value)} r="5" />
            )}
            <text
              className={`chart-label ${e.line.role === "sim" ? "fill-pale" : e.line.role === "holding" ? "fill-amber" : "fill-dim"}`}
              x={X1 + 14}
              y={e.y + 5}
            >
              {endLabel(e.line, e.value)}
            </text>
          </g>
        ))}

        {hover && hoverValue !== null && (
          <g pointerEvents="none">
            <line className="stroke-pale" x1={x(hover.step)} x2={x(hover.step)} y1={Y0} y2={Y1} />
            <circle className="fill-amber" cx={x(hover.step)} cy={y(hoverValue)} r="6" />
          </g>
        )}

        <rect
          x={X0}
          y={Y0}
          width={X1 - X0}
          height={Y1 - Y0}
          fill="transparent"
          className="cursor-crosshair"
          onPointerMove={(e) => setHover({ step: stepAt(e.clientX), clientX: e.clientX, clientY: e.clientY })}
          onPointerLeave={() => setHover(null)}
          onClick={(e) => {
            setHover(null);
            onPick(stepAt(e.clientX));
          }}
        />

        {/* Over the chart's click area, so a tick's click opens its trail, not the moment. */}
        {ticks.map((t) => {
            const decision = t.decision;
            if (decision === null) return null;
            return (
              <rect
                key={`hit-${t.position}`}
                x={x(t.opened_step) - 6}
                y={Y1 - 18}
                width={12}
                height={18}
                fill="transparent"
                className="cursor-pointer"
                onClick={() => {
                  setHover(null);
                  onOpenTrail(decision);
                }}
              >
                <title>{`${t.asset.name}: ${t.direction} opened. Click for how it was decided.`}</title>
              </rect>
            );
          })}
      </svg>

      {hover && sim && hoverValue !== null && (
        <Tooltip
          hover={hover}
          value={hoverValue}
          sim={sim}
          holding={holding ? reachedValueAt(holding.points, hover.step) : null}
          ticks={ticks}
          startingValue={startingValue}
          stepsStartAt={stepsStartAt}
          windowSteps={windowSteps}
        />
      )}
    </div>
  );
}

function Tooltip(props: {
  hover: Hover;
  value: number;
  sim: ChartLine;
  holding: number | null;
  ticks: TradeTick[];
  startingValue: number;
  stepsStartAt: string | null;
  windowSteps: number;
}) {
  const { hover, value, sim, holding, ticks, startingValue, stepsStartAt, windowSteps } = props;
  const step = hover.step;
  const lastMidnight = Math.floor((step - 1) / STEPS_PER_DAY) * STEPS_PER_DAY;
  const atMidnight = valueAt(sim.points, lastMidnight) ?? startingValue;
  const open = ticks.filter((t) => t.opened_step <= step && (t.closed_step === null || t.closed_step > step));
  const near = (s: number | null) => s !== null && Math.abs(s - step) <= windowSteps;
  const nearby = ticks.filter((t) => near(t.opened_step) || near(t.closed_step));
  const gap = holding === null ? null : value - holding;

  const left = hover.clientX + 18 + 300 > window.innerWidth ? hover.clientX - 318 : hover.clientX + 18;
  const rows: [string, string][] = [
    ["Account value", dollars(value)],
    ["Holding the five assets", holding === null ? "--" : dollars(holding)],
    [
      gap !== null && gap < 0 ? "Behind holding by" : "Ahead of holding by",
      gap === null ? "--" : dollars(Math.abs(gap)),
    ],
    ["Since midnight UTC", signedDollars(value - atMidnight)],
    ["Since the start", signedDollars(value - startingValue)],
    ["Positions open then", String(open.length)],
    [`Trades opened or closed within ${(windowSteps * 15) / 60} h`, String(nearby.length)],
  ];

  return (
    <div
      className="pointer-events-none fixed z-20 w-[300px] border-[1.5px] border-rule bg-screen font-mono text-[13.5px] tracking-wider"
      style={{ left, top: Math.max(8, Math.min(window.innerHeight - 260, hover.clientY + 16)) }}
    >
      <div className="bg-amber px-[1.5ch] py-1 text-screen">
        {stepsStartAt ? dayAndTime(stepTime(stepsStartAt, step)) : `Step ${step}`}
      </div>
      <dl className="grid grid-cols-[1fr_auto] gap-x-[2ch] px-[1.5ch] py-2">
        {rows.map(([name, figure]) => (
          <div key={name} className="contents">
            <dt className="text-dim">{name}</dt>
            <dd className="text-right text-pale">{figure}</dd>
          </div>
        ))}
      </dl>
      <div className="border-t border-rule px-[1.5ch] py-1 text-dim">Step {step} / click to open this moment</div>
    </div>
  );
}
