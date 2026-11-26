// The Trade page's price chart (spec appendix 7, section 7): the asset's 15-minute closes around
// the trade, drawn as the other charts are (straight lines, faint grid, hatching under the line,
// ticks on the inside of the frame). The entry and the close are marked on the line, the stop
// price is a dashed level while the trade was open, and each position screen or review is a tick
// along the bottom: a tall one for a review, a short one for a screen that said no. Clicking a
// tick opens its decision trail. Hovering reads out one bar.
import { area as d3area, bisector, line as d3line, scaleLinear } from "d3";
import { useRef, useState } from "react";

import type { TradePage } from "./api/client";
import type { OpenTrail } from "./pieces";
import { dayAndTime, fromApi, price, shortDay, timeOfDay } from "./format";

const W = 1400;
const H = 360;
const M = { t: 16, r: 24, b: 60, l: 110 };
const X0 = M.l;
const X1 = W - M.r;
const Y0 = M.t;
const Y1 = H - M.b;

type Point = { step: number; at: Date | null; value: number; rescaled: number };
const byStep = bisector((p: Point) => p.step).center;

// Real prices lead; a chart whose asset has no key draws the prices the agent saw.
export function TradeChart({ page, onOpenTrail }: { page: TradePage; onOpenTrail: OpenTrail }) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [hover, setHover] = useState<Point | null>(null);
  const real = page.bars.length > 0 && page.bars.every((b) => b.close.real !== null);
  const points: Point[] = page.bars.map((b) => ({
    step: b.step,
    at: b.at ? fromApi(b.at) : null,
    value: real ? b.close.real! : b.close.rescaled,
    rescaled: b.close.rescaled,
  }));
  if (points.length === 0) return <p className="font-mono text-dim">No prices stored around this trade.</p>;

  const valueOf = (p: { real: number | null; rescaled: number }) => (real ? p.real : p.rescaled);
  const stop = page.stop_price ? valueOf(page.stop_price) : null;
  const priced = page.marks.filter((m) => m.price && valueOf(m.price) !== null);
  const levels = [...points.map((p) => p.value), ...priced.map((m) => valueOf(m.price!)!), ...(stop === null ? [] : [stop])];
  const low = Math.min(...levels);
  const high = Math.max(...levels);
  const pad = Math.max((high - low) * 0.08, high * 0.002);
  const y = scaleLinear().domain([low - pad, high + pad]).nice(5).range([Y1, Y0]);
  const first = points[0].step;
  const last = points[points.length - 1].step;
  const x = scaleLinear().domain([first, Math.max(last, first + 1)]).range([X0, X1]);
  const path = d3line<Point>()
    .x((p) => x(p.step))
    .y((p) => y(p.value));
  const hatch = d3area<Point>()
    .x((p) => x(p.step))
    .y0(Y1)
    .y1((p) => y(p.value));

  const t = page.trade;
  const opened = t.opened_step ?? t.decided_step;
  const closed = t.closed_step ?? last;
  const atOf = (step: number) => points[byStep(points, step)];
  const xTicks = x.ticks(8).filter((s) => Number.isInteger(s));

  function pick(clientX: number) {
    const box = svgRef.current!.getBoundingClientRect();
    setHover(atOf(x.invert(((clientX - box.left) * W) / box.width)));
  }

  return (
    <div className="border-[1.5px] border-rule px-2 pt-3 pb-1">
      <svg
        ref={svgRef}
        viewBox={`0 0 ${W} ${H}`}
        className="block w-full"
        role="img"
        aria-label={`Price of ${t.asset.name} around the trade`}
        onMouseMove={(e) => pick(e.clientX)}
        onMouseLeave={() => setHover(null)}
      >
        <defs>
          <pattern id="trade-hatch" width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <line x1="0" y1="0" x2="0" y2="7" stroke="var(--color-rule)" strokeWidth="1" />
          </pattern>
        </defs>
        {/* The time the trade was open, shaded faintly. */}
        <rect x={x(opened)} y={Y0} width={Math.max(0, x(closed) - x(opened))} height={Y1 - Y0} className="fill-grid" opacity={0.35} />
        {y.ticks(5).map((v) => (
          <g key={v}>
            {y(v) > Y0 + 1 && y(v) < Y1 - 1 && <line className="stroke-grid" x1={X0} x2={X1} y1={y(v)} y2={y(v)} />}
            <line className="stroke-rule" x1={X0} x2={X0 + 10} y1={y(v)} y2={y(v)} />
            <text className="axis-number" x={X0 - 12} y={y(v) + 5} textAnchor="end">
              {real ? price(v) : v}
            </text>
          </g>
        ))}
        {xTicks.map((s) => {
          const p = atOf(s);
          return (
            <g key={s}>
              <line className="stroke-grid" x1={x(s)} x2={x(s)} y1={Y0} y2={Y1} />
              <text className="axis-number" x={x(s)} y={Y1 + 44} textAnchor="middle">
                {p.at ? `${shortDay(p.at)} ${timeOfDay(p.at)}` : `step ${s}`}
              </text>
            </g>
          );
        })}
        <path d={hatch(points) ?? undefined} fill="url(#trade-hatch)" opacity={0.45} />
        <path d={path(points) ?? undefined} fill="none" className="stroke-amber" strokeWidth={1.6} />
        {stop !== null && (
          <g>
            <line className="stroke-pale" x1={x(opened)} x2={x(closed)} y1={y(stop)} y2={y(stop)} strokeDasharray="8 5" strokeWidth={1.4} />
            <text className="chart-label fill-pale" x={(x(opened) + x(closed)) / 2} y={y(stop) - 8} textAnchor="middle">
              stop price
            </text>
          </g>
        )}
        {page.marks.map((m) => {
          if (m.kind === "position review" || m.kind === "position screen") {
            const review = m.kind === "position review";
            const tick = (
              <line
                className="stroke-pale"
                x1={x(m.step)}
                x2={x(m.step)}
                y1={Y1}
                y2={Y1 - (review ? 34 : 14)}
                strokeWidth={review ? 3 : 1.5}
              />
            );
            return m.decision ? (
              <g
                key={`${m.step}-${m.kind}`}
                className="cursor-pointer"
                role="button"
                aria-label={`Open the trail of the ${m.kind} at step ${m.step}`}
                onClick={() => onOpenTrail(m.decision!)}
              >
                <rect x={x(m.step) - 8} y={Y1 - 40} width={16} height={40} fill="transparent" />
                {tick}
              </g>
            ) : (
              <g key={`${m.step}-${m.kind}`}>{tick}</g>
            );
          }
          if (m.kind === "stop price" || !m.price || valueOf(m.price) === null) return null;
          const cx = x(m.step);
          const cy = y(valueOf(m.price)!);
          const entry = m.kind === "entry";
          return (
            <g key={`${m.step}-${m.kind}`}>
              {entry ? (
                <rect x={cx - 6} y={cy - 6} width={12} height={12} className="fill-screen stroke-pale" strokeWidth={2} />
              ) : (
                <circle cx={cx} cy={cy} r={6.5} className="fill-pale stroke-screen" strokeWidth={1.5} />
              )}
              <text className="chart-label fill-pale" x={cx} y={cy - 14} textAnchor={cx > X1 - 60 ? "end" : cx < X0 + 60 ? "start" : "middle"}>
                {entry ? "entry" : "close"}
              </text>
            </g>
          );
        })}
        <rect className="stroke-rule" x={X0} y={Y0} width={X1 - X0} height={Y1 - Y0} fill="none" strokeWidth={1.5} />
        {hover && (
          <g pointerEvents="none">
            <line className="stroke-pale" x1={x(hover.step)} x2={x(hover.step)} y1={Y0} y2={Y1} strokeDasharray="3 4" />
            <circle className="fill-pale" cx={x(hover.step)} cy={y(hover.value)} r={4} />
          </g>
        )}
      </svg>
      <p className="px-[1ch] pb-1 font-mono text-[13.5px] tracking-wider text-dim" aria-live="polite">
        {hover
          ? `${hover.at ? dayAndTime(hover.at) : `Step ${hover.step}`}: closed at ${real ? price(hover.value) : hover.value} [the agent saw ${hover.rescaled}]`
          : "Point at the chart to read one 15-minute bar; click a tick along the bottom to open its trail."}
      </p>
    </div>
  );
}
