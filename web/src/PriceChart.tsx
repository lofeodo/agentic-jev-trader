// One asset's price chart on the Dataset screen (spec appendix 7, section 9): each day's close
// in real dollars, drawn as the sim chart is (straight lines, faint grid, hatching under the
// line, ticks on the inside of the frame). Hovering reads out one day.
import { area as d3area, bisector, line as d3line, scaleLinear, scaleUtc } from "d3";
import { useRef, useState } from "react";

import type { PriceChart as Chart } from "./api/client";
import { day, price } from "./format";

const W = 1400;
const H = 300;
const M = { t: 16, r: 24, b: 44, l: 110 };
const X0 = M.l;
const X1 = W - M.r;
const Y0 = M.t;
const Y1 = H - M.b;

type Point = { when: Date; day: string; real: number; rescaled: number };
const byWhen = bisector((p: Point) => p.when).center;
const year = new Intl.DateTimeFormat("en-GB", { month: "short", year: "numeric", timeZone: "UTC" });

export function PriceChart({ chart }: { chart: Chart }) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [hover, setHover] = useState<Point | null>(null);
  const points: Point[] = chart.points
    .filter((p) => p.day !== null && p.close.real !== null)
    .map((p) => ({ when: new Date(`${p.day}T00:00:00Z`), day: p.day!, real: p.close.real!, rescaled: p.close.rescaled }));
  if (points.length === 0) {
    return <p className="font-mono text-dim">No real prices: this dataset has no asset key.</p>;
  }

  const lows = points.map((p) => p.real);
  const low = Math.min(...lows);
  const high = Math.max(...lows);
  const pad = Math.max((high - low) * 0.06, high * 0.005);
  const y = scaleLinear().domain([low - pad, high + pad]).nice(5).range([Y1, Y0]);
  const x = scaleUtc().domain([points[0].when, points[points.length - 1].when]).range([X0, X1]);
  const path = d3line<Point>()
    .x((p) => x(p.when))
    .y((p) => y(p.real));
  const hatch = d3area<Point>()
    .x((p) => x(p.when))
    .y0(Y1)
    .y1((p) => y(p.real));
  const patternId = `hatch-${chart.asset.masked_id}`;

  function pick(clientX: number) {
    const box = svgRef.current!.getBoundingClientRect();
    const when = x.invert(((clientX - box.left) * W) / box.width);
    setHover(points[byWhen(points, when)]);
  }

  return (
    <div className="border-[1.5px] border-rule px-2 pt-3 pb-1">
      <svg
        ref={svgRef}
        viewBox={`0 0 ${W} ${H}`}
        className="block w-full"
        role="img"
        aria-label={`Daily closing price of ${chart.asset.name}`}
        onMouseMove={(e) => pick(e.clientX)}
        onMouseLeave={() => setHover(null)}
      >
        <defs>
          <pattern id={patternId} width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <line x1="0" y1="0" x2="0" y2="7" stroke="var(--color-rule)" strokeWidth="1" />
          </pattern>
        </defs>
        {y.ticks(5).map((t) => (
          <g key={t}>
            {y(t) > Y0 + 1 && y(t) < Y1 - 1 && <line className="stroke-grid" x1={X0} x2={X1} y1={y(t)} y2={y(t)} />}
            <line className="stroke-rule" x1={X0} x2={X0 + 10} y1={y(t)} y2={y(t)} />
            <text className="axis-number" x={X0 - 12} y={y(t) + 5} textAnchor="end">
              {price(t)}
            </text>
          </g>
        ))}
        {x.ticks(8).map((t) => (
          <g key={t.toISOString()}>
            <line className="stroke-grid" x1={x(t)} x2={x(t)} y1={Y0} y2={Y1} />
            <line className="stroke-rule" x1={x(t)} x2={x(t)} y1={Y1 - 8} y2={Y1} />
            <text className="axis-number" x={x(t)} y={Y1 + 27} textAnchor="middle">
              {year.format(t)}
            </text>
          </g>
        ))}
        <path d={hatch(points) ?? undefined} fill={`url(#${patternId})`} opacity={0.45} />
        <path d={path(points) ?? undefined} fill="none" className="stroke-amber" strokeWidth={1.6} />
        <rect className="stroke-rule" x={X0} y={Y0} width={X1 - X0} height={Y1 - Y0} fill="none" strokeWidth={1.5} />
        {hover && (
          <g>
            <line className="stroke-pale" x1={x(hover.when)} x2={x(hover.when)} y1={Y0} y2={Y1} strokeDasharray="3 4" />
            <circle className="fill-pale" cx={x(hover.when)} cy={y(hover.real)} r={4} />
          </g>
        )}
      </svg>
      <p className="px-[1ch] pb-1 font-mono text-[13.5px] tracking-wider text-dim" aria-live="polite">
        {hover
          ? `${day(hover.day)}: closed at ${price(hover.real)} [the agent saw ${hover.rescaled}]`
          : `${points.length} days, from ${price(points[0].real)} to ${price(points[points.length - 1].real)}. Point at the chart to read one day.`}
      </p>
    </div>
  );
}
