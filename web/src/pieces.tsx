// Small pieces shared by the sim page and its side panel.
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

export function ErrorBox({ title, text }: { title: string; text: string }) {
  return (
    <div role="alert" className="border-[1.5px] border-rule">
      <div className="bg-amber px-[2ch] py-1 font-mono text-[13.5px] tracking-widest text-screen">{title}</div>
      <p className="px-[2ch] py-2">{text}</p>
    </div>
  );
}

export function SectionHeading({ number, title, says }: { number: number; title: string; says: string }) {
  return (
    <div className="mb-4 flex items-stretch border-[1.5px] border-rule">
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

export function statusWords(sim: Pick<LiveFigures, "status" | "stop_reason" | "not_responding">) {
  if (sim.not_responding) return "Not responding";
  if (sim.status === "stopped" && sim.stop_reason) return `Stopped: ${sim.stop_reason}`;
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
