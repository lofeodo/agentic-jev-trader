// The Comparison screen (spec appendix 7, section 10; appendix 9, section 6): the project's answer.
// Per part of the test period ("market"), never merged: a verdict for each LLM, both winners,
// each repeat, and the gap over time.
import { line as d3line, scaleLinear } from "d3";

import { fetchComparison, type GapLine, type MarketComparison, type ModelResult } from "./api/client";
import { day, dollars, signedDollars } from "./format";
import { ErrorBox, Pair, SectionHeading } from "./pieces";
import { useRead } from "./useRead";

const VERDICT_WORDS: Record<ModelResult["verdict"], string> = {
  helped: "Memory helped",
  hurt: "Memory hurt",
  "can't tell": "Can't tell",
  waiting: "Waiting",
};

const th = "border-b border-rule py-[.4rem] pr-[2ch] text-left font-mono text-[13.5px] font-light tracking-wider text-dim";
const td = "py-[.42rem] pr-[2ch] align-top font-mono";

const money = (value: number | null) => (value === null ? "--" : dollars(value));
const spread = (value: number | null) => (value === null ? "--" : `±${dollars(value)}`);

export function ComparisonScreen() {
  const { data, error } = useRead(fetchComparison);

  return (
    <section>
      <h1 className="mb-1 text-center text-[2.1rem] leading-tight tracking-[.02em]">Comparison</h1>
      <p className="mb-6 text-center text-[1.1rem] text-dim">
        Does the agent end with more money when it has memory than when it has none?
      </p>

      {error && (
        <div className="mb-6">
          <ErrorBox title="Cannot reach the API" text={`${error}. Asking again when you come back to this tab.`} />
        </div>
      )}
      {data === null && !error && <p className="text-center font-mono text-dim">Loading...</p>}

      {data !== null && (
        <p className="mx-auto mb-8 max-w-[110ch] font-mono text-[13.5px] tracking-wider text-dim">
          Each part of the test period (a falling market and a rising one) is 30 days replayed three
          times (three repeats), each time by three sims side by side from $10,000: with memory using
          Claude Haiku, with memory using GLM Flash, and without memory. Jev answers the same
          question a little differently each time, so the repeats land apart: ending at $10,100,
          $10,200 and $10,300 averages $10,200 and typically lands $100 from it. That $100 is the
          standard deviation, shown ±$100. The threshold combines the two groups' standard
          deviations into one (with memory ±$100 and without ±$50 make about $79). Memory helped
          when its average ends higher than without memory's by more than the threshold; hurt when
          lower by more; otherwise we can't tell. A verdict is provisional until every sim of its
          market has finished. The two markets are never added together. The models' real cost is
          shown beside each verdict, not taken out of it.
        </p>
      )}

      {data !== null && data.markets.length === 0 && (
        <div className="border-[1.5px] border-rule px-[2ch] py-10 text-center">
          <p className="text-[1.2rem] text-pale">No measurement sims yet</p>
          <p className="mt-1 text-dim">The verdicts appear here once the measurement sims run.</p>
        </div>
      )}

      {data?.markets.map((market, i) => (
        <Market key={`${market.dataset}-${market.market}`} market={market} number={i + 1} />
      ))}
    </section>
  );
}

function Market({ market, number }: { market: MarketComparison; number: number }) {
  const days =
    market.first_day && market.last_day ? `${day(market.first_day)} to ${day(market.last_day)}` : "";
  return (
    <div className="mb-14">
      <SectionHeading number={number} title={market.market} says={days} />

      <div className="mb-6 grid gap-4 md:grid-cols-2">
        {market.models.map((m) => (
          <Verdict key={m.model} result={m} market={market} />
        ))}
      </div>

      {(market.performance || market.price) && (
        <div className="mb-6 grid gap-4 md:grid-cols-2">
          {market.performance && (
            <Winner
              title="Performance winner"
              winner={market.performance.winner}
              market={market}
              says={market.performance.says}
            />
          )}
          {market.price && (
            <Winner title="Price winner" winner={market.price.winner} market={market} says={market.price.says} />
          )}
        </div>
      )}

      {market.notes.length > 0 && (
        <div className="mb-6">
          {market.notes.map((note) => (
            <ErrorBox key={note} title="Something changed between the sims" text={note} />
          ))}
        </div>
      )}

      <h3 className="mb-2 font-mono text-[13.5px] tracking-widest text-dim">Each repeat: account value at the end</h3>
      <Repeats market={market} />

      <h3 className="mt-8 mb-2 font-mono text-[13.5px] tracking-widest text-dim">
        The gap over time: with memory minus without, averaged over the repeats, at each day's end
      </h3>
      <GapChart lines={market.gap_over_time} />

      <p className="mt-3 font-mono text-[12.5px] tracking-wider text-dim">
        Jev versions that answered: {market.jev_versions.length ? market.jev_versions.join(", ") : "none recorded yet"}
      </p>
    </div>
  );
}

function Verdict({ result, market }: { result: ModelResult; market: MarketComparison }) {
  const without = market.without_memory;
  return (
    <div className="border-[1.5px] border-rule">
      <div className="flex border-b-[1.5px] border-rule font-mono text-[13.5px] tracking-widest">
        <span className="border-r-[1.5px] border-rule px-[2ch] py-1.5 text-dim">{result.label}</span>
        <span className={`px-[2ch] py-1.5 ${result.verdict === "waiting" ? "text-dim" : "bg-amber text-screen"}`}>
          {VERDICT_WORDS[result.verdict]}
        </span>
        {result.provisional && <span className="px-[2ch] py-1.5 text-dim">Provisional</span>}
      </div>
      <div className="px-[2ch] py-3">
        <div className="mb-3 flex flex-wrap gap-3 font-mono text-[13.5px] tracking-wider">
          <Pair name="With memory" value={`${money(result.with_memory.average_usd)} ${spread(result.with_memory.standard_deviation_usd)}`} />
          <Pair name="Without" value={`${money(without.average_usd)} ${spread(without.standard_deviation_usd)}`} />
          <Pair name="Gap" value={result.difference_usd === null ? "--" : signedDollars(result.difference_usd)} />
          <Pair name="Threshold" value={money(result.threshold_usd)} />
        </div>
        <p className="text-[15px]">{result.says}</p>
        <p className="mt-2 font-mono text-[12.5px] tracking-wider text-dim">
          {result.usd_per_evaluation_or_review === null
            ? "No full evaluations or position reviews priced yet."
            : `The LLM cost $${result.usd_per_evaluation_or_review.toFixed(4)} per full evaluation or position review`}
          {result.seconds_per_full_evaluation !== null &&
            `; ${result.seconds_per_full_evaluation.toFixed(1)} seconds per full evaluation`}
          {`; lookups per full evaluation: ${result.lookups_per_full_evaluation === null ? "not recorded yet" : result.lookups_per_full_evaluation.toFixed(1)}.`}
        </p>
      </div>
    </div>
  );
}

function Winner({
  title,
  winner,
  market,
  says,
}: {
  title: string;
  winner: string | null;
  market: MarketComparison;
  says: string;
}) {
  const label = market.models.find((m) => m.model === winner)?.label ?? "None";
  return (
    <div className="border-[1.5px] border-rule px-[2ch] py-3">
      <div className="font-mono text-[13.5px] tracking-wider text-dim">{title}</div>
      <div className={`font-mono text-[1.6rem] leading-tight ${winner ? "text-pale" : "text-dim"}`}>{label}</div>
      <div className="text-[14px] text-dim">{says}</div>
    </div>
  );
}

function Repeats({ market }: { market: MarketComparison }) {
  const columns = [...new Set(market.repeats.flatMap((r) => r.sims.map((s) => s.label)))];
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-separate border-spacing-0">
        <thead>
          <tr>
            <th scope="col" className={th}>Repeat</th>
            {columns.map((c) => (
              <th key={c} scope="col" className={th}>{c}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {market.repeats.map((r) => (
            <tr key={r.number ?? "none"} className="hover:bg-amber hover:text-screen [&:hover_*]:text-screen">
              <td className={`${td} text-pale`}>{r.number ?? "--"}</td>
              {columns.map((c) => {
                const sims = r.sims.filter((s) => s.label === c);
                return (
                  <td key={c} className={td}>
                    {sims.length === 0
                      ? "--"
                      : sims.map((s) => (
                          <a key={s.sim_id} href={`#/sims/${s.sim_id}`} className="mr-[2ch] underline-offset-4 hover:underline">
                            {s.ending_value_usd === null ? s.status : dollars(s.ending_value_usd)}{" "}
                            <span className="text-[12.5px] text-dim">[sim {s.sim_id}]</span>
                          </a>
                        ))}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const W = 1400;
const H = 260;
const M = { t: 16, r: 200, b: 40, l: 96 };

type GapPoint = GapLine["points"][number];

function GapChart({ lines }: { lines: GapLine[] }) {
  const drawn = lines.filter((l) => l.points.length > 0);
  if (drawn.length === 0) {
    return (
      <p className="border-[1.5px] border-rule px-[2ch] py-6 text-center font-mono text-dim">
        Drawn once a sim with memory and one without have both finished.
      </p>
    );
  }
  const count = Math.max(...drawn.map((l) => l.points.length));
  const gaps = drawn.flatMap((l) => l.points.map((p) => p.gap_usd)).concat(0);
  const low = Math.min(...gaps);
  const high = Math.max(...gaps);
  const pad = Math.max((high - low) * 0.1, 10);
  const y = scaleLinear().domain([low - pad, high + pad]).nice(5).range([H - M.b, M.t]);
  const x = scaleLinear().domain([0, Math.max(count - 1, 1)]).range([M.l, W - M.r]);
  const path = d3line<GapPoint>()
    .x((_, i) => x(i))
    .y((p) => y(p.gap_usd));
  const every = count > 10 ? 5 : 1;

  return (
    <div className="border-[1.5px] border-rule px-2 pt-3 pb-1">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="block w-full"
        role="img"
        aria-label="Line chart of the gap between the sims with memory and without, day by day"
      >
        {y.ticks(5).map((t) => (
          <g key={t}>
            <line className={t === 0 ? "stroke-dim" : "stroke-grid"} x1={M.l} x2={W - M.r} y1={y(t)} y2={y(t)} strokeDasharray={t === 0 ? "2 5" : undefined} />
            <text className="axis-number" x={M.l - 12} y={y(t) + 5} textAnchor="end">
              {signedDollars(t)}
            </text>
          </g>
        ))}
        {drawn[0].points.map((p, i) =>
          i % every === 0 && p.day ? (
            <text key={p.day} className="axis-number" x={x(i)} y={H - M.b + 26} textAnchor="middle">
              {day(p.day).replace(/ \d{4}$/, "")}
            </text>
          ) : null,
        )}
        <rect className="stroke-rule" x={M.l} y={M.t} width={W - M.r - M.l} height={H - M.b - M.t} fill="none" strokeWidth="1.5" />
        {drawn.map((l, i) => {
          const last = l.points[l.points.length - 1];
          return (
            <g key={l.model}>
              <path
                d={path(l.points) ?? ""}
                fill="none"
                className={i === 0 ? "stroke-amber" : "stroke-pale"}
                strokeWidth={2}
                strokeDasharray={i === 0 ? undefined : "7 5"}
              />
              <text
                className={`chart-label ${i === 0 ? "fill-amber" : "fill-pale"}`}
                x={W - M.r + 14}
                y={y(last.gap_usd) + 5 + i * 19}
              >
                {`${l.label} ${signedDollars(last.gap_usd)}`}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
