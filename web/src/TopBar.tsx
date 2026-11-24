import type { SpendingTotal } from "./api/client";
import { dollarsAndCents } from "./format";

// Only Trading sims exists so far; the rest of the menu is shown dimmed until it is built.
const LATER_SCREENS = ["Comparison", "Datasets", "Playbook", "Spending"];

export function TopBar({ spending }: { spending: SpendingTotal | null }) {
  return (
    <header className="font-mono text-[13.5px] tracking-widest">
      <div className="flex flex-wrap items-stretch border-[1.5px] border-rule">
        <span className="border-r-[1.5px] border-rule px-[2ch] py-2">Jev/Trader</span>
        <nav className="mr-auto flex flex-wrap" aria-label="Screens">
          <a
            href="#/"
            aria-current="page"
            className="border-r-[1.5px] border-rule bg-amber px-[2ch] py-2 text-screen"
          >
            Trading sims
          </a>
          {LATER_SCREENS.map((screen) => (
            <span
              key={screen}
              title="Not built yet"
              className="border-r-[1.5px] border-rule px-[2ch] py-2 text-dim"
            >
              {screen}
            </span>
          ))}
        </nav>
        <span className="self-center px-[2ch] py-2 text-dim">
          Models:{" "}
          <b className="font-normal text-amber">
            {spending ? dollarsAndCents(spending.spent_usd) : "..."}
          </b>
          {spending && ` of ${dollarsAndCents(spending.ceiling_usd)} spent`}
        </span>
      </div>
      <div className="mb-11 flex w-fit border-x-[1.5px] border-b-[1.5px] border-rule">
        <span className="border-r-[1.5px] border-rule px-[2ch] py-1.5 text-dim">Command:</span>
        <span className="py-1.5 pl-[2ch]">Read only: sims start from the command line</span>
        <kbd className="px-[2ch] py-1.5 pl-[1ch] font-mono">&lt;GO&gt;</kbd>
      </div>
    </header>
  );
}
