// The A moment side panel (spec appendix 7, section 4): opened by a click on the chart, it shows
// the account at that moment, the positions it held, and what it opened or closed around then.
import { useEffect, useState } from "react";

import { fetchMoment, type Moment } from "./api/client";
import { AssetTag, ErrorBox, PriceTag, orderWords } from "./pieces";
import { dayAndTime, dollars, fromApi, signedDollars, toApi, units } from "./format";

export function MomentPanel({ simId, step, at, onClose }: { simId: number; step: number; at: Date; onClose: () => void }) {
  const [moment, setMoment] = useState<Moment | null>(null);
  const [error, setError] = useState<string | null>(null);
  const asked = toApi(at);

  useEffect(() => {
    let stopped = false;
    setMoment(null);
    setError(null);
    fetchMoment(simId, asked)
      .then((m) => !stopped && setMoment(m))
      .catch((problem) => !stopped && setError(problem instanceof Error ? problem.message : String(problem)));
    return () => {
      stopped = true;
    };
  }, [simId, asked]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <aside
      aria-label="A moment"
      className="fixed top-0 right-0 bottom-0 z-30 w-[min(480px,100vw)] overflow-y-auto border-l-[1.5px] border-rule bg-screen"
    >
      <div className="flex items-center justify-between bg-amber px-[2ch] py-1 font-mono text-[13.5px] tracking-widest text-screen">
        <span>A moment</span>
        <button type="button" onClick={onClose} className="cursor-pointer font-mono tracking-widest uppercase" aria-label="Close the moment">
          Close [Esc]
        </button>
      </div>
      <div className="px-[2ch] py-4">
        <h2 className="text-[1.4rem] leading-tight">{dayAndTime(moment ? fromApi(moment.at) : at)}</h2>
        <p className="mb-4 font-mono text-[12.5px] tracking-wider text-dim">Step {moment?.step ?? step}</p>
        {error && <ErrorBox title="Cannot read this moment" text={error} />}
        {!moment && !error && <p className="font-mono text-dim">Loading...</p>}
        {moment && <MomentBody moment={moment} />}
      </div>
    </aside>
  );
}

function Row({ name, figure }: { name: string; figure: string }) {
  return (
    <div className="contents">
      <dt className="text-dim">{name}</dt>
      <dd className="text-right text-pale">{figure}</dd>
    </div>
  );
}

function MomentBody({ moment }: { moment: Moment }) {
  const a = moment.account;
  const gap = a && moment.holding_value !== null ? a.account_value - moment.holding_value : null;
  const hours = (moment.window_steps * 15) / 60;
  return (
    <>
      <div className="mb-1 font-mono text-[13.5px] tracking-wider text-dim">The account then</div>
      {a === null ? (
        <p className="mb-6 font-mono text-dim">The sim had stored nothing yet.</p>
      ) : (
        <dl className="mb-6 grid grid-cols-[1fr_auto] gap-x-[2ch] gap-y-1 font-mono text-[15px]">
          <Row name="Account value" figure={dollars(a.account_value)} />
          <Row name="Holding the five assets" figure={moment.holding_value === null ? "--" : dollars(moment.holding_value)} />
          <Row name="Against holding" figure={gap === null ? "--" : signedDollars(gap)} />
          <Row name="Since midnight UTC" figure={moment.since_midnight === null ? "--" : signedDollars(moment.since_midnight)} />
          <Row name="Since the start" figure={moment.since_start === null ? "--" : signedDollars(moment.since_start)} />
          <Row name="Cash" figure={dollars(a.cash)} />
          <Row name="Held in positions" figure={dollars(a.exposure)} />
          <Row name="Borrowed" figure={a.loan ? dollars(a.loan) : "none"} />
        </dl>
      )}
      <p className="mb-6 text-[14px] text-dim">
        Held in positions adds every position together, a bet on a fall counted like a bet on a rise.
        Borrowed is what the account owed for buying beyond its own cash.
      </p>

      <div className="mb-1 font-mono text-[13.5px] tracking-wider text-dim">Positions held then</div>
      {moment.positions.length === 0 ? (
        <p className="mb-6 font-mono text-dim">None.</p>
      ) : (
        <ul className="mb-6 font-mono text-[15px]">
          {moment.positions.map((p) => (
            <li key={p.position} className="border-b border-grid py-2">
              <div>
                <AssetTag asset={p.asset} /> {p.direction}
              </div>
              <div className="text-[13.5px] text-dim">
                {units(p.units)} units, bought at <PriceTag price={p.average_price} />
                {p.price_then && (
                  <>
                    , then <PriceTag price={p.price_then} />
                  </>
                )}
                {p.value_usd !== null && `, worth ${dollars(p.value_usd)}`}
              </div>
            </li>
          ))}
        </ul>
      )}

      <div className="mb-1 font-mono text-[13.5px] tracking-wider text-dim">
        Opened or closed within {hours} h either side
      </div>
      {moment.nearby.length === 0 ? (
        <p className="font-mono text-dim">Nothing.</p>
      ) : (
        <ol className="font-mono text-[14px]">
          {moment.nearby.map((o) => (
            <li key={`${o.step_decided}-${o.asset.masked_id}-${o.kind}`} className="py-1">
              <div className="text-dim">
                {o.step_carried_out !== null && moment.at
                  ? `${o.step_carried_out - moment.step >= 0 ? "+" : ""}${((o.step_carried_out - moment.step) * 15) / 60} h`
                  : ""}
              </div>
              <AssetTag asset={o.asset} /> {orderWords(o)}
            </li>
          ))}
        </ol>
      )}
    </>
  );
}
