// The Trading sim page (spec appendix 7, section 5). This file holds its top half: the header and
// key figures, the chart, the three meters, open positions and latest orders, and the notable
// moments; `SimReport` the bottom half. While the sim is in progress the quick figures are asked
// for every second, never before the last answer came back; a finished or stopped sim's page asks
// once. Stop and Resume sit in the header (appendix 8, section 8.7); after either, the page reads
// the sim again.
import { useEffect, useRef, useState } from "react";

import {
  fetchChart,
  fetchLive,
  fetchSimHeader,
  resumeSim,
  stopSim,
  type Chart,
  type ChartLine,
  type LiveFigures,
  type SimHeader,
} from "./api/client";
import {
  AssetTag,
  DirectionWords,
  ErrorBox,
  KeyFigure,
  Pair,
  PriceTag,
  SectionHeading,
  TrailButton,
  decisionWords,
  orderWords,
  statusWords,
} from "./pieces";
import { DecisionTrailPanel } from "./DecisionTrailPanel";
import { MomentPanel } from "./MomentPanel";
import { SimChart } from "./SimChart";
import { SimReport } from "./SimReport";
import {
  dayAndTime,
  dollars,
  dollarsAndCents,
  fromApi,
  signedDollars,
  stepTime,
  units,
} from "./format";

// A setting (appendix 8, section 8.9); the 20-second one is in `SimReport`.
const LIVE_REFRESH_MS = 1_000;

// New points are added to their line; a point the line already has is skipped.
function withNewPoints(lines: ChartLine[], live: LiveFigures): ChartLine[] {
  if (live.new_points.length === 0) return lines;
  return lines.map((line) => {
    const last = line.points.length ? line.points[line.points.length - 1].step : -Infinity;
    const added = live.new_points
      .filter((p) => p.sim_id === line.sim_id && p.step > last)
      .map(({ step, value }) => ({ step, value }));
    return added.length ? { ...line, points: [...line.points, ...added] } : line;
  });
}

// The step the page has points up to: the earliest of the lines' last points.
function pointsUpTo(lines: ChartLine[]): number | null {
  const lasts = lines.filter((l) => l.points.length).map((l) => l.points[l.points.length - 1].step);
  return lasts.length ? Math.min(...lasts) : null;
}

export function SimPage({ id }: { id: number }) {
  const [header, setHeader] = useState<SimHeader | null>(null);
  const [chart, setChart] = useState<Chart | null>(null);
  const [live, setLive] = useState<LiveFigures | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [momentStep, setMomentStep] = useState<number | null>(null);
  const [trail, setTrail] = useState<string | null>(null); // the decision whose trail is open
  const [reloads, setReloads] = useState(0); // goes up after Stop or Resume: the sim is read again
  const linesRef = useRef<ChartLine[]>([]);

  useEffect(() => {
    let stopped = false;
    let timer: number | undefined;
    let wasInProgress = false;

    async function loadAll() {
      const [h, c, l] = await Promise.all([fetchSimHeader(id), fetchChart(id), fetchLive(id, null)]);
      if (stopped) return null;
      linesRef.current = c.lines;
      setHeader(h);
      setChart(c);
      setLive(l);
      return l;
    }

    async function loadLive() {
      const l = await fetchLive(id, pointsUpTo(linesRef.current));
      if (stopped) return null;
      // A line with no points yet is left out of `after_step`, so its first points could come
      // after a gap: when one starts, the whole chart is read again once.
      const empty = new Set(linesRef.current.filter((x) => !x.points.length).map((x) => x.sim_id));
      if (l.new_points.some((p) => empty.has(p.sim_id))) {
        const c = await fetchChart(id);
        if (stopped) return null;
        linesRef.current = c.lines;
      } else {
        linesRef.current = withNewPoints(linesRef.current, l);
      }
      setChart((c) => (c ? { ...c, lines: linesRef.current, ticks: l.ticks } : c));
      setLive(l);
      return l;
    }

    let loaded = false; // the header and the whole chart are in

    async function tick() {
      let again = true;
      try {
        const l = loaded ? await loadLive() : await loadAll();
        if (l === null) return;
        loaded = true;
        setError(null);
        if (wasInProgress && !l.in_progress) await loadAll(); // it just ended: read it whole once
        wasInProgress = l.in_progress;
        again = l.in_progress;
      } catch (problem) {
        if (stopped) return;
        setError(problem instanceof Error ? problem.message : String(problem));
      }
      if (again && !stopped) timer = window.setTimeout(() => void tick(), LIVE_REFRESH_MS);
    }

    void tick();
    return () => {
      stopped = true;
      window.clearTimeout(timer);
    };
  }, [id, reloads]);

  if (!header || !chart || !live) {
    return (
      <section>
        <BackLink />
        {error ? <ErrorBox title="Cannot reach the API" text={`${error}. Asking again shortly.`} /> : (
          <p className="text-center font-mono text-dim">Loading...</p>
        )}
      </section>
    );
  }

  const running = live.in_progress;
  const replayed = live.replayed_at ? dayAndTime(fromApi(live.replayed_at)) : "Not started";
  const gap = live.holding_value === null ? null : live.account_value - live.holding_value;

  return (
    <section>
      <BackLink />
      <h1 className="mb-3 text-center text-[2.1rem] leading-tight tracking-[.02em]">{header.name}</h1>
      <div className="mb-6 flex flex-wrap justify-center gap-3 font-mono text-[13.5px] tracking-wider">
        <Pair name="Status" value={statusWords(live)} />
        <Pair
          name="Day"
          value={`${running ? Math.min(live.days_done + 1, live.days_total) : live.days_done} of ${live.days_total}`}
        />
        <Pair name="Replaying" value={replayed} />
        <Pair name="Step" value={`${live.step_reached ?? "--"} of ${header.last_step}`} />
        <Pair name="Kind" value={header.kind} />
        <StopOrResume live={live} header={header} onDone={() => setReloads((n) => n + 1)} />
      </div>
      {header.failure_reason && (
        <div className="mb-6">
          <ErrorBox title="Why it failed" text={header.failure_reason} />
        </div>
      )}
      {error && (
        <div className="mb-6">
          <ErrorBox title="Cannot reach the API" text={`${error}. Asking again shortly.`} />
        </div>
      )}

      <div className="mb-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <KeyFigure name="Account value" figure={dollars(live.account_value)} says={`Started with ${dollars(header.starting_value)}: ${signedDollars(live.account_value - header.starting_value)} so far`} first />
        <KeyFigure
          name="Holding the five assets"
          figure={live.holding_value === null ? "--" : dollars(live.holding_value)}
          says={gap === null ? "Not worked out yet for this moment" : `The sim is ${signedDollars(gap)} against it`}
        />
        <KeyFigure name="Trades" figure={String(live.trades)} says="Positions opened so far" />
        <KeyFigure
          name="Spent on the models"
          figure={dollarsAndCents(live.spent_usd)}
          says={live.spending_cap_usd === null ? "No spending cap" : `Of a ${dollarsAndCents(live.spending_cap_usd)} cap: the sim stops itself there`}
        />
      </div>

      <SimChart
        lines={chart.lines}
        ticks={chart.ticks}
        firstStep={header.first_step}
        lastStep={header.last_step}
        startingValue={chart.starting_value}
        stepsStartAt={header.steps_start_at}
        windowSteps={chart.window_steps}
        onPick={setMomentStep}
      />
      <p className="mt-2 font-mono text-[13.5px] tracking-wider text-dim">
        Solid: this sim, hatched beneath / dashed: holding the five assets / faint: other sims over the
        same days (a second one dash-dotted) / dotted: the starting amount / ticks along the bottom: a trade opened. Point at the
        chart for that moment; click to open it.
      </p>

      <div className="mt-8 grid gap-8 lg:grid-cols-[1fr_340px]">
        <div>
          {running && <Meters live={live} />}
          {running && <Now live={live} header={header} onOpenTrail={setTrail} />}
          {!running && (
            <p className="font-mono text-[13.5px] tracking-wider text-dim">
              The meters and open positions show while a sim runs.
              {live.open_positions.length > 0 && ` It stopped holding ${live.open_positions.length} open position(s).`}
            </p>
          )}
        </div>
        <NotableMoments live={live} />
      </div>

      <SimReport id={id} header={header} inProgress={running} firstNumber={running ? 2 : 1} onOpenTrail={setTrail} />

      {momentStep !== null && header.steps_start_at && (
        <MomentPanel
          simId={id}
          step={momentStep}
          at={stepTime(header.steps_start_at, momentStep)}
          onClose={() => setMomentStep(null)}
        />
      )}
      {trail !== null && <DecisionTrailPanel key={trail} simId={id} decision={trail} onClose={() => setTrail(null)} />}
    </section>
  );
}

// Stop while the sim is in progress; Resume once it is stopped or not responding. A sim its
// spending cap stopped is resumed with a new cap.
function StopOrResume({ live, header, onDone }: { live: LiveFigures; header: SimHeader; onDone: () => void }) {
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [cap, setCap] = useState("");
  const canStop = live.status === "created" || live.status === "running";
  const canResume = live.status === "stopped" || live.not_responding;
  const needsCap = live.status === "stopped" && live.stop_reason === "spending cap";
  if (!canStop && !canResume) return null;

  async function act(what: () => Promise<unknown>) {
    setBusy(true);
    setProblem(null);
    try {
      await what();
      onDone();
    } catch (error) {
      setProblem(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  }

  function stop() {
    if (!window.confirm(`Stop ${header.name} now? The step it is working on is thrown away and redone on resume.`)) return;
    void act(() => stopSim(header.id));
  }

  function resume() {
    const newCap = needsCap ? Number(cap) : null;
    if (needsCap && !(newCap! > 0)) {
      setProblem(`Give a new cap above the ${dollarsAndCents(live.spent_usd)} it has spent.`);
      return;
    }
    void act(() => resumeSim(header.id, newCap));
  }

  const button =
    "cursor-pointer border-[1.5px] border-amber px-[1.5ch] py-1 text-amber uppercase hover:bg-amber hover:text-screen disabled:cursor-wait disabled:opacity-60";
  return (
    <span className="flex flex-wrap items-stretch gap-3">
      {canResume && needsCap && (
        <label className="flex border-[1.5px] border-rule">
          <span className="border-r-[1.5px] border-rule px-[1.5ch] py-1 text-dim">New cap $</span>
          <input
            type="number"
            min="0"
            step="0.01"
            value={cap}
            onChange={(e) => setCap(e.target.value)}
            className="w-[9ch] bg-transparent px-[1ch] text-pale"
            aria-label="New spending cap in dollars"
          />
        </label>
      )}
      {canResume && (
        <button type="button" className={button} disabled={busy} onClick={resume}>
          {busy ? "Resuming..." : "Resume"}
        </button>
      )}
      {canStop && (
        <button type="button" className={button} disabled={busy} onClick={stop}>
          {busy ? "Stopping..." : "Stop"}
        </button>
      )}
      {problem && (
        <span role="alert" className="basis-full text-center text-amber">
          Refused: {problem}
        </span>
      )}
    </span>
  );
}

function BackLink() {
  return (
    <a href="#/" className="mb-4 inline-block font-mono text-[13.5px] tracking-wider text-dim hover:text-amber">
      &lt; Trading sims
    </a>
  );
}

function Meter({ name, figure, of, share, says }: { name: string; figure: string; of: string; share: number | null; says: string }) {
  const filled = share === null ? 0 : Math.max(0, Math.min(1, share));
  return (
    <div>
      <div className="font-mono text-[13.5px] tracking-wider text-dim">{name}</div>
      <div className="font-mono text-[1.15rem]">
        {figure} <span className="text-[13.5px] text-dim">{of}</span>
      </div>
      <div className="my-1 h-[6px] border border-rule" role="meter" aria-valuenow={filled} aria-valuemin={0} aria-valuemax={1} aria-label={name}>
        <div className="h-full bg-amber" style={{ width: `${filled * 100}%` }} />
      </div>
      <div className="font-mono text-[12.5px] tracking-wider text-dim">{says}</div>
    </div>
  );
}

function Meters({ live }: { live: LiveFigures }) {
  const m = live.meters;
  const lossShare = m.daily_loss_limit_usd ? Math.max(0, -m.day_change) / m.daily_loss_limit_usd : null;
  const heldShare = m.exposure_limit_usd ? m.held_usd / m.exposure_limit_usd : null;
  const spentShare = live.spending_cap_usd ? live.spent_usd / live.spending_cap_usd : null;
  return (
    <div className="mb-8 grid gap-6 md:grid-cols-3">
      <Meter
        name="Today, since midnight UTC"
        figure={signedDollars(m.day_change)}
        of={m.daily_loss_limit_usd === null ? "no daily loss limit" : `of -${dollars(m.daily_loss_limit_usd)} allowed`}
        share={lossShare}
        says={m.daily_loss_reached ? "Daily loss limit reached: no new trades today" : "Daily loss limit: past it, code blocks new trades for the day"}
      />
      <Meter
        name="Held in positions"
        figure={dollars(m.held_usd)}
        of={m.exposure_limit_usd === null ? "no exposure limit" : `of ${dollars(m.exposure_limit_usd)} allowed`}
        share={heldShare}
        says="Exposure limit: the most all positions may add up to"
      />
      <Meter
        name="Spent on the models"
        figure={dollarsAndCents(live.spent_usd)}
        of={live.spending_cap_usd === null ? "no cap" : `of ${dollarsAndCents(live.spending_cap_usd)} cap`}
        share={spentShare}
        says="Spending cap: the sim stops itself there"
      />
    </div>
  );
}

const th = "border-b border-rule py-[.4rem] pr-[2ch] font-mono text-[13.5px] font-light tracking-wider text-dim";
const td = "py-[.42rem] pr-[2ch] align-top font-mono text-[15px]";

// A position's asset leads to its trade's page; "trail" and a decision's words open how it was
// decided.
function Now({ live, header, onOpenTrail }: { live: LiveFigures; header: SimHeader; onOpenTrail: (decision: string) => void }) {
  return (
    <div>
      <SectionHeading number={1} title="Now" says="What the sim holds, and its latest orders" />
      {live.open_positions.length === 0 ? (
        <p className="mb-6 font-mono text-dim">No open positions.</p>
      ) : (
        <div className="mb-6 overflow-x-auto">
          <table className="w-full border-separate border-spacing-0">
            <thead>
              <tr>
                <th className={`${th} text-left`}>Asset</th>
                <th className={`${th} text-left`}>Direction</th>
                <th className={`${th} text-right`}>Units</th>
                <th className={`${th} text-right`}>Bought at</th>
                <th className={`${th} text-right`}>Price now</th>
                <th className={`${th} text-right`}>Stop price</th>
                <th className={`${th} text-right`}>So far</th>
              </tr>
            </thead>
            <tbody>
              {live.open_positions.map((p) => (
                <tr key={p.position} className="hover:bg-amber hover:text-screen [&:hover_*]:text-screen">
                  <td className={td}>
                    <a href={`#/sims/${header.id}/trades/${p.position}`} className="underline">
                      <AssetTag asset={p.asset} />
                    </a>
                    <div className="text-[12.5px] text-dim">
                      opened {p.opened_at ? dayAndTime(fromApi(p.opened_at)) : `step ${p.opened_step}`}
                    </div>
                    <TrailButton decision={p.decision} onOpenTrail={onOpenTrail} />
                  </td>
                  <td className={td}>{p.direction}</td>
                  <td className={`${td} text-right`}>{units(p.units)}</td>
                  <td className={`${td} text-right`}><PriceTag price={p.entry_price} /></td>
                  <td className={`${td} text-right`}>{p.price_now ? <PriceTag price={p.price_now} /> : "--"}</td>
                  <td className={`${td} text-right`}>{p.stop_price ? <PriceTag price={p.stop_price} /> : "none"}</td>
                  <td className={`${td} text-right`}>{p.profit_so_far === null ? "--" : signedDollars(p.profit_so_far)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-1 font-mono text-[12.5px] tracking-wider text-dim">
            Real prices lead; the price the agent saw follows in brackets. So far: what the position
            has made or lost at the price now, after trading costs.
          </p>
          <DirectionWords />
        </div>
      )}

      <div className="mb-2 font-mono text-[13.5px] tracking-wider text-dim">Latest decisions, newest first</div>
      {live.latest_decisions.length === 0 ? (
        <p className="mb-6 font-mono text-dim">No decisions yet.</p>
      ) : (
        <ol className="mb-6 font-mono text-[15px]">
          {live.latest_decisions.map((d) => (
            <li key={`${d.step}-${d.asset.masked_id}`} className="flex flex-wrap gap-x-[2ch] py-[.2rem]">
              <span className="w-[22ch] text-dim">{d.at ? dayAndTime(fromApi(d.at)) : `step ${d.step}`}</span>
              <AssetTag asset={d.asset} />
              <button type="button" onClick={() => onOpenTrail(d.decision)} className="cursor-pointer text-left hover:text-amber">
                {decisionWords(d)}
              </button>
            </li>
          ))}
        </ol>
      )}

      <div className="mb-2 font-mono text-[13.5px] tracking-wider text-dim">Latest orders, newest first</div>
      {live.latest_orders.length === 0 ? (
        <p className="font-mono text-dim">No orders yet.</p>
      ) : (
        <ol className="font-mono text-[15px]">
          {live.latest_orders.map((o) => (
            <li key={`${o.step_decided}-${o.asset.masked_id}-${o.kind}-${o.status}`} className="flex flex-wrap gap-x-[2ch] py-[.2rem]">
              <span className="w-[22ch] text-dim">
                {o.decided_at ? dayAndTime(fromApi(o.decided_at)) : `step ${o.step_decided}`}
              </span>
              <AssetTag asset={o.asset} />
              <span>{orderWords(o)}</span>
            </li>
          ))}
        </ol>
      )}
      {header.variant === "buy_hold" && (
        <p className="mt-2 font-mono text-[12.5px] tracking-wider text-dim">
          Holding buys each asset once, on the first step, and keeps it.
        </p>
      )}
    </div>
  );
}

const MOMENT_WORDS: Record<string, string> = {
  restarted: "Restarted from its last stored step",
  "forced close": "Forced close: code closed every position",
  "daily loss limit tripped": "Daily loss limit reached",
  "spending cap reached": "Spending cap reached",
  stopped: "Stopped",
  "an LLM limit hit": "An LLM limit hit",
  "an unknown episode ID dropped": "An unknown episode ID dropped",
  "a failed reply": "A failed reply",
};

function NotableMoments({ live }: { live: LiveFigures }) {
  return (
    <aside>
      <div className="mb-3 border-[1.5px] border-rule">
        <div className="bg-amber px-[2ch] py-1 font-mono text-[13.5px] tracking-widest text-screen">Notable moments</div>
        {live.notable_moments.length === 0 ? (
          <p className="px-[2ch] py-3 font-mono text-[13.5px] text-dim">None so far.</p>
        ) : (
          <ol className="px-[2ch] py-2 font-mono text-[13.5px] tracking-wider">
            {[...live.notable_moments].reverse().map((m) => (
              <li key={`${m.step}-${m.kind}`} className="py-1">
                <div className="text-dim">{m.at ? dayAndTime(fromApi(m.at)) : `step ${m.step}`}</div>
                <div>{MOMENT_WORDS[m.kind] ?? m.kind}</div>
              </li>
            ))}
          </ol>
        )}
      </div>
      <p className="font-mono text-[12.5px] tracking-wider text-dim">
        Daily loss limit reached, stopped, restarted, an LLM limit hit, a failed reply, a forced close,
        the spending cap reached.
      </p>
    </aside>
  );
}
