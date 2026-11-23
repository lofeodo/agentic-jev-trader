import type { SimLine } from "./api/client";
import { day, dollars, dollarsAndCents, signedDollars } from "./format";

const KINDS: { kind: string; title: string; says: string }[] = [
  { kind: "measurement", title: "Measurement", says: "Their results count" },
  { kind: "build-up", title: "Build-up", says: "Fills the base memory; never counts" },
  { kind: "free", title: "Free", says: "Days of your choice; never counts" },
  { kind: "tuning", title: "Tuning", says: "Command-line tool; never counts" },
  { kind: "practice", title: "Practice", says: "Command-line tool; never counts" },
];

const COLUMNS = ["Sim", "Status", "Days", "Account value", "Against holding", "Trades", "Spent / cap"];
const cell = "py-[.42rem] pr-[2ch] align-top font-mono text-base";
const number = `${cell} text-right whitespace-nowrap`;

function statusWords(sim: SimLine) {
  if (sim.not_responding) return "Not responding";
  if (sim.status === "stopped" && sim.stop_reason) return `Stopped: ${sim.stop_reason}`;
  if (sim.status === "failed") return "Failed";
  return sim.status;
}

function Line({ sim }: { sim: SimLine }) {
  const gap = sim.holding_value === null ? null : sim.account_value - sim.holding_value;
  return (
    <tr className="hover:bg-amber hover:text-screen [&:hover_*]:text-screen">
      <td className={cell}>
        <div>{sim.name}</div>
        <div className="text-[13.5px] tracking-wider text-dim">
          {sim.first_day && sim.last_day && `${day(sim.first_day)} to ${day(sim.last_day)} UTC / `}
          steps {sim.first_step} to {sim.last_step}
        </div>
        <div className="text-[13.5px] tracking-wider text-dim">
          {sim.assets.map((asset, i) => (
            <span key={asset.masked_id}>
              {i > 0 && " / "}
              <span className="text-amber">{asset.name}</span> [{asset.masked_id}]
            </span>
          ))}
        </div>
      </td>
      <td className={`${cell} whitespace-nowrap`}>{statusWords(sim)}</td>
      <td className={number}>
        {sim.days_done} of {sim.days_total}
      </td>
      <td className={`${number} text-pale`}>{dollars(sim.account_value)}</td>
      <td className={number}>{gap === null ? "--" : signedDollars(gap)}</td>
      <td className={number}>{sim.trades}</td>
      <td className={number}>
        {dollarsAndCents(sim.spent_usd)}{" "}
        <span className="text-dim">
          / {sim.spending_cap_usd === null ? "no cap" : dollarsAndCents(sim.spending_cap_usd)}
        </span>
      </td>
    </tr>
  );
}

function Group({ number: n, title, says, sims }: { number: number; title: string; says: string; sims: SimLine[] }) {
  return (
    <tbody>
      <tr>
        <td colSpan={COLUMNS.length} className="pt-7 pb-2">
          <div className="flex items-stretch border-[1.5px] border-rule">
            <span className="border-r-[1.5px] border-rule px-[1.6ch] py-2 font-mono text-[15px]">
              {String(n).padStart(2, "0")}
            </span>
            <h2 className="flex flex-1 items-center gap-[2ch] px-[2ch] py-2 text-[1.15rem] tracking-[.14em] whitespace-nowrap after:flex-1 after:border-t-[1.5px] after:border-rule after:content-['']">
              {title}
            </h2>
            <span className="self-center pr-[2ch] font-mono text-[13.5px] tracking-wider whitespace-nowrap text-dim">
              {says}
            </span>
          </div>
        </td>
      </tr>
      {sims.map((sim) => (
        <Line key={sim.id} sim={sim} />
      ))}
    </tbody>
  );
}

export function SimsScreen({ sims, error }: { sims: SimLine[] | null; error: string | null }) {
  const groups = KINDS.map((group) => ({
    ...group,
    sims: (sims ?? []).filter((sim) => sim.kind === group.kind),
  })).filter((group) => group.sims.length > 0);

  return (
    <section>
      <h1 className="mb-1 text-center text-[2.1rem] leading-tight tracking-[.02em]">
        Trading sims
      </h1>
      <p className="mb-6 text-center text-[1.1rem] text-dim">
        Every sim, against simply holding the five assets
      </p>

      {error && (
        <div role="alert" className="mb-6 border-[1.5px] border-rule">
          <div className="bg-amber px-[2ch] py-1 font-mono text-[13.5px] tracking-widest text-screen">
            Cannot reach the API
          </div>
          <p className="px-[2ch] py-2">{error}. Asking again shortly.</p>
        </div>
      )}

      {sims === null && !error && <p className="text-center font-mono text-dim">Loading...</p>}

      {sims !== null && sims.length === 0 && (
        <div className="border-[1.5px] border-rule px-[2ch] py-10 text-center">
          <p className="text-[1.2rem] text-pale">No trading sims yet</p>
          <p className="mt-1 text-dim">
            A sim of holding the five assets is the comparison line, so it is not listed here.
          </p>
        </div>
      )}

      {groups.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full border-separate border-spacing-0">
            <thead>
              <tr>
                {COLUMNS.map((name, i) => (
                  <th
                    key={name}
                    scope="col"
                    className={`border-b border-rule py-[.4rem] pr-[2ch] font-mono text-[13.5px] font-light tracking-wider text-dim ${i < 2 ? "text-left" : "text-right"}`}
                  >
                    {name}
                  </th>
                ))}
              </tr>
            </thead>
            {groups.map((group, i) => (
              <Group key={group.kind} number={i + 1} title={group.title} says={group.says} sims={group.sims} />
            ))}
          </table>
          <p className="mt-4 font-mono text-[13.5px] tracking-wider text-dim">
            Against holding: the sim's account value minus what holding the five assets was worth at
            the same moment. +$41 means the sim is $41 ahead.
          </p>
        </div>
      )}
    </section>
  );
}
