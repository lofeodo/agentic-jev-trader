// Small pieces shared by the sim page and its side panel.
import type { ReactNode } from "react";
import type { AssetName, DecisionLine, LiveFigures, OrderLine, Price } from "./api/client";
import { dollars, price } from "./format";

// The real name leads; the masked ID the agent saw follows as a small tag.
export function AssetTag({ asset }: { asset: AssetName }) {
  return (
    <span>
      <span className="text-pale">{asset.name}</span>{" "}
      <span className="text-[12.5px] text-dim">[{asset.masked_id}]</span>
    </span>
  );
}

const rescaled = (value: number) => new Intl.NumberFormat("en-US", { maximumFractionDigits: 4 }).format(value);

// The real price leads; the rescaled price the agent saw follows in brackets.
export function PriceTag({ price: p }: { price: Price }) {
  return (
    <span>
      {p.real === null ? "--" : price(p.real)}{" "}
      <span className="text-[12.5px] text-dim">[{rescaled(p.rescaled)}]</span>
    </span>
  );
}

// Opens the decision trail of a trade, an open position or a decision; nothing for code's own
// trades (holding), which no decision opened.
export function TrailButton({ decision, onOpenTrail }: { decision: string | null; onOpenTrail: (decision: string) => void }) {
  if (decision === null) return null;
  return (
    <div>
      <button type="button" onClick={() => onOpenTrail(decision)} className="cursor-pointer text-[12.5px] text-dim underline">
        trail
      </button>
    </div>
  );
}

// `text` or `children`: what went wrong, as one paragraph or as the caller lays it out.
export function ErrorBox({ title, text, children }: { title: string; text?: string; children?: ReactNode }) {
  return (
    <div role="alert" className="border-[1.5px] border-rule">
      <div className="bg-amber px-[2ch] py-1 font-mono text-[13.5px] tracking-widest text-screen">{title}</div>
      {text !== undefined && <p className="px-[2ch] py-2 whitespace-pre-line">{text}</p>}
      {children}
    </div>
  );
}

// A form's field label, its input box, and its button.
export const fieldLabel = "font-mono text-[13.5px] tracking-wider text-dim";
export const field = "bg-amber px-[1ch] py-1 font-mono text-screen placeholder:text-screen/60";
export const formButton =
  "cursor-pointer border-[1.5px] border-amber px-[2ch] py-1.5 font-mono tracking-widest text-amber uppercase hover:bg-amber hover:text-screen disabled:cursor-wait disabled:opacity-60";

// A label sharing a box with its value, split by a line.
export function Pair({ name, value }: { name: string; value: string }) {
  return (
    <span className="flex border-[1.5px] border-rule">
      <span className="border-r-[1.5px] border-rule px-[1.5ch] py-1 text-dim">{name}</span>
      <span className="px-[1.5ch] py-1 text-pale">{value}</span>
    </span>
  );
}

// One of a page's key figures, in an outlined box. The first one on a page is the one to read first.
export function KeyFigure({ name, figure, says, first }: { name: string; figure: string; says: string; first?: boolean }) {
  return (
    <div className="border-[1.5px] border-rule px-[2ch] py-3">
      <div className="font-mono text-[13.5px] tracking-wider text-dim">{name}</div>
      <div className={`font-mono text-[1.9rem] leading-tight ${first ? "text-pale" : ""}`}>{figure}</div>
      <div className="text-[14px] text-dim">{says}</div>
    </div>
  );
}

// The kinds of sim, in the order screens list them, each with what it is for.
export const KINDS: { kind: string; title: string; says: string }[] = [
  { kind: "measurement", title: "Measurement", says: "Their results count" },
  { kind: "build-up", title: "Build-up", says: "Fills the base memory; never counts" },
  { kind: "free", title: "Free", says: "Days of your choice; never counts" },
  { kind: "tuning", title: "Tuning", says: "Command-line tool; never counts" },
  { kind: "practice", title: "Practice", says: "Command-line tool; never counts" },
];

// `space`: the room under it; a heading inside a table row has none.
export function SectionHeading({
  number,
  title,
  says,
  space = "mb-4",
}: {
  number: number;
  title: string;
  says: string;
  space?: string;
}) {
  return (
    <div className={`${space} flex items-stretch border-[1.5px] border-rule`}>
      <span className="border-r-[1.5px] border-rule px-[1.6ch] py-2 font-mono text-[15px]">
        {String(number).padStart(2, "0")}
      </span>
      <h2 className="flex flex-1 items-center gap-[2ch] px-[2ch] py-2 text-[1.15rem] tracking-[.14em] whitespace-nowrap after:flex-1 after:border-t-[1.5px] after:border-rule after:content-['']">
        {title}
      </h2>
      <span className="self-center pr-[2ch] font-mono text-[13.5px] tracking-wider whitespace-nowrap text-dim">{says}</span>
    </div>
  );
}

// What long, short and a stop price mean, in plain words with dollars.
export function DirectionWords() {
  return (
    <p className="mt-2 font-mono text-[12.5px] tracking-wider text-dim">
      Long: a bet the price rises. Buy $1,000 of a stock at $100 a share; at $110 it is worth $1,100,
      +$100. Short: a bet it falls. Borrow shares and sell them for $1,000 at $100; buy them back at
      $90 for $900 and keep the $100 gap. Stop price: where code closes a losing trade. Long at $100
      with a stop price of $97, the most lost is about $3 a share.
    </p>
  );
}

export function statusWords(sim: Pick<LiveFigures, "status" | "stop_reason" | "not_responding">) {
  if (sim.not_responding) return "Not responding";
  if (sim.status === "stopped" && sim.stop_reason) return `Stopped: ${sim.stop_reason}`;
  if (sim.status === "failed") return "Failed";
  return sim.status;
}

const LIMITS: Record<string, string> = {
  daily_loss: "the daily loss limit was reached",
  session_end: "too close to the stock market's close",
  forced_close: "a forced close was waiting",
};

// One decision in plain words: "Jev's screen: 31% worth a closer look; did nothing".
export function decisionWords(d: DecisionLine) {
  const action = d.action === "nothing" ? "did nothing" : d.action;
  if (d.tier === 0) {
    const why = d.skipped_because ? (LIMITS[d.skipped_because] ?? d.skipped_because) : "code alone";
    return `Not asked: ${why}; ${action}`;
  }
  const share = d.screen_answer === null ? "--" : `${Math.round(d.screen_answer * 100)}%`;
  return `Jev's ${d.kind}: ${share} worth a closer look; ${action}`;
}

const REASONS: Record<string, string> = {
  jev: "Jev chose it",
  stop_price: "its stop price was reached",
  forced_close: "a forced close",
  sim_ended: "closed because the sim ended",
  buy_hold: "holding buys once",
};

// One order in plain words: "bought $2,000 (Jev chose it)", "sell waiting for the next bar".
export function orderWords(o: OrderLine) {
  const reason = REASONS[o.reason] ?? o.reason;
  const what = o.kind === "entry" ? "opened" : o.kind === "add" ? "added to" : o.kind === "reduce" ? "made smaller" : "closed";
  if (o.status === "waiting") return `${what}: waiting for the next bar (${reason})`;
  if (o.status === "cancelled") return `${what}: cancelled${o.limited_by ? ` by the ${o.limited_by.replace("_", " ")} limit` : ""}`;
  const side = o.side === "buy" ? "bought" : "sold";
  const value = o.value_usd === null ? "" : ` ${dollars(o.value_usd)}`;
  const trimmed = o.limited_by && o.amount_chosen !== null ? `; Jev chose ${dollars(o.amount_chosen)}, trimmed by the ${o.limited_by.replace("_", " ")} limit` : "";
  return `${what}: ${side}${value} (${reason}${trimmed})`;
}
