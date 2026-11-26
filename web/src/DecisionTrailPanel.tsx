// The decision trail side panel (spec appendix 7, section 6): opened by a click on a trade, an
// open position or a decision, it shows everything asked and answered on the way to it, as a
// strip of boxes, one per stop. Clicking a stop shows its messages word for word from storage,
// masked IDs and rescaled prices kept, with the asset key beside them that turns both back into
// real ones (spec appendix 8, section 13).
import { useCallback, useState } from "react";

import { fetchTrail, type DecisionTrail } from "./api/client";
import { AssetTag, ErrorBox, FigureRows, SidePanel, limitWords } from "./pieces";
import { dayAndTime, dollars, dollarsAndCents, fromApi, price } from "./format";
import { useRead } from "./useRead";

type Stop = DecisionTrail["stops"][number];
type Message = Stop["messages"][number];
type Order = NonNullable<DecisionTrail["order"]>;
type KeyLine = DecisionTrail["key"][number];

// The full strip of each kind, left to right. A trail that stopped early (a full evaluation that
// picked no trade, a position review that held) shows the stops it never reached as empty boxes.
const STRIPS: Record<DecisionTrail["kind"], string[]> = {
  full_evaluation: ["screen", "memory", "pick", "size", "limits", "order"],
  position_review: ["position screen", "memory", "answer", "limits", "order"],
  screen: ["screen"],
  position_screen: ["position screen"],
};

// Each stop's title, and what it covers in plain words, by the name the API gives it.
const STOPS: Record<string, { title: string; says: string }> = {
  screen: { title: "Screen", says: "Is a full evaluation worth running now? Jev's cheap yes-or-no question." },
  memory: {
    title: "Memory",
    says: "Which past episodes Jev reads: what the LLM was sent, each lookup it made in memory and what came back, and its answer with its note.",
  },
  pick: { title: "Pick", says: "Which trade, if any: Jev's request and answer." },
  size: { title: "Size", says: "How much money Jev chose to put in." },
  limits: { title: "Limits", says: "What code trimmed: the size Jev chose, the size after trimming, and which limit trimmed it." },
  order: { title: "Order", says: "The order placed and the costs charged." },
  "position screen": {
    title: "Position screen",
    says: "Is a position review worth running now? Jev's cheap yes-or-no question about an open position.",
  },
  answer: {
    title: "Jev's answer",
    says: "What to do with the position (hold, close, reduce or add) and how much: Jev's requests and answers.",
  },
};

const stopTitle = (name: string) => STOPS[name]?.title ?? name;

// The decision's kind, and what it is in plain words.
function kindWords(trail: DecisionTrail): [string, string] {
  if (trail.kind === "full_evaluation")
    return ["a full evaluation", "Jev's long look at an asset with no position, ending in a trade or none."];
  if (trail.kind === "position_review" && trail.end_of_session)
    return [
      "an end-of-session review",
      "The review every open stock position gets near the market's close, with no position screen first: keep it overnight or not.",
    ];
  if (trail.kind === "position_review")
    return ["a position review", "Jev's long look at an open position: hold it, close it, make it smaller, or add to it."];
  if (trail.kind === "position_screen")
    return ["a position screen", "Jev's quick question about an open position: is a position review worth running?"];
  return ["a screen", "Jev's quick question about an asset with no position: is a full evaluation worth running?"];
}

export function DecisionTrailPanel({ simId, decision, onClose }: { simId: number; decision: string; onClose: () => void }) {
  const read = useCallback(() => fetchTrail(simId, decision), [simId, decision]);
  const { data: trail, error } = useRead(read);

  return (
    <SidePanel title="Decision trail" wide onClose={onClose}>
      {error && <ErrorBox title="Cannot read this decision trail" text={error} />}
      {!trail && !error && <p className="font-mono text-dim">Loading...</p>}
      {trail && <TrailBody simId={simId} trail={trail} />}
    </SidePanel>
  );
}

function TrailBody({ simId, trail }: { simId: number; trail: DecisionTrail }) {
  const [chosen, setChosen] = useState(trail.stops[0]?.name ?? "");
  const stop = trail.stops.find((s) => s.name === chosen);
  // An end-of-session review has no position screen: its strip starts at memory.
  const strip = STRIPS[trail.kind].filter((name) => !(trail.end_of_session && name === "position screen"));
  const [kind, kindSays] = kindWords(trail);

  return (
    <>
      <h2 className="mb-1 text-[1.4rem] leading-tight">
        <AssetTag asset={trail.asset} />: {kind}
      </h2>
      <p className="text-[14px] text-dim">{kindSays}</p>
      <p className="mb-4 font-mono text-[12.5px] tracking-wider text-dim">
        {trail.at ? dayAndTime(fromApi(trail.at)) : `Step ${trail.step}`} / step {trail.step} / decision {trail.decision}
        {trail.position !== null && (
          <>
            {" / "}
            <a href={`#/sims/${simId}/trades/${trail.position}`} className="underline hover:text-amber">
              trade {trail.position}
            </a>
          </>
        )}
      </p>

      <ol className="mb-1 flex items-stretch font-mono text-[13px] tracking-wider" aria-label="The stops">
        {strip.map((name, i) => {
          const reached = trail.stops.find((s) => s.name === name);
          return (
            <li key={name} className="flex flex-1 items-stretch">
              {i > 0 && <span className="self-center px-[.5ch] text-dim">&gt;</span>}
              {reached ? (
                <StopBox stop={reached} chosen={reached.name === chosen} onChoose={() => setChosen(reached.name)} />
              ) : (
                <div className="flex-1 border-[1.5px] border-dashed border-grid px-[1ch] py-1 normal-case text-dim">
                  <div>{stopTitle(name)}</div>
                  <div className="text-[12px]">not reached</div>
                </div>
              )}
            </li>
          );
        })}
      </ol>
      <p className="mb-5 font-mono text-[12px] tracking-wider text-dim">Click a box to read what passed at that stop.</p>

      {stop && <StopDetail stop={stop} trail={trail} />}
    </>
  );
}

function marksIn(stop: Stop) {
  return stop.messages.reduce((n, m) => n + m.marks.length, 0);
}

function StopBox({ stop, chosen, onChoose }: { stop: Stop; chosen: boolean; onChoose: () => void }) {
  const marks = marksIn(stop);
  return (
    <button
      type="button"
      onClick={onChoose}
      aria-pressed={chosen}
      className={`flex-1 cursor-pointer border-[1.5px] px-[1ch] py-1 text-left ${
        chosen ? "border-amber bg-amber text-screen" : "border-rule hover:text-pale"
      }`}
    >
      <div>{stopTitle(stop.name)}</div>
      <div className={`text-[12px] ${chosen ? "" : "text-dim"}`}>{stop.outcome}</div>
      {marks > 0 && <div className="text-[12px]">[! {marks} marked]</div>}
    </button>
  );
}

function StopDetail({ stop, trail }: { stop: Stop; trail: DecisionTrail }) {
  return (
    <div className="grid gap-[2ch] md:grid-cols-[1fr_230px]">
      <div className="min-w-0">
        <h3 className="mb-1 font-mono text-[15px] tracking-wider text-pale">
          {stopTitle(stop.name)}: {stop.outcome}
        </h3>
        <p className="mb-4 text-[14px] text-dim">{STOPS[stop.name]?.says}</p>
        {stop.name === "limits" && <LimitsFigures order={trail.order} outcome={stop.outcome} />}
        {stop.name === "order" && <OrderFigures order={trail.order} />}
        {stop.name !== "limits" && stop.name !== "order" && stop.messages.length === 0 && (
          <p className="font-mono text-dim">No messages passed at this stop.</p>
        )}
        <ol>
          {stop.messages.map((m, i) => (
            <MessageBlock key={i} message={m} />
          ))}
        </ol>
      </div>
      <TrailKeyBox keyLines={trail.key} />
    </div>
  );
}

const SENDERS: Record<string, string> = { code: "Code", jev: "Jev", llm: "The LLM" };

// The standing text is long and the same every time; it opens on a click.
const FOLDED = new Set(["instructions", "tools"]);

const MARK_WORDS: Record<string, string> = {
  "refused at the limit": "Refused at the limit: the LLM had used all its lookups (or its time), so code turned this one away",
  "asked again": "Asked again: this reply was not a proper tool call, so code asked the LLM once more",
  "episode never shown": "Episode never shown: the LLM named a past episode it was never shown",
};

function MessageBlock({ message }: { message: Message }) {
  const heading = `${SENDERS[message.sender] ?? message.sender}: ${message.role}`;
  // Word for word: the app's capitals are lifted, so the text reads exactly as it was stored.
  const text = <pre className="overflow-x-auto px-[1.5ch] py-2 font-mono text-[13px] whitespace-pre-wrap normal-case text-pale">{message.text}</pre>;
  return (
    <li className={`mb-3 border-[1.5px] ${message.marks.length ? "border-amber" : "border-grid"}`}>
      {message.marks.map((mark) => (
        <div key={mark} role="note" className="bg-amber px-[1.5ch] py-1 font-mono text-[12.5px] tracking-wider text-screen">
          ! {MARK_WORDS[mark] ?? mark}
        </div>
      ))}
      {FOLDED.has(message.role) ? (
        <details>
          <summary className="cursor-pointer px-[1.5ch] py-1 font-mono text-[12.5px] tracking-wider text-dim">
            {heading} ({message.text.length.toLocaleString("en-US")} characters, click to read)
          </summary>
          {text}
        </details>
      ) : (
        <>
          <div className="px-[1.5ch] pt-1 font-mono text-[12.5px] tracking-wider text-dim">{heading}</div>
          {text}
        </>
      )}
    </li>
  );
}

// With no order carried out, the stop's outcome says what the limits did ("trimmed to nothing
// by the trade risk limit"); the size Jev chose is at the size stop.
function LimitsFigures({ order, outcome }: { order: Order | null; outcome: string }) {
  if (order === null)
    return <p className="mb-4 font-mono text-dim">No order was carried out: {outcome.replaceAll("_", " ")}.</p>;
  return (
    <>
      <FigureRows
        rows={[
          ["Size Jev chose", order.amount_chosen_usd === null ? "--" : dollars(order.amount_chosen_usd)],
          ["Size after the limits", dollars(order.amount_placed_usd)],
          ["Trimmed by", order.limited_by ? limitWords(order.limited_by) : "nothing"],
        ]}
      />
      <p className="mb-4 text-[14px] text-dim">
        A limit is a cap code enforces on the account. If Jev chose $3,000 and a limit allowed only $2,000 more to be
        held, code placed $2,000.
      </p>
    </>
  );
}

function OrderFigures({ order }: { order: Order | null }) {
  if (order === null) return <p className="font-mono text-dim">No order was carried out.</p>;
  return (
    <>
      <FigureRows
        rows={[
          ["Placed", dollars(order.amount_placed_usd)],
          ["Slippage", dollarsAndCents(order.slippage_usd)],
          ["Commission or trading fee", dollarsAndCents(order.commission_or_fee_usd)],
          ["Costs in all", dollarsAndCents(order.slippage_usd + order.commission_or_fee_usd)],
        ]}
      />
      <p className="mb-4 text-[14px] text-dim">
        Slippage: the price filled a little worse than the last one shown. Buying $2,000 at 0.05% above it costs $1.
        Commission or trading fee: what the broker (for a stock) or the exchange (for crypto) charges for the trade, such
        as $1 a stock order whatever its size, or 0.1% of a $1,000 crypto order, $1.
      </p>
    </>
  );
}

// The asset key: which asset each masked ID is, and what a rescaled price is in real dollars.
function TrailKeyBox({ keyLines }: { keyLines: KeyLine[] }) {
  return (
    <aside aria-label="The asset key" className="self-start border-[1.5px] border-rule bg-screen md:sticky md:top-0 font-mono text-[12.5px] tracking-wider">
      <div className="bg-amber px-[1.5ch] py-1 text-screen">The asset key</div>
      <p className="px-[1.5ch] pt-2 text-dim">
        The messages are as the models saw them. Each asset hides behind a masked ID (Apple shows as ASSET_01), and its
        prices are rescaled: multiplied by a scale, so a real $200 at scale 0.5 shows as 100. A real price is the shown
        price divided by the scale.
      </p>
      <ul className="px-[1.5ch] py-2">
        {keyLines.map((k) => (
          <li key={k.masked_id} className="border-b border-grid py-1 last:border-b-0">
            <div className="text-pale">{k.masked_id}</div>
            <div>
              {k.name} ({k.ticker})
            </div>
            <div className="text-dim">
              scale {k.price_scale}: shown 100 is {price(100 / k.price_scale)}
            </div>
          </li>
        ))}
      </ul>
    </aside>
  );
}
