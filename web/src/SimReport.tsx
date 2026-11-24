// The Trading sim page, its bottom half (spec appendix 7, section 5): the trades table, the
// measurements, the scorecard and the settings. The first three are worked out by the API when
// asked for; while the sim is in progress they are asked for again every 20 seconds, never before
// the last answer came back. A finished or stopped sim's page asks once.
import { useEffect, useState, type ReactNode } from "react";

import {
  fetchMeasurements,
  fetchScorecard,
  fetchTrades,
  type Breakdown,
  type DayMark,
  type Figure,
  type FilterCounts,
  type MeasurementGroup,
  type Scorecard,
  type SimHeader,
  type Split,
  type TradeFilters,
  type TradeLine,
} from "./api/client";
import { AssetTag, DirectionWords, ErrorBox, PriceTag, SectionHeading } from "./pieces";
import { dayAndTime, dollars, dollarsAndCents, fromApi, signedDollars, units } from "./format";

// A setting (appendix 8, section 8.9), like the 1-second one on the sim page.
const REPORT_REFRESH_MS = 20_000;
const PAGE_SIZE = 50;
const STEP_MINUTES = 15; // one step of the sim's clock

const th = "border-b border-rule py-[.4rem] pr-[2ch] font-mono text-[13.5px] font-light tracking-wider text-dim";
const td = "py-[.42rem] pr-[2ch] align-top font-mono text-[15px]";
const row = "hover:bg-amber hover:text-screen [&:hover_*]:text-screen";
const note = "font-mono text-[12.5px] tracking-wider text-dim";

// Reads `load` once, then again every 20 seconds while `keepAsking`; reads afresh when `deps`
// change, and once more when the sim stops being in progress.
function usePolled<T>(load: () => Promise<T>, keepAsking: boolean, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let stopped = false;
    let timer: number | undefined;
    async function tick() {
      try {
        const answer = await load();
        if (stopped) return;
        setData(answer);
        setError(null);
      } catch (problem) {
        if (stopped) return;
        setError(problem instanceof Error ? problem.message : String(problem));
      }
      if (keepAsking && !stopped) timer = window.setTimeout(() => void tick(), REPORT_REFRESH_MS);
    }
    void tick();
    return () => {
      stopped = true;
      window.clearTimeout(timer);
    };
  }, [keepAsking, ...deps]);
  return { data, error };
}

export function SimReport({ id, header, inProgress, firstNumber }: { id: number; header: SimHeader; inProgress: boolean; firstNumber: number }) {
  return (
    <>
      <Trades id={id} inProgress={inProgress} number={firstNumber} />
      <MeasurementsSection id={id} inProgress={inProgress} number={firstNumber + 1} />
      <ScorecardSection id={id} inProgress={inProgress} number={firstNumber + 2} />
      <SettingsSection header={header} number={firstNumber + 3} />
    </>
  );
}

function Problem({ error }: { error: string | null }) {
  return error ? (
    <div className="mb-4">
      <ErrorBox title="Cannot reach the API" text={`${error}. Asking again shortly.`} />
    </div>
  ) : null;
}

// Trades

const NO_FILTERS: TradeFilters = { lost_money: false, trimmed: false, stop_price: false, overnight: false, no_trade: false };

const FILTERS: { key: keyof TradeFilters & keyof FilterCounts; label: string }[] = [
  { key: "lost_money", label: "Lost money" },
  { key: "trimmed", label: "Trimmed by a limit" },
  { key: "stop_price", label: "Closed at the stop price" },
  { key: "overnight", label: "Held overnight" },
  { key: "no_trade", label: "Add full evaluations with no trade" },
];

const ENDINGS: Record<string, string> = {
  jev: "Jev chose to close it",
  stop_price: "Its stop price was reached",
  forced_close: "A forced close",
  sim_ended: "Closed because the sim ended",
};

const MARKS: Record<string, string> = {
  "daily loss limit reached": "Daily loss limit reached: no new trades that day",
  "loan interest paid": "Loan interest paid",
  "forced close": "Forced close: code closed every position",
};

const limitWords = (limit: string) => `the ${limit.replaceAll("_", " ")} limit`;

const when = (at: string | null, step: number | null) =>
  at ? dayAndTime(fromApi(at)) : step === null ? "--" : `step ${step}`;

function Trades({ id, inProgress, number }: { id: number; inProgress: boolean; number: number }) {
  const [filters, setFilters] = useState<TradeFilters>(NO_FILTERS);
  const [page, setPage] = useState(1);
  const { data: table, error } = usePolled(() => fetchTrades(id, filters, page, PAGE_SIZE), inProgress, [id, page, ...Object.values(filters)]);
  const pages = table ? Math.max(1, Math.ceil(table.total / table.page_size)) : 1;

  const toggle = (key: keyof TradeFilters) => {
    setFilters((f) => ({ ...f, [key]: !f[key] }));
    setPage(1);
  };

  return (
    <section className="mt-10">
      <SectionHeading number={number} title="Trades" says="Every trade, and the full evaluations that ended in no trade" />
      <Problem error={error} />
      <div className="mb-3 flex flex-wrap gap-2 font-mono text-[13.5px] tracking-wider">
        {FILTERS.map(({ key, label }) => (
          <button
            key={key}
            type="button"
            aria-pressed={filters[key]}
            onClick={() => toggle(key)}
            className={`border-[1.5px] border-rule px-[1.5ch] py-1 ${filters[key] ? "bg-amber text-screen" : "hover:text-pale"}`}
          >
            {label} ({table ? table.counts[key] : "-"})
          </button>
        ))}
      </div>
      {table && table.marks.length > 0 && <Marks marks={table.marks} />}
      {!table ? (
        <p className="font-mono text-dim">Loading...</p>
      ) : table.lines.length === 0 ? (
        <p className="font-mono text-dim">{table.counts.trades === 0 ? "No trades yet." : "No trades match these filters."}</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full border-separate border-spacing-0">
            <thead>
              <tr>
                <th className={`${th} text-left`}>Opened</th>
                <th className={`${th} text-left`}>Asset</th>
                <th className={`${th} text-left`}>Direction</th>
                <th className={`${th} text-right`}>Put in</th>
                <th className={`${th} text-right`}>Bought / sold at</th>
                <th className={`${th} text-left`}>Closed</th>
                <th className={`${th} text-right`}>Result</th>
                <th className={`${th} text-left`}>How it ended</th>
              </tr>
            </thead>
            <tbody>
              {table.lines.map((line) =>
                line.kind === "trade" ? <TradeRow key={`t${line.position}`} line={line} /> : <NoTradeRow key={`n${line.decision}`} line={line} />,
              )}
            </tbody>
          </table>
        </div>
      )}
      {table && pages > 1 && (
        <div className="mt-3 flex items-center gap-[2ch] font-mono text-[13.5px] tracking-wider">
          <button type="button" disabled={page <= 1} onClick={() => setPage(page - 1)} className="border-[1.5px] border-rule px-[1.5ch] py-1 disabled:text-dim">
            &lt; Earlier
          </button>
          <span className="text-dim">
            Page {page} of {pages} ({table.total} lines)
          </span>
          <button type="button" disabled={page >= pages} onClick={() => setPage(page + 1)} className="border-[1.5px] border-rule px-[1.5ch] py-1 disabled:text-dim">
            Later &gt;
          </button>
        </div>
      )}
      <p className={`mt-2 ${note}`}>
        Result: what the trade made or lost after every trading cost (slippage, commission or fee, and
        a short's nightly borrow fee): bought for $1,000, sold for $1,100, $2 of commissions, +$98.
        Trimmed: code made the trade smaller to fit a risk limit. Held overnight: still open at
        midnight UTC. Prices: the real one first, the one the agent saw in brackets.
      </p>
      <DirectionWords />
    </section>
  );
}

function Marks({ marks }: { marks: DayMark[] }) {
  return (
    <ul className="mb-3 flex flex-wrap gap-x-[3ch] gap-y-1 font-mono text-[13.5px] tracking-wider">
      {marks.map((m) => (
        <li key={`${m.step}-${m.kind}`}>
          <span className="text-dim">{when(m.at, m.step)}</span> {MARKS[m.kind] ?? m.kind}
          {m.amount_usd !== null && `: ${dollarsAndCents(m.amount_usd)}`}
        </li>
      ))}
    </ul>
  );
}

function TradeRow({ line }: { line: TradeLine }) {
  const tags = [line.trimmed && "trimmed", line.held_overnight && "overnight"].filter(Boolean).join(", ");
  return (
    <tr className={row}>
      <td className={td}>{when(line.opened_at, line.opened_step)}</td>
      <td className={td}>
        <AssetTag asset={line.asset} />
        {line.units !== null && <div className="text-[12.5px] text-dim">{units(line.units)} units</div>}
      </td>
      <td className={td}>{line.direction}</td>
      <td className={`${td} text-right`}>
        {line.put_in_usd === null ? "--" : dollars(line.put_in_usd)}
        {line.trimmed && line.amount_chosen !== null && line.limited_by && (
          <div className="text-[12.5px] text-dim">
            Jev chose {dollars(line.amount_chosen)}; trimmed by {limitWords(line.limited_by)}
          </div>
        )}
      </td>
      <td className={`${td} text-right`}>
        {line.entry_price ? <PriceTag price={line.entry_price} /> : "--"}
        <div>{line.exit_price ? <PriceTag price={line.exit_price} /> : <span className="text-dim">still open</span>}</div>
      </td>
      <td className={td}>{line.closed_step === null ? "Open" : when(line.closed_at, line.closed_step)}</td>
      <td className={`${td} text-right`}>
        {line.profit_usd === null ? "--" : signedDollars(line.profit_usd)}
        {line.trading_costs_usd !== null && <div className="text-[12.5px] text-dim">costs {dollarsAndCents(line.trading_costs_usd)}</div>}
      </td>
      <td className={td}>
        {line.closing_reason ? (ENDINGS[line.closing_reason] ?? line.closing_reason) : "--"}
        {tags && <div className="text-[12.5px] text-dim">{tags}</div>}
      </td>
    </tr>
  );
}

function NoTradeRow({ line }: { line: TradeLine }) {
  const why =
    line.pick === "no_trade"
      ? "Jev picked no trade"
      : line.limited_by
        ? `Jev picked a ${line.direction ?? ""} trade; ${limitWords(line.limited_by)} left nothing of it`
        : "No order was placed";
  return (
    <tr className={`${row} text-dim`}>
      <td className={td}>{when(line.decided_at, line.decided_step)}</td>
      <td className={td}>
        <AssetTag asset={line.asset} />
      </td>
      <td className={td}>no trade</td>
      <td className={`${td} text-right`}>--</td>
      <td className={`${td} text-right`}>--</td>
      <td className={td}>--</td>
      <td className={`${td} text-right`}>--</td>
      <td className={td}>
        {why}
        {line.screen_answer !== null && (
          <div className="text-[12.5px]">screen: {Math.round(line.screen_answer * 100)}% worth a full evaluation</div>
        )}
      </td>
    </tr>
  );
}

// Measurements

function value(unit: string, v: number | null | undefined): string {
  if (v === null || v === undefined) return "--";
  switch (unit) {
    case "usd":
      return dollars(v);
    case "signed_usd":
      return signedDollars(v);
    case "cents":
      return dollarsAndCents(v);
    case "share":
      return `${(v * 100).toFixed(v !== 0 && Math.abs(v) < 0.1 ? 1 : 0)}%`;
    case "count":
      return String(Math.round(v));
    case "hours":
      return `${v.toFixed(1)} h`;
    case "days":
      return `${v} d`;
    default:
      return v.toFixed(2);
  }
}

function MeasurementsSection({ id, inProgress, number }: { id: number; inProgress: boolean; number: number }) {
  const { data, error } = usePolled(() => fetchMeasurements(id), inProgress, [id]);
  return (
    <section className="mt-10">
      <SectionHeading number={number} title="Measurements" says="Six groups, each beside holding the five assets" />
      <Problem error={error} />
      {!data ? (
        <p className="font-mono text-dim">Loading...</p>
      ) : (
        <>
          {data.groups.map((group) => (
            <Group key={group.key} group={group} holding={data.holding_sim_id !== null} />
          ))}
          <p className={note}>
            Holding the five assets: a separate account that puts $2,000 into each of the five assets on
            the first day and never trades. It shows what the market did; the agent gets credit only for
            what it ends above it. Measured up to the step this sim has reached.
          </p>
        </>
      )}
    </section>
  );
}

function Group({ group, holding }: { group: MeasurementGroup; holding: boolean }) {
  return (
    <div className="mb-8">
      <div className="mb-2 flex flex-wrap items-baseline gap-x-[2ch] border-b-[1.5px] border-rule pb-1">
        <h3 className="text-[1.05rem] tracking-[.12em]">{group.title}</h3>
        <span className={note}>{group.says}</span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full border-separate border-spacing-0">
          <thead>
            <tr>
              <th className={`${th} text-left`}>What happened</th>
              <th className={`${th} w-[14ch] text-right`}>This sim</th>
              {holding && <th className={`${th} w-[14ch] text-right`}>Holding</th>}
            </tr>
          </thead>
          <tbody>
            {group.figures.map((f) => (
              <FigureRow key={f.key} figure={f} holding={holding} />
            ))}
          </tbody>
        </table>
      </div>
      {group.breakdowns.map((b) => (
        <BreakdownTable key={b.key} breakdown={b} />
      ))}
    </div>
  );
}

function FigureRow({ figure: f, holding }: { figure: Figure; holding: boolean }) {
  return (
    <tr className={row}>
      <td className="py-[.42rem] pr-[2ch] align-top">
        <div className="text-[15px]">{f.says}</div>
        <div className={note}>{f.name}</div>
      </td>
      <td className={`${td} text-right text-pale`}>{value(f.unit, f.sim)}</td>
      {holding && <td className={`${td} text-right`}>{value(f.unit, f.holding)}</td>}
    </tr>
  );
}

function BreakdownTable({ breakdown: b }: { breakdown: Breakdown }) {
  if (b.rows.length === 0) return null;
  const withValue = b.rows.some((r) => r.value !== null);
  return (
    <div className="mt-3 max-w-[640px]">
      <div className="font-mono text-[13.5px] tracking-wider">
        {b.name} <span className="text-dim">/ {b.says}</span>
      </div>
      <table className="w-full border-separate border-spacing-0">
        <tbody>
          {b.rows.map((r) => (
            <tr key={r.label} className={row}>
              <td className={td}>{r.label}</td>
              <td className={`${td} text-right`}>{r.trades} trade(s)</td>
              {withValue && <td className={`${td} text-right`}>{value(b.unit, r.value)}</td>}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// Scorecard

const SPLITS: { key: Split; label: string }[] = [
  { key: "trend", label: "Trend" },
  { key: "volume", label: "Volume level" },
  { key: "part_of_day", label: "Part of the day" },
];

function ScorecardSection({ id, inProgress, number }: { id: number; inProgress: boolean; number: number }) {
  const [split, setSplit] = useState<Split[]>([]);
  const { data, error } = usePolled(() => fetchScorecard(id, split), inProgress, [id, split.join()]);
  const toggle = (key: Split) => setSplit((s) => (s.includes(key) ? s.filter((x) => x !== key) : SPLITS.map((x) => x.key).filter((x) => x === key || s.includes(x))));

  return (
    <section className="mt-10">
      <SectionHeading number={number} title="Scorecard" says="How the sim's own closed trades did, group by group" />
      <Problem error={error} />
      <div className="mb-3 flex flex-wrap items-center gap-2 font-mono text-[13.5px] tracking-wider">
        <span className="text-dim">Split further by</span>
        {SPLITS.map(({ key, label }) => (
          <button
            key={key}
            type="button"
            aria-pressed={split.includes(key)}
            onClick={() => toggle(key)}
            className={`border-[1.5px] border-rule px-[1.5ch] py-1 ${split.includes(key) ? "bg-amber text-screen" : "hover:text-pale"}`}
          >
            {label}
          </button>
        ))}
      </div>
      {!data ? <p className="font-mono text-dim">Loading...</p> : <ScorecardTable card={data} />}
      <p className={`mt-2 ${note}`}>
        A group is a candle pattern (a shape in the last hour of 15-minute bars, such as a hammer), a
        direction and a kind of asset; a trade counts once for each pattern it opened beside. Stocks
        and crypto are never counted together. With the trend: a long while the price is above its
        20-day average, or a short while it is below. Volume level: trading against its usual amount
        at that time of day. The agent is shown a group only once it holds{" "}
        {data ? data.minimum_sample : 10} closed trades: with fewer, a lucky streak would look like
        a rule.
      </p>
    </section>
  );
}

function ScorecardTable({ card }: { card: Scorecard }) {
  if (card.lines.length === 0) return <p className="font-mono text-dim">No closed trades to count yet.</p>;
  const shown = (part: Split) => card.split.includes(part);
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-separate border-spacing-0">
        <thead>
          <tr>
            <th className={`${th} text-left`}>Candle pattern</th>
            <th className={`${th} text-left`}>Direction</th>
            <th className={`${th} text-left`}>Asset</th>
            {shown("trend") && <th className={`${th} text-left`}>Trend</th>}
            {shown("volume") && <th className={`${th} text-left`}>Volume</th>}
            {shown("part_of_day") && <th className={`${th} text-left`}>Part of day</th>}
            <th className={`${th} text-right`}>Trades</th>
            <th className={`${th} text-right`}>Made money</th>
            <th className={`${th} text-right`}>Average gain</th>
            <th className={`${th} text-right`}>Average loss</th>
            <th className={`${th} text-right`}>Altogether</th>
            <th className={`${th} text-left`}>Shown to the agent</th>
          </tr>
        </thead>
        <tbody>
          {card.lines.map((x) => (
            <tr key={[x.pattern, x.direction, x.asset_class, x.trend, x.volume_level, x.part_of_day].join("|")} className={row}>
              <td className={td}>{x.pattern}</td>
              <td className={td}>{x.direction}</td>
              <td className={td}>{x.asset_class}</td>
              {shown("trend") && <td className={td}>{x.trend}</td>}
              {shown("volume") && <td className={td}>{x.volume_level}</td>}
              {shown("part_of_day") && <td className={td}>{x.part_of_day}</td>}
              <td className={`${td} text-right`}>{x.trades}</td>
              <td className={`${td} text-right`}>{Math.round(x.share_made_money * 100)}%</td>
              <td className={`${td} text-right`}>{x.average_gain === null ? "--" : signedDollars(x.average_gain)}</td>
              <td className={`${td} text-right`}>{x.average_loss === null ? "--" : signedDollars(x.average_loss)}</td>
              <td className={`${td} text-right`}>{signedDollars(x.total_profit)}</td>
              <td className={td}>{x.shown_to_agent ? "Yes" : <span className="text-dim">{x.trades < card.minimum_sample ? `No: under ${card.minimum_sample}` : "No: the agent never reads this split"}</span>}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className={`mt-1 ${note}`}>{card.closed_trades} closed trade(s) counted.</p>
    </div>
  );
}

// Settings

type Setting = { label: string; show: (v: number, account: number) => string };
const pct = (v: number) => `${+(v * 100).toFixed(3)}%`;
const ofAccount = (v: number, account: number) => `${pct(v)} of account value (${dollars(v * account)} of ${dollars(account)})`;
// One night's share (1/365) of a yearly rate on an amount.
const nightly = (yearly: number, amount: number) => `$${((yearly * amount) / 365).toFixed(2)}`;
const times = (v: number, account: number) => `${v} times account value (${dollars(v * account)})`;

const RISK: Record<string, Setting> = {
  trade_risk_limit: { label: "Trade risk limit: the most one trade may lose at its stop price", show: ofAccount },
  position_limit: { label: "Position limit: the most in one position", show: times },
  exposure_limit: { label: "Exposure limit: the most held in all positions together", show: times },
  daily_loss_limit: { label: "Daily loss limit: past this loss since midnight UTC, no new trades that day", show: ofAccount },
  forced_close_share: { label: "Forced close: every position closes when the account falls below this share of what it holds", show: (v, account) => `${pct(v)} (holding ${dollars(2 * account)}, all closes below ${dollars(v * 2 * account)})` },
  no_new_stock_trade_bars: { label: "No new stock trade in a session's last bars", show: (v) => `${v} bars (${v * STEP_MINUTES} minutes)` },
  screen_cut_off: { label: "Screen cut-off: Jev's yes needed for a full evaluation", show: (v) => pct(v) },
};

const COSTS: Record<string, Setting> = {
  slippage: { label: "Slippage: every order is carried out at a price this much worse", show: (v) => `${pct(v)} ($${(v * 100).toFixed(2)} on a $100 price)` },
  stock_commission: { label: "Stock commission, per order", show: (v) => dollarsAndCents(v) },
  crypto_trading_fee: { label: "Crypto trading fee, per order", show: (v) => `${pct(v)} (${dollarsAndCents(v * 2000)} on $2,000)` },
  stock_borrow_fee_yearly: { label: "Stock borrow fee for a short kept overnight, a year", show: (v) => `${pct(v)} (${nightly(v, 2000)} a night on $2,000)` },
  crypto_borrow_fee_yearly: { label: "Crypto borrow fee for a short kept overnight, a year", show: (v) => `${pct(v)} (${nightly(v, 2000)} a night on $2,000)` },
  loan_interest_yearly: { label: "Loan interest on money owed at midnight, a year", show: (v) => `${pct(v)} (${nightly(v, 10000)} a night on $10,000)` },
};

function SettingsSection({ header, number }: { header: SimHeader; number: number }) {
  const s = header.settings as Record<string, unknown>;
  const account = header.starting_value;
  const risk = (s.risk_profile ?? null) as Record<string, unknown> | null;
  const costs = (s.trading_costs ?? {}) as Record<string, unknown>;
  const stops = (s.stop_prices ?? null) as { multiples?: number[]; distance_cap?: number } | null;
  const jev = (s.jev ?? null) as Record<string, unknown> | null;
  const shown = new Set(["risk_profile", "trading_costs", "stop_prices", "jev", "starting_value", "reading_version"]);
  const others = Object.entries(s).filter(([k]) => !shown.has(k));

  return (
    <section className="mt-10">
      <SectionHeading number={number} title="Settings" says="Every number the sim ran with" />
      <div className="grid gap-8 lg:grid-cols-2">
        <SettingsBox title={`Risk profile${risk?.name ? `: ${String(risk.name)}` : ""}`}>
          {risk === null ? (
            <SettingRow label="No risk profile" text="Holding never trades, so no limits apply" />
          ) : (
            Object.entries(risk)
              .filter(([k]) => k !== "name")
              .map(([k, v]) =>
                k === "size_buckets" && Array.isArray(v) ? (
                  <SettingRow key={k} label="Size buckets: the sizes Jev chooses among" text={(v as number[]).map((x) => `${pct(x)} (${dollars(x * account)})`).join(", ")} />
                ) : (
                  <SettingRow key={k} label={RISK[k]?.label ?? k} text={typeof v === "number" && RISK[k] ? RISK[k].show(v, account) : JSON.stringify(v)} />
                ),
              )
          )}
        </SettingsBox>
        <SettingsBox title="Trading costs">
          {Object.entries(costs).map(([k, v]) => (
            <SettingRow key={k} label={COSTS[k]?.label ?? k} text={typeof v === "number" && COSTS[k] ? COSTS[k].show(v, account) : JSON.stringify(v)} />
          ))}
          {stops && (
            <>
              <SettingRow label="Stop prices: tight, medium and wide, in typical moves from the price" text={`${(stops.multiples ?? []).join(", ")} (at $100 with a $0.60 typical move, a long's are ${(stops.multiples ?? []).map((m) => `$${(100 - 0.6 * m).toFixed(2)}`).join(", ")})`} />
              <SettingRow label="Stop price distance cap: the furthest from the price" text={stops.distance_cap === undefined ? "--" : `${pct(stops.distance_cap)} ($${(stops.distance_cap * 100).toFixed(2)} at $100)`} />
            </>
          )}
        </SettingsBox>
        <SettingsBox title="The sim">
          <SettingRow label="Dataset" text={String(header.dataset)} />
          <SettingRow label="Kind and variant" text={`${header.kind}, ${header.variant}`} />
          <SettingRow label="Starting amount" text={dollars(account)} />
          <SettingRow label="Estimated cost of the models" text={header.estimated_cost_usd === null ? "--" : dollarsAndCents(header.estimated_cost_usd)} />
          <SettingRow label="Spending cap: the sim stops itself there" text={header.spending_cap_usd === null ? "none" : dollarsAndCents(header.spending_cap_usd)} />
          <SettingRow label="Code version" text={header.code_version ?? "--"} />
          {others.map(([k, v]) => (
            <SettingRow key={k} label={k} text={JSON.stringify(v)} />
          ))}
        </SettingsBox>
        <SettingsBox title="Models">
          {jev === null ? (
            <SettingRow label="None" text="Holding calls no model" />
          ) : (
            <>
              {Object.entries(jev).map(([k, v]) => (
                <SettingRow key={k} label={`Jev: ${k.replaceAll("_", " ")}`} text={String(v)} />
              ))}
              <SettingRow label="Jev's reading version: a fingerprint of the wording it is sent" text={String(s.reading_version ?? "--")} />
            </>
          )}
        </SettingsBox>
      </div>
    </section>
  );
}

function SettingsBox({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="border-[1.5px] border-rule">
      <div className="border-b-[1.5px] border-rule px-[2ch] py-1 font-mono text-[13.5px] tracking-widest text-dim">{title}</div>
      <dl className="px-[2ch] py-2">{children}</dl>
    </div>
  );
}

function SettingRow({ label, text }: { label: string; text: string }) {
  return (
    <div className="flex flex-wrap justify-between gap-x-[2ch] py-[.3rem]">
      <dt className="text-[14px] text-dim">{label}</dt>
      <dd className="font-mono text-[15px] text-pale">{text}</dd>
    </div>
  );
}
