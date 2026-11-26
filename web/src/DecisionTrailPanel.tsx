// The decision trail side panel (spec appendix 7, section 6): opened by a click on a trade, an
// open position or a decision, it shows everything asked and answered on the way to it, as a
// strip of boxes, one per stop. Clicking a stop shows its messages word for word from storage,
// masked IDs and rescaled prices kept, with the key beside them that turns both back into real
// ones (spec appendix 8, section 13).
import { useCallback, useState } from "react";

import { fetchTrail, type DecisionTrail } from "./api/client";
import { AssetTag, ErrorBox, SidePanel } from "./pieces";
import { dayAndTime, dollars, dollarsAndCents, fromApi, price } from "./format";
import { useRead } from "./useRead";

type Stop = DecisionTrail["stops"][number];
type Message = Stop["messages"][number];
type Order = NonNullable<DecisionTrail["order"]>;
type KeyLine = DecisionTrail["key"][number];

// The full strip of each kind, left to right. A trail that stopped early (a closer look that
// picked no trade, a review that held) shows the stops it never reached as empty boxes.
const STRIPS: Record<DecisionTrail["kind"], string[]> = {
  full_evaluation: ["screen", "memory", "pick", "size", "limits", "order"],
  position_review: ["position screen", "memory", "answer", "limits", "order"],
  screen: ["screen"],
  position_screen: ["position screen"],
};

const STOP_TITLES: Record<string, string> = {
  screen: "Screen",
  memory: "Memory",
  pick: "Pick",
  size: "Size",
  limits: "Limits",
  order: "Order",
  "position screen": "Position screen",
  answer: "Jev's answer",
};

const STOP_SAYS: Record<string, string> = {
  screen: "Is a closer look worth it? Jev's cheap yes-or-no question.",
  memory:
    "Which past episodes Jev reads: what the LLM was sent, each lookup it made in memory and what came back, and its answer.",
  pick: "Which trade, if any: Jev's request and answer.",
  size: "How much money Jev chose to put in.",
  limits: "What code trimmed: the size Jev chose, the size after trimming, and which limit trimmed it.",
  order: "The order placed and the costs charged.",
  "position screen": "Is a closer look at this open position worth it? Jev's cheap yes-or-no question.",
  answer: "What to do with the position (hold, close, reduce or add) and how much: Jev's requests and answers.",
};

function kindWords(trail: DecisionTrail) {
  if (trail.kind === "full_evaluation") return "a closer look before a trade";
  if (trail.kind === "position_review") return trail.end_of_session ? "an end-of-session review" : "a position review";
  if (trail.kind === "position_screen") return "a position screen";
  return "a screen";
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

  return (
    <>
      <h2 className="mb-1 text-[1.4rem] leading-tight">
        <AssetTag asset={trail.asset} />: {kindWords(trail)}
      </h2>
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
                  <div>{STOP_TITLES[name] ?? name}</div>
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
      <div>{STOP_TITLES[stop.name] ?? stop.name}</div>
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
          {STOP_TITLES[stop.name] ?? stop.name}: {stop.outcome}
        </h3>
        <p className="mb-4 text-[14px] text-dim">{STOP_SAYS[stop.name]}</p>
        {stop.name === "limits" && <LimitsFigures order={trail.order} />}
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
  "refused at the limit": "Refused at the limit: the LLM had used its 6 lookups (or its time), so code turned this one away",
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

function Figures({ rows }: { rows: [string, string][] }) {
  return (
    <dl className="mb-3 grid grid-cols-[1fr_auto] gap-x-[2ch] gap-y-1 font-mono text-[15px]">
      {rows.map(([name, figure]) => (
        <div key={name} className="contents">
          <dt className="text-dim">{name}</dt>
          <dd className="text-right text-pale">{figure}</dd>
        </div>
      ))}
    </dl>
  );
}

const limitName = (limit: string) => limit.replaceAll("_", " ");

function LimitsFigures({ order }: { order: Order | null }) {
  if (order === null) return <p className="font-mono text-dim">No order was carried out, so nothing was placed.</p>;
  return (
    <>
      <Figures
        rows={[
          ["Size Jev chose", order.amount_chosen_usd === null ? "--" : dollars(order.amount_chosen_usd)],
          ["Size after the limits", dollars(order.amount_placed_usd)],
          ["Trimmed by", order.limited_by ? `the ${limitName(order.limited_by)} limit` : "nothing"],
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
      <Figures
        rows={[
          ["Placed", dollars(order.amount_placed_usd)],
          ["Slippage", dollarsAndCents(order.slippage_usd)],
          ["Commission or fee", dollarsAndCents(order.commission_or_fee_usd)],
          ["Costs in all", dollarsAndCents(order.slippage_usd + order.commission_or_fee_usd)],
        ]}
      />
      <p className="mb-4 text-[14px] text-dim">
        Slippage: the price filled a little worse than the last one shown. Buying $2,000 at 0.05% above it costs $1.
        Commission or fee: what the broker or exchange charges for the trade.
      </p>
    </>
  );
}

// The key: which asset each masked ID is, and what a rescaled price is in real dollars.
function TrailKeyBox({ keyLines }: { keyLines: KeyLine[] }) {
  return (
    <aside aria-label="The key" className="self-start border-[1.5px] border-rule bg-screen md:sticky md:top-0 font-mono text-[12.5px] tracking-wider">
      <div className="bg-amber px-[1.5ch] py-1 text-screen">The key</div>
      <p className="px-[1.5ch] pt-2 text-dim">
        The text above is as the models saw it: masked IDs and rescaled prices. A real price is the shown price divided
        by the scale.
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
