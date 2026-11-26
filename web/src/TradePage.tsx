// The Trade page (spec appendix 7, section 7): one trade reviewed the way a trader would. The
// price chart around it, the order, every position review (told apart from the steps where the
// position screen said no), the nightly charges, and memory: the entry memory beside each
// review's fresh memory. Clicking a review opens its decision trail. A trade's records no longer
// change once it is closed, so the page is read once (and again on coming back to the tab).
import { useCallback, useState, type ReactNode } from "react";

import {
  fetchTrade,
  fetchTrail,
  type DecisionTrail,
  type TradePage as TradePageAnswer,
} from "./api/client";
import { DecisionTrailPanel } from "./DecisionTrailPanel";
import {
  AssetTag,
  DirectionWords,
  ENDINGS,
  ErrorBox,
  Pair,
  PriceTag,
  SectionHeading,
  fieldLabel as label,
  limitWords,
  type OpenTrail,
  when,
} from "./pieces";
import { TradeChart } from "./TradeChart";
import { useRead } from "./useRead";
import { dollars, dollarsAndCents, signedDollars, units } from "./format";

type PositionStep = TradePageAnswer["position_steps"][number];
type MemoryRead = TradePageAnswer["entry_memory"];
type TrailKey = DecisionTrail["key"][number];

const note = "font-mono text-[12.5px] tracking-wider text-dim";

const share = (value: number) => `${Math.round(value * 100)}%`;

export function TradePage({ simId, trade }: { simId: number; trade: number }) {
  const read = useCallback(() => fetchTrade(simId, trade), [simId, trade]);
  const { data: page, error } = useRead(read);
  const [trail, setTrail] = useState<string | null>(null);
  const closeTrail = useCallback(() => setTrail(null), []);

  return (
    <section>
      <a href={`#/sims/${simId}`} className="mb-4 inline-block font-mono text-[13.5px] tracking-wider text-dim hover:text-amber">
        &lt; The sim
      </a>
      {error && <ErrorBox title="Cannot read this trade" text={error} />}
      {!page && !error && <p className="text-center font-mono text-dim">Loading...</p>}
      {page && <TradeBody simId={simId} page={page} onOpenTrail={setTrail} />}
      {trail !== null && <DecisionTrailPanel key={trail} simId={simId} decision={trail} onClose={closeTrail} />}
    </section>
  );
}

function TradeBody({ simId, page, onOpenTrail }: { simId: number; page: TradePageAnswer; onOpenTrail: OpenTrail }) {
  const t = page.trade;
  const reviews = page.position_steps.filter((s) => s.kind === "review").length;
  const saidNo = page.position_steps.length - reviews;
  return (
    <>
      <h1 className="mb-3 text-center text-[2.1rem] leading-tight tracking-[.02em]">
        Trade {t.position}: <AssetTag asset={t.asset} /> {t.direction}
      </h1>
      <div className="mb-6 flex flex-wrap justify-center gap-3 font-mono text-[13.5px] tracking-wider">
        <Pair name="Opened" value={when(t.opened_at, t.opened_step)} />
        <Pair name="Closed" value={t.closed_step === null ? "still open" : when(t.closed_at, t.closed_step)} />
        <Pair name="Ended" value={t.closing_reason ? (ENDINGS[t.closing_reason] ?? t.closing_reason) : "--"} />
        <Pair name="Result" value={t.profit_usd === null ? "--" : signedDollars(t.profit_usd)} />
        {t.decision && (
          <button
            type="button"
            onClick={() => onOpenTrail(t.decision!)}
            className="cursor-pointer border-[1.5px] border-amber px-[1.5ch] py-1 text-amber uppercase hover:bg-amber hover:text-screen"
          >
            How it was opened
          </button>
        )}
      </div>

      <SectionHeading number={1} title="The price around the trade" says="Closing price of each 15-minute bar, 32 bars either side" />
      <TradeChart page={page} onOpenTrail={onOpenTrail} />
      <p className={`mt-2 ${note}`}>
        Square: the entry (where the trade opened). Dot: where the trade closed. Dashed: the stop price,
        where code closes the trade at a loss: long at $100 with a stop price of $97, code sells
        once the price falls to $97, losing about $3 a share. Shaded: while the trade was open. Ticks along the bottom: tall
        for a position review, short for a step where the position screen said no. Prices: the real one;
        the one the agent saw follows in brackets in the readout.
      </p>
      <DirectionWords />

      <div className="mt-10">
        <SectionHeading number={2} title="The order" says="Size chosen, size placed, and costs" />
        <Order page={page} />
      </div>

      <div className="mt-10">
        <SectionHeading
          number={3}
          title="Position reviews"
          says={`${reviews} review${reviews === 1 ? "" : "s"}, ${saidNo} screen${saidNo === 1 ? "" : "s"} said no`}
        />
        <PositionSteps steps={page.position_steps} onOpenTrail={onOpenTrail} />
      </div>

      <div className="mt-10">
        <SectionHeading number={4} title="Nightly charges" says="Paid for holding past midnight UTC" />
        <NightlyCharges page={page} />
      </div>

      <div className="mt-10">
        <SectionHeading number={5} title="Memory" says="What Jev read from past trades" />
        <Memory simId={simId} page={page} onOpenTrail={onOpenTrail} />
      </div>
    </>
  );
}

function OrderRow({ name, children }: { name: string; children: ReactNode }) {
  return (
    <div className="contents">
      <dt className="text-dim">{name}</dt>
      <dd className="text-right text-pale">{children}</dd>
    </div>
  );
}

function Order({ page }: { page: TradePageAnswer }) {
  const o = page.order;
  const t = page.trade;
  return (
    <div className="grid gap-8 lg:grid-cols-[minmax(0,560px)_1fr]">
      <dl className="grid grid-cols-[1fr_auto] gap-x-[2ch] gap-y-1 font-mono text-[15px]">
        <OrderRow name="Size Jev chose">{o.amount_chosen_usd === null ? "--" : dollars(o.amount_chosen_usd)}</OrderRow>
        <OrderRow name="Size placed">{dollars(o.amount_placed_usd)}</OrderRow>
        <OrderRow name="Trimmed by">{o.limited_by ? limitWords(o.limited_by) : "no limit: placed as chosen"}</OrderRow>
        <OrderRow name="Units">{t.units === null ? "--" : units(t.units)}</OrderRow>
        <OrderRow name="Entry price">{t.entry_price ? <PriceTag price={t.entry_price} /> : "--"}</OrderRow>
        <OrderRow name="Stop price">{page.stop_price ? <PriceTag price={page.stop_price} /> : "none"}</OrderRow>
        <OrderRow name="Exit price">{t.exit_price ? <PriceTag price={t.exit_price} /> : "still open"}</OrderRow>
        <OrderRow name="Slippage">{dollarsAndCents(o.slippage_usd)}</OrderRow>
        <OrderRow name="Commission or trading fee">{dollarsAndCents(o.commission_or_fee_usd)}</OrderRow>
        <OrderRow name="All trading costs">{t.trading_costs_usd === null ? "--" : dollarsAndCents(t.trading_costs_usd)}</OrderRow>
      </dl>
      <p className="text-[14px] text-dim">
        Jev names a size; code then trims it to fit the risk limits (caps on the account that code
        enforces). If Jev chose $3,000 and a limit allowed $1,500, $1,500 is placed. Slippage:
        the order filled a little worse than the bar's price, such as buying at $100.05 when the bar
        said $100.00. Commission (stocks): a flat charge per order, such as $1. Trading fee (crypto): a
        share of the order's value, such as 0.1% of $1,000, $1. The costs above are
        the entry order's; all trading costs adds every order of the trade and its nightly charges.
      </p>
    </div>
  );
}

const ANSWERS: Record<string, string> = {
  hold: "hold: keep it as it is",
  close: "close it",
  reduce: "make it smaller",
  add: "add to it",
};

function answerWords(s: PositionStep) {
  const words = s.answer ? (ANSWERS[s.answer] ?? s.answer) : "--";
  // The amount is the order carried out: for an add, after the limits, not the size Jev chose
  // (the trail shows both).
  if (s.amount_usd === null) return words;
  return s.answer === "add" ? `${words}; ${dollars(s.amount_usd)} after the limits` : `${words}, ${dollars(s.amount_usd)}`;
}

// A review stands out in an outlined box with its answer and Jev's probabilities; a step where the
// position screen said no is one faint line: nothing more was asked.
function PositionSteps({ steps, onOpenTrail }: { steps: PositionStep[]; onOpenTrail: OpenTrail }) {
  if (steps.length === 0) {
    return <p className="font-mono text-dim">The position was never looked at while open.</p>;
  }
  return (
    <>
      <ol className="grid gap-2">
        {steps.map((s) =>
          s.kind === "review" ? (
            <li key={s.step} className="border-[1.5px] border-rule px-[2ch] py-2">
              <div className="flex flex-wrap items-baseline gap-x-[2ch] font-mono text-[15px]">
                <span className="text-dim">{when(s.at, s.step)}</span>
                <span className="bg-amber px-[1ch] text-screen">{s.end_of_session ? "End-of-session review" : "Review"}</span>
                {s.screen_answer !== null && <span className="text-dim">screen: {share(s.screen_answer)} worth a closer look</span>}
                <span className="text-pale">Jev: {answerWords(s)}</span>
                {s.decision && (
                  <button type="button" onClick={() => onOpenTrail(s.decision!)} className="ml-auto cursor-pointer text-[13.5px] underline hover:text-pale">
                    open its trail
                  </button>
                )}
              </div>
              {s.probabilities.length > 0 && (
                <ul className="mt-2 grid gap-x-[3ch] gap-y-1 font-mono text-[13.5px] tracking-wider sm:grid-cols-4">
                  {s.probabilities.map((p) => (
                    <li key={p.option}>
                      <div className="flex justify-between">
                        <span className={p.option === s.answer ? "text-pale" : "text-dim"}>{p.option}</span>
                        <span>{share(p.probability)}</span>
                      </div>
                      <div className="h-[6px] border border-rule">
                        <div className="h-full bg-amber" style={{ width: `${Math.max(0, Math.min(1, p.probability)) * 100}%` }} />
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </li>
          ) : (
            <li key={s.step} className="flex flex-wrap items-baseline gap-x-[2ch] px-[2ch] py-1 font-mono text-[14px] text-dim">
              <span>{when(s.at, s.step)}</span>
              <span className="border border-dashed border-dim px-[1ch]">Screen said no</span>
              <span>
                {s.screen_answer === null ? "" : `${share(s.screen_answer)} worth a closer look; `}nothing more asked, held on its stop price
              </span>
              {s.decision && (
                <button type="button" onClick={() => onOpenTrail(s.decision!)} className="ml-auto cursor-pointer text-[12.5px] underline hover:text-amber">
                  trail
                </button>
              )}
            </li>
          ),
        )}
      </ol>
      <p className={`mt-2 ${note}`}>
        While a trade is open, Jev's position screen asks at each step whether it calls for action. A
        no means nothing more is asked: the trade is held, guarded by its stop price. A yes starts a
        review: Jev says hold, close, make it smaller or add to it, and how sure it is of each. 70%
        on hold means Jev rated holding the likeliest right answer. A stock is also reviewed before
        the market closes for the day (an end-of-session review), with no screen first.
      </p>
    </>
  );
}

const CHARGES: Record<string, string> = {
  borrow_fee: "Borrow fee",
  loan_interest: "Loan interest",
};

function NightlyCharges({ page }: { page: TradePageAnswer }) {
  const charges = page.nightly_charges;
  const total = charges.reduce((sum, c) => sum + c.amount_usd, 0);
  return (
    <>
      {charges.length === 0 ? (
        <p className="font-mono text-dim">None: the trade paid nothing for being held overnight.</p>
      ) : (
        <dl className="grid max-w-[560px] grid-cols-[auto_1fr_auto] gap-x-[2ch] gap-y-1 font-mono text-[15px]">
          {charges.map((c) => (
            <div key={`${c.step}-${c.kind}`} className="contents">
              <dt className="text-dim">{when(c.at, c.step)}</dt>
              <dd>{CHARGES[c.kind] ?? c.kind}</dd>
              <dd className="text-right text-pale">{dollarsAndCents(c.amount_usd)}</dd>
            </div>
          ))}
          <div className="contents">
            <dt className="text-dim">All together</dt>
            <dd />
            <dd className="text-right text-pale">{dollarsAndCents(total)}</dd>
          </div>
        </dl>
      )}
      <p className={`mt-2 ${note}`}>
        Borrow fee: a short (a bet the price falls) sells shares borrowed from the broker, who charges
        a little for each day they are kept: at 10% a year, a $2,000 short pays about 55 cents a day.
        Loan interest: what the account pays for money it borrowed to buy beyond its own cash: at 5%
        a year, a $10,000 loan costs about $1.37 a day.
      </p>
    </>
  );
}

// The asset key turns the masked IDs and rescaled prices memory was written in back into real ones; the
// Trade page has none of its own, so it is read from the trail of the decision that opened it.
function Memory({ simId, page, onOpenTrail }: { simId: number; page: TradePageAnswer; onOpenTrail: OpenTrail }) {
  const reviews = page.position_steps.filter((s) => s.kind === "review" && s.fresh_memory);
  const entry = page.entry_memory;
  const empty = (m: MemoryRead | null) => !m || (m.scorecard_lines.length === 0 && m.episodes.length === 0);
  if (empty(entry) && reviews.every((s) => empty(s.fresh_memory))) {
    return <p className="font-mono text-dim">Jev read no past trades for this one: the sim ran without memory, or memory was still empty.</p>;
  }
  return (
    <>
      <div className="grid gap-8 lg:grid-cols-2">
        <div>
          <MemoryHeading title="Entry memory" says="Read when the trade opened; kept, not read again" decision={entry.decision} onOpenTrail={onOpenTrail} />
          <MemoryBody memory={entry} />
        </div>
        <div>
          <MemoryHeading title="Fresh memory" says="Picked anew for each review's own moment" decision={null} onOpenTrail={onOpenTrail} />
          {reviews.length === 0 ? (
            <p className="font-mono text-dim">No reviews: nothing read after the entry.</p>
          ) : (
            reviews.map((s) => (
              <div key={s.step} className="mb-6">
                <div className="mb-2 flex flex-wrap items-baseline gap-x-[2ch] border-b border-rule pb-1 font-mono text-[13.5px] tracking-wider">
                  <span>
                    {s.end_of_session ? "End-of-session review" : "Review"}, {when(s.at, s.step)}
                  </span>
                  {s.decision && (
                    <button type="button" onClick={() => onOpenTrail(s.decision!)} className="ml-auto cursor-pointer text-dim underline hover:text-amber">
                      open its trail
                    </button>
                  )}
                </div>
                <MemoryBody memory={s.fresh_memory!} />
              </div>
            ))
          )}
        </div>
      </div>
      <p className={`mt-4 ${note}`}>
        Scorecard lines: how trades like this one went before, such as 11 closed trades, 4 of them wins.
        Past episodes: earlier moments Jev was shown, each with what was decided and how it ended. Both
        are word for word as Jev read them: assets by their masked IDs (disguised labels, so Jev
        cannot recall an asset's real history) and prices rescaled.
      </p>
      {page.trade.decision && <AssetKey simId={simId} decision={page.trade.decision} />}
    </>
  );
}

function MemoryHeading({
  title,
  says,
  decision,
  onOpenTrail,
}: {
  title: string;
  says: string;
  decision: string | null;
  onOpenTrail: OpenTrail;
}) {
  return (
    <div className="mb-3 border-[1.5px] border-rule">
      <div className="flex justify-between bg-amber px-[2ch] py-1 font-mono text-[13.5px] tracking-widest text-screen">
        <span>{title}</span>
        {decision && (
          <button type="button" onClick={() => onOpenTrail(decision)} className="cursor-pointer underline">
            open its trail
          </button>
        )}
      </div>
      <div className="px-[2ch] py-1 font-mono text-[12.5px] tracking-wider text-dim">{says}</div>
    </div>
  );
}

function MemoryBody({ memory }: { memory: MemoryRead }) {
  return (
    <>
      <div className={`mb-1 ${label}`}>Scorecard lines</div>
      {memory.scorecard_lines.length === 0 ? (
        <p className="mb-4 font-mono text-[14px] text-dim">None.</p>
      ) : (
        <ul className="mb-4 font-mono text-[14px] normal-case">
          {memory.scorecard_lines.map((line) => (
            <li key={line} className="border-b border-grid py-1">
              {line}
            </li>
          ))}
        </ul>
      )}
      <div className={`mb-1 ${label}`}>Past episodes, newest first</div>
      {memory.episodes.length === 0 ? (
        <p className="font-mono text-[14px] text-dim">None.</p>
      ) : (
        <ol>
          {memory.episodes.map((e, n) => (
            <li key={`${n}-${e.episode}`} className="mb-2 border-l-[1.5px] border-rule pl-[1.5ch]">
              <div className="font-mono text-[12.5px] tracking-wider text-dim">{e.episode || "--"}</div>
              <p className="font-mono text-[14px] whitespace-pre-line normal-case">{e.text}</p>
            </li>
          ))}
        </ol>
      )}
    </>
  );
}

const scale = new Intl.NumberFormat("en-US", { maximumSignificantDigits: 4 });

function AssetKey({ simId, decision }: { simId: number; decision: string }) {
  const read = useCallback(() => fetchTrail(simId, decision), [simId, decision]);
  const { data: trail } = useRead(read);
  if (!trail || trail.key.length === 0) return null;
  return (
    <div className="mt-4">
      <div className={`mb-1 ${label}`}>The asset key</div>
      <ul className="flex flex-wrap gap-3 font-mono text-[13.5px] tracking-wider">
        {trail.key.map((k: TrailKey) => (
          <li key={k.masked_id}>
            <Pair name={k.masked_id} value={`${k.name} (${k.ticker}), real price = shown / ${scale.format(k.price_scale)}`} />
          </li>
        ))}
      </ul>
      <p className={`mt-2 ${note}`}>
        To read a price in memory as it really was, divide it by the asset's scale: with a scale of
        0.5, a shown 100.00 was a real $200.
      </p>
    </div>
  );
}
